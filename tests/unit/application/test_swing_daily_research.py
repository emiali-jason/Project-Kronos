"""LOCAL-03 isolated retained-only publication and lifecycle acceptance."""
from datetime import timedelta,datetime,timezone,time
from pathlib import Path
from threading import Event,Thread,Lock
from types import SimpleNamespace
from dataclasses import replace
from hashlib import sha256
from io import BytesIO
from zipfile import ZipFile
import json
import pytest
from kronos.application.swing_daily_research import daily_chain, local_observations
from kronos.application.swing_prospective_research import SwingProspectiveResearchApplication
from kronos.application.swing_research_control import SwingResearchControl
from kronos.application.swing_research_integration import SwingResearchEventCapture
from kronos.swing.v1.prospective_research import record,IST,ProspectiveResearchStore
from kronos.common.maintenance_admission import MaintenanceAdmissionCoordinator
from tests.unit.application.test_nse_local_analysis_workflow import _rig,_refresh
from tests.unit.swing.v1.test_nse_local_analysis import _case
from kronos.swing.v1.models import V1Direction

@pytest.fixture
def rig(tmp_path):
 r=_rig(tmp_path);_refresh(r);r.research.local_history_reader=r.owner.retained_research
 return r

def snap(root):return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
def day(r):return r.research.clock().astimezone(IST).date()
def publish(r,trigger='MANUAL',**kw):
 return r.research.record_daily(reporting_date=day(r),trigger=trigger,attempt_identity='a'*32,**kw)
def controller(r):
 r.application.retained_daily_research_sources=lambda day:()
 c=SwingResearchControl(application=r.application,intake=None,research=r.research,
  capture=SwingResearchEventCapture(r.research,require_commissioning=True),calendar=None,clock=r.research.clock)
 a=MaintenanceAdmissionCoordinator();state={'shutdown':False,'ready':True}
 c.configure_daily(admission=a,shutdown_lock=Lock(),shutdown_started=lambda:state['shutdown'],ready=lambda:state['ready'])
 return c,a,state

@pytest.mark.parametrize('order',[('MANUAL','SCHEDULE'),('SCHEDULE','MANUAL')])
def test_exactly_one_base_manual_schedule_race_order_and_export_replay(rig,order):
 before=snap(rig.research.store.root/'records'/'SWING_WO12_LOCAL_ANALYSIS_ORIGINAL_V1')
 first=publish(rig,order[0]);second=publish(rig,order[1]);assert first['state']=='PUBLISHED' and second['state']=='ALREADY_COVERED'
 chain=daily_chain(rig.research.store,day(rig).isoformat());assert len(chain)==1 and chain[0].data['publication_kind']=='BASE'
 path=Path(chain[0].data['workbook_path']);payload=path.read_bytes();assert sha256(payload).hexdigest()==chain[0].data['workbook_sha256']
 assert snap(rig.research.store.root/'records'/'SWING_WO12_LOCAL_ANALYSIS_ORIGINAL_V1')==before
 with ZipFile(BytesIO(payload)) as f:
  names=f.read('xl/workbook.xml').decode();assert all(x in names for x in ('Opportunities','Tracks','Events','Analysis','Data_Quality','Metadata','Local_Research'))
  sheet=f.read('xl/worksheets/sheet7.xml').decode();assert rig.requirement.canonical_instrument in sheet and 'LOCAL_ASSESSMENT_MISSING' not in sheet
  assert '<f>' not in sheet and 'KRONOS-NSE-LOCAL-RESEARCH-1.0' in sheet
  assert 'RESEARCH_ONLY_NO_ADMISSION_OR_EXECUTION' in sheet
 assert path.read_bytes()==payload

