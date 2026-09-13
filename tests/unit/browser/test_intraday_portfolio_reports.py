"""Real shared HTTP routes with isolated source stores and no runtime control."""
import json
import os
from pathlib import Path
from http.client import HTTPConnection
from threading import Thread
from time import perf_counter
import pytest
from kronos.browser.server import create_browser_server
from kronos.browser.reports import export_reports_xlsx, export_reports_csv, export_reports_json
from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.application.swing_native_review import NativeReviewWorkflow
from kronos.application.swing_v1_review import SwingV1ReviewWorkflow
from kronos.swing.v1.native_review import NativeReviewEvidenceStore
from kronos.swing.v1.evidence_store import LocalTradingViewEvidenceStore
from kronos.market.calendar import MarketCalendarPublisher
from tests.unit.intraday.test_wo1516_books import fixture, projection
from tests.unit.browser.test_browser_reports import _Provider, _ready, NOW, _xlsx_rows


@pytest.fixture
def server(tmp_path):
    books,journal,futures,lifecycle,current=fixture(tmp_path)
    app=SwingOpportunitiesApplication(_Provider,initial_snapshot=_ready(),clock=lambda:NOW,market_calendar_publisher=MarketCalendarPublisher())
    srv=create_browser_server(app,port=0,native_review=NativeReviewWorkflow(NativeReviewEvidenceStore((tmp_path/'native').resolve())),
        v1_review=SwingV1ReviewWorkflow(LocalTradingViewEvidenceStore((tmp_path/'legacy').resolve())))
    srv.intraday_books=books
    thread=Thread(target=srv.serve_forever,daemon=True);thread.start()
    yield srv,books,lifecycle
    srv.shutdown();thread.join(timeout=2);srv.server_close()


def get(server,path):
    conn=HTTPConnection('127.0.0.1',server.server_port,timeout=5)
    conn.request('GET',path);response=conn.getresponse();data=response.read();status=response.status
    conn.close();return status,data


@pytest.mark.parametrize('path,marker',[
    ('/portfolio?product=INTRADAY','LUPIN-20260913-100000'),
    ('/portfolio?product=SWING','SWING PORTFOLIO'),
    ('/portfolio?product=INTRADAY&search=OTHER','NO ACTIVE INTRADAY PAPER POSITIONS'),
    ('/portfolio?product=INTRADAY&direction=SHORT','NO ACTIVE INTRADAY PAPER POSITIONS'),
    ('/portfolio?product=INTRADAY&monitoring=INTERRUPTED','NO ACTIVE INTRADAY PAPER POSITIONS'),
    ('/reports?product=INTRADAY','LUPIN-20260913-100000'),
    ('/reports?product=INTRADAY&view=LIVE','LIVE_POSITION_NOT_COMMISSIONED_V1'),
    ('/reports?product=INTRADAY&view=PAPER_OBSERVATIONS','NO HISTORICAL RECORDS'),
    ('/reports?product=INTRADAY&exit_reason=TARGET','NO HISTORICAL RECORDS'),
    ('/reports/export.csv?product=INTRADAY','opportunity_id'),
    ('/reports/export.json?product=INTRADAY','OPP-IDENTITY'),
    ('/reports?product=SWING','NO HISTORICAL RECORDS'),
])
def test_shared_routes_are_inert(server,path,marker):
    srv,books,lifecycle=server
    before=(dict(lifecycle.store.values),lifecycle.owner_count,lifecycle.subscription_count)
    status,data=get(srv,path)
    assert status==200 and marker in data.decode()
    assert before==(dict(lifecycle.store.values),lifecycle.owner_count,lifecycle.subscription_count)
    assert srv.swing_monitoring_hub.active_session_count==0
    assert srv.swing_monitoring_hub.subscription_count==0


@pytest.mark.parametrize('path',[
    '/portfolio?product=OTHER','/portfolio?product=INTRADAY&quantity=7',
    '/portfolio?product=INTRADAY&monitoring=CONNECTED','/portfolio?product=INTRADAY&product=SWING',
    '/reports?product=INTRADAY&exit_reason=OTHER','/reports?product=INTRADAY&completeness=MAYBE',
    '/reports?product=INTRADAY&quick=TODAY','/reports?product=INTRADAY&raw=true'])
def test_shared_routes_reject_unauthorized_filters(server,path):
    assert get(server[0],path)[0]==400


def test_wo16_xlsx_route_and_filters(server):
    status,body=get(server[0],'/reports/export.xlsx?product=INTRADAY&view=ALL_RECORDS')
    assert status==200 and len(_xlsx_rows(body))==2
    status,body=get(server[0],'/reports/export.xlsx?product=INTRADAY&view=ALL_RECORDS&search=OTHER')
    assert status==200 and len(_xlsx_rows(body))==1


def test_wo15_wo16_unavailable_source_returns_bounded_error(server):
    srv,books,_=server
    books._failure='INTRADAY_BOOK_SOURCE_UNAVAILABLE';books._hydrated=True
    for route in ('/portfolio?product=INTRADAY','/reports?product=INTRADAY','/reports/export.json?product=INTRADAY'):
        status,body=get(srv,route)
        assert status==503 and b'unavailable' in body and b'/Users/' not in body


def test_wo15_wo16_small_latency_and_export_qa(server):
    srv,books,_=server
    values={}
    for name,path in [('portfolio','/portfolio?product=INTRADAY'),('reports','/reports?product=INTRADAY'),
                      ('filter','/reports?product=INTRADAY&search=LUPIN'),('xlsx','/reports/export.xlsx?product=INTRADAY&view=ALL_RECORDS')]:
        samples=[]
        for _ in range(3):
            start=perf_counter();status,body=get(srv,path);samples.append((perf_counter()-start)*1000)
            assert status==200
        values[name+'_milliseconds']=samples
    output=os.environ.get('WO1516_QA_OUTPUT')
    if output:
        target=Path(output);target.mkdir(parents=True,exist_ok=True)
        (target/'latency.json').write_text(json.dumps(values,indent=2))
        for name,path in [('portfolio','/portfolio?product=INTRADAY'),('reports','/reports?product=INTRADAY')]:
            (target/(name+'.html')).write_bytes(get(srv,path)[1])
        p=projection(books)
        for suffix,writer in [('xlsx',lambda p:export_reports_xlsx(p,generated_at=NOW)),('csv',export_reports_csv),('json',export_reports_json)]:
            (target/('ISOLATED_REPORT.'+suffix)).write_bytes(writer(p))
