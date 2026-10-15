"""Theta-local Swing-style chart controls; no Swing analytical semantics."""

from html import escape
from urllib.parse import urlencode

REFERENCES = {"GOLDM": "COMEX Gold", "SILVERM": "COMEX Silver", "COPPER": "COMEX Copper",
              "CRUDEOIL": "NYMEX Light Crude", "NATURALGAS": "NYMEX Natural Gas"}
CHART_STYLES = """
.theta-chart-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(285px,1fr));gap:14px}
.theta-chart-card{border:1px solid var(--line);background:var(--panel);border-radius:10px;padding:15px;min-width:0}
.theta-chart-card h3{margin:0;color:var(--blue);font-size:18px}.theta-chart-heading{display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap}
.theta-chart-state{font-size:11px;font-weight:800;color:var(--muted)}.theta-chart-card[data-ready="true"] .theta-chart-state{color:var(--green)}
.theta-chart-guide{font-size:12px;color:var(--muted);line-height:1.7;margin:12px 0}.theta-chart-preview{display:block;margin-bottom:12px}
.theta-chart-preview img{display:block;width:100%;height:auto;max-height:220px;object-fit:contain;background:#020b14;border:1px solid var(--line);border-radius:6px}
.theta-chart-metadata{font-size:10px;color:var(--muted);overflow-wrap:anywhere;margin-top:9px}.theta-chart-metadata summary{cursor:pointer}
.theta-chart-card .chart-paste-target{min-height:88px}.theta-chart-card .chart-paste-target strong,.theta-chart-card .chart-paste-target span{display:block}
.theta-chart-card .chart-paste-target span{color:var(--muted);font-size:11px;margin-top:5px}.theta-chart-question{font-size:11px;margin-top:12px;border-top:1px solid var(--line);padding-top:10px}
.theta-chart-card .chart-paste-target.received{grid-template-columns:1fr}
.theta-chart-counts{display:flex;gap:18px;flex-wrap:wrap;font-size:12px;margin:12px 0}.theta-macro-card{margin-top:14px}
"""


def chart_controls(workspace, rows, workflow_status=None):
    cards = workspace['cards']
    selected = None if workflow_status is None else workflow_status.get('selected_question_pack')
    v3_current = bool(selected is not None and selected['current'])
    current_packs = (len(selected['currentness']) if v3_current else
        sum(row['status'] in {'ANSWER_PENDING', 'ACCEPTED_EXTERNAL_EVIDENCE'} for row in rows))
    imported = None if workflow_status is None else workflow_status.get('import_operation')
    imported_result = None if imported is None else imported['result']['intake']
    v3_import_current = bool(v3_current and imported_result is not None
        and imported_result['question_batch_id'] == selected['batch_id'])
    accepted = (sum(row['receipt_id'] is not None and row['currentness'] == 'CURRENT'
                    for row in imported_result['children'].values()) if v3_import_current else
        sum(row['status'] == 'ACCEPTED_EXTERNAL_EVIDENCE' for row in rows))
    ready = sum(card['chart'] is not None for card in cards[:-1])
    macro = 'READY' if cards[-1]['chart'] is not None else 'MISSING'
    body = ('<section class="theta-panel"><h2>TradingView chart intake</h2>'
        '<p class="theta-muted">Copy one composite, click its commodity card, then press Cmd+V / Ctrl+V. '
        'The focused card is your subject attestation; KRONOS does not infer identities from pixels. '
        'PNG / JPEG only · exact originals · 16 MiB maximum.</p>'
        f'<div class="theta-chart-counts"><span>COMMODITY CHARTS READY: {ready} / 5</span>'
        f'<span>GLOBAL MACRO: {macro}</span><span title="Current retained Question packs">QUESTION PACKS: {current_packs} / 5</span>'
        f'<span>ANSWERS ACCEPTED: {accepted} / 5</span></div>'
        '<p class="theta-muted">Macro is supporting context. Chart acceptance time is not verified chart time. '
        'Question counts reflect current retained packs.</p>'
        '<p id="theta-chart-refresh" hidden>Chart selection changed. <a href="/theta-earners/new-analysis">Refresh retained charts and current Question state</a>.</p>'
        '<div class="theta-chart-grid">')
    by_subject = {row['subject']: row for row in rows}
    for card in cards[:-1]:
        body += chart_card(card, by_subject[card['subject']], v3_current=v3_current)
    return body + '</div>' + chart_card(cards[-1], None, v3_current=v3_current) + '</section>' + chart_script()


