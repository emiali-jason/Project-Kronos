"""Real Browser handlers, fixture stores/ports only; no production navigation."""
from datetime import timedelta
from pathlib import Path
from threading import Event
from time import monotonic,sleep
from types import SimpleNamespace
import html,json
import pytest
from tests.unit.browser.test_browser_server import _running_server,_request,_request_bytes
from tests.unit.application.test_nse_local_analysis_workflow import _rig,_refresh
from tests.unit.application.test_swing_daily_research import controller,snap,day
from kronos.browser.swing_daily_research import render_daily_research


def test_retained_only_button_is_separate_and_get_is_write_free(tmp_path,monkeypatch):
 r=_rig(tmp_path/'rig');_refresh(r);r.research.local_history_reader=r.owner.retained_research
 c,a,state=controller(r);server,thread=_running_server();old=server.swing_research_control;server.swing_research_control=c;old.close()
 c.configure_daily(admission=server.maintenance_admission,shutdown_lock=server._shutdown_lock,
  shutdown_started=lambda:server._shutdown_started,ready=lambda:True)
 # No timed test activation; manual route tested at an arbitrary retained date.
 c.poll_daily=lambda:None
 def forbidden(*a,**k):raise AssertionError('ACQUISITION_OR_RECONCILIATION')
 monkeypatch.setattr(c,'submit_update',forbidden)
 monkeypatch.setattr(server.application,'reconcile_committed_analysis',forbidden)
 monkeypatch.setattr('kronos.swing.v1.nse_local_analysis.analyze_local',forbidden)
 before=snap(r.research.store.root)
 try:
  status,headers,body=_request(server,'GET','/swing/research');assert status==200
  assert 'Record Today' in body and 'Historical Research Update' in body and '/swing/research/record' in body
  assert 'Opportunity Journey' in body and r.requirement.canonical_instrument in body and 'KRONOS-NSE-LOCAL-RESEARCH-1.0' in body
  assert snap(r.research.store.root)==before
  identity='b'*32;status,headers,body=_request(server,'POST','/swing/research/record',headers={'Content-Type':'application/x-www-form-urlencoded','Host':f'127.0.0.1:{server.server_port}','Origin':f'http://127.0.0.1:{server.server_port}'},body=('operation_identity='+identity).encode())
  assert status==303
  end=monotonic()+5
  while c.work_status()['owned_workers'] and monotonic()<end:sleep(.01)
  assert c.daily_status()['last_attempt']['state']=='PUBLISHED'
  publication=c.daily_status()['publications'][0]
  before_read=snap(r.research.store.root)
  status,headers,payload=_request_bytes(server,'GET','/swing/research?download='+publication['identity'])
  assert status==200 and 'spreadsheetml' in headers['Content-Type']
  assert snap(r.research.store.root)==before_read
  assert server.maintenance_admission.snapshot()['owners'].get('SWING_RESEARCH',0)==0
  assert _request(server,'GET','/swing/research?download=unretained')[0]==404
 finally:server.shutdown();server.server_close();thread.join(5)

@pytest.mark.parametrize('bad',[b'',b'operation_identity=no',b'operation_identity='+b'a'*32+b'&unexpected=x',b'operation_identity='+b'a'*32+b'&operation_identity='+b'a'*32])
def test_recording_rejects_bad_requests_and_foreign_origin_before_owner(bad):
 server,thread=_running_server();calls=[];server.swing_research_control.submit_daily=lambda *a:calls.append(a)
 h={'Host':f'127.0.0.1:{server.server_port}','Origin':f'http://127.0.0.1:{server.server_port}','Content-Type':'application/x-www-form-urlencoded'}
 try:
  assert _request(server,'POST','/swing/research/record',headers=h,body=bad)[0]==503
  assert calls==[]
  h['Origin']='https://foreign.invalid';assert _request(server,'POST','/swing/research/record',headers=h,body=b'operation_identity='+b'a'*32)[0]==403
 finally:server.shutdown();server.server_close();thread.join(5)

@pytest.mark.parametrize('width',[1440,390])
def test_journey_presentation_explicit_historical_missingness_and_safe_markup(tmp_path,width):
 r=_rig(tmp_path);_refresh(r);r.research.local_history_reader=r.owner.retained_research
 rows=r.research.local_journey();body=render_daily_research({'state':'READY','publications':[]},rows)
 assert 'HISTORICAL' in body and 'Original conviction' in body and 'UNKNOWN' in body
 assert 'UNRESOLVED' in body and 'Unavailable' in body
 assert 'grid-template-columns:1fr' in body and 'overflow-wrap:anywhere' in body
 assert len(rows[0]['thesis']['horizons'])==3
 # Exact real renderer artifact for offline Chromium, no production data.
 Path(tmp_path/'journey.html').write_text('<!doctype html><html><meta name="viewport" content="width=device-width,initial-scale=1"><body>'+body+'</body></html>')


def test_incomplete_governance_is_not_ready_and_does_not_break_pulse():
 server,thread=_running_server()
 try:
  server.connection_governance=SimpleNamespace(maintenance_active=False)
  assert server.swing_research_control._daily_ready() is False
  server.swing_research_control.poll_daily()
 finally:server.connection_governance=None;server.shutdown();server.server_close();thread.join(5)


def test_real_research_owner_must_be_closed_before_maintenance_proof(tmp_path):
 from tests.unit.browser.test_browser_server import _mcx_drain_server
 r=_rig(tmp_path/'rig');_refresh(r);r.research.local_history_reader=r.owner.retained_research
 c,a,s=controller(r);server=_mcx_drain_server(tmp_path/'domains')
 server.swing_research_control=c
 try:
  assert not server._maintenance_final_owner_proof()
  c.close()
  assert server._maintenance_final_owner_proof()
 finally:c.close()
