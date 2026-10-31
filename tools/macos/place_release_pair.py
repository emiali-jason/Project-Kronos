"""Explicit initial pre-activation placement. Never startup/admission authority.

The operator must separately approve the exact executor, order and old/new pair.
A complete prepared record is not proof of original timely completion. Every
operation is one-shot; interrupted/late work is retained, never resumed/repaired.
"""
from __future__ import annotations

import argparse
import ctypes
import ast
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256, new as hash_new
import fcntl
import json
import os
from pathlib import Path
import re
import socket
import stat
import sys
import threading

# Fixed source-relative imports, not caller-selected package discovery.
_REPOSITORY = Path(__file__).resolve().parents[2]
if str(_REPOSITORY / 'src') not in sys.path:
    sys.path[:0] = [str(_REPOSITORY / 'src'), str(_REPOSITORY)]
from kronos.common import release_admission as admission
from kronos.common import failed_successor_restore as restoration
from kronos.common import legacy_bootstrap as bootstrap
from tools.macos import package_launcher as package

PORT = 8947
MAX_DOCUMENT = 8 * 1024 * 1024
MAX_FILES = 100_000
MAX_BYTES = 8 * 1024**3
SCHEMA = 'KRONOS_INITIAL_PAIR_PLACEMENT_ORDER_V1'
PAIR_SCHEMA = 'KRONOS_RELEASE_PAIR_V1'
JOURNAL_NAME = 'release-placement-v1'
FINAL_STAGE = 'final-unactivated'


class PlacementError(ValueError):
    pass


def deny(reason):
    raise PlacementError('PLACEMENT_' + reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def document(raw, *, final_lf=False):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result: deny('DUPLICATE_KEY')
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=pairs,
                           parse_constant=lambda _: deny('NONFINITE'))
        if raw != canonical(value) + (b'\n' if final_lf else b''): deny('DOCUMENT_ENCODING')
        return value
    except (UnicodeError, json.JSONDecodeError, TypeError):
        deny('DOCUMENT_ENCODING')


def closed(value, fields):
    if type(value) is not dict or set(value) != set(fields): deny('FIELDS')


def path(value):
    p = Path(value)
    if not p.is_absolute() or '..' in p.parts or '.' in p.parts: deny('PATH')
    for component in (p, *p.parents):
        if component.is_symlink(): deny('PATH_ALIAS')
    return p


def _signature(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _directory_fd(value):
    p=path(value);fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
    try:
        for part in p.parts[1:]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
            os.close(fd);fd=child;info=os.fstat(fd)
            if info.st_uid not in {0,os.getuid()} or info.st_mode&0o022:deny('UNSAFE_DIRECTORY')
        return fd
    except BaseException:
        os.close(fd);raise


def _read_regular(p, *, limit, check, private=False):
    p = path(p)
    directory=_directory_fd(p.parent)
    try:fd = os.open(p.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,dir_fd=directory)
    except BaseException:os.close(directory);raise
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid not in {0, os.getuid()}
                or before.st_mode & 0o022 or before.st_size > limit
                or (private and (before.st_uid != os.getuid() or stat.S_IMODE(before.st_mode) != 0o600))):
            deny('FILE')
        raw = bytearray()
        while True:
            check()
            chunk = os.read(fd, min(65536, limit + 1 - len(raw)))
            if not chunk: break
            raw.extend(chunk)
            if len(raw) > limit: deny('SIZE')
        after = os.fstat(fd)
        if _signature(before) != _signature(after) or _signature(after) != _signature(os.stat(p.name,dir_fd=directory,follow_symlinks=False)): deny('CHANGED_READ')
        check()
        return bytes(raw), before
    finally:
        try:os.close(fd)
        finally:os.close(directory)


def read_reference(reference, check, *, private=True):
    closed(reference, ('identity', 'path', 'bytes', 'sha256'))
    if (not isinstance(reference['identity'], str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,200}', reference['identity'])
            or type(reference['bytes']) is not int or not 0 < reference['bytes'] <= MAX_DOCUMENT
            or not isinstance(reference['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', reference['sha256'])):
        deny('REFERENCE')
    raw, _ = _read_regular(reference['path'], limit=MAX_DOCUMENT, check=check, private=private)
    if len(raw) != reference['bytes'] or sha256(raw).hexdigest() != reference['sha256']: deny('REFERENCE_BYTES')
    return raw


def _assignment(raw, name):
    tree = ast.parse(raw)
    values = [ast.literal_eval(node.value) for node in tree.body
              if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets)]
    if len(values) != 1: deny('PIN_ASSIGNMENT')
    return values[0]


def _c_assignment(raw, name):
    found = re.findall(r'static const char \*' + re.escape(name) + r'\s*=\s*(NULL|"(?:\\.|[^"\\])*");', raw.decode())
    if len(found) != 1: deny('C_PIN_ASSIGNMENT')
    return None if found[0] == 'NULL' else json.loads(found[0]).encode()