def chart_card(card, row, *, v3_current=False):
    subject, chart, intake = card['subject'], card['chart'], card['intake']
    macro = subject == 'GLOBAL_MACRO'
    title = 'GLOBAL MACRO CONTEXT' if macro else subject
    state = ('MACRO CHART READY' if chart else 'MACRO CHART MISSING') if macro else ('CHART READY' if chart else 'CHART MISSING')
    target = 'theta-chart-' + subject
    cycle = card['cycle_id'] or 'UNSTARTED'
    query = {'subject': subject, 'cycle': cycle, 'revision': card['revision_id'] or 'MISSING'}
    url = '/theta-earners/chart?' + urlencode(query)
    body = (f'<article class="theta-chart-card{" theta-macro-card" if macro else ""}" data-ready="{str(chart is not None).lower()}">'
        f'<div class="theta-chart-heading"><h3>{title}</h3><strong class="theta-chart-state">{state}</strong></div>')
    if macro:
        body += ('<p class="theta-chart-guide">ONE SHARED TRADINGVIEW COMPOSITE · SUPPORTING EVIDENCE, NOT A FORECAST SUBJECT<br>'
            'DXY · US 10Y · US 30Y · USD/INR · Nasdaq-100 · USD/CNH · CSI 300 · Dow Jones</p>')
    else:
        body += (f'<p class="theta-chart-guide">TRADINGVIEW COMPOSITE · ONE IMAGE<br>Reference: {REFERENCES[subject]} · 1D | 4H | 1H<br>'
            'MCX: 1D | 4H | 1H</p>')
    if chart:
        preview = escape('/theta-earners/chart-preview?' + urlencode(query), quote=True)
        body += (f'<a class="theta-chart-preview" href="{preview}" target="_blank" rel="noopener" aria-label="Open exact original {title}">'
            f'<img loading="lazy" src="{preview}" alt="Exact retained {title} composite"><span>Open exact original</span></a>')
    body += (f'<div id="{target}" class="chart-paste-target{" received" if chart else ""}" role="button" tabindex="0" '
        f'aria-label="Paste {title} TradingView composite" data-upload-url="{escape(url,quote=True)}" '
        f'data-subject="{subject}" data-cycle="{cycle}" data-revision="{card["revision_id"] or "MISSING"}" '
        f'data-chart-accepted="{str(chart is not None).lower()}">'
        '<div><strong>PASTE TRADINGVIEW CHART</strong><span>Cmd+V / Ctrl+V · Click, then paste</span></div></div>'
        f'<p id="{target}-feedback" role="status" aria-live="polite" hidden></p><div class="chart-slot-actions">')
    if chart:
        body += f'<button class="theta-replace-chart" type="button" data-target="{target}">Replace Chart</button>'
    body += (f'<label class="file-choice" for="{target}-file">Choose File</label><input id="{target}-file" '
        f'class="theta-chart-file chart-file" type="file" accept="image/png,image/jpeg" data-target="{target}"></div>')
    if chart:
        values = {'Cycle': intake['cycle_id'] if intake else 'NOT_ESTABLISHED — legacy record',
            'Role': intake['role'] if intake else 'NOT_ESTABLISHED — legacy record',
            'Revision': card['revision_id'], 'Accepted': intake['accepted_at'] if intake else 'NOT_ESTABLISHED',
            'Media type': chart['media_type'], 'Original bytes': intake['byte_length'] if intake else 'NOT_ESTABLISHED',
            'SHA-256': chart['sha256'], 'Time basis': intake['cutoff_basis'] if intake else 'SPONSOR_DECLARED'}
        body += '<details class="theta-chart-metadata"><summary>Accepted chart identity and integrity</summary>'
        body += ''.join('<p>'+escape(name)+': '+escape(str(value))+'</p>' for name,value in values.items()) + '</details>'
    if macro:
        question_state = 'SUPPORTING CONTEXT · no sixth forecast / required for TE-02 Question packs'
    elif not chart:
        question_state = 'QUESTION PACK · NOT READY'
    elif v3_current or row['status'] in {'ANSWER_PENDING', 'ACCEPTED_EXTERNAL_EVIDENCE'}:
        question_state = 'QUESTION PACK · CURRENT PACK RETAINED'
    else:
        question_state = 'QUESTION PACK · NOT CURRENT / target and methodology checks remain required'
    return body + '<div class="theta-chart-question">'+escape(question_state)+'</div></article>'


