"""INT-E additive publication, exact research denominators and truthful views."""
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from io import BytesIO
from zipfile import ZipFile
import json
import pytest
from kronos.application.intraday_sponsor_reporting import sponsor_sheets, monthly_path, summary_document
from kronos.application.intraday_opportunity_journey import JOURNEY_COLUMNS
from kronos.browser.intraday_research import export_research_workbook, validate_research_workbook
from kronos.browser.intraday_sponsor_reports import export_sheet, render_portfolio_context, report_sheet
from tests.unit.application.test_intraday_research import _application
from tests.unit.browser.test_browser_reports import _ready
from kronos.browser.dashboard import IntradayDashboardSummary


def mixed_projection(tmp_path):
    app, run = _application(tmp_path)
    p = app.project(ensure_origins=True, workbook_version='2.4.0')
    rows = []
    for score, match in [(3,'MATCHED'), (4,'NOT_MATCHED'), (5,'NOT_EVALUABLE')]:
        data = dict.fromkeys(JOURNEY_COLUMNS, 'NOT_ESTABLISHED')
        data.update({'Opportunity ID':f'RELIANCE-{score}', 'Security':'RELIANCE', 'Trading Date':'2026-08-28',
            'Direction':'LONG','Initial Count':score,'Assessment Price':100,'EOD Match':match,
            'Entry Met':'NOT_EVALUABLE','Target Met':'NOT_EVALUABLE','Stop Met':'NOT_EVALUABLE',
            'False Advance 3':'YES' if match=='NOT_MATCHED' else 'NO',
            'False Advance 4':'YES' if score==4 else 'NOT_ADVANCED', 'False Advance 5':'NOT_EVALUABLE',
            'WO09 Currentness':'HISTORICAL_ONLY'})
        rows.append(tuple(data[c] for c in JOURNEY_COLUMNS))
    return app, replace(p, journey=tuple(rows))


def test_additive_workbook_primary_order_and_seven_legacy_sheets(tmp_path):
    app, p = mixed_projection(tmp_path)
    data = export_research_workbook(p); validate_research_workbook(data,p)
    with ZipFile(BytesIO(data)) as z:
        assert z.testzip() is None
        xml = z.read('xl/workbook.xml').decode()
        assert xml.index('name="Monthly Summary"') < xml.index('name="Opportunities"')
        assert len([n for n in z.namelist() if n.startswith('xl/tables/table')]) == 18
        assert all('name="'+n+'"' in xml for n in ('Opportunities','Tracks','Events','Analysis','Data_Quality','Metadata','Opportunity_Journey'))
        assert '<f>' not in z.read('xl/worksheets/sheet8.xml').decode()
    assert data == export_research_workbook(p)


def test_summary_denominator_and_missing_not_zero(tmp_path):
    app,p = mixed_projection(tmp_path)
    d = summary_document(p)
    assert d['metrics']['Considered opportunity / methodology cohorts']==3
    assert d['metrics']['Evaluated']==2 and d['metrics']['Not evaluable']==1
    assert d['false_advance_rows']==1
    sheets=dict((n,(cols,rows)) for n,cols,rows in sponsor_sheets(p))
    assert len(sheets['Near Ready'][1])==len(sheets['Ready'][1])==len(sheets['Now'][1])==1
    assert 'NOT_EVALUABLE' in sheets['Opportunity Journey'][1][0]
    assert d['metrics']['Net profitability'].startswith('NOT_EVALUABLE')


@pytest.mark.parametrize('month,expected',[('2026_12','2026/2026-12 — December.xlsx'),('2027_01','2027/2027-01 — January.xlsx')])
def test_year_month_layout(month,expected):
    assert monthly_path(Path('/statistics'),month)==Path('/statistics')/expected


