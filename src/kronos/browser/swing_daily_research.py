"""Pure LOCAL-03 research/Journey presentation; no owner calls or writes."""
from html import escape
from urllib.parse import urlencode


def render_daily_research(daily, observations):
    e=lambda x:escape(str(x))
    status=daily or {'state':'UNAVAILABLE','publications':[]}
    body=('<style>.local-journey{min-width:0;overflow-wrap:anywhere}.local-journey code{white-space:normal;word-break:break-word}'
          '.local-journey-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}'
          '.local-journey article{min-width:0;padding:12px;border:1px solid var(--line);border-radius:8px}'
          '.local-journey button{white-space:normal;min-height:40px}.local-journey dl{display:grid;grid-template-columns:1fr 1fr;gap:4px}'
          '.local-journey dd{margin:0;overflow-wrap:anywhere}@media(max-width:600px){.local-journey-grid{grid-template-columns:1fr}}</style>'
          '<section class="panel local-journey"><h2>Today’s retained research</h2>'
          '<p>Record retained evidence only. No market acquisition, Native analysis, model inference or historical UPDATE.</p>'
          '<p>Automatic recording · 23:00 Asia/Kolkata while KRONOS is READY. Missed dates catch up from retained evidence. '
          'A manual early BASE is supplemented when later evidence is recorded.</p>'
          '<p>Recorder · '+e(status['state'])+'</p>')
    if status.get('failure'):body+='<p role="alert">'+e(status['failure'])+'</p>'
    if status.get('last_attempt'):body+='<p>Last recording attempt · '+e(status['last_attempt'].get('state','Unavailable'))+'</p>'
    body+='<h3>Immutable daily publications and Excel</h3>'
    pubs=sorted(status.get('publications',()),key=lambda r:(r['reporting_date'],r['sequence']),reverse=True)
    if not pubs:body+='<p>No daily publication retained. Missing evidence is not a completed recording.</p>'
    for r in pubs:
        body+='<p>'+e(r['reporting_date'])+' · '+e(r['publication_kind'])+' '+e(r['sequence'])+' · '+e(r['coverage'])+' · <a href="/swing/research?'+urlencode({'download':r['identity']})+'">Open retained WO-12 Excel</a><br><code>'+e(r['identity'])+'</code></p>'
    body+='<h2>Opportunity Journey — original Local research</h2><p>Secondary Review and later research observations. '
    body+='Current source binding is separate from live market, Review/V2 or trading authority.</p><div class="local-journey-grid">'
    if not observations:body+='<p>Local assessments unavailable. No opinion is manufactured.</p>'
    for r in observations:
        t=r['thesis'];o=t['overall']
        body+='<article><h3>'+e(r['instrument'])+'</h3><p>Native '+e(r['native_direction'])+' → Local '+e(o['disposition'])+' · '+e(o['direction'])+'</p><p>'+e(r['currentness'])+'</p>'
        body+='<p>Original conviction · '+e(o['conviction'])+' · qualitative, not a probability.<br>'+e(o['reason'])+'</p><p>Method · <code>'+e(r['method_version'])+'</code><br>Assessment captured · '+e(r['captured_at'])+'<br>Evidence cutoff · '+e(r['evidence_cutoff'])+'</p>'
        body+='<p>Original · <code>'+e(r['original_identity'])+'</code><br>Run · <code>'+e(r['run_identity'])+'</code><br>Publication · <code>'+e(r['publication_sha256'])+'</code></p>'
        body+='<p>Owner Opportunity Journey · '+e(r['opportunity_identity'] or 'UNRESOLVED — no exact retained origin link')+'</p>'
        for event in r['journey_events']:
            body+='<p>'+e(event['schema'])+' · '+e(event['event_at'] or 'Unknown event time')+' · '+e(event['state'] or 'Unavailable')+'</p>'
        body+='<details><summary>Three horizons and original reasoning</summary>'
        for h in t['horizons']:body+='<p>'+e(h['identity'])+' · '+e(h['direction'])+' · '+e(h['reason'])+'</p>'
        for k in ('supporting_domains','opposing_domains'):
            body+='<p>'+e(k.replace('_',' '))+' · '+e('; '.join(x['timeframe']+' '+x['domain'] for x in o[k]) or 'None established')+'</p>'
        body+='</details><details><summary>Conditional scenarios, missing evidence and risks</summary>'
        for s in t['scenarios']:
            body+='<p>'+e(s['horizon'])+' · '+e(s['kind'])+' · '+e(s['direction'])+' · '+e(s['state'])+'<br>'+e(s['reason'])
            if s['state']=='AVAILABLE':
                body+='<br>Entry '+e(s['entry_zone']['low'])+' – '+e(s['entry_zone']['high'])+' · Invalidation '+e(s['stop_reference']['value'])+' · Target '+e(s['target_zone']['low'])+' – '+e(s['target_zone']['high'])+' · Reward/risk '+e(s['risk_reward']['conservative_ratio'])
            else:body+='<br>Entry / invalidation / target / reward-risk: Unavailable'
            body+='</p>'
        body+='<p>'+e('; '.join(t['limitations']))+'</p></details><p>Q3/Q5/Q10 UNKNOWN. Research only; no position or execution authority.</p></article>'
    return body+'</div>'+render_local_outcomes(observations)+'</section>'


