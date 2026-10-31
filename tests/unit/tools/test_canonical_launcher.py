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


@pytest.fixture(autouse=True)
def preparatory_pin_disposable_binding(monkeypatch):
    from tests.unit.tools.test_place_release_pair import assert_actual_preparatory_source
    assert_actual_preparatory_source()
    from kronos.common import release_admission as admission
    monkeypatch.setattr(admission,'PERSISTENT_ANCHOR_BINDING',None)


def _fixture_native_source(source_path):
    from tests.unit.tools.test_place_release_pair import assert_actual_preparatory_source
    actual=assert_actual_preparatory_source()
    source=source_path.read_text()
    exact='static const char *approved_persistent_binding = '+json.dumps(actual.decode())+';'
    # Normalize only the proved production P assignment in disposable compiled
    # sources. Existing fixture code then installs its exact local pins as before.
    return source.replace(exact,'static const char *approved_persistent_binding = NULL;')


def _s305_setup_control(tmp_path,monkeypatch,*,source_root=None):
    """Actual setup writer/helper/custody; synthetic authority/signature pins.

    Reuses the disposable Git-backed source/package and owned-process inventory
    seam. No production root, status endpoint, control token or GUI is used.
    """
    from hashlib import sha256
    from kronos.common import legacy_bootstrap as b,release_admission as a
    from tests.unit.common import test_failed_successor_restore as fixture
    from tests.unit.common import test_legacy_bootstrap as setup
    c=_s304_compile_preparer(tmp_path,monkeypatch,source_root=source_root)
    anchor=c['anchor'];installation=c['installation'];base=anchor.parent
    raw=b._canonical(installation);staged=base/'s305-staged-enrollment.json';staged.write_bytes(raw);staged.chmod(0o600)
    destination=anchor/'e02-frozen-enrollment.json'
    fd=os.open(anchor,os.O_RDONLY|os.O_DIRECTORY)
    try:observed=a.descriptor_filesystem_identity(fd)
    finally:os.close(fd)
    persistent=dict(schema='KRONOS_PERSISTENT_ANCHOR_BINDING_V1',installation_identity=installation['identity'],
        enrollment=fixture._ref(destination,installation['identity'],raw),anchor_path=str(anchor),
        volume_uuid=observed['volume_uuid'],file_id=observed['file_id'],owner=os.getuid(),required_mode='0700',
        bundle_id=installation['bundle_id'],bundle_path=installation['bundle_path'],repository_path=installation['repository_path'])
    pinned=b._canonical(persistent)
    c.update(persistent=persistent,pinned=pinned,staged=staged,destination=destination)
    unit=c['evidence']/'preparer.c';source=unit.read_text()
    source=source.replace('approved_persistent_binding = NULL;','approved_persistent_binding = '+json.dumps(pinned.decode())+';')
    source=source.replace(' && strstr(name,".json")','')
    source=source.replace('int result=native_initialize(argv[2],argv[4],argv[5]);',
        ('int result=!strcmp(argv[6],"initialize")?native_initialize(argv[2],argv[4],argv[5]):native_setup(argv[2],argv[4],argv[5]);'
         if 'static int native_setup(' in source else 'int result=preserved_operational_main();'))
    unit=c['evidence']/'setup.c';unit.write_text(source)
    command=['clang','-Wall','-Wextra','-Werror',str(unit),'-o',c['args'][0]]
    result=subprocess.run(command,capture_output=True,text=True)
    (c['evidence']/'setup-compile.json').write_text(json.dumps(dict(command=command,actual_exit=result.returncode,
        stdout=result.stdout,stderr=result.stderr,source_sha256=sha256(unit.read_bytes()).hexdigest()),indent=2))
    assert result.returncode==0,result.stderr
    binary=Path(c['args'][0]);shutil.copy2(binary,c['evidence']/'setup-launcher')
    shim=Path(c['args'][4]);text=shim.read_text().replace('a.CANONICAL_PARENT=',
        'a.PERSISTENT_ANCHOR_BINDING='+repr(pinned)+'\na.APPROVED_BINDING=a.AnchorBinding(a.Path('+repr(str(anchor))+'),'+
        repr(installation['device'])+','+repr(installation['inode'])+','+repr(installation['owner'])+')\na.CANONICAL_PARENT=')
    shim.write_text(text);shim.chmod(0o755);shutil.copy2(shim,c['evidence']/'setup-helper-python')
    # The rebuilt executable is genuinely checked by the existing artifact
    # validator; update its synthetic selection coherently, never stub it.
    selection_path=Path(c['env']['KRONOS_NATIVE_SELECTION_PATH']);selection=json.loads(selection_path.read_bytes())
    artifact_path=Path(selection['artifact_manifest']['path']);artifact=json.loads(artifact_path.read_bytes())
    rows=setup._c02_bundle_manifest(Path(c['args'][3]));digest=sha256(binary.read_bytes()).hexdigest()
    artifact.update(bundle_manifest=rows,bundle_identity=sha256(b._canonical(rows)).hexdigest(),
        built_binary_sha256=digest,signed_binary_sha256=digest)
    artifact_path.write_bytes(b._canonical(artifact)+b'\n')
    selection['artifact_manifest']=fixture._ref(artifact_path,'artifact',artifact_path.read_bytes())
    selection['target']['artifact_manifest_sha256']=sha256(artifact_path.read_bytes()).hexdigest()
    selection_path.write_bytes(b._canonical(selection));selection_path.chmod(0o600)
    c['selection']=fixture._ref(selection_path,selection['selection_id'],selection_path.read_bytes())
    c['selected']=selection
    for suffix,key in [('PATH','path'),('BYTES','bytes'),('SHA256','sha256'),('ID','identity')]:
        c['env']['KRONOS_NATIVE_SELECTION_'+suffix]=str(c['selection'][key])
    (c['evidence']/'test-only-seams.json').write_text(json.dumps(dict(
        authority='SYNTHETIC FOUR-ROLE DOCUMENTS; NOT SPONSOR APPROVAL',signature='EXPLICIT DISPOSABLE SIGNATURE SEAM',
        parent_image='ACTUAL KERNEL IMAGE; CANONICAL REQUIREMENT PINNED TO DISPOSABLE BINARY',
        inventory='OWNED FIXTURE PROCESS NAMESPACE ONLY',gui='NO GUI OR CHILD DISPATCH'),indent=2))
    return c


def _s305_setup_env(c,operation,input_ref):
    from hashlib import sha256
    from kronos.common import legacy_bootstrap as b,release_admission as a
    from tests.unit.common import test_failed_successor_restore as fixture
    now=datetime.now(UTC);path=c['anchor'].parent/(operation.lower()+'-order.json')
    value=dict(schema=a.SETUP_ORDER_SCHEMA,identity=operation.lower()+'-order',operation=operation,
        installation_identity=c['installation']['identity'],binding_sha256=sha256(c['pinned']).hexdigest(),
        selection=c['selection'],input=input_ref,valid_from=(now-timedelta(seconds=30)).isoformat(),
        valid_until=(now+timedelta(minutes=4)).isoformat(),decisions=c['selected']['decisions'])
    raw=fixture._put(path,value);env=dict(c['env'],KRONOS_SETUP_OPERATION=operation)
    for key in list(env):
        if key.startswith('KRONOS_INITIALIZATION_'):del env[key]
    for prefix,ref in [('KRONOS_SETUP_ORDER',fixture._ref(path,value['identity'],raw)),('KRONOS_SETUP_INPUT',input_ref)]:
        for suffix,key in [('PATH','path'),('BYTES','bytes'),('SHA256','sha256'),('ID','identity')]:env[prefix+'_'+suffix]=str(ref[key])
    return env


