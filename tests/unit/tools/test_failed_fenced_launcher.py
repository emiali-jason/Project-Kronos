"""R3 bootstrap transport/source qualification in the kernel-isolated harness."""
from __future__ import annotations

from dataclasses import replace
import fcntl
import os
from pathlib import Path
import struct
import subprocess
import sys
import threading
import time

import pytest

from kronos.common.failed_fenced_startup import (
    CompositionLatch, NativeBootstrap, RecoveryStartupError, SELECTORS,
    receive_composition_frame, run_native_helper, selectors, send_composition_frame,
)


class Budget:
    """Synthetic qualified same-boot budget; never a production authority."""
    def __init__(self, seconds=1):
        self.deadline = self.now_ns() + int(seconds * 1e9)

    def now_ns(self):
        return time.clock_gettime_ns(time.CLOCK_MONOTONIC)

    def check(self, deadline_ns=None):
        if self.now_ns() >= min(self.deadline, self.deadline if deadline_ns is None else deadline_ns):
            raise RecoveryStartupError("TEST_REMAINING_BUDGET_EXPIRED")

    def remaining_seconds(self, deadline_ns=None):
        self.check(deadline_ns)
        return (min(self.deadline, self.deadline if deadline_ns is None else deadline_ns) - self.now_ns()) / 1e9


def test_recovery_selectors_are_locators_not_partial_or_mixed_authority():
    valid = dict(zip(SELECTORS, ("1.0.0", "a" * 64, "b" * 64)))
    assert selectors(valid) == ("a" * 64, "b" * 64)
    assert selectors({}) is None
    assert valid == dict(zip(SELECTORS, ("1.0.0", "a" * 64, "b" * 64)))


@pytest.mark.parametrize("fault", ["missing_version", "missing_slot", "missing_nonce", "version", "slot", "nonce",
                                  "extra", "ordinary", "legacy", "mode"])
def test_recovery_selector_denials(fault):
    env = dict(zip(SELECTORS, ("1.0.0", "a" * 64, "b" * 64)))
    if fault.startswith("missing_"):
        env.pop(SELECTORS[{"missing_version": 0, "missing_slot": 1, "missing_nonce": 2}[fault]])
    elif fault in {"version", "slot", "nonce"}:
        env[SELECTORS[{"version": 0, "slot": 1, "nonce": 2}[fault]]] = "INVALID"
    else:
        env[{"extra": "KRONOS_FAILED_FENCED_RECOVERY_PATH", "ordinary": "KRONOS_MAINTENANCE_GENERATION",
             "legacy": "KRONOS_LEGACY_BOOTSTRAP_ID", "mode": "KRONOS_LAUNCH_MODE"}[fault]] = "x"
    with pytest.raises(RecoveryStartupError, match="SELECTORS_REJECTED"):
        selectors(env)


def _receive(raw, *, keep_open=False, seconds=1, fragment=False):
    read, write = os.pipe()
    finished = threading.Event()
    def writer():
        try:
            if fragment:
                for piece in raw:
                    os.write(write, bytes((piece,)))
            elif raw:
                os.write(write, raw)
            if keep_open:
                finished.wait(2)
        except BrokenPipeError:
            pass
        finally:
            os.close(write)
    thread = threading.Thread(target=writer)
    thread.start()
    try:
        return receive_composition_frame(Budget(seconds), descriptor=read, expected_descriptor=read)
    finally:
        finished.set()
        thread.join()


@pytest.mark.parametrize("size", [1, 128, 8192])
@pytest.mark.parametrize("fragment", [False, True])
def test_one_complete_frame_and_eof_returns_exact_original_bytes(size, fragment):
    raw = b"x" * size
    value, received = _receive(struct.pack("!I", size) + raw, fragment=fragment)
    assert value == raw
    assert received <= time.clock_gettime_ns(time.CLOCK_MONOTONIC)


@pytest.mark.parametrize("raw,reason", [
    (b"", "TRUNCATED"), (b"\x00", "TRUNCATED"),
    (struct.pack("!I", 0), "LENGTH_REJECTED"),
    (struct.pack("!I", 8193), "LENGTH_REJECTED"),
    (struct.pack("!I", 4) + b"abc", "TRUNCATED"),
    (struct.pack("!I", 1) + b"ab", "EXTRA_BYTES"),
    (struct.pack("!I", 1) + b"a" + struct.pack("!I", 1) + b"b", "EXTRA_BYTES"),
])
def test_malformed_truncated_or_second_frame_denied(raw, reason):
    with pytest.raises(RecoveryStartupError, match=reason):
        _receive(raw)


def test_complete_bytes_without_eof_do_not_grant_authority():
    with pytest.raises(RecoveryStartupError, match="BUDGET_EXPIRED"):
        _receive(struct.pack("!I", 1) + b"a", keep_open=True, seconds=.03)


def test_reader_rejects_ordinary_file_and_closes_descriptor(tmp_path):
    p = tmp_path / "grant-file"; p.write_bytes(struct.pack("!I", 1) + b"a")
    fd = os.open(p, os.O_RDONLY)
    with pytest.raises(RecoveryStartupError, match="PIPE_REQUIRED"):
        receive_composition_frame(Budget(), descriptor=fd, expected_descriptor=fd)
    with pytest.raises(OSError):
        os.fstat(fd)


def test_send_closes_writer_and_sets_cloexec_before_transfer():
    read, write = os.pipe()
    original = b"exact authenticated record bytes"
    thread = threading.Thread(target=lambda: send_composition_frame(write, original, Budget()))
    thread.start()
    value, _ = receive_composition_frame(Budget(), descriptor=read, expected_descriptor=read)
    thread.join()
    assert value == original
    with pytest.raises(OSError):
        os.fstat(write)


def test_latch_is_one_use_and_ignores_persisted_bytes():
    latch = CompositionLatch(b"retained", {"kind": "COMPOSITION_AUTHORITY"}, 1, 2)
    budget = Budget()
    assert latch.take(budget, budget.deadline) == {"kind": "COMPOSITION_AUTHORITY"}
    with pytest.raises(RecoveryStartupError, match="LATCH_SPENT"):
        latch.take(budget, budget.deadline)


def test_latch_cannot_reset_expired_ready_deadline():
    latch = CompositionLatch(b"retained", {}, 1, 2)
    with pytest.raises(RecoveryStartupError, match="BUDGET_EXPIRED"):
        latch.take(Budget(), 1)
    with pytest.raises(RecoveryStartupError, match="LATCH_SPENT"):
        latch.take(Budget(), 2**63)


def test_source_helper_passes_exact_output_and_actual_nonzero_failure():
    assert run_native_helper([sys.executable, "-c", "print('native')"], budget=Budget()) == b"native\n"
    with pytest.raises(subprocess.CalledProcessError) as exc:
        run_native_helper([sys.executable, "-c", "raise SystemExit(7)"], budget=Budget())
    assert exc.value.returncode == 7


def test_late_native_helper_is_joined_and_never_cancellation_or_success(tmp_path):
    done = tmp_path / "helper-actually-completed"
    start = time.monotonic()
    with pytest.raises(RecoveryStartupError, match="SOURCE_HELPER_DEADLINE"):
        run_native_helper([sys.executable, "-c", "import time,pathlib;time.sleep(.08);pathlib.Path(" + repr(str(done)) + ").write_text('done')"],
                          budget=Budget(.02))
    assert done.read_text() == "done"
    assert time.monotonic() - start >= .08


def test_native_bootstrap_runtime_remains_exact_startup_identity():
    from tests.unit.intraday.test_runtime_identity import _seed
    from hashlib import sha256
    evidence = _seed(process_id=os.getpid())
    process = {"pid": str(os.getpid()), "kernel_birth": {"seconds": "1", "microseconds": "2"},
               "runtime": sha256(evidence.evidence_identity.encode()).hexdigest()}
    native = NativeBootstrap(evidence, process, (("bootstrap.module", "a" * 64),))
    assert native.validate(expected_process=process, expected_modules=native.modules) is native
    assert native.runtime != "b" * 64
    with pytest.raises(RecoveryStartupError, match="NATIVE_IDENTITY"):
        native.validate(expected_process=process, expected_modules=(("bootstrap.module", "b" * 64),))


def _early_parser():
    """Execute the actual stdlib-only pre-capture definitions, no app import."""
    import ast
    from hashlib import sha256
    path = Path(__file__).parents[3] / "tools/kronos_browser.py"
    # tests/unit/tools -> repository is parents[3]. This extracts the exact
    # definitions so the test cannot substitute a reimplemented parser.
    source = path.read_text()
    tree = ast.parse(source, filename=str(path))
    definitions = [node for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef))
                   and node.name in {"_InheritedRecoveryBudget", "_inherited_recovery_budget"}]
    assert len(definitions) == 2
    namespace = {"os": os, "Path": Path, "sha256": sha256}
    exec(compile(ast.Module(body=definitions, type_ignores=[]), str(path), "exec"), namespace)
    return namespace["_inherited_recovery_budget"]


def _early_records(tmp_path, fault=None):
    import hmac
    import json
    from hashlib import sha256
    root = tmp_path / "recovery-v1"
    slot, nonce = "a" * 64, "b" * 64
    for path in (root, root / "slots", root / "slots" / slot, root / "custody"):
        path.mkdir(mode=0o700)
    control = b"KRONOS_BROWSER_BACKEND_CONTROL_V1\n333\n" + b"c" * 64 + b"\n"
    key_id = sha256(control).hexdigest()
    canonical = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")
    now = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    origin = now - (20_000_000_000 if fault == "stale" else 100_000_000)
    stop = origin + (16_000_000_000 if fault == "extended" else 15_000_000_000)
    clock = {"type": "CLOCK_MONOTONIC", "boot_id": "test-boot", "qualification": {}}
    limits = {"clock": clock, "origin_ns": str(origin), "stop_deadline_ns": str(stop)}
    names = ("slot guard transaction binding authorization scope_approvals control_challenge launcher launcher_capability endpoint limits successor_source successor_capability installed_package rollback_package compatibility").split()
    payload = dict.fromkeys(names)
    payload.update(slot=slot, limits=limits)
    def record(kind, payload):
        value = {"protocol": "KRONOS-FAILED-FENCED-RECOVERY-V1", "version": "1.0.0", "kind": kind,
                 "role": "LAUNCHER", "key_id": key_id, "clock": clock, "issued_ns": str(origin), "payload": payload}
        key = hmac.digest(bytes.fromhex("c" * 64), ("KRONOS-FAILED-FENCED-RECOVERY-V1/1.0.0/key/LAUNCHER/" + key_id).encode("ascii"), "sha256")
        value["mac"] = hmac.new(key, b"KRONOS-FAILED-FENCED-RECOVERY-V1/1.0.0/record\n" + canonical(value), "sha256").hexdigest()
        return canonical(value)
    claim = record("CLAIM", payload)
    intent = record("CHILD_INTENT", {"slot": slot, "child_nonce": nonce,
        "claim": {"kind": "CLAIM", "hash": sha256(claim).hexdigest()}, "limits": limits})
    if fault == "tampered":
        claim = claim.replace(b'"CLAIM"', b'"PLAIN"')
    if fault == "noncanonical":
        claim += b"\n"
    for path, raw in ((root / "slots" / slot / "claim", claim),
                      (root / "slots" / slot / "child-intent", intent),
                      (root / "custody" / (key_id + ".control"), control)):
        path.write_bytes(raw)
        path.chmod(0o600)
    return dict(zip(SELECTORS, ("1.0.0", slot, nonce)))


