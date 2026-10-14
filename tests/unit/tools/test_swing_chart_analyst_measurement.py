"""Labelled synthetic diagnostic qualification; never genuine chart findings."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from time import perf_counter_ns

import pytest
from tools.swing_chart_analyst_measurement import (
    Meter,MeasurementError,canonical,digest,read_json,publish,main,
)

class Clock:
    now=100
    def __call__(self):return self.now
    def advance(self,value):self.now+=value


def fixture(tmp_path,**kwargs):
    pdf=tmp_path/'synthetic-questions.pdf';pdf.write_bytes(b'%PDF-1.4\nLABELLED SYNTHETIC HASH FIXTURE; NOT A REVIEW PACK\n')
    charts=lambda subject:[dict(leg='NATIVE',timeframe=tf,request_identity='REQ-'+subject,
        subject_identity=subject,revision_identity='REV-'+subject+'-'+tf,chart_sha256='a'*64) for tf in ('1W','1D','4H','1H')]
    binding=dict(execution_identity='SYNTHETIC-EXECUTION',pack_identity='SYNTHETIC-PACK',
        pack_sha256=sha256(pdf.read_bytes()).hexdigest(),pack_bytes=pdf.stat().st_size,
        candidates=[dict(candidate_identity=x,instrument=x,charts=charts(x)) for x in ('CANDIDATE-A','CANDIDATE-B')])
    clock=Clock();m=Meter.create(tmp_path/'timing',binding,pdf,clock=clock,**kwargs)
    return m,clock,binding,pdf


def test_exact_monotonic_elapsed_and_wall_clock_rollback(tmp_path):
    m,clock,_,_=fixture(tmp_path,wall=iter(['2026-10-13T09:00:00+00:00','2026-10-13T09:00:01+00:00','2026-10-13T08:59:00+00:00']).__next__)
    with m.phase('M02') as result:clock.advance(700)
    e=m.report()['events'][-1]
    assert e['elapsed_ns']==700 and e['start_ns']==100 and e['end_ns']==800
    assert e['outcome']=='SUCCEEDED' and e['method']=='DIRECT_MONOTONIC'
    assert e['wall_end']<e['wall_start']  # correlation clock never determines duration
    assert result['event_identity']==e['integrity_sha256']


def test_fixed_candidate_timeframe_attribution_order_and_unknown(tmp_path):
    m,clock,binding,_=fixture(tmp_path)
    for phase,kwargs in [('M01',{}),('M07',dict(candidate='CANDIDATE-B')),
                         ('M08',dict(candidate='CANDIDATE-A',timeframe='4H',leg='NATIVE'))]:
        with m.phase(phase,**kwargs):clock.advance(10)
    r=m.report();assert r['binding']['candidates']==binding['candidates']
    assert [x['phase'] for x in r['events'] if x['kind']=='END']==['M01','M07','M08']
    assert all(len(r['attribution_buckets'][k])==1 for k in ('FIXED_PACK','PER_CANDIDATE','PER_TIMEFRAME'))
    assert next(x for x in r['phase_coverage'] if x['phase']=='M07' and x['attribution']['candidate']=='CANDIDATE-A')['state']=='UNKNOWN'
    tf=[x['attribution']['timeframe'] for x in r['phase_coverage'] if x['phase']=='M08' and x['attribution']['candidate']=='CANDIDATE-A']
    assert tf==['1W','1D','4H','1H']
    assert r['total_elapsed_ns'] is None and r['unattributed_elapsed_ns'] is None


def test_failure_and_explicit_retry_preserve_first_attempt(tmp_path):
    m,clock,_,_=fixture(tmp_path)
    with m.phase('M13') as failed:
        clock.advance(15);failed['failure_code']='VALIDATION_REJECTED'
    first=tuple(p.read_bytes() for p in sorted((m.root/'events').iterdir()))
    with m.phase('M13',retry_of=failed['event_identity']) as successor:clock.advance(10)
    r=m.report();ends=[e for e in r['events'] if e['kind']=='END']
    assert [e['outcome'] for e in ends]==['FAILED','SUCCEEDED']
    assert ends[0]['failure_code']=='VALIDATION_REJECTED' and ends[0]['elapsed_ns']==15
    assert ends[1]['retried'] and ends[1]['retry_of']==failed['event_identity']
    assert tuple(p.read_bytes() for p in sorted((m.root/'events').iterdir())[:2])==first
    assert successor['event_identity']!=failed['event_identity']


def test_exception_propagates_without_persisting_message(tmp_path):
    m,clock,_,_=fixture(tmp_path)
    with pytest.raises(RuntimeError,match='PRIVATE-SECRET-DO-NOT-RETAIN'):
        with m.phase('M12'):clock.advance(42);raise RuntimeError('PRIVATE-SECRET-DO-NOT-RETAIN')
    e=m.report()['events'][-1]
    assert e['outcome']=='FAILED' and e['elapsed_ns']==42 and e['failure_code']=='OPERATION_EXCEPTION'
    assert 'PRIVATE-SECRET' not in b''.join(p.read_bytes() for p in (m.root/'events').iterdir()).decode()


def test_overlap_union_and_unattributed_remainder_are_not_a_phase(tmp_path):
    m,c,_,_=fixture(tmp_path)
    with m.phase('M17'):
        c.advance(10)
        with m.phase('M07',candidate='CANDIDATE-A'):
            c.advance(5)
            with m.phase('M08',candidate='CANDIDATE-A',timeframe='1H',leg='NATIVE'):c.advance(20)
            c.advance(5)
        c.advance(20)
    r=m.report()
    assert r['total_elapsed_ns']==60 and r['measured_stage_sum_ns']==50
    assert r['covered_union_ns']==30 and r['unattributed_elapsed_ns']==30
    assert next(x for x in r['phase_coverage'] if x['phase']=='M16')['state']=='UNKNOWN'


def test_public_total_receipt_does_not_infer_missing_boundaries(tmp_path):
    m,c,_,_=fixture(tmp_path)
    with m.phase('M02'):c.advance(10)
    receipt=dict(operation_identity_sha256='a'*64,wall_start='2026-10-13T09:00:00+00:00',
        wall_end='2026-10-13T09:00:05+00:00',elapsed_ns=5_000_000_000,outcome='SUCCEEDED',failure_code=None,result_sha256=None)
    m.import_public_receipt('M17',receipt)
    r=m.report();assert r['total_elapsed_ns']==5_000_000_000
    assert r['unattributed_elapsed_ns'] is None and r['remainder_state']=='UNKNOWN'
    assert r['events'][-1]['source_receipt_sha256']==digest(receipt)
    assert r['events'][-1]['method']=='DERIVED_PUBLIC_RECEIPT'


@pytest.mark.parametrize('field',['reasoning','stdout','stderr','argv','access_token','extra'])
def test_private_and_additional_fields_rejected(tmp_path,field):
    m,_,_,_=fixture(tmp_path)
    receipt=dict(operation_identity_sha256='a'*64,wall_start='2026-10-13T09:00:00+00:00',
        wall_end='2026-10-13T09:00:01+00:00',elapsed_ns=100,outcome='SUCCEEDED',failure_code=None,result_sha256=None)
    receipt[field]='DO_NOT_PERSIST'
    with pytest.raises(MeasurementError):m.import_public_receipt('M02',receipt)
    assert not list((m.root/'events').iterdir())


@pytest.mark.parametrize('kwargs',[
    dict(candidate='OTHER'),dict(candidate='CANDIDATE-A',timeframe='5M',leg='NATIVE'),
    dict(candidate='CANDIDATE-A',timeframe='1H',leg='SUPPORTING_REFERENCE'),dict(timeframe='1H',leg='NATIVE'),
])
def test_wrong_candidate_chart_binding_rejects_before_operation(tmp_path,kwargs):
    m,_,_,_=fixture(tmp_path);called=[]
    with pytest.raises(MeasurementError):
        with m.phase('M06',**kwargs):called.append(True)
    assert not called and not list((m.root/'events').iterdir())


def test_started_without_end_is_incomplete_not_elapsed(tmp_path):
    m,_,_,_=fixture(tmp_path)
    start=m._append(m._values('M06','CANDIDATE-A','1D','NATIVE',None,None))
    r=Meter(m.root).report();assert r['incomplete_events']==[start] and r['evidence_state']=='INCOMPLETE'
    assert r['events'][0]['elapsed_ns'] is None
    assert next(x for x in r['phase_coverage'] if x['phase']=='M06')['state']=='UNKNOWN'


def test_replay_and_read_are_write_free(tmp_path):
    m,c,_,_=fixture(tmp_path)
    with m.phase('M02'):c.advance(5)
    before={str(p): (p.read_bytes(),p.stat().st_mtime_ns,p.stat().st_mode) for p in m.root.rglob('*') if p.is_file()}
    assert m.report()==Meter(m.root).report()
    after={str(p): (p.read_bytes(),p.stat().st_mtime_ns,p.stat().st_mode) for p in m.root.rglob('*') if p.is_file()}
    assert before==after
    p=next((m.root/'events').glob('*'));v=read_json(p)
    assert publish(p,v)==sha256(p.read_bytes()).hexdigest()
    with pytest.raises(MeasurementError,match='REPLAY_CONFLICT'):publish(p,dict(v,phase='M03'))
    assert p.read_bytes()==before[str(p)][0]


def test_changed_manifest_and_event_tamper_reject(tmp_path):
    m,_,_,_=fixture(tmp_path)
    with m.phase('M02'):pass
    p=next((m.root/'events').glob('*'));v=read_json(p);v['phase']='M03';p.write_bytes(canonical(v))
    with pytest.raises(MeasurementError):m.report()
    p=m.root/'manifest.json';v=read_json(p);v['binding']['pack_identity']='OTHER';p.write_bytes(canonical(v))
    with pytest.raises(MeasurementError):Meter(m.root)


def test_malformed_event_never_published(tmp_path):
    m,_,_,_=fixture(tmp_path)
    v=m._values('M02',None,None,None,None,None);v['start_ns']=-1
    with pytest.raises(MeasurementError):m._append(v)
    assert not list((m.root/'events').iterdir())


def test_rejected_retry_and_ambiguous_total(tmp_path):
    m,_,_,_=fixture(tmp_path)
    with m.phase('M02') as successful:pass
    with pytest.raises(MeasurementError):
        with m.phase('M02',retry_of=successful['event_identity']):pass
    with m.phase('M17'):pass
    with m.phase('M17'):pass
    with pytest.raises(MeasurementError,match='TOTAL_AMBIGUOUS'):m.report()


def test_binding_modes_symlinks_and_duplicate_keys(tmp_path):
    m,_,binding,pdf=fixture(tmp_path)
    assert stat.S_IMODE(m.root.stat().st_mode)==0o700
    assert all(stat.S_IMODE(p.stat().st_mode)==0o600 for p in m.root.rglob('*') if p.is_file())
    with pytest.raises(FileExistsError):Meter.create(m.root,binding,pdf)
    other=deepcopy(binding);other['pack_sha256']='f'*64
    with pytest.raises(MeasurementError,match='PACK_MISMATCH'):Meter.create(tmp_path/'wrong',other,pdf)
    link=tmp_path/'link';link.symlink_to(m.root,target_is_directory=True)
    with pytest.raises(MeasurementError,match='SYMLINK'):Meter(link)
    path=tmp_path/'duplicates.json';path.write_text('{"phase":"M02","phase":"M03"}')
    with pytest.raises(MeasurementError,match='DUPLICATE_KEY'):read_json(path)


def test_no_authority_and_original_artifacts_unchanged(tmp_path):
    m,c,binding,pdf=fixture(tmp_path);original=pdf.read_bytes();answer=b'{"governed_output":"LABELLED SYNTHETIC"}'
    def operation():return answer
    plain=operation()
    with m.phase('M10') as result:
        measured=operation();result['result_sha256']=sha256(measured).hexdigest();c.advance(10)
    assert measured==plain and pdf.read_bytes()==original and binding==m.binding
    assert m.report()['authority']=='DIAGNOSTIC_ONLY'
    assert not any(k in m.report() for k in ('admission','ready','position','v2','answer','analyst_observations'))


def test_cli_disabled_default_and_enabled_keep_stdout_stderr_and_exit(tmp_path):
    m,_,_,_=fixture(tmp_path)
    script=Path(__file__).resolve().parents[3]/'tools/swing_chart_analyst_measurement.py'
    command=[sys.executable,'-c','import sys;print("EXACT-OUTPUT");print("EXACT-STDERR",file=sys.stderr);sys.exit(7)']
    plain=subprocess.run(command,capture_output=True)
    disabled=subprocess.run([sys.executable,str(script),'measure','--',*command],capture_output=True)
    enabled=subprocess.run([sys.executable,str(script),'measure','--enabled','--root',str(m.root),'--phase','M12','--',*command],capture_output=True)
    assert (plain.stdout,plain.stderr,plain.returncode)==(disabled.stdout,disabled.stderr,disabled.returncode)
    assert (plain.stdout,plain.stderr,plain.returncode)==(enabled.stdout,enabled.stderr,enabled.returncode)
    e=m.report()['events'][-1];assert e['outcome']=='FAILED' and e['failure_code']=='PROCESS_EXIT_NONZERO'
    assert all('EXACT-' not in p.read_text() for p in (m.root/'events').glob('*.json'))
    read=subprocess.run([sys.executable,str(script),'report','--root',str(m.root)],capture_output=True)
    assert read.returncode==0 and json.loads(read.stdout)==m.report()


def test_measured_overhead_is_recorded_without_zero_claim(tmp_path):
    pdf=tmp_path/'pdf';pdf.write_bytes(b'LABELLED-SYNTHETIC')
    base=dict(execution_identity='BENCH',pack_identity='BENCH-PACK',pack_sha256=sha256(pdf.read_bytes()).hexdigest(),
        pack_bytes=pdf.stat().st_size,candidates=[dict(candidate_identity='A',instrument='A',charts=[dict(leg='NATIVE',timeframe='1H',request_identity='REQ',subject_identity='SUB',revision_identity='REV',chart_sha256='a'*64)])])
    rows=[]
    for count in (1,16,64):
        m=Meter.create(tmp_path/f'bench{count}',base,pdf)
        start=perf_counter_ns()
        for _ in range(count):pass
        plain=perf_counter_ns()-start;start=perf_counter_ns()
        for _ in range(count):
            with m.phase('M02'):pass
        enabled=perf_counter_ns()-start
        assert 0<enabled<5_000_000_000 and len(m.events())==2*count  # catastrophic-overhead guard for this bounded synthetic sample
        rows.append(dict(phases=count,disabled_ns=plain,enabled_ns=enabled,additional_ns=enabled-plain,
                         measured_average_additional_ns=(enabled-plain)/count))
    target=os.environ.get('SWING_MEASUREMENT_EVIDENCE_OUTPUT')
    if target:
        Path(target).write_text(json.dumps(rows,indent=2)+'\n')


@pytest.mark.parametrize('operation',[None,'a'*64])
def test_imported_public_receipt_identical_replay_and_conflict(tmp_path,operation):
    m,_,_,_=fixture(tmp_path)
    receipt=dict(operation_identity_sha256=operation,wall_start='2026-10-13T09:00:00+00:00',
        wall_end='2026-10-13T09:00:01+00:00',elapsed_ns=100,outcome='SUCCEEDED',failure_code=None,result_sha256=None)
    first=m.import_public_receipt('M02',receipt)
    before={p:p.read_bytes() for p in m.root.rglob('*') if p.is_file()}
    assert Meter(m.root).import_public_receipt('M02',receipt)==first
    assert before=={p:p.read_bytes() for p in m.root.rglob('*') if p.is_file()}
    with pytest.raises(MeasurementError,match='REPLAY_CONFLICT'):m.import_public_receipt('M02',dict(receipt,elapsed_ns=101))
    assert before=={p:p.read_bytes() for p in m.root.rglob('*') if p.is_file()}


def test_known_total_cannot_hide_a_same_clock_boundary_contradiction(tmp_path):
    m,c,_,_=fixture(tmp_path)
    with m.phase('M17'):c.advance(10)
    with m.phase('M02'):c.advance(10)
    with pytest.raises(MeasurementError,match='TOTAL_BOUNDARY_CONTRADICTION'):m.report()


def test_wrong_phase_and_direct_operation_replay_do_not_execute(tmp_path):
    m,_,_,_=fixture(tmp_path)
    with m.phase('M02',operation_identity_sha256='a'*64):pass
    called=[]
    for phase,kwargs in [('M99',{}),('M07',{}),('M08',{}),('M02',dict(operation_identity_sha256='a'*64))]:
        with pytest.raises(MeasurementError):
            with m.phase(phase,**kwargs):called.append(True)
    assert not called


def test_same_clock_total_is_separate_from_fixed_pack_cost(tmp_path):
    m,c,_,_=fixture(tmp_path)
    with m.phase('M17'):
        with m.phase('M02'):c.advance(10)
    r=m.report()
    assert len(r['attribution_buckets']['TOTAL_EXECUTION'])==1
    assert len(r['attribution_buckets']['FIXED_PACK'])==1


@pytest.mark.parametrize('name',['KRONOS','kronos','Kronos'])
def test_production_path_and_manifest_symlink_reject(tmp_path,name):
    m,_,_,_=fixture(tmp_path)
    with pytest.raises(MeasurementError,match='PRODUCTION_ROOT_DENIED'):
        Meter('/Users/example/Library/Application Support/'+name+'/timing')
    manifest=m.root/'manifest.json';copy=tmp_path/'saved';copy.write_bytes(manifest.read_bytes());manifest.unlink();manifest.symlink_to(copy)
    with pytest.raises(MeasurementError,match='SYMLINK'):Meter(m.root)


def test_invalid_enabled_journal_prevents_child_dispatch(tmp_path):
    m,_,_,_=fixture(tmp_path)
    (m.root/'events'/'bad.json').write_text('{"access_token":"DO_NOT_PERSIST"}')
    marker=tmp_path/'child-ran'
    script=Path(__file__).resolve().parents[3]/'tools/swing_chart_analyst_measurement.py'
    result=subprocess.run([sys.executable,str(script),'measure','--enabled','--root',str(m.root),'--phase','M02',
        '--',sys.executable,'-c',f'from pathlib import Path;Path({str(marker)!r}).write_text("BAD")'],capture_output=True)
    assert result.returncode!=0 and not marker.exists()


def test_cli_initialization_and_import_preserve_exact_binding(tmp_path):
    m,_,binding,pdf=fixture(tmp_path)
    binding_file=tmp_path/'binding.json';binding_file.write_bytes(canonical(binding))
    newroot=tmp_path/'cli-timing'
    assert main(['init','--root',str(newroot),'--binding',str(binding_file),'--question-pdf',str(pdf)])==0
    assert Meter(newroot).binding==binding
    receipt=dict(operation_identity_sha256='a'*64,wall_start='2026-10-13T09:00:00+00:00',
        wall_end='2026-10-13T09:00:01+00:00',elapsed_ns=100,outcome='SUCCEEDED',failure_code=None,result_sha256=None)
    source=tmp_path/'public.json';source.write_bytes(canonical(receipt))
    assert main(['import-public-receipt','--root',str(newroot),'--receipt',str(source),'--phase','M02'])==0
    assert Meter(newroot).events()[-1]['method']=='DERIVED_PUBLIC_RECEIPT'


def test_two_diagnostic_writers_keep_exclusive_sequences(tmp_path):
    m,_,_,_=fixture(tmp_path)
    script=Path(__file__).resolve().parents[3]/'tools/swing_chart_analyst_measurement.py'
    children=[subprocess.Popen([sys.executable,str(script),'measure','--enabled','--root',str(m.root),
        '--phase','M02','--operation-sha256',str(i)*64,'--',sys.executable,'-c','pass'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        for i in (1,2)]
    for child in children:
        out,error=child.communicate(timeout=10)
        assert child.returncode==0,(out,error)
    records=m.events()
    assert [x['sequence'] for x in records]==[1,2,3,4]
    assert len([x for x in records if x['outcome']=='SUCCEEDED'])==2
    assert len({x['clock_domain'] for x in records})==2


@pytest.mark.parametrize('market,instrument',[
    ('NSE','INFY'),('MCX','GOLDM26NOVFUT'),('MCX','SILVERM26NOVFUT'),
    ('MCX','COPPER26OCTFUT'),('MCX','CRUDEOIL26OCTFUT'),('MCX','NATURALGAS26OCTFUT')])
def test_six_market_binding_rows_preserve_native_and_supporting_order(tmp_path,market,instrument):
    pdf=tmp_path/'synthetic.pdf';pdf.write_bytes(b'LABELLED SYNTHETIC; NOT GENUINE CHART EVIDENCE')
    timeframes=('1W','1D','4H','1H') if market=='NSE' else ('1D','4H','1H')
    charts=[dict(leg=leg,timeframe=tf,request_identity='SYNTHETIC-REQ-'+leg,
        subject_identity='SYNTHETIC-SUB-'+leg,revision_identity='SYNTHETIC-REV-'+leg+'-'+tf,
        chart_sha256=('a' if leg=='NATIVE' else 'b')*64)
        for leg in (('NATIVE',) if market=='NSE' else ('NATIVE','SUPPORTING_REFERENCE')) for tf in timeframes]
    binding=dict(execution_identity='SYNTHETIC-'+instrument,pack_identity='SYNTHETIC-PACK',
        pack_sha256=sha256(pdf.read_bytes()).hexdigest(),pack_bytes=pdf.stat().st_size,
        candidates=[dict(candidate_identity='CAND-'+instrument,instrument=instrument,charts=charts)])
    m=Meter.create(tmp_path/'run',binding,pdf)
    for chart in charts:
        with m.phase('M08',candidate='CAND-'+instrument,timeframe=chart['timeframe'],leg=chart['leg']):pass
    report=m.report()
    assert report['binding']==binding
    assert [(e['leg'],e['timeframe']) for e in report['events'] if e['kind']=='END']==[(x['leg'],x['timeframe']) for x in charts]
    assert all(x['state']=='OBSERVED' for x in report['phase_coverage'] if x['phase']=='M08')
    if market=='MCX':
        with pytest.raises(MeasurementError,match='CHART_MISMATCH'):
            with m.phase('M08',candidate='CAND-'+instrument,timeframe='1W',leg='NATIVE'):pass


def test_identity_unavailable_public_receipt_cannot_cross_candidate_binding(tmp_path):
    m,_,_,_=fixture(tmp_path)
    receipt=dict(operation_identity_sha256=None,wall_start='2026-10-13T09:00:00+00:00',
        wall_end='2026-10-13T09:00:01+00:00',elapsed_ns=100,outcome='SUCCEEDED',failure_code=None,result_sha256=None)
    m.import_public_receipt('M07',receipt,candidate='CANDIDATE-A')
    before={p:p.read_bytes() for p in m.root.rglob('*') if p.is_file()}
    with pytest.raises(MeasurementError,match='REPLAY_CONFLICT'):
        m.import_public_receipt('M07',receipt,candidate='CANDIDATE-B')
    assert before=={p:p.read_bytes() for p in m.root.rglob('*') if p.is_file()}


def test_reader_waits_for_exclusive_writer_staging(tmp_path):
    """Deterministic predecessor failure: unlocked reader sees .timing staging."""
    m,_,_,_=fixture(tmp_path)
    from time import monotonic,sleep
    signals=tmp_path/'signals';signals.mkdir()
    writer_code=r"""
