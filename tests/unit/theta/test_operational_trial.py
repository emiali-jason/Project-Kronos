"""TE-09R real-authority, real-clock composition; all market evidence SYNTHETIC."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime,timezone
from types import SimpleNamespace
from http.client import HTTPConnection
from io import BytesIO
import json
import os
from pathlib import Path
import re
import select
import socket
import subprocess
import sys
from urllib.parse import urlencode
from zipfile import ZipFile
from threading import Thread

from PIL import Image,ImageDraw
import pytest

from kronos.theta.contracts import SUBJECTS,ThetaError,digest,encode,stamp
from kronos.theta.operational import TrialPaths,compose,admit_originals,reviewed_owner,OWNERSHIP
from kronos.theta.methodology import ThetaMethodologyPublication
from tests.unit.theta.test_assessment import documented_child,limited_c3
from tests.unit.theta.test_combined_intake import snapshot
from tests.unit.theta.test_producer_v3 import completed
from tests.unit.theta.test_workflow import chart
from tools import theta_trial


def paths(root):
    inbox=root/'answers';outbox=root/'questions'
    inbox.mkdir(mode=0o700);outbox.mkdir(mode=0o700)
    return TrialPaths(root/'runtime',inbox,outbox,'SYNTHETIC_REHEARSAL')


def originals():
    # The nonqualification transport path is tested with exact synthetic pixels,
    # never Sponsor originals. Watermark survives exact PDF/ZIP chart embedding.
    return {role:{'payload':chart(),'media_type':'image/png','sha256':digest(chart())}
            for role in (*SUBJECTS,'GLOBAL_MACRO')}


def test_real_clock_review_methodology_targets_and_fresh_original_receipts(tmp_path):
    config=paths(tmp_path.resolve());before=datetime.now(timezone.utc)
    app,metadata=compose(config)
    assert not app.workflow.qualification_mode and len(metadata['targets'])==5
    assert reviewed_owner().current_sha256=='bfd2f9c50c823455e124cccf50722d05a92cacaf8665d6b6968d1327940dda1d'
    assert sum(len(x['targets']) for x in metadata['targets'].values())==10
    with pytest.raises(ThetaError,match='CONFIRMATION_REQUIRED'):
        admit_originals(app,originals(),sponsor_confirmed=False)
    workspace=admit_originals(app,originals(),sponsor_confirmed=True)
    after=datetime.now(timezone.utc)
    for card in workspace['cards']:
        assert before<=stamp(card['intake']['accepted_at'])<=after
        assert card['intake']['cutoff_basis']=='INTAKE_RECEIPT_NOT_CHART_TIME'
        assert app.store.load_blob(card['chart']['sha256'])==chart()
    inventory=snapshot(app.store.root)
    assert admit_originals(app,originals(),sponsor_confirmed=True)==workspace
    assert snapshot(app.store.root)==inventory


@pytest.mark.parametrize('mutation',['sha','bytes','role','extra','corrupt'])
def test_original_payload_only_preflight_fails_before_selection(tmp_path,mutation):
    app,_=compose(paths(tmp_path.resolve()));values=originals()
    if mutation=='sha': values['COPPER']['sha256']='0'*64
    if mutation=='bytes': values['COPPER']['payload']=b'bad'
    if mutation=='role': values['GOLD']=values.pop('GOLDM')
    if mutation=='extra': values['COPPER']['old_receipt']={}
    if mutation=='corrupt':
        values['COPPER']['payload']=b'\x89PNG\r\n\x1a\ntruncated'
        values['COPPER']['sha256']=digest(values['COPPER']['payload'])
    with pytest.raises(ValueError,match='ORIGINAL_INVALID'):
        admit_originals(app,values,sponsor_confirmed=True)
    assert not (app.store.root/'current.json').exists()


def test_foreign_and_qualification_stores_cannot_be_adopted(tmp_path):
    config=paths(tmp_path.resolve());config.root.mkdir(mode=0o700);(config.root/'evidence').mkdir()
    (config.root/'evidence/current.json').write_bytes(b'qualification selection')
    with pytest.raises(ThetaError,match='FOREIGN_STORE'): compose(config)
    assert not (config.root/OWNERSHIP).exists()


def test_rehearsal_ownership_cannot_be_relabelled_genuine(tmp_path):
    config=paths(tmp_path.resolve());app,_=compose(config)
    raw=(config.root/OWNERSHIP).read_bytes()
    forged=json.loads(raw);forged['mode']='GENUINE_TRIAL'
    (config.root/OWNERSHIP).write_bytes(encode(forged))
    with pytest.raises(ThetaError,match='FOREIGN_STORE'):compose(config)


def test_missing_permissions_symlinks_and_arbitrary_genuine_paths_fail_closed(tmp_path):
    config=paths(tmp_path.resolve())
    config.inbox.chmod(0o777)
    with pytest.raises(ThetaError,match='PERMISSION_INVALID'):compose(config)
    config.inbox.chmod(0o700)
    linked=tmp_path/'linked';linked.symlink_to(config.outbox,target_is_directory=True)
    with pytest.raises(OSError):compose(TrialPaths(config.root,config.inbox,linked,config.mode))
    with pytest.raises(ThetaError,match='PATH_INVALID'):
        compose(TrialPaths(config.root,config.inbox,config.outbox,'GENUINE_TRIAL'))


def test_methodology_boundary_and_tampered_review_are_not_runtime_flags(tmp_path,monkeypatch):
    publication=ThetaMethodologyPublication()
    with pytest.raises(ThetaError):publication.research_inputs(datetime(2026,10,12,9,20,tzinfo=timezone.utc))
    import kronos.theta.operational as module
    monkeypatch.setattr(module,'REVIEW_SHA256','0'*64)
    with pytest.raises(ThetaError,match='CA_REVIEW_INVALID'):compose(paths(tmp_path.resolve()))


def test_tampered_methodology_fails_before_operational_ownership(tmp_path,monkeypatch):
    import kronos.theta.operational as module
    from kronos.theta.methodology import ROOT,RESEARCH_ID
    publication=tmp_path/'publication';publication.mkdir()
    for p in ROOT.iterdir():
        if p.is_file():(publication/p.name).write_bytes(p.read_bytes())
    (publication/(RESEARCH_ID+'.json')).write_bytes(b'{}')
    monkeypatch.setattr(module,'ThetaMethodologyPublication',lambda:ThetaMethodologyPublication(publication))
    config=paths(tmp_path.resolve())
    with pytest.raises(ThetaError):compose(config)
    assert not config.root.exists()


@pytest.mark.parametrize('port',[8947,8948,8968])
def test_protected_ports_are_rejected_before_any_runtime_transition(tmp_path,port):
    config=paths(tmp_path.resolve())
    args=SimpleNamespace(mode=config.mode,root=config.root,inbox=config.inbox,outbox=config.outbox,port=port,child=False)
    with pytest.raises(ValueError,match='PORT_INVALID'):theta_trial.preflight(args)
    assert not config.root.exists()


def test_original_manifest_closed_fields_and_nofollow_reads(tmp_path):
    config=paths(tmp_path.resolve());inputs=config.root/'support/originals';inputs.mkdir(parents=True)
    raw=chart();sha=digest(raw);source=inputs/sha;source.write_bytes(raw)
    manifest=inputs.parent/'originals.json'
    value={'originals':{s:{'path':str(source),'sha256':sha,'media_type':'image/png'} for s in (*SUBJECTS,'GLOBAL_MACRO')}}
    manifest.write_text(json.dumps(value))
    args=SimpleNamespace(root=config.root,mode=config.mode,originals_manifest=manifest,sponsor_confirmed_originals=True)
    assert len(theta_trial.original_manifest(args))==6
    assert theta_trial.safe_file(source,16*1024*1024)==raw
    value['originals']['GOLDM']['receipt']={};manifest.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='ORIGINAL_INVALID'):theta_trial.original_manifest(args)
    linked=inputs/'linked';linked.symlink_to(source)
    with pytest.raises(OSError):theta_trial.safe_file(linked,16*1024*1024)
    hard=inputs/'hard';os.link(source,hard)
    with pytest.raises(ValueError,match='ORIGINAL_INVALID'):theta_trial.safe_file(hard,16*1024*1024)


def test_child_without_kernel_denial_cannot_initialize_kronos(tmp_path):
    config=paths(tmp_path.resolve());support=config.root/'support';support.mkdir(parents=True)
    probe=support/'kernel-denial-probe';probe.write_bytes(b'controlled probe');probe.chmod(0o600)
    args=SimpleNamespace(root=config.root)
    with pytest.raises(ValueError,match='KERNEL_PROTECTION_MISSING'):theta_trial.child(args)
    assert not (config.root/OWNERSHIP).exists()


def test_six_originals_may_include_exact_jpeg_without_receipt_conversion(tmp_path):
    config=paths(tmp_path.resolve());app,_=compose(config);values=originals()
    image=Image.new('RGB',(64,32),'#102436');stream=BytesIO();image.save(stream,format='JPEG')
    raw=stream.getvalue();values['COPPER']={'payload':raw,'media_type':'image/jpeg','sha256':digest(raw)}
    workspace=admit_originals(app,values,sponsor_confirmed=True)
    copper=next(c for c in workspace['cards'] if c['subject']=='COPPER')
    assert copper['chart']['media_type']=='image/jpeg' and app.store.load_blob(digest(raw))==raw


def request(port,method,path,body=None,*,content_type='application/x-www-form-urlencoded',origin=None,host=None):
    connection=HTTPConnection('127.0.0.1',port,timeout=20)
    headers={'Host':host or f'127.0.0.1:{port}'}
    if method=='POST':headers.update(Origin=origin or f'http://127.0.0.1:{port}',**{'Content-Type':content_type})
    try:
        connection.request(method,path,body=body,headers=headers)
        response=connection.getresponse();return response.status,response.read()
    finally:connection.close()


@contextmanager
def runtime(config,port):
    # macOS does not permit nesting sandbox-exec. This test is already inside
    # tools/kronos_test.py's production-denying kernel boundary. The standalone
    # rehearsal separately proves the actual operational child policy/bootstrap.
    from kronos.application.swing_opportunities import SwingOpportunitiesApplication
    from kronos.browser.product_routes import ProductBrowserRoutes
    from kronos.browser.theta_routes import ThetaBrowserRoutes
    from kronos.browser.server import create_browser_server
    app,_=compose(config);calls=[]
    def forbidden():calls.append('FORBIDDEN');raise AssertionError('Provider forbidden')
    route=ThetaBrowserRoutes(app.workflow,sponsor_workflow=app);original=route._page
    route._page=lambda snap,body,**kw:original(snap,'<strong>SYNTHETIC — NOT FOR GENUINE FORECASTING</strong>'+body,**kw)
    server=create_browser_server(SwingOpportunitiesApplication(forbidden),port=port,
        product_routes=ProductBrowserRoutes((route,)))
    server.RequestHandlerClass=theta_trial.handler(server.RequestHandlerClass,config.mode)
    server.service_actions=lambda:None
    thread=Thread(target=server.serve_forever,daemon=True);thread.start();log=[]
    try:
        yield server,log
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)
        log.append(json.dumps({'provider_calls':len(calls)}))
        assert not calls and not thread.is_alive()


def free_port():
    with socket.socket() as reserved:
        reserved.bind(('127.0.0.1',0));return reserved.getsockname()[1]


def http_create(port):
    status,page=request(port,'GET','/theta-earners/new-analysis')
    assert status==200 and b'SYNTHETIC' in page
    state=re.search(rb'name="input_state_sha256" value="([0-9a-f]+)"',page).group(1).decode()
    assert request(port,'POST','/theta-earners/question',urlencode({'input_state_sha256':state}))[0]==303


def synthetic_answer(batch,questions,*,invalid=None):
    value=completed(batch,questions);now=datetime.now(timezone.utc)
    for subject,child in value['answers'].items():
        child['analyzed_at']=now.isoformat();documented_child(child)
        if subject=='SILVERM':limited_c3(child,'E2')
    if invalid:value['answers'][invalid]['forecasts']['E1']['confidence_pct']='101'
    return json.dumps(value,ensure_ascii=False,indent=2).encode()+b'\n'


def test_kernel_http_workflow_security_restart_replay_and_exact_projection(tmp_path):
    config=paths(tmp_path.resolve());port=free_port()
    # Admit six controlled originals through the same future transfer operation.
    app,_=compose(config);admit_originals(app,originals(),sponsor_confirmed=True)
    with runtime(config,port) as (_,logs):
        for p in ['/swing/opportunities','/intraday','/provider/connect','/orders','/settings']:
            assert request(port,'GET',p)[0]==403
            assert request(port,'POST',p,b'')[0]==403
        assert request(port,'DELETE','/theta-earners')[0]==403
        assert request(port,'GET','/theta-earners',host=f'evil.test:{port}')[0]==403
        assert request(port,'POST','/theta-earners/question',b'',origin='https://foreign.example')[0]==403
        http_create(port)
        app,_=compose(config);batch,questions=app.intake._batch(app.producer.selected()['batch_id'])
        assert not batch['synthetic'] and all(not q['synthetic'] for q in questions.values())
        raw=synthetic_answer(batch,questions)
        (config.inbox/(batch['batch_id']+'_ANSWERS.json')).write_bytes(raw)
        assert request(port,'POST','/theta-earners/import',urlencode({'question_batch_id':batch['batch_id']}))[0]==303
        result=app.restore_status()['import_operation']['result']
        assert result['intake']['package_status']=='COMPLETE'
        assert all(v['status']=='ACCEPTED' for v in result['intake']['children'].values())
        assert len({v['receipt_id'] for v in result['intake']['children'].values()})==5
        assert result['assessments']['SILVERM']['E1']=='DOCUMENTED'
        assert result['assessments']['SILVERM']['E2']=='LIMITED'
        for subject,child in result['intake']['children'].items():
            assert app.intake.accepted_evidence(child['receipt_id'])['package_raw']==raw
        before=snapshot(app.store.root)
        status,outlook=request(port,'GET','/theta-earners')
        assert status==200 and b'SYNTHETIC' in outlook
        for subject,q in questions.items():
            address='/theta-earners/detail?'+urlencode({'question':q['question_id'],'subject':subject})
            status,detail=request(port,'GET',address);assert status==200 and b'SYNTHETIC' in detail
            for h in ('E1','E2'):
                forecast=json.loads(raw)['answers'][subject]['forecasts'][h]
                assert forecast['lower'].encode() in detail and forecast['upper'].encode() in detail
        assert snapshot(app.store.root)==before
    with runtime(config,port) as (_,second_log):
        assert request(port,'GET','/theta-earners')[1]==outlook
        assert snapshot(app.store.root)==before
        assert request(port,'POST','/theta-earners/import',urlencode({'question_batch_id':batch['batch_id']}))[0]==303
        replay=app.restore_status()['import_operation']['result']
        assert replay['intake']['package_status']=='REPLAY'
        assert {s:v['receipt_id'] for s,v in replay['intake']['children'].items()}=={s:v['receipt_id'] for s,v in result['intake']['children'].items()}
        assert all(a['disposition']=='REPLAY' for a in replay['assessments'].values())
        # A foreign rehearsal wrapper cannot satisfy this runtime's exact batch.
        foreign=json.loads(raw);foreign['question_batch_id']='TEB-'+'0'*64
        foreign['answer_package_id']='SYNTHETIC-FOREIGN-PACKAGE'
        (config.inbox/(batch['batch_id']+'_ANSWERS.json')).write_bytes(json.dumps(foreign).encode())
        assert request(port,'POST','/theta-earners/import',urlencode({'question_batch_id':batch['batch_id']}))[0]==409
        assert app.restore_status()['import_operation']['result']['intake']['package_status']=='REJECTED'
        for child in result['intake']['children'].values():
            assert app.intake.accepted_evidence(child['receipt_id'])['package_raw']==raw
    assert all('"provider_calls": 0' in ''.join(log) for log in (logs,second_log))


def test_partial_acceptance_and_assessment_remain_independent(tmp_path):
    config=paths(tmp_path.resolve());app,_=compose(config)
    admit_originals(app,originals(),sponsor_confirmed=True)
    created=app.create_question_pack(app.input_state_sha256())['result']
    batch,questions=app.intake._batch(created['batch_id']);raw=synthetic_answer(batch,questions,invalid='COPPER')
    (config.inbox/(batch['batch_id']+'_ANSWERS.json')).write_bytes(raw)
    result=app.import_astra_answers(batch['batch_id'])['result']
    assert result['intake']['package_status']=='PARTIAL'
    assert result['assessments']['COPPER'] is None
    assert sum(v['status']=='ACCEPTED' for v in result['intake']['children'].values())==4
    assert all(v['receipt_id'] for s,v in result['intake']['children'].items() if s!='COPPER')
