"""Actual canonical startup with disposable post-expiry retained authority."""
from dataclasses import replace
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
import json

import pytest

from tools import kronos_browser
from kronos.application.intraday_runtime import create_intraday_runtime
from kronos.browser.intraday_probables_v2_control import IntradayProbablesV2OperationalControl
from kronos.browser.server import KronosBrowserServer
from kronos.intraday.runtime_identity import LauncherConfiguration, create_runtime_manifest
from kronos.intraday.live_shadow import artifact, key, COHORT_A, COHORT_B
from kronos.intraday.live_shadow_quote import admission_pair
from kronos.common.maintenance import DrainStartupContext
from tests.unit.intraday.test_runtime_identity import _seed
from tests.unit.intraday.test_live_shadow import seed_row
from tests.unit.intraday.test_live_shadow_epochs import inventory
from tests.unit.intraday.test_live_shadow_successor_compatibility import relation
from tests.unit.application.test_intraday_discovery_operation import _configured_shared

START=datetime.fromisoformat('2026-09-12T07:50:33.006722+05:30')
END=datetime.fromisoformat('2026-10-12T07:50:33.006722+05:30')
AFTER=END+timedelta(hours=4)


def seed_authority(root, monkeypatch):
    shared,_,factories,requests=_configured_shared()
    runtime=create_intraday_runtime(shared,evidence_root=root,clock=lambda:START)
    control=IntradayProbablesV2OperationalControl(runtime.discovery_v2_operation,runtime.probables_v2_application,
        runtime.refresh_v2_provenance_store,startup_evidence=_seed(startup_boundary_at=START),
        launcher_configuration=LauncherConfiguration(0,False),clock=lambda:START)
    current=runtime.discovery_v2_operation.live_shadow
    target=current._manifest
    # Production-shaped predecessor proof and exact approved direct relation;
    # all artifacts are newly generated in this disposable test estate.
    historical=replace(target.capabilities[-1],implementation_digest='1'*64)
    old_manifest=create_runtime_manifest(target.startup,LauncherConfiguration(0,False),(*target.capabilities[:-1],historical))
    current._manifest=None;current.bind_runtime(old_manifest)
    current.accept_runtime(expected_revision='a'*40,request_identity='ISOLATED_ORIGINAL_AUTHORITY')
    current._probables_store=None
    with monkeypatch.context() as scoped:
        scoped.setattr("tests.unit.intraday.test_live_shadow.NOW",START)
        row,_=seed_row(current,price=None)
    raw=current._epochs.raw
    body=dict(row.body,assessment=admission_pair(None),boundary=START.isoformat(),captured_at=START.isoformat())
    path=raw.root/'observation'/(row.key+'.json');path.write_bytes(artifact('observation',row.key,body).payload)
    batch=raw.all('batch')[0].body
    for n in range(18):
        oid=key('observation',current._window.key,COHORT_B,str(n))
        bid=key('batch',current._window.key,COHORT_B,str(n))
        raw.retain(artifact('observation',oid,dict(body,result=str(n),cohort=COHORT_B,narrow=False,
            assessment=dict(body['assessment'],authority='WO06H_COHORT_B_RESEARCH_QUOTE'))))
        raw.retain(artifact('batch',bid,dict(batch,recorded_at=START.isoformat(),expected={COHORT_A:[],COHORT_B:[oid]})))
    from kronos.application.intraday_runtime_identity import compose_runtime_manifest
    current._manifest=compose_runtime_manifest(target.startup,LauncherConfiguration(0,False),runtime.discovery_v2_operation,control)
    current._epochs.retain(relation(current))
    assert factories==[] and requests==[0]
    return current


@pytest.mark.parametrize('fault',[None,'production_copy','corrupt','capability','configuration','missing_relation','pending',
    'swing','native','wo11','wo17','notification','provider','transport','final_write'])
