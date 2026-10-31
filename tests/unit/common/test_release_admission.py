"""Disposable anchors/processes; real flock custody, never production admission."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
from kronos.common import release_admission as admission


@pytest.fixture(autouse=True)
def preparatory_pin_disposable_binding(monkeypatch):
    from tests.unit.tools.test_place_release_pair import assert_actual_preparatory_source
    assert_actual_preparatory_source()
    monkeypatch.setattr(admission,'PERSISTENT_ANCHOR_BINDING',None)


@pytest.mark.parametrize('finding',('valid','wrong-digest','wrong-installation','unsafe-mode','symlink-input',
    'existing-destination','expired','ordinary-reader'))
def test_s305_enrollment_preview_cannot_admit(tmp_path,anchor,monkeypatch,record_property,finding):
    from hashlib import sha256
    a=admission;fd=held(anchor)
    try:
        observed=a.descriptor_filesystem_identity(fd)
        core=dict(anchor_path=str(anchor.path),device=anchor.device,inode=anchor.inode,owner=anchor.owner,
            bundle_id='com.project-kronos.browser-v1',bundle_path=str(tmp_path/'KRONOS.app'),repository_path=str(tmp_path/'repository'))
        installation=dict(identity=sha256(a._canonical_document(core)).hexdigest(),**core)
        raw=a._canonical_document(installation);source=tmp_path/'placement-input.json';source.write_bytes(raw);source.chmod(0o600)
        destination=anchor.path/'enrollment.json'
        reference=dict(identity=installation['identity'],path=str(source),bytes=len(raw),sha256=sha256(raw).hexdigest())
        policy=dict(schema='KRONOS_PERSISTENT_ANCHOR_BINDING_V1',installation_identity=installation['identity'],
            enrollment=dict(reference,path=str(destination)),anchor_path=str(anchor.path),**observed,owner=anchor.owner,
            required_mode='0700',bundle_id=core['bundle_id'],bundle_path=core['bundle_path'],repository_path=core['repository_path'])
        monkeypatch.setattr(a,'PERSISTENT_ANCHOR_BINDING',a._canonical_document(policy));monkeypatch.setattr(a,'APPROVED_BINDING',anchor)
        parent=os.getppid();birth=a.kernel_process_birth(parent)
        class Checks:
            def __init__(self):self.budget=a.ValidationBudget(a.monotonic_ns()+5_000_000_000)
            def check(self):
                self.budget.check()
                assert os.getppid()==parent and a.kernel_process_birth(parent)==birth
        checks=Checks()
        if finding=='wrong-digest':reference['sha256']='f'*64
        elif finding=='wrong-installation':
            value=dict(installation,owner=installation['owner']+1);source.write_bytes(a._canonical_document(value))
            reference.update(bytes=source.stat().st_size,sha256=sha256(source.read_bytes()).hexdigest())
        elif finding=='unsafe-mode':source.chmod(0o644)
        elif finding=='symlink-input':
            target=tmp_path/'symlink-target.json';source.rename(target);source.symlink_to(target)
        elif finding=='existing-destination':destination.write_bytes(raw);destination.chmod(0o600)
        elif finding=='expired':checks.budget=a.ValidationBudget(a.monotonic_ns()-1)
        if finding in ('valid','ordinary-reader'):
            assert a.preview_enrollment(anchor,reference,checks=checks)==installation
            with pytest.raises((ValueError,FileNotFoundError)):
                a.frozen_installation(core['repository_path'],core['bundle_path'],core['anchor_path'])
            assert not destination.exists()
        else:
            with pytest.raises((ValueError,OSError)):a.preview_enrollment(anchor,reference,checks=checks)
        # The preview neither adopts nor releases the native owner's lock.
        independent=os.open(anchor.path,os.O_RDONLY|os.O_DIRECTORY)
        try:
            with pytest.raises(BlockingIOError):fcntl.flock(independent,fcntl.LOCK_EX|fcntl.LOCK_NB)
        finally:os.close(independent)
        record_property('application_before_teardown','ACTUAL FD FILESYSTEM IDENTITY AND EXCLUSION; READ-ONLY PREVIEW; ORIGINAL BUDGET; NO ADMISSION OR PUBLICATION')
    finally:os.close(fd)


@pytest.fixture
def anchor(tmp_path):
    path = tmp_path / "anchor"
    path.mkdir(mode=0o700)
    st = path.stat()
    return admission.AnchorBinding(path, st.st_dev, st.st_ino, os.getuid())


def held(binding):
    fd = admission.open_anchor(binding)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return fd


def available(binding):
    fd = admission.open_anchor(binding)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        return True
    finally:
        os.close(fd)


def fork_result(fn):
    read, write = os.pipe()
    child = os.fork()
    if child == 0:
        os.close(read)
        try:
            result = {"result": fn()}
        except BaseException as error:
            result = {"error": type(error).__name__, "message": str(error)}
        os.write(write, json.dumps(result).encode())
        os.close(write)
        os._exit(0)
    os.close(write)
    raw = os.read(read, 65536)
    os.close(read)
    assert os.waitpid(child, 0)[1] == 0
    return json.loads(raw)


def custody(fd, binding):
    return admission.AdmissionCustody(fd, binding, os.getppid(),
        parent_image=lambda pid: admission.CANONICAL_PARENT)


def test_real_shared_custody_close_does_not_unlock_parent(anchor):
    fd = held(anchor)
    try:
        def child():
            owner = custody(fd, anchor)
            assert not os.get_inheritable(fd)
            owner.check()
            owner.begin_failure_cleanup()
            owner.completed_failure_cleanup()
            return owner.released
        assert fork_result(child) == {"result": True}
        assert not available(anchor)
    finally:
        os.close(fd)
    assert available(anchor)


@pytest.mark.parametrize("fault", ["independent", "closed", "wrong-parent", "wrong-image"])
def test_invalid_custody_never_becomes_authority(anchor, fault):
    fd = held(anchor)
    try:
        def child():
            supplied = fd
            if fault == "independent": supplied = admission.open_anchor(anchor)
            if fault == "closed": os.close(supplied)
            return admission.AdmissionCustody(supplied, anchor,
                os.getppid() + (1 if fault == "wrong-parent" else 0),
                parent_image=lambda pid: "wrong" if fault == "wrong-image" else admission.CANONICAL_PARENT)
        result = fork_result(child)
        assert result["error"] in {"ValueError", "BlockingIOError", "OSError"}
        assert not available(anchor)
    finally:
        os.close(fd)


@pytest.mark.parametrize("fault", ["missing", "symlink", "unsafe-mode", "wrong-inode", "wrong-device", "wrong-owner", "unapproved"])
def test_anchor_denials_do_not_create_or_rebind(anchor, fault):
    path = anchor.path
    binding = anchor
    if fault == "missing": path.rmdir()
    if fault == "symlink":
        path.rename(path.with_name("original"));path.symlink_to(path.with_name("original"))
    if fault == "unsafe-mode": path.chmod(0o755)
    if fault == "wrong-inode": binding = admission.AnchorBinding(path, anchor.device, anchor.inode + 1, anchor.owner)
    if fault == "wrong-device": binding = admission.AnchorBinding(path, anchor.device + 1, anchor.inode, anchor.owner)
    if fault == "wrong-owner": binding = admission.AnchorBinding(path, anchor.device, anchor.inode, anchor.owner + 1)
    if fault == "unapproved": binding = admission.AnchorBinding(path, 0, 0, anchor.owner)
    with pytest.raises((ValueError, OSError)):
        admission.open_anchor(binding)
    if fault == "missing": assert not path.exists()


def test_repository_replacement_does_not_select_a_lock_domain(anchor, tmp_path):
    repo = tmp_path / "repo";repo.mkdir()
    fd = held(anchor)
    try:
        repo.rename(tmp_path / "retired-repo");repo.mkdir()
        assert not available(anchor)
        assert fork_result(lambda: custody(fd, anchor).check()) == {"result": None}
    finally:
        os.close(fd)


def test_replaced_anchor_denies_inherited_startup(anchor):
    fd = held(anchor)
    try:
        anchor.path.rename(anchor.path.with_name("old-anchor"));anchor.path.mkdir(mode=0o700)
        assert fork_result(lambda: custody(fd, anchor).check())["error"] == "ValueError"
    finally:
        os.close(fd)


def test_incomplete_cleanup_retains_real_custody(anchor):
    fd = held(anchor)
    try:
        def child():
            owner = custody(fd, anchor)
            owner.begin_failure_cleanup()
            with pytest.raises(ValueError):owner.check()
            assert not owner.released
            assert not available(anchor)
            # Only a separately completed cleanup closes this reference.
            owner.completed_failure_cleanup()
            return owner.released
        assert fork_result(child) == {"result": True}
        assert not available(anchor)
    finally:
        os.close(fd)


def ready_server(tmp_path, *, valid=True):
    runtime = "a" * 64
    root = tmp_path / "receipt"; (root / "maintenance").mkdir(parents=True)
    receipt = {"schema": "RUNTIME_STARTUP_MAINTENANCE_EXIT_V1", "runtime_identity": runtime,
        "maintenance_identity": "generation", "trigger": "VERIFIED_CANONICAL_STARTUP", "at": "2026-10-25T00:00:00+00:00"}
    if valid:(root / "maintenance" / (runtime + "-startup.json")).write_text(json.dumps(receipt))
    governance = SimpleNamespace(maintenance_status=lambda: {"startup": "READY", "active": False, "failure": None},
        shutting_down=False, process=SimpleNamespace(runtime_identity=runtime),
        maintenance_identity="generation", store=SimpleNamespace(root=root))
    return SimpleNamespace(connection_governance=governance, socket=SimpleNamespace(fileno=lambda: 10), _domain_closed=False)


@pytest.mark.parametrize("fault", [None, "missing-receipt", "blocked", "cleanup", "shutdown", "wrong-receipt"])
def test_ready_release_requires_durable_completion_and_no_cleanup(anchor, tmp_path, fault):
    server = ready_server(tmp_path, valid=fault != "missing-receipt")
    if fault == "blocked":server.connection_governance.maintenance_status=lambda: {"startup": "BLOCKED", "active": True, "failure": "FAILED"}
    if fault == "shutdown":server.connection_governance.shutting_down=True
    if fault == "wrong-receipt":
        receipt=next((server.connection_governance.store.root/'maintenance').iterdir());receipt.write_text('{}')
    fd = held(anchor)
    try:
        def child():
            owner = custody(fd, anchor)
            if fault == "cleanup":owner.begin_failure_cleanup()
            if fault:
                with pytest.raises((ValueError, OSError)):owner.release_ready(server)
                return not owner.released
            owner.release_ready(server)
            return owner.released
        assert fork_result(child) == {"result": True}
        assert not available(anchor)
    finally:
        os.close(fd)
    assert available(anchor)


def test_python_helpers_do_not_receive_admission_descriptor(anchor):
    fd = held(anchor)
    try:
        def child():
            owner = custody(fd, anchor)
            code='import os,sys;\ntry:os.fstat(int(sys.argv[1]));raise SystemExit(7)\nexcept OSError:pass'
            result=subprocess.run([sys.executable,'-B','-c',code,str(fd)],close_fds=True,timeout=5)
            owner.check()
            return result.returncode
        assert fork_result(child) == {"result": 0}
    finally:
        os.close(fd)


@pytest.mark.parametrize("phase", ["before-validation", "during-startup"])
def test_actual_parent_loss_denies_further_effects(anchor, tmp_path, phase):
    script = tmp_path / 'parent-loss.py'
    script.write_text('''import os,sys,time,json,fcntl
from pathlib import Path
from kronos.common import release_admission as a
from hashlib import sha256
assert sha256(a.PERSISTENT_ANCHOR_BINDING).hexdigest()=='85ea2fa04da20f40377b242d71db96762020e77042a7b4923c331c6f82ab7891'
a.PERSISTENT_ANCHOR_BINDING=None
path=Path(sys.argv[1]);st=path.stat();binding=a.AnchorBinding(path,st.st_dev,st.st_ino,os.getuid())
fd=a.open_anchor(binding);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
r,w=os.pipe();parent=os.getpid();child=os.fork()
if child:
 os.close(w);os.read(r,1);os.close(r);os._exit(0)
os.close(r)
try:
 if sys.argv[2]=='during-startup': owner=a.AdmissionCustody(fd,binding,parent,parent_image=lambda p:a.CANONICAL_PARENT)
 os.write(w,b'x');os.close(w)
 deadline=time.monotonic()+3
 while os.getppid()==parent and time.monotonic()<deadline:time.sleep(.01)
 try:
  if sys.argv[2]=='before-validation':owner=a.AdmissionCustody(fd,binding,parent,parent_image=lambda p:a.CANONICAL_PARENT)
  else:owner.check()
 except ValueError:
  print('PARENT_LOSS_DENIED',flush=True)
  os.close(fd)
  raise SystemExit(0)
 raise SystemExit(9)
except BaseException:
 raise
''')
    result = subprocess.run([sys.executable,'-B',str(script),str(anchor.path),phase],
        capture_output=True,text=True,timeout=6)
    assert result.returncode==0
    assert result.stdout.strip()=='PARENT_LOSS_DENIED'
    assert available(anchor)


def test_approved_production_binding_initializes_and_matches_native_literals():
    # Inspect literals/imported data only; never open or lock the production path.
    import re
    assert admission.APPROVED_BINDING == admission.AnchorBinding(
        Path('/Users/imranali/Library/Application Support/KRONOS/runtime'),
        16777232, 694844364, 501)
    source = (Path(__file__).resolve().parents[3] / 'tools/macos/kronos_launcher.c').read_text()
    for name, expected in [('device', admission.APPROVED_BINDING.device),
                           ('inode', admission.APPROVED_BINDING.inode)]:
        value = re.search(r'approved_admission_' + name + r' = ([0-9]+);', source)
        assert value and int(value.group(1)) == expected
    anchor = re.search(r'static const char \*admission_anchor = "([^"]+)";', source)
    assert anchor and anchor.group(1) == str(admission.APPROVED_BINDING.path)


@pytest.mark.parametrize('fault', ['missing', 'wrong-path'])
def test_unapproved_binding_denies_before_custody_or_path_access(monkeypatch, anchor, fault):
    binding = None if fault == 'missing' else anchor
    monkeypatch.setattr(admission, 'APPROVED_BINDING', binding)
    def forbidden(*args, **kwargs):pytest.fail('unapproved binding reached custody/path access')
    monkeypatch.setattr(admission, 'AdmissionCustody', forbidden)
    monkeypatch.setattr(admission, 'open_anchor', forbidden)
    with pytest.raises(ValueError, match='BINDING_NOT_APPROVED'):admission.adopt_from_launcher()


def test_close_only_contract_has_no_explicit_unlock():
    source=Path(admission.__file__).read_text()
    assert 'LOCK_UN' not in source


@pytest.mark.parametrize('fault',['closed','reopened','anchor-replaced'])
def test_custody_change_after_valid_adoption_denies_next_startup_phase(anchor,fault):
    fd=held(anchor)
    try:
        def child():
            owner=custody(fd,anchor)
            if fault in {'closed','reopened'}:
                os.close(fd)
                if fault=='reopened':
                    replacement=admission.open_anchor(anchor)
                    os.dup2(replacement,fd,inheritable=False)
                    if replacement!=fd:os.close(replacement)
            else:
                anchor.path.rename(anchor.path.with_name('retired-anchor'))
                anchor.path.mkdir(mode=0o700)
            with pytest.raises((ValueError,OSError)):owner.check()
            return not owner.released
        assert fork_result(child)=={'result':True}
    finally:
        os.close(fd)


@pytest.fixture
def validation_case(monkeypatch):
    monkeypatch.setattr(admission,'_VALIDATION_UNRESOLVED',False)
    monkeypatch.setattr(admission,'_OWNED_VALIDATION_HELPERS',{})
    yield
    # Dispose only the Popen-owned fixture children; never groups/other processes.
    for child in admission._OWNED_VALIDATION_HELPERS.values():
        if child.poll() is None:child.kill()
        child.wait(timeout=3)


def test_validation_success_preserves_bytes_and_excludes_unrelated_secrets(validation_case,monkeypatch,tmp_path):
    monkeypatch.setenv('KRONOS_MAINTENANCE_PROOF','DISPOSABLE_SECRET')
    monkeypatch.setenv('OPENAI_API_KEY','DISPOSABLE_SECRET')
    code='import os,sys;assert "KRONOS_MAINTENANCE_PROOF" not in os.environ;assert "OPENAI_API_KEY" not in os.environ;sys.stdout.buffer.write(sys.stdin.buffer.read())'
    budget=admission.ValidationBudget(admission.monotonic_ns()+2_000_000_000)
    assert admission.validation_output([sys.executable,'-B','-c',code],cwd=tmp_path,
        budget=budget,ceiling=1,phase='TEST_NORMAL',input_bytes=b'exact\nbytes')==b'exact\nbytes'
    assert not budget.failed and not admission.validation_unresolved()
    assert admission._OWNED_VALIDATION_HELPERS=={}


@pytest.mark.parametrize('mode',['blocked-read','blocked-write','output-limit','failure'])
def test_validation_failures_are_bounded_and_sticky(validation_case,tmp_path,capfd,mode):
    import time
    code={'blocked-read':'import time;time.sleep(3)',
          'blocked-write':'import time;time.sleep(3)',
          'output-limit':'print("x"*1000)', 'failure':'raise SystemExit(7)'}[mode]
    budget=admission.ValidationBudget(admission.monotonic_ns()+200_000_000)
    started=time.monotonic()
    with pytest.raises((ValueError,subprocess.CalledProcessError)):
        admission.validation_output([sys.executable,'-B','-c',code],cwd=tmp_path,budget=budget,
            ceiling=1,phase='TEST_FAILURE',input_bytes=b'x'*1_000_000 if mode=='blocked-write' else b'',capacity=100)
    assert time.monotonic()-started<1
    assert budget.failed
    outcome=json.loads(capfd.readouterr().err.strip())
    assert outcome['phase']=='TEST_FAILURE' and outcome['direct_child']>0
    assert outcome['clock']=='CLOCK_MONOTONIC'
    if mode!='failure':assert outcome['cleanup']=='CLEANUP_UNRESOLVED'
    with pytest.raises(ValueError):
        admission.validation_output([sys.executable,'-B','-c','print("never")'],cwd=tmp_path,
            budget=budget,ceiling=1,phase='NO_RETRY')


def test_expiry_before_spawn_reports_without_creating_child(validation_case,tmp_path,capfd):
    budget=admission.ValidationBudget(admission.monotonic_ns()-1)
    with pytest.raises(ValueError,match='DEADLINE'):
        admission.validation_output([sys.executable,'-B','-c','raise SystemExit(9)'],cwd=tmp_path,
            budget=budget,ceiling=1,phase='BEFORE_SPAWN')
    assert admission._OWNED_VALIDATION_HELPERS=={}
    outcome=json.loads(capfd.readouterr().err)
    assert outcome['direct_child'] is None and outcome['observed_result']=='NOT_STARTED_DEADLINE'


def test_late_zero_exit_is_rejected_not_reclassified_as_success(validation_case,monkeypatch,tmp_path,capfd):
    import time
    marker=tmp_path/'zero-exit'
    real=admission.monotonic_ns;deadline=real()+1_000_000_000;calls=0
    def clock():
        nonlocal calls
        calls+=1
        if calls>=3:
            end=time.monotonic()+.5
            while not marker.exists() and time.monotonic()<end:time.sleep(.005)
            time.sleep(.05)
            return deadline+1
        return real()
    monkeypatch.setattr(admission,'monotonic_ns',clock)
    budget=admission.ValidationBudget(deadline)
    with pytest.raises(ValueError,match='DEADLINE'):
        admission.validation_output([sys.executable,'-B','-c',
            'from pathlib import Path;Path('+repr(str(marker))+').write_text("zero")'],
            cwd=tmp_path,budget=budget,ceiling=1,phase='LATE_ZERO')
    assert marker.exists() and budget.failed and admission.validation_unresolved()
    assert all(child.poll()==0 for child in admission._OWNED_VALIDATION_HELPERS.values())
    assert json.loads(capfd.readouterr().err)['cleanup']=='CLEANUP_UNRESOLVED'


def test_monotonic_domain_and_nested_deadline_cannot_reset(monkeypatch):
    now=admission.monotonic_ns();end=now+100_000_000
    monkeypatch.setenv('KRONOS_VALIDATION_CLOCK','CLOCK_MONOTONIC')
    monkeypatch.setenv('KRONOS_VALIDATION_DEADLINE_NS',str(end))
    budget=admission.inherited_budget(60,required=True)
    assert budget.deadline_ns==end and budget.capped(20)<=end
    monkeypatch.setenv('KRONOS_VALIDATION_CLOCK','OTHER_CLOCK')
    with pytest.raises(ValueError,match='CLOCK_DOMAIN'):admission.inherited_budget(60,required=True)


def test_validation_python_spawn_contract_is_close_fds_without_preexec():
    source=Path(admission.__file__).read_text()
    helper=source.split('def validation_output(',1)[1]
    assert 'close_fds=True' in helper
    assert 'preexec_fn=' not in helper and 'pass_fds=' not in helper
    assert 'killpg' not in helper


def test_unwritable_outcome_stream_keeps_cleanup_unresolved(tmp_path):
    code='''import os,json
from kronos.common import release_admission as a
os.close(2)
a.report_validation('DISPOSABLE',1,None,'DENIED','NOT_STARTED')
print(json.dumps({'unresolved':a.validation_unresolved()}))
'''
    result=subprocess.run([sys.executable,'-B','-c',code],capture_output=True,text=True,timeout=3)
    assert result.returncode==0
    assert json.loads(result.stdout)=={'unresolved':True}


def test_ignored_sigchld_denies_before_spawning_any_validator(tmp_path):
    code='''import signal,json,sys
from kronos.common import release_admission as a
signal.signal(signal.SIGCHLD,signal.SIG_IGN)
try:a.validation_output([sys.executable,'-B','-c','raise SystemExit(9)'],cwd=None,
 budget=a.ValidationBudget(a.monotonic_ns()+1000000000),ceiling=1,phase='NO_AUTOREAP')
except ValueError:pass
else:raise SystemExit(8)
assert not a._OWNED_VALIDATION_HELPERS
assert a.validation_unresolved()
print('OWNERSHIP_DENIED_BEFORE_SPAWN')
'''
    result=subprocess.run([sys.executable,'-B','-c',code],capture_output=True,text=True,timeout=3)
    assert result.returncode==0,result.stderr
    assert result.stdout.strip()=='OWNERSHIP_DENIED_BEFORE_SPAWN'
    record=json.loads(result.stderr)
    assert record['direct_child'] is None and record['cleanup']=='CLEANUP_UNRESOLVED'


def test_environment_keeps_destination_selectors_for_rejection():
    environment=admission.validation_environment({'DEVELOPER_DIR':'fixture-invalid',
        'GIT_SSH_COMMAND':'fixture-invalid','KRONOS_MAINTENANCE_PROOF':'secret',
        'SSH_AUTH_SOCK':'fixture-sock','KRB5CCNAME':'fixture-cache'})
    assert environment=={'DEVELOPER_DIR':'fixture-invalid','GIT_SSH_COMMAND':'fixture-invalid',
        'SSH_AUTH_SOCK':'fixture-sock','KRB5CCNAME':'fixture-cache'}


@pytest.mark.parametrize('partial',['complete','absent-helpers','broken-poll'])
def test_failed_backend_reports_then_retains_existing_custody(anchor,partial):
    code='''import os,fcntl,sys
from pathlib import Path
from types import SimpleNamespace
from kronos.common import release_admission as a
from hashlib import sha256
assert sha256(a.PERSISTENT_ANCHOR_BINDING).hexdigest()=='85ea2fa04da20f40377b242d71db96762020e77042a7b4923c331c6f82ab7891'
a.PERSISTENT_ANCHOR_BINDING=None
path=Path(sys.argv[1]);st=path.stat();binding=a.AnchorBinding(path,st.st_dev,st.st_ino,os.getuid())
fd=a.open_anchor(binding);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
def broken():raise RuntimeError('fixture unfinished helper')
modules={'complete':(a,), 'absent-helpers':(a,SimpleNamespace()),
 'broken-poll':(a,SimpleNamespace(_OWNED_VALIDATION_HELPERS={'owned':SimpleNamespace(poll=broken)}))}[sys.argv[2]]
a.retain_failure_custody(SimpleNamespace(descriptor=fd,released=False,budget=None),modules)
'''
    process=subprocess.Popen([sys.executable,'-B','-c',code,str(anchor.path),partial],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        record=json.loads(process.stderr.readline())
        assert record['observed_result']=='STARTUP_DENIED_CUSTODY_RETAINED'
        assert record['cleanup']=='CLEANUP_UNRESOLVED'
        assert not available(anchor)
        with pytest.raises(subprocess.TimeoutExpired):process.wait(timeout=.2)
    finally:
        if process.poll() is None:process.terminate()
        process.wait(timeout=3)
    assert available(anchor)


def test_e02_actual_descriptor_filesystem_identity_and_exclusion(anchor, tmp_path):
    """Real macOS APIs/FDs; no device/volume or lock-acceptance seam."""
    import ctypes
    import struct
    class AttrList(ctypes.Structure):
        _fields_ = [("bitmapcount", ctypes.c_uint16), ("reserved", ctypes.c_uint16),
                    ("common", ctypes.c_uint32), ("volume", ctypes.c_uint32),
                    ("directory", ctypes.c_uint32), ("file", ctypes.c_uint32),
                    ("fork", ctypes.c_uint32)]
    libc = ctypes.CDLL(None, use_errno=True)
    libc.fgetattrlist.argtypes = [ctypes.c_int, ctypes.POINTER(AttrList),
                                 ctypes.c_void_p, ctypes.c_size_t, ctypes.c_ulong]
    fd = held(anchor)
    try:
        observations = []
        for common, volume, expected_length in [(0x82000000, 0, 32), (0x80000000, 0x80040000, 40)]:
            attrs = AttrList(5, 0, common, volume, 0, 0, 0)
            buffer = ctypes.create_string_buffer(128)
            rc = libc.fgetattrlist(fd, ctypes.byref(attrs), buffer, len(buffer), 0)
            error = ctypes.get_errno()
            raw = buffer.raw
            print('E02_ACTUAL_FD_ATTRIBUTE', json.dumps(dict(rc=rc, errno=error,
                requested_common=common, requested_volume=volume, raw=raw.hex())))
            assert rc == 0, (common, volume, error)
            length = struct.unpack_from('=I', raw)[0]
            assert length == expected_length
            returned = struct.unpack_from('=5I', raw, 4)
            assert returned[0] & 0x80000000
            if volume:
                assert returned[1] & 0x40000
                assert raw[24:40] != bytes(16)
            else:
                assert returned[0] & 0x02000000
                assert struct.unpack_from('=Q', raw, 24)[0] == os.fstat(fd).st_ino
            observations.append(raw[:length].hex())
        assert not available(anchor)
        original = anchor.path.with_name('original-anchor')
        anchor.path.rename(original)
        anchor.path.mkdir(mode=0o700)
        assert os.fstat(fd).st_ino == original.stat().st_ino
        assert anchor.path.stat().st_ino != os.fstat(fd).st_ino
        assert fork_result(lambda: custody(fd, anchor).check())['error'] == 'ValueError'
        print('E02_APPLICATION_OBSERVATION', json.dumps(dict(actual_attributes=observations,
            independent_lock_conflict=True, named_replacement_denied=True,
            production_observations=False, boot_device_simulation=False)))
    finally:
        os.close(fd)
        print('E02_SEPARATE_FIXTURE_TEARDOWN', json.dumps(dict(held_descriptor_closed=True)))


@pytest.mark.parametrize('fault',('volume','file-id','enrollment','private-mode','replacement'))
def test_e02_actual_persistent_anchor_denials(tmp_path,monkeypatch,record_property,fault):
    from tests.unit.common import test_legacy_bootstrap as setup
    c=setup._e02_installed_control(tmp_path,monkeypatch)
    try:
        policy=dict(c.persistent)
        if fault=='volume':policy['volume_uuid']='00000000-0000-0000-0000-000000000001'
        if fault=='file-id':policy['file_id']+=1
        if fault=='enrollment':Path(policy['enrollment']['path']).write_bytes(b'changed frozen enrollment')
        if fault=='private-mode':c.anchor.chmod(0o500)
        if fault=='replacement':c.anchor.rename(c.anchor.with_name('preserved-anchor'));c.anchor.mkdir(mode=0o700)
        monkeypatch.setattr(admission,'PERSISTENT_ANCHOR_BINDING',admission._canonical_document(policy))
        with pytest.raises((ValueError,OSError)):
            admission.open_anchor(c.custody.binding)
        assert not c.custody.released
        record_property('e02_application',json.dumps(dict(fault=fault,actual_fd_attribute_comparison=True,
            custody_not_released=True,fixture_teardown_separate=True)))
    finally:
        if fault=='private-mode':c.anchor.chmod(0o700)
        c.custody._close()


@pytest.mark.parametrize('fault',('changed-boot','exact-deadline','late-deadline','missing-inherited-boot','wrong-inherited-boot'))
def test_e02_original_budget_and_boot_fence(tmp_path,monkeypatch,record_property,fault):
    from tests.unit.common import test_legacy_bootstrap as setup
    c=setup._e02_installed_control(tmp_path,monkeypatch)
    budget=c.budget;original=budget.deadline_ns;boot=budget.boot_identity
    try:
        if fault=='changed-boot':monkeypatch.setattr(admission,'kernel_boot_identity',lambda:'00000000-0000-0000-0000-000000000001')
        if fault in {'exact-deadline','late-deadline'}:
            monkeypatch.setattr(admission,'monotonic_ns',lambda:original+(fault=='late-deadline'))
        if fault in {'missing-inherited-boot','wrong-inherited-boot'}:
            monkeypatch.setenv('KRONOS_VALIDATION_CLOCK','CLOCK_MONOTONIC')
            monkeypatch.setenv('KRONOS_VALIDATION_DEADLINE_NS',str(original))
            if fault=='missing-inherited-boot':monkeypatch.delenv('KRONOS_VALIDATION_BOOT_SESSION',raising=False)
            else:monkeypatch.setenv('KRONOS_VALIDATION_BOOT_SESSION','00000000-0000-0000-0000-000000000001')
            with pytest.raises(ValueError,match='BOOT_CONTEXT'):admission.inherited_budget(120,required=True)
        else:
            with pytest.raises(ValueError):c.custody.check()
            assert budget.failed
            monkeypatch.setattr(admission,'kernel_boot_identity',lambda:boot)
            with pytest.raises(ValueError):budget.check()
        assert budget.deadline_ns==original and not c.custody.released
        record_property('e02_clock_simulation',json.dumps(dict(fault=fault,actual_budget_type=True,
            unchanged_original_deadline=original,host_boot_or_clock_changed=False,application_cleanup_claimed=False)))
    finally:c.custody._close()


@pytest.mark.parametrize('fault',('short-zero','zero','file-fsync','directory-fsync','close','exact-expiry'))
def test_e02_actual_exclusive_publication_preserves_uncertainty(tmp_path,monkeypatch,record_property,fault):
    from tests.unit.common import test_legacy_bootstrap as setup
    from kronos.common import legacy_bootstrap as adapter
    c=setup._e02_installed_control(tmp_path,monkeypatch)
    path=c.journal/'bounded-publication-unit.json';value={'meaning':'PERSISTENCE UNIT ONLY; NO OWNER OR AUTHORITY ASSERTION'}
    expected=adapter._canonical(value);real_open=os.open;real_write=os.write;real_sync=os.fsync;real_close=os.close
    tagged={'fd':None,'writes':0,'fired':False};parent_inode=c.journal.stat().st_ino
    try:
        with monkeypatch.context() as patch:
            def opened(name,flags,*args,**kwargs):
                fd=real_open(name,flags,*args,**kwargs)
                if str(name)==str(path) and flags&os.O_CREAT:tagged['fd']=fd
                return fd
            def written(fd,raw):
                if fd==tagged['fd'] and fault in {'short-zero','zero'}:
                    tagged['writes']+=1
                    if fault=='short-zero' and tagged['writes']==1:return real_write(fd,raw[:3])
                    tagged['fired']=True;return 0
                return real_write(fd,raw)
            def synced(fd):
                targeted=(fd==tagged['fd'] and fault in {'file-fsync','exact-expiry'}) or (
                    fault=='directory-fsync' and os.fstat(fd).st_ino==parent_inode)
                result=real_sync(fd)
                if targeted:
                    tagged['fired']=True
                    if fault=='exact-expiry':patch.setattr(admission,'monotonic_ns',lambda:c.budget.deadline_ns)
                    else:raise OSError('E02_ACTUAL_SYNC_FAILURE')
                return result
            def closed(fd):
                result=real_close(fd)
                if fd==tagged['fd'] and fault=='close' and not tagged['fired']:
                    tagged['fired']=True;raise OSError('E02_CLOSE_OUTCOME_UNCERTAIN')
                return result
            patch.setattr(os,'open',opened);patch.setattr(os,'write',written);patch.setattr(os,'fsync',synced);patch.setattr(os,'close',closed)
            with pytest.raises((ValueError,OSError)):adapter._ordinary_write(path,value,c.custody)
        raw=path.read_bytes()
        assert raw==(expected[:3] if fault=='short-zero' else b'' if fault=='zero' else expected)
        with pytest.raises((ValueError,OSError)):adapter._ordinary_write(path,value,c.custody)
        assert path.read_bytes()==raw and tagged['fired']
        record_property('e02_publication',json.dumps(dict(fault=fault,actual_retained_bytes=len(raw),successful_disposition=False,
            partial_or_uncertain_artifact_preserved=True,original_deadline=c.budget.deadline_ns,teardown_not_application_cleanup=True)))
    finally:c.custody._close()


def test_e02_actual_custody_parent_birth_change_denies(tmp_path,monkeypatch,record_property):
    from tests.unit.common import test_legacy_bootstrap as setup
    c=setup._e02_installed_control(tmp_path,monkeypatch)
    original=c.budget.deadline_ns
    try:
        c.custody.check()
        monkeypatch.setattr(admission,'kernel_process_birth',lambda pid:'0'*64)
        with pytest.raises(ValueError):c.custody.check()
        assert c.custody.budget is c.budget and c.budget.deadline_ns==original
        assert not c.custody.released
        record_property('e02_pid_reuse',json.dumps(dict(simulated_birth_change=True,
            actual_custody_and_budget=True,production_process_observation=False)))
    finally:c.custody._close()
