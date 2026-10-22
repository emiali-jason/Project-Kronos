"""Swing-only presentation over prepared owner facts; no I/O or analytical work.

The controls adapt the existing Intraday Machine Review interaction pattern.
Source/currentness, analytical decisions and all writes remain with existing owners.
"""
from html import escape
import json
from urllib.parse import urlencode

NSE_REVIEW = '/swing/nse-review'
MCX_REVIEW = '/swing/mcx-review'
_DISPOSITIONS = ('SUPPORT', 'REJECT', 'CHALLENGE', 'WAIT', 'INSUFFICIENT_EVIDENCE')


def local_view(projection, candidate):
    """Bind one prepared result using the existing Local presentation envelope."""
    unavailable = dict(state='UNAVAILABLE', reason='LOCAL_ASSESSMENT_NOT_PREPARED',
                       row=None, result=None)
    if not projection or projection.get('error') or not candidate:
        return unavailable
    workspace = projection.get('workspace') or {}
    if (workspace.get('state') != 'CURRENT' or not candidate.get('eligible')
            or candidate.get('market') != 'NSE'
            or workspace.get('run_identity') != candidate.get('run_identity')):
        return unavailable
    local = projection.get('local_analysis')
    if not local:
        return unavailable
    if (local.get('run_identity') not in {None, workspace.get('run_identity')}
            or local.get('publication_sha256') not in {None, workspace.get('manifest')}):
        return dict(unavailable, reason='LOCAL_RESEARCH_BINDING_MISMATCH')
    if local.get('state') != 'READY':
        return dict(unavailable, state='STALE' if local.get('state') == 'STALE' else 'UNAVAILABLE',
                    reason=local.get('reason') or 'LOCAL_ASSESSMENT_NOT_PREPARED')
    matches = [r for r in local.get('rows', ())
               if r.get('instrument') == candidate.get('instrument')
               and r.get('requirement_id') == candidate.get('requirement_sha256')]
    if len(matches) != 1:
        return dict(unavailable, reason='LOCAL_RESEARCH_BINDING_MISMATCH' if matches else
                    'LOCAL_ASSESSMENT_NOT_PREPARED')
    row = matches[0]
    state, reason, result = row.get('state', 'UNAVAILABLE'), row.get('reason'), row.get('result')
    if result is not None:
        binding = result.get('binding', {})
        if (state != 'SUCCEEDED' or local.get('run_identity') != workspace.get('run_identity')
                or local.get('publication_sha256') != workspace.get('manifest')
                or binding.get('instrument') != candidate.get('instrument')
                or binding.get('run_identity') != workspace.get('run_identity')
                or binding.get('publication_sha256') != workspace.get('manifest')
                or binding.get('assessment_sha256') != candidate.get('assessment_sha256')
                or binding.get('requirement_sha256') != candidate.get('requirement_sha256')
                or binding.get('direction') != candidate.get('direction')
                or result.get('contract') != 'KRONOS-SWING-NSE-LOCAL-RESULT-V1'
                or result.get('authority') != 'RESEARCH_ONLY_NO_ADMISSION_OR_EXECUTION'
                or result.get('input_sha256') != row.get('input_sha256')
                or not row.get('original_identity') or not row.get('result_sha256')
                or result.get('method_version') != local.get('method_version')
                or result.get('thesis', {}).get('overall', {}).get('disposition') not in _DISPOSITIONS):
            state, reason, result = 'UNAVAILABLE', 'LOCAL_RESEARCH_BINDING_MISMATCH', None
    elif state == 'SUCCEEDED':
        state, reason = 'UNAVAILABLE', 'LOCAL_ORIGINAL_OUTPUT_UNAVAILABLE'
    if state not in {'SUCCEEDED', 'STALE', 'NOT_RECORDED', 'UNAVAILABLE', 'FAILED'}:
        state, reason, result = 'UNAVAILABLE', 'LOCAL_ASSESSMENT_STATE_UNAVAILABLE', None
    return dict(state=state, reason=reason, row=row, result=result)


