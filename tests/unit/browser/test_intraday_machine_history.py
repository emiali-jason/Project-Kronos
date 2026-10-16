"""Actual product route transport and rendering of isolated machine history."""
from html.parser import HTMLParser
from types import SimpleNamespace
from urllib.parse import urlsplit,parse_qs
import pytest
from kronos.browser.intraday_machine_history import history_response,MACHINE_HISTORY_ROUTE
from kronos.browser.product_routes import BrowserGetRequest
from tests.unit.application.test_intraday_machine_history import history_fixture,inventory,retain_positive
from tests.unit.browser.test_intraday_wo08_browser import _routes
from tests.unit.browser.test_product_route_isolation import _snapshot


class Links(HTMLParser):
    def __init__(self):super().__init__();self.links=[]
    def handle_starttag(self,tag,attrs):
        if tag=='a':self.links.append(dict(attrs).get('href',''))


def get(f,**values):return history_response(f.reader,{k:[str(v)] for k,v in values.items()},_snapshot)


@pytest.mark.parametrize('query',[{'extra':['x']},{'page':['1','2']},{'run':['../x']},
    {'run':[]},{'run':['']},{'run':['a'*161]},{'page':['0']},{'page_size':['51']},
    {'page':['999']},{'page_size':['1.5']},{'assessment':['WO08-ASSESSMENT-'+'a'*64]}])
def test_query_rejection_is_bounded_without_raw_details(tmp_path,query):
    f=history_fixture(tmp_path);before=inventory(tmp_path)
    r=history_response(f.reader,query,_snapshot)
    assert r.status.value==400 and str(tmp_path) not in r.body and inventory(tmp_path)==before


def test_actual_route_bypasses_current_projection_and_preserves_other_routes(tmp_path):
    f=history_fixture(tmp_path/'evidence')
    def forbidden():raise AssertionError('current projection forbidden')
    routes=_routes(tmp_path/'route',SimpleNamespace(status_document=forbidden),machine_history=f.reader)
    before=inventory(tmp_path)
    r=routes.handle_get(BrowserGetRequest(MACHINE_HISTORY_ROUTE,{'run':[f.run.run_identity]}),_snapshot)
    assert r.status.value==200 and 'Complete validated assessment population: 98' in r.body
    assert 'no authority for new work' in r.body and 'not a complete historical READY/NOW catalogue' in r.body
    assert not routes.owns_post(MACHINE_HISTORY_ROUTE)
    assert routes.handle_get(BrowserGetRequest('/swing/review',{}),_snapshot) is None
    assert inventory(tmp_path)==before


def test_conflict_has_actual_safe_clickable_run_only_reload_no_retry(tmp_path,monkeypatch):
    f=history_fixture(tmp_path);calls=[];original=f.reader.page
    def page(**kw):calls.append(kw);return original(**kw)
    monkeypatch.setattr(f.reader,'page',page)
    r=get(f,run=f.run.run_identity,page=2,page_size=50,population='0'*64)
    assert r.status.value==409 and r.content_type.startswith('text/html') and len(calls)==1
    parser=Links();parser.feed(r.body)
    links=[x for x in parser.links if x.startswith(MACHINE_HISTORY_ROUTE+'?')]
    assert len(links)==1 and parse_qs(urlsplit(links[0]).query)=={'run':[f.run.run_identity]}
    assert 'no authority for new work' in r.body and 'Reload selected run explicitly' in r.body
    reloaded=history_response(f.reader,parse_qs(urlsplit(links[0]).query),_snapshot)
    assert reloaded.status.value==200 and len(calls)==2 and 'Page 1' in reloaded.body


def test_escaping_pairing_known_run_outside_window_and_missing_states(tmp_path):
    f=history_fixture(tmp_path);f.recent[:]=[dict(result='<script>alert(1)</script>',run_identity=None)]
    r=get(f,run=f.run.run_identity)
    assert '<script>alert(1)</script>' not in r.body and '&lt;script&gt;' in r.body
    assert 'outside the current recent-five window' in r.body
    assert 'Original readiness not linked' in r.body and 'Assessment Price not retained' in r.body
    assert r.body.count('Known exact retained readiness identity')==25
    section=r.body.split('<section class="machine-history">',1)[1].split('</section>',1)[0]
    assert 'method="post"' not in section  # Existing shared-shell Connect/Exit controls stay unchanged.
    assert 'overflow-x:auto' in r.body


@pytest.mark.parametrize('size,count',[(25,25),(50,50)])
def test_form_controls_and_full_population_paging(tmp_path,size,count):
    f=history_fixture(tmp_path);r=get(f,run=f.run.run_identity,page_size=size)
    assert r.status.value==200 and r.body.count('Known exact retained readiness identity')==count
    parser=Links();parser.feed(r.body)
    nxt=next(x for x in parser.links if 'population=' in x and 'page=2' in x)
    r2=history_response(f.reader,parse_qs(urlsplit(nxt).query),_snapshot)
    assert r2.status.value==200 and 'Page 2' in r2.body and 'Original manifest member order' in r2.body


