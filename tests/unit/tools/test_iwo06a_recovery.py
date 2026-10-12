"""Versioned historical-expiry recovery shares the existing one-use path."""
from copy import deepcopy
import hashlib
import json
import re
import subprocess

import pytest
from tests.unit.tools.test_canonical_launcher import SOURCE, compile_source, _failed_active_scope_documents
from tests.unit.tools.test_failed_active_successor import exact_successor
from tests.unit.intraday.test_live_shadow_epoch_deterministic_digest import production_case
from tools.failed_active_successor import verify_documents

END=1791771633006722
PREDECESSOR='37c9dc94ccbbfd35b78c3dfa7c0369a7f41b0df3'
CAPABILITY='WO06H-CAPABILITY-f61cfe6c7395d0ee8554d82946a5a7fa88444c09151f53bc171253a3d35aa31b'


@pytest.fixture(scope='module')
def history_probe(tmp_path_factory):
    root=tmp_path_factory.mktemp('historical-recovery').resolve()
    installed=root/'installed.app';installed.mkdir()
    files={}
    source=SOURCE.read_text().replace('int main(void) {','int unused_application_main(void) {')
    source=source.replace('static const char *canonical_bundle = "/Applications/KRONOS.app";',
        'static const char *canonical_bundle = '+json.dumps(str(installed))+';')
    for name in ('relation','diagnosis','sponsor'):
        path=root/name;path.write_text('isolated-'+name)
        files[name]=(str(path),hashlib.sha256(path.read_bytes()).hexdigest())
        if name!='sponsor':source=re.sub(r'#define RECOVERY_HISTORY_'+name.upper()+r' "[^"]+"',
            '#define RECOVERY_HISTORY_'+name.upper()+' "'+files[name][1]+'"',source)
    source+=r'''
int main(int argc,char **argv) {
    RecoveryAuthorization a={0};
    if(argc==5) {
        printf("%d\n",recovery_load_authorization(argv[1],argv[2],argv[3],18089,argv[4],RECOVERY_END_US+1,&a));return 0;
    }
    if(argc==4) {
        char runtime[BACKEND_STATUS_RESPONSE_BYTES],status[BACKEND_STATUS_RESPONSE_BYTES],intraday[BACKEND_STATUS_RESPONSE_BYTES];
        if(!recovery_read_file(argv[1],runtime,sizeof(runtime),0) || !recovery_read_file(argv[2],status,sizeof(status),0) ||
            !recovery_read_file(argv[3],intraday,sizeof(intraday),0))return 2;
        a.historical=1;a.pid=18089;strcpy(a.predecessor,RECOVERY_HISTORY_PREDECESSOR);memset(a.maintenance,'a',64);
        printf("%d\n",recovery_runtime_matches(&a,runtime,status,intraday));return 0;
    }
    return 3;
}
'''
    binary=root/'probe';compile_source(source,binary)
    return binary,installed,files


@pytest.mark.parametrize('fault',[None,'v1','before_expiry','expired','future','long','pid','predecessor',
    'capability','relation','diagnosis','research_state','window','unknown','duplicate'])
