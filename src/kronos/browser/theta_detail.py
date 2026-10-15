"""TE-07 pure presentation of exact retained V3 Astra/TE-05C evidence.

No acquisition, evaluation, persistence, source fetch or prose interpretation.
"""
from html import escape
import ipaddress
import re
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit
from zoneinfo import ZoneInfo

from kronos.browser.theta_theme import commodity_symbol
from kronos.theta.contracts import stamp


DETAIL_STYLES = """
.theta-detail-view{min-width:0}.theta-detail-view p{white-space:pre-wrap}
.theta-detail-view .theta-detail-header h2{display:flex;align-items:center;gap:12px}
.theta-detail-view .theta-detail-header .theta-id{font-size:10px;margin:6px 0}
.theta-detail-view .theta-horizons{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
.theta-detail-view .theta-horizons .theta-panel{margin:0;padding:20px}
.theta-detail-view .theta-range{font-size:clamp(24px,2vw,31px);color:#eee8f6;line-height:1.5;overflow-wrap:anywhere;white-space:normal}
.theta-detail-view .theta-confidence{border:0;background:none;color:#d8d1e9;font-size:16px;padding:0;border-radius:0}
.theta-detail-view .theta-kicker{font-size:10px;letter-spacing:.08em;color:#a99bbe;margin-bottom:9px}
.theta-detail-view dl{display:grid;grid-template-columns:minmax(130px,1fr) minmax(0,2.5fr);gap:8px 16px;font-size:12px;margin:14px 0}
.theta-detail-view dt{color:#99a7ba}.theta-detail-view dd{margin:0;white-space:pre-wrap;overflow-wrap:anywhere}
.theta-detail-view details{margin-top:14px;border-top:1px solid #353146;padding-top:12px}
.theta-detail-view summary{cursor:pointer;color:#d4cae5;font-weight:600;font-size:13px;line-height:1.6}
.theta-detail-view h3{font-size:15px;color:#d9cee9;margin:16px 0 9px}
.theta-detail-view .theta-record{border-left:2px solid #4b405e;padding:4px 0 4px 15px;margin:18px 0;scroll-margin-top:30px}
.theta-detail-view .theta-record h4{font-size:13px;line-height:1.6;margin:0 0 5px;color:#d6cbe7}
.theta-detail-view .theta-record p{font-size:13px;margin:7px 0;line-height:1.7}
.theta-detail-view .theta-applicability{font-size:10px;color:#9eaac0;margin:4px 0}
.theta-detail-view .theta-reference-list{font-size:11px;color:#a1aec1;line-height:1.8;overflow-wrap:anywhere}
.theta-detail-view a{color:#bdb0df;text-underline-offset:3px}
.theta-detail-view .theta-criteria{width:100%;border-collapse:collapse;font-size:12px;margin-top:14px}
.theta-detail-view .theta-criteria td,.theta-detail-view .theta-criteria th{padding:10px 8px;border-bottom:1px solid #303043;vertical-align:top;text-align:left;overflow-wrap:anywhere}
.theta-detail-view .theta-criteria th{font-size:10px;color:#a1aec1}.theta-detail-view .theta-criteria td:first-child{width:29%}
.theta-detail-view .theta-criteria td:nth-child(2){width:18%;font-size:10px;letter-spacing:.02em;color:#b9abce}
.theta-detail-view .theta-criteria details{border:0;padding:0;margin-top:7px}.theta-detail-view .theta-criteria summary{font-size:10px;color:#99a7ba;font-weight:400}
.theta-detail-view .theta-detail-charts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
.theta-detail-view .theta-detail-charts img{display:block;width:100%;height:auto;object-fit:contain;margin:12px 0;border:1px solid #413953;border-radius:5px}
.theta-detail-view .theta-state{color:#b9abce;font-size:12px;letter-spacing:.06em}.theta-detail-view .theta-original-action{display:inline-block;margin-top:8px}
.theta-detail-view .theta-detail-nav{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;margin:18px 0}
.theta-detail-view [id]{scroll-margin-top:25px}
@media(max-width:1050px){.theta-detail-view .theta-horizons,.theta-detail-view .theta-detail-charts{grid-template-columns:minmax(0,1fr)}}
@media(max-width:760px){.theta-detail-view dl{grid-template-columns:minmax(0,1fr);gap:4px}.theta-detail-view dd{margin-bottom:8px}.theta-detail-view .theta-criteria thead{display:none}.theta-detail-view .theta-criteria tr{display:grid;grid-template-columns:minmax(0,1fr);padding:12px 0;border-bottom:1px solid #303043}.theta-detail-view .theta-criteria td{width:auto!important;border:0;padding:5px 0}}
"""

