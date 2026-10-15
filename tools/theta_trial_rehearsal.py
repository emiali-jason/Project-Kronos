#!/usr/bin/env python3
"""TE-09R disposable operational-policy proof. Stdlib supervisor, no KRONOS imports.

Only controlled synthetic pixels/research enter the trial. The worker admits
actual retained authority/methodology. Never supplies synthetic authority.
All input/output/evidence directories are substitutes under a new temp root.
"""
from argparse import ArgumentParser
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import hashlib
from http.client import HTTPConnection
from io import BytesIO
import json
import os
from pathlib import Path
import re
import select
import signal
import socket
import subprocess
import sys
import tempfile
from urllib.parse import urlencode
from zipfile import ZipFile

from PIL import Image,ImageDraw

REPOSITORY=Path(__file__).resolve().parents[1]
SUBJECTS=('GOLDM','SILVERM','COPPER','CRUDEOIL','NATURALGAS')


def request(port,method,path,body=None,content_type='application/x-www-form-urlencoded',origin=None,host=None):
    c=HTTPConnection('127.0.0.1',port,timeout=30)
    headers={'Host':host or f'127.0.0.1:{port}'}
    if method=='POST':headers.update(Origin=origin or f'http://127.0.0.1:{port}',**{'Content-Type':content_type})
    try:
        c.request(method,path,body=body,headers=headers);r=c.getresponse();return r.status,r.read()
    finally:c.close()