def test_early_budget_reads_authenticated_inherited_bounds_without_application_imports(tmp_path):
    env = _early_records(tmp_path)
    read, write = os.pipe()
    try:
        budget = _early_parser()(env, estate=tmp_path, _pipe_descriptor=read)
        assert budget.stop_deadline_ns - budget.origin_ns == 15_000_000_000
        assert 0 < budget.remaining_seconds() < 15
        assert fcntl.fcntl(read, fcntl.F_GETFD) & fcntl.FD_CLOEXEC
        assert not hasattr(budget, "registry")  # denial-only timing context
    finally:
        os.close(read)
        os.close(write)


@pytest.mark.parametrize("fault", ["stale", "extended", "tampered", "noncanonical", "wrong_nonce", "private_mode", "symlink", "unknown_selector"])
def test_early_budget_rejects_stale_extended_changed_and_untrusted_bounds(tmp_path, fault):
    env = _early_records(tmp_path, fault)
    claim_path = tmp_path / "recovery-v1/slots" / ("a" * 64) / "claim"
    if fault == "wrong_nonce":
        env[SELECTORS[2]] = "d" * 64
    if fault == "unknown_selector":
        env["KRONOS_FAILED_FENCED_RECOVERY_STOP"] = "fabricated"
    if fault == "private_mode":
        claim_path.chmod(0o644)
    if fault == "symlink":
        preserved = claim_path.with_name("preserved-claim")
        claim_path.rename(preserved)
        claim_path.symlink_to(preserved)
    read, write = os.pipe()
    try:
        with pytest.raises((ValueError, OSError)):
            _early_parser()(env, estate=tmp_path, _pipe_descriptor=read)
    finally:
        os.close(read)
        os.close(write)


def test_native_complete_source_inventory_uses_actual_startup_encoding():
    from kronos.common.failed_fenced_startup import validate_source_inventory_blob
    from kronos.intraday.runtime_identity import canonical
    rows = (("kronos", "a" * 64), ("tools.kronos_browser", "b" * 64))
    assert validate_source_inventory_blob(canonical(rows)) == rows
    for invalid in (rows[::-1], (rows[0], rows[0]), (("arbitrary/path", "a" * 64),)):
        with pytest.raises(RecoveryStartupError):
            validate_source_inventory_blob(canonical(invalid))
    with pytest.raises(RecoveryStartupError):
        validate_source_inventory_blob(canonical(rows) + b"\n")


def test_ready_phase_is_separate_from_shared_stop_budget_and_does_not_resurrect_grant():
    from types import SimpleNamespace
    from kronos.common.failed_fenced_startup import ReadyBudget
    now = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    original = SimpleNamespace(clock={"type": "CLOCK_MONOTONIC"}, origin_ns=now - 20_000_000_000,
                               stop_deadline_ns=now - 5_000_000_000)
    latch = CompositionLatch(b"actual validated live frame", {"payload": {
        "stop_deadline_ns": str(original.stop_deadline_ns), "ready_deadline_ns": str(now + 95_000_000_000)}},
        now - 6_000_000_000, now - 5_500_000_000)
    phase = ReadyBudget(original, latch)
    assert phase.check() >= now
    assert phase.stop_deadline_ns == original.stop_deadline_ns
    latch.take(phase, phase.ready_deadline_ns)
    with pytest.raises(RecoveryStartupError, match="LATCH_REQUIRED"):
        ReadyBudget(original, latch)