def test_optional_proof_failure_keeps_valid_historical_page(tmp_path):
    f=history_fixture(tmp_path,experimental=True);a,r=retain_positive(f)
    (f.readiness.first_five/(r.first_five_document['claim_identity']+'.json')).unlink()
    response=get(f,run=f.run.run_identity,assessment=a.identity,readiness=r.readiness_identity)
    assert response.status.value==200 and 'EXACT_READINESS_REQUIRED_PROOF_NOT_ESTABLISHED' in response.body
    assert 'Complete validated assessment population: 98' in response.body
    assert '&quot;original&quot;' not in response.body


def test_absent_composition_503_and_visual_history_dispatch_unchanged(tmp_path):
    f=history_fixture(tmp_path/'evidence');seen=[]
    visual=SimpleNamespace(render=lambda snapshot:seen.append('html') or 'retained visual history',
        artifact=lambda query:seen.append(query) or __import__('kronos.browser.product_routes',fromlist=['BrowserRouteResponse']).BrowserRouteResponse(b'pdf',content_type='application/pdf'))
    routes=_routes(tmp_path/'route',SimpleNamespace(),visual_history=visual)
    assert routes.handle_get(BrowserGetRequest(MACHINE_HISTORY_ROUTE,{}),_snapshot).status.value==503
    assert 'retained visual history' in routes.handle_get(BrowserGetRequest('/intraday/review/history',{}),_snapshot).body
    assert routes.handle_get(BrowserGetRequest('/intraday/review/history/artifact',{'identity':['EXACT']}),_snapshot).body==b'pdf'
    assert seen==['html',{'identity':['EXACT']}]


def test_disposable_rehearsal_pages_export_from_actual_renderer(tmp_path):
    """Export only rendered synthetic HTML when the caller requests evidence."""
    import os,json
    from pathlib import Path
    f=history_fixture(tmp_path/'evidence',experimental=True,price=True)
    a,r=retain_positive(f)
    responses={}
    def capture(query):
        response=history_response(f.reader,query,_snapshot)
        key='&'.join(k+'='+str(v[0]) for k,v in sorted(query.items()))
        responses[key]=dict(status=response.status.value,content_type=response.content_type,body=response.body)
        return response
    capture({})
    one=f.reader.page(run=f.run.run_identity)
    for size in [25,50]:
        token=f.reader.page(run=f.run.run_identity,page_size=size)['population']
        for page in range(1,5 if size==25 else 3):
            capture({'run':[f.run.run_identity],'page':[str(page)],'page_size':[str(size)],'population':[token]})
        capture({'run':[f.run.run_identity],'page_size':[str(size)]})
    capture({'run':[f.run.run_identity]})
    capture({'run':[f.run.run_identity],'page':['2'],'population':['0'*64]})
    capture({'run':[f.run.run_identity],'assessment':[a.identity],'readiness':[r.readiness_identity]})
    capture({'run':[f.run.run_identity],'assessment':[a.identity],'readiness':[r.readiness_identity],
        'page':['1'],'page_size':['25'],'population':[one['population']]})
    capture({'run':[f.run.run_identity],'assessment':[a.identity],'readiness':['INTRADAY-WO09-EXPERIMENTAL-'+'A'*64]})
    f.recent.clear()
    capture({'run':[f.run.run_identity],'page_size':['26']})
    capture({'run':['INTRADAY-PROBABLES-V2-RUN-'+'A'*64]})
    capture({'run':['bad']})
    assert responses['run='+f.run.run_identity]['status']==200
    from kronos.browser.intraday_wo08 import IntradayVisualHistory
    from kronos.intraday.review_v2_persistence import IntradayReviewV2Store
    from kronos.intraday.review_mcx_paired_persistence import IntradayMcxPairedReviewStore
    from kronos.intraday.visual_reconciliation_v2_persistence import VisualReconciliationStore
    visual=IntradayVisualHistory(IntradayReviewV2Store(tmp_path/'visual'),
        IntradayMcxPairedReviewStore(tmp_path/'paired'),VisualReconciliationStore(tmp_path/'reconciled'))
    visual_html=visual.render(_snapshot())
    if os.environ.get('SCOPE_C_REHEARSAL_DIR'):
        p=Path(os.environ['SCOPE_C_REHEARSAL_DIR']);p.mkdir(parents=True,exist_ok=True)
        (p/'responses.json').write_text(json.dumps(dict(run=f.run.run_identity,
            assessment=a.identity,readiness=r.readiness_identity,responses=responses,visual_history_html=visual_html),indent=2))
