"""Installation-scoped startup custody, not release or provisioning authority.

Production binding names the separately approved installation identity.
No path/environment discovery may replace it or turn a missing binding into
permission. Fixture callers may exercise the same primitives with private anchors.
"""
from __future__ import annotations

import ctypes
from dataclasses import dataclass
import fcntl
import json
import os
from pathlib import Path
import stat
import sys
import time
import selectors
import subprocess
import signal

ADMISSION_DESCRIPTOR = 197
PRODUCTION_ANCHOR = Path("/Users/imranali/Library/Application Support/KRONOS/runtime")
CANONICAL_PARENT = "/Applications/KRONOS.app/Contents/MacOS/KRONOS"


@dataclass(frozen=True)
class AnchorBinding:
    path: Path
    device: int
    inode: int
    owner: int


APPROVED_BINDING = AnchorBinding(PRODUCTION_ANCHOR, 16777232, 694844364, 501)


# E02 compatibility is opt-in exact-source policy, never caller configuration.
PERSISTENT_ANCHOR_BINDING = b'{"anchor_path":"/Users/imranali/Library/Application Support/KRONOS/runtime","bundle_id":"com.project-kronos.browser-v1","bundle_path":"/Applications/KRONOS.app","enrollment":{"bytes":355,"identity":"5e6222c665fdb83f0750ff7ef4e0aa4c9423c8d82ece3554869d98817448aad6","path":"/Users/imranali/Library/Application Support/KRONOS/runtime/e02-frozen-enrollment.json","sha256":"f09519b6d460d2c5b6fe8405f0d0dc0beeff521ae5195fd9f9e023aa28afab8c"},"file_id":694844364,"installation_identity":"5e6222c665fdb83f0750ff7ef4e0aa4c9423c8d82ece3554869d98817448aad6","owner":501,"repository_path":"/Users/imranali/Documents/GitHub/Project-Kronos","required_mode":"0700","schema":"KRONOS_PERSISTENT_ANCHOR_BINDING_V1","volume_uuid":"ef7987a8-eb54-439a-8694-b1b1d87ead2c"}'