def chart_script():
    return r'''<script>
(()=>{
const types=new Set(['image/png','image/jpeg']),maximum=16777216;
let queue=Promise.resolve(),pending=0,accepted=0,hadFailure=false,reloadTimer=null;
function report(target,reason){const feedback=document.getElementById(target.id+'-feedback');
 if(feedback){feedback.hidden=false;feedback.textContent=reason;}}
function receive(target,file){
 if(target.getAttribute('aria-busy')==='true'){report(target,'UPLOAD_ALREADY_PENDING');return;}
 if(target.dataset.chartAccepted==='true'){report(target,'CHART_ALREADY_CURRENT · Click Replace Chart first.');return;}
 if(!file||!types.has(file.type)){report(target,'UNSUPPORTED_IMAGE_TYPE · PNG / JPEG only.');return;}
 if(file.size<=0||file.size>maximum){report(target,'IMAGE_TOO_LARGE_OR_EMPTY');return;}
 target.setAttribute('aria-busy','true');report(target,'PROCESSING');pending++;
 if(reloadTimer!==null){clearTimeout(reloadTimer);reloadTimer=null;}
 queue=queue.then(async()=>{
  try{
   const response=await fetch(target.dataset.uploadUrl,{method:'POST',headers:{'Content-Type':file.type,'Accept':'application/json'},body:file});
   const result=await response.json();
   if(!response.ok||result.outcome!=='CHART_RECEIVED'||!result.revision_id||!result.sha256){
    hadFailure=true;report(target,result.failure==='THETA_CHART_BINDING_STALE'?'BINDING STALE · Refresh before retrying.':'CHART_REJECTED · No accepted evidence replaced.');return;}
   for(const other of document.querySelectorAll('.theta-chart-card .chart-paste-target')){
    if(other.dataset.cycle==='UNSTARTED'){
     other.dataset.cycle=result.cycle_id;
     const url=new URL(other.dataset.uploadUrl,location.href);url.searchParams.set('cycle',result.cycle_id);other.dataset.uploadUrl=url.pathname+url.search;}}
   target.dataset.revision=result.revision_id;target.dataset.chartAccepted='true';accepted++;
   const url=new URL(target.dataset.uploadUrl,location.href);url.searchParams.set('revision',result.revision_id);target.dataset.uploadUrl=url.pathname+url.search;
   const card=target.closest('.theta-chart-card');if(card){card.dataset.ready='true';
    const state=card.querySelector('.theta-chart-state');if(state)state.textContent=target.dataset.subject==='GLOBAL_MACRO'?'MACRO CHART READY':'CHART READY';
    const readiness=card.querySelector('.theta-chart-question');if(readiness&&target.dataset.subject!=='GLOBAL_MACRO')readiness.textContent='QUESTION PACK · NOT CURRENT';}
   report(target,'CHART READY · Exact original retained.');
   const refresh=document.getElementById('theta-chart-refresh');if(refresh)refresh.hidden=false;
   for(const section of document.querySelectorAll('[data-theta-forecast],[data-theta-manual]'))section.hidden=true;
  }catch(_){hadFailure=true;report(target,'CHART_INTAKE_UNAVAILABLE · Refresh to verify retained state.');}
  finally{target.removeAttribute('aria-busy');pending--;if(pending===0&&accepted>0&&!hadFailure)reloadTimer=setTimeout(()=>location.reload(),900);}
 });
}
for(const target of document.querySelectorAll('.theta-chart-card .chart-paste-target')){
 target.addEventListener('click',()=>target.focus());
 target.addEventListener('paste',event=>{
  const items=event.clipboardData&&Array.from(event.clipboardData.items||[]);
  const image=items&&items.find(item=>item.kind==='file'&&types.has(item.type));
  if(!image){report(target,'NO_IMAGE_IN_CLIPBOARD · Copy a PNG / JPEG TradingView image.');return;}
  event.preventDefault();receive(target,image.getAsFile());});
}
for(const input of document.querySelectorAll('.theta-chart-file'))input.addEventListener('change',()=>{
 const target=document.getElementById(input.dataset.target);if(target)receive(target,input.files&&input.files[0]);input.value='';});
for(const button of document.querySelectorAll('.theta-replace-chart'))button.addEventListener('click',()=>{
 const target=document.getElementById(button.dataset.target);if(target&&target.getAttribute('aria-busy')!=='true'){
  target.dataset.chartAccepted='false';target.classList.add('replace-ready');target.focus();report(target,'REPLACE CHART · Paste or choose file; original stays retained.');}});
addEventListener('pageshow',()=>document.querySelectorAll('.theta-chart-card .chart-paste-target[aria-busy="true"]').forEach(target=>target.removeAttribute('aria-busy')));
})();
</script>'''