def test_later_same_day_evidence_is_append_only_supplement(rig):
 publish(rig);old=daily_chain(rig.research.store,day(rig).isoformat())[0];old_bytes=Path(old.data['workbook_path']).read_bytes()
 value=record('DECISION',origin_identity='unresolved-retained-origin',decided_at=rig.research.clock().isoformat(),source_identity='OWNER-SOURCE',choice='IGNORE')
 with rig.research.store.transaction():rig.research.store.retain(value)
 result=publish(rig,'SCHEDULE');assert result['kind']=='SUPPLEMENT'
 chain=daily_chain(rig.research.store,day(rig).isoformat());assert len(chain)==2 and chain[1].data['prior_publication']==old.identity
 assert Path(old.data['workbook_path']).read_bytes()==old_bytes
 assert any(r['identity']==value.identity for r in chain[1].data['source_records'])
 assert publish(rig)['state']=='ALREADY_COVERED'

@pytest.mark.parametrize('fault',['daily_after_prepare','daily_after_artifact','daily_after_receipt'])
def test_restart_resumes_frozen_intent_without_second_base(rig,fault):
 rig.research.fault_hook=lambda phase: (_ for _ in ()).throw(RuntimeError('isolated crash')) if phase==fault else None
 with pytest.raises(RuntimeError):publish(rig)
 old_originals=snap(rig.research.store.root/'records'/'SWING_WO12_LOCAL_ANALYSIS_ORIGINAL_V1')
 restarted=SwingProspectiveResearchApplication(store=rig.research.store,publication_root=rig.research.publication_root,clock=rig.research.clock)
 restarted.local_history_reader=rig.owner.retained_research
 restarted.record_daily(reporting_date=day(rig),trigger='CATCHUP',attempt_identity='b'*32)
 assert len(daily_chain(rig.research.store,day(rig).isoformat()))==1
 assert snap(rig.research.store.root/'records'/'SWING_WO12_LOCAL_ANALYSIS_ORIGINAL_V1')==old_originals

def test_manual_early_then_late_evidence_and_next_epoch_supplement(rig):
 publish(rig)
 value=record('CHECKPOINT',observed_at=rig.research.clock().isoformat(),opportunity_identity='retained',reason='UNAVAILABLE')
 with rig.research.store.transaction():rig.research.store.retain(value)
 result=publish(rig,'CATCHUP');assert result['kind']=='SUPPLEMENT'

def test_busy_cross_process_lock_cannot_create_duplicate_base(rig):
 ready,release=Event(),Event()
 def held():
  with rig.research.store.transaction():ready.set();assert release.wait(3)
 t=Thread(target=held);t.start();assert ready.wait(3)
 try:
  with pytest.raises(ValueError,match='BUSY'):publish(rig)
 finally:release.set();t.join(3)
 assert publish(rig)['kind']=='BASE'
 assert len(daily_chain(rig.research.store,day(rig).isoformat()))==1

def test_current_publication_match_is_not_live_recommendation_and_old_original_remains(rig):
 current=rig.application.publication_status();row=local_observations(rig.research,current)[0]
 assert row['currentness']=='MATCHES_RETAINED_PUBLICATION_NOT_CURRENTNESS_CERTIFICATION'
 original=row['original_identity'];before=snap(rig.research.store.root)
 rig.state['manifest']='b'*64
 assert local_observations(rig.research,rig.application.publication_status())[0]['currentness']=='HISTORICAL'
 assert snap(rig.research.store.root)==before and local_observations(rig.research)[0]['original_identity']==original

def test_multiple_independent_originals_preserved_without_rewriting(rig,tmp_path):
 other=_rig(tmp_path/'other',arguments=_case(native_direction=V1Direction.SHORT));_refresh(other)
 # Real owner-generated input/result, not modified or self-rehashed findings.
 for kind in ('LOCAL_ANALYSIS_ORIGINAL','LOCAL_ANALYSIS_DISPOSITION'):
  for r in other.research.store.records(kind):rig.research.store.retain(r)
 rig.owner.restore();assert len(local_observations(rig.research))==2
 publish(rig);assert len(rig.research.store.records('LOCAL_ANALYSIS_ORIGINAL'))==2

def test_no_acquiring_update_provider_model_or_native_calls(rig,monkeypatch):
 def forbidden(*a,**k):raise AssertionError('FORBIDDEN_ACQUISITION_OR_ANALYSIS')
 monkeypatch.setattr(rig.research,'update',forbidden)
 monkeypatch.setattr(rig.application,'authenticated_read_only_capability',forbidden)
 monkeypatch.setattr('kronos.swing.v1.nse_local_analysis.analyze_local',forbidden)
 monkeypatch.setenv('OPENAI_API_KEY','')
 assert publish(rig)['state']=='PUBLISHED'