def verify_source_pins(repository, *, selected=True, check=lambda:None):
    """Real text/byte agreement; no module rebinding or selected-code import."""
    repository = path(repository)
    c = _read_regular(repository / 'tools/macos/kronos_launcher.c',limit=MAX_DOCUMENT,check=check)[0]
    a = _assignment(_read_regular(repository / 'src/kronos/common/release_admission.py',limit=MAX_DOCUMENT,check=check)[0], 'PERSISTENT_ANCHOR_BINDING')
    g = _assignment(_read_regular(repository / 'src/kronos/common/failed_successor_restore.py',limit=MAX_DOCUMENT,check=check)[0], 'INITIALIZATION_DISPOSITION')
    o = _assignment(_read_regular(repository / 'src/kronos/common/legacy_bootstrap.py',limit=MAX_DOCUMENT,check=check)[0], 'ORDINARY_RESTART_POLICY')
    if (_c_assignment(c, 'approved_persistent_binding') != a
            or _c_assignment(c, 'approved_initialization_disposition') != g
            or _c_assignment(c, 'approved_ordinary_restart_policy') != o): deny('PIN_PAIR')
    if selected and (a != admission.PERSISTENT_ANCHOR_BINDING
                     or g != restoration.INITIALIZATION_DISPOSITION
                     or o != bootstrap.ORDINARY_RESTART_POLICY): deny('EXECUTOR_POLICY')
    return a, g, o


