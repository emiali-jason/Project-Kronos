"""APP-01A: kernel-resolved app path, seal and inert build-only probe."""
import json
import os
from pathlib import Path
import plistlib
import selectors
import shutil
import socket
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from threading import Thread

import pytest

from kronos.common.maintenance import publish_drain_handoff

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'tools/macos/kronos_launcher.c'


def compile_source(source, destination):
    unit = destination.parent / 'unit.c'
    unit.write_text(source)
    subprocess.run(['clang', '-Wall', '-Wextra', '-Werror', str(unit), '-o', str(destination)],
                   check=True, capture_output=True)
    unit.unlink()


def compile_start_monitor_harness(tmp_path):
    source = SOURCE.read_text().replace(
        'int main(void) {',
        'int unused_application_main(void) {',
    )
    source += r'''
static long fake_clock_values[8];
static size_t fake_clock_count = 0;
static size_t fake_clock_index = 0;
static int fake_ready_on_call = 0;
static int fake_ready_calls = 0;
static int fake_pause_calls = 0;
static int fake_observe_calls = 0;
static int fake_child_exit_on_call = 0;
static int fake_interrupt_observe_once = 0;
static int fake_interrupt_pause_once = 0;
static long fake_wall_clock = 0;

static int fake_monotonic_now(struct timespec *value) {
    if (fake_clock_index >= fake_clock_count) return -1;
    value->tv_sec = fake_clock_values[fake_clock_index++];
    value->tv_nsec = 0;
    return 0;
}

static pid_t fake_observe_child(pid_t child, int *status) {
    ++fake_observe_calls;
    if (fake_interrupt_observe_once) {
        fake_interrupt_observe_once = 0;
        errno = EINTR;
        return -1;
    }
    if (fake_child_exit_on_call == fake_observe_calls) {
        *status = 0;
        return child;
    }
    return 0;
}

static int fake_ready(void) {
    ++fake_ready_calls;
    return fake_ready_on_call > 0 && fake_ready_calls >= fake_ready_on_call;
}

static int fake_pause(
    const struct timespec *duration,
    struct timespec *remaining
) {
    ++fake_pause_calls;
    fake_wall_clock = fake_wall_clock == 0 ? 5000000000L : -5000000000L;
    if (fake_interrupt_pause_once) {
        fake_interrupt_pause_once = 0;
        *remaining = *duration;
        errno = EINTR;
        return -1;
    }
    return 0;
}

static void set_fake_clock(long first, long second, long third) {
    fake_clock_values[0] = first;
    fake_clock_values[1] = second;
    fake_clock_values[2] = third;
    fake_clock_count = 3;
}

int main(int argc, char **argv) {
    if (argc != 2) return 90;
    BackendStartMonitor monitor = {
        .monotonic_now = fake_monotonic_now,
        .observe_child = fake_observe_child,
        .ready = fake_ready,
        .pause = fake_pause,
    };
    BackendStartResult result;
    if (strcmp(argv[1], "delayed-ready") == 0) {
        set_fake_clock(0, 31, 45);
        fake_ready_on_call = 2;
        result = monitor_backend_start(4242, 120, &monitor);
        return result == BACKEND_START_READY && fake_pause_calls == 1 ? 0 : 1;
    }
    if (strcmp(argv[1], "child-exited") == 0) {
        set_fake_clock(0, 1, 2);
        fake_child_exit_on_call = 1;
        result = monitor_backend_start(4242, 120, &monitor);
        return result == BACKEND_START_CHILD_EXITED && fake_ready_calls == 0 ? 0 : 2;
    }
    if (strcmp(argv[1], "ready-timeout") == 0) {
        set_fake_clock(0, 30, 120);
        result = monitor_backend_start(4242, 120, &monitor);
        return result == BACKEND_START_READY_TIMEOUT &&
            fake_pause_calls == 1 && fake_ready_calls == 1 ? 0 : 3;
    }
    if (strcmp(argv[1], "interrupted-wall-jump") == 0) {
        set_fake_clock(0, 31, 45);
        fake_ready_on_call = 2;
        fake_interrupt_observe_once = 1;
        fake_interrupt_pause_once = 1;
        result = monitor_backend_start(4242, 120, &monitor);
        return result == BACKEND_START_READY && fake_pause_calls == 1 &&
            fake_wall_clock != 0 ? 0 : 4;
    }
    if (strcmp(argv[1], "internal-failure") == 0) {
        result = monitor_backend_start(4242, 120, &monitor);
        return result == BACKEND_START_INTERNAL_FAILURE ? 0 : 5;
    }
    return 91;
}
'''
    binary = tmp_path / 'start-monitor'
    compile_source(source, binary)
    return binary


def compile_readiness_response_harness(tmp_path):
    source = SOURCE.read_text().replace(
        'int main(void) {',
        'int unused_application_main(void) {',
    )
    source += r'''
int main(void) {
    char response[BACKEND_STATUS_RESPONSE_BYTES] = {0};
    static const char prefix[] =
        "HTTP/1.0 200 OK\r\nContent-Length: 5000\r\n\r\n"
        "{\"service\":\"KRONOS_BROWSER_V1\",\"provider\":\"DISCONNECTED\","
        "\"analysis\":\"READY\",\"padding\":\"";
    size_t used = strlen(prefix);
    (void)memcpy(response, prefix, used);
    (void)memset(response + used, 'x', 4300);
    used += 4300;
    static const char suffix[] = "\",\"runtime_ready\":true}";
    (void)memcpy(response + used, suffix, sizeof(suffix));
    if (strstr(response, "\"runtime_ready\":true") - response <= 4095) return 2;
    if (!response_is_ready(response)) return 3;
    response[0] = 'X';
    return response_is_ready(response) ? 4 : 0;
}
'''
    binary = tmp_path / 'readiness-response'
    compile_source(source, binary)
    return binary


def compile_status_probe(tmp_path, port, probe):
    source = SOURCE.read_text().replace(
        'htons(8947)',
        f'htons({port})',
    ).replace(
        'int main(void) {',
        'int unused_application_main(void) {',
    )
    source += f'\nint main(void) {{ return {probe}() ? 0 : 1; }}\n'
    binary = tmp_path / probe
    compile_source(source, binary)
    return binary


def compile_launcher_lock_harness(tmp_path):
    source = SOURCE.read_text().replace(
        'int main(void) {',
        'int unused_application_main(void) {',
    )
    source += r'''
int main(int argc, char **argv) {
    if (argc != 3) return 90;
    int descriptor = acquire_launcher_lock(argv[2]);
    if (descriptor < 0) return 91;
    puts("LOCKED");
    fflush(stdout);
    if (strcmp(argv[1], "hold") == 0 && getchar() == EOF) return 92;
    return close(descriptor) == 0 ? 0 : 93;
}
'''
    binary = tmp_path / 'launcher-lock'
    compile_source(source, binary)
    return binary


def compile_workspace_script_harness(tmp_path):
    source = SOURCE.read_text().replace(
        'int main(void) {',
        'int unused_application_main(void) {',
    )
    source += '\nint main(void) { puts(workspace_script); return 0; }\n'
    binary = tmp_path / 'workspace-script'
    compile_source(source, binary)
    return binary


def compile_v2_handoff_probe(tmp_path):
    source = SOURCE.read_text().replace('int main(void) {',
        'int unused_application_main(void) {')
    source += r'''
int main(int argc, char **argv) {
    if (argc != 8) return 90;
    return verify_v2_handoff(argv[1], argv[2], argv[3], argv[4],
        argv[5], (pid_t)atoi(argv[6]), argv[7],
        "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd")
        ? 0 : 1;
}
'''
    binary = tmp_path / 'v2-handoff-probe'
    compile_source(source, binary)
    return binary


def compile_cold_absence_probe(tmp_path):
    source = SOURCE.read_text().replace('int main(void) {',
        'int unused_application_main(void) {')
    source += r'''
int main(int argc, char **argv) {
    return argc == 2 && cold_start_has_no_control_or_live_handoff(argv[1]) ? 0 : 1;
}
'''
    binary = tmp_path / 'cold-absence-probe'
    compile_source(source, binary)
    return binary


def compile_isolated_transition_probe(tmp_path, port):
    source = SOURCE.read_text().replace('htons(8947)', f'htons({port})').replace(
        'int main(void) {', 'int unused_application_main(void) {')
    source += r'''
int main(int argc, char **argv) {
    if (argc != 8) return 90;
    pid_t pid = (pid_t)atoi(argv[5]);
    if (!request_graceful_shutdown(pid,
        "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
        argv[6], 1)) return 91;
    if (!wait_for_backend_stop(pid)) return 92;
    if (!verify_v2_handoff(argv[1], argv[2], argv[3], argv[4],
        argv[6], pid, argv[7],
        "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"))
        return 93;
    return 0;
}
'''
    binary = tmp_path / 'isolated-transition-probe'
    compile_source(source, binary)
    return binary


def compile_isolated_cold_start_probe(tmp_path, port):
    source = SOURCE.read_text().replace('htons(8947)', f'htons({port})').replace(
        'int main(void) {', 'int unused_application_main(void) {')
    source += r'''
int main(int argc, char **argv) {
    if (argc != 5 || !cold_start_has_no_control_or_live_handoff(argv[4])) return 90;
    return start_backend(argv[1], argv[2], argv[3], argv[1], 0, "", "", "")
        == BACKEND_START_READY ? 0 : 91;
}
'''
    binary = tmp_path / 'isolated-cold-start-probe'
    compile_source(source, binary)
    return binary


def compile_isolated_successor_probe(tmp_path, port):
    source = SOURCE.read_text().replace('htons(8947)', f'htons({port})').replace(
        'int main(void) {', 'int unused_application_main(void) {')
    source += r'''
int main(int argc, char **argv) {
    if (argc != 8) return 90;
    return start_backend(argv[1], argv[2], argv[3], argv[4],
        (pid_t)atoi(argv[5]),
        "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
        argv[6], argv[7]) == BACKEND_START_READY ? 0 : 91;
}
'''
    binary = tmp_path / 'isolated-successor-probe'
    compile_source(source, binary)
    return binary


def status_body(*, padding=0, maintenance=True, ready=True):
    payload = {
        'service': 'KRONOS_BROWSER_V1',
        'provider': 'DISCONNECTED',
        'analysis': 'READY',
        'padding': 'x' * padding,
    }
    if maintenance:
        payload['maintenance'] = {
            'protocol': 'KRONOS_MAINTENANCE_HANDOFF_V1',
            'state': 'INACTIVE',
            'active': False,
            'generation': None,
            'startup': 'READY',
            'failure': None,
        }
    payload['runtime_ready'] = ready
    return json.dumps(payload, separators=(',', ':')).encode()


def status_response(body, *, status='200 OK', content_length=None):
    declared = len(body) if content_length is None else content_length
    return (
        f'HTTP/1.0 {status}\r\nContent-Type: application/json\r\n'
        f'Content-Length: {declared}\r\n\r\n'.encode()
        + body
    )


