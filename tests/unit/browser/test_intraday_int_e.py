"""Read-only real HTTP reporting rehearsal in the kernel-denied test estate."""
from pathlib import Path
from hashlib import sha256
from tests.unit.browser.test_intraday_portfolio_reports import server, get
from tests.unit.application.test_intraday_research import _application
import pytest


@pytest.mark.parametrize('section',['OPPORTUNITY_HISTORY','PREDICTION_PERFORMANCE','FALSE_ADVANCES','LIFECYCLE_HISTORY'])
@pytest.mark.parametrize('suffix',['','/export.csv','/export.json','/export.xlsx'])
def test_reporting_http_population_inert_and_exports(server,tmp_path,section,suffix):
    srv,books,lifecycle=server
    root=tmp_path/'research-fixture';root.mkdir()
    owner,_=_application(root)
    owner.update(operation_identity="DISPOSABLE-RESEARCH-PUBLICATION")
    srv.intraday_research_application=owner
    before={str(p):sha256(p.read_bytes()).hexdigest() for p in tmp_path.rglob('*') if p.is_file()}
    owner.update=lambda **k:(_ for _ in ()).throw(AssertionError('GET_UPDATE'))
    status,body=get(srv,'/reports'+suffix+'?product=INTRADAY&section='+section+'&month=2026_08')
    assert status==200 and body
    assert before=={str(p):sha256(p.read_bytes()).hexdigest() for p in tmp_path.rglob('*') if p.is_file()}
    assert srv.swing_monitoring_hub.active_session_count==0


def test_missing_composition_is_unavailable_not_empty(server):
    srv,*_=server
    del srv.intraday_books
    for route in ('/portfolio?product=INTRADAY','/reports?product=INTRADAY'):
        status,body=get(srv,route)
        assert status==503 and b'unavailable' in body
    status,body=get(srv,'/reports?product=INTRADAY&section=PREDICTION_PERFORMANCE')
    assert status==503


@pytest.mark.parametrize('extra',['section=OTHER','section=PREDICTION_PERFORMANCE&section=FALSE_ADVANCES','section=PREDICTION_PERFORMANCE&quantity=7'])
def test_new_filter_boundary(server,extra):
    assert get(server[0],'/reports?product=INTRADAY&'+extra)[0]==400


def test_normal_statistics_action_opens_publication_hub_without_get_write(tmp_path):
    from kronos.browser.intraday_routes import IntradayBrowserRoutes
    from kronos.browser.intraday_research import IntradayResearchControl
    from kronos.application.intraday_runtime import create_intraday_workstation
    from kronos.browser.product_routes import BrowserGetRequest
    from tests.unit.application.test_swing_opportunities import _ready
    owner,_=_application(tmp_path)
    routes=IntradayBrowserRoutes(create_intraday_workstation(),research_control=IntradayResearchControl(owner))
    before=tuple(tmp_path.rglob('*'))
    response=routes.handle_get(BrowserGetRequest('/intraday/statistics',{}),_ready)
    assert response.status==200 and 'MONTHLY STATISTICS / EXCEL' in response.body
    assert 'UPDATE RESEARCH' in response.body and 'RAW TECHNICAL SNAPSHOT' in response.body
    assert 'Not yet published' in response.body
    assert before==tuple(tmp_path.rglob('*'))
    opportunity=routes.handle_get(BrowserGetRequest('/intraday',{}),_ready)
    assert 'href="/intraday/statistics"' in opportunity.body


@pytest.mark.parametrize('section',['OPPORTUNITY_HISTORY','PREDICTION_PERFORMANCE','FALSE_ADVANCES','LIFECYCLE_HISTORY'])
def test_rendered_report_form_and_exports_accept_all_controls(server,tmp_path,section):
    from html.parser import HTMLParser
    from urllib.parse import urlencode
    class Inputs(HTMLParser):
        def __init__(self):super().__init__();self.values={}
        def handle_starttag(self,tag,attrs):
            d=dict(attrs)
            if tag=='input' and 'name' in d:self.values[d['name']]=d.get('value','')
    srv,*_=server;root=tmp_path/'publication';root.mkdir();owner,_=_application(root)
    owner.update(operation_identity='FORM-PUBLICATION');srv.intraday_research_application=owner
    status,body=get(srv,'/reports?'+urlencode(dict(product='INTRADAY',section=section,month='2026_08')))
    assert status==200
    parser=Inputs();parser.feed(body.decode())
    assert {'truth','completion'}<=parser.values.keys()
    for values in (parser.values,parser.values|dict(truth='PAPER_OBSERVATION',completion='INCOMPLETE',direction='LONG',search='RELIANCE',status='CLOSED',**{'from':'2026-08-01','to':'2026-08-31'})):
        for suffix in ('','/export.csv','/export.json','/export.xlsx'):
            assert get(srv,'/reports'+suffix+'?'+urlencode(values))[0]==200


@pytest.mark.parametrize('extra',['direction=SIDEWAYS','truth=LIVE','completion=CLOSED','month=2026_13','from=bad','from=2026-08-31&to=2026-08-01'])
def test_invalid_input_is_400_before_publication_read(server,extra):
    srv,*_=server
    class Unreadable:
        def clock(self):raise AssertionError('FILTER_READS_OWNER')
        def open_current(self,*a):raise AssertionError('FILTER_READS_PUBLICATION')
    srv.intraday_research_application=Unreadable()
    for suffix in ('','/export.csv'):
        status,body=get(srv,'/reports'+suffix+'?product=INTRADAY&section=OPPORTUNITY_HISTORY&'+extra)
        assert status==400 and b'filter is invalid' in body


@pytest.mark.parametrize('route',['/notifications','/notifications/swing','/notifications/intraday'])
def test_notifications_reject_report_parameters_without_reading_research(server,route):
    srv,*_=server
    class Unreadable:
        def open_current(self,*a):raise AssertionError('NOTIFICATION_READS_RESEARCH')
    srv.intraday_research_application=Unreadable()
    status,body=get(srv,route+'?product=INTRADAY&section=PREDICTION_PERFORMANCE')
    assert status==400 and b'Notification filter is invalid' in body
