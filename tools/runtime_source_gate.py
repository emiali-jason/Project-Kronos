"""RUNTIME-01 startup-only source qualification; no runtime or evidence writes."""
from __future__ import annotations

import ctypes
from hashlib import sha1
from dataclasses import replace
from pathlib import Path
import os
import re
import subprocess
import sys

CANONICAL = Path("/Applications/KRONOS.app")
EXECUTABLE = CANONICAL / "Contents/MacOS/KRONOS"


def fixed_native_estate():
    """Same native account root as C; HOME is never a guard locator."""
    import pwd
    if os.getuid()!=os.geteuid():
        raise ValueError('RECOVERY_NATIVE_ACCOUNT_CHANGED')
    home=Path(pwd.getpwuid(os.geteuid()).pw_dir)
    if not home.is_absolute() or '..' in home.parts:
        raise ValueError('RECOVERY_NATIVE_ACCOUNT_HOME_INVALID')
    return home/'Library/Application Support/KRONOS/runtime'


def canonical_parent(*, budget=None):
    """Kernel parent image plus strict bundle seal; no environment authority."""
    if sys.platform != "darwin":
        raise ValueError("CANONICAL_LAUNCHER_REQUIRED")
    try:
        buffer = ctypes.create_string_buffer(4096)
        library = ctypes.CDLL("/usr/lib/libproc.dylib")
        if (library.proc_pidpath(os.getppid(), buffer, len(buffer)) <= 0
                or Path(os.fsdecode(buffer.value)) != EXECUTABLE
                or EXECUTABLE.resolve() != EXECUTABLE):
            raise ValueError("CANONICAL_LAUNCHER_REQUIRED")
        command = ["/usr/bin/codesign", "--verify", "--deep", "--strict",
            "-R", '=identifier "com.project-kronos.browser-v1"', str(CANONICAL)]
        if budget is None:
            subprocess.run(command, check=True, capture_output=True, timeout=10)
        else:
            from kronos.common.failed_fenced_startup import run_native_helper
            run_native_helper(command, budget=budget, timeout_cap=10)
    except (OSError, subprocess.SubprocessError):
        raise ValueError("CANONICAL_SIGNATURE_INVALID") from None


def native_boot_id():
    """Actual same-boot identifier, with no wall-clock conversion or hint."""
    if sys.platform != 'darwin':
        raise ValueError("RECOVERY_DARWIN_BOOT_REQUIRED")
    library = ctypes.CDLL(None, use_errno=True)
    library.sysctlbyname.argtypes = [ctypes.c_char_p, ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_size_t), ctypes.c_void_p, ctypes.c_size_t]
    library.sysctlbyname.restype = ctypes.c_int
    buffer = ctypes.create_string_buffer(128); size = ctypes.c_size_t(len(buffer))
    if library.sysctlbyname(b'kern.bootsessionuuid', buffer, ctypes.byref(size), None, 0) != 0:
        raise ValueError("RECOVERY_NATIVE_BOOT_UNAVAILABLE")
    raw = buffer.raw[:size.value]
    if not raw.endswith(b'\0') or len(raw) < 2 or b'\0' in raw[:-1]:
        raise ValueError("RECOVERY_NATIVE_BOOT_UNAVAILABLE")
    value = raw[:-1].decode('ascii')
    if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,159}', value) is None:
        raise ValueError("RECOVERY_NATIVE_BOOT_UNAVAILABLE")
    return value