def run_status_probe(tmp_path, response, probe, *, fragmented=False):
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(1)
    listener.settimeout(5)
    binary = compile_status_probe(tmp_path, listener.getsockname()[1], probe)
    requests = []
    errors = []

    def peer():
        try:
            connection, _ = listener.accept()
            with connection:
                request = b''
                while b'\r\n\r\n' not in request:
                    request += connection.recv(256)
                requests.append(request)
                if fragmented:
                    offset = 0
                    widths = (1, 7, 31, 257)
                    fragment = 0
                    while offset < len(response):
                        width = widths[fragment % len(widths)]
                        connection.sendall(response[offset:offset + width])
                        offset += width
                        fragment += 1
                else:
                    connection.sendall(response)
        except Exception as error:  # pragma: no cover - asserted below
            errors.append(error)
        finally:
            listener.close()

    thread = Thread(target=peer)
    thread.start()
    try:
        completed = subprocess.run([str(binary)], capture_output=True, timeout=5)
    finally:
        thread.join(6)
        listener.close()
    assert not thread.is_alive() and not errors
    assert len(requests) == 1 and requests[0].startswith(b'GET /status ')
    return completed


def run_replacement_probe(tmp_path, payload, *, target, expected):
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(1)
    listener.settimeout(5)
    port = listener.getsockname()[1]
    source = SOURCE.read_text().replace('htons(8947)', f'htons({port})').replace(
        'int main(void) {', 'int unused_application_main(void) {',
    )
    source += f'''\nint main(void) {{
        return backend_replacement_readiness({os.getpid()}, "{target}") == {expected}
            ? 0 : 1;
    }}\n'''
    binary = tmp_path / 'replacement-probe'
    compile_source(source, binary)
    response = status_response(json.dumps(payload, separators=(',', ':')).encode())
    requests = []

    def peer():
        connection, _ = listener.accept()
        with connection:
            request = b''
            while b'\r\n\r\n' not in request:
                request += connection.recv(256)
            requests.append(request)
            connection.sendall(response)
        listener.close()

    thread = Thread(target=peer)
    thread.start()
    completed = subprocess.run([str(binary)], capture_output=True, timeout=5)
    thread.join(6)
    assert not thread.is_alive()
    assert requests == [
        b'GET /runtime/status HTTP/1.0\r\nHost: 127.0.0.1:8947\r\nConnection: close\r\n\r\n'
    ]
    assert completed.returncode == 0


OLD_RUNTIME_REVISION = 'cf55fa827b33d27ec44efb8988d413b1088ae07d'


def old_runtime_payload():
    payload = replacement_payload(revision=OLD_RUNTIME_REVISION)
    payload.pop('analysis_work')
    payload.pop('analysis_execution')
    payload.pop('maintenance_drain')
    return payload


def old_status_payload():
    runtime = replacement_payload(revision=OLD_RUNTIME_REVISION)
    return {
        'service': 'KRONOS_BROWSER_V1',
        'provider': 'CONNECTED',
        'analysis': 'READY',
        'intraday_wo11_work': dict(runtime['intraday_wo11_work']),
        'intraday_wo17_work': dict(runtime['intraday_wo17_work']),
        'housekeeping': dict(runtime['housekeeping']),
        'swing_bulk_import': dict(runtime['swing_bulk_import']),
        'swing_publication': {
            'control': {'schema_version': 'KRONOS-SWING-RUN-PUBLICATION-V1'},
            'request_result': '',
            'reconciliation_unavailable': False,
            'analysis_work': dict(runtime['analysis_work']),
            'analysis_execution': dict(runtime['analysis_execution']),
        },
        'maintenance': dict(runtime['maintenance']),
        'runtime_ready': True,
    }


def run_old_replacement_probe(tmp_path, payloads, *, expected, expected_requests):
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(3)
    listener.settimeout(1)
    port = listener.getsockname()[1]
    source = SOURCE.read_text().replace('htons(8947)', f'htons({port})').replace(
        'int main(void) {', 'int unused_application_main(void) {',
    )
    source += f'''\nint main(void) {{
        return backend_replacement_readiness({os.getpid()}, "{'b' * 40}") == {expected}
            ? 0 : 1;
    }}\n'''
    binary = tmp_path / 'old-replacement-probe'
    compile_source(source, binary)
    responses = [
        status_response(json.dumps(value, separators=(',', ':')).encode())
        for value in payloads
    ]
    requests = []
    errors = []

    def peer():
        try:
            for response in responses:
                try:
                    connection, _ = listener.accept()
                except socket.timeout:
                    break
                with connection:
                    request = b''
                    while b'\r\n\r\n' not in request:
                        request += connection.recv(256)
                    requests.append(request)
                    connection.sendall(response)
        except Exception as error:  # pragma: no cover - asserted below
            errors.append(error)
        finally:
            listener.close()

    thread = Thread(target=peer)
    thread.start()
    completed = subprocess.run([str(binary)], capture_output=True, timeout=5)
    thread.join(6)
    assert not thread.is_alive() and not errors
    assert requests == expected_requests
    assert completed.returncode == 0, completed.stderr.decode()


def replacement_payload(*, revision='a' * 40, worker=False, owners=0):
    return {
        'schema': 'KRONOS-RUNTIME-STATE/1.0.0',
        'process': {'pid': os.getpid(), 'revision': revision, 'source_state': 'CLEAN_COMMIT'},
        'maintenance': {
            'protocol': 'KRONOS_MAINTENANCE_HANDOFF_V1', 'state': 'INACTIVE',
            'active': False, 'generation': 'f' * 64, 'startup': 'READY', 'failure': None,
        },
        'maintenance_drain': {
            'state': 'OPEN', 'generation': None, 'owners': {}, 'failure': None,
        },
        'maintenance_claim': 'DRAINABLE' if not worker and not owners else 'BLOCKED',
        'rest_authentication': 'CONNECTED',
        'connection_attempt': {
            'state': 'SUCCEEDED', 'remaining_seconds': 0.0, 'generation': 1,
            'request_identity': 'request', 'worker_active': False,
            'resources_pending': False, 'cleanup_state': 'COMPLETE',
            'unresolved_resources': [], 'restoration_worker_active': False,
        },
        'monitoring': {
            'schema': 'KRONOS-SHARED-MONITORING-STATUS/1.0.0', 'hub_state': 'IDLE',
            'transport_state': 'IDLE', 'session_count': 0, 'active_session_count': 0,
            'owner_count': owners, 'subscription_count': 0, 'subscriptions': [], 'owners': [],
        },
        'intraday_wo11_work': {
            'state': 'RUNNING' if worker else 'IDLE',
            'generation': 1 if worker else None, 'owned_workers': int(worker),
            'queued_items': 0,
        },
        'intraday_wo17_work': {
            'state': 'IDLE', 'generation': None, 'owned_workers': 0, 'queued_items': 0,
        },
        'housekeeping': {
            'production_activation': True, 'interval_seconds': 21600,
            'lifecycle_state': 'IDLE', 'shutdown_requested': False,
            'owned_workers': 0, 'worker_generation': None, 'pass_active': False,
        },
        'swing_bulk_import': {'state': 'IDLE', 'owned_workers': 1, 'batch_active': False},
        'analysis_work': {
            'state': 'IDLE', 'generation': None, 'run_identity': None,
            'owned_work_count': 0, 'queued_jobs': 0,
        },
        'analysis_execution': {
            'state': 'IDLE', 'pid': None, 'generation': None, 'failure': None,
            'failure_diagnostic': None, 'owned_workers': 0, 'queued_jobs': 0,
        },
    }


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


@pytest.mark.parametrize('scenario', [
    'delayed-ready',
    'child-exited',
    'ready-timeout',
    'interrupted-wall-jump',
    'internal-failure',
])
def test_start_monitor_has_typed_bounded_results(tmp_path, scenario):
    binary = compile_start_monitor_harness(tmp_path)
    subprocess.run([str(binary), scenario], check=True, capture_output=True, timeout=5)


def test_start_contract_uses_monotonic_120_second_deadline_and_exact_alerts():
    source = SOURCE.read_text()
    assert '#define BACKEND_START_READY_TIMEOUT_SECONDS 120' in source
    assert 'clock_gettime(CLOCK_MONOTONIC, value)' in source
    assert 'CLOCK_REALTIME' not in source
    assert 'for (int attempt = 0; attempt < 300; ++attempt)' not in source
    assert 'It was not reused' not in source
    for name in (
        'BACKEND_START_READY',
        'BACKEND_START_CHILD_EXITED',
        'BACKEND_START_READY_TIMEOUT',
        'BACKEND_START_INTERNAL_FAILURE',
    ):
        assert name in source
    assert '"KRONOS restart blocked"' in source
    assert (
        '"The existing KRONOS backend could not be stopped through the authenticated '
        'maintenance handoff. No replacement was started. Contact Engineering."'
    ) in source
    assert '"KRONOS is still starting"' in source
    assert (
        '"The previous backend stopped safely and the replacement was started, but it '
        'did not become ready within 120 seconds. Do not relaunch KRONOS. Contact Engineering."'
    ) in source
    assert (
        '"The previous backend stopped safely, but the replacement process exited before '
        'becoming ready. Do not relaunch KRONOS. Contact Engineering."'
    ) in source
    assert (
        '"The previous backend stopped safely, but the replacement could not be started '
        'or monitored safely. Do not relaunch KRONOS. Contact Engineering."'
    ) in source


def test_readiness_response_budget_covers_status_beyond_old_cutoff(tmp_path):
    binary = compile_readiness_response_harness(tmp_path)
    subprocess.run([str(binary)], check=True, capture_output=True, timeout=5)
    source = SOURCE.read_text()
    readiness = source.split('static int backend_is_ready(void) {', 1)[1].split(
        'static int open_workspace(void) {', 1
    )[0]
    assert '#define BACKEND_STATUS_RESPONSE_BYTES (64 * 1024)' in source
    assert 'char response[BACKEND_STATUS_RESPONSE_BYTES]' in readiness
    assert 'char response[4096]' not in readiness


def test_short_status_response_passes_both_status_checks(tmp_path):
    response = status_response(status_body())
    for probe in ('backend_is_ready', 'backend_supports_maintenance'):
        case = tmp_path / probe
        case.mkdir()
        assert run_status_probe(case, response, probe).returncode == 0


def test_fragmented_large_status_passes_readiness_and_maintenance(tmp_path):
    response = status_response(status_body(padding=4300))
    protocol_offset = response.index(b'KRONOS_MAINTENANCE_HANDOFF_V1')
    assert len(response) > 4280 and protocol_offset > 4095
    for probe in ('backend_is_ready', 'backend_supports_maintenance'):
        case = tmp_path / probe
        case.mkdir()
        assert run_status_probe(case, response, probe, fragmented=True).returncode == 0


