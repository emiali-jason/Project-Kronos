"""Reporting-only V1: exact cohort and published WO11 events, never candle inference."""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
import pytest
from kronos.application.intraday_opportunity_journey import JOURNEY_COLUMNS, _lifecycle_values
from kronos.browser.intraday_research import export_research_workbook
from tests.unit.application.test_intraday_research import _application
from tests.unit.application.test_intraday_wo08_research import considered_application


def test_versioned_sheet_preserves_legacy_rows_and_frozen_policy(tmp_path):
    app,_,_=considered_application(tmp_path,later=True)
    legacy=app.project(ensure_origins=True,workbook_version='2.2.0')
    current=app.project()
    assert current.opportunities==legacy.opportunities
    assert (current.tracks,current.events,current.analysis,current.data_quality)==(legacy.tracks,legacy.events,legacy.analysis,legacy.data_quality)
    assert len(current.journey)==1
    row=dict(zip(JOURNEY_COLUMNS,current.journey[0]))
    assert JOURNEY_COLUMNS[0]=='Opportunity ID'
    assert row['Opportunity Identity']!=row['Consideration Identity']
    assert row['Initial Count']=='NOT_ESTABLISHED'
    assert row['Original Disposition']=='ASSESSMENT_UNAVAILABLE'
    assert row['I2']=='NOT_COMMISSIONED'
    assert row['First 5 of 5 At']==row['First Retained 5 Snapshot At']=='NOT_ESTABLISHED'
    assert row['Entry Met']==row['Target Met']==row['Stop Met']=='NOT_EVALUABLE'
    assert row['Paper Created']=='NO'
    assert row['Identified At'].endswith('+05:30 IST')
    a,b=map(lambda p:ZipFile(BytesIO(export_research_workbook(p))),(legacy,current))
    assert len([n for n in b.namelist() if n.startswith('xl/tables/table')])==7
    for i in range(1,6):
        assert a.read(f'xl/worksheets/sheet{i}.xml')==b.read(f'xl/worksheets/sheet{i}.xml')
        assert a.read(f'xl/tables/table{i}.xml')==b.read(f'xl/tables/table{i}.xml')
    sheet=b.read('xl/worksheets/sheet7.xml').decode()
    assert 'frozen' in sheet and '<autoFilter' in sheet and 'ht="32"' in sheet
    assert '<alignment wrapText="1" vertical="center"/>' in b.read('xl/styles.xml').decode()
    assert dict(legacy.metadata)['policy_checksum']==dict(current.metadata)['policy_checksum']
    assert dict(current.metadata)['same_interval_acceptance']=='DEFERRED_OUTSIDE_V1'


def test_legacy_receipt_exact_byte_recovery_and_new_upgrade(tmp_path):
    app,_=_application(tmp_path)
    projection=app.project(ensure_origins=True,workbook_version='2.2.0')
    with app.store.transaction():
        result=app._update_month_locked(operation_identity='LEGACY',_projection=projection)
    original=result.workbook_path.read_bytes()
    receipt=app.store.current_receipt(projection.year_month)
    assert receipt.data['schema_version']=='2.2.0'
    result.workbook_path.write_bytes(b'corrupt')
    with app.store.transaction():
        recovered=app._recover_receipted_workbook(receipt,operation_identity='RECOVERY',completed_at=app.clock())
    assert recovered.workbook_sha256==sha256(original).hexdigest()
    assert recovered.workbook_path.read_bytes()==original
    assert app.store.current_receipt(projection.year_month)==receipt
    assert len([n for n in ZipFile(BytesIO(original)).namelist() if n.startswith('xl/tables/table')])==6
    upgraded=app.update(operation_identity='UPGRADE')
    assert upgraded.outcome=='PUBLISHED'
    assert app.store.current_receipt(projection.year_month).data['schema_version']=='2.3.0'
    assert app.store.load(receipt.identity)==receipt
    assert app.update(operation_identity='REPEAT').outcome=='ALREADY_UP_TO_DATE'


