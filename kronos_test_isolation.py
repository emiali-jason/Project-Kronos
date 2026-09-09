"""Test-only bootstrap. Never imported by production composition."""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import socket
import errno
import subprocess
import sys

MARKER = 'KRONOS_TEST_ISOLATION_MANIFEST'
_STATE = None
_ORIGINAL_RESOLVE = Path.resolve
_ORIGINAL_HOME = Path.home
_ORIGINAL_POPEN = subprocess.Popen
_ORIGINAL_IS_ABSOLUTE = Path.is_absolute
_ORIGINAL_BIND = socket.socket.bind


class IsolationError(RuntimeError):
    pass


def _inside(path, root):
    return path == root or root in path.parents


def _canonical(path):
    return _ORIGINAL_RESOLVE(Path(path), strict=False)


def state():
    if _STATE is None:
        raise IsolationError('KRONOS_TEST_ISOLATION_REQUIRED')
    return _STATE


def check_path(path):
    candidate = _canonical(path)
    if any(_inside(candidate, Path(root)) for root in state()['protected']):
        raise IsolationError('KRONOS_TEST_PRODUCTION_PATH_FORBIDDEN')
    return candidate


def install(*, required=False):
    global _STATE
    if _STATE is not None:
        return _STATE
    marker = os.environ.get(MARKER)
    if not marker:
        if required:
            raise IsolationError('KRONOS_TEST_ISOLATION_REQUIRED: use tools/kronos_test.py')
        return None
    try:
        path = Path(marker)
        metadata = path.stat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o600:
            raise IsolationError('KRONOS_TEST_MANIFEST_INVALID')
        data = json.loads(path.read_bytes())
        root = _canonical(data['root'])
        if not root.name.startswith('kronos-test-') or _canonical(path.parent) != root:
            raise IsolationError('KRONOS_TEST_ROOT_INVALID')
        home, probe = _canonical(data['home']), _canonical(data['probe'])
        if not _inside(home, root) or not _inside(probe, root) or home == root:
            raise IsolationError('KRONOS_TEST_ROOT_INVALID')
        # The launcher creates a readable owned control file. Kernel policy
        # denies its data, but permits stat. Ordinary permissions cannot satisfy
        # this check: unguarded/spoofed pytest exits before Kronos imports.
        probe_stat = probe.stat()
        if not stat.S_ISREG(probe_stat.st_mode) or probe_stat.st_uid != os.getuid() or stat.S_IMODE(probe_stat.st_mode) != 0o600:
            raise IsolationError('KRONOS_TEST_PROBE_INVALID')
        try:
            probe.read_bytes()
        except PermissionError:
            pass
        else:
            raise IsolationError('KRONOS_TEST_KERNEL_PROTECTION_MISSING')
        with socket.socket() as client:
            try:
                client.connect(('127.0.0.1', data['blocked_test_port']))
            except PermissionError:
                pass
            else:
                raise IsolationError('KRONOS_TEST_NETWORK_PROTECTION_MISSING')
        if any(name == 'kronos' or name.startswith('kronos.') for name in sys.modules):
            raise IsolationError('KRONOS_TEST_BOOTSTRAP_TOO_LATE')
        _STATE = data
        _STATE['manifest'] = str(path)
        # No HOME reassignment. Bind Python defaults before application imports.
        Path.home = classmethod(lambda cls: cls(home))
        # Restrict real fixture sockets to the kernel's finite private port set.
        # Native children inherit that same outbound allowlist.
        def bind(sock, address):
            if sock.family == socket.AF_INET and address[1] == 0:
                for port in data['allowed_ports']:
                    try:
                        return _ORIGINAL_BIND(sock, (address[0], port))
                    except OSError as error:
                        if error.errno != errno.EADDRINUSE:
                            raise
                raise IsolationError('KRONOS_TEST_FIXTURE_PORTS_EXHAUSTED')
            return _ORIGINAL_BIND(sock, address)
        socket.socket.bind = bind
        def resolve(self, strict=False):
            result = _ORIGINAL_RESOLVE(self, strict=strict)
            check_path(result)
            return result
        Path.resolve = resolve
        def is_absolute(self):
            absolute = _ORIGINAL_IS_ABSOLUTE(self)
            if absolute:
                lexical = os.path.normpath(str(self))
                if any(lexical == item or lexical.startswith(item + os.sep) for item in data["protected"]):
                    raise IsolationError("KRONOS_TEST_PRODUCTION_PATH_FORBIDDEN")
            return absolute
        Path.is_absolute = is_absolute
        for key in tuple(os.environ):
            if (key.startswith(('KRONOS_', 'KITE_', 'OPENAI_', 'TELEGRAM_'))
                and key != MARKER):
                os.environ.pop(key, None)
        os.environ['PYTHON_DOTENV_DISABLED'] = '1'
        # Keep Python child bootstrapping even when a test passes an explicit
        # minimal env. Non-Python children still inherit the kernel sandbox.
        class IsolatedPopen(_ORIGINAL_POPEN):
            def __init__(self, *args, **kwargs):
                environment = dict(os.environ if kwargs.get('env') is None else kwargs['env'])
                environment[MARKER] = str(path)
                environment['PYTHONPATH'] = data['pythonpath']
                environment['PYTHON_DOTENV_DISABLED'] = '1'
                kwargs['env'] = environment
                super().__init__(*args, **kwargs)
        subprocess.Popen = IsolatedPopen
        return _STATE
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise IsolationError('KRONOS_TEST_ISOLATION_INVALID') from error