def test_new_monthly_publication_idempotency_recovery_and_old_bytes(tmp_path):
    app,_ = _application(tmp_path)
    old_projection=app.project(ensure_origins=True,workbook_version='2.3.0')
    old=export_research_workbook(old_projection)
    result=app.update(operation_identity='INT-E-001')
    assert result.workbook_path.name=='2026-08 — August.xlsx'
    assert result.workbook_path.parent==app.publication_root/'2026'
    again=app.update(operation_identity='INT-E-002')
    assert again.idempotent and again.workbook_sha256==result.workbook_sha256
    assert export_research_workbook(old_projection)==old
    assert len(app.store.records('WO12_OPPORTUNITY_ORIGIN_V1'))==1
    result.workbook_path.write_bytes(b'INTERRUPTED')
    recovered=app.update(operation_identity='INT-E-003')
    assert recovered.outcome=='RECOVERED_CANONICAL_WORKBOOK'
    assert app.open_current('2026_08')[1]==result.workbook_path.read_bytes()


def test_receipt_failure_rolls_back_and_never_serves_partial(tmp_path,monkeypatch):
    app,_=_application(tmp_path)
    monkeypatch.setattr(app.store,'publish_receipt',lambda *a: (_ for _ in ()).throw(OSError('FAULT')))
    with pytest.raises(OSError):app.update(operation_identity='INT-E-FAIL')
    assert app.store.current_receipt('2026_08') is None
    with pytest.raises(ValueError,match='UNAVAILABLE'):app.open_current('2026_08')
    assert not monthly_path(app.publication_root,'2026_08').exists()


def test_all_exports_same_selected_population_and_no_active_content(tmp_path):
    app,p=mixed_projection(tmp_path)
    from kronos.application.intraday_sponsor_reporting import filtered_sheet
    sheet=filtered_sheet(p,'Prediction Performance',status='NOT_MATCHED',direction='LONG')
    assert len(sheet[2])==1
    assert len(json.loads(export_sheet(sheet,'json'))['rows'])==1
    assert len(export_sheet(sheet,'csv').decode().splitlines())==2
    with ZipFile(BytesIO(export_sheet(sheet,'xlsx'))) as z:
        assert z.testzip() is None and '<f>' not in z.read('xl/worksheets/sheet1.xml').decode()
        assert not any('externalLink' in n or 'vba' in n for n in z.namelist())


def test_portfolio_ready_only_and_observation_zero_exposure():
    attention=IntradayDashboardSummary(1,1,'CURRENT_SESSION_VERIFIED',opportunities=(
        dict(status='Ready',security='SAIL',direction='SHORT',waiting='Follow-through',monitoring=dict(state='INACTIVE',reason='EXPIRED')),
        dict(status='Now',security='OTHER',direction='LONG',waiting='NONE',monitoring=None)))
    html=render_portfolio_context(attention,())
    assert 'SAIL' in html and 'OTHER' not in html and '4/5' in html and 'EXPIRED' in html
    assert 'zero exposure' in html and 'No matching active Paper Observations' in html
    assert 'Current attention source unavailable' in render_portfolio_context(None,())


