"""Actual LOCAL owner → WO-12 immutable projection/export, synthetic candles."""
from datetime import timedelta, datetime
from pathlib import Path
from io import BytesIO
from zipfile import ZipFile
import json
import pytest
from tests.unit.application.test_swing_daily_research import rig, publish, day, snap, controller
from tests.unit.swing.v1.test_local_research_outcomes import case
from kronos.swing.v1.prospective_research import record, origin, GovernedCalendar, GovernedSession, calendar_record, FollowupCandle, candle_record, IST
from kronos.application.swing_prospective_research import SwingProspectiveResearchApplication
from kronos.browser.swing_daily_research import render_daily_research
from kronos.browser.swing_research_workbook import SwingResearchProjection, export_swing_research_workbook


def retain_measurement(rig):
    original=rig.research.store.records('LOCAL_ANALYSIS_ORIGINAL')[0]
    b=json.loads(original.data['result_json'])['result']['binding']
    signal=datetime.fromisoformat(original.data['completed_at'])
    price=json.loads(original.data['input_json'])['evidence']['summary']['frames'][1]['values']['close']
    o=origin(continuity_identity='SYNTHETIC-CONTINUITY',market='NSE',instrument=b['instrument'],contract_identity='SYNTHETIC-EXACT-EQ',expiry=None,
      direction=b['direction'],admitted_at=signal,source_identity='SYNTHETIC-NATIVE',source_version='1',source_sha256='b'*64,
      origin_run_identity=b['run_identity'],origin_assessment_sha256=b['assessment_sha256'],native_setup_identity='SYNTHETIC-SETUP',
      contract_binding=dict(canonical_instrument=b['instrument'],exchange='NSE',provider='KITE',segment='NSE',trading_symbol=b['instrument'],instrument_type='EQ',expiry=None))
    sessions=tuple(GovernedSession('LOCAL04-S'+str(i),'NSE',(signal+timedelta(days=i)).date(),(signal+timedelta(days=i)).replace(hour=9,minute=15),(signal+timedelta(days=i)).replace(hour=15,minute=30)) for i in range(1,21))
    cal=calendar_record(GovernedCalendar('NSE','SYNTHETIC-CALENDAR','1',signal,signal.date(),sessions[-1].trading_date,sessions))
    candles=tuple(candle_record(FollowupCandle(o.data['exact_contract_identity'],s.identity,'SYNTHETIC-C'+str(i),'1',s.closes_at+timedelta(minutes=1),str(float(price)+i),str(float(price)+i+2),str(float(price)+i-2),True)) for i,s in enumerate(sessions,1))
    with rig.research.store.transaction():
      for item in (o,cal,*candles):rig.research.store.retain(item)
    rig.research.clock=lambda:sessions[-1].closes_at+timedelta(minutes=2)
    return original,o,cal,candles,signal


def test_actual_original_outcomes_workbook_and_restart_immutable(rig):
    original,o,cal,candles,signal=retain_measurement(rig)
    before=snap(rig.research.store.root)
    rows=rig.research.local_journey();outcome=rows[0]['outcomes']
    assert outcome['original_identity']==original.identity and outcome['exact_contract_identity']==o.data['exact_contract_identity']
    assert outcome['direction'][0]['status']=='OBSERVED' and len(outcome['direction'])==10
    assert snap(rig.research.store.root)==before
    # Reporting the original month retains later captured outcomes explicitly;
    # this is a current research snapshot, not a backdated original opinion.
    reporting_day=signal.astimezone(IST).date()
    result=rig.research.record_daily(reporting_date=reporting_day,trigger='MANUAL',attempt_identity='e'*32)
    receipt=rig.research.store.records('DAILY_PUBLICATION')[0];payload=Path(receipt.data['workbook_path']).read_bytes()
    assert cal.identity in {r['identity'] for r in receipt.data['source_records']}
    assert all(c.identity in {r['identity'] for r in receipt.data['source_records']} for c in candles)
    with ZipFile(BytesIO(payload)) as z:
      assert 'Local_Outcomes' in z.read('xl/workbook.xml').decode() and 'Local_Performance' in z.read('xl/workbook.xml').decode()
      assert 'DIRECTION' in z.read('xl/worksheets/sheet8.xml').decode()
      assert 'direction_adjusted_pct' in z.read('xl/worksheets/sheet8.xml').decode()
    restored=SwingProspectiveResearchApplication(store=rig.research.store,publication_root=rig.research.publication_root,clock=rig.research.clock)
    restored.local_history_reader=rig.owner.retained_research
    assert restored.local_journey()[0]['outcomes']==outcome
    again=restored.record_daily(reporting_date=reporting_day,trigger='CATCHUP',attempt_identity='f'*32)
    assert again['state']=='ALREADY_COVERED' and Path(receipt.data['workbook_path']).read_bytes()==payload
    assert rig.research.store.records('LOCAL_ANALYSIS_ORIGINAL')[0]==original


