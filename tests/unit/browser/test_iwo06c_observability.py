"""06C isolated UX/read-model evidence; no production or predictive authority."""
from dataclasses import asdict, replace
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
import json
import os
import time
import pytest

from kronos.browser.intraday_wo08 import render_machine_review, render_sponsor_opportunities, _duration_text, _analysis_history
from kronos.browser.intraday_probables_v2_control import analysis_history_entry
from kronos.intraday.refresh_v2 import create_refresh_v2_provenance, RefreshV2Outcome
from kronos.intraday.refresh_v2_persistence import RefreshV2ProvenanceStore
from kronos.intraday.operation_accounting import create_operation_accounting
from tests.unit.browser.test_intraday_attention_funnel import documents
from tests.unit.browser.test_product_route_isolation import _snapshot
from tests.unit.intraday.test_probables_v2_refresh_control import _control, SEMANTIC_BOUNDARY


def inventory(root):
    return {str(p):sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}


def clone(record, **changes):
    core=asdict(record)
    for k in ('provenance_identity','integrity_identity','contract_identity','contract_version'):core.pop(k)
    return create_refresh_v2_provenance(**{**core,**changes})


def history_fixture(tmp_path, seconds=82):
    _,runtime,control,calls,requests=_control(tmp_path,authenticated=False)
    control.execute_document({})
    seed=control._store.latest()
    started=seed.operation_completed_at
    accounting=create_operation_accounting(operation_identity='KRONOS-INTRADAY-DISCOVERY-OPERATION-ISOLATED',
        operation_kind='V2',analysis_boundary=SEMANTIC_BOUNDARY,trusted_admission_time=None,
        operation_started_at=started,provider_acquisition_started_at=None,
        operation_completed_at=started+timedelta(seconds=seconds),discovery_run_identity=None,
        governed_members=98,nse_index_focus_members=93,nominal_evaluation_members=98,nominal_timeframe_coverage=392,
        factually_evaluable=98,factual_failures=0,prerequisite_unavailable=0,not_reached_members=0,
        actual_provider_requests=None,request_categories=None,benchmark_subject_requests=None)
    record=clone(seed,request_identity='HISTORY-TIMED',observation_boundary=SEMANTIC_BOUNDARY,
        outcome=RefreshV2Outcome.FAILED,failure='ISOLATED_FAILURE',
        operation_accounting_identity=accounting.accounting_identity,
        operation_completed_at=accounting.operation_completed_at)
    assert calls==[] and requests==[0]
    return runtime,control,record,accounting


@pytest.mark.parametrize('microseconds,expected',[(None,'Duration unavailable'),(-1,'Duration unavailable'),
    (0,'0s'),(1000000,'1s'),(59000000,'59s'),(81568302,'1m 22s'),(181000000,'3m 1s')])
def test_duration_formatting(microseconds,expected):
    assert _duration_text(microseconds)==expected


def test_exact_accounting_duration_and_missing_are_not_click_or_render_time(tmp_path):
    runtime,control,r,a=history_fixture(tmp_path)
    entry=analysis_history_entry(r,a)
    assert entry['duration_microseconds']==82000000 and entry['analysed_population']==98
    assert entry['result']=='FAILED'  # Actual retained outcome is not relabelled success.
    assert analysis_history_entry(r,None)['duration_microseconds'] is None
    with pytest.raises(ValueError,match='BINDING_INVALID'):
        analysis_history_entry(clone(r,operation_accounting_identity='UNRELATED'),a)
    html=_analysis_history(dict(recent_analysis_history=(entry,analysis_history_entry(r,None))))
    assert '1m 22s' in html and 'Duration unavailable' in html and '98 analysed' in html
    assert 'Exact operation timing' in html and r.provenance_identity in html


def test_recent_selection_bounded_no_get_scan_restart_and_fresh_integrity(tmp_path,monkeypatch):
    runtime,control,r,a=history_fixture(tmp_path)
    store=control._store
    for i in range(9):
        store.retain(clone(r,request_identity='HISTORY-'+str(i),operation_completed_at=r.operation_completed_at+timedelta(days=i)))
    assert len(store.recent())==5
    original=inventory(tmp_path)
    restarted=RefreshV2ProvenanceStore(tmp_path.resolve())
    assert restarted.recent()==store.recent()
    with monkeypatch.context() as scoped:
        scoped.setattr(Path,'glob',lambda *a,**k:pytest.fail('GET scanned retained history'))
        assert len(store.recent())==5 and len(restarted.recent())==5
    assert original==inventory(tmp_path)
    older=store.recent()[-1];path=store._path(older.provenance_identity)
    path.write_bytes(b'corrupt')
    with pytest.raises(ValueError):store.recent()
    assert store.latest().request_identity=='HISTORY-8'  # No operational latest invalidation by a historical-view failure.


def test_control_history_reads_exact_retained_accounting_no_provider_or_writes(tmp_path):
    runtime,control,r,a=history_fixture(tmp_path)
    runtime.discovery_v2_operation.accounting_store.retain(a)
    control._store.retain(r)
    before=inventory(tmp_path)
    entries=control.analysis_history_document()
    assert entries[0]==analysis_history_entry(r,a)
    assert before==inventory(tmp_path)


