"""One-time, explicitly issued legacy migration; never an ordinary SPH handoff.

The coordinator owns a fresh migration proof. No Provider capability or legacy
shutdown token is placed in this contract. Production execution is separately gated.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, UTC
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import socket
import stat

from kronos.common.connection_governance import _bytes
from kronos.common.maintenance import HANDOFF_SECONDS

SCHEMA = 'KRONOS_LEGACY_BOOTSTRAP_V1'
LEGACY_REVISION = '0dd6a74d3da25e52d0bd82326a30647f5111adce'
ENV_ID = 'KRONOS_LEGACY_BOOTSTRAP_ID'
ENV_PROOF = 'KRONOS_LEGACY_BOOTSTRAP_PROOF'
SIDE_EFFECT = 'EXPECTED_LEGACY_BOOTSTRAP_NOTIFICATION_SIDE_EFFECT'
RISK = 'LEGACY_SHUTDOWN_SIDE_EFFECT_RISK'


class BootstrapError(ValueError):
    """Closed, non-secret diagnostic; no raw HTTP/credential exception."""


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


def consume_startup_context(root: Path, environment, *, revision, source_state,
                            repository, runtime_identity, now, **bootstrap_checks):
    """Only one authority protocol can enter composition; never fall back."""
    from kronos.common.maintenance import consume_handoff, _ENV
    legacy = any(k in environment for k in (ENV_ID, ENV_PROOF))
    mode = environment.pop('KRONOS_LAUNCH_MODE', None)
    if mode not in (None, 'LEGACY_BOOTSTRAP') or (mode == 'LEGACY_BOOTSTRAP' and not legacy):
        raise BootstrapError('BOOTSTRAP_MODE_CONTEXT_MISSING')
    if legacy and any(k in environment for k in _ENV):
        raise BootstrapError('BOOTSTRAP_MIXED_PROTOCOLS')
    if legacy:
        return consume_bootstrap(root / 'legacy-bootstrap-v1', environment,
            revision=revision, source_state=source_state, repository=repository,
            runtime_identity=runtime_identity, now=now, **bootstrap_checks)
    return consume_handoff(root / 'maintenance', environment,
        runtime_identity=runtime_identity, now=now)
