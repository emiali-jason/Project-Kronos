"""INT-D presentation-only attention over retained source-valid projections."""
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from kronos.browser.intraday_wo08 import render_machine_review, render_sponsor_opportunities
from kronos.intraday.sponsor_presentation import opportunity_label
from kronos.browser.dashboard import IntradayDashboardSummary, project_intraday_dashboard, project_sponsor_dashboard
from kronos.browser.intraday_wo09_control import project_card, project_analysis_details
from kronos.browser.views import render_dashboard
from kronos.application.notifications import NotificationWorkspaceSnapshot
from tests.unit.browser.test_intraday_iwo_ux import projection_fixture, summary_sources, mcx_options
from tests.unit.browser.test_product_route_isolation import _snapshot


FOUR = dict(five_rows=[(108,102,106)]*25+[(115,110,113),(117,114,116)])
THREE = dict(**FOUR, daily=(118,92,105))


def documents(tmp_path):
    rows, cards, details = [], [], {}
    for i, (subject, options) in enumerate((
        ('NSE-EQ-SAIL', THREE), ('NSE-EQ-BAJAJ-AUTO', FOUR), ('NSE-EQ-RELIANCE', {}),
        ('NSE-EQ-INFY', THREE), ('NSE-EQ-HDFCBANK', FOUR), ('NSE-EQ-DIVISLAB', {}),
        ('NSE-EQ-UNAVAILABLE', dict(missing_five=(26,))),
    )):
        a, r, _, detail = projection_fixture(tmp_path/str(i), subject=subject, **options)
        rows.append(dict(identity=a.identity, integrity=a.integrity,
            **{k:v for k,v in a.data.items() if k != 'source_document'},
            assessment_price='123.45', assessment_price_time=a.data['created_at']))
        from kronos.intraday.wo09_persistence import Wo09Store
        store=Wo09Store(tmp_path/str(i))
        cards.append(project_card(r, store.load_requirements(r.readiness_identity)))
        detail['F. EXPERIMENTAL OBSERVATION']['monitoring'] = dict(
            state=('ACTIVE','UNAVAILABLE','INACTIVE')[i%3], reason='Isolated retained monitoring projection.')
        details[r.readiness_identity]=detail
    # Lower-score retained read-model descriptors exercise all diagnostic states;
    # they are never represented as producer qualification or new authority.
    for score in (0,1,2):
        row=dict(rows[0], identity='LOW-'+str(score), subject='NSE-EQ-LOW'+str(score),
                 probable_result_identity='LOW-'+str(score))
        card=replace(cards[0],readiness_identity='LOW-READINESS-'+str(score),
                     instrument=row['subject'],readiness_state='NO_FOCUS',score=f'{score} / 5')
        rows.append(row);cards.append(card)
        details[card.readiness_identity]={'A. MACHINE WO08 ASSESSMENT':dict(identity=row['identity'])}
    for i in range(88):
        rows.append(dict(rows[0], identity='EXCLUDED-'+str(i), subject='NSE-EQ-EXCLUDED'+str(i),
                         probable_result_identity='EXCLUDED-'+str(i), probables_state='NOT_ADMITTED',
                         disposition='HARD_GATE', failure_reason='PROBABLES_NOT_ADMITTED'))
    # Put an actual exact-bound MCX assessment in the same 98-row attention
    # fixture; its source contract remains visible rather than NSE-normalized.
    a,r,q,d=projection_fixture(tmp_path/'mcx',**mcx_options())
    rows[-1]=dict(identity=a.identity,**a.data,assessment_price='123.45')
    cards.append(project_card(r,q))
    d['F. EXPERIMENTAL OBSERVATION']['monitoring']=dict(state='INACTIVE',reason='No selective watch required.')
    details[r.readiness_identity]=d
    assert len(rows)==98
    readiness=dict(cards=tuple(cards),analysis_details=details,
        operational_summary=IntradayDashboardSummary(3,2,'CURRENT_SESSION_VERIFIED',tuple(c.readiness_identity for c in cards)))
    return dict(currentness='SOURCE_LINEAGE_CURRENT',assessments=tuple(rows)),readiness