def test_missing_local_is_not_fabricated_from_native(rig):
 from types import SimpleNamespace
 r=_rig(rig.root/'missing');r.research.local_history_reader=r.owner.retained_research
 b=dict(run_identity=r.state['native'].run_identity,publication={'sha256':'a'*64},
  completed_at=r.research.clock().isoformat(),evidence_cutoff=r.state['facts'].observed_at.isoformat(),artifacts={},
  assessments=[dict(instrument=a.canonical_instrument,direction=a.direction.value,assessment_sha256=a.result_sha256,
   status=a.status.value,product_path=a.product_path.value,weekly_state=a.weekly_state.value) for a in r.state['native'].assessments])
 publish(r,history=(b,));receipt=daily_chain(r.research.store,day(r).isoformat())[0]
 with ZipFile(receipt.data['workbook_path']) as f:
  sheet=f.read('xl/worksheets/sheet7.xml').decode();assert 'LOCAL_ASSESSMENT_MISSING' in sheet
 assert not r.research.store.records('LOCAL_ANALYSIS_ORIGINAL')

def test_corrupt_immutable_workbook_blocks_without_repair(rig):
 publish(rig);r=daily_chain(rig.research.store,day(rig).isoformat())[0];p=Path(r.data['workbook_path']);p.write_bytes(b'CORRUPTED')
 with pytest.raises(ValueError,match='ARTIFACT_UNAVAILABLE'):publish(rig)
 assert p.read_bytes()==b'CORRUPTED'

@pytest.mark.parametrize('mode',['shutdown','not_ready','fenced','stopping'])
def test_unadmitted_work_has_no_durable_write_or_leaked_ticket(rig,mode):
 c,a,s=controller(rig);before=snap(rig.research.store.root)
 if mode=='shutdown':s['shutdown']=True
 if mode=='not_ready':s['ready']=False
 if mode=='fenced':a.claim('f'*64)
 if mode=='stopping':c.quiesce_daily()
 try:
  if mode=='not_ready':
   with pytest.raises(ValueError,match='NOT_READY'):c.submit_daily('c'*32)
  else:assert c.submit_daily('c'*32)['state'] in {'FENCED','STOPPED'}
  assert snap(rig.research.store.root)==before and not a.snapshot()['owners']
 finally:c.close()

def test_worker_registration_counted_through_final_writes_and_exit_handshake(rig):
 c,a,s=controller(rig);started,release=Event(),Event();original=rig.research.record_daily
 def held(**kwargs):started.set();assert release.wait(3);return original(**kwargs)
 rig.research.record_daily=held
 parent=a.admit('BROWSER_POST');c.submit_daily('d'*32,parent);parent.release();assert started.wait(3)
 assert c.work_status()['owned_workers']==1 and a.snapshot()['owners']=={'SWING_RESEARCH':1}
 assert c.submit_daily('e'*32)['state']=='BUSY'
 generation='9'*64;assert a.claim(generation);a.draining(generation)
 assert not a.wait_for_zero(generation,0)
 release.set();c.close();assert not a.snapshot()['owners']
 assert c.daily_status()['last_attempt']['state']=='PUBLISHED'
 assert rig.research.store.records('DAILY_ATTEMPT')

@pytest.mark.parametrize('hour,expected',[(22,False),(23,True),(0,False)])
def test_2300_IST_schedule_not_host_timezone(rig,hour,expected):
 c,a,s=controller(rig);now=rig.research.clock().astimezone(IST).replace(hour=hour,minute=0,second=0,microsecond=0)
 c.clock=lambda:now;calls=[]
 # Real scheduler due decision; synthetic dispatch sink avoids background work.
 c.submit_daily=lambda identity,**kw:calls.append(kw) or {'state':'QUEUED'}
 c.poll_daily()
 assert bool(calls)==True  # Earlier hours catch up yesterday, never publish today early.
 assert (calls[0]['reporting_date']==now.date())==expected
 assert calls[0]['trigger']==('SCHEDULE' if expected else 'CATCHUP')
 c.close()