CRITERION_LABELS = {
    "C1": "Identity, provenance and references", "C2": "Horizon-specific rationale",
    "C3": "Supportive and opposing research", "C4": "Assumptions and limitations",
    "C5": "T0 and source chronology", "C6": "Chart/fundamental reconciliation",
    "C7": "Scheduled-event treatment", "C8": "Confidence justification and path risk",
    "C9": "Declared unresolved contradictions",
}
REASON_TEXT = {
    "C1_LINKS_DOCUMENTED": "Required material claim and source connections are documented.",
    "C1_MATERIAL_CONNECTION_GAP": "Required material claim/source connections are not established.",
    "C2_RATIONALE_DOCUMENTED": "Required horizon rationale and research links are documented.",
    "C2_RATIONALE_COVERAGE_GAP": "Required rationale or research coverage links are not established.",
    "C3_PERSPECTIVES_DOCUMENTED": "Recorded support, opposition and counterevidence links are documented.",
    "C3_PERSPECTIVE_TREATMENT_GAP": "Required support/opposition or counterevidence treatment is not established.",
    "C4_DECLARATIONS_DOCUMENTED": "Required assumptions and limitations treatment is documented.",
    "C4_DECLARATION_TREATMENT_GAP": "Required assumptions/limitations treatment is not established.",
    "C5_ACCEPTED_CHRONOLOGY_DOCUMENTED": "The retained accepted graph documents the required chronology.",
    "C6_RECONCILIATION_DOCUMENTED": "Required chart/research reconciliation links are documented.",
    "C6_RECONCILIATION_GAP": "Required chart/research reconciliation links are not established.",
    "C7_EVENTS_DOCUMENTED": "Required treatment of the declared events is documented.",
    "C7_EVENT_TREATMENT_GAP": "Required declared-event treatment or review completion is not established.",
    "C8_EXPLANATIONS_DOCUMENTED": "Required confidence justification and path-risk links are documented.",
    "C8_EXPLANATION_LINK_GAP": "Required confidence/path-risk evidence links are not established.",
    "C9_NO_DECLARED_UNRESOLVED_CONTRADICTION": "The inspectable retained relationships declare no applicable unresolved contradiction.",
    "C9_DECLARED_UNRESOLVED_CONTRADICTION": "A retained applicable relationship declares an unresolved contradiction.",
    "C9_RELATIONSHIP_RECORD_GAP": "Required relationship documentation is not established.",
    "POLICY_NOT_ADMITTED": "The exact governed assessment policy could not be admitted.",
}
SECTIONS = {
    "chart_assessment": "CHART ASSESSMENT", "reference_mcx_assessment": "REFERENCE MARKET vs MCX",
    "commodity_research": "COMMODITY RESEARCH", "macro_fundamental_research": "MACRO / FUNDAMENTAL RESEARCH",
    "bullish_evidence": "BULLISH EVIDENCE", "bearish_evidence": "BEARISH EVIDENCE",
    "counterevidence": "COUNTEREVIDENCE", "reconciliation": "RECONCILIATION", "uncertainty": "UNCERTAINTY",
}
KINDS = {"evidence_ids": "evidence", "source_ids": "source", "observation_ids": "observation",
         "relation_ids": "relation", "event_ids": "event", "assumption_ids": "assumption",
         "limitation_ids": "limitation"}


def e(value):
    return escape(str(value), quote=True)


def public_url(value):
    """Conservative presentation-only external-link admission; no DNS/network."""
    if not isinstance(value, str) or any(ord(c) < 33 for c in value) or '\\' in value:
        return None
    try:
        parts = urlsplit(value)
        host = (parts.hostname or '').lower().rstrip('.')
        port = parts.port
        if (parts.scheme not in {"http", "https"} or parts.username is not None
                or parts.password is not None or not host or '%' in host
                or host == 'localhost' or host.endswith(('.localhost', '.local', '.internal', '.lan', '.home', '.test', '.invalid'))):
            return None
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if '.' not in host or host.replace('.', '').isdigit() or host.startswith('0x'):
                return None
        else:
            if not address.is_global:
                return None
        for key, query_value in parse_qsl(parts.query):
            key = key.casefold().replace('-', '').replace('_', '')
            if key in {'key', 'auth', 'code'} or any(word in key for word in ('token', 'secret', 'password', 'session', 'cookie', 'signature', 'apikey', 'authorization', 'credential')):
                return None
            if re.search(r'file:|localhost|(?:^|[/])(?:Users|private|internal)(?:/|$)', query_value, re.I):
                return None
        if re.search(r'(?:^|[/#])(?:private|internal|credentials|\.ssh|\.aws)(?:[/#]|$)', unquote(parts.path + '#' + parts.fragment), re.I):
            return None
    except ValueError:
        return None
    return value