import os,sys,time
from pathlib import Path
import tools.swing_chart_analyst_measurement as tool
root,signals=sys.argv[1:];signals=Path(signals);original=os.link
first=True
def paused(source,destination,*a,**kw):
    global first
    if first:
        first=False
        (signals/'staged').write_text('actual exclusive publication staging')
        deadline=time.monotonic()+8
        while not (signals/'release').exists():
            if time.monotonic()>deadline:raise TimeoutError('ISOLATED_RELEASE_MISSING')
            time.sleep(.005)
    return original(source,destination,*a,**kw)
tool.os.link=paused
raise SystemExit(tool.main(['measure','--enabled','--root',root,'--phase','M02',
    '--operation-sha256','1'*64,'--',sys.executable,'-c','pass']))
"""
    reader_code=r"""
import sys,traceback
from pathlib import Path
from tools.swing_chart_analyst_measurement import main
root,signals=sys.argv[1:]
Path(signals,'reader-invoked').write_text('actual measure')
try:
    raise SystemExit(main(['measure','--enabled','--root',root,'--phase','M02',
        '--operation-sha256','2'*64,'--',sys.executable,'-c','pass']))
except Exception:
    traceback.print_exc();raise SystemExit(1)
"""
    writer=subprocess.Popen([sys.executable,'-c',writer_code,str(m.root),str(signals)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    reader=None
    try:
        deadline=monotonic()+5
        while not (signals/'staged').exists():
            assert monotonic()<deadline,'writer did not reach actual staging'
            sleep(.005)
        assert any(p.name.startswith('.timing-') for p in (m.root/'events').iterdir())
        reader=subprocess.Popen([sys.executable,'-c',reader_code,str(m.root),str(signals)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        deadline=monotonic()+5
        while not (signals/'reader-invoked').exists():
            assert monotonic()<deadline,'reader did not invoke actual main'
            sleep(.005)
        # The shared read lock must wait, not reject private in-flight staging.
        with pytest.raises(subprocess.TimeoutExpired):reader.wait(timeout=.2)
    finally:
        (signals/'release').write_text('release isolated writer')
        wo,we=writer.communicate(timeout=8)
        if reader is not None:ro,re=reader.communicate(timeout=8)
    assert writer.returncode==0,we.decode()
    assert reader.returncode==0,re.decode()
    records=m.events()
    assert [e['sequence'] for e in records]==[1,2,3,4]
    assert len([e for e in records if e['outcome']=='SUCCEEDED'])==2
    assert stat.S_IMODE(m.root.stat().st_mode)==0o700
    assert stat.S_IMODE((m.root/'events').stat().st_mode)==0o700
    assert all(stat.S_IMODE(p.stat().st_mode)==0o600 for p in m.root.rglob('*') if p.is_file())
    before={p:p.read_bytes() for p in m.root.rglob('*') if p.is_file()}
    assert m.report()['evidence_state']=='READABLE_DIAGNOSTIC'
    assert before=={p:p.read_bytes() for p in m.root.rglob('*') if p.is_file()}


def test_operation_identity_is_checked_under_append_lock_before_dispatch(tmp_path):
    m,_,_,_=fixture(tmp_path)
    # Prepare both starts before either append. The second cannot dispatch.
    a=m._values('M02',None,None,None,'3'*64,None)
    b=m._values('M02',None,None,None,'3'*64,None)
    m._append(a)
    before={p:p.read_bytes() for p in m.root.rglob('*') if p.is_file()}
    with pytest.raises(MeasurementError,match='OPERATION_ALREADY_RECORDED'):m._append(b)
    assert before=={p:p.read_bytes() for p in m.root.rglob('*') if p.is_file()}
    assert m.report()['evidence_state']=='INCOMPLETE'
