from http.client import HTTPConnection
from threading import Thread
from pathlib import Path
import json
import os
import re
from urllib.parse import urlencode

import pytest

from kronos.application.swing_native_review import NativeReviewWorkflow
from kronos.application.swing_v1_review import SwingV1ReviewWorkflow
from kronos.browser.server import create_browser_server
from kronos.browser.restart_control import BrowserBackendRestartControl
from kronos.swing.v1 import LocalTradingViewEvidenceStore
from kronos.swing.v1.native_review import NativeReviewEvidenceStore
from tests.unit.application.test_sph_maintenance import composed
from tests.unit.provider.test_connection_governance import GENERATION


@pytest.fixture
def running(tmp_path):
    g,shared,app,provider,calls=composed(tmp_path,maintenance=GENERATION)
    control=BrowserBackendRestartControl.create(tmp_path/'runtime'/'control')
    server=create_browser_server(app,port=0,restart_control=control,
        v1_review=SwingV1ReviewWorkflow(LocalTradingViewEvidenceStore(tmp_path/'charts')),
        native_review=NativeReviewWorkflow(NativeReviewEvidenceStore(tmp_path/'native')))
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    yield server,g,provider,calls,tmp_path
    server.shutdown();server.server_close();thread.join(5)


def request(server,path,*,method='GET',fields=None,headers=None):
    host=f'127.0.0.1:{server.server_port}'
    headers=headers or {'Host':host,'Origin':f'http://{host}'}
    body=urlencode(fields) if fields else None
    conn=HTTPConnection('127.0.0.1',server.server_port,timeout=5)
    conn.request(method,path,body=body,headers=headers)
    result=conn.getresponse();data=result.read().decode();status=result.status
    conn.close();return status,data


def test_get_polling_status_and_controls_remain_provider_inert(running):
    server,g,p,calls,tmp=running
    for route in ('/status','/swing/opportunities','/settings'):
        status,body=request(server,route)
        assert status==200
        if route=='/status':assert json.loads(body)['maintenance']['active'] is True
        else:
            assert 'END MAINTENANCE' in body
            assert g.action_reference('MAINTENANCE_EXIT') in body
    assert calls==[] and p.begin_count==0
    assert not (g.store.root).exists()
    assert not list((tmp/'native').rglob('facts/*.json'))


@pytest.mark.parametrize('route',['/swing/analysis','/control/intraday-discovery','/intraday/live-shadow/accept-runtime','/provider/disconnect'])
def test_maintenance_rejects_operational_posts_before_dispatch(running,route):
    server,g,p,calls,tmp=running
    assert request(server,route,method='POST')[0]==503
    assert calls==[] and p.begin_count==0


def test_provider_connect_during_maintenance_is_durably_rejected(running):
    server,g,p,calls,tmp=running
    assert request(server,'/provider/connect',method='POST')[0]==303
    identity=next(g.store.root.iterdir()).name
    rows=g.store.read(identity)
    assert rows['admission']['state']=='REJECTED'
    assert rows['request']['trigger']=='LOCAL_HTTP_UNATTRIBUTED'
    assert calls==[] and p.begin_count==0


def test_explicit_exit_is_inert_then_connect_records_valid_header_context(running):
    server,g,p,calls,tmp=running
    assert request(server,'/control/maintenance/exit',method='POST',fields={'action_reference':'bad'})[0]==409
    assert request(server,'/control/maintenance/exit',method='POST',fields={'action_reference':g.action_reference('MAINTENANCE_EXIT')})[0]==303
    assert calls==[] and p.begin_count==0
    code,body=request(server,'/swing/opportunities')
    assert 'END MAINTENANCE' not in body
    assert 'data-provider-control="HEADER"><input type="hidden" name="action_reference"' in body
    assert request(server,'/provider/connect',method='POST',fields={'action_reference':g.action_reference('HEADER')})[0]==303
    assert p.begin_count==1
    records=[g.store.read(d.name) for d in g.store.root.iterdir() if d.name!='maintenance']
    assert records[0]['request']['surface']=='HEADER'
    assert records[0]['request']['trigger']=='LOCAL_HTTP_UNATTRIBUTED'
    assert records[0]['completion']['state']=='SUCCESS'


def test_settings_reference_is_distinct_and_no_header_origin_spoofing(running):
    server,g,p,calls,tmp=running
    status,body=request(server,'/settings')
    assert status==200
    assert 'data-provider-control="SETTINGS"><input type="hidden" name="action_reference"' in body
    assert g.action_reference('SETTINGS') in body
    assert request(server,'/provider/connect',method='POST',headers={'Origin':'http://evil.invalid'})[0]==403
    assert p.begin_count==0


def test_validated_shutdown_creates_handoff_before_stopping(running):
    server,g,p,calls,tmp=running
    control=server.restart_control
    host=f'127.0.0.1:{server.server_port}'
    headers={'Host':host,'X-Kronos-Backend-Pid':str(os.getpid()),
        'X-Kronos-Restart-Token':control._token,'X-Kronos-Maintenance-Generation':'f'*64}
    assert request(server,'/control/shutdown',method='POST',headers=headers)[0]==202
    assert g.shutting_down and g.maintenance_identity=='f'*64
    handoff=tmp/'runtime'/'maintenance'/f'{"f"*64}.json'
    assert handoff.exists() and json.loads(handoff.read_bytes())['record']['parent_pid']==os.getpid()
    assert p.begin_count==0 and calls==[]


def test_restart_rejects_an_inflight_authentication_without_handoff(running):
    from dataclasses import replace
    from kronos.application.swing_opportunities import ProviderConnectionState
    server,g,p,calls,tmp=running
    original=server.application.snapshot
    server.application.snapshot=lambda:replace(original(),provider_state=ProviderConnectionState.CONNECTING)
    control=server.restart_control;host=f'127.0.0.1:{server.server_port}'
    headers={'Host':host,'X-Kronos-Backend-Pid':str(os.getpid()),
        'X-Kronos-Restart-Token':control._token,'X-Kronos-Maintenance-Generation':'f'*64}
    assert request(server,'/control/shutdown',method='POST',headers=headers)[0]==409
    assert not g.shutting_down
    assert not (tmp/'runtime'/'maintenance').exists()


def test_explicit_sponsor_exit_establishes_local_maintenance_cause(running):
    server,g,p,calls,tmp=running
    assert request(server,'/control/exit',method='POST')[0]==202
    assert g.shutting_down and g.maintenance_active
    assert g.maintenance_identity != GENERATION
    assert calls==[] and p.begin_count==0
