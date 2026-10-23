"""Strictly sealed launcher artifacts and non-launching atomic installation.

Building is engineering; installing requires a separately authorized call. No
function stops a runtime, calls HTTP, or invokes LaunchServices.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
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


def _descriptor_identity(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_gid, value.st_nlink, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns)


@contextmanager
def _governed_package_root(bundle, budget):
    """No-follow package root; shared ancestor identity is not sibling state."""
    path=Path(bundle)
    if not path.is_absolute() or '..' in path.parts:
        raise PackageError('PACKAGE_PATH_REJECTED')
    descriptors=[];chain=[]
    def ancestor(value):
        return (value.st_dev,value.st_ino,value.st_mode,value.st_uid,value.st_gid)
    try:
        budget.check()
        fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
        descriptors.append(fd)
        for part in path.parts[1:]:
            budget.check()
            named=os.stat(part,dir_fd=fd,follow_symlinks=False)
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
            descriptors.append(child);opened=os.fstat(child)
            if ancestor(named)!=ancestor(opened):
                raise PackageError('PACKAGE_GOVERNED_PATH_CHANGED')
            chain.append((fd,part,child,ancestor(opened)));fd=child
        before=os.fstat(fd)
        if before.st_uid!=os.getuid() or stat.S_IMODE(before.st_mode)!=0o755:
            raise PackageError('PACKAGE_BUNDLE_OWNER_OR_MODE_INVALID')
        yield fd
        budget.check()
        if _descriptor_identity(os.fstat(fd))!=_descriptor_identity(before):
            raise PackageError('PACKAGE_GOVERNED_PATH_CHANGED')
        for parent,name,child,identity in chain:
            budget.check()
            if (ancestor(os.fstat(child))!=identity
                    or ancestor(os.stat(name,dir_fd=parent,follow_symlinks=False))!=identity):
                raise PackageError('PACKAGE_GOVERNED_PATH_CHANGED')
    except OSError:
        raise PackageError('PACKAGE_GOVERNED_PATH_REJECTED') from None
    finally:
        for fd in reversed(descriptors):os.close(fd)


def read_governed_member(bundle, relative, expected, *, budget):
    """Capture only the two fixed native members within exact retained bounds."""
    if (relative not in {BINARY,'Contents/_CodeSignature/CodeResources'}
            or type(expected) is not bytes or not 0<len(expected)<=64*1024*1024):
        raise PackageError('PACKAGE_GOVERNED_MEMBER_BOUND')
    with _governed_package_root(bundle,budget) as root:
        descriptors=[];chain=[];parent=root
        try:
            for part in relative.split('/')[:-1]:
                budget.check()
                child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
                descriptors.append(child);observed=os.fstat(child)
                if (observed.st_uid!=os.getuid() or stat.S_IMODE(observed.st_mode)!=0o755
                        or _descriptor_identity(os.stat(part,dir_fd=parent,follow_symlinks=False))!=_descriptor_identity(observed)):
                    raise PackageError('PACKAGE_GOVERNED_MEMBER_CHANGED')
                chain.append((parent,part,child,_descriptor_identity(observed)));parent=child
            name=relative.split('/')[-1];budget.check()
            fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK,dir_fd=parent)
            descriptors.append(fd);before=os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_uid!=os.getuid() or before.st_nlink!=1
                    or stat.S_IMODE(before.st_mode)!=(0o755 if relative==BINARY else 0o644)
                    or before.st_size!=len(expected)
                    or _descriptor_identity(os.stat(name,dir_fd=parent,follow_symlinks=False))!=_descriptor_identity(before)):
                raise PackageError('PACKAGE_GOVERNED_MEMBER_CHANGED')
            blocks=[];length=0
            while True:
                budget.check();block=os.read(fd,min(65536,len(expected)+1-length))
                if not block:break
                blocks.append(block);length+=len(block)
                if length>len(expected):raise PackageError('PACKAGE_GOVERNED_MEMBER_CHANGED')
            budget.check();raw=b''.join(blocks)
            if (raw!=expected or _descriptor_identity(os.fstat(fd))!=_descriptor_identity(before)
                    or _descriptor_identity(os.stat(name,dir_fd=parent,follow_symlinks=False))!=_descriptor_identity(before)):
                raise PackageError('PACKAGE_GOVERNED_MEMBER_CHANGED')
            for directory,part,child,identity in chain:
                if (_descriptor_identity(os.fstat(child))!=identity
                        or _descriptor_identity(os.stat(part,dir_fd=directory,follow_symlinks=False))!=identity):
                    raise PackageError('PACKAGE_GOVERNED_MEMBER_CHANGED')
            return raw
        except OSError:
            raise PackageError('PACKAGE_GOVERNED_MEMBER_REJECTED') from None
        finally:
            for fd in reversed(descriptors):os.close(fd)


def _descriptor_manifest(root, budget):
    """The native manifest shape, read once through retained no-follow FDs."""
    rows = []; remaining = [4096, 64 * 1024 * 1024]
    def walk(fd, prefix=''):
        budget.check(); before = os.fstat(fd)
        if before.st_uid != os.getuid() or stat.S_IMODE(before.st_mode) != 0o755:
            raise PackageError('PACKAGE_RETAINED_OWNER_OR_MODE')
        names = sorted(os.listdir(fd))
        for name in names:
            budget.check(); remaining[0] -= 1
            if remaining[0] < 0:
                raise PackageError('PACKAGE_RETAINED_BOUND')
            relative = prefix + name
            named = os.stat(name, dir_fd=fd, follow_symlinks=False)
            directory = stat.S_ISDIR(named.st_mode)
            if not directory and not stat.S_ISREG(named.st_mode):
                raise PackageError('PACKAGE_RETAINED_TYPE')
            child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
                            (os.O_DIRECTORY if directory else 0), dir_fd=fd)
            try:
                opened = os.fstat(child)
                expected = 0o755 if directory or relative == BINARY else 0o644
                if (_descriptor_identity(opened) != _descriptor_identity(named)
                        or opened.st_uid != os.getuid()
                        or stat.S_IMODE(opened.st_mode) != expected
                        or (not directory and opened.st_nlink != 1)):
                    raise PackageError('PACKAGE_RETAINED_CHANGED')
                if directory:
                    rows.append(dict(path=relative, mode=expected, sha256=None))
                    walk(child, relative + '/')
                else:
                    remaining[1] -= opened.st_size
                    if remaining[1] < 0:
                        raise PackageError('PACKAGE_RETAINED_BOUND')
                    digest = sha256(); length = 0
                    while True:
                        budget.check(); block = os.read(child, 65536)
                        if not block: break
                        length += len(block); digest.update(block)
                        if length > opened.st_size:
                            raise PackageError('PACKAGE_RETAINED_CHANGED')
                    if length != opened.st_size:
                        raise PackageError('PACKAGE_RETAINED_CHANGED')
                    rows.append(dict(path=relative, mode=expected, sha256=digest.hexdigest()))
                if (_descriptor_identity(os.fstat(child)) != _descriptor_identity(opened)
                        or _descriptor_identity(os.stat(name, dir_fd=fd, follow_symlinks=False))
                           != _descriptor_identity(opened)):
                    raise PackageError('PACKAGE_RETAINED_CHANGED')
            finally:
                os.close(child)
        if _descriptor_identity(os.fstat(fd)) != _descriptor_identity(before):
            raise PackageError('PACKAGE_RETAINED_CHANGED')
    walk(root)
    return sorted(rows, key=lambda row: row['path'])


@contextmanager
def retained_install_package(approved_identities, *, budget):
    """Locate only the installer's retained exchanged original, without effects.

    The fixed canonical install parent and existing .kronos-install-* layout
    locate bytes; exact independently approved manifest identities select them.
    No caller path, newest-file rule, installation or rollback is introduced.
    The named descriptor chain stays unchanged through the consumer's native
    signature verification. Absence yields None; ambiguity/unsafe bytes deny.
    """
    from tools.runtime_source_gate import CANONICAL
    identities = frozenset(approved_identities)
    if (not identities or any(type(value) is not str or len(value) != 64
            or any(c not in '0123456789abcdef' for c in value) for value in identities)):
        raise PackageError('PACKAGE_APPROVED_IDENTITIES_REQUIRED')
    parent = Path(CANONICAL).parent
    if not parent.is_absolute() or '..' in parent.parts:
        raise PackageError('PACKAGE_PATH_REJECTED')
    descriptors = []; chain = []; selected = None
    def ancestry_identity(value):
        return (value.st_dev,value.st_ino,value.st_mode,value.st_uid,value.st_gid)
    def open_child(fd, name, *, strict=True):
        child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
        descriptors.append(child); observed = os.fstat(child)
        identity=_descriptor_identity if strict else ancestry_identity
        if identity(observed) != identity(os.stat(name, dir_fd=fd, follow_symlinks=False)):
            raise PackageError('PACKAGE_RETAINED_CHANGED')
        chain.append((fd, name, child, identity(observed),strict))
        return child
    def unchanged():
        budget.check()
        for fd, name, child, identity,strict in chain:
            snapshot=_descriptor_identity if strict else ancestry_identity
            reopened = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            try:
                if (snapshot(os.fstat(child)) != identity
                        or snapshot(os.fstat(reopened)) != identity):
                    raise PackageError('PACKAGE_RETAINED_CHANGED')
            finally: os.close(reopened)
    try:
        root = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(root)
        for index,part in enumerate(parent.parts[1:]):
            # Shared ancestors (for example /private/var/.../T) may acquire
            # unrelated siblings. Keep their exact vnode/type/owner/mode;
            # retain full metadata for the selected install parent and below.
            root = open_child(root, part,strict=index==len(parent.parts)-2)
        names = sorted(os.listdir(root))
        if len(names) > 4096:
            raise PackageError('PACKAGE_RETAINED_BOUND')
        matches = []
        for name in names:
            budget.check()
            if not name.startswith('.kronos-install-'): continue
            stage = open_child(root, name); info = os.fstat(stage)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise PackageError('PACKAGE_RETAINED_STAGE_INVALID')
            bundle = open_child(stage, 'KRONOS.app')
            rows = _descriptor_manifest(bundle, budget)
            identity = sha256(canonical(rows)).hexdigest()
            if identity in identities:
                matches.append((parent / name / 'KRONOS.app', identity, bundle, rows))
        if len(matches) > 1:
            raise PackageError('PACKAGE_RETAINED_AMBIGUOUS')
        unchanged()
        if matches:
            selected = matches[0]
            yield selected[0], selected[1]
        else:
            yield None
        unchanged()
        if selected and _descriptor_manifest(selected[2], budget) != selected[3]:
            raise PackageError('PACKAGE_RETAINED_CHANGED')
    except OSError:
        raise PackageError('PACKAGE_RETAINED_PATH_REJECTED') from None
    finally:
        for descriptor in reversed(descriptors): os.close(descriptor)


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def safe_path(path):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts or any(p.is_symlink() for p in (path, *path.parents)):
        raise PackageError('PACKAGE_PATH_REJECTED')
    return path


def manifest(bundle, *, budget=None):
    if budget is not None:
        with _governed_package_root(bundle,budget) as descriptor:
            return _descriptor_manifest(descriptor,budget)
    bundle = safe_path(bundle)
    if not bundle.is_dir():
        raise PackageError('PACKAGE_BUNDLE_MISSING')
    metadata = bundle.stat()
    if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o755:
        raise PackageError('PACKAGE_BUNDLE_OWNER_OR_MODE_INVALID')
    rows = []
    for path in sorted(bundle.rglob('*')):
        if budget is not None:
            budget.check()
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
        if budget is not None:
            budget.check()
    return rows


def identity(bundle):
    return sha256(canonical(manifest(bundle))).hexdigest()


def run(*args, budget=None, **kwargs):
    if budget is not None:
        # Governed verification retains its actual helper through return. It
        # cannot use subprocess.run's independent timeout/cancellation policy.
        if kwargs:
            raise PackageError('PACKAGE_GOVERNED_COMMAND_OPTIONS_REJECTED')
        from kronos.common.failed_fenced_startup import run_native_helper
        try:
            output = run_native_helper(list(args), budget=budget, timeout_cap=60)
        except (subprocess.SubprocessError, OSError):
            raise PackageError('PACKAGE_COMMAND_FAILED') from None
        return subprocess.CompletedProcess(args, 0, stdout=output, stderr=b'')
    try:
        return subprocess.run(args, check=True, capture_output=True, timeout=60, **kwargs)
    except (subprocess.SubprocessError, OSError):
        raise PackageError('PACKAGE_COMMAND_FAILED') from None


def verify(bundle, expected_identity=None, *, budget=None):
    if budget is not None:
        budget.check()
    bundle = safe_path(bundle)
    rows = manifest(bundle, budget=budget)
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
    if budget is None:
        run('/usr/bin/codesign', '--verify', '--strict', '--verbose=2', str(bundle))
    else:
        run('/usr/bin/codesign', '--verify', '--strict', '--verbose=2', str(bundle), budget=budget)
        if manifest(bundle, budget=budget) != rows:
            raise PackageError('PACKAGE_CHANGED_DURING_GOVERNED_VERIFICATION')
        budget.check()
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
