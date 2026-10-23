"""Closed Swing release recovery: real C predicates, disposable process boundaries.

These probes never execute the production launcher main or contact a runtime.
The lifecycle probe compiles the unchanged main body with every effect replaced.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest

from tests.unit.tools.test_canonical_launcher import (
    SOURCE, compile_source, _failed_active_scope_documents,
)

INCIDENT = 'KRONOS-SWING-FAILED-ACTIVE-AND-FENCED-RECOVERY-ENGINEERING-20261022'
PREDECESSORS = (
    '355922f92f7b826191ae86bd7bb0473349f3c1cc',
    '1579f1cbad2f98370b62f5511a7d339c131ab15a',
)
FAILURES = (
    'ACCEPTANCE_RESTORATION_NOT_ESTABLISHED',
    'SWING_RESTORATION_NOT_ESTABLISHED',
    'RUNTIME_RESTORATION_PROOF_UNAVAILABLE',
    'WO11_RESTORATION_FAILED',
    'WO17_RESTORATION_FAILED',
    'STARTUP_COMPLETION_RECORD_UNAVAILABLE',
)
NOW = 1792600000000000


@pytest.fixture(scope='module')
def release_authorization_probe(tmp_path_factory):
    root = tmp_path_factory.mktemp('release-authorization-c').resolve()
    installed = root/'installed.app'
    installed.mkdir()
    source = SOURCE.read_text().replace('int main(void) {', 'int unused_application_main(void) {')
    source = source.replace('static const char *canonical_bundle = "/Applications/KRONOS.app";',
        'static const char *canonical_bundle = '+json.dumps(str(installed))+';')
    source += r'''
int main(int argc,char **argv) {
    if(argc!=6)return 2;
    RecoveryAuthorization a={0};
    long long now=strtoll(argv[5],NULL,10);
    int accepted=recovery_load_authorization(argv[1],argv[2],argv[3],4242,argv[4],now,&a);
    printf("%d",accepted);
    if(accepted){
        char generation[65]={0};memset(generation,'e',64);
        printf(" %d",recovery_reserve(&a,generation,now));
        printf(" %d",recovery_attempt_matches(&a,generation));
        printf(" %d",recovery_reserve(&a,generation,now));
    }
    puts("");return 0;
}
'''
    binary = root/'probe'
    compile_source(source, binary)
    return binary, installed


def _release_authority(root, installed):
    root.chmod(0o700)
    control = root/'control'
    control.write_text('KRONOS_BROWSER_BACKEND_CONTROL_V1\n4242\n'+'d'*64+'\n')
    control.chmod(0o600)
    rollback = root/'rollback.app'
    rollback.mkdir()
    files = {}
    for name in ('sponsor', 'diagnosis', 'artifact_review'):
        path = root/name
        path.write_text('isolated '+name+' fixture')
        path.chmod(0o600)
        files[name] = (str(path), hashlib.sha256(path.read_bytes()).hexdigest())
    # This probe isolates C byte-binding admission. The mandatory Python receipt
    # semantics are exercised separately; fixture strings are never review proof.
    authority = dict(
        schema='KRONOS-SWING-RELEASE-RECOVERY-AUTHORIZATION/1.0.0',
        recovery_class='FAILED_ACTIVE_RECOVERY_REPLACEMENT', incident_id=INCIDENT,
        state='SPONSOR_APPROVED', attempt_identity='a'*64,
        sponsor_authorization_reference='ISOLATED-RELEASE-REVIEW',
        sponsor_authorization_path=files['sponsor'][0], sponsor_authorization_sha256=files['sponsor'][1],
        predecessor_pid=4242, predecessor_revision=PREDECESSORS[0], predecessor_start_us=NOW-1000,
        predecessor_maintenance_identity='f'*64, private_control_sha256=hashlib.sha256(control.read_bytes()).hexdigest(),
        installed_package_identity='b'*64, rollback_bundle=str(rollback), rollback_package_identity='c'*64,
        successor_revision='b'*40, expected_successor_capability='WO06H-CAPABILITY-'+'c'*64,
        expected_startup_failure=FAILURES[1], diagnosis_path=files['diagnosis'][0], diagnosis_sha256=files['diagnosis'][1],
        artifact_review_path=files['artifact_review'][0], artifact_review_sha256=files['artifact_review'][1],
        valid_from_us=NOW-1, valid_until_us=NOW+1799999999)
    return authority, control


@pytest.mark.parametrize('predecessor', PREDECESSORS)
@pytest.mark.parametrize('failure', FAILURES)
def test_closed_release_authority_and_one_use(release_authorization_probe, tmp_path, predecessor, failure):
    binary, installed = release_authorization_probe
    root = tmp_path.resolve()
    authority, control = _release_authority(root, installed)
    authority.update(predecessor_revision=predecessor, expected_startup_failure=failure)
    path = root/('a'*64+'.authorization.json')
    path.write_text(json.dumps(authority)); path.chmod(0o600)
    args = [str(binary), str(root), 'a'*64, str(control), 'b'*40, str(NOW)]
    assert subprocess.check_output(args, text=True).strip() == '1 1 1 0'
    before = (root/('a'*64+'.attempt.json')).read_bytes()
    assert subprocess.check_output(args, text=True).strip() == '1 0 0 0'
    assert (root/('a'*64+'.attempt.json')).read_bytes() == before


@pytest.mark.parametrize('fault', [
    'schema', 'class', 'incident', 'state', 'attempt', 'predecessor', 'pid', 'pid_type',
    'start', 'start_future', 'maintenance', 'control', 'installed', 'rollback_identity',
    'rollback_same', 'rollback_link', 'revision', 'same_revision', 'capability', 'capability_short',
    'failure', 'provider_failure', 'transport_failure', 'fenced_failure', 'sponsor', 'diagnosis',
    'review', 'review_public', 'future', 'expired', 'long', 'before_history', 'duplicate', 'unknown',
    'missing', 'root_public', 'auth_public', 'auth_link', 'control_public', 'preexisting_attempt',
])
def test_release_c_authorization_rejects_unbound_or_ambiguous_authority(release_authorization_probe, tmp_path, fault):
    binary, installed = release_authorization_probe
    root = tmp_path.resolve()
    authority, control = _release_authority(root, installed)
    changes = {
        'schema': ('schema', 'KRONOS-IWO07R3-RECOVERY-AUTHORIZATION/1.0.0'),
        'class': ('recovery_class', 'NORMAL_REPLACEMENT'), 'incident': ('incident_id', 'OTHER'),
        'state': ('state', 'PENDING'), 'attempt': ('attempt_identity', 'c'*64),
        'predecessor': ('predecessor_revision', '0'*40), 'pid': ('predecessor_pid', 4243),
        'pid_type': ('predecessor_pid', '4242'), 'start': ('predecessor_start_us', 0),
        'start_future': ('predecessor_start_us', NOW), 'maintenance': ('predecessor_maintenance_identity', 'unknown'),
        'control': ('private_control_sha256', '0'*64), 'installed': ('installed_package_identity', 'unknown'),
        'rollback_identity': ('rollback_package_identity', 'unknown'), 'rollback_same': ('rollback_bundle', str(installed)),
        'revision': ('successor_revision', 'c'*40), 'same_revision': ('successor_revision', PREDECESSORS[0]),
        'capability': ('expected_successor_capability', 'OTHER-'+'c'*64),
        'capability_short': ('expected_successor_capability', 'WO06H-CAPABILITY-'+'c'*63),
        'failure': ('expected_startup_failure', 'OTHER'), 'provider_failure': ('expected_startup_failure', 'PROVIDER_RETAINED'),
        'transport_failure': ('expected_startup_failure', 'TRANSPORT_RETAINED'),
        'fenced_failure': ('expected_startup_failure', 'FAILED_FENCED'),
        'sponsor': ('sponsor_authorization_sha256', '0'*64), 'diagnosis': ('diagnosis_sha256', '0'*64),
        'review': ('artifact_review_sha256', '0'*64), 'future': ('valid_from_us', NOW+1),
        'expired': ('valid_until_us', NOW), 'long': ('valid_until_us', NOW+1800000000),
        'before_history': ('valid_from_us', 1791771633006721), 'unknown': ('extra', True),
    }
    if fault in changes:
        key, value = changes[fault]; authority[key] = value
    if fault == 'missing': del authority['artifact_review_path']
    if fault == 'root_public': root.chmod(0o755)
    if fault == 'control_public': control.chmod(0o644)
    if fault == 'review_public': (root/'artifact_review').chmod(0o644)
    if fault == 'rollback_link':
        link = root/'rollback-link.app'; link.symlink_to(authority['rollback_bundle'])
        authority['rollback_bundle'] = str(link)
    raw = json.dumps(authority)
    if fault == 'duplicate': raw = raw[:-1]+',"incident_id":'+json.dumps(INCIDENT)+'}'
    path = root/('a'*64+'.authorization.json')
    if fault == 'auth_link':
        actual = root/'actual'; actual.write_text(raw); actual.chmod(0o600); path.symlink_to(actual)
    else:
        path.write_text(raw); path.chmod(0o644 if fault == 'auth_public' else 0o600)
    if fault == 'preexisting_attempt':
        attempt = root/('a'*64+'.attempt.json'); attempt.write_text('partial reservation'); attempt.chmod(0o600)
    target = PREDECESSORS[0] if fault == 'same_revision' else 'b'*40
    result = subprocess.check_output([str(binary), str(root), 'a'*64, str(control), target, str(NOW)], text=True).strip()
    assert result == ('1 0 0 0' if fault == 'preexisting_attempt' else '0')
    if fault == 'preexisting_attempt': assert attempt.read_text() == 'partial reservation'
    else: assert not (root/('a'*64+'.attempt.json')).exists()


@pytest.fixture(scope='module')
def release_runtime_probe(tmp_path_factory):
    root = tmp_path_factory.mktemp('release-runtime-c')
    source = SOURCE.read_text().replace('int main(void) {', 'int unused_application_main(void) {')
    source += r'''
int main(int argc,char **argv) {
    if(argc!=6)return 2;
    char r[BACKEND_STATUS_RESPONSE_BYTES],s[BACKEND_STATUS_RESPONSE_BYTES],d[BACKEND_STATUS_RESPONSE_BYTES];
    if(!recovery_read_file(argv[1],r,sizeof(r),0) || !recovery_read_file(argv[2],s,sizeof(s),0) ||
       !recovery_read_file(argv[3],d,sizeof(d),0))return 2;
    RecoveryAuthorization a={0};a.swing_release=1;a.pid=4242;
    strcpy(a.predecessor,argv[4]);memset(a.maintenance,'f',64);strcpy(a.startup_failure,argv[5]);
    printf("%d\n",recovery_runtime_matches(&a,r,s,d));return 0;
}
'''
    binary = root/'probe'; compile_source(source, binary)
    return binary


def _release_documents(predecessor=PREDECESSORS[0], failure=FAILURES[1]):
    runtime, status, intraday = deepcopy(_failed_active_scope_documents())
    runtime['process'].update(pid=4242, revision=predecessor)
    for doc in (runtime, status): doc['maintenance'].update(generation='f'*64, failure=failure)
    intraday['live_shadow'].update(failure=None, acceptance_disposition='HISTORICAL_ACCEPTANCE_EXPIRED',
        historical_restoration='KRONOS-WO06H-HISTORICAL-RESTORATION/1.0.0', historical_evidence='READABLE',
        collection_authority='EXPIRED', enabled=False,
        window=dict(start='2026-09-12T07:50:33.006722+05:30', end='2026-10-12T07:50:33.006722+05:30'),
        counts=dict(cohort_a=1, cohort_b=18, eod_available=0))
    return runtime, status, intraday


def _probe_documents(binary, tmp_path, documents, predecessor=PREDECESSORS[0], failure=FAILURES[1]):
    paths = []
    for i, document in enumerate(documents):
        path = tmp_path.resolve()/str(i); path.write_text(json.dumps(document)); paths.append(str(path))
    return subprocess.check_output([str(binary), *paths, predecessor, failure], text=True).strip()


@pytest.mark.parametrize('predecessor', PREDECESSORS)
@pytest.mark.parametrize('failure', FAILURES)
def test_failed_active_blocked_release_preserves_counted_admission(release_runtime_probe, tmp_path, predecessor, failure):
    documents = _release_documents(predecessor, failure)
    assert documents[0]['maintenance']['state'] == 'FAILED_ACTIVE'
    assert documents[0]['maintenance']['startup'] == 'BLOCKED'
    assert _probe_documents(release_runtime_probe, tmp_path, documents, predecessor, failure) == '1'


@pytest.mark.parametrize('fault', [
    'failed_fenced', 'claimed', 'drain_failed', 'drain_generation', 'undrainable', 'state', 'not_blocked',
    'maintenance', 'failure', 'status_failure', 'pid', 'revision', 'dirty', 'ready', 'provider', 'provider_lease',
    'provider_cleanup', 'unknown_owner', 'uncounted_wo11', 'incomplete_wo11', 'analysis', 'monitoring',
    'bulk', 'housekeeping', 'shadow_failure', 'active_acceptance', 'enabled', 'historical_unreadable',
    'active_collection', 'restamped_window', 'changed_count', 'missing_history',
])
def test_release_denies_fenced_uncertain_and_nonhistorical_runtime_without_mutation(release_runtime_probe, tmp_path, fault):
    r, s, d = _release_documents()
    if fault == 'failed_fenced': r['maintenance_drain'].update(state='FAILED_FENCED', failure='DRAIN_TIMEOUT')
    elif fault == 'claimed': r['maintenance_drain']['state'] = 'FENCED'
    elif fault == 'drain_failed': r['maintenance_drain']['failure'] = 'CLEANUP_FAILED'
    elif fault == 'drain_generation': r['maintenance_drain']['generation'] = 'c'*64
    elif fault == 'undrainable': r['maintenance_claim'] = 'BLOCKED'
    elif fault == 'state': r['maintenance']['state'] = 'INACTIVE'
    elif fault == 'not_blocked': r['maintenance']['startup'] = 'READY'
    elif fault == 'maintenance': s['maintenance']['generation'] = 'c'*64
    elif fault == 'failure': r['maintenance']['failure'] = FAILURES[0]
    elif fault == 'status_failure': s['maintenance']['failure'] = FAILURES[0]
    elif fault == 'pid': r['process']['pid'] += 1
    elif fault == 'revision': r['process']['revision'] = '0'*40
    elif fault == 'dirty': r['process']['source_state'] = 'DIRTY'
    elif fault == 'ready': s['runtime_ready'] = True
    elif fault == 'provider': s['provider'] = 'CONNECTED'
    elif fault == 'provider_lease': r['provider_runtime']['retained_lease_count'] = 1
    elif fault == 'provider_cleanup': r['provider_runtime']['cleanup_state'] = 'UNKNOWN'
    elif fault == 'unknown_owner': r['maintenance_drain']['owners']['UNKNOWN'] = 1
    elif fault == 'uncounted_wo11': r['intraday_wo11_work'].update(state='RUNNING', owned_workers=1, generation=3)
    elif fault == 'incomplete_wo11': r['intraday_wo11_work']['continuity'] = 'UNKNOWN'
    elif fault == 'analysis': r['analysis_execution']['owned_workers'] = 1
    elif fault == 'monitoring': r['monitoring']['session_count'] = 1
    elif fault == 'bulk': r['swing_bulk_import']['batch_active'] = True
    elif fault == 'housekeeping': r['housekeeping']['shutdown_requested'] = True
    elif fault == 'shadow_failure': d['live_shadow']['failure'] = 'CORRUPT'
    elif fault == 'active_acceptance': d['live_shadow']['runtime_accepted'] = True
    elif fault == 'enabled': d['live_shadow']['enabled'] = True
    elif fault == 'historical_unreadable': d['live_shadow']['historical_evidence'] = 'UNREADABLE'
    elif fault == 'active_collection': d['live_shadow']['collection_authority'] = 'ACTIVE'
    elif fault == 'restamped_window': d['live_shadow']['window']['end'] = '2099-01-01T00:00:00+00:00'
    elif fault == 'changed_count': d['live_shadow']['counts']['cohort_b'] += 1
    elif fault == 'missing_history': del d['live_shadow']['historical_restoration']
    documents = r, s, d
    before = deepcopy(documents)
    assert _probe_documents(release_runtime_probe, tmp_path, documents) == '0'
    assert documents == before


@pytest.mark.parametrize('owner', ['WO11', 'WO17'])
def test_release_allows_only_counted_supported_worker_drain(release_runtime_probe, tmp_path, owner):
    documents = _release_documents()
    runtime = documents[0]
    runtime['intraday_'+owner.lower()+'_work'].update(state='RUNNING', owned_workers=1, queued_items=2, generation=3)
    runtime['maintenance_drain']['owners'][owner] = 1
    assert _probe_documents(release_runtime_probe, tmp_path, documents) == '1'


def test_release_pid_reuse_rejected_by_kernel_start_identity(tmp_path):
    source = SOURCE.read_text().replace('int main(void) {', 'int unused_application_main(void) {')
    source += r'''
int main(void) {
    RecoveryAuthorization a={0};struct proc_bsdinfo info;a.pid=getpid();
    if(proc_pidinfo(a.pid,PROC_PIDTBSDINFO,0,&info,sizeof(info))!=(int)sizeof(info))return 2;
    a.predecessor_start_us=(long long)info.pbi_start_tvsec*1000000+(long long)info.pbi_start_tvusec;
    printf("%d ",recovery_release_process_start(&a));
    a.predecessor_start_us++;printf("%d ",recovery_release_process_start(&a));
    a.pid=0;printf("%d\n",recovery_release_process_start(&a));return 0;
}
'''
    binary = tmp_path/'kernel-identity'; compile_source(source, binary)
    assert subprocess.check_output([str(binary)], text=True).strip() == '1 0 0'


@pytest.fixture(scope='module')
def release_orchestration_probe(tmp_path_factory):
    root = tmp_path_factory.mktemp('release-orchestration')
    original = SOURCE.read_text()
    source = original.replace('int main(void) {', 'int unused_application_main(void) {')
    source += r'''
static const char *fault;
static int assesses=0,continuities=0,bindings=0,handoffs=0,packages=0;
static int shutdowns=0,starts=0,reservations=0;
static int step(const char *name,int result){printf("%s\n",name);return strcmp(fault,name)?result:0;}
static int fake_control(pid_t *pid,char *token){*pid=4242;memset(token,'d',64);token[64]=0;return step("control",1);}
static int fake_authority(RecoveryAuthorization *a){
    memset(a,0,sizeof(*a));a->swing_release=1;a->pid=4242;
    strcpy(a->predecessor,RECOVERY_RELEASE_PREDECESSOR);strcpy(a->successor,"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb");
    memset(a->package,'b',64);memset(a->rollback_identity,'c',64);strcpy(a->rollback,"/disposable/rollback.app");
    strcpy(a->relation,"/disposable/independent-artifact-review.json");
    a->valid_from=RECOVERY_END_US;a->valid_until=RECOVERY_END_US+RECOVERY_HISTORY_MAX_VALIDITY_US;
    return step("authorization",1);
}
static int fake_package(char *out){packages++;memset(out,packages==1?'b':'c',64);out[64]=0;return step(packages==1?"installed":"rollback",1);}
static int fake_assess(void){return step(++assesses==1?"assess_initial":"assess_final",1);}
static int fake_continuity(void){return step(++continuities==1?"continuity_before":"continuity_after",1);}
static int fake_binding(void){return step(++bindings==1?"bindings_before":"bindings_after",1);}
static int fake_handoff(void){return step(++handoffs==1?"handoff_initial":"handoff_final",1);}
static int fake_reserve(void){reservations++;return step("reserve",1);}
static int fake_shutdown(void){shutdowns++;return step("shutdown",1);}
static int fake_absence(void){if(!strcmp(fault,"pid_alive"))return 0;errno=!strcmp(fault,"ownership_unknown")?EPERM:ESRCH;return -1;}
static BackendStartResult fake_start(void){
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
#define recovery_assess(a,repository,python) fake_assess()
#define connect_backend() open("/dev/null",O_RDONLY)
#define recovery_continuity(repository,python,home,generation) fake_continuity()
#define recovery_bindings_match(a,repository,python,proof) fake_binding()
#define recovery_reserve(a,generation,now) fake_reserve()
#define request_graceful_shutdown(pid,token,generation,v2) fake_shutdown()
#define wait_for_backend_stop(pid) step("exit",1)
#define verify_v2_handoff(repository,python,path,control,generation,pid,revision,proof) fake_handoff()
#define recovery_attempt_matches(a,generation) step("attempt_readback",1)
#define kill(pid,signal) fake_absence()
#define recovery_listener_scan(pid,absent) step("listener_absent",1)
#define recovery_now_us() (!strcmp(fault,"authority_expired")?RECOVERY_END_US+RECOVERY_HISTORY_MAX_VALIDITY_US:RECOVERY_END_US+1)
#define start_backend(repository,python,entry,path,pid,token,generation,revision) fake_start()
#define open_workspace() (step("open",1),0)
#define show_restart_blocked() (step("blocked",1),1)
#define show_alert(title,message) 1
#define show_replacement_child_exited() 1
#define show_replacement_ready_timeout() 1
#define show_replacement_internal_failure() 1
'''
    source += 'int exercise_main(void) {'+original.split('int main(void) {', 1)[1]
    source += r'''
int main(int argc,char **argv){
    if(argc!=2)return 2;fault=argv[1];
    setenv("KRONOS_LAUNCH_MODE",RECOVERY_CLASS,1);
    setenv("KRONOS_RECOVERY_ATTEMPT","aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",1);
    setenv("KRONOS_REPLACEMENT_REVISION","bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",1);
    int result=exercise_main();printf("COUNTS %d %d %d %d\n",result,reservations,shutdowns,starts);return 0;
}
'''
    binary = root/'probe'; compile_source(source, binary)
    return binary


@pytest.mark.parametrize('fault', [
    'none', 'canonical', 'source', 'target', 'control', 'authorization', 'installed', 'rollback',
    'assess_initial', 'continuity_before', 'assess_final', 'bindings_before', 'reserve', 'shutdown',
    'exit', 'handoff_initial', 'continuity_after', 'bindings_after', 'attempt_readback', 'handoff_final',
    'pid_alive', 'ownership_unknown', 'listener_absent', 'authority_expired', 'child_exit', 'timeout', 'internal',
])
def test_release_actual_main_preserves_one_use_drain_handoff_and_one_start(release_orchestration_probe, fault):
    lines = subprocess.check_output([str(release_orchestration_probe), fault], text=True).splitlines()
    result, reservations, shutdowns, starts = map(int, lines[-1].split()[1:])
    assert reservations <= 1 and shutdowns <= 1 and starts <= 1
    if fault == 'none':
        assert (result, reservations, shutdowns, starts) == (0, 1, 1, 1)
        assert lines.index('source') < lines.index('control') < lines.index('assess_initial')
        assert lines.index('continuity_before') < lines.index('bindings_before') < lines.index('reserve') < lines.index('shutdown')
        assert lines.index('shutdown') < lines.index('exit') < lines.index('handoff_initial') < lines.index('continuity_after')
        assert lines.index('bindings_after') < lines.index('attempt_readback') < lines.index('handoff_final')
        assert lines.index('handoff_final') < lines.index('listener_absent') < lines.index('start') < lines.index('open')
    else:
        assert result == 1 and 'open' not in lines
        assert starts == (1 if fault in ('child_exit', 'timeout', 'internal') else 0)
        if fault in ('canonical', 'source', 'target', 'control', 'authorization', 'installed', 'rollback',
                     'assess_initial', 'continuity_before', 'assess_final', 'bindings_before', 'reserve'):
            assert shutdowns == 0
        if fault in ('shutdown', 'exit', 'handoff_initial', 'continuity_after', 'bindings_after',
                     'attempt_readback', 'handoff_final', 'pid_alive', 'ownership_unknown', 'listener_absent', 'authority_expired'):
            assert reservations == 1 and starts == 0


@pytest.fixture(scope='module')
def release_helper_probe(tmp_path_factory):
    root = tmp_path_factory.mktemp('release-helper-protocol').resolve()
    source = SOURCE.read_text().replace('int main(void) {', 'int unused_application_main(void) {')
    source += r'''
int main(int argc,char **argv){
    if(argc!=4)return 2;RecoveryAuthorization a={0};
    strcpy(a.file,"/disposable/authorization.json");memset(a.digest,'a',64);memset(a.successor,'b',40);
    char generation[65]={0};memset(generation,'c',64);
    printf("%d\n",recovery_release_verify(&a,argv[1],argv[2],argv[3],
        strcmp(argv[3],"retired")?"[{}, {}, {}]":NULL,generation,4242));return 0;
}
'''
    binary = root/'probe'; compile_source(source, binary)
    return binary


@pytest.mark.parametrize('phase', ['preflight', 'retired', 'successor'])
@pytest.mark.parametrize('outcome', ['valid', 'old_marker', 'invalid', 'extra', 'exit_failure'])
def test_release_helper_is_mandatory_and_uses_distinct_protocol(release_helper_probe, tmp_path, phase, outcome):
    import sys
    root = tmp_path.resolve()
    home = Path(os.environ['HOME'])  # Argument construction only; the fixture helper opens no runtime paths.
    marker = {
        'valid': 'KRONOS_SWING_RELEASE_RECOVERY_V1 VALID\n',
        'old_marker': 'KRONOS_IWO07R3_RECOVERY_V1 VALID\n',
        'invalid': 'KRONOS_SWING_RELEASE_RECOVERY_V1 INVALID\n',
        'extra': 'KRONOS_SWING_RELEASE_RECOVERY_V1 VALID\nextra\n',
        'exit_failure': 'KRONOS_SWING_RELEASE_RECOVERY_V1 VALID\n',
    }[outcome]
    expected = ['-B', 'tools/failed_active_successor.py', '--release-phase', phase,
        '--authorization', '/disposable/authorization.json', '--authorization-sha256', 'a'*64,
        '--revision', 'b'*40, '--generation', 'c'*64, '--pid', '4242',
        '--maintenance-root', str(home/'Library/Application Support/KRONOS/runtime/maintenance'),
        '--evidence-root', str(home/'Library/Application Support/KRONOS/evidence')]
    script = root/'helper'
    script.write_text('#!'+sys.executable+'\nimport sys\n'
        +'assert sys.argv[1:] == '+repr(expected)+'\n'
        +'assert sys.stdin.read() == '+repr('' if phase == 'retired' else '[{}, {}, {}]')+'\n'
        +'sys.stdout.write('+repr(marker)+')\n'
        +'raise SystemExit('+('2' if outcome == 'exit_failure' else '0')+')\n')
    script.chmod(0o700)
    assert subprocess.check_output([str(release_helper_probe), str(root), str(script), phase], text=True).strip() == (
        '1' if outcome == 'valid' else '0')
