"""APP-01A: kernel-resolved app path, seal and inert build-only probe."""
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'tools/macos/kronos_launcher.c'


def compile_source(source, destination):
    unit = destination.parent / 'unit.c'
    unit.write_text(source)
    subprocess.run(['clang', '-Wall', '-Wextra', '-Werror', str(unit), '-o', str(destination)],
                   check=True, capture_output=True)
    unit.unlink()


@pytest.fixture
def guarded_bundle(tmp_path):
    app = tmp_path / 'Applications/KRONOS.app'
    exe = app / 'Contents/MacOS/KRONOS'
    exe.parent.mkdir(parents=True)
    info = dict(CFBundleIdentifier='com.project-kronos.browser-v1', CFBundleExecutable='KRONOS',
                CFBundleName='KRONOS', CFBundlePackageType='APPL')
    (app / 'Contents/Info.plist').write_bytes(plistlib.dumps(info))
    source = SOURCE.read_text().replace('"/Applications/KRONOS.app"', json.dumps(str(app)))
    source = source.replace('"/Applications/KRONOS.app/Contents/MacOS/KRONOS"', json.dumps(str(exe)))
    # This isolated compiled harness can ONLY validate. The production main is
    # never called; there is no production build flag or environment override.
    source = source.replace('int main(void) {', 'int unused_application_main(void) {')
    source += '\nint main(void) { return canonical_operational_image() ? 0 : 1; }\n'
    compile_source(source, exe)
    subprocess.run(['codesign', '--force', '--sign', '-', '--timestamp=none', str(app)],
                   check=True, capture_output=True)
    return app, exe


def result(exe, **kwargs):
    return subprocess.run([str(exe)], capture_output=True, timeout=10, **kwargs).returncode


def test_canonical_resolved_image_and_signature(guarded_bundle):
    _, exe = guarded_bundle
    assert result(exe) == 0


@pytest.mark.parametrize('kind', ['repository', 'output', 'qualification', 'rollback', 'installer-evidence'])
def test_noncanonical_copy_fails_closed(guarded_bundle, tmp_path, kind):
    app, _ = guarded_bundle
    copy = tmp_path / kind / 'KRONOS.app'
    shutil.copytree(app, copy)
    assert result(copy / 'Contents/MacOS/KRONOS') == 1


def test_alias_resolves_to_canonical_only(guarded_bundle, tmp_path):
    app, exe = guarded_bundle
    alias = tmp_path / 'launcher-alias'
    alias.symlink_to(exe)
    assert result(alias) == 0  # actual executable remains the canonical one
    other = tmp_path / 'other/KRONOS.app'
    shutil.copytree(app, other)
    alias.unlink(); alias.symlink_to(other / 'Contents/MacOS/KRONOS')
    assert result(alias) == 1


def test_canonical_symlink_to_external_bundle_rejected(guarded_bundle, tmp_path):
    app, exe = guarded_bundle
    other = tmp_path / 'external.app'
    app.rename(other); app.symlink_to(other, target_is_directory=True)
    assert result(exe) == 1


def test_missing_canonical_app_rejects_other_copy(guarded_bundle, tmp_path):
    app, _ = guarded_bundle
    moved = tmp_path / 'moved.app'; app.rename(moved)
    assert result(moved / 'Contents/MacOS/KRONOS') == 1


@pytest.mark.parametrize('tamper', ['resource', 'wrong-identifier', 'unsigned'])
def test_canonical_identity_and_signature_rejection(guarded_bundle, tamper):
    app, exe = guarded_bundle
    if tamper == 'resource':
        with (app / 'Contents/Info.plist').open('ab') as stream: stream.write(b'\nchanged')
    elif tamper == 'wrong-identifier':
        info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
        info['CFBundleIdentifier'] = 'com.example.not-kronos'
        (app / 'Contents/Info.plist').write_bytes(plistlib.dumps(info))
        subprocess.run(['codesign', '--force', '--sign', '-', str(app)], check=True, capture_output=True)
    else:
        subprocess.run(['codesign', '--remove-signature', str(exe)], check=True, capture_output=True)
    assert result(exe) != 0


@pytest.mark.parametrize('environment', [{}, {'KRONOS_CANONICAL_PATH': '/tmp'},
    {'KRONOS_LAUNCH_MODE': 'LEGACY_BOOTSTRAP', 'KRONOS_LEGACY_BOOTSTRAP_ID': 'a'*64,
     'KRONOS_LEGACY_BOOTSTRAP_PROOF': 'b'*64}])
def test_real_main_rejects_noncanonical_before_any_runtime_access(tmp_path, environment):
    exe = tmp_path / 'launcher'
    compile_source(SOURCE.read_text(), exe)
    assert result(exe, env=environment) == 1


def test_build_probe_exits_without_operational_authority(tmp_path):
    exe = tmp_path / 'launcher'
    compile_source(SOURCE.read_text(), exe)
    p = subprocess.run([str(exe)], env={'KRONOS_LAUNCH_MODE': 'PACKAGE_VERIFY'},
                       capture_output=True, timeout=5)
    assert p.returncode == 0 and p.stdout == b'KRONOS_LAUNCHER_PACKAGE_V1_OK\n'


def test_historical_inode_acl_denies_execution_without_byte_or_mode_change(tmp_path):
    exe = tmp_path / 'historical-inert'
    compile_source('int main(void) {return 0;}\n', exe)
    original, mode = exe.read_bytes(), exe.stat().st_mode
    subprocess.run(['/bin/chmod', '+a#', '0', 'everyone deny execute', str(exe)], check=True)
    alias = tmp_path / 'alias'; alias.symlink_to(exe)
    for path in (exe, alias):
        assert not os.access(path, os.X_OK)
        with pytest.raises(PermissionError):result(path)
    assert exe.read_bytes() == original and exe.stat().st_mode == mode
    subprocess.run(['/bin/chmod', '-a#', '0', str(exe)], check=True)
    assert result(exe) == 0 and exe.read_bytes() == original
