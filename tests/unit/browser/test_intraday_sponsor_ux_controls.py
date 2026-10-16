"""Governed disposable read models and actual client control logic; no Provider."""
from dataclasses import replace
from hashlib import sha256
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import subprocess
import shutil

import pytest

from kronos.browser.intraday_machine_controls import CONTROLS_JS
from kronos.browser.intraday_wo08 import _machine_table, render_machine_review, render_sponsor_opportunities, _latest_attempt_summary
from tests.unit.browser.test_intraday_attention_funnel import documents
from tests.unit.browser.test_product_route_isolation import _snapshot


class Rows(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.rows = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'tr' and 'data-assessment-controls' in attrs:
            self.rows.append((attrs['id'], json.loads(attrs['data-assessment-controls'])))


def inventory(root):
    return {str(p): sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}


def javascript(tmp_path, assertions):
    path = tmp_path / 'controls.cjs'
    path.write_text(CONTROLS_JS + '\n' + assertions)
    node = shutil.which('node')
    assert node is not None, 'Node.js required for actual client logic qualification'
    subprocess.run([node, '--check', str(path)], check=True, capture_output=True, text=True)
    result = subprocess.run([node, str(path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_all_controls_combine_and_sort_actual_client_logic(tmp_path):
    javascript(tmp_path, r'''
const assert=require('node:assert/strict');
const a={security:'Copper · MCX-FUT-COPPER-2026-10-30',direction:'SHORT',score:'4',
 status:'READY · SELL_READY · Current eligible assessment',waiting:['Follow-through'],monitoring:'ACTIVE',price:'9.95',secondary:true,order:1};
const b={...a,security:'Alpha',score:'5',price:'100',order:0};
const c={...a,security:'Conflict',direction:'CONFLICTING',score:'UNAVAILABLE',price:'UNAVAILABLE',secondary:false,order:2};
const filters={security:'copper-2026',direction:'SHORT',score:'4',status:a.status,waiting:'Follow-through',monitoring:'ACTIVE',minimum:'9',maximum:'10',secondary:true};
assert.equal(matches(a,filters),true);assert.equal(matches(b,filters),false);assert.equal(matches(c,filters),false);
for(const key of ['direction','score','status','waiting','monitoring'])assert.equal(matches(a,{...filters,[key]:'absent'}),false);
assert.equal(matches(a,{minimum:'10'}),false);assert.equal(matches(a,{maximum:'9.949'}),false);
assert.equal(matches(c,{minimum:'0'}),false);assert.equal(matches(c,{direction:'CONFLICTING',score:'UNAVAILABLE'}),true);
assert.equal(matches(c,{secondary:true}),false);assert.equal(matches(c,{}),true);
assert.deepEqual([a,b,c].sort((x,y)=>compareRows(x,y,'price-asc')).map(x=>x.security),[a.security,b.security,c.security]);
assert.deepEqual([a,b,c].sort((x,y)=>compareRows(x,y,'score-desc')).map(x=>x.score),['5','4','UNAVAILABLE']);
assert.deepEqual([a,b,c].sort((x,y)=>compareRows(x,y,'security-asc')).map(x=>x.security),['Alpha','Conflict',a.security]);
assert.deepEqual([a,b,c].sort((x,y)=>compareRows(x,y,'original')).map(x=>x.order),[0,1,2]);
assert.equal(compareRows(a,{...a,score:'NOT_APPLICABLE'},'score-asc'),-1);
assert.equal(compareRows({...a,score:'0'},{...a,score:'UNAVAILABLE'},'score-desc'),-1);
''')


@pytest.mark.parametrize('left,right,expected', [
    ('9.95', '100', -1), ('100', '9.95', 1), ('9007199254740992.01', '9007199254740992.02', -1),
    ('1.000', '1', 0), ('1e3', '999', 1), ('0', '-0', 0), ('-1.1', '-1.01', -1),
    ('0.000001', '.001', -1), ('-100', '-99', -1), ('100000000000.00001', '1e11', 1),
])
def test_exact_numeric_order_without_float_rounding(tmp_path, left, right, expected):
    output = javascript(tmp_path, 'console.log(Math.sign(compareDecimal(decimal(' + json.dumps(left)
        + '),decimal(' + json.dumps(right) + '))));')
    assert int(output) == expected


def test_missing_values_do_not_become_zero(tmp_path):
    javascript(tmp_path, '''const assert=require('node:assert/strict');
for(const v of ['', 'UNAVAILABLE', 'NOT_APPLICABLE', null, false, 'NaN', '<script>'])assert.equal(decimal(v),null);
assert.equal(decimal('0').sign,0);
''')


def test_rendered_population_pairs_exact_contract_and_no_writes(tmp_path):
    status, readiness = documents(tmp_path)
    before = inventory(tmp_path)
    html = render_machine_review(_snapshot(), status, readiness)
    parsed = Rows(html)
    primary = [r for key, r in parsed.rows if key.startswith('review-')]
    diagnostics = [r for key, r in parsed.rows if key.startswith('diagnostic-')]
    assert len(primary) == 11 and len(diagnostics) == 98
    assert html.count('class="row-detail"') == 109
    assert any('MCX-FUT-' in r['security'] for r in diagnostics)
    assert {r['monitoring'] for r in diagnostics} == {'ACTIVE', 'INACTIVE', 'UNAVAILABLE'}
    assert {'0', '1', '2', '3', '4', '5', 'UNAVAILABLE'} <= {r['score'] for r in diagnostics}
    assert all(r['price'] == '123.45' for r in diagnostics)
    assert 'data-population="Current Secondary Review population"' in html
    assert 'data-population="Complete Diagnostics population"' in html
    assert 'aria-live="polite"' in html and '<noscript>' in html and 'data-clear-controls' in html
    assert html.count('id="secondary-review-only"') == 1
    assert inventory(tmp_path) == before
    destination = os.environ.get('SPONSOR_UX_OUTPUT')
    if destination:
        out = Path(destination); out.mkdir(parents=True, exist_ok=True)
        (out / 'review.html').write_text(html)
        status['currentness'] = 'SUPERSEDED'
        (out / 'historical.html').write_text(render_machine_review(_snapshot(), status, readiness))


def test_not_applicable_negative_directions_and_escaped_identifiers(tmp_path):
    status, readiness = documents(tmp_path)
    row = dict(status['assessments'][0])
    row.update(subject='NSE-EQ-<script>"&', direction='CONFLICTING', assessment_price=None,
               exact_mcx_contract_identity='MCX-"<&')
    row['criteria'] = [dict(c, state='NOT_APPLICABLE') for c in row['criteria']]
    readiness['cards'] = (replace(readiness['cards'][0], score='NOT_APPLICABLE', readiness_state='HARD_GATE'),)
    html = _machine_table([row], readiness, retained=True)
    data = Rows(html).rows[0][1]
    assert data['score'] == 'NOT_APPLICABLE' and data['direction'] == 'CONFLICTING'
    assert data['price'] == 'UNAVAILABLE' and 'Retained evidence' in data['status']
    assert '<script>"&' not in html and '&lt;script&gt;' in html
    assert 'Current eligible assessment' not in html


def test_no_outstanding_criteria_and_unavailable_remain_distinct(tmp_path):
    status, readiness = documents(tmp_path)
    rows = Rows(_machine_table(status['assessments'], readiness)).rows
    now = next(data for _, data in rows if data['score'] == '5')
    unavailable = next(data for _, data in rows if 'NSE-EQ-UNAVAILABLE' in data['security'])
    assert now['waiting'] == ['No outstanding criteria']
    assert unavailable['score'] == 'UNAVAILABLE'
    assert unavailable['waiting'] != ['No outstanding criteria']


def test_visible_summary_uses_one_exact_attempt_not_last_success(tmp_path):
    from tests.unit.browser.test_iwo06c_observability import history_fixture
    from kronos.browser.intraday_probables_v2_control import analysis_history_entry
    _, _, record, accounting = history_fixture(tmp_path / 'history', seconds=79.895253)
    entry = analysis_history_entry(record, accounting)
    status, readiness = documents(tmp_path / 'render')
    control = dict(recent_analysis_history=(entry,), last_refresh_attempt=dict(
        attempted_at='2026-09-10T20:16:00+05:30', outcome='UNRELATED_SUCCESS'))
    html = render_sponsor_opportunities(_snapshot(), status, readiness, refresh_status=control)
    summary = html.split('<aside class="machine-review latest-analysis"')[1].split('</aside>')[0]
    assert 'Failed' in summary and '1m 20s' in summary and '98 analysed' in summary
    assert 'UNRELATED' not in summary and '10 SEP' not in summary
    assert 'Boundary · ' in summary and 'Completed · ' in summary
    assert 'Analysis History · recent retained attempts' in html and 'Exact operation timing' in html
    destination = os.environ.get('SPONSOR_UX_OUTPUT')
    if destination:
        (Path(destination) / 'opportunities.html').write_text(html)


@pytest.mark.parametrize('change', [dict(), dict(operation_accounting_identity=None),
    dict(provenance_identity=None), dict(duration_authority='REQUEST_ENVELOPE'), dict(duration_microseconds=None)])
def test_missing_accounting_or_binding_never_reconstructs_duration(change):
    entry = dict(provenance_identity='PROVENANCE', operation_accounting_identity='ACCOUNTING',
        duration_authority='RETAINED_OPERATION_ACCOUNTING', duration_microseconds=82000000,
        result='FAILED', analysed_population=98)
    if change:
        entry.update(change)
        html = _latest_attempt_summary(dict(recent_analysis_history=(entry,)))
    else:
        html = _latest_attempt_summary({})
    assert 'Duration unavailable' in html and '1m 22s' not in html


def test_latest_failed_attempt_duration_is_not_an_older_success():
    failed = dict(provenance_identity='FAILED-ID', operation_accounting_identity='FAILED-ACCOUNTING',
        duration_authority='RETAINED_OPERATION_ACCOUNTING', duration_microseconds=1000000,
        result='FAILED', boundary='2026-10-16T10:21:00+05:30', analysed_population=0)
    old = dict(failed, result='SUCCESS', duration_microseconds=82000000, boundary='2026-09-10T20:16:00+05:30')
    html = _latest_attempt_summary(dict(recent_analysis_history=(failed, old)))
    assert 'Failed · 1s · 0 analysed' in html
    assert '10 SEP' not in html and '1m 22s' not in html