def render_local_outcomes(observations):
    """Measured samples and uncertainties, never inferred PAPER executions."""
    from kronos.swing.v1.local_research_outcomes import aggregate, scenario_counts
    e = lambda value: escape(str(value))
    outcomes = [r['outcomes'] for r in observations if r.get('outcomes') is not None]
    body = '<h2>Local research outcomes — retained evidence</h2><p>Matched Native/Local observations, not independent security samples. '
    body += 'Only completed governed sessions after the original assessment date count. Twenty-session research is additive; legacy WO-12 1/3/5/10 remains unchanged. '
    body += 'Level touches are not fills. Candle excursions are not position MFE/MAE. Win probability unavailable.</p>'
    if not outcomes:
        return body + '<p>No observable original at this evidence cut. Outcomes unavailable.</p>'
    body += '<details><summary>Sample sizes, coverage and directional outcomes</summary><div class="local-journey-grid">'
    for g in aggregate(outcomes):
        body += '<article><h3>'+e(g['horizon_sessions'])+' sessions · '+e(g['cohort'])+'</h3><p>'
        body += 'Originals '+e(g['observations'])+' · distinct instruments '+e(g['distinct_instruments'])+'<br>'
        body += 'Observed '+e(g['observed'])+' · pending '+e(g['pending'])+' · unavailable '+e(g['unavailable'])+' · abstained '+e(g['abstained'])+'<br>'
        body += 'Method '+e(g['method_version'])+'<br>With direction '+e(g['with_direction'])+' · against '+e(g['against_direction'])+' · unchanged '+e(g['unchanged'])+'<br>Native disagreements '+e(g['native_disagreements'])+' · observed rejected-Native positives '+e(g['observed_missed_native'])+'</p></article>'
    body += '</div></details><details><summary>Scenario samples by horizon and setup</summary>'
    for g in scenario_counts(outcomes):
        body += '<p>'+e(g['horizon'])+' · '+e(g['setup'])+' · '+e(g['direction'])+' · radius '+e(g['structural_radius'])+' · '+e(g['method_version'])+'<br>'
        body += 'Samples '+e(g['observations'])+' · observed '+e(g['observed'])+' · pending '+e(g['pending'])+' · unavailable '+e(g['unavailable'])+'<br>'
        body += 'Ambiguous '+e(g['ambiguous'])+' · entry not reached '+e(g['entry_not_reached'])+' · entry only '+e(g['entry_touch_only'])+' · target touches '+e(g['target_touch'])+' · invalidation touches '+e(g['invalidation_touch'])+'</p>'
    body += '</details>'
    for r in observations:
        o = r.get('outcomes')
        if o is None: continue
        body += '<details><summary>'+e(o['instrument'])+' · original '+e(o['original_identity'])+' · measured outcomes</summary>'
        body += '<p>Signal clock '+e(o['signal_at'])+' · retained reference close '+e(o['reference_price'])+' at '+e(o['reference_observed_at'])+'<br>Measurement '+e(o['contract'])+' · <code>'+e(o['identity'])+'</code></p>'
        for d in o['direction']:
            body += '<p>'+e(d['horizon_sessions'])+' sessions · '+e(d['cohort'])+' · '+e(d['direction'])+' · '+e(d['status'])
            if d['direction_adjusted_pct'] is not None:
                body += '<br>Direction-adjusted '+e(d['direction_adjusted_pct'])+'% · candle MFE '+e(d['candle_mfe_pct'])+'% · candle MAE '+e(d['candle_mae_pct'])+'%'
            else: body += '<br>Directional return / excursions: Unavailable · '+e(d['reason'] or 'No directional conclusion')
            body += '</p>'
        body += '<details><summary>Scenario entry windows and level touches</summary>'
        for s in o['scenarios']:
            body += '<p>'+e(s['horizon'])+' · '+e(s['kind'])+' · '+e(s['direction'])+' · radius '+e(s['structural_radius'])+' · '+e(s['status'])+'<br>'+e(s['reason'])
            body += '<br>Entry window '+e(s['entry_window_sessions'])+' sessions · theoretical reward/risk '+e(s['theoretical_rr'] if s['theoretical_rr'] is not None else 'Unavailable')+' · realized reward/risk and P&amp;L: Unavailable</p>'
        body += '</details><p>Unscanned opportunities cannot be measured. Rejected Local ideas remain in the matched cohort; positive Native outcomes are observable missed-opportunity evidence, not hindsight trades.</p>'
        body += '<h4>Factual lifecycle evidence from the existing owner</h4>'
        if not r.get('factual_tracks'): body += '<p>No linked factual PAPER position outcome retained. No position or fill is inferred.</p>'
        for t in r.get('factual_tracks', ()):
            body += '<p>'+e(t['truth_class'])+' · '+e(t['state'])+' · '+e(t['observed_at'])+'<br>Owner event '+e(t['source_event_identity'])+' · entry '+e(t.get('entry_price') or 'Unavailable')+' · exit '+e(t.get('exit_price') or 'Unavailable')+' · source gross P&amp;L '+e(t.get('gross_pnl') if t.get('gross_pnl') is not None else 'Unavailable')+'</p>'
        body += '</details>'
    return body