@pytest.mark.parametrize('renderer',[render_sponsor_opportunities,render_machine_review])
def test_98_attention_primary_and_full_diagnostics(tmp_path,renderer):
    status,readiness=documents(tmp_path)
    before={str(p):sha256(p.read_bytes()).hexdigest() for p in tmp_path.rglob('*.json')}
    html=renderer(_snapshot(),status,readiness)
    if renderer is render_sponsor_opportunities:
        assert 'NEAR READY' not in html and 'SECONDARY REVIEW' not in html
        assert html.count('id="review-candidate-')==5
        assert 'Diagnostics in Review' in html
        assert 'READY</span><strong>2' in html and 'NOW</span><strong>3' in html
        for i in range(3):assert 'LOW'+str(i) not in html
    else:
        primary,diagnostics=html.split('<details id="intraday-diagnostics">',1)
        assert 'NEAR READY</span><strong>2' in primary
        assert 'SECONDARY REVIEW</span><strong>11' in primary
        assert 'READY</span><strong>2' in primary and 'NOW</span><strong>3' in primary
        assert primary.count('id="review-candidate-')==11
        assert diagnostics.count('id="diagnostic-candidate-')==98
        for i in range(3):assert 'LOW'+str(i) in diagnostics
        assert 'UNAVAILABLE' in diagnostics and 'EXCLUDED86' in diagnostics
        assert 'Analysed</span><strong>98' in html and 'Considered</span><strong>11' in html
        assert html.count('id="review-candidate-')==98
    assert status['assessments'][-1]['exact_mcx_contract_identity'] in html
    assert 'BAJAJ AUTO' in html and 'Follow-through' in html
    assert before=={str(p):sha256(p.read_bytes()).hexdigest() for p in tmp_path.rglob('*.json')}
    destination=os.environ.get('INT_D_REHEARSAL_OUTPUT')
    if destination:
        out=Path(destination);out.mkdir(parents=True,exist_ok=True)
        (out/(renderer.__name__+'.html')).write_text(html)


@pytest.mark.parametrize('score,state,direction,expected',[
    ('0 / 5','NO_FOCUS','LONG',None),('1 / 5','NO_FOCUS','LONG',None),('2 / 5','NO_FOCUS','LONG',None),
    ('3 / 5','NEAR_READY','LONG','NEAR READY'),('4 / 5','BUY_READY','LONG','READY'),
    ('5 / 5','SELL_NOW','SHORT','NOW'),('4 / 5','READINESS_UNAVAILABLE','LONG',None),
    ('5 / 5','HARD_GATE','LONG',None),('3 / 5','READINESS_UNAVAILABLE','LONG',None),
    ('4 / 5','SELL_READY','LONG',None),('NOT_APPLICABLE','HARD_GATE','LONG',None),
])
def test_score_cannot_override_gate_unavailability_or_direction(tmp_path,score,state,direction,expected):
    _,readiness=documents(tmp_path)
    card=replace(readiness['cards'][0],score=score,readiness_state=state,direction=direction)
    assert opportunity_label(card)==expected
    assert opportunity_label(replace(card,monitorability_state='SUPERSEDED')) is None


@pytest.mark.parametrize('currentness',['SUPERSEDED','SOURCE_LINEAGE_CURRENT'])
def test_historical_sessions_missing_authority_and_stale_pointer_are_diagnostics(tmp_path,currentness):
    status,readiness=documents(tmp_path)
    status['currentness']=currentness
    readiness['operational_summary']=IntradayDashboardSummary(0,0,'NO_CURRENT_READINESS')
    html=render_sponsor_opportunities(_snapshot(),status,readiness)
    assert 'id="review-candidate-' not in html and 'No current READY/NOW opportunities.' in html
    reviewed=render_machine_review(_snapshot(),status,readiness)
    primary,diagnostics=reviewed.split('<details id="intraday-diagnostics">',1)
    assert 'id="review-candidate-' not in primary
    assert diagnostics.count('id="diagnostic-candidate-')==98
    assert 'NEAR READY</span><strong>0' in primary
    readiness['operational_summary']=IntradayDashboardSummary()
    html=render_sponsor_opportunities(_snapshot(),status,readiness)
    assert 'READY</span><strong>—' in html and 'NEAR READY' not in html


@pytest.mark.parametrize('direction',['LONG','SHORT'])
def test_source_valid_transitions_restarted_store_and_dashboard_exclusion(tmp_path,direction):
    from datetime import datetime
    from kronos.intraday.wo09_persistence import Wo09Store
    from tests.unit.intraday.test_wo09_experimental import publish,origin_for
    from tests.unit.intraday.test_wo08_experimental import experimental_fixture
    store=Wo09Store(tmp_path)
    origin=None
    for i,(options,score,label) in enumerate(((THREE,3,'NEAR READY'),(FOUR,4,'READY'),({},5,'NOW'),
        (FOUR,4,'READY'),(THREE,3,'NEAR READY'),({**THREE, 'five_rows':[(108,102,106)]*25+[(121,110,113),(121,114,120)]},2,None))):
        # Explicit override for the last recipe, no analytical state is forged.
        a=experimental_fixture(direction,**options)[-1]
        at=datetime.fromisoformat(a.data['created_at'])+timedelta(seconds=i)
        origin=origin or origin_for(a)
        r,q=publish(store,a,origin,at)
        assert r.satisfied_count==score
        card=project_card(r,q)
        assert opportunity_label(card)==label
        restarted=Wo09Store(tmp_path)
        assert restarted.restore_current()[0][1]==r
        assert opportunity_label(project_card(restarted.load_readiness(r.readiness_identity),q))==label