def test_real_canonical_post_expiry_composition(tmp_path,monkeypatch,request,fault):
    from tests.unit.swing.v1.test_opportunity_continuity import scenario
    from tests.unit.swing.test_run_publication import make_checkpoint
    snapshot, bindings = scenario.__wrapped__()
    publication, _, _, _ = make_checkpoint(tmp_path/'swing-retained',snapshot,bindings)
    for name, store in (("MtfFactEvidenceStore",publication.mtf_store),
            ("NativeDiscoveryEvidenceStore",publication.native_store),
            ("RelativeContextEvidenceStore",publication.relative_store),
            ("LocalSwingRunProvenanceStore",publication.provenance_store)):
        monkeypatch.setattr(kronos_browser,name,lambda *_a,_store=store,**_kw:_store)
    production_copy = fault == 'production_copy'
    if production_copy:
        # Only the fresh filename-adapted child qualifies exact production map.
        import sys
        if not any(type(f).__name__=='CandidateFinder' for f in sys.meta_path):
            pytest.skip('Exact production-copy rehearsal runs in fresh canonical-filename child')
        import shutil
        from kronos.application.intraday_shadow_history import HistoricalIntradayLiveShadowService
        from kronos.intraday.live_shadow_persistence import ShadowStore
        output=Path(request.config.option.xmlpath).parent
        snapshot=output/'production-authority-snapshot'/'intraday-v1'
        manifest=json.loads((output/'PRODUCTION-AUTHORITY-SNAPSHOT-MANIFEST.json').read_bytes())
        for row in manifest['files']:
            copied=output/'production-authority-snapshot'/row['relative']
            assert sha256(copied.read_bytes()).hexdigest()==row['sha256']
        root=tmp_path/'intraday';shutil.copytree(snapshot,root)
        old=HistoricalIntradayLiveShadowService(store=ShadowStore(root),clock=lambda:AFTER)
        monkeypatch.setattr(kronos_browser,'LauncherConfiguration',lambda *_:LauncherConfiguration(8947,False))
        fault=None
    else:
        seed_authority(tmp_path/'fixture-warmup',monkeypatch)
        root=tmp_path/'intraday';old=seed_authority(root,monkeypatch)
    raw=old._epochs.raw
    if fault=='corrupt':next((raw.root/'acceptance').glob('*.json')).write_text('{}')
    if fault=='missing_relation':next(old._epochs.root.glob('WO06H-SUCCESSOR_COMPATIBILITY-*')).unlink()
    if fault=='pending':
        from tests.unit.intraday.test_live_shadow_successor_compatibility import mutate
        p=next(old._epochs.root.glob('WO06H-SUCCESSOR_COMPATIBILITY-*'));r=json.loads(p.read_bytes());p.unlink()
        old._epochs.retain(mutate(r,lambda b:b['owner_approvals'][0].update(disposition='PENDING')))
    before=inventory(raw.root)
    monkeypatch.setattr('tools.runtime_source_gate.qualify_startup',lambda *_:'a'*40)
    monkeypatch.setattr(kronos_browser,'_STARTUP_EVIDENCE',_seed(startup_boundary_at=AFTER,process_nonce='2'*32))
    checkpoint=DrainStartupContext('a'*64,'EMPTY',0,sha256(b'').hexdigest() if fault!='notification' else 'f'*64)
    monkeypatch.setattr(kronos_browser,'consume_startup_context',lambda *_a,**_kw:checkpoint)
    monkeypatch.setattr(kronos_browser,'_build_provider',lambda **_:pytest.fail('REAL_PROVIDER_FORBIDDEN'))
    compositions=[]
    def compose(provider,**kwargs):
        kwargs.update(evidence_root=root,clock=lambda:AFTER)
        runtime=create_intraday_runtime(provider,**kwargs);compositions.append(runtime)
        if fault=='wo11':runtime.lifecycle_application.last_failure='ISOLATED_RESTORATION_FAILURE'
        return runtime
    monkeypatch.setattr(kronos_browser,'create_intraday_runtime',compose)
    if fault=='configuration':monkeypatch.setattr(kronos_browser,'LauncherConfiguration',lambda *_:LauncherConfiguration(9999,False))
    if fault=='capability':
        from kronos.application import intraday_runtime_identity
        original=intraday_runtime_identity._capability
        def changed(identity,version,*functions):
            result=original(identity,version,*functions)
            return replace(result,implementation_digest='f'*64) if identity=='WO_05A_TRUSTED_TIME_ADMISSION' else result
        monkeypatch.setattr(intraday_runtime_identity,'_capability',changed)
    if fault=='provider':monkeypatch.setattr(kronos_browser.SharedAuthenticatedProviderRuntime,'read_only_status',lambda _:dict(capability_state='AVAILABLE'))
    if fault=='transport':
        from kronos.application.shared_monitoring import SharedSwingMonitoringHub
        monkeypatch.setattr(SharedSwingMonitoringHub,'active_session_count',property(lambda _:1))
    servers=[];create=kronos_browser.create_browser_server
    def capture(*args,**kwargs):
        server=create(*args,**kwargs);servers.append(server)
        if fault in ('swing','native'):
            outcomes=server.startup_restoration_outcomes()
            server.startup_restoration_outcomes=lambda:tuple((k,'FAILED' if k==('V3_RECORDS' if fault=='swing' else 'NATIVE_REVIEW') else v) for k,v in outcomes)
        return server
    monkeypatch.setattr(kronos_browser,'create_browser_server',capture)
    if fault=='wo17':
        monkeypatch.setattr(kronos_browser.IntradayWo17OperationalControl,'status_document',lambda _:dict(restoration_state='CORRUPT',failure_stage='RESTORE',failure_reason='ISOLATED',current_positions=[]))
    if fault=='final_write':
        monkeypatch.setattr('kronos.common.connection_governance.immutable_write',lambda *_:(_ for _ in ()).throw(OSError('isolated write')))
    observed=[]
    def serve(server,**_):
        state=server.connection_governance.maintenance_status()
        shadow=compositions[0].discovery_v2_operation.live_shadow.status()
        expected='READY' if fault is None else 'BLOCKED'
        if fault is None and not production_copy:
            assert shadow['runtime_proof']['capabilities']==old._runtime_proof()['capabilities'],json.dumps(dict(old=old._runtime_proof(),new=shadow['runtime_proof']),indent=2)
        assert state['startup']==expected,json.dumps(dict(fault=fault,state=state,shadow=shadow),indent=2)
        assert state['active'] is (fault is not None)
        if fault is None:
            if production_copy:
                from kronos.intraday.live_shadow_transition import capability_identity
                assert capability_identity(shadow['runtime_proof'])=='WO06H-CAPABILITY-f61cfe6c7395d0ee8554d82946a5a7fa88444c09151f53bc171253a3d35aa31b'
                collector=compositions[0].discovery_v2_operation.live_shadow
                from kronos.intraday.live_shadow import ShadowError
                with pytest.raises(ShadowError,match='SHADOW_RESTORATION_WINDOW_EXPIRED'):
                    collector.accept_runtime(expected_revision=collector._manifest.startup.source_revision,
                        request_identity='FORBIDDEN_POST_EXPIRY_ACCEPTANCE')
                assert collector._accepted is None
                assert inventory(raw.root)==before
            assert shadow['acceptance_disposition']=='HISTORICAL_ACCEPTANCE_EXPIRED'
            assert not shadow['enabled'] and not shadow['runtime_accepted']
            assert shadow['counts']['cohort_a']==1 and shadow['counts']['cohort_b']==18
            assert shadow['counts']['eod_available']==0
            server.connection_governance.require_operations()
            runtime=compositions[0]
            assert runtime.wo08_store.current_run()==()
            assert runtime.wo09_application.restore()==()
            assert runtime.research_application.project().opportunities==()
            assert server.intraday_notifications.checkpoint()['state']=='EMPTY'
            assert server.provider_runtime.read_only_status()['capability_state']=='ABSENT'
            assert all(v in ('SUCCESS','NOT_APPLICABLE','APPLICABILITY_NOT_ESTABLISHED') for _,v in server.startup_restoration_outcomes())
        observed.append(dict(fault=fault,maintenance=state,shadow=shadow,swing=server.startup_restoration_outcomes()))
    monkeypatch.setattr(KronosBrowserServer,'serve_forever',serve)
    try:
        if fault=='notification':
            with pytest.raises(ValueError,match='WO13_NOTIFICATION_CHECKPOINT_MISMATCH'):
                kronos_browser.main(['--port','0','--no-browser'])
            assert not observed
            assert servers[0].connection_governance.startup_state!='READY'
        else:assert kronos_browser.main(['--port','0','--no-browser'])==0
    finally:
        for server in servers:
            if fault=='transport':server.swing_monitoring_hub._session=None
            server.server_close()
    assert inventory(raw.root)==before
    output=Path(request.config.option.xmlpath).parent if request.config.option.xmlpath else tmp_path
    (output/('canonical-post-expiry-'+('production-copy' if production_copy else str(fault))+'.json')).write_text(json.dumps(observed,indent=2,default=str)+'\n')