@pytest.mark.parametrize('failure', ['missing-protocol', 'truncated', 'incomplete'])
def test_missing_or_incomplete_status_fails_closed(tmp_path, failure):
    body = status_body(maintenance=failure != 'missing-protocol')
    if failure == 'truncated':
        marker = body.index(b'KRONOS_MAINTENANCE_HANDOFF_V1')
        complete = body
        body = body[:marker + 8]
        response = status_response(body, content_length=len(complete))
        probe = 'backend_supports_maintenance'
    elif failure == 'incomplete':
        response = status_response(body, content_length=len(body) + 20)
        probe = 'backend_is_ready'
    else:
        response = status_response(body)
        probe = 'backend_supports_maintenance'
    assert run_status_probe(tmp_path, response, probe).returncode != 0


def test_oversized_status_fails_closed(tmp_path):
    oversized_bytes = 70 * 1024
    body = status_body() + (b'x' * oversized_bytes)
    assert len(body) > oversized_bytes
    response = status_response(body)
    assert run_status_probe(tmp_path, response, 'backend_is_ready').returncode != 0


def test_revision_mismatch_is_an_explicit_idle_governed_replacement(tmp_path):
    run_replacement_probe(
        tmp_path,
        replacement_payload(revision='a' * 40),
        target='b' * 40,
        expected='REPLACEMENT_REQUIRED',
    )


def test_exact_loaded_revision_is_reused_without_a_replacement(tmp_path):
    run_replacement_probe(
        tmp_path,
        replacement_payload(revision='b' * 40),
        target='b' * 40,
        expected='REPLACEMENT_ALREADY_LOADED',
    )


def test_exact_cf55_old_schema_pair_authorizes_one_compatibility_handoff(tmp_path):
    runtime = old_runtime_payload()
    status = old_status_payload()
    run_old_replacement_probe(
        tmp_path,
        [runtime, status, runtime],
        expected='REPLACEMENT_REQUIRED_OLD_CF55',
        expected_requests=[
            b'GET /runtime/status HTTP/1.0\r\nHost: 127.0.0.1:8947\r\nConnection: close\r\n\r\n',
            b'GET /status HTTP/1.0\r\nHost: 127.0.0.1:8947\r\nConnection: close\r\n\r\n',
            b'GET /runtime/status HTTP/1.0\r\nHost: 127.0.0.1:8947\r\nConnection: close\r\n\r\n',
        ],
    )


@pytest.mark.parametrize(
    ('case', 'expected_count'),
    [
        ('runtime-intraday-busy', 1),
        ('runtime-monitoring-owner', 1),
        ('status-analysis-missing', 2),
        ('status-analysis-busy', 2),
        ('status-generation-conflict', 2),
        ('status-not-ready', 2),
        ('recheck-intraday-busy', 3),
        ('recheck-generation-conflict', 3),
        ('recheck-revision-conflict', 3),
    ],
)
def test_cf55_compatibility_rejects_missing_busy_conflicting_or_changing_facts(
    tmp_path, case, expected_count,
):
    first = old_runtime_payload()
    status = old_status_payload()
    recheck = old_runtime_payload()
    if case == 'runtime-intraday-busy':
        first['intraday_wo11_work'].update(state='RUNNING', generation=1, owned_workers=1)
    elif case == 'runtime-monitoring-owner':
        first['monitoring']['owner_count'] = 1
    elif case == 'status-analysis-missing':
        status['swing_publication'].pop('analysis_work')
    elif case == 'status-analysis-busy':
        status['swing_publication']['analysis_work'].update(
            state='RUNNING', generation=1, run_identity='run', owned_work_count=1,
        )
    elif case == 'status-generation-conflict':
        status['maintenance']['generation'] = 'e' * 64
    elif case == 'status-not-ready':
        status['runtime_ready'] = False
    elif case == 'recheck-intraday-busy':
        recheck['intraday_wo11_work'].update(state='RUNNING', generation=2, owned_workers=1)
    elif case == 'recheck-generation-conflict':
        recheck['maintenance']['generation'] = 'e' * 64
    elif case == 'recheck-revision-conflict':
        recheck['process']['revision'] = 'c' * 40
    payloads = [first, status, recheck]
    requests = [
        b'GET /runtime/status HTTP/1.0\r\nHost: 127.0.0.1:8947\r\nConnection: close\r\n\r\n',
        b'GET /status HTTP/1.0\r\nHost: 127.0.0.1:8947\r\nConnection: close\r\n\r\n',
        b'GET /runtime/status HTTP/1.0\r\nHost: 127.0.0.1:8947\r\nConnection: close\r\n\r\n',
    ][:expected_count]
    run_old_replacement_probe(
        tmp_path,
        payloads,
        expected='REPLACEMENT_NOT_READY',
        expected_requests=requests,
    )


def test_old_schema_compatibility_is_revision_scoped(tmp_path):
    runtime = old_runtime_payload()
    runtime['process']['revision'] = 'd' * 40
    run_old_replacement_probe(
        tmp_path,
        [runtime],
        expected='REPLACEMENT_NOT_READY',
        expected_requests=[
            b'GET /runtime/status HTTP/1.0\r\nHost: 127.0.0.1:8947\r\nConnection: close\r\n\r\n',
        ],
    )


def test_replacement_records_the_authorizing_predicate_before_handoff():
    source = SOURCE.read_text()
    main = source.split('int main(void) {', 1)[1]
    predicate = main.index('KRONOS_REPLACEMENT_PREDICATE=OLD_RUNTIME_CF55_STATUS_PAIR')
    shutdown = main.index('request_graceful_shutdown(backend_pid, token, generation, replacement || recovery)')
    assert predicate < shutdown
    assert 'KRONOS_REPLACEMENT_PREDICATE=CURRENT_RUNTIME_STATUS' in main


@pytest.mark.parametrize(
    'payload',
    [replacement_payload(worker=True), replacement_payload(owners=1)],
)
def test_revision_replacement_rejects_active_shared_work(tmp_path, payload):
    run_replacement_probe(
        tmp_path,
        payload,
        target='b' * 40,
        expected='REPLACEMENT_NOT_READY',
    )


def test_corrected_predecessor_allows_only_counted_drainable_work(tmp_path):
    payload = replacement_payload(worker=True)
    payload['maintenance_drain']['owners'] = {'WO11': 1}
    payload['maintenance_claim'] = 'DRAINABLE'
    run_replacement_probe(tmp_path, payload, target='b' * 40,
        expected='REPLACEMENT_REQUIRED')


def test_unknown_work_cannot_borrow_a_drainable_marker(tmp_path):
    payload = replacement_payload(worker=True)
    payload['maintenance_drain']['owners'] = {'UNKNOWN': 1}
    run_replacement_probe(tmp_path, payload, target='b' * 40,
        expected='REPLACEMENT_NOT_READY')


def test_legacy_idle_status_without_v2_drain_marker_cannot_enter_corrected_replacement(tmp_path):
    payload = replacement_payload(revision='a' * 40)
    payload.pop('maintenance_drain')
    run_replacement_probe(tmp_path, payload, target='b' * 40,
        expected='REPLACEMENT_NOT_READY')


def test_revision_replacement_mode_preserves_ordinary_dock_reuse_contract():
    source = SOURCE.read_text()
    main = source.split('int main(void) {', 1)[1]
    assert 'strcmp(mode, "GOVERNED_REPLACEMENT") == 0' in main
    assert 'KRONOS_REPLACEMENT_REVISION' in main
    assert (
        'if (!bootstrap && !replacement && !recovery && backend_is_reusable(control_path)) '
        'return open_workspace();'
    ) in main
    readiness = main.index('backend_replacement_readiness(')
    shutdown = main.index('request_graceful_shutdown(backend_pid, token, generation, replacement || recovery)')
    start = main.index('BackendStartResult start_result = start_backend(')
    assert readiness < shutdown < start
    assert main.count('request_graceful_shutdown(') == 1
    assert main.count('start_backend(') == 1


def test_revision_replacement_requires_exact_clean_published_target():
    source = SOURCE.read_text()
    main = source.split('int main(void) {', 1)[1]
    qualification = main.index('qualify_source(repository, python)')
    target = main.index('repository_revision_matches(repository, target_revision)')
    lock = main.index('acquire_launcher_lock(repository)')
    readiness = main.index('backend_replacement_readiness(')
    assert qualification < target < lock < readiness
    assert 'valid_revision(target_revision)' in main
    assert '/usr/bin/git", "git", "rev-parse", "HEAD"' in source
    child = source.split('static BackendStartResult start_backend(', 1)[1].split(
        'int main(void) {', 1
    )[0]
    assert 'unsetenv("KRONOS_LAUNCH_MODE")' in child
    assert 'unsetenv("KRONOS_REPLACEMENT_REVISION")' in child
    assert child.index('unsetenv("KRONOS_REPLACEMENT_REVISION")') < child.index(
        'execl(python, python, "-B", browser_entry, "--no-browser"'
    )


@pytest.mark.parametrize(
    ('status', 'include_length'),
    [('503 Service Unavailable', True), ('200 OK', False)],
)
def test_non_200_or_malformed_status_fails_closed(tmp_path, status, include_length):
    body = status_body()
    response = status_response(body, status=status)
    if not include_length:
        response = response.replace(
            f'Content-Length: {len(body)}\r\n'.encode(),
            b'',
        )
    assert run_status_probe(tmp_path, response, 'backend_is_ready').returncode != 0


def test_shutdown_rejection_and_start_results_route_without_retry_or_kill():
    source = SOURCE.read_text()
    main = source.split('int main(void) {', 1)[1]
    shutdown_call = main.index('request_graceful_shutdown(backend_pid, token, generation, replacement || recovery)')
    stop_wait = main.index('wait_for_backend_stop(backend_pid)')
    start_call = main.index('BackendStartResult start_result = start_backend(')
    assert shutdown_call < stop_wait < start_call
    assert main.index('return show_restart_blocked();') < start_call
    token_clear = main.index('(void)memset(token, 0, sizeof(token));', start_call)
    result_switch = main.index('switch (start_result)', start_call)
    assert start_call < token_clear < result_switch
    assert main.count('start_backend(') == 1
    assert main.count('open_workspace()') == 3
    assert main.index('case BACKEND_START_READY:') < main.rindex('open_workspace()')
    monitor = source.split('static BackendStartResult monitor_backend_start(', 1)[1]
    monitor = monitor.split('/* ADR-0061:', 1)[0]
    assert 'kill(' not in monitor
    assert 'fork(' not in monitor
    stop = source.split('static int wait_for_backend_stop(', 1)[1]
    stop = stop.split('static int qualify_source(', 1)[0]
    assert 'process_gone && socket_fd < 0' in stop