@pytest.mark.parametrize('direction',['LONG','SHORT'])
@pytest.mark.parametrize('exit_kind',['TARGET','STOP_LOSS','NONE'])
def test_retained_governed_lifecycle_chronology(tmp_path,monkeypatch,direction,exit_kind):
    from tests.unit.intraday.test_wo11_lifecycle_application import fixture,emit
    app,h,_,provider,clock,cap,_=fixture(tmp_path,monkeypatch,direction)
    app.action(handoff_identity=h.identity,action='ACTIVATE_PAPER',action_identity='ARM')
    clock[0]+=timedelta(minutes=5);app.pulse()
    current=app.store.restore()[0]
    clock[0]+=timedelta(seconds=1)
    sign=Decimal(1) if direction=='LONG' else Decimal(-1)
    current=emit(app,cap,clock,current,str(Decimal(current.data['intake']['entry'])+sign))
    assert current.data['state']=='ACTIVE'
    if exit_kind!='NONE':
        clock[0]+=timedelta(seconds=1)
        level='target' if exit_kind=='TARGET' else 'stop'
        current=emit(app,cap,clock,current,str(Decimal(current.data['intake'][level])+(sign if level=='target' else -sign)))
    if exit_kind=='NONE':
        from kronos.provider.contracts.monitoring import MonitoringConnectionState
        app._connection(current.data['track_identity'],MonitoringConnectionState.DISCONNECTED)
        current=app.store.restore()[0]
    before={p:p.read_bytes() for p in app.store.root.rglob('*') if p.is_file()}
    values=_lifecycle_values(app.store.restore(),app.store)
    assert values['Entry Met']=='YES'
    assert values['Entry First Met At']==current.data['entry']['at']
    assert values['Target Met']==('YES' if exit_kind=='TARGET' else 'NOT_EVALUABLE')
    assert values['Stop Met']==('YES' if exit_kind=='STOP_LOSS' else 'NOT_EVALUABLE')
    if exit_kind!='NONE':
        assert values['First Terminal Event']==('TARGET_FIRST' if exit_kind=='TARGET' else 'STOP_FIRST')
        assert values['Target First Met At' if exit_kind=='TARGET' else 'Stop First Met At']==current.data['exit']['at']
    assert before=={p:p.read_bytes() for p in app.store.root.rglob('*') if p.is_file()}
    assert len(provider.calls)==1
    if exit_kind=='NONE':
        assert values['Monitoring Gap Count']>=1
        assert values['Chronology Coverage']=='RETAINED_WO11_MODEL_EVENTS_WITH_MONITORING_GAPS'
    # Multiple tracks cannot provide one synthetic chronology even when their
    # retained entry times happen to agree. No scalar event is selected.
    ambiguous=_lifecycle_values((current,current),app.store)
    assert ambiguous['Entry Met']==ambiguous['Target Met']==ambiguous['Stop Met']=='NOT_EVALUABLE'
    assert ambiguous['Chronology Coverage']=='MULTIPLE_RETAINED_TRACKS'


@pytest.mark.parametrize('order',[('LONG','SHORT'),('SHORT','LONG')])
def test_same_opportunity_direction_reversal_never_splices_progression(tmp_path,order):
    """Typed store/projection seam; not a new ordinary Analysis publication."""
    from types import SimpleNamespace
    from datetime import datetime
    from kronos.intraday.probables_v2_persistence import ProbablesV2Store
    from kronos.intraday.wo09_persistence import Wo09Store
    from kronos.intraday.wo12_research_store import ResearchStore
    from kronos.application.intraday_research import IntradayResearchApplication
    from tests.unit.intraday.test_wo08_experimental import experimental_fixture
    from tests.unit.intraday.test_wo09_experimental import publish,origin_for
    from tests.unit.application.test_intraday_research import _EmptyStore,_Lifecycle
    rows=[experimental_fixture(d) for d in ('LONG','SHORT')]
    probables=ProbablesV2Store(tmp_path/'probables')
    wo09=Wo09Store(tmp_path/'wo09')
    origin=origin_for(rows[0][-1]);research=ResearchStore(tmp_path/'research');research.retain(origin)
    at=datetime.fromisoformat(rows[0][-1].data['created_at'])
    readiness=[]
    for i,(_,_,mapping,run,_,assessment) in enumerate(rows if order[0]=='LONG' else rows[::-1]):
        probables.retain_complete(run=run,mappings=(mapping,))
        r,_=publish(wo09,assessment,origin,at+timedelta(seconds=i+1));readiness.append(r)
    app=IntradayResearchApplication(probables=probables,wo09=wo09,futures=_EmptyStore(),lifecycle=_Lifecycle(),
        store=research,publication_root=tmp_path/'Statistics',clock=lambda:at+timedelta(seconds=3),
        wo08=SimpleNamespace(records=lambda:tuple(r[-1] for r in rows)))
    from kronos.application.intraday_wo08_research import associate_assessments
    from kronos.intraday.wo12_eod_validation import consideration
    associations=associate_assessments(assessments=app.wo08,shadow=None,probables=probables,origins=(origin,),
        readiness=app._readiness_history_by_result(),futures=app.futures,lifecycle=app.lifecycle,watch_store=wo09)
    research.retain(consideration(associations[0],probables,None))
    projection=app.project()
    assert len(projection.journey)==1
    row=dict(zip(JOURNEY_COLUMNS,projection.journey[0]))
    assert row['Direction']=='LONG' and row['Final WO09 Direction']==order[-1]
    assert row['Initial WO09 Direction']==order[0]
    readiness=sorted(readiness,key=lambda r:r.direction)
    assert row['Readiness References']==readiness[0].readiness_identity
    assert row['Other Scope Readiness References']==readiness[1].readiness_identity
    assert row['First Five Fact']==readiness[0].first_five_document['fact_identity']
    assert row['First Five Fact']!=readiness[1].first_five_document['fact_identity']
    assert row['5 of 5 Measurement']==Decimal(rows[0][-1].data['experimental_measurement']['price'])
    assert row['WO08 Identity']==rows[0][-1].identity


