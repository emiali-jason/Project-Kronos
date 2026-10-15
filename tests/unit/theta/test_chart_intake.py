"""TE-01 disposable chart mechanics, not analytical or market qualification."""

from datetime import timedelta
from html import unescape
from http.client import HTTPConnection
from io import BytesIO
import json
import os
import re
import shutil
import subprocess
from urllib.parse import parse_qs, urlencode, urlsplit

from PIL import Image
import pytest

from kronos.browser.product_routes import BrowserGetRequest, BrowserPostRequest
from kronos.browser.theta_charts import chart_script
from kronos.browser.theta_routes import ThetaBrowserRoutes
from kronos.theta.contracts import CANONICAL, SUBJECTS, ThetaError, digest, encode
from kronos.theta.store import ThetaStore, sealed, unseal
from kronos.theta.workflow import CHART_ROLES, ThetaWorkflow
from tests.unit.theta.test_browser import snapshot
from tests.unit.theta.test_rehearsal import running
from tests.unit.theta.test_workflow import NOW, accepted, authority, chart, workflow


@pytest.fixture
def empty(tmp_path):
    return ThetaWorkflow(ThetaStore(tmp_path.resolve() / 'theta'),
        inbox=tmp_path.resolve() / 'answers', outbox=tmp_path.resolve() / 'questions', clock=lambda: NOW)


def image(format='PNG', color='red'):
    stream = BytesIO()
    Image.new('RGB', (31, 19), color).save(stream, format=format)
    return stream.getvalue()


def role(workflow, subject):
    return next(c for c in workflow.chart_workspace()['cards'] if c['subject'] == subject)


def receive(workflow, subject, *, payload=None, media_type='image/png', bound=True):
    card = role(workflow, subject)
    return workflow.intake_chart(subject=subject, label='Synthetic composite ' + subject,
        media_type=media_type, payload=image() if payload is None else payload,
        information_cutoff=workflow.now().isoformat(), cutoff_basis='INTAKE_RECEIPT_NOT_CHART_TIME',
        **({'expected_cycle_id': card['cycle_id'] or 'UNSTARTED',
            'expected_revision_id': card['revision_id']} if bound else {}))


def inventory(workflow):
    return {str(p.relative_to(workflow.store.root)): p.read_bytes()
            for p in workflow.store.root.rglob('*') if p.is_file()}


def path(card, endpoint='chart'):
    return '/theta-earners/' + endpoint + '?' + urlencode(dict(subject=card['subject'],
        cycle=card['cycle_id'] or 'UNSTARTED', revision=card['revision_id'] or 'MISSING'))


def raw(routes, card, payload, content_type='image/png'):
    address = urlsplit(path(card))
    return routes.handle_post(BrowserPostRequest(address.path, parse_qs(address.query),
        content_type, payload), snapshot)


def test_six_empty_cards_no_sixth_subject_or_invented_question_readiness(empty):
    workspace = empty.chart_workspace()
    assert workspace['cycle_id'] is None and len(workspace['cards']) == 6
    assert len(empty.summary()) == 5 and 'GLOBAL_MACRO' not in SUBJECTS
    page = ThetaBrowserRoutes(empty).handle_get(BrowserGetRequest('/theta-earners/new-analysis', {}), snapshot).body
    assert page.count('class="theta-chart-card') == 6
    assert page.count('role="button" tabindex="0"') == 6
    assert page.count('data-upload-url=') == 6
    assert page.count('Choose File') == 6
    assert 'COMMODITY CHARTS READY: 0 / 5' in page
    assert 'GLOBAL MACRO: MISSING' in page and 'QUESTION PACKS: 0 / 5' in page
    assert 'form id="theta-chart"' not in page and 'FileReader' not in page
    assert 'COMEX Gold' in page and 'COMEX Silver' in page and 'COMEX Copper' in page
    assert 'NYMEX Light Crude' in page and 'NYMEX Natural Gas' in page
    assert all(s in page for s in ('DXY', 'US 10Y', 'US 30Y', 'USD/INR', 'Nasdaq-100', 'USD/CNH', 'CSI 300', 'Dow Jones'))
    assert not (empty.store.root / 'cycles').exists()