def locator(value):
    if value is None:
        return 'NOT_ESTABLISHED'
    url = public_url(value)
    if url is not None:
        return f'<a href="{e(url)}" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer">{e(value)}</a>'
    if re.fullmatch(r'[A-Za-z][A-Za-z0-9_.:-]{0,99}', value) and not re.search(
            r'(?:^|[_.:-])(?:PRIVATE|INTERNAL|LOCAL|TOKEN|SECRET|ACCOUNT|PROVIDER|KITE|SESSION)(?:$|[_.:-])', value, re.I):
        return e(value)
    return 'Public locator unavailable — private or unsafe locator withheld'


def anchor(kind, identity):
    return 'theta-' + kind + '-' + identity


def refs(kind, values):
    if not values:
        return '<span class="theta-muted">NO DOCUMENTED REFERENCES</span>'
    return ', '.join(f'<a href="#{quote(anchor(kind, identity), safe="")}">{e(identity)}</a>' for identity in values)


def typed_refs(values):
    return ' · '.join(e(ref['kind']) + ': ' + refs('horizon' if ref['kind'] == 'FORECAST'
                      else ref['kind'].lower(), [ref['identity']]) for ref in values) or 'NO DOCUMENTED REFERENCES'


def dt(value):
    if value is None:
        return 'NOT_ESTABLISHED'
    local = stamp(value).astimezone(ZoneInfo('Asia/Kolkata'))
    return f'<time datetime="{e(value)}" title="{e(value)}">{local.strftime("%d %b %Y · %I:%M:%S %p")} IST</time>'


def fields(values):
    return '<dl>' + ''.join(f'<dt>{e(label)}</dt><dd>{value}</dd>' for label, value in values) + '</dl>'


def applicable(values, horizon):
    return [v for v in values if horizon in v['horizons']]


def item(kind, identity, title, body, horizons=None):
    scope = '' if horizons is None else '<div class="theta-applicability">APPLIES TO: ' + e(' · '.join(horizons)) + '</div>'
    return f'<article class="theta-record" id="{e(anchor(kind, identity))}"><h4>{e(title)}</h4>{scope}{body}</article>'


def disclosure(title, body, *, identity=None, opened=False):
    return (f'<details{(" id=" + chr(34) + e(identity) + chr(34)) if identity else ""}{" open" if opened else ""}>'
            f'<summary>{e(title)}</summary>{body}</details>')


def assessment_panel(record, horizon):
    if record is None:
        return ('<p class="theta-state">NOT_EVALUABLE</p><p class="theta-muted">RETAINED ASSESSMENT NOT EVALUABLE. '
                'No integrity-valid retained C1–C9 record is available. The accepted Astra forecast remains intact.</p>')
    result = record['horizons'][horizon]
    body = f'<p class="theta-state">{e(result["result"])}</p>'
    rows = ''
    for c in result['criteria']:
        code = c['reason_code']
        explanation = REASON_TEXT.get(code.removeprefix('THETA_ASSESSMENT_'), 'The retained criterion carries the reason below.')
        reference_body = ''.join(f'<div class="theta-reference-list">{e(key.replace("_", " "))}: {refs(KINDS[key], ids)}</div>'
                                 for key, ids in c['references'].items() if ids)
        if not reference_body:
            reference_body = '<p class="theta-muted">NO DOCUMENTED CRITERION REFERENCES</p>'
        for event in c.get('event_timing', []):
            reference_body += '<p class="theta-muted">' + refs('event', [event['event_id']]) + ' · ' + e(event['position']) + '</p>'
        rows += (f'<tr data-criterion="{e(c["criterion_id"])}"><td>{e(c["criterion_id"])} — {e(CRITERION_LABELS[c["criterion_id"]])}</td>'
                 f'<td data-result>{e(c["result"])}</td><td><p>{e(explanation)}</p>'
                 + disclosure('REASON / RETAINED REFERENCES', f'<code data-reason>{e(code)}</code>' + reference_body) + '</td></tr>')
    table = ('<table class="theta-criteria"><thead><tr><th>Criterion</th><th>Documentary state</th><th>Retained explanation</th></tr></thead><tbody>'
             + rows + '</tbody></table>')
    return body + disclosure(f'{horizon} · C1–C9 DOCUMENTARY EXPLANATION', table)


