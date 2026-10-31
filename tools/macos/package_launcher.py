"""Strictly sealed launcher artifacts and non-launching atomic installation.

Building is engineering; installing requires a separately authorized call. No
function stops a runtime, calls HTTP, or invokes LaunchServices.
"""
from __future__ import annotations

import argparse
import ctypes
from hashlib import sha256
import json
import os
from pathlib import Path
import plistlib
import shutil
import stat
import subprocess
import tempfile
import zipfile
from xml.parsers.expat import ExpatError

FLAGS = ('-Wall', '-Wextra', '-Werror', '-O2', '-mmacosx-version-min=13.0')
BINARY = 'Contents/MacOS/KRONOS'
RESOURCES = ('Contents/Info.plist', 'Contents/Resources/KRONOS.icns', 'Contents/Resources/KRONOS.png')


class PackageError(ValueError):
    pass


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def safe_path(path):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts or any(p.is_symlink() for p in (path, *path.parents)):
        raise PackageError('PACKAGE_PATH_REJECTED')
    return path


def manifest(bundle):
    bundle = safe_path(bundle)
    if not bundle.is_dir():
        raise PackageError('PACKAGE_BUNDLE_MISSING')
    metadata = bundle.stat()
    if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o755:
        raise PackageError('PACKAGE_BUNDLE_OWNER_OR_MODE_INVALID')
    rows = []
    for path in sorted(bundle.rglob('*')):
        safe_path(path)
        s = path.lstat()
        if s.st_uid != os.getuid() or not (stat.S_ISREG(s.st_mode) or stat.S_ISDIR(s.st_mode)):
            raise PackageError('PACKAGE_OWNER_OR_TYPE_INVALID')
        mode = stat.S_IMODE(s.st_mode)
        expected = 0o755 if path.is_dir() or path.relative_to(bundle).as_posix() == BINARY else 0o644
        if mode != expected:
            raise PackageError('PACKAGE_MODE_INVALID')
        rows.append({'path': path.relative_to(bundle).as_posix(), 'mode': mode,
                     'sha256': digest(path) if path.is_file() else None})
    return rows


def identity(bundle):
    return sha256(canonical(manifest(bundle))).hexdigest()


def run(*args, **kwargs):
    try:
        return subprocess.run(args, check=True, capture_output=True, timeout=60, **kwargs)
    except (subprocess.SubprocessError, OSError):
        raise PackageError('PACKAGE_COMMAND_FAILED') from None


def verify(bundle, expected_identity=None):
    bundle = safe_path(bundle)
    rows = manifest(bundle)
    files = {r['path'] for r in rows if r['sha256'] is not None}
    if files != {*RESOURCES, BINARY, 'Contents/_CodeSignature/CodeResources'}:
        raise PackageError('PACKAGE_CONTENTS_INVALID')
    try:
        info = plistlib.loads((bundle / RESOURCES[0]).read_bytes())
    except (ValueError, ExpatError):
        raise PackageError('PACKAGE_INFO_INVALID') from None
    if (info.get('CFBundleIdentifier') != 'com.project-kronos.browser-v1'
        or info.get('CFBundleExecutable') != 'KRONOS' or info.get('CFBundlePackageType') != 'APPL'
        or info.get('CFBundleIconFile') != 'KRONOS' or info.get('LSMinimumSystemVersion') != '13.0'):
        raise PackageError('PACKAGE_INFO_INVALID')
    actual = sha256(canonical(rows)).hexdigest()
    if expected_identity is not None and actual != expected_identity:
        raise PackageError('PACKAGE_IDENTITY_MISMATCH')
    run('/usr/bin/codesign', '--verify', '--strict', '--verbose=2', str(bundle))
    return actual


def archive(bundle, destination):
    """Canonical ZIP metadata; signing/compiler determinism measured separately."""
    destination = safe_path(destination)
    with zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_STORED) as z:
        for row in manifest(bundle):
            name = bundle.name + '/' + row['path']
            if row['sha256'] is None:
                name += '/'
            item = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            item.create_system = 3
            item.external_attr = ((stat.S_IFDIR if row['sha256'] is None else stat.S_IFREG) | row['mode']) << 16
            z.writestr(item, b'' if row['sha256'] is None else (bundle / row['path']).read_bytes())
    return digest(destination)