def _eligible_rows(projection, market=None, discovery=None):
    if not projection or projection.get('error'):
        return None
    workspace = projection.get('workspace') or {}
    if workspace.get('state') != 'CURRENT':
        return None
    if discovery is not None and workspace.get('run_identity') != discovery.run_identity:
        return None
    rows, seen = [], set()
    assessments = {} if discovery is None else {
        (a.canonical_instrument, a.result_sha256): a for a in discovery.assessments}
    for row in projection.get('rows', ()):
        if not row.get('eligible') or (market and row.get('market') != market):
            continue
        key = (row.get('run_identity'), row.get('market'), row.get('instrument'),
               row.get('assessment_sha256'), row.get('requirement_sha256'))
        if (key in seen or key[0] != workspace.get('run_identity')
                or not all(key) or key[1] not in {'NSE', 'MCX'}):
            return None
        if discovery is not None:
            assessment = assessments.get((row['instrument'], row['assessment_sha256']))
            if (assessment is None or assessment.status.value != 'PROBABLE'
                    or assessment.direction.value != row.get('direction')
                    or ('NSE' if assessment.product_path.name == 'NSE' else 'MCX') != row['market']):
                return None
        seen.add(key)
        rows.append(row)
    return rows


def build_dashboard_counts(projection, discovery=None):
    """One governed current cut; unknown population-level attribution stays null."""
    names = ('nse_eligible', 'mcx_eligible', 'completed', 'support', 'reject', 'challenge',
             'wait', 'insufficient', 'unavailable', 'failed', 'stale', 'not_recorded')
    counts = dict.fromkeys(names)
    counts.update(historical=None, attempts=None)
    rows = _eligible_rows(projection, discovery=discovery)
    if rows is None:
        return counts
    counts['nse_eligible'] = sum(r['market'] == 'NSE' for r in rows)
    counts['mcx_eligible'] = sum(r['market'] == 'MCX' for r in rows)
    nse = [r for r in rows if r['market'] == 'NSE']
    local = projection.get('local_analysis') or {}
    # Empty eligible set is known empty; an unavailable global capsule does not
    # establish how many individual candidates failed or became stale.
    if nse and local.get('state') != 'READY':
        return counts
    for name in names[2:]:
        counts[name] = 0
    for row in nse:
        value = local_view(projection, row)
        if value['state'] == 'SUCCEEDED' and value['result'] is not None:
            counts['completed'] += 1
            disposition = value['result']['thesis']['overall']['disposition']
            counts[{'INSUFFICIENT_EVIDENCE': 'insufficient'}.get(disposition, disposition.lower())] += 1
        else:
            counts[{'NOT_RECORDED': 'not_recorded', 'STALE': 'stale', 'FAILED': 'failed'}.get(
                value['state'], 'unavailable')] += 1
    return counts


def render_stage_counts(projection, discovery=None, *, nse_only=False):
    counts = build_dashboard_counts(projection, discovery)
    labels = [('nse_eligible', 'NSE Review eligible')]
    if not nse_only:
        labels.append(('mcx_eligible', 'MCX Review eligible'))
    labels += [('completed', 'NSE Local completed'), ('support', 'NSE SUPPORT'),
        ('reject', 'NSE REJECT'), ('challenge', 'NSE CHALLENGE'), ('wait', 'NSE WAIT / NEUTRAL'),
        ('unavailable', 'NSE unavailable'), ('failed', 'NSE failed'), ('stale', 'NSE stale')]
    def display(v):
        return 'Unavailable' if v is None else str(v)
    return ('<section class="swing-research-summary" aria-label="Source-bound second-stage accounting">'
        '<h2>Secondary research</h2><div class="swing-research-counters">'
        + ''.join('<div><span>' + label + '</span><strong data-count="' + key + '">'
                  + display(counts[key]) + '</strong></div>' for key, label in labels)
        + '</div><p class="secondary">Insufficient evidence · ' + display(counts['insufficient'])
        + ' · Not recorded · ' + display(counts['not_recorded'])
        + ' · Historical Local total · Unavailable (separate retained history).</p>'
        '<p class="secondary">Eligibility is not completion. WAIT is a completed abstention; '
        'NEUTRAL is a direction, not an extra result. Local SUPPORT is not K4/V2 acceptance. '
        'Global failure/staleness without per-security evidence is Unavailable, not zero.</p></section>')