@pytest.mark.parametrize('subject', CHART_ROLES)
@pytest.mark.parametrize('format,media_type', [('PNG', 'image/png'), ('JPEG', 'image/jpeg')])
def test_each_role_exact_bytes_identity_preview_and_restart(empty, subject, format, media_type):
    before = empty.chart_workspace()
    payload = image(format)
    identity = receive(empty, subject, payload=payload, media_type=media_type)
    current = role(empty, subject)
    assert current['chart_id'] == identity and current['chart']['sha256'] == digest(payload)
    assert current['intake']['byte_length'] == len(payload)
    assert current['intake']['accepted_at'] == NOW.isoformat()
    assert current['intake']['cycle_id'] == current['cycle_id']
    assert current['intake']['subject'] == (None if subject == 'GLOBAL_MACRO' else subject)
    assert current['intake']['role'] == ('GLOBAL_MACRO' if subject == 'GLOBAL_MACRO' else 'COMMODITY_COMPOSITE')
    assert current['intake']['cutoff_basis'] == 'INTAKE_RECEIPT_NOT_CHART_TIME'
    assert empty.preview_chart(subject=subject, cycle_id=current['cycle_id'],
        revision_id=current['revision_id']) == (media_type, payload)
    assert all(c['chart'] is None for c in empty.chart_workspace()['cards'] if c['subject'] != subject)
    restart = ThetaWorkflow(ThetaStore(empty.store.root), inbox=empty.inbox, outbox=empty.outbox, clock=lambda: NOW)
    assert restart.chart_workspace() == empty.chart_workspace()
    assert restart.preview_chart(subject=subject, cycle_id=current['cycle_id'],
        revision_id=current['revision_id'])[1] == payload
    assert before['cycle_id'] is None


@pytest.mark.parametrize('subject', CHART_ROLES)
def test_replacement_changes_only_selected_role_preserves_originals_and_history(empty, subject):
    for s in CHART_ROLES:
        receive(empty, s)
    before = empty.chart_workspace()
    retained = inventory(empty)
    old = role(empty, subject)
    empty.clock = lambda: NOW + timedelta(minutes=2)
    receive(empty, subject, payload=image(color='blue'))
    after = empty.chart_workspace()
    new = role(empty, subject)
    assert new['revision_id'] != old['revision_id'] and new['cycle_id'] == old['cycle_id']
    assert new['intake']['previous_revision_id'] == old['revision_id']
    assert [c for c in before['cards'] if c['subject'] != subject] == [c for c in after['cards'] if c['subject'] != subject]
    assert all(inventory(empty)[p] == value for p, value in retained.items() if p != 'current.json')
    assert empty.chart_bytes(old['chart']['sha256']) == image()
    with pytest.raises(ThetaError, match='BINDING_STALE'):
        empty.preview_chart(subject=subject, cycle_id=old['cycle_id'], revision_id=old['revision_id'])
    current = inventory(empty)
    with pytest.raises(ThetaError, match='BINDING_STALE'):
        empty.intake_chart(subject=subject, label='stale', media_type='image/png',
            payload=image(), information_cutoff=NOW.isoformat(), expected_cycle_id=old['cycle_id'],
            expected_revision_id=old['revision_id'])
    assert inventory(empty) == current


@pytest.mark.parametrize('payload,media_type', [(b'text', 'image/png'), (image(), 'image/jpeg'),
    (b'\x89PNG\r\n\x1a\ntruncated', 'image/png'), (image(), 'image/webp'),
    (b'', 'image/png'), (b'\x89PNG\r\n\x1a\n' + b'x' * (16 * 1024 * 1024), 'image/png')])
def test_invalid_image_never_selects_or_creates_cycle(empty, payload, media_type):
    empty.chart_workspace()
    before = inventory(empty)
    with pytest.raises(ThetaError, match='CHART_INVALID'):
        receive(empty, 'COPPER', payload=payload, media_type=media_type)
    assert inventory(empty) == before


