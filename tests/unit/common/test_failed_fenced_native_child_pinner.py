"""Actual disposable interpreter execution of the fixed native pin program.

The source declarations and fixed entry are synthetic qualifications. Actual
Python loader/code/payload/argv identity checks execute in a fresh process; no
canonical C parent, review attribution, child grant or product startup is claimed.
"""
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from tools.runtime_source_gate import native_child_bootstrap_script


def _frame(tmp_path, fault=None):
    root = Path(__file__).resolve().parents[3]
    source = (root / 'tools/runtime_source_gate.py').read_bytes()
    mutation = {
        'payload': "entry.__spec__.loader.payload = b'changed'",
        'code': "entry.__spec__.loader.code = compile('CHANGED=True',entry.__file__,'exec')",
        'loader': "entry.__spec__.loader = type('Fake',(),{})()",
        'program': "sys.orig_argv[sys.orig_argv.index('-c')+1] += '\\n'",
        'capsule': "sys.modules['_kronos_native_child_bootstrap'].sources = ()",
        'unloaded': "entry.__spec__.loader.executed = False",
    }.get(fault, '')
    entry = ("import sys\nfrom tools.runtime_source_gate import native_child_pinned_module\n"
             "from kronos.intraday import runtime_identity\n"
             "def main(args=None):\n    entry=sys.modules[__name__]\n    " + (mutation or 'pass') +
             "\n    name,digest=native_child_pinned_module(entry)\n"
             "    assert name=='tools.kronos_browser' and len(digest)==64\n"
             "    print('ACTUAL_PINNED_ENTRY_VERIFIED')\n    return 0\n").encode()
    if fault and fault.startswith('batch-'):
        change = {
            'batch-valid': 'pass',
            'batch-capsule': "sys.modules['_kronos_native_child_bootstrap'].sources = ()",
            'batch-program': "sys.orig_argv[sys.orig_argv.index('-c')+1] += '\\n'",
            'batch-payload': "entry.__spec__.loader.payload=b'changed'",
            'batch-code': "entry.__spec__.loader.code=compile('CHANGED=True',entry.__file__,'exec')",
            'batch-expired': "raise ValueError('NATIVE_CHILD_PIN_TEST_DEADLINE')",
        }[fault]
        entry = ("import sys\nfrom tools.runtime_source_gate import native_child_pinned_modules\n"
            "from kronos.intraday import runtime_identity\n"
            "def main(args=None):\n    entry=sys.modules[__name__]\n    calls=[0]\n"
            "    def check():\n        calls[0]+=1\n        if calls[0]==2: " + change + "\n"
            "    result=native_child_pinned_modules((entry,sys.modules['tools.runtime_source_gate']),check_deadline=check)\n"
            "    assert result[0][0]=='tools.kronos_browser' and len(result)==2 and calls[0]>=4\n"
            "    print('ACTUAL_PINNED_BATCH_VERIFIED')\n    return 0\n").encode()
    sources = {'kronos': b'', 'kronos.intraday': b'', 'kronos.intraday.runtime_identity': b'FIXTURE=1\n',
               'tools.runtime_source_gate': source, 'tools.kronos_browser': entry}
    if fault=='native-package-namespace':
        sources['tools.macos.package_launcher']=b'CAPTURED_NATIVE_PACKAGE=1\n'
        sources['tools.kronos_browser']=b'from tools.macos import package_launcher\nassert package_launcher.CAPTURED_NATIVE_PACKAGE==1\n'+entry
    elif fault=='unknown-namespace':
        sources['tools.kronos_browser']=b'import tools.unknown.child\n'+entry
    blob = {'identity':'synthetic-qualification','hash':'a'*64,'bytes':'1'}
    plan = {'schema':'KRONOS-FAILED-FENCED-BOOTSTRAP-PLAN/1.0.0','identity':'synthetic-child-plan',
            'source_inventory':blob,'qualification':blob,
            'modules':[{'name':name,'digest':sha256(raw).hexdigest()} for name,raw in sorted(sources.items())]}
    canonical = lambda obj: json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()
    rows=[]
    for name,raw in sorted(sources.items()):
        path=tmp_path/(name+'.py');path.write_bytes(raw);path.chmod(0o600)
        rows.append({'name':name,'path':str(path.resolve()),'package':name in {'kronos','kronos.intraday'}})
    if fault == 'source':Path(rows[0]['path']).write_bytes(b'changed')
    if fault == 'symlink':
        path=Path(rows[0]['path']);target=path.with_suffix('.target');path.rename(target);path.symlink_to(target)
    if fault == 'hardlink':os.link(rows[0]['path'],str(tmp_path/'second-link'))
    if fault == 'writable':Path(rows[0]['path']).chmod(0o666)
    if fault == 'unknown':rows.append({'name':'tools.unknown','path':rows[0]['path'],'package':False})
    inventory=[[name,sha256(raw).hexdigest()] for name,raw in sorted(sources.items())]
    inventory_raw=canonical(inventory)
    plan['source_inventory']={'identity':'synthetic-complete-source','hash':sha256(inventory_raw).hexdigest(),'bytes':str(len(inventory_raw))}
    return canonical({'inventory':inventory,'plan':plan,'plan_hash':sha256(canonical(plan)).hexdigest(),'sources':rows})