def test_exact_historical_authorization(history_probe,tmp_path,fault):
    binary,installed,files=history_probe
    root=tmp_path.resolve();root.chmod(0o700)
    control=root/'control';control.write_text('KRONOS_BROWSER_BACKEND_CONTROL_V1\n18089\n'+'d'*64+'\n');control.chmod(0o600)
    rollback=root/'rollback.app';rollback.mkdir()
    doc=dict(schema='KRONOS-FAILED-ACTIVE-RECOVERY-AUTHORIZATION/2.0.0',recovery_class='FAILED_ACTIVE_RECOVERY_REPLACEMENT',
        research_state='HISTORICAL_ACCEPTANCE_EXPIRED',state='SPONSOR_APPROVED',attempt_identity='a'*64,
        sponsor_authorization_reference='ISOLATED-EXACT',sponsor_authorization_path=files['sponsor'][0],sponsor_authorization_sha256=files['sponsor'][1],
        predecessor_pid=18089,predecessor_revision=PREDECESSOR,successor_revision='b'*40,
        expected_successor_capability=CAPABILITY,compatibility_relation_sha256=files['relation'][1],diagnosis_sha256=files['diagnosis'][1],
        window_start='2026-09-12T07:50:33.006722+05:30',window_end='2026-10-12T07:50:33.006722+05:30',
        predecessor_maintenance_identity='a'*64,private_control_sha256=hashlib.sha256(control.read_bytes()).hexdigest(),
        installed_package_identity='b'*64,rollback_bundle=str(rollback),rollback_package_identity='c'*64,
        relation_path=files['relation'][0],diagnosis_path=files['diagnosis'][0],valid_from_us=END,valid_until_us=END+1800000000)
    changes={'v1':('schema','KRONOS-FAILED-ACTIVE-RECOVERY-AUTHORIZATION/1.0.0'),
        'before_expiry':('valid_from_us',END-1),'expired':('valid_until_us',END+1),'future':('valid_from_us',END+2),
        'long':('valid_until_us',END+1800000001),'pid':('predecessor_pid',18090),'predecessor':('predecessor_revision','c'*40),
        'capability':('expected_successor_capability','OTHER'),'relation':('compatibility_relation_sha256','0'*64),
        'diagnosis':('diagnosis_sha256','0'*64),'research_state':('research_state','ACTIVE'),
        'window':('window_end','2099-01-01T00:00:00+00:00'),'unknown':('unknown',True)}
    if fault in changes:doc[changes[fault][0]]=changes[fault][1]
    raw=json.dumps(doc)
    if fault=='duplicate':raw=raw[:-1]+',"research_state":"HISTORICAL_ACCEPTANCE_EXPIRED"}'
    path=root/('a'*64+'.authorization.json');path.write_text(raw);path.chmod(0o600)
    assert subprocess.check_output([str(binary),str(root),'a'*64,str(control),'b'*40],text=True).strip()==('1' if fault is None else '0')


@pytest.mark.parametrize('fault',[None,'old_incident','wrong_failure','ready','provider','owner','revision','pid'])
def test_historical_predecessor_scope(history_probe,tmp_path,fault):
    binary,_,_=history_probe
    runtime,status,intraday=_failed_active_scope_documents()
    runtime['process'].update(pid=18089,revision=PREDECESSOR)
    intraday['live_shadow']['failure']='SHADOW_RESTORATION_WINDOW_NOT_ACTIVE'
    if fault=='old_incident':intraday['live_shadow']['failure']='SHADOW_RESTORATION_RUNTIME_INCOMPATIBLE'
    elif fault=='wrong_failure':intraday['live_shadow']['failure']='CORRUPT'
    elif fault=='ready':status['runtime_ready']=True
    elif fault=='provider':runtime['provider_runtime']['retained_lease_count']=1
    elif fault=='owner':runtime['maintenance_drain']['owners']['UNKNOWN']=1
    elif fault=='revision':runtime['process']['revision']='0'*40
    elif fault=='pid':runtime['process']['pid']=18090
    paths=[]
    for n,doc in enumerate((runtime,status,intraday)):
        path=tmp_path.resolve()/str(n);path.write_text(json.dumps(doc));paths.append(str(path))
    assert subprocess.check_output([str(binary),*paths],text=True).strip()==('1' if fault is None else '0')


@pytest.mark.parametrize('fault',[None,'active','enabled','accepted','schema','evidence','collection','counts','failure','window'])
def test_successor_requires_explicit_historical_truth(exact_successor,fault):
    documents,record,expected=deepcopy(exact_successor)
    shadow=documents[2]['live_shadow'];shadow.update(runtime_accepted=False,enabled=False,
        acceptance_disposition='HISTORICAL_ACCEPTANCE_EXPIRED',historical_restoration='KRONOS-WO06H-HISTORICAL-RESTORATION/1.0.0',
        historical_evidence='READABLE',collection_authority='EXPIRED')
    shadow['counts'].update(cohort_a=1,cohort_b=18,eod_available=0)
    if fault=='active':shadow['acceptance_disposition']='EXISTING_ACCEPTANCE_RESTORED'
    elif fault=='enabled':shadow['enabled']=True
    elif fault=='accepted':shadow['runtime_accepted']=True
    elif fault=='schema':shadow['historical_restoration']='UNKNOWN'
    elif fault=='evidence':shadow['historical_evidence']='NOT_ESTABLISHED'
    elif fault=='collection':shadow['collection_authority']='ACTIVE'
    elif fault=='counts':shadow['counts']['cohort_b']=19
    elif fault=='failure':shadow['failure']='CORRUPT'
    elif fault=='window':shadow['window']['end']='2099-01-01T00:00:00+00:00'
    if fault is None:verify_documents(documents,record,**expected,research_state='HISTORICAL_ACCEPTANCE_EXPIRED')
    else:
        with pytest.raises(ValueError):verify_documents(documents,record,**expected,research_state='HISTORICAL_ACCEPTANCE_EXPIRED')