def review_link(row, *, market=None):
    market = market or (row or {}).get('market')
    route = NSE_REVIEW if market == 'NSE' else MCX_REVIEW
    if row and row.get('eligible') and row.get('run_identity') and row.get('requirement_sha256'):
        route += '?' + urlencode({'run': row['run_identity'], 'candidate': row['requirement_sha256']})
        route += ('#nse-research-' if market == 'NSE' else '#review-candidate-') + row['requirement_sha256']
    return route


def render_compact_local(projection, candidate):
    if not candidate or candidate.get('market') != 'NSE':
        return '<span>Local research · Not applicable</span>'
    value = local_view(projection, candidate)
    result = value['result']
    if result is None:
        return ('<span>Independent local analysis · ' + escape(value['state'].replace('_', ' '))
            + '</span><small>No current local recommendation is established.</small>'
            + '<small>' + escape(str(value['reason'] or 'Unavailable')) + '</small>')
    overall = result['thesis']['overall']
    return ('<span>Independent Local · <strong>' + escape(overall['disposition'])
        + ' · ' + escape(overall['direction']) + '</strong></span><span>Conviction · '
        + escape(overall['conviction']) + '</span>')


def mcx_contract_projection(facts, run_identity):
    """Read exact existing lineage from the same prepared immutable MTF context."""
    from kronos.swing.v1.mtf_facts import SameRunMtfFactSnapshot
    if facts is None:
        return {}
    if type(facts) is not SameRunMtfFactSnapshot or facts.run_identity != run_identity:
        raise ValueError('SWING_REVIEW_CONTRACT_BINDING_INVALID')
    values = {}
    for instrument in facts.instruments:
        lineage = instrument.mcx_request_lineage
        if lineage is None:
            continue
        if lineage.run_identity != run_identity or lineage.family.value != instrument.canonical_instrument:
            raise ValueError('SWING_REVIEW_CONTRACT_BINDING_INVALID')
        values[instrument.canonical_instrument] = dict(trading_symbol=lineage.trading_symbol,
            expiry=lineage.expiry)
    return values


def scope_review(projection, market):
    """A render-only copy. The original remains the owner/final-fence authority."""
    if market not in {'NSE', 'MCX'}:
        raise ValueError('SWING_REVIEW_MARKET_INVALID')
    view = dict(projection)
    view['rows'] = tuple(r for r in projection.get('rows', ()) if r['market'] == market)
    view['packages'] = tuple(p for p in projection.get('packages', ()) if p['market'] == market)
    if market == 'MCX':
        view['local_analysis'] = None
        view['technical_summaries'] = ()
    workspace = projection.get('workspace')
    if workspace is not None:
        view['workspace'] = dict(workspace, population=len(view['rows']),
            eligible=sum(bool(r.get('eligible')) for r in view['rows']),
            excluded=sum(not r.get('eligible') for r in view['rows']),
            nse=sum(r.get('eligible', False) and r['market'] == 'NSE' for r in view['rows']),
            mcx=sum(r.get('eligible', False) and r['market'] == 'MCX' for r in view['rows']))
    return view