def _canonical_document(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def kernel_boot_identity():
    import uuid
    if sys.platform != 'darwin': _deny()
    library = ctypes.CDLL(None, use_errno=True)
    value = ctypes.create_string_buffer(64)
    length = ctypes.c_size_t(len(value))
    if library.sysctlbyname(b'kern.bootsessionuuid', value, ctypes.byref(length), None, 0) != 0:
        _deny()
    try:
        result = str(uuid.UUID(value.value.decode('ascii')))
    except (ValueError, UnicodeError): _deny()
    if length.value != 37: _deny()
    return result


def kernel_process_birth(pid):
    from hashlib import sha256
    class BsdInfo(ctypes.Structure):
        _fields_=[(n,ctypes.c_uint32) for n in ('flags','status','xstatus','pid','ppid','uid','gid',
            'ruid','rgid','svuid','svgid','reserved')]+[('comm',ctypes.c_char*16),('name',ctypes.c_char*32)]
        _fields_ += [(n,ctypes.c_uint32) for n in ('nfiles','pgid','pjobc','tdev','tpgid')]
        _fields_ += [('nice',ctypes.c_int32),('seconds',ctypes.c_uint64),('microseconds',ctypes.c_uint64)]
    value=BsdInfo()
    if (sys.platform!='darwin' or pid<2 or ctypes.sizeof(value)!=136
            or ctypes.CDLL('/usr/lib/libproc.dylib').proc_pidinfo(pid,3,0,ctypes.byref(value),ctypes.sizeof(value))!=ctypes.sizeof(value)
            or value.pid!=pid or not value.seconds or value.microseconds>=1000000):_deny()
    return sha256(str(value.seconds*1000000+value.microseconds).encode()).hexdigest()


def descriptor_filesystem_identity(descriptor):
    """Independently query this opened object; returned masks/layout fail closed."""
    import struct
    import uuid
    if sys.platform != 'darwin': _deny()
    class Attributes(ctypes.Structure):
        _fields_ = [('count', ctypes.c_uint16), ('reserved', ctypes.c_uint16),
                    ('common', ctypes.c_uint32), ('volume', ctypes.c_uint32),
                    ('directory', ctypes.c_uint32), ('file', ctypes.c_uint32),
                    ('fork', ctypes.c_uint32)]
    library = ctypes.CDLL(None, use_errno=True)
    library.fgetattrlist.argtypes = [ctypes.c_int, ctypes.POINTER(Attributes),
                                    ctypes.c_void_p, ctypes.c_size_t, ctypes.c_ulong]
    values = []
    for common, volume, size, returned_common, returned_volume in (
            (0x82000000, 0, 32, 0x82000000, 0),
            (0x80000000, 0x80040000, 40, 0x80000000, 0x80040000)):
        attributes = Attributes(5, 0, common, volume, 0, 0, 0)
        buffer = ctypes.create_string_buffer(128)
        if library.fgetattrlist(descriptor, ctypes.byref(attributes), buffer, len(buffer), 0) != 0:
            _deny()
        raw = buffer.raw
        masks = struct.unpack_from('=5I', raw, 4)
        # ATTR_VOL_INFO is a request marker, not a returned attribute.
        if (struct.unpack_from('=I', raw)[0] != size or masks[0] != returned_common
                or masks[1] not in {returned_volume, returned_volume & 0x7fffffff}
                or any(masks[2:])): _deny()
        values.append(raw[24:size])
    file_id = struct.unpack('=Q', values[0])[0]
    if not file_id or values[1] == bytes(16) or file_id != os.fstat(descriptor).st_ino:
        _deny()
    return dict(volume_uuid=str(uuid.UUID(bytes=values[1])), file_id=file_id)


def _private_reference_path(reference):
    if (type(reference) is not dict or set(reference) != {'identity','path','bytes','sha256'}
            or type(reference['bytes']) is not int or not 1 <= reference['bytes'] <= 65535): _deny()
    path = Path(reference['path'])
    if not path.is_absolute() or any(part in {'.','..'} for part in path.parts): _deny()
    return path


def _private_reference(reference):
    from hashlib import sha256
    path = _private_reference_path(reference)
    directory = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
            os.close(directory); directory = child
            info = os.fstat(directory)
            if info.st_uid not in {0,os.getuid()} or info.st_mode & 0o022: _deny()
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=directory)
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                    or stat.S_IMODE(before.st_mode) != 0o600 or before.st_size != reference['bytes']): _deny()
            raw = bytearray()
            while len(raw) <= reference['bytes']:
                chunk = os.read(fd, reference['bytes'] + 1 - len(raw))
                if not chunk: break
                raw.extend(chunk)
            after = os.fstat(fd); named = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
            fields = lambda s: (s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
            if fields(before) != fields(after) or fields(after) != fields(named): _deny()
            if len(raw) != reference['bytes'] or sha256(raw).hexdigest() != reference['sha256']: _deny()
            return bytes(raw)
        finally: os.close(fd)
    finally: os.close(directory)


def _persistent_binding_bytes(binding, raw):
    """One identical P/L predicate for installed and placement-only inputs."""
    from hashlib import sha256
    if not isinstance(binding, AnchorBinding): _deny()
    if type(PERSISTENT_ANCHOR_BINDING) is not bytes: _deny()
    value = json.loads(PERSISTENT_ANCHOR_BINDING)
    fields = {'schema','installation_identity','enrollment','anchor_path','volume_uuid',
              'file_id','owner','required_mode','bundle_id','bundle_path','repository_path'}
    if (type(value) is not dict or set(value) != fields
            or PERSISTENT_ANCHOR_BINDING != _canonical_document(value)
            or value['schema'] != 'KRONOS_PERSISTENT_ANCHOR_BINDING_V1'
            or value['anchor_path'] != str(binding.path) or value['file_id'] != binding.inode
            or value['owner'] != binding.owner or value['required_mode'] != '0700'): _deny()
    _private_reference_path(value['enrollment'])
    enrollment = json.loads(raw)
    if (raw != _canonical_document(enrollment)
            or set(enrollment) != {'identity','anchor_path','device','inode','owner','bundle_id','bundle_path','repository_path'}
            or enrollment['identity'] != value['installation_identity']
            or enrollment['identity'] != value['enrollment']['identity']
            or sha256(_canonical_document({k:v for k,v in enrollment.items() if k!='identity'})).hexdigest() != enrollment['identity']
            or (enrollment['device'],enrollment['inode'],enrollment['owner']) != (binding.device,binding.inode,binding.owner)
            or any(enrollment[k] != value[k] for k in ('anchor_path','bundle_id','bundle_path','repository_path'))): _deny()
    import uuid
    if str(uuid.UUID(value['volume_uuid'])) != value['volume_uuid']: _deny()
    return value, enrollment


def persistent_binding(binding):
    """Ordinary readers always require the exact installed enrollment file."""
    if PERSISTENT_ANCHOR_BINDING is None: return None
    if type(PERSISTENT_ANCHOR_BINDING) is not bytes: _deny()
    policy = json.loads(PERSISTENT_ANCHOR_BINDING)
    return _persistent_binding_bytes(binding, _private_reference(policy['enrollment']))


def preview_enrollment(binding, reference, *, checks):
    """Read-only placement input; never adoption, publication or admission.

    Native holds actual exclusion. This helper independently validates the same
    source-pinned P/L bytes and opened anchor before L's destination exists.
    No ordinary reader or AdmissionCustody uses this preview path.
    """
    from hashlib import sha256
    checks.check(); checks.budget.check()
    raw = _private_reference(reference)
    policy, enrollment = _persistent_binding_bytes(binding, raw)
    expected = policy['enrollment']
    if (reference['identity'] != expected['identity']
            or len(raw) != expected['bytes'] or sha256(raw).hexdigest() != expected['sha256']
            or reference['path'] == expected['path']
            or Path(expected['path']).parent != binding.path): _deny()
    try: Path(expected['path']).lstat()
    except FileNotFoundError: pass
    else: _deny()
    descriptor = _open_bound_anchor(binding, (policy,enrollment))
    try:
        if descriptor_filesystem_identity(descriptor) != dict(
                volume_uuid=policy['volume_uuid'],file_id=policy['file_id']): _deny()
    finally: os.close(descriptor)
    checks.check(); checks.budget.check()
    return dict(enrollment)


def installation_matches(installation, binding, *, descriptor=None):
    selected = persistent_binding(binding)
    if selected is None:
        if (installation['anchor_path'] != str(binding.path)
                or (installation['device'],installation['inode'],installation['owner'])
                    != (binding.device,binding.inode,binding.owner)): return False
        fd = open_anchor(binding)
        try:
            if descriptor is not None:
                held, named = os.fstat(descriptor), os.fstat(fd)
                return (held.st_dev,held.st_ino,held.st_uid) == (named.st_dev,named.st_ino,named.st_uid)
            return True
        finally: os.close(fd)
    policy, frozen = selected
    if installation != frozen: return False
    owned = descriptor is None
    fd = open_anchor(binding) if owned else descriptor
    try:
        observed = descriptor_filesystem_identity(fd)
        return observed == dict(volume_uuid=policy['volume_uuid'],file_id=policy['file_id'])
    finally:
        if owned: os.close(fd)


def frozen_installation(repository, bundle, anchor):
    from hashlib import sha256
    binding = APPROVED_BINDING
    if PERSISTENT_ANCHOR_BINDING is not None and (binding is None or str(binding.path) != anchor): _deny()
    selected = persistent_binding(binding)
    if selected is not None:
        _, enrollment = selected
        if enrollment['repository_path'] != repository or enrollment['bundle_path'] != bundle: _deny()
        if not installation_matches(enrollment,binding): _deny()
        return dict(enrollment)
    metadata = Path(anchor).stat()
    core = dict(anchor_path=anchor,device=metadata.st_dev,inode=metadata.st_ino,owner=metadata.st_uid,
        bundle_id='com.project-kronos.browser-v1',bundle_path=bundle,repository_path=repository)
    return dict(identity=sha256(_canonical_document(core)).hexdigest(),**core)


def _deny():
    raise ValueError("INSTALLATION_ADMISSION_CUSTODY_INVALID")


def open_anchor(binding):
    """Walk existing components without following links or creating the anchor."""
    return _open_bound_anchor(binding, persistent_binding(binding))


def _open_bound_anchor(binding, compatibility):
    """Shared no-follow descriptor predicate; no lock or directory creation."""
    if (not isinstance(binding, AnchorBinding) or not binding.path.is_absolute()
            or binding.device <= 0 or binding.inode <= 0 or binding.owner != os.getuid()
            or any(x in {".", ".."} for x in binding.path.parts)):
        _deny()
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for component in binding.path.parts[1:]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
                            | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
            metadata = os.fstat(fd)
            if (metadata.st_uid not in {0, binding.owner} or metadata.st_mode & 0o022):
                _deny()
        metadata = os.fstat(fd)
        if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != binding.owner
                or metadata.st_mode & 0o077
                or metadata.st_ino != binding.inode):
            _deny()
        if compatibility is None:
            if metadata.st_dev != binding.device: _deny()
        elif (stat.S_IMODE(metadata.st_mode)!=0o700 or descriptor_filesystem_identity(fd) != dict(
                volume_uuid=compatibility[0]['volume_uuid'],file_id=compatibility[0]['file_id'])): _deny()
        return fd
    except BaseException:
        os.close(fd)
        raise