def build(repository, output):
    repository, output = safe_path(repository), safe_path(output)
    output.mkdir(mode=0o700)  # Exclusive build destination; never overwrite artifacts.
    bundle = output / 'KRONOS.app'
    (bundle / 'Contents/MacOS').mkdir(parents=True)
    (bundle / 'Contents/Resources').mkdir()
    template = repository / 'tools/macos/KRONOS.app'
    for item in RESOURCES:
        shutil.copyfile(safe_path(template / item), bundle / item)
    source = safe_path(repository / 'tools/macos/kronos_launcher.c')
    run('/usr/bin/clang', *FLAGS, str(source), '-o', str(bundle / BINARY))
    built = digest(bundle / BINARY)
    for path in (bundle, *bundle.rglob('*')):
        path.chmod(0o755 if path.is_dir() or path == bundle / BINARY else 0o644)
    # Seal last, after Info.plist/resources and executable bytes are final.
    run('/usr/bin/codesign', '--force', '--sign', '-', '--timestamp=none', str(bundle))
    sealed = verify(bundle)
    environment = {'PATH': '/usr/bin:/bin', 'KRONOS_LAUNCH_MODE': 'PACKAGE_VERIFY'}
    probe = run(str(bundle / BINARY), env=environment)
    if probe.stdout != b'KRONOS_LAUNCHER_PACKAGE_V1_OK\n':
        raise PackageError('PACKAGE_EXECUTION_REJECTED')
    record = {'schema': 'KRONOS_LAUNCHER_PACKAGE_V1',
        'source_revision': run('git', '-C', str(repository), 'rev-parse', 'HEAD').stdout.decode().strip(),
        'source_state': 'DIRTY_WORKTREE' if run('git', '-C', str(repository), 'status', '--porcelain').stdout else 'CLEAN_COMMIT',
        'source_launcher_sha256': digest(source), 'previous_tracked_binary_sha256': digest(template / BINARY),
        'built_binary_sha256': built, 'signed_binary_sha256': digest(bundle / BINARY),
        'procedure_sha256': digest(Path(__file__).resolve()), 'compiler_flags': FLAGS,
        'compiler': run('/usr/bin/clang', '--version').stdout.decode().strip(),
        'signing': 'AD_HOC; timestamp=none; no entitlements; resources sealed',
        'strict_verification': 'PASS', 'isolated_execution': 'PASS',
        'bundle_identity': sealed, 'bundle_manifest': manifest(bundle),
        'archive_sha256': archive(bundle, output / 'KRONOS-launcher.zip')}
    (output / 'manifest.json').write_bytes(canonical(record) + b'\n')
    return record


def exchange(left, right):
    """macOS renamex_np(RENAME_SWAP): exchange both directories atomically."""
    libc = ctypes.CDLL(None, use_errno=True)
    function = libc.renamex_np
    function.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint)
    function.restype = ctypes.c_int
    if function(os.fsencode(left), os.fsencode(right), 0x00000002) != 0:
        raise PackageError('PACKAGE_ATOMIC_EXCHANGE_FAILED')


def sync_tree(bundle):
    for p in (bundle, *bundle.rglob('*')):
        fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def install(candidate, destination, *, candidate_identity, installed_identity, rollback,
            swap=exchange, verifier=verify):
    """Future authorized installation only. Never launch. Tests use temporary apps.

    The manifest identities must have been independently approved; the package
    does not attest itself. The rollback artifact is retained before any swap.
    """
    if any(not isinstance(value, str) or len(value) != 64
           or any(c not in '0123456789abcdef' for c in value)
           for value in (candidate_identity, installed_identity)):
        raise PackageError('PACKAGE_APPROVED_IDENTITIES_REQUIRED')
    candidate, destination, rollback = map(safe_path, (candidate, destination, rollback))
    locations = (candidate, destination, rollback)
    if rollback.exists() or any(a == b or a in b.parents or b in a.parents
                               for i, a in enumerate(locations) for b in locations[i+1:]):
        raise PackageError('PACKAGE_INSTALL_PATH_INVALID')
    verifier(candidate, candidate_identity)
    verifier(destination, installed_identity)
    shutil.copytree(destination, rollback)
    verifier(rollback, installed_identity)
    sync_tree(rollback)
    stage_root = Path(tempfile.mkdtemp(prefix='.kronos-install-', dir=destination.parent))
    staged = stage_root / 'KRONOS.app'
    shutil.copytree(candidate, staged)
    verifier(staged, candidate_identity)
    sync_tree(staged)
    # Recheck the live target at the last safe point before replacement.
    verifier(destination, installed_identity)
    swap(staged, destination)
    try:
        verifier(destination, candidate_identity)
        sync_tree(destination)
    except Exception:
        # Restore the exact directory exchanged out, not a reconstructed bundle.
        swap(staged, destination)
        verifier(destination, installed_identity)
        raise PackageError('PACKAGE_INSTALL_ROLLED_BACK') from None
    # The exchanged-out original is also retained; no rollback deletion here.
    return {'installed_identity': candidate_identity, 'rollback_identity': installed_identity,
            'rollback': str(rollback), 'exchanged_original': str(staged), 'launched': False}


def main():
    parser = argparse.ArgumentParser(description='Build a sealed launcher; does not install or launch KRONOS.')
    parser.add_argument('--repository', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.repository, args.output), indent=2))


if __name__ == '__main__':
    main()