def test_unknown_role_future_cutoff_and_invalid_clock_are_rejected(empty):
    for subject, cutoff in [('GOLD', NOW.isoformat()), ('GLOBAL_MACRO', (NOW + timedelta(days=1)).isoformat())]:
        with pytest.raises(ThetaError):
            empty.intake_chart(subject=subject, label='test', media_type='image/png',
                information_cutoff=cutoff, payload=image())
    empty.clock = lambda: NOW.replace(tzinfo=None)
    with pytest.raises(ThetaError, match='CLOCK_INVALID'):
        receive(empty, 'GOLDM')


def test_macro_is_supporting_and_existing_question_keeps_exact_five_chart_binding(workflow):
    identity, _, _ = accepted(workflow)
    question = workflow.store.question(identity)
    before = workflow.summary()
    receive(workflow, 'GLOBAL_MACRO')
    assert workflow.summary() == before
    assert workflow.store.question(identity) == question
    assert len(question['charts']) == 5 and len(question['targets']) == 10
    assert all(c['subject'] in SUBJECTS for c in question['charts'])
    assert workflow.create_question(SUBJECTS) == identity
    with pytest.raises(ThetaError):
        workflow.create_question(('GLOBAL_MACRO',))
    receive(workflow, 'COPPER', payload=image(color='blue'))
    after = workflow.summary()
    assert next(r for r in after if r['subject'] == 'COPPER')['question_id'] is None
    assert [r for r in before if r['subject'] != 'COPPER'] == [r for r in after if r['subject'] != 'COPPER']
    new = workflow.create_question(('COPPER',))
    assert workflow.store.question(new)['charts'] == [role(workflow, 'COPPER')['chart']]


def test_chart_ready_does_not_claim_question_ready_without_owner(empty):
    for s in SUBJECTS:
        receive(empty, s)
    page = ThetaBrowserRoutes(empty).handle_get(BrowserGetRequest('/theta-earners/new-analysis', {}), snapshot).body
    assert 'COMMODITY CHARTS READY: 5 / 5' in page and 'GLOBAL MACRO: MISSING' in page
    assert 'QUESTION PACKS: 0 / 5' in page
    assert page.count('NOT CURRENT / target and methodology checks remain required') == 5
    with pytest.raises(ThetaError, match='NOT_ESTABLISHED'):
        empty.create_question(SUBJECTS)
    empty.authority_provider = authority
    assert empty.create_question(SUBJECTS)  # Missing Macro adds no new generation gate.


@pytest.mark.parametrize('missing', ['current', 'cycle', 'revision', 'blob'])
def test_selected_dependency_missing_never_uses_mtime_or_orphan_fallback(empty, missing):
    receive(empty, 'COPPER')
    old = role(empty, 'COPPER')
    empty.clock = lambda: NOW + timedelta(minutes=1)
    receive(empty, 'COPPER', payload=image(color='blue'))
    current = role(empty, 'COPPER')
    targets = {'current': empty.store.root / 'current.json',
        'cycle': empty.store.root / 'cycles' / (current['cycle_id'] + '.json'),
        'revision': empty.store.root / 'chart-revisions' / (current['revision_id'] + '.json'),
        'blob': empty.store.root / 'blobs' / current['chart']['sha256']}
    os.utime(empty.store.root / 'charts' / (old['chart_id'] + '.json'), (9999999999, 9999999999))
    targets[missing].unlink()  # Disposable corrupt fixture only.
    with pytest.raises((ThetaError, OSError)):
        empty.chart_workspace()
    page = ThetaBrowserRoutes(empty).handle_get(BrowserGetRequest('/theta-earners/new-analysis', {}), snapshot).body
    assert 'CHART EVIDENCE INVALID / UNAVAILABLE' in page
    assert 'data-upload-url=' not in page and 'CURRENT PACK RETAINED' not in page
    with pytest.raises((ThetaError, OSError)):
        receive(empty, 'COPPER')