def scoped_bulk_status(status, projection):
    if status is None or status.get('unavailable'):
        return status
    packages = projection.get('packages', ())
    if any(status.get('review_pack_identity') == p.get('review_pack_identity')
           and status.get('request_identity') == p.get('request_identity') for p in packages):
        return status
    names = {r['instrument'] for r in projection.get('rows', ())}
    candidates = status.get('candidates', ())
    if candidates and all(r.get('canonical_instrument') in names for r in candidates):
        return status
    return None


def validate_focus(projection, run, candidate):
    if run is None and candidate is None:
        return None
    workspace = (projection or {}).get('workspace') or {}
    if run != workspace.get('run_identity'):
        raise ValueError('REVIEW_BINDING_STALE')
    matches = [row for row in projection.get('rows', ())
               if row.get('requirement_sha256') == candidate and row.get('run_identity') == run]
    if len(matches) != 1:
        raise ValueError('REVIEW_BINDING_STALE')
    return candidate


def render_nse_review(snapshot, projection, discovery=None, *, focus=None):
    from kronos.browser.views import _page, _nse_local_panel, _nse_technical_panel, _intake_error
    view = scope_review(projection or dict(rows=(), packages=(), error='REVIEW_BINDING_UNAVAILABLE'), 'NSE')
    body = ('<section class="swing-research-review"><h2>NSE Local Review</h2>'
        '<p>Independent local Python research · retained completed Kite/Native evidence · No model API. '
        'TradingView charts and Chart Analyst Answers are not prerequisites.</p>'
        '<p><a href="/swing/v1-review?market=NSE">Legacy NSE chart evidence and existing WO-07F workflow</a>'
        ' · <a href="/swing/research">Retained research history and original assessments</a></p>')
    body += render_stage_counts(view, discovery, nse_only=True)
    if view.get('error'):
        body += '<p role="alert">Review binding unavailable</p>' + _intake_error(view['error'])
    workspace = view.get('workspace') or {}
    body += '<p>Currentness · ' + escape(str(workspace.get('state') or 'UNAVAILABLE')) + '</p>'
    rows = view.get('rows', ())
    body += _controls()
    body += ('<div class="swing-research-table-region" tabindex="0" role="region" aria-label="NSE Local Review securities">'
        '<table class="swing-research-table"><thead><tr>' + ''.join('<th scope="col">' + label + '</th>' for label in (
            'Security', 'Native direction', 'Native status', 'Local conclusion', 'Local direction',
            'Conviction', 'Short horizon', 'Medium horizon', 'Longer horizon', 'Currentness', 'Details'))
        + '</tr></thead><tbody>')
    for index, row in enumerate(rows):
        value = local_view(view, row)
        result = value['result']
        overall = {} if result is None else result['thesis']['overall']
        horizons = {} if result is None else {r['identity']: r['direction'] for r in result['thesis']['horizons']}
        current = ('BINDING CURRENT' if row.get('expected') is not None and not view.get('error')
                   else 'BINDING STALE' if row.get('error') == 'REVIEW_BINDING_STALE' else 'UNAVAILABLE')
        status = 'PROBABLE · REVIEW ELIGIBLE' if row.get('eligible') else 'REVIEW INELIGIBLE'
        conclusion = overall.get('disposition', 'Unavailable')
        conviction = overall.get('conviction', 'UNAVAILABLE')
        data = dict(security=row['instrument'], direction=row.get('direction') or 'UNAVAILABLE',
            conclusion=conclusion, conviction=conviction, currentness=current, availability=value['state'])
        identity = row.get('requirement_sha256') or 'excluded-' + str(index)
        details_id = 'nse-research-' + identity
        fields = [row['instrument'], row.get('direction') or 'Unavailable', status, conclusion,
            overall.get('direction', 'Unavailable'), conviction, horizons.get('SHORT', 'Unavailable'),
            horizons.get('MEDIUM', 'Unavailable'), horizons.get('LONGER', 'Unavailable'), current]
        labels = ['Security', 'Native direction', 'Native status', 'Local conclusion', 'Local direction',
                  'Conviction', 'Short horizon', 'Medium horizon', 'Longer horizon', 'Currentness']
        body += ('<tr class="swing-research-row" data-research-row="'
            + escape(json.dumps(data, separators=(',', ':')), quote=True) + '">'
            + ''.join('<td data-label="' + label + '">' + escape(str(field)) + '</td>' for label, field in zip(labels, fields))
            + '<td data-label="Details"><a href="#' + escape(details_id, quote=True)
            + '" data-open-research="' + escape(details_id, quote=True) + '">View details</a></td></tr>')
        body += ('<tr class="swing-research-detail"><td colspan="11"><details data-security-detail name="swing-nse-security" id="'
            + escape(details_id, quote=True) + '"' + (' open' if focus == identity else '')
            + '><summary>' + escape(row['instrument']) + ' · full research and evidence</summary>')
        if result is None:
            body += '<p>No current Local recommendation. ' + escape(str(value['reason'] or value['state'])) + '</p>'
        if row.get('error'):
            body += _intake_error(row['error'])
        if row.get('eligible'):
            args = (view, row['instrument'], row.get('run_identity'), row.get('assessment_sha256'),
                    row.get('direction'), row.get('requirement_sha256'))
            # Existing renderers preserve complete numerical/scenario/provenance
            # semantics. They perform no engine evaluation or history access.
            body += _nse_local_panel(*args) + _nse_technical_panel(*args)
        body += '</details></td></tr>'
    body += '</tbody></table></div>'
    if not rows:
        body += '<p>No NSE Review candidates in this source population.</p>'
    body += ('<p data-research-empty hidden>No securities match these filters. Clear All restores the population.</p>'
        '<p class="secondary">Historical originals remain in Research; this table does not reconstruct history '
        'or certify K4/V2, entry, a fill or trading readiness.</p></section><script>' + CONTROLS_JS + '</script>')
    return _page(title='Swing — NSE Review', subtitle='Independent local research and complete retained evidence',
        snapshot=snapshot, active_nav='Swing', active_tab='NSE Review', body=body, extra_styles=RESEARCH_CSS)