def _s305_activation_control(tmp_path,monkeypatch,request,*,files=1,owner_blocker=False,metadata_fault=None,unresolved_verify=False):
    """Actual setup/init/activation/attempt writers; synthetic reviewed inputs.

    Initial-assessment document shapes model accepted 83556's byte bindings.
    They do not assert an actual product-owner review or production eligibility.
    """
    from hashlib import sha256
    from types import SimpleNamespace
    from kronos.common import legacy_bootstrap as b,release_admission as a
    from tests.unit.common import test_failed_successor_restore as fixture
    from tests.unit.common import test_legacy_bootstrap as setup
    c=_s305_setup_control(tmp_path,monkeypatch)
    request.addfinalizer(lambda:shutil.copytree(c['anchor'].parent,c['evidence']/'A1-finalizer-primary',symlinks=True))
    initial=fixture._ref(c['staged'],c['installation']['identity'],c['staged'].read_bytes())
    assert _s305_retained_run(c,_s305_setup_env(c,'PLACE_ENROLLMENT',initial),'A1-enrollment').returncode==0
    result=_s305_retained_run(c,c['env'],'A1-initialization','initialize');assert result.returncode==0,result.stderr
    root=c['anchor']/'failed-successor-restore-v1';original_genesis={p.name:p.read_bytes() for p in root.iterdir()}
    base=c['anchor'].parent;store=base/'accepted-owner-records';store.mkdir(mode=0o700)
    for number in range(files):fixture._put(store/(str(number)+'.json'),dict(
        label='DISPOSABLE RETAINED VALUE; NOT OWNER AUTHORITY',committed=number,delivery='UNCERTAIN_PRESERVED'))
    budget=a.ValidationBudget(a.monotonic_ns()+120_000_000_000)
    checks=SimpleNamespace(budget=budget,check=budget.check)
    scopes=[dict(path=str(store),present=True),dict(path=str(base/'accepted-absent-owner-scope'),present=False)]
    rows=b._native_file_rows(scopes,checks)
    identities=base/'accepted-identities.json';assessment=base/'accepted-assessment.json'
    # Pretty report bytes intentionally exercise exact existing presentation,
    # not a rewritten canonical substitute for the accepted report format.
    identities.write_text(json.dumps(dict(schema='KRONOS-83556-SAVED-RECORD-IDENTITIES-V1',records=[
        dict(path=row['path'],sha256=row['sha256'],bytes=row['bytes'],mode=f"{row['mode']:04o}",
            unchanged=True,retained_object='SYNTHETIC_FIXTURE_ONLY') for row in rows],limitations=['SYNTHETIC']),indent=2)+'\n')
    identities.chmod(0o600)
    assessment.write_text(json.dumps(dict(schema='KRONOS-83556-ELIGIBILITY-REGISTER-V1',order=83556,
        recommendation='SAVED_STATE_SUPPORTS_BOUNDED_FIRST_START_PREPARATION; NO_DEMONSTRATED_SAVED_STATE_REPAIR_REQUIRED',
        actual_startup_authority='NOT_GRANTED',new_demonstrated_saved_state_blockers=['MANDATORY_OWNER_FACT_MISSING'] if owner_blocker else [],inconsistent_saved_state_findings=[],
        all_saved_files_unchanged=True,saved_record_files=len(rows),label='SYNTHETIC DISPOSABLE AUTHORITY SEAM'),indent=2)+'\n')
    assessment.chmod(0o600)
    chunks=[]
    for start in range(0,len(rows),128):
        path=base/('initial-files-'+str(start//128)+'.json');identity='initial-files-'+str(start//128)
        chunks.append(fixture._ref(path,identity,fixture._put(path,dict(
            schema='KRONOS_PREPARED_ACTIVATION_FILES_V1',identity=identity,files=rows[start:start+128]))))
    state_path=base/'initial-state.json'
    state=dict(schema='KRONOS_PREPARED_ACTIVATION_STATE_V1',identity='initial-state',
        installation_identity=c['installation']['identity'],scopes=scopes,chunks=chunks,
        assessment=fixture._ref(assessment,'accepted-assessment',assessment.read_bytes()),
        identities=fixture._ref(identities,'accepted-identities',identities.read_bytes()))
    state_ref=fixture._ref(state_path,'initial-state',fixture._put(state_path,state))
    genesis=json.loads(fixture._s304_resolve_retained_fixture(root,c['installation']))
    evidence_path=Path(genesis['evidence']['path']);evidence=json.loads(evidence_path.read_bytes())
    intent=c['anchor']/'controlled-setup-v1/enrollment.intent.json'
    evidence['subsequent_observations'] += [fixture._ref(intent,'setup-enrollment',intent.read_bytes()),state_ref]
    raw=fixture._put(evidence_path,evidence);genesis['evidence']=fixture._ref(evidence_path,genesis['evidence']['identity'],raw)
    g=b._canonical(genesis)
    ordinary=dict(schema='ORDINARY_SAME_RELEASE_V1',scope='ORDINARY_SAME_RELEASE_WITH_QUALIFIED_STOP',
        installation_identity=c['installation']['identity'],binding_sha256=sha256(c['pinned']).hexdigest(),
        genesis_disposition_sha256=sha256(g).hexdigest(),release_id='S305-SYNTHETIC-RELEASE',
        installed_selection_path=str(c['anchor']/'ordinary-start-v1/installed-selection.json'))
    o=b._canonical(ordinary)
    source=(c['evidence']/'setup.c').read_text()
    source=source.replace('approved_initialization_disposition = NULL;',
        'approved_initialization_disposition = '+json.dumps(g.decode())+';')
    source=source.replace('approved_ordinary_restart_policy = NULL;',
        'approved_ordinary_restart_policy = '+json.dumps(o.decode())+';')
    prefix='''\n#include <stdio.h>\nstatic int s305_observe_rename(int,const char *,int,const char *);\n#define renameat s305_observe_rename\n'''
    insertion=source.rfind('int main(int argc,char **argv) {')
    source=prefix+source[:insertion]+r'''
#undef renameat
static int s305_observe_rename(int from,const char *old,int to,const char *name) {
 int result=renameat(from,old,to,name);
 if(!result && !strcmp(name,"admission-head.json"))snprintf(s304_stage,sizeof(s304_stage),"activation-final-commit");
 return result;
}
'''+source[insertion:]
    expiry='''int result=fsync(fd);
    if(!result && !strcmp(s304_fault,"ordinary-durability-expiry")) {
        char current[PATH_MAX];
        if(fcntl(fd,F_GETPATH,current)==0 && strstr(current,"/accepted-owner-records/")) {
            s304_now=validation_current_deadline();
            fprintf(stderr,"ACTUAL_OWNER_FSYNC_RETURNED_AT_CONTROLLED_EXACT_DEADLINE\\n");
        }
    }'''
    assert source.count('int result=fsync(fd);')==1
    source=source.replace('int result=fsync(fd);',expiry)
    target='s304_fault=argv[6];int result='
    replacement=r'''
    s304_fault=argv[6];
    if(!strncmp(argv[6],"ordinary",8)) {
        int ok=native_gate(argv[2],argv[4],"ORDINARY");
        if(ok)ok=native_original_reserve(0);
        if(ok && !strcmp(argv[6],"ordinary-interrupt"))_exit(97);
        if(ok && !strcmp(argv[6],"ordinary-expiry"))s304_now=validation_current_deadline();
        if(ok)ok=native_advance("CHILD_START_RESERVED","{}");
        if(ok) {
            char path[PATH_MAX];snprintf(path,sizeof(path),"%s/ONE-CHILD-EFFECT",admission_anchor);
            int effect=open(path,O_WRONLY|O_CREAT|O_EXCL,0600);
            ok=effect>=0 && write(effect,"ONE",3)==3 && fsync(effect)==0;
            if(effect>=0 && close(effect)!=0)ok=0;
        }
        fprintf(stderr,"ACTUAL_NEW_ATTEMPT_RESULT=%d HEAD=%s ORIGINAL_DEADLINE=%lld OBSERVED=%lld\n",
            ok,native_journal.state,validation_deadline_ns,validation_now_ns());
        finish_admission();return ok?0:1;
    }
    int result='''
    assert target in source;source=source.replace(target,replacement)
    unit=c['evidence']/'A1-launcher.c';unit.write_text(source)
    command=['clang','-Wall','-Wextra','-Werror',str(unit),'-o',c['args'][0]]
    compiled=subprocess.run(command,capture_output=True,text=True)
    (c['evidence']/'A1-compile.json').write_text(json.dumps(dict(command=command,actual_exit=compiled.returncode,
        stdout=compiled.stdout,stderr=compiled.stderr,source_sha256=sha256(unit.read_bytes()).hexdigest()),indent=2))
    assert compiled.returncode==0,compiled.stderr
    binary=Path(c['args'][0]);shutil.copy2(binary,c['evidence']/'A1-launcher')
    shim=Path(c['args'][4]);text=shim.read_text().replace('b._verify_bundle_signature=',
        'from kronos.common import failed_successor_restore as r\nr.INITIALIZATION_DISPOSITION='+repr(g)+
        '\nb.ORDINARY_RESTART_POLICY='+repr(o)+'\nb._verify_bundle_signature=')
    recorder='''
from pathlib import Path
import os
actual_validation=b.native_validation_result
def observed_validation(value):
    location=Path(BASE)/('helper-'+str(os.getpid()))
    location.with_suffix('.request.json').write_bytes(b._canonical(value))
    try: result=actual_validation(value)
    except BaseException as error:
        location.with_suffix('.exception.json').write_text(repr(error))
        raise
    location.with_suffix('.actual-response.json').write_bytes(b._canonical(result))
    if UNRESOLVED and value['action']=='setup-verify-prepared':
        budget=a.inherited_budget(20,required=True)
        a.validation_output([sys.executable,'-c','import time;time.sleep(5)'],cwd=BASE,
            budget=budget,ceiling=.05,phase='ACTUAL_NESTED_ACTIVATION_VERIFICATION')
    if FAULT and value['action']=='setup-prepare':
        if FAULT=='missing-boot':result.pop('boot_session')
        elif FAULT=='wrong-boot':result['boot_session']='11111111-1111-1111-1111-111111111111'
        elif FAULT=='missing-policy':result.pop('ordinary_policy_sha256')
        elif FAULT=='wrong-policy':result['ordinary_policy_sha256']='f'*64
    location.with_suffix('.returned-response.json').write_bytes(b._canonical(result))
    return result
b.native_validation_result=observed_validation
'''.replace('BASE',repr(str(base))).replace('UNRESOLVED',repr(unresolved_verify)).replace('FAULT',repr(metadata_fault))
    text=text.replace('assert sys.argv[1:3]',recorder+'\nassert sys.argv[1:3]')
    shim.write_text(text);shim.chmod(0o755);shutil.copy2(shim,c['evidence']/'A1-helper-python')
    # New release selection paths preserve the actual initializer's original
    # source/artifact/selection documents and every genesis byte.
    artifact_path=base/'A1-artifact-manifest.json';artifact=json.loads(Path(c['selected']['artifact_manifest']['path']).read_bytes())
    bundle_rows=setup._c02_bundle_manifest(Path(c['args'][3]));digest=sha256(binary.read_bytes()).hexdigest()
    artifact.update(bundle_manifest=bundle_rows,bundle_identity=sha256(b._canonical(bundle_rows)).hexdigest(),
        built_binary_sha256=digest,signed_binary_sha256=digest)
    artifact_path.write_bytes(b._canonical(artifact)+b'\n');artifact_path.chmod(0o600)
    now=datetime.now(UTC);selected=dict(c['selected'],selection_id='A1-selection',
        artifact_manifest=fixture._ref(artifact_path,'A1-artifact',artifact_path.read_bytes()),
        target=dict(c['selected']['target'],artifact_manifest_sha256=sha256(artifact_path.read_bytes()).hexdigest()),
        valid_from=(now-timedelta(seconds=30)).isoformat(),valid_until=(now+timedelta(minutes=4)).isoformat())
    selection_path=base/'A1-selection.json';raw=fixture._put(selection_path,selected)
    c['selection']=fixture._ref(selection_path,'A1-selection',raw);c['selected']=selected
    installed=dict(c['selection'],path=ordinary['installed_selection_path'])
    activation_path=base/'A1-activation.json';activation=dict(schema=b.ORDINARY_ACTIVATION_SCHEMA,identity='A1-activation',
        policy_sha256=sha256(o).hexdigest(),installation_identity=c['installation']['identity'],
        genesis_disposition_sha256=sha256(g).hexdigest(),release_id=ordinary['release_id'],selection=installed,
        decisions=selected['decisions'],activated_at=now.isoformat())
    activation_ref=fixture._ref(activation_path,'A1-activation',fixture._put(activation_path,activation))
    package_path=base/'A1-package.json';package=dict(schema='KRONOS_PREPARED_ORDINARY_ACTIVATION_V1',
        identity='A1-package',selection=c['selection'],activation=activation_ref,state=state_ref)
    package_ref=fixture._ref(package_path,'A1-package',fixture._put(package_path,package))
    for suffix,key in [('PATH','path'),('BYTES','bytes'),('SHA256','sha256'),('ID','identity')]:
        c['env']['KRONOS_NATIVE_SELECTION_'+suffix]=str(c['selection'][key])
    env=_s305_setup_env(c,'ACTIVATE_SELECTION',package_ref)
    ordinary_env={k:v for k,v in env.items() if not k.startswith(('KRONOS_SETUP_','KRONOS_NATIVE_SELECTION_'))}
    assert all((root/name).read_bytes()==value for name,value in original_genesis.items())
    c.update(activation_env=env,ordinary_env=ordinary_env,genesis=g,ordinary_policy=o,state=state,
        owner_store=store,initial_genesis=original_genesis,package_ref=package_ref,activation_ref=activation_ref)
    return c


@pytest.mark.parametrize('completion',('timely','late','lost-acknowledgement'))
def test_s305_A1_actual_activation_and_once_reserved_assessment(tmp_path,monkeypatch,record_property,request,completion):
    c=_s305_activation_control(tmp_path,monkeypatch,request)
    fault={'timely':'valid','late':'activation-final-commit:directory-expiry',
        'lost-acknowledgement':'lost-acknowledgement'}[completion]
    result=_s305_retained_run(c,c['activation_env'],'A1-activation',fault)
    assert result.returncode=={'timely':0,'late':1,'lost-acknowledgement':98}[completion],result.stderr
    root=c['anchor']/'failed-successor-restore-v1';head=json.loads((root/'admission-head.json').read_bytes())
    assert head['state']=='ORDINARY_ACTIVATED' and head['sequence']==2
    intent=(c['anchor']/'controlled-setup-v1/activation.intent.json').read_bytes()
    assert json.loads(intent)['original_outcome']=='UNPROVED'
    first=_s305_retained_run(c,c['ordinary_env'],'A1-new-attempt','ordinary')
    assert first.returncode==0,first.stderr
    effect=c['anchor']/'ONE-CHILD-EFFECT';assert effect.read_bytes()==b'ONE'
    after=json.loads((root/'admission-head.json').read_bytes());assert after['state']=='CHILD_START_RESERVED'
    phase=json.loads((root/(after['active_reservation_id']+'.json')).read_bytes())
    assert phase['details']['current_activation_check']['original_outcome']=='NOT_RECLASSIFIED'
    previous=json.loads(Path(phase['previous']['path']).read_bytes())
    assert phase['details']['timing']==previous['details']['timing']
    assert phase['details']['timing']['deadline_ns']!=json.loads(intent)['timing']['deadline_ns']
    assert 'ORIGINAL_DEADLINE='+str(phase['details']['timing']['deadline_ns']) in first.stderr
    assert (c['anchor']/'controlled-setup-v1/activation.intent.json').read_bytes()==intent
    original={p.name:p.read_bytes() for p in root.iterdir()}
    second=_s305_retained_run(c,c['ordinary_env'],'A1-denied-second-attempt','ordinary')
    assert second.returncode==1 and original=={p.name:p.read_bytes() for p in root.iterdir()}
    record_property('application_before_teardown','ACTUAL NATIVE ACTIVATION/RESERVATION/CHILD-INTENT WRITERS; MARKER ONLY, NO APPLICATION CHILD; ORIGINAL OUTCOME UNCHANGED; NO SECOND ATTEMPT')


@pytest.mark.parametrize('fault',('activation.intent.json:prefix','installed-selection.json:zero',
    'activation.json:prefix','activation.json:directory-expiry','activation.json:directory-death',
    'head-2.json:prefix','setup-activation.ordinary-activated.json:prefix','head-2.next:prefix'))
def test_s305_A1_partial_activation_is_persistently_fenced(tmp_path,monkeypatch,record_property,request,fault):
    c=_s305_activation_control(tmp_path,monkeypatch,request)
    result=_s305_retained_run(c,c['activation_env'],'A1-partial',fault)
    assert result.returncode in (1,-9),result.stderr
    assert not (c['anchor']/'ONE-CHILD-EFFECT').exists()
    before={str(p.relative_to(c['anchor'])):p.read_bytes() for p in c['anchor'].rglob('*') if p.is_file()}
    denied=_s305_retained_run(c,c['ordinary_env'],'A1-next-invocation','ordinary')
    assert denied.returncode==1 and before=={
        str(p.relative_to(c['anchor'])):p.read_bytes() for p in c['anchor'].rglob('*') if p.is_file()}
    replay=_s305_retained_run(c,c['activation_env'],'A1-no-setup-retry')
    assert replay.returncode==1 and before=={
        str(p.relative_to(c['anchor'])):p.read_bytes() for p in c['anchor'].rglob('*') if p.is_file()}
    record_property('application_before_teardown','ACTUAL PARTIAL/EXPIRED/DEAD-CUSTODIAN PUBLICATION RETAINED; NEW INVOCATION CANNOT CLEAR IT; NO CLAIM/CHILD; NO RETRY')


@pytest.mark.parametrize('finding',('source','artifact','missing-state-chunk','changed-state-chunk','owner-blocker',
    'missing-boot','wrong-boot','missing-policy','wrong-policy'))
def test_s305_A1_authority_pairing_and_evidence_denials(tmp_path,monkeypatch,record_property,request,finding):
    c=_s305_activation_control(tmp_path,monkeypatch,request,owner_blocker=finding=='owner-blocker',
        metadata_fault=finding if finding in ('missing-boot','wrong-boot','missing-policy','wrong-policy') else None)
    if finding=='source':(Path(c['args'][2])/'README.md').write_bytes(b'CHANGED ACTUAL SELECTED SOURCE\n')
    if finding=='artifact':(Path(c['args'][3])/'Contents/Resources/KRONOS.png').write_bytes(b'CHANGED ACTUAL ARTIFACT')
    if finding=='missing-state-chunk':Path(c['state']['chunks'][0]['path']).unlink()
    if finding=='changed-state-chunk':
        path=Path(c['state']['chunks'][0]['path']);path.write_bytes(path.read_bytes()+b' ')
    before={str(p.relative_to(c['anchor'])):p.read_bytes() for p in c['anchor'].rglob('*') if p.is_file()}
    result=_s305_retained_run(c,c['activation_env'],'A1-binding-denial')
    assert result.returncode==1,result.stderr
    assert before=={str(p.relative_to(c['anchor'])):p.read_bytes() for p in c['anchor'].rglob('*') if p.is_file()}
    assert not (c['anchor']/'ordinary-start-v1').exists()
    assert not (c['anchor']/'controlled-setup-v1/activation.intent.json').exists()
    record_property('application_before_teardown','ACTUAL COMPARISONS/PIN AGREEMENT; DENIAL BEFORE PREPARATION EFFECTS; SYNTHETIC AUTHORITY/SIGNATURE/ASSESSMENT; ACTUAL FILE BYTES/CUSTODY/BUDGET')


@pytest.mark.parametrize('finding',('expiry','durability-expiry','interruption','changed-owner-record','new-owner-file','missing-owner-record'))
def test_s305_A1_failed_new_attempt_is_spent(tmp_path,monkeypatch,record_property,request,finding):
    c=_s305_activation_control(tmp_path,monkeypatch,request)
    assert _s305_retained_run(c,c['activation_env'],'A1-prepare').returncode==0
    original_intent=(c['anchor']/'controlled-setup-v1/activation.intent.json').read_bytes()
    if finding=='changed-owner-record':next(c['owner_store'].iterdir()).write_bytes(b'CHANGED RETAINED OWNER DATA')
    if finding=='new-owner-file':(c['owner_store']/'unexpected.json').write_bytes(b'{}')
    if finding=='missing-owner-record':next(c['owner_store'].iterdir()).unlink()
    fault={'expiry':'ordinary-expiry','durability-expiry':'ordinary-durability-expiry',
        'interruption':'ordinary-interrupt'}.get(finding,'ordinary')
    first=_s305_retained_run(c,c['ordinary_env'],'A1-failed-new-attempt',fault)
    assert first.returncode==(97 if finding=='interruption' else 1),first.stderr
    root=c['anchor']/'failed-successor-restore-v1';head=json.loads((root/'admission-head.json').read_bytes())
    assert head['state']=='ORIGINAL_RESERVED' and head['sequence']==3
    record=json.loads((root/(head['active_reservation_id']+'.json')).read_bytes())
    assert record['details']['prior_activation']['identity']=='setup-activation'
    if finding=='durability-expiry':assert 'ACTUAL_OWNER_FSYNC_RETURNED_AT_CONTROLLED_EXACT_DEADLINE' in first.stderr
    assert not (c['anchor']/'ONE-CHILD-EFFECT').exists()
    before={p.name:p.read_bytes() for p in root.iterdir()}
    second=_s305_retained_run(c,c['ordinary_env'],'A1-second-denied','ordinary')
    assert second.returncode==1 and before=={p.name:p.read_bytes() for p in root.iterdir()}
    assert original_intent==(c['anchor']/'controlled-setup-v1/activation.intent.json').read_bytes()
    record_property('application_before_teardown','NEW DURABLE RESERVATION SPENT; ORIGINAL DEADLINE/ACTIVATION UNCERTAINTY RETAINED; NO CHILD; SECOND ATTEMPT DENIED; NO OWNER REPAIR')


def test_s305_A1_chunked_exact_retained_roster(tmp_path,monkeypatch,record_property,request):
    c=_s305_activation_control(tmp_path,monkeypatch,request,files=300)
    assert len(c['state']['chunks'])==3
    assert c['state']['identities']['bytes']>65536  # Exact existing report envelope, no recanonicalization.
    assert _s305_retained_run(c,c['activation_env'],'A1-prepare-chunked').returncode==0
    result=_s305_retained_run(c,c['ordinary_env'],'A1-assess-chunked','ordinary')
    assert result.returncode==0,result.stderr
    assert (c['anchor']/'ONE-CHILD-EFFECT').read_bytes()==b'ONE'
    record_property('application_before_teardown','300 ACTUAL RETAINED FILES, THREE BOUNDED CHUNKS, EXACT PRETTY REPORT BYTES, ACTUAL FSYNC/READBACK, SINGLE RESERVED CHILD-EFFECT MARKER ONLY')


def test_s305_A1_concurrent_activation_uses_actual_exclusion(tmp_path,monkeypatch,record_property,request):
    import fcntl
    c=_s305_activation_control(tmp_path,monkeypatch,request)
    first=subprocess.Popen([*c['args'],'hold-custody'],env=c['activation_env'],stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        assert first.stderr.readline().strip()=='ACTUAL_CUSTODY_HELD'
        descriptor=os.open(c['anchor'],os.O_RDONLY|os.O_DIRECTORY)
        try:
            with pytest.raises(BlockingIOError):fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
        finally:os.close(descriptor)
        denied=_s305_retained_run(c,c['activation_env'],'A1-concurrent-denial')
        assert denied.returncode==92
        stdout,stderr=first.communicate('continue',timeout=30)
        (c['evidence']/'A1-concurrent-owner.json').write_text(json.dumps(dict(actual_exit=first.returncode,
            stdout=stdout,stderr=stderr,wait_owner='THIS POPEN ONLY',application_cleanup='NO APPLICATION STARTED',
            teardown='SEPARATE; ACTUAL OWNER ALREADY TERMINAL'),indent=2))
        assert first.returncode==0,stderr
        head=json.loads((c['anchor']/'failed-successor-restore-v1/admission-head.json').read_bytes())
        assert head['state']=='ORDINARY_ACTIVATED' and head['sequence']==2
    finally:
        if first.poll() is None:first.communicate('continue',timeout=30)
    record_property('application_before_teardown','ACTUAL HELD OFD/INDEPENDENT LOCK PROBE; CONCURRENT ACTOR DENIED; ONLY ONE NATIVE PHASE PUBLICATION')


def test_s305_A1_unresolved_verify_stays_fenced_after_custodian_death(tmp_path,monkeypatch,record_property,request):
    import fcntl,time
    c=_s305_activation_control(tmp_path,monkeypatch,request,unresolved_verify=True)
    out=(c['evidence']/'A1-unresolved-native.stdout.log').open('w')
    err=(c['evidence']/'A1-unresolved-native.stderr.log').open('w')
    command=[*c['args'],'valid'];process=subprocess.Popen(command,env=c['activation_env'],stdout=out,stderr=err,text=True)
    observed=False
    try:
        until=time.monotonic()+15
        while time.monotonic()<until:
            text=(c['evidence']/'A1-unresolved-native.stderr.log').read_text()
            if 'HELPER_OUTCOME_UNRESOLVED' in text:
                assert process.poll() is None
                descriptor=os.open(c['anchor'],os.O_RDONLY|os.O_DIRECTORY)
                try:
                    with pytest.raises(BlockingIOError):fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
                finally:os.close(descriptor)
                observed=True;break
            if process.poll() is not None:break
            time.sleep(.01)
        assert observed,(c['evidence']/'A1-unresolved-native.stderr.log').read_text()
        head=json.loads((c['anchor']/'failed-successor-restore-v1/admission-head.json').read_bytes())
        assert head['state']=='NATIVE_ACTIVATED' and head['sequence']==1
        assert (c['anchor']/'controlled-setup-v1/activation.intent.json').is_file()
        assert not (c['anchor']/'ONE-CHILD-EFFECT').exists()
        shutil.copytree(c['anchor'].parent,c['evidence']/'A1-application-before-forced-teardown',symlinks=True)
        (c['evidence']/'A1-unresolved-application.json').write_text(json.dumps(dict(command=command,
            actual_owner_pid=process.pid,owner_live=True,independent_probe='EXCLUDED',
            outcome='ACTUAL NESTED VALIDATION TIMEOUT; HELPER EXIT 79; NO PHASE COMMIT; CUSTODY RETAINED',
            application_cleanup_success=False),indent=2))
    finally:
        if process.poll() is None:process.kill()
        code=process.wait(timeout=10);out.close();err.close()
        (c['evidence']/'A1-forced-fixture-teardown.json').write_text(json.dumps(dict(
            actual_owner_exit=code,wait_owner='THIS POPEN ONLY',forced_fixture_termination=True,
            unresolved_application_outcome_preserved=True,application_cleanup_claimed=False),indent=2))
    before={str(p.relative_to(c['anchor'])):p.read_bytes() for p in c['anchor'].rglob('*') if p.is_file()}
    denied=_s305_retained_run(c,c['ordinary_env'],'A1-after-custodian-death','ordinary')
    assert denied.returncode==1 and before=={
        str(p.relative_to(c['anchor'])):p.read_bytes() for p in c['anchor'].rglob('*') if p.is_file()}
    record_property('application_before_teardown','ACTUAL TWO-LEVEL VALIDATION TIMEOUT/EXIT79; ACTUAL EXCLUSION; FORCED TEST TEARDOWN SEPARATE; PERSISTENT PARTIAL ACTIVATION DENIES FRESH INVOCATION')


def _s305_retained_run(c,env,label,fault='valid'):
    from hashlib import sha256
    evidence=c['evidence']/label;evidence.mkdir()
    args=[*c['args'],fault]
    try:
        result=subprocess.run(args,env=env,capture_output=True,text=True,timeout=30)
        (evidence/'application.json').write_text(json.dumps(dict(command=args,actual_exit=result.returncode,
            stdout=result.stdout,stderr=result.stderr,command_waited=True),indent=2))
    except BaseException as error:
        (evidence/'application-exception.json').write_text(json.dumps(dict(command=args,
            exception_type=type(error).__name__,exception=repr(error),success_claimed=False),indent=2))
        raise
    finally:
        # Capture original selected documents, authorities, source/package
        # fixture and partial artifacts while their disposable root exists.
        # Exact historical bytes cannot be recreated by a later run.
        shutil.copytree(c['anchor'].parent,evidence/'original-fixture',symlinks=True)
        members=[]
        for path in sorted(c['anchor'].rglob('*')):
            if path.is_file():
                relative=path.relative_to(c['anchor']);target=evidence/'retained-primary'/relative
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
                members.append(dict(path=str(relative),bytes=path.stat().st_size,mode=oct(path.stat().st_mode&0o777),
                    sha256=sha256(path.read_bytes()).hexdigest()))
        (evidence/'runtime-inventory.json').write_text(json.dumps(members,indent=2))
    return result


@pytest.mark.parametrize('operation',('PLACE_ENROLLMENT','PRESERVE_STALE_CONTROL'))
@pytest.mark.parametrize('fault',('valid','intent-prefix','object-zero','object-directory-error',
    'object-directory-expiry','object-directory-late','object-directory-crash','lost-acknowledgement'))
def test_s305_actual_setup_preserves_uncertainty(tmp_path,monkeypatch,record_property,operation,fault):
    from tests.unit.common import test_failed_successor_restore as fixture
    import fcntl
    c=_s305_setup_control(tmp_path,monkeypatch)
    initial=fixture._ref(c['staged'],c['installation']['identity'],c['staged'].read_bytes())
    env=_s305_setup_env(c,'PLACE_ENROLLMENT',initial)
    if operation=='PRESERVE_STALE_CONTROL':
        assert _s305_retained_run(c,env,'enrollment').returncode==0
        # Reaped disposable PID: actual ESRCH, never a fabricated process check.
        child=subprocess.Popen(['/usr/bin/true']);child.wait(timeout=5)
        path=Path(c['args'][5]);raw=('KRONOS_BROWSER_BACKEND_CONTROL_V1\n'+str(child.pid)+'\n'+'a'*64+'\n').encode()
        path.write_bytes(raw);path.chmod(0o600)
        env=_s305_setup_env(c,operation,fixture._ref(path,'selected-stale-control',raw))
    stem='enrollment' if operation=='PLACE_ENROLLMENT' else 'stale-control'
    object_name='e02-frozen-enrollment.json' if operation=='PLACE_ENROLLMENT' else 'stale-control.original'
    actual_fault=(stem+'.intent.json:prefix' if fault=='intent-prefix' else
        object_name+':'+fault.removeprefix('object-') if fault.startswith('object-') else fault)
    result=_s305_retained_run(c,env,'first',actual_fault)
    if fault=='valid':
        assert result.returncode==0,result.stderr
        assert 'PREPARATION_ONLY_PENDING_EXACT_REVIEW' in result.stdout
        if operation=='PLACE_ENROLLMENT':assert c['destination'].read_bytes()==c['staged'].read_bytes()
        else:
            assert not path.exists()
            assert (c['anchor']/'controlled-setup-v1/stale-control.original').read_bytes()==raw
    else:
        assert result.returncode in (1,97,98),result.stderr
        assert 'PREPARATION_ONLY_PENDING_EXACT_REVIEW' not in result.stdout
        if operation=='PRESERVE_STALE_CONTROL' and fault!='lost-acknowledgement':assert path.read_bytes()==raw
    original={str(p.relative_to(c['anchor'])):p.read_bytes() for p in c['anchor'].rglob('*') if p.is_file()}
    second=_s305_retained_run(c,env,'replay')
    assert second.returncode==1
    assert original=={str(p.relative_to(c['anchor'])):p.read_bytes() for p in c['anchor'].rglob('*') if p.is_file()}
    assert not (c['anchor']/'failed-successor-restore-v1').exists()
    descriptor=os.open(c['anchor'],os.O_RDONLY|os.O_DIRECTORY)
    try:fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
    finally:os.close(descriptor)
    record_property('application_before_teardown',json.dumps(dict(first_exit=result.returncode,replay_exit=second.returncode,
        no_child_or_claim=True,custody_independently_available_after_owned_process_exit=True,
        teardown='SEPARATE PYTEST DISPOSABLE ROOT CLEANUP; PRIMARY BYTES ALREADY COPIED')))


@pytest.mark.parametrize('finding',('wrong-input','wrong-order','wrong-selection','missing-order','unknown-selector',
    'existing-destination','existing-namespace','symlink-namespace','live-control-pid','premature-initialization'))
def test_s305_actual_setup_denials_precede_writes(tmp_path,monkeypatch,record_property,finding):
    from tests.unit.common import test_failed_successor_restore as fixture
    from kronos.common import legacy_bootstrap as b
    c=_s305_setup_control(tmp_path,monkeypatch)
    ref=fixture._ref(c['staged'],c['installation']['identity'],c['staged'].read_bytes())
    env=_s305_setup_env(c,'PLACE_ENROLLMENT',ref);root=c['anchor']/'controlled-setup-v1'
    if finding=='wrong-input':c['staged'].write_bytes(b'CHANGED')
    elif finding=='wrong-order':
        path=Path(env['KRONOS_SETUP_ORDER_PATH']);value=json.loads(path.read_bytes());value['installation_identity']='a'*64
        raw=fixture._put(path,value)
        from hashlib import sha256
        env['KRONOS_SETUP_ORDER_BYTES']=str(len(raw));env['KRONOS_SETUP_ORDER_SHA256']=sha256(raw).hexdigest()
    elif finding=='wrong-selection':env['KRONOS_NATIVE_SELECTION_SHA256']='f'*64
    elif finding=='missing-order':del env['KRONOS_SETUP_ORDER_ID']
    elif finding=='unknown-selector':env['KRONOS_SETUP_RETRY']='true'
    elif finding=='existing-destination':c['destination'].write_bytes(c['staged'].read_bytes());c['destination'].chmod(0o600)
    elif finding=='existing-namespace':root.mkdir(mode=0o700)
    elif finding=='symlink-namespace':root.symlink_to(c['anchor'].parent,target_is_directory=True)
    elif finding=='live-control-pid':
        path=Path(c['args'][5]);path.write_text('KRONOS_BROWSER_BACKEND_CONTROL_V1\n'+str(os.getpid())+'\n'+'a'*64+'\n');path.chmod(0o600)
    elif finding=='premature-initialization':
        root.mkdir(mode=0o700);(root/'enrollment.intent.json').write_bytes(b'{');(root/'enrollment.intent.json').chmod(0o600)
        c['destination'].write_bytes(c['staged'].read_bytes());c['destination'].chmod(0o600)
        env=c['env']
    before={str(p.relative_to(c['anchor'])):p.read_bytes() for p in c['anchor'].rglob('*') if p.is_file()}
    result=_s305_retained_run(c,env,'denial','initialize' if finding=='premature-initialization' else 'valid')
    assert result.returncode==1,result.stderr
    assert before=={str(p.relative_to(c['anchor'])):p.read_bytes() for p in c['anchor'].rglob('*') if p.is_file()}
    assert not (c['anchor']/'failed-successor-restore-v1').exists()
    record_property('application_before_teardown','ACTUAL NATIVE DENIAL; NO WRITES; OWNED COMMAND WAITED; TEARDOWN SEPARATE')


def test_s305_actual_setup_concurrency(tmp_path,monkeypatch,record_property):
    from tests.unit.common import test_failed_successor_restore as fixture
    import fcntl
    c=_s305_setup_control(tmp_path,monkeypatch)
    env=_s305_setup_env(c,'PLACE_ENROLLMENT',fixture._ref(c['staged'],c['installation']['identity'],c['staged'].read_bytes()))
    first=subprocess.Popen([*c['args'],'hold-custody'],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        assert first.stderr.readline().strip()=='ACTUAL_CUSTODY_HELD'
        descriptor=os.open(c['anchor'],os.O_RDONLY|os.O_DIRECTORY)
        try:
            with pytest.raises(BlockingIOError):fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
        finally:os.close(descriptor)
        second=_s305_retained_run(c,env,'concurrent-denial')
        assert second.returncode==92 and not (c['anchor']/'controlled-setup-v1').exists()
        stdout,stderr=first.communicate('continue',timeout=30)
        (c['evidence']/'concurrent-owner-result.json').write_text(json.dumps(dict(actual_exit=first.returncode,
            stdout=stdout,stderr=stderr,wait_owner='THIS POPEN ONLY',application_cleanup='NO PRODUCT OWNER STARTED',
            fixture_teardown='SEPARATE; ALL OWNED COMMANDS TERMINAL'),indent=2))
        assert first.returncode==0,stderr
        assert c['destination'].read_bytes()==c['staged'].read_bytes()
    finally:
        if first.poll() is None:first.communicate('continue',timeout=30)
    record_property('application_before_teardown','ACTUAL EXCLUSION; CONCURRENT WRITER DENIED; ONE WAIT OWNER; NO APPLICATION START')


def test_s305_actual_preparation_orders_initialization_without_admission(tmp_path,monkeypatch,record_property,request):
    from tests.unit.common import test_failed_successor_restore as fixture
    from kronos.common import legacy_bootstrap as b,release_admission as a
    c=_s305_setup_control(tmp_path,monkeypatch)
    request.addfinalizer(lambda:shutil.copytree(c['anchor'].parent,c['evidence']/'finalizer-primary-snapshot',symlinks=True))
    env=_s305_setup_env(c,'PLACE_ENROLLMENT',fixture._ref(c['staged'],c['installation']['identity'],c['staged'].read_bytes()))
    assert _s305_retained_run(c,env,'place-enrollment').returncode==0
    initialized=_s305_retained_run(c,c['env'],'prepare-initialization','initialize')
    assert initialized.returncode==0,initialized.stderr
    root=c['anchor']/'failed-successor-restore-v1'
    original={p.name:p.read_bytes() for p in root.iterdir()}
    binding=a.AnchorBinding(c['anchor'],c['installation']['device'],c['installation']['inode'],c['installation']['owner'])
    monkeypatch.setattr(a,'APPROVED_BINDING',binding);monkeypatch.setattr(a,'PERSISTENT_ANCHOR_BINDING',c['pinned'])
    class Checks:
        def __init__(self):self.budget=a.ValidationBudget(a.monotonic_ns()+10_000_000_000);self.binding=binding
        def check(self):self.budget.check()
    checks=Checks()
    with pytest.raises(ValueError):a.validate_installation_anchor(c['installation'],checks)
    # Separate synthetic exact-genesis decision, not writer self-admission.
    raw=fixture._s304_resolve_retained_fixture(root,c['installation'])
    unbound=raw
    from kronos.common import failed_successor_restore as restore
    monkeypatch.setattr(restore,'INITIALIZATION_DISPOSITION',raw)
    with pytest.raises(ValueError):a.validate_installation_anchor(c['installation'],checks)
    value=json.loads(raw);path=Path(value['evidence']['path']);evidence=json.loads(path.read_bytes())
    intent=c['anchor']/'controlled-setup-v1/enrollment.intent.json'
    evidence['subsequent_observations'].append(fixture._ref(intent,'setup-enrollment',intent.read_bytes()))
    evidence_raw=fixture._put(path,evidence);value['evidence']=fixture._ref(path,value['evidence']['identity'],evidence_raw)
    approved=b._canonical(value);monkeypatch.setattr(restore,'INITIALIZATION_DISPOSITION',approved)
    assert a.validate_installation_anchor(c['installation'],checks)
    restore._initialization_admission(root,c['installation'],checks=checks)
    retained=c['evidence']/'separate-synthetic-review';retained.mkdir()
    for path in root.iterdir():shutil.copy2(path,retained/path.name)
    (retained/'synthetic-genesis-disposition.json').write_bytes(approved)
    assert all((root/name).read_bytes()==raw for name,raw in original.items())
    assert set(p.name for p in root.iterdir())==set(original)|{
        's304-separate-resolution-order.json','s304-separate-resolution-evidence.json'}
    # Actual native head-reader component. It takes real anchor custody and
    # uses static disposable P/G bytes. No helper acceptance or lifecycle
    # function is substituted; no source/package/startup proof is claimed.
    def native_reader(disposition,label):
        source=(c['evidence']/'setup.c').read_text()
        source=source[:source.rfind('int main(int argc,char **argv) {')]
        source=source.replace('approved_initialization_disposition = NULL;',
            'approved_initialization_disposition = '+json.dumps(disposition.decode())+';')
        source+=r'''
int main(int argc,char **argv) {
 if(argc!=4)return 90;
 admission_anchor=argv[1];canonical_bundle=argv[2];canonical_executable=argv[0];
 struct stat st;if(stat(argv[1],&st)!=0)return 91;
 approved_admission_device=st.st_dev;approved_admission_inode=st.st_ino;
 validation_deadline_ns=validation_now_ns()+120000000000LL;
 admission_descriptor=acquire_installation_admission(argv[1],st.st_dev,st.st_ino);
 if(admission_descriptor<0)return 92;
 int accepted=native_open_journal(argv[3]);
 puts(accepted?"GENESIS_READER_ACCEPTED":"GENESIS_READER_DENIED");
 return initialization_return(accepted?0:1);
}
'''
        unit=c['evidence']/(label+'.c');binary=c['evidence']/(label+'-reader');unit.write_text(source)
        command=['clang','-Wall','-Wextra','-Werror',str(unit),'-o',str(binary)]
        compiled=subprocess.run(command,capture_output=True,text=True)
        (c['evidence']/(label+'-compile.json')).write_text(json.dumps(dict(command=command,
            actual_exit=compiled.returncode,stdout=compiled.stdout,stderr=compiled.stderr),indent=2))
        assert compiled.returncode==0,compiled.stderr
        args=[str(binary),str(c['anchor']),c['args'][3],c['installation']['identity']]
        result=subprocess.run(args,capture_output=True,text=True,timeout=10)
        (c['evidence']/(label+'-application.json')).write_text(json.dumps(dict(command=args,
            actual_exit=result.returncode,stdout=result.stdout,stderr=result.stderr,owned_command_waited=True,
            component='ACTUAL NATIVE GENESIS READER ONLY; NO STARTUP OR ARTIFACT QUALIFICATION'),indent=2))
        return result
    # Keep both separately prepared evidence documents so a failure compares
    # binding predicates rather than a mismatched evidence hash.
    old_evidence=json.loads(path.read_bytes());old_evidence['subsequent_observations']=[]
    old_path=root/'s305-unbound-resolution-evidence.json';old_raw=fixture._put(old_path,old_evidence)
    old_value=json.loads(unbound);old_value['evidence']=fixture._ref(old_path,old_value['evidence']['identity'],old_raw)
    assert native_reader(b._canonical(old_value),'unbound').returncode==1
    assert native_reader(approved,'bound').returncode==0
    intent.write_bytes(intent.read_bytes()+b' ')
    with pytest.raises(ValueError):a.validate_installation_anchor(c['installation'],checks)
    assert native_reader(approved,'tampered').returncode==1
    for path in root.iterdir():shutil.copy2(path,retained/path.name)
    shutil.copy2(intent,retained/'tampered-setup-intent.json')
    record_property('application_before_teardown','ACTUAL WRITER PREPARATION; NO SELF ADMISSION; DISTINCT SYNTHETIC G REQUIRED; DIRECT R3.1 GUARD; TAMPER DENIES')


def _s304_compile_preparer(tmp_path,monkeypatch,*,object_format='sha1',source_root=None):
    """Actual native preparation + actual read-only helper, disposable bindings.

    Signature/publication authority is synthetic. Kernel process inventory is
    scoped to the owned fixture namespace so tests never inspect production.
    No comparison, consumer, filesystem write or custody check is stubbed.
    """
    from hashlib import sha256
    from kronos.common import legacy_bootstrap as adapter
    from tests.unit.common import test_legacy_bootstrap as setup
    from tests.unit.common import test_failed_successor_restore as fixture
    control=setup._c02_dispatch_case(tmp_path,monkeypatch,object_format=object_format);case=control['case']
    anchor=case.root/'fresh-initialization-anchor';anchor.mkdir(mode=0o700)
    bundle=control['bundle'];binary=bundle/'Contents/MacOS/KRONOS'
    evidence=ROOT.parent/'qualification/s304-native-evidence'/tmp_path.parents[1].name/tmp_path.name
    evidence.mkdir(parents=True)
    prelude=r'''
#include <libproc.h>
#include <time.h>
#include <stdarg.h>
#include <unistd.h>
#include <fcntl.h>
static int s304_list(uint32_t,uint32_t,void *,int);
static int s304_openat(int,const char *,int,...);
static ssize_t s304_write(int,const void *,size_t);
static int s304_sync(int);
static int s304_close(int);
static int s304_clock(clockid_t,struct timespec *);
#define proc_listpids s304_list
#define openat s304_openat
#define write s304_write
#define fsync s304_sync
#define close s304_close
#define clock_gettime s304_clock
'''
    code_root=Path(source_root) if source_root is not None else ROOT
    source=_fixture_native_source(code_root/'tools/macos/kronos_launcher.c').replace('int main(void) {','int preserved_operational_main(void) {')
    port=json.loads(Path(os.environ['KRONOS_TEST_ISOLATION_MANIFEST']).read_text())['allowed_ports'][0]
    source=source.replace('8947',str(port))
    source=source.replace('static const dev_t approved_admission_device = 16777232;','static dev_t approved_admission_device = 0;')
    source=source.replace('static const ino_t approved_admission_inode = 694844364;','static ino_t approved_admission_inode = 0;')
    tail=r'''
#undef proc_listpids
#undef openat
#undef write
#undef fsync
#undef close
#undef clock_gettime
static const char *s304_fault="valid";
static char s304_stage[240]="root",s304_last[300]="";
static long long s304_now=0;
static int s304_fired=0;
static int s304_inventories=0;
static const char *s304_repository=NULL;
static int s304_event(const char *operation) {
    char event[300];snprintf(event,sizeof(event),"%s:%s",s304_stage,operation);
    if(s304_fired || strcmp(s304_fault,event))return 0;
    s304_fired=1;snprintf(s304_last,sizeof(s304_last),"%s",event);return 1;
}
static int s304_list(uint32_t type,uint32_t uid,void *out,int capacity) {
    (void)type;(void)uid;if(capacity<(int)sizeof(pid_t))return 0;
    s304_inventories++;
    if(s304_inventories==3 && !strcmp(s304_fault,"final-observation:expiry"))s304_now=validation_current_deadline();
    if(s304_inventories==3 && !strcmp(s304_fault,"final-observation:late"))s304_now=validation_current_deadline()+1;
    pid_t owned=getpid();memcpy(out,&owned,sizeof(owned));return sizeof(owned);
}
static int s304_openat(int dir,const char *name,int flags,...) {
    mode_t mode=0;if(flags&O_CREAT){va_list ap;va_start(ap,flags);mode=(mode_t)va_arg(ap,int);va_end(ap);}
    int fd=openat(dir,name,flags,mode);
    if(fd>=0 && (flags&O_CREAT) && strstr(name,".json")) {
        snprintf(s304_stage,sizeof(s304_stage),"%s",name);
        if(!strncmp(name,"initialization-",15) && strcmp(name,"initialization-attempt.json"))
            snprintf(s304_stage,sizeof(s304_stage),"activation-phase.json");
        if(s304_event("open-crash"))_exit(97);
    }
    return fd;
}
static ssize_t s304_write(int fd,const void *raw,size_t count) {
    struct stat st;if(fstat(fd,&st)==0 && S_ISREG(st.st_mode)) {
        if(s304_event("prefix")){size_t n=count>7?7:count;ssize_t result=write(fd,raw,n);errno=EIO;return result;}
        if(s304_fired && strstr(s304_fault,":prefix")){errno=EIO;return -1;}
        if(s304_event("zero"))return 0;
        if(s304_event("short"))return write(fd,raw,count>1?count/2:count);
        if(s304_event("eintr")){errno=EINTR;return -1;}
    }
    return write(fd,raw,count);
}
static int s304_sync(int fd) {
    struct stat st;int dir=fstat(fd,&st)==0 && S_ISDIR(st.st_mode);
    if(s304_event(dir?"directory-error":"file-error")){errno=EIO;return -1;}
    int result=fsync(fd);
    if(dir && s304_event("directory-source-change")) {
        char path[PATH_MAX];snprintf(path,sizeof(path),"%s/README.md",s304_repository);
        int changed=open(path,O_WRONLY|O_TRUNC);if(changed>=0){write(changed,"CHANGED AFTER COMMIT\n",21);close(changed);}
    }
    if(s304_event(dir?"directory-death":"file-death"))kill(getpid(),SIGKILL);
    if(s304_event(dir?"directory-crash":"file-crash"))_exit(97);
    if(s304_event(dir?"directory-expiry":"file-expiry"))s304_now=validation_current_deadline();
    if(s304_event(dir?"directory-late":"file-late"))s304_now=validation_current_deadline()+1;
    return result;
}
static int s304_close(int fd) {
    struct stat st;int regular=fstat(fd,&st)==0 && S_ISREG(st.st_mode);int result=close(fd);
    if(regular && s304_event("close-error")){errno=EIO;return -1;}
    return result;
}
static int s304_clock(clockid_t kind,struct timespec *out) {
    if(kind==CLOCK_MONOTONIC && s304_now){out->tv_sec=s304_now/1000000000;out->tv_nsec=s304_now%1000000000;return 0;}
    return clock_gettime(kind,out);
}
int main(int argc,char **argv) {
    if(argc!=7)return 90;
    admission_anchor=argv[1];canonical_bundle=argv[3];canonical_executable=argv[0];
    s304_repository=argv[2];
    struct stat st;if(stat(argv[1],&st)!=0)return 91;
    approved_admission_device=st.st_dev;approved_admission_inode=st.st_ino;
    validation_deadline_ns=validation_now_ns()+120000000000LL;
    admission_descriptor=acquire_installation_admission(argv[1],st.st_dev,st.st_ino);
    if(admission_descriptor<0){fprintf(stderr,"ACTUAL_CUSTODY_DENIED\n");return 92;}
    if(!strcmp(argv[6],"hold-custody")){char byte;fprintf(stderr,"ACTUAL_CUSTODY_HELD\n");fflush(stderr);if(read(0,&byte,1)!=1)return 93;}
    s304_fault=argv[6];int result=native_initialize(argv[2],argv[4],argv[5]);
    if(!strcmp(argv[6],"lost-acknowledgement"))_exit(98);
    fprintf(stderr,"APPLICATION_RESULT=%d ORIGINAL_DEADLINE=%lld OBSERVED=%lld UNRESOLVED_HELPER=%d FAULT=%s\n",
        result,validation_deadline_ns,validation_now_ns(),validation_cleanup_unresolved,s304_last);
    return initialization_return(result);
}
'''
    unit=evidence/'preparer.c';unit.write_text(prelude+source+tail)
    command=['clang','-Wall','-Wextra','-Werror',str(unit),'-o',str(binary)]
    compiled=subprocess.run(command,capture_output=True,text=True)
    (evidence/'compile.json').write_text(json.dumps(dict(command=command,actual_exit=compiled.returncode,
        stdout=compiled.stdout,stderr=compiled.stderr,executed_source_sha256=sha256(unit.read_bytes()).hexdigest()),indent=2))
    assert compiled.returncode==0,compiled.stderr
    binary.chmod(0o755);shutil.copy2(binary,evidence/'preparer')
    shim=case.root/'s304-helper-python'
    shim.write_text('#!'+sys.executable+'\nimport sys\nsys.path[:0]='+repr([str(code_root/'src'),str(code_root)])+'\n'+
        'from kronos.common import legacy_bootstrap as b,release_admission as a\n'+
        'from hashlib import sha256\nif a.PERSISTENT_ANCHOR_BINDING is not None: assert sha256(a.PERSISTENT_ANCHOR_BINDING).hexdigest()=="85ea2fa04da20f40377b242d71db96762020e77042a7b4923c331c6f82ab7891"\na.PERSISTENT_ANCHOR_BINDING=None\na.CANONICAL_PARENT='+repr(str(binary))+'\n'+
        'b._verify_bundle_signature=lambda *_:None\n'+
        'assert sys.argv[1:3]==["-B","-c"]\nexec(sys.argv[3],{"__name__":"__main__"})\n')
    shim.chmod(0o755);shutil.copy2(shim,evidence/'helper-python')
    installation=adapter._native_installation(str(control['repository']),str(bundle),str(anchor))
    artifact=json.loads(control['artifact_manifest'].read_bytes());rows=setup._c02_bundle_manifest(bundle)
    digest=sha256(binary.read_bytes()).hexdigest()
    artifact.update(bundle_manifest=rows,bundle_identity=sha256(adapter._canonical(rows)).hexdigest(),
        built_binary_sha256=digest,signed_binary_sha256=digest)
    control['artifact_manifest'].write_bytes(adapter._canonical(artifact)+b'\n')
    selected=json.loads(case.permit_path.read_bytes());target=dict(selected['restoration_target'],
        artifact_manifest_sha256=sha256(control['artifact_manifest'].read_bytes()).hexdigest())
    order_path=case.root/'s304-explicit-operator-order.json'
    order=fixture._ref(order_path,'s304-synthetic-order',fixture._put(order_path,{
        'label':'SYNTHETIC INITIALIZATION ONLY; NO PRODUCTION AUTHORITY'}))
    now=datetime.now(UTC)
    selection=dict(schema=adapter.NATIVE_SELECTION_SCHEMA,selection_id='s304-selection',mode='ORDINARY',
        installation=installation,target=target,source_manifest=fixture._ref(control['source_manifest'],'source',control['source_manifest'].read_bytes()),
        artifact_manifest=fixture._ref(control['artifact_manifest'],'artifact',control['artifact_manifest'].read_bytes()),
        operational_order=order,decisions={k:order for k in ('sponsor','ca','pcp','product')},permit=None,
        valid_from=(now-timedelta(seconds=30)).isoformat(),valid_until=(now+timedelta(minutes=4)).isoformat())
    selection_path=case.root/'s304-selection.json';raw=fixture._put(selection_path,selection)
    env=dict(os.environ,KRONOS_INITIALIZATION_ELIGIBILITY='COLD_ABSENT')
    for prefix,ref in [('KRONOS_INITIALIZATION_ORDER',order),('KRONOS_NATIVE_SELECTION',fixture._ref(selection_path,'s304-selection',raw))]:
        for suffix,key in [('PATH','path'),('BYTES','bytes'),('SHA256','sha256'),('ID','identity')]:env[prefix+'_'+suffix]=str(ref[key])
    case.close()  # Setup custody belongs to the separate synthetic helper root.
    args=[str(binary),str(anchor),str(control['repository']),str(bundle),str(shim),str(anchor/'browser-backend-v1.control')]
    return dict(args=args,env=env,anchor=anchor,evidence=evidence,installation=installation,case=case)


@pytest.mark.parametrize('fault', ('valid','root:directory-error','root:directory-expiry',
    *[name+':'+event for name in ('initialization-attempt.json','head-1.json','activation-phase.json','admission-head.json')
      for event in ('open-crash','prefix','zero','file-error','file-crash','close-error',
                    'directory-error','directory-crash','directory-expiry','directory-late')],
    'initialization-attempt.json:short','initialization-attempt.json:eintr',
    'admission-head.json:directory-death','lost-acknowledgement',
    'final-observation:expiry','final-observation:late','admission-head.json:directory-source-change'))
def test_s304_actual_native_prepare_crash_and_expiry(tmp_path,monkeypatch,record_property,fault):
    from hashlib import sha256
    import fcntl
    control=_s304_compile_preparer(tmp_path,monkeypatch)
    args=[*control['args'],fault]
    result=subprocess.run(args,env=control['env'],capture_output=True,text=True,timeout=30)
    evidence=control['evidence'];anchor=control['anchor'];journal=anchor/'failed-successor-restore-v1'
    (evidence/'application-result.json').write_text(json.dumps(dict(command=args,actual_exit=result.returncode,
        stdout=result.stdout,stderr=result.stderr,authority_signature_path='SYNTHETIC_DISPOSABLE_ONLY',
        process_inventory='OWNED FIXTURE NAMESPACE; NO PRODUCTION PROCESS INSPECTION'),indent=2))
    members=[]
    if journal.exists():
        for path in journal.iterdir():
            dst=evidence/'retained-primary'/path.name;dst.parent.mkdir(exist_ok=True)
            shutil.copy2(path,dst);members.append(dict(path=path.name,bytes=path.stat().st_size,
                mode=oct(path.stat().st_mode&0o777),sha256=sha256(path.read_bytes()).hexdigest()))
    (evidence/'runtime-inventory.json').write_text(json.dumps(members,indent=2))
    if fault in ('valid','initialization-attempt.json:short','initialization-attempt.json:eintr'):
        assert result.returncode==0 and 'PREPARED_PENDING_EXACT_ADMISSION_REVIEW' in result.stdout
        assert len(members)==4
        assert (journal/'admission-head.json').read_bytes()==(journal/'head-1.json').read_bytes()
    else:
        assert result.returncode in (1,97,98,-9)
        assert 'PREPARED_PENDING_EXACT_ADMISSION_REVIEW' not in result.stdout
    before={p.name:p.read_bytes() for p in journal.iterdir()} if journal.exists() else {}
    second=subprocess.run([*control['args'],'valid'],env=control['env'],capture_output=True,text=True,timeout=30)
    (evidence/'second-invocation.json').write_text(json.dumps(dict(actual_exit=second.returncode,
        stdout=second.stdout,stderr=second.stderr),indent=2))
    assert second.returncode==1 and before=={p.name:p.read_bytes() for p in journal.iterdir()}
    descriptor=os.open(anchor,os.O_RDONLY|os.O_DIRECTORY)
    fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB);os.close(descriptor)
    record_property('s304_application_before_fixture_teardown',json.dumps(dict(
        actual_exit=result.returncode,second_invocation_denied=True,permanent_artifacts_preserved=True,
        custody_released_after_process_terminal=True,fixture_teardown='AFTER PRIMARY COPY; pytest temporary directory only')))


def test_s304_actual_concurrent_initialization_and_lock_probe(tmp_path,monkeypatch,record_property):
    import fcntl
    control=_s304_compile_preparer(tmp_path,monkeypatch)
    first=subprocess.Popen([*control['args'],'hold-custody'],env=control['env'],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        assert first.stderr.readline().strip()=='ACTUAL_CUSTODY_HELD'
        descriptor=os.open(control['anchor'],os.O_RDONLY|os.O_DIRECTORY)
        try:
            with pytest.raises(BlockingIOError):fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
        finally:os.close(descriptor)
        second=subprocess.run([*control['args'],'valid'],env=control['env'],capture_output=True,text=True,timeout=30)
        assert second.returncode==92 and not (control['anchor']/'failed-successor-restore-v1').exists()
        stdout,stderr=first.communicate('continue',timeout=30)
        assert first.returncode==0 and 'PREPARED_PENDING_EXACT_ADMISSION_REVIEW' in stdout
        (control['evidence']/'concurrent-application.json').write_text(json.dumps(dict(
            first_actual_exit=first.returncode,second_actual_exit=second.returncode,
            first_stdout=stdout,first_stderr=stderr,second_stdout=second.stdout,second_stderr=second.stderr,
            independent_lock_probe='EXCLUDED_WHILE_ACTUAL_OWNER_HELD',wait_owner='PYTEST POPEN OWNER ONLY'),indent=2))
        journal=control['anchor']/'failed-successor-restore-v1'
        for path in journal.iterdir():
            dst=control['evidence']/'retained-primary'/path.name;dst.parent.mkdir(exist_ok=True);shutil.copy2(path,dst)
        record_property('s304_application_outcome','one actual preparer; concurrent admission excluded; no admission descriptor; teardown follows primary copy')
    finally:
        if first.poll() is None:first.communicate('continue',timeout=30)


@pytest.mark.parametrize('finding',('missing-order','partial-order','unknown-selector','wrong-installation',
    'wrong-selection-mode','changed-source','wrong-parent-image','existing-empty-root','symlink-root'))
def test_s304_actual_preparation_denies_before_creation(tmp_path,monkeypatch,record_property,finding):
    from hashlib import sha256
    from tests.unit.common import test_failed_successor_restore as fixture
    from kronos.common import legacy_bootstrap as adapter
    control=_s304_compile_preparer(tmp_path,monkeypatch);env=dict(control['env'])
    journal=control['anchor']/'failed-successor-restore-v1'
    if finding=='missing-order':
        for key in list(env):
            if key.startswith('KRONOS_INITIALIZATION_ORDER_'):del env[key]
    elif finding=='partial-order':del env['KRONOS_INITIALIZATION_ORDER_SHA256']
    elif finding=='unknown-selector':env['KRONOS_INITIALIZATION_ASSUME_APPROVED']='1'
    elif finding in ('wrong-installation','wrong-selection-mode'):
        path=Path(env['KRONOS_NATIVE_SELECTION_PATH']);selection=json.loads(path.read_bytes())
        if finding=='wrong-installation':
            core=dict(selection['installation']);core.pop('identity');core['inode']+=1
            selection['installation']=dict(core,identity=sha256(adapter._canonical(core)).hexdigest())
        else:selection['mode']='GOVERNED_REPLACEMENT'
        raw=fixture._put(path,selection)
        env['KRONOS_NATIVE_SELECTION_BYTES']=str(len(raw));env['KRONOS_NATIVE_SELECTION_SHA256']=sha256(raw).hexdigest()
    elif finding=='changed-source':(Path(control['args'][2])/'README.md').write_bytes(b'CHANGED SOURCE\n')
    elif finding=='wrong-parent-image':
        shim=Path(control['args'][4]);shim.write_text(shim.read_text().replace(
            'from hashlib import sha256\nif a.PERSISTENT_ANCHOR_BINDING is not None: assert sha256(a.PERSISTENT_ANCHOR_BINDING).hexdigest()=="85ea2fa04da20f40377b242d71db96762020e77042a7b4923c331c6f82ab7891"\na.PERSISTENT_ANCHOR_BINDING=None\na.CANONICAL_PARENT='+repr(control['args'][0]),'from hashlib import sha256\nif a.PERSISTENT_ANCHOR_BINDING is not None: assert sha256(a.PERSISTENT_ANCHOR_BINDING).hexdigest()=="85ea2fa04da20f40377b242d71db96762020e77042a7b4923c331c6f82ab7891"\na.PERSISTENT_ANCHOR_BINDING=None\na.CANONICAL_PARENT='+repr(control['args'][0]+'.wrong')))
    elif finding=='existing-empty-root':journal.mkdir(mode=0o700)
    elif finding=='symlink-root':
        target=control['anchor']/'retained-private-target';target.mkdir(mode=0o700)
        (target/'untouched').write_bytes(b'PRESERVE');journal.symlink_to(target,target_is_directory=True)
    result=subprocess.run([*control['args'],'valid'],env=env,capture_output=True,text=True,timeout=30)
    assert result.returncode==1 and 'PREPARED_PENDING' not in result.stdout
    if finding=='existing-empty-root':assert list(journal.iterdir())==[]
    elif finding=='symlink-root':assert journal.is_symlink() and (journal/'untouched').read_bytes()==b'PRESERVE'
    else:assert not journal.exists()
    (control['evidence']/'denial-application.json').write_text(json.dumps(dict(finding=finding,
        actual_exit=result.returncode,stdout=result.stdout,stderr=result.stderr,
        runtime_transition=False,fixture_teardown='AFTER application observations'),indent=2))
    record_property('s304_application_outcome',finding+': denied before creation; existing objects preserved; teardown separate')


def test_s304_actual_preparation_git_sha256_control(tmp_path,monkeypatch,record_property):
    control=_s304_compile_preparer(tmp_path,monkeypatch,object_format='sha256')
    result=subprocess.run([*control['args'],'valid'],env=control['env'],capture_output=True,text=True,timeout=30)
    journal=control['anchor']/'failed-successor-restore-v1'
    assert result.returncode==0,result.stderr
    attempt=json.loads((journal/'initialization-attempt.json').read_bytes())
    assert len(attempt['parent']['revision'])==64
    for path in journal.iterdir():
        dst=control['evidence']/'retained-primary'/path.name;dst.parent.mkdir(exist_ok=True);shutil.copy2(path,dst)
    (control['evidence']/'sha256-application.json').write_text(json.dumps(dict(actual_exit=result.returncode,
        stdout=result.stdout,stderr=result.stderr,git_storage='sha256',admission='PENDING'),indent=2))
    record_property('s304_git_storage','ACTUAL GIT SHA256; original budget; prepare-only, no admitted descriptor')


def test_s304_actual_unresolved_helper_retains_initialization_custody(tmp_path,monkeypatch,record_property):
    import fcntl,time
    control=_s304_compile_preparer(tmp_path,monkeypatch)
    shim=Path(control['args'][4]);script=shim.read_text()
    script=script.replace('assert sys.argv',
        'actual=b._validation_output\n'+
        'def uncertain(arguments,repository,checks,phase,**kwargs):\n'+
        ' return actual([sys.executable,"-B","-c","print(\\\"x\\\"*1000,flush=True)"],repository,checks,phase,capacity=16)\n'+
        'b._validation_output=uncertain\nassert sys.argv')
    script=script.replace('exec(sys.argv[3],{"__name__":"__main__"})',
        'try:\n exec(sys.argv[3],{"__name__":"__main__"})\nfinally:\n'+
        ' import json\n from pathlib import Path\n waits=[]\n'+
        ' for child in a._OWNED_VALIDATION_HELPERS.values():waits.append(dict(pid=child.pid,actual_exit=child.wait(timeout=3)))\n'+
        ' Path('+repr(str(control['evidence']/'inner-helper-fixture-teardown.json'))+').write_text(json.dumps(dict(waits=waits,unresolved_state_preserved=a.validation_unresolved(),application_cleanup_claimed=False)))')
    shim.write_text(script);shutil.copy2(shim,control['evidence']/'unresolved-helper-python')
    out=(control['evidence']/'unresolved-native.stdout.log').open('w')
    err=(control['evidence']/'unresolved-native.stderr.log').open('w')
    process=subprocess.Popen([*control['args'],'valid'],env=control['env'],stdout=out,stderr=err,text=True)
    observed=False
    try:
        until=time.monotonic()+15
        while time.monotonic()<until:
            text=(control['evidence']/'unresolved-native.stderr.log').read_text()
            if 'HELPER_OUTCOME_UNRESOLVED' in text:
                assert process.poll() is None
                descriptor=os.open(control['anchor'],os.O_RDONLY|os.O_DIRECTORY)
                try:
                    with pytest.raises(BlockingIOError):fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
                finally:os.close(descriptor)
                observed=True;break
            if process.poll() is not None:break
            time.sleep(.01)
        assert observed,(control['evidence']/'unresolved-native.stderr.log').read_text()
        assert not (control['anchor']/'failed-successor-restore-v1').exists()
        (control['evidence']/'unresolved-application-before-teardown.json').write_text(json.dumps(dict(
            parent_still_live=True,actual_exclusion='INDEPENDENT LOCK PROBE BLOCKED',
            disposition='ACTUAL NESTED OUTPUT UNCERTAINTY; NO ADMISSION',application_cleanup=False),indent=2))
        record_property('s304_application_outcome','actual nested uncertainty; actual native parent retains custody; no renewed deadline; test termination separate')
    finally:
        if process.poll() is None:process.terminate()
        code=process.wait(timeout=10);out.close();err.close()
        (control['evidence']/'unresolved-fixture-teardown.json').write_text(json.dumps(dict(
            native_actual_exit=code,termination='SEPARATE FORCED FIXTURE TEARDOWN',
            application_cleanup_claimed=False,observed_primary_exclusion=observed),indent=2))


@pytest.mark.parametrize('finding',('valid','no-policy','different-python-policy','changed-genesis',
    'grafted-lineage','missing-evidence','current-durability-failure'))
def test_s304_actual_native_python_static_admission(tmp_path,monkeypatch,record_property,finding):
    from hashlib import sha256
    from tests.unit.common import test_failed_successor_restore as fixture
    from tests.unit.common import test_legacy_bootstrap as setup
    from kronos.common import legacy_bootstrap as adapter
    control=_s304_compile_preparer(tmp_path,monkeypatch)
    # The actual initializer leaves complete bytes at its exact original expiry.
    completed=subprocess.run([*control['args'],'admission-head.json:directory-expiry'],
        env=control['env'],capture_output=True,text=True,timeout=30)
    assert completed.returncode==1
    root=control['anchor']/'failed-successor-restore-v1'
    original={p.name:p.read_bytes() for p in root.iterdir()}
    policy=fixture._s304_resolve_retained_fixture(root,control['installation'])
    from types import SimpleNamespace
    from kronos.common import release_admission as admission
    installation=control['installation'];anchor=control['anchor']
    enrollment=anchor.parent/'e02-frozen-enrollment.json';enrollment_raw=fixture._put(enrollment,installation)
    descriptor=os.open(anchor,os.O_RDONLY|os.O_DIRECTORY)
    try:observed=admission.descriptor_filesystem_identity(descriptor)
    finally:os.close(descriptor)
    persistent=dict(schema='KRONOS_PERSISTENT_ANCHOR_BINDING_V1',installation_identity=installation['identity'],
        enrollment=fixture._ref(enrollment,installation['identity'],enrollment_raw),anchor_path=str(anchor),
        volume_uuid=observed['volume_uuid'],file_id=observed['file_id'],owner=os.getuid(),required_mode='0700',
        bundle_id=installation['bundle_id'],bundle_path=installation['bundle_path'],repository_path=installation['repository_path'])
    ordinary=dict(schema='ORDINARY_SAME_RELEASE_V1',scope='ORDINARY_SAME_RELEASE_WITH_QUALIFIED_STOP',
        installation_identity=installation['identity'],binding_sha256=sha256(adapter._canonical(persistent)).hexdigest(),
        genesis_disposition_sha256=sha256(policy).hexdigest(),release_id='E02-SEPARATELY-ADMITTED-SYNTHETIC-CONTROL',
        installed_selection_path=str(anchor/'ordinary-start-v1/installed-selection.json'))
    e02_control=SimpleNamespace(anchor=anchor,journal=root,installation=installation,persistent=persistent,
        policy=ordinary,now=datetime.now(UTC),process=json.loads(Path(json.loads(policy)['genesis_phase']['path']).read_bytes())['parent'])
    python_policy=policy
    if finding=='different-python-policy':
        value=json.loads(policy);value['identity']='a-different-separate-disposition'
        python_policy=adapter._canonical(value)
    source=_fixture_native_source(SOURCE).replace('int main(void) {','int preserved_operational_main(void) {')
    source=source.replace('static const dev_t approved_admission_device = 16777232;','static dev_t approved_admission_device = 0;')
    source=source.replace('static const ino_t approved_admission_inode = 694844364;','static ino_t approved_admission_inode = 0;')
    if finding!='no-policy':
        source=source.replace('approved_initialization_disposition = NULL;',
            'approved_initialization_disposition = '+json.dumps(policy.decode())+';')
    source=source.replace('approved_persistent_binding = NULL;',
        'approved_persistent_binding = '+json.dumps(adapter._canonical(persistent).decode())+';')
    source=source.replace('approved_ordinary_restart_policy = NULL;',
        'approved_ordinary_restart_policy = '+json.dumps(adapter._canonical(ordinary).decode())+';')
    if finding=='current-durability-failure':
        source='#include <unistd.h>\n#include <errno.h>\nstatic int denied_sync(int fd){(void)fd;errno=EIO;return -1;}\n#define fsync denied_sync\n'+source
    source+=r'''
int main(int argc,char **argv) {
    if(argc!=5)return 90;struct stat st;if(stat(argv[1],&st)!=0)return 91;
    admission_anchor=argv[1];approved_admission_device=st.st_dev;approved_admission_inode=st.st_ino;
    canonical_bundle=argv[3];canonical_executable=argv[0];
    validation_deadline_ns=validation_now_ns()+120000000000LL;
    admission_descriptor=acquire_installation_admission(argv[1],st.st_dev,st.st_ino);
    if(admission_descriptor<0)return 92;
    int allowed=native_gate(argv[2],argv[4],"ORDINARY") && native_original_reserve(0);
    fprintf(stderr,"ADMISSION_ALLOWED=%d UNRESOLVED_HELPER=%d\n",allowed,validation_cleanup_unresolved);
    if(validation_owned_child()>0 || validation_cleanup_unresolved)return 79;
    if(native_journal.root>=0)close(native_journal.root);close(admission_descriptor);
    return allowed?0:1;
}
'''
    evidence=control['evidence'];unit=evidence/'separately-pinned-reader.c';unit.write_text(source)
    binary=Path(control['args'][0]);command=['clang','-Wall','-Wextra','-Werror',str(unit),'-o',str(binary)]
    compiled=subprocess.run(command,capture_output=True,text=True)
    (evidence/'pinned-compile.json').write_text(json.dumps(dict(command=command,actual_exit=compiled.returncode,
        stdout=compiled.stdout,stderr=compiled.stderr,executed_source_sha256=sha256(unit.read_bytes()).hexdigest()),indent=2))
    assert compiled.returncode==0,compiled.stderr
    binary.chmod(0o755);shutil.copy2(binary,evidence/'separately-pinned-reader')
    shim=Path(control['args'][4]);script=shim.read_text()
    script=script.replace('assert sys.argv',
        'from kronos.common import failed_successor_restore as r\nr.INITIALIZATION_DISPOSITION='+repr(python_policy)+'\nassert sys.argv')
    script=script.replace('assert sys.argv',
        'from pathlib import Path\na.PERSISTENT_ANCHOR_BINDING='+repr(adapter._canonical(persistent))+'\n'+
        'a.APPROVED_BINDING=a.AnchorBinding(Path('+repr(str(anchor))+'),'+str(installation['device'])+','+str(installation['inode'])+','+str(installation['owner'])+')\n'+
        'b.ORDINARY_RESTART_POLICY='+repr(adapter._canonical(ordinary))+'\nassert sys.argv')
    shim.write_text(script);shutil.copy2(shim,evidence/'separately-pinned-helper-python')
    # Preserve the initial artifact/selection documents; create separate current
    # package/selection bindings for the separately compiled disposable reader.
    selection_path=Path(control['env']['KRONOS_NATIVE_SELECTION_PATH'])
    selection=json.loads(selection_path.read_bytes());old_artifact=Path(selection['artifact_manifest']['path'])
    artifact=json.loads(old_artifact.read_bytes());bundle=Path(control['args'][3])
    rows=setup._c02_bundle_manifest(bundle);digest=sha256(binary.read_bytes()).hexdigest()
    artifact.update(bundle_manifest=rows,bundle_identity=sha256(adapter._canonical(rows)).hexdigest(),
        built_binary_sha256=digest,signed_binary_sha256=digest)
    new_artifact=old_artifact.with_name('s304-current-artifact.json')
    new_artifact.write_bytes(adapter._canonical(artifact)+b'\n');new_artifact.chmod(0o600)
    selection['artifact_manifest']=fixture._ref(new_artifact,'current-artifact',new_artifact.read_bytes())
    selection['target']['artifact_manifest_sha256']=sha256(new_artifact.read_bytes()).hexdigest()
    selection['selection_id']='s304-current-selection'
    new_selection=selection_path.with_name('s304-current-selection.json');raw=fixture._put(new_selection,selection)
    env=dict(control['env'])
    for suffix,key in [('PATH','path'),('BYTES','bytes'),('SHA256','sha256'),('ID','identity')]:
        env['KRONOS_NATIVE_SELECTION_'+suffix]=str(fixture._ref(new_selection,selection['selection_id'],raw)[key])
    e02_control.selection=selection
    setup._e02_publish_control_activation(e02_control)
    env={k:v for k,v in env.items() if not k.startswith('KRONOS_NATIVE_SELECTION_')}
    if finding=='changed-genesis':
        item=json.loads((root/'head-1.json').read_bytes());item['recorded_at']='2026-10-25T00:00:00+00:00'
        fixture._put(root/'head-1.json',item);fixture._put(root/'admission-head.json',item)
    elif finding=='grafted-lineage':
        item=json.loads((root/'head-1.json').read_bytes());item.update(sequence=2,previous_head_sha256='f'*64)
        fixture._put(root/'head-2.json',item);fixture._put(root/'admission-head.json',item)
    elif finding=='missing-evidence':(root/'s304-separate-resolution-evidence.json').unlink()
    run=subprocess.run([str(binary),*control['args'][1:4],str(shim)],env=env,capture_output=True,text=True,timeout=30)
    (evidence/'separate-admission-application.json').write_text(json.dumps(dict(
        initializer_actual_exit=completed.returncode,initializer_stdout=completed.stdout,initializer_stderr=completed.stderr,
        admitted_actual_exit=run.returncode,stdout=run.stdout,stderr=run.stderr,
        original_policy_outcome=json.loads(policy)['original_outcome'],
        authority_signature_path='SYNTHETIC TEST-ONLY SOURCE-PINNED DISPOSITIONS'),indent=2))
    assert run.returncode==(0 if finding=='valid' else 1),run.stderr
    assert (root/'initialization-attempt.json').read_bytes()==original['initialization-attempt.json']
    assert json.loads(policy)['original_outcome']=='UNPROVED_OR_LATE_UNRESOLVED'
    if finding=='valid':assert json.loads((root/'admission-head.json').read_bytes())['state']=='ORIGINAL_RESERVED'
    for path in root.iterdir():
        dst=evidence/'retained-primary'/path.name;dst.parent.mkdir(exist_ok=True);shutil.copy2(path,dst)
    record_property('s304_application_before_fixture_teardown',json.dumps(dict(
        original_exit=completed.returncode,admission_exit=run.returncode,
        original_unresolved_outcome_preserved=True,fixture_teardown='AFTER native exits and primary copies')))


@pytest.mark.parametrize('mode,state',[
    ('ORDINARY','NATIVE_ACTIVATED'),('LEGACY_BOOTSTRAP','NATIVE_ACTIVATED'),
    ('GOVERNED_REPLACEMENT','NATIVE_ACTIVATED'),
    ('FAILED_ACTIVE_RECOVERY_REPLACEMENT','NATIVE_ACTIVATED'),
    *[(mode,'UNRESOLVED') for mode in ('ORDINARY','LEGACY_BOOTSTRAP','GOVERNED_REPLACEMENT',
        'FAILED_ACTIVE_RECOVERY_REPLACEMENT','FAILED_SUCCESSOR_RESTORATION')],
    ('ORDINARY','RESTORATION_RESERVED'),('ORDINARY','CHILD_START_RESERVED'),
    ('ORDINARY','FORK_UNCERTAINTY')])
def test_r33_actual_native_readonly_gate_and_original_reservation(tmp_path,monkeypatch,record_property,mode,state):
    """Actual C -> bounded helper -> Git/artifact checks -> durable C writer.

    This component has no application child and establishes no native R READY.
    """
    from hashlib import sha256
    from kronos.common import legacy_bootstrap as adapter
    from tests.unit.common import test_legacy_bootstrap as setup
    from tests.unit.common import test_failed_successor_restore as fixture
    control=setup._c02_dispatch_case(tmp_path,monkeypatch);case=control['case']
    repository,bundle=control['repository'],control['bundle']
    anchor=case.custody.binding.path;metadata=anchor.stat();binary=bundle/'Contents/MacOS/KRONOS'
    evidence=ROOT.parent/'qualification/r33-native-gate-evidence'/tmp_path.parents[1].name/tmp_path.name
    evidence.mkdir(parents=True)
    source=_fixture_native_source(SOURCE).replace('int main(void) {','int unused_application_main(void) {')
    source=source.replace('static const dev_t approved_admission_device = 16777232;','static dev_t approved_admission_device = 0;')
    source=source.replace('static const ino_t approved_admission_inode = 694844364;','static ino_t approved_admission_inode = 0;')
    source='#include <unistd.h>\nstatic pid_t r33_fixture_fork(void);\n#define fork r33_fixture_fork\n'+source
    source+=r'''
#undef fork
static int r33_fail_fork=0;
static pid_t r33_fixture_fork(void) {
 if(r33_fail_fork && !strcmp(native_journal.state,"CHILD_START_RESERVED")){errno=EAGAIN;return -1;}
 return fork();
}
int main(int argc,char **argv) {
 if(argc!=8)return 90;
 struct stat st;if(stat(argv[1],&st)!=0)return 91;
 admission_anchor=argv[1];approved_admission_device=st.st_dev;approved_admission_inode=st.st_ino;
 canonical_bundle=argv[3];canonical_executable=argv[0];
 admission_descriptor=acquire_installation_admission(argv[1],st.st_dev,st.st_ino);
 if(admission_descriptor<0){puts("CUSTODY_DENIED");return 0;}
 validation_deadline_ns=validation_now_ns()+120000000000LL;
 if(!native_gate(argv[2],argv[4],argv[5])){puts("HEAD_DENIED_BEFORE_EFFECT");close(admission_descriptor);return 0;}
 if(!native_original_reserve(0))return 94;
 if(atoi(argv[7])) {
  r33_fail_fork=1;char pythonpath[PATH_MAX*2],entry[PATH_MAX];
  snprintf(pythonpath,sizeof(pythonpath),"%s/src:%s",argv[2],argv[2]);
  snprintf(entry,sizeof(entry),"%s/tools/kronos_browser.py",argv[2]);
  BackendStartResult result=start_backend(argv[2],argv[4],entry,pythonpath,0,"","","");
  if(result!=BACKEND_START_INTERNAL_FAILURE || admission_child!=0 ||
     strcmp(native_journal.state,"CHILD_START_RESERVED"))return 95;
  puts("FORK_UNCERTAINTY_ALLOWANCE_RETAINED");close(native_journal.root);close(admission_descriptor);return 0;
 }
 if(!native_advance("CHILD_START_RESERVED","{}")) {
  puts("RESERVATION_DENIED_BEFORE_EFFECT");close(admission_descriptor);return 0;
 }
 int effect=open(argv[6],O_WRONLY|O_CREAT|O_EXCL,0600);
 if(effect<0)return 92;if(write(effect,"NATIVE_DURABLE_BEFORE_EFFECT",28)!=28)return 93;close(effect);
 puts("RESERVED_BEFORE_EFFECT");close(native_journal.root);close(admission_descriptor);return 0;
}
'''
    unit=evidence/'native-gate.c';unit.write_text(source)
    command=['clang','-Wall','-Wextra','-Werror',str(unit),'-o',str(binary)]
    compiled=subprocess.run(command,capture_output=True,text=True)
    (evidence/'clang.stdout.log').write_text(compiled.stdout);(evidence/'clang.stderr.log').write_text(compiled.stderr)
    assert compiled.returncode==0,compiled.stderr
    binary.chmod(0o755)
    shutil.copy2(binary,evidence/'native-gate')
    shim=tmp_path/'helper-python'
    shim.write_text('#!'+sys.executable+'\n'+
        'import sys\n'+
        'sys.path[:0]='+repr([str(ROOT/'src'),str(ROOT)])+'\n'+
        'from kronos.common import legacy_bootstrap as b,release_admission as a\n'+
        'from hashlib import sha256\nif a.PERSISTENT_ANCHOR_BINDING is not None: assert sha256(a.PERSISTENT_ANCHOR_BINDING).hexdigest()=="85ea2fa04da20f40377b242d71db96762020e77042a7b4923c331c6f82ab7891"\na.PERSISTENT_ANCHOR_BINDING=None\na.CANONICAL_PARENT='+repr(str(binary))+'\n'+
        'b._verify_bundle_signature=lambda *_:None\n'+
        'assert sys.argv[1:3]==["-B","-c"]\n'+
        'exec(sys.argv[3],{"__name__":"__main__"})\n')
    shim.chmod(0o755);shutil.copy2(shim,evidence/'helper-python')
    artifact=json.loads(control['artifact_manifest'].read_bytes())
    rows=setup._c02_bundle_manifest(bundle);digest=sha256(binary.read_bytes()).hexdigest()
    artifact.update(bundle_manifest=rows,bundle_identity=sha256(adapter._canonical(rows)).hexdigest(),
        built_binary_sha256=digest,signed_binary_sha256=digest)
    control['artifact_manifest'].write_bytes(adapter._canonical(artifact)+b'\n')
    now=datetime.now(UTC)
    def ref(path,identity):return fixture._ref(path,identity,path.read_bytes())
    decisions={}
    for label in ('sponsor','ca','pcp','product'):
        path=case.root/(label+'-component-fixture.txt');path.write_bytes(('SYNTHETIC AUTHORITY: '+label).encode());path.chmod(0o600)
        decisions[label]=ref(path,label+'-component-fixture')
    permit=json.loads(case.permit_path.read_bytes());target=dict(permit['restoration_target'],
        artifact_manifest_sha256=sha256(control['artifact_manifest'].read_bytes()).hexdigest())
    selection=dict(schema=adapter.NATIVE_SELECTION_SCHEMA,selection_id='native-component-selection',mode=mode,
        installation=permit['installation'],target=target,
        source_manifest=ref(control['source_manifest'],'component-source'),
        artifact_manifest=ref(control['artifact_manifest'],'component-artifact'),
        decisions=decisions,operational_order=decisions['sponsor'],permit=None,
        valid_from=(now-timedelta(seconds=30)).isoformat(),valid_until=(now+timedelta(minutes=4)).isoformat())
    selected=case.root/'native-component-selection.json';fixture._put(selected,selection)
    parent=json.loads(case.reservation_path.read_bytes())['parent']
    initial_state='NATIVE_ACTIVATED' if state=='FORK_UNCERTAINTY' else state
    record=adapter._native_phase('activation-component',initial_state,original='activation-component',
        installation=permit['installation'],parent=parent,selected=None,predecessor=None,
        previous=None,details={},now=now)
    record_path=case.head_path.parent/'activation-component.json';raw=fixture._put(record_path,record)
    head=json.loads(case.head_path.read_bytes());head.update(sequence=1,state=initial_state,incident_id=None,
        active_reservation_id=record['identity'],active_reservation_sha256=sha256(raw).hexdigest(),
        previous_head_sha256='0'*64,recorded_at=now.isoformat())
    fixture._put(case.head_path,head);fixture._put(case.head_path.parent/'head-1.json',head)
    e02_control=None
    if initial_state=='NATIVE_ACTIVATED':
        # Replace only unexecuted synthetic setup, retaining its old head bytes.
        old=case.head_path.parent/'head-2.json'
        if old.exists():old.rename(case.root/'s304-unexecuted-setup-head-2.json')
        policy=fixture._s304_admit_fixture(case.head_path.parent,permit['installation'])
        if mode=='ORDINARY':
            from types import SimpleNamespace
            from kronos.common import release_admission as admission
            installation=permit['installation']
            enrollment=case.root/'e02-enrollment.json';raw=fixture._put(enrollment,installation)
            observed=admission.descriptor_filesystem_identity(case.custody.descriptor)
            persistent=dict(schema='KRONOS_PERSISTENT_ANCHOR_BINDING_V1',installation_identity=installation['identity'],
                enrollment=ref(enrollment,installation['identity']),anchor_path=str(anchor),
                volume_uuid=observed['volume_uuid'],file_id=observed['file_id'],owner=os.getuid(),required_mode='0700',
                bundle_id=installation['bundle_id'],bundle_path=str(bundle),repository_path=str(repository))
            ordinary=dict(schema='ORDINARY_SAME_RELEASE_V1',scope='ORDINARY_SAME_RELEASE_WITH_QUALIFIED_STOP',
                installation_identity=installation['identity'],binding_sha256=sha256(adapter._canonical(persistent)).hexdigest(),
                genesis_disposition_sha256=sha256(policy).hexdigest(),release_id='E02-SYNTHETIC-EXISTING-CONTROL',
                installed_selection_path=str(anchor/'ordinary-start-v1/installed-selection.json'))
            e02_control=SimpleNamespace(anchor=anchor,journal=case.head_path.parent,installation=installation,
                now=now,process=parent,persistent=persistent,policy=ordinary,selection=selection)
        shutil.copy2(unit,evidence/'unexecuted-prepin-native-gate.c')
        shutil.copy2(binary,evidence/'unexecuted-prepin-native-gate')
        pinned_source=source.replace('approved_initialization_disposition = NULL;',
            'approved_initialization_disposition = '+json.dumps(policy.decode())+';')
        if e02_control is not None:
            pinned_source=pinned_source.replace('approved_persistent_binding = NULL;',
                'approved_persistent_binding = '+json.dumps(adapter._canonical(e02_control.persistent).decode())+';')
            pinned_source=pinned_source.replace('approved_ordinary_restart_policy = NULL;',
                'approved_ordinary_restart_policy = '+json.dumps(adapter._canonical(e02_control.policy).decode())+';')
        unit.write_text(pinned_source)
        pinned=subprocess.run(['clang','-Wall','-Wextra','-Werror',str(unit),'-o',str(binary)],capture_output=True,text=True)
        (evidence/'separate-pin-compile.json').write_text(json.dumps(dict(actual_exit=pinned.returncode,
            stdout=pinned.stdout,stderr=pinned.stderr,command=['clang','-Wall','-Wextra','-Werror',str(unit),'-o',str(binary)]),indent=2))
        assert pinned.returncode==0,pinned.stderr
        binary.chmod(0o755);shutil.copy2(binary,evidence/'native-gate-final')
        script=shim.read_text().replace('assert sys.argv',
            'from kronos.common import failed_successor_restore as r\nr.INITIALIZATION_DISPOSITION='+repr(policy)+'\nassert sys.argv')
        shim.write_text(script);shutil.copy2(shim,evidence/'helper-python-final')
        rows=setup._c02_bundle_manifest(bundle);digest=sha256(binary.read_bytes()).hexdigest()
        artifact.update(bundle_manifest=rows,bundle_identity=sha256(adapter._canonical(rows)).hexdigest(),
            built_binary_sha256=digest,signed_binary_sha256=digest)
        control['artifact_manifest'].write_bytes(adapter._canonical(artifact)+b'\n')
        selection['artifact_manifest']=ref(control['artifact_manifest'],'component-artifact')
        selection['target']['artifact_manifest_sha256']=selection['artifact_manifest']['sha256']
        fixture._put(selected,selection)
        if e02_control is not None:
            setup._e02_publish_control_activation(e02_control)
            script=shim.read_text().replace('assert sys.argv',
                'from pathlib import Path\na.PERSISTENT_ANCHOR_BINDING='+repr(adapter._canonical(e02_control.persistent))+'\n'+
                'a.APPROVED_BINDING=a.AnchorBinding(Path('+repr(str(anchor))+'),'+str(metadata.st_dev)+','+str(metadata.st_ino)+','+str(os.getuid())+')\n'+
                'b.ORDINARY_RESTART_POLICY='+repr(adapter._canonical(e02_control.policy))+'\nassert sys.argv')
            shim.write_text(script);shutil.copy2(shim,evidence/'helper-python-final')
    before={p.name:p.read_bytes() for p in case.head_path.parent.iterdir()}
    case.close()  # Fixture teardown of setup reference, BEFORE native custody.
    env=dict(os.environ,KRONOS_NATIVE_SELECTION_PATH=str(selected),
        KRONOS_NATIVE_SELECTION_BYTES=str(selected.stat().st_size),
        KRONOS_NATIVE_SELECTION_SHA256=sha256(selected.read_bytes()).hexdigest(),
        KRONOS_NATIVE_SELECTION_ID=selection['selection_id'])
    if e02_control is not None:
        env={k:v for k,v in env.items() if not k.startswith('KRONOS_NATIVE_SELECTION_')}
    effect=tmp_path/'effect'
    command=[str(binary),str(anchor),str(repository),str(bundle),str(shim),mode,str(effect),str(int(state=='FORK_UNCERTAINTY'))]
    result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=100)
    (evidence/'stdout.log').write_text(result.stdout);(evidence/'stderr.log').write_text(result.stderr)
    after={p.name:p.read_bytes() for p in case.head_path.parent.iterdir()}
    for label,values in [('before',before),('after',after)]:
        for name,raw in values.items():
            directory=evidence/label;directory.mkdir(exist_ok=True);(directory/name).write_bytes(raw)
    (evidence/'command-result.json').write_text(json.dumps(dict(command=command,actual_exit=result.returncode,
        compile_actual_exit=compiled.returncode,source_sha256=sha256(SOURCE.read_bytes()).hexdigest(),
        compiled_unit_sha256=sha256(unit.read_bytes()).hexdigest(),binary_sha256=digest,
        test_teardown='Setup reference closed before native acquisition; native component closes after result. No application cleanup claim.',
        seams='DISPOSABLE_BINDING; ACTUAL_KERNEL_PARENT_IMAGE_AT_DISPOSABLE_BUNDLE; SIGNATURE_AND_BUILD_PUBLICATION_FIXTURE; ACTUAL_COMPARISONS_AND_READONLY_HELPER; NO_APPLICATION_CHILD'),indent=2)+'\n')
    assert result.returncode==0,result.stderr
    if initial_state=='NATIVE_ACTIVATED':
        if state=='FORK_UNCERTAINTY':
            assert result.stdout=='FORK_UNCERTAINTY_ALLOWANCE_RETAINED\n' and not effect.exists(),result.stderr
        else:
            assert result.stdout=='RESERVED_BEFORE_EFFECT\n',result.stderr
            assert effect.read_bytes()==b'NATIVE_DURABLE_BEFORE_EFFECT\x00'[:28]
        final=json.loads(case.head_path.read_bytes());assert final['state']=='CHILD_START_RESERVED' and final['sequence']==(4 if e02_control is not None else 3)
        again=subprocess.run(command,env=env,capture_output=True,text=True,timeout=100)
        (evidence/'repeat-result.json').write_text(json.dumps(dict(actual_exit=again.returncode,stdout=again.stdout,stderr=again.stderr),indent=2)+'\n')
        assert again.returncode==0 and again.stdout=='HEAD_DENIED_BEFORE_EFFECT\n'
        assert case.head_path.read_bytes()==after['admission-head.json']
    else:
        assert result.stdout=='HEAD_DENIED_BEFORE_EFFECT\n' and not effect.exists(),result.stderr
        assert before==after
    record_property('native_comparison_and_writer','ACTUAL_C_AND_HELPER; NO_CONSUMER_STUB_OR_HEAD_WRITER_HELPER')


@pytest.fixture(scope='module')
def r33_journal_probe(tmp_path_factory):
    """Actual journal/files/flock; only binding and syscall fault are fixtures."""
    root=tmp_path_factory.mktemp('r33-journal-binary')
    source=_fixture_native_source(SOURCE).replace('int main(void) {','int unused_application_main(void) {')
    source=source.replace('static const dev_t approved_admission_device = 16777232;',
                          'static dev_t approved_admission_device = 0;')
    source=source.replace('static const ino_t approved_admission_inode = 694844364;',
                          'static ino_t approved_admission_inode = 0;')
    source='#include <unistd.h>\nstatic int r33_fault_fsync(int);\n#define fsync r33_fault_fsync\n'+source
    source+=r'''
#undef fsync
static int fault_at=0,sync_calls=0;
static int r33_fault_fsync(int fd) {
    struct stat intent;
    if(native_journal.root>=0 && fstatat(native_journal.root,"head-2.json",&intent,AT_SYMLINK_NOFOLLOW)!=0)
        return fsync(fd); /* Additional admission proof syncs precede transition intent. */
    sync_calls++;if(fault_at && sync_calls==fault_at){errno=EIO;return -1;}
    return fsync(fd);
}
int main(int argc,char **argv) {
    if(argc!=5)return 90;
    struct stat st;if(stat(argv[1],&st)!=0)return 91;
    admission_anchor=argv[1];approved_admission_device=st.st_dev;approved_admission_inode=st.st_ino;
    admission_descriptor=acquire_installation_admission(argv[1],st.st_dev,st.st_ino);
    if(admission_descriptor<0)return 92;
    validation_deadline_ns=validation_now_ns()+10000000000LL;
    int opened=native_open_journal(argv[2]);
    if(!opened){puts("DENIED_BEFORE_EFFECT");close(admission_descriptor);return 0;}
    fault_at=atoi(argv[3]);
    const char *id="original-r33-component-attempt";
    char record[1024];
    snprintf(record,sizeof(record),"{\"identity\":\"%s\",\"installation_identity\":\"%s\",\"phase\":\"ORIGINAL_RESERVED\",\"schema\":\"%s\"}",id,argv[2],NATIVE_PHASE_SCHEMA);
    int committed=native_commit("ORIGINAL_RESERVED",id,"incident-r33-component",record);
    if(committed) {
        int effect=open(argv[4],O_WRONLY|O_CREAT|O_EXCL,0600);
        if(effect<0)return 93;
        if(write(effect,"EFFECT_AFTER_DURABLE_READBACK",29)!=29 || fsync(effect)!=0)return 94;
        close(effect);puts("COMMITTED_THEN_EFFECT");
    } else puts("DENIED_BEFORE_EFFECT");
    close(native_journal.root);close(admission_descriptor);return 0;
}
'''
    binary=root/'journal-probe';unit=root/'r33-journal.c';unit.write_text(source)
    command=['clang','-Wall','-Wextra','-Werror',str(unit),'-o',str(binary)]
    result=subprocess.run(command,capture_output=True)
    evidence=ROOT.parent/'qualification/r33-native-build-evidence'/root.parents[1].name/root.name
    evidence.mkdir(parents=True)
    shutil.copy2(unit,evidence/unit.name)
    (evidence/'clang.stdout.log').write_bytes(result.stdout)
    (evidence/'clang.stderr.log').write_bytes(result.stderr)
    from hashlib import sha256
    (evidence/'command-result.json').write_text(json.dumps(dict(command=command,
        actual_exit=result.returncode,production_source_sha256=sha256(SOURCE.read_bytes()).hexdigest(),
        compiled_unit_sha256=sha256(unit.read_bytes()).hexdigest(),
        binary_sha256=sha256(binary.read_bytes()).hexdigest() if binary.exists() else None,
        seams='DISPOSABLE_BINDING_AND_FSYNCS; ACTUAL_NATIVE_JOURNAL_CODE'),indent=2)+'\n')
    if binary.exists():shutil.copy2(binary,evidence/binary.name)
    assert result.returncode==0,result.stderr.decode()
    return binary


def _r33_initial_journal(tmp_path):
    from hashlib import sha256
    from tests.unit.common import test_failed_successor_restore as fixture
    anchor=tmp_path/'anchor';anchor.mkdir(mode=0o700)
    root=anchor/'failed-successor-restore-v1';root.mkdir(mode=0o700)
    encode=lambda value:json.dumps(value,sort_keys=True,separators=(',',':')).encode()
    st=anchor.stat()
    core=dict(anchor_path=str(anchor),device=st.st_dev,inode=st.st_ino,owner=os.getuid(),
        bundle_id='com.project-kronos.browser-v1',bundle_path='/Applications/KRONOS.app',
        repository_path=str(tmp_path/'synthetic-repository'))
    installation=sha256(encode(core)).hexdigest()
    record=dict(schema='KRONOS_NATIVE_ADMISSION_PHASE_V1',identity='activation-fixture',
                installation_identity=installation,phase='NATIVE_ACTIVATED')
    raw=encode(record)
    head=dict(schema='KRONOS_RESTORATION_ADMISSION_HEAD_V1',
        installation_identity=installation,sequence=1,state='NATIVE_ACTIVATED',incident_id=None,
        active_reservation_id=record['identity'],active_reservation_sha256=sha256(raw).hexdigest(),
        previous_head_sha256='0'*64,recorded_at='2026-10-27T00:00:00.000000+00:00')
    for name,payload in [('activation-fixture.json',raw),('admission-head.json',encode(head)),
                         ('head-1.json',encode(head))]:
        path=root/name;path.write_bytes(payload);path.chmod(0o600)
    fixture._s304_admit_fixture(root,dict(identity=installation,**core))
    return anchor,root,installation


@pytest.mark.parametrize('fault',('valid','missing-head','wrong-record-hash','bad-mode',
                                'unselected-next-intent','symlink-head',1,2,3,4,5,6))
def test_r33_native_journal_durable_before_effect(r33_journal_probe,tmp_path,record_property,fault):
    from hashlib import sha256
    anchor,root,installation=_r33_initial_journal(tmp_path)
    policy=(root/'s304-fixture-disposition.json').read_bytes()
    original=(r33_journal_probe.parent/'r33-journal.c').read_text()
    source=original.replace('approved_initialization_disposition = NULL;',
        'approved_initialization_disposition = '+json.dumps(policy.decode())+';')
    unit=tmp_path/'s304-admitted-journal.c';unit.write_text(source)
    result=subprocess.run(['clang','-Wall','-Wextra','-Werror',str(unit),'-o',str(r33_journal_probe)],capture_output=True,text=True)
    pinned_evidence=ROOT.parent/'qualification/s304-journal-builds'/tmp_path.parents[1].name/tmp_path.name
    pinned_evidence.mkdir(parents=True)
    shutil.copy2(unit,pinned_evidence/unit.name)
    (pinned_evidence/'compile-result.json').write_text(json.dumps(dict(
        command=['clang','-Wall','-Wextra','-Werror',str(unit),'-o',str(r33_journal_probe)],
        actual_exit=result.returncode,stdout=result.stdout,stderr=result.stderr),indent=2))
    if result.returncode==0:shutil.copy2(r33_journal_probe,pinned_evidence/'admitted-journal')
    assert result.returncode==0,result.stderr
    before={p.name:p.read_bytes() for p in root.iterdir()}
    if fault=='missing-head':(root/'admission-head.json').unlink()
    elif fault=='wrong-record-hash':(root/'activation-fixture.json').write_bytes(b'{}')
    elif fault=='bad-mode':(root/'admission-head.json').chmod(0o644)
    elif fault=='unselected-next-intent':
        p=root/'head-2.json';p.write_bytes(b'partial');p.chmod(0o600)
    elif fault=='symlink-head':
        (root/'admission-head.json').unlink();(root/'admission-head.json').symlink_to(root/'head-1.json')
    effect=tmp_path/'effect'
    result=subprocess.run([str(r33_journal_probe),str(anchor),installation,
        str(fault if isinstance(fault,int) else 0),str(effect)],capture_output=True,text=True,timeout=15)
    evidence=ROOT.parent/'qualification/r33-journal-evidence'/tmp_path.parents[1].name/tmp_path.name
    evidence.mkdir(parents=True)
    (evidence/'stdout.log').write_text(result.stdout);(evidence/'stderr.log').write_text(result.stderr)
    for path in root.iterdir():
        if path.is_file() and not path.is_symlink():(evidence/path.name).write_bytes(path.read_bytes())
    (evidence/'outcome.json').write_text(json.dumps(dict(fault=fault,actual_exit=result.returncode,
        effect_created=effect.exists(),application_cleanup_claimed=False,
        seam='DISPOSABLE_INITIALIZED_HEAD_AND_BINDING; REAL_NATIVE_PUBLICATION_AND_READBACK; FSYNC_FAILURE_INJECTION'),indent=2)+'\n')
    assert result.returncode==0,result.stderr
    assert effect.exists()==(fault=='valid')
    assert (root/'head-1.json').read_bytes()==before['head-1.json']
    if fault=='valid':
        assert (root/'admission-head.json').read_bytes()==(root/'head-2.json').read_bytes()
        head=json.loads((root/'admission-head.json').read_bytes())
        assert head['previous_head_sha256']==sha256(before['admission-head.json']).hexdigest()
        assert head['state']=='ORIGINAL_RESERVED'
    elif isinstance(fault,int):
        assert (root/'head-2.json').exists()  # Spent/blocked intent is never removed.
        assert (root/'admission-head.json').read_bytes()==before['admission-head.json']
        repeated=subprocess.run([str(r33_journal_probe),str(anchor),installation,'0',str(effect)],
            capture_output=True,text=True,timeout=15)
        (evidence/'repeat-result.json').write_text(json.dumps(dict(actual_exit=repeated.returncode,
            stdout=repeated.stdout,stderr=repeated.stderr),indent=2)+'\n')
        assert repeated.returncode==0 and repeated.stdout.strip()=='DENIED_BEFORE_EFFECT'
        assert not effect.exists()
    record_property('fault',str(fault));record_property('actual_exit',result.returncode)
    record_property('effect_created',effect.exists())

from kronos.common.maintenance import publish_drain_handoff

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'tools/macos/kronos_launcher.c'


def compile_source(source, destination):
    unit = destination.parent / 'unit.c'
    unit.write_text(source)
    result = subprocess.run(['clang', '-Wall', '-Wextra', '-Werror', str(unit), '-o', str(destination)],
                   capture_output=True)
    assert result.returncode == 0, result.stderr.decode()
    unit.unlink()


def compile_start_monitor_harness(tmp_path):
    source = _fixture_native_source(SOURCE).replace(
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
    fake_clock_values[3] = third;
    fake_clock_count = 4;
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
    if (strcmp(argv[1], "late-ready") == 0) {
        set_fake_clock(0,119,121);fake_ready_on_call=1;
        result=monitor_backend_start(4242,120,&monitor);
        return result==BACKEND_START_READY_TIMEOUT?0:6;
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
    source = _fixture_native_source(SOURCE).replace(
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
    source = _fixture_native_source(SOURCE).replace(
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
    source = _fixture_native_source(SOURCE).replace(
        'int main(void) {',
        'int unused_application_main(void) {',
    )
    source += r'''
int main(int argc, char **argv) {
    if (argc != 3) return 90;
    struct stat st;if(stat(argv[2],&st)!=0)return 94;
    int descriptor = acquire_installation_admission(argv[2],st.st_dev,st.st_ino);
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
    source = _fixture_native_source(SOURCE).replace(
        'int main(void) {',
        'int unused_application_main(void) {',
    )
    source += '\nint main(void) { puts(workspace_script); return 0; }\n'
    binary = tmp_path / 'workspace-script'
    compile_source(source, binary)
    return binary


def compile_v2_handoff_probe(tmp_path):
    source = _fixture_native_source(SOURCE).replace('int main(void) {',
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
    source = _fixture_native_source(SOURCE).replace('int main(void) {',
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
    source = _fixture_native_source(SOURCE).replace('htons(8947)', f'htons({port})').replace(
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


def fixture_start_custody(source):
    source = source.replace('static const dev_t approved_admission_device = 16777232;',
                            'static dev_t approved_admission_device = 0;')
    source = source.replace('static const ino_t approved_admission_inode = 694844364;',
                            'static ino_t approved_admission_inode = 0;')
    return source + r'''
static int fixture_start_custody(void) {
    static char path[PATH_MAX];
    const char *tmp=getenv("TMPDIR");if(!tmp)return 0;
    char resolved[PATH_MAX];if(!realpath(tmp,resolved))return 0;
    if(snprintf(path,sizeof(path),"%s/slice22-anchor-XXXXXX",resolved)>=(int)sizeof(path) || !mkdtemp(path))return 0;
    struct stat st;if(stat(path,&st)!=0)return 0;
    admission_anchor=path;approved_admission_device=st.st_dev;approved_admission_inode=st.st_ino;
    admission_descriptor=acquire_installation_admission(path,st.st_dev,st.st_ino);
    return admission_descriptor>=0;
}
'''


def compile_isolated_cold_start_probe(tmp_path, port):
    source = _fixture_native_source(SOURCE).replace('htons(8947)', f'htons({port})').replace(
        'int main(void) {', 'int unused_application_main(void) {')
    source = fixture_start_custody(source)
    source += r'''
int main(int argc, char **argv) {
    if (argc != 5 || !cold_start_has_no_control_or_live_handoff(argv[4])) return 90;
    if(!fixture_start_custody())return 94;
    return start_backend(argv[1], argv[2], argv[3], argv[1], 0, "", "", "")
        == BACKEND_START_READY ? 0 : 91;
}
'''
    binary = tmp_path / 'isolated-cold-start-probe'
    compile_source(source, binary)
    return binary


def compile_isolated_successor_probe(tmp_path, port):
    source = _fixture_native_source(SOURCE).replace('htons(8947)', f'htons({port})').replace(
        'int main(void) {', 'int unused_application_main(void) {')
    source = fixture_start_custody(source)
    source += r'''
int main(int argc, char **argv) {
    if (argc != 8) return 90;
    if(!fixture_start_custody())return 94;
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
    source = _fixture_native_source(SOURCE).replace('htons(8947)', f'htons({port})').replace(
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
    source = _fixture_native_source(SOURCE).replace('htons(8947)', f'htons({port})').replace(
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
    source = _fixture_native_source(SOURCE).replace('"/Applications/KRONOS.app"', json.dumps(str(app)))
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
    compile_source(_fixture_native_source(SOURCE), exe)
    assert result(exe, env=environment) == 1


def test_build_probe_exits_without_operational_authority(tmp_path):
    exe = tmp_path / 'launcher'
    compile_source(_fixture_native_source(SOURCE), exe)
    p = subprocess.run([str(exe)], env={'KRONOS_LAUNCH_MODE': 'PACKAGE_VERIFY'},
                       capture_output=True, timeout=5)
    assert p.returncode == 0 and p.stdout == b'KRONOS_LAUNCHER_PACKAGE_V1_OK\n'


@pytest.mark.parametrize('scenario', [
    'delayed-ready',
    'child-exited',
    'ready-timeout',
    'interrupted-wall-jump',
    'internal-failure', 'late-ready',
])
def test_start_monitor_has_typed_bounded_results(tmp_path, scenario):
    binary = compile_start_monitor_harness(tmp_path)
    subprocess.run([str(binary), scenario], check=True, capture_output=True, timeout=5)


def _assert_exclusive_original_and_restoration_dispatch(main):
    restoration,ordinary=main.split('    pid_t backend_pid = 0;',1)
    assert restoration.count('start_backend(')==ordinary.count('start_backend(')==1
    branch=restoration.split('    if(restoration) {',1)[1]
    assert 'switch(outcome)' in branch
    assert branch.rstrip().endswith('return show_replacement_internal_failure();\n    }')
    for outcome in ('READY','CHILD_EXITED','READY_TIMEOUT','INTERNAL_FAILURE'):
        assert 'case BACKEND_START_'+outcome+':' in branch
    assert ordinary.count('request_graceful_shutdown(')==1


def test_start_contract_uses_monotonic_120_second_deadline_and_exact_alerts():
    source = _fixture_native_source(SOURCE)
    assert '#define BACKEND_START_READY_TIMEOUT_SECONDS 120' in source
    assert 'clock_gettime(CLOCK_MONOTONIC, value)' in source
    monotonic = source.split('static long long validation_now_ns(void) {',1)[1].split('static int validation_permitted',1)[0]
    assert 'CLOCK_REALTIME' not in monotonic
    assert 'clock_gettime(CLOCK_MONOTONIC' in monotonic
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
    source = _fixture_native_source(SOURCE)
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
    source = _fixture_native_source(SOURCE)
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
    source = _fixture_native_source(SOURCE)
    main = source.split('int main(void) {', 1)[1]
    assert 'strcmp(mode, "GOVERNED_REPLACEMENT") == 0' in main
    assert 'KRONOS_REPLACEMENT_REVISION' in main
    assert (
        'if (!bootstrap && !replacement && !recovery && !restoration && native_reuse(control_path)) '
        'return open_workspace();'
    ) in main
    readiness = main.index('backend_replacement_readiness(')
    shutdown = main.index('request_graceful_shutdown(backend_pid, token, generation, replacement || recovery)')
    start = main.index('BackendStartResult start_result = start_backend(')
    assert readiness < shutdown < start
    assert main.count('request_graceful_shutdown(') == 1
    _assert_exclusive_original_and_restoration_dispatch(main)


def test_revision_replacement_requires_exact_clean_published_target():
    source = _fixture_native_source(SOURCE)
    main = source.split('int main(void) {', 1)[1]
    qualification = main.index('qualify_source(repository, python)')
    target = main.index('repository_revision_matches(repository, target_revision)')
    lock = main.index('acquire_launcher_lock(repository)')
    readiness = main.index('backend_replacement_readiness(')
    assert lock < qualification < target < readiness
    assert 'valid_revision(target_revision)' in main
    assert 'char *arguments[]={"git","rev-parse","HEAD",NULL}' in source
    assert 'bounded_validation_cli(repository,"/usr/bin/git"' in source
    child = source.split('static BackendStartResult start_backend(', 1)[1].split(
        'int main(void) {', 1
    )[0]
    assert 'unsetenv("KRONOS_LAUNCH_MODE")' in child
    assert 'unsetenv("KRONOS_REPLACEMENT_REVISION")' in child
    assert child.index('unsetenv("KRONOS_REPLACEMENT_REVISION")') < child.index(
        'execl(python, python, "-B", browser_entry, "--no-browser"'
    )


def test_fixed_maintenance_refusal_preserves_shared_gate_and_transition_order():
    source = _fixture_native_source(SOURCE)
    main = source.split('int main(void) {', 1)[1]
    assert 'clean published maintenance/release-b-swing-ux revision' in main
    assert 'clean published develop revision' not in main
    assert main.index('qualify_source(repository, python)') < main.index('request_graceful_shutdown(')
    assert main.index('request_graceful_shutdown(') < main.index('BackendStartResult start_result = start_backend(')
    assert 'char *arguments[]={(char*)python,"-B",gate,NULL}' in source
    assert '"SOURCE_GATE",60' in source
    backend = (ROOT / 'tools/kronos_browser.py').read_text()
    backend_main = backend[backend.index('def main('):]
    assert 'from tools.runtime_source_gate import qualify_startup' in backend_main
    assert backend_main.index('qualify_startup(') < backend_main.index('consume_startup_context(')


@pytest.mark.parametrize('helper_exit', [0, 1])
def test_native_source_helper_result_prevents_fixture_transition_on_denial(tmp_path, helper_exit):
    # Only the existing source-wrapper function runs. Operational main is renamed;
    # the disposable helper never imports KRONOS, invokes Git or starts a backend.
    repository = tmp_path / 'repository'; (repository / 'tools').mkdir(parents=True)
    (repository / 'tools/runtime_source_gate.py').write_text(f'raise SystemExit({helper_exit})\n')
    marker = tmp_path / 'fixture-transition'
    source = _fixture_native_source(SOURCE).replace('int main(void) {', 'int unused_application_main(void) {')
    source += r'''
int main(int argc, char **argv) {
    if (argc != 4) return 90;
    if (!qualify_source(argv[1], argv[2])) { puts("DENIED"); return 23; }
    FILE *marker = fopen(argv[3], "w");
    if (!marker) return 91;
    fputs("fixture only", marker); fclose(marker); return 0;
}
'''
    binary = tmp_path / 'source-refusal-fixture'
    compile_source(source, binary)
    result = subprocess.run([str(binary), str(repository), sys.executable, str(marker)],
                            capture_output=True, timeout=20)
    assert result.returncode == (0 if helper_exit == 0 else 23)
    assert marker.exists() is (helper_exit == 0)
    if helper_exit:
        assert result.stdout == b'DENIED\n'


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
    source = _fixture_native_source(SOURCE)
    main = source.split('int main(void) {', 1)[1]
    shutdown_call = main.index('request_graceful_shutdown(backend_pid, token, generation, replacement || recovery)')
    stop_wait = main.index('wait_for_backend_stop(backend_pid)')
    start_call = main.index('BackendStartResult start_result = start_backend(')
    assert shutdown_call < stop_wait < start_call
    assert main.index('return show_restart_blocked();') < start_call
    token_clear = main.index('(void)memset(token, 0, sizeof(token));', start_call)
    result_switch = main.index('switch (start_result)', start_call)
    assert start_call < token_clear < result_switch
    _assert_exclusive_original_and_restoration_dispatch(main)
    assert main.count('open_workspace()') == 4
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
import socket,os
os.dup2(os.open(os.devnull,os.O_WRONLY),2)
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
    source = _fixture_native_source(SOURCE)
    main = source.split('int main(void) {', 1)[1]
    assert main.index('readiness == REPLACEMENT_REQUIRED_OLD_CF55') < main.index(
        'request_graceful_shutdown(backend_pid, token, generation, replacement || recovery)')
    assert main.index('wait_for_backend_stop(backend_pid)') < main.index(
        'verify_v2_handoff(repository, python, python_path,') < main.index(
        'BackendStartResult start_result = start_backend(')
    assert 'BACKEND_START_READY_TIMEOUT_SECONDS 120' in source
    _assert_exclusive_original_and_restoration_dispatch(main)


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
os.dup2(os.open(os.devnull,os.O_WRONLY),2)
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
    source = _fixture_native_source(SOURCE)
    main = source.split('int main(void) {', 1)[1]
    qualification = main.index('qualify_source(repository, python)')
    lock = main.index('acquire_launcher_lock(repository)')
    reuse = main.index(
        'if (!bootstrap && !replacement && !recovery && !restoration && native_reuse(control_path)) '
        'return open_workspace();'
    )
    listener = main.index('int socket_connected = connect_backend();')
    start = main.index('BackendStartResult start_result = start_backend(')
    assert lock < qualification < reuse < listener < start
    assert (
        'if (!bootstrap && !replacement && !recovery) return show_existing_backend_unhealthy();'
        in main
    )
    _assert_exclusive_original_and_restoration_dispatch(main)
    reusable = source.split('static int backend_is_reusable(', 1)[1].split(
        'static int backend_supports_maintenance(', 1
    )[0]
    assert 'backend_is_ready()' in reusable
    assert 'read_control_record(control_path' in reusable
    assert 'kill(backend_pid, 0) == 0' in reusable


def test_workspace_focuses_existing_kronos_tab_and_refreshes_only_canonical_stale_tab(
    tmp_path,
) -> None:
    source = _fixture_native_source(SOURCE)
    workspace = source.split('static int open_workspace(void) {', 1)[1].split(
        'static int show_alert(', 1
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
    # The approved replacement contract denies contention immediately; it never
    # waits for another launcher. The installation anchor is independent of repo.
    binary = compile_launcher_lock_harness(tmp_path)
    anchor = tmp_path / 'installation-anchor'
    anchor.mkdir(mode=0o700)
    before = tuple(anchor.iterdir())
    holder = subprocess.Popen([str(binary), 'hold', str(anchor)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout is not None and holder.stdout.readline() == 'LOCKED\n'
        denied = subprocess.run([str(binary), 'acquire', str(anchor)],
            capture_output=True, text=True, timeout=2)
        assert denied.returncode == 91
        assert denied.stdout == ''
        assert holder.stdin is not None
        holder.stdin.write('x');holder.stdin.flush();holder.stdin.close()
        assert holder.wait(timeout=5) == 0
        admitted = subprocess.run([str(binary), 'acquire', str(anchor)],
            capture_output=True, text=True, timeout=2)
        assert admitted.returncode == 0
        assert admitted.stdout == 'LOCKED\n'
        assert tuple(anchor.iterdir()) == before
    finally:
        if holder.poll() is None:
            if holder.stdin and not holder.stdin.closed:holder.stdin.close()
            holder.wait(timeout=5)


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
    source = _fixture_native_source(SOURCE).replace('int main(void) {', 'int unused_application_main(void) {')
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
    source = _fixture_native_source(SOURCE).replace('int main(void) {', 'int unused_application_main(void) {')
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
    source = _fixture_native_source(SOURCE).replace('int main(void) {', 'int unused_application_main(void) {')
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
    source=_fixture_native_source(SOURCE).replace('int main(void) {','int unused_application_main(void) {')
    source+='\nint main(void) {'
    for path in (rollback,installed,alias):
        source+='printf("%d ",recovery_separate_bundle('+json.dumps(str(path))+','+json.dumps(str(installed))+'));'
    source+='return 0;}'
    executable=tmp_path/'rollback-probe';compile_source(source,executable)
    assert subprocess.check_output([str(executable)],text=True).strip()=='1 0 0'


@pytest.fixture(scope="module")
def recovery_documents_probe(tmp_path_factory):
    root = tmp_path_factory.mktemp("recovery-documents")
    source = _fixture_native_source(SOURCE).replace('int main(void) {', 'int unused_application_main(void) {')
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
    source = _fixture_native_source(SOURCE).replace('int main(void) {', 'int unused_application_main(void) {')
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
    source = _fixture_native_source(SOURCE).replace('int main(void) {', 'int unused_application_main(void) {')
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
    source = _fixture_native_source(SOURCE).replace('int main(void) {', 'int unused_application_main(void) {')
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
    source = _fixture_native_source(SOURCE).replace('int main(void) {', 'int unused_application_main(void) {')
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
    original = _fixture_native_source(SOURCE)
    source = original.replace('int main(void) {', 'int unused_application_main(void) {')
    source += r'''
static const char *fault;
static int history_mode=0,incident_mode=0;
static int calls_assess=0,calls_continuity=0,calls_binding=0,calls_verify=0,calls_package=0;
static int shutdowns=0,starts=0,reservations=0;
static int step(const char *name,int result) {printf("%s\n",name);return fault&&strcmp(fault,name)==0?0:result;}
static int fake_control(pid_t *pid,char *token) {*pid=history_mode?18089:12985;memset(token,'d',64);token[64]=0;return step("control",1);}
static int fake_authority(RecoveryAuthorization *a) {
    memset(a,0,sizeof(*a));a->historical=history_mode;a->swing_incident=incident_mode;a->pid=history_mode?18089:12985;
    strcpy(a->predecessor,history_mode?RECOVERY_HISTORY_PREDECESSOR:RECOVERY_PREDECESSOR);
    memset(a->package,'b',64);memset(a->rollback_identity,'c',64);strcpy(a->rollback,"/disposable/rollback.app");
    /* Independent fixture identities: never derive the expected filename from the production selector. */
    const char *legacy="4f6aac6c3a9f59fe2e19b788fb6266fec1a239358e71f2abc9f9c9ac4c0731ef";
    const char *historical="1a9a7b8b997447716f1b6f11b02fbcccf88fda2644b4a2af23604dbf5f293976";
    int selected=strcmp(fault,"relation_swapped")==0?!history_mode:history_mode;
    snprintf(a->relation,sizeof(a->relation),"%s/Library/Application Support/KRONOS/evidence/intraday-v1/live-shadow-v1/epochs-v1/WO06H-SUCCESSOR_COMPATIBILITY-%s.json",getenv("HOME"),selected?historical:legacy);
    if(!strcmp(fault,"relation_elsewhere"))strcpy(a->relation,"/disposable/other/relation.json");
    if(!strcmp(fault,"relation_suffix"))strcat(a->relation,".other");
    if(!strcmp(fault,"relation_parent"))snprintf(a->relation,sizeof(a->relation),"%s/Library/Application Support/KRONOS/evidence/intraday-v1/live-shadow-v1/epochs-v1/../epochs-v1/WO06H-SUCCESSOR_COMPATIBILITY-%s.json",getenv("HOME"),selected?historical:legacy);
    a->valid_from=history_mode?RECOVERY_END_US:RECOVERY_START_US;
    a->valid_until=history_mode?RECOVERY_END_US+RECOVERY_HISTORY_MAX_VALIDITY_US:RECOVERY_END_US;
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
#define admission_still_bound() 1
#define finish_admission() ((void)0)
/* Historical main wiring only: native predicates have separate actual C tests. */
#define native_gate(repository,python,mode) step("native_gate",1)
#define native_original_reserve(pid) (native_startup.active=1,step("native_reserve",1))
#define native_dispatch_intent(control,generation) step("native_dispatch",1)
#define native_retired(home,generation) step("native_retired",1)
#define recovery_control_record(path,pid,token) fake_control(pid,token)
#define recovery_load_authorization(root,attempt,control,pid,target,now,a) fake_authority(a)
#define recovery_package_identity(repository,python,bundle,out) fake_package(out)
#define recovery_assess(a,repository,python) fake_assess()
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
#define recovery_now_us() (history_mode?RECOVERY_END_US+1:RECOVERY_START_US+1)
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
    if(argc!=3)return 2;fault=argv[1];history_mode=strcmp(argv[2],"v1")!=0;incident_mode=!strcmp(argv[2],"v3");
    setenv("KRONOS_LAUNCH_MODE",RECOVERY_CLASS,1);
    setenv("KRONOS_RECOVERY_ATTEMPT","aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",1);
    setenv("KRONOS_REPLACEMENT_REVISION","bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",1);
    int result=exercise_main();printf("COUNTS %d %d %d %d\n",result,reservations,shutdowns,starts);return 0;
}
'''
    executable = root / "probe"; compile_source(source, executable)
    return executable


@pytest.mark.parametrize("version", ["v1", "v2"])
@pytest.mark.parametrize("fault", ["none", "native_gate", "native_reserve", "native_dispatch", "native_retired", "canonical", "source", "target", "control",
    "relation_swapped", "relation_elsewhere", "relation_suffix", "relation_parent",
    "authorization", "installed", "rollback", "assess_initial", "continuity_before",
    "assess_final", "bindings_before", "reserve", "shutdown", "exit", "handoff_initial", "continuity_after",
    "bindings_after", "attempt_readback", "handoff_final", "listener_absent", "child_exit", "timeout", "internal"])
def test_actual_recovery_main_orders_one_use_drain_and_one_successor(recovery_orchestration_probe, fault, version):
    lines = subprocess.check_output([str(recovery_orchestration_probe), fault, version], text=True).splitlines()
    result, reservations, shutdowns, starts = map(int, lines[-1].split()[1:])
    assert starts <= 1 and shutdowns <= 1 and reservations <= 1
    if fault == "none":
        assert (result, reservations, shutdowns, starts) == (0, 1, 1, 1)
        assert lines.index("native_gate") < lines.index("continuity_before")
        assert lines.index("continuity_before") < lines.index("native_reserve") < lines.index("native_dispatch") < lines.index("reserve") < lines.index("shutdown") < lines.index("exit")
        assert lines.index("handoff_initial") < lines.index("native_retired") < lines.index("continuity_after")
        assert lines.index("exit") < lines.index("handoff_initial") < lines.index("continuity_after") < lines.index("attempt_readback")
        assert lines.index("handoff_final") < lines.index("listener_absent") < lines.index("start") < lines.index("open")
    else:
        assert result == 1 and "open" not in lines
        assert starts == (1 if fault in ("child_exit", "timeout", "internal") else 0)
        if fault in ("canonical", "source", "target", "control", "relation_swapped", "relation_elsewhere", "relation_suffix", "relation_parent"):
            assert reservations == shutdowns == starts == 0
            assert "installed" not in lines
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
    source = _fixture_native_source(SOURCE).replace('int main(void) {', 'int unused_application_main(void) {')
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
    source = _fixture_native_source(SOURCE)
    reviewed = re.search(r'#define RECOVERY_REVIEW_ARTIFACT_SHA256 "([0-9a-f]{64})"', source).group(1)
    persisted = re.search(r'#define RECOVERY_RELATION "([0-9a-f]{64})"', source).group(1)
    assert reviewed == "e5d63954815ffa526390e1d5d0e668a8c490371ead305c85a14b43d6c300c58e"
    assert persisted == "707ca654076df91af1935d082a569d8d8c0335f52a08d63a8047ea1a94e4e48b"
    assert reviewed != persisted
    # Provenance is explicit, but never an alternate byte authorization.
    assert source.count("RECOVERY_REVIEW_ARTIFACT_SHA256") == 1
    assert 'recovery_field(&j,0,"compatibility_relation_sha256",recovery_relation(a))' in source
    assert 'strcmp(actual,recovery_relation(a))' in source


@pytest.fixture(scope='module')
def iwo07r3_authorization_probe(tmp_path_factory):
    import hashlib
    root=tmp_path_factory.mktemp('iwo07r3-auth').resolve()
    installed=root/'installed.app';installed.mkdir()
    diagnosis=root/'forensic.zip';diagnosis.write_bytes(b'disposable forensic')
    digest=hashlib.sha256(diagnosis.read_bytes()).hexdigest()
    source=_fixture_native_source(SOURCE).replace('int main(void) {','int unused_application_main(void) {')
    source=source.replace('static const char *canonical_bundle = "/Applications/KRONOS.app";',
        'static const char *canonical_bundle = '+json.dumps(str(installed))+';')
    import re
    source=re.sub(r'#define RECOVERY_SWING_DIAGNOSIS "[^"]+"', '#define RECOVERY_SWING_DIAGNOSIS "'+digest+'"', source)
    source+=r'''
int main(int argc,char **argv) {
    if(argc!=5)return 2;RecoveryAuthorization a;
    int admitted=recovery_load_authorization(argv[1],argv[2],argv[3],RECOVERY_SWING_PID,argv[4],RECOVERY_SWING_START_US+10000000,&a);
    if(admitted){char generation[65]={0};memset(generation,'f',64);
        printf("%d %d %d\n",admitted,recovery_reserve(&a,generation,RECOVERY_SWING_START_US+10000000),
               recovery_reserve(&a,generation,RECOVERY_SWING_START_US+10000000));
    }else printf("0\n");return 0;
}
'''
    # Reservation calls must be sequenced; C argument evaluation order is unspecified.
    source=source.replace('printf("%d %d %d\\n",admitted,recovery_reserve(&a,generation,RECOVERY_SWING_START_US+10000000),\n               recovery_reserve(&a,generation,RECOVERY_SWING_START_US+10000000));',
        'int first=recovery_reserve(&a,generation,RECOVERY_SWING_START_US+10000000);int replay=recovery_reserve(&a,generation,RECOVERY_SWING_START_US+10000000);printf("%d %d %d\\n",admitted,first,replay);')
    binary=root/'probe';compile_source(source,binary)
    return binary,installed,diagnosis,digest


@pytest.mark.parametrize('fault',[None,'pid','start','generation','revision','failure_schema','old_bundle','rollback','control','stage_a','diagnosis','sponsor','unknown','expired','too_long','duplicate'])
def test_iwo07r3_actual_c_admission_and_one_use(iwo07r3_authorization_probe,tmp_path,fault):
    import hashlib
    from tools import failed_active_successor as h
    binary,installed,diagnosis,diagnosis_hash=iwo07r3_authorization_probe
    root=tmp_path.resolve();root.chmod(0o700)
    control=root/'control';control.write_text('disposable private control');control.chmod(0o600)
    sponsor=root/'sponsor';sponsor.write_text('disposable');receipt=root/'receipt';receipt.write_text('{}');receipt.chmod(0o600)
    rollback=root/'rollback.app';rollback.mkdir()
    a=dict(schema=h.INCIDENT_SCHEMA,state='SPONSOR_APPROVED',recovery_class='FAILED_ACTIVE_RECOVERY_REPLACEMENT',attempt_identity='a'*64,
        sponsor_authorization_reference='DISPOSABLE',sponsor_authorization_path=str(sponsor),sponsor_authorization_sha256=hashlib.sha256(sponsor.read_bytes()).hexdigest(),
        predecessor_revision=h.INCIDENT_REVISION,predecessor_pid=h.INCIDENT_PID,predecessor_start_us=h.INCIDENT_START_US,
        predecessor_maintenance_identity=h.INCIDENT_GENERATION,private_control_sha256=hashlib.sha256(control.read_bytes()).hexdigest(),
        predecessor_package_identity=h.INCIDENT_PACKAGE,successor_revision='b'*40,installed_package_identity='b'*64,
        rollback_bundle=str(rollback),rollback_package_identity=h.INCIDENT_PACKAGE,diagnosis_path=str(diagnosis),diagnosis_sha256=diagnosis_hash,
        stage_a_receipt_path=str(receipt),stage_a_receipt_sha256=hashlib.sha256(receipt.read_bytes()).hexdigest(),valid_from_us=h.INCIDENT_START_US+1,valid_until_us=h.INCIDENT_START_US+20000000)
    changes=dict(pid=('predecessor_pid',1),start=('predecessor_start_us',1),generation=('predecessor_maintenance_identity','0'*64),
        revision=('predecessor_revision','0'*40),failure_schema=('schema','OTHER'),old_bundle=('installed_package_identity',h.INCIDENT_PACKAGE),
        rollback=('rollback_bundle',str(installed)),control=('private_control_sha256','0'*64),stage_a=('stage_a_receipt_sha256','0'*64),
        diagnosis=('diagnosis_sha256','0'*64),sponsor=('sponsor_authorization_sha256','0'*64),unknown=('extra',True),
        expired=('valid_until_us',h.INCIDENT_START_US+10000000),too_long=('valid_until_us',h.INCIDENT_START_US+1800000002))
    if fault in changes: k,v=changes[fault];a[k]=v
    raw=json.dumps(a)
    if fault=='duplicate': raw=raw[:-1]+',"state":"SPONSOR_APPROVED"}'
    path=root/('a'*64+'.authorization.json');path.write_text(raw);path.chmod(0o600)
    result=subprocess.check_output([str(binary),str(root),'a'*64,str(control),'b'*40],text=True).strip()
    assert result==('1 1 0' if fault is None else '0')


@pytest.fixture(scope='module')
def iwo07r3_documents_probe(tmp_path_factory):
    root=tmp_path_factory.mktemp('iwo07r3-documents')
    source=_fixture_native_source(SOURCE).replace('int main(void) {','int unused_application_main(void) {')
    source+=r'''
int main(int argc,char **argv) {
    if(argc!=4)return 2;char r[BACKEND_STATUS_RESPONSE_BYTES],s[BACKEND_STATUS_RESPONSE_BYTES],d[BACKEND_STATUS_RESPONSE_BYTES];
    if(!recovery_read_file(argv[1],r,sizeof(r),0)||!recovery_read_file(argv[2],s,sizeof(s),0)||!recovery_read_file(argv[3],d,sizeof(d),0))return 2;
    RecoveryAuthorization a={0};a.swing_incident=1;a.pid=RECOVERY_SWING_PID;
    strcpy(a.predecessor,RECOVERY_SWING_PREDECESSOR);strcpy(a.maintenance,RECOVERY_SWING_GENERATION);
    printf("%d\n",recovery_runtime_matches(&a,r,s,d));return 0;
}
'''
    binary=root/'probe';compile_source(source,binary);return binary


@pytest.mark.parametrize('fault',[None,'pid','generation','revision','maintenance','failure','provider','unknown_owner','wo11','shadow','analysis','monitoring'])
def test_iwo07r3_actual_c_incident_drain_predicate(iwo07r3_documents_probe,tmp_path,fault):
    from tools import failed_active_successor as h
    r,s,d=_failed_active_scope_documents()
    r['process'].update(pid=h.INCIDENT_PID,revision=h.INCIDENT_REVISION)
    for doc in (r,s): doc['maintenance'].update(generation=h.INCIDENT_GENERATION,failure='SWING_RESTORATION_NOT_ESTABLISHED')
    d['live_shadow']['failure']=None
    if fault=='pid': r['process']['pid']+=1
    elif fault=='generation': s['maintenance']['generation']='b'*64
    elif fault=='revision': r['process']['revision']='b'*40
    elif fault=='maintenance': r['maintenance']['state']='INACTIVE'
    elif fault=='failure': r['maintenance']['failure']='ACCEPTANCE_RESTORATION_NOT_ESTABLISHED'
    elif fault=='provider': r['provider_runtime']['owned_work_count']=1
    elif fault=='unknown_owner': r['maintenance_drain']['owners']['OTHER']=1
    elif fault=='wo11': r['intraday_wo11_work']['continuity']='INCOMPLETE'
    elif fault=='shadow': d['live_shadow']['failure']='OTHER'
    elif fault=='analysis': r['analysis_execution']['owned_workers']=1
    elif fault=='monitoring': r['monitoring']['session_count']=1
    paths=[]
    for i,doc in enumerate((r,s,d)):
        p=tmp_path.resolve()/str(i);p.write_text(json.dumps(doc));paths.append(str(p))
    assert subprocess.check_output([str(iwo07r3_documents_probe),*paths],text=True).strip()==('1' if fault is None else '0')


@pytest.mark.parametrize("fault", ["none", "native_gate", "native_reserve", "native_dispatch", "native_retired", "canonical", "source", "target", "control", "authorization", "installed", "rollback", "assess_initial", "continuity_before", "assess_final", "bindings_before", "reserve", "shutdown", "exit", "handoff_initial", "continuity_after", "bindings_after", "attempt_readback", "handoff_final", "listener_absent", "child_exit", "timeout", "internal"])
def test_iwo07r3_actual_main_preserves_single_transition_order(recovery_orchestration_probe, fault):
    # Real main orchestration, disposable boundary doubles. Predicates have
    # separate actual C and Python tests, not inferred from this wiring proof.
    test_actual_recovery_main_orders_one_use_drain_and_one_successor(recovery_orchestration_probe, fault, "v3")


# Slice 2.2: these harnesses never call operational main or production endpoints.
@pytest.fixture
def native_admission_probe(tmp_path):
    source = _fixture_native_source(SOURCE).replace('int main(void) {', 'int unused_application_main(void) {')
    source = source.replace('static const dev_t approved_admission_device = 16777232;',
                            'static dev_t approved_admission_device = 0;')
    source = source.replace('static const ino_t approved_admission_inode = 694844364;',
                            'static ino_t approved_admission_inode = 0;')
    source = 'static int fixture_admission_ready(void);\n' + source
    source = source.replace('.ready = backend_is_ready,', '.ready = fixture_admission_ready,')
    source = source.replace('#define BACKEND_START_READY_TIMEOUT_SECONDS 120',
                            '#define BACKEND_START_READY_TIMEOUT_SECONDS 2')
    source += r"""
static char fixture_marker[PATH_MAX];
static int fixture_admission_ready(void) {return access(fixture_marker,F_OK)==0;}
int main(int argc,char **argv) {
    if(argc<3)return 90;
    struct stat st;if(stat(argv[2],&st)!=0)return 91;
    admission_anchor=argv[2];approved_admission_device=st.st_dev;approved_admission_inode=st.st_ino;
    admission_descriptor=acquire_installation_admission(admission_anchor,st.st_dev,st.st_ino);
    if(admission_descriptor<0)return 92;
    if(!strcmp(argv[1],"contention")) {
        int other=acquire_installation_admission(admission_anchor,st.st_dev,st.st_ino);
        if(other>=0)return 93;
        finish_admission();return 0;
    }
    if(!strcmp(argv[1],"helper") || !strcmp(argv[1],"helper-invalid")) {
        int invalid=!strcmp(argv[1],"helper-invalid");
        int alias=dup(admission_descriptor);if(alias<0)return 94;
        pid_t child=fork();if(child<0)return 95;
        if(child==0){
            if(invalid)close(admission_descriptor);
            close_helper_admission();
            if(fcntl(alias,F_GETFD)!=-1 || errno!=EBADF)_exit(96);
            _exit(0);
        }
        int result;if(waitpid(child,&result,0)!=child || !WIFEXITED(result) ||
            WEXITSTATUS(result)!=(invalid?126:0))return 97;
        close(alias);
        if(!admission_still_bound())return 98;
        finish_admission();return 0;
    }
    if(!strcmp(argv[1],"cleanup-confirmed") || !strcmp(argv[1],"cleanup-unresolved")) {
        int complete=!strcmp(argv[1],"cleanup-confirmed");
        pid_t child=fork();if(child<0)return 106;
        if(child==0)_exit(complete?ADMISSION_CLEANUP_COMPLETE_EXIT:1);
        admission_child=child;
        puts("CUSTODY_HELD");fflush(stdout);
        finish_admission();return complete?0:107;
    }
    if(!strcmp(argv[1],"exec")) {
        if(argc!=9)return 99;
        strcpy(fixture_marker,argv[6]);
        BackendStartResult result=start_backend(argv[3],argv[4],argv[5],argv[8],0,"","","");
        if(result!=BACKEND_START_READY){finish_admission();return 100;}
        finish_admission();
        int probe=acquire_installation_admission(admission_anchor,st.st_dev,st.st_ino);
        if(probe>=0){close(probe);return 101;} /* Backend still owns shared custody. */
        int done=open(argv[7],O_WRONLY|O_CREAT|O_EXCL,0600);if(done<0)return 102;close(done);
        int status;if(waitpid(admission_child,&status,0)!=admission_child || status!=0)return 103;
        probe=acquire_installation_admission(admission_anchor,st.st_dev,st.st_ino);
        if(probe<0)return 104;close(probe);return 0;
    }
    return 105;
}
"""
    binary=tmp_path/'native-admission-fixture'
    compile_source(source,binary)
    return binary


@pytest.mark.parametrize('case',['contention','helper','helper-invalid'])
def test_native_installation_lock_and_helper_alias_exclusion(tmp_path,native_admission_probe,case):
    anchor=tmp_path/'anchor';anchor.mkdir(mode=0o700)
    result=subprocess.run([str(native_admission_probe),case,str(anchor)],capture_output=True,timeout=6)
    assert result.returncode==0,result.stderr


def test_native_backend_exec_preserves_actual_shared_descriptor(tmp_path,native_admission_probe):
    anchor=tmp_path/'anchor';anchor.mkdir(mode=0o700)
    marker=tmp_path/'ready';done=tmp_path/'done';entry=tmp_path/'backend.py'
    entry.write_text('''import os,time,subprocess,sys
from pathlib import Path
from kronos.common import release_admission as a
path=Path('''+repr(str(anchor))+''');st=path.stat()
a.CANONICAL_PARENT='''+repr(str(native_admission_probe))+'''
owner=a.AdmissionCustody(197,a.AnchorBinding(path,st.st_dev,st.st_ino,os.getuid()),os.getppid())
assert not os.get_inheritable(197)
code='import os;\\ntry:os.fstat(197);raise SystemExit(9)\\nexcept OSError:pass'
assert subprocess.run([sys.executable,'-B','-c',code],close_fds=True).returncode==0
Path('''+repr(str(marker))+''').write_text('ADOPTED')
deadline=time.monotonic()+4
while not Path('''+repr(str(done))+''').exists():
 if time.monotonic()>deadline:raise SystemExit(8)
 time.sleep(.01)
owner.begin_failure_cleanup();owner.completed_failure_cleanup()
''')
    python_path=str(ROOT/'src')+':'+str(ROOT)
    result=subprocess.run([str(native_admission_probe),'exec',str(anchor),str(ROOT),
        sys.executable,str(entry),str(marker),str(done),python_path],capture_output=True,timeout=8)
    assert result.returncode==0,(result.returncode,result.stderr)
    assert marker.read_text()=='ADOPTED'
    assert done.exists()


def test_installation_custody_native_source_order_and_close_only():
    source=_fixture_native_source(SOURCE);main=source.split('int main(void) {',1)[1]
    assert main.index('acquire_launcher_lock(repository)')<main.index('qualify_source(')
    assert main.index('qualify_source(')<main.index('request_graceful_shutdown(')
    wrapper=source.split('static int acquire_launcher_lock(',1)[1].split('/* Helpers',1)[0]
    assert '(void)repository;' in wrapper
    assert 'acquire_installation_admission(admission_anchor,approved_admission_device,' in wrapper
    assert 'LOCK_EX|LOCK_NB' in source
    assert 'LOCK_UN' not in source
    backend=source.split('static BackendStartResult start_backend(',1)[1].split('int main(void)',1)[0]
    assert backend.index('admission_still_bound()')<backend.index('fork()')
    assert backend.count('fork()')==1
    assert 'dup2(admission_descriptor, ADMISSION_BACKEND_DESCRIPTOR)' in backend
    assert 'close_helper_admission();' not in backend
    # Each other fork child closes aliases before helper work, including exec failure.
    boundary=source.split('static int bounded_validation_cli(',1)[1].split('static int canonical_image_path',1)[0]
    assert boundary.index('close_helper_admission();')<boundary.index('validation_child_environment(')<boundary.index('execv(')
    assert source.count('close_helper_admission();')==1
    assert 'finish_admission();\n    char script' in source


@pytest.mark.parametrize('acknowledged',[True,False])
def test_native_failed_child_death_requires_cleanup_acknowledgement(
        tmp_path,native_admission_probe,acknowledged):
    from kronos.common.release_admission import AnchorBinding,open_anchor
    import fcntl
    anchor=tmp_path/'anchor';anchor.mkdir(mode=0o700);st=anchor.stat()
    case='cleanup-confirmed' if acknowledged else 'cleanup-unresolved'
    process=subprocess.Popen([str(native_admission_probe),case,str(anchor)],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        assert process.stdout.readline()=='CUSTODY_HELD\n'
        if acknowledged:
            assert process.wait(timeout=3)==0
        else:
            with pytest.raises(subprocess.TimeoutExpired):process.wait(timeout=.2)
            probe=open_anchor(AnchorBinding(anchor,st.st_dev,st.st_ino,os.getuid()))
            try:
                with pytest.raises(BlockingIOError):fcntl.flock(probe,fcntl.LOCK_EX|fcntl.LOCK_NB)
            finally:os.close(probe)
    finally:
        # Only the disposable directly owned fixture is terminated; this grants
        # no production termination or descendant-completion authority.
        if process.poll() is None:process.terminate()
        process.wait(timeout=3)


@pytest.fixture
def bounded_cli_probe(tmp_path):
    source=_fixture_native_source(SOURCE).replace('int main(void) {','int unused_application_main(void) {')
    source='static int fixture_stall=0,fixture_late=0;\n'+source
    source=source.replace('if(child==0) {\n        close_helper_admission();',
        'if(child==0) {\n        if(fixture_stall==2)for(;;)pause();\n        close_helper_admission();')
    source=source.replace('execv(executable,arguments);_exit(125);',
        'if(fixture_stall)for(;;)pause();execv(executable,arguments);_exit(125);')
    source=source.replace('long long finished=validation_now_ns();',
        'if(fixture_late)usleep(200000);long long finished=validation_now_ns();')
    source+=r'''
static void fixture_interrupt(int signal){(void)signal;}
int main(int argc,char **argv) {
    if(argc!=4)return 90;
    const char *mode=argv[1];
    char code[1024],output[128]={0};char *input=NULL;
    int normal=!strcmp(mode,"normal") || !strcmp(mode,"eintr");
    if(normal || !strcmp(mode,"late-zero"))strcpy(code,
      "import os,sys,time;assert 'KRONOS_MAINTENANCE_PROOF' not in os.environ;assert 'OPENAI_API_KEY' not in os.environ;time.sleep(.08);print('OK')");
    else if(!strcmp(mode,"failure") || !strcmp(mode,"lost-report"))strcpy(code,"raise SystemExit(7)");
    else if(!strcmp(mode,"output"))strcpy(code,"print('x'*1000)");
    else strcpy(code,"import time;time.sleep(3)");
    if(!strcmp(mode,"blocked-write")){input=malloc(1048577);if(!input)return 91;memset(input,'x',1048576);input[1048576]=0;}
    if(!strcmp(mode,"pre-exec"))fixture_stall=1;
    if(!strcmp(mode,"pre-close"))fixture_stall=2;
    if(!strcmp(mode,"late-zero"))fixture_late=1;
    if(!strcmp(mode,"eintr")) {
        struct sigaction action={0};action.sa_handler=fixture_interrupt;sigaction(SIGALRM,&action,NULL);
        struct itimerval timer={.it_interval={0,10000},.it_value={0,10000}};setitimer(ITIMER_REAL,&timer,NULL);
    }
    if(!strcmp(argv[3],"retain")) {
        struct stat st;const char *path=getenv("FIXTURE_ANCHOR");
        if(!path || stat(path,&st)!=0)return 97;
        admission_descriptor=acquire_installation_admission(path,st.st_dev,st.st_ino);
        if(admission_descriptor<0)return 98;
    }
    if(!strcmp(mode,"lost-report")) {
        int broken[2];if(pipe(broken)!=0)return 109;close(broken[0]);
        if(dup2(broken[1],STDERR_FILENO)<0)return 110;close(broken[1]);
    }
    validation_deadline_ns=validation_now_ns()+(normal?1000000000LL:150000000LL);
    char *arguments[]={argv[2],"-B","-c",code,NULL};
    int result=bounded_validation_cli(NULL,argv[2],arguments,input,output,sizeof(output),0,"FIXTURE_CLI",10);
    free(input);
    printf("DECISION %d %d %d %ld\n",result,validation_failed,validation_cleanup_unresolved,(long)validation_direct_child);fflush(stdout);
    if(normal)return result && !strcmp(output,"OK\n")?0:92;
    if(result || !validation_failed)return 93;
    if(!strcmp(mode,"failure"))return validation_cleanup_unresolved?94:0;
    if(!validation_cleanup_unresolved)return 95;
    /* A second helper is denied by sticky failure before another fork. */
    pid_t first=validation_direct_child;
    if(bounded_validation_cli(NULL,argv[2],arguments,NULL,output,sizeof(output),0,"NO_RETRY",10) || validation_direct_child!=first)return 96;
    if(!strcmp(argv[3],"retain")) {
        puts("CUSTODY_HELD");fflush(stdout);finish_admission();return 99;
    }
    /* Fixture-only reap of the directly owned helper. No group or descendant claim. */
    int status;if(validation_direct_child>0)while(waitpid(validation_direct_child,&status,0)<0 && errno==EINTR){}
    return 0;
}
'''
    binary=tmp_path/'bounded-cli';compile_source(source,binary);return binary


@pytest.mark.parametrize('mode',['normal','blocked-read','blocked-write','pre-exec','pre-close','failure','output','late-zero','eintr'])
def test_slice23_native_cli_deadline_io_and_sticky_failure(tmp_path,bounded_cli_probe,mode):
    import time
    environment=dict(os.environ,KRONOS_MAINTENANCE_PROOF='DISPOSABLE_SECRET',OPENAI_API_KEY='DISPOSABLE_SECRET')
    started=time.monotonic()
    result=subprocess.run([str(bounded_cli_probe),mode,sys.executable,'finish'],env=environment,
        capture_output=True,text=True,timeout=3)
    assert result.returncode==0,(result.returncode,result.stderr)
    assert time.monotonic()-started<2
    if mode not in {'normal','eintr'}:
        outcomes=[json.loads(line) for line in result.stderr.splitlines()]
        assert outcomes[0]['phase']=='FIXTURE_CLI'
        assert outcomes[0]['direct_child']>0 and outcomes[0]['clock']=='CLOCK_MONOTONIC'
        assert 'DISPOSABLE_SECRET' not in result.stderr
        if mode!='failure':assert outcomes[0]['cleanup']=='CLEANUP_UNRESOLVED'


@pytest.mark.parametrize('mode',['blocked-read','pre-close','lost-report'])
def test_slice23_native_decision_reports_before_retained_custody(tmp_path,bounded_cli_probe,mode):
    import fcntl
    from kronos.common.release_admission import AnchorBinding,open_anchor
    anchor=tmp_path/'anchor';anchor.mkdir(mode=0o700);st=anchor.stat()
    process=subprocess.Popen([str(bounded_cli_probe),mode,sys.executable,'retain'],
        env=dict(os.environ,FIXTURE_ANCHOR=str(anchor)),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        assert process.stdout.readline().startswith('DECISION 0 1 1 ')
        assert process.stdout.readline()=='CUSTODY_HELD\n'
        with pytest.raises(subprocess.TimeoutExpired):process.wait(timeout=.2)
        probe=open_anchor(AnchorBinding(anchor,st.st_dev,st.st_ino,os.getuid()))
        try:
            with pytest.raises(BlockingIOError):fcntl.flock(probe,fcntl.LOCK_EX|fcntl.LOCK_NB)
        finally:os.close(probe)
    finally:
        if process.poll() is None:process.terminate()
        process.wait(timeout=3)
    records=[json.loads(line) for line in process.stderr.read().splitlines()]
    if mode=='lost-report':assert records==[]
    else:assert any(row['cleanup']=='CLEANUP_UNRESOLVED' for row in records)


def test_slice23_declared_budgets_and_phase_gates_are_source_bound():
    source=_fixture_native_source(SOURCE);main=source.split('int main(void) {',1)[1]
    assert main.index('validation_deadline_ns+=120000000000LL')<main.index('canonical_operational_image()')
    assert '"NATIVE_SIGNATURE",10' in source and '"LOCAL_REVISION",10' in source
    assert '"SOURCE_GATE",60' in source and '"POST_RETIREMENT_HANDOFF",10' in source
    assert '#define HANDOFF_SECONDS 45' in source
    backend=source.split('static BackendStartResult start_backend(',1)[1].split('int main(void)',1)[0]
    assert backend.index('backend_ready_deadline_ns=before_fork')<backend.index('fork()')
    assert 'KRONOS_VALIDATION_CLOCK' in backend and 'KRONOS_VALIDATION_DEADLINE_NS' in backend
    assert 'if (!admission_still_bound() || !validation_permitted())' in backend
    assert 'kill(child,SIGKILL)' in source and 'killpg' not in source
    assert 'if(monitor->monotonic_now(&completed)!=0)' in source
    assert 'deadline_ns' in source and 'CLEANUP_UNRESOLVED' in source



def test_slice23_predecessor_window_starts_before_claim_and_is_not_reset():
    source=_fixture_native_source(SOURCE)
    wrapper=source.split('static int request_graceful_shutdown(pid_t',1)[1].split('static int wait_for_backend_stop',1)[0]
    assert wrapper.index('stop_deadline_ns=before_claim+15000000000LL')<wrapper.index('request_graceful_shutdown_effect(')
    assert 'handoff_deadline_ns=before_claim+45000000000LL' in wrapper
    stop=source.split('static int wait_for_backend_stop(',1)[1].split('static int cold_start',1)[0]
    assert 'if(!stop_deadline_ns)stop_deadline_ns=' in stop
    assert 'stop_deadline_ns=0' in stop
    assert 'PREDECESSOR_DRAIN_STOP' in stop and 'CLEANUP_UNRESOLVED' in source


@pytest.fixture
def overlapping_native_reporter(tmp_path):
    source=_fixture_native_source(SOURCE).replace('int main(void) {','int unused_application_main(void) {')
    source='#include <stdarg.h>\nstatic int report_fixture_fcntl(int,int,...);\n'+source
    start=source.index('static void validation_outcome(const char *phase,')
    end=source.index('static int validation_environment_key',start)
    source=source[:start]+source[start:end].replace('fcntl(', 'report_fixture_fcntl(')+source[end:]
    source+=r'''
static int report_fixture_fcntl(int fd,int operation,...) {
    if(operation==F_GETFL)return fcntl(fd,operation);
    va_list arguments;va_start(arguments,operation);int flags=va_arg(arguments,int);va_end(arguments);
    int result=fcntl(fd,operation,flags);
    if(fd==2 && operation==F_SETFL && (flags&O_NONBLOCK)) {
        if(write(1,"A\n",2)!=2)_exit(95);
        char ready;if(read(0,&ready,1)!=1)_exit(96);
    }
    return result;
}
int main(void) {
    validation_outcome("NATIVE_OVERLAP",1,getpid(),"DENIED",1);
    return 0;
}
'''
    binary=tmp_path/'native-overlap';compile_source(source,binary);return binary


def test_slice23_f02_overlapping_native_python_reporting_stays_nonblocking(overlapping_native_reporter):
    import fcntl,time
    read,write=os.pipe();flags=fcntl.fcntl(write,fcntl.F_GETFL)
    fcntl.fcntl(write,fcntl.F_SETFL,flags|os.O_NONBLOCK)
    try:
        while True:os.write(write,b'x'*4096)
    except BlockingIOError:pass
    try:
        while True:os.write(write,b'x')
    except BlockingIOError:pass
    fcntl.fcntl(write,fcntl.F_SETFL,flags)
    a=b=None
    try:
        a=subprocess.Popen([str(overlapping_native_reporter)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=write)
        assert a.stdout.readline()==b'A\n'
        code='''import os,sys,fcntl
from kronos.common import release_admission as a
real=fcntl.fcntl
def hook(fd,operation,*args):
 result=real(fd,operation,*args)
 if fd==2 and operation==fcntl.F_SETFL and args[0]&os.O_NONBLOCK:
  print('B',flush=True);sys.stdin.buffer.read(1)
 return result
a.fcntl.fcntl=hook
a.report_validation('PYTHON_OVERLAP',1,os.getpid(),'DENIED','CLEANUP_UNRESOLVED')
assert a.validation_unresolved()
print('DONE',flush=True)
'''
        b=subprocess.Popen([sys.executable,'-B','-c',code],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=write)
        assert b.stdout.readline()==b'B\n'
        a.stdin.write(b'x');a.stdin.flush();assert a.wait(timeout=2)==0
        still_nonblocking=bool(fcntl.fcntl(write,fcntl.F_GETFL)&os.O_NONBLOCK)
        b.stdin.write(b'x');b.stdin.flush()
        try:b.wait(timeout=.5);completed=True
        except subprocess.TimeoutExpired:completed=False
        assert still_nonblocking and completed,{'nonblocking':still_nonblocking,'second_completed':completed}
        assert b.stdout.readline()==b'DONE\n' and b.returncode==0
    finally:
        for process in (a,b):
            if process is not None:
                if process.poll() is None:process.terminate()
                process.wait(timeout=2)
        os.close(read);os.close(write)


@pytest.mark.parametrize('mode', ('success','rejected','bad-revision','timeout','output','unresolved-exit'))
def test_r33_f01_nested_validation_disposition_reaches_native_custody(
        tmp_path,monkeypatch,record_property,mode):
    """Actual native CLI -> actual Python entry -> actual nested CLI owner.

    The only predicate seam substitutes a disposable command for the parent's
    Git CLI. Neither the owner state, entry result nor native cleanup is stubbed.
    """
    import fcntl
    import time
    from hashlib import sha256
    from kronos.common import legacy_bootstrap as adapter,release_admission as admission
    from tests.unit.common import test_legacy_bootstrap as setup
    from tests.unit.common import test_failed_successor_restore as fixture
    control=setup._c02_dispatch_case(tmp_path,monkeypatch);case=control['case']
    repository,bundle=control['repository'],control['bundle']
    anchor=case.custody.binding.path;metadata=anchor.stat()
    evidence=ROOT.parent/'qualification/f01-boundary-evidence'/tmp_path.parents[1].name/tmp_path.name
    evidence.mkdir(parents=True)
    source=_fixture_native_source(SOURCE).replace('int main(void) {','int preserved_operational_main(void) {')
    source=source.replace('static const dev_t approved_admission_device = 16777232;','static dev_t approved_admission_device = 0;')
    source=source.replace('static const ino_t approved_admission_inode = 694844364;','static ino_t approved_admission_inode = 0;')
    source+=r'''
int main(int argc,char **argv) {
 if(argc!=6)return 90;
 struct stat st;if(stat(argv[1],&st)!=0)return 91;
 admission_anchor=argv[1];approved_admission_device=st.st_dev;approved_admission_inode=st.st_ino;
 canonical_bundle=argv[3];canonical_executable=argv[0];
 admission_descriptor=acquire_installation_admission(argv[1],st.st_dev,st.st_ino);
 if(admission_descriptor<0)return 92;
 validation_deadline_ns=validation_now_ns()+120000000000LL;
 int accepted=native_gate(argv[2],argv[4],"ORDINARY");
 int diagnostic=open(argv[5],O_WRONLY|O_CREAT|O_EXCL,0600);
 size_t bytes=strlen(native_startup.last_result);
 if(diagnostic<0 || write(diagnostic,native_startup.last_result,bytes)!=(ssize_t)bytes || fsync(diagnostic)!=0)return 93;
 close(diagnostic);
 printf("NATIVE_DECISION %d %d %d %ld %lld\n",accepted,validation_failed,
     validation_cleanup_unresolved,(long)validation_direct_child,validation_deadline_ns);fflush(stdout);
 /* This is the unchanged native disposition, including indefinite exclusion
  * when the actual bounded Python validation child exits unresolved. */
 finish_admission();puts("NATIVE_CUSTODY_CLOSED");fflush(stdout);return 0;
}
'''
    unit=evidence/'native-boundary.c';unit.write_text(source)
    binary=bundle/'Contents/MacOS/KRONOS'
    command=['clang','-Wall','-Wextra','-Werror',str(unit),'-o',str(binary)]
    compiled=subprocess.run(command,capture_output=True,text=True)
    (evidence/'compile-result.json').write_text(json.dumps(dict(command=command,actual_exit=compiled.returncode,
        stdout=compiled.stdout,stderr=compiled.stderr,production_native_sha256=sha256(SOURCE.read_bytes()).hexdigest(),
        compiled_unit_sha256=sha256(unit.read_bytes()).hexdigest()),indent=2)+'\n')
    assert compiled.returncode==0,compiled.stderr
    binary.chmod(0o755);shutil.copy2(binary,evidence/'native-boundary')
    installation=json.loads(case.permit_path.read_bytes())['installation']
    now=datetime.now(UTC)
    phase=adapter._native_phase('activation-f01','NATIVE_ACTIVATED',original='activation-f01',
        installation=installation,parent=json.loads(case.reservation_path.read_bytes())['parent'],
        selected=None,predecessor=None,previous=None,details={},now=now)
    raw=fixture._put(case.head_path.parent/'activation-f01.json',phase)
    head=dict(schema='KRONOS_RESTORATION_ADMISSION_HEAD_V1',installation_identity=installation['identity'],
        sequence=1,state='NATIVE_ACTIVATED',incident_id=None,active_reservation_id='activation-f01',
        active_reservation_sha256=sha256(raw).hexdigest(),previous_head_sha256='0'*64,recorded_at=now.isoformat())
    fixture._put(case.head_path,head);fixture._put(case.head_path.parent/'head-1.json',head)
    nested=evidence/'nested-validation.py'
    old=case.head_path.parent/'head-2.json'
    if old.exists():old.rename(case.root/'s304-unexecuted-f01-head-2.json')
    policy=fixture._s304_admit_fixture(case.head_path.parent,installation)
    shutil.copy2(unit,evidence/'unexecuted-prepin-boundary.c');shutil.copy2(binary,evidence/'unexecuted-prepin-boundary')
    source=source.replace('approved_initialization_disposition = NULL;',
        'approved_initialization_disposition = '+json.dumps(policy.decode())+';')
    unit.write_text(source)
    compiled_pin=subprocess.run(command,capture_output=True,text=True)
    (evidence/'separate-pin-compile.json').write_text(json.dumps(dict(command=command,
        actual_exit=compiled_pin.returncode,stdout=compiled_pin.stdout,stderr=compiled_pin.stderr,
        executed_unit_sha256=sha256(unit.read_bytes()).hexdigest()),indent=2))
    assert compiled_pin.returncode==0,compiled_pin.stderr
    binary.chmod(0o755);shutil.copy2(binary,evidence/'native-boundary-final')
    nested.write_text('import sys\nsys.path[:0]='+repr([str(ROOT/'src'),str(ROOT)])+'\n'+r'''
import json,os,subprocess,sys,time
from pathlib import Path
from kronos.common import release_admission as owner
mode=sys.argv[1];evidence=Path(sys.argv[2])
if mode=='success':os.execv('/usr/bin/git',['/usr/bin/git','rev-parse','HEAD'])
if mode=='rejected':raise SystemExit(7)
if mode=='bad-revision':print('not-a-git-revision');raise SystemExit(0)
if mode=='timeout':time.sleep(30)
if mode=='output':print('x'*1000,flush=True);time.sleep(30)
if mode=='unresolved-exit':
 budget=owner.inherited_budget(120,required=True);original_deadline=budget.deadline_ns
 try:
  owner.validation_output([sys.executable,'-B','-c',"print('x'*1000,flush=True)"],
      cwd=Path.cwd(),budget=budget,ceiling=10,phase='F01_NESTED_OWNER',capacity=16)
 except BaseException as error:
  (evidence/'nested-owner-outcome.json').write_text(json.dumps(dict(exception=type(error).__name__,
      unresolved=owner.validation_unresolved(),budget_failed=budget.failed,
      original_deadline_ns=original_deadline,final_deadline_ns=budget.deadline_ns,
      inherited_deadline_ns=int(os.environ['KRONOS_VALIDATION_DEADLINE_NS']),
      owned_helpers=[dict(pid=p.pid,actual_exit=p.returncode) for p in owner._OWNED_VALIDATION_HELPERS.values()])))
 finally:
  waits=[]
  for child in owner._OWNED_VALIDATION_HELPERS.values():
   waits.append(dict(pid=child.pid,actual_exit=child.wait(timeout=3)))
  (evidence/'nested-owner-fixture-teardown.json').write_text(json.dumps(dict(waits=waits,
      application_cleanup_claimed=False,unresolved_state_preserved=owner.validation_unresolved())))
 if owner.validation_unresolved():raise SystemExit(79)
 raise SystemExit('ACTUAL_UNRESOLVED_OUTCOME_NOT_OBSERVED')
''')
    shim=evidence/'validation-entry-python'
    shim.write_text('#!'+sys.executable+'\n'+
        'import json,os,sys\nfrom pathlib import Path\n'+
        'sys.path[:0]='+repr([str(ROOT/'src'),str(ROOT)])+'\n'+
        'from kronos.common import legacy_bootstrap as entry,release_admission as owner\n'+
        'from kronos.common import failed_successor_restore as s304_restore\ns304_restore.INITIALIZATION_DISPOSITION='+repr(policy)+'\n'+
        'owner.CANONICAL_PARENT='+repr(str(binary))+'\n'+
        'evidence=Path('+repr(str(evidence))+')\n'+
        'actual_output=entry._validation_output\nobservations=[]\n'+
        'def nested_output(arguments,repository,checks,phase,**kwargs):\n'+
        ' assert phase=="NATIVE_PARENT_SOURCE"\n'+
        ' budget=checks.budget;before=budget.deadline_ns;raised=None\n'+
        ' try:return actual_output(['+repr(sys.executable)+',"-B",'+repr(str(nested))+','+repr(mode)+',str(evidence)],repository,checks,phase,capacity=64)\n'+
        ' except BaseException as error:raised=dict(exception=type(error).__name__,returncode=getattr(error,"returncode",None));raise\n'+
        ' finally:observations.append(dict(original_deadline_ns=before,final_deadline_ns=budget.deadline_ns,same_budget=checks.budget is budget,budget_failed=budget.failed,raised=raised))\n'+
        'entry._validation_output=nested_output\n'+
        'assert sys.argv[1:3]==["-B","-c"]\n'+
        'failure=None\ntry:exec(sys.argv[3],{"__name__":"__main__"})\n'+
        'except BaseException as error:\n'+
        ' failure=dict(exception=type(error).__name__,exit_code=error.code if isinstance(error,SystemExit) else 1,nested_returncode=getattr(error,"returncode",None));raise\n'+
        'finally:\n'+
        ' (evidence/"python-entry-outcome.json").write_text(json.dumps(dict(failure=failure,unresolved=owner.validation_unresolved(),budget_observations=observations,inherited_deadline_ns=int(os.environ["KRONOS_VALIDATION_DEADLINE_NS"]))))\n'+
        ' waits=[]\n for child in owner._OWNED_VALIDATION_HELPERS.values():waits.append(dict(pid=child.pid,actual_exit=child.wait(timeout=3)))\n'+
        ' (evidence/"python-entry-fixture-teardown.json").write_text(json.dumps(dict(waits=waits,application_cleanup_claimed=False,unresolved_state_preserved=owner.validation_unresolved())))\n')
    shim.chmod(0o755)
    case.close()  # Close setup custody before the actual native parent acquires it.
    argv=[str(binary),str(anchor),str(repository),str(bundle),str(shim),str(evidence/'actual-python-output.log')]
    out=(evidence/'native.stdout.log').open('w');err=(evidence/'native.stderr.log').open('w')
    process=subprocess.Popen(argv,stdout=out,stderr=err,text=True)
    before_teardown=None;forced=False
    try:
        until=time.monotonic()+22
        while True:
            lines=(evidence/'native.stdout.log').read_text().splitlines()
            decisions=[line for line in lines if line.startswith('NATIVE_DECISION ')]
            if decisions:break
            if process.poll() is not None:pytest.fail('native fixture exited before reporting decision: '+(evidence/'native.stderr.log').read_text())
            if time.monotonic()>=until:pytest.fail('native bounded decision not observed')
            time.sleep(.01)
        accepted,failed,unresolved,helper,deadline=map(int,decisions[0].split()[1:])
        if not unresolved:process.wait(timeout=3)
        probe=admission.open_anchor(admission.AnchorBinding(anchor,metadata.st_dev,metadata.st_ino,os.getuid()))
        try:
            try:fcntl.flock(probe,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:excluded=True
            else:excluded=False
        finally:os.close(probe)
        python=json.loads((evidence/'python-entry-outcome.json').read_text())
        before_teardown=dict(mode=mode,accepted=accepted,native_failed=failed,native_unresolved=unresolved,
            actual_validation_child=helper,native_absolute_deadline_ns=deadline,
            independent_admission_probe_excluded=excluded,native_parent_still_running=process.poll() is None,
            python_entry=python,application_cleanup_claimed=False,observed_before_test_teardown=True)
        (evidence/'boundary-before-fixture-teardown.json').write_text(json.dumps(before_teardown,indent=2)+'\n')
        uncertain=mode in {'timeout','output','unresolved-exit'}
        assert bool(python['unresolved']) is uncertain
        assert accepted==(mode=='success') and failed==(mode!='success')
        assert bool(unresolved) is uncertain,before_teardown
        assert excluded is uncertain,before_teardown
        assert (process.poll() is None) is uncertain
        assert all(row['same_budget'] and row['original_deadline_ns']==row['final_deadline_ns']
            for row in python['budget_observations'])
        if uncertain:
            assert python['failure']['exit_code']==79
            diagnostics=(evidence/'actual-python-output.log').read_text()
            assert 'CLEANUP_UNRESOLVED' in diagnostics and 'NATIVE_PARENT_SOURCE' in diagnostics
        elif mode=='bad-revision':assert python['failure']['exit_code']==78
        elif mode=='rejected':assert python['failure']['exception']=='CalledProcessError' and python['failure']['nested_returncode']==7
        else:assert python['failure'] is None
        if mode=='unresolved-exit':
            assert python['budget_observations'][0]['raised']==dict(exception='CalledProcessError',returncode=79)
            nested_result=json.loads((evidence/'nested-owner-outcome.json').read_text())
            assert nested_result['unresolved'] and nested_result['exception']=='ValueError'
            assert nested_result['original_deadline_ns']==nested_result['final_deadline_ns']
        record_property('boundary','ACTUAL_NATIVE_CLI_PYTHON_ENTRY_AND_NESTED_OWNER; ACTUAL_INDEPENDENT_FLOCK_PROBE')
        record_property('seams','DISPOSABLE_ANCHOR_CANONICAL_IMAGE_AND_GIT_COMMAND; NO_OWNER_FLAG_OR_CLEANUP_BOOLEAN_STUB')
    finally:
        if process.poll() is None:forced=True;process.terminate()
        code=process.wait(timeout=3);out.close();err.close()
        (evidence/'native-fixture-teardown.json').write_text(json.dumps(dict(command=argv,owned_pid=process.pid,
            actual_exit=code,waited=True,forced_test_teardown=forced,application_cleanup_claimed=False,
            outcome_recorded_before_teardown=before_teardown is not None),indent=2)+'\n')


def _e02_compile_installed_control(control,source_root,evidence,*,component=True,shim=None,port=None):
    """Actual C/Python validators; only fixed fixture pins/entry/path/signature seams."""
    from hashlib import sha256
    from tests.unit.common import test_legacy_bootstrap as setup
    from tests.unit.common import test_failed_successor_restore as fixture
    from kronos.common import legacy_bootstrap as adapter
    c=control;source=_fixture_native_source(source_root/'tools/macos/kronos_launcher.c')
    source=source.replace('approved_initialization_disposition = NULL;',
        'approved_initialization_disposition = '+json.dumps(c.genesis.decode())+';')
    source=source.replace('approved_persistent_binding = NULL;',
        'approved_persistent_binding = '+json.dumps(adapter._canonical(c.persistent).decode())+';')
    source=source.replace('approved_ordinary_restart_policy = NULL;',
        'approved_ordinary_restart_policy = '+json.dumps(adapter._canonical(c.policy).decode())+';')
    source=source.replace('int main(void) {','int preserved_operational_main(void) {')
    source=source.replace('static const dev_t approved_admission_device = 16777232;',
        'static const dev_t approved_admission_device = '+str(c.installation['device'])+';')
    source=source.replace('static const ino_t approved_admission_inode = 694844364;',
        'static const ino_t approved_admission_inode = '+str(c.installation['inode'])+';')
    source=source.replace('"/Users/imranali/Library/Application Support/KRONOS/runtime"',json.dumps(str(c.anchor)))
    binary=c.bundle/'Contents/MacOS/KRONOS'
    source=source.replace('"/Applications/KRONOS.app/Contents/MacOS/KRONOS"',json.dumps(str(binary)))
    source=source.replace('"/Applications/KRONOS.app"',json.dumps(str(c.bundle)))
    if port is not None:source=source.replace('8947',str(port))
    # Qualification-only syscall/time seams. The production deadline is never
    # modified; only the generated native observer's clock return is controlled.
    prelude=r'''
#include <unistd.h>
#include <time.h>
#include <fcntl.h>
static int e02_fixture_sync(int);
static ssize_t e02_fixture_write(int,const void *,size_t);
static int e02_fixture_clock(clockid_t,struct timespec *);
#define fsync e02_fixture_sync
#define write e02_fixture_write
#define clock_gettime e02_fixture_clock
'''
    faults=r'''
#undef fsync
#undef write
#undef clock_gettime
static long long e02_observed_after_ns=0;
static int e02_prefix_written=0;
static int e02_fixture_clock(clockid_t clock,struct timespec *out) {
 int rc=clock_gettime(clock,out);
 if(!rc && clock==CLOCK_MONOTONIC && e02_observed_after_ns) {
  out->tv_sec=(time_t)(e02_observed_after_ns/1000000000LL);out->tv_nsec=(long)(e02_observed_after_ns%1000000000LL);
 }
 return rc;
}
static int e02_target_fd(int fd,const char *suffix) {
 char path[PATH_MAX];return fcntl(fd,F_GETPATH,path)==0 && strstr(path,suffix)!=NULL;
}
static ssize_t e02_fixture_write(int fd,const void *raw,size_t size) {
 const char *fault=getenv("E02_TEST_STOP_FAULT");
 if(fault && !strcmp(fault,"prefix") && !strcmp(native_startup.mode,"ORDINARY_STOP") && e02_target_fd(fd,".terminal.json")) {
  if(e02_prefix_written)return 0;e02_prefix_written=1;
  return write(fd,raw,size<5?size:5);
 }
 return write(fd,raw,size);
}
static int e02_fixture_sync(int fd) {
 const char *current=getenv("E02_TEST_CURRENT_DURABILITY_FAILURE");
 if(current && !strcmp(current,"deny") && !strcmp(native_startup.mode,"ORDINARY") && e02_target_fd(fd,".owners.json")) {
  errno=EIO;return -1;
 }
 int result=fsync(fd);const char *fault=getenv("E02_TEST_STOP_FAULT");
 if(!result && fault && !strcmp(fault,"late") && !strcmp(native_startup.mode,"ORDINARY_STOP") && e02_target_fd(fd,".terminal.json")) {
  e02_observed_after_ns=validation_current_deadline();
  fprintf(stderr,"E02_QUALIFICATION_ONLY_LATE_PUBLICATION original_deadline_ns=%lld\n",validation_current_deadline());
 }
 return result;
}
'''
    source=prelude+source+faults
    if component:
        source+=r'''
int main(int argc,char **argv) {
 if(argc!=6)return 90;
 admission_descriptor=acquire_installation_admission(admission_anchor,approved_admission_device,approved_admission_inode);
 if(admission_descriptor<0){puts("CUSTODY_DENIED");return 0;}
 validation_deadline_ns=validation_now_ns()+120000000000LL;
 char volume[37];uint64_t id;if(!descriptor_filesystem_identity(admission_descriptor,volume,&id))return 91;
 printf("ACTUAL_FD_IDENTITY=%s:%llu\n",volume,(unsigned long long)id);
 if(!native_gate(argv[1],argv[2],"ORDINARY")){puts("HEAD_DENIED");finish_admission();return 0;}
 if(!strcmp(argv[5],"boot"))operation_boot_identity[0]=operation_boot_identity[0]=='a'?'b':'a';
 if(!native_original_reserve(0)){puts("POLICY_OR_RESERVATION_DENIED");finish_admission();return 0;}
 if(!native_advance("CHILD_START_RESERVED","{}")){puts("CURRENT_CHECK_DENIED");finish_admission();return 0;}
 int effect=open(argv[3],O_WRONLY|O_CREAT|O_EXCL,0600);if(effect<0)return 92;
 if(write(effect,"ONE_RESERVED_EFFECT",19)!=19 || fsync(effect)!=0 || close(effect)!=0)return 93;
 puts("ONE_RESERVED_EFFECT");fflush(stdout);
 while(!strcmp(argv[5],"hold") && access(argv[4],F_OK)!=0 && validation_permitted()) {
  struct timespec delay={.tv_sec=0,.tv_nsec=10000000};nanosleep(&delay,NULL);
 }
 finish_admission();return 0;
}
'''
    else:
        source+=r'''
int main(void) {
 const char *mode=getenv("KRONOS_LAUNCH_MODE");
 const char *repository=E02_REPOSITORY,*python=E02_PYTHON;
 admission_descriptor=acquire_installation_admission(admission_anchor,approved_admission_device,approved_admission_inode);
 if(admission_descriptor<0)return 92;
 validation_deadline_ns=validation_now_ns()+120000000000LL;
 if(mode && !strcmp(mode,"ORDINARY_STOP") && !native_stop_budget())return 91;
 if(!native_gate(repository,python,mode?mode:"ORDINARY")){finish_admission();return 93;}
 char control[PATH_MAX],entry[PATH_MAX],path[PATH_MAX*2];
 snprintf(control,sizeof(control),"%s/browser-backend-v1.control",admission_anchor);
 if(mode && !strcmp(mode,"ORDINARY_STOP")){int r=native_ordinary_stop(repository,python,control);finish_admission();return r;}
 if(mode)return 94;
 if(native_reuse(control)){finish_admission();puts("ACTUAL_READY_REUSE");return 0;}
 if(!cold_start_has_no_control_or_live_handoff(control) || !native_original_reserve(0)){finish_admission();return 95;}
 if(getenv("E02_TEST_STOP_AFTER_RESERVE")) {
  puts("E02_ACTUAL_RESERVATION_HELD_BEFORE_FORK");fflush(stdout);
  while(validation_permitted()){struct timespec pause={.tv_sec=0,.tv_nsec=10000000};nanosleep(&pause,NULL);}
  finish_admission();return 99;
 }
 snprintf(entry,sizeof(entry),"%s/tools/kronos_browser.py",repository);snprintf(path,sizeof(path),"%s/src:%s",repository,repository);
 BackendStartResult result=start_backend(repository,python,entry,path,0,"","","");
 if(result==BACKEND_START_READY) {
  printf("E02_ACTUAL_CHILD_READY=%ld\n",(long)admission_child);fflush(stdout);finish_admission();
  int status;pid_t reaped;do{reaped=waitpid(admission_child,&status,0);}while(reaped<0&&errno==EINTR);
  printf("E02_ACTUAL_DIRECT_CHILD_EXIT=%d\n",status);fflush(stdout);
  return reaped==admission_child && WIFEXITED(status) && WEXITSTATUS(status)==0?0:98;
 }
 if(result==BACKEND_START_CHILD_EXITED && native_terminal_cleanup()) {
  printf("E02_ACTUAL_FAILED_CHILD_STATE=%s\n",native_journal.state);fflush(stdout);finish_admission();return 78;
 }
 finish_admission();return 79;
}
'''
        source='#define E02_REPOSITORY '+json.dumps(str(c.repository))+'\n#define E02_PYTHON '+json.dumps(str(shim))+'\n'+source
    evidence.mkdir(parents=True,exist_ok=True)
    unit=evidence/'e02-native.c';unit.write_text(source)
    command=['clang','-Wall','-Wextra','-Werror',str(unit),'-o',str(binary)]
    compiled=subprocess.run(command,capture_output=True,text=True)
    (evidence/'compile-result.json').write_text(json.dumps(dict(command=command,actual_exit=compiled.returncode,
        stdout=compiled.stdout,stderr=compiled.stderr,source_sha256=sha256((source_root/'tools/macos/kronos_launcher.c').read_bytes()).hexdigest(),
        generated_source_sha256=sha256(unit.read_bytes()).hexdigest(),seams='SYNTHETIC_AUTHORITY_AND_STATIC_PINS; PRIVATE_PATH_PORT; COMPONENT_MAIN; ACTUAL_IMPLEMENTATION_COMPONENTS'),indent=2)+'\n')
    assert compiled.returncode==0,compiled.stderr
    binary.chmod(0o755)
    artifact=json.loads(c.artifact_manifest.read_bytes());rows=setup._c02_bundle_manifest(c.bundle);digest=sha256(binary.read_bytes()).hexdigest()
    artifact.update(bundle_manifest=rows,bundle_identity=sha256(adapter._canonical(rows)).hexdigest(),
        built_binary_sha256=digest,signed_binary_sha256=digest)
    c.artifact_manifest.write_bytes(adapter._canonical(artifact)+b'\n')
    c.selection['artifact_manifest']=fixture._ref(c.artifact_manifest,'e02-artifact',c.artifact_manifest.read_bytes())
    c.selection['target']=dict(c.selection['target'],artifact_manifest_sha256=c.selection['artifact_manifest']['sha256'])
    setup._e02_publish_control_activation(c)
    _e02_retain_selected_documents(c,evidence)
    shutil.copy2(binary,evidence/'e02-native')
    return binary


def _e02_helper_shim(control,source_root,path):
    from kronos.common import legacy_bootstrap as adapter
    c=control
    script='#!'+sys.executable+'\nimport sys\nfrom pathlib import Path\n'
    script+='sys.path[:0]='+repr([str(source_root/'src'),str(source_root)])+'\n'
    script+='from kronos.common import release_admission as a,legacy_bootstrap as b,failed_successor_restore as r\n'
    script+='from hashlib import sha256\nif a.PERSISTENT_ANCHOR_BINDING is not None: assert sha256(a.PERSISTENT_ANCHOR_BINDING).hexdigest()=="85ea2fa04da20f40377b242d71db96762020e77042a7b4923c331c6f82ab7891"\na.PERSISTENT_ANCHOR_BINDING=None\na.CANONICAL_PARENT='+repr(str(c.bundle/'Contents/MacOS/KRONOS'))+'\n'
    script+='a.APPROVED_BINDING=a.AnchorBinding(Path('+repr(str(c.anchor))+'),'+str(c.installation['device'])+','+str(c.installation['inode'])+','+str(c.installation['owner'])+')\n'
    script+='a.PERSISTENT_ANCHOR_BINDING='+repr(adapter._canonical(c.persistent))+'\n'
    script+='r.INITIALIZATION_DISPOSITION='+repr(c.genesis)+'\n'
    script+='b.ORDINARY_RESTART_POLICY='+repr(adapter._canonical(c.policy))+'\n'
    script+='b._verify_bundle_signature=lambda *_:None\n'
    return script


@pytest.mark.parametrize('fault',('valid','old-device','injected-selection','changed-artifact','changed-source',
    'substituted-anchor','boot','missing-history','concurrent'))
def test_e02_actual_native_fixed_selection_and_reservation(tmp_path,monkeypatch,record_property,fault):
    from tests.unit.common import test_legacy_bootstrap as setup
    from hashlib import sha256
    import time
    c=setup._e02_installed_control(tmp_path,monkeypatch,device_delta=-1 if fault=='old-device' else 0)
    evidence=ROOT.parent/'qualification/e02-native-evidence'/tmp_path.parents[1].name/tmp_path.name
    shim=tmp_path/'e02-helper-python'
    shim.write_text(_e02_helper_shim(c,ROOT,shim)+'assert sys.argv[1:3]==["-B","-c"]\nexec(sys.argv[3],{"__name__":"__main__"})\n');shim.chmod(0o755)
    binary=_e02_compile_installed_control(c,ROOT,evidence)
    c.custody._close()  # Setup custody teardown, before the actual native owner.
    effect=tmp_path/'effect';stop=tmp_path/'release-native'
    environment={k:v for k,v in os.environ.items() if not k.startswith('KRONOS_NATIVE_SELECTION_')}
    if fault=='injected-selection':environment['KRONOS_NATIVE_SELECTION_PATH']=c.policy['installed_selection_path']
    if fault=='changed-artifact':(c.bundle/'Contents/Resources/KRONOS.png').write_bytes(b'foreign installed resource')
    if fault=='changed-source':(c.repository/'README.md').write_bytes(b'foreign source after activation')
    if fault=='substituted-anchor':c.anchor.rename(c.anchor.with_name('preserved-original-anchor'));c.anchor.mkdir(mode=0o700)
    if fault=='missing-history':(c.journal/'head-1.json').rename(c.case.root/'preserved-missing-genesis.json')
    argv=[str(binary),str(c.repository),str(shim),str(effect),str(stop),'hold' if fault=='concurrent' else fault]
    before={str(p.relative_to(c.anchor)):p.read_bytes() for p in c.anchor.rglob('*') if p.is_file()}
    process=None
    try:
        if fault=='concurrent':
            out=(evidence/'stdout.log').open('w');err=(evidence/'stderr.log').open('w')
            process=subprocess.Popen(argv,env=environment,stdout=out,stderr=err,text=True)
            deadline=time.monotonic()+20
            while not effect.exists():
                assert process.poll() is None,(evidence/'stderr.log').read_text()
                if time.monotonic()>=deadline:pytest.fail('native reserved effect missing')
                time.sleep(.002)
            second=subprocess.run(argv,env=environment,capture_output=True,text=True,timeout=10)
            assert second.returncode==0 and second.stdout=='CUSTODY_DENIED\n'
            stop.write_bytes(b'cooperative fixture release')
            code=process.wait(timeout=10);out.close();err.close()
            result=subprocess.CompletedProcess(argv,code,(evidence/'stdout.log').read_text(),(evidence/'stderr.log').read_text())
            (evidence/'concurrent-result.json').write_text(json.dumps(dict(actual_exit=second.returncode,stdout=second.stdout,stderr=second.stderr),indent=2)+'\n')
        else:result=subprocess.run(argv,env=environment,capture_output=True,text=True,timeout=60)
        (evidence/'command-result.json').write_text(json.dumps(dict(command=argv,actual_exit=result.returncode,
            stdout=result.stdout,stderr=result.stderr,simulated_device_delta=c.simulated_device_delta,
            actual_host_reboot=False,application_child=False,teardown_is_not_application_cleanup=True),indent=2)+'\n')
        assert result.returncode==0,result.stderr
        if fault in {'valid','old-device','concurrent'}:
            assert effect.read_bytes()==b'ONE_RESERVED_EFFECT'
            head=json.loads((c.journal/'admission-head.json').read_bytes());assert head['state']=='CHILD_START_RESERVED'
            assert len(list(c.journal.glob('original-*.json')))==2  # reservation + sole-fork intent, not two starts
            again=subprocess.run(argv,env=environment,capture_output=True,text=True,timeout=20)
            assert again.returncode==0 and 'HEAD_DENIED' in again.stdout
            (evidence/'replay-result.json').write_text(json.dumps(dict(actual_exit=again.returncode,stdout=again.stdout,stderr=again.stderr),indent=2)+'\n')
        else:
            assert not effect.exists()
            assert {str(p.relative_to(c.anchor)):p.read_bytes() for p in c.anchor.rglob('*') if p.is_file()}==before
        record_property('e02_native_application',json.dumps(dict(fault=fault,actual_c_and_readonly_helper=True,
            actual_attributes_and_lock=True,one_reserved_effect=fault in {'valid','old-device','concurrent'},application_child=False)))
    finally:
        if process is not None and process.poll() is None:
            stop.write_bytes(b'cooperative fixture release');process.wait(timeout=10)
        retained=evidence/'retained-runtime';retained.mkdir(exist_ok=True)
        for p in c.anchor.rglob('*'):
            if p.is_file():
                q=retained/p.relative_to(c.anchor);q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
        (evidence/'separate-fixture-teardown.json').write_text(json.dumps(dict(native_waited=True,application_cleanup_claimed=False),indent=2)+'\n')

def _e02_retain_selected_documents(c,evidence):
    """Retain exact fixture inputs before execution, never backfill old attempts."""
    import stat
    from hashlib import sha256
    from kronos.common import legacy_bootstrap as adapter
    target=evidence/'selected-inputs';target.mkdir()
    objects=target/'objects';objects.mkdir()
    rows=[];seen=set();pending=[]
    def scan(value):
        if isinstance(value,dict):
            if {'path','bytes','sha256'}<=set(value):pending.append(value)
            for child in value.values():scan(child)
        elif isinstance(value,list):
            for child in value:scan(child)
    for name,value in [('persistent-binding.json',adapter._canonical(c.persistent)),
                       ('ordinary-policy.json',adapter._canonical(c.policy)),
                       ('genesis-disposition.json',c.genesis)]:
        (target/name).write_bytes(value)
        scan(json.loads(value))
    for path in [c.source_manifest,c.artifact_manifest,Path(c.policy['installed_selection_path']),
                 Path(c.policy['installed_selection_path']).with_name('activation.json')]:
        raw=path.read_bytes();pending.append(dict(path=str(path),bytes=len(raw),sha256=sha256(raw).hexdigest()))
    while pending:
        ref=pending.pop();key=(ref['path'],ref['sha256'])
        if key in seen:continue
        seen.add(key);path=Path(ref['path']);raw=path.read_bytes();mode=stat.S_IMODE(path.stat().st_mode)
        assert len(raw)==ref['bytes'] and sha256(raw).hexdigest()==ref['sha256'],ref
        obj=objects/ref['sha256']
        if obj.exists():assert obj.read_bytes()==raw
        else:obj.write_bytes(raw);obj.chmod(mode)
        rows.append(dict(path=str(path),bytes=len(raw),sha256=ref['sha256'],mode=f'{mode:04o}',object=str(obj.relative_to(target))))
        try:parsed=json.loads(raw)
        except (UnicodeError,ValueError):continue
        scan(parsed)
    (target/'ORIGINAL-INPUT-INDEX.json').write_text(json.dumps(rows,indent=2)+'\n')


@pytest.mark.parametrize('disabled_pin',('persistent','ordinary'))
def test_e02_mixed_disabled_native_pin_cannot_reserve(tmp_path,monkeypatch,record_property,disabled_pin):
    """A gate result is not admission: fixed ordinary selection must deny."""
    from tests.unit.common import test_legacy_bootstrap as setup
    from tests.unit.common import test_failed_successor_restore as fixture
    from kronos.common import legacy_bootstrap as adapter
    from hashlib import sha256
    c=setup._e02_installed_control(tmp_path,monkeypatch)
    evidence=ROOT.parent/'qualification/e02-mixed-pin-evidence'/tmp_path.parents[1].name/tmp_path.name
    shim=tmp_path/'e02-helper-python'
    shim.write_text(_e02_helper_shim(c,ROOT,shim)+'assert sys.argv[1:3]==["-B","-c"]\nexec(sys.argv[3],{"__name__":"__main__"})\n');shim.chmod(0o755)
    binary=_e02_compile_installed_control(c,ROOT,evidence)
    # Only generated fixture pin population changes, before selected execution.
    source=(evidence/'e02-native.c').read_text()
    name='approved_persistent_binding' if disabled_pin=='persistent' else 'approved_ordinary_restart_policy'
    raw=adapter._canonical(c.persistent if disabled_pin=='persistent' else c.policy).decode()
    needle=name+' = '+json.dumps(raw)+';'
    assert source.count(needle)==1
    source=source.replace(needle,name+' = NULL;')
    unit=evidence/'mixed-pin-native.c';unit.write_text(source)
    argv=['clang','-Wall','-Wextra','-Werror',str(unit),'-o',str(binary)]
    result=subprocess.run(argv,capture_output=True,text=True)
    (evidence/'mixed-pin-build.json').write_text(json.dumps(dict(command=argv,actual_exit=result.returncode,
        stdout=result.stdout,stderr=result.stderr,source_sha256=sha256(unit.read_bytes()).hexdigest(),
        seam='ONLY ONE GENERATED STATIC PIN DISABLED; PRODUCTION FUNCTIONS UNCHANGED'),indent=2)+'\n')
    assert result.returncode==0,result.stderr
    shutil.copy2(binary,evidence/'mixed-pin-native')
    artifact=json.loads(c.artifact_manifest.read_bytes());rows=setup._c02_bundle_manifest(c.bundle);digest=sha256(binary.read_bytes()).hexdigest()
    artifact.update(bundle_manifest=rows,bundle_identity=sha256(adapter._canonical(rows)).hexdigest(),
        built_binary_sha256=digest,signed_binary_sha256=digest)
    c.artifact_manifest.write_bytes(adapter._canonical(artifact)+b'\n')
    c.selection['artifact_manifest']=fixture._ref(c.artifact_manifest,'e02-artifact',c.artifact_manifest.read_bytes())
    c.selection['target']=dict(c.selection['target'],artifact_manifest_sha256=c.selection['artifact_manifest']['sha256'])
    setup._e02_publish_control_activation(c)
    selected=evidence/'mixed-selected';selected.mkdir();_e02_retain_selected_documents(c,selected)
    c.custody._close();before={str(p.relative_to(c.anchor)):p.read_bytes() for p in c.anchor.rglob('*') if p.is_file()}
    command=[str(binary),str(c.repository),str(shim),str(tmp_path/'effect'),str(tmp_path/'stop'),'valid']
    observed=subprocess.run(command,capture_output=True,text=True,timeout=30)
    (evidence/'mixed-pin-outcome.json').write_text(json.dumps(dict(command=command,actual_exit=observed.returncode,
        stdout=observed.stdout,stderr=observed.stderr,disabled_native_pin=disabled_pin,
        python_pin_remains_populated=True,application_child=False),indent=2)+'\n')
    assert observed.returncode==0 and 'HEAD_DENIED' in observed.stdout,observed.stderr
    assert not (tmp_path/'effect').exists()
    assert {str(p.relative_to(c.anchor)):p.read_bytes() for p in c.anchor.rglob('*') if p.is_file()}==before
    retained=evidence/'retained-runtime';shutil.copytree(c.anchor,retained)
    (evidence/'separate-fixture-teardown.json').write_text(json.dumps(dict(actual_native_waited=True,
        no_application_child=True,application_cleanup_claimed=False),indent=2)+'\n')
    record_property('mixed_pin_boundary','ACTUAL_GATE_MAY_SUCCEED; FIXED_INSTALLED_SELECTION_DENIES_BEFORE_RESERVATION_OR_EFFECT')

# ORDER 83553: actual native/helper boundary, disposable authority/path/signature
# and synthetic retained-owner documents. No comparison or consumer is stubbed.
def _f01_pin_control(tmp_path,monkeypatch,mode,case_name,*,wire_action=None):
    from hashlib import sha256
    from kronos.common import legacy_bootstrap as b, release_admission as a, failed_successor_restore as r
    from tests.unit.common import test_legacy_bootstrap as setup
    from tests.unit.common import test_failed_successor_restore as fixture
    evidence=ROOT.parent/'qualification/f01-pin-evidence'/tmp_path.parents[1].name/tmp_path.name
    evidence.mkdir(parents=True)
    code_root=Path(os.environ.get('F01_REVIEWED_SOURCE_ROOT',str(ROOT)))
    if mode=='ADMISSION_HEAD_INITIALIZATION':
        old=_s304_compile_preparer(tmp_path,monkeypatch,source_root=code_root)
        anchor=old['anchor'];installation=old['installation'];base=old['case'].root
        repository=Path(old['args'][2]);bundle=Path(old['args'][3]);binary=Path(old['args'][0]);shim=Path(old['args'][4])
        selection_path=Path(old['env']['KRONOS_NATIVE_SELECTION_PATH'])
        selection=json.loads(selection_path.read_bytes());source=(old['evidence']/'preparer.c').read_text()
        environment=dict(old['env']);command=[*old['args'],'valid'];genesis=r.INITIALIZATION_DISPOSITION
        # The companion fixture's G is a source pin only in prepare-only mode;
        # it does not admit this fresh root, and no such admission is asserted.
        original_helper=shim.read_text()
    else:
        c=setup._c02_dispatch_case(tmp_path,monkeypatch);case=c['case'];base=case.root
        installation=json.loads(case.permit_path.read_bytes())['installation']
        anchor=Path(installation['anchor_path']);repository=c['repository'];bundle=c['bundle']
        binary=bundle/'Contents/MacOS/KRONOS';shim=base/'f01-helper-python';selection_path=base/'f01-selection.json'
        genesis=r.INITIALIZATION_DISPOSITION;environment=dict(os.environ)
        source=_fixture_native_source(code_root/'tools/macos/kronos_launcher.c').replace('int main(void) {','int preserved_operational_main(void) {')
        source=source.replace('static const dev_t approved_admission_device = 16777232;','static dev_t approved_admission_device = 0;')
        source=source.replace('static const ino_t approved_admission_inode = 694844364;','static ino_t approved_admission_inode = 0;')
        source+=r'''
int main(int argc,char **argv) {
 if(argc!=7)return 90;
 struct stat st;if(stat(argv[1],&st)!=0)return 91;
 admission_anchor=argv[1];canonical_bundle=argv[3];canonical_executable=argv[0];
 approved_admission_device=st.st_dev;approved_admission_inode=st.st_ino;
 admission_descriptor=acquire_installation_admission(argv[1],st.st_dev,st.st_ino);
 if(admission_descriptor<0)return 92;
 validation_deadline_ns=validation_now_ns()+120000000000LL;long long original=validation_deadline_ns;
 int accepted=native_gate(argv[2],argv[4],argv[5]);
 if(accepted && !strcmp(argv[6],"tamper-after-validation")) {
  int restoration=!strcmp(argv[5],"FAILED_SUCCESSOR_RESTORATION");
  accepted=native_select_environment() && native_validation(restoration?"restoration-reserve":"original-reserve",
      restoration?"":"f01-apply-reserve",restoration?"{}":"{\"predecessor\":null}",1);
  if(accepted) {
   char *field=strstr(native_startup.last_result,"\"boot_session\"");if(!field)return 95;
   field[1]='x';puts("F01_STORED_FRAME_MUTATED");accepted=native_apply_proposal();
  }
 } else if(accepted) {
  if(!strcmp(argv[5],"FAILED_SUCCESSOR_RESTORATION")) {
   accepted=native_select_environment() && native_validation("restoration-reserve","","{}",1) && native_apply_proposal();
  } else accepted=native_original_reserve(0);
 }
 fprintf(stderr,"F01_APPLICATION accepted=%d original_deadline=%lld final_deadline=%lld unresolved=%d\n",accepted,original,validation_deadline_ns,validation_cleanup_unresolved);
 if(original!=validation_deadline_ns)return 94;
 finish_admission();return accepted?0:1;
}
'''
        original_helper='#!'+sys.executable+'\nimport sys\nfrom pathlib import Path\nsys.path[:0]='+repr([str(code_root/'src'),str(code_root)])+'\nfrom kronos.common import legacy_bootstrap as b,release_admission as a,failed_successor_restore as r\nfrom hashlib import sha256\nif a.PERSISTENT_ANCHOR_BINDING is not None: assert sha256(a.PERSISTENT_ANCHOR_BINDING).hexdigest()=="85ea2fa04da20f40377b242d71db96762020e77042a7b4923c331c6f82ab7891"\na.PERSISTENT_ANCHOR_BINDING=None\na.CANONICAL_PARENT='+repr(str(binary))+'\nb._verify_bundle_signature=lambda *_:None\nassert sys.argv[1:3]==["-B","-c"]\nexec(sys.argv[3],{"__name__":"__main__"})\n'
        permit=json.loads(case.permit_path.read_bytes());now=datetime.now(UTC)
        decisions={}
        for label in ('sponsor','ca','pcp','product'):
            p=base/('f01-'+label+'.json');raw=fixture._put(p,{'fixture':'SYNTHETIC '+label+'; NO OPERATIONAL AUTHORITY'})
            decisions[label]=fixture._ref(p,'f01-'+label,raw)
        selection=dict(schema=b.NATIVE_SELECTION_SCHEMA,selection_id='f01-selection',mode=mode,
            installation=installation,target=permit['restoration_target'],source_manifest=fixture._ref(c['source_manifest'],'source',c['source_manifest'].read_bytes()),
            artifact_manifest=fixture._ref(c['artifact_manifest'],'artifact',c['artifact_manifest'].read_bytes()),
            operational_order=decisions['sponsor'],decisions=decisions,permit=None,
            valid_from=(now-timedelta(seconds=30)).isoformat(),valid_until=(now+timedelta(minutes=8)).isoformat())
        journal=anchor/'failed-successor-restore-v1'
        # Preserve the unexecuted restoration setup, then select a coherent
        # native phase after the retained, separately admitted genesis.
        shutil.copytree(journal,evidence/'unexecuted-original-setup')
        first=json.loads((journal/'head-1.json').read_bytes());first_raw=(journal/'head-1.json').read_bytes()
        phase=b._native_phase('f01-phase','NATIVE_ACTIVATED',original='f01-phase',installation=installation,
            parent=json.loads((journal/(first['active_reservation_id']+'.json')).read_bytes())['parent'],
            selected=None,predecessor=None,previous=None,details={},now=now)
        state='NATIVE_ACTIVATED';incident_id=None
        if mode==b.RESTORATION_MODE:
            # Genuine owned process terminal observations replace arbitrary
            # live PID guesses, without claiming historical production facts.
            dead=[]
            for index in range(2):
                proc=subprocess.Popen([sys.executable,'-c','import sys;print("OWNED",flush=True);sys.stdin.read(1);sys.exit('+str(78 if index else 0)+')'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
                assert proc.stdout.readline().strip()=='OWNED'
                birth=a.kernel_process_birth(proc.pid);proc.communicate('x',timeout=5)
                assert proc.returncode==(78 if index else 0);dead.append(dict(pid=proc.pid,kernel_birth=birth,actual_exit=proc.returncode))
            (evidence/'owned-historical-process-observations.json').write_text(json.dumps(dead,indent=2)+'\n')
            incident=json.loads(case.incident_path.read_bytes())
            incident['predecessor'].update({k:dead[0][k] for k in ('pid','kernel_birth')})
            incident['failed_successor'].update({k:dead[1][k] for k in ('pid','kernel_birth')})
            fixture._put(case.incident_path,incident)
            failure=json.loads(case.failure_path.read_bytes());failure['failed_successor']=incident['failed_successor']
            failure['parent_terminal'].update(child_pid=dead[1]['pid'],child_kernel_birth=dead[1]['kernel_birth'])
            fixture._put(case.failure_path,failure)
            retained=base/'f01-retained-owner-state';retained.mkdir(mode=0o700)
            p=retained/'committed.json';raw=fixture._put(p,{'fixture':'SYNTHETIC retained-state document; not canonical owner qualification'})
            scopes=[dict(path=str(retained),present=True)]
            rows=[dict(path=str(p),bytes=len(raw),sha256=sha256(raw).hexdigest(),mode=0o600)]
            settled=json.loads(case.settled_path.read_bytes())
            owner_path=base/'f01-owners.json';owner_raw=fixture._put(owner_path,dict(schema='KRONOS_NATIVE_CHILD_FACT_V1',phase='settled-owners',
                child=incident['failed_successor'],parent=incident['original_parent'],payload=dict(validated_current=True,notification_checkpoint=settled['notification_checkpoint'])))
            state_path=base/'f01-state.json';state_raw=fixture._put(state_path,dict(schema='KRONOS_NATIVE_CHILD_FACT_V1',phase='settled-state-files',
                child=incident['failed_successor'],parent=incident['original_parent'],original_attempt_id=incident['original_attempt_id'],
                payload=dict(owner_results=fixture._ref(owner_path,'f01-owners',owner_raw),scopes=scopes,files=rows)))
            state_ref=fixture._ref(state_path,'f01-state',state_raw)
            settled.update(state_manifest_identity='f01-state',state_manifest_sha256=state_ref['sha256'],owner_results_sha256=sha256(owner_raw).hexdigest())
            fixture._put(case.settled_path,settled)
            failure['settled_state']=fixture._ref(case.settled_path,settled['settled_state_id'],case.settled_path.read_bytes());fixture._put(case.failure_path,failure)
            permit['incident']=fixture._ref(case.incident_path,incident['incident_id'],case.incident_path.read_bytes())
            permit['settled_state']=fixture._ref(case.settled_path,settled['settled_state_id'],case.settled_path.read_bytes())
            permit['failure_cleanup']=fixture._ref(case.failure_path,failure['failure_cleanup_id'],case.failure_path.read_bytes())
            permit.update(valid_from=selection['valid_from'],valid_until=selection['valid_until'])
            for label,prefix in [('sponsor','sponsor_order'),('ca','ca_decision'),('pcp','pcp_decision'),('product','product_decision')]:
                permit['authority'][prefix+'_identity']=decisions[label]['identity'];permit['authority'][prefix+'_sha256']=decisions[label]['sha256']
            fixture._put(case.permit_path,permit)
            selection['permit']=fixture._ref(case.permit_path,permit['permit_id'],case.permit_path.read_bytes())
            phase.update(phase='INCIDENT_OPEN',original_attempt_id=incident['original_attempt_id'],details=dict(eligible_restoration=True,
                incident=permit['incident'],settled_state=permit['settled_state'],failure_cleanup=permit['failure_cleanup'],state_manifest=state_ref))
            state='INCIDENT_OPEN';incident_id=incident['incident_id']
        # The native roster also preserves the original genesis phase itself.
        phase_raw=fixture._put(journal/'f01-phase.json',phase)
        head=dict(first,sequence=2,state=state,incident_id=incident_id,active_reservation_id='f01-phase',
            active_reservation_sha256=sha256(phase_raw).hexdigest(),previous_head_sha256=sha256(first_raw).hexdigest(),recorded_at=now.isoformat())
        fixture._put(journal/'head-2.json',head);fixture._put(journal/'admission-head.json',head)
        command=[str(binary),str(anchor),str(repository),str(bundle),str(shim),mode]
        case.close()
    # Exact valid P/L bytes. Alternate enrollment locations give two otherwise
    # valid populated documents with unequal digests, not a wrong-volume denial.
    enrollment=base/'f01-enrollment.json';enrollment_raw=fixture._put(enrollment,installation)
    fd=os.open(anchor,os.O_RDONLY|os.O_DIRECTORY)
    try:observed=a.descriptor_filesystem_identity(fd)
    finally:os.close(fd)
    persistent=dict(schema='KRONOS_PERSISTENT_ANCHOR_BINDING_V1',installation_identity=installation['identity'],
        enrollment=fixture._ref(enrollment,installation['identity'],enrollment_raw),anchor_path=str(anchor),volume_uuid=observed['volume_uuid'],
        file_id=observed['file_id'],owner=os.getuid(),required_mode='0700',bundle_id=installation['bundle_id'],bundle_path=str(bundle),repository_path=str(repository))
    ordinary=dict(schema='ORDINARY_SAME_RELEASE_V1',scope='ORDINARY_SAME_RELEASE_WITH_QUALIFIED_STOP',installation_identity=installation['identity'],
        binding_sha256=sha256(b._canonical(persistent)).hexdigest(),genesis_disposition_sha256=sha256(genesis).hexdigest(),
        release_id='F01-EXPLICIT-SYNTHETIC-PIN-CONTROL',installed_selection_path=str(anchor/'ordinary-start-v1/installed-selection.json'))
    values={'persistent':b._canonical(persistent),'ordinary':b._canonical(ordinary),'genesis':genesis}
    native={k:None for k in values};python={k:None for k in values}
    if mode!='ADMISSION_HEAD_INITIALIZATION':native['genesis']=python['genesis']=genesis
    if case_name=='matched-enabled':native.update(values);python.update(values)
    elif case_name.startswith(('native-only-','python-only-','unequal-')):
        side,pin=case_name.rsplit('-',1)
        if side=='native-only':native[pin]=values[pin]
        elif side=='python-only':python[pin]=values[pin]
        else:
            native[pin]=python[pin]=values[pin]
            if pin=='persistent':
                other=base/'f01-alternate-enrollment.json';other.write_bytes(enrollment_raw);other.chmod(0o600)
                native[pin]=b._canonical(dict(persistent,enrollment=fixture._ref(other,installation['identity'],enrollment_raw)))
            else:native[pin]=values[pin]+b'\n'  # native exact-byte identity differs; Python retains its valid canonical pin
    names={'persistent':'approved_persistent_binding','ordinary':'approved_ordinary_restart_policy','genesis':'approved_initialization_disposition'}
    for pin,value in native.items():
        if value is not None:source=source.replace(names[pin]+' = NULL;',names[pin]+' = '+json.dumps(value.decode())+';')
    unit=evidence/'f01-native.c';unit.write_text(source)
    compile_command=['clang','-Wall','-Wextra','-Werror',str(unit),'-o',str(binary)]
    built=subprocess.run(compile_command,capture_output=True,text=True)
    (evidence/'compile.json').write_text(json.dumps(dict(command=compile_command,actual_exit=built.returncode,stdout=built.stdout,stderr=built.stderr,
        production_source_root=str(code_root),reviewed_source_sha256=sha256((code_root/'tools/macos/kronos_launcher.c').read_bytes()).hexdigest(),python_source_sha256=sha256((code_root/'src/kronos/common/legacy_bootstrap.py').read_bytes()).hexdigest(),generated_source_sha256=sha256(unit.read_bytes()).hexdigest()),indent=2)+'\n')
    assert built.returncode==0,built.stderr
    binary.chmod(0o755);shutil.copy2(binary,evidence/'f01-native')
    additions='from pathlib import Path\nfrom kronos.common import failed_successor_restore as r\n'
    additions+='a.APPROVED_BINDING=a.AnchorBinding(Path('+repr(str(anchor))+'),'+str(installation['device'])+','+str(installation['inode'])+','+str(installation['owner'])+')\n'
    additions+='a.PERSISTENT_ANCHOR_BINDING='+repr(python['persistent'])+'\nb.ORDINARY_RESTART_POLICY='+repr(python['ordinary'])+'\nr.INITIALIZATION_DISPOSITION='+repr(python['genesis'])+'\n'
    additions+='import json,os,traceback\n_original_f01=b.native_validation_result\ndef _record_f01(request):\n try:result=_original_f01(request)\n except BaseException:\n  Path('+repr(str(evidence))+',request["action"]+".failure.log").write_text(traceback.format_exc()[-8000:])\n  raise\n original=b._canonical(result)\n wire=dict(result)\n'
    fault=case_name if case_name.startswith(('missing-','wrong-','null-')) else None
    if wire_action is None:wire_action='initialization-prepare' if mode=='ADMISSION_HEAD_INITIALIZATION' else 'gate'
    key={'missing-persistent':'persistent_binding_sha256','missing-ordinary':'ordinary_policy_sha256','missing-genesis':'initialization_disposition_sha256','missing-boot':'boot_session'}.get(fault)
    if key:additions+=' if request["action"]=='+repr(wire_action)+':wire.pop('+repr(key)+',None)\n'
    if fault=='wrong-boot':additions+=' if request["action"]=='+repr(wire_action)+':wire["boot_session"]="00000000-0000-0000-0000-000000000001"\n'
    if fault=='null-boot':additions+=' if request["action"]=='+repr(wire_action)+':wire["boot_session"]=None\n'
    additions+=' record=dict(request=request,actual=result,wire=wire,actual_kernel_boot=a.kernel_boot_identity(),inherited_deadline_ns=os.environ.get("KRONOS_VALIDATION_DEADLINE_NS"))\n'
    additions+=' Path('+repr(str(evidence))+',request["action"]+".json").write_text(json.dumps(record,indent=2)+"\\n")\n return wire\nb.native_validation_result=_record_f01\n'
    original_helper=original_helper.replace('assert sys.argv',additions+'assert sys.argv')
    shim.write_text(original_helper);shim.chmod(0o755);shutil.copy2(shim,evidence/'helper-python')
    # Rebind only fixture manifests after the disposable binary is final.
    artifact_path=Path(selection['artifact_manifest']['path']);artifact=json.loads(artifact_path.read_bytes());rows=setup._c02_bundle_manifest(bundle)
    digest=sha256(binary.read_bytes()).hexdigest();artifact.update(bundle_manifest=rows,bundle_identity=sha256(b._canonical(rows)).hexdigest(),built_binary_sha256=digest,signed_binary_sha256=digest)
    artifact_path.write_bytes(b._canonical(artifact)+b'\n');selection['artifact_manifest']=fixture._ref(artifact_path,selection['artifact_manifest']['identity'],artifact_path.read_bytes())
    selection['target']['artifact_manifest_sha256']=selection['artifact_manifest']['sha256']
    if selection['permit'] is not None:
        path=Path(selection['permit']['path']);permit=json.loads(path.read_bytes());permit['restoration_target']=selection['target'];fixture._put(path,permit)
        selection['permit']=fixture._ref(path,permit['permit_id'],path.read_bytes())
    raw=fixture._put(selection_path,selection)
    for suffix,key in [('PATH','path'),('BYTES','bytes'),('SHA256','sha256'),('ID','identity')]:
        environment['KRONOS_NATIVE_SELECTION_'+suffix]=str(fixture._ref(selection_path,selection['selection_id'],raw)[key])
    if mode!='ADMISSION_HEAD_INITIALIZATION':command.append('unused')
    inputs=evidence/'input-objects';inputs.mkdir();references=[];pending=[selection,persistent]
    while pending:
        v=pending.pop()
        if isinstance(v,dict):
            if {'path','bytes','sha256'}<=set(v):
                p=Path(v['path']);data=p.read_bytes();assert len(data)==v['bytes'] and sha256(data).hexdigest()==v['sha256']
                dest=inputs/v['sha256']
                if not dest.exists():
                    dest.write_bytes(data);dest.chmod(p.stat().st_mode&0o777)
                    try:pending.append(json.loads(data))
                    except (ValueError,UnicodeError):pass
                references.append(dict(v,mode=oct(p.stat().st_mode&0o777)))
            pending.extend(v.values())
        elif isinstance(v,list):pending.extend(v)
    for label,values_pin in [('native',native),('python',python)]:
        for pin,value in values_pin.items():
            if value is not None:(evidence/(label+'-'+pin+'.json')).write_bytes(value)
    (evidence/'input-index.json').write_text(json.dumps(references,indent=2)+'\n')
    return dict(command=command,env=environment,evidence=evidence,anchor=anchor,native=native,python=python,mode=mode,case_name=case_name)


def _f01_run_and_retain(c):
    import fcntl
    from hashlib import sha256
    journal=c['anchor']/'failed-successor-restore-v1'
    before={p.name:p.read_bytes() for p in journal.iterdir()} if journal.exists() else {}
    observed=subprocess.run(c['command'],env=c['env'],capture_output=True,text=True,timeout=35)
    after={p.name:p.read_bytes() for p in journal.iterdir()} if journal.exists() else {}
    retained=c['evidence']/'retained-primary';retained.mkdir()
    for p in journal.iterdir() if journal.exists() else []:shutil.copy2(p,retained/p.name)
    (c['evidence']/'application-outcome.json').write_text(json.dumps(dict(command=c['command'],actual_exit=observed.returncode,
        stdout=observed.stdout,stderr=observed.stderr,mode=c['mode'],case=c['case_name'],head_unchanged=before==after,
        before={k:sha256(v).hexdigest() for k,v in before.items()},after={k:sha256(v).hexdigest() for k,v in after.items()},
        claims=list(journal.glob('*.child-claimed.json')).__len__() if journal.exists() else 0,
        seams='COMPONENT ENTRY, SYNTHETIC AUTHORITY/OWNER RECORDS, PRIVATE CANONICAL PATH, SIGNATURE; ACTUAL NATIVE/PYTHON VALIDATION AND WRITERS'),indent=2)+'\n')
    fd=os.open(c['anchor'],os.O_RDONLY|os.O_DIRECTORY)
    try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    finally:os.close(fd)
    (c['evidence']/'separate-fixture-outcome.json').write_text(json.dumps(dict(native_process_waited=True,independent_lock_available_after_exit=True,
        application_cleanup_claimed=False,fixture_teardown='Only pytest disposable roots after primary retention'),indent=2)+'\n')
    return observed,before,after


_F01_MODES=('ADMISSION_HEAD_INITIALIZATION','GOVERNED_REPLACEMENT','FAILED_ACTIVE_RECOVERY_REPLACEMENT','FAILED_SUCCESSOR_RESTORATION')
_F01_CASES=('matched-disabled','matched-enabled','native-only-persistent','python-only-persistent','unequal-persistent',
    'native-only-ordinary','python-only-ordinary','unequal-ordinary','missing-persistent','missing-ordinary','missing-genesis','missing-boot','wrong-boot','null-boot')

@pytest.mark.parametrize('mode',_F01_MODES)
def test_f01_reviewed_fixture_controls(tmp_path,monkeypatch,mode):
    c=_f01_pin_control(tmp_path,monkeypatch,mode,'matched-disabled')
    result,before,after=_f01_run_and_retain(c)
    assert result.returncode==0,result.stderr
    assert before!=after

@pytest.mark.parametrize('mode',_F01_MODES)
@pytest.mark.parametrize('case_name',_F01_CASES)
def test_f01_symmetric_native_helper_agreement(tmp_path,monkeypatch,record_property,mode,case_name):
    from hashlib import sha256
    c=_f01_pin_control(tmp_path,monkeypatch,mode,case_name)
    result,before,after=_f01_run_and_retain(c)
    positive=case_name.startswith('matched-')
    assert result.returncode==(0 if positive else 1),result.stderr
    assert (before!=after) is positive
    if positive:
        calls=list(c['evidence'].glob('*.json'))
        for p in calls:
            data=json.loads(p.read_bytes())
            if 'actual_kernel_boot' not in data:continue
            actual=data['actual']
            for pin,key in [('persistent','persistent_binding_sha256'),('ordinary','ordinary_policy_sha256'),('genesis','initialization_disposition_sha256')]:
                value=c['python'][pin];assert key in actual and actual[key]==(sha256(value).hexdigest() if value is not None else None)
            assert actual['boot_session']==data['actual_kernel_boot']
    assert not list((c['anchor']/'failed-successor-restore-v1').glob('*.child-claimed.json'))
    record_property('f01_boundary','ACTUAL NATIVE HELPER AND JOURNAL WRITERS; NO APPLICATION CHILD; SYNTHETIC AUTHORITY/STATE FIXTURES')

@pytest.mark.parametrize('pin',('genesis',))
@pytest.mark.parametrize('side',('native-only','python-only','unequal'))
def test_f01_initialization_genesis_pin_agreement(tmp_path,monkeypatch,pin,side):
    c=_f01_pin_control(tmp_path,monkeypatch,'ADMISSION_HEAD_INITIALIZATION',side+'-'+pin)
    result,before,after=_f01_run_and_retain(c)
    assert result.returncode==1,result.stderr
    assert before==after=={}

@pytest.mark.parametrize('mode',_F01_MODES)
@pytest.mark.parametrize('fault',('missing-persistent','missing-ordinary','missing-genesis','missing-boot','wrong-boot'))
def test_f01_late_response_still_requires_agreement(tmp_path,monkeypatch,mode,fault):
    action='initialization-recheck' if mode=='ADMISSION_HEAD_INITIALIZATION' else 'restoration-reserve' if mode=='FAILED_SUCCESSOR_RESTORATION' else 'original-reserve'
    c=_f01_pin_control(tmp_path,monkeypatch,mode,fault,wire_action=action)
    result,before,after=_f01_run_and_retain(c)
    assert result.returncode==1,result.stderr
    assert 'PREPARED_PENDING_EXACT_ADMISSION_REVIEW' not in result.stdout
    assert (c['evidence']/(action+'.json')).exists()  # actual validated proposal reached the boundary
    if mode=='ADMISSION_HEAD_INITIALIZATION':
        assert before=={} and len(after)==4  # earlier valid preparation remains permanently retained
        again=subprocess.run(c['command'],env=c['env'],capture_output=True,text=True,timeout=35)
        assert again.returncode==1 and after=={p.name:p.read_bytes() for p in (c['anchor']/'failed-successor-restore-v1').iterdir()}
        (c['evidence']/'subsequent-initializer-denied.json').write_text(json.dumps(dict(actual_exit=again.returncode,stdout=again.stdout,stderr=again.stderr),indent=2)+'\n')
    else:assert before==after
    assert not list((c['anchor']/'failed-successor-restore-v1').glob('*.child-claimed.json'))

@pytest.mark.parametrize('mode',_F01_MODES[1:])
def test_f01_apply_rechecks_retained_response_before_writes(tmp_path,monkeypatch,mode):
    c=_f01_pin_control(tmp_path,monkeypatch,mode,'matched-disabled')
    c['command'][-1]='tamper-after-validation'
    result,before,after=_f01_run_and_retain(c)
    assert result.returncode==1 and 'F01_STORED_FRAME_MUTATED' in result.stdout,result.stderr
    assert before==after
