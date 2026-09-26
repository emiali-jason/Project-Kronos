"""APP-01A: kernel-resolved app path, seal and inert build-only probe."""
import json
import os
from pathlib import Path
import plistlib
import selectors
import shutil
import socket
import subprocess
from threading import Thread

import pytest

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


def replacement_payload(*, revision='a' * 40, worker=False, owners=0):
    return {
        'schema': 'KRONOS-RUNTIME-STATE/1.0.0',
        'process': {'pid': os.getpid(), 'revision': revision, 'source_state': 'CLEAN_COMMIT'},
        'maintenance': {
            'protocol': 'KRONOS_MAINTENANCE_HANDOFF_V1', 'state': 'INACTIVE',
            'active': False, 'generation': 'f' * 64, 'startup': 'READY', 'failure': None,
        },
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


def test_revision_replacement_mode_preserves_ordinary_dock_reuse_contract():
    source = SOURCE.read_text()
    main = source.split('int main(void) {', 1)[1]
    assert 'strcmp(mode, "GOVERNED_REPLACEMENT") == 0' in main
    assert 'KRONOS_REPLACEMENT_REVISION' in main
    assert (
        'if (!bootstrap && !replacement && backend_is_reusable(control_path)) '
        'return open_workspace();'
    ) in main
    readiness = main.index('backend_replacement_readiness(')
    shutdown = main.index('request_graceful_shutdown(backend_pid, token, generation)')
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
    shutdown_call = main.index('request_graceful_shutdown(backend_pid, token, generation)')
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
    monitor = monitor.split('static BackendStartResult start_backend(', 1)[0]
    assert 'kill(' not in monitor
    assert 'fork(' not in monitor
    stop = source.split('static int wait_for_backend_stop(', 1)[1]
    stop = stop.split('static int qualify_source(', 1)[0]
    assert 'process_gone && socket_fd < 0' in stop


def test_ready_runtime_is_reused_before_any_transition_or_start() -> None:
    source = SOURCE.read_text()
    main = source.split('int main(void) {', 1)[1]
    qualification = main.index('qualify_source(repository, python)')
    lock = main.index('acquire_launcher_lock(repository)')
    reuse = main.index(
        'if (!bootstrap && !replacement && backend_is_reusable(control_path)) '
        'return open_workspace();'
    )
    listener = main.index('int socket_connected = connect_backend();')
    start = main.index('BackendStartResult start_result = start_backend(')
    assert qualification < lock < reuse < listener < start
    assert (
        'if (!bootstrap && !replacement) return show_existing_backend_unhealthy();'
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