def _controls():
    fields = '<label>Security search<input type="search" data-research-filter="security" autocomplete="off"></label>'
    for key, label in (('direction', 'Native direction'), ('conclusion', 'Local conclusion'),
                       ('conviction', 'Conviction'), ('currentness', 'Currentness'), ('availability', 'Research availability')):
        fields += '<label>' + label + '<select data-research-filter="' + key + '"><option value="">All</option></select></label>'
    return ('<fieldset class="swing-research-controls" hidden><legend>Find and compare research</legend>'
        '<div>' + fields + '<label>Sort<select data-research-filter="sort">'
        '<option value="original">Publication order</option><option value="security-asc">Security A–Z</option>'
        '<option value="security-desc">Security Z–A</option></select></label></div>'
        '<button type="button" data-research-clear>Clear All</button>'
        '<p role="status" aria-live="polite" data-research-count></p>'
        '<small>Local display only. Sorting is not a trading recommendation.</small></fieldset>'
        '<noscript>All retained rows and expandable evidence are readable. Filtering requires JavaScript.</noscript>')


CONTROLS_JS = r"""
function researchMatches(row, filters){
 return Object.entries(filters).every(([key,value])=>key==='sort'||!value||
  (key==='security'?row.security.toLowerCase().includes(value.toLowerCase()):row[key]===value));
}
function researchCompare(a,b,sort){
 const x=a.security.toLowerCase(),y=b.security.toLowerCase();
 return (sort==='original'?0:(x===y?0:x<y?-1:1)*(sort==='security-desc'?-1:1))||a.order-b.order;
}
if(typeof module!=='undefined'&&module.exports)module.exports={researchMatches,researchCompare};
if(typeof document!=='undefined')document.querySelectorAll('.swing-research-review').forEach(browser=>{
 const controls=browser.querySelector('.swing-research-controls');if(!controls)return;
 const rows=[...browser.querySelectorAll('[data-research-row]')].map((main,order)=>({main,
  detail:main.nextElementSibling,data:{...JSON.parse(main.dataset.researchRow),order}}));
 const fields=Object.fromEntries([...controls.querySelectorAll('[data-research-filter]')].map(e=>[e.dataset.researchFilter,e]));
 ['direction','conclusion','conviction','currentness','availability'].forEach(key=>{
  [...new Set(rows.map(row=>row.data[key]))].sort().forEach(value=>{
   const option=document.createElement('option');option.value=value;option.textContent=value.replaceAll('_',' ');fields[key].append(option);
  });
 });
 const details=[...browser.querySelectorAll('[data-security-detail]')];
 details.forEach(detail=>detail.addEventListener('toggle',()=>{if(detail.open)details.forEach(other=>{if(other!==detail)other.open=false;});}));
 browser.querySelectorAll('[data-open-research]').forEach(link=>link.addEventListener('click',()=>{
  const detail=document.getElementById(link.dataset.openResearch);if(detail){details.forEach(other=>{other.open=other===detail;});detail.querySelector('summary').focus();}
 }));
 function update(){
  const filters=Object.fromEntries(Object.entries(fields).map(([k,e])=>[k,e.value.trim()]));let visible=0;
  const fragment=document.createDocumentFragment();
  [...rows].sort((a,b)=>researchCompare(a.data,b.data,filters.sort)).forEach(row=>{
   const hidden=!researchMatches(row.data,filters);row.main.hidden=hidden;row.detail.hidden=hidden;
   if(hidden)row.detail.querySelector('[data-security-detail]').open=false;else visible++;
   fragment.append(row.main,row.detail);
  });
  browser.querySelector('tbody').append(fragment);
  controls.querySelector('[data-research-count]').textContent='Showing '+visible+' of '+rows.length+' NSE Review candidates';
  browser.querySelector('[data-research-empty]').hidden=visible!==0;
 }
 controls.addEventListener('input',update);controls.addEventListener('change',update);
 controls.querySelector('[data-research-clear]').addEventListener('click',()=>{
  Object.entries(fields).forEach(([k,e])=>{e.value=k==='sort'?'original':'';});update();
 });
 controls.hidden=false;update();
});
"""