def test_normal_analysis_after_expiry_preserves_all_shadow_bytes(tmp_path,monkeypatch,request):
    from tests.unit.provider.test_shared_provider_runtime import _authenticate
    from tests.unit.instrument.test_active_derivative_selection import _rows
    from tests.unit.application.test_intraday_discovery_operation import _request_at
    from kronos.application.intraday_discovery_operation import DiscoveryOperationState
    seed_authority(tmp_path/'warmup',monkeypatch)
    root=tmp_path/'intraday';old=seed_authority(root,monkeypatch)
    before=inventory(old._epochs.raw.root)
    shared,provider,factories,calls=_configured_shared()
    provider.capability.instrument_master_records=lambda:_rows()
    _authenticate(shared)
    ticks=[0]
    def clock():
        ticks[0]+=1
        return AFTER-timedelta(seconds=1) if ticks[0]==1 else AFTER+timedelta(milliseconds=ticks[0])
    runtime=create_intraday_runtime(shared,evidence_root=root,clock=clock)
    control=IntradayProbablesV2OperationalControl(runtime.discovery_v2_operation,runtime.probables_v2_application,
        runtime.refresh_v2_provenance_store,startup_evidence=_seed(startup_boundary_at=AFTER,process_nonce='3'*32),
        launcher_configuration=LauncherConfiguration(0,False),clock=clock)
    shadow=runtime.discovery_v2_operation.live_shadow
    assert shadow.status()['acceptance_disposition']=='HISTORICAL_ACCEPTANCE_EXPIRED'
    result=runtime.discovery_v2_operation.execute(_request_at('IWO06A-POST-EXPIRY-FAKE-PROVIDER',AFTER))
    from dataclasses import asdict
    assert result.state is DiscoveryOperationState.COMPLETE,json.dumps(asdict(result),indent=2,default=str)
    assert result.universe_count==98 and result.machine_fact_successes==98
    assert len(runtime.wo08_store.current_run())==98
    assert len(runtime.wo09_application.restore())==98
    assert runtime.research_application.project(ensure_origins=True) is not None
    assert shadow.status()['counts']['cohort_a']==1 and shadow.status()['counts']['cohort_b']==18
    assert inventory(old._epochs.raw.root)==before
    restored=create_intraday_runtime(shared,evidence_root=root,clock=clock)
    assert restored.wo08_store.current_run()==runtime.wo08_store.current_run()
    assert restored.wo09_application.restore()==runtime.wo09_application.restore()
    assert inventory(old._epochs.raw.root)==before
    output=Path(request.config.option.xmlpath).parent if request.config.option.xmlpath else tmp_path
    (output/'post-expiry-normal-analysis.json').write_text(json.dumps(dict(
        outcome=result.state.value,universe=98,wo08=98,wo09=98,wo12='AVAILABLE',
        real_provider_calls=0,fake_provider_history_calls=calls[0],shadow_counts=shadow.status()['counts'],
        all_shadow_bytes_unchanged=True,restoration='PASS'),indent=2)+'\n')