def canonical_controller_identity(pid, *, budget):
    """Actual Darwin parent instance and securely captured canonical image.

    The native controller uses the same executable SHA-256 for its Process Id;
    no environment, request, proof field or source inventory chooses this Id.
    """
    import stat
    from hashlib import sha256
    from kronos.common.failed_fenced_startup import _bootstrap_process_observation
    if type(pid) is not int or pid < 2 or sys.platform != 'darwin':
        raise ValueError("CANONICAL_LAUNCHER_REQUIRED")
    def verify_image():
        budget.check()
        buffer = ctypes.create_string_buffer(4096)
        library = ctypes.CDLL("/usr/lib/libproc.dylib")
        if (library.proc_pidpath(pid, buffer, len(buffer)) <= 0
                or Path(os.fsdecode(buffer.value)) != EXECUTABLE):
            raise ValueError("CANONICAL_LAUNCHER_REQUIRED")
        from kronos.common.failed_fenced_startup import run_native_helper
        run_native_helper(["/usr/bin/codesign", "--verify", "--deep", "--strict",
            "-R", '=identifier "com.project-kronos.browser-v1"', str(CANONICAL)],
            budget=budget, timeout_cap=10)
    verify_image()
    before = _bootstrap_process_observation(pid, budget)
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    parent = os.open('/', flags | os.O_DIRECTORY)
    try:
        for part in EXECUTABLE.parts[1:-1]:
            child = os.open(part, flags | os.O_DIRECTORY, dir_fd=parent)
            os.close(parent); parent = child
        descriptor = os.open(EXECUTABLE.name, flags, dir_fd=parent)
        try:
            initial = os.fstat(descriptor)
            if not stat.S_ISREG(initial.st_mode) or initial.st_nlink != 1:
                raise ValueError("CANONICAL_LAUNCHER_IMAGE_UNAVAILABLE")
            digest = sha256()
            while True:
                budget.check()
                part = os.read(descriptor, 65536)
                if not part:
                    break
                digest.update(part)
            after = os.fstat(descriptor)
            named = os.stat(EXECUTABLE.name, dir_fd=parent, follow_symlinks=False)
            fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
            if any(getattr(initial, key) != getattr(after, key) or getattr(initial, key) != getattr(named, key) for key in fields):
                raise ValueError("CANONICAL_LAUNCHER_IMAGE_CHANGED")
        finally:
            os.close(descriptor)
    finally:
        os.close(parent)
    if _bootstrap_process_observation(pid, budget) != before:
        raise ValueError("CANONICAL_LAUNCHER_PROCESS_CHANGED")
    verify_image()
    return {"pid": before["pid"], "kernel_birth": before["kernel_birth"], "runtime": digest.hexdigest()}


def canonical_parent_identity(*, budget):
    """Bind the actual canonical parent, including PID reuse and reparenting."""
    parent = os.getppid()
    result = canonical_controller_identity(parent, budget=budget)
    if os.getppid() != parent:
        raise ValueError("CANONICAL_LAUNCHER_PROCESS_CHANGED")
    return result


def qualify_repository(root, *, budget=None):
    """Exact develop publication, including staged and untracked source policy."""
    root = Path(root).resolve()
    def git(*args):
        if budget is not None:
            from kronos.common.failed_fenced_startup import run_native_helper
            return run_native_helper(["git", *args], cwd=root, budget=budget,
                                     timeout_cap=20).decode().strip()
        return subprocess.check_output(["git", *args], cwd=root,
            stderr=subprocess.DEVNULL, timeout=20).decode().strip()
    try:
        if Path(git("rev-parse", "--show-toplevel")).resolve() != root:
            raise ValueError("SOURCE_PROOF_UNAVAILABLE")
        if git("status", "--porcelain=v1", "--untracked-files=all"):
            raise ValueError("SOURCE_NOT_CLEAN")
        revision = git("rev-parse", "HEAD")
        if (not re.fullmatch(r"[a-f0-9]{40}", revision)
                or git("branch", "--show-current") != "develop"
                or git("rev-parse", "origin/develop") != revision
                or git("ls-remote", "--exit-code", "origin", "refs/heads/develop").split()
                    != [revision, "refs/heads/develop"]):
            raise ValueError("SOURCE_REVISION_NOT_AUTHORIZED")
        # Do not trust index stat caches, assume-unchanged or ignored Python files.
        tree = git("ls-tree", "-r", revision, "--", "src/kronos", "tools")
        blobs = {line.split("\t", 1)[1]: line.split("\t", 1)[0].split()[2]
                 for line in tree.splitlines()}
        seen = set()
        for prefix in ("src/kronos", "tools"):
            for path in (root / prefix).rglob("*.py"):
                if budget is not None:
                    budget.check()
                if path.is_symlink() or not path.resolve().is_relative_to(root):
                    raise ValueError("SOURCE_NOT_CLEAN")
                seen.add(str(path.relative_to(root)))
                payload = path.read_bytes()
                actual = sha1(b"blob " + str(len(payload)).encode() + b"\0" + payload).hexdigest()
                if blobs.get(str(path.relative_to(root))) != actual:
                    raise ValueError("SOURCE_NOT_CLEAN")
        if seen != {name for name in blobs if name.endswith(".py")}:
            raise ValueError("SOURCE_NOT_CLEAN")
        if git("rev-parse", "HEAD") != revision or git("status", "--porcelain=v1", "--untracked-files=all"):
            raise ValueError("SOURCE_NOT_CLEAN")
        return revision
    except (OSError, subprocess.SubprocessError, IndexError):
        raise ValueError("SOURCE_PROOF_UNAVAILABLE") from None