def _parent_image(pid):
    if sys.platform != "darwin" or pid < 2:
        _deny()
    buffer = ctypes.create_string_buffer(4096)
    if ctypes.CDLL("/usr/lib/libproc.dylib").proc_pidpath(pid, buffer, len(buffer)) <= 0:
        _deny()
    return os.fsdecode(buffer.value)


class AdmissionCustody:
    """Borrow the canonical parent's inherited open-file-description lock.

    The reviewed launcher retains its original EX throughout child validation and
    monitor disposition. Under that source-enforced invariant, EX success on the
    inherited descriptor plus independent-open conflict distinguishes shared OFD
    custody from an independent open, not merely matching stat metadata.
    """
    def __init__(self, descriptor, binding, parent, *, parent_image=_parent_image, budget=None):
        self.descriptor = descriptor
        self.binding = binding
        self.parent = parent
        self.parent_birth = kernel_process_birth(parent)
        self.parent_image = parent_image
        self.budget = budget
        self.released = False
        self.cleanup_started = False
        self.cleanup_complete = False
        self.boot_identity = kernel_boot_identity()
        self.anchor_observation = None
        # This happens before parent checks, capture or any helper execution.
        os.set_inheritable(descriptor, False)
        self.check()

    def check(self):
        if self.budget is not None:self.budget.check()
        if (kernel_boot_identity() != self.boot_identity or kernel_process_birth(self.parent)!=self.parent_birth or self.released or self.cleanup_started or os.getppid() != self.parent
                or self.parent_image(self.parent) != CANONICAL_PARENT):
            _deny()
        metadata = os.fstat(self.descriptor)
        if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != self.binding.owner
                or metadata.st_ino != self.binding.inode
                or os.get_inheritable(self.descriptor)):
            _deny()
        probe = open_anchor(self.binding)
        try:
            named = os.fstat(probe)
            if (metadata.st_dev,metadata.st_ino) != (named.st_dev,named.st_ino): _deny()
            observed = dict(boot_session=self.boot_identity,device=metadata.st_dev,
                inode=metadata.st_ino,owner=metadata.st_uid,parent=self.parent,parent_birth=self.parent_birth,
                parent_image=self.parent_image(self.parent))
            if self.anchor_observation is not None and observed != self.anchor_observation: _deny()
            self.anchor_observation = observed
            fcntl.flock(self.descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                pass
            else:
                _deny()
        finally:
            os.close(probe)  # Close only; never unlock the shared description.
        if os.getppid() != self.parent or self.parent_image(self.parent) != CANONICAL_PARENT:
            _deny()

    def release_ready(self, server):
        self.check()
        governance = server.connection_governance
        state = governance.maintenance_status()
        if (state.get("startup") != "READY" or state.get("active") is not False
                or state.get("failure") is not None or governance.shutting_down
                or getattr(server, "_domain_closed", False)
                or server.socket.fileno() < 0):
            _deny()
        process = governance.process
        receipt = governance.store.root / "maintenance" / (process.runtime_identity + "-startup.json")
        document = json.loads(receipt.read_bytes())
        if (document.get("schema") != "RUNTIME_STARTUP_MAINTENANCE_EXIT_V1"
                or document.get("runtime_identity") != process.runtime_identity
                or document.get("maintenance_identity") != governance.maintenance_identity
                or document.get("trigger") != "VERIFIED_CANONICAL_STARTUP"
                or not document.get("at")):
            _deny()
        self.check()
        self._close()

    def begin_failure_cleanup(self):
        self.cleanup_started = True

    def completed_failure_cleanup(self):
        if not self.cleanup_started:
            _deny()
        self._close()
        self.cleanup_complete = True

    def _close(self):
        if not self.released:
            os.close(self.descriptor)
            self.released = True


def adopt_from_launcher():
    if APPROVED_BINDING is None or APPROVED_BINDING.path != PRODUCTION_ANCHOR:
        raise ValueError("INSTALLATION_ADMISSION_BINDING_NOT_APPROVED")
    return AdmissionCustody(ADMISSION_DESCRIPTOR, APPROVED_BINDING, os.getppid(),
                           budget=inherited_budget(120, required=True))


# This is the narrow existing validation boundary, not a product worker supervisor.
_OWNED_VALIDATION_HELPERS = {}
_VALIDATION_UNRESOLVED = False


def monotonic_ns():
    return time.clock_gettime_ns(time.CLOCK_MONOTONIC)


class ValidationBudget:
    def __init__(self, deadline_ns):
        if type(deadline_ns) is not int or deadline_ns <= 0:
            raise ValueError("VALIDATION_CLOCK_DOMAIN_UNAVAILABLE")
        self.deadline_ns = deadline_ns
        self.boot_identity = kernel_boot_identity()
        self.failed = False

    def check(self):
        if kernel_boot_identity() != self.boot_identity:
            self.failed=True
            raise ValueError('VALIDATION_BOOT_CONTEXT_MISMATCH')
        if self.failed or monotonic_ns() >= self.deadline_ns:
            self.failed = True
            raise ValueError("VALIDATION_DEADLINE_EXPIRED")

    def capped(self, seconds):
        self.check()
        return min(self.deadline_ns, monotonic_ns() + int(seconds * 1_000_000_000))


def inherited_budget(ceiling, *, required=False):
    now = monotonic_ns()
    value = os.environ.get("KRONOS_VALIDATION_DEADLINE_NS")
    domain = os.environ.get("KRONOS_VALIDATION_CLOCK")
    if value is None and not required:
        return ValidationBudget(now + int(ceiling * 1_000_000_000))
    if domain != "CLOCK_MONOTONIC" or value is None or not value.isdecimal():
        raise ValueError("VALIDATION_CLOCK_DOMAIN_UNAVAILABLE")
    boot = os.environ.get('KRONOS_VALIDATION_BOOT_SESSION')
    if ((PERSISTENT_ANCHOR_BINDING is not None and boot is None)
            or (boot is not None and boot != kernel_boot_identity())):
        raise ValueError('VALIDATION_BOOT_CONTEXT_MISMATCH')
    result = ValidationBudget(min(int(value), now + int(ceiling * 1_000_000_000)))
    result.check()
    return result


def validation_environment(environment=None):
    original = os.environ if environment is None else environment
    approved = {"PATH", "HOME", "XDG_CONFIG_HOME", "SSH_AUTH_SOCK", "SSH_AGENT_PID",
        "SSH_ASKPASS", "SSH_ASKPASS_REQUIRE", "SSH_SK_PROVIDER", "DISPLAY", "XAUTHORITY", "TERM", "LANG", "TMPDIR",
        "DEVELOPER_DIR", "KRB5CCNAME", "KRB5_CONFIG", "KRB5_KTNAME",
        "USER", "LOGNAME", "SHELL", "PYTHONPATH", "PYTHONDONTWRITEBYTECODE",
        "__CF_USER_TEXT_ENCODING", "KRONOS_VALIDATION_CLOCK", "KRONOS_VALIDATION_DEADLINE_NS", "KRONOS_VALIDATION_BOOT_SESSION"}
    # Preserve actual Git transport/configuration selectors for the existing
    # destination validator to reject, never sanitize them into apparent approval.
    return {key: value for key, value in original.items()
            if key in approved or key.startswith(("LC_", "GIT_"))}


def validation_unresolved():
    return _VALIDATION_UNRESOLVED


def report_validation(phase, deadline, child, result, cleanup):
    global _VALIDATION_UNRESOLVED
    document = {"schema": "KRONOS_VALIDATION_OUTCOME_V1", "phase": phase,
        "clock": "CLOCK_MONOTONIC", "deadline_ns": deadline,
        "direct_child": child, "observed_result": result, "cleanup": cleanup}
    raw = (json.dumps(document, separators=(",", ":")) + "\n").encode()
    # Existing controlled-attempt stderr stream; never block a decision merely
    # to report it, and never print argv, input proof, environment or output.
    try:
        flags = fcntl.fcntl(2, fcntl.F_GETFL)
        fcntl.fcntl(2, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        # Shared open-file-description flags remain nonblocking for the full
        # concurrent startup-writer lifetime. No writer restores a stale value.
        if os.write(2, raw) != len(raw):_VALIDATION_UNRESOLVED = True
    except OSError:
        _VALIDATION_UNRESOLVED = True  # Missing output cannot discharge custody.


def validation_output(arguments, *, cwd, budget, ceiling, phase, input_bytes=b"", capacity=262144):
    """Bound one directly owned validation CLI; never signal groups/products.

    Expiry/failure is sticky. Killing or reaping this child does not certify the
    SSH/validator descendant chain; unresolved outcomes retain admission custody.
    """
    global _VALIDATION_UNRESOLVED
    if _VALIDATION_UNRESOLVED:
        raise ValueError("VALIDATION_CLEANUP_UNRESOLVED")
    try:
        deadline = budget.capped(ceiling)  # Before process creation and pipe exchange.
    except ValueError:
        report_validation(phase, budget.deadline_ns, None, "NOT_STARTED_DEADLINE", "NOT_STARTED")
        raise
    child = None
    result = "SPAWN_FAILURE"
    output = bytearray()
    try:
        if signal.getsignal(signal.SIGCHLD) != signal.SIG_DFL:
            result = "CHILD_OWNERSHIP_NOT_ESTABLISHED"
            _VALIDATION_UNRESOLVED = True
            raise ValueError("VALIDATION_CHILD_OWNERSHIP_UNAVAILABLE")
        environment = validation_environment()
        environment.update(KRONOS_VALIDATION_CLOCK="CLOCK_MONOTONIC",
                           KRONOS_VALIDATION_DEADLINE_NS=str(deadline),
                           KRONOS_VALIDATION_BOOT_SESSION=budget.boot_identity)
        child = subprocess.Popen(arguments, cwd=cwd, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=environment,
            close_fds=True)
        _OWNED_VALIDATION_HELPERS[child.pid] = child
        result = "IO_FAILURE"
        selector = selectors.DefaultSelector()
        try:
            for stream in (child.stdin, child.stdout): os.set_blocking(stream.fileno(), False)
            selector.register(child.stdout, selectors.EVENT_READ)
            sent = 0
            if input_bytes: selector.register(child.stdin, selectors.EVENT_WRITE)
            else: child.stdin.close()
            while selector.get_map() or child.poll() is None:
                remaining = (deadline - monotonic_ns()) / 1_000_000_000
                if remaining <= 0:
                    result = "DEADLINE_EXPIRED"
                    raise ValueError("VALIDATION_DEADLINE_EXPIRED")
                for key, events in selector.select(min(remaining, .02)):
                    try:
                        if key.fileobj is child.stdout:
                            raw = os.read(key.fd, min(65536, capacity + 1 - len(output)))
                            if not raw: selector.unregister(child.stdout)
                            else:
                                output.extend(raw)
                                if len(output) > capacity:
                                    result = "OUTPUT_LIMIT"
                                    raise ValueError("VALIDATION_OUTPUT_LIMIT")
                        else:
                            sent += os.write(key.fd, input_bytes[sent:sent + 65536])
                            if sent == len(input_bytes):
                                selector.unregister(child.stdin);child.stdin.close()
                    except (BlockingIOError, InterruptedError):
                        continue
            # Both the complete output and terminal result must precede deadline.
            if monotonic_ns() >= deadline:
                result = "LATE_RESULT"
                raise ValueError("VALIDATION_DEADLINE_EXPIRED")
            if child.returncode != 0:
                result = "CHILD_EXIT_" + str(child.returncode)
                if child.returncode == 79:
                    _VALIDATION_UNRESOLVED = True
                raise subprocess.CalledProcessError(child.returncode, arguments)
            _OWNED_VALIDATION_HELPERS.pop(child.pid, None)
            return bytes(output)
        finally:
            selector.close()
    except BaseException:
        budget.failed = True
        if child is not None:
            if child.poll() is None:
                # Exactly this Popen-owned direct child only, never a PID snapshot
                # or process group. No extra cleanup wait extends the decision.
                try:child.kill()
                except ProcessLookupError:pass
                child.poll()
                _VALIDATION_UNRESOLVED = True
            if result in {"DEADLINE_EXPIRED", "LATE_RESULT", "OUTPUT_LIMIT"}:
                _VALIDATION_UNRESOLVED = True
            if child.returncode is not None and not _VALIDATION_UNRESOLVED:
                _OWNED_VALIDATION_HELPERS.pop(child.pid, None)
        report_validation(phase, deadline, None if child is None else child.pid, result,
            "CLEANUP_UNRESOLVED" if _VALIDATION_UNRESOLVED else
            "NOT_STARTED" if child is None else "DIRECT_CHILD_OBSERVED")
        raise
    finally:
        if child is not None:
            for stream in (child.stdin, child.stdout):
                if stream is not None and not stream.closed: stream.close()


def retain_failure_custody(custody, helper_modules):
    """Decision is already denied/reported. Retain, never restart or reacquire.

    Only directly owned Popen objects are polled/reaped. Product cleanup is not
    retried, and observation of helper death never becomes clearance.
    """
    deadline = getattr(getattr(custody, "budget", None), "deadline_ns", 0)
    report_validation("BACKEND_CUSTODY", deadline, os.getpid(),
                      "STARTUP_DENIED_CUSTODY_RETAINED", "CLEANUP_UNRESOLVED")
    while True:
        for module in helper_modules:
            children = getattr(module, "_OWNED_VALIDATION_HELPERS", {})
            if isinstance(children, dict):
                for child in tuple(children.values()):
                    try:child.poll()  # Exact ownership only; never clearance.
                    except BaseException:pass
        time.sleep(.1)


def validate_installation_anchor(installation, checks):
    binding = getattr(checks, 'binding', None)
    if binding is None:
        binding = (APPROVED_BINDING if PERSISTENT_ANCHOR_BINDING is not None else
            AnchorBinding(Path(installation['anchor_path']),installation['device'],
                installation['inode'],installation['owner']))
    if not isinstance(binding,AnchorBinding):
        binding = AnchorBinding(binding.path,binding.device,binding.inode,binding.owner)
    return (installation_matches(installation,binding,descriptor=getattr(checks,'descriptor',None))
            and setup_genesis_bound(installation, checks))


SETUP_DIRECTORY = 'controlled-setup-v1'
SETUP_ATTEMPT_SCHEMA = 'KRONOS_CONTROLLED_SETUP_ATTEMPT_V1'
SETUP_ORDER_SCHEMA = 'KRONOS_CONTROLLED_SETUP_ORDER_V1'
SETUP_OPERATIONS = {'PLACE_ENROLLMENT':'enrollment',
                    'PRESERVE_STALE_CONTROL':'stale-control',
                    'ACTIVATE_SELECTION':'activation'}


def _setup_check(checks):
    if checks is None or getattr(checks,'budget',None) is None: _deny()
    checks.check(); checks.budget.check()


def _setup_current(directory, name, path, identity, checks):
    """Bounded no-follow current bytes, not evidence of completed publication."""
    from hashlib import sha256
    _setup_check(checks)
    fd = os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=directory)
    try:
        before=os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid!=os.getuid()
                or stat.S_IMODE(before.st_mode)!=0o600 or not 0<before.st_size<=65535): _deny()
        raw=bytearray()
        while len(raw)<=65535:
            _setup_check(checks)
            part=os.read(fd,min(16384,65536-len(raw)))
            if not part:break
            raw.extend(part)
        after=os.fstat(fd);named=os.stat(name,dir_fd=directory,follow_symlinks=False)
        fields=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        if fields(before)!=fields(after) or fields(after)!=fields(named) or len(raw)!=before.st_size: _deny()
    finally:os.close(fd)
    _setup_check(checks)
    return bytes(raw),dict(identity=identity,path=str(path),bytes=len(raw),sha256=sha256(raw).hexdigest())


