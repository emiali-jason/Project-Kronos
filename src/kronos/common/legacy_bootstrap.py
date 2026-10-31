"""One-time, explicitly issued legacy migration; never an ordinary SPH handoff.

The coordinator owns a fresh migration proof. No Provider capability or legacy
shutdown token is placed in this contract. Production execution is separately gated.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, UTC
from hashlib import sha1, sha256
import ctypes
import hmac
import json
import os
from pathlib import Path
import plistlib
import re
import secrets
import socket
import stat
import subprocess

from kronos.common.connection_governance import _bytes
from kronos.common.maintenance import HANDOFF_SECONDS

SCHEMA = 'KRONOS_LEGACY_BOOTSTRAP_V1'
LEGACY_REVISION = '0dd6a74d3da25e52d0bd82326a30647f5111adce'
ENV_ID = 'KRONOS_LEGACY_BOOTSTRAP_ID'
ENV_PROOF = 'KRONOS_LEGACY_BOOTSTRAP_PROOF'
SIDE_EFFECT = 'EXPECTED_LEGACY_BOOTSTRAP_NOTIFICATION_SIDE_EFFECT'
RISK = 'LEGACY_SHUTDOWN_SIDE_EFFECT_RISK'

RESTORATION_MODE = 'FAILED_SUCCESSOR_RESTORATION'
RESTORATION_SELECTOR_ENV = (
    'KRONOS_RESTORATION_ORIGINAL_ATTEMPT_ID',
    'KRONOS_RESTORATION_PERMIT_PATH',
    'KRONOS_RESTORATION_PERMIT_BYTES',
    'KRONOS_RESTORATION_PERMIT_SHA256',
    'KRONOS_RESTORATION_PERMIT_ID',
    'KRONOS_RESTORATION_RESERVATION_PATH',
    'KRONOS_RESTORATION_RESERVATION_BYTES',
    'KRONOS_RESTORATION_RESERVATION_SHA256',
    'KRONOS_RESTORATION_RESERVATION_ID',
)
RESTORATION_CHILD_ENV = (
    'KRONOS_RESTORATION_PARENT_KERNEL_BIRTH',
    'KRONOS_RESTORATION_CHILD_KERNEL_BIRTH',
    'KRONOS_RESTORATION_SOURCE_MANIFEST_PATH',
    'KRONOS_RESTORATION_ARTIFACT_MANIFEST_PATH',
)


class BootstrapError(ValueError):
    """Closed, non-secret diagnostic; no raw HTTP/credential exception."""


@dataclass(frozen=True, slots=True)
class RestorationSelection:
    """Narrow non-secret selector supplied by the future native reservation."""

    original_attempt_id: str
    permit_path: Path
    permit_bytes: int
    permit_sha256: str
    permit_id: str
    reservation_path: Path
    reservation_bytes: int
    reservation_sha256: str
    reservation_id: str


@dataclass(frozen=True, slots=True)
class RestorationObservation:
    """Adapter-local proof completed before the R3.1 exclusive claim."""

    child: object
    repository: str
    installation_identity: str
    permit_sha256: str
    source_manifest_path: str
    artifact_manifest_path: str
    captured_sources: tuple
    loaded_modules: tuple
    load_verification: str


@dataclass(frozen=True, slots=True)
class RestorationAttempt:
    """In-process accepted identities; neither a new permit nor an R3.1 schema."""

    context: object
    observation: RestorationObservation
    selection: RestorationSelection
    environment: tuple
    custody: object
    budget: object
    deadline_ns: int
    head_reference: tuple
    claim_reference: tuple
    claimed_at: str
    validated_at: datetime


def _restoration_environment(environment):
    return tuple((name, environment.get(name)) for name in (
        'KRONOS_LAUNCH_MODE', *RESTORATION_SELECTOR_ENV, *RESTORATION_CHILD_ENV))


def _hex(value, size=64):
    return isinstance(value, str) and re.fullmatch('[a-f0-9]{'+str(size)+'}', value) is not None


def _aware(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise BootstrapError('BOOTSTRAP_TIME_INVALID')
    return parsed


def _secure(path: Path, *, directory=False):
    if not path.is_absolute() or '..' in path.parts or any(p.is_symlink() for p in (path, *path.parents)):
        raise BootstrapError('BOOTSTRAP_PATH_INVALID')
    s = path.lstat()
    if (s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) != (0o700 if directory else 0o600)
        or not (stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode))):
        raise BootstrapError('BOOTSTRAP_PERMISSIONS_INVALID')


def _root(path: Path, *, create=False):
    if not path.is_absolute() or '..' in path.parts or any(p.is_symlink() for p in (path, *path.parents)):
        raise BootstrapError('BOOTSTRAP_PATH_INVALID')
    if create:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
    _secure(path, directory=True)


def _read(path: Path):
    _secure(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as f:
        s = os.fstat(f.fileno())
        if s.st_uid != os.getuid() or s.st_mode & 0o077 or s.st_size > 32768:
            raise BootstrapError('BOOTSTRAP_PERMISSIONS_INVALID')
        return json.loads(f.read())


@dataclass(frozen=True)
class LegacyBinding:
    pid: int
    revision: str
    runtime: str
    startup: str
    configuration: str
    repository: str
    replacement_revision: str
    installed_launcher_sha256: str
    control_digest: str
    listener: str = '127.0.0.1:8947'

    def __post_init__(self):
        if (type(self.pid) is not int or self.pid < 2 or self.revision != LEGACY_REVISION
            or not re.fullmatch(r'INTRADAY-RUNTIME-[a-f0-9]{64}', self.runtime)
            or not re.fullmatch(r'INTRADAY-LAUNCHER-CONFIG-[a-f0-9]{64}', self.configuration)
            or not _hex(self.replacement_revision, 40) or self.replacement_revision == self.revision
            or not _hex(self.installed_launcher_sha256) or not _hex(self.control_digest)
            or self.listener != '127.0.0.1:8947' or not Path(self.repository).is_absolute()):
            raise BootstrapError('BOOTSTRAP_BINDING_INVALID')
        _aware(self.startup)


@dataclass(frozen=True)
class LegacySnapshot:
    binding: LegacyBinding
    listener_pids: tuple[int, ...]
    authentication_inflight: bool
    analysis_inflight: bool
    intraday_inflight: bool
    historical_inflight: bool
    provider_task_inflight: bool | None = None
    browser_control_inflight: bool | None = None
    monitoring_inflight: bool | None = None

    def check(self, expected):
        if self.binding != expected or self.listener_pids != (expected.pid,):
            raise BootstrapError('BOOTSTRAP_LEGACY_IDENTITY_MISMATCH')
        for key in ('authentication_inflight', 'analysis_inflight', 'intraday_inflight', 'historical_inflight'):
            if getattr(self, key) is not False:
                raise BootstrapError('BOOTSTRAP_KNOWN_WORK_INFLIGHT')
        for key in ('provider_task_inflight', 'browser_control_inflight', 'monitoring_inflight'):
            if getattr(self, key) is not None and getattr(self, key) is not False:
                raise BootstrapError('BOOTSTRAP_KNOWN_WORK_INFLIGHT')


@dataclass(frozen=True)
class Ticket:
    identity: str
    proof: str = field(repr=False)

    def __post_init__(self):
        if not _hex(self.identity) or not _hex(self.proof):
            raise BootstrapError('BOOTSTRAP_TICKET_INVALID')

    def environment(self):
        return {ENV_ID: self.identity, ENV_PROOF: self.proof}


def _write(root, ticket, phase, record):
    body = {'schema': SCHEMA, 'migration': ticket.identity, 'phase': phase, 'record': record}
    envelope = {'body': body, 'mac': hmac.new(bytes.fromhex(ticket.proof), _bytes(body), 'sha256').hexdigest()}
    # Every transition is exclusive, including concurrent dispatch/consumption.
    # A partial write is retained as a failed attempt; never overwrite/retry it.
    try:
        fd = os.open(root / (phase+'.json'), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as handle:
            handle.write(_bytes(envelope))
            handle.flush()
            os.fsync(handle.fileno())
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError:
        raise BootstrapError('BOOTSTRAP_TRANSITION_REJECTED') from None


def _load(root, ticket, phase):
    item = _read(root / (phase+'.json'))
    if set(item) != {'body', 'mac'} or not isinstance(item['mac'], str):
        raise BootstrapError('BOOTSTRAP_INTEGRITY_INVALID')
    body = item['body']
    if (set(body) != {'schema', 'migration', 'phase', 'record'} or body['schema'] != SCHEMA
        or body['migration'] != ticket.identity or body['phase'] != phase
        or not hmac.compare_digest(item['mac'], hmac.new(bytes.fromhex(ticket.proof), _bytes(body), 'sha256').hexdigest())):
        raise BootstrapError('BOOTSTRAP_INTEGRITY_INVALID')
    return body['record']


def validate(root: Path, ticket: Ticket, now: datetime):
    try:
        _root(root)
        if (root/'consumed.json').exists():
            raise BootstrapError('BOOTSTRAP_PERMANENTLY_CONSUMED')
        record = _load(root, ticket, 'prepared')
        if set(record) != {'binding', 'coordinator_pid', 'created_at', 'authorization_reference', 'quiescence', 'risk', 'notification_policy'}:
            raise BootstrapError('BOOTSTRAP_RECORD_INVALID')
        binding = LegacyBinding(**record['binding'])
        q = dict(record['quiescence'])
        q['listener_pids'] = tuple(q['listener_pids'])
        LegacySnapshot(binding=binding, **q).check(binding)
        if (type(record['coordinator_pid']) is not int or record['coordinator_pid'] < 2
            or record['coordinator_pid'] == binding.pid or record['risk'] != RISK
            or record['notification_policy'] != SIDE_EFFECT
            or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', record['authorization_reference'])
            or not 0 <= (now-_aware(record['created_at'])).total_seconds() <= HANDOFF_SECONDS):
            raise BootstrapError('BOOTSTRAP_STALE_OR_INVALID')
        return record, binding
    except BootstrapError:
        raise
    except (ValueError, TypeError, KeyError, OSError, AttributeError):
        raise BootstrapError('BOOTSTRAP_VALIDATION_REJECTED') from None


class LegacyBootstrapCoordinator:
    def __init__(self, root: Path, expected: LegacyBinding, *, clock=lambda: datetime.now(UTC)):
        self.root, self.expected, self.clock = Path(root), expected, clock

    def prepare(self, observed: LegacySnapshot, authorization_reference: str):
        observed.check(self.expected)
        if self.expected.pid == os.getpid() or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', authorization_reference):
            raise BootstrapError('BOOTSTRAP_AUTHORITY_INVALID')
        _root(self.root, create=True)
        # Permanent single reservation: failures require explicit engineering review,
        # never overwrite an expired/failed attempt or create an alternate generation.
        if any(self.root.iterdir()):
            raise BootstrapError('BOOTSTRAP_ALREADY_RESERVED')
        ticket = Ticket(secrets.token_hex(32), secrets.token_hex(32))
        q = asdict(observed); q.pop('binding'); q['listener_pids'] = list(q['listener_pids'])
        _write(self.root, ticket, 'prepared', {'binding': asdict(self.expected),
            'coordinator_pid': os.getpid(), 'created_at': self.clock().isoformat(),
            'authorization_reference': authorization_reference, 'quiescence': q,
            'risk': RISK, 'notification_policy': SIDE_EFFECT})
        validate(self.root, ticket, self.clock())
        return ticket

    def shutdown(self, ticket: Ticket, observe, shutdown):
        record, binding = validate(self.root, ticket, self.clock())
        if record['coordinator_pid'] != os.getpid() or binding != self.expected:
            raise BootstrapError('BOOTSTRAP_COORDINATOR_MISMATCH')
        observe().check(binding)  # Recheck immediately before permitting the old POST.
        # Status reads may consume the entire lifetime: validate again after them.
        validate(self.root, ticket, self.clock())
        if (self.root/'shutdown-authorized.json').exists():
            raise BootstrapError('BOOTSTRAP_SHUTDOWN_ALREADY_DISPATCHED')
        _write(self.root, ticket, 'shutdown-authorized', {'prepared_digest': sha256(_bytes(record)).hexdigest(),
            'at': self.clock().isoformat(), 'legacy_pid': binding.pid})
        validate(self.root, ticket, self.clock())
        return shutdown()  # May run only after valid durable prepared/authorized records.

    def stopped(self, ticket: Ticket, *, legacy_alive: bool, listener_free: bool):
        record, binding = validate(self.root, ticket, self.clock())
        if record['coordinator_pid'] != os.getpid() or legacy_alive or not listener_free:
            raise BootstrapError('BOOTSTRAP_LEGACY_NOT_STOPPED')
        _load(self.root, ticket, 'shutdown-authorized')
        _write(self.root, ticket, 'stopped', {'legacy_pid': binding.pid, 'at': self.clock().isoformat()})


def process_exists(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def listener_free():
    with socket.socket() as sock:
        sock.settimeout(1)
        return sock.connect_ex(('127.0.0.1', 8947)) != 0


def consume_bootstrap(root: Path, environment, *, revision, source_state, repository,
                      runtime_identity, now, process_id=None, old_alive=process_exists,
                      port_free=listener_free):
    identity, proof = environment.pop(ENV_ID, None), environment.pop(ENV_PROOF, None)
    if identity is None and proof is None:
        return None
    try:
        ticket = Ticket(identity, proof)
        record, binding = validate(root, ticket, now)
        pid = os.getpid() if process_id is None else process_id
        if (source_state != 'CLEAN_COMMIT' or revision != binding.replacement_revision
            or str(repository) != binding.repository or pid in (binding.pid, record['coordinator_pid'])
            or type(pid) is not int or pid < 2
            or not _hex(runtime_identity) or old_alive(binding.pid) or not port_free()):
            raise BootstrapError('BOOTSTRAP_REPLACEMENT_MISMATCH')
        authorized = _load(root, ticket, 'shutdown-authorized')
        stopped = _load(root, ticket, 'stopped')
        if (authorized != {'prepared_digest': sha256(_bytes(record)).hexdigest(),
                           'at': authorized.get('at'), 'legacy_pid': binding.pid}
            or stopped != {'legacy_pid': binding.pid, 'at': stopped.get('at')}
            or not _aware(record['created_at']) <= _aware(authorized['at']) <= _aware(stopped['at']) <= now):
            raise BootstrapError('BOOTSTRAP_ORDER_INVALID')
        # An exclusive immutable marker permanently disables this deployment's
        # legacy path before the replacement composes any application capability.
        _write(root, ticket, 'consumed', {'pid': pid, 'runtime': runtime_identity, 'at': now.isoformat(),
                                        'legacy_pid': binding.pid, 'decommissioned': True})
        return ticket.identity
    except BootstrapError:
        raise
    except (ValueError, TypeError, KeyError, OSError, AttributeError):
        raise BootstrapError('BOOTSTRAP_CONSUMPTION_REJECTED') from None


def _restoration_selection(environment, *, consume=False):
    present = tuple(name for name in RESTORATION_SELECTOR_ENV if name in environment)
    if not present:
        return None
    if len(present) != len(RESTORATION_SELECTOR_ENV):
        raise BootstrapError('BOOTSTRAP_RESTORATION_SELECTOR_INVALID')
    values = {name: environment[name] for name in RESTORATION_SELECTOR_ENV}
    if consume:
        for name in RESTORATION_SELECTOR_ENV:
            environment.pop(name, None)
    try:
        permit_bytes = int(values['KRONOS_RESTORATION_PERMIT_BYTES'])
        reservation_bytes = int(values['KRONOS_RESTORATION_RESERVATION_BYTES'])
        result = RestorationSelection(
            original_attempt_id=values['KRONOS_RESTORATION_ORIGINAL_ATTEMPT_ID'],
            permit_path=Path(values['KRONOS_RESTORATION_PERMIT_PATH']),
            permit_bytes=permit_bytes,
            permit_sha256=values['KRONOS_RESTORATION_PERMIT_SHA256'],
            permit_id=values['KRONOS_RESTORATION_PERMIT_ID'],
            reservation_path=Path(values['KRONOS_RESTORATION_RESERVATION_PATH']),
            reservation_bytes=reservation_bytes,
            reservation_sha256=values['KRONOS_RESTORATION_RESERVATION_SHA256'],
            reservation_id=values['KRONOS_RESTORATION_RESERVATION_ID'],
        )
    except (TypeError, ValueError):
        raise BootstrapError('BOOTSTRAP_RESTORATION_SELECTOR_INVALID') from None
    identity = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,199}')
    if (identity.fullmatch(result.original_attempt_id) is None
            or identity.fullmatch(result.permit_id) is None
            or identity.fullmatch(result.reservation_id) is None
            or not result.permit_path.is_absolute()
            or not result.reservation_path.is_absolute()
            or type(result.permit_bytes) is not int
            or type(result.reservation_bytes) is not int
            or not 1 <= result.permit_bytes <= 65536
            or not 1 <= result.reservation_bytes <= 65536
            or not _hex(result.permit_sha256)
            or not _hex(result.reservation_sha256)):
        raise BootstrapError('BOOTSTRAP_RESTORATION_SELECTOR_INVALID')
    return result


def _manifest_sha256(path_value, custody):
    """Hash one native-selected installed manifest under inherited custody."""
    try:
        path = Path(path_value)
        if (not path.is_absolute() or '..' in path.parts
                or any(parent.is_symlink() for parent in (path, *path.parents))):
            raise BootstrapError('BOOTSTRAP_RESTORATION_CHILD_IDENTITY_INVALID')
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            metadata = os.fstat(descriptor)
            if (not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_uid not in {0, os.getuid()}
                    or metadata.st_mode & 0o022
                    or not 1 <= metadata.st_size <= 8 * 1024 * 1024):
                raise BootstrapError('BOOTSTRAP_RESTORATION_CHILD_IDENTITY_INVALID')
            digest = sha256()
            remaining = metadata.st_size
            while remaining:
                custody.check()
                block = os.read(descriptor, min(remaining, 65536))
                if not block:
                    raise BootstrapError('BOOTSTRAP_RESTORATION_CHILD_IDENTITY_INVALID')
                digest.update(block)
                remaining -= len(block)
            if os.read(descriptor, 1):
                raise BootstrapError('BOOTSTRAP_RESTORATION_CHILD_IDENTITY_INVALID')
            final = os.fstat(descriptor)
            if ((final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns)
                    != (metadata.st_dev, metadata.st_ino, metadata.st_size,
                        metadata.st_mtime_ns)):
                raise BootstrapError('BOOTSTRAP_RESTORATION_CHILD_IDENTITY_INVALID')
            return digest.hexdigest()
        finally:
            os.close(descriptor)
    except BootstrapError:
        raise
    except (OSError, TypeError, ValueError):
        raise BootstrapError('BOOTSTRAP_RESTORATION_CHILD_IDENTITY_INVALID') from None


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode('utf-8')


def _closed_json(raw, *, final_lf, canonical=True):
    """Decode one exact canonical document while rejecting duplicate keys."""
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError('DUPLICATE_KEY')
            result[key] = value
        return result
    try:
        if raw.startswith(b'\xef\xbb\xbf'):
            raise ValueError('BOM')
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                           parse_constant=lambda _value: (_ for _ in ()).throw(
                               ValueError('NONFINITE')))
        if canonical and raw != _canonical(value) + (b'\n' if final_lf else b''):
            raise ValueError('NONCANONICAL')
        return value
    except (UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        raise BootstrapError('BOOTSTRAP_RESTORATION_DOCUMENT_INVALID') from None


def _read_manifest(path_value, custody, *, final_lf, canonical=True):
    path = Path(path_value)
    try:
        if (not path.is_absolute() or '..' in path.parts
                or any(parent.is_symlink() for parent in (path, *path.parents))):
            raise BootstrapError('BOOTSTRAP_RESTORATION_DOCUMENT_INVALID')
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            before = os.fstat(descriptor)
            if (not stat.S_ISREG(before.st_mode)
                    or before.st_uid not in {0, os.getuid()}
                    or before.st_mode & 0o022
                    or not 1 <= before.st_size <= 8 * 1024 * 1024):
                raise BootstrapError('BOOTSTRAP_RESTORATION_DOCUMENT_INVALID')
            raw = bytearray()
            while len(raw) < before.st_size:
                custody.check()
                block = os.read(descriptor, min(65536, before.st_size - len(raw)))
                if not block:
                    raise BootstrapError('BOOTSTRAP_RESTORATION_DOCUMENT_INVALID')
                raw.extend(block)
            if os.read(descriptor, 1):
                raise BootstrapError('BOOTSTRAP_RESTORATION_DOCUMENT_INVALID')
            after = os.fstat(descriptor)
            named = path.stat(follow_symlinks=False)
            fields = lambda value: (value.st_dev, value.st_ino, value.st_mode,
                                    value.st_uid, value.st_size, value.st_mtime_ns,
                                    value.st_ctime_ns)
            if fields(before) != fields(after) or fields(after) != fields(named):
                raise BootstrapError('BOOTSTRAP_RESTORATION_DOCUMENT_INVALID')
            payload = bytes(raw)
            return path, payload, _closed_json(payload, final_lf=final_lf,canonical=canonical)
        finally:
            os.close(descriptor)
    except BootstrapError:
        raise
    except (OSError, TypeError, ValueError):
        raise BootstrapError('BOOTSTRAP_RESTORATION_DOCUMENT_INVALID') from None


def _validation_output(arguments, repository, custody, phase, *, capacity=262144):
    from kronos.common.release_admission import validation_output
    return validation_output(arguments, cwd=repository, budget=custody.budget,
                             ceiling=10, phase=phase, capacity=capacity)


def _repository_file(repository, relative):
    if (not isinstance(relative, str) or not relative or relative.startswith('/')
            or '\\' in relative or '\x00' in relative):
        raise BootstrapError('BOOTSTRAP_RESTORATION_SOURCE_INVALID')
    parts = relative.split('/')
    if any(part in {'', '.', '..'} for part in parts):
        raise BootstrapError('BOOTSTRAP_RESTORATION_SOURCE_INVALID')
    path = repository.joinpath(*parts)
    if (not path.resolve().is_relative_to(repository)
            or any(parent.is_symlink() for parent in (path, *path.parents)
                   if parent == repository or repository in parent.parents)):
        raise BootstrapError('BOOTSTRAP_RESTORATION_SOURCE_INVALID')
    return path


def _tracked_files(repository, revision, custody):
    rows = []
    seen = set()
    folded = set()
    try:
        # Ask Git for the storage format rather than guessing from a supplied
        # revision or silently defaulting to SHA-1. One exact known answer only.
        object_format = _validation_output(
            ['/usr/bin/git', 'rev-parse', '--show-object-format=storage'],
            repository, custody, 'RESTORATION_SOURCE_OBJECT_FORMAT')
        if object_format == b'sha1\n':
            object_hash, oid_size = sha1, 40
        elif object_format == b'sha256\n':
            object_hash, oid_size = sha256, 64
        else:
            raise ValueError('UNSUPPORTED_OR_AMBIGUOUS_OBJECT_FORMAT')
        if not _hex(revision, oid_size):
            raise ValueError('REVISION_OBJECT_FORMAT_MISMATCH')
        raw = _validation_output(
            ['/usr/bin/git', 'ls-tree', '-r', '-z', '--full-tree', revision],
            repository, custody, 'RESTORATION_SOURCE_TREE',
            capacity=8 * 1024 * 1024)
        for item in raw.split(b'\0'):
            if not item:
                continue
            header, encoded = item.split(b'\t', 1)
            mode, kind, oid = header.decode('ascii').split(' ')
            relative = encoded.decode('utf-8')
            if (mode not in {'100644', '100755'} or kind != 'blob'
                    or not _hex(oid, oid_size)
                    or relative in seen or relative.casefold() in folded):
                raise ValueError('UNSUPPORTED_TREE')
            seen.add(relative); folded.add(relative.casefold())
            path = _repository_file(repository, relative)
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                metadata = os.fstat(descriptor)
                expected_mode = 0o644 if mode == '100644' else 0o755
                if (not stat.S_ISREG(metadata.st_mode)
                        or stat.S_IMODE(metadata.st_mode) != expected_mode):
                    raise ValueError('MODE')
                digest = sha256()
                # Both identities consume the same bytes from this no-follow
                # regular-file descriptor. Git includes its blob size header.
                blob_digest = object_hash(
                    b'blob ' + str(metadata.st_size).encode('ascii') + b'\0')
                observed_bytes = 0
                while True:
                    custody.check()
                    block = os.read(descriptor, 65536)
                    if not block:
                        break
                    digest.update(block)
                    blob_digest.update(block)
                    observed_bytes += len(block)
                final = os.fstat(descriptor)
                if (observed_bytes != metadata.st_size
                        or (metadata.st_dev, metadata.st_ino, metadata.st_mode,
                            metadata.st_size, metadata.st_mtime_ns,
                            metadata.st_ctime_ns)
                        != (final.st_dev, final.st_ino, final.st_mode,
                            final.st_size, final.st_mtime_ns, final.st_ctime_ns)):
                    raise ValueError('CHANGED')
                if blob_digest.hexdigest() != oid:
                    raise ValueError('SELECTED_GIT_BLOB_MISMATCH')
                rows.append({'path': relative, 'mode': mode,
                             'sha256': digest.hexdigest()})
            finally:
                os.close(descriptor)
        return sorted(rows, key=lambda row: row['path'])
    except (OSError, UnicodeError, ValueError, subprocess.SubprocessError):
        raise BootstrapError('BOOTSTRAP_RESTORATION_SOURCE_INVALID') from None


def _validate_source_manifest(path_value, repository, custody, *, revision,
                              pinned_capture_sha256, captured_sources,
                              loaded_modules, load_verification):
    path, raw, value = _read_manifest(path_value, custody, final_lf=False)
    fields = {'schema', 'origin_url', 'source_ref', 'revision', 'git_tree_oid',
              'files', 'capture'}
    if (type(value) is not dict or set(value) != fields
            or value['schema'] != 'KRONOS_RESTORATION_SOURCE_MANIFEST_V1'
            or value['revision'] != revision
            or not isinstance(value['origin_url'], str) or not value['origin_url']
            or not isinstance(value['source_ref'], str)
            or not value['source_ref'].startswith('refs/heads/')
            or re.fullmatch(r'[a-f0-9]{40}|[a-f0-9]{64}', value['git_tree_oid']) is None
            or type(value['files']) is not list or type(value['capture']) is not list
            or load_verification != 'PINNED_STARTUP_IMPORTS'
            or not _hex(pinned_capture_sha256)):
        raise BootstrapError('BOOTSTRAP_RESTORATION_SOURCE_INVALID')
    if path == repository or repository in path.parents:
        relative_manifest = path.relative_to(repository).as_posix()
    else:
        relative_manifest = None
    actual_files = _tracked_files(repository, revision, custody)
    if value['files'] != actual_files or (relative_manifest is not None
                                          and relative_manifest in {
                                              row['path'] for row in actual_files}):
        raise BootstrapError('BOOTSTRAP_RESTORATION_SOURCE_INVALID')
    tree_oid = _validation_output(['/usr/bin/git', 'rev-parse',
                                   revision + '^{tree}'], repository, custody,
                                  'RESTORATION_SOURCE_TREE_ID').decode().strip()
    ref_revision = _validation_output(['/usr/bin/git', 'show-ref', '--verify',
                                       '--hash', value['source_ref']], repository,
                                      custody, 'RESTORATION_SOURCE_REF').decode().strip()
    origin = _validation_output(['/usr/bin/git', 'remote', 'get-url', 'origin'],
                                repository, custody,
                                'RESTORATION_SOURCE_ORIGIN').decode().strip()
    if (tree_oid != value['git_tree_oid'] or ref_revision != revision
            or origin != value['origin_url']):
        raise BootstrapError('BOOTSTRAP_RESTORATION_SOURCE_INVALID')
    if value['files'] != sorted(value['files'], key=lambda row: row.get('path', '')):
        raise BootstrapError('BOOTSTRAP_RESTORATION_SOURCE_INVALID')
    file_rows = {row['path']: row for row in value['files'] if type(row) is dict}
    if (len(file_rows) != len(value['files'])
            or any(set(row) != {'path', 'mode', 'sha256'}
                   or row['mode'] not in {'100644', '100755'}
                   or not _hex(row['sha256']) for row in value['files'])):
        raise BootstrapError('BOOTSTRAP_RESTORATION_SOURCE_INVALID')
    try:
        captured = [dict(module=name, path=relative, sha256=digest)
                    for name, relative, digest in captured_sources]
        captured.sort(key=lambda row: row['module'])
    except (TypeError, ValueError):
        raise BootstrapError('BOOTSTRAP_RESTORATION_SOURCE_INVALID') from None
    if (value['capture'] != captured
            or any(type(row) is not dict
                   or set(row) != {'module', 'path', 'sha256'}
                   or re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*',
                                   row['module']) is None
                   or not _hex(row['sha256'])
                   or file_rows.get(row['path'], {}).get('sha256') != row['sha256']
                   for row in captured)
            or len({row['module'] for row in captured}) != len(captured)
            or len({row['path'].casefold() for row in captured}) != len(captured)):
        raise BootstrapError('BOOTSTRAP_RESTORATION_SOURCE_INVALID')
    pairs = [[row['module'], row['sha256']] for row in captured]
    if sha256(_canonical(pairs)).hexdigest() != pinned_capture_sha256:
        raise BootstrapError('BOOTSTRAP_RESTORATION_SOURCE_INVALID')
    capture_map = {row['module']: row['sha256'] for row in captured}
    try:
        if any(capture_map.get(name) != digest for name, digest in loaded_modules):
            raise BootstrapError('BOOTSTRAP_RESTORATION_SOURCE_INVALID')
    except (TypeError, ValueError):
        raise BootstrapError('BOOTSTRAP_RESTORATION_SOURCE_INVALID') from None
    return value, sha256(raw).hexdigest(), sha256(_canonical(actual_files)).hexdigest()


def _bundle_manifest(bundle, custody):
    if (not bundle.is_absolute() or '..' in bundle.parts
            or any(parent.is_symlink() for parent in (bundle, *bundle.parents))):
        raise BootstrapError('BOOTSTRAP_RESTORATION_ARTIFACT_INVALID')
    metadata = bundle.stat()
    if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o755):
        raise BootstrapError('BOOTSTRAP_RESTORATION_ARTIFACT_INVALID')
    rows = []
    for path in sorted(bundle.rglob('*')):
        if path.is_symlink():
            raise BootstrapError('BOOTSTRAP_RESTORATION_ARTIFACT_INVALID')
        item = path.lstat()
        if item.st_uid != os.getuid() or not (stat.S_ISREG(item.st_mode)
                                              or stat.S_ISDIR(item.st_mode)):
            raise BootstrapError('BOOTSTRAP_RESTORATION_ARTIFACT_INVALID')
        relative = path.relative_to(bundle).as_posix()
        expected = 0o755 if path.is_dir() or relative == 'Contents/MacOS/KRONOS' else 0o644
        if stat.S_IMODE(item.st_mode) != expected:
            raise BootstrapError('BOOTSTRAP_RESTORATION_ARTIFACT_INVALID')
        digest = None
        if path.is_file():
            custody.check()
            digest = sha256(path.read_bytes()).hexdigest()
        rows.append({'path': relative, 'mode': expected, 'sha256': digest})
    return rows


def _verify_bundle_signature(bundle, custody, _identity):
    _validation_output(['/usr/bin/codesign', '--verify', '--strict', '--verbose=2',
                        str(bundle)], bundle.parent, custody,
                       'RESTORATION_BUNDLE_SIGNATURE')


def _restoration_parent_bundle(bundle_path, custody):
    """Bind the selected package to the adopted parent's canonical image.

    The custody observer is the existing kernel proc_pidpath mechanism in
    production. Permit/environment strings never supply an observed image.
    Compare exact paths before resolving, so aliases cannot grant admission.
    """
    from kronos.common.release_admission import CANONICAL_PARENT
    try:
        observed = custody.parent_image(custody.parent)
        bundle = Path(bundle_path)
        executable = bundle / 'Contents/MacOS/KRONOS'
        if (type(observed) is not str or observed != CANONICAL_PARENT
                or str(bundle) != bundle_path or not bundle.is_absolute()
                or '..' in bundle.parts or str(executable) != observed
                or any(path.is_symlink() for path in (executable, *executable.parents))
                or str(executable.resolve(strict=True)) != observed
                or not stat.S_ISREG(executable.stat(follow_symlinks=False).st_mode)):
            raise BootstrapError('BOOTSTRAP_RESTORATION_PARENT_BUNDLE_MISMATCH')
        custody.check()
        return bundle
    except BootstrapError:
        raise
    except (AttributeError, OSError, TypeError, ValueError):
        raise BootstrapError('BOOTSTRAP_RESTORATION_PARENT_BUNDLE_MISMATCH') from None


def _validate_artifact_manifest(path_value, bundle, source, files, custody):
    _path, raw, value = _read_manifest(path_value, custody, final_lf=True)
    fields = {'schema', 'source_revision', 'source_state', 'source_launcher_sha256',
              'previous_tracked_binary_sha256', 'built_binary_sha256',
              'signed_binary_sha256', 'procedure_sha256', 'compiler_flags',
              'compiler', 'signing', 'strict_verification', 'isolated_execution',
              'bundle_identity', 'bundle_manifest', 'archive_sha256'}
    hex_fields = {'source_launcher_sha256', 'previous_tracked_binary_sha256',
                  'built_binary_sha256', 'signed_binary_sha256',
                  'procedure_sha256', 'bundle_identity', 'archive_sha256'}
    if (type(value) is not dict or set(value) != fields
            or value['schema'] != 'KRONOS_LAUNCHER_PACKAGE_V1'
            or value['source_state'] != 'CLEAN_COMMIT'
            or value['source_revision'] != source['revision']
            or any(not _hex(value[name]) for name in hex_fields)
            or value['compiler_flags'] != ['-Wall', '-Wextra', '-Werror', '-O2',
                                            '-mmacosx-version-min=13.0']
            or not isinstance(value['compiler'], str) or not value['compiler']
            or value['signing'] != 'AD_HOC; timestamp=none; no entitlements; resources sealed'
            or value['strict_verification'] != 'PASS'
            or value['isolated_execution'] != 'PASS'
            or type(value['bundle_manifest']) is not list):
        raise BootstrapError('BOOTSTRAP_RESTORATION_ARTIFACT_INVALID')
    file_map = {row['path']: row['sha256'] for row in files}
    if (value['source_launcher_sha256'] != file_map.get('tools/macos/kronos_launcher.c')
            or value['procedure_sha256'] != file_map.get('tools/macos/package_launcher.py')
            or value['previous_tracked_binary_sha256']
                != file_map.get('tools/macos/KRONOS.app/Contents/MacOS/KRONOS')):
        raise BootstrapError('BOOTSTRAP_RESTORATION_ARTIFACT_INVALID')
    actual = _bundle_manifest(bundle, custody)
    binary = bundle / 'Contents/MacOS/KRONOS'
    expected_files = {'Contents/Info.plist', 'Contents/Resources/KRONOS.icns',
                      'Contents/Resources/KRONOS.png', 'Contents/MacOS/KRONOS',
                      'Contents/_CodeSignature/CodeResources'}
    if (value['bundle_manifest'] != actual
            or {row['path'] for row in actual if row['sha256'] is not None} != expected_files
            or value['bundle_identity'] != sha256(_canonical(actual)).hexdigest()
            or value['signed_binary_sha256'] != sha256(binary.read_bytes()).hexdigest()):
        raise BootstrapError('BOOTSTRAP_RESTORATION_ARTIFACT_INVALID')
    # package_launcher.build copies these exact source bytes. Bind the already
    # verified Git inventory to the actual hashes just matched to the package.
    installed_hashes = {row['path']: row['sha256'] for row in actual}
    for relative in ('Contents/Info.plist', 'Contents/Resources/KRONOS.icns',
                     'Contents/Resources/KRONOS.png'):
        source_hash = file_map.get('tools/macos/KRONOS.app/' + relative)
        if source_hash is None or source_hash != installed_hashes[relative]:
            raise BootstrapError('BOOTSTRAP_RESTORATION_ARTIFACT_INVALID')
    try:
        info = plistlib.loads((bundle / 'Contents/Info.plist').read_bytes())
    except (OSError, ValueError):
        raise BootstrapError('BOOTSTRAP_RESTORATION_ARTIFACT_INVALID') from None
    if (info.get('CFBundleIdentifier') != 'com.project-kronos.browser-v1'
            or info.get('CFBundleExecutable') != 'KRONOS'
            or info.get('CFBundlePackageType') != 'APPL'
            or info.get('CFBundleIconFile') != 'KRONOS'
            or info.get('LSMinimumSystemVersion') != '13.0'):
        raise BootstrapError('BOOTSTRAP_RESTORATION_ARTIFACT_INVALID')
    custody.check()
    _verify_bundle_signature(bundle, custody, value['bundle_identity'])
    custody.check()
    return sha256(raw).hexdigest()


def _kernel_birth_digest(seconds, microseconds):
    if (type(seconds) is not int or seconds <= 0 or type(microseconds) is not int
            or not 0 <= microseconds <= 999999):
        raise BootstrapError('BOOTSTRAP_RESTORATION_PROCESS_IDENTITY_INVALID')
    start_us = seconds * 1000000 + microseconds
    return sha256(str(start_us).encode('ascii')).hexdigest()


def _observe_process(pid):
    class BsdInfo(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint32) for name in (
            'flags', 'status', 'xstatus', 'pid', 'ppid', 'uid', 'gid',
            'ruid', 'rgid', 'svuid', 'svgid', 'reserved')]
        _fields_ += [('comm', ctypes.c_char * 16), ('name', ctypes.c_char * 32)]
        _fields_ += [(name, ctypes.c_uint32) for name in (
            'nfiles', 'pgid', 'pjobc', 'tdev', 'tpgid')]
        _fields_ += [('nice', ctypes.c_int32), ('seconds', ctypes.c_uint64),
                     ('microseconds', ctypes.c_uint64)]
    try:
        info = BsdInfo()
        if ctypes.sizeof(info) != 136:
            raise ValueError('STRUCTURE')
        query = ctypes.CDLL('/usr/lib/libproc.dylib', use_errno=True).proc_pidinfo
        query.argtypes = (ctypes.c_int, ctypes.c_int, ctypes.c_uint64,
                          ctypes.c_void_p, ctypes.c_int)
        query.restype = ctypes.c_int
        if query(pid, 3, 0, ctypes.byref(info), ctypes.sizeof(info)) != ctypes.sizeof(info):
            raise ValueError('INCOMPLETE')
        if info.pid != pid:
            raise ValueError('PID')
        return {'pid': info.pid, 'parent_pid': info.ppid,
                'kernel_birth': _kernel_birth_digest(info.seconds, info.microseconds)}
    except (OSError, TypeError, ValueError):
        raise BootstrapError('BOOTSTRAP_RESTORATION_PROCESS_IDENTITY_INVALID') from None


def capture_restoration_child(environment, *, custody, process_id, parent_pid,
                              runtime_identity, loaded_revision,
                              pinned_capture_sha256, repository,
                              captured_sources, loaded_modules,
                              load_verification):
    """Construct observed child facts; permit bytes never supply these values.

    Kernel-birth facts and installed-manifest locators are produced by the future
    native reservation path.  PID/PPID, runtime/revision, manifest bytes and the
    pinned capture are independently observed here under the adopted custody.
    """
    from kronos.common.failed_successor_restore import (
        RestorationChildIdentity, SelectedPermit, _document, _installation,
        _target,
    )
    mode = environment.get('KRONOS_LAUNCH_MODE')
    if mode != RESTORATION_MODE:
        mode = environment.pop('KRONOS_LAUNCH_MODE', None)
    present = tuple(name for name in RESTORATION_CHILD_ENV if name in environment)
    if mode != RESTORATION_MODE:
        if present:
            raise BootstrapError('BOOTSTRAP_MIXED_PROTOCOLS')
        return None
    if len(present) != len(RESTORATION_CHILD_ENV):
        raise BootstrapError('BOOTSTRAP_RESTORATION_CHILD_IDENTITY_INVALID')
    try:
        custody.check()
        if (process_id != os.getpid() or parent_pid != os.getppid()
                or parent_pid != custody.parent):
            raise BootstrapError('BOOTSTRAP_RESTORATION_PROCESS_IDENTITY_INVALID')
        observed_child = _observe_process(process_id)
        observed_parent = _observe_process(parent_pid)
        if (observed_child['parent_pid'] != parent_pid
                or observed_child['kernel_birth']
                    != environment[RESTORATION_CHILD_ENV[1]]
                or observed_parent['kernel_birth']
                    != environment[RESTORATION_CHILD_ENV[0]]):
            raise BootstrapError('BOOTSTRAP_RESTORATION_PROCESS_IDENTITY_INVALID')
        selection = _restoration_selection(environment)
        if selection is None:
            raise BootstrapError('BOOTSTRAP_RESTORATION_SELECTOR_INVALID')
        permit_selection = SelectedPermit(selection.permit_path,
            selection.permit_bytes, selection.permit_sha256, selection.permit_id)
        permit_document, _ = _document(permit_selection.path,
            permit_selection.byte_size, permit_selection.sha256)
        installation = _installation(permit_document['installation'])
        target = _target(permit_document['restoration_target'])
        bundle = _restoration_parent_bundle(installation['bundle_path'], custody)
        actual_repository = Path(repository)
        if (not actual_repository.is_absolute() or '..' in actual_repository.parts
                or any(path.is_symlink() for path in
                       (actual_repository, *actual_repository.parents))
                or str(actual_repository.resolve()) != installation['repository_path']):
            raise BootstrapError('BOOTSTRAP_RESTORATION_REPOSITORY_MISMATCH')
        source, source_digest, tree_digest = _validate_source_manifest(
            environment[RESTORATION_CHILD_ENV[2]], actual_repository, custody,
            revision=loaded_revision,
            pinned_capture_sha256=pinned_capture_sha256,
            captured_sources=captured_sources, loaded_modules=loaded_modules,
            load_verification=load_verification)
        artifact_digest = _validate_artifact_manifest(
            environment[RESTORATION_CHILD_ENV[3]],
            bundle, source, source['files'], custody)
        if (target['revision'] != loaded_revision
                or target['origin_url'] != source['origin_url']
                or target['source_ref'] != source['source_ref']
                or target['tree_sha256'] != tree_digest
                or target['source_manifest_sha256'] != source_digest
                or target['artifact_manifest_sha256'] != artifact_digest
                or target['pinned_capture_sha256'] != pinned_capture_sha256):
            raise BootstrapError('BOOTSTRAP_RESTORATION_SOURCE_INVALID')
        child = RestorationChildIdentity(
            process_id=process_id,
            parent_pid=parent_pid,
            parent_kernel_birth=observed_parent['kernel_birth'],
            kernel_birth=observed_child['kernel_birth'],
            runtime_identity=runtime_identity,
            loaded_revision=loaded_revision,
            source_manifest_sha256=source_digest,
            artifact_manifest_sha256=artifact_digest,
            pinned_capture_sha256=pinned_capture_sha256,
        )
        custody.check()
        return RestorationObservation(child=child,
            repository=str(actual_repository.resolve()),
            installation_identity=installation['identity'],
            permit_sha256=selection.permit_sha256,
            source_manifest_path=str(Path(environment[RESTORATION_CHILD_ENV[2]])),
            artifact_manifest_path=str(Path(environment[RESTORATION_CHILD_ENV[3]])),
            captured_sources=tuple(tuple(row) for row in captured_sources),
            loaded_modules=tuple(tuple(row) for row in loaded_modules),
            load_verification=load_verification)
    except BootstrapError:
        raise
    except (AttributeError, KeyError, OSError, TypeError, ValueError):
        raise BootstrapError('BOOTSTRAP_RESTORATION_CHILD_IDENTITY_INVALID') from None


def retain_restoration_attempt(environment, *, context, custody, observation,
                               head_sha256, claimed_at, consumer_final_at, clock):
    """Retain the claim time and the consumer's latest accepted UTC separately.

    Called immediately after successful consumption. Every operation here is a
    read; the original claim/head are never repaired or replaced on failure.
    """
    from kronos.common import failed_successor_restore as restore
    try:
        selection = _restoration_selection(environment)
        reservation, _ = restore._document(selection.reservation_path,
            selection.reservation_bytes, selection.reservation_sha256)
        head_path, claim_path = Path(reservation['head_path']), Path(reservation['claim_path'])
        _, head_raw = restore._current_document(head_path)
        claim, claim_raw = restore._current_document(claim_path)
        if (sha256(head_raw).hexdigest() != head_sha256
                or claim.get('claimed_at') != claimed_at.isoformat()):
            raise BootstrapError('BOOTSTRAP_RESTORATION_RECHECK_REJECTED')
        attempt = RestorationAttempt(context, observation, selection,
            _restoration_environment(environment), custody, custody.budget,
            custody.budget.deadline_ns,
            (head_path, len(head_raw), sha256(head_raw).hexdigest()),
            (claim_path, len(claim_raw), sha256(claim_raw).hexdigest()),
            claim['claimed_at'], consumer_final_at)
        return revalidate_restoration_context(environment, context=context,
            custody=custody, child=observation.child, repository=observation.repository,
            now=consumer_final_at, attempt=attempt, clock=clock)
    except BootstrapError:
        raise
    except (AttributeError, KeyError, OSError, TypeError, ValueError, OverflowError):
        raise BootstrapError('BOOTSTRAP_RESTORATION_RECHECK_REJECTED') from None


def revalidate_restoration_context(environment, *, context, custody, child,
                                   repository, now, attempt=None, clock=None):
    """Recheck the selected immutable attempt without creating another claim."""
    from kronos.common import failed_successor_restore as restore
    from kronos.common.release_admission import ValidationBudget
    try:
        clock = clock or (lambda: datetime.now(UTC))
        initial_now = clock()
        if (type(attempt) is not RestorationAttempt
                or attempt.context is not context or attempt.custody is not custody
                or type(attempt.budget) is not ValidationBudget
                or custody.budget is not attempt.budget
                or attempt.budget.deadline_ns != attempt.deadline_ns
                or _restoration_environment(environment) != attempt.environment
                or child != attempt.observation.child
                or not isinstance(initial_now, datetime) or initial_now.tzinfo is None
                or initial_now.utcoffset() != UTC.utcoffset(initial_now)
                or initial_now < attempt.validated_at or initial_now < now):
            raise BootstrapError('BOOTSTRAP_RESTORATION_RECHECK_REJECTED')
        selection = _restoration_selection(environment)
        if (environment.get('KRONOS_LAUNCH_MODE') != RESTORATION_MODE
                or selection is None
                or selection != attempt.selection
                or type(context) is not restore.RestorationStartupContext
                or type(child) is not restore.RestorationChildIdentity
                or type(custody) is not restore.AdmissionCustody
                or context.original_attempt_id != selection.original_attempt_id
                or context.permit_id != selection.permit_id
                or context.permit_sha256 != selection.permit_sha256
                or context.reservation_id != selection.reservation_id
                or context.reservation_sha256 != selection.reservation_sha256
                or context.process_id != child.process_id
                or context.runtime_identity != child.runtime_identity
                or context.loaded_revision != child.loaded_revision):
            raise BootstrapError('BOOTSTRAP_RESTORATION_RECHECK_REJECTED')
        custody.check()
        original = attempt.observation
        fresh = capture_restoration_child(environment, custody=custody,
            process_id=os.getpid(), parent_pid=os.getppid(),
            runtime_identity=child.runtime_identity, loaded_revision=child.loaded_revision,
            pinned_capture_sha256=child.pinned_capture_sha256, repository=repository,
            captured_sources=original.captured_sources,
            loaded_modules=original.loaded_modules,
            load_verification=original.load_verification)
        if fresh != original:
            raise BootstrapError('BOOTSTRAP_RESTORATION_RECHECK_REJECTED')
        permit_document, _ = restore._document(
            selection.permit_path, selection.permit_bytes, selection.permit_sha256)
        permit = restore._permit(permit_document,
            restore.SelectedPermit(selection.permit_path, selection.permit_bytes,
                selection.permit_sha256, selection.permit_id), initial_now)
        incident_document, _, incident_reference = restore._load_reference(permit['incident'])
        incident = restore._incident(incident_document, incident_reference,
                                     permit['installation'])
        settled_document, _, settled_reference = restore._load_reference(permit['settled_state'])
        settled = restore._settled(settled_document, settled_reference, incident)
        failure_document, _, failure_reference = restore._load_reference(
            permit['failure_cleanup'])
        restore._failure(failure_document, failure_reference, incident,
                         settled_reference)
        reservation_selection = restore.SelectedReservation(
            selection.reservation_path, selection.reservation_bytes,
            selection.reservation_sha256, selection.reservation_id)
        reservation_document, _ = restore._document(
            selection.reservation_path, selection.reservation_bytes,
            selection.reservation_sha256)
        reservation = restore._reservation(
            reservation_document, reservation_selection, permit,
            restore.SelectedPermit(selection.permit_path, selection.permit_bytes,
                selection.permit_sha256, selection.permit_id), incident,
            settled_reference)
        target = permit['restoration_target']
        if (permit['installation']['repository_path'] != str(Path(repository).resolve())
                or child.loaded_revision != target['revision']
                or child.source_manifest_sha256 != target['source_manifest_sha256']
                or child.artifact_manifest_sha256 != target['artifact_manifest_sha256']
                or child.pinned_capture_sha256 != target['pinned_capture_sha256']
                or context.settled_state_manifest_identity
                    != settled['state_manifest_identity']
                or context.settled_state_manifest_sha256
                    != settled['state_manifest_sha256']
                or context.notification_checkpoint()
                    != settled['notification_checkpoint']):
            raise BootstrapError('BOOTSTRAP_RESTORATION_RECHECK_REJECTED')
        # Recheck certified inputs only. Live application stores may legitimately
        # reconcile/enqueue during composition and must never be rolled back.
        for path, size, digest in (
                (selection.permit_path, selection.permit_bytes, selection.permit_sha256),
                (selection.reservation_path, selection.reservation_bytes, selection.reservation_sha256),
                *((Path(ref['path']), ref['bytes'], ref['sha256'])
                  for ref in (incident_reference, failure_reference, settled_reference))):
            restore._read_raw(path, size, digest)
        for path, expected, final_lf in (
                (original.source_manifest_path, child.source_manifest_sha256, False),
                (original.artifact_manifest_path, child.artifact_manifest_sha256, True)):
            _, raw, _ = _read_manifest(path, custody, final_lf=final_lf)
            if sha256(raw).hexdigest() != expected:
                raise BootstrapError('BOOTSTRAP_RESTORATION_RECHECK_REJECTED')
        head, head_raw = restore._head(Path(reservation['head_path']), reservation,
                                reservation_selection, permit['installation'], checks=custody)
        claim, claim_raw = restore._current_document(Path(reservation['claim_path']))
        if ((Path(reservation['head_path']), len(head_raw), sha256(head_raw).hexdigest())
                != attempt.head_reference
                or (Path(reservation['claim_path']), len(claim_raw), sha256(claim_raw).hexdigest())
                != attempt.claim_reference):
            raise BootstrapError('BOOTSTRAP_RESTORATION_RECHECK_REJECTED')
        expected_claim = {
            'schema': restore.CLAIM_SCHEMA,
            'incident_id': context.incident_id,
            'original_attempt_id': context.original_attempt_id,
            'permit_id': context.permit_id,
            'permit_sha256': context.permit_sha256,
            'reservation_id': context.reservation_id,
            'reservation_sha256': context.reservation_sha256,
            'attempt_nonce': reservation['attempt_nonce'],
            'installation_identity': permit['installation']['identity'],
            'parent': reservation['parent'],
            'child': {'pid': child.process_id, 'kernel_birth': child.kernel_birth,
                      'runtime_identity': child.runtime_identity,
                      'revision': child.loaded_revision},
            'source_manifest_sha256': child.source_manifest_sha256,
            'artifact_manifest_sha256': child.artifact_manifest_sha256,
            'pinned_capture_sha256': child.pinned_capture_sha256,
            'settled_state_id': settled['settled_state_id'],
            'settled_state_sha256': settled_reference['sha256'],
            'maintenance_identity': context.maintenance_identity,
            'claimed_at': attempt.claimed_at,
        }
        if (claim != expected_claim
                or head['active_reservation_id'] != context.reservation_id
                or head['active_reservation_sha256'] != context.reservation_sha256):
            raise BootstrapError('BOOTSTRAP_RESTORATION_RECHECK_REJECTED')
        restore._aware_utc(claim['claimed_at'])
        custody.check()
        final_now = clock()
        if (not isinstance(final_now, datetime) or final_now.tzinfo is None
                or final_now.utcoffset() != UTC.utcoffset(final_now)
                or final_now < initial_now or final_now < attempt.validated_at
                or not restore._aware_utc(permit['valid_from']) <= final_now
                       <= restore._aware_utc(reservation['valid_until'])
                or custody.budget is not attempt.budget
                or attempt.budget.deadline_ns != attempt.deadline_ns
                or _restoration_environment(environment) != attempt.environment):
            raise BootstrapError('BOOTSTRAP_RESTORATION_RECHECK_REJECTED')
        result = replace(attempt, validated_at=final_now)
        # No I/O, parent validation or renewed budget follows this decision.
        attempt.budget.check()
        return result
    except BootstrapError:
        raise
    except (AttributeError, KeyError, OSError, TypeError, ValueError,
            OverflowError):
        raise BootstrapError('BOOTSTRAP_RESTORATION_RECHECK_REJECTED') from None


def consume_startup_context(root: Path, environment, *, revision, source_state,
                            repository, runtime_identity, now, **bootstrap_checks):
    """Only one authority protocol can enter composition; never fall back."""
    from kronos.common.maintenance import consume_drain_handoff, consume_handoff, _ENV
    legacy = any(k in environment for k in (ENV_ID, ENV_PROOF))
    # Keep the restoration selector available through the final pre-activation
    # revalidation.  Ordinary protocols retain their historical consume-once
    # environment semantics.
    mode = environment.get('KRONOS_LAUNCH_MODE')
    handoff_protocol = environment.pop('KRONOS_MAINTENANCE_PROTOCOL', None)
    predecessor_revision = environment.pop('KRONOS_MAINTENANCE_REVISION', None)
    restoration_selector_present = any(
        name in environment for name in RESTORATION_SELECTOR_ENV)
    restoration_child_present = any(name in environment for name in RESTORATION_CHILD_ENV)
    restoration = mode == RESTORATION_MODE
    if (mode not in (None, 'LEGACY_BOOTSTRAP', RESTORATION_MODE)
            or (mode == 'LEGACY_BOOTSTRAP' and not legacy)
            or ((restoration_selector_present or restoration_child_present)
                and not restoration)):
        raise BootstrapError('BOOTSTRAP_MODE_CONTEXT_MISSING')
    if restoration:
        selection = _restoration_selection(environment)
        child_values = {name: environment.get(name)
                        for name in RESTORATION_CHILD_ENV}
        if (selection is None or any(value is None for value in child_values.values())
                or legacy or handoff_protocol is not None
                or predecessor_revision is not None
                or any(name in environment for name in _ENV)):
            raise BootstrapError('BOOTSTRAP_MIXED_PROTOCOLS')
        custody = bootstrap_checks.pop('custody', None)
        observation = bootstrap_checks.pop('restoration_observation', None)
        clock = bootstrap_checks.pop('restoration_clock', None)
        retain = bootstrap_checks.pop('restoration_retain', False)
        if bootstrap_checks or type(retain) is not bool or source_state != 'CLEAN_COMMIT':
            raise BootstrapError('BOOTSTRAP_RESTORATION_REJECTED')
        try:
            from kronos.common.failed_successor_restore import (
                AdmissionCustody, RestorationChildIdentity,
                RestorationStartupContext, SelectedPermit, SelectedReservation,
                consume_failed_successor_restore, _document, _installation,
            )
            if type(observation) is not RestorationObservation:
                raise BootstrapError('BOOTSTRAP_RESTORATION_REJECTED')
            child = observation.child
            if (type(custody) is not AdmissionCustody
                    or type(child) is not RestorationChildIdentity
                    or child.process_id != os.getpid()
                    or child.parent_pid != os.getppid()
                    or child.runtime_identity != runtime_identity
                    or child.loaded_revision != revision
                    or observation.permit_sha256 != selection.permit_sha256
                    or observation.source_manifest_path
                        != environment[RESTORATION_CHILD_ENV[2]]
                    or observation.artifact_manifest_path
                        != environment[RESTORATION_CHILD_ENV[3]]):
                raise BootstrapError('BOOTSTRAP_RESTORATION_REJECTED')
            permit = SelectedPermit(selection.permit_path, selection.permit_bytes,
                                    selection.permit_sha256, selection.permit_id)
            reservation = SelectedReservation(
                selection.reservation_path, selection.reservation_bytes,
                selection.reservation_sha256, selection.reservation_id)
            # Reject repository disagreement before the consumer can create its
            # permanent claim. Use the existing selected-byte and installation
            # validators; this does not grant source/artifact correspondence.
            custody.check()
            permit_document, _ = _document(permit.path, permit.byte_size, permit.sha256)
            installation = _installation(permit_document['installation'])
            actual_repository = Path(repository)
            selected_repository = Path(installation['repository_path'])
            if (not actual_repository.is_absolute()
                    or '..' in actual_repository.parts
                    or any(path.is_symlink() for path in
                           (actual_repository, *actual_repository.parents,
                            selected_repository, *selected_repository.parents))
                    or str(actual_repository.resolve()) != installation['repository_path']
                    or selected_repository.resolve() != actual_repository.resolve()
                    or observation.repository != str(actual_repository.resolve())
                    or observation.installation_identity != installation['identity']):
                raise BootstrapError('BOOTSTRAP_RESTORATION_REPOSITORY_MISMATCH')
            custody.check()
            options = dict(custody=custody, child=child)
            if clock is not None:
                options['clock'] = clock
            if retain:
                from kronos.common.failed_successor_restore import _current_document
                reservation_document, _ = _document(reservation.path,
                    reservation.byte_size, reservation.sha256)
                _, head_raw = _current_document(Path(reservation_document['head_path']))
                samples = []
                actual_clock = clock or (lambda: datetime.now(UTC))
                def recorded_clock():
                    value = actual_clock()
                    samples.append(value)
                    return value
                options['clock'] = recorded_clock
            result = consume_failed_successor_restore(permit, reservation, **options)
            if (type(result) is not RestorationStartupContext
                    or result.original_attempt_id != selection.original_attempt_id
                    or result.loaded_revision != revision
                    or result.runtime_identity != runtime_identity):
                raise BootstrapError('BOOTSTRAP_RESTORATION_REJECTED')
            if retain:
                # The unchanged approved consumer samples initial, claim and
                # final UTC. Keep the actual claim timestamp unchanged and
                # carry its final accepted UTC into the adapter's rollback
                # baseline. No second consuming operation occurs.
                if len(samples) != 3:
                    raise BootstrapError('BOOTSTRAP_RESTORATION_RECHECK_REJECTED')
                return retain_restoration_attempt(environment, context=result,
                    custody=custody, observation=observation,
                    head_sha256=sha256(head_raw).hexdigest(), claimed_at=samples[1],
                    consumer_final_at=samples[2], clock=actual_clock)
            # The future native selector supplies the manifest locators, but
            # the child facts above are hashes of the actual opened bytes.
            # Preserve the child fields in this consumed environment only as
            # evidence that the exact closed selector was present; never use
            # these values as source/artifact identity.
            return result
        except BootstrapError:
            raise
        except (AttributeError, KeyError, OSError, TypeError, ValueError,
                OverflowError):
            raise BootstrapError('BOOTSTRAP_RESTORATION_REJECTED') from None
    if legacy and (handoff_protocol is not None or predecessor_revision is not None):
        raise BootstrapError('BOOTSTRAP_MIXED_PROTOCOLS')
    if (handoff_protocol is None) != (predecessor_revision is None):
        raise BootstrapError('BOOTSTRAP_MIXED_PROTOCOLS')
    if legacy and any(k in environment for k in _ENV):
        raise BootstrapError('BOOTSTRAP_MIXED_PROTOCOLS')
    if legacy:
        return consume_bootstrap(root / 'legacy-bootstrap-v1', environment,
            revision=revision, source_state=source_state, repository=repository,
            runtime_identity=runtime_identity, now=now, **bootstrap_checks)
    if handoff_protocol is not None:
        if handoff_protocol != 'V2' or source_state != 'CLEAN_COMMIT':
            raise BootstrapError('BOOTSTRAP_MIXED_PROTOCOLS')
        return consume_drain_handoff(root / 'maintenance', environment,
            runtime_identity=runtime_identity, now=now,
            loaded_revision=predecessor_revision, **{
                name: bootstrap_checks[name] for name in
                ('process_id', 'predecessor_gone', 'port_free')
                if name in bootstrap_checks
            })
    return consume_handoff(root / 'maintenance', environment,
        runtime_identity=runtime_identity, now=now)


# P01-P03 native validation helpers are read-only. The native executable alone
# publishes phase records and advances the admission head under its held OFD.
# Helpers have no inherited admission descriptor and cannot consume a child.
NATIVE_PHASE_SCHEMA = 'KRONOS_NATIVE_ADMISSION_PHASE_V1'
NATIVE_SELECTION_SCHEMA = 'KRONOS_NATIVE_STARTUP_SELECTION_V1'
NATIVE_SELECTION_ENV = tuple('KRONOS_NATIVE_SELECTION_' + key
                             for key in ('PATH', 'BYTES', 'SHA256', 'ID'))
NATIVE_ATTEMPT_ENV = tuple('KRONOS_NATIVE_ATTEMPT_' + key
                           for key in ('PATH', 'BYTES', 'SHA256', 'ID'))


def _native_deny():
    raise BootstrapError('NATIVE_STARTUP_ADMISSION_REJECTED')


def _native_reference(reference, *, document=True):
    from kronos.common import failed_successor_restore as restore
    if type(reference) is not dict or set(reference) != {'identity', 'path', 'bytes', 'sha256'}:
        _native_deny()
    if not restore._identity(reference['identity']):
        _native_deny()
    if document:
        return restore._document(Path(reference['path']), reference['bytes'], reference['sha256'])
    return restore._read_raw(Path(reference['path']), reference['bytes'], reference['sha256'])


def _native_selected_reference(environment, names):
    from kronos.common import failed_successor_restore as restore
    values = [environment.get(name) for name in names]
    if (any(type(value) is not str or not value for value in values)
            or re.fullmatch(r'[1-9][0-9]{0,5}', values[1]) is None
            or not _hex(values[2]) or not restore._identity(values[3])):
        _native_deny()
    return dict(path=values[0], bytes=int(values[1]), sha256=values[2], identity=values[3])


class _NativeReadOnlyChecks:
    """Budget/parent observation for a helper; never AdmissionCustody proof.

    The native caller checks its real OFD both before and after the helper and
    before publication. This class owns no descriptor and never enters the
    R3.1 consumer. The real child independently uses actual adopted custody.
    """
    def __init__(self, parent_pid, parent_birth):
        from kronos.common.release_admission import inherited_budget
        self.parent_pid, self.parent_birth = parent_pid, parent_birth
        self.budget = inherited_budget(120, required=True)
        self.check()

    def check(self):
        self.budget.check()
        if (os.getppid() != self.parent_pid
                or _observe_process(self.parent_pid)['kernel_birth'] != self.parent_birth):
            _native_deny()


def _native_manifest_reference(reference, checks, *, final_lf):
    from kronos.common import failed_successor_restore as restore
    if (type(reference) is not dict or set(reference) != {'identity', 'path', 'bytes', 'sha256'}
            or not restore._identity(reference['identity'])
            or type(reference['bytes']) is not int or not 1 <= reference['bytes'] <= 8 * 1024 * 1024
            or not _hex(reference['sha256'])):
        _native_deny()
    _, raw, value = _read_manifest(reference['path'], checks, final_lf=final_lf)
    if len(raw) != reference['bytes'] or sha256(raw).hexdigest() != reference['sha256']:
        _native_deny()
    return value, raw


def _native_source(selection, checks):
    """Verify selected Git/package inputs without claiming child load evidence."""
    source, source_raw = _native_manifest_reference(selection['source_manifest'], checks, final_lf=False)
    artifact, artifact_raw = _native_manifest_reference(selection['artifact_manifest'], checks, final_lf=True)
    target, installation = selection['target'], selection['installation']
    repository = Path(installation['repository_path'])
    fields = {'schema', 'origin_url', 'source_ref', 'revision', 'git_tree_oid', 'files', 'capture'}
    if (type(source) is not dict or set(source) != fields
            or source['schema'] != 'KRONOS_RESTORATION_SOURCE_MANIFEST_V1'
            or source['revision'] != target['revision']
            or source['origin_url'] != target['origin_url']
            or source['source_ref'] != target['source_ref']
            or sha256(source_raw).hexdigest() != target['source_manifest_sha256']):
        _native_deny()
    files = _tracked_files(repository, target['revision'], checks)
    if source['files'] != files or sha256(_canonical(files)).hexdigest() != target['tree_sha256']:
        _native_deny()
    for args, expected in (
            (('rev-parse', target['revision'] + '^{tree}'), source['git_tree_oid']),
            (('show-ref', '--verify', '--hash', target['source_ref']), target['revision']),
            (('remote', 'get-url', 'origin'), target['origin_url'])):
        if _validation_output(['/usr/bin/git', *args], repository, checks,
                              'NATIVE_SOURCE_INPUT').decode().strip() != expected:
            _native_deny()
    # This is a deterministic selected source declaration, not a StartupCapture
    # or StartupEvidence. Actual pinned imports remain exclusively child facts.
    expected_capture = []
    for row in files:
        relative = row['path']
        for prefix, package in (('src/kronos/', 'kronos'), ('tools/', 'tools')):
            if relative.startswith(prefix) and relative.endswith('.py'):
                parts = list(Path(relative[len(prefix):]).with_suffix('').parts)
                if parts[-1] == '__init__': parts.pop()
                expected_capture.append(dict(module='.'.join([package, *parts]),
                    path=relative, sha256=row['sha256']))
    expected_capture.sort(key=lambda row: row['module'])
    if (source['capture'] != expected_capture
            or sha256(_canonical([[r['module'], r['sha256']] for r in expected_capture])).hexdigest()
                != target['pinned_capture_sha256']):
        _native_deny()
    bundle = Path(installation['bundle_path'])
    digest = _validate_artifact_manifest(selection['artifact_manifest']['path'],
        bundle, source, files, checks)
    if (digest != target['artifact_manifest_sha256']
            or sha256(artifact_raw).hexdigest() != digest
            or artifact['source_revision'] != target['revision']):
        _native_deny()
    return source


def _native_selection(reference, checks, *, mode, repository, bundle, anchor, now):
    from kronos.common import failed_successor_restore as restore
    value, raw = _native_reference(reference)
    fields = {'schema', 'selection_id', 'mode', 'installation', 'target',
              'source_manifest', 'artifact_manifest', 'operational_order',
              'decisions', 'permit', 'valid_from', 'valid_until'}
    if (set(value) != fields or value['schema'] != NATIVE_SELECTION_SCHEMA
            or value['selection_id'] != reference['identity'] or value['mode'] != mode
            or type(value['decisions']) is not dict
            or set(value['decisions']) != {'sponsor', 'ca', 'pcp', 'product'}
            or not restore._aware_utc(value['valid_from']) <= now <= restore._aware_utc(value['valid_until'])):
        _native_deny()
    installation = restore._installation(value['installation'])
    restore._target(value['target'])
    if (installation['repository_path'] != repository or installation['bundle_path'] != bundle
            or installation['anchor_path'] != anchor):
        _native_deny()
    _native_reference(value['operational_order'], document=False)
    for document in value['decisions'].values():
        _native_reference(document, document=False)
    # Exact document integrity/applicability is checked here. Human approval
    # meaning, provenance and scope remain the approved supervised procedure.
    if value['operational_order'] != value['decisions']['sponsor']:
        _native_deny()
    if mode == RESTORATION_MODE:
        permit, _ = _native_reference(value['permit'])
        chosen = restore.SelectedPermit(Path(value['permit']['path']), value['permit']['bytes'],
                                        value['permit']['sha256'], value['permit']['identity'])
        permit = restore._permit(permit, chosen, now)
        if (permit['installation'] != installation or permit['restoration_target'] != value['target']):
            _native_deny()
        for label, prefix in (('sponsor', 'sponsor_order'), ('ca', 'ca_decision'),
                              ('pcp', 'pcp_decision'), ('product', 'product_decision')):
            ref = value['decisions'][label]
            if (permit['authority'][prefix + '_identity'] != ref['identity']
                    or permit['authority'][prefix + '_sha256'] != ref['sha256']):
                _native_deny()
    elif value['permit'] is not None:
        _native_deny()
    _native_source(value, checks)
    checks.check()
    return value, raw


def _native_head(installation, *, checks):
    """Read the one initialized native head; never create or repair it."""
    from kronos.common import failed_successor_restore as restore
    root = Path(installation['anchor_path']) / 'failed-successor-restore-v1'
    restore._initialization_admission(root, installation, checks=checks)
    restore._secure_parent(root)
    head, raw = restore._current_document(root / 'admission-head.json')
    fields = {'schema', 'installation_identity', 'sequence', 'state', 'incident_id',
              'active_reservation_id', 'active_reservation_sha256', 'previous_head_sha256', 'recorded_at'}
    if (set(head) != fields or head['schema'] != restore.HEAD_SCHEMA
            or head['installation_identity'] != installation['identity']
            or type(head['sequence']) is not int or not 1 <= head['sequence'] <= 1000000000
            or not restore._identity(head['active_reservation_id'])
            or not _hex(head['active_reservation_sha256']) or not _hex(head['previous_head_sha256'])
            or head['state'] not in {'NATIVE_ACTIVATED', 'ORIGINAL_RESERVED',
                'SHUTDOWN_DISPATCH_INTENT', 'PREDECESSOR_RETIRED', 'CHILD_START_RESERVED',
                'INCIDENT_OPEN', 'RESTORATION_RESERVED', 'READY_COMPLETE', 'READY_OUTSIDE_PERMIT',
                'UNRESOLVED','STOPPED','ORDINARY_ACTIVATED','ORDINARY_STOP_INTENT'}
            or (head['incident_id'] is not None and not restore._identity(head['incident_id']))):
        _native_deny()
    restore._aware_utc(head['recorded_at'])
    _, retained = restore._current_document(root / ('head-' + str(head['sequence']) + '.json'))
    if retained != raw or os.path.lexists(root / ('head-' + str(head['sequence'] + 1) + '.json')):
        _native_deny()
    if head['sequence'] == 1:
        if head['state'] != 'NATIVE_ACTIVATED' or head['previous_head_sha256'] != '0' * 64: _native_deny()
    else:
        previous_head, previous_raw = restore._current_document(root / ('head-' + str(head['sequence'] - 1) + '.json'))
        if (sha256(previous_raw).hexdigest() != head['previous_head_sha256']
                or previous_head.get('sequence') != head['sequence'] - 1
                or previous_head.get('installation_identity') != installation['identity']
                or restore._aware_utc(previous_head['recorded_at']) > restore._aware_utc(head['recorded_at'])):
            _native_deny()
    record, record_raw = restore._document(root / (head['active_reservation_id'] + '.json'),
        (root / (head['active_reservation_id'] + '.json')).stat().st_size,
        head['active_reservation_sha256'])
    if head['state'] == 'RESTORATION_RESERVED':
        if (record.get('schema') != restore.RESERVATION_SCHEMA
                or record.get('reservation_id') != head['active_reservation_id']
                or record.get('incident_id') != head['incident_id']):
            _native_deny()
    elif (record.get('schema') != NATIVE_PHASE_SCHEMA
            or record.get('identity') != head['active_reservation_id']
            or record.get('phase') != head['state']):
        _native_deny()
    if record.get('installation_identity') != installation['identity']:
        _native_deny()
    checks.check()
    checks.budget.check()
    return root, head, raw, record, record_raw


def _native_phase(identity, phase, *, original, installation, parent,
                  selected, predecessor, previous, details, now):
    """Return proposed immutable bytes for the native writer, never publish."""
    return dict(schema=NATIVE_PHASE_SCHEMA, identity=identity, phase=phase,
        original_attempt_id=original, installation_identity=installation['identity'],
        installation=installation, parent=parent, predecessor=predecessor,
        selection=selected, previous=previous, details=details, recorded_at=now.isoformat())


def _native_installation(repository, bundle, anchor):
    from kronos.common import failed_successor_restore as restore
    from kronos.common import release_admission as admission
    return restore._installation(admission.frozen_installation(repository,bundle,anchor))


def _native_parent(checks, repository, bundle):
    from kronos.common import release_admission as admission
    observed = _observe_process(checks.parent_pid)
    image = admission._parent_image(checks.parent_pid)
    from kronos.common import failed_successor_restore as restore
    # The image requirement is the existing canonical requirement; a selected
    # document/environment string never supplies an observed image.
    expected = str(Path(bundle) / 'Contents/MacOS/KRONOS')
    if (image != admission.CANONICAL_PARENT or image != expected
            or Path(image).resolve() != Path(image)):
        _native_deny()
    revision = _validation_output(['/usr/bin/git', 'rev-parse', 'HEAD'],
        Path(repository), checks, 'NATIVE_PARENT_SOURCE').decode().strip()
    if restore._REVISION.fullmatch(revision) is None:
        _native_deny()
    identity = dict(pid=checks.parent_pid, kernel_birth=observed['kernel_birth'], revision=revision)
    return dict(runtime_identity=sha256(_canonical(identity)).hexdigest(), **identity)


def _native_observed_absent(process):
    try: current = _observe_process(process['pid'])
    except BootstrapError:
        try: os.kill(process['pid'], 0)
        except ProcessLookupError: return True
        return False
    return current['kernel_birth'] != process['kernel_birth']


def _native_advance(request, current, head, previous, installation, parent, now, checks):
    from kronos.common import failed_successor_restore as restore
    fields = {'schema', 'identity', 'phase', 'original_attempt_id', 'installation_identity',
        'installation', 'parent', 'predecessor', 'selection', 'previous', 'details', 'recorded_at'}
    if (set(current) != fields or current['parent'] != parent
            or current['selection'] != request['selected']
            or current['installation'] != installation
            or type(request['details']) is not dict
            or set(request['details']) != {'phase', 'observed'}):
        _native_deny()
    phase, observed = request['details']['phase'], request['details']['observed']
    allowed = {'SHUTDOWN_DISPATCH_INTENT': {'ORIGINAL_RESERVED'},
        'PREDECESSOR_RETIRED': {'SHUTDOWN_DISPATCH_INTENT'},
        'CHILD_START_RESERVED': {'ORIGINAL_RESERVED', 'PREDECESSOR_RETIRED'}}
    if phase not in allowed or head['state'] not in allowed[phase]: _native_deny()
    details = dict(current['details'])
    predecessor = current['predecessor']
    if phase == 'SHUTDOWN_DISPATCH_INTENT':
        if (predecessor is None or type(observed) is not dict or set(observed) != {'generation', 'control'}
                or not _hex(observed['generation'])): _native_deny()
        if predecessor['revision'] is not None: restore._process(predecessor)
        if _observe_process(predecessor['pid'])['kernel_birth'] != predecessor['kernel_birth']: _native_deny()
        raw = _native_reference(observed['control'], document=False)
        fields = raw.decode('ascii').strip().split()
        if (len(fields) != 3 or fields[0] != 'KRONOS_BROWSER_BACKEND_CONTROL_V1'
                or fields[1] != str(predecessor['pid']) or not _hex(fields[2])): _native_deny()
        details.update(generation=observed['generation'], control=observed['control'])
    elif phase == 'PREDECESSOR_RETIRED':
        if (type(observed) is not dict or set(observed) != {'shutdown_accepted', 'listener_absent', 'handoff'}
                or observed['shutdown_accepted'] is not True or observed['listener_absent'] is not True
                or predecessor is None or not _native_observed_absent(predecessor)):
            _native_deny()
        signed, _ = _native_reference(observed['handoff'])
        core = signed['record']
        from kronos.common.maintenance import _valid_drain, HANDOFF_SECONDS
        v2 = core['schema'] == 'KRONOS_MAINTENANCE_HANDOFF_V2'
        if (set(signed) != {'record', 'proof'} or not _hex(signed['proof'])
                or core['schema'] not in {'KRONOS_MAINTENANCE_HANDOFF_V1','KRONOS_MAINTENANCE_HANDOFF_V2'}
                or core['generation'] != details['generation']
                or core['parent_pid'] != predecessor['pid']
                or (v2 and (core['runtime_identity'] != predecessor['runtime_identity']
                    or core['loaded_revision'] != predecessor['revision'] or not _valid_drain(core['drain'])))
                or (not v2 and request['mode'] != 'LEGACY_BOOTSTRAP')
                or not 0 <= (now - restore._aware_utc(core['created_at'])).total_seconds() <= HANDOFF_SECONDS):
            _native_deny()
        details['handoff'] = observed['handoff']
    else:
        if observed != {} or (predecessor is not None and head['state'] != 'PREDECESSOR_RETIRED'):
            _native_deny()
        # Child PID/runtime are deliberately absent. The sole-fork intent is
        # committed now; actual identity is published separately after fork.
        if details.get('mode')=='ORDINARY':
            _check_operation_timing(details['timing'],checks)
            _ordinary_activation(installation,checks,now=now,selection=request['selected'])
            if details.get('prior_stop') is not None:
                details['current_stop_check']=_ordinary_current_check(details['prior_stop'],installation,checks)
            if details.get('prior_activation') is not None:
                details['current_activation_check']=_ordinary_activation_current_check(details['prior_activation'],installation,checks)
        details['child_identity'] = 'NOT_YET_OBSERVED'
    identity = current['original_attempt_id'] + '.' + phase.lower().replace('_', '-')
    if not restore._identity(identity): _native_deny()
    return _native_phase(identity, phase, original=current['original_attempt_id'],
        installation=installation, parent=parent, selected=request['selected'],
        predecessor=predecessor, previous=previous, details=details, now=now)


def _native_file_rows(scopes, checks):
    rows = []
    for scope in scopes:
        if type(scope) is not dict or set(scope) != {'path', 'present'} or type(scope['present']) is not bool:
            _native_deny()
        base = Path(scope['path'])
        if (not base.is_absolute() or '..' in base.parts
                or any(p.is_symlink() for p in (base, *base.parents))
                or os.path.lexists(base) != scope['present']):
            _native_deny()
        if not scope['present']: continue
        if not base.is_dir(): _native_deny()
        for path in sorted(base.rglob('*')):
            checks.check()
            metadata = path.stat(follow_symlinks=False)
            if stat.S_ISDIR(metadata.st_mode): continue
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid(): _native_deny()
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
            try:
                before = os.fstat(fd);size = 0;digest = sha256()
                while True:
                    checks.check();block = os.read(fd, 65536)
                    if not block: break
                    size += len(block);digest.update(block)
                after = os.fstat(fd);named = path.stat(follow_symlinks=False)
                fields = lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
                if fields(metadata) != fields(before) or fields(before) != fields(after) or fields(after) != fields(named) or size != before.st_size:
                    _native_deny()
                rows.append(dict(path=str(path),bytes=size,sha256=digest.hexdigest(),mode=stat.S_IMODE(before.st_mode)))
            finally: os.close(fd)
    return sorted(rows, key=lambda row:row['path'])


def _native_recheck_settled(reference, settled, checks, incident):
    state, _ = _native_manifest_reference(reference, checks, final_lf=False)
    if (state.get('schema') != 'KRONOS_NATIVE_CHILD_FACT_V1'
            or state.get('phase') != 'settled-state-files'
            or state.get('child') != incident['failed_successor']
            or state.get('parent') != incident['original_parent']
            or state.get('original_attempt_id') != incident['original_attempt_id']
            or reference['identity'] != settled['state_manifest_identity']
            or reference['sha256'] != settled['state_manifest_sha256']):
        _native_deny()
    payload = state['payload']
    owners, _ = _native_reference(payload['owner_results'])
    if (payload['owner_results']['sha256'] != settled['owner_results_sha256']
            or owners.get('schema') != 'KRONOS_NATIVE_CHILD_FACT_V1'
            or owners.get('phase') != 'settled-owners' or owners.get('child') != state['child']
            or owners.get('parent') != state['parent']
            or owners['payload'].get('validated_current') is not True
            or owners['payload']['notification_checkpoint'] != settled['notification_checkpoint']
            or _native_file_rows(payload['scopes'], checks) != payload['files']):
        _native_deny()


def _native_restoration(selection, current, head, installation, parent, root, now, checks):
    from kronos.common import failed_successor_restore as restore
    if head['state'] != 'INCIDENT_OPEN' or current['details'].get('eligible_restoration') is not True:
        _native_deny()
    permit, _ = _native_reference(selection['permit'])
    incident_document, _, incident_ref = restore._load_reference(permit['incident'])
    incident = restore._incident(incident_document, incident_ref, installation)
    settled_document, _, settled_ref = restore._load_reference(permit['settled_state'])
    settled = restore._settled(settled_document, settled_ref, incident)
    failure_document, _, failure_ref = restore._load_reference(permit['failure_cleanup'])
    restore._failure(failure_document, failure_ref, incident, settled_ref)
    if (incident['original_attempt_id'] != current['original_attempt_id']
            or incident['incident_id'] != head['incident_id']
            or any(current['details'][name] != reference for name, reference in (
                ('incident', incident_ref), ('failure_cleanup', failure_ref), ('settled_state', settled_ref)))
            or not _native_observed_absent(incident['failed_successor'])
            or not _native_observed_absent(incident['predecessor'])):
        _native_deny()
    # Current settled files were produced through the actual owner seam. Byte
    # correspondence is rechecked under native exclusion before reservation;
    # application output may legitimately progress after the child consumes.
    _native_recheck_settled(current['details']['state_manifest'], settled, checks, incident)
    identity = 'restoration-' + sha256(_canonical([
        installation['identity'], incident['original_attempt_id'], incident['incident_id']])).hexdigest()
    record = dict(schema=restore.RESERVATION_SCHEMA, reservation_id=identity,
        incident_id=incident['incident_id'], permit_id=permit['permit_id'],
        permit_sha256=selection['permit']['sha256'], installation_identity=installation['identity'],
        state='RESTORATION_RESERVED', parent=parent, restoration_target=permit['restoration_target'],
        settled_state=settled_ref, attempt_nonce=sha256(_canonical([identity, parent, now.isoformat()])).hexdigest(),
        created_at=now.isoformat(), valid_until=permit['valid_until'],
        head_path=str(root / 'admission-head.json'),
        claim_path=str(root / (incident['incident_id'] + '.' + identity + '.child-claimed.json')))
    restore._reservation(record, restore.SelectedReservation(root / (identity + '.json'),
        len(_canonical(record)), sha256(_canonical(record)).hexdigest(), identity), permit,
        restore.SelectedPermit(Path(selection['permit']['path']), selection['permit']['bytes'],
            selection['permit']['sha256'], selection['permit']['identity']), incident, settled_ref)
    return record


def _native_fact(root, selected, phase, checks, *, parent, child=None, original=None):
    """Read one exclusive fact from its selected child, never infer an absent one."""
    from kronos.common import failed_successor_restore as restore
    path = root / (selected['identity'] + '.' + phase + '.json')
    _, raw, value = _read_manifest(path, checks, final_lf=False)
    if (set(value) != {'schema', 'selected', 'original_attempt_id', 'parent', 'child',
                       'deadline_ns', 'phase', 'payload', 'recorded_at'}
            or value['schema'] != 'KRONOS_NATIVE_CHILD_FACT_V1'
            or value['selected'] != selected or value['phase'] != phase
            or value['parent'] != parent or type(value['payload']) is not dict
            or value['deadline_ns'] != checks.attempt_deadline_ns
            or (child is not None and value['child'] != child)
            or (original is not None and value['original_attempt_id'] != original)
            or restore._aware_utc(value['recorded_at']) > datetime.now(UTC)):
        _native_deny()
    restore._process(value['child'])
    if not restore._identity(value['original_attempt_id']): _native_deny()
    return value, dict(identity=selected['identity'] + '.' + phase,
                      path=str(path), bytes=len(raw), sha256=sha256(raw).hexdigest())


def _native_runtime_observation(encoded):
    """Decode exact HTTP JSON bytes; its field order is not manifest authority."""
    if (type(encoded) is not str or not 2 <= len(encoded) <= 131072
            or len(encoded) % 2 or re.fullmatch(r'[0-9a-f]+', encoded) is None):
        _native_deny()
    def unique(values):
        result = {}
        for key, value in values:
            if key in result: _native_deny()
            result[key] = value
        return result
    try:
        raw = bytes.fromhex(encoded)
        if raw.startswith(b'\xef\xbb\xbf'): _native_deny()
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
                           parse_constant=lambda _value: _native_deny())
        if type(value) is not dict: _native_deny()
        return value
    except (UnicodeError, ValueError, TypeError):
        _native_deny()


def _native_terminal(request, current, head, previous, installation, parent, now,
                     root, checks, selection):
    """Qualify actual child outcomes; return records for the native writer only."""
    from kronos.common import failed_successor_restore as restore
    if (head['state'] not in {'CHILD_START_RESERVED', 'RESTORATION_RESERVED'}
            or current['parent'] != parent): _native_deny()
    selected = previous
    identified, _ = restore._current_document(root / (selected['identity'] + '.identified.json'))
    if (set(identified) != {'schema', 'selected', 'parent', 'child'}
            or identified['schema'] != 'KRONOS_NATIVE_CHILD_IDENTIFIED_V1'
            or identified['selected'] != selected or identified['parent'] != parent
            or set(identified['child']) != {'pid', 'kernel_birth'}): _native_deny()
    capture, capture_ref = _native_fact(root, selected, 'capture', checks, parent=parent)
    child, original = capture['child'], capture['original_attempt_id']
    if identified['child'] != {k:child[k] for k in ('pid', 'kernel_birth')}: _native_deny()
    # Revalidate the real StartupEvidence integrity, not an author-labelled hash.
    from kronos.intraday.runtime_identity import StartupEvidence
    evidence_values = dict(capture['payload']['startup_evidence'])
    evidence_values['startup_boundary_at'] = restore._aware_utc(evidence_values['startup_boundary_at'])
    evidence_values['loaded_modules'] = tuple(tuple(row) for row in evidence_values['loaded_modules'])
    evidence = StartupEvidence(**evidence_values)
    if (evidence.process_id != child['pid'] or evidence.source_state != 'CLEAN_COMMIT'
            or evidence.load_verification != 'PINNED_STARTUP_IMPORTS'
            or evidence.source_revision != selection['target']['revision']
            or evidence.source_snapshot_digest != selection['target']['pinned_capture_sha256']
            or child['revision'] != evidence.source_revision
            or child['runtime_identity'] != sha256(evidence.evidence_identity.encode()).hexdigest()):
        _native_deny()
    if head['state'] == 'CHILD_START_RESERVED':
        if (current['selection'] != request['selected'] or current['original_attempt_id'] != original
                or current['details']['target'] != selection['target']): _native_deny()
    else:
        permit, _ = _native_reference(selection['permit'])
        incident, _ = _native_reference(permit['incident'])
        if (current['permit_sha256'] != selection['permit']['sha256']
                or current['permit_id'] != selection['permit']['identity']
                or original != incident['original_attempt_id']): _native_deny()
        claim, _ = restore._current_document(Path(current['claim_path']))
        if (claim['reservation_id'] != current['reservation_id']
                or claim['reservation_sha256'] != previous['sha256']
                or claim['permit_sha256'] != selection['permit']['sha256']
                or claim['child'] != child or claim['parent'] != parent): _native_deny()
    consumed, consumed_ref = _native_fact(root, selected, 'consumed', checks,
        parent=parent, child=child, original=original)
    facts = [capture_ref, consumed_ref]
    def fact(phase):
        value, reference = _native_fact(root, selected, phase, checks,
            parent=parent, child=child, original=original)
        facts.append(reference)
        return value
    documents = []
    details = dict(child=child, selected=selected, observations=request['details'], facts=facts,
                   eligible_restoration=False)
    if request['action'] == 'child-ready':
        observed = request['details']
        if (set(observed) != {'child_pid', 'listener_owned', 'runtime_json_hex', 'control'}
                or observed['child_pid'] != child['pid'] or observed['listener_owned'] is not True
                or _observe_process(child['pid'])['kernel_birth'] != child['kernel_birth']): _native_deny()
        runtime = _native_runtime_observation(observed['runtime_json_hex'])
        if (runtime['schema'] != 'KRONOS-RUNTIME-STATE/1.0.0'
                or runtime['process'] != dict(pid=child['pid'], revision=child['revision'], source_state='CLEAN_COMMIT')
                or runtime['maintenance']['active'] is not False
                or runtime['maintenance']['startup'] != 'READY'): _native_deny()
        control_raw = _native_reference(observed['control'], document=False)
        parts = control_raw.decode('ascii').strip().split()
        if (len(parts) != 3 or parts[0] != 'KRONOS_BROWSER_BACKEND_CONTROL_V1'
                or parts[1] != str(child['pid']) or not _hex(parts[2])): _native_deny()
        intent, completion = fact('completion-entered'), fact('completion-outcome')
        if intent['payload'] != dict(entered=True): _native_deny()
        result = completion['payload']
        if (result['returned'] is not True or result['state'] != 'READY'
                or result['ready_observed'] is not True or result['receipt'] is None): _native_deny()
        receipt_ref = dict(result['receipt'], identity=child['runtime_identity'] + '-startup')
        receipt_raw = _native_reference(receipt_ref, document=False)
        receipt = json.loads(receipt_raw)
        if (set(receipt) != {'schema','runtime_identity','maintenance_identity','at','trigger'}
                or receipt['schema'] != 'RUNTIME_STARTUP_MAINTENANCE_EXIT_V1'
                or receipt['runtime_identity'] != child['runtime_identity']
                or receipt['maintenance_identity'] != consumed['payload']['maintenance_identity']
                or receipt['trigger'] != 'VERIFIED_CANONICAL_STARTUP'): _native_deny()
        restore._aware_utc(receipt['at'])
        latest = restore._aware_utc(intent['recorded_at'])
        for phase in ('completion-outcome','ready-release-intent','ready-release-returned',
                      'ux10-intent','ux10-returned','wo13-intent','wo13-returned','k5-intent','k5-returned','startup-success'):
            value = completion if phase == 'completion-outcome' else fact(phase)
            observed_at = restore._aware_utc(value['recorded_at'])
            if observed_at < latest: _native_deny()
            latest = observed_at
            if phase.endswith('-returned'):
                if value['payload'] != dict(outcome='returned', custody_released=True, cleanup_started=False): _native_deny()
        success = value['payload']
        if (success['ready'] is not True or success['custody_released'] is not True
                or success['activation'] != ['ready-release','ux10','wo13','k5']): _native_deny()
        details.update(receipt=receipt_ref, runtime=runtime)
        phase = 'READY_COMPLETE'
    elif request['action'] == 'child-exited':
        observed = request['details']
        if (set(observed) != {'child_pid','terminal_reaped','exit_code'}
                or observed['child_pid'] != child['pid'] or observed['terminal_reaped'] is not True
                or not _native_observed_absent(child)): _native_deny()
        cleanup, ack = fact('cleanup-observed'), fact('cleanup-acknowledged')
        result = cleanup['payload']
        from kronos.browser.server import _StartupCleanup
        from kronos.common.maintenance import _valid_drain
        if (observed['exit_code'] != 78 or result['complete'] is not True
                or result['final_owner_proof'] is not True or result['helpers_unresolved'] is not False
                or result['errors'] or set(result['ledger']) != set(_StartupCleanup._names)
                or any(row['state'] not in {'NOT_CREATED','CREATED_AND_CLEANED'}
                    for row in result['ledger'].values())
                or ack['payload'] != dict(cleanup_started=True,cleanup_complete=True,custody_released=True)):
            _native_deny()
        details['cleanup_complete'] = True
        if result['ready_observed'] is True or result['ready_evidence']['ready_or_receipt'] is True:
            phase = 'READY_OUTSIDE_PERMIT'
        else:
            # Completion intent with no positive final outcome is ambiguous.
            # A successful application cleanup does not supply missing continuity.
            phase = 'UNRESOLVED'
            predecessor = current.get('predecessor')
            v2 = consumed['payload']['original_v2']
            eligible = (head['state'] == 'CHILD_START_RESERVED' and not result['completion_entered']
                and result['ready_evidence']['receipt_proven_absent'] is True
                and result['settled_continuity'] == 'VALIDATED_CURRENT' and result['settled'] is not None
                and predecessor is not None and _native_observed_absent(predecessor)
                and _valid_drain(result['final_owner_attestation'])
                and v2 is not None and consumed['payload']['protocol'] == 'DrainStartupContext')
            if not eligible and current.get('details',{}).get('mode')=='ORDINARY' and predecessor is None:
                phase='STOPPED'
            if eligible:
                incident_id = 'incident-' + sha256(_canonical([installation['identity'], original])).hexdigest()
                incident = dict(schema=restore.INCIDENT_SCHEMA, incident_id=incident_id,
                    original_attempt_id=original, installation_identity=installation['identity'],
                    predecessor=predecessor, original_parent=parent, failed_successor=child,
                    failed_target=current['details']['target'], original_admission_identity=original,
                    original_v2=dict(handoff_identity=v2['handoff']['identity'],handoff_sha256=v2['handoff']['sha256'],
                        consumption_identity=v2['consumption']['identity'],consumption_sha256=v2['consumption']['sha256']),
                    created_at=now.isoformat())
                def retain(document, identity):
                    raw = _canonical(document)
                    reference = dict(identity=identity,path=str(root / (identity + '.json')),
                        bytes=len(raw),sha256=sha256(raw).hexdigest())
                    documents.append(dict(reference=reference,document=document));return reference
                incident_ref = retain(incident, incident_id)
                restore._incident(incident, incident_ref, installation)
                cert = result['settled']
                settled = dict(schema=restore.SETTLED_SCHEMA,settled_state_id=incident_id+'.settled',
                    incident_id=incident_id,status='CERTIFIED_CURRENT',
                    state_manifest_identity=cert['state_manifest']['identity'],state_manifest_sha256=cert['state_manifest']['sha256'],
                    owner_results_sha256=cert['owner_results']['sha256'],notification_checkpoint=cert['notification_checkpoint'],
                    original_v2=incident['original_v2'],certified_at=now.isoformat())
                settled_ref = retain(settled,settled['settled_state_id']);restore._settled(settled,settled_ref,incident)
                _native_recheck_settled(cert['state_manifest'],settled,checks,incident)
                failure = dict(schema=restore.FAILURE_SCHEMA,failure_cleanup_id=incident_id+'.failure',
                    incident_id=incident_id,original_attempt_id=original,failed_successor=child,
                    failure_stage='PRE_COMPLETION',failure_result='ACTUAL_CHILD_FAILURE_CLEANED',
                    ready=dict(completion_entered=False,outcome='COMPLETION_PROVEN_NOT_ENTERED',
                        receipt='PROVEN_NOT_CREATED',ambiguity='NONE'),
                    cleanup=dict(state='COMPLETE',owner_ledger_identity=facts[-2]['identity'],
                        owner_ledger_sha256=facts[-2]['sha256'],final_owner_proof_identity=facts[-2]['identity'],
                        final_owner_proof_sha256=facts[-2]['sha256'],validation_helpers='TERMINAL',
                        actionable_owner_count=0,acknowledged=True,custody_disposition='RELEASED_AFTER_COMPLETE_CLEANUP'),
                    parent_terminal=dict(parent_pid=parent['pid'],parent_kernel_birth=parent['kernel_birth'],
                        child_pid=child['pid'],child_kernel_birth=child['kernel_birth'],observation='TERMINAL_REAPED',exit_code=78),
                    settled_state=settled_ref,recorded_at=now.isoformat())
                failure_ref = retain(failure,failure['failure_cleanup_id']);restore._failure(failure,failure_ref,incident,settled_ref)
                details.update(eligible_restoration=True,incident=incident_ref,settled_state=settled_ref,
                    failure_cleanup=failure_ref,state_manifest=cert['state_manifest'])
                phase = 'INCIDENT_OPEN'
    else: _native_deny()
    identity = selected['identity'] + '.' + phase.lower().replace('_','-')
    record = _native_phase(identity,phase,original=original,installation=installation,parent=parent,
        selected=request['selected'],predecessor=current.get('predecessor'),previous=previous,details=details,now=now)
    return record, documents


def _native_initialization_enrollment(reference, checks, *, installation):
    """Accept only an existing native capture/success lineage, never status.

    The retained pre-R3 Release B has no verified instance of this format.
    Missing evidence stays denied; this function creates no historical proof.
    """
    from kronos.common import failed_successor_restore as restore
    from kronos.intraday.runtime_identity import StartupEvidence
    capture, _ = _native_manifest_reference(reference,checks,final_lf=False)
    if (set(capture)!={'schema','selected','original_attempt_id','parent','child','deadline_ns','phase','payload','recorded_at'}
            or capture.get('schema') != 'KRONOS_NATIVE_CHILD_FACT_V1'
            or capture.get('phase') != 'capture'):
        _native_deny()
    child = restore._process(capture['child'])
    values = dict(capture['payload']['startup_evidence'])
    values['startup_boundary_at'] = restore._aware_utc(values['startup_boundary_at'])
    values['loaded_modules'] = tuple(tuple(row) for row in values['loaded_modules'])
    evidence = StartupEvidence(**values)
    if (evidence.process_id != child['pid'] or evidence.source_revision != child['revision']
            or evidence.source_state != 'CLEAN_COMMIT'
            or evidence.load_verification != 'PINNED_STARTUP_IMPORTS'
            or child['runtime_identity'] != sha256(evidence.evidence_identity.encode()).hexdigest()
            or _observe_process(child['pid'])['kernel_birth'] != child['kernel_birth']):
        _native_deny()
    selected = capture['selected']
    selected_document, _ = _native_reference(selected)
    if selected_document.get('schema')==restore.RESERVATION_SCHEMA:
        if selected_document.get('installation_identity')!=installation['identity']:_native_deny()
        target=restore._target(selected_document['restoration_target'])
    elif (selected_document.get('schema')==NATIVE_PHASE_SCHEMA
          and selected_document.get('phase')=='CHILD_START_RESERVED'):
        if selected_document.get('installation')!=installation:_native_deny()
        target=restore._target(selected_document['details']['target'])
    else:_native_deny()
    if (target['revision']!=evidence.source_revision
            or target['pinned_capture_sha256']!=evidence.source_snapshot_digest
            or selected_document.get('parent')!=capture['parent']): _native_deny()
    path = Path(reference['path']).parent / (selected['identity'] + '.startup-success.json')
    success, _ = restore._current_document(path)
    if (success.get('schema') != 'KRONOS_NATIVE_CHILD_FACT_V1'
            or success.get('phase') != 'startup-success'
            or any(success.get(k) != capture[k] for k in (
                'selected','original_attempt_id','parent','child'))
            or success['payload'].get('ready') is not True
            or success['payload'].get('custody_released') is not True
            or success['payload'].get('activation') != ['ready-release','ux10','wo13','k5']):
        _native_deny()
    released, _ = restore._current_document(Path(reference['path']).parent /
        (selected['identity']+'.ready-release-returned.json'))
    if (released.get('schema') != 'KRONOS_NATIVE_CHILD_FACT_V1'
            or released.get('phase') != 'ready-release-returned'
            or any(released.get(k) != capture[k] for k in ('selected','original_attempt_id','parent','child'))
            or released['payload'] != dict(outcome='returned',custody_released=True,cleanup_started=False)):
        _native_deny()
    checks.check()
    return child


def _native_initialization_proposal(request, checks, installation, parent, now):
    """Head-independent read-only proposal. Cannot supply admission proof."""
    from kronos.common import failed_successor_restore as restore
    details = request['details']
    if (type(details) is not dict or set(details) != {
            'operator_order','eligibility','predecessor_evidence','observed_predecessor'}
            or not restore._identity(request['identity'])
            or details['eligibility'] not in {'COLD_ABSENT','EXISTING_RELEASE_B'}): _native_deny()
    selection, _ = _native_selection(request['selected'], checks, mode='ORDINARY',
        repository=request['repository'], bundle=request['bundle'], anchor=request['anchor'], now=now)
    if selection['installation']!=installation:_native_deny()
    _native_reference(details['operator_order'], document=False)
    root = Path(installation['anchor_path']) / 'failed-successor-restore-v1'
    recheck=request['action']=='initialization-recheck'
    if recheck:
        restore._secure_parent(root)
    else:
        try:root.lstat()
        except FileNotFoundError:pass
        else:_native_deny()
    predecessor = None
    if details['eligibility'] == 'COLD_ABSENT':
        if details['predecessor_evidence'] is not None or details['observed_predecessor'] is not None:
            _native_deny()
    else:
        process = _native_initialization_enrollment(details['predecessor_evidence'], checks,installation=installation)
        if details['observed_predecessor'] != {k:process[k] for k in ('pid','kernel_birth')}: _native_deny()
        predecessor = dict(process=process, evidence=details['predecessor_evidence'])
    attempt = dict(schema=restore.INITIALIZATION_ATTEMPT_SCHEMA, attempt_id=request['identity'],
        installation=installation, selection=request['selected'], operator_order=details['operator_order'],
        parent=parent, predecessor=predecessor, eligibility=details['eligibility'],
        started_at=now.isoformat(), deadline_ns=checks.attempt_deadline_ns)
    if recheck:
        existing, attempt_raw=restore._current_document(root/'initialization-attempt.json')
        if (set(existing)!=set(attempt) or any(existing[k]!=v for k,v in attempt.items() if k!='started_at')
                or now<restore._aware_utc(existing['started_at'])):_native_deny()
        phase,phase_raw=restore._current_document(root/(request['identity']+'.json'))
        head,head_raw=restore._current_document(root/'admission-head.json')
        _,first_raw=restore._current_document(root/'head-1.json')
        if (head_raw!=first_raw or head.get('sequence')!=1 or head.get('state')!='NATIVE_ACTIVATED'
                or head.get('active_reservation_id')!=request['identity']
                or head.get('active_reservation_sha256')!=sha256(phase_raw).hexdigest()
                or phase.get('installation')!=installation or phase.get('parent')!=parent
                or phase.get('selection')!=request['selected'] or phase.get('phase')!='NATIVE_ACTIVATED'
                or phase.get('details',{}).get('initialization_attempt')!=dict(
                    identity=request['identity'],path=str(root/'initialization-attempt.json'),
                    bytes=len(attempt_raw),sha256=sha256(attempt_raw).hexdigest())
                or os.path.lexists(root/'head-2.json')):_native_deny()
        final=datetime.now(UTC)
        if final<now or final>restore._aware_utc(selection['valid_until']):_native_deny()
        checks.check()
        return dict(disposition='PREPARED_PENDING_EXACT_ADMISSION_REVIEW',installation=installation,
            attempt=existing,phase=phase,head=head)
    raw = _canonical(attempt)
    attempt_ref = dict(identity=request['identity'], path=str(root/'initialization-attempt.json'),
        bytes=len(raw), sha256=sha256(raw).hexdigest())
    phase = _native_phase(request['identity'], 'NATIVE_ACTIVATED', original=request['identity'],
        installation=installation, parent=parent, selected=request['selected'],
        predecessor=None if predecessor is None else predecessor['process'], previous=None,
        details=dict(initialization_attempt=attempt_ref, enrolled_predecessor=predecessor,
            mode='ORDINARY', target=selection['target'], operational_order=selection['operational_order'],
            decisions=selection['decisions']), now=now)
    phase_raw = _canonical(phase)
    head = dict(schema=restore.HEAD_SCHEMA, installation_identity=installation['identity'], sequence=1,
        state='NATIVE_ACTIVATED', incident_id=None, active_reservation_id=request['identity'],
        active_reservation_sha256=sha256(phase_raw).hexdigest(), previous_head_sha256='0'*64,
        recorded_at=now.isoformat())
    checks.check()
    if restore._aware_utc(selection['valid_until']) < datetime.now(UTC): _native_deny()
    return dict(disposition='PREPARED_PENDING_EXACT_ADMISSION_REVIEW', installation=installation,
        attempt=attempt, phase=phase, head=head)


def _native_setup_proposal(request, checks, now):
    """Read-only proposal for the explicit, non-starting native setup route.

    The native parent retains actual exclusion. Integrity bindings do not
    authenticate the separately required operator/owner decisions.
    """
    from kronos.common import release_admission as admission
    from kronos.common import failed_successor_restore as restore
    details=request['details']
    if type(details) is dict and details.get('operation')=='ACTIVATE_SELECTION':
        return _native_activation_proposal(request,checks,now)
    if (request['action']!='setup-prepare' or type(details) is not dict
            or set(details)!={'operation','operator_order','input'}
            or details['operation'] not in {'PLACE_ENROLLMENT','PRESERVE_STALE_CONTROL'}
            or admission.PERSISTENT_ANCHOR_BINDING is None
            or restore.INITIALIZATION_DISPOSITION is not None or ORDINARY_RESTART_POLICY is not None):_native_deny()
    operation=details['operation'];stem=admission.SETUP_OPERATIONS[operation]
    if request['identity']!='setup-'+stem:_native_deny()
    if operation=='PLACE_ENROLLMENT':
        installation=admission.preview_enrollment(admission.APPROVED_BINDING,details['input'],checks=checks)
    else:installation=_native_installation(request['repository'],request['bundle'],request['anchor'])
    if any(installation[k]!=request[r] for k,r in (
            ('repository_path','repository'),('bundle_path','bundle'),('anchor_path','anchor'))):_native_deny()
    parent=_native_parent(checks,request['repository'],request['bundle'])
    selected,_=_native_selection(request['selected'],checks,mode='ORDINARY',
        repository=request['repository'],bundle=request['bundle'],anchor=request['anchor'],now=now)
    if selected['installation']!=installation:_native_deny()
    order,order_raw=_native_reference(details['operator_order'])
    if (order_raw!=_canonical(order) or set(order)!={
            'schema','identity','operation','installation_identity','binding_sha256','selection',
            'input','valid_from','valid_until','decisions'}
            or order['schema']!=admission.SETUP_ORDER_SCHEMA or order['identity']!=details['operator_order']['identity']
            or order['operation']!=operation or order['installation_identity']!=installation['identity']
            or order['binding_sha256']!=sha256(admission.PERSISTENT_ANCHOR_BINDING).hexdigest()
            or order['selection']!=request['selected'] or order['input']!=details['input']
            or order['decisions']!=selected['decisions']
            or not restore._aware_utc(order['valid_from'])<=now<=restore._aware_utc(order['valid_until'])):_native_deny()
    anchor=Path(request['anchor']);root=anchor/'failed-successor-restore-v1'
    if os.path.lexists(root):_native_deny()
    preserved=None;source=None
    if operation=='PLACE_ENROLLMENT':
        if os.path.lexists(anchor/admission.SETUP_DIRECTORY):_native_deny()
        source=admission._private_reference(details['input'])
        destination=json.loads(admission.PERSISTENT_ANCHOR_BINDING)['enrollment']['path']
    else:
        prior=admission.setup_preparation_inputs(installation,checks)
        if len(prior)!=1 or prior[0]['document']['operation']!='PLACE_ENROLLMENT':_native_deny()
        if details['input']['path']!=str(anchor/'browser-backend-v1.control'):_native_deny()
        source=admission._private_reference(details['input'])
        # Parse only to require actual PID absence. Never authenticate with or
        # transmit the original token to a service.
        match=re.fullmatch(rb'KRONOS_BROWSER_BACKEND_CONTROL_V1\n([1-9][0-9]*)\n[0-9a-f]{64}\n',source)
        if match is None or not 2<=int(match[1])<=2147483647:_native_deny()
        try:os.kill(int(match[1]),0)
        except ProcessLookupError:pass
        else:_native_deny()
        destination=str(anchor/admission.SETUP_DIRECTORY/'stale-control.original')
        preserved=dict(identity='setup-preserved-stale-control',path=destination,
            bytes=len(source),sha256=sha256(source).hexdigest())
    attempt=dict(schema=admission.SETUP_ATTEMPT_SCHEMA,identity=request['identity'],operation=operation,
        installation_identity=installation['identity'],binding_sha256=sha256(admission.PERSISTENT_ANCHOR_BINDING).hexdigest(),
        order=details['operator_order'],input=details['input'],preserved=preserved,parent=parent,
        timing=dict(boot_session=admission.kernel_boot_identity(),clock='CLOCK_MONOTONIC',
            started_ns=admission.monotonic_ns(),deadline_ns=checks.attempt_deadline_ns),original_outcome='UNPROVED')
    checks.check();checks.budget.check()
    final=datetime.now(UTC)
    if final<now or final>min(restore._aware_utc(order['valid_until']),restore._aware_utc(selected['valid_until'])):_native_deny()
    return dict(disposition='PREPARATION_ONLY_PENDING_EXACT_REVIEW',installation=installation,
        attempt=attempt,destination=destination)


def native_validation_result(request):
    """Closed read-only stdin interface used by the actual native executable.

    Selection and decision hashes are integrity bindings under the supervised
    operator procedure. This function neither authenticates a human nor writes
    an admission head, reservation, cleanup acknowledgement or child claim.
    """
    from kronos.common import failed_successor_restore as restore
    required = {'action', 'repository', 'bundle', 'anchor', 'parent_pid', 'parent_birth',
                'mode', 'selected', 'identity', 'details', 'attempt_deadline_ns'}
    if type(request) is not dict or set(request) != required:
        _native_deny()
    if request['mode'] not in {'CONTROLLED_INSTALLATION_SETUP', 'ADMISSION_HEAD_INITIALIZATION', 'ORDINARY', 'LEGACY_BOOTSTRAP', 'GOVERNED_REPLACEMENT',
                               'FAILED_ACTIVE_RECOVERY_REPLACEMENT', 'ORDINARY_STOP', RESTORATION_MODE}:
        _native_deny()
    checks = _NativeReadOnlyChecks(request['parent_pid'], request['parent_birth'])
    if (type(request['attempt_deadline_ns']) is not int
            or request['attempt_deadline_ns'] < checks.budget.deadline_ns): _native_deny()
    # The helper has its existing shorter execution ceiling. The parent's
    # original absolute attempt deadline is carried separately, never renewed.
    checks.attempt_deadline_ns = request['attempt_deadline_ns']
    now = datetime.now(UTC)
    from kronos.common import release_admission as admission
    pair = dict(ordinary_policy_sha256=(sha256(ORDINARY_RESTART_POLICY).hexdigest() if ORDINARY_RESTART_POLICY is not None else None),persistent_binding_sha256=(sha256(admission.PERSISTENT_ANCHOR_BINDING).hexdigest()
        if admission.PERSISTENT_ANCHOR_BINDING is not None else None),
        initialization_disposition_sha256=(sha256(restore.INITIALIZATION_DISPOSITION).hexdigest()
            if restore.INITIALIZATION_DISPOSITION is not None else None),
        boot_session=admission.kernel_boot_identity())
    if request['mode']=='CONTROLLED_INSTALLATION_SETUP':
        result=_native_setup_proposal(request,checks,now)
        result.update(pair)
        checks.check();checks.budget.check()
        return result
    installation = _native_installation(request['repository'], request['bundle'], request['anchor'])
    parent = _native_parent(checks, request['repository'], request['bundle'])
    if request['mode'] == 'ADMISSION_HEAD_INITIALIZATION':
        if request['action'] not in {'initialization-prepare','initialization-recheck'}: _native_deny()
        admission.setup_preparation_inputs(installation,checks)
        result = _native_initialization_proposal(request, checks, installation, parent, now)
        result.update(pair)
        checks.check()
        checks.budget.check()
        return result
    root, head, head_raw, current, current_raw = _native_head(installation, checks=checks)
    disposition_digest = restore._initialization_admission(root, installation, checks=checks)
    pair['initialization_disposition_sha256'] = disposition_digest
    if restore._aware_utc(head['recorded_at']) > now:
        _native_deny()
    head_reference = dict(identity='head-' + str(head['sequence']), path=str(root / 'admission-head.json'),
                          bytes=len(head_raw), sha256=sha256(head_raw).hexdigest())
    previous = dict(identity=head['active_reservation_id'], path=str(root / (head['active_reservation_id'] + '.json')),
                    bytes=len(current_raw), sha256=sha256(current_raw).hexdigest())
    if request['action'] == 'gate':
        if request['mode'] == RESTORATION_MODE:
            allowed = head['state'] == 'INCIDENT_OPEN'
        elif request['mode']=='ORDINARY_STOP':
            allowed = head['state']=='READY_COMPLETE'
        elif request['mode']=='ORDINARY':
            allowed = head['state'] in {'NATIVE_ACTIVATED','READY_COMPLETE','ORDINARY_ACTIVATED','ORDINARY_STOP_INTENT'}
        else:
            allowed = head['state'] in {'NATIVE_ACTIVATED', 'READY_COMPLETE'}
        if not allowed:
            _native_deny()
        checks.check()
        return dict(installation=installation, parent=parent, head=head_reference,
                    phase=head['state'], current=current,
                    **pair)
    selection, selected_raw = _native_selection(request['selected'], checks,
        mode=('ORDINARY' if request['mode']=='ORDINARY_STOP' else request['mode']), repository=request['repository'], bundle=request['bundle'],
        anchor=request['anchor'], now=now)
    if request['action']=='ordinary-durability-plan':
        if (request['mode']!='ORDINARY' or head['state']!='ORIGINAL_RESERVED' or current['parent']!=parent):_native_deny()
        _check_operation_timing(current['details']['timing'],checks)
        plan=[];prior=current['details'].get('prior_stop')
        if prior is not None:
            _ordinary_current_check(prior,installation,checks)
            stop,_=_native_reference(prior)
            owner,terminal=_ordinary_stop_documents(stop,installation,checks)
            for suffix in ('owners','terminal'):
                path=root/(stop['identity']+'.'+suffix+'.json');_,raw=restore._current_document(path)
                plan.append(dict(identity=path.stem,path=str(path),bytes=len(raw),sha256=sha256(raw).hexdigest(),mode=0o600))
            ref=owner['payload']['state_manifest'];manifest,_=_native_reference(ref)
            plan.append(dict(ref,mode=0o600))
            for row in manifest['files']:plan.append(dict(identity='retained-owner-state',**row))
        chunks=[]
        activation=current['details'].get('prior_activation')
        if activation is not None:
            intent,package,state,_=_prepared_activation_inputs(activation,installation,checks,current=True)
            _prepared_activation_lineage(activation,installation,checks)
            _,_,active_ref=_ordinary_activation(installation,checks,now=now,selection=request['selected'])
            references=[activation,intent['order'],intent['input'],package['state'],state['assessment'],state['identities'],
                package['activation'],package['selection'],active_ref,request['selected']]
            order,_=_native_reference(intent['order'])
            references.extend(order['decisions'].values())
            seen=set()
            for ref in references:
                if ref['path'] not in seen:plan.append(dict(ref,mode=0o600));seen.add(ref['path'])
            chunks=[dict(ref,mode=0o600) for ref in state['chunks']]
        checks.check();checks.budget.check()
        return dict(durability_plan=plan,durability_chunks=chunks,head=head_reference,**pair)
    elif request['action']=='ordinary-stop-terminal':
        if (request['mode']!='ORDINARY_STOP' or head['state']!='ORDINARY_STOP_INTENT'
                or current['parent']!=parent or current['identity']!=request['identity']):_native_deny()
        _ordinary_activation(installation,checks,now=now,selection=request['selected'])
        _check_operation_timing(current['details']['timing'],checks)
        if not _native_observed_absent(current['predecessor']):_native_deny()
        owner,owner_raw=restore._current_document(root/(current['identity']+'.owners.json'))
        _ordinary_validate_owners(owner,current)
        terminal=dict(schema='KRONOS_ORDINARY_STOP_TERMINAL_V1',stop_identity=current['identity'],
            installation_identity=installation['identity'],child=current['predecessor'],
            timing=current['details']['timing'],payload=dict(terminal_observed=True,
                listener_absent=True,validation_helpers='TERMINAL',observed_ns=admission.monotonic_ns(),
                owners_sha256=sha256(owner_raw).hexdigest()))
        checks.check();checks.budget.check()
        return dict(terminal=terminal,**pair)
    elif request['action']=='ordinary-stop-reserve':
        if request['mode']!='ORDINARY_STOP' or head['state']!='READY_COMPLETE': _native_deny()
        _ordinary_activation(installation,checks,now=now,selection=request['selected'])
        child=current['details']['child'];restore._process(child)
        if (_observe_process(child['pid'])['kernel_birth']!=child['kernel_birth']
                or request['details']!={'generation':request['details'].get('generation')}
                or not _hex(request['details']['generation'])):_native_deny()
        record=_native_phase(request['identity'],'ORDINARY_STOP_INTENT',original=request['identity'],
            installation=installation,parent=parent,selected=request['selected'],predecessor=child,
            previous=previous,details=dict(generation=request['details']['generation'],timing=_operation_timing(checks)),now=now)
        result=dict(phase=record['phase'],identity=record['identity'],incident_id=None,
            record=record,head=head_reference,installation=installation,parent=parent)
    elif request['action'] == 'original-reserve':
        if (head['state'] not in {'NATIVE_ACTIVATED','READY_COMPLETE','ORDINARY_ACTIVATED','ORDINARY_STOP_INTENT'}
                or request['mode'] in {RESTORATION_MODE,'ORDINARY_STOP'} or not restore._identity(request['identity'])
                or request['details'] != {'predecessor': request['details'].get('predecessor')}):
            _native_deny()
        ordinary_details = {}
        if request['mode']=='ORDINARY':
            _ordinary_activation(installation,checks,now=now,selection=request['selected'])
            if head['state']=='ORDINARY_STOP_INTENT':
                _ordinary_stop_documents(current,installation,checks)
                ordinary_details['prior_stop']=previous
            elif head['state']!='ORDINARY_ACTIVATED':_native_deny()
            elif 'setup_attempt' in current['details']:
                ordinary_details['prior_activation']=current['details']['setup_attempt']
                _prepared_activation_inputs(ordinary_details['prior_activation'],installation,checks)
            ordinary_details['timing']=_operation_timing(checks)
        predecessor = request['details']['predecessor']
        if (head['state']=='NATIVE_ACTIVATED' and current.get('details',{}).get('enrolled_predecessor') is not None
                and (request['mode']!='GOVERNED_REPLACEMENT' or predecessor is None)):_native_deny()
        if predecessor is None and current.get('details', {}).get('child') is not None:
            prior_child = restore._process(current['details']['child'])
            if not _native_observed_absent(prior_child): _native_deny()
        if predecessor is not None:
            if (type(predecessor) is not dict or set(predecessor) != {'pid','kernel_birth'}
                    or _observe_process(predecessor['pid'])['kernel_birth'] != predecessor['kernel_birth']): _native_deny()
            known = current.get('details', {}).get('child')
            if known is None and head['state'] == 'NATIVE_ACTIVATED' and request['mode'] == 'GOVERNED_REPLACEMENT':
                enrolled = current.get('details', {}).get('enrolled_predecessor')
                if enrolled is not None:
                    known = _native_initialization_enrollment(enrolled['evidence'], checks,installation=installation)
                    if known != enrolled['process']: _native_deny()
            if known is not None:
                restore._process(known)
                if {key:known[key] for key in predecessor} != predecessor: _native_deny()
                predecessor = known
            elif request['mode'] == 'LEGACY_BOOTSTRAP':
                # Legacy processes predate StartupEvidence. Observe their actual
                # kernel identity without inventing a loaded-source/runtime ID;
                # this branch can never supply an eligible V2 restoration.
                predecessor = dict(predecessor,revision=None,runtime_identity=None)
            else: _native_deny()
        record = _native_phase(request['identity'], 'ORIGINAL_RESERVED',
            original=request['identity'], installation=installation, parent=parent,
            selected=request['selected'], predecessor=predecessor, previous=previous,
            details=dict(mode=request['mode'], target=selection['target'],
                operational_order=selection['operational_order'], decisions=selection['decisions'],**ordinary_details), now=now)
        result = dict(phase='ORIGINAL_RESERVED', identity=record['identity'], incident_id=None,
                      record=record, head=head_reference, installation=installation, parent=parent)
    elif request['action'] == 'original-advance':
        record = _native_advance(request, current, head, previous, installation, parent, now, checks)
        result = dict(phase=record['phase'], identity=record['identity'], incident_id=None,
                      record=record, head=head_reference, installation=installation, parent=parent)
    elif request['action'] == 'restoration-reserve':
        record = _native_restoration(selection, current, head, installation, parent, root, now, checks)
        result = dict(phase='RESTORATION_RESERVED', identity=record['reservation_id'],
            incident_id=record['incident_id'], record=record, head=head_reference,
            installation=installation, parent=parent, selection=selection)
    elif request['action'] in {'child-ready', 'child-exited'}:
        record, documents = _native_terminal(request,current,head,previous,installation,
            parent,now,root,checks,selection)
        result = dict(phase=record['phase'],identity=record['identity'],
            incident_id=(record['details']['incident']['identity'] if record['phase'] == 'INCIDENT_OPEN'
                         else head['incident_id']),record=record,documents=documents,
            head=head_reference,installation=installation,parent=parent)
    else:
        _native_deny()
    result['original_attempt_id'] = record.get('original_attempt_id', current.get('original_attempt_id'))
    result.update(pair)
    result['initialization_disposition_sha256'] = disposition_digest
    # Late reads/time/budget can invalidate a proposal. They never write a head
    # or authorize a later invocation to select a different record implicitly.
    if restore._aware_utc(selection['valid_until']) < datetime.now(UTC):
        _native_deny()
    checks.check()
    checks.budget.check()
    return result


def native_validation_stdio():
    import sys
    try:
        raw = sys.stdin.buffer.read(65537)
        if not 1 <= len(raw) <= 65536:
            _native_deny()
        request = json.loads(raw)
        if raw != _canonical(request):
            _native_deny()
        result = native_validation_result(request)
        sys.stdout.buffer.write(_canonical(result))
        sys.stdout.buffer.flush()
    except (BootstrapError, ValueError, TypeError, KeyError, AttributeError, OSError, OverflowError):
        raise SystemExit(78) from None
    finally:
        from kronos.common.release_admission import validation_unresolved
        # The actual nested-validation owner keeps uncertainty sticky. Even a
        # caught error or an escaping CalledProcessError cannot turn the Python
        # entry's exit into clearance for its possible validator descendants.
        if validation_unresolved():
            raise SystemExit(79) from None


class NativeStartupFacts:
    """Exclusive child observations for one native-selected attempt.

    This is not a head writer, cleanup owner or replacement startup context.
    Unknown construction/continuity/READY facts are retained as unknown.
    """
    def __init__(self, environment, *, custody, evidence, capture):
        from kronos.common import failed_successor_restore as restore
        from kronos.common import release_admission as admission
        from kronos.intraday.runtime_identity import StartupCapture, StartupEvidence
        if (type(custody) is not admission.AdmissionCustody
                or type(custody.budget) is not admission.ValidationBudget
                or type(evidence) is not StartupEvidence or not isinstance(capture, StartupCapture)
                or capture._finished is not evidence or evidence.process_id != os.getpid()
                or evidence.source_state != 'CLEAN_COMMIT'
                or evidence.load_verification != 'PINNED_STARTUP_IMPORTS'):
            _native_deny()
        self.custody, self.budget = custody, custody.budget
        self.deadline = self.budget.deadline_ns
        custody.check()
        self.reference = _native_selected_reference(environment, NATIVE_ATTEMPT_ENV)
        self.record, _ = _native_reference(self.reference)
        self.root = Path(self.reference['path']).parent
        self.identifier = self.reference['identity']
        self.parent = self.record['parent']
        self.child = dict(pid=os.getpid(), kernel_birth=_observe_process(os.getpid())['kernel_birth'],
            runtime_identity=sha256(evidence.evidence_identity.encode()).hexdigest(),
            revision=evidence.source_revision)
        if self.record.get('schema') == restore.RESERVATION_SCHEMA:
            selection = _restoration_selection(environment)
            permit, _ = restore._document(selection.permit_path, selection.permit_bytes, selection.permit_sha256)
            self.installation = restore._installation(permit['installation'])
            target = restore._target(permit['restoration_target'])
            incident, _ = _native_reference(permit['incident'])
            self.original = incident['original_attempt_id']
            expected_state = 'RESTORATION_RESERVED'
        elif (self.record.get('schema') == NATIVE_PHASE_SCHEMA
              and self.record.get('phase') == 'CHILD_START_RESERVED'):
            self.installation = restore._installation(self.record['installation'])
            target = restore._target(self.record['details']['target'])
            self.original = self.record['original_attempt_id']
            expected_state = 'CHILD_START_RESERVED'
        else:
            _native_deny()
        _, head, head_raw, _, _ = _native_head(self.installation, checks=custody)
        identified, _ = restore._current_document(self.root / (self.identifier + '.identified.json'))
        if (head['state'] != expected_state
                or head['active_reservation_id'] != self.identifier
                or head['active_reservation_sha256'] != self.reference['sha256']
                or environment.get('KRONOS_NATIVE_HEAD_SHA256') != sha256(head_raw).hexdigest()
                or self.root != Path(self.installation['anchor_path']) / 'failed-successor-restore-v1'
                or self.parent['pid'] != os.getppid() or self.parent['pid'] != custody.parent
                or self.parent['kernel_birth'] != _observe_process(os.getppid())['kernel_birth']
                or identified != dict(schema='KRONOS_NATIVE_CHILD_IDENTIFIED_V1',
                    selected=self.reference, parent=self.parent,
                    child=dict(pid=self.child['pid'], kernel_birth=self.child['kernel_birth']))
                or target['revision'] != evidence.source_revision
                or target['pinned_capture_sha256'] != evidence.source_snapshot_digest):
            _native_deny()
        self.head_sha256 = sha256(head_raw).hexdigest()
        self.completion_entered = False
        self.ready_observed = False
        self.completion_returned = False
        self.activation = []
        self.startup_success_published = False
        self.composed = None
        self.context = None
        self.publish('capture', dict(startup_evidence=json.loads(json.dumps(asdict(evidence),
            default=lambda value: value.isoformat())), original_capture_digest=evidence.source_snapshot_digest,
            loaded_modules=[list(row) for row in evidence.loaded_modules]))

    def check(self):
        from kronos.common import release_admission as admission
        import fcntl
        owner = self.custody
        self.budget.check()
        if (owner.budget is not self.budget or self.budget.deadline_ns != self.deadline
                or os.getppid() != self.parent['pid']
                or _observe_process(self.parent['pid'])['kernel_birth'] != self.parent['kernel_birth']
                or owner.parent_image(owner.parent) != admission.CANONICAL_PARENT):
            _native_deny()
        if not owner.released:
            # Cleanup deliberately makes AdmissionCustody.check() unavailable.
            # Observe the SAME descriptor using its existing OFD test; never
            # clear cleanup_started, reopen custody or unlock the description.
            metadata = os.fstat(owner.descriptor)
            if (not admission.validate_installation_anchor(self.installation,owner)
                    or not stat.S_ISDIR(metadata.st_mode) or os.get_inheritable(owner.descriptor)):
                _native_deny()
            # AnchorBinding is a value type in the pinned module; the adopted
            # object's binding belongs to the byte-verified bootstrap module.
            # Copy only the original binding values for the independent probe.
            # The custody object and its original descriptor remain untouched.
            probe = admission.open_anchor(admission.AnchorBinding(owner.binding.path,
                owner.binding.device,owner.binding.inode,owner.binding.owner))
            try:
                fcntl.flock(owner.descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                try: fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError: pass
                else: _native_deny()
            finally: os.close(probe)
        # After actual close-only release, the canonical parent still holds its
        # original description. Child fact writes acquire no replacement lock.
        self.budget.check()

    def publish(self, phase, payload):
        from kronos.common import failed_successor_restore as restore
        self.check()
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,39}', phase): _native_deny()
        value = dict(schema='KRONOS_NATIVE_CHILD_FACT_V1', selected=self.reference,
            original_attempt_id=self.original, parent=self.parent, child=self.child,
            deadline_ns=self.deadline, phase=phase, payload=payload, recorded_at=datetime.now(UTC).isoformat())
        raw = _canonical(value)
        if len(raw) > 8 * 1024 * 1024: _native_deny()
        restore._secure_parent(self.root)
        path = self.root / (self.identifier + '.' + phase + '.json')
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        with os.fdopen(fd, 'wb') as handle:
            handle.write(raw);handle.flush();os.fsync(handle.fileno())
        directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try: os.fsync(directory)
        finally: os.close(directory)
        metadata = path.stat(follow_symlinks=False)
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600): _native_deny()
        _, observed, _ = _read_manifest(path, self, final_lf=False)
        if observed != raw: _native_deny()
        self.check()
        return dict(identity=self.identifier + '.' + phase, path=str(path), bytes=len(raw), sha256=sha256(raw).hexdigest())

    def consumed(self, context, maintenance_root):
        from kronos.common.maintenance import DrainStartupContext
        from kronos.common.failed_successor_restore import RestorationStartupContext
        self.context = context
        if type(context) is DrainStartupContext:
            original_v2 = {}
            for key, name in (('handoff', context.generation + '.json'),
                              ('consumption', context.generation + '.consumed.json')):
                path = Path(maintenance_root) / name
                raw = path.read_bytes()
                original_v2[key] = dict(identity=context.generation + ('.consumed' if key == 'consumption' else ''),
                    path=str(path), bytes=len(raw), sha256=sha256(raw).hexdigest())
        elif type(context) is RestorationStartupContext:
            original_v2 = dict(handoff=dict(identity=context.original_v2_handoff_identity,
                sha256=context.original_v2_handoff_sha256), consumption=dict(
                identity=context.original_v2_consumption_identity, sha256=context.original_v2_consumption_sha256))
        else: original_v2 = None
        maintenance_identity = (context.maintenance_identity if type(context) is RestorationStartupContext
            else context.generation if type(context) is DrainStartupContext else context or self.child['runtime_identity'])
        checkpoint = (context.notification_checkpoint() if type(context) in
            {DrainStartupContext, RestorationStartupContext} else None)
        self.publish('consumed', dict(protocol=type(context).__name__, original_v2=original_v2,
            maintenance_identity=maintenance_identity, notification_checkpoint=checkpoint))

    def composition_returned(self, server, runtime, wo17, product_routes, scopes):
        if self.composed is not None or server._startup_fully_composed is not True: _native_deny()
        self.composed = (server, runtime, wo17, product_routes, tuple(scopes))

    def certify_settled(self):
        owner_results, declared, files = _current_owner_state(self.composed,self)
        owner_reference = self.publish('settled-owners',owner_results)
        state_reference = self.publish('settled-state-files', dict(scopes=declared, files=files, owner_results=owner_reference))
        return dict(state_manifest=state_reference, owner_results=owner_reference,
                    notification_checkpoint=owner_results['notification_checkpoint'])

    def completion_intent(self):
        self.completion_entered = True
        self.publish('completion-entered', dict(entered=True))

    def completion_outcome(self, server, *, returned):
        self.completion_returned = returned
        governance = server.connection_governance
        receipt = governance.store.root / 'maintenance' / (self.child['runtime_identity'] + '-startup.json')
        raw = receipt.read_bytes() if receipt.is_file() and not receipt.is_symlink() else None
        # Missing receipt never becomes never-READY evidence.
        self.ready_observed = governance.startup_state == 'READY' or raw is not None
        self.publish('completion-outcome', dict(returned=returned, state=governance.startup_state,
            ready_observed=self.ready_observed, receipt=(None if raw is None else dict(
                path=str(receipt), bytes=len(raw), sha256=sha256(raw).hexdigest()))))

    def boundary(self, phase, *, outcome):
        if phase not in {'ready-release', 'ux10', 'wo13', 'k5'} or outcome not in {'intent', 'returned'}:
            _native_deny()
        if outcome == 'returned': self.activation.append(phase)
        self.publish(phase + '-' + outcome, dict(outcome=outcome,
            custody_released=self.custody.released, cleanup_started=self.custody.cleanup_started))

    def cleanup_observed(self, cleanup, *, complete, final_owner_proof, helpers_unresolved):
        snapshot = cleanup.snapshot()
        ready_evidence = dict(ready_or_receipt=self.ready_observed,receipt_proven_absent=False)
        attestation = None
        if self.composed is not None:
            governance = self.composed[0].connection_governance
            path = governance.store.root / 'maintenance' / (self.child['runtime_identity'] + '-startup.json')
            present = os.path.lexists(path)
            ready_evidence = dict(ready_or_receipt=(self.ready_observed or present or governance.startup_state == 'READY'),
                receipt_proven_absent=(not self.completion_entered and not present
                    and governance.startup_state not in {'READY'}))
            if complete and final_owner_proof:
                attestation = self.composed[0]._maintenance_drain_attestation()
        settled = None
        if (complete and final_owner_proof and not helpers_unresolved and not self.completion_entered
                and not self.ready_observed and self.composed is not None):
            try: settled = self.certify_settled()
            except (AttributeError, ValueError, TypeError, KeyError, OSError) as error:
                # No owner is recreated and no absence becomes continuity.
                self.publish('continuity-unavailable', dict(state='UNKNOWN',error=type(error).__name__,reason=str(error)))
        self.publish('cleanup-observed', dict(ledger=snapshot, complete=complete,
            final_owner_proof=final_owner_proof, helpers_unresolved=helpers_unresolved,
            final_owner_attestation=attestation,
            completion_entered=self.completion_entered, ready_observed=self.ready_observed,
            ready_evidence=ready_evidence,
            construction_only_absence_not_continuity=True,
            errors=[dict(owner=name, error=type(error).__name__) for name, error in cleanup.errors],
            settled_continuity='UNKNOWN' if settled is None else 'VALIDATED_CURRENT', settled=settled))

    def cleanup_acknowledged(self):
        self.publish('cleanup-acknowledged', dict(cleanup_started=self.custody.cleanup_started,
            cleanup_complete=self.custody.cleanup_complete, custody_released=self.custody.released))

    def startup_success(self, server):
        if (not self.completion_returned or not self.ready_observed
                or self.activation != ['ready-release', 'ux10', 'wo13', 'k5']
                or not self.custody.released or self.custody.cleanup_started
                or server.connection_governance.startup_state != 'READY'):
            _native_deny()
        self.publish('startup-success', dict(ready=True, custody_released=True,
            activation=list(self.activation), server_port=server.server_port))
        self.startup_success_published = True



def _current_owner_state(composed,checks):
    from kronos.browser.runtime_state import _swing_restoration_failure
    from kronos.browser.theta_routes import ThetaBrowserRoutes
    server, runtime, wo17_reader, product_routes, scopes = composed
    swing = server.startup_restoration_outcomes()
    shadow = runtime.discovery_v2_operation.live_shadow.status()
    historical = (shadow.get('historical_restoration') == 'KRONOS-WO06H-HISTORICAL-RESTORATION/1.0.0'
        and shadow.get('acceptance_disposition') == 'HISTORICAL_ACCEPTANCE_EXPIRED'
        and shadow.get('historical_evidence') == 'READABLE' and shadow.get('collection_authority') == 'EXPIRED'
        and shadow.get('enabled') is False and shadow['runtime_accepted'] is False)
    wo17 = wo17_reader()
    if (_swing_restoration_failure(swing) or shadow['failure']
            or (shadow['window'] is not None and not shadow['runtime_accepted'] and not historical)
            or runtime.lifecycle_application.last_failure is not None
            or wo17['restoration_state'] not in {'LOADED', 'NOT_YET_RUN'}
            or wo17['failure_stage'] is not None or wo17['failure_reason'] is not None
            or (wo17['restoration_state'] == 'NOT_YET_RUN' and wo17['current_positions'] != [])
            or runtime.journal_application.last_failure is not None):
        _native_deny()
    journal = runtime.journal_application.snapshot()
    books = server.intraday_books.snapshot()
    theta = [route for route in product_routes._routes if type(route) is ThetaBrowserRoutes]
    if len(theta) != 1 or theta[0].sponsor_workflow is None: _native_deny()
    theta_status = theta[0].sponsor_workflow.restore_status()
    checkpoint = server.intraday_notifications.checkpoint(certify_durable=True)
    from kronos.common.maintenance import _valid_notification_checkpoint
    if not _valid_notification_checkpoint(checkpoint): _native_deny()
    owner_results = dict(validated_current=True,
        swing_outcomes=[list(row) for row in swing], shadow_failure=shadow['failure'],
        shadow_window=shadow['window'], shadow_runtime_accepted=shadow['runtime_accepted'],
        wo11_failure=runtime.lifecycle_application.last_failure,
        wo17_state=wo17['restoration_state'], wo17_failure_stage=wo17['failure_stage'],
        wo17_failure_reason=wo17['failure_reason'], journal_records=len(journal.records),
        books_records=len(books), theta_status_sha256=sha256(_canonical(theta_status)).hexdigest(),
        notification_checkpoint=checkpoint)
    paths = sorted({Path(path).resolve() for path in (*scopes, theta[0].sponsor_workflow.store.root)}, key=str)
    roots = [path for path in paths if not any(other != path and other in path.parents for other in paths)]
    declared = [dict(path=str(path),present=os.path.lexists(path)) for path in roots]
    files = _native_file_rows(declared, checks)
    return owner_results,declared,files


# ORDER 83552: disabled until a separately reviewed source/artifact activation.
ORDINARY_RESTART_POLICY = None
ORDINARY_ACTIVATION_SCHEMA = 'KRONOS_ORDINARY_ACTIVATION_V1'


def _ordinary_policy(installation, checks):
    from kronos.common import failed_successor_restore as restore
    from kronos.common import release_admission as admission
    raw = ORDINARY_RESTART_POLICY
    if type(raw) is not bytes: _native_deny()
    policy = _closed_json(raw, final_lf=False)
    fields = {'schema','scope','installation_identity','binding_sha256',
              'genesis_disposition_sha256','release_id','installed_selection_path'}
    if (set(policy) != fields or policy['schema'] != 'ORDINARY_SAME_RELEASE_V1'
            or policy['scope'] != 'ORDINARY_SAME_RELEASE_WITH_QUALIFIED_STOP'
            or policy['installation_identity'] != installation['identity']
            or not restore._identity(policy['release_id'])
            or type(admission.PERSISTENT_ANCHOR_BINDING) is not bytes
            or policy['binding_sha256'] != sha256(admission.PERSISTENT_ANCHOR_BINDING).hexdigest()
            or type(restore.INITIALIZATION_DISPOSITION) is not bytes
            or policy['genesis_disposition_sha256'] != sha256(restore.INITIALIZATION_DISPOSITION).hexdigest()
            or policy['installed_selection_path'] != str(Path(installation['anchor_path']) /
                'ordinary-start-v1/installed-selection.json')): _native_deny()
    checks.check();checks.budget.check()
    return policy, sha256(raw).hexdigest()


def _ordinary_activation(installation, checks, *, now, selection=None):
    """Fixed installed documents plus one immutable controlled activation head."""
    from kronos.common import failed_successor_restore as restore
    policy, digest = _ordinary_policy(installation,checks)
    path = Path(policy['installed_selection_path'])
    activation_path = path.with_name('activation.json')
    activation, raw = restore._current_document(activation_path)
    if (set(activation) != {'schema','identity','policy_sha256','installation_identity',
            'genesis_disposition_sha256','release_id','selection','decisions','activated_at'}
            or activation['schema'] != ORDINARY_ACTIVATION_SCHEMA
            or not restore._identity(activation['identity'])
            or activation['policy_sha256'] != digest
            or activation['installation_identity'] != installation['identity']
            or activation['genesis_disposition_sha256'] != policy['genesis_disposition_sha256']
            or activation['release_id'] != policy['release_id']
            or Path(activation['selection']['path']) != path
            or restore._aware_utc(activation['activated_at']) > now): _native_deny()
    reference = dict(identity=activation['identity'],path=str(activation_path),bytes=len(raw),sha256=sha256(raw).hexdigest())
    root, head, _, _, _ = _native_head(installation,checks=checks)
    matches = 0
    for sequence in range(1,head['sequence']+1):
        checks.check();checks.budget.check()
        prior, _ = restore._current_document(root / ('head-'+str(sequence)+'.json'))
        record, _ = restore._document(root / (prior['active_reservation_id']+'.json'),
            (root / (prior['active_reservation_id']+'.json')).stat().st_size,prior['active_reservation_sha256'])
        if prior['state'] == 'ORDINARY_ACTIVATED':
            details=record.get('details')
            if (type(details) is not dict or details.get('activation')!=reference
                    or set(details) not in ({'activation'},{'activation','setup_attempt'})
                    or record.get('installation') != installation): _native_deny()
            if 'setup_attempt' in details:
                _prepared_activation_inputs(details['setup_attempt'],installation,checks)
            matches += 1
    if matches != 1 or (selection is not None and selection != activation['selection']): _native_deny()
    selected, _ = _native_selection(activation['selection'],checks,mode='ORDINARY',
        repository=installation['repository_path'],bundle=installation['bundle_path'],
        anchor=installation['anchor_path'],now=now)
    if selected['installation'] != installation or selected['decisions'] != activation['decisions']: _native_deny()
    return selected, activation['selection'], reference


def _activation_report(reference,checks):
    """Exact already-reviewed report bytes; never recanonicalize history.

    Only this typed report path permits noncanonical presentation. Existing
    source/artifact readers retain their canonical default and checks.
    """
    from kronos.common import failed_successor_restore as restore
    if (type(reference) is not dict or set(reference)!={'identity','path','bytes','sha256'}
            or not restore._identity(reference['identity']) or type(reference['bytes']) is not int
            or not 1<=reference['bytes']<=8*1024*1024 or not _hex(reference['sha256'])):_native_deny()
    path,raw,value=_read_manifest(reference['path'],checks,final_lf=False,canonical=False)
    info=path.lstat()
    if (info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o600
            or len(raw)!=reference['bytes'] or sha256(raw).hexdigest()!=reference['sha256']):_native_deny()
    checks.check();checks.budget.check()
    return value


def _activation_state(reference,installation,checks,*,current):
    """G-bound accepted initial assessment, exact roster and current readback.

    No owner is constructed and no historical clean shutdown is inferred.
    The separate attributable G/activation decisions authorize use of this
    accepted assessment. Exact file correspondence preserves its value facts.
    """
    from kronos.common import failed_successor_restore as restore
    state,_=_native_reference(reference)
    fields={'schema','identity','installation_identity','scopes','chunks','assessment','identities'}
    if (type(state) is not dict or set(state)!=fields
            or state['schema']!='KRONOS_PREPARED_ACTIVATION_STATE_V1'
            or state['identity']!=reference['identity'] or state['installation_identity']!=installation['identity']
            or type(state['scopes']) is not list or not 1<=len(state['scopes'])<=128
            or type(state['chunks']) is not list or not 1<=len(state['chunks'])<=128):_native_deny()
    disposition=json.loads(restore.INITIALIZATION_DISPOSITION)
    evidence,_=_native_reference(disposition['evidence'])
    if sum(row==reference for row in evidence['observations']+evidence['subsequent_observations'])!=1:_native_deny()
    assessment=_activation_report(state['assessment'],checks)
    identities=_activation_report(state['identities'],checks)
    if (assessment.get('schema')!='KRONOS-83556-ELIGIBILITY-REGISTER-V1' or assessment.get('order')!=83556
            or assessment.get('recommendation')!='SAVED_STATE_SUPPORTS_BOUNDED_FIRST_START_PREPARATION; NO_DEMONSTRATED_SAVED_STATE_REPAIR_REQUIRED'
            or assessment.get('actual_startup_authority')!='NOT_GRANTED'
            or assessment.get('new_demonstrated_saved_state_blockers')!=[]
            or assessment.get('inconsistent_saved_state_findings')!=[]
            or assessment.get('all_saved_files_unchanged') is not True
            or identities.get('schema')!='KRONOS-83556-SAVED-RECORD-IDENTITIES-V1'
            or type(identities.get('records')) is not list or not 1<=len(identities['records'])<=16384
            or assessment.get('saved_record_files')!=len(identities['records'])):_native_deny()
    rows=[];seen_chunks=set()
    for ref in state['chunks']:
        if ref['path'] in seen_chunks:_native_deny()
        seen_chunks.add(ref['path']);chunk,_=_native_reference(ref)
        if (set(chunk)!={'schema','identity','files'} or chunk['schema']!='KRONOS_PREPARED_ACTIVATION_FILES_V1'
                or chunk['identity']!=ref['identity'] or type(chunk['files']) is not list
                or not 1<=len(chunk['files'])<=128):_native_deny()
        for row in chunk['files']:
            if (type(row) is not dict or set(row)!={'path','bytes','sha256','mode'}
                    or not Path(row['path']).is_absolute() or '..' in Path(row['path']).parts
                    or type(row['bytes']) is not int or not 0<=row['bytes']<=1024*1024*1024
                    or not _hex(row['sha256']) or type(row['mode']) is not int
                    or not 0<=row['mode']<=0o777):_native_deny()
            rows.append(row)
    if rows!=sorted(rows,key=lambda row:row['path']) or len({row['path'] for row in rows})!=len(rows):_native_deny()
    by_path={row['path']:row for row in rows};approved=set()
    for row in identities['records']:
        if (type(row) is not dict or set(row)!={'path','sha256','bytes','mode','unchanged','retained_object'}
                or row['unchanged'] is not True or type(row['mode']) is not str
                or re.fullmatch(r'0[0-7]{3}',row['mode']) is None or row['path'] in approved
                or by_path.get(row['path'])!=dict(path=row['path'],sha256=row['sha256'],bytes=row['bytes'],mode=int(row['mode'],8))):_native_deny()
        approved.add(row['path'])
    # Runtime journal/reservation changes must never be laundered into the
    # retained owner-state snapshot, nor can an empty/incomplete roster pass.
    anchor=Path(installation['anchor_path'])
    for scope in state['scopes']:
        path=Path(scope['path'])
        if path==anchor or path in anchor.parents or anchor in path.parents:_native_deny()
    if current and _native_file_rows(state['scopes'],checks)!=rows:_native_deny()
    checks.check();checks.budget.check()
    return state,rows


def _prepared_activation_inputs(reference,installation,checks,*,current=False):
    from kronos.common import release_admission as admission
    intent,_=_native_reference(reference)
    expected=Path(installation['anchor_path'])/admission.SETUP_DIRECTORY/'activation.intent.json'
    if (reference['path']!=str(expected) or reference['identity']!='setup-activation'
            or intent.get('schema')!=admission.SETUP_ATTEMPT_SCHEMA or intent.get('identity')!='setup-activation'
            or intent.get('operation')!='ACTIVATE_SELECTION' or intent.get('installation_identity')!=installation['identity']
            or intent.get('original_outcome')!='UNPROVED' or intent.get('preserved') is not None):_native_deny()
    _check_operation_timing(intent['timing'],checks,historical=True)
    package,_=_native_reference(intent['input'])
    if (set(package)!={'schema','identity','selection','activation','state'}
            or package['schema']!='KRONOS_PREPARED_ORDINARY_ACTIVATION_V1'
            or package['identity']!=intent['input']['identity']):_native_deny()
    state,rows=_activation_state(package['state'],installation,checks,current=current)
    order,_=_native_reference(intent['order'])
    if (order.get('input')!=intent['input'] or order.get('selection')!=package['selection']
            or order.get('operation')!='ACTIVATE_SELECTION' or order.get('installation_identity')!=installation['identity']
            or order.get('binding_sha256')!=sha256(admission.PERSISTENT_ANCHOR_BINDING).hexdigest()):_native_deny()
    if current:
        from kronos.common import release_admission as a
        if a.validation_unresolved():_native_deny()
        control=Path(installation['anchor_path'])/'browser-backend-v1.control'
        if os.path.lexists(control) or not _native_observed_absent(intent['parent']):_native_deny()
    return intent,package,state,rows


def _ordinary_activation_current_check(reference,installation,checks):
    intent,package,state,rows=_prepared_activation_inputs(reference,installation,checks,current=True)
    checks.check();checks.budget.check()
    return dict(original_activation=reference,original_outcome='NOT_RECLASSIFIED',
        current_state='VERIFIED_UNDER_NEW_ATTEMPT',files=len(rows))


def _prepared_activation_lineage(reference,installation,checks):
    """Complete immutable activation, not a timely-outcome or startup receipt."""
    from kronos.common import failed_successor_restore as restore
    intent,package,_,_=_prepared_activation_inputs(reference,installation,checks)
    policy,digest=_ordinary_policy(installation,checks)
    path=Path(policy['installed_selection_path']);activation_path=path.with_name('activation.json')
    activation,raw=restore._current_document(activation_path)
    supplied,supplied_raw=_native_reference(package['activation'])
    if (raw!=supplied_raw or activation!=supplied or set(activation)!={
            'schema','identity','policy_sha256','installation_identity','genesis_disposition_sha256',
            'release_id','selection','decisions','activated_at'}
            or activation['schema']!=ORDINARY_ACTIVATION_SCHEMA or activation['policy_sha256']!=digest
            or activation['installation_identity']!=installation['identity']
            or activation['genesis_disposition_sha256']!=policy['genesis_disposition_sha256']
            or activation['release_id']!=policy['release_id']
            or activation['selection']['path']!=str(path)):_native_deny()
    original,_=_native_reference(package['selection']);installed,installed_raw=_native_reference(activation['selection'])
    if (original!=installed or any(package['selection'][k]!=activation['selection'][k] for k in ('identity','bytes','sha256'))
            or sha256(installed_raw).hexdigest()!=activation['selection']['sha256']):_native_deny()
    actual=dict(identity=activation['identity'],path=str(activation_path),bytes=len(raw),sha256=sha256(raw).hexdigest())
    order,_=_native_reference(intent['order'])
    if (order.get('decisions')!=activation['decisions'] or installed.get('decisions')!=activation['decisions']
            or installed.get('installation')!=installation):_native_deny()
    root=Path(installation['anchor_path'])/'failed-successor-restore-v1'
    head,_=restore._current_document(root/'admission-head.json');matches=0
    if type(head.get('sequence')) is not int or not 2<=head['sequence']<=1000000000:_native_deny()
    for sequence in range(1,head['sequence']+1):
        checks.check();prior,_=restore._current_document(root/('head-'+str(sequence)+'.json'))
        if prior.get('state')!='ORDINARY_ACTIVATED':continue
        record,_=restore._document(root/(prior['active_reservation_id']+'.json'),
            (root/(prior['active_reservation_id']+'.json')).stat().st_size,prior['active_reservation_sha256'])
        if (record.get('details')!={'activation':actual,'setup_attempt':reference}
                or record.get('installation')!=installation or record.get('parent')!=intent['parent']
                or record.get('selection')!=activation['selection']):_native_deny()
        matches+=1
    if matches!=1:_native_deny()
    checks.check();checks.budget.check()
    return actual


def _native_activation_proposal(request,checks,now):
    from kronos.common import failed_successor_restore as restore
    from kronos.common import release_admission as admission
    details=request['details']
    if (set(details)!={'operation','operator_order','input'} or details['operation']!='ACTIVATE_SELECTION'
            or request['identity']!='setup-activation' or request['action'] not in {'setup-prepare','setup-verify-prepared'}):_native_deny()
    installation=_native_installation(request['repository'],request['bundle'],request['anchor'])
    parent=_native_parent(checks,request['repository'],request['bundle'])
    policy,policy_digest=_ordinary_policy(installation,checks)
    selected,selected_raw=_native_selection(request['selected'],checks,mode='ORDINARY',
        repository=request['repository'],bundle=request['bundle'],anchor=request['anchor'],now=now)
    order,order_raw=_native_reference(details['operator_order'])
    if (order_raw!=_canonical(order) or set(order)!={'schema','identity','operation','installation_identity',
            'binding_sha256','selection','input','valid_from','valid_until','decisions'}
            or order['schema']!=admission.SETUP_ORDER_SCHEMA or order['identity']!=details['operator_order']['identity']
            or order['operation']!='ACTIVATE_SELECTION' or order['installation_identity']!=installation['identity']
            or order['binding_sha256']!=sha256(admission.PERSISTENT_ANCHOR_BINDING).hexdigest()
            or order['selection']!=request['selected'] or order['input']!=details['input']
            or order['decisions']!=selected['decisions'] or selected['installation']!=installation
            or not restore._aware_utc(order['valid_from'])<=now<=restore._aware_utc(order['valid_until'])):_native_deny()
    package,_=_native_reference(details['input'])
    if (set(package)!={'schema','identity','selection','activation','state'}
            or package['schema']!='KRONOS_PREPARED_ORDINARY_ACTIVATION_V1'
            or package['identity']!=details['input']['identity'] or package['selection']!=request['selected']):_native_deny()
    activation,activation_raw=_native_reference(package['activation'])
    installed_ref=dict(request['selected'],path=policy['installed_selection_path'])
    if (set(activation)!={'schema','identity','policy_sha256','installation_identity','genesis_disposition_sha256',
            'release_id','selection','decisions','activated_at'} or activation['schema']!=ORDINARY_ACTIVATION_SCHEMA
            or activation['identity']!=package['activation']['identity'] or activation['policy_sha256']!=policy_digest
            or activation['installation_identity']!=installation['identity']
            or activation['genesis_disposition_sha256']!=policy['genesis_disposition_sha256']
            or activation['release_id']!=policy['release_id'] or activation['selection']!=installed_ref
            or activation['decisions']!=selected['decisions']
            or not restore._aware_utc(order['valid_from'])<=restore._aware_utc(activation['activated_at'])<=now):_native_deny()
    if request['action']=='setup-verify-prepared':
        path=Path(request['anchor'])/admission.SETUP_DIRECTORY/'activation.intent.json'
        intent,raw=restore._current_document(path)
        reference=dict(identity='setup-activation',path=str(path),bytes=len(raw),sha256=sha256(raw).hexdigest())
        if (intent.get('input')!=details['input'] or intent.get('order')!=details['operator_order']
                or intent.get('parent')!=parent):_native_deny()
        _check_operation_timing(intent['timing'],checks)
        # This entered publication is still nonadmitted. The real native
        # parent independently enforces G/current-head under its exact owned
        # intent before committing the phase. Never exempt ordinary readers.
        active,active_raw=restore._current_document(Path(policy['installed_selection_path']))
        placed,placed_raw=restore._current_document(Path(policy['installed_selection_path']).with_name('activation.json'))
        if active!=selected or active_raw!=selected_raw or placed!=activation or placed_raw!=activation_raw:_native_deny()
        _activation_state(package['state'],installation,checks,current=True)
        if admission.validation_unresolved():_native_deny()
        final=datetime.now(UTC)
        if final<now or final>min(restore._aware_utc(order['valid_until']),restore._aware_utc(selected['valid_until'])):_native_deny()
        checks.check();checks.budget.check()
        return dict(disposition='PREPARED_ACTIVATION_UNPROVED',installation=installation,
            intent_sha256=reference['sha256'])
    root,head,head_raw,current,current_raw=_native_head(installation,checks=checks)
    if (head['sequence']!=1 or head['state']!='NATIVE_ACTIVATED'
            or current['details'].get('enrolled_predecessor') is not None
            or os.path.lexists(Path(request['anchor'])/'ordinary-start-v1')):_native_deny()
    records=admission.setup_preparation_inputs(installation,checks)
    if not records or any(row['document']['operation']=='ACTIVATE_SELECTION' for row in records):_native_deny()
    _activation_state(package['state'],installation,checks,current=True)
    if admission.validation_unresolved() or os.path.lexists(Path(request['anchor'])/'browser-backend-v1.control'):_native_deny()
    intent=dict(schema=admission.SETUP_ATTEMPT_SCHEMA,identity='setup-activation',operation='ACTIVATE_SELECTION',
        installation_identity=installation['identity'],binding_sha256=sha256(admission.PERSISTENT_ANCHOR_BINDING).hexdigest(),
        order=details['operator_order'],input=details['input'],preserved=None,parent=parent,
        timing=_operation_timing(checks),original_outcome='UNPROVED')
    intent_raw=_canonical(intent);intent_ref=dict(identity='setup-activation',
        path=str(Path(request['anchor'])/admission.SETUP_DIRECTORY/'activation.intent.json'),
        bytes=len(intent_raw),sha256=sha256(intent_raw).hexdigest())
    activation_ref=dict(identity=activation['identity'],path=str(Path(policy['installed_selection_path']).with_name('activation.json')),
        bytes=len(activation_raw),sha256=sha256(activation_raw).hexdigest())
    previous=dict(identity=head['active_reservation_id'],path=str(root/(head['active_reservation_id']+'.json')),
        bytes=len(current_raw),sha256=sha256(current_raw).hexdigest())
    record=_native_phase('setup-activation.ordinary-activated','ORDINARY_ACTIVATED',original='setup-activation',
        installation=installation,parent=parent,selected=installed_ref,predecessor=None,previous=previous,
        details=dict(activation=activation_ref,setup_attempt=intent_ref),now=now)
    checks.check();checks.budget.check()
    final=datetime.now(UTC)
    if final<now or final>min(restore._aware_utc(order['valid_until']),restore._aware_utc(selected['valid_until'])):_native_deny()
    return dict(disposition='PREPARED_ACTIVATION_UNPROVED',installation=installation,intent=intent,
        installed_selection=selected,activation=activation,record=record,
        head=dict(identity='head-'+str(head['sequence']),path=str(root/'admission-head.json'),
            bytes=len(head_raw),sha256=sha256(head_raw).hexdigest()))


def _operation_timing(checks):
    from kronos.common import release_admission as admission
    return dict(boot_session=admission.kernel_boot_identity(),clock='CLOCK_MONOTONIC',
        started_ns=admission.monotonic_ns(),deadline_ns=getattr(checks,'attempt_deadline_ns',checks.budget.deadline_ns))


def _check_operation_timing(timing,checks,*,historical=False):
    from kronos.common import release_admission as admission
    if (type(timing) is not dict or set(timing) != {'boot_session','clock','started_ns','deadline_ns'}
            or timing['clock'] != 'CLOCK_MONOTONIC'
            or type(timing['started_ns']) is not int or type(timing['deadline_ns']) is not int
            or not 0 < timing['started_ns'] < timing['deadline_ns']): _native_deny()
    import uuid
    if str(uuid.UUID(timing['boot_session'])) != timing['boot_session']: _native_deny()
    if not historical:
        if (timing['boot_session'] != admission.kernel_boot_identity()
                or timing['deadline_ns'] != getattr(checks,'attempt_deadline_ns',checks.budget.deadline_ns)):
            _native_deny()
        checks.check();checks.budget.check()


def _ordinary_stop_documents(current,installation,checks):
    """Read COMPLETE independent producer facts. Never infer cleanup from exit."""
    from kronos.common import failed_successor_restore as restore
    root = Path(installation['anchor_path'])/'failed-successor-restore-v1'
    if current['phase'] != 'ORDINARY_STOP_INTENT': _native_deny()
    timing = current['details']['timing'];_check_operation_timing(timing,checks,historical=True)
    base = current['identity']
    owner, owner_raw = restore._current_document(root/(base+'.owners.json'))
    terminal, terminal_raw = restore._current_document(root/(base+'.terminal.json'))
    fields = {'schema','stop_identity','installation_identity','child','timing','payload'}
    if (set(owner) != fields or set(terminal) != fields
            or owner['schema'] != 'KRONOS_ORDINARY_STOP_OWNERS_V1'
            or terminal['schema'] != 'KRONOS_ORDINARY_STOP_TERMINAL_V1'
            or any(v['stop_identity'] != base or v['installation_identity'] != installation['identity']
                or v['child'] != current['predecessor'] or v['timing'] != timing for v in (owner,terminal))): _native_deny()
    from kronos.browser.server import _StartupCleanup
    from kronos.common.maintenance import _valid_drain
    _ordinary_validate_owners(owner,current)
    facts = owner['payload']
    if (Path(facts['state_manifest']['path']) != root/(base+'.state.json') or facts['state_manifest']['identity']!=base+'.state'):_native_deny()
    if (set(facts) != {'ledger','final_owner_proof','drain','control_removed','state_manifest','observed_ns'}
            or facts['final_owner_proof'] is not True or facts['control_removed'] is not True
            or set(facts['ledger']) != set(_StartupCleanup._names)
            or any(row['state'] not in {'NOT_CREATED','CREATED_AND_CLEANED'} for row in facts['ledger'].values())
            or not _valid_drain(facts['drain'])
            or not timing['started_ns'] <= facts['observed_ns'] < timing['deadline_ns']): _native_deny()
    end = terminal['payload']
    if (set(end) != {'terminal_observed','listener_absent','validation_helpers','observed_ns','owners_sha256'}
            or end['terminal_observed'] is not True or end['listener_absent'] is not True
            or end['validation_helpers'] != 'TERMINAL'
            or end['owners_sha256'] != sha256(owner_raw).hexdigest()
            or not facts['observed_ns'] <= end['observed_ns'] < timing['deadline_ns']): _native_deny()
    checks.check();checks.budget.check()
    return owner,terminal


def _ordinary_current_check(stop_reference,installation,checks):
    """One new reserved attempt, original deadline, prospective current facts."""
    from kronos.common import release_admission as admission
    current, _ = _native_reference(stop_reference)
    owners, terminal = _ordinary_stop_documents(current,installation,checks)
    if not _native_observed_absent(current['predecessor']) or not _native_observed_absent(current['parent']): _native_deny()
    control = Path(installation['anchor_path'])/'browser-backend-v1.control'
    if os.path.lexists(control): _native_deny()
    # The retained manifest is produced after actual owners close, not by an
    # operator summary or a generic empty-state assertion.
    manifest, _ = _native_reference(owners['payload']['state_manifest'])
    if (set(manifest) != {'schema','scopes','files','owner_results'}
            or manifest['schema'] != 'KRONOS_ORDINARY_STOP_STATE_V1'
            or _native_file_rows(manifest['scopes'],checks) != manifest['files']
            or manifest['owner_results'].get('validated_current') is not True): _native_deny()
    checks.check();checks.budget.check()
    return dict(original_stop=stop_reference,original_acknowledgement='NOT_RECLASSIFIED',
        current_state='VERIFIED_UNDER_NEW_ATTEMPT',boot_session=admission.kernel_boot_identity())


def ordinary_stop_context(server,generation,identifier):
    """Authenticate the actual canonical stop custodian against its durable head."""
    from kronos.common import release_admission as admission
    from kronos.common import failed_successor_restore as restore
    if not restore._identity(identifier) or not _hex(generation): _native_deny()
    root = server.restart_control.path.parent/'failed-successor-restore-v1'
    record, raw = restore._current_document(root/(identifier+'.json'))
    if (record.get('phase') != 'ORDINARY_STOP_INTENT' or record.get('identity') != identifier
            or record['details']['generation'] != generation
            or record['predecessor']['pid'] != os.getpid()
            or record['predecessor']['runtime_identity'] != server.connection_governance.process.runtime_identity
            or _observe_process(os.getpid())['kernel_birth'] != record['predecessor']['kernel_birth']
            or _observe_process(record['parent']['pid'])['kernel_birth'] != record['parent']['kernel_birth']
            or admission._parent_image(record['parent']['pid']) != admission.CANONICAL_PARENT): _native_deny()
    budget = admission.ValidationBudget(record['details']['timing']['deadline_ns'])
    class Checks:
        def check(self):
            self.budget.check()
            if _observe_process(record['parent']['pid'])['kernel_birth'] != record['parent']['kernel_birth']: _native_deny()
    checks=Checks();checks.budget=budget;checks.attempt_deadline_ns=budget.deadline_ns
    _check_operation_timing(record['details']['timing'],checks)
    _, head, _, _, _ = _native_head(record['installation'],checks=checks)
    if head['active_reservation_id'] != identifier or head['active_reservation_sha256'] != sha256(raw).hexdigest(): _native_deny()
    _ordinary_activation(record['installation'],checks,now=datetime.now(UTC),selection=record['selection'])
    return record,checks


def _ordinary_write(path,value,checks):
    """Exact exclusive publication, preserving partial/late bytes on failure."""
    from kronos.common import failed_successor_restore as restore
    checks.check();raw=_canonical(value);restore._secure_parent(path.parent)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    try:
        used=0
        while used<len(raw):
            checks.check();n=os.write(fd,raw[used:])
            if n<=0:raise OSError('ORDINARY_STOP_SHORT_WRITE')
            used+=n
        os.fsync(fd);checks.check()
    finally:os.close(fd)
    directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:os.fsync(directory)
    finally:os.close(directory)
    checks.check()
    _,retained=restore._current_document(path)
    if retained!=raw:_native_deny()
    checks.check()
    return dict(identity=path.stem,path=str(path),bytes=len(raw),sha256=sha256(raw).hexdigest())


def publish_ordinary_stop_owners(server,context):
    """Only the actual entry's completed ledger can supply this producer."""
    from kronos.common import release_admission as admission
    record,checks=context
    checks.check()
    cleanup=server._startup_cleanup
    if (cleanup.server is not server or not server._maintenance_final_owner_proof()
            or admission.validation_unresolved()):_native_deny()
    ledger={key:dict(value) for key,value in cleanup.snapshot().items()}
    if any(row['state'] not in {'NOT_CREATED','CREATED_AND_CLEANED'} for row in ledger.values()):_native_deny()
    if os.path.lexists(server.restart_control.path):_native_deny()
    # Preserve exact currently committed owner evidence. The actual server's
    # retained-state roster is captured before stop by the entry below.
    owner_results,scopes,files = _current_owner_state(server._ordinary_composition,checks)
    root=Path(record['installation']['anchor_path'])/'failed-successor-restore-v1'
    manifest=_ordinary_write(root/(record['identity']+'.state.json'),
        dict(schema='KRONOS_ORDINARY_STOP_STATE_V1',scopes=scopes,files=files,owner_results=owner_results),checks)
    value=dict(schema='KRONOS_ORDINARY_STOP_OWNERS_V1',stop_identity=record['identity'],
        installation_identity=record['installation_identity'],child=record['predecessor'],
        timing=record['details']['timing'],payload=dict(ledger=ledger,final_owner_proof=True,
            drain=server._maintenance_drain_attestation(),control_removed=True,
            state_manifest=manifest,observed_ns=admission.monotonic_ns()))
    return _ordinary_write(root/(record['identity']+'.owners.json'),value,checks)


