"""Production-shaped disposable Analysis: actual composition, governed fake Provider.

All product state is in the kernel-isolated test home. No network or real
Provider client is available. Only the explicitly requested evidence report is
retained outside that disposable root.
"""
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
import traceback

import pytest
from kronos.application.intraday_runtime import create_intraday_runtime
from kronos.application.intraday_discovery_operation import DiscoveryOperationState
from kronos.application.intraday_wo08_shadow import Wo08ShadowCollector
from kronos.intraday.wo08_shadow_persistence import Wo08ShadowStore
from kronos.common.maintenance_admission import MaintenanceAdmissionCoordinator
from tests.unit.application.test_intraday_discovery_operation import _configured_shared, _request_at, IST
from tests.unit.provider.test_shared_provider_runtime import _authenticate
from tests.unit.instrument.test_active_derivative_selection import _rows

BOUNDARY = datetime(2026, 8, 26, 11, 17, tzinfo=IST)


def _bytes(root):
    return {str(p.relative_to(root)):sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file()}


def _report(output, name, data):
    # Exact isolated test evidence destination supplied by the commissioning task.
    output.mkdir(parents=True,exist_ok=True)
    existing=list(output.glob(name+'-*.json'))
    path=output/(name+'-'+str(len(existing)+1).zfill(3)+'.json')
    path.write_text(json.dumps(data,sort_keys=True,indent=2,default=str)+'\n')
    return path