def context_records(research, family, horizon):
    kind = 'assumption' if family == 'assumptions' else 'limitation'
    entries = applicable(research[family], horizon)
    if not entries:
        return '<p class="theta-muted">NO DOCUMENTED ITEMS</p>'
    return ''.join('<article class="theta-record"><h4>' + e(v['identity']) + '</h4>'
        + '<div class="theta-applicability">APPLIES TO: ' + e(' · '.join(v['horizons'])) + ' · ' + e(v['scope']) + '</div>'
        + '<p>' + e(v['statement']) + '</p>'
        + fields([('Supporting evidence', refs('evidence', v['supporting_evidence_ids'])),
                  ('Affected references', typed_refs(v['affected_references'])),
                  ('Unresolved consequence', e(v['unresolved_consequence'] or 'NOT_ESTABLISHED'))]) + '</article>' for v in entries)


def events(research, horizon):
    entries = applicable(research['scheduled_events'], horizon)
    if not entries:
        return '<p class="theta-muted">NO DOCUMENTED EVENT RECORDS</p>'
    body = ''
    for v in entries:
        window = v['scheduled_window']
        body += ('<article class="theta-record"><h4>' + e(v['description']) + '</h4>'
                 '<div class="theta-applicability">' + e(v['event_id']) + ' · APPLIES TO: ' + e(' · '.join(v['horizons'])) + '</div>'
                 + fields([('Availability', e(v['availability'])),
                           ('Scheduled window', 'NOT_ESTABLISHED' if window is None else dt(window['start']) + ' → ' + dt(window['end'])),
                           ('Schedule known at', dt(v['schedule_known_at'])),
                           ('Possible impact · ASTRA-ASSERTED', e(v['possible_impact'] or 'NOT_ESTABLISHED')),
                           ('Limitations', e(v['limitations'])),
                           ('Source', refs('source', [] if v['schedule_source_id'] is None else [v['schedule_source_id']])),
                           ('Evidence', refs('evidence', v['evidence_ids']))]) + '</article>')
    return body