def _ordinary_validate_owners(owner,current):
    from kronos.browser.server import _StartupCleanup
    from kronos.common.maintenance import _valid_drain
    if (set(owner)!={'schema','stop_identity','installation_identity','child','timing','payload'}
            or owner['schema']!='KRONOS_ORDINARY_STOP_OWNERS_V1'
            or owner['stop_identity']!=current['identity']
            or owner['installation_identity']!=current['installation_identity']
            or owner['child']!=current['predecessor'] or owner['timing']!=current['details']['timing']):_native_deny()
    p=owner['payload'];t=owner['timing']
    if (set(p)!={'ledger','final_owner_proof','drain','control_removed','state_manifest','observed_ns'}
            or p['final_owner_proof'] is not True or p['control_removed'] is not True
            or set(p['ledger'])!=set(_StartupCleanup._names)
            or any(x['state'] not in {'NOT_CREATED','CREATED_AND_CLEANED'} for x in p['ledger'].values())
            or any(p['ledger'][key]['state']!='CREATED_AND_CLEANED' for key in
                ('provider','intraday_runtime','application','control','server','coordinator','sponsor_work','listener','housekeeping','official_check'))
            or not _valid_drain(p['drain']) or not t['started_ns']<=p['observed_ns']<t['deadline_ns']):_native_deny()