def qualify_startup(root, evidence, *, budget=None):
    if budget is None:
        canonical_parent()
        revision = qualify_repository(root)
    else:
        budget.check()
        canonical_parent(budget=budget)
        revision = qualify_repository(root, budget=budget)
    try:
        replace(evidence)
        if (evidence.source_revision != revision or evidence.source_state != "CLEAN_COMMIT"
                or evidence.process_id != os.getpid()
                or evidence.load_verification != "PINNED_STARTUP_IMPORTS"
                or not evidence.source_snapshot_digest):
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError("SOURCE_PROOF_UNAVAILABLE") from None
    return revision


if __name__ == "__main__":
    try:
        canonical_parent()
        qualify_repository(Path(__file__).resolve().parents[1])
    except ValueError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)


# Exact stdlib native-entry program embedded by canonical C before any product import.
NATIVE_CHILD_PIN_BOOTSTRAP = "import os,sys,time,json,hashlib,types,stat,importlib.abc,importlib.util\norigin,stop=__KRONOS_ORIGIN__,__KRONOS_STOP__\nframe_hex=__KRONOS_FRAME_HEX__\ndef check():\n    current=globals().get('capsule')\n    if current is not None and getattr(current,'ready_session',None) is not None:\n        from tools.runtime_source_gate import native_child_ready_budget\n        native_child_ready_budget(current).check();return\n    now=time.clock_gettime_ns(time.CLOCK_MONOTONIC)\n    if stop!=origin+15000000000 or not origin<=now<stop:raise RuntimeError('NATIVE_CHILD_PIN_BUDGET')\ndef pairs(rows):\n    result={}\n    for key,value in rows:\n        if key in result:raise RuntimeError('NATIVE_CHILD_PIN_DUPLICATE')\n        result[key]=value\n    return result\ncheck()\nraw=bytes.fromhex(frame_hex)\nif not 1<=len(raw)<=67108864:raise RuntimeError('NATIVE_CHILD_PIN_BOUND')\nframe=json.loads(raw,object_pairs_hook=pairs)\nif json.dumps(frame,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()!=raw or set(frame)!={'inventory','plan','plan_hash','sources'}:raise RuntimeError('NATIVE_CHILD_PIN_CANONICAL')\nplan=frame['plan'];planraw=json.dumps(plan,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()\nif hashlib.sha256(planraw).hexdigest()!=frame['plan_hash'] or set(plan)!={'schema','identity','source_inventory','modules','qualification'} or plan['schema']!='KRONOS-FAILED-FENCED-BOOTSTRAP-PLAN/1.0.0':raise RuntimeError('NATIVE_CHILD_PIN_PLAN')\ninventory=frame['inventory'];inventory_raw=json.dumps(inventory,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()\nif type(inventory) is not list or not 1<=len(inventory)<=4096 or any(type(row) is not list or len(row)!=2 or any(type(value) is not str for value in row) for row in inventory):raise RuntimeError('NATIVE_CHILD_PIN_INVENTORY')\nif hashlib.sha256(inventory_raw).hexdigest()!=plan['source_inventory']['hash'] or str(len(inventory_raw))!=plan['source_inventory']['bytes']:raise RuntimeError('NATIVE_CHILD_PIN_INVENTORY_HASH')\nexpected=dict(inventory)\nif len(expected)!=len(inventory) or list(expected)!=sorted(expected):raise RuntimeError('NATIVE_CHILD_PIN_MODULES')\nplanned={row['name']:row['digest'] for row in plan['modules']}\nif len(planned)!=len(plan['modules']) or list(planned)!=sorted(planned) or any(expected.get(name)!=digest for name,digest in planned.items()):raise RuntimeError('NATIVE_CHILD_PIN_PLAN_SOURCE')\ndef capture(path):\n    if type(path) is not str or not path.startswith('/') or '\\x00' in path:raise RuntimeError('NATIVE_CHILD_PIN_SOURCE_PATH')\n    parts=path.split('/')[1:]\n    if not parts or any(part in {'','.','..'} for part in parts):raise RuntimeError('NATIVE_CHILD_PIN_SOURCE_PATH')\n    flags=os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW\n    parent=os.open('/',flags|os.O_DIRECTORY);ancestors=[]\n    try:\n        for part in parts[:-1]:\n            child=os.open(part,flags|os.O_DIRECTORY,dir_fd=parent)\n            os.close(parent);parent=child\n            st=os.fstat(parent);ancestors.append((st.st_dev,st.st_ino,st.st_uid,st.st_mode))\n            if st.st_uid not in {0,os.getuid()} or st.st_mode&0o022:raise RuntimeError('NATIVE_CHILD_PIN_SOURCE_PARENT')\n        descriptor=os.open(parts[-1],flags,dir_fd=parent)\n        try:\n            before=os.fstat(descriptor)\n            if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or before.st_uid not in {0,os.getuid()} or before.st_mode&0o022 or not 0<=before.st_size<=16777216:raise RuntimeError('NATIVE_CHILD_PIN_SOURCE_PRIVATE')\n            chunks=[];total=0\n            while True:\n                check();part=os.read(descriptor,65536)\n                if not part:break\n                total+=len(part)\n                if total>16777216:raise RuntimeError('NATIVE_CHILD_PIN_SOURCE_BOUND')\n                chunks.append(part)\n            after=os.fstat(descriptor);named=os.stat(parts[-1],dir_fd=parent,follow_symlinks=False)\n            fields=('st_dev','st_ino','st_uid','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')\n            if any(getattr(before,k)!=getattr(after,k) or getattr(before,k)!=getattr(named,k) for k in fields):raise RuntimeError('NATIVE_CHILD_PIN_SOURCE_CHANGED')\n            reopened=os.open('/',flags|os.O_DIRECTORY)\n            try:\n                for index,part in enumerate(parts[:-1]):\n                    child=os.open(part,flags|os.O_DIRECTORY,dir_fd=reopened)\n                    os.close(reopened);reopened=child;st=os.fstat(reopened)\n                    if (st.st_dev,st.st_ino,st.st_uid,st.st_mode)!=ancestors[index]:raise RuntimeError('NATIVE_CHILD_PIN_SOURCE_PARENT_CHANGED')\n            finally:os.close(reopened)\n            return b''.join(chunks)\n        finally:os.close(descriptor)\n    finally:os.close(parent)\nsources={}\nfor row in frame['sources']:\n    check()\n    if set(row)!={'name','package','path'} or type(row['package']) is not bool or row['name'] in sources:raise RuntimeError('NATIVE_CHILD_PIN_SOURCE')\n    try:payload=capture(row['path'])\n    except OSError:raise RuntimeError('NATIVE_CHILD_PIN_SOURCE_UNAVAILABLE') from None\n    if expected.get(row['name'])!=hashlib.sha256(payload).hexdigest():raise RuntimeError('NATIVE_CHILD_PIN_SOURCE_HASH')\n    sources[row['name']]=(payload,row['package'],row['path'])\nif set(sources)!=set(expected) or not {'tools.kronos_browser','kronos.intraday.runtime_identity','tools.runtime_source_gate'}<=set(sources):raise RuntimeError('NATIVE_CHILD_PIN_ROSTER')\ncapsule=types.ModuleType('_kronos_native_child_bootstrap')\ncapsule.pid=os.getpid();capsule.origin=origin;capsule.stop=stop;capsule.frame_hex=frame_hex\ncapsule.script=sys.orig_argv[sys.orig_argv.index('-c')+1];capsule.plan_hash=frame['plan_hash']\ncapsule.sources=tuple((name,sources[name]) for name in sorted(sources));capsule.plan=planraw\nconstructed={}\nclass PinnedLoader(importlib.abc.Loader):\n    def __init__(self,name):\n        if name not in sources or name in constructed:raise RuntimeError('NATIVE_CHILD_PIN_REPLAY')\n        self.name=name;self.payload=sources[name][0];self.path=sources[name][2]\n        self.code=compile(self.payload,self.path,'exec',dont_inherit=True);self.executed=False\n        constructed[name]=self\n    def create_module(self,spec):return None\n    def exec_module(self,module):\n        check()\n        if module.__spec__.loader is not self or module.__spec__.name!=self.name or self.executed:raise RuntimeError('NATIVE_CHILD_PIN_LOADER_CHANGED')\n        self.executed=True;module.__file__=self.path;exec(self.code,module.__dict__)\n    def is_package(self,name):return sources[name][1]\nclass PinnedFinder(importlib.abc.MetaPathFinder):\n    def find_spec(self,name,path=None,target=None):\n        if name in sources:return importlib.util.spec_from_loader(name,PinnedLoader(name),is_package=sources[name][1])\n        if name in {'tools','tools.macos'} and name not in sources and any(key.startswith(name+'.') for key in sources):\n            spec=importlib.util.spec_from_loader(name,loader=None,is_package=True);spec.submodule_search_locations=[];return spec\n        if name in {'tools','kronos'} or name.startswith(('tools.','kronos.')):raise ImportError('NATIVE_CHILD_PIN_UNCAPTURED_MODULE')\ncapsule.loader_type=PinnedLoader;capsule.constructed=constructed;capsule.finder=PinnedFinder()\nsys.modules[capsule.__name__]=capsule;sys.meta_path.insert(0,capsule.finder)\ncheck()\nfrom tools import kronos_browser as entry\nraise SystemExit(entry.main(['--no-browser']))\n"


