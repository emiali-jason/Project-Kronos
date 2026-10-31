"""Disposable actual macOS exchanges/signatures/locks; synthetic authority only."""
import ast
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
import plistlib
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading

import pytest
from tools.macos import place_release_pair as p
from tools.macos import package_launcher as package
from kronos.common import release_admission as a

ROOT=Path(__file__).resolve().parents[3]
P_SHA='85ea2fa04da20f40377b242d71db96762020e77042a7b4923c331c6f82ab7891'


def assert_actual_preparatory_source():
    """Verify real retained source BEFORE any local fixture rebinding."""
    python_pin=p._assignment((ROOT/'src/kronos/common/release_admission.py').read_bytes(),'PERSISTENT_ANCHOR_BINDING')
    native=(ROOT/'tools/macos/kronos_launcher.c').read_bytes()
    assert type(python_pin) is bytes and sha256(python_pin).hexdigest()==P_SHA
    assert p._c_assignment(native,'approved_persistent_binding')==python_pin
    assert p._c_assignment(native,'approved_initialization_disposition') is None
    assert p._c_assignment(native,'approved_ordinary_restart_policy') is None
    assert p._assignment((ROOT/'src/kronos/common/failed_successor_restore.py').read_bytes(),'INITIALIZATION_DISPOSITION') is None
    assert p._assignment((ROOT/'src/kronos/common/legacy_bootstrap.py').read_bytes(),'ORDINARY_RESTART_POLICY') is None
    return python_pin


def private(path,value,*,final_lf=False):
    raw=p.canonical(value)+(b'\n' if final_lf else b'')
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw);path.chmod(0o600)
    return dict(identity=value.get('identity','document') if isinstance(value,dict) else 'roster',path=str(path),bytes=len(raw),sha256=sha256(raw).hexdigest())