def test_actual_c_launcher_compiles_without_weakening_warnings(tmp_path):
    source = Path(__file__).parents[3] / "tools/macos/kronos_launcher.c"
    unit = tmp_path / "unit.c"
    unit.write_text(source.read_text().replace("int main(void) {", "int unused_application_main(void) {")
                    + "\nint main(void) { return 0; }\n")
    result = subprocess.run(["clang", "-Wall", "-Wextra", "-Werror", str(unit), "-o", str(tmp_path / "compiled")], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_actual_darwin_native_birth_observation_preserves_kernel_fields(tmp_path):
    import ctypes
    import json
    from hashlib import sha256
    from types import SimpleNamespace
    from tools.failed_fenced_launcher import DarwinKernelObserver, _ProcBSDInfo
    from kronos.common.failed_fenced_recovery import RecoveryBudget, RecoveryCodec, RecoveryStore, canonical_bytes
    from kronos.common.failed_fenced_startup import validate_platform_evidence
    # Synthetic clock authority and estate, actual current-process libproc
    # observation. No proof in this fixture grants operational permission.
    evidence = {"authority": "PCP", "contract": "test-clock", "identity": "test-clock",
                "hash": "d" * 64, "bytes": "1"}
    clock = {"type": "CLOCK_MONOTONIC", "boot_id": "isolated-test-boot", "qualification": evidence}
    now = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    budget = RecoveryBudget(clock, now, now + 15_000_000_000)
    raw_control = ("KRONOS_BROWSER_BACKEND_CONTROL_V1\n" + str(os.getpid()) + "\n" + "a" * 64 + "\n").encode("ascii")
    codec = RecoveryCodec(raw_control, clock)
    store = RecoveryStore(tmp_path)
    scope = {"schema": "KRONOS_FAILED_FENCED_GUARD_SCOPE_V1", "version": "1.0.0",
             "service": "isolated", "installation": "isolated", "policy": "MANDATORY"}
    store.provision(scope, sha256(canonical_bytes(scope)).hexdigest())
    lib = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
    lib.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
    lib.proc_pidinfo.restype = ctypes.c_int
    info = _ProcBSDInfo()
    assert lib.proc_pidinfo(os.getpid(), 3, 0, ctypes.byref(info), ctypes.sizeof(info)) == 136
    process = {"pid": str(os.getpid()), "kernel_birth": {"seconds": str(info.start_seconds),
               "microseconds": str(info.start_microseconds)}, "runtime": "isolated-runtime"}
    observer = DarwinKernelObserver(codec, store, budget, process)
    before = {str(path.relative_to(tmp_path)): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    observed = observer.process_observation(process)
    retained = observed["native"]
    native = validate_platform_evidence(observed["payload"], retained, SimpleNamespace(store=store), {})
    assert native["return_bytes"] == "136" and native["errno"] == "0"
    assert native["observed_process"] == process
    assert json.loads(retained)["subject"] == process
    assert set(observed) == {"native", "payload"} and "mac" not in observed["payload"]
    assert {str(path.relative_to(tmp_path)): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()} == before
    wrong = dict(process, kernel_birth={"seconds": "0", "microseconds": "0"})
    with pytest.raises(RecoveryStartupError, match="PROCESS_CHANGED"):
        observer.process_observation(wrong)


@pytest.mark.parametrize("entry", ["directory", "partial", "corrupt_file", "dangling_symlink", "unknown_version", "absent_namespace", "absent_estate"])
def test_unprepared_startup_cannot_strip_selectors_to_bypass_enrollment(tmp_path, monkeypatch, entry):
    from tools import kronos_browser
    import pwd
    from types import SimpleNamespace
    fixture_home = tmp_path / "native-account-home"
    estate = fixture_home / "Library/Application Support/KRONOS/runtime"
    if entry != "absent_estate":
        estate.mkdir(parents=True, mode=0o700)
    monkeypatch.setattr(pwd, "getpwuid", lambda uid: SimpleNamespace(pw_dir=str(fixture_home)))
    path = estate / ("recovery-v2" if entry == "unknown_version" else "recovery-v1")
    if entry in {"directory", "partial", "unknown_version"}:
        path.mkdir(mode=0o700)
    elif entry == "corrupt_file":
        path.write_bytes(b"corrupt")
    elif entry == "dangling_symlink":
        path.symlink_to(estate / "missing")
    if entry == "partial":
        (path / "slots").mkdir(mode=0o700)
    redirected = tmp_path / "redirected-home"
    redirected.mkdir()
    monkeypatch.setenv("HOME", str(redirected))
    # Legacy default/config paths deliberately disagree with the source-owned
    # native account. They must never select an empty guard namespace.
    monkeypatch.setattr(kronos_browser, "DEFAULT_BACKEND_CONTROL_PATH", redirected / "browser-backend-v1.control")
    monkeypatch.setattr(kronos_browser, "_RECOVERY_EARLY_BUDGET", None)
    called = []
    monkeypatch.setattr(kronos_browser, "_main", lambda *args, **kwargs: called.append(True))
    with pytest.raises(RecoveryStartupError, match="GUARD_PREPARATION_REQUIRED"):
        kronos_browser.main(["--no-browser"])
    assert called == []


def test_capable_entry_preserves_prepared_ordinary_dispatch(monkeypatch):
    """Dispatch boundary only; full native fixtures validate the preparation."""
    from tools import kronos_browser
    from kronos.common import failed_fenced_startup
    factory = object.__new__(failed_fenced_startup.PreparedRuntimeFactory)
    observed = []
    def acquire(startup, *, origin_ns):
        assert startup is kronos_browser._STARTUP_EVIDENCE
        assert origin_ns == kronos_browser._CANONICAL_ENTRY_ORIGIN_NS
        observed.append("static-validated")
        return factory
    def compose(argv, *, prepared_runtime, recovery_child):
        assert prepared_runtime is factory and recovery_child is None
        observed.append(tuple(argv))
        return 0
    monkeypatch.setattr(kronos_browser, "_RECOVERY_EARLY_BUDGET", None)
    monkeypatch.setattr(failed_fenced_startup, "load_capture_installation", acquire)
    monkeypatch.setattr(kronos_browser, "_main", compose)
    assert kronos_browser.main(["--port", "9123", "--no-browser"]) == 0
    assert observed == ["static-validated", ("--port", "9123", "--no-browser")]


def test_runtime_entry_rejects_unknown_factory_without_constructing_products(tmp_path, monkeypatch):
    from tools import kronos_browser
    monkeypatch.setattr(kronos_browser, "_RECOVERY_EARLY_BUDGET", None)
    with pytest.raises(RecoveryStartupError, match="PROSPECTIVE_RUNTIME_REQUIRED"):
        kronos_browser.main(["--no-browser"], prepared_runtime={"classification": "MANDATORY"})


@pytest.fixture(scope="module")
def native_codec_binary(tmp_path_factory):
    """Compile the actual source into a disposable, inert codec test process."""
    folder = tmp_path_factory.mktemp("native-r3-codec")
    source = Path(__file__).parents[3] / "tools/macos/kronos_launcher.c"
    unit = folder / "codec.c"
    unit.write_text(source.read_text().replace("int main(void) {", "int unused_application_main(void) {") + r'''
int main(int argc,char **argv) {
    if(argc!=5)return 90;
    struct proc_bsdinfo info;memset(&info,0,sizeof(info));
    if(proc_pidinfo(getpid(),PROC_PIDTBSDINFO,0,&info,sizeof(info))!=(int)sizeof(info))return 91;
    char controller[1024],control[256];
    snprintf(controller,sizeof(controller),"{\"kernel_birth\":{\"microseconds\":\"%llu\",\"seconds\":\"%llu\"},\"pid\":\"%ld\",\"runtime\":\"isolated-controller\"}",
        (unsigned long long)info.pbi_start_tvusec,(unsigned long long)info.pbi_start_tvsec,(long)getpid());
    snprintf(control,sizeof(control),"KRONOS_BROWSER_BACKEND_CONTROL_V1\n%ld\n%s\n",(long)getppid(),
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
    FFR3NativeCodec codec;
    if(!ffr3_native_codec_init(&codec,control,argv[2],controller))return 92;
    if(!strcmp(argv[1],"verify"))return ffr3_native_verify(&codec,argv[4],atoi(argv[3]))?0:3;
    char output[16384];size_t size=ffr3_native_encode(&codec,argv[1],atoi(argv[3]),argv[4],123,output,sizeof(output));
    if(size==0)return 4;
    return fwrite(output,1,size,stdout)==size?0:5;
}
''')
    binary = folder / "native-codec"
    compiled = subprocess.run(["clang", "-Wall", "-Wextra", "-Werror", str(unit), "-o", str(binary)], capture_output=True, text=True)
    assert compiled.returncode == 0, compiled.stderr
    return binary


def _native_codec_call(binary, kind, payload, external=False):
    import json
    clock = {"type": "CLOCK_MONOTONIC", "boot_id": "isolated-test-boot", "qualification": {
        "authority": "PCP", "contract": "test-clock", "identity": "test-clock", "hash": "d" * 64, "bytes": "1"}}
    clock_raw = json.dumps(clock, sort_keys=True, separators=(",", ":"))
    result = subprocess.run([str(binary), kind, clock_raw, str(int(external)), payload], capture_output=True)
    return result, clock


@pytest.mark.parametrize("kind,external", [("FAILURE", False), ("CHILD_STARTED", False),
    ("CONTROLLER_ADMISSION", True), ("CONTROLLER_CLOSURE", True)])
def test_actual_c_role_mac_matches_existing_exact_python_domain(native_codec_binary, kind, external):
    import json
    from kronos.common.failed_fenced_recovery import RecoveryCodec, canonical_bytes
    result, clock = _native_codec_call(native_codec_binary, kind, '{"fixture":"unsigned-only-component"}', external)
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    control = ("KRONOS_BROWSER_BACKEND_CONTROL_V1\n" + str(os.getpid()) + "\n" + "a" * 64 + "\n").encode()
    codec = RecoveryCodec(control, clock)
    assert result.stdout == canonical_bytes(value)
    assert value["role"] == "LAUNCHER" and value["key_id"] == codec.key_id
    mac = value.pop("mac")
    assert codec._mac(value, external) == mac
    checked, _ = _native_codec_call(native_codec_binary, "verify", result.stdout.decode(), external)
    assert checked.returncode == 0


@pytest.mark.parametrize("payload", ['{"a":1}', '{"z":"last","a":"first"}',
    '{"a":"x", "b":"y"}', '{"a":"x","a":"x"}', '{"a":"\\u0041"}'])
def test_actual_c_encoder_rejects_noncanonical_or_numeric_payloads(native_codec_binary, payload):
    result, _ = _native_codec_call(native_codec_binary, "FAILURE", payload)
    assert result.returncode == 4 and result.stdout == b""


@pytest.mark.parametrize("fault", ["mac", "role", "clock", "key_id", "protocol", "extra"])
def test_actual_c_verifier_rejects_context_and_domain_tampering(native_codec_binary, fault):
    import json
    from kronos.common.failed_fenced_recovery import canonical_bytes
    result, _ = _native_codec_call(native_codec_binary, "FAILURE", '{"fixture":"component"}')
    assert result.returncode == 0
    value = json.loads(result.stdout)
    if fault == "clock":
        value["clock"]["boot_id"] = "another-boot"
    elif fault == "extra":
        value["unexpected"] = "field"
    else:
        value[fault] = {"mac": "0" * 64, "role": "HELPER", "key_id": "b" * 64, "protocol": "other"}[fault]
    denied, _ = _native_codec_call(native_codec_binary, "verify", canonical_bytes(value).decode())
    assert denied.returncode == 3


@pytest.fixture(scope="module")
def native_io_binary(tmp_path_factory):
    folder = tmp_path_factory.mktemp("native-r3-io")
    source = Path(__file__).parents[3] / "tools/macos/kronos_launcher.c"
    unit = folder / "io.c"
    unit.write_text(source.read_text().replace("int main(void) {", "int unused_application_main(void) {") + r'''
int main(int argc,char **argv) {
    struct timespec now;if(clock_gettime(CLOCK_MONOTONIC,&now)!=0)return 90;
    struct timespec stop=now;stop.tv_sec+=15;
    if(argc==3&&!strcmp(argv[1],"response")){
        int descriptor=atoi(argv[2]);if(fcntl(descriptor,F_SETFL,O_NONBLOCK)!=0)return 97;
        stop=now;stop.tv_sec+=1;char response[8192];
        int length=ffr3_read_original_response(descriptor,response,sizeof(response),&stop);
        if(length<0)return 3;return fwrite(response,1,(size_t)length,stdout)==(size_t)length?0:98;
    }
    if(argc==5 && !strcmp(argv[1],"publish")){
        int directory=open(argv[2],O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);if(directory<0)return 91;
        int valid=ffr3_publish_immutable(directory,argv[3],argv[4],strlen(argv[4]),&stop);close(directory);return valid?0:3;
    }
    if(argc==4&&!strcmp(argv[1],"image")){
        pid_t child=fork();if(child<0)return 94;
        if(!child){execl(argv[2],argv[2],"-I","-B","-c",argv[3],argv[0],(char*)NULL);_exit(95);}
        int status=0;pid_t joined;do{joined=waitpid(child,&status,0);}while(joined<0&&errno==EINTR);
        return joined==child&&WIFEXITED(status)?WEXITSTATUS(status):96;
    }
    if(argc==4 && (!strcmp(argv[1],"source")||!strcmp(argv[1],"record"))){
        int directory=open(argv[2],O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);if(directory<0)return 92;
        size_t length=0;char *raw=ffr3_capture_at(directory,argv[3],16U*FFR3_MAX_RECORD,&length,!strcmp(argv[1],"source")?-1:1,&stop);close(directory);
        if(!raw)return 3;unsigned char bytes[32];char hash[65];CC_SHA256(raw,(CC_LONG)length,bytes);ffr3_hex(bytes,hash);printf("%zu:%s",length,hash);free(raw);return 0;
    }
    if(argc==5 && !strcmp(argv[1],"helper")){
        int directory=open(argv[3],O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);if(directory<0)return 92;
        size_t bytes=0;char *pin=ffr3_capture_at(directory,"pin.json",64U*1024U*1024U,&bytes,1,&stop);close(directory);
        if(!pin)return 93;
        FFR3HelperCall call={.python=argv[2],.pin_frame=pin,.pin_bytes=bytes,.context=argv[4],
            .origin_ns=(unsigned long long)now.tv_sec*1000000000ULL+(unsigned long long)now.tv_nsec,
            .stop_ns=(unsigned long long)stop.tv_sec*1000000000ULL+(unsigned long long)stop.tv_nsec,.stop=stop};
        char *raw=NULL;size_t length=0;int valid=ffr3_run_semantic_helper(&call,&raw,&length);
        int duplicate=ffr3_run_semantic_helper(&call,&raw,&length);
        if(!valid || duplicate || !call.joined){free(pin);free(raw);return 4;}
        int written=fwrite(raw,1,length,stdout)==length;free(pin);free(raw);return written?0:5;
    }
    return 94;
}
''')
    binary = folder / "native-io"
    compiled = subprocess.run(["clang", "-Wall", "-Wextra", "-Werror", str(unit), "-o", str(binary)], capture_output=True, text=True)
    assert compiled.returncode == 0, compiled.stderr
    return binary


def _read_native_response(native_io_binary,raw,*,fragment=False,keep_open=False):
    import socket
    reader,writer=socket.socketpair()
    finished=threading.Event()
    def send():
        try:
            if fragment:
                for part in (raw[:7],raw[7:29],raw[29:-3],raw[-3:]):
                    writer.sendall(part);time.sleep(.01)
            else:writer.sendall(raw)
            if keep_open:finished.wait(3)
        except (BrokenPipeError,OSError):pass
        finally:writer.close()
    thread=threading.Thread(target=send);thread.start()
    try:
        return subprocess.run([str(native_io_binary),'response',str(reader.fileno())],
            pass_fds=(reader.fileno(),),capture_output=True,timeout=2)
    finally:
        finished.set();reader.close();thread.join(4)


def test_native_original_response_finishes_fragmented_held_open_202_without_eof(native_io_binary):
    body=b'{"status":"DRAINING"}'
    raw=b'HTTP/1.0 202 Accepted\r\nContent-Type: application/json; charset=utf-8\r\nContent-Length: '+str(len(body)).encode()+b'\r\n\r\n'+body
    result=_read_native_response(native_io_binary,raw,fragment=True,keep_open=True)
    assert result.returncode==0 and result.stdout==raw


@pytest.mark.parametrize('fault',['missing','duplicate','negative','leading_zero','chunked','oversize','truncated','extra','nul'])
def test_native_original_response_denies_ambiguous_unbounded_or_incomplete_frames(native_io_binary,fault):
    headers=b'Content-Length: 2\r\n';body=b'{}'
    if fault=='missing':headers=b'X-Observation: present\r\n'
    elif fault=='duplicate':headers+=b'content-length: 2\r\n'
    elif fault=='negative':headers=b'Content-Length: -2\r\n'
    elif fault=='leading_zero':headers=b'Content-Length: 02\r\n'
    elif fault=='chunked':headers+=b'Transfer-Encoding: chunked\r\n'
    elif fault=='oversize':headers=b'Content-Length: 99999999999999999999\r\n'
    elif fault=='truncated':body=b'{'
    elif fault=='extra':body+=b'extra'
    else:body=b'\x00}'
    raw=b'HTTP/1.0 202 Accepted\r\n'+headers+b'\r\n'+body
    result=_read_native_response(native_io_binary,raw,keep_open=fault=='truncated')
    assert result.returncode==3


def test_native_immutable_publication_fsync_readback_and_no_overwrite(native_io_binary, tmp_path):
    os.chmod(tmp_path, 0o700)
    command = [str(native_io_binary), "publish", str(tmp_path), "fixed-original.json", "original exact bytes"]
    first = subprocess.run(command, capture_output=True)
    assert first.returncode == 0, first.stderr
    path = tmp_path / "fixed-original.json"
    before = path.stat()
    assert path.read_bytes() == b"original exact bytes" and before.st_mode & 0o777 == 0o600
    second = subprocess.run(command[:-1] + ["replacement"], capture_output=True)
    assert second.returncode == 3
    assert path.read_bytes() == b"original exact bytes" and path.stat().st_ino == before.st_ino


@pytest.mark.parametrize("fault", ["directory_mode", "symlink", "directory"])
def test_native_immutable_publication_denies_nonprivate_or_existing_entries(native_io_binary, tmp_path, fault):
    os.chmod(tmp_path, 0o755 if fault == "directory_mode" else 0o700)
    target = tmp_path / "fixed.json"
    if fault == "symlink":
        target.symlink_to(tmp_path / "not-created")
    elif fault == "directory":
        target.mkdir(mode=0o700)
    result = subprocess.run([str(native_io_binary), "publish", str(tmp_path), "fixed.json", "body"], capture_output=True)
    assert result.returncode == 3
    assert not (tmp_path / "not-created").exists()


def test_actual_c_pinned_helper_executes_captured_bytes_once_without_role_key(native_io_binary, tmp_path):
    """Positive native transport fixture, not an operational authority test."""
    import json
    from hashlib import sha256
    from kronos.common.failed_fenced_recovery import canonical_bytes
    payload = b'''def native_helper_main(*,origin_ns,stop_deadline_ns):
 import os,struct,json
 def exact(n):
  b=b''
  while len(b)<n:
   try:p=os.read(0,n-len(b))
   except BlockingIOError:continue
   if not p:raise RuntimeError('truncated')
   b+=p
  return b
 size=struct.unpack('!I',exact(4))[0];body=json.loads(exact(size))
 if os.read(0,1)!=b'':raise RuntimeError('extra')
 raw=json.dumps({'decision':'UNSIGNED_FIXTURE_ONLY','helper_pid':body['helper']['pid'],'has_role_key':False},sort_keys=True,separators=(',',':')).encode()
 os.write(1,struct.pack('!I',len(raw))+raw)
 return 0
'''
    blob = {"identity": "isolated-fixture", "hash": "a" * 64, "bytes": "1"}
    plan = {"schema": "KRONOS-FAILED-FENCED-BOOTSTRAP-PLAN/1.0.0", "identity": "fixture-plan",
            "source_inventory": blob, "qualification": blob,
            "modules": [{"name": "tools.failed_fenced_launcher", "digest": sha256(payload).hexdigest()}]}
    inventory = [[row["name"], row["digest"]] for row in plan["modules"]]
    inventory_raw = canonical_bytes(inventory)
    plan["source_inventory"] = {"identity":"fixture-source","hash":sha256(inventory_raw).hexdigest(),"bytes":str(len(inventory_raw))}
    frame = {"inventory": inventory, "plan": plan, "plan_hash": sha256(canonical_bytes(plan)).hexdigest(), "sources": [{
        "name": "tools.failed_fenced_launcher", "package": False, "path": str(tmp_path / "never-read.py"), "payload": payload.hex()}]}
    pin = tmp_path / "pin.json";pin.write_bytes(canonical_bytes(frame));pin.chmod(0o600)
    result = subprocess.run([str(native_io_binary), "helper", sys.executable, str(tmp_path), '{"helper":null}'], capture_output=True)
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert value["decision"] == "UNSIGNED_FIXTURE_ONLY" and value["has_role_key"] is False
    assert int(value["helper_pid"]) >= 2 and int(value["helper_pid"]) != os.getpid()
    assert not (tmp_path / "never-read.py").exists()


def test_embedded_native_pin_bootstrap_matches_reviewable_exact_python_bytes():
    import json
    from tools.failed_fenced_launcher import NATIVE_PIN_BOOTSTRAP
    source = (Path(__file__).parents[3] / "tools/macos/kronos_launcher.c").read_text()
    block = source.split("static const char *ffr3_pin_bootstrap =\n", 1)[1].split("    ;\n", 1)[0]
    assert "".join(json.loads(line.strip()) for line in block.splitlines()) == NATIVE_PIN_BOOTSTRAP


@pytest.fixture
def received_semantic_exchange(tmp_path, monkeypatch):
    """Real pipe receiver; native/source syscall leaves are controlled fixtures.

    This fixture deliberately establishes no canonical-parent, human approval
    or operational grant. It tests immutable transport/currentness boundaries.
    """
    from hashlib import sha256
    from kronos.common.failed_fenced_startup import NativeSemanticExchange
    from kronos.common.failed_fenced_recovery import RecoveryStore, canonical_bytes
    from kronos.browser import restart_control
    from tools import failed_fenced_launcher, runtime_source_gate
    # The receiver's source inventory validation imports this actual verifier.
    # Capture it prospectively; do not depend on another test's import order.
    from kronos.intraday import runtime_identity
    import pwd
    from types import SimpleNamespace
    fixture_home = tmp_path / "native-account-home"
    estate = fixture_home / "Library/Application Support/KRONOS/runtime"
    estate.mkdir(parents=True, mode=0o700)
    monkeypatch.setattr(pwd, "getpwuid", lambda uid: SimpleNamespace(pw_dir=str(fixture_home)))
    monkeypatch.setattr(restart_control, "DEFAULT_BACKEND_CONTROL_PATH", estate / "browser-backend-v1.control")
    store = RecoveryStore(estate)
    scope = {"schema": "KRONOS_FAILED_FENCED_GUARD_SCOPE_V1", "version": "1.0.0",
             "service": "isolated", "installation": "isolated", "policy": "MANDATORY"}
    store.provision(scope, sha256(canonical_bytes(scope)).hexdigest())
    names = sorted({getattr(getattr(module, "__spec__", None), "name", "") for module in tuple(sys.modules.values())})
    captured = {name: ("controlled-observation-fixture:" + name).encode() for name in names
                if type(name) is str and (name in {"tools", "kronos"} or name.startswith(("tools.", "kronos.")))}
    dummy = {"identity": "fixture", "hash": "a" * 64, "bytes": "1"}
    plan = {"schema": "KRONOS-FAILED-FENCED-BOOTSTRAP-PLAN/1.0.0", "identity": "fixture-plan",
            "source_inventory": dummy, "qualification": dummy,
            "modules": [{"name": name, "digest": sha256(raw).hexdigest()} for name, raw in sorted(captured.items())]}
    plan["source_inventory"] = store.write_blob("fixture-source-inventory", canonical_bytes(
        [[name, sha256(raw).hexdigest()] for name, raw in sorted(captured.items())]))
    plan_ref = store.write_blob("fixture-plan", canonical_bytes(plan))
    birth = {"seconds": "1", "microseconds": "2"}
    helper = {"pid": str(os.getpid()), "kernel_birth": birth, "runtime": "fixture-helper"}
    controller = dict(helper, pid=str(os.getppid()), runtime="fixture-controller")
    clock = {"type": "CLOCK_MONOTONIC", "boot_id": "fixture-boot", "qualification": {
        "authority": "PCP", "contract": "fixture", "identity": "fixture", "hash": "d" * 64, "bytes": "1"}}
    origin = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    auth_raw = b'{"kind":"FAILURE"}'
    body = {"stage": "PREPARATION", "action": "AUTHORIZE", "operation": "fixture-operation",
        "controller": controller, "helper": helper, "clock": clock, "origin_ns": str(origin),
        "stop_deadline_ns": str(origin + 15_000_000_000), "key_id": "a" * 64, "control_pid": str(os.getpid()),
        "controller_capability": dummy, "admission": None, "dispatch": None,
        "authenticated": [{"hash": sha256(auth_raw).hexdigest(), "bytes": str(len(auth_raw)), "kind": "FAILURE", "external": False}],
        "custody": {"key_id": "a" * 64, "control_pid": str(os.getpid()), "retained_control_hash": "a" * 64,
                    "retained_control_bytes": "100", "verified_ns": str(origin)},
        "preparations": [{"mode": "ORIGINAL", "service": "fixture", "installation": "fixture", "lineage": {},
                          "attempt": "fixture", "anchors": {"pin": dummy, "approval": dummy, "catalogue": dummy, "decisions": []}}],
        "helper_plan": plan_ref, "helper_entry": {"identity": "fixture-entry", "hash": sha256(captured["tools.failed_fenced_launcher"]).hexdigest(),
                                                    "bytes": str(len(captured["tools.failed_fenced_launcher"]))}}
    monkeypatch.setattr(NativeSemanticExchange, "_native_process", staticmethod(lambda pid: dict(birth)))
    monkeypatch.setattr(NativeSemanticExchange, "_native_image_identity", staticmethod(lambda pid, budget: ((1, 2, 3, 4, 5, 6, 7, 8), "b" * 64)))
    monkeypatch.setattr(NativeSemanticExchange, "_native_parent_image_path", staticmethod(lambda pid: "/Applications/KRONOS.app/Contents/MacOS/KRONOS"))
    monkeypatch.setattr(runtime_source_gate, "canonical_parent", lambda **kwargs: None)
    monkeypatch.setattr(failed_fenced_launcher, "native_pinned_module", lambda module, plan_hash: captured[module.__spec__.name])
    from contextlib import contextmanager
    @contextmanager
    def received(body_change=None):
        from copy import deepcopy
        delivered = deepcopy(body)
        if body_change is not None:
            body_change(delivered)
        raw = canonical_bytes(delivered);read, write = os.pipe();out_read, out_write = os.pipe()
        saved = os.dup(0), os.dup(1)
        def send():
            try:
                frame, offset = struct.pack("!I", len(raw)) + raw, 0
                while offset < len(frame):
                    offset += os.write(write, frame[offset:])
            finally:
                os.close(write)
        thread = threading.Thread(target=send);thread.start()
        try:
            os.dup2(read, 0);os.dup2(out_write, 1);os.close(read);os.close(out_write)
            exchange = NativeSemanticExchange.receive(origin_ns=origin, stop_deadline_ns=origin + 15_000_000_000)
            thread.join()
            yield exchange, auth_raw
        finally:
            os.dup2(saved[0], 0);os.dup2(saved[1], 1)
            os.close(saved[0]);os.close(saved[1]);os.close(out_read);thread.join()
    return received


def test_native_semantic_receiver_exact_context_and_both_custody_sizes(received_semantic_exchange):
    with received_semantic_exchange() as (exchange, raw):
        exchange.require_current();exchange.authenticate(raw, external=False)
        payload = {"process": {"pid": exchange.control_pid}, "live_control": {"hash": exchange.key_id, "bytes": "100"},
            "retained_control": {"hash": exchange.key_id, "bytes": "100"}, "boot_id": exchange.clock["boot_id"]}
        exchange.verify_custody(payload)
        payload["live_control"]["bytes"] = "99"
        with pytest.raises(RecoveryStartupError, match="CUSTODY_BINDING_CHANGED"):
            exchange.verify_custody(payload)
        with pytest.raises(RecoveryStartupError, match="NOT_AUTHENTICATED"):
            exchange.authenticate(b'{"kind":"FAILURE","other":null}', external=False)


@pytest.mark.parametrize("fault", ["body", "attribute", "authentication", "plan", "modules", "budget"])
def test_native_semantic_exchange_mutation_cannot_extend_or_restamp_context(received_semantic_exchange, fault):
    with received_semantic_exchange() as (exchange, _):
        if fault == "body":exchange._body["operation"] = "different"
        elif fault == "attribute":exchange.action = "CHILD_FORK"
        elif fault == "authentication":next(iter(exchange._authenticated.values()))["bytes"] = "0"
        elif fault == "plan":exchange._plan["modules"][0]["digest"] = "0" * 64
        elif fault == "modules":exchange._modules["unapproved.module"] = "f" * 64
        else:exchange.budget.stop_deadline_ns += 1
        with pytest.raises(RecoveryStartupError, match="CONTEXT_CHANGED"):
            exchange.require_current()


def test_native_semantic_exchange_cannot_be_constructed_from_caller_refs():
    from kronos.common.failed_fenced_startup import NativeSemanticExchange
    with pytest.raises(RecoveryStartupError, match="RECEIVER_REQUIRED"):
        NativeSemanticExchange({}, ())


def test_child_pinner_native_literal_is_exact_qualified_python_program():
    """The C entry cannot substitute a weaker bootstrap or default UI launch."""
    import ast
    import re
    from tools.runtime_source_gate import NATIVE_CHILD_PIN_BOOTSTRAP
    source = (Path(__file__).parents[3] / "tools/macos/kronos_launcher.c").read_text()
    value = re.search(r"static const char \*ffr3_child_pin_template = (\".*?\");\n", source)
    assert value is not None
    assert ast.literal_eval(value[1]) == NATIVE_CHILD_PIN_BOOTSTRAP
    assert "entry.main(['--no-browser'])" in NATIVE_CHILD_PIN_BOOTSTRAP
    assert "row['payload']" not in NATIVE_CHILD_PIN_BOOTSTRAP


@pytest.fixture(scope="module")
def native_broker_binary(tmp_path_factory):
    """Actual private C broker; this is a transport component, not a runtime approval."""
    folder = tmp_path_factory.mktemp("native-r3-duplex")
    source = Path(__file__).parents[3] / "tools/macos/kronos_launcher.c"
    unit = folder / "duplex.c"
    unit.write_text(source.read_text().replace('int null=open("/dev/null",O_WRONLY);', 'int null=dup(2);').replace("int main(void) {", "int unused_application_main(void) {") + r'''
int main(int argc,char **argv) {
    if(argc!=4)return 90;
    struct proc_bsdinfo info;memset(&info,0,sizeof(info));
    if(proc_pidinfo(getpid(),PROC_PIDTBSDINFO,0,&info,sizeof(info))!=(int)sizeof(info))return 91;
    FFR3PreparedNative p={0};p.mode="\"ORIGINAL\"";
    clock_gettime(CLOCK_MONOTONIC,&p.origin);p.stop=p.origin;p.stop.tv_sec+=15;
    FFR3Session s={0};s.prepared=&p;s.grant_writer=-1;
    char controller[1024],control[256];
    snprintf(controller,sizeof(controller),"{\"kernel_birth\":{\"microseconds\":\"%llu\",\"seconds\":\"%llu\"},\"pid\":\"%ld\",\"runtime\":\"native-component-fixture\"}",
        (unsigned long long)info.pbi_start_tvusec,(unsigned long long)info.pbi_start_tvsec,(long)getpid());
    snprintf(control,sizeof(control),"KRONOS_BROWSER_BACKEND_CONTROL_V1\n%ld\n%s\n",(long)getppid(),
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
    const char *clock="{\"boot_id\":\"isolated-fixture\",\"qualification\":{\"authority\":\"PCP\",\"bytes\":\"1\",\"contract\":\"fixture\",\"hash\":\"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd\",\"identity\":\"fixture\"},\"type\":\"CLOCK_MONOTONIC\"}";
    if(!ffr3_native_codec_init(&s.codec,control,clock,controller))return 92;
    char raw[8192];if(!ffr3_native_encode(&s.codec,"FAILURE",0,"{\"fixture\":\"transport-only\"}",ffr3_now_ns(),raw,sizeof(raw)))return 93;
    char *hex=ffr3_bytes_hex(raw,strlen(raw));
    char *context=ffr3_format("{\"broker\":true,\"fault\":\"%s\",\"helper\":{},\"probe\":\"%s\"}",argv[3],hex);free(hex);
    int valid=context&&ffr3_run_broker(&s,argv[1],argv[2],strlen(argv[2]),context);free(context);
    printf("joined=%d;done=%d",s.helper_joined,s.done);memset(&s.codec,0,sizeof(s.codec));return valid?0:3;
}
''')
    binary = folder / "native-duplex"
    compiled = subprocess.run(["clang", "-Wall", "-Wextra", "-Werror", str(unit), "-o", str(binary)], capture_output=True, text=True)
    assert compiled.returncode == 0, compiled.stderr
    return binary


def _native_broker_frame():
    import json
    from hashlib import sha256
    payload = b'''import os,struct,json,hashlib,select,time

def native_helper_main(*,origin_ns,stop_deadline_ns):
    def read(size):
        result=b''
        while len(result)<size:
            now=time.clock_gettime_ns(time.CLOCK_MONOTONIC)
            if now>=stop_deadline_ns:raise RuntimeError('deadline')
            poll=select.poll();poll.register(0,select.POLLIN|select.POLLHUP|select.POLLERR)
            if not poll.poll(max(1,(stop_deadline_ns-now+999999)//1000000)):continue
            try:part=os.read(0,size-len(result))
            except (BlockingIOError,InterruptedError):continue
            if not part:raise RuntimeError('closed')
            result+=part
        return result
    raw=read(struct.unpack('!I',read(4))[0]);body=json.loads(raw)
    context=hashlib.sha256(raw).hexdigest()
    assert set(body)=={'broker','fault','helper','probe'} and body['broker'] is True
    assert int(body['helper']['pid'])==os.getpid()
    probe=bytes.fromhex(body['probe'])
    if body['fault']=='mac':
        value=json.loads(probe);value['mac']='0'*64
        probe=json.dumps(value,sort_keys=True,separators=(',',':')).encode()
    def call(sequence,kind,payload):
        request={'context':('f'*64 if body['fault']=='context' else context),'sequence':str(sequence),'kind':kind,'payload':payload}
        raw=json.dumps(request,sort_keys=True,separators=(',',':')).encode()
        frame=struct.pack('!I',len(raw))+raw
        while frame:
            count=os.write(1,frame);frame=frame[count:]
        response=json.loads(read(struct.unpack('!I',read(4))[0]))
        assert response['context']==context and response['sequence']==str(sequence)
        return response['result']
    value=call(1 if body['fault']=='sequence' else 0,'VERIFY',{'raw':probe.hex(),'external':False})
    assert value=={'hash':hashlib.sha256(probe).hexdigest(),'bytes':str(len(probe)),'kind':'FAILURE','external':False}
    if body['fault']=='issuer':call(1,'PUBLISH',{'kind':'SOURCE','external':True,'payload':{}})
    else:assert call(1,'DONE',{})=={'returned':True}
    return 0
'''
    name = "tools.failed_fenced_launcher"
    plan = {"schema": "KRONOS-FAILED-FENCED-BOOTSTRAP-PLAN/1.0.0", "identity": "transport-fixture-only",
            "source_inventory": {"identity": "fixture", "hash": "a" * 64, "bytes": "1"},
            "modules": [{"name": name, "digest": sha256(payload).hexdigest()}],
            "qualification": {"identity": "fixture", "hash": "b" * 64, "bytes": "1"}}
    canonical = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    inventory = [[row["name"], row["digest"]] for row in plan["modules"]]
    inventory_raw = canonical(inventory)
    plan["source_inventory"] = {"identity":"fixture-source","hash":sha256(inventory_raw).hexdigest(),"bytes":str(len(inventory_raw))}
    return canonical({"inventory": inventory, "plan": plan, "plan_hash": sha256(canonical(plan)).hexdigest(),
        "sources": [{"name": name, "package": False, "path": "/synthetic/native-broker-fixture.py", "payload": payload.hex()}]}).decode()


def test_actual_c_keyless_duplex_verifies_then_joins_one_original_helper(native_broker_binary):
    import sys
    result = subprocess.run([str(native_broker_binary), sys.executable, _native_broker_frame(), "none"], capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert result.stdout == b"joined=1;done=1"


@pytest.mark.parametrize("fault", ["context", "sequence", "mac", "issuer"])
def test_actual_c_keyless_duplex_denies_changed_context_replay_mac_or_helper_issuer(native_broker_binary, fault):
    import sys
    result = subprocess.run([str(native_broker_binary), sys.executable, _native_broker_frame(), fault], capture_output=True, timeout=20)
    assert result.returncode == 3
    assert result.stdout == b"joined=1;done=0"


@pytest.fixture(scope="module")
def native_fact_binary(tmp_path_factory):
    """Actual C retention gate; payload facts are explicitly synthetic fixtures."""
    folder = tmp_path_factory.mktemp("native-r3-fact")
    source = Path(__file__).parents[3] / "tools/macos/kronos_launcher.c"
    unit = folder / "fact.c"
    unit.write_text(source.read_text().replace("int main(void) {", "int unused_application_main(void) {") + r'''
int main(int argc,char **argv) {
    if(argc!=4)return 90;
    FFR3PreparedNative p={0};p.mode=!strcmp(argv[3],"recovery")?"\"RECOVERY\"":"\"ORIGINAL\"";
    p.blobs=open(argv[1],O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);if(p.blobs<0)return 91;
    clock_gettime(CLOCK_MONOTONIC,&p.origin);p.stop=p.origin;p.stop.tv_sec+=15;
    FFR3Session s={0};s.prepared=&p;s.grant_writer=-1;
    if(!strcmp(argv[3],"custody-original")||!strcmp(argv[3],"custody-recovery")){
        p.mode=!strcmp(argv[3],"custody-original")?"\"ORIGINAL\"":"\"RECOVERY\"";p.root=p.blobs;
        s.control=argv[2];s.control_bytes=strlen(argv[2]);unsigned char digest[32];
        CC_SHA256(s.control,(CC_LONG)s.control_bytes,digest);ffr3_hex(digest,s.codec.key_id);
        int valid=ffr3_checkpoint_storage(&s);close(p.blobs);return valid?0:3;
    }
    if(!strcmp(argv[3],"scan")){
        int complete=0;char *proof=ffr3_scan_proof(&s,"CONTROL_BINDING",NULL,NULL,&complete);
        free(proof);printf("%d\n",complete);
        complete=0;proof=ffr3_scan_proof(&s,"CONTROL_BINDING",NULL,NULL,&complete);
        free(proof);printf("%d\n",complete);close(p.blobs);return 0;
    }
    if(!strcmp(argv[3],"reserved"))s.original_reserved=1;
    if(!strcmp(argv[3],"readonly"))s.read_only=1;
    char *result=NULL;
    if(s.read_only){strcpy(s.context_hash,"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
        char *request=ffr3_format("{\"context\":\"%s\",\"kind\":\"FACT\",\"payload\":%s,\"sequence\":\"0\"}",s.context_hash,argv[2]);
        result=request?ffr3_broker_request(&s,request):NULL;free(request);
    }else result=ffr3_broker_fact(&s,argv[2]);
    if(result)puts(result);int returned=result!=NULL;
    if(!strcmp(argv[3],"duplicate")){char *again=ffr3_broker_fact(&s,argv[2]);if(again){free(again);free(result);close(p.blobs);return 92;}}
    free(result);for(size_t i=0;i<s.fact_count;i++)free(s.fact_refs[i]);close(p.blobs);return returned?0:3;
}
''')
    binary = folder / "native-fact"
    compiled = subprocess.run(["clang", "-Wall", "-Wextra", "-Werror", str(unit), "-o", str(binary)], capture_output=True, text=True)
    assert compiled.returncode == 0, compiled.stderr
    return binary


def _synthetic_package_fact():
    """Closed shape only; this does not assert a real signature or source review."""
    from kronos.common.failed_fenced_recovery import canonical_bytes
    blob = {"identity": "synthetic-immutable-reference", "hash": "b" * 64, "bytes": "1"}
    return canonical_bytes({"kind": "PACKAGE", "payload": {"identity": "synthetic-package-fact",
        "artifact_approval": "synthetic-approval", "manifest": blob, "executable": blob,
        "signature": blob, "role": "INSTALLED", "verified_ns": str(time.clock_gettime_ns(time.CLOCK_MONOTONIC))}}).decode()


def test_native_unsigned_fact_retention_has_no_proof_or_launch_authority(native_fact_binary, tmp_path):
    import json
    from hashlib import sha256
    from kronos.common.failed_fenced_recovery import canonical_bytes
    os.chmod(tmp_path, 0o700)
    proposal = _synthetic_package_fact()
    result = subprocess.run([str(native_fact_binary), str(tmp_path), proposal, "original"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    ref = json.loads(result.stdout)["fact"]
    raw = canonical_bytes(json.loads(proposal)["payload"])
    assert ref == {"identity": "synthetic-package-fact", "hash": sha256(raw).hexdigest(), "bytes": str(len(raw))}
    assert list(tmp_path.iterdir()) == [tmp_path / (ref["hash"] + ".blob")]
    assert (tmp_path / (ref["hash"] + ".blob")).read_bytes() == raw
    assert all(key not in json.loads(raw) for key in ("mac", "issuer", "protocol", "authorization", "controller_capability"))


def test_native_control_receipt_observation_distinguishes_absence_from_partial_ambiguity(native_fact_binary, tmp_path):
    os.chmod(tmp_path, 0o700)
    empty = subprocess.run([str(native_fact_binary), str(tmp_path), "{}", "scan"], capture_output=True, text=True)
    assert empty.returncode == 0 and empty.stdout == "1\n1\n"
    partial = tmp_path / ("a" * 64 + ".blob")
    partial.write_bytes(b"partial original publication")
    partial.chmod(0o600)
    ambiguous = subprocess.run([str(native_fact_binary), str(tmp_path), "{}", "scan"], capture_output=True, text=True)
    assert ambiguous.returncode == 0 and ambiguous.stdout == "0\n0\n"
    assert partial.read_bytes() == b"partial original publication"


def test_native_recovery_cannot_create_or_repair_original_checkpoint(native_fact_binary, tmp_path):
    from hashlib import sha256
    os.chmod(tmp_path,0o700)
    custody=tmp_path/'custody';custody.mkdir(mode=0o700)
    private='KRONOS_BROWSER_BACKEND_CONTROL_V1\n12345\n'+'9'*64+'\n'
    ref=custody/(sha256(private.encode()).hexdigest()+'.control')
    missing=subprocess.run([str(native_fact_binary),str(tmp_path),private,'custody-recovery'],capture_output=True,text=True)
    assert missing.returncode==3 and list(custody.iterdir())==[]
    original=subprocess.run([str(native_fact_binary),str(tmp_path),private,'custody-original'],capture_output=True,text=True)
    assert original.returncode==0 and ref.read_bytes()==private.encode()
    assert ref.stat().st_mode&0o777==0o600
    before=ref.stat()
    retained=subprocess.run([str(native_fact_binary),str(tmp_path),private,'custody-recovery'],capture_output=True,text=True)
    assert retained.returncode==0 and ref.stat().st_ino==before.st_ino
    ref.write_bytes(b'partial checkpoint')
    partial=subprocess.run([str(native_fact_binary),str(tmp_path),private,'custody-recovery'],capture_output=True,text=True)
    assert partial.returncode==3 and ref.read_bytes()==b'partial checkpoint'


def test_native_checkpoint_retention_follows_actual_original_admission_dispatch():
    source=(Path(__file__).parents[3]/'tools/macos/kronos_launcher.c').read_text()
    body=source[source.index('static int ffr3_execute_prepared(void) {'):source.index('\nint main(void) {')]
    assert body.index('ffr3_admission(&session,"original.authorize"')<body.index('ffr3_retain_control(&session)')
    assert body.index('ffr3_dispatch(&session,"DISPATCHED"')<body.index('ffr3_retain_control(&session)')


@pytest.mark.parametrize("state", ["recovery", "reserved", "readonly"])
def test_native_fact_retention_denies_recovery_after_reservation_and_static_reader(native_fact_binary, tmp_path, state):
    os.chmod(tmp_path, 0o700)
    result = subprocess.run([str(native_fact_binary), str(tmp_path), _synthetic_package_fact(), state], capture_output=True, text=True)
    assert result.returncode == 3, result.stderr
    assert list(tmp_path.iterdir()) == []


def test_native_fact_retention_preserves_duplicate_failure_and_original_bytes(native_fact_binary, tmp_path):
    os.chmod(tmp_path, 0o700)
    result = subprocess.run([str(native_fact_binary), str(tmp_path), _synthetic_package_fact(), "duplicate"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    retained = list(tmp_path.iterdir())
    assert len(retained) == 1
    assert retained[0].stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("fault", ["future", "extra", "kind"])
def test_native_fact_retention_denies_malformed_or_unobserved_payload(native_fact_binary, tmp_path, fault):
    import json
    from kronos.common.failed_fenced_recovery import canonical_bytes
    os.chmod(tmp_path, 0o700)
    value = json.loads(_synthetic_package_fact())
    if fault == "future":
        value["payload"]["verified_ns"] = str(time.clock_gettime_ns(time.CLOCK_MONOTONIC) + 1_000_000_000_000)
    elif fault == "extra":
        value["payload"]["approved"] = True
    else:
        value["kind"] = "RECOVERY_AUTHORITY"
    result = subprocess.run([str(native_fact_binary), str(tmp_path), canonical_bytes(value).decode(), "original"], capture_output=True, text=True)
    assert result.returncode == 3, result.stderr
    assert list(tmp_path.iterdir()) == []


@pytest.fixture(scope="module")
def native_historical_binary(tmp_path_factory):
    """Native historical MAC/custody adapter; no runtime-source approval implied."""
    folder = tmp_path_factory.mktemp("native-r3-historical")
    source = Path(__file__).parents[3] / "tools/macos/kronos_launcher.c"
    unit = folder / "historical.c"
    unit.write_text(source.read_text().replace("int main(void) {", "int unused_application_main(void) {") + r'''
int main(int argc,char **argv) {
    if(argc!=3)return 90;
    struct proc_bsdinfo info;memset(&info,0,sizeof(info));if(proc_pidinfo(getpid(),PROC_PIDTBSDINFO,0,&info,sizeof(info))!=(int)sizeof(info))return 91;
    FFR3PreparedNative p={0};p.mode="\"ORIGINAL\"";p.root=open(argv[1],O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);if(p.root<0)return 92;
    p.blobs=ffr3_child_directory(p.root,"blobs");p.records=ffr3_child_directory(p.root,"records");
    snprintf(p.controller,sizeof(p.controller),"{\"kernel_birth\":{\"microseconds\":\"%llu\",\"seconds\":\"%llu\"},\"pid\":\"%ld\",\"runtime\":\"synthetic-component-controller\"}",(unsigned long long)info.pbi_start_tvusec,(unsigned long long)info.pbi_start_tvsec,(long)getpid());
    clock_gettime(CLOCK_MONOTONIC,&p.origin);p.stop=p.origin;p.stop.tv_sec+=15;
    FFR3Session s={0};s.prepared=&p;s.grant_writer=-1;char control[256];snprintf(control,sizeof(control),"KRONOS_BROWSER_BACKEND_CONTROL_V1\n%ld\n%s\n",(long)getppid(),"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
    const char *clock="{\"boot_id\":\"new-synthetic-boot\",\"qualification\":{\"authority\":\"PCP\",\"bytes\":\"1\",\"contract\":\"synthetic\",\"hash\":\"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd\",\"identity\":\"synthetic\"},\"type\":\"CLOCK_MONOTONIC\"}";
    if(!ffr3_native_codec_init(&s.codec,control,clock,p.controller))return 93;
    char *result=ffr3_broker_verify(&s,argv[2]);if(result)puts(result);int ok=result!=NULL;free(result);memset(&s.codec,0,sizeof(s.codec));close(p.blobs);close(p.records);close(p.root);return ok?0:3;
}
''')
    binary = folder / "native-historical"
    compiled = subprocess.run(["clang", "-Wall", "-Wextra", "-Werror", str(unit), "-o", str(binary)], capture_output=True, text=True)
    assert compiled.returncode == 0, compiled.stderr
    return binary


def _historical_control_fixture(tmp_path, fault):
    from hashlib import sha256
    from kronos.common.failed_fenced_recovery import RecoveryCodec, canonical_bytes
    os.chmod(tmp_path, 0o700)
    for name in ("blobs", "records", "custody", "slots", "guards"):
        (tmp_path / name).mkdir(mode=0o700)
    control = ("KRONOS_BROWSER_BACKEND_CONTROL_V1\n%d\n%s\n" % (os.getpid(), "b" * 64)).encode()
    clock = {"type": "CLOCK_MONOTONIC", "boot_id": "old-synthetic-boot", "qualification": {
        "authority": "PCP", "contract": "synthetic", "identity": "synthetic", "hash": "d" * 64, "bytes": "1"}}
    codec = RecoveryCodec(control, clock)
    reference = {"identity": "synthetic-control", "hash": sha256(control).hexdigest(), "bytes": str(len(control))}
    payload = {"identity": "synthetic-historical-control", "process": {"pid": str(os.getpid()),
        "kernel_birth": {"seconds": "1", "microseconds": "2"}, "runtime": "synthetic-retained-source"},
        "live_control": dict(reference), "retained_control": dict(reference), "schema": "KRONOS_BROWSER_BACKEND_CONTROL_V1",
        "boot_id": clock["boot_id"], "verified_ns": "1"}
    if fault == "live_length": payload["live_control"]["bytes"] = str(len(control) + 1)
    if fault == "retained_length": payload["retained_control"]["bytes"] = str(len(control) + 1)
    if fault == "process": payload["process"]["pid"] = "2"
    if fault == "boot": payload["boot_id"] = "incorrect-boot"
    raw = codec.encode_proof("CONTROL_BINDING", payload, payload["process"], "PREDECESSOR", 1)
    if fault == "mac":
        import json
        value = json.loads(raw);value["mac"] = "0" * 64;raw = canonical_bytes(value)
    if fault != "missing_custody":
        path = tmp_path / "custody" / (reference["hash"] + ".control")
        path.write_bytes(control);path.chmod(0o600)
    if fault != "missing_retained":
        path = tmp_path / "blobs" / (sha256(raw).hexdigest() + ".blob")
        path.write_bytes(raw);path.chmod(0o600)
    return control, raw, canonical_bytes({"external": True, "raw": raw.hex()}).decode()


def test_native_historical_verification_keeps_original_clock_custody_and_no_key_exposure(native_historical_binary, tmp_path):
    import json
    from hashlib import sha256
    control, raw, proposal = _historical_control_fixture(tmp_path, "none")
    result = subprocess.run([str(native_historical_binary), str(tmp_path), proposal], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"hash": sha256(raw).hexdigest(), "bytes": str(len(raw)), "kind": "CONTROL_BINDING", "external": True}
    assert control.decode() not in result.stdout and "b" * 64 not in result.stdout


@pytest.mark.parametrize("fault", ["missing_custody", "missing_retained", "live_length", "retained_length", "process", "boot", "mac"])
def test_native_historical_verification_rejects_missing_or_changed_original_custody(native_historical_binary, tmp_path, fault):
    _, _, proposal = _historical_control_fixture(tmp_path, fault)
    before = {str(path.relative_to(tmp_path)): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    result = subprocess.run([str(native_historical_binary), str(tmp_path), proposal], capture_output=True, text=True)
    assert result.returncode == 3, result.stderr
    assert result.stdout == ""
    assert {str(path.relative_to(tmp_path)): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()} == before


def _guard_only_null_context(body):
    body.update(stage="GUARD_ADMISSION", action="VERIFY_STATUS", operation="installation.guard", broker=True,
        controller_capability=None, admission=None, dispatch=None, authenticated=[], key_id=None, control_pid=None, custody=None)


def test_native_static_guard_receiver_has_no_current_key_control_or_custody(received_semantic_exchange):
    with received_semantic_exchange(_guard_only_null_context) as (exchange, _):
        exchange.require_current()
        assert exchange.key_id is None and exchange.control_pid is None
        assert exchange._body["controller_capability"] is None and exchange._body["custody"] is None
        with pytest.raises(RecoveryStartupError, match="NO_CURRENT_CUSTODY"):
            exchange.verify_custody({})


@pytest.mark.parametrize("field", ["key_id", "control_pid", "controller_capability", "custody"])
def test_native_operational_receiver_rejects_null_guard_only_fields(received_semantic_exchange, field):
    def change(body): body[field] = None
    with pytest.raises(ValueError):
        with received_semantic_exchange(change):
            pytest.fail("Operational transport accepted guard-only null authority")


@pytest.mark.parametrize("field,value", [("key_id", "a"*64), ("control_pid", "2"), ("custody", {})])
def test_native_static_guard_receiver_rejects_restamped_current_authority(received_semantic_exchange, field, value):
    def change(body):
        _guard_only_null_context(body)
        body[field] = value
    with pytest.raises(RecoveryStartupError, match="READONLY_GUARD_CONTEXT"):
        with received_semantic_exchange(change):
            pytest.fail("Static reader accepted a current authority claim")


def test_native_source_capture_accepts_legitimate_empty_module_only(native_io_binary, tmp_path):
    from hashlib import sha256
    os.chmod(tmp_path, 0o700)
    path = tmp_path / "__init__.py"
    path.write_bytes(b"");path.chmod(0o600)
    source = subprocess.run([str(native_io_binary), "source", str(tmp_path), path.name], capture_output=True, text=True)
    assert source.returncode == 0 and source.stdout == "0:" + sha256(b"").hexdigest(), source.stderr
    proof = subprocess.run([str(native_io_binary), "record", str(tmp_path), path.name], capture_output=True, text=True)
    assert proof.returncode == 3 and proof.stdout == ""


@pytest.mark.parametrize("fault", ["symlink", "alias"])
def test_native_empty_source_capture_preserves_nofollow_and_unique_inode(native_io_binary, tmp_path, fault):
    os.chmod(tmp_path, 0o700)
    original = tmp_path / "source.py";original.write_bytes(b"");original.chmod(0o600)
    selected = tmp_path / "__init__.py"
    if fault == "symlink": selected.symlink_to(original)
    else: os.link(original, selected)
    result = subprocess.run([str(native_io_binary), "source", str(tmp_path), selected.name], capture_output=True, text=True)
    assert result.returncode == 3 and result.stdout == ""
    assert original.read_bytes() == b""


def test_actual_native_image_capture_binds_kernel_mapped_vnode_and_exact_bytes(native_io_binary):
    """Actual source/syscalls with an isolated, unique native C parent image.

    Only the canonical-path leaf is replaced. The test does not establish an
    approved production launcher or read the /Applications bundle.
    """
    source = Path(__file__).parents[3] / "src/kronos/common/failed_fenced_startup.py"
    program = r'''import sys,os,stat,ast,time,json
from pathlib import Path
from hashlib import sha256
sys.path[:0]=[ROOT+'/src',ROOT]
from kronos.common.failed_fenced_recovery import RecoveryBudget
from kronos.common.failed_fenced_startup import RecoveryStartupError
module=ast.parse(Path(SOURCE).read_text())
owner=next(node for node in module.body if isinstance(node,ast.ClassDef) and node.name=='NativeSemanticExchange')
method=next(node for node in owner.body if isinstance(node,ast.FunctionDef) and node.name=='_native_image_identity')
method.decorator_list=[]
class FixtureImage(ast.NodeTransformer):
 def visit_Constant(self,node):
  if node.value=='/Applications/KRONOS.app/Contents/MacOS/KRONOS':return ast.copy_location(ast.Constant(str(Path(sys.argv[1]).resolve())),node)
  return node
method=FixtureImage().visit(method)
namespace={'os':os,'stat':stat,'sha256':sha256,'RecoveryStartupError':RecoveryStartupError}
exec(compile(ast.fix_missing_locations(ast.Module(body=[method],type_ignores=[])),SOURCE,'exec'),namespace)
clock={'type':'CLOCK_MONOTONIC','boot_id':'synthetic-image','qualification':{'authority':'PCP','contract':'synthetic','identity':'synthetic','hash':'a'*64,'bytes':'1'}}
now=time.clock_gettime_ns(time.CLOCK_MONOTONIC)
stamp,digest=namespace['_native_image_identity'](os.getppid(),RecoveryBudget(clock,now,now+15_000_000_000))
observed=Path(sys.argv[1]).stat()
assert observed.st_nlink==1
assert stamp[:3]==(observed.st_dev,observed.st_ino,observed.st_size)
assert digest==sha256(Path(sys.argv[1]).read_bytes()).hexdigest()
print('ACTUAL_NATIVE_MAPPED_VNODE_VERIFIED')
'''
    program = "ROOT=" + repr(str(source.parents[3])) + "\nSOURCE=" + repr(str(source)) + "\n" + program
    result = subprocess.run([str(native_io_binary), "image", sys.executable, program], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "ACTUAL_NATIVE_MAPPED_VNODE_VERIFIED\n"


def test_native_code_identity_ignores_only_marshal_object_interning():
    """marshal flags can differ without any executable/location difference."""
    import marshal
    from tools.failed_fenced_launcher import _native_code_shape
    compiled = compile("value = 7\n", "/synthetic/source.py", "exec", dont_inherit=True)
    # A constant sharing the location-table byte object serializes as a
    # reference; an equal separate bytes object serializes inline. CodeType
    # deliberately interns filenames, so a filename clone cannot model this.
    original = compiled.replace(co_consts=compiled.co_consts + (compiled.co_linetable,))
    cloned = original.replace(co_consts=compiled.co_consts + (bytes(bytearray(compiled.co_linetable)),))
    assert original.co_consts[-1] == cloned.co_consts[-1] and original.co_consts[-1] is not cloned.co_consts[-1]
    assert marshal.dumps(original) != marshal.dumps(cloned)
    assert _native_code_shape(original) == _native_code_shape(cloned)


@pytest.fixture
def actual_native_loader_witness(monkeypatch):
    """Execute the exact embedded loader class, without any native authority."""
    import ast
    import types
    import importlib.abc
    import importlib.util
    from tools import failed_fenced_launcher as native
    source = b"value = 7\n"
    name = "kronos.synthetic_native_witness"
    frame = {"plan_hash": "a" * 64}
    sources = {name: (source, False, "/synthetic/native-source.py"),
        name + "_late": (b"later = 11\n", False, "/synthetic/native-late.py")}
    constructed = {}
    namespace = {"importlib": importlib, "sources": sources, "frame": frame, "constructed": constructed}
    tree = ast.parse(native.NATIVE_PIN_BOOTSTRAP)
    node = next(value for value in tree.body if isinstance(value, ast.ClassDef) and value.name == "PinnedLoader")
    exec(compile(ast.Module(body=[node], type_ignores=[]), "<string>", "exec", dont_inherit=True), namespace)
    loader_type = namespace["PinnedLoader"]
    loader = loader_type(name)
    module = types.ModuleType(name)
    module.__spec__ = importlib.util.spec_from_loader(name, loader, is_package=False)
    loader.exec_module(module)
    capsule = types.ModuleType("_kronos_native_bootstrap")
    capsule.script_hash = native.NATIVE_PIN_BOOTSTRAP_SHA256
    capsule.plan_hash = frame["plan_hash"]
    capsule.sources = tuple(sorted(sources.items()))
    capsule.constructed = constructed
    capsule.loader_type = loader_type
    capsule.finder = object()
    monkeypatch.setitem(sys.modules, capsule.__name__, capsule)
    monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(sys, "meta_path", [capsule.finder] + sys.meta_path)
    monkeypatch.setattr(native, "_NATIVE_PIN_WITNESSES", {})
    return native, capsule, module, namespace


def test_native_loaded_code_witness_reuses_only_completed_exact_validation(actual_native_loader_witness, monkeypatch):
    import builtins
    native, capsule, module, namespace = actual_native_loader_witness
    calls = []
    def counted(*args, **kwargs):
        calls.append(args[1])
        return builtins.compile(*args, **kwargs)
    monkeypatch.setattr(native, "compile", counted, raising=False)
    assert native.native_pinned_module(module, capsule.plan_hash) is capsule.sources[0][1][0]
    assert len(calls) == 2
    calls.clear()
    for _ in range(50):
        assert native.native_pinned_module(module, capsule.plan_hash) is capsule.sources[0][1][0]
    assert calls == []


def test_native_loaded_code_witness_fully_validates_each_later_module(actual_native_loader_witness, monkeypatch):
    import builtins
    import types
    import importlib.util
    native, capsule, module, namespace = actual_native_loader_witness
    native.native_pinned_module(module, capsule.plan_hash)
    name = module.__spec__.name + "_late"
    loader = capsule.loader_type(name)
    later = types.ModuleType(name)
    later.__spec__ = importlib.util.spec_from_loader(name, loader, is_package=False)
    loader.exec_module(later)
    calls = []
    def counted(*args, **kwargs):
        calls.append(args[1])
        return builtins.compile(*args, **kwargs)
    monkeypatch.setattr(native, "compile", counted, raising=False)
    assert native.native_pinned_module(later, capsule.plan_hash) is dict(capsule.sources)[name][0]
    assert len(calls) == 2
    calls.clear()
    assert native.native_pinned_module(module, capsule.plan_hash) is dict(capsule.sources)[module.__spec__.name][0]
    assert calls == []


@pytest.mark.parametrize("fault", ["code", "method", "method_code", "payload", "capture", "source_map", "source_row", "source_extra", "globals", "frame", "finder"])
def test_native_loaded_code_witness_denies_replaced_or_mutated_objects(actual_native_loader_witness, fault):
    import types
    native, capsule, module, namespace = actual_native_loader_witness
    native.native_pinned_module(module, capsule.plan_hash)
    loader = module.__spec__.loader
    if fault == "code": loader.code = loader.code.replace()
    elif fault == "method": capsule.loader_type.exec_module = types.FunctionType(capsule.loader_type.exec_module.__code__, namespace)
    elif fault == "method_code": capsule.loader_type.exec_module.__code__ = capsule.loader_type.exec_module.__code__.replace()
    elif fault == "payload": loader._kronos_native_pinned_payload = bytes(bytearray(loader._kronos_native_pinned_payload))
    elif fault == "capture": capsule.sources = tuple(list(capsule.sources))
    elif fault == "source_map": namespace["sources"] = dict(namespace["sources"])
    elif fault == "source_row": namespace["sources"][module.__spec__.name] = tuple(list(namespace["sources"][module.__spec__.name]))
    elif fault == "source_extra": namespace["sources"]["kronos.unreviewed_extra"] = (b"changed=True\n",False,"/synthetic/extra.py")
    elif fault == "globals": namespace["unexpected_mutation"] = True
    elif fault == "frame": namespace["frame"]["plan_hash"] = "b" * 64
    else: sys.meta_path.remove(capsule.finder)
    with pytest.raises(RecoveryStartupError, match="FIXED_(CAPTURE_CHANGED|LOADER_REQUIRED)"):
        native.native_pinned_module(module, "a" * 64)


@pytest.mark.parametrize("field", ["co_code", "co_names", "co_filename", "co_qualname", "co_firstlineno", "co_flags", "co_linetable", "co_exceptiontable", "co_consts"])
def test_native_code_identity_rejects_every_executable_location_or_nested_constant_change(field):
    from tools.failed_fenced_launcher import _native_code_shape
    original = compile("def nested(value):\n try:\n  return value + 7\n except TypeError:\n  return 'missing'\n", "/synthetic/source.py", "exec", dont_inherit=True)
    value = getattr(original, field)
    if field == "co_code": changed = value + b"\x09\x00"  # retained metadata only; never execute this fixture
    elif field in {"co_linetable", "co_exceptiontable"}: changed = value + b"\x00"
    elif field in {"co_filename", "co_qualname"}: changed = value + "changed"
    elif field == "co_firstlineno": changed = value + 1
    elif field == "co_flags": changed = value ^ 0x2000
    elif field == "co_names": changed = value + ("unexpected_name",)
    else:
        import types
        changed = tuple(item.replace(co_consts=item.co_consts + ("changed nested constant",)) if type(item) is types.CodeType else item for item in value)
    altered = original.replace(**{field: changed})
    assert _native_code_shape(original) != _native_code_shape(altered)


@pytest.fixture(scope="module")
def native_process_observation_binary(tmp_path_factory):
    """Actual bounded native observation, with explicit syscall-denial leaves.

    Actual exit tests fork and truly reap a disposable child. No signal, model,
    Provider, production process, control key or operational approval is used.
    """
    folder = tmp_path_factory.mktemp("native-r3-process-observation")
    source = Path(__file__).parents[3] / "tools/macos/kronos_launcher.c"
    text = source.read_text().replace("int main(void) {", "int unused_application_main(void) {")
    original = "*size=proc_pidinfo(pid,PROC_PIDTBSDINFO,0,process,sizeof(*process));"
    assert text.count(original) == 1
    text = text.replace(original, "*size=fixture_process_info(pid,PROC_PIDTBSDINFO,0,process,sizeof(*process));")
    unit = folder / "process-observation.c"
    unit.write_text('#include <stdint.h>\n#include <pthread.h>\nstatic int fixture_process_info(int,int,uint64_t,void*,int);\n' + text + r'''
static const char *fixture_fault="actual";
static int fixture_process_info(int pid,int flavor,uint64_t arg,void *buffer,int bytes) {
    if(!strcmp(fixture_fault,"error")){errno=EACCES;return 0;}
    if(!strcmp(fixture_fault,"short")){errno=0;return bytes-1;}
    if(!strcmp(fixture_fault,"error-with-full")){
        int n=proc_pidinfo(pid,flavor,arg,buffer,bytes);errno=EACCES;return n;
    }
    int n=proc_pidinfo(pid,flavor,arg,buffer,bytes);
    if(!strcmp(fixture_fault,"wrong-pid")&&n==bytes){
        ((struct proc_bsdinfo*)buffer)->pbi_pid++;errno=0;
    }
    return n;
}
static void *fixture_reap(void *value) {
    pid_t pid=*(pid_t*)value;int status=0;
    while(waitpid(pid,&status,0)<0&&errno==EINTR){}
    return NULL;
}
int main(int argc,char **argv) {
    if(argc!=2)return 90;
    if(!strcmp(argv[1],"decimal")){
        unsigned long long value=0;
        if(!ffr3_process_decimal("0",&value)||value||!ffr3_process_decimal("18446744073709551615",&value)||value!=ULLONG_MAX)return 91;
        const char *bad[]={"","00","01","-1","+1","1x","18446744073709551616"};
        for(size_t i=0;i<sizeof(bad)/sizeof(bad[0]);i++)if(ffr3_process_decimal(bad[i],&value))return 92;
        puts("decimal=bounded");return 0;
    }
    int descriptors[2];if(pipe(descriptors)!=0)return 93;
    pid_t child=fork();if(child<0)return 94;
    if(child==0){
        close(descriptors[1]);char byte;if(read(descriptors[0],&byte,1)!=1)_exit(95);
        close(descriptors[0]);usleep(180000);_exit(0);
    }
    close(descriptors[0]);struct proc_bsdinfo birth={0};
    if(proc_pidinfo(child,PROC_PIDTBSDINFO,0,&birth,sizeof(birth))!=(int)sizeof(birth))return 96;
    pthread_t reaper;if(pthread_create(&reaper,NULL,fixture_reap,&child)!=0)return 97;
    if(write(descriptors[1],"x",1)!=1)return 98;close(descriptors[1]);
    struct timespec stop;clock_gettime(CLOCK_MONOTONIC,&stop);
    unsigned long long start=ffr3_now_ns();int exiting=1;
    if(!strcmp(argv[1],"live-expired")){stop.tv_nsec+=40000000L;if(stop.tv_nsec>=1000000000L){stop.tv_sec++;stop.tv_nsec-=1000000000L;}}
    else if(!strcmp(argv[1],"already-expired"))stop.tv_sec--;
    else stop.tv_sec+=2;
    if(!strcmp(argv[1],"birth"))exiting=0;
    unsigned long long expected_seconds=birth.pbi_start_tvsec;
    if(!strcmp(argv[1],"reused"))expected_seconds++;
    if(!strcmp(argv[1],"invalid-microseconds"))birth.pbi_start_tvusec=1000000ULL;
    if(!strcmp(argv[1],"error")||!strcmp(argv[1],"short")||!strcmp(argv[1],"wrong-pid")||!strcmp(argv[1],"error-with-full"))fixture_fault=argv[1];
    struct proc_bsdinfo observed={0};int size=-1,error=-1;
    int accepted=ffr3_observe_process(child,expected_seconds,birth.pbi_start_tvusec,exiting,&stop,&observed,&size,&error);
    unsigned long long elapsed=ffr3_now_ns()-start;
    if(pthread_join(reaper,NULL)!=0)return 99;
    printf("accepted=%d;elapsed_ns=%llu;size=%d;errno=%d;expected_pid=%u;observed_pid=%u",accepted,elapsed,size,error,birth.pbi_pid,observed.pbi_pid);
    return 0;
}
''')
    binary = folder / "process-observation"
    compiled = subprocess.run(["clang", "-Wall", "-Wextra", "-Werror", str(unit), "-o", str(binary)], capture_output=True, text=True)
    assert compiled.returncode == 0, compiled.stderr
    return binary


def _actual_native_process_observation(binary, mode):
    result = subprocess.run([str(binary), mode], capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stderr
    return dict((key, int(value)) for key, value in (field.split("=", 1) for field in result.stdout.split(";")))


def test_native_exit_observation_waits_for_actual_matching_child_to_exit(native_process_observation_binary):
    import errno
    observed = _actual_native_process_observation(native_process_observation_binary, "delayed")
    assert observed["accepted"] == 1
    assert observed["size"] == 0 and observed["errno"] == errno.ESRCH
    assert 120_000_000 <= observed["elapsed_ns"] < 2_000_000_000


def test_native_exit_observation_live_process_cannot_outlive_original_stop(native_process_observation_binary):
    observed = _actual_native_process_observation(native_process_observation_binary, "live-expired")
    assert observed["accepted"] == 0
    assert 30_000_000 <= observed["elapsed_ns"] < 180_000_000
    assert observed["expected_pid"] == observed["observed_pid"]


@pytest.mark.parametrize("mode", ["already-expired", "invalid-microseconds", "error", "short", "wrong-pid", "error-with-full"])
def test_native_process_observation_denies_expiry_and_ambiguous_kernel_results(native_process_observation_binary, mode):
    observed = _actual_native_process_observation(native_process_observation_binary, mode)
    assert observed["accepted"] == 0
    assert observed["elapsed_ns"] < 180_000_000


@pytest.mark.parametrize("mode", ["birth", "reused"])
def test_native_process_observation_preserves_actual_birth_and_reuse_evidence(native_process_observation_binary, mode):
    observed = _actual_native_process_observation(native_process_observation_binary, mode)
    assert observed["accepted"] == 1
    assert observed["expected_pid"] == observed["observed_pid"]
    assert observed["elapsed_ns"] < 180_000_000


def test_native_process_binding_decimal_values_are_canonical_and_bounded(native_process_observation_binary):
    result = subprocess.run([str(native_process_observation_binary), "decimal"], capture_output=True, text=True)
    assert result.returncode == 0 and result.stdout == "decimal=bounded\n", result.stderr