def test_restart_catchup_and_no_repeated_failed_date_in_epoch(rig):
 c,a,s=controller(rig);now=rig.research.clock().astimezone(IST).replace(hour=23,minute=1)
 c.clock=lambda:now;calls=[]
 c.submit_daily=lambda identity,**kw:calls.append(kw['reporting_date']) or {'state':'QUEUED'}
 for _ in range(4):c._daily_next_check=0;c.poll_daily()
 assert calls.count(now.date())==1 and len(calls)==len(set(calls))
 c.close()
 restarted,a,s=controller(rig);restarted.clock=lambda:now;again=[]
 restarted.submit_daily=lambda identity,**kw:again.append(kw['reporting_date']) or {'state':'QUEUED'}
 restarted.poll_daily();assert again==[now.date()];restarted.close()

def test_no_history_write_from_journey_and_replay(rig,monkeypatch):
 before=snap(rig.research.store.root)
 monkeypatch.setattr('kronos.swing.v1.nse_local_analysis.analyze_local',lambda *a,**k: (_ for _ in ()).throw(AssertionError('GET_RECALCULATED')))
 for _ in range(3):assert local_observations(rig.research)
 assert snap(rig.research.store.root)==before

def test_existing_six_sheet_workbook_receipt_is_not_overwritten_by_daily(rig):
 from kronos.browser.swing_research_workbook import export_swing_research_workbook
 # Existing receipted monthly path may be six-sheet historical bytes.
 p=rig.research.publication_root/'KRONOS_Swing_Research_2026_10.xlsx';p.parent.mkdir(parents=True,exist_ok=True)
 payload=b'UNCHANGED-RECEIPTED-HISTORICAL-WORKBOOK';p.write_bytes(payload)
 value=record('RECEIPT',year_month='2026_10',workbook_path=str(p),workbook_sha256=sha256(payload).hexdigest(),workbook_bytes=len(payload),published_at=rig.research.clock().isoformat())
 with rig.research.store.transaction():rig.research.store.retain(value)
 publish(rig);assert p.read_bytes()==payload and rig.research._receipt_verified(value)

def test_empty_retained_day_records_gaps_not_successful_market_outcomes(tmp_path):
 from tests.unit.application.test_nse_local_analysis_workflow import _commission
 app=SwingProspectiveResearchApplication(store=ProspectiveResearchStore((tmp_path/'store').resolve()),publication_root=(tmp_path/'published').resolve(),clock=lambda:datetime(2026,10,19,12,tzinfo=timezone.utc))
 _commission(app,app.clock());r=app.record_daily(reporting_date=app.clock().astimezone(IST).date(),trigger='MANUAL',attempt_identity='1'*32)
 assert r['coverage']=='RECORDED_WITH_GAPS'
 assert not app.store.records('LOCAL_ANALYSIS_ORIGINAL') and not app.store.records('CHECKPOINT')

def test_clock_and_commissioning_boundaries_fail_closed(rig):
 with pytest.raises(ValueError,match='FUTURE_DATE'):
  rig.research.record_daily(reporting_date=day(rig)+timedelta(days=1),trigger='MANUAL',attempt_identity='a'*32)
 with pytest.raises(ValueError,match='BEFORE_COMMISSIONING'):
  rig.research.record_daily(reporting_date=day(rig)-timedelta(days=4),trigger='CATCHUP',attempt_identity='a'*32)