def test_legacy_selected_chart_readable_without_invented_cycle_or_intake_time(empty):
    core = dict(subject='COPPER', canonical_subject=CANONICAL['COPPER'], label='legacy', media_type='image/png',
        information_cutoff=NOW.isoformat(), sha256=digest(image()))
    identity = 'TEC-' + digest(encode(core))
    with empty.store.transaction():
        empty.store.blob(image())
        empty.store.retain('charts', identity + '.json', sealed(core))
        empty.store.select({'schema': 'KRONOS-THETA-SELECTION-V1', 'subjects': {'COPPER':
            {'chart_id': identity, 'question_id': None}}})
    current = role(empty, 'COPPER')
    assert current['cycle_id'] is None and current['intake'] is None
    assert empty.preview_chart(subject='COPPER', cycle_id='UNSTARTED', revision_id=identity)[1] == image()
    receive(empty, 'GLOBAL_MACRO')
    assert role(empty, 'COPPER')['intake'] is None
    receive(empty, 'COPPER', payload=image(color='blue'))
    assert role(empty, 'COPPER')['intake']['previous_revision_id'] == identity


@pytest.mark.parametrize('subject', CHART_ROLES)
def test_raw_route_and_original_preview_for_each_role(empty, subject):
    routes = ThetaBrowserRoutes(empty)
    response = raw(routes, role(empty, subject), image())
    value = json.loads(response.body)
    assert response.status == 200 and value['outcome'] == 'CHART_RECEIVED'
    current = role(empty, subject)
    assert value['revision_id'] == current['revision_id'] and value['sha256'] == digest(image())
    assert 'TAC-' in value['cycle_id']
    url = urlsplit(path(current, 'chart-preview'))
    preview = routes.handle_get(BrowserGetRequest(url.path, parse_qs(url.query)), snapshot)
    assert preview.status == 200 and preview.body == image() and preview.content_type == 'image/png'
    page = routes.handle_get(BrowserGetRequest('/theta-earners/new-analysis', {}), snapshot).body
    assert path(current, 'chart-preview').replace('&', '&amp;') in page
    assert 'Replace Chart' in page and 'Original bytes' in page and current['revision_id'] in page


@pytest.mark.parametrize('query', [{}, {'subject': ['COPPER']},
    {'subject': ['COPPER', 'GOLDM'], 'cycle': ['UNSTARTED'], 'revision': ['MISSING']},
    {'subject': ['COPPER'], 'cycle': ['UNSTARTED'], 'revision': ['MISSING'], 'extra': ['x']}])
def test_route_rejects_incomplete_or_ambiguous_bindings(empty, query):
    routes = ThetaBrowserRoutes(empty)
    assert routes.handle_post(BrowserPostRequest('/theta-earners/chart', query, 'image/png', image()), snapshot).status == 409
    assert routes.handle_get(BrowserGetRequest('/theta-earners/chart-preview', query), snapshot).status == 409
    assert all(c['chart'] is None for c in empty.chart_workspace()['cards'])


def test_identical_current_replay_is_idempotent_and_older_binding_rejected(empty):
    first = role(empty, 'COPPER')
    receive(empty, 'COPPER')
    selected = empty.chart_workspace()
    retained = inventory(empty)
    receive(empty, 'COPPER')
    assert empty.chart_workspace() == selected and inventory(empty) == retained
    assert raw(ThetaBrowserRoutes(empty), first, image()).status == 409


def test_corrupt_selected_revision_is_not_silently_repaired_by_replacement(empty):
    receive(empty, 'COPPER')
    current = role(empty, 'COPPER')
    revision_path = empty.store.root / 'chart-revisions' / (current['revision_id'] + '.json')
    revision_path.write_bytes(b'corrupt synthetic fixture')
    retained = inventory(empty)
    with pytest.raises(ThetaError):
        empty.intake_chart(subject='COPPER', label='replacement', media_type='image/png',
            information_cutoff=NOW.isoformat(), payload=image(color='blue'))
    assert inventory(empty) == retained


def test_image_pixel_bound_rejects_before_decoding(empty, monkeypatch):
    class Oversized:
        def __init__(self, _):
            pass
        def getSize(self):
            return 10001, 4000
        def getRGBData(self):
            pytest.fail('Oversized image must not be decompressed')
    monkeypatch.setattr('kronos.theta.workflow.ImageReader', Oversized)
    with pytest.raises(ThetaError, match='CHART_INVALID'):
        receive(empty, 'COPPER')