RESEARCH_CSS = r"""
.swing-research-summary,.swing-research-review{min-width:0;max-width:100%;overflow-wrap:anywhere}
.swing-research-summary{margin:12px 0;padding:12px;border:1px solid var(--line);border-radius:8px}
.swing-research-counters{display:grid;grid-template-columns:repeat(auto-fit,minmax(105px,1fr));gap:8px}
.swing-research-counters>div{border:1px solid var(--line);border-radius:5px;padding:8px;min-width:0}
.swing-research-counters span{display:block;color:var(--muted);font-size:10px}.swing-research-counters strong{display:block;font-size:16px}
.swing-research-summary .secondary,.swing-research-review .secondary{font-size:11px;color:var(--muted)}
.swing-research-controls{border:1px solid var(--line);border-radius:6px;padding:12px;margin:12px 0}
.swing-research-controls>div{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:8px}
.swing-research-controls label{display:block;font-size:11px}.swing-research-controls input,.swing-research-controls select{box-sizing:border-box;width:100%;min-height:36px;background:#102b3d;color:var(--text);border:1px solid var(--line);border-radius:4px}
.swing-research-controls button{min-height:36px;margin-top:10px}.swing-research-table-region{max-width:100%;overflow-x:auto}
.swing-research-table{width:100%;border-collapse:collapse;font-size:11px;table-layout:fixed}
.swing-research-table td,.swing-research-table th{padding:8px 5px;text-align:left;vertical-align:top;border-bottom:1px solid var(--line);overflow-wrap:anywhere}
.swing-research-table th{font-size:10px;color:var(--muted)}.swing-research-detail>td{padding:0;border:0}
.swing-research-detail>td>details{padding:10px;border:1px solid var(--line);border-radius:6px;margin-bottom:8px}
.swing-research-detail summary{min-height:36px;cursor:pointer;overflow-wrap:anywhere}
.swing-research-review [hidden]{display:none!important}.swing-research-review a:focus-visible,.swing-research-review summary:focus-visible{outline:2px solid var(--green);outline-offset:2px}
.swing-compact-local{display:flex;gap:6px 14px;flex-wrap:wrap;font-size:11px;padding:7px 0}
.swing-compact-local span{overflow-wrap:anywhere}.native-opportunity .opp-head{margin-bottom:4px}
.native-opportunity .swing-review-readiness{margin-top:6px}.native-opportunity .native-opportunity-actions{display:flex;gap:8px;flex-wrap:wrap}
@media(max-width:760px){.swing-research-table,.swing-research-table tbody{display:block}.swing-research-table thead{display:none}
 .swing-research-row{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));border:1px solid var(--line);border-radius:5px;margin-top:8px}
 .swing-research-row td{display:block;min-width:0}.swing-research-row td:before{content:attr(data-label);display:block;font-size:10px;color:var(--muted)}
 .swing-research-detail,.swing-research-detail>td{display:block;width:100%;box-sizing:border-box}.swing-research-table-region{overflow-x:visible}
 .swing-research-controls>div{grid-template-columns:minmax(0,1fr)}.swing-research-counters{grid-template-columns:repeat(2,minmax(0,1fr))}}
"""