def test_corrected_predecessor_requires_signed_zero_handoff_before_start(tmp_path):
    control = tmp_path / 'runtime' / 'browser-backend-v1.control'
    maintenance = control.parent / 'maintenance'
    generation = 'a' * 64
    revision = 'f' * 40
    drain = {name: 0 for name in (
        'coordinator_owners', 'wo11_owned', 'wo11_queued', 'wo17_owned',
        'wo17_queued', 'housekeeping_owned', 'bulk_owned',
        'notification_scheduled', 'monitoring_sessions', 'provider_owned',
        'provider_leases',
    )}
    drain['notification_checkpoint'] = {'state': 'EMPTY', 'pending_count': 0,
        'sha256': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'}
    publish_drain_handoff(maintenance, generation=generation,
        parent_pid=os.getpid(), proof='d' * 64,
        runtime_identity='e' * 64, loaded_revision=revision,
        drain=drain, now=datetime.now(UTC))
    binary = compile_v2_handoff_probe(tmp_path)
    args = [str(binary), str(ROOT), sys.executable,
        f'{ROOT / "src"}:{ROOT}', str(control), generation,
        str(os.getpid()), revision]
    before = {p.name: p.read_bytes() for p in maintenance.iterdir()}
    assert subprocess.run(args, capture_output=True).returncode == 0
    assert {p.name: p.read_bytes() for p in maintenance.iterdir()} == before
    assert subprocess.run([*args[:-1], 'b' * 40], capture_output=True).returncode != 0
    assert subprocess.run([*args[:6], str(os.getpid() + 1), revision],
        capture_output=True).returncode != 0
    original = maintenance / f'{generation}.json'
    original.write_bytes(original.read_bytes().replace(b'"wo11_owned":0', b'"wo11_owned":1'))
    assert subprocess.run(args, capture_output=True).returncode != 0


def test_cold_branch_rejects_control_or_live_unconsumed_handoff(tmp_path):
    control = tmp_path / 'runtime' / 'browser-backend-v1.control'
    control.parent.mkdir()
    binary = compile_cold_absence_probe(tmp_path)
    run = lambda: subprocess.run([str(binary), str(control)], capture_output=True).returncode
    assert run() == 0
    control.write_text('stale')
    assert run() != 0
    control.unlink()
    maintenance = control.parent / 'maintenance'
    maintenance.mkdir(mode=0o700)
    maintenance.chmod(0o700)
    generation = 'a' * 64
    handoff = maintenance / f'{generation}.json'
    handoff.write_text('{}')
    assert run() != 0
    (maintenance / f'{generation}.consumed.json').write_text('{}')
    assert run() == 0


def test_no_predecessor_rehearses_one_canonical_fake_start(tmp_path):
    reservation = socket.socket()
    reservation.bind(('127.0.0.1', 0))
    port = reservation.getsockname()[1]
    reservation.close()
    repository = tmp_path / 'repository'
    repository.mkdir()
    control = tmp_path / 'runtime' / 'browser-backend-v1.control'
    control.parent.mkdir()
    marker = tmp_path / 'starts.txt'
    fake = tmp_path / 'fake-browser.py'
    fake.write_text('''
import socket
from pathlib import Path
from sys import argv
Path(%r).open('a').write('START\\n')
listener = socket.socket()
listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
listener.bind(('127.0.0.1', %d))
listener.listen(4)
while True:
    peer, _ = listener.accept()
    with peer:
        request = b''
        while b'\\r\\n\\r\\n' not in request:
            request += peer.recv(1024)
        body = b'{"service":"KRONOS_BROWSER_V1","provider":"DISCONNECTED","analysis":"READY","runtime_ready":true}'
        peer.sendall(b'HTTP/1.0 200 OK\\r\\nContent-Length: ' + str(len(body)).encode() + b'\\r\\n\\r\\n' + body)
        if request.startswith(b'GET /stop '):
            break
listener.close()
''' % (str(marker), port))
    binary = compile_isolated_cold_start_probe(tmp_path, port)
    started = subprocess.run([str(binary), str(repository), sys.executable,
        str(fake), str(control)], capture_output=True, timeout=8)
    try:
        assert started.returncode == 0, started.stderr
        assert marker.read_text().splitlines() == ['START']
    finally:
        with socket.create_connection(('127.0.0.1', port), timeout=2) as peer:
            peer.sendall(b'GET /stop HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n')
            assert b'200 OK' in peer.recv(1024)


def test_v2_replacement_keeps_legacy_branch_separate_and_deadline_unchanged():
    source = SOURCE.read_text()
    main = source.split('int main(void) {', 1)[1]
    assert main.index('readiness == REPLACEMENT_REQUIRED_OLD_CF55') < main.index(
        'request_graceful_shutdown(backend_pid, token, generation, replacement || recovery)')
    assert main.index('wait_for_backend_stop(backend_pid)') < main.index(
        'verify_v2_handoff(repository, python, python_path,') < main.index(
        'BackendStartResult start_result = start_backend(')
    assert 'BACKEND_START_READY_TIMEOUT_SECONDS 120' in source
    assert main.count('start_backend(') == 1


def test_corrected_predecessor_isolated_drain_exit_and_signed_rehearsal(tmp_path):
    generation = 'a' * 64
    revision = 'f' * 40
    control = tmp_path / 'runtime' / 'browser-backend-v1.control'
    control.parent.mkdir()
    script = r'''
import os, socket, sys
from datetime import UTC, datetime
from pathlib import Path
from kronos.common.maintenance import publish_drain_handoff
listener = socket.socket()
listener.bind(('127.0.0.1', 0))
listener.listen(2)
print(listener.getsockname()[1], flush=True)
for index in range(2):
    peer, _ = listener.accept()
    with peer:
        request = b''
        while b'\r\n\r\n' not in request:
            request += peer.recv(2048)
        body = (b'{"protocol":"KRONOS_MAINTENANCE_HANDOFF_V1"}' if index == 0
                else b'{"status":"DRAINING"}')
        code = b'200 OK' if index == 0 else b'202 Accepted'
        peer.sendall(b'HTTP/1.0 ' + code + b'\r\nContent-Length: ' +
                     str(len(body)).encode() + b'\r\n\r\n' + body)
drain = {name: 0 for name in (
    'coordinator_owners', 'wo11_owned', 'wo11_queued', 'wo17_owned',
    'wo17_queued', 'housekeeping_owned', 'bulk_owned',
    'notification_scheduled', 'monitoring_sessions', 'provider_owned',
    'provider_leases')}
drain['notification_checkpoint'] = {'state': 'EMPTY', 'pending_count': 0,
    'sha256': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'}
publish_drain_handoff(Path(sys.argv[1]) / 'maintenance',
    generation=sys.argv[2], parent_pid=os.getpid(), proof='d'*64,
    runtime_identity='e'*64, loaded_revision=sys.argv[3],
    drain=drain, now=datetime.now(UTC))
listener.close()
'''
    environment = dict(os.environ, PYTHONPATH=f'{ROOT / "src"}:{ROOT}')
    predecessor = subprocess.Popen([sys.executable, '-B', '-c', script,
        str(control.parent), generation, revision], env=environment,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert predecessor.stdout is not None
        port = int(predecessor.stdout.readline().strip())
        binary = compile_isolated_transition_probe(tmp_path, port)
        args = [str(binary), str(ROOT), sys.executable,
            f'{ROOT / "src"}:{ROOT}', str(control),
            str(predecessor.pid), generation, revision]
        probe = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        predecessor.wait(timeout=10)
        stdout, stderr = probe.communicate(timeout=17)
        assert predecessor.returncode == 0, predecessor.stderr.read()
        assert probe.returncode == 0, (probe.returncode, stdout, stderr)
        assert (control.parent / 'maintenance' / f'{generation}.json').is_file()
        assert not (control.parent / 'maintenance' / f'{generation}.consumed.json').exists()
        fake = tmp_path / 'fake-successor.py'
        marker = tmp_path / 'successor-starts.txt'
        fake.write_text(r'''
import os, socket
from datetime import UTC, datetime
from pathlib import Path
from kronos.common.legacy_bootstrap import consume_startup_context
from sys import argv
def port_free():
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(('127.0.0.1', %d))
    return True
try:
    identity = consume_startup_context(Path(%r), os.environ,
        revision='b'*40, source_state='CLEAN_COMMIT', repository=Path(%r),
        runtime_identity='c'*64, now=datetime.now(UTC), port_free=port_free)
except Exception as error:
    Path(%r).write_text(type(error).__name__ + ':' + str(error))
    raise
assert identity.generation == %r
assert identity.notification_checkpoint()['state'] == 'EMPTY'
Path(%r).open('a').write('START\n')
listener = socket.socket()
listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
listener.bind(('127.0.0.1', %d))
listener.listen(4)
while True:
    peer, _ = listener.accept()
    with peer:
        request = b''
        while b'\r\n\r\n' not in request:
            request += peer.recv(1024)
        body = b'{"service":"KRONOS_BROWSER_V1","provider":"DISCONNECTED","analysis":"READY","runtime_ready":true}'
        peer.sendall(b'HTTP/1.0 200 OK\r\nContent-Length: ' + str(len(body)).encode() + b'\r\n\r\n' + body)
        if request.startswith(b'GET /stop '):
            break
listener.close()
''' % (port, str(control.parent), str(ROOT), str(tmp_path / 'successor-error.txt'),
       generation, str(marker), port))
        successor = compile_isolated_successor_probe(tmp_path, port)
        started = subprocess.run([str(successor), str(ROOT), sys.executable,
            str(fake), f'{ROOT / "src"}:{ROOT}', str(predecessor.pid),
            generation, revision],
            capture_output=True, timeout=8)
        assert started.returncode == 0, (
            started.stderr,
            (tmp_path / 'successor-error.txt').read_text()
            if (tmp_path / 'successor-error.txt').exists() else 'no child error')
        assert marker.read_text().splitlines() == ['START']
        assert (control.parent / 'maintenance' / f'{generation}.consumed.json').is_file()
        with socket.create_connection(('127.0.0.1', port), timeout=2) as peer:
            peer.sendall(b'GET /stop HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n')
            assert b'200 OK' in peer.recv(1024)
    finally:
        if predecessor.poll() is None:
            predecessor.terminate()
            predecessor.wait(timeout=3)


def test_ready_runtime_is_reused_before_any_transition_or_start() -> None:
    source = SOURCE.read_text()
    main = source.split('int main(void) {', 1)[1]
    qualification = main.index('qualify_source(repository, python)')
    lock = main.index('acquire_launcher_lock(repository)')
    reuse = main.index(
        'if (!bootstrap && !replacement && !recovery && backend_is_reusable(control_path)) '
        'return open_workspace();'
    )
    listener = main.index('int socket_connected = connect_backend();')
    start = main.index('BackendStartResult start_result = start_backend(')
    assert qualification < lock < reuse < listener < start
    assert (
        'if (!bootstrap && !replacement && !recovery) return show_existing_backend_unhealthy();'
        in main
    )
    assert main.count('start_backend(') == 1
    reusable = source.split('static int backend_is_reusable(', 1)[1].split(
        'static int backend_supports_maintenance(', 1
    )[0]
    assert 'backend_is_ready()' in reusable
    assert 'read_control_record(control_path' in reusable
    assert 'kill(backend_pid, 0) == 0' in reusable


def test_workspace_focuses_existing_kronos_tab_and_refreshes_only_canonical_stale_tab(
    tmp_path,
) -> None:
    source = SOURCE.read_text()
    workspace = source.split('static int open_workspace(void) {', 1)[1].split(
        'static int acquire_launcher_lock(', 1
    )[0]
    assert 'tell application \\"Google Chrome\\"' in source
    assert 'URL of browserTab starts with \\"http://127.0.0.1:8947/\\"' in source
    assert 'set active tab index of browserWindow to tabNumber' in source
    assert 'set index of browserWindow to 1' in source
    assert ('if URL of browserTab is \\"http://127.0.0.1:8947/swing/opportunities\\" then '
            '"') in source
    assert 'open location \\"http://127.0.0.1:8947/swing/opportunities\\"' in source
    assert '"/usr/bin/open"' not in workspace
    script = subprocess.run(
        [str(compile_workspace_script_harness(tmp_path))],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    compiled = tmp_path / 'workspace.scpt'
    subprocess.run(
        ['/usr/bin/osacompile', '-e', script, '-o', str(compiled)],
        check=True,
        capture_output=True,
    )
    assert compiled.is_file()


def test_launcher_lock_serializes_concurrent_cold_clicks_without_creating_a_lock_file(
    tmp_path,
) -> None:
    binary = compile_launcher_lock_harness(tmp_path)
    repository = tmp_path / 'repository'
    repository.mkdir()
    before = tuple(repository.iterdir())
    holder = subprocess.Popen(
        [str(binary), 'hold', str(repository)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert holder.stdout is not None and holder.stdout.readline() == 'LOCKED\n'
    waiter = subprocess.Popen(
        [str(binary), 'acquire', str(repository)],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert waiter.stdout is not None
    selector = selectors.DefaultSelector()
    selector.register(waiter.stdout, selectors.EVENT_READ)
    assert selector.select(timeout=0.2) == []
    assert holder.stdin is not None
    holder.stdin.write('x')
    holder.stdin.flush()
    holder.stdin.close()
    assert holder.wait(timeout=5) == 0
    assert waiter.stdout.readline() == 'LOCKED\n'
    assert waiter.wait(timeout=5) == 0
    assert tuple(repository.iterdir()) == before


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


# FAILED_ACTIVE recovery: source-proven owner-scope stop. These probes invoke
# neither launcher main nor the live Browser, Provider, stores or runtime.
def _failed_active_scope_probe_server(swing_failure):
    from types import SimpleNamespace
    maintenance = {"protocol": "KRONOS_MAINTENANCE_HANDOFF_V1", "state": "FAILED_ACTIVE", "active": True, "startup": "BLOCKED",
                   "failure": "ACCEPTANCE_RESTORATION_NOT_ESTABLISHED",
                   "generation": "a" * 64}
    completed = []
    governance = SimpleNamespace(
        process=SimpleNamespace(pid=12985, loaded_revision="cbe496e31d466eb28b7b710ffe9231b4324b1137",
                                source_state="CLEAN_COMMIT"),
        maintenance_status=lambda: dict(maintenance),
        complete_startup=completed.append)
    server = SimpleNamespace(
        connection_governance=governance,
        trade_window=SimpleNamespace(paper_observation_projections=lambda: ()),
        visual_v3_live=SimpleNamespace(restoration_error=swing_failure),
        provider_runtime=SimpleNamespace(read_only_status=lambda: {
            "capability_state": "ABSENT", "cleanup_state": "COMPLETE",
            "owned_work_count": 0, "retained_lease_count": 0, "unresolved_cleanup_count": 0}),
        swing_monitoring_hub=SimpleNamespace(active_session_count=0, status_document=lambda: {
            "session_count": 0, "active_session_count": 0, "owner_count": 0,
            "subscription_count": 0, "transport_cleanup": {"state": "COMPLETE"}}),
        application=SimpleNamespace(snapshot=lambda: SimpleNamespace(
            provider_state=SimpleNamespace(value="DISCONNECTED")),
            connection_attempt_status=lambda: None),
        request_capacity_status=lambda: {"active": 1})
    shadow = SimpleNamespace(status=lambda: {
        "failure": "SHADOW_RESTORATION_RUNTIME_INCOMPATIBLE",
        "window": {"retained": True}, "runtime_accepted": False})
    return server, shadow, completed


def test_failed_active_scope_startup_masks_additional_swing_failure():
    from kronos.browser.runtime_state import complete_startup
    without, shadow, clean_results = _failed_active_scope_probe_server(None)
    with_failure, shadow2, failed_results = _failed_active_scope_probe_server(
        "VISUAL_V3_RESTORATION_UNAVAILABLE")
    complete_startup(without, shadow)
    complete_startup(with_failure, shadow2)
    assert clean_results == failed_results == ["ACCEPTANCE_RESTORATION_NOT_ESTABLISHED"]
    assert with_failure.visual_v3_live.restoration_error == "VISUAL_V3_RESTORATION_UNAVAILABLE"


def test_failed_active_scope_runtime_projection_cannot_distinguish_swing_failure():
    from kronos.browser.runtime_state import complete_startup, status_document
    without, shadow, _ = _failed_active_scope_probe_server(None)
    with_failure, shadow2, _ = _failed_active_scope_probe_server(
        "VISUAL_V3_RESTORATION_UNAVAILABLE")
    complete_startup(without, shadow)
    complete_startup(with_failure, shadow2)
    assert status_document(without) == status_document(with_failure)
    assert "VISUAL_V3_RESTORATION_UNAVAILABLE" not in json.dumps(status_document(with_failure))


def _failed_active_scope_documents():
    server, shadow, _ = _failed_active_scope_probe_server(None)
    from kronos.browser.runtime_state import complete_startup, status_document
    complete_startup(server, shadow)
    runtime = status_document(server)
    runtime.update(
        maintenance_claim="DRAINABLE",
        maintenance_drain={"state": "OPEN", "generation": None, "failure": None,
                           "owners": {"SERVER_PULSE": 1}},
        intraday_wo11_work={"state": "IDLE", "continuity": "COMPLETE", "failure": None,
                           "owned_workers": 0, "queued_items": 0},
        intraday_wo17_work={"state": "IDLE", "continuity": "COMPLETE", "failure": None,
                           "owned_workers": 0, "queued_items": 0},
        analysis_work={"state": "IDLE", "owned_work_count": 0, "queued_jobs": 0},
        analysis_execution={"state": "IDLE", "owned_workers": 0, "queued_jobs": 0,
                            "cleanup_state": "COMPLETE", "failure": None, "pid": None},
        housekeeping={"lifecycle_state": "IDLE", "last_failure": None,
                      "shutdown_requested": False, "pass_active": False, "owned_workers": 0},
        swing_bulk_import={"state": "IDLE", "batch_active": False})
    return runtime, {"service": "KRONOS_BROWSER_V1", "runtime_ready": False, "provider": "DISCONNECTED", "maintenance": dict(runtime["maintenance"])}, {
        "active_operation_identity": None, "current_failure": None, "live_shadow": {
            "failure": "SHADOW_RESTORATION_RUNTIME_INCOMPATIBLE", "runtime_accepted": False,
            "epoch_failure": None, "publication_hook_failure": None}}


def test_failed_active_scope_c_admission_does_not_require_predecessor_health(tmp_path):
    # R2 CA supersession: masked predecessor health is not admission authority.
    # This probe proves only that fact; durable continuity is separately required.
    runtime, status, intraday = _failed_active_scope_documents()
    documents = [json.dumps(item) for item in (runtime, status, intraday)]
    literals = [json.dumps(item) for item in documents]
    source = SOURCE.read_text().replace('int main(void) {', 'int unused_application_main(void) {')
    source += "\nint main(void) { RecoveryAuthorization a={0}; a.pid=12985; "
    source += 'strcpy(a.predecessor,RECOVERY_PREDECESSOR); memset(a.maintenance,\'a\',64); '
    source += f'int admitted=recovery_runtime_matches(&a,{literals[0]},{literals[1]},{literals[2]}); '
    source += 'printf("%d\\n",admitted); return 0; }\n'
    executable = tmp_path / 'recovery-scope-probe'
    compile_source(source, executable)
    result = subprocess.run([str(executable)], check=True, text=True, capture_output=True)
    assert result.stdout.strip() == "1"


@pytest.mark.parametrize("domain", ["WO11", "WO17"])
def test_failed_active_r4_successor_startup_rejects_required_domain_failure(tmp_path, monkeypatch, domain):
    """Scope blocker: real domain owner reports failure, shared startup misses it.

    Disposable stores and fake server only. This is not a production restoration
    or a complete canonical-server acceptance test.
    """
    from types import SimpleNamespace
    from kronos.browser.runtime_state import complete_startup, status_document
    from kronos.common.connection_governance import ConnectionProcess, ConnectionAuditStore, ConnectionGovernance
    from kronos.application.intraday_lifecycle import IntradayLifecycleApplication
    from kronos.intraday.wo11_lifecycle_store import LifecycleStore
    from kronos.intraday.wo17_persistence import Wo17Store
    from kronos.application.intraday_wo17 import IntradayWo17RestorationService

    healthy, shadow, healthy_results = _failed_active_scope_probe_server(None)
    failed, _, failed_results = _failed_active_scope_probe_server(None)
    # Simulate an accepted/restored successor WO06H; no record is retained.
    shadow.status = lambda: {"failure": None, "window": None, "runtime_accepted": True}
    def read_failed():
        raise OSError("isolated restoration read failure")
    if domain == "WO11":
        store = LifecycleStore(tmp_path / "wo11")
        monkeypatch.setattr(store, "restore", read_failed)
        owner = IntradayLifecycleApplication(futures=None, store=store, clock=lambda: None,
            session_source=None, timing_source=None, operational_guard=lambda: None)
        assert owner.last_failure == "WO11_RESTORATION_FAILED"
        assert owner.work_status()["failure"] is None
        assert owner.work_status()["continuity"] == "COMPLETE"
        failed.intraday_lifecycle = owner
    else:
        store = Wo17Store(tmp_path / "wo17")
        monkeypatch.setattr(store, "restore_all", read_failed)
        restored = IntradayWo17RestorationService(store=store).restore()
        assert restored.state.value == "CORRUPT"
        assert restored.failure_reason == "WO17_RESTORATION_FAILED"
        failed.intraday_runtime = SimpleNamespace(wo17_restored=restored)
    process = ConnectionProcess(pid=4242, startup_at="2026-10-10T12:00:00+05:30",
        runtime_identity="b" * 64, loaded_revision="f927747e9a8f9b656026fbab7a179fbac5eef8bf",
        source_state="CLEAN_COMMIT")
    for name, server in (("healthy", healthy), ("failed", failed)):
        server.connection_governance = ConnectionGovernance(process,
            ConnectionAuditStore(tmp_path / name), maintenance_identity="a" * 64,
            clock=lambda: datetime(2026, 10, 10, tzinfo=UTC))
        wo11 = getattr(server, "intraday_lifecycle", SimpleNamespace(last_failure=None))
        wo17 = dict(restoration_state="NOT_YET_RUN", failure_stage=None, failure_reason=None, current_positions=[])
        if name == "failed" and domain == "WO17":
            wo17.update(restoration_state=restored.state.value, failure_stage=restored.failure_stage,
                        failure_reason=restored.failure_reason)
        complete_startup(server, shadow, wo11=wo11, wo17=wo17,
            swing_outcomes=tuple((key, "SUCCESS") for key in
                ("LEGACY_MTF", "LEGACY_NATIVE", "NATIVE_REVIEW", "V3_RECORDS", "V3_RESTORE", "TRADE_WINDOW")))
        assert server.connection_governance.startup_state == ("READY" if name == "healthy" else "BLOCKED")
        assert server.connection_governance.maintenance_active == (name == "failed")
        assert len(list((tmp_path / name / "maintenance").glob("*-startup.json"))) == (1 if name == "healthy" else 0)


@pytest.mark.parametrize('raw,expected', [
    ('p12985\nf7\nn127.0.0.1:8947\n', 1),
    ('p12985\nf17\nn127.0.0.1:8947\n', 1),
    ('p12985\nn127.0.0.1:8947\n', 0),
    ('p12985\nf\nn127.0.0.1:8947\n', 0),
    ('p12986\nf7\nn127.0.0.1:8947\n', 0),
    ('p12985\nf7\nn*:8947\n', 0),
    ('p12985\nf7\nn127.0.0.1:8947\np42\nf8\nn127.0.0.1:8947\n', 0),
    ('p12985\nf7\nn127.0.0.1:8947\nf8\nn127.0.0.1:8947\n', 0),
])
def test_r4_listener_requires_one_exact_process_file_address(tmp_path, raw, expected):
    source = SOURCE.read_text().replace('int main(void) {', 'int unused_application_main(void) {')
    source += '\nint main(void) { printf("%d\\n", recovery_listener_record(' + json.dumps(raw) + ',12985)); return 0; }\n'
    executable = tmp_path/'listener-probe'
    compile_source(source, executable)
    assert subprocess.check_output([str(executable)], text=True).strip() == str(expected)


def test_r4_authorization_reservation_is_durable_readback_and_one_use(tmp_path):
    root = tmp_path.resolve()/'authorization'
    root.mkdir(mode=0o700)
    auth = root/'authorization.json'
    auth.write_text('{}')
    auth.chmod(0o600)
    source = SOURCE.read_text().replace('int main(void) {', 'int unused_application_main(void) {')
    source += '\nint main(void) { RecoveryAuthorization a={0};'
    source += f'strcpy(a.root,{json.dumps(str(root))});strcpy(a.file,{json.dumps(str(auth))});'
    source += '''memset(a.attempt,'a',64); a.pid=12985; a.valid_from=RECOVERY_START_US;
    a.valid_until=RECOVERY_END_US; char generation[65]={0};memset(generation,'b',64);
    if(!recovery_file_digest(a.file,a.digest,1))return 2;
    int first=recovery_reserve(&a,generation,RECOVERY_START_US+1);
    int replay=recovery_reserve(&a,generation,RECOVERY_START_US+2);
    printf("%d %d\\n",first,replay);return 0;}'''
    executable=tmp_path/'reservation-probe'
    compile_source(source,executable)
    assert subprocess.check_output([str(executable)],text=True).strip() == '1 0'
    retained = root/('a'*64+'.attempt.json')
    value=json.loads(retained.read_text())
    assert value['generation']=='b'*64 and value['predecessor_pid']==12985
    assert retained.stat().st_mode & 0o777 == 0o600


def test_r4_rollback_is_separate_canonical_resolved_bundle(tmp_path):
    installed=tmp_path.resolve()/'installed.app'; installed.mkdir()
    rollback=tmp_path.resolve()/'rollback.app'; rollback.mkdir()
    alias=tmp_path.resolve()/'alias.app'; alias.symlink_to(installed,target_is_directory=True)
    source=SOURCE.read_text().replace('int main(void) {','int unused_application_main(void) {')
    source+='\nint main(void) {'
    for path in (rollback,installed,alias):
        source+='printf("%d ",recovery_separate_bundle('+json.dumps(str(path))+','+json.dumps(str(installed))+'));'
    source+='return 0;}'
    executable=tmp_path/'rollback-probe';compile_source(source,executable)
    assert subprocess.check_output([str(executable)],text=True).strip()=='1 0 0'


@pytest.fixture(scope="module")
def recovery_documents_probe(tmp_path_factory):
    root = tmp_path_factory.mktemp("recovery-documents")
    source = SOURCE.read_text().replace('int main(void) {', 'int unused_application_main(void) {')
    source += r'''
int main(int argc,char **argv) {
    if(argc!=4)return 2;
    char runtime[BACKEND_STATUS_RESPONSE_BYTES],status[BACKEND_STATUS_RESPONSE_BYTES],intraday[BACKEND_STATUS_RESPONSE_BYTES];
    if(!recovery_read_file(argv[1],runtime,sizeof(runtime),0) ||
       !recovery_read_file(argv[2],status,sizeof(status),0) ||
       !recovery_read_file(argv[3],intraday,sizeof(intraday),0))return 3;
    RecoveryAuthorization a={0};a.pid=12985;strcpy(a.predecessor,RECOVERY_PREDECESSOR);memset(a.maintenance,'a',64);
    printf("%d\n",recovery_runtime_matches(&a,runtime,status,intraday));return 0;
}
'''
    executable = root / "probe"
    compile_source(source, executable)
    return executable


@pytest.mark.parametrize("fault", [None, "status_generation", "status_failure", "missing_status_maintenance",
    "status_service", "runtime_pid", "runtime_revision", "wrong_incident", "claimed", "fenced",
    "unknown_owner", "provider_connected", "provider_lease", "broker_operation", "wo11_incomplete",
    "analysis_running", "monitoring", "housekeeping", "bulk", "shadow_failure"])
def test_recovery_cross_documents_and_actual_owners(recovery_documents_probe, tmp_path, fault):
    runtime, status, intraday = _failed_active_scope_documents()
    if fault == "status_generation": status["maintenance"]["generation"] = "b" * 64
    elif fault == "status_failure": status["maintenance"]["failure"] = "OTHER"
    elif fault == "missing_status_maintenance": del status["maintenance"]
    elif fault == "status_service": status["service"] = "OTHER"
    elif fault == "runtime_pid": runtime["process"]["pid"] += 1
    elif fault == "runtime_revision": runtime["process"]["revision"] = "b" * 40
    elif fault == "wrong_incident": runtime["maintenance"]["failure"] = "OTHER"
    elif fault == "claimed": runtime["maintenance_drain"]["generation"] = "b" * 64
    elif fault == "fenced": runtime["maintenance_drain"]["state"] = "FENCED"
    elif fault == "unknown_owner": runtime["maintenance_drain"]["owners"]["UNKNOWN"] = 1
    elif fault == "provider_connected": status["provider"] = "CONNECTED"
    elif fault == "provider_lease": runtime["provider_runtime"]["retained_lease_count"] = 1
    elif fault == "broker_operation": intraday["active_operation_identity"] = "ACTIVE"
    elif fault == "wo11_incomplete": runtime["intraday_wo11_work"]["continuity"] = "INCOMPLETE"
    elif fault == "analysis_running": runtime["analysis_execution"]["owned_workers"] = 1
    elif fault == "monitoring": runtime["monitoring"]["session_count"] = 1
    elif fault == "housekeeping": runtime["housekeeping"]["pass_active"] = True
    elif fault == "bulk": runtime["swing_bulk_import"]["batch_active"] = True
    elif fault == "shadow_failure": intraday["live_shadow"]["failure"] = "OTHER"
    paths = []
    for index, document in enumerate((runtime, status, intraday)):
        path = tmp_path.resolve() / str(index)
        path.write_text(json.dumps(document))
        paths.append(str(path))
    assert subprocess.check_output([str(recovery_documents_probe), *paths], text=True).strip() == ("1" if fault is None else "0")


@pytest.mark.parametrize("owner", ["WO11", "WO17", "HOUSEKEEPING"])
@pytest.mark.parametrize("fault", [None, "unaccounted", "undercounted", "failure", "generation_missing"])
def test_recovery_admits_known_counted_workers_until_final_drain(recovery_documents_probe, tmp_path, owner, fault):
    runtime, status, intraday = _failed_active_scope_documents()
    runtime["maintenance_drain"]["owners"][owner] = 1
    if owner == "HOUSEKEEPING":
        work = runtime["housekeeping"]
        work.update(lifecycle_state="RUNNING", owned_workers=1, worker_generation=4, pass_active=True)
        generation, failure = "worker_generation", "last_failure"
    else:
        work = runtime["intraday_" + owner.lower() + "_work"]
        work.update(state="RUNNING", owned_workers=1, queued_items=3, generation=4)
        generation, failure = "generation", "failure"
    if fault == "unaccounted": del runtime["maintenance_drain"]["owners"][owner]
    elif fault == "undercounted": work["owned_workers"] = 2
    elif fault == "failure": work[failure] = "FAILED"
    elif fault == "generation_missing": del work[generation]
    paths = []
    for index, document in enumerate((runtime, status, intraday)):
        path = tmp_path.resolve() / str(index); path.write_text(json.dumps(document)); paths.append(str(path))
    assert subprocess.check_output([str(recovery_documents_probe), *paths], text=True).strip() == ("1" if fault is None else "0")


@pytest.fixture(scope="module")
def recovery_authorization_probe(tmp_path_factory):
    import hashlib
    root = tmp_path_factory.mktemp("authorization-binding").resolve()
    installed = root / "installed.app"; installed.mkdir()
    constants = {}
    for name in ("relation", "diagnosis", "sponsor"):
        path = root / name
        path.write_text(name)
        constants[name] = (str(path), hashlib.sha256(path.read_bytes()).hexdigest())
    source = SOURCE.read_text().replace('int main(void) {', 'int unused_application_main(void) {')
    source = source.replace('static const char *canonical_bundle = "/Applications/KRONOS.app";',
        'static const char *canonical_bundle = ' + json.dumps(str(installed)) + ';')
    for name in ("relation", "diagnosis"):
        import re
        source = re.sub(r'#define RECOVERY_' + name.upper() + r' "[^"]+"',
            '#define RECOVERY_' + name.upper() + ' "' + constants[name][1] + '"', source)
    source += r'''
int main(int argc,char **argv) {
    if(argc!=5)return 2;
    RecoveryAuthorization a={0};
    printf("%d\n",recovery_load_authorization(argv[1],argv[2],argv[3],12985,argv[4],RECOVERY_START_US+1,&a));return 0;
}
'''
    executable = root / "probe"; compile_source(source, executable)
    return executable, installed, constants


@pytest.mark.parametrize("fault", [None, "missing", "state", "class", "attempt", "pid", "predecessor",
    "successor", "control", "capability", "relation", "diagnosis", "sponsor", "window", "expiry",
    "future", "same_rollback", "schema", "unknown", "duplicate"])
def test_recovery_authorization_exact_bindings(recovery_authorization_probe, tmp_path, fault):
    import hashlib
    executable, installed, constants = recovery_authorization_probe
    root = tmp_path.resolve(); root.chmod(0o700)
    control = root / "control"; control.write_text("KRONOS_BROWSER_BACKEND_CONTROL_V1\n12985\n" + "d" * 64 + "\n"); control.chmod(0o600)
    rollback = root / "rollback.app"; rollback.mkdir()
    document = dict(schema="KRONOS-FAILED-ACTIVE-RECOVERY-AUTHORIZATION/1.0.0",
        recovery_class="FAILED_ACTIVE_RECOVERY_REPLACEMENT", state="SPONSOR_APPROVED", attempt_identity="a" * 64,
        sponsor_authorization_reference="EXACT-DISPOSABLE-TEST", sponsor_authorization_path=constants["sponsor"][0],
        sponsor_authorization_sha256=constants["sponsor"][1], predecessor_pid=12985,
        predecessor_revision="cbe496e31d466eb28b7b710ffe9231b4324b1137", successor_revision="b" * 40,
        expected_successor_capability="WO06H-CAPABILITY-9104752f2f4028b169cd5bcc249477024eb67b1ab2351a30415e40e5fa7e6e40",
        compatibility_relation_sha256=constants["relation"][1], diagnosis_sha256=constants["diagnosis"][1],
        window_start="2026-09-12T07:50:33.006722+05:30", window_end="2026-10-12T07:50:33.006722+05:30",
        predecessor_maintenance_identity="a" * 64, private_control_sha256=hashlib.sha256(control.read_bytes()).hexdigest(),
        installed_package_identity="b" * 64, rollback_bundle=str(rollback), rollback_package_identity="c" * 64,
        relation_path=constants["relation"][0], diagnosis_path=constants["diagnosis"][0],
        valid_from_us=1789179633006722, valid_until_us=1791771633006722)
    changes = {"state": ("state", "PENDING"), "class": ("recovery_class", "OTHER"), "attempt": ("attempt_identity", "b" * 64),
        "pid": ("predecessor_pid", 12986), "predecessor": ("predecessor_revision", "0" * 40), "successor": ("successor_revision", "0" * 40),
        "control": ("private_control_sha256", "0" * 64), "capability": ("expected_successor_capability", "WRONG"),
        "relation": ("compatibility_relation_sha256", "0" * 64), "diagnosis": ("diagnosis_sha256", "0" * 64),
        "sponsor": ("sponsor_authorization_sha256", "0" * 64), "window": ("window_end", "2027-10-12T07:50:33.006722+05:30"),
        "expiry": ("valid_until_us", 1789179633006723), "future": ("valid_from_us", 1789179633006724),
        "same_rollback": ("rollback_bundle", str(installed)), "schema": ("schema", "WRONG"), "unknown": ("unknown", True)}
    if fault in changes: document[changes[fault][0]] = changes[fault][1]
    path = root / ("a" * 64 + ".authorization.json")
    if fault != "missing":
        raw = json.dumps(document)
        if fault == "duplicate": raw = raw[:-1] + ',"state":"SPONSOR_APPROVED"}'
        path.write_text(raw); path.chmod(0o600)
    result = subprocess.check_output([str(executable), str(root), "a" * 64, str(control), "b" * 40], text=True)
    assert result.strip() == ("1" if fault is None else "0")


def test_recovery_helper_timeout_and_explicit_import_path(tmp_path):
    source = SOURCE.read_text().replace('int main(void) {', 'int unused_application_main(void) {')
    source += r'''
int main(int argc,char **argv) {
    if(argc!=3)return 2;
    char output[PATH_MAX*2+2];
    char *path_args[]={argv[2],"-c","import os; print(os.environ['PYTHONPATH'])",NULL};
    if(!recovery_run_helper(argv[1],argv[2],path_args,NULL,output,sizeof(output),0))return 3;
    printf("%s",output);
    struct timespec before,deadline,after;clock_gettime(CLOCK_MONOTONIC,&before);deadline=before;
    deadline.tv_nsec+=150000000;if(deadline.tv_nsec>=1000000000){deadline.tv_sec++;deadline.tv_nsec-=1000000000;}
    recovery_io_deadline=&deadline;
    char *stall_args[]={argv[2],"-c","import time; time.sleep(1); print('TOO LATE')",NULL};
    int accepted=recovery_run_helper(argv[1],argv[2],stall_args,NULL,output,sizeof(output),0);
    clock_gettime(CLOCK_MONOTONIC,&after);recovery_io_deadline=NULL;
    double elapsed=(after.tv_sec-before.tv_sec)+(after.tv_nsec-before.tv_nsec)/1000000000.0;
    printf("%d %.3f\n",accepted,elapsed);
    /* Reap this read-only fixture helper after measuring timeout behavior. */
    while(waitpid(-1,NULL,0)<0&&errno==EINTR){}return 0;
}
'''
    binary = tmp_path / "helper-timeout"; compile_source(source, binary)
    result = subprocess.run([str(binary), str(tmp_path), sys.executable], check=True, capture_output=True, text=True, timeout=5)
    path, measurement = result.stdout.splitlines()
    assert path == f"{tmp_path}/src:{tmp_path}"
    accepted, elapsed = measurement.split()
    assert accepted == "0" and float(elapsed) < .75


def test_recovery_http_stall_cannot_extend_deadline(tmp_path):
    source = SOURCE.read_text().replace('int main(void) {', 'int unused_application_main(void) {')
    source += r'''
int main(void) {
    int sockets[2];if(socketpair(AF_UNIX,SOCK_STREAM,0,sockets)!=0)return 2;
    struct timespec before,deadline,after;clock_gettime(CLOCK_MONOTONIC,&before);deadline=before;
    deadline.tv_nsec+=150000000;if(deadline.tv_nsec>=1000000000){deadline.tv_sec++;deadline.tv_nsec-=1000000000;}
    recovery_io_deadline=&deadline;
    char response[1024];int accepted=read_response(sockets[0],response,sizeof(response));
    clock_gettime(CLOCK_MONOTONIC,&after);recovery_io_deadline=NULL;
    close(sockets[0]);close(sockets[1]);
    printf("%d %.3f\n",accepted,(after.tv_sec-before.tv_sec)+(after.tv_nsec-before.tv_nsec)/1000000000.0);return 0;
}
'''
    binary = tmp_path / "http-timeout"; compile_source(source, binary)
    result = subprocess.run([str(binary)], check=True, capture_output=True, text=True, timeout=3)
    accepted, elapsed = result.stdout.split()
    assert accepted == "-1" and float(elapsed) < .75


@pytest.mark.parametrize("fault", ["generation", "pid", "authorization", "successor", "time", "removed", "corrupt"])
def test_reservation_recheck_detects_changed_or_ambiguous_attempt(tmp_path, fault):
    root = tmp_path.resolve() / "authorization"; root.mkdir(mode=0o700)
    auth = root / "authorization.json"; auth.write_text("{}"); auth.chmod(0o600)
    source = SOURCE.read_text().replace('int main(void) {', 'int unused_application_main(void) {')
    source += '\nint main(void) { RecoveryAuthorization a={0};'
    source += f'strcpy(a.root,{json.dumps(str(root))});strcpy(a.file,{json.dumps(str(auth))});'
    source += r'''
    memset(a.attempt,'a',64);a.pid=12985;a.valid_from=RECOVERY_START_US;a.valid_until=RECOVERY_END_US;
    char generation[65]={0};memset(generation,'b',64);
    if(!recovery_file_digest(a.file,a.digest,1) || !recovery_reserve(&a,generation,RECOVERY_START_US+1))return 2;
    if(!recovery_attempt_matches(&a,generation))return 3;
    '''
    changes = {"generation": "generation[0]='c';", "pid": "a.pid++;", "authorization": "a.digest[0]=a.digest[0]=='a'?'b':'a';",
        "successor": "strcpy(a.successor,\"changed\");", "time": "a.reserved_at++;"}
    if fault in changes: source += changes[fault]
    else:
        path = root / ("a" * 64 + ".attempt.json")
        if fault == "removed": source += 'unlink(' + json.dumps(str(path)) + ');'
        else: source += 'FILE *f=fopen(' + json.dumps(str(path)) + ',"w");if(!f)return 4;fputs("{}",f);fclose(f);'
    source += 'printf("%d\\n",recovery_attempt_matches(&a,generation));return 0;}'
    binary = tmp_path / "reservation-recheck"; compile_source(source, binary)
    assert subprocess.check_output([str(binary)], text=True).strip() == "0"


@pytest.fixture(scope="module")
def recovery_orchestration_probe(tmp_path_factory):
    root = tmp_path_factory.mktemp("recovery-orchestration")
    original = SOURCE.read_text()
    source = original.replace('int main(void) {', 'int unused_application_main(void) {')
    source += r'''
static const char *fault;
static int calls_assess=0,calls_continuity=0,calls_binding=0,calls_verify=0,calls_package=0;
static int shutdowns=0,starts=0,reservations=0;
static int step(const char *name,int result) {printf("%s\n",name);return fault&&strcmp(fault,name)==0?0:result;}
static int fake_control(pid_t *pid,char *token) {*pid=12985;memset(token,'d',64);token[64]=0;return step("control",1);}
static int fake_authority(RecoveryAuthorization *a) {
    memset(a,0,sizeof(*a));a->pid=12985;strcpy(a->predecessor,RECOVERY_PREDECESSOR);
    memset(a->package,'b',64);memset(a->rollback_identity,'c',64);strcpy(a->rollback,"/disposable/rollback.app");
    snprintf(a->relation,sizeof(a->relation),"%s/Library/Application Support/KRONOS/evidence/intraday-v1/live-shadow-v1/epochs-v1/WO06H-SUCCESSOR_COMPATIBILITY-4f6aac6c3a9f59fe2e19b788fb6266fec1a239358e71f2abc9f9c9ac4c0731ef.json",getenv("HOME"));
    a->valid_from=RECOVERY_START_US;a->valid_until=RECOVERY_END_US;
    return step("authorization",1);
}
static int fake_package(char *out) {calls_package++;memset(out,calls_package==1?'b':'c',64);out[64]=0;return step(calls_package==1?"installed":"rollback",1);}
static int fake_assess(void) {return step(++calls_assess==1?"assess_initial":"assess_final",1);}
static int fake_continuity(void) {return step(++calls_continuity==1?"continuity_before":"continuity_after",1);}
static int fake_binding(void) {return step(++calls_binding==1?"bindings_before":"bindings_after",1);}
static int fake_verify(void) {return step(++calls_verify==1?"handoff_initial":"handoff_final",1);}
static int fake_reserve(void) {reservations++;return step("reserve",1);}
static int fake_shutdown(void) {shutdowns++;return step("shutdown",1);}
static int fake_kill(void) {errno=ESRCH;return -1;}
static BackendStartResult fake_start(void) {
    starts++;step("start",1);
    if(!strcmp(fault,"child_exit"))return BACKEND_START_CHILD_EXITED;
    if(!strcmp(fault,"timeout"))return BACKEND_START_READY_TIMEOUT;
    if(!strcmp(fault,"internal"))return BACKEND_START_INTERNAL_FAILURE;
    return BACKEND_START_READY;
}
#define canonical_operational_image() step("canonical",1)
#define discover_repository(home,repository) (strcpy((repository),(home)),1)
#define access(path,mode) 0
#define qualify_source(repository,python) step("source",1)
#define repository_revision_matches(repository,revision) step("target",1)
#define acquire_launcher_lock(repository) 1
#define recovery_control_record(path,pid,token) fake_control(pid,token)
#define recovery_load_authorization(root,attempt,control,pid,target,now,a) fake_authority(a)
#define recovery_package_identity(repository,python,bundle,out) fake_package(out)
#define recovery_assess(a) fake_assess()
#define connect_backend() open("/dev/null",O_RDONLY)
#define recovery_continuity(repository,python,home,generation) fake_continuity()
#define recovery_bindings_match(a,repository,python,proof) fake_binding()
#define recovery_reserve(a,generation,now) fake_reserve()
#define request_graceful_shutdown(pid,token,generation,v2) fake_shutdown()
#define wait_for_backend_stop(pid) step("exit",1)
#define verify_v2_handoff(repository,python,path,control,generation,pid,revision,proof) fake_verify()
#define recovery_attempt_matches(a,generation) step("attempt_readback",1)
#define kill(pid,signal) fake_kill()
#define recovery_listener_scan(pid,absent) step("listener_absent",1)
#define recovery_now_us() (RECOVERY_START_US+1)
#define start_backend(repository,python,entry,path,pid,token,generation,revision) fake_start()
#define open_workspace() (step("open",1),0)
#define show_restart_blocked() (step("blocked",1),1)
#define show_alert(title,message) 1
#define show_replacement_child_exited() 1
#define show_replacement_ready_timeout() 1
#define show_replacement_internal_failure() 1
'''
    # Run the actual main control flow with only external effects replaced. The
    # unmodified compiled main above keeps all actual production helpers checked.
    source += original.split('int main(void) {', 1)[1].join(['int exercise_main(void) {', ''])
    source += r'''
int main(int argc,char **argv) {
    if(argc!=2)return 2;fault=argv[1];
    setenv("KRONOS_LAUNCH_MODE",RECOVERY_CLASS,1);
    setenv("KRONOS_RECOVERY_ATTEMPT","aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",1);
    setenv("KRONOS_REPLACEMENT_REVISION","bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",1);
    int result=exercise_main();printf("COUNTS %d %d %d %d\n",result,reservations,shutdowns,starts);return 0;
}
'''
    executable = root / "probe"; compile_source(source, executable)
    return executable


@pytest.mark.parametrize("fault", ["none", "authorization", "installed", "rollback", "assess_initial", "continuity_before",
    "assess_final", "bindings_before", "reserve", "shutdown", "exit", "handoff_initial", "continuity_after",
    "bindings_after", "attempt_readback", "handoff_final", "listener_absent", "child_exit", "timeout", "internal"])
def test_actual_recovery_main_orders_one_use_drain_and_one_successor(recovery_orchestration_probe, fault):
    lines = subprocess.check_output([str(recovery_orchestration_probe), fault], text=True).splitlines()
    result, reservations, shutdowns, starts = map(int, lines[-1].split()[1:])
    assert starts <= 1 and shutdowns <= 1 and reservations <= 1
    if fault == "none":
        assert (result, reservations, shutdowns, starts) == (0, 1, 1, 1)
        assert lines.index("continuity_before") < lines.index("reserve") < lines.index("shutdown") < lines.index("exit")
        assert lines.index("exit") < lines.index("handoff_initial") < lines.index("continuity_after") < lines.index("attempt_readback")
        assert lines.index("handoff_final") < lines.index("listener_absent") < lines.index("start") < lines.index("open")
    else:
        assert result == 1 and "open" not in lines
        assert starts == (1 if fault in ("child_exit", "timeout", "internal") else 0)
        if fault in ("authorization", "installed", "rollback", "assess_initial", "continuity_before", "assess_final", "bindings_before", "reserve"):
            assert shutdowns == 0


@pytest.fixture(scope="module")
def recovery_canonical_relation_probe(tmp_path_factory):
    """Exercise the production relation constant without a launcher invocation."""
    import hashlib
    import re
    root = tmp_path_factory.mktemp("canonical-relation-binding").resolve()
    installed = root / "installed.app"
    installed.mkdir()
    diagnosis = root / "diagnosis"
    diagnosis.write_text("disposable diagnosis")
    diagnosis_hash = hashlib.sha256(diagnosis.read_bytes()).hexdigest()
    source = SOURCE.read_text().replace('int main(void) {', 'int unused_application_main(void) {')
    source = source.replace('static const char *canonical_bundle = "/Applications/KRONOS.app";',
        'static const char *canonical_bundle = ' + json.dumps(str(installed)) + ';')
    source = re.sub(r'#define RECOVERY_DIAGNOSIS "[^"]+"',
        '#define RECOVERY_DIAGNOSIS "' + diagnosis_hash + '"', source)
    # RECOVERY_RELATION is deliberately not substituted: this tests the actual
    # production persisted-byte binding, not a fixture-selected hash.
    source += r'''
int main(int argc,char **argv) {
    if(argc!=5)return 2;
    RecoveryAuthorization a={0};
    printf("%d\n",recovery_load_authorization(argv[1],argv[2],argv[3],12985,argv[4],RECOVERY_START_US+1,&a));return 0;
}
'''
    executable = root / "probe"
    compile_source(source, executable)
    return executable, diagnosis, diagnosis_hash


@pytest.mark.parametrize("representation,claimed_hash,accepted", [
    ("canonical", "canonical", True),
    ("review", "review", False),
    ("review", "canonical", False),
    ("canonical", "review", False),
    ("other", "other", False),
    ("other", "canonical", False),
    ("mutated", "canonical", False),
])
def test_recovery_requires_exact_canonical_relation_bytes(
        recovery_canonical_relation_probe, tmp_path, representation, claimed_hash, accepted):
    import hashlib
    from kronos.intraday.population_measurement import canonical
    executable, diagnosis, diagnosis_hash = recovery_canonical_relation_probe
    review_hash = "e5d63954815ffa526390e1d5d0e668a8c490371ead305c85a14b43d6c300c58e"
    persisted_hash = "707ca654076df91af1935d082a569d8d8c0335f52a08d63a8047ea1a94e4e48b"
    review = (ROOT / "tests/fixtures/intraday/wo06h_r5_relation_binding/FINAL-DIRECT-SUCCESSOR-RELATION.json").read_bytes()
    value = json.loads(review)
    persisted = canonical(value)
    assert hashlib.sha256(review).hexdigest() == review_hash
    assert hashlib.sha256(persisted).hexdigest() == persisted_hash
    if representation == "mutated":
        value["body"]["direction"] = "TARGET_TO_SOURCE"
    raw = {"canonical": persisted, "review": review, "other": b"other relation", "mutated": canonical(value)}[representation]
    root = tmp_path.resolve()
    root.chmod(0o700)
    relation = root / "relation.json"
    relation.write_bytes(raw)
    sponsor = root / "sponsor"
    sponsor.write_text("disposable Sponsor authorization")
    control = root / "control"
    control.write_text("KRONOS_BROWSER_BACKEND_CONTROL_V1\n12985\n" + "d" * 64 + "\n")
    control.chmod(0o600)
    rollback = root / "rollback.app"
    rollback.mkdir()
    hashes = dict(canonical=persisted_hash, review=review_hash, other=hashlib.sha256(raw).hexdigest())
    document = dict(schema="KRONOS-FAILED-ACTIVE-RECOVERY-AUTHORIZATION/1.0.0",
        recovery_class="FAILED_ACTIVE_RECOVERY_REPLACEMENT", state="SPONSOR_APPROVED", attempt_identity="a" * 64,
        sponsor_authorization_reference="EXACT-DISPOSABLE-CANONICAL-BINDING-TEST", sponsor_authorization_path=str(sponsor),
        sponsor_authorization_sha256=hashlib.sha256(sponsor.read_bytes()).hexdigest(), predecessor_pid=12985,
        predecessor_revision="cbe496e31d466eb28b7b710ffe9231b4324b1137", successor_revision="b" * 40,
        expected_successor_capability="WO06H-CAPABILITY-9104752f2f4028b169cd5bcc249477024eb67b1ab2351a30415e40e5fa7e6e40",
        compatibility_relation_sha256=hashes[claimed_hash], diagnosis_sha256=diagnosis_hash,
        window_start="2026-09-12T07:50:33.006722+05:30", window_end="2026-10-12T07:50:33.006722+05:30",
        predecessor_maintenance_identity="a" * 64, private_control_sha256=hashlib.sha256(control.read_bytes()).hexdigest(),
        installed_package_identity="b" * 64, rollback_bundle=str(rollback), rollback_package_identity="c" * 64,
        relation_path=str(relation), diagnosis_path=str(diagnosis),
        valid_from_us=1789179633006722, valid_until_us=1791771633006722)
    assert len(document) == 24  # Existing closed authorization schema is preserved.
    path = root / ("a" * 64 + ".authorization.json")
    path.write_text(json.dumps(document))
    path.chmod(0o600)
    result = subprocess.check_output([str(executable), str(root), "a" * 64, str(control), "b" * 40], text=True)
    assert result.strip() == ("1" if accepted else "0")


def test_recovery_review_provenance_is_separate_from_production_binding():
    import re
    source = SOURCE.read_text()
    reviewed = re.search(r'#define RECOVERY_REVIEW_ARTIFACT_SHA256 "([0-9a-f]{64})"', source).group(1)
    persisted = re.search(r'#define RECOVERY_RELATION "([0-9a-f]{64})"', source).group(1)
    assert reviewed == "e5d63954815ffa526390e1d5d0e668a8c490371ead305c85a14b43d6c300c58e"
    assert persisted == "707ca654076df91af1935d082a569d8d8c0335f52a08d63a8047ea1a94e4e48b"
    assert reviewed != persisted
    # Provenance is explicit, but never an alternate byte authorization.
    assert source.count("RECOVERY_REVIEW_ARTIFACT_SHA256") == 1
    assert 'recovery_field(&j,0,"compatibility_relation_sha256",RECOVERY_RELATION)' in source
    assert 'strcmp(actual,RECOVERY_RELATION)' in source