def test_near_ready_never_dashboard_and_read_does_not_notify(tmp_path,monkeypatch):
    store,owner,r=summary_sources(tmp_path,monkeypatch,**THREE)
    notices=[];store.notification_listener=lambda *args:notices.append(args)
    summary=project_intraday_dashboard(store,owner)
    assert r.satisfied_count==3 and summary.current_readiness==(r.readiness_identity,)
    assert summary.ready==summary.now==0 and summary.opportunities==()
    base=project_sponsor_dashboard(_snapshot(),None,(),NotificationWorkspaceSnapshot(()))
    html=render_dashboard(_snapshot(),replace(base,intraday=summary))
    intraday=html.split('<article class="strategy-card intraday">')[1].split('</article>')[0]
    assert 'NEAR READY' not in intraday and r.canonical_subject_identity not in intraday
    assert notices==[]
    from kronos.application.intraday_notification_sources import ready
    from tests.unit.intraday.test_wo09_experimental import origin_for
    from kronos.intraday.wo09_experimental import assessment_from
    assert ready(origin_for(assessment_from(r.assessment_document)),r) is None


def test_exact_mcx_contract_in_primary(tmp_path):
    a,r,q,d=projection_fixture(tmp_path,**mcx_options())
    card=project_card(r,q)
    status=dict(currentness='SOURCE_LINEAGE_CURRENT',assessments=(dict(identity=a.identity,**a.data),))
    readiness=dict(cards=(card,),analysis_details={r.readiness_identity:d},
        operational_summary=IntradayDashboardSummary(1,0,'CURRENT_SESSION_VERIFIED',(r.readiness_identity,)))
    html=render_sponsor_opportunities(_snapshot(),status,readiness)
    assert a.data['exact_mcx_contract_identity'] in html and 'NOW' in html


def test_canonical_http_opportunities_uses_funnel_not_probables_cards(tmp_path,monkeypatch):
    from tests.unit.browser.test_intraday_wo08_browser import _routes
    from tests.unit.browser.test_browser_swing_notifications_correction import browser,inventory
    from kronos.browser.product_routes import ProductBrowserRoutes
    from tests.unit.browser.test_browser_server import _request
    from kronos.browser.intraday_wo09_control import IntradayWo09Projection
    from kronos.intraday.wo09_persistence import Wo09Store
    status,readiness=documents(tmp_path/'sources')
    projection=IntradayWo09Projection(Wo09Store(tmp_path/'readiness'),machine_successor=True)
    monkeypatch.setattr(projection,'status_document',lambda:readiness)
    routes=_routes(tmp_path/'routes',SimpleNamespace(status_document=lambda:status),
        wo09_projection=projection)
    with browser(tmp_path/'server') as (server,_,_):
        server.product_routes=ProductBrowserRoutes((routes,))
        before=inventory(tmp_path)
        for route in ('/intraday','/intraday/review'):
            code,_,html=_request(server,'GET',route)
            assert code==200
            if route=='/intraday':
                assert html.count('id="review-candidate-')==5 and 'NEAR READY' not in html
            else:
                primary,diagnostics=html.split('<details id="intraday-diagnostics">',1)
                assert primary.count('id="review-candidate-')==11
                assert diagnostics.count('id="diagnostic-candidate-')==98
        assert inventory(tmp_path)==before
        assert server.swing_monitoring_hub.status_document()['owner_count']==0


def test_publication_conflict_and_missing_machine_projection_fail_closed(tmp_path):
    from tests.unit.browser.test_intraday_wo08_browser import _routes
    from kronos.browser.product_routes import BrowserGetRequest
    def failure():raise ValueError('WO09_PUBLICATION_EXPECTATION_CHANGED')
    routes=_routes(tmp_path,SimpleNamespace(status_document=failure))
    for path in ('/intraday','/intraday/review'):
        response=routes.handle_get(BrowserGetRequest(path,{}),_snapshot)
        assert response.status.value==503 and 'READ_ONLY_PROJECTION' in response.body
        assert 'WO09_PUBLICATION_EXPECTATION_CHANGED' in response.body