def setup_preparation_inputs(installation, checks):
    """Observe the initial setup namespace; no success file clears its fence.

    A complete pre-genesis preparation can be considered by the separately
    authorized initializer and later exact G review. Empty/partial/foreign
    namespaces deny across invocations, regardless of a new budget.
    """
    from hashlib import sha256
    anchor=Path(installation['anchor_path'])
    binding=getattr(checks,'binding',None)
    if binding is None:
        binding=(APPROVED_BINDING if PERSISTENT_ANCHOR_BINDING is not None else
            AnchorBinding(anchor,installation['device'],installation['inode'],installation['owner']))
    if not isinstance(binding,AnchorBinding):
        binding=AnchorBinding(binding.path,binding.device,binding.inode,binding.owner)
    fd=open_anchor(binding)
    try:
        if str(binding.path)!=str(anchor): _deny()
        try:directory=os.open(SETUP_DIRECTORY,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
        except FileNotFoundError:return ()
        try:
            _setup_check(checks);before=os.fstat(directory)
            if before.st_uid!=os.getuid() or stat.S_IMODE(before.st_mode)!=0o700: _deny()
            names=set(os.listdir(directory))
            allowed={'enrollment.intent.json','stale-control.intent.json','stale-control.original','activation.intent.json'}
            if (not names or not names<=allowed or 'enrollment.intent.json' not in names
                    or (('stale-control.original' in names) != ('stale-control.intent.json' in names))): _deny()
            if type(PERSISTENT_ANCHOR_BINDING) is not bytes:_deny()
            records=[]
            for operation,stem in SETUP_OPERATIONS.items():
                name=stem+'.intent.json'
                if name not in names:continue
                path=anchor/SETUP_DIRECTORY/name
                raw,reference=_setup_current(directory,name,path,'setup-'+stem,checks)
                document=json.loads(raw)
                if (raw!=_canonical_document(document) or set(document)!={
                        'schema','identity','operation','installation_identity','binding_sha256',
                        'order','input','preserved','parent','timing','original_outcome'}
                        or document['schema']!=SETUP_ATTEMPT_SCHEMA or document['identity']!=reference['identity']
                        or document['operation']!=operation or document['installation_identity']!=installation['identity']
                        or document['binding_sha256']!=sha256(PERSISTENT_ANCHOR_BINDING).hexdigest()
                        or document['original_outcome']!='UNPROVED'): _deny()
                timing=document['timing']
                if (type(timing) is not dict or set(timing)!={'boot_session','clock','started_ns','deadline_ns'}
                        or timing['clock']!='CLOCK_MONOTONIC' or type(timing['started_ns']) is not int
                        or type(timing['deadline_ns']) is not int or not 0<timing['started_ns']<timing['deadline_ns']): _deny()
                import uuid
                if str(uuid.UUID(timing['boot_session']))!=timing['boot_session']: _deny()
                parent=document['parent']
                if (type(parent) is not dict or set(parent)!={'pid','kernel_birth','runtime_identity','revision'}
                        or type(parent['pid']) is not int or parent['pid']<2): _deny()
                order_raw=_private_reference(document['order']);order=json.loads(order_raw)
                if (order_raw!=_canonical_document(order) or set(order)!={
                        'schema','identity','operation','installation_identity','binding_sha256',
                        'selection','input','valid_from','valid_until','decisions'}
                        or order['schema']!=SETUP_ORDER_SCHEMA or order['identity']!=document['order']['identity']
                        or any(order[k]!=document[k] for k in ('operation','installation_identity','binding_sha256','input'))): _deny()
                selected=json.loads(_private_reference(order['selection']))
                if (selected.get('installation')!=installation or selected.get('decisions')!=order['decisions']
                        or set(order['decisions'])!={'sponsor','ca','pcp','product'}): _deny()
                for authority in order['decisions'].values():_private_reference(authority)
                if operation=='PLACE_ENROLLMENT':
                    policy,frozen=persistent_binding(binding)
                    if (frozen!=installation or document['preserved'] is not None
                            or any(document['input'][k]!=policy['enrollment'][k] for k in ('identity','bytes','sha256'))): _deny()
                elif operation=='PRESERVE_STALE_CONTROL':
                    preserved=document['preserved'];expected_path=anchor/SETUP_DIRECTORY/'stale-control.original'
                    if (type(preserved) is not dict or preserved.get('path')!=str(expected_path)
                            or document['input']['path']!=str(anchor/'browser-backend-v1.control')
                            or any(preserved[k]!=document['input'][k] for k in ('bytes','sha256'))): _deny()
                    _private_reference(preserved)
                records.append(dict(reference=reference,document=document))
            after=os.fstat(directory);named=os.stat(SETUP_DIRECTORY,dir_fd=fd,follow_symlinks=False)
            fields=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_mtime_ns,s.st_ctime_ns)
            if fields(before)!=fields(after) or fields(after)!=fields(named): _deny()
            _setup_check(checks)
            return tuple(records)
        finally:os.close(directory)
    finally:os.close(fd)


def setup_genesis_bound(installation, checks):
    """Direct R3.1 and helper readers require explicit G-bound setup evidence."""
    records=setup_preparation_inputs(installation,checks)
    if not records:return True  # Unchanged approved legacy/disposable estates.
    from kronos.common import failed_successor_restore as restore
    if type(restore.INITIALIZATION_DISPOSITION) is not bytes:_deny()
    disposition=json.loads(restore.INITIALIZATION_DISPOSITION)
    evidence=json.loads(_private_reference(disposition['evidence']))
    observed=evidence['observations']+evidence['subsequent_observations']
    for row in records:
        if row['document']['operation']=='ACTIVATE_SELECTION':
            # The source-pinned ordinary policy conditionally permits this
            # complete immutable preparation, not a timely-outcome assertion.
            # Its one new reserved attempt must still do current assessment.
            from kronos.common import legacy_bootstrap as bootstrap
            bootstrap._prepared_activation_lineage(row['reference'],installation,checks)
            continue
        if sum(ref==row['reference'] for ref in observed)!=1:_deny()
    _setup_check(checks)
    return True
