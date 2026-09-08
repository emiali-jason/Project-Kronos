"""Explicit one-time deployment coordinator. Importing it performs no operation.

Execution requires a future Sponsor-approved plan and --execute. Installation is
separate: this tool verifies the already installed package, never installs it.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, UTC
from hashlib import sha256
import http.client
import json
import os
from pathlib import Path
import subprocess
import time

from kronos.common.legacy_bootstrap import (
    BootstrapError, LegacyBinding, LegacySnapshot, LegacyBootstrapCoordinator,
    _secure, _hex, _load, process_exists, listener_free,
)
from tools.macos.package_launcher import verify, digest, safe_path, BINARY

V2 = '/control/intraday-discovery/v2/status'
V1 = '/control/intraday-discovery/status'
HISTORY = '/control/intraday-historical-qualification/status'
MASTER = '/control/provider-instrument-master/status'


def http(method, route, headers=None):
    # Fixed loopback endpoint, no redirects, no proxies, no arbitrary route input
    # from the plan. Never serialize/log private shutdown headers or HTTP errors.
    connection = http.client.HTTPConnection('127.0.0.1', 8947, timeout=5)
    try:
        connection.request(method, route, headers=headers or {})
        response = connection.getresponse()
        data = response.read(2_000_001)
        if len(data) > 2_000_000 or response.status != (202 if method == 'POST' else 200):
            raise BootstrapError('BOOTSTRAP_HTTP_REJECTED')
        return json.loads(data)
    except (OSError, ValueError, http.client.HTTPException):
        raise BootstrapError('BOOTSTRAP_HTTP_REJECTED') from None
    finally:
        connection.close()


def command(*args):
    try:
        return subprocess.run(args, check=True, capture_output=True, timeout=10).stdout.decode().strip()
    except (OSError, subprocess.SubprocessError):
        raise BootstrapError('BOOTSTRAP_INSPECTION_FAILED') from None


def listener_owners(document):
    pid = None
    result = []
    for line in document.splitlines():
        if line.startswith('p') and line[1:].isdigit():
            pid = int(line[1:])
        elif line.startswith('n'):
            if pid is None or line[1:] != '127.0.0.1:8947':
                raise BootstrapError('BOOTSTRAP_LISTENER_ADDRESS_MISMATCH')
            result.append(pid)
        elif line and not line.startswith('f'):
            raise BootstrapError('BOOTSTRAP_LISTENER_STATUS_INVALID')
    if not result:
        raise BootstrapError('BOOTSTRAP_LISTENER_MISSING')
    return tuple(sorted(result))


def owners():
    return listener_owners(command('/usr/sbin/lsof', '-nP', '-Fpn',
        '-iTCP:8947', '-sTCP:LISTEN'))


def repository_gate(expected):
    repo = safe_path(expected.repository)
    git = lambda *args: command('git', '-C', str(repo), *args)
    if (git('branch', '--show-current') != 'develop' or git('rev-parse', 'HEAD') != expected.replacement_revision
        or git('rev-parse', 'origin/develop') != expected.replacement_revision
        or git('rev-list', '--left-right', '--count', 'origin/develop...HEAD') != '0\t0'
        or git('status', '--porcelain', '--untracked-files=all')):
        raise BootstrapError('BOOTSTRAP_REPOSITORY_MISMATCH')
    # Match the normal launcher's unique repository discovery before shutdown.
    matches = []
    for root in ('Documents/GitHub', 'Developer', 'Projects'):
        parent = Path.home() / root
        if parent.is_dir():
            for child in parent.iterdir():
                if (not child.name.startswith('.') and (child/'.git').is_dir()
                    and (child/'pyproject.toml').is_file() and (child/'src/kronos').is_dir()
                    and (child/'tools/kronos_browser.py').is_file() and os.access(child/'.venv/bin/python', os.X_OK)):
                    matches.append(child)
    if matches != [repo]:
        raise BootstrapError('BOOTSTRAP_LAUNCHER_REPOSITORY_AMBIGUOUS')


def read_control(path, expected):
    _secure(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as f:
        raw = f.read(4097)
    if len(raw) > 4096 or sha256(raw).hexdigest() != expected.control_digest:
        raise BootstrapError('BOOTSTRAP_CONTROL_MISMATCH')
    parts = raw.decode('ascii').splitlines()
    if (len(parts) != 3 or parts[0] != 'KRONOS_BROWSER_BACKEND_CONTROL_V1'
        or parts[1] != str(expected.pid) or not _hex(parts[2])):
        raise BootstrapError('BOOTSTRAP_CONTROL_MISMATCH')
    return parts[2]  # In-memory shutdown authority only; never migration evidence.


def snapshot(expected, control, launcher, *, get=lambda route: http('GET', route), listeners=owners):
    repository_gate(expected)
    read_control(control, expected)
    if digest(launcher / BINARY) != expected.installed_launcher_sha256:
        raise BootstrapError('BOOTSTRAP_LAUNCHER_MISMATCH')
    status, v1, v2, historical, master = [get(p) for p in ('/status', V1, V2, HISTORY, MASTER)]
    runtime = v2['runtime_identity']; startup = runtime['startup']
    actual = replace(expected, pid=startup['process_id'], revision=runtime['loaded_commit_revision'],
        runtime=runtime['manifest_identity'], startup=startup['startup_boundary_at'],
        configuration=runtime['configuration_identity'])
    if status['service'] != 'KRONOS_BROWSER_V1' or startup['source_state'] != 'CLEAN_COMMIT':
        raise BootstrapError('BOOTSTRAP_LEGACY_STATUS_INVALID')
    # These legacy controls expose active operations, but not a complete task
    # registry or transport quiescence. Missing observability stays unknown.
    if 'context_availability' not in master:
        raise BootstrapError('BOOTSTRAP_PROVIDER_TASK_STATUS_UNAVAILABLE')
    provider = status['provider']; analysis = status['analysis']
    if provider not in ('CONNECTED', 'DISCONNECTED', 'CONNECTING', 'ERROR'):
        raise BootstrapError('BOOTSTRAP_LEGACY_STATUS_INVALID')
    if analysis not in ('NOT RUN', 'RUNNING', 'READY', 'ERROR'):
        raise BootstrapError('BOOTSTRAP_LEGACY_STATUS_INVALID')
    return LegacySnapshot(actual, listeners(), provider == 'CONNECTING', analysis == 'RUNNING',
        v1['active_operation_identity'] is not None or v2['active_operation_identity'] is not None,
        historical['active_operation_identity'] is not None,
        monitoring_inflight=True if status['live_monitoring'] == 'TESTING' else None)


def replacement_environment(ticket):
    # Allow-list launch necessities. No inherited Provider/token/cookie context,
    # Python injection hooks, or old shutdown authority enters the child.
    result = {k: os.environ[k] for k in ('HOME', 'USER', 'LOGNAME', 'TMPDIR', 'LANG') if k in os.environ}
    result.update(PATH='/usr/bin:/bin:/usr/sbin:/sbin', KRONOS_LAUNCH_MODE='LEGACY_BOOTSTRAP')
    result.update(ticket.environment())
    return result


def verify_replacement(expected, ticket, *, get=lambda route: http('GET', route), listeners=owners):
    status, v1, v2 = [get(p) for p in ('/status', V1, V2)]
    runtime = v2['runtime_identity']; startup = runtime['startup']
    if (listeners() != (startup['process_id'],) or startup['process_id'] == expected.pid
        or runtime['loaded_commit_revision'] != expected.replacement_revision
        or runtime['configuration_identity'] != expected.configuration
        or startup['source_state'] != 'CLEAN_COMMIT' or status['provider'] != 'DISCONNECTED'
        or status.get('maintenance') != {'protocol': 'KRONOS_MAINTENANCE_HANDOFF_V1',
                                        'active': True, 'generation': ticket.identity}
        or v1['operation_available'] is not False or v2['operation_available'] is not False
        or v1['active_operation_identity'] is not None or v2['active_operation_identity'] is not None
        or v2['live_shadow']['enabled'] is not False):
        raise BootstrapError('BOOTSTRAP_GUARDED_ACCEPTANCE_FAILED')
    return {'pid': startup['process_id'], 'runtime': runtime['manifest_identity'],
            'loaded_revision': runtime['loaded_commit_revision'], 'maintenance': 'ACTIVE',
            'provider': 'DISCONNECTED', 'live_shadow': 'INACTIVE'}


def migrate(expected, launcher, bundle_identity, authorization_reference, *, observe=None,
            shutdown=None, launch=None, accept=None, alive=process_exists, free=listener_free,
            sleep=time.sleep, coordinator=None):
    if not _hex(bundle_identity):
        raise BootstrapError('BOOTSTRAP_APPROVED_PACKAGE_IDENTITY_REQUIRED')
    launcher = safe_path(launcher)
    verify(launcher, bundle_identity)
    control = Path.home() / 'Library/Application Support/KRONOS/runtime/browser-backend-v1.control'
    c = coordinator or LegacyBootstrapCoordinator(control.parent/'legacy-bootstrap-v1', expected)
    observe = observe or (lambda: snapshot(expected, control, launcher))
    def legacy_shutdown():
        token = read_control(control, expected)
        result = http('POST', '/control/shutdown', {'X-Kronos-Backend-Pid': str(expected.pid),
                                                   'X-Kronos-Restart-Token': token})
        if result.get('status') != 'STOPPING':
            raise BootstrapError('BOOTSTRAP_SHUTDOWN_REJECTED')
    ticket = c.prepare(observe(), authorization_reference)
    c.shutdown(ticket, observe, shutdown or legacy_shutdown)
    for _ in range(150):
        if not alive(expected.pid) and free():
            break
        sleep(.1)
    else:
        raise BootstrapError('BOOTSTRAP_STOP_TIMEOUT_NO_RETRY')
    c.stopped(ticket, legacy_alive=alive(expected.pid), listener_free=free())
    if launch is None:
        def launch(environment):
            try:
                subprocess.run([str(launcher / BINARY)], env=environment, check=True, timeout=35,
                               capture_output=True)
            except (OSError, subprocess.SubprocessError):
                raise BootstrapError('BOOTSTRAP_START_FAILED_NO_RETRY') from None
    verify(launcher, bundle_identity)
    launch(replacement_environment(ticket))
    result = (accept or (lambda t: verify_replacement(expected, t)))(ticket)
    consumed = _load(c.root, ticket, 'consumed')
    if consumed['pid'] != result['pid'] or consumed['decommissioned'] is not True:
        raise BootstrapError('BOOTSTRAP_CONSUMPTION_NOT_PROVEN')
    return {**result, 'migration': ticket.identity, 'bootstrap': 'PERMANENTLY_CONSUMED',
            'evidence_inertness': 'REQUIRES_SEPARATE_BEFORE_AFTER_INVENTORY',
            'end_maintenance': 'NOT_INVOKED', 'provider_connect': 'NOT_INVOKED'}


def main():
    parser = argparse.ArgumentParser(description='One-time legacy migration; future deployment authorization required.')
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.execute:
        print('PLAN_ONLY: no installation, shutdown, restart, or HTTP operation performed.')
        return 0
    try:
        plan = json.loads(safe_path(args.plan).read_bytes())
        if set(plan) != {'binding', 'launcher', 'bundle_identity', 'authorization_reference'}:
            raise BootstrapError('BOOTSTRAP_PLAN_INVALID')
        print(json.dumps(migrate(LegacyBinding(**plan['binding']), Path(plan['launcher']),
                                 plan['bundle_identity'], plan['authorization_reference']), indent=2))
        return 0
    except (ValueError, KeyError, TypeError, OSError):
        print('BOOTSTRAP_REJECTED: preserve evidence; no automatic retry.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