def native_child_bootstrap_script(frame_raw, origin_ns, stop_deadline_ns):
    """Materialize only the fixed native script plus literal captured data."""
    if (type(frame_raw) is not bytes or not 1<=len(frame_raw)<=67108864
            or type(origin_ns) is not int or type(stop_deadline_ns) is not int
            or origin_ns<0 or stop_deadline_ns!=origin_ns+15_000_000_000):
        raise ValueError('NATIVE_CHILD_PIN_CONTEXT')
    return NATIVE_CHILD_PIN_BOOTSTRAP.replace('__KRONOS_ORIGIN__',str(origin_ns)).replace(
        '__KRONOS_STOP__',str(stop_deadline_ns)).replace('__KRONOS_FRAME_HEX__',repr(frame_raw.hex()))


def _native_child_capture(*, plan_hash=None):
    """Validate the complete live C capture, without granting authority."""
    import types
    from hashlib import sha256
    capsule=sys.modules.get('_kronos_native_child_bootstrap')
    if type(capsule) is not types.ModuleType or capsule.pid!=os.getpid():
        raise ValueError('NATIVE_CHILD_PIN_CAPSULE_REQUIRED')
    frame_raw=bytes.fromhex(capsule.frame_hex)
    expected_script=native_child_bootstrap_script(frame_raw,capsule.origin,capsule.stop)
    if (capsule.script!=expected_script or '-c' not in sys.orig_argv
            or sys.orig_argv[sys.orig_argv.index('-c')+1]!=expected_script
            or plan_hash is not None and capsule.plan_hash!=plan_hash
            or capsule.finder not in sys.meta_path or type(capsule.sources) is not tuple
            or sha256(capsule.plan).hexdigest()!=capsule.plan_hash):
        raise ValueError('NATIVE_CHILD_PIN_PROGRAM_CHANGED')
    sources=dict(capsule.sources)
    if len(sources)!=len(capsule.sources):raise ValueError('NATIVE_CHILD_PIN_CAPTURE_CHANGED')
    import json
    frame=json.loads(frame_raw)
    expected=dict(frame['inventory'])
    inventory_raw=json.dumps(frame['inventory'],sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()
    if (sha256(inventory_raw).hexdigest()!=frame['plan']['source_inventory']['hash']
            or str(len(inventory_raw))!=frame['plan']['source_inventory']['bytes']
            or len(expected)!=len(frame['inventory']) or list(expected)!=sorted(expected)):
        raise ValueError('NATIVE_CHILD_PIN_CAPTURE_CHANGED')
    if (frame['plan_hash']!=capsule.plan_hash or set(sources)!=set(expected)
            or {(name,values[1],values[2]) for name,values in sources.items()}!={(row['name'],row['package'],row['path']) for row in frame['sources']}
            or any(type(values[0]) is not bytes or sha256(values[0]).hexdigest()!=expected[name] for name,values in sources.items())):
        raise ValueError('NATIVE_CHILD_PIN_CAPTURE_CHANGED')
    return capsule, sources


def _native_child_executed_module(module, capsule, sources):
    import types
    from hashlib import sha256
    specification=getattr(module,'__spec__',None);name=getattr(specification,'name',None)
    loader=getattr(specification,'loader',None)
    if (name not in sources or type(loader) is not capsule.loader_type
            or capsule.constructed.get(name) is not loader or loader.name!=name
            or loader.payload is not sources[name][0] or loader.path!=sources[name][2]
            or not loader.executed or not isinstance(loader.code,types.CodeType)
            or getattr(module,'__loader__',None) is not loader):
        raise ValueError('NATIVE_CHILD_PIN_EXECUTED_BYTES_UNPROVEN')
    compiled=compile(loader.payload,loader.path,'exec',dont_inherit=True)
    if loader.code!=compiled:
        raise ValueError('NATIVE_CHILD_PIN_EXECUTED_CODE_CHANGED')
    return name,sha256(loader.payload).hexdigest()



def native_child_pinned_module(module, *, plan_hash=None):
    """Exact live C-entry loader witness; no attribute-only acceptance."""
    capsule, sources = _native_child_capture(plan_hash=plan_hash)
    return _native_child_executed_module(module, capsule, sources)


def native_child_pinned_modules(modules, *, plan_hash=None, check_deadline):
    """One bounded read-only batch; full immutable capture checked at both ends.

    No result survives this call. Each executed loader/code is checked exactly;
    callers still compare the complete observed set with their approved plan.
    """
    check_deadline()
    capsule, sources = _native_child_capture(plan_hash=plan_hash)
    result = []
    for module in modules:
        check_deadline()
        result.append(_native_child_executed_module(module, capsule, sources))
    observed, final_sources = _native_child_capture(plan_hash=plan_hash)
    if observed is not capsule or final_sources != sources:
        raise ValueError("NATIVE_CHILD_PIN_CAPTURE_CHANGED")
    check_deadline()
    return tuple(result)


def native_child_ready_budget(capsule):
    """Finite post-consumption loader phase; never a supplied deadline setter."""
    from kronos.common.failed_fenced_startup import BootstrapSession, ReadyBudget, CompositionLatch
    from kronos.common.failed_fenced_recovery import record_ref
    session=getattr(capsule,'ready_session',None)
    if (capsule is not sys.modules.get('_kronos_native_child_bootstrap')
            or type(session) is not BootstrapSession or session._pid!=os.getpid()
            or type(session.ready_budget) is not ReadyBudget
            or type(session.latch) is not CompositionLatch or not session.latch._spent
            or not hasattr(session,'consumption_raw') or not hasattr(session,'startup_context_raw')):
        raise ValueError('NATIVE_CHILD_PIN_READY_CONTEXT')
    native_child_pinned_module(sys.modules['tools.kronos_browser'])
    consumed=session.codec.decode(session.consumption_raw,'CONSUMPTION')['payload']
    startup=session.codec.decode(session.startup_context_raw,'STARTUP_CONTEXT')['payload']
    grant=session.latch.record['payload'];started=session.chain['CHILD_STARTED']['payload']
    if (session.store.read_reservation(consumed['slot'],'consumption')!=session.consumption_raw
            or session.store.resolve(record_ref(session.startup_context_raw))!=session.startup_context_raw
            or consumed['consumer']!=session.native.process or session.native.process['pid']!=str(os.getpid())
            or consumed['composition_authority']!=record_ref(session.latch.raw)
            or consumed['authority_bytes']!=session.latch.raw.hex()
            or consumed['child_nonce']!=grant['child_nonce'] or startup['runtime']!=session.native.process
            or startup['consumption']!=record_ref(session.consumption_raw)
            or int(grant['stop_deadline_ns'])!=capsule.stop or session.budget.origin_ns!=capsule.origin
            or session.ready_budget.origin_ns!=capsule.origin or session.ready_budget.stop_deadline_ns!=capsule.stop
            or not capsule.origin<=session.latch.received_ns<=session.latch.verified_ns<capsule.stop
            or session.ready_budget.ready_deadline_ns!=int(started['fork_enter_ns'])+120_000_000_000
            or int(grant['ready_deadline_ns'])!=session.ready_budget.ready_deadline_ns):
        raise ValueError('NATIVE_CHILD_PIN_READY_BINDING')
    return session.ready_budget


def advance_native_child_loader(session):
    """Called only after the actual child publishes both consumption receipts."""
    capsule=sys.modules.get('_kronos_native_child_bootstrap')
    if capsule is None:return
    if getattr(capsule,'ready_session',None) is not None:
        raise ValueError('NATIVE_CHILD_PIN_READY_REPLAY')
    capsule.ready_session=session
    try:native_child_ready_budget(capsule).check()
    except BaseException:
        del capsule.ready_session
        raise