@contextmanager
def running(root,port,manifest=None):
    command=[sys.executable,'-B',str(REPOSITORY/'tools/theta_trial.py'),
        '--mode','SYNTHETIC_REHEARSAL','--root',str(root/'runtime'),
        '--inbox',str(root/'answers'),'--outbox',str(root/'questions'),'--port',str(port)]
    if manifest:command+=['--originals-manifest',str(manifest),'--sponsor-confirmed-originals']
    p=subprocess.Popen(command,
        stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    log=[];worker=None
    try:
        assert select.select([p.stdout],[],[],35)[0],'startup timeout'
        line=p.stdout.readline();log.append(line)
        assert '"status": "READY"' in line,line
        worker=json.loads(line)['pid']
        yield log
    finally:
        if worker is not None:os.kill(worker,signal.SIGTERM)
        try:tail,_=p.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            p.terminate();tail,_=p.communicate(timeout=5)
        log.append(tail)
        assert p.returncode==0,''.join(log)
        assert '"provider_calls": 0' in ''.join(log),''.join(log)


def record(path):
    return json.loads(path.read_bytes())['value']


def operation(evidence):
    selected=record(evidence/'current.json')
    return record(evidence/'v3-browser-operations'/(selected['v3_import_operation']+'.json'))['result']


def inventory(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def policy_proof(root,port):
    # Exercise the genuine Review Pack exception geometry with disposable
    # substitute paths. No genuine file is probed or permissions changed.
    sys.path.insert(0,str(REPOSITORY))
    from tools import theta_trial as tool
    review=root/'SURROGATE-REVIEW-PACK';inbox=review/'Theta/CHATGPT ANSWERS';outbox=review/'Theta/KRONOS QUESTIONS'
    for p in (inbox,outbox,review/'Other') :p.mkdir(mode=0o700,parents=True,exist_ok=True)
    (inbox/'input.json').write_bytes(b'UNCHANGED');(review/'Other/retained').write_bytes(b'UNCHANGED')
    secret=root/'SURROGATE-KEYCHAINS';secret.mkdir(mode=0o700);(secret/'control').write_bytes(b'NOT A CREDENTIAL')
    raw=tool.policy(root/'runtime',inbox,outbox,port,root/'runtime/support/kernel-denial-probe')
    raw=raw.replace(str(tool.REAL_HOME/'Documents/Project-KRONOS/KRONOS REVIEW PACK'),str(review))
    raw=raw.replace(str(tool.REAL_HOME/'Library/Keychains'),str(secret))
    profile=root/'runtime/support/surrogate-policy.sb';profile.write_text(raw)
    code='''import os,json,sys
from pathlib import Path
inbox,outbox,other,secret=map(Path,sys.argv[1:])
assert (inbox/'input.json').read_bytes()==b'UNCHANGED'
for path,mode in ((inbox/'input.json','wb'),(other/'retained','rb'),(secret/'control','rb')):
 try: open(path,mode).close()
 except PermissionError: pass
 else: raise AssertionError('denial missing')
cursor=Path('/')
for part in outbox.parts[1:]:
 cursor=cursor/part
 try: os.mkdir(cursor,0o700)
 except FileExistsError: pass
with open(outbox/'NEW-CONTROL','xb') as stream:stream.write(b'CONTROL')
try:open(outbox/'NEW-CONTROL','xb')
except FileExistsError:pass
else:raise AssertionError('clobber')
print(json.dumps({'answer_read_only':True,'unrelated_review_denied':True,'credential_surrogate_denied':True,'nested_no_clobber_publication':True}))
'''
    result=subprocess.run(['/usr/bin/sandbox-exec','-f',str(profile),sys.executable,'-I','-B','-c',code,
        str(inbox),str(outbox),str(review/'Other'),str(secret)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert (inbox/'input.json').read_bytes()==b'UNCHANGED'
    return json.loads(result.stdout)


def answer(template,questions,*,invalid=None):
    # Research is a retained portable synthetic fixture, not a preview store,
    # provider input, authority record, receipt or selection document.
    # PLC-01: construct controlled research from the governed source fixture;
    # do not import a historical operational Answer/closure-output artifact.
    sys.path.insert(0,str(REPOSITORY));sys.path.insert(0,str(REPOSITORY/'src'))
    from tests.unit.theta.v3_fixture import synthetic_contracts
    fixture=synthetic_contracts()[2]
    value=deepcopy(template);value['answer_package_id']='SYNTHETIC-TE09R-'+('PARTIAL' if invalid else 'COMPLETE')
    now=datetime.now(timezone.utc)
    ranges={'GOLDM':('119000.00','126500.00'),'SILVERM':('145000.00','162500.00'),
        'COPPER':('910.50','985.750'),'CRUDEOIL':('5700.00','6450.00'),'NATURALGAS':('255.50','315.250')}
    for subject,child in value['answers'].items():
        old=fixture['answers'][subject];t0=datetime.fromisoformat(questions[subject]['information_cutoff'])
        child.update(answer_id='SYNTHETIC-TE09R-'+subject,analyzed_at=now.isoformat(),
            analyst=deepcopy(old['analyst']),research=deepcopy(old['research']))
        for obs in child['research']['chart_observations']:
            obs['chart_reference']=deepcopy(child['binding']['commodity_chart']);obs['visible_as_of']=None
        for source in child['research']['sources']:
            source.update(available_at=(t0-timedelta(seconds=1)).isoformat(),accessed_at=now.isoformat())
        for event in child['research']['scheduled_events']:
            event['schedule_known_at']=t0.isoformat()
            if event.get('scheduled_window'):
                event['scheduled_window']={'start':(t0+timedelta(days=1)).isoformat(),'end':(t0+timedelta(days=1,hours=1)).isoformat()}
        for horizon,f in child['forecasts'].items():
            f.update({k:deepcopy(v) for k,v in old['forecasts'][horizon].items() if k!='target'})
            f.update(lower=ranges[subject][0],upper=ranges[subject][1],confidence_pct='82.00' if horizon=='E1' else '78.25')
    if invalid:value['answers'][invalid]['forecasts']['E1']['confidence_pct']='101'
    return json.dumps(value,ensure_ascii=False,indent=2).encode()+b'\n'


def main():
    parser=ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    root=Path(tempfile.mkdtemp(prefix='theta-te09r-SYNTHETIC-')).resolve()
    for name in ('answers','questions'): (root/name).mkdir(mode=0o700)
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    assert port not in {8947,8948,8968,8970}
    report={'label':'SYNTHETIC — NOT FOR GENUINE FORECASTING','root':str(root),'port':port,'checks':{}}
    evidence=root/'runtime/evidence'
    (root/'runtime').mkdir(mode=0o700)
    inputs=root/'runtime/support/originals';inputs.mkdir(mode=0o700,parents=True)
    located={}
    for role in (*SUBJECTS,'GLOBAL_MACRO'):
        image=Image.new('RGB',(1100,520),'#102436');draw=ImageDraw.Draw(image)
        draw.text((30,30),'SYNTHETIC — NOT FOR GENUINE FORECASTING — '+role,fill='white')
        stream=BytesIO();image.save(stream,format='PNG');raw=stream.getvalue();sha=hashlib.sha256(raw).hexdigest()
        (inputs/sha).write_bytes(raw);located[role]={'path':str(inputs/sha),'sha256':sha,'media_type':'image/png'}
    manifest=inputs.parent/'originals-manifest.json';manifest.write_text(json.dumps({'originals':located}))
    started=datetime.now(timezone.utc)
    with running(root,port,manifest) as log:
        report['startup']=json.loads(log[0]);assert report['startup']['qualification_mode'] is False
        for path in ('/swing/opportunities','/intraday','/provider/connect','/orders','/accounts','/runtime/status'):
            assert request(port,'GET',path)[0]==403 and request(port,'POST',path,b'')[0]==403
        assert request(port,'GET','/theta-earners',host='foreign.example')[0]==403
        assert request(port,'POST','/theta-earners/question',b'',origin='https://foreign.example')[0]==403
        report['checks']['host_origin_non_theta_denial']='PASS'
        selection=record(evidence/'current.json')
        for role in (*SUBJECTS,'GLOBAL_MACRO'):
            entry=selection['macro'] if role=='GLOBAL_MACRO' else selection['subjects'][role]
            revision=record(evidence/'chart-revisions'/(entry['revision_id']+'.json'))
            assert revision['sha256']==located[role]['sha256']
            assert started<=datetime.fromisoformat(revision['accepted_at'])<=datetime.now(timezone.utc)
            assert revision['cutoff_basis']=='INTAKE_RECEIPT_NOT_CHART_TIME'
        report['checks']['six_exact_controlled_originals']='PASS'
        report['filesystem_policy_proof']=policy_proof(root,port)
        report['checks']['nested_directory_permissions_and_credential_denial']='PASS'
        page=request(port,'GET','/theta-earners/new-analysis')[1]
        state=re.search(rb'name="input_state_sha256" value="([0-9a-f]+)"',page).group(1).decode()
        status,response=request(port,'POST','/theta-earners/question',urlencode({'input_state_sha256':state}));assert status==303,(status,response)
        page=request(port,'GET','/theta-earners/new-analysis')[1]
        batch=re.search(rb'name="question_batch_id" value="(TEB-[0-9a-f]+)"',page).group(1).decode()
        selected=record(evidence/'current.json');transport=record(evidence/'v3-question-transports'/(batch+'.json'))
        pack=(root/'questions'/transport['filename']).read_bytes()
        with ZipFile(BytesIO(pack)) as z:
            template=json.loads(z.read('combined-answer-template.json'))
            questions={subject:json.loads(z.read('individual/'+subject+'/question.json')) for subject in SUBJECTS}
            manifest=json.loads(z.read('manifest.json'))
            assert all(hashlib.sha256(z.read(n)).hexdigest()==h for n,h in manifest.items())
            assert all(not q['synthetic'] for q in questions.values())
            assert len([n for n in z.namelist() if n.endswith('QUESTION.pdf')])==5
        raw=answer(template,questions);(root/'answers'/(batch+'_ANSWERS.json')).write_bytes(raw)
        status,response=request(port,'POST','/theta-earners/import',urlencode({'question_batch_id':batch}));assert status==303,(status,response)
        accepted=operation(evidence);assert accepted['intake']['package_status']=='COMPLETE',accepted
        receipts={s:v['receipt_id'] for s,v in accepted['intake']['children'].items()}
        assert len(set(receipts.values()))==5 and len(accepted['assessments'])==5
        assert (evidence/'blobs'/hashlib.sha256(raw).hexdigest()).read_bytes()==raw
        report['checks']['combined_create_import_five_acceptances']='PASS'
        report['checks']['raw_original_and_separate_assessments']='PASS'
        before=inventory(evidence)
        status,outlook=request(port,'GET','/theta-earners');assert status==200 and b'SYNTHETIC' in outlook
        for subject,q in questions.items():
            status,detail=request(port,'GET','/theta-earners/detail?'+urlencode({'question':q['question_id'],'subject':subject}))
            assert status==200 and b'SYNTHETIC' in detail
            for f in json.loads(raw)['answers'][subject]['forecasts'].values():
                assert f['lower'].encode() in detail and f['upper'].encode() in detail and f['confidence_pct'].encode() in detail
        assert inventory(evidence)==before
        report['checks']['five_exact_detail_and_inert_get']='PASS'
    report['first_shutdown']=''.join(log)
    stopped=inventory(evidence)
    with running(root,port) as log2:
        assert request(port,'GET','/theta-earners')[0]==200 and inventory(evidence)==stopped
        assert request(port,'POST','/theta-earners/import',urlencode({'question_batch_id':batch}))[0]==303
        replay=operation(evidence);assert replay['intake']['package_status']=='REPLAY'
        assert {s:v['receipt_id'] for s,v in replay['intake']['children'].items()}==receipts
        assert all(v['disposition']=='REPLAY' for v in replay['assessments'].values())
        report['checks']['real_process_restart_and_idempotent_replay']='PASS'
    report['second_shutdown']=''.join(log2)
    report['evidence_inventory']=inventory(evidence)
    report['genuine_trial_root_created']=False
    report['status']='PASS'
    args.output.mkdir(mode=0o700,parents=True,exist_ok=True)
    (args.output/'OPERATIONAL-REHEARSAL.json').write_text(json.dumps(report,indent=2)+'\n')
    (args.output/'SYNTHETIC-COMBINED-ANSWER.json').write_bytes(raw)
    (args.output/'SYNTHETIC-PRODUCTION-SHAPED-QUESTION-PACK.zip').write_bytes(pack)
    print(json.dumps({'status':'PASS','root':str(root),'port':port,'checks':report['checks'],'runtime_stopped':True}))


if __name__=='__main__':main()