# Compact discovery rows use the existing cards/market partition, with all full
# numerical/visual details delegated to the dedicated Review surfaces.
RESEARCH_CSS += r"""
.swing-compact-dashboard .swing-opportunities-grid{grid-template-columns:minmax(0,1fr)}
.swing-compact-dashboard .swing-card-list{gap:6px}
.swing-compact-dashboard .native-opportunity{display:grid;grid-template-columns:minmax(135px,.8fr) minmax(220px,1.8fr) minmax(150px,1fr) minmax(130px,1fr);gap:8px 12px;align-items:start;padding:10px}
.swing-compact-dashboard .native-opportunity .opp-head{display:block;margin:0}.swing-compact-dashboard .native-opportunity .opp-head h3{font-size:15px;margin:0 0 4px}
.swing-compact-dashboard .native-opportunity .direction{display:inline-block;margin-top:5px}
.swing-compact-dashboard .swing-sponsor-summary{display:flex;gap:4px 10px;flex-wrap:wrap;font-size:10px;margin:0}
.swing-compact-dashboard .swing-sponsor-summary .swing-card-fact{display:inline-block;padding:0;border:0;background:none}
.swing-compact-dashboard .swing-governed-status,.swing-compact-dashboard .swing-pending-facts{width:100%;margin:0}
.swing-compact-dashboard .swing-pending-facts ul{margin:3px 0;padding-left:14px;font-size:10px}
.swing-compact-dashboard .swing-review-readiness{margin:0;display:block}.swing-compact-dashboard .swing-readiness-states{gap:3px;margin-bottom:6px}
.swing-compact-dashboard .swing-compact-local{padding:0;display:block}.swing-compact-dashboard .swing-compact-local>span,.swing-compact-dashboard .swing-compact-local>small{display:block;margin-bottom:4px}
.swing-compact-dashboard .native-opportunity>p,.swing-compact-dashboard .native-opportunity>.wo07-card-warning{grid-column:1/-1;margin:0;font-size:10px}
@media(max-width:1100px){.swing-compact-dashboard .native-opportunity{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:600px){.swing-compact-dashboard .native-opportunity{grid-template-columns:minmax(0,1fr)}}
"""