def test_overlapping_bound_replacements_admit_only_one_selected_revision(empty):
    from concurrent.futures import ThreadPoolExecutor
    receive(empty, 'COPPER')
    old = role(empty, 'COPPER')
    def replace(color):
        try:
            return empty.intake_chart(subject='COPPER', label=color, media_type='image/png',
                information_cutoff=NOW.isoformat(), payload=image(color=color),
                expected_cycle_id=old['cycle_id'], expected_revision_id=old['revision_id'])
        except ThetaError as error:
            return str(error)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(replace, ['blue', 'green']))
    assert sum(r.startswith('TEC-') for r in results) == 1
    assert results.count('THETA_CHART_BINDING_STALE') == 1
    assert role(empty, 'COPPER')['intake']['previous_revision_id'] == old['revision_id']


def test_real_shared_http_same_origin_guard_and_six_serial_cards(empty):
    with running(empty) as server:
        host = '127.0.0.1:' + str(server.server_port)
        def request(method, url, payload=None, origin=None):
            connection = HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            try:
                connection.request(method, url, body=payload, headers={'Host': host,
                    'Origin': origin or 'http://' + host, 'Content-Type': 'image/png'})
                response = connection.getresponse()
                return response.status, dict(response.getheaders()), response.read()
            finally:
                connection.close()
        before = empty.chart_workspace()
        assert request('POST', path(before['cards'][0]), image(), 'https://foreign.example')[0] == 403
        assert empty.chart_workspace() == before
        for subject in CHART_ROLES:
            current = role(empty, subject)
            status, _, body = request('POST', path(current), image())
            assert status == 200, body
            current = role(empty, subject)
            status, headers, binary = request('GET', path(current, 'chart-preview'))
            assert status == 200 and binary == image() and headers['Content-Type'] == 'image/png'
        retained = inventory(empty)
        page = request('GET', '/theta-earners/new-analysis')[2].decode()
        assert 'COMMODITY CHARTS READY: 5 / 5' in page and 'GLOBAL MACRO: READY' in page
        assert inventory(empty) == retained
        assert request('POST', path(before['cards'][0]), image())[0] == 409


@pytest.mark.parametrize('case', ['six', 'failed', 'fallback', 'replace', 'unsupported', 'oversized', 'pending', 'nonimage'])
def test_focused_clipboard_javascript_and_file_fallback(case):
    node = shutil.which('node')
    assert node is not None, 'Node.js required for TE-01 paste-event qualification'
    script = chart_script().removeprefix('<script>').removesuffix('</script>')
    harness = r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
const names=['GOLDM','SILVERM','COPPER','CRUDEOIL','NATURALGAS','GLOBAL_MACRO'];
const test=process.argv[1],requests=[],resolvers=[],timers=[],sections=[{hidden:false},{hidden:false}],refresh={hidden:true};
let reloads=0,focused=-1;
const targets=names.map((name,i)=>{
 const state={textContent:'CHART MISSING'},question={textContent:'QUESTION PACK · NOT READY'};
 const target={id:'theta-chart-'+name,dataset:{subject:name,cycle:'UNSTARTED',revision:'MISSING',chartAccepted:'false',
  uploadUrl:'/theta-earners/chart?subject='+name+'&cycle=UNSTARTED&revision=MISSING'},attrs:{},listeners:{},
  addEventListener(n,f){this.listeners[n]=f},focus(){focused=i},getAttribute(n){return this.attrs[n]},
  setAttribute(n,v){this.attrs[n]=v},removeAttribute(n){delete this.attrs[n]},classList:{add(){}},
  closest:()=>({dataset:{},querySelector:s=>s==='.theta-chart-state'?state:question}),feedback:{hidden:true,textContent:''}};
 target.state=state;return target;
});
const inputs=targets.map(t=>({dataset:{target:t.id},files:[],value:'file',listeners:{},addEventListener(n,f){this.listeners[n]=f}}));
const button={dataset:{target:targets[0].id},listeners:{},addEventListener(n,f){this.listeners[n]=f}};
const byId=Object.fromEntries(targets.flatMap(t=>[[t.id,t],[t.id+'-feedback',t.feedback]]));byId['theta-chart-refresh']=refresh;
const document={getElementById:id=>byId[id],querySelectorAll:s=>s==='.theta-chart-card .chart-paste-target'?targets:
 s==='.theta-chart-file'?inputs:s==='.theta-replace-chart'?[button]:s==='[data-theta-forecast],[data-theta-manual]'?sections:[]};
