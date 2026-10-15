#!/usr/bin/env python3
"""TE-09R2 bounded genuine-path proof. No chart/Question/Answer operations.

Stdlib supervisor runs outside the test sandbox (macOS cannot nest profiles).
Genuine names are used read-only for ancestry checks. Runtime state and all
write/no-clobber/attack controls use a fresh disposable root. No credential data.
"""
from argparse import ArgumentParser
from datetime import datetime, timezone
import hashlib
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import runpy
import select
import signal
import socket
import subprocess
import sys
import tempfile

REPOSITORY=Path(__file__).resolve().parents[1]


def inventory(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def main():
    parser=ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    tool=runpy.run_path(str(REPOSITORY/'tools/theta_trial.py'),run_name='supervisor')
    root=Path(tempfile.mkdtemp(prefix='theta-te09r2-')).resolve()
    runtime=root/'runtime';support=runtime/'support'
    runtime.mkdir(mode=0o700);support.mkdir(mode=0o700)
    for name in ('home','tmp'):(support/name).mkdir(mode=0o700)
    inbox=root/'answers';outbox=root/'questions'
    inbox.mkdir(mode=0o700);outbox.mkdir(mode=0o700)
    probe=support/'kernel-denial-probe';probe.write_bytes(b'TE09R2 DENIAL CONTROL\n');probe.chmod(0o600)
    genuine_inbox=tool['SPONSOR']/'CHATGPT ANSWERS'
    genuine_outbox=tool['SPONSOR']/'KRONOS QUESTIONS'
    before={str(p):inventory(p) for p in (genuine_inbox,genuine_outbox,tool['GENUINE_ROOT'],
             tool['RETAINED_CHART_ROOT']/'populated/evidence',tool['PREVIEW_ROOT']/'evidence')}
    env={k:v for k,v in os.environ.items() if k in {'PATH','LANG','LC_ALL','LC_CTYPE','USER','LOGNAME'}}
    env.update(TMPDIR=str(support/'tmp'),PYTHON_DOTENV_DISABLED='1',PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1')
    with socket.socket() as blocked, socket.socket() as reservation:
        blocked.bind(('127.0.0.1',0));blocked.listen(1)
        reservation.bind(('127.0.0.1',0));port=reservation.getsockname()[1];reservation.close()
        assert port not in {8947,8948,8968,8970}
        raw=tool['policy'](runtime,genuine_inbox,genuine_outbox,port,probe)
        profile=support/'genuine-path-policy.sb';profile.write_text(raw)
        paths={'runtime':str(runtime),'inbox':str(genuine_inbox),'outbox':str(genuine_outbox),
               'genuine_root':str(tool['GENUINE_ROOT']),'sponsor':str(tool['SPONSOR']),
               'repo':str(REPOSITORY),'home':str(tool['REAL_HOME']),
               'retained':str(tool['RETAINED_CHART_ROOT']),'preview':str(tool['PREVIEW_ROOT'])}
        # No actual Sponsor content reads/writes. Exact ancestor metadata and
        # no-follow directory opens; actual Answer writeability queried only.
        code='''import json,os,runpy,sys
from pathlib import Path
p=json.loads(sys.argv[1]);m=runpy.run_path(p['repo']+'/tools/theta_trial.py',run_name='proof')
a=m['arguments'](['--mode','GENUINE_TRIAL','--root',p['genuine_root'],'--inbox',p['inbox'],'--outbox',p['outbox'],'--port','8970','--child'])
m['preflight'](a)
Path.home=classmethod(lambda cls:cls(Path(p['runtime'])/'support/home'))
sys.path.insert(0,p['repo']+'/src')
from kronos.theta.operational import TrialPaths
TrialPaths(Path(p['genuine_root']),Path(p['inbox']),Path(p['outbox']),'GENUINE_TRIAL').validate()
opened=[]
for target in (Path(p['sponsor']).parent,Path(p['sponsor']),Path(p['inbox']),Path(p['outbox'])):
 target.lstat();fd=os.open(target,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);os.close(fd);opened.append(str(target))
assert not os.access(p['inbox'],os.W_OK)
assert os.access(p['outbox'],os.W_OK)
denied=[]
for target in (Path(p['sponsor']).parent/'SWING',Path(p['sponsor']).parent/'Intraday',Path(p['sponsor']).parent/'Support Charts',Path(p['home'])/'Library/Keychains',Path(p['home'])/'Library/Application Support/KRONOS',Path(p['retained'])/'populated/evidence',Path(p['preview'])/'evidence'):
 try:os.open(target,os.O_RDONLY|os.O_NOFOLLOW)
 except PermissionError:denied.append(str(target))
 else:raise AssertionError('unauthorized read was not denied')
print(json.dumps({'actual_genuine_preflight':'PASS','operational_path_validation':'PASS','exact_ancestor_opens':opened,'actual_answer_write_access':False,'actual_question_write_access':True,'denied_paths':denied}))
'''
        proof=subprocess.run(['/usr/bin/sandbox-exec','-f',str(profile),sys.executable,'-I','-B','-c',code,json.dumps(paths)],
                              env=env,cwd=REPOSITORY,capture_output=True,text=True,timeout=30)
        assert proof.returncode==0,proof.stderr
        report={'status':'PASS','verified_at':datetime.now(timezone.utc).isoformat(),
                'root':str(root),'port':port,'actual_path_proof':json.loads(proof.stdout)}
        # Identical policy grammar with surrogate frozen paths for all data and
        # destructive operation negatives. No genuine file is an attack fixture.
        review=root/'SURROGATE-REVIEW';si=review/'Theta Earners/CHATGPT ANSWERS';so=review/'Theta Earners/KRONOS QUESTIONS'
        for p in (si,so,review/'Other',review/'Theta Earners/Other'):p.mkdir(mode=0o700,parents=True,exist_ok=True)
        control=si/'expected.json';control.write_bytes(b'CONTROL')
        (review/'Other/control').write_bytes(b'CONTROL')
        (review/'Theta Earners/Other/control').write_bytes(b'CONTROL')
        forged=si/'foreign.json';forged.symlink_to(review/'Other/control')
        profile2=support/'surrogate-policy.sb'
        profile2.write_text(raw.replace(str(tool['SPONSOR'].parent),str(review)))
        negative='''import json,os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1]+'/src')
from kronos.theta.store import directory,read_at,write_at
review=Path(sys.argv[2]);si=review/'Theta Earners/CHATGPT ANSWERS';so=review/'Theta Earners/KRONOS QUESTIONS'
assert (si/'expected.json').read_bytes()==b'CONTROL'
checks=[]
for p,flags in ((si/'NEW',os.O_CREAT|os.O_EXCL|os.O_WRONLY),(si/'expected.json',os.O_WRONLY),(review/'Other/control',os.O_RDONLY),(review/'Theta Earners/Other/control',os.O_RDONLY)):
 try:fd=os.open(p,flags,0o600)
 except PermissionError:checks.append('DENIED:'+p.name)
 else:os.close(fd);raise AssertionError('unauthorized access allowed')
for action in (lambda:os.unlink(si/'expected.json'),lambda:os.rename(si/'expected.json',si/'renamed.json')):
 try:action()
 except PermissionError:checks.append('ANSWER_DELETE_RENAME_DENIED')
 else:raise AssertionError('Answer mutation allowed')
with directory(si) as fd:
 try:read_at(fd,'foreign.json')
 except OSError:checks.append('EXPECTED_ANSWER_SYMLINK_DENIED')
 else:raise AssertionError('symlink consumed')
 try:read_at(fd,'../Other/control')
 except ValueError:checks.append('FOREIGN_EXPECTED_ANSWER_PATH_DENIED')
 else:raise AssertionError('traversal consumed')
with directory(so,create=True) as fd:
 write_at(fd,'CONTROL.json',b'CONTROL')
 write_at(fd,'CONTROL.json',b'CONTROL')
 try:write_at(fd,'CONTROL.json',b'CONFLICT')
 except ValueError:checks.append('GOVERNED_NO_CLOBBER_PASS')
 else:raise AssertionError('overwrite')
 assert read_at(fd,'CONTROL.json')==b'CONTROL'
print(json.dumps({'checks':checks,'answer_unchanged':True,'outbox_exact_governed_write':True}))
'''
        proof2=subprocess.run(['/usr/bin/sandbox-exec','-f',str(profile2),sys.executable,'-I','-B','-c',negative,str(REPOSITORY),str(review)],
                               env=env,cwd=REPOSITORY,capture_output=True,text=True,timeout=30)
        assert proof2.returncode==0,proof2.stderr
        assert control.read_bytes()==b'CONTROL'
        report['negative_and_publication_proof']=json.loads(proof2.stdout)
        # All four same-named path components are attack fixtures only. They
        # are rejected under the same kernel policy and unchanged no-follow
        # traversal, without ever replacing a Sponsor path.
        attacks=[]
        for component in ('KRONOS REVIEW PACK','Theta Earners','KRONOS QUESTIONS','CHATGPT ANSWERS'):
            attack_root=support/('attack-'+component.replace(' ','-'));attack_root.mkdir(mode=0o700)
            attack_review=attack_root/'KRONOS REVIEW PACK';attack_sponsor=attack_review/'Theta Earners'
            ai=attack_sponsor/'CHATGPT ANSWERS';ao=attack_sponsor/'KRONOS QUESTIONS'
            ai.mkdir(mode=0o700,parents=True);ao.mkdir(mode=0o700)
            selected={'KRONOS REVIEW PACK':attack_review,'Theta Earners':attack_sponsor,
                      'KRONOS QUESTIONS':ao,'CHATGPT ANSWERS':ai}[component]
            moved=attack_root/'moved';selected.rename(moved);selected.symlink_to(moved,target_is_directory=True)
            attack_code='''import os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1]+'/src')
from kronos.theta.store import directory
try:
 with directory(Path(sys.argv[2])):pass
except OSError:print('NOFOLLOW_REJECTED')
else:raise AssertionError('symlink followed')
'''
            outcome=subprocess.run(['/usr/bin/sandbox-exec','-f',str(profile),sys.executable,'-I','-B','-c',attack_code,str(REPOSITORY),str(ai if component=='CHATGPT ANSWERS' else ao)],
                                   env=env,cwd=REPOSITORY,capture_output=True,text=True,timeout=30)
            assert outcome.returncode==0 and outcome.stdout.strip()=='NOFOLLOW_REJECTED',outcome.stderr
            attacks.append(component)
        report['kernel_nofollow_symlink_components_rejected']=attacks
        # Real operational child and genuine-path policy, with disposable
        # runtime/inbox/outbox and no originals manifest. No new runtime mode,
        # authority override or production enrollment is introduced.
        bootstrap='''import runpy,sys
m=runpy.run_path(sys.argv[1],run_name='bounded_rehearsal')
raise SystemExit(m['main'](sys.argv[2:]))
'''
        # Disposable outbox is outside the runtime root by the frozen path
        # contract. Only this test-owned directory needs an additional write
        # exception. Genuine Question/Answer paths and ancestor rules are exact
        # unchanged policy bytes; no Sponsor write operation is invoked.
        rehearsal_profile=support/'rehearsal-policy.sb'
        rehearsal_profile.write_text(raw+'\n(allow file-write* (subpath '+json.dumps(str(outbox))+'))\n')
        command=['/usr/bin/sandbox-exec','-f',str(rehearsal_profile),sys.executable,'-I','-B','-c',bootstrap,
                 str(REPOSITORY/'tools/theta_trial.py'),'--child','--mode','SYNTHETIC_REHEARSAL',
                 '--root',str(runtime),'--inbox',str(inbox),'--outbox',str(outbox),
                 '--port',str(port),'--denied-port',str(blocked.getsockname()[1])]
        proc=subprocess.Popen(command,env=env,cwd=REPOSITORY,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        worker=None;log=[]
        try:
            assert select.select([proc.stdout],[],[],40)[0],'startup timeout'
            line=proc.stdout.readline();log.append(line)
            if not line.startswith('{'):
                remainder,_=proc.communicate(timeout=10);log.append(remainder)
                raise AssertionError(''.join(log))
            ready=json.loads(line);assert ready['status']=='READY',line
            worker=ready['pid'];report['startup']=ready
            assert ready['qualification_mode'] is False and ready['target_count']==10
            before_get=inventory(runtime/'evidence')
            for route in ('/theta-earners','/theta-earners/new-analysis'):
                c=HTTPConnection('127.0.0.1',port,timeout=15)
                try:
                    c.request('GET',route);response=c.getresponse();page=response.read()
                    assert response.status==200 and b'SYNTHETIC' in page
                finally:c.close()
            # Initial GET may initialize the empty selection; it must never
            # commission charts/Questions/Answers. Repeat reads are inert.
            after_get=inventory(runtime/'evidence')
            for name in after_get:
                assert not name.startswith(('charts/','chart-revisions/','v3-questions/','v3-batches/','v3-imports/'))
            assert not list(inbox.iterdir()) and not list(outbox.iterdir())
            report['empty_runtime_only']=True
            c=HTTPConnection('127.0.0.1',port,timeout=15)
            try:c.request('GET','/theta-earners/new-analysis');response=c.getresponse();assert response.status==200;response.read()
            finally:c.close()
            assert inventory(runtime/'evidence')==after_get
            report['repeat_get_inert']=True
        finally:
            if worker is not None:os.kill(worker,signal.SIGTERM)
            elif proc.poll() is None:proc.terminate()
            tail,_=proc.communicate(timeout=20);log.append(tail)
            if worker is None:print('REHEARSAL_STARTUP_FAILURE:'+''.join(log),file=sys.stderr)
        assert proc.returncode==0,''.join(log)
        assert '"provider_calls": 0' in ''.join(log) and '"broker_operations": 0' in ''.join(log)
        report['shutdown']=''.join(log);report['runtime_stopped']=True
        assert before=={name:inventory(Path(name)) for name in before}
        report['protected_inventories_unchanged']=True
        report['genuine_chart_admissions']=0;report['genuine_questions']=0;report['answer_imports']=0
        args.output.mkdir(mode=0o700,parents=True,exist_ok=True)
        (args.output/'GENUINE-PATH-REHEARSAL.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))


if __name__=='__main__':main()
