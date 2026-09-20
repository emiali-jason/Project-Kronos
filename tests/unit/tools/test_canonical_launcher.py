"""APP-01A: kernel-resolved app path, seal and inert build-only probe."""
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess

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


def test_shutdown_rejection_and_start_results_route_without_retry_or_kill():
    source = SOURCE.read_text()
    main = source.split('int main(void) {', 1)[1]
    start_call = main.index('BackendStartResult start_result = start_backend(')
    assert main.index('return show_restart_blocked();') < start_call
    token_clear = main.index('(void)memset(token, 0, sizeof(token));', start_call)
    result_switch = main.index('switch (start_result)', start_call)
    assert start_call < token_clear < result_switch
    assert main.count('start_backend(') == 1
    assert main.count('open_workspace()') == 1
    assert main.index('case BACKEND_START_READY:') < main.index('open_workspace()')
    monitor = source.split('static BackendStartResult monitor_backend_start(', 1)[1]
    monitor = monitor.split('static BackendStartResult start_backend(', 1)[0]
    assert 'kill(' not in monitor
    assert 'fork(' not in monitor


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