def _run(raw):
    origin=time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    script=native_child_bootstrap_script(raw,origin,origin+15_000_000_000)
    # Only these disposable declared source files are read before imports.
    # The fixed program checks their expected digests and executes the capture;
    # no environment authority, product owner or network is introduced.
    return subprocess.run([sys.executable,'-I','-B','-c',script],capture_output=True,text=True,timeout=20,
        env={'PATH':os.environ.get('PATH',''),'PYTHONDONTWRITEBYTECODE':'1'})


def test_fixed_program_executes_and_verifies_captured_bytes(tmp_path):
    result=_run(_frame(tmp_path))
    assert result.returncode==0, result.stderr
    assert result.stdout=='ACTUAL_PINNED_ENTRY_VERIFIED\n'


def test_fixed_program_allows_only_declared_native_package_namespace(tmp_path):
    result=_run(_frame(tmp_path,'native-package-namespace'))
    assert result.returncode==0,result.stderr
    assert result.stdout=='ACTUAL_PINNED_ENTRY_VERIFIED\n'


def test_fixed_program_denies_unknown_namespace_before_product_entry(tmp_path):
    result=_run(_frame(tmp_path,'unknown-namespace'))
    assert result.returncode!=0
    assert 'NATIVE_CHILD_PIN_UNCAPTURED_MODULE' in result.stderr


@pytest.mark.parametrize('fault',['source','unknown','payload','code','loader','program','capsule','unloaded','symlink','hardlink','writable'])
def test_fixed_program_rejects_changed_or_unproven_execution(tmp_path,fault):
    result=_run(_frame(tmp_path,fault))
    assert result.returncode!=0
    assert 'ACTUAL_PINNED_ENTRY_VERIFIED' not in result.stdout
    assert 'NATIVE_CHILD_PIN_' in result.stderr


def test_fixed_program_rejects_an_extended_budget(tmp_path):
    with pytest.raises(ValueError,match='CONTEXT'):
        native_child_bootstrap_script(_frame(tmp_path),1,15_000_000_002)


@pytest.mark.parametrize('fault',['batch-valid','batch-capsule','batch-program','batch-payload','batch-code','batch-expired'])
def test_bounded_batch_checks_actual_code_capture_and_deadline(tmp_path,fault):
    result=_run(_frame(tmp_path,fault))
    if fault=='batch-valid':
        assert result.returncode==0,result.stderr
        assert result.stdout=='ACTUAL_PINNED_BATCH_VERIFIED\n'
    else:
        assert result.returncode!=0
        assert 'ACTUAL_PINNED_BATCH_VERIFIED' not in result.stdout
        assert 'NATIVE_CHILD_PIN_' in result.stderr


def test_complete_capture_is_separate_from_exact_executed_plan(tmp_path):
    frame=json.loads(_frame(tmp_path))
    # A qualified module may be retained for later product composition without
    # claiming that its body executed in the earlier bootstrap census.
    unused=tmp_path/'unexecuted.py';payload=b'raise AssertionError("MUST_NOT_EXECUTE")\n'
    unused.write_bytes(payload);unused.chmod(0o600)
    frame['inventory'].append(['tools.unexecuted',sha256(payload).hexdigest()])
    frame['inventory'].sort()
    frame['sources'].append({'name':'tools.unexecuted','package':False,'path':str(unused.resolve())})
    canonical=lambda x:json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()
    raw=canonical(frame['inventory'])
    frame['plan']['source_inventory'].update(hash=sha256(raw).hexdigest(),bytes=str(len(raw)))
    frame['plan_hash']=sha256(canonical(frame['plan'])).hexdigest()
    result=_run(canonical(frame))
    assert result.returncode==0,result.stderr
    assert result.stdout=='ACTUAL_PINNED_ENTRY_VERIFIED\n'


@pytest.mark.parametrize('fault',['inventory-hash','inventory-size','duplicate','unsorted','plan-extra','plan-hash-change'])
def test_complete_capture_and_plan_require_independent_exact_binding(tmp_path,fault):
    frame=json.loads(_frame(tmp_path));canonical=lambda x:json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()
    if fault=='inventory-hash':frame['inventory'][0][1]='f'*64
    elif fault=='inventory-size':frame['plan']['source_inventory']['bytes']='1'
    elif fault in {'duplicate','unsorted'}:
        if fault=='duplicate':frame['inventory'].append(frame['inventory'][-1])
        else:frame['inventory'].reverse()
        raw=canonical(frame['inventory'])
        frame['plan']['source_inventory'].update(hash=sha256(raw).hexdigest(),bytes=str(len(raw)))
    elif fault=='plan-extra':frame['plan']['modules'].append({'name':'tools.unknown','digest':'f'*64})
    else:frame['plan']['modules'][0]['digest']='f'*64
    frame['plan_hash']=sha256(canonical(frame['plan'])).hexdigest()
    result=_run(canonical(frame))
    assert result.returncode!=0
    assert 'ACTUAL_PINNED_ENTRY_VERIFIED' not in result.stdout
    assert 'NATIVE_CHILD_PIN_' in result.stderr