def test_availability_status_is_lightweight_and_does_not_publish(tmp_path,monkeypatch):
    app,_=_application(tmp_path)
    def forbidden(**kwargs):raise AssertionError('status must not project or publish')
    monkeypatch.setattr(app,'project',forbidden)
    status=app.status_document()
    assert status['available_workbook_version']=='2.3.0'
    assert status['opportunity_journey_version']=='1.0.0'
    assert status['chronology_authority']=='RETAINED_GOVERNED_WO11_MODEL_EVENTS_ONLY'
    assert not app.store.root.exists() and not app.publication_root.exists()


def test_ambiguity_successor_never_recovers_old_positive_exit(tmp_path,monkeypatch):
    from tests.unit.intraday.test_wo11_lifecycle_application import fixture,emit
    from kronos.application.intraday_lifecycle_intake import instrument_record
    from kronos.intraday.wo11_lifecycle_contract import websocket_observation
    from kronos.intraday.wo11_lifecycle import observe
    from kronos.provider.contracts.monitoring import ProviderMarketTick
    app,h,_,_,clock,cap,_=fixture(tmp_path,monkeypatch)
    app.action(handoff_identity=h.identity,action='ACTIVATE_PAPER',action_identity='ARM')
    clock[0]+=timedelta(minutes=5);app.pulse();current=app.store.restore()[0]
    clock[0]+=timedelta(seconds=1)
    current=emit(app,cap,clock,current,str(Decimal(current.data['intake']['entry'])+1))
    clock[0]+=timedelta(seconds=1)
    current=emit(app,cap,clock,current,str(Decimal(current.data['intake']['target'])+1))
    assert _lifecycle_values(app.store.restore(),app.store)['Target Met']=='YES'
    original_exit=current.data['exit']['identity']
    # Retained later ambiguity through the governed lifecycle transition/store
    # seam. This is not a new market-price interpretation or callback simulation.
    tick=ProviderMarketTick(instrument_record(current.data['intake']['future']),Decimal(current.data['intake']['stop'])-1,
        clock[0],clock[0],'KITE_CONNECT_WEBSOCKET','session-test',None,True,True,True)
    observed=websocket_observation(tick,authorization_identity=current.data['track_identity'],
        instrument=tick.instrument,session_identity=current.data['intake']['session_identity'],
        expected_session_identity=current.data['intake']['session_identity'],causal_at=current.data['armed_at'],decision_at=clock[0])
    transition=observe(current,observed)
    assert transition.current.data['state']=='OUTCOME_AMBIGUOUS'
    with app.store.transaction():
        app._commit(current,transition,emit_notifications=False)
    values=_lifecycle_values(app.store.restore(),app.store)
    assert values['Target Met']==values['Stop Met']==values['First Terminal Event']=='NOT_EVALUABLE'
    assert values['Chronology Coverage']=='WO11_OUTCOME_AMBIGUOUS'
    assert app.store.load(original_exit).data['reason']=='TARGET'


