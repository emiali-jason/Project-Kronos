"""Five real Sponsor destinations; historical GETs and Swing remain separate."""
from html.parser import HTMLParser
from pathlib import Path
import inspect

import pytest

from kronos.browser.intraday_views import _intraday_tabs, render_intraday_lifecycle_placeholder, render_intraday_wo09
from kronos.browser.intraday_futures_control import IntradayFuturesControl, render_futures
from kronos.browser.intraday_wo09_control import IntradayWo09Projection
from kronos.browser.product_routes import BrowserGetRequest, BrowserPostRequest
from tests.unit.browser.test_intraday_review_workflow import _routes, _fingerprints
from tests.unit.browser.test_product_route_isolation import _snapshot
from tests.unit.intraday.test_wo10_native_composition import native
from tests.unit.intraday.test_wo10_futures import session

EXPECTED = [("OPPORTUNITIES", "/intraday"), ("REVIEW", "/intraday/review"),
            ("TRADE CANDIDATES", "/intraday/trade-candidates"), ("ACTIVE", "/intraday/active"), ("CLOSED", "/intraday/closed")]


class Links(HTMLParser):
    def __init__(self, html):
        super().__init__(); self.inside=False;self.a=None;self.links=[];self.feed(html)
    def handle_starttag(self,tag,attrs):
        d=dict(attrs)
        if tag=="nav" and d.get("aria-label")=="Intraday workflow":self.inside=True
        if self.inside and tag=="a":self.a=["",d["href"],d.get("class","")]
    def handle_data(self,data):
        if self.a is not None:self.a[0]+=data
    def handle_endtag(self,tag):
        if tag=="a" and self.a is not None:self.links.append(self.a);self.a=None
        if tag=="nav":self.inside=False


@pytest.mark.parametrize("active",["opportunities","review","trade-candidates","active","closed"])
def test_exact_nav_order_and_active(active):
    links=Links(_intraday_tabs(False,active=active)).links
    assert [(label,path) for label,path,_ in links]==EXPECTED
    assert [path for _,path,cls in links if cls=="active"]==["/intraday" if active=="opportunities" else "/intraday/"+active]


@pytest.mark.parametrize("number",range(10,18))
def test_historical_renderers_use_consolidated_navigation(number):
    from kronos.browser import intraday_views
    assert "_intraday_tabs(" in inspect.getsource(getattr(intraday_views,"render_intraday_wo"+str(number)))
    assert [(l,p) for l,p,_ in Links(_intraday_tabs(False,active="wo"+str(number))).links]==EXPECTED
    from kronos.browser.intraday_routes import IntradayBrowserRoutes
    route=inspect.getsource(IntradayBrowserRoutes.handle_get)
    prefix="WO12_V2" if number==12 else "WO"+str(number)
    assert prefix+"_PRODUCT_ROUTE" in route
    assert prefix+"_STATUS_ROUTE" in route


@pytest.mark.parametrize("path",["/intraday/active","/intraday/closed"])
def test_lifecycle_routes_are_inert_and_real(tmp_path,path):
    *_,routes=_routes(tmp_path)
    before=_fingerprints(tmp_path)
    response=routes.handle_get(BrowserGetRequest(path,{}),_snapshot)
    assert response.status==200 and "Prospective lifecycle is not implemented" in response.body
    assert [(l,p) for l,p,_ in Links(response.body).links]==EXPECTED
    assert _fingerprints(tmp_path)==before


def test_trade_candidates_and_historical_futures_alias(tmp_path):
    app,kw,_,_=native(tmp_path/"future")
    *_,routes=_routes(tmp_path/"browser")
    routes._futures_control=IntradayFuturesControl(app,lambda *_:session())
    before=_fingerprints(tmp_path)
    for path in ("/intraday/trade-candidates","/intraday/futures"):
        response=routes.handle_get(BrowserGetRequest(path,{}),_snapshot)
        assert response.status==200 and "NSE-EQ-LUPIN" in response.body
        assert [(l,p) for l,p,_ in Links(response.body).links]==EXPECTED
    assert _fingerprints(tmp_path)==before


def test_opportunities_readiness_link_only_current_five(tmp_path):
    from kronos.intraday.wo09_readiness import CurrentnessState
    from tests.unit.intraday.test_wo10_futures import NOW
    from datetime import timedelta
    app,kw,_,_=native(tmp_path)
    projection=IntradayWo09Projection(app.wo09)
    html=render_intraday_wo09(_snapshot(),projection.status_document())
    assert html.count('href="/intraday/trade-candidates"')==2
    app.wo09.mark_currentness("NSE-EQ-LUPIN",CurrentnessState.REASSESSMENT_DUE,updated_at=NOW+timedelta(seconds=1))
    html=render_intraday_wo09(_snapshot(),projection.status_document())
    assert html.count('href="/intraday/trade-candidates"')==1


def test_construction_route_rejects_geometry_and_unknown_payload(tmp_path):
    import json
    app,kw,_,_=native(tmp_path/"future")
    *_,routes=_routes(tmp_path/"browser")
    routes._futures_control=IntradayFuturesControl(app,lambda *_:session())
    before=_fingerprints(tmp_path)
    payload={"handoff_identity":kw["adapter"].wo09.handoff_identity,"request_identity":"BAD","geometry":{}}
    response=routes.handle_post(BrowserPostRequest("/control/intraday-futures/construction",{},"application/json",json.dumps(payload).encode()),_snapshot)
    assert response.status==400
    assert _fingerprints(tmp_path)==before