const file={type:test==='unsupported'?'image/webp':'image/png',size:test==='oversized'?16777217:100};
const fetch=(url,options)=>{requests.push({url,options});return new Promise(resolve=>resolvers.push(()=>resolve({
 ok:!(test==='failed'&&url.includes('COPPER')),json:async()=>test==='failed'&&url.includes('COPPER')?
 {failure:'THETA_CHART_BINDING_STALE'}:{outcome:'CHART_RECEIVED',cycle_id:'TAC-synthetic',revision_id:'TCR-'+requests.length,sha256:'b'.repeat(64)}})));};
vm.runInNewContext(SCRIPT,{document,Set,Array,Promise,URL,fetch,location:{href:'http://localhost:8948/theta-earners',reload:()=>reloads++},
 setTimeout:f=>{timers.push(f);return timers.length},clearTimeout:()=>{},addEventListener:()=>{}});
function paste(i){targets[i].listeners.paste({preventDefault(){},clipboardData:{items:test==='nonimage'?
 [{kind:'string',type:'text/plain'}]:[{kind:'file',type:file.type,getAsFile:()=>file}]}});}
(async()=>{
 targets[5].listeners.click();assert.equal(focused,5);
 const order=test==='six'||test==='failed'?[5,0,1,2,3,4]:[0];
 if(test==='replace'){targets[0].dataset.chartAccepted='true';paste(0);assert.equal(requests.length,0);
  button.listeners.click();assert.equal(focused,0);assert.equal(targets[0].dataset.chartAccepted,'false');}
 if(test==='fallback'){inputs[0].files=[file];inputs[0].listeners.change();assert.equal(inputs[0].value,'');}
 else for(const i of order)paste(i);
 if(test==='pending'){paste(0);assert.equal(targets[0].feedback.textContent,'UPLOAD_ALREADY_PENDING');}
 await new Promise(setImmediate);
 if(['unsupported','oversized','nonimage'].includes(test)){assert.equal(requests.length,0);assert.equal(targets[0].attrs['aria-busy'],undefined);return;}
 assert.equal(requests.length,1);
 for(let n=0;n<order.length;n++){
  const i=order[n],url=new URL(requests[n].url,'http://localhost:8948');
  assert.equal(url.searchParams.get('subject'),names[i]);
  assert.equal(url.searchParams.get('cycle'),n===0?'UNSTARTED':'TAC-synthetic');
  assert.equal(requests[n].options.body,file);assert.equal(requests[n].options.headers['Content-Type'],'image/png');
  assert.equal(requests[n].options.headers.Accept,'application/json');
  resolvers[n]();await new Promise(setImmediate);
  assert.equal(targets[i].attrs['aria-busy'],undefined);
  if(test==='failed'&&i===2){assert.match(targets[i].feedback.textContent,/BINDING STALE/);assert.equal(targets[i].dataset.chartAccepted,'false');}
  else {assert.match(targets[i].feedback.textContent,/CHART READY/);assert.equal(targets[i].dataset.chartAccepted,'true');}
  assert.equal(requests.length,Math.min(n+2,order.length));
 }
 assert.equal(refresh.hidden,false);assert(sections.every(s=>s.hidden));
 paste(5===order[0]?5:0);assert.equal(requests.length,order.length);
 if(test==='failed')assert.equal(timers.length,0);else {assert.equal(timers.length,1);timers[0]();assert.equal(reloads,1);}
})().catch(error=>{console.error(error);process.exitCode=1});
'''.replace('SCRIPT', json.dumps(script))
    result = subprocess.run([node, '-e', harness, case], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