def test_genuine_retained_originals_export_in_isolation_without_rewriting(tmp_path):
 # The fixture copy was made explicitly before the kernel test boundary. The
 # real production Statistics tree remains denied throughout this test.
 fixture=Path(__file__).resolve().parents[4]/'genuine-retained-fixtures'
 assert fixture.is_dir()
 store=ProspectiveResearchStore((tmp_path/'evidence').resolve())
 for p in fixture.rglob('*.json'):
  from kronos.swing.v1.prospective_research import Record
  value=Record(**json.loads(p.read_bytes()));store.retain(value)
  if value.schema=='SWING_WO12_COMMISSIONING_V1':store.publish_pointer('COMMISSIONING','active',value)
 now=datetime(2026,10,19,17,45,tzinfo=timezone.utc)
 app=SwingProspectiveResearchApplication(store=store,publication_root=(tmp_path/'published').resolve(),clock=lambda:now)
 before=snap(store.root/'records'/'SWING_WO12_LOCAL_ANALYSIS_ORIGINAL_V1')
 rows=app.local_journey();assert {r['instrument'] for r in rows}=={'BHEL','BDL','ALKEM','RVNL'}
 r=app.record_daily(reporting_date=now.astimezone(IST).date(),trigger='MANUAL',attempt_identity='c'*32)
 assert r['state']=='PUBLISHED' and snap(store.root/'records'/'SWING_WO12_LOCAL_ANALYSIS_ORIGINAL_V1')==before
 assert len(store.records('LOCAL_ANALYSIS_ORIGINAL'))==4


def test_operation_uuid_replay_never_adds_attempt_or_late_supplement(rig):
 from time import monotonic,sleep
 c,a,s=controller(rig)
 try:
  c.submit_daily('d'*32)
  deadline=monotonic()+3
  while c.work_status()['owned_workers'] and monotonic()<deadline:sleep(.01)
  before=snap(rig.research.store.root)
  c.submit_daily('d'*32)
  while c.work_status()['owned_workers'] and monotonic()<deadline:sleep(.01)
  assert snap(rig.research.store.root)==before
  assert len(rig.research.store.records('DAILY_ATTEMPT'))==1
  assert a.snapshot()['owners'].get('SWING_RESEARCH',0)==0
 finally:c.close()


def test_ist_midnight_day_partition_and_late_capture_is_supplement(rig):
 original=rig.research.clock();publish(rig)
 next_day=original.astimezone(IST).date()+timedelta(days=1)
 now=datetime.combine(next_day,time(0,1),tzinfo=IST)
 rig.research.clock=lambda:now
 value=record('DECISION',origin_identity='retained-source',decided_at=original.isoformat(),choice='IGNORE')
 rig.research.store.retain(value)
 result=rig.research.record_daily(reporting_date=original.astimezone(IST).date(),trigger='CATCHUP',attempt_identity='e'*32)
 assert result['kind']=='SUPPLEMENT'
 old=daily_chain(rig.research.store,original.astimezone(IST).date().isoformat())
 assert any(v['identity']==value.identity for v in old[-1].data['source_records'])
 newer=rig.research.record_daily(reporting_date=next_day,trigger='MANUAL',attempt_identity='f'*32)
 assert newer['kind']=='BASE'
 assert not any(v['identity']==value.identity for v in daily_chain(rig.research.store,next_day.isoformat())[0].data['source_records'])

@pytest.mark.parametrize('change',['date','sequence','digest','outside','symlink'])
def test_untrusted_publication_path_rejected_without_touching_original(rig,tmp_path,change):
 from kronos.application.swing_daily_research import publication_path
 publish(rig);r=daily_chain(rig.research.store,day(rig).isoformat())[0];d=dict(r.data)
 original=Path(d['workbook_path']).read_bytes()
 if change=='date':d['reporting_date']='../outside'
 if change=='sequence':d['sequence']=True
 if change=='digest':d['source_digest']='not-a-digest'
 if change=='outside':d['workbook_path']='/outside/'+str(Path(d['workbook_path']).relative_to(rig.research.publication_root))
 if change=='symlink':
  link=tmp_path/'link';link.symlink_to(rig.research.publication_root,target_is_directory=True)
  d['workbook_path']=str(link/Path(d['workbook_path']).relative_to(rig.research.publication_root))
 with pytest.raises((ValueError,KeyError)):publication_path(rig.research.publication_root,d)
 assert Path(r.data['workbook_path']).read_bytes()==original


def test_dispatch_failure_does_not_escape_shared_service_pulse(rig):
 c,a,s=controller(rig)
 c.submit_daily=lambda *a,**k:(_ for _ in ()).throw(ValueError('CORRUPT_SOURCE'))
 c.poll_daily()
 assert c.daily_status()['state']=='BLOCKED'
 assert c.daily_status()['failure']=='DAILY_DISPATCH_UNAVAILABLE'
 assert not a.snapshot()['owners']
 c.close()