def test_legacy_export_matches_frozen_baseline_golden(tmp_path):
    # Verified against both unmodified exporter/application modules at 1d5eca.
    # The fixed publication path is metadata only; this test writes no workbook.
    app,_=_application(tmp_path)
    app.publication_root=Path('/private/tmp/KRONOS-WO12-LEGACY-GOLDEN')
    payload=export_research_workbook(app.project(ensure_origins=True,workbook_version='2.2.0'))
    assert len(payload)==20072
    assert sha256(payload).hexdigest()=='8d05dec758a9a5c50605f21ad37b80f96a024a94edaffe6fbe58c802cf8c3b35'


def assert_journey_readback(payload,expected_rows):
    """Compare every generated cell against the projected source value."""
    from xml.etree import ElementTree as ET
    ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with ZipFile(BytesIO(payload)) as archive:
        root=ET.fromstring(archive.read('xl/worksheets/sheet7.xml'))
    actual=[]
    for row in root.findall('s:sheetData/s:row',ns):
        cells=[]
        for cell in row.findall('s:c',ns):
            element=cell.find('s:is/s:t',ns) if cell.get('t')=='inlineStr' else cell.find('s:v',ns)
            cells.append(None if element is None else element.text)
        actual.append(tuple(cells))
    assert actual[0]==JOURNEY_COLUMNS
    assert actual[1:]==[tuple(None if value is None else str(value) for value in row) for row in expected_rows]


def test_exact_mcx_contract_roll_is_not_original_contract_progression(tmp_path,monkeypatch):
    """Real typed contract sources through a retained-store reporting seam."""
    import tests.unit.intraday.test_wo09_experimental as source_test
    from kronos.intraday.probables_v2_persistence import ProbablesV2Store
    from kronos.intraday.wo09_persistence import Wo09Store
    from kronos.intraday.wo12_research_store import ResearchStore
    from kronos.application.intraday_research import IntradayResearchApplication
    from kronos.application.intraday_wo08_research import associate_assessments
    from kronos.intraday.wo12_eod_validation import consideration
    from types import SimpleNamespace
    from datetime import datetime
    from tests.unit.application.test_intraday_research import _EmptyStore,_Lifecycle
    original=source_test.experimental_fixture;sources=[]
    def capture(*args,**kwargs):
        value=original(*args,**kwargs);sources.append(value);return value
    monkeypatch.setattr(source_test,'experimental_fixture',capture)
    source_test.test_mcx_same_contract_new_acquisition_binding_keeps_first_five(tmp_path/'source-proof')
    assert len(sources)==3
    probables=ProbablesV2Store(tmp_path/'probables');wo09=Wo09Store(tmp_path/'wo09')
    origin=source_test.origin_for(sources[0][-1]);store=ResearchStore(tmp_path/'research');store.retain(origin)
    records=[]
    for offset,(_,_,mapping,run,_,assessment) in enumerate(sources):
        probables.retain_complete(run=run,mappings=(mapping,))
        r,_=source_test.publish(wo09,assessment,origin,datetime.fromisoformat(assessment.data['created_at'])+timedelta(seconds=offset))
        records.append(r)
    app=IntradayResearchApplication(probables=probables,wo09=wo09,futures=_EmptyStore(),lifecycle=_Lifecycle(),store=store,
        publication_root=tmp_path/'Statistics',clock=lambda:records[-1].created_at,
        wo08=SimpleNamespace(records=lambda:tuple(s[-1] for s in sources)))
    associations=associate_assessments(assessments=app.wo08,shadow=None,probables=probables,origins=(origin,),
        readiness=app._readiness_history_by_result(),futures=app.futures,lifecycle=app.lifecycle,watch_store=wo09)
    store.retain(consideration(associations[0],probables,None))
    row=dict(zip(JOURNEY_COLUMNS,app.project().journey[0]))
    assert row['Exact MCX Contract']==records[0].exact_mcx_contract_identity
    assert row['Initial WO09 Contract']==records[0].exact_mcx_contract_identity
    assert row['Final WO09 Contract']==records[-1].exact_mcx_contract_identity
    assert row['Exact MCX Contract']!=row['Final WO09 Contract']
    assert row['Other Scope Readiness References']==records[-1].readiness_identity
    assert set(row['Readiness References'].split('; '))=={r.readiness_identity for r in records[:2]}
    assert row['First Five Fact']==records[0].first_five_document['fact_identity']
    assert row['First Five Fact']!=records[-1].first_five_document['fact_identity']