def command(*args,cwd=None):
    result=subprocess.run(list(map(str,args)),cwd=cwd,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    return result.stdout.strip()


def make_backend(root,pin,label,artifacts):
    from tools.runtime_source_gate import SOURCE_BRANCH,SOURCE_ORIGIN,SOURCE_REF
    root.mkdir(parents=True)
    for d in ('tools/macos','src/kronos/common','tools/macos/KRONOS.app/Contents/Resources','tools/macos/KRONOS.app/Contents/MacOS'):(root/d).mkdir(parents=True,exist_ok=True)
    source='''#include <stdio.h>
static const char *approved_persistent_binding = PIN;
static const char *approved_initialization_disposition = NULL;
static const char *approved_ordinary_restart_policy = NULL;
int main(void) {(void)approved_persistent_binding;(void)approved_initialization_disposition;(void)approved_ordinary_restart_policy;puts("KRONOS_LAUNCHER_PACKAGE_V1_OK");return 0;}
'''.replace('PIN','NULL' if pin is None else json.dumps(pin.decode()))+'\n/* '+label+' SYNTHETIC INERT FIXTURE */\n'
    (root/'tools/macos/kronos_launcher.c').write_text(source)
    (root/'src/kronos/common/release_admission.py').write_text('PERSISTENT_ANCHOR_BINDING = '+repr(pin)+'\n')
    (root/'src/kronos/common/failed_successor_restore.py').write_text('INITIALIZATION_DISPOSITION = None\n')
    (root/'src/kronos/common/legacy_bootstrap.py').write_text('ORDINARY_RESTART_POLICY = None\n')
    shutil.copy2(ROOT/'tools/macos/package_launcher.py',root/'tools/macos/package_launcher.py')
    for name in package.RESOURCES:shutil.copy2(ROOT/'tools/macos/KRONOS.app'/name,root/'tools/macos/KRONOS.app'/name)
    info=root/'tools/macos/KRONOS.app/Contents/Info.plist'
    values=plistlib.loads(info.read_bytes());values['CFBundleVersion']='1.0.0' if label=='old' else '2.0.0'
    info.write_bytes(plistlib.dumps(values))
    (root/'tools/macos/KRONOS.app'/package.BINARY).write_bytes(b'SYNTHETIC TRACKED TEMPLATE; NEVER EXECUTED')
    (root/'tools/kronos_browser.py').write_text("raise AssertionError('MUST_NOT_LAUNCH_KRONOS')\n")
    (root/'pyproject.toml').write_text('[project]\nname="placement-fixture"\nversion="0.0.0"\n')
    (root/'.gitignore').write_text('.venv/\n')
    command(sys.executable,'-m','venv','--without-pip',root/'.venv')
    command('/usr/bin/git','init','-b',SOURCE_BRANCH,root)
    command('/usr/bin/git','-C',root,'config','user.name','DISPOSABLE TEST')
    command('/usr/bin/git','-C',root,'config','user.email','disposable@example.invalid')
    command('/usr/bin/git','-C',root,'remote','add','origin',SOURCE_ORIGIN)
    command('/usr/bin/git','-C',root,'config','branch.'+SOURCE_BRANCH+'.remote','origin')
    command('/usr/bin/git','-C',root,'config','branch.'+SOURCE_BRANCH+'.merge',SOURCE_REF)
    command('/usr/bin/git','-C',root,'add','.')
    command('/usr/bin/git','-C',root,'commit','-m','SYNTHETIC '+label)
    result=recorded_build(root,artifacts/label)
    return artifacts/label/'KRONOS.app',result


def recorded_build(root,output):
    commands=[];original_run=package.run
    def observed_run(*args,**kwargs):
        result=original_run(*args,**kwargs)
        commands.append(dict(argv=list(map(str,args)),actual_exit=result.returncode,
            stdout=result.stdout.decode(errors='replace'),stderr=result.stderr.decode(errors='replace')))
        return result
    package.run=observed_run
    try:result=package.build(root,output)
    finally:package.run=original_run
    (output/'actual-build-commands.json').write_text(json.dumps(commands,indent=2)+'\n')
    (output/'executed-launcher-source.c').write_bytes((root/'tools/macos/kronos_launcher.c').read_bytes())
    return result


@pytest.fixture
def case(tmp_path,monkeypatch,record_property,request):
    actual=assert_actual_preparatory_source()
    home=tmp_path/'home';anchor=home/'Library/Application Support/KRONOS/runtime';anchor.mkdir(parents=True,mode=0o700)
    anchor.parent.chmod(0o700)
    repo=home/'Documents/GitHub/Project-Kronos';bundle=home/'Applications/KRONOS.app';bundle.parent.mkdir(parents=True)
    stage=tmp_path/'outside-discovery';stage.mkdir();artifacts=tmp_path/'artifacts';artifacts.mkdir()
    metadata=anchor.stat();core=dict(anchor_path=str(anchor),device=metadata.st_dev,inode=metadata.st_ino,owner=os.getuid(),bundle_id='com.project-kronos.browser-v1',bundle_path=str(bundle),repository_path=str(repo))
    installation=dict(identity=sha256(p.canonical(core)).hexdigest(),**core)
    enrollment=private(tmp_path/'inputs/enrollment.json',installation)
    fd=os.open(anchor,os.O_RDONLY|os.O_DIRECTORY)
    try:observed=a.descriptor_filesystem_identity(fd)
    finally:os.close(fd)
    policy=dict(schema='KRONOS_PERSISTENT_ANCHOR_BINDING_V1',installation_identity=installation['identity'],enrollment=dict(enrollment,path=str(anchor/'e02-frozen-enrollment.json')),anchor_path=str(anchor),**observed,owner=os.getuid(),required_mode='0700',bundle_id=core['bundle_id'],bundle_path=str(bundle),repository_path=str(repo))
    pin=p.canonical(policy)
    monkeypatch.setattr(a,'PERSISTENT_ANCHOR_BINDING',pin);monkeypatch.setattr(a,'APPROVED_BINDING',a.AnchorBinding(anchor,metadata.st_dev,metadata.st_ino,os.getuid()))
    oldapp,oldrecord=make_backend(repo,None,'old',artifacts)
    shutil.copytree(oldapp,bundle)
    newrepo=stage/'new-backend';newapp,newrecord=make_backend(newrepo,pin,'new',artifacts)
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    monkeypatch.setattr(p,'PORT',port)
    # Explicit disposable PID namespace; kernel argument comparison remains real.
    monkeypatch.setattr(p,'_process_ids',lambda:(os.getpid(),))
    owner=p.Placement(a.ValidationBudget(a.monotonic_ns()+120_000_000_000))
    def pair(root,app,record,label):
        executable=(root/'.venv/bin/python').resolve();raw=executable.read_bytes()
        probe=json.loads(command(root/'.venv/bin/python','-I','-S','-B','-c','import sys,json;print(json.dumps(dict(version=sys.version,implementation=sys.implementation.name,base_prefix=sys.base_prefix)))'))
        artifact=private(tmp_path/('inputs/'+label+'-artifact.json'),record,final_lf=True)
        roster=private(tmp_path/('inputs/'+label+'-roster.json'),owner._roster(root))
        value=dict(schema=p.PAIR_SCHEMA,identity=label,repository=str(repo),bundle=str(bundle),roster=roster,
            revision=record['source_revision'],tree=command('/usr/bin/git','-C',root,'rev-parse','HEAD^{tree}'),artifact=artifact,
            interpreter=dict(path=str(executable),bytes=len(raw),sha256=sha256(raw).hexdigest(),**probe))
        return private(tmp_path/('inputs/'+label+'.json'),value)
    old=pair(repo,bundle,oldrecord,'old-pair');new=pair(newrepo,newapp,newrecord,'new-pair')
    now=datetime.now(timezone.utc);authority=private(tmp_path/'inputs/SYNTHETIC-authority.json',dict(identity='authority',label='SYNTHETIC FOUR ROLE TEST AUTHORITY; NOT OPERATIONAL APPROVAL'))
    tool=Path(p.__file__).resolve();raw=tool.read_bytes()
    order=dict(schema=p.SCHEMA,identity='placement-fixture',operation='PLACE',stage='PREPARATORY',installation_identity=installation['identity'],binding_sha256=sha256(pin).hexdigest(),enrollment=enrollment,
        executor=dict(identity='executor',path=str(tool),bytes=len(raw),sha256=sha256(raw).hexdigest()),current=old,selected=new,selected_backend=str(newrepo),selected_bundle=str(newapp),control=None,private_inputs=[],prior=None,
        valid_from=(now-timedelta(seconds=10)).isoformat(),valid_until=(now+timedelta(minutes=4)).isoformat(),decisions={k:authority for k in ('sponsor','ca','pcp','product')})
    order_path=tmp_path/'inputs/order.json'
    evidence=ROOT.parent/'qualification'/'placement-evidence'/os.environ.get('KRONOS_TEST_RUN_ID','isolated')/tmp_path.parents[1].name/tmp_path.name
    evidence.mkdir(parents=True,exist_ok=True)
    isolation=Path(os.environ['KRONOS_TEST_ISOLATION_MANIFEST'])
    shutil.copy2(isolation,evidence/'original-harness-isolation.json')
    shutil.copy2(isolation.parent/'isolation.sb',evidence/'original-harness-policy.sb')
    objects=dict(owner=owner,order=order,order_path=order_path,old=old,new=new,repo=repo,bundle=bundle,newrepo=newrepo,newapp=newapp,anchor=anchor,evidence=evidence,policy=policy)
    record_property('actual_populated_source_P_sha256',sha256(actual).hexdigest())
    record_property('fixture_seams','SYNTHETIC AUTHORITY/PIN PATHS/BACKEND/INERT NATIVE; REAL MAC FD IDENTITY/FLOCK/ACTUAL SIGNED APP INSTALL AND DIRECTORY EXCHANGE; NO PRODUCT CHILD')
    try:yield objects
    finally:
        # Original attempt outcome and actual resources are recorded BEFORE
        # forced defensive test cleanup. No result is upgraded by teardown.
        owner=objects['owner']
        disposition=owner.close()
        # Observe the real current owner, independently of any stale local.
        import fcntl
        current=objects['owner'];probe=os.open(anchor,os.O_RDONLY|os.O_DIRECTORY)
        try:
            try:fcntl.flock(probe,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:blocked=True
            else:blocked=False
        finally:os.close(probe)
        owner_observation=dict(local_is_current=owner is current,current_descriptor=current.descriptor,
            independent_lock_blocked=blocked,reported_resources=disposition,
            current_original_deadline=current.original_deadline)
        (evidence/'current-owner-observation.json').write_text(json.dumps(owner_observation,indent=2)+'\n')
        (evidence/'application-outcome.json').write_text(json.dumps(dict(resources=disposition,events=owner.events,budget_deadline=owner.budget.deadline_ns,original_deadline=owner.original_deadline),indent=2)+'\n')
        # Entire original disposable estate, including staged/current pair and
        # actual compiled/signature artifacts, before harness removal.
        shutil.copytree(tmp_path,evidence/'disposable-before-test-teardown',symlinks=True)
        forced=owner.descriptor is not None
        if forced:os.close(owner.descriptor);owner.descriptor=None
        (evidence/'fixture-teardown.json').write_text(json.dumps(dict(forced_fixture_fd_close=forced,application_cleanup_success_claimed=False,source_records_repaired=False),indent=2)+'\n')
        assert owner is current, 'FIXTURE_CLEANUP_REPORTED_STALE_OWNER'
        if disposition['state']=='CLOSED':assert current.descriptor is None and not blocked


def invoke(c):
    ref=private(c['order_path'],c['order'])
    return c['owner'].execute(ref)


def test_populated_preparatory_source_is_exact_and_disabled():
    assert sha256(assert_actual_preparatory_source()).hexdigest()==P_SHA


def test_actual_placement_and_separately_ordered_rollback(case):
    c=case;deadline=c['owner'].original_deadline
    result=invoke(c);assert result['launched'] is False and result['original_outcome']=='UNPROVED'
    directory=c['anchor'].parent/p.JOURNAL_NAME
    selected=json.loads(Path(c['new']['path']).read_bytes())
    artifact=json.loads(Path(selected['artifact']['path']).read_bytes())
    old_selected=json.loads(Path(c['old']['path']).read_bytes())
    old_artifact=json.loads(Path(old_selected['artifact']['path']).read_bytes())
    assert artifact['bundle_identity']!=old_artifact['bundle_identity']
    assert package.verify(c['bundle'],artifact['bundle_identity'])==artifact['bundle_identity']
    assert not (c['anchor']/'e02-frozen-enrollment.json').exists()
    assert not (c['anchor']/'failed-successor-restore-v1').exists()
    assert not (c['anchor']/'ordinary-start-v1').exists()
    assert c['owner'].budget.deadline_ns==deadline
    placement_disposition=c['owner'].close()
    assert placement_disposition['state']=='CLOSED'
    (c['evidence']/'placement-before-rollback-application.json').write_text(json.dumps(dict(resources=placement_disposition,events=c['owner'].events,original_deadline=c['owner'].original_deadline,budget_deadline=c['owner'].budget.deadline_ns),indent=2)+'\n')
    rollback=p.Placement(a.ValidationBudget(a.monotonic_ns()+120_000_000_000))
    c['owner']=rollback
    prior=directory/'placement.prepared.json'
    reference=dict(identity='placement-fixture',path=str(prior),bytes=prior.stat().st_size,sha256=sha256(prior.read_bytes()).hexdigest())
    c['order']=dict(c['order'],identity='rollback-fixture',operation='ROLLBACK',current=c['new'],selected=c['old'],
        selected_backend=str(directory/'placement.checkpoint.backend'),selected_bundle=str(directory/'placement.checkpoint.app'),prior=reference)
    c['order_path']=c['order_path'].with_name('rollback-order.json')
    assert invoke(c)['original_outcome']=='UNPROVED'
    old=json.loads(Path(c['old']['path']).read_bytes());original=json.loads(Path(old['artifact']['path']).read_bytes())
    assert package.verify(c['bundle'],original['bundle_identity'])==original['bundle_identity']
    assert (directory/'placement.intent.json').is_file() and (directory/'rollback.intent.json').is_file()
    assert not list(c['anchor'].iterdir())


@pytest.mark.parametrize('finding',('binding','source','artifact','interpreter','second-repository','active-journal','existing-transaction','live-control','pin-disagreement','wrong-bundle','dangling-maintenance','dangling-ordinary'))
def test_wrong_pair_or_state_denies_before_swaps(case,finding):
    c=case;before=package.identity(c['bundle']);old_revision=command('/usr/bin/git','-C',c['repo'],'rev-parse','HEAD')
    if finding=='binding':c['order']['binding_sha256']='f'*64
    elif finding=='source':(c['newrepo']/'pyproject.toml').write_text('CHANGED')
    elif finding=='artifact':(c['newapp']/'Contents/Resources/KRONOS.png').write_bytes(b'CHANGED')
    elif finding=='interpreter':
        x=json.loads(Path(c['new']['path']).read_bytes());x['interpreter']['sha256']='f'*64
        c['order']['selected']=private(Path(c['new']['path']),x)
    elif finding=='second-repository':shutil.copytree(c['repo'],c['repo'].with_name('SECOND'),symlinks=True)
    elif finding=='active-journal':(c['anchor']/'failed-successor-restore-v1').mkdir()
    elif finding=='existing-transaction':(c['anchor'].parent/p.JOURNAL_NAME).mkdir()
    elif finding=='live-control':
        control=c['anchor']/'browser-backend-v1.control';raw=('KRONOS_BROWSER_BACKEND_CONTROL_V1\n'+str(os.getpid())+'\n'+'c'*64+'\n').encode();control.write_bytes(raw);control.chmod(0o600)
        c['order']['control']=dict(identity='selected-control',path=str(control),bytes=len(raw),sha256=sha256(raw).hexdigest())
    elif finding in ('dangling-maintenance','dangling-ordinary'):
        name='maintenance' if finding=='dangling-maintenance' else 'ordinary-start-v1'
        (c['anchor']/name).symlink_to(c['anchor'].parent/'SYNTHETIC-MISSING-STATE-DIRECTORY',target_is_directory=True)
    elif finding=='wrong-bundle':
        other=c['newrepo'].parent/'wrong-bundle.app';shutil.copytree(c['bundle'],other)
        c['order']['selected_bundle']=str(other)
    elif finding=='pin-disagreement':
        # Coherently refresh roster/commit to ensure the real pin comparison,
        # rather than a stale manifest, denies. Artifact source identity follows.
        f=c['newrepo']/'src/kronos/common/release_admission.py';f.write_text('PERSISTENT_ANCHOR_BINDING = None\n')
        command('/usr/bin/git','-C',c['newrepo'],'add','.');command('/usr/bin/git','-C',c['newrepo'],'commit','-m','coherent pin disagreement')
        value=json.loads(Path(c['new']['path']).read_bytes());value['revision']=command('/usr/bin/git','-C',c['newrepo'],'rev-parse','HEAD');value['tree']=command('/usr/bin/git','-C',c['newrepo'],'rev-parse','HEAD^{tree}')
        value['roster']=private(Path(value['roster']['path']),c['owner']._roster(c['newrepo']))
        artifact=json.loads(Path(value['artifact']['path']).read_bytes());artifact['source_revision']=value['revision'];value['artifact']=private(Path(value['artifact']['path']),artifact,final_lf=True)
        c['order']['selected']=private(Path(c['new']['path']),value)
    with pytest.raises((ValueError,OSError,subprocess.CalledProcessError)):invoke(c)
    assert package.identity(c['bundle'])==before
    assert command('/usr/bin/git','-C',c['repo'],'rev-parse','HEAD')==old_revision


@pytest.mark.parametrize('boundary',('after-backend-swap','before-app-swap','after-app-swap','prepared-zero-write','prepared-prefix-write','prepared-exact-expiry','late-fsync'))
def test_actual_partial_effects_preserve_intent_and_deny_replay(case,monkeypatch,boundary):
    c=case;real_exchange=package.exchange;real_install=package.install;real_write=c['owner']._write;real_sync=c['owner']._sync_dir
    def exchange(left,right):
        real_exchange(left,right)
        if boundary=='after-backend-swap':raise KeyboardInterrupt('ACTUAL BACKEND SWAPPED; INTERRUPTED')
    def install(*args,**kwargs):
        if boundary=='before-app-swap':raise KeyboardInterrupt('APP NOT ENTERED')
        result=real_install(*args,**kwargs)
        if boundary=='after-app-swap':raise KeyboardInterrupt('ACTUAL APP INSTALLED; ACK LOST')
        return result
    monkeypatch.setattr(package,'exchange',exchange);monkeypatch.setattr(package,'install',install)
    def write(target,raw,**options):
        if target.name=='placement.prepared.json' and boundary in {'prepared-zero-write','prepared-prefix-write'}:
            actual_write=os.write;fired=[False]
            def short(fd,data):
                if boundary=='prepared-prefix-write' and not fired[0]:fired[0]=True;return actual_write(fd,data[:7])
                return 0
            with monkeypatch.context() as patch:
                patch.setattr(os,'write',short)
                return real_write(target,raw,**options)
        result=real_write(target,raw,**options)
        if target.name=='placement.prepared.json' and boundary=='prepared-exact-expiry':
            monkeypatch.setattr(a,'monotonic_ns',lambda:c['owner'].original_deadline)
        return result
    monkeypatch.setattr(c['owner'],'_write',write)
    def sync(target):
        result=real_sync(target)
        if boundary=='late-fsync' and target==c['repo'].parent:monkeypatch.setattr(a,'monotonic_ns',lambda:c['owner'].original_deadline)
        return result
    monkeypatch.setattr(c['owner'],'_sync_dir',sync)
    with pytest.raises((ValueError,OSError,KeyboardInterrupt)):invoke(c)
    directory=c['anchor'].parent/p.JOURNAL_NAME
    assert (directory/'placement.intent.json').is_file()
    assert (directory/'placement.checkpoint.backend').is_dir() and (directory/'placement.checkpoint.app').is_dir()
    assert not (c['anchor']/'failed-successor-restore-v1').exists()
    assert not (c['anchor']/'ordinary-start-v1').exists()
    # Separate fresh invocation cannot adopt/repair the original partial result.
    other=p.Placement(a.ValidationBudget(a.monotonic_ns()+120_000_000_000))
    try:
        with pytest.raises((ValueError,OSError)):other.execute(private(c['order_path'],c['order']))
    finally:other.close()


def test_actual_concurrent_exclusion(case):
    c=case;ref=private(c['order_path'],c['order']);c['owner']._acquire(c['order']['enrollment'])
    other=p.Placement(a.ValidationBudget(a.monotonic_ns()+120_000_000_000))
    try:
        with pytest.raises(BlockingIOError):other.execute(ref)
        assert not (c['anchor'].parent/p.JOURNAL_NAME).exists()
    finally:assert other.close()['state']=='CLOSED'


def test_entered_durable_work_cannot_be_closed_as_complete(case,monkeypatch):
    c=case;entered=threading.Event();release=threading.Event();real=c['owner']._sync_dir;errors=[]
    def blocked(target):
        if target==c['anchor'].parent:
            with c['owner'].io():entered.set();assert release.wait(10)
        return real(target)
    monkeypatch.setattr(c['owner'],'_sync_dir',blocked)
    def worker():
        try:invoke(c)
        except BaseException as error:errors.append(error)
    thread=threading.Thread(target=worker);thread.start()
    try:
        assert entered.wait(10)
        disposition=c['owner'].close();assert disposition['state']=='UNRESOLVED' and disposition['custody_retained'] and disposition['active_io']==1
    finally:release.set();thread.join(30);assert not thread.is_alive()
    assert c['owner'].close()['state']=='UNRESOLVED'


def test_actual_owned_live_entry_arguments_deny(case,monkeypatch):
    c=case
    child=subprocess.Popen([sys.executable,'-B','-c','import time;time.sleep(10)',str(c['newrepo']/'tools/kronos_browser.py')])
    try:
        monkeypatch.setattr(p,'_process_ids',lambda:(os.getpid(),child.pid))
        with pytest.raises(p.PlacementError,match='LIVE_PROCESS'):invoke(c)
        assert not (c['anchor'].parent/p.JOURNAL_NAME).exists()
    finally:child.terminate();child.wait(timeout=5)


def test_fresh_imported_preparatory_pin_before_rebinding(record_property):
    code="import sys,json,hashlib;sys.path[:0]="+repr([str(ROOT/'src'),str(ROOT)])+";from kronos.common import release_admission as a,failed_successor_restore as r,legacy_bootstrap as b;print(json.dumps(dict(pin=hashlib.sha256(a.PERSISTENT_ANCHOR_BINDING).hexdigest(),genesis=r.INITIALIZATION_DISPOSITION,ordinary=b.ORDINARY_RESTART_POLICY)))"
    observed=json.loads(command(sys.executable,'-I','-S','-B','-c',code))
    assert observed==dict(pin=P_SHA,genesis=None,ordinary=None)
    record_property('actual_fresh_import_values',json.dumps(observed,sort_keys=True))


@pytest.mark.parametrize('boundary',('file-fsync','file-close'))
def test_actual_durability_error_preserves_bytes_and_uncertainty(case,monkeypatch,boundary):
    c=case;real_write=c['owner']._write
    def write(target,raw,**options):
        if target.name!='placement.checkpointed.json':return real_write(target,raw,**options)
        real_fsync=os.fsync;real_close=os.close;fired=[False]
        def selected(fd):
            return target.exists() and os.fstat(fd).st_ino==target.lstat().st_ino
        def sync(fd):
            result=real_fsync(fd)
            if selected(fd) and not fired[0]:fired[0]=True;raise OSError(5,'CONTROLLED FSYNC RESULT UNCERTAINTY AFTER ACTUAL CALL')
            return result
        def close(fd):
            hit=selected(fd) and not fired[0]
            result=real_close(fd)
            if hit:fired[0]=True;raise OSError(5,'CONTROLLED CLOSE RESULT UNCERTAINTY AFTER ACTUAL CALL')
            return result
        with monkeypatch.context() as patch:
            patch.setattr(os,'fsync' if boundary=='file-fsync' else 'close',sync if boundary=='file-fsync' else close)
            return real_write(target,raw,**options)
    monkeypatch.setattr(c['owner'],'_write',write)
    before=package.identity(c['bundle'])
    with pytest.raises(OSError,match='UNCERTAINTY'):invoke(c)
    assert package.identity(c['bundle'])==before
    assert (c['anchor'].parent/p.JOURNAL_NAME/'placement.checkpointed.json').read_bytes()
    assert c['owner'].close()['state']=='UNRESOLVED'


def test_selected_stale_control_spent_inputs_and_product_bytes_are_preserved(case):
    c=case;control=c['anchor']/'browser-backend-v1.control'
    raw=b'KRONOS_BROWSER_BACKEND_CONTROL_V1\n2147483647\n'+b'c'*64+b'\n'
    control.write_bytes(raw);control.chmod(0o600)
    c['order']['control']=dict(identity='SYNTHETIC-selected-stale-control',path=str(control),bytes=len(raw),sha256=sha256(raw).hexdigest())
    handoff=c['anchor']/'maintenance'/('a'*64+'.json');handoff.parent.mkdir(mode=0o700)
    consumed=handoff.with_name(handoff.stem+'.consumed.json')
    for target in (handoff,consumed):target.write_bytes(b'{"synthetic_fixture":"permanently spent; never reused"}');target.chmod(0o600)
    record=c['anchor'].parent/'evidence/swing-v1/SYNTHETIC-committed.json';record.parent.mkdir(parents=True);record.write_bytes(b'{"outcome":"COMMITTED","delivery":"UNCERTAIN"}')
    preserved={str(f):f.read_bytes() for f in (control,handoff,consumed,record)}
    assert invoke(c)['launched'] is False
    assert all(Path(name).read_bytes()==data for name,data in preserved.items())
    assert not (c['anchor']/'e02-frozen-enrollment.json').exists()
    assert not (c['anchor']/'failed-successor-restore-v1').exists()


def test_short_writes_and_eintr_complete_exact_evidence(case,monkeypatch):
    c=case;actual=os.write;calls=[0]
    def short(fd,data):
        calls[0]+=1
        if calls[0]%7==1:raise InterruptedError()
        return actual(fd,data[:max(1,min(17,len(data)))])
    monkeypatch.setattr(os,'write',short)
    assert invoke(c)['original_outcome']=='UNPROVED'
    assert calls[0]>100
    assert json.loads((c['anchor'].parent/p.JOURNAL_NAME/'placement.prepared.json').read_bytes())['launched'] is False


@pytest.mark.parametrize('stage',('PREPARATORY','FINAL_UNACTIVATED'))
def test_actual_unresolved_helper_retains_exclusion_and_spent_intent(case,monkeypatch,stage):
    import signal,select
    c=case
    if stage=='FINAL_UNACTIVATED':_two_stage_control(c,monkeypatch)
    ref=private(c['order_path'],c['order']);read,write=os.pipe();child=os.fork()
    if child==0:
        os.close(read)
        owner=p.Placement(a.ValidationBudget(a.monotonic_ns()+2_000_000_000));real=owner.helper
        def controlled(arguments,cwd,phase,capacity=262144):
            if phase=='PLACEMENT_SIGNATURE':
                arguments=[sys.executable,'-B','-c','import time;time.sleep(5)']
            return real(arguments,cwd,phase,capacity)
        owner.helper=controlled
        try:owner.execute(ref);os._exit(96)
        except BaseException as error:
            disposition=owner.close()
            raw=json.dumps(dict(exception=type(error).__name__,unresolved=a.validation_unresolved(),resources=disposition,actual_owned_helper_pids=list(a._OWNED_VALIDATION_HELPERS),events=owner.events)).encode()
            os.write(write,raw);os.close(write)
            teardown=[]
            for helper in tuple(a._OWNED_VALIDATION_HELPERS.values()):
                teardown.append(dict(pid=helper.pid,actual_exit=helper.wait(timeout=3)))
            (c['evidence']/'owned-helper-test-teardown.json').write_text(json.dumps(dict(helpers=teardown,original_unresolved_outcome_unchanged=True,application_cleanup_claimed=False)))
            a.retain_failure_custody(owner,[a])
    os.close(write);status=None
    try:
        assert select.select([read],[],[],12)[0]
        chunks=[]
        while True:
            chunk=os.read(read,262144)
            if not chunk:break
            chunks.append(chunk)
        raw=b''.join(chunks);observed=json.loads(raw)
        assert observed['unresolved'] and observed['resources']['state']=='UNRESOLVED' and observed['resources']['custody_retained']
        fd=os.open(c['anchor'],os.O_RDONLY|os.O_DIRECTORY)
        try:
            import fcntl
            with pytest.raises(BlockingIOError):fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        finally:os.close(fd)
        assert (c['anchor'].parent/p.JOURNAL_NAME/(p.FINAL_STAGE if stage=='FINAL_UNACTIVATED' else '.')/'placement.intent.json').is_file()
        (c['evidence']/'unresolved-helper-application.json').write_bytes(raw)
        import time
        end=time.monotonic()+5
        while not (c['evidence']/'owned-helper-test-teardown.json').exists() and time.monotonic()<end:time.sleep(.01)
        assert (c['evidence']/'owned-helper-test-teardown.json').exists()
    finally:
        os.close(read)
        os.kill(child,signal.SIGKILL);_,status=os.waitpid(child,0)
        (c['evidence']/'unresolved-helper-forced-test-teardown.json').write_text(json.dumps(dict(actual_owner_exit=os.waitstatus_to_exitcode(status),forced_fixture_termination=True,application_cleanup_claimed=False)))
    directory=c['anchor'].parent/p.JOURNAL_NAME/(p.FINAL_STAGE if stage=='FINAL_UNACTIVATED' else '.')
    before={str(f.relative_to(directory)):f.read_bytes() for f in directory.rglob('*') if f.is_file()}
    with pytest.raises(p.PlacementError,match='PRIOR_OR_REPLAY'):invoke(c)
    assert before=={str(f.relative_to(directory)):f.read_bytes() for f in directory.rglob('*') if f.is_file()}


def test_admitted_genesis_final_pair_remains_unactivated(case,monkeypatch):
    c=case;control=_two_stage_control(c,monkeypatch)
    journal=control['journal'];original=control['genesis_bytes']
    assert invoke(c)['launched'] is False
    assert original=={f.name:f.read_bytes() for f in journal.iterdir() if f.is_file()}
    assert not (c['anchor']/'ordinary-start-v1').exists()
    assert _placement_history(control['history'])==control['history_before']


def test_manifest_git_correspondence_uses_one_observation_before_swaps(case,monkeypatch):
    c=case;file=c['newrepo']/'pyproject.toml';git_bytes=file.read_bytes()
    working=git_bytes+b'\n# SYNTHETIC coherent working/manifest mutation, unchanged selected Git tree\n'
    tree=command('/usr/bin/git','-C',c['newrepo'],'rev-parse','HEAD^{tree}')
    file.write_bytes(working)
    command('/usr/bin/git','-C',c['newrepo'],'update-index','--assume-unchanged','pyproject.toml')
    assert command('/usr/bin/git','-C',c['newrepo'],'status','--porcelain')==''
    value=json.loads(Path(c['new']['path']).read_bytes())
    value['roster']=private(Path(value['roster']['path']),c['owner']._roster(c['newrepo']))
    c['order']['selected']=private(Path(c['new']['path']),value)
    before=c['owner']._roster(c['repo']);app_before=package.identity(c['bundle'])
    original=p._read_regular;observations=[]
    def interleave(target,**options):
        if Path(target)==file:
            ordinal=len(observations)+1
            if ordinal==2:file.write_bytes(git_bytes)
            try:result=original(target,**options)
            finally:
                if ordinal==2:file.write_bytes(working)
            observations.append(dict(ordinal=ordinal,actual_bytes_sha256=sha256(result[0]).hexdigest(),actual_bytes=len(result[0])))
            return result
        return original(target,**options)
    monkeypatch.setattr(p,'_read_regular',interleave)
    try:
        with pytest.raises(ValueError):invoke(c)
        assert c['owner']._roster(c['repo'])==before,'Git/content disagreement must deny BEFORE backend placement'
        assert package.identity(c['bundle'])==app_before,'Git/content disagreement must deny BEFORE app placement'
        assert len(observations)>=2
    finally:
        (c['evidence']/'same-read-reproduction.json').write_text(json.dumps(dict(
            selected_git_tree=tree,tree_after=command('/usr/bin/git','-C',c['newrepo'],'rev-parse','HEAD^{tree}'),
            index_flag='ASSUME_UNCHANGED; DISPOSABLE REPOSITORY ONLY',tracked_file='pyproject.toml',
            git_bytes_sha256=sha256(git_bytes).hexdigest(),selected_working_manifest_sha256=sha256(working).hexdigest(),
            actual_observations=observations,comparison_seam='REAL SAFE READS AND REAL GIT COMPARISON; controlled mutation only between distinct observations'),indent=2)+'\n')


def test_coherent_roster_cannot_substitute_unmeasured_external_dependency(case):
    c=case;outside=c['newrepo'].parent/'outside-dependency.py';outside.write_text('SYNTHETIC_UNMEASURED_DEPENDENCY=True\n')
    link=c['newrepo']/'.venv/lib/unmeasured.py';link.parent.mkdir(exist_ok=True);link.symlink_to(outside)
    value=json.loads(Path(c['new']['path']).read_bytes());value['roster']=private(Path(value['roster']['path']),c['owner']._roster(c['newrepo']))
    c['order']['selected']=private(Path(c['new']['path']),value)
    before=c['owner']._roster(c['repo']);app_before=package.identity(c['bundle'])
    with pytest.raises(p.PlacementError,match='EXTERNAL_DEPENDENCY_ALIAS'):invoke(c)
    assert c['owner']._roster(c['repo'])==before and package.identity(c['bundle'])==app_before



def _placement_history(directory):
    """Exact prior files/types/modes; adding a final child is not old history."""
    import stat
    rows={}
    for item in sorted(directory.rglob('*')):
        rel=item.relative_to(directory)
        if rel.parts[0]=='final-unactivated':continue
        info=item.lstat();row=dict(mode=stat.S_IMODE(info.st_mode))
        if item.is_symlink():row.update(type='symlink',target=os.readlink(item))
        elif item.is_dir():row.update(type='directory')
        else:row.update(type='file',sha256=sha256(item.read_bytes()).hexdigest())
        rows[str(rel)]=row
    return rows


def _two_stage_control(c,monkeypatch,*,partial=False):
    """Same real disposable anchor; synthetic separately admitted genesis."""
    from kronos.common import failed_successor_restore as restoration,legacy_bootstrap as bootstrap
    from tests.unit.common import test_failed_successor_restore as fixture
    if partial:
        real=c['owner']._write
        def interrupted(target,raw,**kwargs):
            if target.name!='placement.prepared.json':return real(target,raw,**kwargs)
            write=os.write;calls=[0]
            def prefix(fd,data):
                calls[0]+=1
                return write(fd,data[:7]) if calls[0]==1 else 0
            with monkeypatch.context() as patch:
                patch.setattr(os,'write',prefix);return real(target,raw,**kwargs)
        with monkeypatch.context() as patch:
            patch.setattr(c['owner'],'_write',interrupted)
            with pytest.raises(p.PlacementError,match='ZERO_WRITE'):invoke(c)
    else:
        result=invoke(c);assert result['original_outcome']=='UNPROVED' and not result['launched']
    history=c['anchor'].parent/p.JOURNAL_NAME
    preparation=history/'placement.prepared.json'
    prepared_ref=dict(identity=c['order']['identity'],path=str(preparation),bytes=preparation.stat().st_size,sha256=sha256(preparation.read_bytes()).hexdigest())
    before=_placement_history(history)
    original_owner=c['owner'];resources=original_owner.close();assert resources['state']==('UNRESOLVED' if partial else 'CLOSED')
    (c['evidence']/'preparatory-application.json').write_text(json.dumps(dict(resources=resources,events=original_owner.events,original_deadline=original_owner.original_deadline),indent=2)+'\n')
    if partial:
        assert original_owner.descriptor is not None
        os.close(original_owner.descriptor);original_owner.descriptor=None
        (c['evidence']/'partial-preparation-fixture-teardown.json').write_text(json.dumps(dict(forced_test_custody_release=True,application_cleanup_success=False,original_outcome='UNRESOLVED')))
    c['owner']=p.Placement(a.ValidationBudget(a.monotonic_ns()+120_000_000_000))
    assert c['owner'].budget is not original_owner.budget
    installation=json.loads(Path(c['order']['enrollment']['path']).read_bytes())
    private(c['anchor']/'e02-frozen-enrollment.json',installation)
    journal=c['anchor']/'failed-successor-restore-v1';journal.mkdir(mode=0o700)
    private(journal/'admission-head.json',dict(schema=restoration.HEAD_SCHEMA,installation_identity=installation['identity'],sequence=1,state='NATIVE_ACTIVATED',active_reservation_id='synthetic-placeholder',active_reservation_sha256='0'*64,incident_id=None,previous_head_sha256='0'*64,recorded_at=datetime.now(timezone.utc).isoformat()))
    monkeypatch.setattr(restoration,'INITIALIZATION_DISPOSITION',None)
    genesis=fixture._s304_admit_fixture(journal,installation)
    policy=p.canonical(dict(schema='ORDINARY_SAME_RELEASE_V1',scope='ORDINARY_SAME_RELEASE_WITH_QUALIFIED_STOP',installation_identity=installation['identity'],binding_sha256=c['order']['binding_sha256'],genesis_disposition_sha256=sha256(genesis).hexdigest(),release_id='SYNTHETIC-FINAL-FIXTURE',installed_selection_path=str(c['anchor']/'ordinary-start-v1/installed-selection.json')))
    monkeypatch.setattr(bootstrap,'ORDINARY_RESTART_POLICY',policy)
    finalrepo=c['newrepo'].parent/'final-backend';shutil.copytree(c['repo'],finalrepo,symlinks=True)
    source=finalrepo/'tools/macos/kronos_launcher.c'
    source.write_text(source.read_text().replace('approved_initialization_disposition = NULL;','approved_initialization_disposition = '+json.dumps(genesis.decode())+';').replace('approved_ordinary_restart_policy = NULL;','approved_ordinary_restart_policy = '+json.dumps(policy.decode())+';'))
    (finalrepo/'src/kronos/common/failed_successor_restore.py').write_text('INITIALIZATION_DISPOSITION = '+repr(genesis)+'\n')
    (finalrepo/'src/kronos/common/legacy_bootstrap.py').write_text('ORDINARY_RESTART_POLICY = '+repr(policy)+'\n')
    info=finalrepo/'tools/macos/KRONOS.app/Contents/Info.plist';values=plistlib.loads(info.read_bytes());values['CFBundleVersion']='3.0.0';info.write_bytes(plistlib.dumps(values))
    command('/usr/bin/git','-C',finalrepo,'add','.');command('/usr/bin/git','-C',finalrepo,'commit','-m','SYNTHETIC separately admitted final pair')
    output=c['newapp'].parents[1]/'two-stage-final';record=recorded_build(finalrepo,output)
    value=json.loads(Path(c['new']['path']).read_bytes());value.update(identity='final-pair',revision=record['source_revision'],tree=command('/usr/bin/git','-C',finalrepo,'rev-parse','HEAD^{tree}'))
    value['artifact']=private(output/'artifact.json',record,final_lf=True);value['roster']=private(output/'roster.json',c['owner']._roster(finalrepo))
    finalpair=private(output/'pair.json',value)
    old_order=c['order'];c['order']=dict(old_order,identity='final-placement-fixture',stage='FINAL_UNACTIVATED',current=c['new'],selected=finalpair,selected_backend=str(finalrepo),selected_bundle=str(output/'KRONOS.app'),prior=prepared_ref)
    c['order_path']=c['order_path'].with_name('final-order.json')
    genesis_bytes={f.name:f.read_bytes() for f in journal.iterdir() if f.is_file()}
    return dict(history=history,prior=prepared_ref,history_before=before,genesis=genesis,genesis_bytes=genesis_bytes,journal=journal,preparatory_order=old_order,original_owner=original_owner,final_pair=finalpair)


def test_two_stage_same_anchor_preserves_preparation(case,monkeypatch):
    c=case;control=_two_stage_control(c,monkeypatch);outcome={}
    real=c['owner']._admission_state
    def observed(*args):
        result=real(*args);outcome['actual_admission_reader_returned']=True;return result
    monkeypatch.setattr(c['owner'],'_admission_state',observed)
    try:
        result=invoke(c)
        assert result['original_outcome']=='UNPROVED' and result['launched'] is False
        final=control['history']/'final-unactivated'
        assert (final/'placement.intent.json').is_file() and (final/'placement.prepared.json').is_file()
        assert c['owner'].budget is not control['original_owner'].budget
        assert _placement_history(control['history'])==control['history_before']
        assert control['genesis_bytes']=={f.name:f.read_bytes() for f in control['journal'].iterdir() if f.is_file()}
        assert not (c['anchor']/'ordinary-start-v1').exists()
        disposition=c['owner'].close();assert disposition['state']=='CLOSED'
        (c['evidence']/'final-application-before-repeat.json').write_text(json.dumps(dict(resources=disposition,events=c['owner'].events,original_deadline=c['owner'].original_deadline),indent=2)+'\n')
        repeated=p.Placement(a.ValidationBudget(a.monotonic_ns()+120_000_000_000))
        try:
            with pytest.raises(p.PlacementError,match='PRIOR_OR_REPLAY'):repeated.execute(private(c['order_path'],c['order']))
        finally:assert repeated.close()['state']=='CLOSED'
        outcome['accepted']=True
    except BaseException as error:
        outcome.update(accepted=False,exception=type(error).__name__,message=str(error));raise
    finally:
        outcome.update(prior_history_unchanged=_placement_history(control['history'])==control['history_before'],final_original_deadline=c['owner'].original_deadline,preparatory_original_deadline=control['original_owner'].original_deadline,fixture_authority='SYNTHETIC independent genesis; actual admission reader, actual SDK and locks; no native initialization or startup claim')
        (c['evidence']/'two-stage-observation.json').write_text(json.dumps(outcome,indent=2)+'\n')



@pytest.mark.parametrize('fault',('missing-prior','wrong-prior','wrong-pair','same-order','missing-authority','partial-preparation','genesis-change'))
def test_final_stage_denies_incomplete_or_mismatched_lineage(case,monkeypatch,fault):
    c=case;control=_two_stage_control(c,monkeypatch,partial=fault=='partial-preparation')
    before=c['owner']._roster(c['repo']);bundle=package.identity(c['bundle'])
    if fault=='missing-prior':c['order']['prior']=None
    elif fault=='wrong-prior':c['order']['prior']=dict(control['prior'],sha256='f'*64)
    elif fault=='wrong-pair':c['order']['current']=c['old']
    elif fault=='same-order':c['order']['identity']=control['preparatory_order']['identity']
    elif fault=='missing-authority':c['order']['decisions']={k:v for k,v in c['order']['decisions'].items() if k!='ca'}
    elif fault=='genesis-change':
        from kronos.common import failed_successor_restore as restoration
        from tests.unit.common import test_failed_successor_restore as fixture
        alternative=fixture._s304_resolve_retained_fixture(control['journal'],json.loads(Path(c['order']['enrollment']['path']).read_bytes()))
        real=c['owner']._admission_state;calls=[0]
        def changed(*args):
            value=real(*args);calls[0]+=1
            if calls[0]==1:monkeypatch.setattr(restoration,'INITIALIZATION_DISPOSITION',alternative)
            return value
        monkeypatch.setattr(c['owner'],'_admission_state',changed)
    with pytest.raises((ValueError,OSError)):invoke(c)
    assert c['owner']._roster(c['repo'])==before and package.identity(c['bundle'])==bundle
    assert not (control['history']/p.FINAL_STAGE).exists()
    assert _placement_history(control['history'])==control['history_before']


@pytest.mark.parametrize('boundary',('reservation-prefix','after-backend','after-app','prepared-exact-expiry'))
def test_final_stage_failure_stays_reserved_without_rewriting_preparation(case,monkeypatch,boundary):
    c=case;control=_two_stage_control(c,monkeypatch);real_write=c['owner']._write;real_exchange=package.exchange;real_install=package.install
    final=control['history']/p.FINAL_STAGE;original_deadline=c['owner'].original_deadline
    def write(target,raw,**kwargs):
        if target==final/'placement.intent.json' and boundary=='reservation-prefix':
            actual=os.write;calls=[0]
            def prefix(fd,data):
                calls[0]+=1;return actual(fd,data[:7]) if calls[0]==1 else 0
            with monkeypatch.context() as patch:
                patch.setattr(os,'write',prefix);return real_write(target,raw,**kwargs)
        value=real_write(target,raw,**kwargs)
        if target==final/'placement.prepared.json' and boundary=='prepared-exact-expiry':monkeypatch.setattr(a,'monotonic_ns',lambda:original_deadline)
        return value
    def exchange(left,right):
        value=real_exchange(left,right)
        if left==final/'placement.staged.backend' and boundary=='after-backend':raise KeyboardInterrupt('Actual final backend exchanged; acknowledgement lost')
        return value
    def install(*args,**kwargs):
        value=real_install(*args,**kwargs)
        if boundary=='after-app':raise KeyboardInterrupt('Actual final app installed; acknowledgement lost')
        return value
    monkeypatch.setattr(c['owner'],'_write',write);monkeypatch.setattr(package,'exchange',exchange);monkeypatch.setattr(package,'install',install)
    with pytest.raises((ValueError,OSError,KeyboardInterrupt)):invoke(c)
    assert final.is_dir() and (final/'placement.intent.json').is_file()
    assert c['owner'].original_deadline==original_deadline and c['owner'].budget.deadline_ns==original_deadline
    assert _placement_history(control['history'])==control['history_before']
    outcome=c['owner'].close();assert outcome['state']=='UNRESOLVED'
    (c['evidence']/'original-final-failure.json').write_text(json.dumps(dict(resources=outcome,events=c['owner'].events,deadline=original_deadline),indent=2)+'\n')
    # Separate TEST teardown of held FD is not successful application cleanup.
    assert c['owner'].descriptor is not None
    os.close(c['owner'].descriptor);c['owner'].descriptor=None
    (c['evidence']/'failure-fixture-release.json').write_text(json.dumps(dict(forced_test_close=True,original_application_state='UNRESOLVED')))
    other=p.Placement(a.ValidationBudget(a.monotonic_ns()+120_000_000_000))
    try:
        with pytest.raises(p.PlacementError,match='PRIOR_OR_REPLAY'):other.execute(private(c['order_path'],c['order']))
    finally:assert other.close()['state']=='CLOSED'
    assert _placement_history(control['history'])==control['history_before']
    if boundary=='prepared-exact-expiry':assert json.loads((final/'placement.prepared.json').read_bytes())['original_outcome']=='UNPROVED'
    assert not (c['anchor']/'ordinary-start-v1').exists()


@pytest.mark.parametrize('fault',('valid','wrong-stage','wrong-pair','changed-genesis'))
def test_final_rollback_is_bound_to_its_placement(case,monkeypatch,fault):
    c=case;control=_two_stage_control(c,monkeypatch)
    result=invoke(c);assert result['original_outcome']=='UNPROVED'
    final=control['history']/p.FINAL_STAGE
    intent=json.loads((final/'placement.intent.json').read_bytes())
    assert intent['prior_preparation']==control['prior']
    assert intent['admitted_genesis']['disposition_sha256']==sha256(control['genesis']).hexdigest()
    resources=c['owner'].close();assert resources['state']=='CLOSED'
    (c['evidence']/'final-placement-application.json').write_text(json.dumps(dict(resources=resources,events=c['owner'].events,original_deadline=c['owner'].original_deadline),indent=2)+'\n')
    current=p._read_regular(final/'placement.prepared.json',limit=p.MAX_DOCUMENT,check=lambda:None,private=True)[0]
    prior=dict(identity=result['identity'],path=str(final/'placement.prepared.json'),bytes=len(current),sha256=sha256(current).hexdigest())
    c['owner']=p.Placement(a.ValidationBudget(a.monotonic_ns()+120_000_000_000))
    c['order']=dict(c['order'],identity='final-rollback-fixture',operation='ROLLBACK',current=control['final_pair'],selected=c['new'],selected_backend=str(final/'placement.checkpoint.backend'),selected_bundle=str(final/'placement.checkpoint.app'),prior=prior)
    c['order_path']=c['order_path'].with_name('final-rollback-order.json')
    if fault=='wrong-stage':c['order']['prior']=control['prior']
    elif fault=='wrong-pair':c['order']['selected']=c['old']
    elif fault=='changed-genesis':
        from kronos.common import failed_successor_restore as restoration
        from tests.unit.common import test_failed_successor_restore as fixture
        monkeypatch.setattr(restoration,'INITIALIZATION_DISPOSITION',fixture._s304_resolve_retained_fixture(control['journal'],json.loads(Path(c['order']['enrollment']['path']).read_bytes())))
    before=c['owner']._roster(c['repo']);bundle=package.identity(c['bundle'])
    if fault=='valid':
        assert invoke(c)['original_outcome']=='UNPROVED'
        restored=json.loads(Path(c['new']['path']).read_bytes());artifact=json.loads(Path(restored['artifact']['path']).read_bytes())
        assert package.verify(c['bundle'],artifact['bundle_identity'])==artifact['bundle_identity']
        assert c['owner']._roster(c['repo'])==json.loads(Path(restored['roster']['path']).read_bytes())
        assert (final/'rollback.intent.json').is_file()
        assert _placement_history(control['history'])==control['history_before']
    else:
        with pytest.raises((ValueError,OSError)):invoke(c)
        assert c['owner']._roster(c['repo'])==before and package.identity(c['bundle'])==bundle
        assert not (final/'rollback.intent.json').exists()
    assert not (c['anchor']/'ordinary-start-v1').exists()


def test_each_placement_stage_is_once_only(case,monkeypatch):
    c=case;result=invoke(c);assert not result['launched']
    history=c['anchor'].parent/p.JOURNAL_NAME;before=_placement_history(history)
    assert c['owner'].close()['state']=='CLOSED'
    other=p.Placement(a.ValidationBudget(a.monotonic_ns()+120_000_000_000))
    try:
        with pytest.raises(p.PlacementError,match='PRIOR_OR_REPLAY'):other.execute(private(c['order_path'],c['order']))
    finally:assert other.close()['state']=='CLOSED'
    assert _placement_history(history)==before


# 83564: only explicit, source-bound observed legacy identities qualify.
LEGACY_APPROVED=('ef962c39773be0e94a2e8b8b921b94993a66d071',
 'fc02b6ef538b8b8a2720d34cbbdc9cb18a5706597f46ac4a635f6bd0b53d73b7',
 'ed7a77729ff22aea43134b5dfc9dc2cb32e05204c4e66cd9188d8cf78b434a69')


def _legacy_control(c,monkeypatch):
    """Synthetic fixed identity seam; actual Git bytes/modes/seal/custody paths.

    This is not a historical package attestation. Old source and app are observed
    separately, as in the approved legacy boundary. No product child is allowed.
    """
    if hasattr(p,'LEGACY_IDENTITY'):assert p.LEGACY_IDENTITY==LEGACY_APPROVED
    repo=c['repo']
    for name in ('release_admission.py','failed_successor_restore.py'):(repo/'src/kronos/common'/name).unlink()
    (repo/'src/kronos/common/legacy_bootstrap.py').write_text('# SYNTHETIC PRE-INTERFACE LIBRARY; NO ORDINARY POLICY\n')
    (repo/'tools/macos/kronos_launcher.c').write_text('#include <stdio.h>\nint main(void){puts("HISTORICAL SOURCE; NOT USED AS BUILD ATTESTATION");return 0;}\n')
    command('/usr/bin/git','-C',repo,'checkout','-b','develop')
    command('/usr/bin/git','-C',repo,'config','branch.develop.remote','origin')
    command('/usr/bin/git','-C',repo,'config','branch.develop.merge','refs/heads/develop')
    command('/usr/bin/git','-C',repo,'add','-A');command('/usr/bin/git','-C',repo,'commit','-m','SYNTHETIC legacy observed shape')
    (repo/'src/kronos/common/legacy_bootstrap.py').chmod(0o600)
    revision=command('/usr/bin/git','-C',repo,'rev-parse','HEAD');tree=command('/usr/bin/git','-C',repo,'rev-parse','HEAD^{tree}')
    raw=subprocess.run(['/usr/bin/git','-C',str(repo),'ls-tree','-rz','--full-tree','HEAD'],check=True,capture_output=True).stdout
    entries=[]
    for item in raw.split(b'\0'):
        if not item:continue
        meta,name=item.split(b'\t');mode,kind,blob=meta.split();name=name.decode();data=(repo/name).read_bytes()
        entries.append(dict(path=name,mode=f'{(repo/name).stat().st_mode&0o777:04o}',git_mode=mode.decode(),git_blob=blob.decode(),sha256=sha256(data).hexdigest(),bytes=len(data)))
    inventory=dict(repository=str(repo),revision=revision,entries=entries,entry_count=len(entries))
    inventory_path=c['order_path'].with_name('SYNTHETIC-observed-legacy-inventory.json');inventory_raw=(json.dumps(inventory,indent=2)+'\n').encode();inventory_path.write_bytes(inventory_raw);inventory_path.chmod(0o600)
    inventory_ref=dict(identity='synthetic-observed-legacy-inventory',path=str(inventory_path),bytes=len(inventory_raw),sha256=sha256(inventory_raw).hexdigest())
    artifact=dict(schema='KRONOS_OBSERVED_LEGACY_APP_V1',bundle_identity=package.identity(c['bundle']),bundle_manifest=package.manifest(c['bundle']),source_build_correspondence='UNAVAILABLE')
    monkeypatch.setattr(p,'LEGACY_IDENTITY',(revision,inventory_ref['sha256'],artifact['bundle_identity']),raising=False)
    value=json.loads(Path(c['old']['path']).read_bytes());value.update(schema='KRONOS_OBSERVED_LEGACY_PAIR_V1',revision=revision,tree=tree,legacy_inventory=inventory_ref)
    value['artifact']=private(Path(value['artifact']['path']),artifact,final_lf=True)
    value['roster']=private(Path(value['roster']['path']),c['owner']._roster(repo))
    c['old']=private(Path(c['old']['path']),value);c['order']['current']=c['old']
    (c['evidence']/'legacy-fixture-seams.json').write_text(json.dumps(dict(production_approved_anchors=LEGACY_APPROVED,synthetic_disposable_anchors=p.LEGACY_IDENTITY,source_build_correspondence='UNAVAILABLE',real_comparisons=True,actual_signature_checks=True,actual_Git=True,actual_custody=True,product_startup=False),indent=2)+'\n')
    assert command('/usr/bin/git','--no-optional-locks','-C',repo,'status','--porcelain')==''
    return value


def test_legacy_observed_current_and_exact_preparatory_rollback(case,monkeypatch):
    _legacy_control(case,monkeypatch)
    test_actual_placement_and_separately_ordered_rollback(case)


@pytest.mark.parametrize('fault',('revision','inventory','branch','content','coherent-content','mode','coherent-mode','bundle','provenance','interpreter','implicit','as-selected'))
def test_legacy_foreign_or_changed_identity_denies(case,monkeypatch,fault):
    c=case;value=_legacy_control(c,monkeypatch)
    if fault=='revision':value['revision']='a'*40
    elif fault=='inventory':value['legacy_inventory']=dict(value['legacy_inventory'],sha256='b'*64)
    elif fault=='branch':command('/usr/bin/git','-C',c['repo'],'checkout','-b','foreign-branch')
    elif fault=='content':(c['repo']/'src/kronos/common/legacy_bootstrap.py').write_text('# CHANGED; NO CONTENT ACCEPTANCE STUB\n')
    elif fault=='coherent-content':
        target=c['repo']/'src/kronos/common/legacy_bootstrap.py';target.write_text('# COHERENT WORKING ROSTER BUT NOT THE PINNED GIT BLOB\n')
        command('/usr/bin/git','-C',c['repo'],'update-index','--assume-unchanged','src/kronos/common/legacy_bootstrap.py')
        assert command('/usr/bin/git','-C',c['repo'],'status','--porcelain')==''
        (c['evidence']/'disposable-index-flag.txt').write_text('assume-unchanged only in disposable legacy repository; original selected Git tree and pinned source inventory unchanged\n')
        value['roster']=private(Path(value['roster']['path']),c['owner']._roster(c['repo']))
    elif fault in ('mode','coherent-mode'):
        (c['repo']/'src/kronos/common/legacy_bootstrap.py').chmod(0o644)
        if fault=='coherent-mode':value['roster']=private(Path(value['roster']['path']),c['owner']._roster(c['repo']))
    elif fault=='bundle':
        artifact=json.loads(Path(value['artifact']['path']).read_bytes());artifact['bundle_identity']='d'*64;value['artifact']=private(Path(value['artifact']['path']),artifact,final_lf=True)
    elif fault=='provenance':
        artifact=json.loads(Path(value['artifact']['path']).read_bytes());artifact['source_build_correspondence']='APPROVED';value['artifact']=private(Path(value['artifact']['path']),artifact,final_lf=True)
    elif fault=='interpreter':value['interpreter']['sha256']='f'*64
    elif fault=='implicit':value.pop('legacy_inventory');value['schema']=p.PAIR_SCHEMA
    c['old']=private(Path(c['old']['path']),value);c['order']['current']=c['old']
    if fault=='as-selected':c['order']['selected']=c['old']
    before=c['owner']._roster(c['repo']);bundle=package.identity(c['bundle'])
    with pytest.raises((ValueError,OSError)):invoke(c)
    assert c['owner']._roster(c['repo'])==before and package.identity(c['bundle'])==bundle
    assert not (c['anchor'].parent/p.JOURNAL_NAME/'placement.backend-swapped.json').exists()


def test_legacy_then_two_stage_preserves_original_history(case,monkeypatch):
    _legacy_control(case,monkeypatch)
    test_two_stage_same_anchor_preserves_preparation(case,monkeypatch)


@pytest.mark.parametrize('boundary',('after-backend-swap','prepared-prefix-write','prepared-exact-expiry'))
def test_legacy_partial_expired_attempt_stays_spent(case,monkeypatch,boundary):
    _legacy_control(case,monkeypatch)
    test_actual_partial_effects_preserve_intent_and_deny_replay(case,monkeypatch,boundary)


def test_legacy_concurrent_exclusion(case,monkeypatch):
    _legacy_control(case,monkeypatch)
    test_actual_concurrent_exclusion(case)


def test_legacy_unfinished_write_retains_actual_custody(case,monkeypatch):
    _legacy_control(case,monkeypatch)
    test_entered_durable_work_cannot_be_closed_as_complete(case,monkeypatch)


def test_legacy_unresolved_helper_keeps_actual_exclusion(case,monkeypatch):
    _legacy_control(case,monkeypatch)
    test_actual_unresolved_helper_retains_exclusion_and_spent_intent(case,monkeypatch,'PREPARATORY')


# Sponsor-approved 83564 lock amendment: the legacy metadata exception never
# changes selected-release mode validation or startup/admission authority.
def _lock_row():
    return dict(path='.venv/.lock',mode=0o666,type='file',bytes=0,sha256=sha256(b'').hexdigest())


def _install_legacy_lock(c,monkeypatch):
    _legacy_control(c,monkeypatch)
    value=json.loads(Path(c['old']['path']).read_bytes())
    rows=c['owner']._roster(c['repo'])
    lock=c['repo']/'.venv/.lock'
    fd=os.open(lock,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o666)
    try:os.fchmod(fd,0o666);os.fsync(fd)
    finally:os.close(fd)
    rows.append(_lock_row());rows.sort(key=lambda x:x['path'])
    value['roster']=private(Path(value['roster']['path']),rows)
    c['old']=private(Path(c['old']['path']),value);c['order']['current']=c['old']
    return lock,rows


def test_legacy_tool_lock_exact_checkpoint_and_rollback(case,monkeypatch):
    c=case;lock,rows=_install_legacy_lock(c,monkeypatch)
    original_budget=c['owner'].budget;deadline=c['owner'].original_deadline
    test_actual_placement_and_separately_ordered_rollback(c)
    assert lock.read_bytes()==b'' and lock.stat().st_mode&0o777==0o666
    checkpoint=c['anchor'].parent/p.JOURNAL_NAME/'placement.checkpoint.backend/.venv/.lock'
    assert checkpoint.read_bytes()==b'' and checkpoint.stat().st_mode&0o777==0o666
    assert original_budget.deadline_ns==deadline
    assert c['owner']._roster(c['repo'],legacy_roster=rows)==rows
    (c['evidence']/'exact-legacy-lock-copy.json').write_text(json.dumps(dict(original_mode='0666',checkpoint_mode='0666',rollback_mode='0666',bytes=0,source_build_correspondence='UNAVAILABLE',production_mutation=False),indent=2)+'\n')


@pytest.mark.parametrize('fault',('nonempty','symlink','hardlink','unsafe-mode','foreign-owner','other-path','missing-binding','coherent-symlink','change-during-read'))
def test_legacy_tool_lock_rejected_variants(case,monkeypatch,fault):
    from types import SimpleNamespace
    c=case;lock,rows=_install_legacy_lock(c,monkeypatch);original=lock.stat();fired=[False]
    if fault=='nonempty':lock.write_bytes(b'X')
    elif fault in ('symlink','coherent-symlink'):
        lock.unlink();target=c['order_path'].with_name('alias-empty');target.write_bytes(b'');lock.symlink_to(target)
        if fault=='coherent-symlink':
            rows=[x for x in rows if x['path']!='.venv/.lock']+[dict(path='.venv/.lock',mode=lock.lstat().st_mode&0o777,type='symlink',target=str(target),sha256=sha256(str(target).encode()).hexdigest())]
    elif fault=='hardlink':os.link(lock,c['order_path'].with_name('lock-hardlink'))
    elif fault=='unsafe-mode':lock.chmod(0o664)
    elif fault=='other-path':
        other=lock.with_name('other.lock');other.write_bytes(b'');other.chmod(0o666)
        rows.append(dict(_lock_row(),path='.venv/other.lock'))
    elif fault=='missing-binding':rows=[x for x in rows if x['path']!='.venv/.lock']
    if fault in ('coherent-symlink','other-path','missing-binding'):
        value=json.loads(Path(c['old']['path']).read_bytes());value['roster']=private(Path(value['roster']['path']),sorted(rows,key=lambda x:x['path']));c['old']=private(Path(c['old']['path']),value);c['order']['current']=c['old']
    if fault=='foreign-owner':
        actual=os.fstat
        def observed(fd):
            value=actual(fd)
            if (value.st_dev,value.st_ino)==(original.st_dev,original.st_ino):
                data={n:getattr(value,n) for n in dir(value) if n.startswith('st_')};data['st_uid']=os.getuid()+1;fired[0]=True
                return SimpleNamespace(**data)
            return value
        monkeypatch.setattr(os,'fstat',observed)
    elif fault=='change-during-read':
        actual=os.read
        def changing(fd,count):
            raw=actual(fd,count)
            s=os.fstat(fd)
            if (s.st_dev,s.st_ino)==(original.st_dev,original.st_ino) and not fired[0]:
                fired[0]=True;lock.write_bytes(b'CHANGED DURING ACTUAL READ')
            return raw
        monkeypatch.setattr(os,'read',changing)
    app=package.identity(c['bundle'])
    with pytest.raises((ValueError,OSError)):invoke(c)
    assert package.identity(c['bundle'])==app
    assert not (c['anchor'].parent/p.JOURNAL_NAME/'placement.backend-swapped.json').exists()
    if fault in ('foreign-owner','change-during-read'):assert fired[0]
    if fault=='change-during-read':assert lock.read_bytes()==b'CHANGED DURING ACTUAL READ'
    (c['evidence']/'lock-negative-seams.json').write_text(json.dumps(dict(fault=fault,foreign_owner_metadata_simulated=(fault=='foreign-owner'),all_other_file_operations_actual=True),indent=2)+'\n')


@pytest.mark.parametrize('mode',(0o666,0o600))
def test_selected_tool_lock_preserves_strict_release_mode_checks(case,monkeypatch,mode):
    c=case;_install_legacy_lock(c,monkeypatch)
    value=json.loads(Path(c['new']['path']).read_bytes());rows=c['owner']._roster(c['newrepo'])
    lock=c['newrepo']/'.venv/.lock';lock.write_bytes(b'');lock.chmod(mode)
    rows.append(dict(_lock_row(),mode=mode));value['roster']=private(Path(value['roster']['path']),sorted(rows,key=lambda x:x['path']));c['new']=private(Path(c['new']['path']),value);c['order']['selected']=c['new']
    if mode==0o666:
        with pytest.raises(p.PlacementError,match='TREE_OWNER_MODE'):invoke(c)
        assert not (c['anchor'].parent/p.JOURNAL_NAME/'placement.backend-swapped.json').exists()
    else:
        assert invoke(c)['original_outcome']=='UNPROVED'
        assert (c['repo']/'.venv/.lock').stat().st_mode&0o777==0o600
    assert lock.stat().st_mode&0o777==mode


@pytest.mark.parametrize('fault',('fchmod','fsync','readback','exact-expiry'))
def test_legacy_tool_lock_copy_uncertainty_is_permanent(case,monkeypatch,fault):
    c=case;_install_legacy_lock(c,monkeypatch);created=[];fired=[False]
    original_budget=c['owner'].budget;deadline=c['owner'].original_deadline
    real_open=os.open;real_chmod=os.fchmod;real_sync=os.fsync
    def opening(name,flags,*args,**kwargs):
        fd=real_open(name,flags,*args,**kwargs)
        if str(name)=='.lock' and flags&os.O_CREAT:created.append(fd)
        return fd
    def chmod(fd,mode):
        if created and fd==created[-1] and fault=='fchmod':fired[0]=True;raise OSError('ACTUAL LEGACY LOCK MODE PUBLICATION FAILED')
        return real_chmod(fd,mode)
    def sync(fd):
        result=real_sync(fd)
        if created and fd==created[-1] and not fired[0]:
            fired[0]=True
            if fault=='fsync':raise OSError('ACTUAL LEGACY LOCK FSYNC UNCERTAIN')
            if fault=='readback':os.write(fd,b'BAD READBACK')
            if fault=='exact-expiry':monkeypatch.setattr(a,'monotonic_ns',lambda:deadline)
        return result
    with monkeypatch.context() as patch:
        patch.setattr(os,'open',opening);patch.setattr(os,'fchmod',chmod);patch.setattr(os,'fsync',sync)
        with pytest.raises((ValueError,OSError)):invoke(c)
    assert fired[0] and c['owner'].budget is original_budget and original_budget.deadline_ns==deadline
    history=c['anchor'].parent/p.JOURNAL_NAME
    assert (history/'placement.intent.json').is_file() and not (history/'placement.prepared.json').exists()
    disposition=c['owner'].close()
    if fault!='readback':assert disposition['state']=='UNRESOLVED' and disposition['custody_retained']
    (c['evidence']/'lock-copy-application-outcome.json').write_text(json.dumps(dict(fault=fault,resources=disposition,original_deadline=deadline,spent_intent=True,source_mode_unchanged='0666'),indent=2)+'\n')
    if disposition['custody_retained']:
        blocked=p.Placement(a.ValidationBudget(a.monotonic_ns()+120_000_000_000))
        try:
            with pytest.raises(BlockingIOError):blocked.execute(private(c['order_path'],c['order']))
        finally:assert blocked.close()['state']=='CLOSED'
        # Separate defensive test teardown represents loss of the original
        # holder. It never certifies its unresolved application cleanup.
        os.close(c['owner'].descriptor);c['owner'].descriptor=None
        (c['evidence']/'lock-copy-defensive-fixture-teardown.json').write_text(json.dumps(dict(original_application_outcome=disposition,independent_exclusion_observed=True,forced_fixture_fd_close=True,application_cleanup_success=False),indent=2)+'\n')
        assert c['owner'].unresolved
    other=p.Placement(a.ValidationBudget(a.monotonic_ns()+120_000_000_000))
    try:
        with pytest.raises(p.PlacementError,match='PRIOR_OR_REPLAY'):other.execute(private(c['order_path'],c['order']))
    finally:other.close()


def test_actual_retained_legacy_and_preparatory_pair_readers(case,monkeypatch):
    """Exact retained source/artifacts/dependencies; disposable custody/locators.

    No source pin edit, content/signature acceptance stub or operational
    transition. The temporary actual P binding is used only to compare the real
    selected source; already adopted disposable custody and its budget persist.
    """
    c=case;inputs=json.loads((ROOT.parent/'prepared-pair-inputs/CONTROL.json').read_bytes())
    assert p.LEGACY_IDENTITY==LEGACY_APPROVED
    original_budget=c['owner'].budget;deadline=c['owner'].original_deadline
    from tools import runtime_source_gate as source_gate
    actual_validation=a.validation_output;observations=[]
    def observed_validation(arguments,**kwargs):
        row=dict(argv=list(map(str,arguments)),phase=kwargs.get('phase'),same_original_budget=kwargs.get('budget') is original_budget,original_deadline=deadline)
        observations.append(row)
        try:
            raw=actual_validation(arguments,**kwargs);row.update(actual_exit=0,output_bytes=len(raw),output_sha256=sha256(raw).hexdigest());return raw
        except BaseException as error:
            row.update(exception=type(error).__name__,actual_exit=getattr(error,'returncode',None),unresolved=a.validation_unresolved());raise
        finally:(c['evidence']/'actual-pair-validation-commands.json').write_text(json.dumps(observations,indent=2)+'\n')
    monkeypatch.setattr(a,'validation_output',observed_validation);monkeypatch.setattr(source_gate,'validation_output',observed_validation)
    c['owner'].owner=threading.current_thread();c['owner']._acquire(c['order']['enrollment']);fd=c['owner'].descriptor
    for label,selected in [('legacy',False),('selected',True)]:
        original=json.loads(Path(inputs[label]['path']).read_bytes());original['repository']=c['policy']['repository_path'];original['bundle']=c['policy']['bundle_path']
        ref=private(c['order_path'].with_name(label+'-actual-bytes-pair.json'),original)
        if not selected:c['order']['current']=ref;c['owner'].order=c['order']
        else:monkeypatch.setattr(a,'PERSISTENT_ANCHOR_BINDING',assert_actual_preparatory_source())
        result=c['owner']._pair(ref,Path(inputs[label+'_backend']),Path(inputs[label+'_bundle']),selected=selected)
        assert result==original and c['owner'].descriptor==fd and c['owner'].budget is original_budget and original_budget.deadline_ns==deadline
    assert observations and all(x['same_original_budget'] and x.get('actual_exit')==0 for x in observations)
    assert not (c['anchor'].parent/p.JOURNAL_NAME).exists()
    assert c['owner'].close()['state']=='CLOSED'
    (c['evidence']/'actual-pair-component-proof.json').write_text(json.dumps(dict(real_source_legacy_anchors=LEGACY_APPROVED,source_build_correspondence='UNAVAILABLE',selected_revision=original['revision'],same_budget_and_custody=True,canonical_destination_locators_disposable=True,selected_pin_matches_actual_production_bytes=True,claims_or_product_children_or_placement_created=False,ready_or_native_integration_claimed=False),indent=2)+'\n')



def test_actual_canonical_applications_parent_descriptor(record_property):
    """Actual read-only system-parent FD; no app contents or custody acquired."""
    fd=p._directory_fd('/Applications')
    try:
        s=os.fstat(fd);assert s.st_uid==0 and s.st_gid==80 and s.st_mode&0o7777==0o775
        record_property('actual_system_parent',json.dumps(dict(path='/Applications',uid=s.st_uid,gid=s.st_gid,mode='0775',device=s.st_dev,inode=s.st_ino,app_contents_read=False,production_permission_change=False)))
    finally:os.close(fd)


@pytest.mark.parametrize('fault',('wrong-owner','wrong-admin-group','world-writable','other-group-write','setgid'))
def test_canonical_applications_parent_exact_metadata_denials(monkeypatch,record_property,fault):
    from types import SimpleNamespace
    original=Path('/Applications').lstat();actual=os.fstat
    def observed(fd):
        s=actual(fd)
        if (s.st_dev,s.st_ino)==(original.st_dev,original.st_ino):
            values={k:getattr(s,k) for k in dir(s) if k.startswith('st_')}
            if fault=='wrong-owner':values['st_uid']=os.getuid()
            elif fault=='wrong-admin-group':values['st_gid']=81
            else:values['st_mode']=(s.st_mode&~0o7777)|{'world-writable':0o777,'other-group-write':0o770,'setgid':0o2775}[fault]
            return SimpleNamespace(**values)
        return s
    monkeypatch.setattr(os,'fstat',observed)
    with pytest.raises(p.PlacementError,match='UNSAFE_DIRECTORY'):p._directory_fd('/Applications')
    record_property('negative_metadata_seam',fault+'; actual no-follow directory open; controlled fstat negative; no OS metadata change')


@pytest.mark.parametrize('fault',('group-writable-lookalike','symlink-alias'))
def test_canonical_parent_exception_never_matches_private_lookalikes(tmp_path,fault):
    directory=tmp_path/'Applications'
    if fault=='group-writable-lookalike':directory.mkdir(mode=0o775);directory.chmod(0o775)
    else:directory.symlink_to('/Applications',target_is_directory=True)
    with pytest.raises((ValueError,OSError)):p._directory_fd(directory)