def test_explicit_synthetic_and_genuine_demo_artifacts(rig,request,tmp_path):
 """Artifacts exported outside candidate; not production/currentness claims."""
 import shutil
 from kronos.browser.swing_daily_research import render_daily_research
 from kronos.application.swing_local_analysis import _original
 destination=Path(request.config.option.xmlpath).parent.parent/'sponsor-preview'
 destination.mkdir(exist_ok=True)
 publish(rig)
 synthetic=render_daily_research({'state':'READY','publications':[dict(identity=r.identity,**r.data) for r in rig.research.store.records('DAILY_PUBLICATION')]},rig.research.local_journey())
 heading='<h1>LOCAL-03 — SYNTHETIC TEST FIXTURE</h1><p>Isolated demonstration only. No production schedule or market acceptance.</p>'
 shell=lambda body:'<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{font:16px system-ui;background:#f7f8fa;color:#18202b;margin:16px;--line:#c9d0db}.panel{padding:14px;background:white;border:1px solid #ccd1d9;border-radius:10px}p{line-height:1.45}button{padding:12px}details{margin:12px 0}</style></head><body>'+body+'</body></html>'
 actions='<p><button>Record Today’s Research</button> <button>Historical Research Update</button></p><p>Preview buttons inactive. Actual application uses existing governed POST controls.</p>'
 (destination/'synthetic-journey.html').write_text(shell(heading+actions+synthetic))
 receipt=rig.research.store.records('DAILY_PUBLICATION')[0]
 shutil.copyfile(receipt.data['workbook_path'],destination/'SYNTHETIC-LOCAL03-RESEARCH.xlsx')
 fixture=Path(__file__).resolve().parents[4]/'genuine-retained-fixtures'
 store=ProspectiveResearchStore(tmp_path/'genuine-store')
 originals=[]
 for path in sorted(fixture.glob('SWING_WO12_LOCAL_ANALYSIS_ORIGINAL_V1/*.json')):
  # Existing decoder validates unmodified originals; copied fixture has provenance.
  raw=json.loads(path.read_bytes())
  value=__import__('kronos.swing.v1.prospective_research',fromlist=['Record']).Record(**raw)
  _original(value);store.retain(value);originals.append(value)
 app=SwingProspectiveResearchApplication(store=store,publication_root=tmp_path/'genuine-publications',clock=rig.research.clock)
 app.local_history_reader=lambda:tuple(originals)
 genuine=render_daily_research({'state':'NOT_DEPLOYED','publications':[]},app.local_journey())
 (destination/'genuine-retained-journey.html').write_text(shell('<h1>LOCAL-03 — COPIED GENUINE RETAINED ORIGINALS</h1><p>Historical evidence rendered in isolation. No fresh market or deployed acceptance.</p>'+genuine))
 assert len(originals)==4
 (destination/'provenance.json').write_text(json.dumps({'synthetic':'Owner-generated fixture data, not market evidence','genuine':'Four byte-identical copied production Local originals; historical, no currentness certification','originals':[r.identity for r in originals]},indent=2)+'\n')


def test_changed_publication_during_capture_retains_failure_not_success(rig):
 from time import monotonic,sleep
 c,a,s=controller(rig);read=rig.application.publication_status;calls=[]
 def changing():
  result=read();calls.append(None)
  if len(calls)>1:result={**result,'control':{'current_manifest':{'sha256':'f'*64}}}
  return result
 rig.application.publication_status=changing
 try:
  c.submit_daily('5'*32);end=monotonic()+3
  while c.work_status()['owned_workers'] and monotonic()<end:sleep(.01)
  assert c.daily_status()['last_attempt']['state']=='FAILED'
  assert c.daily_status()['last_attempt']['reason']=='SWING_DAILY_SOURCE_CHANGED'
  assert not rig.research.store.records('DAILY_PUBLICATION')
  assert len(rig.research.store.records('DAILY_ATTEMPT'))==1
  assert not a.snapshot()['owners']
 finally:c.close()