def test_production_composition_analysis_wo08_readiness_research_restart(tmp_path,monkeypatch,request):
    output=Path(request.config.option.xmlpath).parent if request.config.option.xmlpath else tmp_path
    ticks=[0]
    def advancing_clock():
        ticks[0]+=1
        return BOUNDARY-timedelta(seconds=1) if ticks[0]==1 else BOUNDARY+timedelta(milliseconds=ticks[0])
    shared, provider, factories, requests = _configured_shared()
    provider.capability.instrument_master_records=lambda:_rows()
    _authenticate(shared)
    evidence_root=tmp_path/'canonical-intraday-evidence'
    shadow=Wo08ShadowCollector(Wo08ShadowStore(evidence_root))
    admission=MaintenanceAdmissionCoordinator();shadow.bind_maintenance_admission(admission)
    runtime=create_intraday_runtime(shared,evidence_root=evidence_root,clock=advancing_clock,wo08_shadow=shadow)
    assert requests==[0] and shared.active_lease_count==0
    assert runtime.wo08_store.current_pointer() is None
    assert not runtime.review_v2_store.root.exists()
    errors=[]
    original_publish=runtime.wo08_publication.publish_run
    original_evaluate=runtime.wo09_application.evaluate_wo08
    def capture(fn):
        def wrapped(*args,**kwargs):
            try:return fn(*args,**kwargs)
            except Exception:
                errors.append(traceback.format_exc());raise
        return wrapped
    monkeypatch.setattr(runtime.wo08_publication,'publish_run',capture(original_publish))
    monkeypatch.setattr(runtime.wo09_application,'evaluate_wo08',capture(original_evaluate))
    def forbidden(*args,**kwargs):
        raise AssertionError('NEW_INTRADAY_WORK_REQUIRED_RETIRED_VISUAL_OWNER')
    for store in (runtime.review_v2_store,runtime.mcx_paired_review_store,runtime.visual_reconciliation_v2_store):
        monkeypatch.setattr(store,'page_read_scope',forbidden)
    result=runtime.discovery_v2_operation.execute(_request_at('WO08-PRODUCTION-FAITHFUL-REHEARSAL',BOUNDARY))
    assert shadow.close(), 'Research collector did not drain'
    preliminary=dict(stage='ANALYSIS_RETURNED',result=asdict(result),errors=errors,
        fake_historical_calls=requests[0],shadow=str(shadow.snapshot()))
    _report(output,'production-rehearsal-intermediate',preliminary)
    assert result.state is DiscoveryOperationState.COMPLETE, preliminary
    assert result.universe_count==98 and result.machine_fact_successes==98
    assert result.historical_request_count==requests[0]==490
    assert shared.active_lease_count==0 and admission.snapshot()['owners']=={}
    assert not errors
    run=runtime.probables_v2_store.load_current_run()
    assert len(run.results)==98
    assessments=runtime.wo08_store.current_run()
    readiness=runtime.wo09_application.restore()
    assert len(assessments)==len(readiness)==98
    assert all(record.wo08_identity in {a.identity for a in assessments} for _,record in readiness)
    by_identity={a.identity:a for a in assessments}
    assert all(record.created_at == datetime.fromisoformat(by_identity[record.wo08_identity].data['created_at']) for _,record in readiness)
    assert ticks[0]>1
    assert all(record.satisfied_count is None and record.outstanding_count is None for _,record in readiness)
    assert all(record.readiness_state.value in {'READINESS_UNAVAILABLE','HARD_GATE'} for _,record in readiness)
    assert all(a.data['criteria'][index]['state']=='NOT_COMMISSIONED' for a in assessments for index in range(1,5))
    assert {a.data['subject'] for a in assessments if a.data['market_family']=='MCX'} == {
        'MCX-SUBJECT-'+family for family in ('GOLDM','SILVERM','COPPER','CRUDE','NATGAS')}
    natgas=next(a for a in assessments if a.data['subject']=='MCX-SUBJECT-NATGAS')
    assert natgas.data['hard_gate']=='NATGAS_COMMISSIONING_HELD'
    visual_roots=(runtime.review_v2_store.root,runtime.mcx_paired_review_store.root,
                  runtime.visual_reconciliation_v2_store.root)
    assert all(not p.exists() for p in visual_roots)
    assert not runtime.wo09_store.handoffs.exists()
    assert runtime.futures_application.store.records('WO10_OPPORTUNITY_V1')==()
    from kronos.application.intraday_wo09_notifications import project_notification
    assert all(project_notification(record) is None for _,record in readiness)
    before_research=_bytes(runtime.wo08_store.root),_bytes(runtime.wo09_store.root)
    before_calls=requests[0]
    projection=runtime.research_application.project(ensure_origins=True)
    associations=runtime.research_store.records('WO12_WO08_ASSESSMENT_ASSOCIATION_V3')
    assert len(associations)==98
    metrics={row[0]:row for row in projection.analysis}
    assert metrics['WO08 population audit assessment count'][1]==98
    assert metrics['WO08 considered assessment count'][1]==0
    assert metrics['WO08 considered opportunity count'][1]==0
    assert metrics['WO08 unavailable criterion rate'][3] is None
    assert projection.opportunities==() and projection.events==()
    assert all(a.data['live_control_authority']=='NONE' for a in associations)
    assert all(a.data['assessment_identity'] in {r.identity for r in assessments} for a in associations)
    assert any(a.data['t0_state']=='EXACT_ORIGINAL_T0' for a in associations)
    assert before_research==(_bytes(runtime.wo08_store.root),_bytes(runtime.wo09_store.root))
    assert requests[0]==before_calls
    # Startup must validate existing assessments without evaluating new work.
    from kronos.application.intraday_wo08 import Wo08Publication
    from kronos.application.intraday_native_selection import NativePullbackPublication
    monkeypatch.setattr(Wo08Publication,'publish_run',forbidden)
    monkeypatch.setattr(NativePullbackPublication,'publish',forbidden)
    before_restart=_bytes(evidence_root)
    restored=create_intraday_runtime(shared,evidence_root=evidence_root,clock=lambda:BOUNDARY)
    assert restored.wo08_store.current_run()==assessments
    assert restored.wo09_application.restore()==readiness
    assert requests[0]==before_calls
    assert _bytes(evidence_root)==before_restart
    assert all(not p.exists() for p in visual_roots)
    native_store=runtime.probables_v2_application.native_selection.store
    native_manifest=json.loads((native_store.root/'runs'/(run.run_identity+'.json')).read_bytes())
    summary=dict(
        result='PRODUCTION_FAITHFUL_REHEARSAL_PASS', isolation='GOVERNED_KERNEL_PRODUCTION_AND_NETWORK_DENIAL',
        analysis_operation=asdict(result),probables_run=run.run_identity,probables_integrity=run.integrity_identity,
        source_population=98,native_companion_count=len(native_manifest['selections']),
        assessment_count=len(assessments),wo08_current_pointer=runtime.wo08_store.current_pointer(),
        wo08_methodologies=sorted({(r.data['methodology_identity'],r.data['methodology_version'],r.data['methodology_checksum']) for r in assessments}),
        assessment_dispositions=dict(Counter(r.data['disposition'] for r in assessments)),
        wo09_states=dict(Counter(r.readiness_state.value for _,r in readiness)),
        wo12_association_count=len(associations),wo12_audit_count=98,wo12_considered_assessment_count=0,
        wo12_considered_opportunity_count=0,wo12_eod_validation='NOT_EVALUABLE_NO_CONSIDERED_OPPORTUNITY',wo12_t0_states=dict(Counter(r.data['t0_state'] for r in associations)),
        wo12_live_control_authority='NONE',fake_historical_requests=requests[0],real_provider_calls=0,
        chart_analyst_required=False,wo07f_new_work_dependency='NONE',new_visual_artifacts=0,
        positive_handoffs=0,positive_wo10_opportunities=0,success_notification_sources=0,
        restart='EXACT_READBACK_NO_WRITE_NO_BACKFILL_NO_PROVIDER',natgas='HELD',trading_actions=0,
        paper_and_live_business_events='NOT_EXERCISED_NO_QUALIFYING_AUTHORITY',
        artifact_checksums=_bytes(evidence_root))
    _report(output,'production-faithful-rehearsal',summary)