def test_final_hierarchy_complete_diagnostics_and_unavailable_score(tmp_path):
    status,readiness=documents(tmp_path)
    before=inventory(tmp_path)
    review=render_machine_review(_snapshot(),status,readiness)
    primary,diagnostics=review.split('<details id="intraday-diagnostics">',1)
    for label in ('ANALYSED','SECONDARY REVIEW','NEAR READY','READY','NOW'):assert label+'</span><strong>' in primary
    assert 'SECONDARY REVIEW</span><strong>11' in primary
    assert diagnostics.count('id="diagnostic-candidate-')==98
    assert 'Secondary Review only' in diagnostics and 'data-filter="secondary"' in diagnostics
    assert 'data-secondary-review="true"' in diagnostics
    opportunities=render_sponsor_opportunities(_snapshot(),status,readiness)
    assert 'NEAR READY' not in opportunities and 'SECONDARY REVIEW' not in opportunities
    assert opportunities.count('id="review-candidate-')==5
    assert 'Awaiting assessment evidence' in review
    unavailable=next(r for r in status['assessments'] if r['subject']=='NSE-EQ-UNAVAILABLE')
    row=diagnostics.split('id="diagnostic-candidate-'+unavailable['probable_result_identity']+'"')[1].split('</tr>')[0]
    assert '>Unavailable</td>' in row and '1/5' not in row and '0/5' not in row
    assert inventory(tmp_path)==before


@pytest.mark.parametrize('condition',['expired','superseded','missing','direction','subject','run'])
def test_secondary_count_requires_current_exact_authority(tmp_path,condition):
    from kronos.browser.dashboard import IntradayDashboardSummary
    status,readiness=documents(tmp_path)
    if condition in {'expired','missing'}:readiness['operational_summary']=IntradayDashboardSummary() if condition=='missing' else IntradayDashboardSummary(0,0,'NO_CURRENT_READINESS')
    elif condition=='superseded':status['currentness']='SUPERSEDED'
    else:
        field={'direction':'direction','subject':'instrument','run':'probables_run_identity'}[condition]
        readiness['cards']=tuple(replace(c,**{field:'UNRELATED'}) for c in readiness['cards'])
    html=render_machine_review(_snapshot(),status,readiness)
    assert ('SECONDARY REVIEW</span><strong>—' if condition=='missing' else 'SECONDARY REVIEW</span><strong>0') in html
    assert html.count('id="diagnostic-candidate-')==98


def test_98_render_timings_and_artifacts(tmp_path):
    from kronos.browser.dashboard import project_sponsor_dashboard
    from kronos.browser.views import render_dashboard
    from kronos.application.notifications import NotificationWorkspaceSnapshot
    status,readiness=documents(tmp_path)
    dashboard=replace(project_sponsor_dashboard(_snapshot(),None,(),NotificationWorkspaceSnapshot(())),intraday=readiness['operational_summary'])
    functions={'opportunities':lambda:render_sponsor_opportunities(_snapshot(),status,readiness),
        'review':lambda:render_machine_review(_snapshot(),status,readiness),
        'diagnostics':lambda:render_machine_review(_snapshot(),status,readiness),
        'dashboard':lambda:render_dashboard(_snapshot(),dashboard)}
    import subprocess,types,sys
    baseline=types.ModuleType('iwo06c_baseline_view')
    sys.modules[baseline.__name__]=baseline
    payload=subprocess.check_output(['git','show','40312309bca548a89ae3191fe96a7152728a300e:src/kronos/browser/intraday_wo08.py'])
    exec(compile(payload,'ISOLATED_BASELINE_VIEW.py','exec'),baseline.__dict__)
    results={};pages={};before=inventory(tmp_path)
    for name,render in functions.items():
        timings=[]
        for _ in range(3):
            at=time.perf_counter();pages[name]=render();timings.append(time.perf_counter()-at)
        results[name]={'first_seconds':timings[0],'repeated_seconds':timings[1:],'scope':'isolated 98-row rendering, not production read/Provider timing'}
    for name,render in {'opportunities':lambda:baseline.render_sponsor_opportunities(_snapshot(),status,readiness),
            'review':lambda:baseline.render_machine_review(_snapshot(),status,readiness)}.items():
        samples=[]
        for _ in range(3):
            at=time.perf_counter();body=render();samples.append(time.perf_counter()-at)
        results[name]['baseline_seconds']=samples
        results[name]['candidate_bytes']=len(pages[name].encode())
        results[name]['baseline_bytes']=len(body.encode())
    sys.modules.pop(baseline.__name__)
    assert before==inventory(tmp_path)
    if os.environ.get('IWO06C_OUTPUT'):
        out=Path(os.environ['IWO06C_OUTPUT']);out.mkdir(parents=True,exist_ok=True)
        for name,body in pages.items():(out/(name+'.html')).write_text(body)
        (out/'timings.json').write_text(json.dumps(results,indent=2))


def test_protected_runtime_control_code_identity_unchanged():
    import ast, marshal, subprocess
    import kronos.browser.intraday_probables_v2_control as module
    base=subprocess.check_output(['git','show','40312309bca548a89ae3191fe96a7152728a300e:src/kronos/browser/intraday_probables_v2_control.py']).decode()
    current=Path(module.__file__).read_text()
    def extract(text):
        parsed=ast.parse(text)
        cls=next(n for n in parsed.body if isinstance(n,ast.ClassDef) and n.name=='IntradayProbablesV2OperationalControl')
        cls.body=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in {'execute_document','status_document'}]
        tree=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),cls],type_ignores=[])
        ast.fix_missing_locations(tree)
        ns={'_LATEST_EVALUABLE_UNSET':object()}
        exec(compile(tree,'CANONICAL_CONTROL.py','exec'),ns)
        return {name:marshal.dumps(getattr(ns[cls.name],name).__code__) for name in ('execute_document','status_document')}
    assert extract(base)==extract(current)