def test_report_get_has_no_retained_effect(tmp_path):
    app,run=_application(tmp_path);app.update(operation_identity='DISPOSABLE-PUBLISHED')
    before={str(p):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    p,sheet=report_sheet(app,'OPPORTUNITY_HISTORY',{'month':['2026_08']})
    assert before=={str(p):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    assert app.publication_root.exists()  # Prepared publication remains unchanged by GET.


def test_wo09_projection_reads_requirements_once_and_does_not_cache_pointers(tmp_path,monkeypatch):
    from kronos.intraday.wo09_persistence import Wo09Store
    from kronos.browser.intraday_wo09_control import IntradayWo09Projection
    from tests.unit.intraday.test_wo09_experimental import experimental_fixture, origin_for, publish
    from datetime import timedelta
    *_,assessment=experimental_fixture('LONG')
    store=Wo09Store(tmp_path/'wo09')
    at=datetime.fromisoformat(assessment.data['created_at'])+timedelta(seconds=1)
    record,requirements=publish(store,assessment,origin_for(assessment),at)
    assert store.load_requirement_population()[record.readiness_identity]==store.load_requirements(record.readiness_identity)
    count=[0]; original=store.load_requirement_population
    def counted():count[0]+=1;return original()
    monkeypatch.setattr(store,'load_requirement_population',counted)
    view=IntradayWo09Projection(store,machine_successor=True)
    first=view.status_document()
    assert count[0]==1
    pointer=store.current/next(store.current.glob('*.json')).name
    pointer.unlink()
    assert view.status_document()['cards']==()
    assert count[0]==1


def test_wo09_reuse_never_serves_removed_or_changed_requirement(tmp_path):
    from kronos.intraday.wo09_persistence import Wo09Store
    from tests.unit.intraday.test_wo09_experimental import experimental_fixture, origin_for, publish
    from datetime import timedelta
    *_,a=experimental_fixture('LONG');s=Wo09Store(tmp_path/'wo09')
    r,rs=publish(s,a,origin_for(a),datetime.fromisoformat(a.data['created_at'])+timedelta(seconds=1))
    assert len(s.load_requirements(r.readiness_identity))==len(rs)
    p=next(s.requirements.glob('*.json'));saved=p.read_bytes();p.write_bytes(b'{}')
    with pytest.raises((ValueError,KeyError,TypeError)):s.load_requirement_population()
    p.write_bytes(saved);assert len(s.load_requirements(r.readiness_identity))==len(rs)
    p.unlink();assert len(s.load_requirements(r.readiness_identity))==len(rs)-1


def test_published_read_never_composes_and_detects_pointer_change(tmp_path,monkeypatch):
    from kronos.browser.intraday_research import read_published_projection,IntradayResearchControl
    app,_=_application(tmp_path);result=app.update(operation_identity='PUBLISHED-GET')
    monkeypatch.setattr(app,'project',lambda **k:(_ for _ in ()).throw(AssertionError('GET_COMPOSITION')))
    before={str(p):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    status=IntradayResearchControl(app).status_document()
    assert status['last_update'] and status['workbook_verified']
    assert read_published_projection(app,'2026_08').projection_identity==result.projection_identity
    assert before=={str(p):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    saved=app.store.current_receipt;count=[0]
    def changing(month):
        count[0]+=1
        return None if count[0]>2 else saved(month)
    monkeypatch.setattr(app.store,'current_receipt',changing)
    with pytest.raises(ValueError,match='CHANGED'):read_published_projection(app,'2026_08')


def test_historical_six_sheet_results_unavailable_not_zero(tmp_path):
    from kronos.browser.intraday_research import read_published_projection
    app,_=_application(tmp_path)
    p=app.project(ensure_origins=True,workbook_version='2.2.0')
    with app.store.transaction():app._update_month_locked(operation_identity='OLD',_projection=p)
    restored=read_published_projection(app,'2026_08')
    assert restored.workbook_version=='2.2.0'
    d=summary_document(restored)
    assert d['false_advance_rows'] is None and 'NOT_EVALUABLE' in d['metrics']['Prediction results']


def test_workbook_qa_package(tmp_path,request):
    app,p=mixed_projection(tmp_path)
    payload=export_research_workbook(p);validate_research_workbook(payload,p)
    if request.config.option.xmlpath:
        (Path(request.config.option.xmlpath).parent/'INT_E_Sponsor_QA.xlsx').write_bytes(payload)


def test_truth_and_completion_filters_never_combine_exposure_with_observation(tmp_path):
    from kronos.application.intraday_sponsor_reporting import filtered_sheet
    app,p=mixed_projection(tmp_path)
    rows=[]
    for i,row in enumerate(p.journey):
        d=dict(zip(JOURNEY_COLUMNS,row,strict=True))
        d['Paper Class']='PAPER_POSITION' if i==0 else 'PAPER_OBSERVATION' if i==1 else 'NOT_ESTABLISHED'
        d['Paper State']='CLOSED' if i<2 else 'NOT_ESTABLISHED'
        d['Lifecycle References']=f'CURRENT-{i}'
        rows.append(tuple(d[c] for c in JOURNEY_COLUMNS))
    from kronos.application.intraday_research import TRACK_COLUMNS
    tracks=[]
    for i in range(2):
        d=dict.fromkeys(TRACK_COLUMNS,None)
        d.update(source_current_identity=f'CURRENT-{i}',truth_class='PAPER_POSITION' if i==0 else 'PAPER_OBSERVATION',monitoring_complete=True)
        tracks.append(tuple(d[c] for c in TRACK_COLUMNS))
    p=replace(p,journey=tuple(rows),tracks=tuple(tracks))
    assert len(filtered_sheet(p,'Prediction Performance',truth='PAPER_POSITION',completion='COMPLETE')[2])==1
    assert len(filtered_sheet(p,'Opportunity Journey',truth='PAPER_OBSERVATION',completion='COMPLETE')[2])==1
    assert len(filtered_sheet(p,'Opportunity Journey',completion='UNAVAILABLE')[2])==1


def test_historical_generator_bytes_match_baseline(tmp_path):
    import importlib.util
    import subprocess
    baseline=subprocess.run(['git','show','d7d60b7a1aa9eb3ff65d74025e6a2faf58667392:src/kronos/browser/intraday_research.py'],
        cwd=Path(__file__).resolve().parents[3],check=True,capture_output=True).stdout
    path=tmp_path/'baseline_export.py';path.write_bytes(baseline)
    spec=importlib.util.spec_from_file_location('int_e_baseline_export',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    app,_=_application(tmp_path)
    for version in ('2.2.0','2.3.0'):
        p=app.project(ensure_origins=True,workbook_version=version)
        assert export_research_workbook(p)==module.export_research_workbook(p)


@pytest.mark.parametrize('state,complete,expected',[('CLOSED',False,'INCOMPLETE'),('OUTCOME_AMBIGUOUS',None,'UNAVAILABLE'),('CANCELLED',None,'UNAVAILABLE'),('ENTERED',True,'COMPLETE')])
def test_metric_coverage_is_retained_fact_not_terminal_state(tmp_path,state,complete,expected):
    from kronos.application.intraday_research import TRACK_COLUMNS,EVENT_COLUMNS
    from kronos.application.intraday_sponsor_reporting import filtered_sheet
    app,p=mixed_projection(tmp_path)
    d=dict(zip(JOURNEY_COLUMNS,p.journey[0],strict=True))
    d.update({'Paper State':state,'Paper Class':'PAPER_POSITION','Lifecycle References':'CURRENT-EXACT'})
    t=dict.fromkeys(TRACK_COLUMNS,None);t.update(source_current_identity='CURRENT-EXACT',truth_class='PAPER_POSITION',monitoring_complete=complete,terminal=state!='ENTERED',opportunity_identity='ORIGIN')
    e=dict.fromkeys(EVENT_COLUMNS,None);e.update(source_schema='WO11_EVENT_V1',truth_class='PAPER_POSITION',opportunity_identity='ORIGIN',event_at='2026-08-28T10:00:00+05:30',state=state)
    p=replace(p,journey=(tuple(d[c] for c in JOURNEY_COLUMNS),),tracks=(tuple(t[c] for c in TRACK_COLUMNS),),events=(tuple(e[c] for c in EVENT_COLUMNS),))
    assert len(filtered_sheet(p,'Opportunity Journey',completion=expected)[2])==1
    assert len(filtered_sheet(p,'Opportunity Journey',completion='COMPLETE' if expected!='COMPLETE' else 'INCOMPLETE')[2])==0
    from unittest.mock import patch
    with patch('kronos.browser.intraday_research.read_published_projection',return_value=p):
        assert len(report_sheet(app,'LIFECYCLE_HISTORY',{'completion':[expected]})[1][2])==1
    # Missing or ambiguous exact references cannot confer coverage.
    p=replace(p,tracks=p.tracks*2)
    assert len(filtered_sheet(p,'Opportunity Journey',completion='UNAVAILABLE')[2])==1


def test_negative_decimal_exports_remain_numeric_and_formula_text_is_fenced():
    from decimal import Decimal
    import csv
    import xml.etree.ElementTree as E
    sheet=('Numeric',('Value','Text'),((Decimal('-1.25'),'=danger'),))
    rows=list(csv.reader(export_sheet(sheet,'csv').decode().splitlines()))
    assert rows[1]==['-1.25',"'=danger"]
    assert json.loads(export_sheet(sheet,'json'))['rows'][0][0]=='-1.25'
    with ZipFile(BytesIO(export_sheet(sheet,'xlsx'))) as z:
        xml=E.fromstring(z.read('xl/worksheets/sheet1.xml'))
        cell=xml.find('.//{*}c[@r="A2"]')
        assert cell.get('t') in (None,'n') and cell.find('{*}v').text=='-1.25'
        assert xml.find('.//{*}f') is None