def test_changed_outcome_is_immutable_supplement_no_original_rewrite(rig):
    original,o,cal,candles,signal=retain_measurement(rig);late=rig.research.clock()
    rig.research.clock=lambda:signal
    # Early retained cut cannot see later captured candles; retain directly for
    # projection only. Daily publication rejects future-source records by contract.
    early=rig.research.local_journey()[0]['outcomes'];assert all(r['direction_adjusted_pct'] is None for r in early['direction'])
    rig.research.clock=lambda:late
    first=rig.research.record_daily(reporting_date=signal.date(),trigger='MANUAL',attempt_identity='1'*32)
    old=rig.research.store.records('DAILY_PUBLICATION')[0];old_bytes=Path(old.data['workbook_path']).read_bytes()
    raw=dict(candles[0].data);raw.update(source_identity='SYNTHETIC-REVISION',supersedes_source_identity=raw['source_identity'],revision_reason='governed correction',retrieved_at=late.isoformat(),close=raw['high'])
    with rig.research.store.transaction():rig.research.store.retain(record('CANDLE',**raw))
    second=rig.research.record_daily(reporting_date=signal.date(),trigger='CATCHUP',attempt_identity='2'*32)
    assert second['kind']=='SUPPLEMENT' and Path(old.data['workbook_path']).read_bytes()==old_bytes
    assert rig.research.store.records('LOCAL_ANALYSIS_ORIGINAL')[0]==original


def test_legacy_six_and_seven_sheet_recovery_byte_identity(rig):
    p=rig.research._projection(day(rig).strftime('%Y_%m'),rig.research.clock())
    from dataclasses import replace,asdict
    legacy=replace(p,local_outcomes=(),local_performance=(),outcome_contract=None)
    old=asdict(legacy)
    for key in ('local_outcomes','local_performance','outcome_contract'):old.pop(key)
    assert export_swing_research_workbook(SwingResearchProjection(**old))==export_swing_research_workbook(legacy)
    six=replace(legacy,local_research=(),local_contract=None)
    assert len(six.sheets)==6 and len(legacy.sheets)==7


def test_original_without_exact_origin_is_not_invented_outcome(rig,monkeypatch):
    def forbidden(*a,**k):raise AssertionError('ACQUISITION_OR_MODEL')
    monkeypatch.setattr('kronos.swing.v1.nse_local_analysis.analyze_local',forbidden)
    before=snap(rig.research.store.root)
    rows=rig.research.local_journey();assert rows[0]['outcomes']['direction'][0]['reason']=='EXACT_RESEARCH_ORIGIN_UNAVAILABLE'
    body=render_daily_research(None,rows)
    assert 'Win probability unavailable' in body and 'No linked factual PAPER position' in body
    assert snap(rig.research.store.root)==before


def test_retained_basis_owner_is_wired_without_acquisition(rig):
    c,_,_=controller(rig)
    assert rig.research.local_outcome_basis.__self__ is c
    _,o,_,_,signal=retain_measurement(rig)
    calls=[]
    class Basis:
      def basis(self,*a,**k):calls.append((a,k));return 'VERIFIED_NO_ACTION','PROOF'
    c.equity_basis=Basis()
    assert rig.research.local_journey()[0]['outcomes']['direction'][0]['status']=='OBSERVED'
    assert len(calls)==5 and all(k['as_of']==rig.research.clock() for _,k in calls)
    c.close()


def test_rendered_measurement_demo(rig,request):
    retain_measurement(rig)
    rows=rig.research.local_journey();body=render_daily_research({'state':'SYNTHETIC_PREVIEW','publications':[]},rows)
    destination=Path(request.config.option.xmlpath).parent.parent/'sponsor-preview';destination.mkdir(exist_ok=True)
    (destination/'synthetic-outcomes.html').write_text('<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{font:16px system-ui;margin:16px;color:#18202b;background:#f7f8fa;--line:#c9d0db}p{line-height:1.4}details{margin:12px 0}</style></head><body><h1>LOCAL-04 — SYNTHETIC OUTCOME DEMONSTRATION</h1><p>No production observations or market results are claimed.</p>'+body+'</body></html>')
    assert '20 sessions' in body and 'SCENARIO' not in rows[0]['outcomes']['authority']


def test_busy_corporate_action_owner_is_unavailable_without_waiting(rig):
    from threading import Lock
    c,_,_=controller(rig);_,o,_,_,signal=retain_measurement(rig)
    c.equity_basis=object();c._authority_lock=Lock();c._authority_lock.acquire()
    try:
      assert c._local_outcome_basis(o,signal.date(),signal.date(),rig.research.clock())==('UNKNOWN',None)
    finally:c._authority_lock.release();c.close()


def test_factual_paper_owner_event_is_not_recomputed(rig):
    from kronos.swing.v1.prospective_research import lifecycle_track
    original,o,_,_,signal=retain_measurement(rig)
    event=lifecycle_track(o,truth_class='PAPER_POSITION',track_identity='SYNTHETIC-POSITION',state='CLOSED',source_event_identity='OWNER-CLOSURE',source_version='1',observed_at=signal+timedelta(days=1),entry_price='100',exit_price='105',gross_pnl='5')
    with rig.research.store.transaction():rig.research.store.retain(event)
    rows=rig.research.local_journey();body=render_daily_research(None,rows)
    assert rows[0]['factual_tracks'][0]['identity']==event.identity
    assert 'source gross P&amp;L 5' in body and 'OWNER-CLOSURE' in body
    assert all(s['realized_pnl'] is None for s in rows[0]['outcomes']['scenarios'])


def test_duplicate_origin_binding_is_unavailable_not_arbitrarily_selected(rig):
    _,o,_,_,_=retain_measurement(rig)
    with rig.research.store.transaction():rig.research.store.retain(record('ORIGIN',**{**o.data,'opportunity_identity':'SECOND-CONTINUITY'}))
    assert rig.research.local_journey()[0]['outcomes']['direction'][0]['reason']=='EXACT_RESEARCH_ORIGIN_UNAVAILABLE'