def render_detail(detail):
    q, answer, receipt, assessment = (detail[k] for k in ('question', 'answer', 'receipt', 'assessment'))
    subject, research = receipt['subject'], answer['research']
    body = '<div class="theta-detail-view">'
    body += '<section class="theta-panel theta-detail-header">'
    if q['synthetic']:
        body += '<p class="theta-sandbox">SYNTHETIC — NOT FOR GENUINE FORECASTING</p>'
    body += (f'<h2>{commodity_symbol(subject)}{e(subject)} <span class="theta-state">{e(detail["currentness"])}</span></h2>'
             '<p class="theta-muted">Exact accepted Astra forecast and retained KRONOS documentary assessment.</p>'
             + fields([('ANALYSIS COMPLETED', dt(answer['analyzed_at']))])
             + f'<p class="theta-id">Question: {e(q["question_id"])}</p><p class="theta-id">Answer: {e(answer["answer_id"])}</p>')
    if detail['currentness'] != 'CURRENT':
        body += '<p class="theta-muted">HISTORICAL EVIDENCE · ' + e(detail['currentness']) + '. This exact retained forecast does not populate Current Outlook.</p>'
    body += '</section><nav class="theta-detail-nav" aria-label="Detail sections"><a href="#theta-research">ASTRA RESEARCH</a><a href="#theta-charts">CHART EVIDENCE</a><a href="#theta-sources">SOURCES</a><a href="#theta-provenance">PROVENANCE</a></nav>'
    body += '<div class="theta-horizons">'
    for horizon in ('E1', 'E2'):
        forecast, target = answer['forecasts'][horizon], q['targets'][horizon]
        body += (f'<section class="theta-panel" id="theta-horizon-{horizon}" data-detail-horizon="{horizon}"><h2>{horizon} · {e(target["option_expiry"])}</h2>'
                 '<div class="theta-kicker">ASTRA FORECAST</div>'
                 f'<strong class="theta-range" data-lower="{e(forecast["lower"])}" data-upper="{e(forecast["upper"])}">{e(forecast["lower"])} – {e(forecast["upper"])}</strong>'
                 f'<div class="theta-confidence">Confidence: {e(forecast["confidence_pct"])}%</div>'
                 + fields([('Exact underlying MCX future', e(target['underlying_future'])),
                           ('Underlying futures expiry', e(target['futures_expiry'])),
                           ('Quotation unit', e(target['price_unit'])),
                           ('Settlement reference', e(target['settlement_reference'])),
                           ('Settlement definition', 'Daily Settlement Price of the exact underlying MCX futures contract on the option-expiry date.')])
                 + '<div class="theta-kicker">KRONOS DOCUMENTARY ASSESSMENT</div>' + assessment_panel(assessment, horizon))
        why = ''
        for key in ('rationale', 'counterevidence', 'uncertainty', 'path_risk', 'confidence_justification'):
            statement = forecast[key]
            why += f'<h3>{e(key.replace("_", " ").upper())}</h3><div class="theta-applicability">ASTRA-ASSERTED · {e(statement["classification"])}</div><p>{e(statement["text"])}</p>'
            why += '<div class="theta-reference-list">Evidence: ' + refs('evidence', statement['evidence_ids']) + '<br>Sources: ' + refs('source', statement['source_ids']) + '</div>'
        why += '<h3>MATERIAL EVIDENCE REFERENCES</h3>' + refs('evidence', forecast['material_evidence_ids']) + '<h3>MATERIAL SOURCES</h3>' + refs('source', forecast['material_source_ids'])
        body += disclosure(f'{horizon} · WHY / COUNTEREVIDENCE / PATH RISK', why)
        body += disclosure(f'{horizon} · SCHEDULED EVENTS', events(research, horizon))
        body += disclosure(f'{horizon} · ASSUMPTIONS', context_records(research, 'assumptions', horizon))
        body += disclosure(f'{horizon} · LIMITATIONS', context_records(research, 'limitations', horizon)) + '</section>'
    body += '</div><section class="theta-panel"><p class="theta-muted">Confidence is Astra’s stated terminal-range-containment confidence. It is not KRONOS calibrated probability, profitability, OTM, no-touch or trade probability. Documentary states do not adjust the accepted range or confidence.</p>'
    if assessment is not None and assessment['assessment_admission'] == 'ADMITTED':
        body += '<p class="theta-muted">' + e(assessment['verification_claim']) + '</p>'
    body += '<p class="theta-muted">Astra’s research, chart observations, classifications and relationships remain Analyst assertions. Source truth, research completeness and chart interpretation are not independently verified by this page.</p></section>'
    body += '<section class="theta-panel" id="theta-research"><h2>ASTRA RESEARCH · RETAINED COMMODITY CONTEXT</h2><p class="theta-muted">These are the original commodity-level narrative sections. Horizon applicability is carried by their linked evidence; no E1-only or E2-only scope is invented.</p>'
    for key, title in SECTIONS.items():
        section = research[key]
        content = '<div class="theta-applicability">ASTRA-ASSERTED · ' + e(section['availability']) + ' · ' + e(section['classification'] or 'NOT_ESTABLISHED') + '</div><p>' + e(section['text'] if section['text'] is not None else section['reason']) + '</p>' + refs('evidence', section['evidence_ids'])
        body += disclosure(title, content)
    claims = ''
    for v in research['evidence_items']:
        claims += item('evidence', v['evidence_id'], v['evidence_id'], '<div class="theta-applicability">ASTRA-ASSERTED · ' + e(v['classification']) + '</div><p>' + e(v['statement']) + '</p>' + fields([('Sources', refs('source', v['source_ids'])), ('Chart observations', refs('observation', v['observation_ids'])), ('Assumptions', refs('assumption', v['assumption_ids']))]), v['horizons'])
    body += disclosure('STRUCTURED EVIDENCE CLAIMS', claims)
    observations = ''
    for v in research['chart_observations']:
        observations += item('observation', v['observation_id'], v['observation_id'] + ' · ASTRA CHART OBSERVATION', fields([
            ('Role / instrument', e(v['role']) + ' · ' + e(v['displayed_instrument'] or 'NOT_ESTABLISHED')),
            ('Panel / timeframe', e(v['panel_locator']) + ' · ' + e(v['timeframe'] or 'NOT_ESTABLISHED')),
            ('Availability / classification', e(v['availability']) + ' · ' + e(v['classification'] or 'NOT_ESTABLISHED')),
            ('Observation', e(v['observation_text'] or 'NO DOCUMENTED OBSERVATION TEXT')),
            ('Visible / as-of', dt(v['visible_as_of'])), ('Completion', e(v['completion'])),
            ('Unavailable / unreadable reason', e(v['unavailable_reason'] or 'NOT_APPLICABLE')),
            ('Bound chart', refs('chart', ['GLOBAL_MACRO' if v['role'] == 'MACRO' else 'COMMODITY']))]), v['horizons'])
    body += disclosure('ASTRA CHART OBSERVATIONS', observations)
    relationships = ''
    for v in research['relationships']:
        label = v['relationship_type']
        if label == 'SUPPORT': label += ' · SUPPORTING EVIDENCE'
        if label == 'OPPOSITION': label += ' · OPPOSING EVIDENCE'
        relationships += item('relation', v['relation_id'], label + ' · ' + v['relation_id'], '<p>' + e(v['explanation']) + '</p>' + fields([('Retained references', typed_refs(v['references'])), ('Unresolved limitation', e(v['unresolved_limitation'] or 'NO DOCUMENTED UNRESOLVED LIMITATION')), ('Limitations', refs('limitation', v['limitation_ids']))]), v['horizons'])
    relationship_title = 'EVIDENCE RELATIONSHIPS · ASTRA-ASSERTED'
    if any(v['relationship_type'] == 'UNRESOLVED_CONTRADICTION' for v in research['relationships']):
        relationship_title += ' · UNRESOLVED_CONTRADICTION RECORDED'
    body += disclosure(relationship_title, relationships or '<p class="theta-muted">NO DOCUMENTED RELATIONSHIPS</p>')
    # Unique record anchors live in this shared index; horizon views above retain
    # explicit applicability without duplicating machine identities in the DOM.
    index = ''
    for family, kind in (('scheduled_events', 'event'), ('assumptions', 'assumption'), ('limitations', 'limitation')):
        for v in research[family]:
            identity = v['event_id'] if kind == 'event' else v['identity']
            text = v['description'] if kind == 'event' else v['statement']
            links = ' · '.join(f'<a href="#theta-horizon-{h}">{h}</a>' for h in v['horizons'])
            index += item(kind, identity, identity, '<p>' + e(text) + '</p><p class="theta-reference-list">Inspect applicable horizon: ' + links + '</p>', v['horizons'])
    body += disclosure('EVENT / ASSUMPTION / LIMITATION REFERENCE INDEX', index or '<p class="theta-muted">NO DOCUMENTED ITEMS</p>') + '</section>'
    body += '<section class="theta-panel" id="theta-charts"><h2>EXACT QUESTION CHART EVIDENCE</h2><div class="theta-detail-charts">'
    for role, key, title in (('COMMODITY', 'commodity_chart', 'COMMODITY CHART'), ('GLOBAL_MACRO', 'macro_chart', 'GLOBAL MACRO CONTEXT')):
        chart = q['binding'][key]
        url = '/theta-earners/detail-chart?' + urlencode({'question': q['question_id'], 'subject': subject, 'role': role})
        body += f'<article id="theta-chart-{role}"><h3>{title}</h3><img src="{e(url)}" alt="Exact retained {e(title)} original"><a href="{e(url)}" target="_blank" rel="noopener" class="theta-original-action">OPEN EXACT ORIGINAL</a><p class="theta-muted">Question-bound original · aspect ratio preserved</p></article>'
    body += '</div></section><section class="theta-panel" id="theta-sources"><h2>SOURCES · ASTRA-RETAINED PROVENANCE</h2><p class="theta-muted">AVAILABLE BY T0 and RETRIEVED LATER are separate recorded times. Later retrieval does not itself mean later market information was used.</p>'
    for v in research['sources']:
        later = 'RETRIEVED LATER' if stamp(v['accessed_at']) > stamp(q['information_cutoff']) else 'RETRIEVED AT / BEFORE T0'
        body += disclosure(v['source_id'] + ' · ' + v['publisher'] + ' · ' + v['title'], item('source', v['source_id'], v['publisher'] + ' · ' + v['title'], fields([
            ('Source identity / kind', e(v['source_id']) + ' · ' + e(v['source_kind'])),
            ('Public locator', locator(v['url'] or v['reference'])), ('Publication time', dt(v['published_at'])),
            ('AVAILABLE BY T0', dt(v['available_at'])), (later, dt(v['accessed_at'])),
            ('Availability evidence · ASTRA-ASSERTED', e(v['availability_evidence'])),
            ('Observation period', e(v['observation_period'] or 'NOT_ESTABLISHED')),
            ('Archive / version locator', locator(v['archive_version_locator'])),
            ('Relevance', e(v['relevance'])), ('Linked evidence', refs('evidence', v['linked_evidence_ids'])),
            ('Source lineage', e(v['lineage']['status'])), ('Original information identity', locator(v['lineage']['original_information_id'])),
            ('Derivative source references', refs('source', v['lineage']['derivative_source_ids']))])))
    body += '</section><section class="theta-panel"><h2>INFORMATION BOUNDARY</h2>' + fields([
        ('INFORMATION SET CUTOFF / T0', dt(q['information_cutoff'])), ('ANALYSIS COMPLETED', dt(answer['analyzed_at'])),
        ('ANSWER ACCEPTED', dt(receipt['accepted_at'])), ('ASSESSMENT CREATED', 'NOT_ESTABLISHED — retained assessment unavailable' if assessment is None else dt(assessment['assessed_at']))]) + '<p class="theta-muted">T0 bounds the permitted information set. Recorded availability and later retrieval are distinct; later event outcomes are outside the forecast evidence boundary.</p></section>'
    technical = fields([('Question ID', e(q['question_id'])), ('Question SHA-256', e(receipt['question_sha256'])),
        ('Answer ID', e(answer['answer_id'])), ('Receipt ID', e(receipt['acceptance_id'])),
        ('Raw child SHA-256', e(receipt['raw_child_sha256'])), ('Canonical child SHA-256', e(receipt['canonical_child_sha256'])),
        ('Commodity chart SHA-256', e(q['binding']['commodity_chart']['sha256'])), ('Macro chart SHA-256', e(q['binding']['macro_chart']['sha256'])),
        ('Research methodology', e(q['binding']['methodology']['identity'] + ' / ' + q['binding']['methodology']['version'])),
        ('Research methodology SHA-256', e(q['binding']['methodology']['sha256'])),
        ('Target authority', e(q['binding']['target_authority']['identity'] + ' / ' + q['binding']['target_authority']['version'])),
        ('Target authority SHA-256', e(q['binding']['target_authority']['sha256'])),
        ('Assessment ID', e('NOT_ESTABLISHED' if assessment is None else assessment['assessment_id'])),
        ('Analyst identity', e(answer['analyst']['identity'])), ('Analyst model', e(answer['analyst']['model'])),
        ('Analyst provenance · ASTRA-ASSERTED', e(answer['analyst']['provenance']))])
    if assessment is not None:
        technical += fields([('Assessment methodology', e(assessment['assessment_methodology']['identity'] + ' / ' + assessment['assessment_methodology']['version'])), ('Assessment methodology SHA-256', e(assessment['assessment_methodology']['sha256']))])
    for h in ('E1', 'E2'):
        technical += fields([(h + ' target authority reference', e(q['targets'][h]['authority_reference'])),
                             (h + ' exchange evidence reference', e(q['targets'][h]['exchange_evidence_reference']))])
    url = '/theta-earners/answer?' + urlencode({'question': q['question_id']})
    body += '<section class="theta-panel" id="theta-provenance">' + disclosure('TECHNICAL INTEGRITY / PROVENANCE', technical)
    body += f'<a class="theta-original-action" href="{e(url)}">EXACT ACCEPTED ASTRA EVIDENCE</a><p class="theta-muted">Exact original accepted UTF-8 child bytes retained by TE-04B.</p></section></div>'
    body += '''<script>(()=>{function reveal(){let id;try{id=decodeURIComponent(location.hash.slice(1));}catch(_e){return;}const node=document.getElementById(id);if(!node)return;for(let p=node.parentElement;p;p=p.parentElement)if(p.tagName==='DETAILS')p.open=true;node.scrollIntoView({block:'start'});}addEventListener('hashchange',reveal);if(location.hash)reveal();})();</script>'''
    return body