def _process_ids():
    if sys.platform!='darwin':deny('PROCESS_PLATFORM')
    library=ctypes.CDLL('/usr/lib/libproc.dylib',use_errno=True)
    library.proc_listpids.argtypes=(ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_int)
    values=(ctypes.c_int*16384)()
    size=library.proc_listpids(4,os.getuid(),values,ctypes.sizeof(values))
    if size<=0 or size>=ctypes.sizeof(values) or size%ctypes.sizeof(ctypes.c_int):deny('PROCESS_INVENTORY')
    return tuple(values[:size//ctypes.sizeof(ctypes.c_int)])


def _process_arguments(pid):
    # Same CTL_KERN/KERN_PROCARGS2 observation as native initialization. No ps
    # subprocess, PID/name inference or caller/environment identity assertion.
    library=ctypes.CDLL(None,use_errno=True)
    mib=(ctypes.c_int*3)(1,49,pid)
    raw=ctypes.create_string_buffer(262144);size=ctypes.c_size_t(len(raw))
    if library.sysctl(mib,3,raw,ctypes.byref(size),None,0)!=0 or not 4<size.value<len(raw):deny('PROCESS_ARGUMENTS')
    payload=raw.raw[4:size.value]
    if not payload.endswith(b'\0'):deny('PROCESS_ARGUMENTS')
    return tuple(payload.split(b'\0'))


_SDK_LOCK=threading.RLock()


class Placement:
    """One synchronous owner and original budget; no retry or background work."""
    def __init__(self, budget=None):
        self.budget = budget if budget is not None else admission.inherited_budget(120)
        if not isinstance(self.budget, admission.ValidationBudget): deny('BUDGET')
        self.original_deadline = self.budget.deadline_ns
        self.descriptor = None
        self.binding = admission.APPROVED_BINDING
        self.policy = None
        self.owner = None
        self.active_io = 0
        self.unresolved = False
        self.entered = False
        self.events = []
        self._lock = threading.RLock()

    def check(self):
        self.budget.check()
        if self.unresolved:deny('RESOURCE_UNRESOLVED')
        if self.budget.deadline_ns != self.original_deadline: deny('DEADLINE_RENEWAL')
        if admission.validation_unresolved(): deny('HELPER_UNRESOLVED')
        if hasattr(self,'valid_until'):
            now=datetime.now(timezone.utc)
            if now<self.last_utc or now>self.valid_until:deny('ORDER_EXPIRED_OR_UTC_ROLLBACK')
            self.last_utc=now
        if self.descriptor is not None:
            held = os.fstat(self.descriptor)
            named = path(self.policy['anchor_path']).lstat()
            if ((held.st_dev, held.st_ino, held.st_uid, held.st_mode) !=
                    (named.st_dev, named.st_ino, named.st_uid, named.st_mode)
                    or admission.descriptor_filesystem_identity(self.descriptor) !=
                    dict(volume_uuid=self.policy['volume_uuid'], file_id=self.policy['file_id'])):
                deny('CUSTODY_CHANGED')

    @contextmanager
    def io(self):
        self.check()
        with self._lock: self.active_io += 1
        try:
            yield
        except BaseException as error:
            self.unresolved=True
            self.events.append(dict(event='ENTERED_IO_FAILED',exception=type(error).__name__,message=str(error),original_deadline_ns=self.original_deadline))
            raise
        finally:
            with self._lock: self.active_io -= 1
        self.check()

    def helper(self, arguments, cwd, phase, capacity=262144):
        self.check()
        event=dict(event='VALIDATION_HELPER',argv=list(map(str,arguments)),cwd=str(cwd),phase=phase,
                   original_deadline_ns=self.original_deadline)
        self.events.append(event)
        try:
            raw = admission.validation_output(arguments, cwd=cwd, budget=self.budget,
                ceiling=20, phase=phase, capacity=capacity)
        except BaseException as error:
            event.update(exception=type(error).__name__,actual_exit=getattr(error,'returncode',None),
                unresolved=admission.validation_unresolved(),actual_owned_pids=list(admission._OWNED_VALIDATION_HELPERS))
            raise
        event.update(actual_exit=0,terminal_observation='ACTUAL_OWNER_RETURNED_ONLY_AFTER_COMPLETE_OUTPUT_AND_EXIT_ZERO',
            output_bytes=len(raw),output_sha256=sha256(raw).hexdigest(),unresolved=False)
        self.check()
        return raw

    def _acquire(self, enrollment):
        frozen = read_reference(enrollment, self.check)
        policy, installation = admission._persistent_binding_bytes(self.binding, frozen)
        self.policy = policy
        fd = admission._open_bound_anchor(self.binding, (policy, installation))
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.descriptor = fd
            self.check()
            probe = admission._open_bound_anchor(self.binding, (policy, installation))
            try:
                try: fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError: pass
                else: deny('NO_EXCLUSION')
            finally: os.close(probe)
        except BaseException:
            if self.descriptor is None: os.close(fd)
            raise
        self.events.append(dict(event='ACTUAL_EXCLUSION', boot=self.budget.boot_identity,
                                deadline_ns=self.original_deadline))
        return installation

    def _verify_bundle(self,bundle,identity):
        # The existing SDK verifier retains every roster/plist/signature check.
        # Only its command runner is bound, in this serialized foreground call,
        # to the actual existing validation owner and ORIGINAL budget. This is
        # not an acceptance stub or a general process-execution interceptor.
        remaining=max(0,(self.original_deadline-admission.monotonic_ns())/1e9)
        if not _SDK_LOCK.acquire(timeout=remaining):deny('SDK_OWNER_BUSY')
        previous=package.run
        try:
            self.check()
            def bounded_run(*arguments,**kwargs):
                if (kwargs or not arguments or arguments[0]!='/usr/bin/codesign'
                        or tuple(arguments[1:4])!=('--verify','--strict','--verbose=2')):deny('SDK_COMMAND')
                from types import SimpleNamespace
                raw=self.helper(list(arguments),Path(bundle).parent,'PLACEMENT_SIGNATURE')
                return SimpleNamespace(stdout=raw,stderr=b'',returncode=0)
            package.run=bounded_run
            with self.io():return package.verify(bundle,identity)
        finally:
            package.run=previous;_SDK_LOCK.release()

    def _exchange(self,left,right):
        with self.io():package.exchange(left,right)

    def _inventory(self):
        rows=[]
        for pid in _process_ids():
            if pid<=1 or pid==os.getpid(): continue
            self.check()
            arguments=_process_arguments(pid)
            if any(arg.endswith(b'/tools/kronos_browser.py') or arg==b'tools.kronos_browser'
                   or arg.endswith(b'/Contents/MacOS/KRONOS') for arg in arguments):
                rows.append(dict(pid=pid,arguments_sha256=sha256(b'\0'.join(arguments)).hexdigest()))
        return rows

    def _absent(self, expected_control):
        if self._inventory(): deny('LIVE_PROCESS')
        control = Path(self.policy['anchor_path']) / 'browser-backend-v1.control'
        if expected_control is None:
            if os.path.lexists(control): deny('CONTROL_PRESENT')
        else:
            if expected_control['path'] != str(control): deny('CONTROL_PATH')
            raw = read_reference(expected_control, self.check)
            match = re.fullmatch(rb'KRONOS_BROWSER_BACKEND_CONTROL_V1\n([1-9][0-9]*)\n[0-9a-f]{64}\n', raw)
            if not match: deny('CONTROL_FORMAT')
            try: os.kill(int(match[1]), 0)
            except ProcessLookupError: pass
            else: deny('CONTROL_PID_LIVE_OR_REUSED')
        with socket.socket() as probe:
            probe.settimeout(min(.25, max(.001, (self.original_deadline-admission.monotonic_ns())/1e9)))
            import errno
            result = probe.connect_ex(('127.0.0.1', PORT))
            if result != errno.ECONNREFUSED: deny('LISTENER_OR_UNCERTAINTY')
        # Existing maintenance entries are preserved, and any live unconsumed
        # V2 input blocks placement just as it blocks native initial setup.
        maintenance = control.parent / 'maintenance'
        if os.path.lexists(maintenance):
            # An unreadable/dangling/aliased namespace is not absence. Use the
            # held no-follow directory for the actual enumeration as well.
            directory=_directory_fd(maintenance);observed=os.fstat(directory)
            try:
                for name in os.listdir(directory):
                    p=maintenance/name
                    if re.fullmatch('[0-9a-f]{64}\\.json', p.name):
                        _, info = _read_regular(p, limit=65535, check=self.check, private=True)
                        now = datetime.now(timezone.utc).timestamp()
                        if info.st_mtime > now or now-info.st_mtime <= 30:
                            consumed=p.with_name(p.stem+'.consumed.json')
                            if not consumed.is_file() or consumed.is_symlink(): deny('LIVE_HANDOFF')
                            _read_regular(consumed,limit=65535,check=self.check,private=True)
                if (_signature(observed)!=_signature(os.fstat(directory))
                        or _signature(observed)!=_signature(maintenance.lstat())):deny('MAINTENANCE_CHANGED')
            finally:os.close(directory)
        self.check()

    def _roster(self, root, *, git_entries=None, object_format=None):
        root = path(root);rows=[];total=0;seen=set()
        if not root.is_dir() or root.stat().st_uid != os.getuid(): deny('TREE_ROOT')
        for directory, names, files in os.walk(root, followlinks=False):
            names.sort();files.sort()
            for p in [Path(directory), *(Path(directory)/n for n in names+files)]:
                relative=str(p.relative_to(root))
                if relative in seen: continue
                seen.add(relative)
                self.check();info=p.lstat();mode=stat.S_IMODE(info.st_mode)
                if info.st_uid != os.getuid() or mode & 0o022: deny('TREE_OWNER_MODE')
                row=dict(path=relative,mode=mode)
                if stat.S_ISDIR(info.st_mode): row['type']='directory'
                elif stat.S_ISLNK(info.st_mode):
                    target=os.readlink(p);row.update(type='symlink',target=target,sha256=sha256(target.encode()).hexdigest())
                elif stat.S_ISREG(info.st_mode):
                    raw,_=_read_regular(p,limit=1024**3,check=self.check)
                    total+=len(raw);row.update(type='file',bytes=len(raw),sha256=sha256(raw).hexdigest())
                    if git_entries is not None and relative in git_entries:
                        expected_mode,expected_blob=git_entries[relative]
                        blob=hash_new(object_format,b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
                        if mode!=expected_mode or blob!=expected_blob:deny('GIT_CONTENT_MODE')

                else: deny('TREE_TYPE')
                rows.append(row)
                if len(rows)>MAX_FILES or total>MAX_BYTES: deny('TREE_LIMIT')
        if git_entries is not None:
            files={row['path'] for row in rows if row['type']=='file'}
            if not set(git_entries)<=files:deny('GIT_ROSTER')
            for name in files:
                if (name.startswith(('src/kronos/','tools/')) and name.endswith('.py') and name not in git_entries):deny('UNTRACKED_SOURCE')
        self.check();return sorted(rows,key=lambda x:x['path'])

    def _git(self, repository, *args):
        return self.helper(['/usr/bin/git','--no-optional-locks','-C',str(repository),*args], repository,'PLACEMENT_GIT',MAX_DOCUMENT).decode().strip()

    def _pair(self, reference, repository, bundle, *, selected):
        value=document(read_reference(reference,self.check))
        closed(value,('schema','identity','repository','bundle','roster','revision','tree','artifact','interpreter'))
        if (value['schema']!=PAIR_SCHEMA or value['identity']!=reference['identity']
                or value['repository']!=self.policy['repository_path'] or value['bundle']!=self.policy['bundle_path']): deny('PAIR')
        repository=path(repository);bundle=path(bundle)
        expected=document(read_reference(value['roster'],self.check))
        if self._roster(repository)!=expected: deny('BACKEND_ROSTER')
        if not (repository/'.git').is_dir() or (repository/'.git').is_symlink(): deny('GIT_DIRECTORY')
        from tools import runtime_source_gate as source_gate
        token=source_gate._SOURCE_BUDGET.set(self.budget)
        previous_git=source_gate._git
        def observed_git(root,*arguments):
            event=dict(event='SOURCE_DESTINATION_HELPER',argv=['/usr/bin/git',*map(str,arguments)],
                cwd=str(root),original_deadline_ns=self.original_deadline)
            self.events.append(event)
            try:value=previous_git(root,*arguments)
            except BaseException as error:
                event.update(exception=type(error).__name__,actual_exit=getattr(error,'returncode',None),
                    unresolved=admission.validation_unresolved())
                raise
            event.update(actual_exit=0,terminal_observation='EXISTING_VALIDATION_OWNER_RETURNED',
                normalized_stdout=value,encoding='EXISTING_SOURCE_GATE_DECODE_STRIP_PROTOCOL')
            return value
        if not _SDK_LOCK.acquire(timeout=max(0,(self.original_deadline-admission.monotonic_ns())/1e9)):
            source_gate._SOURCE_BUDGET.reset(token);deny('SOURCE_VALIDATOR_BUSY')
        try:
            source_gate._git=observed_git
            source_gate._destination_state(repository)
        finally:
            source_gate._git=previous_git;_SDK_LOCK.release();source_gate._SOURCE_BUDGET.reset(token)
        SOURCE_BRANCH,SOURCE_ORIGIN,SOURCE_REF=source_gate.SOURCE_BRANCH,source_gate.SOURCE_ORIGIN,source_gate.SOURCE_REF
        if (self._git(repository,'rev-parse','HEAD')!=value['revision'] or
                self._git(repository,'rev-parse','HEAD^{tree}')!=value['tree'] or
                self._git(repository,'status','--porcelain=v1','--untracked-files=all')): deny('GIT_STATE')
        if (self._git(repository,'branch','--show-current')!=SOURCE_BRANCH or
                self._git(repository,'config','--get','remote.origin.url')!=SOURCE_ORIGIN or
                self._git(repository,'config','--get','branch.'+SOURCE_BRANCH+'.remote')!='origin' or
                self._git(repository,'config','--get','branch.'+SOURCE_BRANCH+'.merge')!=SOURCE_REF): deny('GIT_PUBLICATION_CONFIGURATION')
        form=self._git(repository,'rev-parse','--show-object-format')
        if form not in {'sha1','sha256'}: deny('GIT_FORMAT')
        tracked=self._git(repository,'ls-tree','-rz','--full-tree','HEAD')
        git_entries={}
        for item in tracked.split('\0'):
            if not item: continue
            meta,name=item.split('\t');mode,kind,blob=meta.split()
            if (kind!='blob' or mode not in {'100644','100755'} or name in git_entries
                    or not re.fullmatch('[0-9a-f]{'+str(40 if form=='sha1' else 64)+'}',blob)): deny('GIT_ENTRY')
            git_entries[name]=(int(mode[-3:],8),blob)
        # Each row's manifest SHA-256 and selected-tree blob identity derive
        # from the SAME safely opened and change-checked immutable payload.
        if self._roster(repository,git_entries=git_entries,object_format=form)!=expected:deny('BACKEND_GIT_ROSTER')
        a,g,o=verify_source_pins(repository,selected=selected,check=self.check)
        if a not in (None,admission.PERSISTENT_ANCHOR_BINDING): deny('FOREIGN_BINDING')
        if (g is None)!=(o is None): deny('INCOMPLETE_ADMISSION_POLICY')
        artifact=document(read_reference(value['artifact'],self.check),final_lf=True)
        self._verify_bundle(bundle,artifact['bundle_identity'])
        if (artifact['schema']!='KRONOS_LAUNCHER_PACKAGE_V1' or artifact['source_revision']!=value['revision']
                or artifact['source_state']!='CLEAN_COMMIT' or package.manifest(bundle)!=artifact['bundle_manifest']
                or package.digest(repository/'tools/macos/kronos_launcher.c')!=artifact['source_launcher_sha256']
                or package.digest(repository/'tools/macos/package_launcher.py')!=artifact['procedure_sha256']
                or package.digest(bundle/package.BINARY)!=artifact['signed_binary_sha256']): deny('ARTIFACT_PAIR')
        for src,dst in zip(('tools/macos/KRONOS.app/'+x for x in package.RESOURCES),package.RESOURCES):
            if package.digest(repository/src)!=package.digest(bundle/dst): deny('COPIED_RESOURCE')
        interpreter=value['interpreter']
        closed(interpreter,('path','bytes','sha256','version','implementation','base_prefix'))
        # The full backend roster must contain dependency payloads, not only
        # names pointing into an unmeasured ambient installation. Only the
        # separately identified base Python executable may resolve outside it.
        for row in expected:
            if row['type']!='symlink':continue
            observed=(repository/row['path']).resolve(strict=True)
            if not observed.is_relative_to(repository):
                if (not re.fullmatch(r'\.venv/bin/python(?:[0-9]+(?:\.[0-9]+)*)?',row['path'])
                        or str(observed)!=interpreter['path']):deny('EXTERNAL_DEPENDENCY_ALIAS')
        self.check()

        executable=repository/'.venv/bin/python'
        resolved=executable.resolve(strict=True)
        if str(resolved)!=interpreter['path']: deny('INTERPRETER_PATH')
        actual,_=_read_regular(resolved,limit=256*1024**2,check=self.check)
        if len(actual)!=interpreter['bytes'] or sha256(actual).hexdigest()!=interpreter['sha256']: deny('INTERPRETER_BYTES')
        probe=self.helper([str(executable),'-I','-S','-B','-c',
            'import sys,json;print(json.dumps(dict(version=sys.version,implementation=sys.implementation.name,base_prefix=sys.base_prefix),sort_keys=True))'],repository,'PLACEMENT_INTERPRETER')
        observed=json.loads(probe)
        if observed!={k:interpreter[k] for k in ('version','implementation','base_prefix')}: deny('INTERPRETER_OBSERVATION')
        if self._roster(repository)!=expected: deny('BACKEND_CHANGED')
        return value

    def _discover(self, roots):
        matches=[]
        for root in roots:
            root=path(root)
            if not root.exists(): continue
            for p in root.iterdir():
                if p.name.startswith('.'): continue
                if ((p/'.git').is_dir() and (p/'pyproject.toml').is_file()
                        and os.access(p/'.venv/bin/python',os.X_OK) and (p/'tools/kronos_browser.py').is_file()
                        and (p/'src/kronos').is_dir()): matches.append(str(p))
        if matches!=[self.policy['repository_path']]: deny('SINGLE_REPOSITORY')

    def _sync_dir(self,p):
        with self.io():
            fd=os.open(path(p),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try:os.fsync(fd)
            finally:os.close(fd)

    def _write(self,p,raw,*,mode=0o600):
        p=path(p)
        with self.io():
            directory=_directory_fd(p.parent)
            try:fd=os.open(p.name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,mode,dir_fd=directory)
            except BaseException:os.close(directory);raise
            try:
                used=0
                while used<len(raw):
                    self.check()
                    try:n=os.write(fd,raw[used:used+65536])
                    except InterruptedError:continue
                    if n<=0: deny('ZERO_WRITE')
                    used+=n
                os.fchmod(fd,mode);os.fsync(fd)
            finally:
                try:os.close(fd)
                finally:os.close(directory)
        self._sync_dir(p.parent)
        observed,_=_read_regular(p,limit=max(MAX_DOCUMENT,len(raw)),check=self.check,private=mode==0o600)
        if observed!=raw: deny('WRITE_READBACK')

    def _copy_tree(self,source,destination):
        rows=self._roster(source);destination=path(destination)
        for row in rows:
            self.check();src=Path(source)/row['path'];dst=destination/row['path']
            if row['type']=='directory':
                with self.io():dst.mkdir(mode=row['mode'])
            elif row['type']=='symlink':
                with self.io():os.symlink(row['target'],dst)
            else:
                raw,_=_read_regular(src,limit=1024**3,check=self.check)
                self._write(dst,raw,mode=row['mode'])
            if row['type']!='directory':self._sync_dir(dst.parent)
        for row in reversed(rows):
            if row['type']=='directory':self._sync_dir(destination/row['path'])
        self._sync_dir(destination.parent)
        if self._roster(destination)!=rows or self._roster(source)!=rows: deny('COPY_CHANGED')

    def _admission_state(self,stage,installation):
        anchor=Path(installation['anchor_path']);journal=anchor/'failed-successor-restore-v1'
        if os.path.lexists(anchor/'ordinary-start-v1'): deny('ALREADY_ACTIVATED_OR_PARTIAL')
        if stage=='PREPARATORY':
            if restoration.INITIALIZATION_DISPOSITION is not None or bootstrap.ORDINARY_RESTART_POLICY is not None or os.path.lexists(journal): deny('NOT_PREPARATORY')
        elif stage=='FINAL_UNACTIVATED':
            if restoration.INITIALIZATION_DISPOSITION is None or bootstrap.ORDINARY_RESTART_POLICY is None: deny('NOT_ADMITTED')
            restoration._initialization_admission(journal,installation,checks=self)
            head=document(_read_regular(journal/'admission-head.json',limit=65535,check=self.check,private=True)[0])
            if head['sequence']!=1 or head['state']!='NATIVE_ACTIVATED' or any(journal.glob('head-2*')): deny('ADMISSION_TRANSITION_EXISTS')
            descriptor=document(restoration.INITIALIZATION_DISPOSITION)
            token=dict(disposition_sha256=sha256(restoration.INITIALIZATION_DISPOSITION).hexdigest(),
                attempt=descriptor['attempt'],head=descriptor['genesis_head'],phase=descriptor['genesis_phase'])
            if hasattr(self,'admitted_genesis') and self.admitted_genesis!=token:deny('GENESIS_CHANGED')
            return token
        else: deny('STAGE')

    def _completed_placement(self,reference,directory,stage):
        """Current evidence correspondence, never original timely completion."""
        if reference is None or reference['path']!=str(directory/'placement.prepared.json'):deny('PLACEMENT_LINEAGE')
        prepared=document(read_reference(reference,self.check))
        original=document(read_reference(prepared['order'],self.check))
        closed(original,self.order)
        if (original['schema']!=SCHEMA or original['operation']!='PLACE' or original['stage']!=stage
                or original['identity']!=prepared['identity'] or reference['identity']!=prepared['identity']
                or any(original[k]!=self.order[k] for k in ('installation_identity','binding_sha256','enrollment'))):deny('PLACEMENT_LINEAGE')
        closed(original['decisions'],('sponsor','ca','pcp','product'))
        for ref in original['decisions'].values():read_reference(ref,self.check)
        extra={}
        if stage=='PREPARATORY':
            if original['prior'] is not None:deny('PLACEMENT_LINEAGE')
        else:
            previous,_=self._completed_placement(original['prior'],directory.parent,'PREPARATORY')
            if original['current']!=previous['selected']:deny('PLACEMENT_LINEAGE')
            extra=dict(prior_preparation=original['prior'],admitted_genesis=self.admitted_genesis)
        expected=dict(schema='KRONOS_INITIAL_PLACEMENT_PREPARED_V1',identity=original['identity'],
            order=prepared['order'],selected=original['selected'],original_outcome='UNPROVED',
            deadline_ns=prepared['deadline_ns'],boot=prepared['boot'],launched=False,**extra)
        if (prepared!=expected or prepared['launched'] is not False
                or type(prepared['deadline_ns']) is not int or prepared['deadline_ns']<=0
                or not isinstance(prepared['boot'],str) or not prepared['boot']):deny('PLACEMENT_LINEAGE')
        def retained(name):return document(_read_regular(directory/name,limit=MAX_DOCUMENT,check=self.check,private=True)[0])
        intent=retained('placement.intent.json')
        intent_expected=dict(schema='KRONOS_INITIAL_PLACEMENT_ATTEMPT_V1',identity=original['identity'],
            order=prepared['order'],current=original['current'],selected=original['selected'],
            boot=prepared['boot'],deadline_ns=prepared['deadline_ns'],original_outcome='UNPROVED',**extra)
        closed(intent,(*intent_expected,'started_ns'))
        if (any(intent[k]!=v for k,v in intent_expected.items()) or type(intent['started_ns']) is not int
                or not 0<intent['started_ns']<intent['deadline_ns']):deny('PLACEMENT_LINEAGE')
        current=document(read_reference(original['current'],self.check))
        if retained('placement.checkpointed.json')!=dict(original_outcome='UNPROVED',backend_roster=current['roster'],selected=original['selected']):deny('PLACEMENT_LINEAGE')
        if retained('placement.backend-swapped.json')!=dict(original_outcome='UNPROVED',selected=original['selected']):deny('PLACEMENT_LINEAGE')
        returned=retained('placement.app-returned.json');closed(returned,('original_outcome','result'))
        result=returned['result'];closed(result,('installed_identity','rollback_identity','rollback','exchanged_original','launched'))
        selected=document(read_reference(original['selected'],self.check))
        old_artifact=document(read_reference(current['artifact'],self.check),final_lf=True)
        new_artifact=document(read_reference(selected['artifact'],self.check),final_lf=True)
        exchanged=path(result['exchanged_original']);bundle=Path(self.policy['bundle_path'])
        if (returned['original_outcome']!='UNPROVED' or result['launched'] is not False
                or result['installed_identity']!=new_artifact['bundle_identity']
                or result['rollback_identity']!=old_artifact['bundle_identity']
                or result['rollback']!=str(directory/'placement.app-installer.rollback')
                or exchanged.name!='KRONOS.app' or exchanged.parent.parent!=bundle.parent
                or not exchanged.parent.name.startswith('.kronos-install-')):deny('PLACEMENT_LINEAGE')
        allowed={'placement.'+n for n in ('intent.json','checkpointed.json','backend-swapped.json','app-returned.json','prepared.json','checkpoint.backend','staged.backend','checkpoint.app','app-installer.rollback')}
        if type(original['private_inputs']) is not list or len(original['private_inputs'])>128:deny('PLACEMENT_LINEAGE')
        for item in original['private_inputs']:
            closed(item,('source','destination'));target=path(item['destination'])
            if target.parent!=directory:deny('PLACEMENT_LINEAGE')
            if _read_regular(target,limit=MAX_DOCUMENT,check=self.check,private=True)[0]!=read_reference(item['source'],self.check):deny('PLACEMENT_LINEAGE')
            allowed.add(target.name)
        fd=_directory_fd(directory)
        try:
            if stat.S_IMODE(os.fstat(fd).st_mode)!=0o700 or set(os.listdir(fd))-(set([FINAL_STAGE]) if stage=='PREPARATORY' else set())!=allowed:deny('PLACEMENT_HISTORY')
        finally:os.close(fd)
        return original,result

    def _verify_retained_checkpoint(self,directory,original,result):
        # These helpers run only after the NEW exclusive intent is durable.
        value=self._pair(original['current'],directory/'placement.checkpoint.backend',directory/'placement.checkpoint.app',selected=False)
        if self._roster(directory/'placement.staged.backend')!=document(read_reference(value['roster'],self.check)):deny('PLACEMENT_CHECKPOINT')
        artifact=document(read_reference(value['artifact'],self.check),final_lf=True)
        self._verify_bundle(directory/'placement.app-installer.rollback',artifact['bundle_identity'])
        self._verify_bundle(result['exchanged_original'],artifact['bundle_identity'])

    def execute(self,order_reference):
        with self._lock:
            if self.entered: deny('SINGLE_FLIGHT_OR_REPLAY')
            self.entered=True;self.owner=threading.current_thread()
        try:
            order=document(read_reference(order_reference,self.check))
            closed(order,('schema','identity','operation','stage','installation_identity','binding_sha256','enrollment','executor',
                'current','selected','selected_backend','selected_bundle','control','private_inputs','prior','valid_from','valid_until','decisions'))
            if order['schema']!=SCHEMA or order['identity']!=order_reference['identity'] or order['operation'] not in {'PLACE','ROLLBACK'}: deny('ORDER')
            now=datetime.now(timezone.utc);start=datetime.fromisoformat(order['valid_from']);end=datetime.fromisoformat(order['valid_until'])
            if start.tzinfo is None or end.tzinfo is None or not start<=now<=end: deny('ORDER_TIME')
            self.order=order;self.valid_until=end;self.initial_utc=now;self.last_utc=now
            if type(order['private_inputs']) is not list or len(order['private_inputs'])>128:deny('INPUT_LIST')
            if type(admission.PERSISTENT_ANCHOR_BINDING) is not bytes or sha256(admission.PERSISTENT_ANCHOR_BINDING).hexdigest()!=order['binding_sha256']: deny('BINDING')
            executor=read_reference(order['executor'],self.check,private=False)
            if path(order['executor']['path'])!=Path(__file__).resolve() or executor!=Path(__file__).read_bytes(): deny('EXECUTOR')
            closed(order['decisions'],('sponsor','ca','pcp','product'))
            for ref in order['decisions'].values():read_reference(ref,self.check)
            installation=self._acquire(order['enrollment'])
            if installation['identity']!=order['installation_identity']: deny('INSTALLATION')
            repo=path(installation['repository_path']);bundle=path(installation['bundle_path']);home=Path(installation['anchor_path']).parents[3]
            roots=[home/'Documents/GitHub',home/'Developer',home/'Projects']
            if repo.parent not in roots: deny('DISCOVERY_PATH')
            self._discover(roots);self.admitted_genesis=self._admission_state(order['stage'],installation);self._absent(order['control'])
            history=path(Path(installation['anchor_path']).parent/JOURNAL_NAME)
            directory=history if order['stage']=='PREPARATORY' else history/FINAL_STAGE
            if any(history==p or p in history.parents or history in p.parents for p in (repo,bundle,Path(installation['anchor_path']))): deny('JOURNAL_PATH')
            selected_repo=path(order['selected_backend']);selected_bundle=path(order['selected_bundle'])
            for p in (selected_repo,selected_bundle):
                if any(p==q or q in p.parents or p in q.parents for q in [*roots,repo,bundle,Path(installation['anchor_path'])]+([history] if order['operation']=='PLACE' else [])): deny('STAGING_DISCOVERABLE_OR_OVERLAP')
            lineage={};retained=None
            if order['operation']=='PLACE':
                if os.path.lexists(directory): deny('PRIOR_OR_REPLAY')
                if order['stage']=='PREPARATORY':
                    if order['prior'] is not None:deny('PRIOR_OR_REPLAY')
                else:
                    original,result=self._completed_placement(order['prior'],history,'PREPARATORY')
                    if order['current']!=original['selected'] or order['identity']==original['identity']:deny('PLACEMENT_LINEAGE')
                    lineage=dict(prior_preparation=order['prior'],admitted_genesis=self.admitted_genesis)
                    retained=(history,original,result)
            else:
                if order['stage']=='PREPARATORY' and os.path.lexists(history/FINAL_STAGE):deny('LATER_STAGE_EXISTS')
                original,result=self._completed_placement(order['prior'],directory,order['stage'])
                if original['current']!=order['selected'] or original['selected']!=order['current']: deny('ROLLBACK_PAIR')
                if selected_repo!=directory/'placement.checkpoint.backend' or selected_bundle!=directory/'placement.checkpoint.app': deny('ROLLBACK_CHECKPOINT')
                if order['stage']=='FINAL_UNACTIVATED':lineage=dict(prior_preparation=original['prior'],admitted_genesis=self.admitted_genesis)
                retained=(directory,original,result)
                # Original complete prepared bytes do not establish timely success.
                self._sync_dir(directory)
            self._absent(order['control']);self._admission_state(order['stage'],installation)
            if order['operation']=='PLACE':
                with self.io():directory.mkdir(mode=0o700)
                self._sync_dir(directory.parent)
            self.directory=directory;stem='placement' if order['operation']=='PLACE' else 'rollback'
            intent=dict(schema='KRONOS_INITIAL_PLACEMENT_ATTEMPT_V1',identity=order['identity'],order=order_reference,
                current=order['current'],selected=order['selected'],boot=self.budget.boot_identity,
                started_ns=admission.monotonic_ns(),deadline_ns=self.original_deadline,original_outcome='UNPROVED',**lineage)
            self._write(directory/(stem+'.intent.json'),canonical(intent))
            if retained is not None:self._verify_retained_checkpoint(*retained)
            current=self._pair(order['current'],repo,bundle,selected=False)
            selected=self._pair(order['selected'],selected_repo,selected_bundle,selected=order['operation']=='PLACE')
            if selected['identity']==current['identity']: deny('NO_PAIR_CHANGE')

            checkpoint=directory/(stem+'.checkpoint.backend');staged=directory/(stem+'.staged.backend')
            self._copy_tree(repo,checkpoint);self._copy_tree(selected_repo,staged)
            self._copy_tree(bundle,directory/(stem+'.checkpoint.app'))
            old_artifact=document(read_reference(current['artifact'],self.check),final_lf=True)
            self._verify_bundle(directory/(stem+'.checkpoint.app'),old_artifact['bundle_identity'])
            # Private reader inputs only, explicitly approved and outside every
            # mutable owner/admission namespace. Never overwrite any input.
            for ref in order['private_inputs']:
                closed(ref,('source','destination'))
                dst=path(ref['destination'])
                if directory not in dst.parents or dst.parent!=directory: deny('PRIVATE_INPUT_LOCATION')
                self._write(dst,read_reference(ref['source'],self.check))
            self._write(directory/(stem+'.checkpointed.json'),canonical(dict(original_outcome='UNPROVED',backend_roster=current['roster'],selected=order['selected'])))
            self._absent(order['control']);self._pair(order['current'],repo,bundle,selected=False)
            with self.io():package.exchange(staged,repo)
            self._sync_dir(repo.parent);self._sync_dir(staged.parent)
            self._write(directory/(stem+'.backend-swapped.json'),canonical(dict(original_outcome='UNPROVED',selected=order['selected'])))
            self._absent(order['control'])
            artifact=document(read_reference(selected['artifact'],self.check),final_lf=True)
            old_artifact=document(read_reference(current['artifact'],self.check),final_lf=True)
            with self.io():
                installed=package.install(selected_bundle,bundle,candidate_identity=artifact['bundle_identity'],
                    installed_identity=old_artifact['bundle_identity'],rollback=directory/(stem+'.app-installer.rollback'),
                    verifier=self._verify_bundle,swap=self._exchange)
            self._sync_dir(bundle.parent);self._sync_dir(directory)
            self._write(directory/(stem+'.app-returned.json'),canonical(dict(original_outcome='UNPROVED',result=installed)))
            self._pair(order['selected'],repo,bundle,selected=order['operation']=='PLACE');self._discover(roots)
            self._admission_state(order['stage'],installation);self._absent(order['control']);self.check()
            now=datetime.now(timezone.utc)
            if now<self.initial_utc or now>self.valid_until: deny('ORDER_EXPIRED_OR_ROLLBACK')
            prepared=dict(schema='KRONOS_INITIAL_PLACEMENT_PREPARED_V1',identity=order['identity'],
                order=order_reference,selected=order['selected'],original_outcome='UNPROVED',
                deadline_ns=self.original_deadline,boot=self.budget.boot_identity,launched=False,**lineage)
            self._write(directory/(stem+'.prepared.json'),canonical(prepared));self.check()
            return prepared
        except BaseException as error:
            if admission.validation_unresolved() or (self.descriptor is not None and isinstance(error,(OSError,KeyboardInterrupt))):self.unresolved=True
            raise

    def close(self):
        """Actual resources separately from placement outcome. No renewed budget."""
        with self._lock:
            if self.active_io or (self.owner is not None and self.owner is not threading.current_thread() and self.owner.is_alive()):self.unresolved=True
            if admission.validation_unresolved():self.unresolved=True
            if self.unresolved or admission.kernel_boot_identity()!=self.budget.boot_identity or admission.monotonic_ns()>=self.original_deadline:
                self.unresolved=True;return dict(state='UNRESOLVED',custody_retained=self.descriptor is not None,active_io=self.active_io)
            if self.descriptor is not None:
                os.close(self.descriptor);self.descriptor=None
            if admission.monotonic_ns()>=self.original_deadline:
                self.unresolved=True;return dict(state='UNRESOLVED',custody_retained=False,active_io=self.active_io)
            return dict(state='CLOSED',custody_retained=False,active_io=0)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=('place','rollback'))
    parser.add_argument('--order-ref',required=True,help='Canonical JSON identity/path/bytes/sha256 reference')
    args=parser.parse_args(argv);owner=Placement();code=1
    try:
        ref=document(args.order_ref.encode())
        order=document(read_reference(ref,owner.check))
        if order['operation']!=args.operation.upper():deny('COMMAND_OPERATION')
        result=owner.execute(ref);print(json.dumps(result,sort_keys=True),flush=True);code=0
    except BaseException as error:
        print(type(error).__name__+': '+str(error),file=sys.stderr,flush=True)
        if isinstance(error,(KeyboardInterrupt,SystemExit)):raise
    finally:
        disposition=owner.close();print(json.dumps(dict(resource_disposition=disposition,events=owner.events),sort_keys=True),file=sys.stderr,flush=True)
        if disposition['state']!='CLOSED' and owner.descriptor is not None:
            admission.retain_failure_custody(owner,[admission])
    if code==0:
        try:owner.check()
        except BaseException:return 1
        if disposition['state']!='CLOSED':return 1
    return code


if __name__=='__main__':
    raise SystemExit(main())
