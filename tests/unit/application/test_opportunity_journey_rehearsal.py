"""Full canonical disposable Analysis chain; no production or network authority."""
import json
from hashlib import sha256
from pathlib import Path
import pytest
from kronos.application.intraday_opportunity_journey import JOURNEY_COLUMNS


@pytest.mark.parametrize('direction',['LONG','SHORT'])
def test_experimental_journey_workbook_from_ordinary_analysis(tmp_path,monkeypatch,request,direction):
    import tests.unit.application.test_iwo_experimental_rehearsal as chain
    factory=chain.create_intraday_runtime
    runtimes=[]
    configured=chain.configured_experimental_runtime
    configurations=[]
    def configure(*args,**kwargs):
        values=configured(*args,**kwargs);configurations.append(values);return values
    monkeypatch.setattr(chain,'configured_experimental_runtime',configure)
    def capture(*args,**kwargs):
        runtime=factory(*args,**kwargs);runtimes.append(runtime);return runtime
    monkeypatch.setattr(chain,'create_intraday_runtime',capture)
    chain.test_normal_analysis_experimental_population_progression_and_restart(tmp_path,direction,monkeypatch,request)
    runtime=runtimes[0]
    research=runtime.research_application
    before={str(p):sha256(p.read_bytes()).hexdigest() for p in (tmp_path/'evidence').rglob('*') if p.is_file()}
    projection=research.project()
    rows=[dict(zip(JOURNEY_COLUMNS,row)) for row in projection.journey]
    assert rows and {r['Market'] for r in rows}=={'NSE','MCX'}
    positives=[r for r in rows if r['First Five Fact']!='NOT_ESTABLISHED']
    assert {r['Market'] for r in positives}=={'NSE','MCX'}
    assert all(r['Direction']==r['Final WO09 Direction']==direction for r in positives)
    for row in positives:
        assert row['Initial Count']==4
        assert row['Missing at 4']=='I2:OUTSTANDING'
        assert row['Watch Eligible at 4']=='YES'
        assert row['Wake Hint Count']>=1
        assert row['First 4 of 5 At']!=row['First 5 of 5 At']
        assert row['Assessment Price']!=row['5 of 5 Measurement']
        assert row['Entry Met']==row['Target Met']==row['Stop Met']=='NOT_EVALUABLE'
        if row['Market']=='MCX':assert row['Exact MCX Contract']!='N/A'
    assert sum(r['Paper Created']=='YES' for r in positives)==2
    assert {r['Paper Class'] for r in positives if r['Paper Created']=='YES'}=={'PAPER_POSITION','PAPER_OBSERVATION'}
    assert before=={str(p):sha256(p.read_bytes()).hexdigest() for p in (tmp_path/'evidence').rglob('*') if p.is_file()}
    # Continue the existing retained tracks through the actual lifecycle owner.
    # Only fake capabilities and the already configured fake factual source run.
    from datetime import timedelta
    from decimal import Decimal
    from kronos.application.shared_monitoring import SharedSwingMonitoringHub
    from kronos.application.intraday_lifecycle_intake import instrument_record
    from kronos.provider.contracts.monitoring import ProviderMarketTick
    from tests.unit.intraday.test_wo11_lifecycle_application import Capability,_wait_for_work
    lifecycle=runtime.lifecycle_application
    now=configurations[0][2]
    cap=Capability();hub=SharedSwingMonitoringHub();lifecycle.bind_monitoring(hub,lambda:cap)
    lifecycle.pulse()
    tracks=lifecycle.store.restore()
    assert all(t.data['state']=='AWAITING_ENTRY' for t in tracks),[(t.data['state'],lifecycle.last_failure) for t in tracks]
    sign=Decimal(1) if direction=='LONG' else Decimal(-1)
    for track in tracks:
        auth=track.data['track_identity']
        def emit(price,sequence):
            now[0]+=timedelta(seconds=1)
            tick=ProviderMarketTick(instrument_record(track.data['intake']['future']),price,now[0],now[0],
                'KITE_CONNECT_WEBSOCKET','DISPOSABLE-JOURNEY-LIFECYCLE',sequence,True,True,True)
            cap.consumer.on_market_tick(tick)
            if lifecycle.work_status()['owned_workers']:_wait_for_work(lifecycle,'IDLE')
            return next(t for t in lifecycle.store.restore() if t.data['track_identity']==auth)
        entry=Decimal(track.data['intake']['entry'])+sign
        emit(entry,1) # post-restoration continuity baseline
        entered=emit(entry,2)
        assert entered.data['entry'] is not None,entered.data
        kind='target' if track.data['intake']['subject'].startswith('NSE-') else 'stop'
        closed=emit(Decimal(track.data['intake'][kind])+(sign if kind=='target' else -sign),3)
        assert closed.data['exit']['reason']==('TARGET' if kind=='target' else 'STOP_LOSS')
    source_before={str(p):sha256(p.read_bytes()).hexdigest() for p in (tmp_path/'evidence').rglob('*') if p.is_file()}
    projection=research.project()
    rows=[dict(zip(JOURNEY_COLUMNS,row)) for row in projection.journey]
    for track in lifecycle.store.restore():
        row=next(r for r in rows if r['Security']==track.data['intake']['subject'])
        assert row['Entry Met']=='YES' and row['Monitoring Gap Count']>=1
        assert row['Model Entry Price']==Decimal(track.data['entry']['price'])
        target=track.data['exit']['reason']=='TARGET'
        assert row['Target Met' if target else 'Stop Met']=='YES'
        assert row['Stop Met' if target else 'Target Met']=='NOT_EVALUABLE'
        assert row['First Terminal Event']==('TARGET_FIRST' if target else 'STOP_FIRST')
        assert row['Future Entry']==Decimal(track.data['intake']['entry'])
        assert row['Lifecycle References']==track.identity
    assert source_before=={str(p):sha256(p.read_bytes()).hexdigest() for p in (tmp_path/'evidence').rglob('*') if p.is_file()}
    from kronos.browser.intraday_research import export_research_workbook,validate_research_workbook
    workbook=export_research_workbook(projection)
    validate_research_workbook(workbook,projection)
    from tests.unit.application.test_opportunity_journey import assert_journey_readback
    assert_journey_readback(workbook,projection.journey)
    if request.config.option.xmlpath:
        out=Path(request.config.option.xmlpath).parent
        (out/f'Opportunity_Journey_{direction}.xlsx').write_bytes(workbook)
        (out/f'Opportunity_Journey_{direction}.json').write_text(json.dumps(dict(
            direction=direction,source_boundary='DISPOSABLE_CANONICAL_FACTORY_ORDINARY_ANALYSIS',
            rows=rows,source_lifecycle=[dict(current_identity=t.identity,entry=t.data['entry'],exit=t.data['exit'],
                comparison_identity=t.data['intake']['comparison_identity'],subject=t.data['intake']['subject'],gaps=t.data['gaps'])
                for t in lifecycle.store.restore()],workbook_sha256=sha256(workbook).hexdigest(),
            same_interval='DEFERRED_OUTSIDE_V1',network='NO_NETWORK_FAKE_PROVIDER'),default=str,indent=2))
