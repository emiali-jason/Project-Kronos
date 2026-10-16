"""Persisted WO08 projection and explicit read-only Intraday visual history.

No evaluator, Provider acquisition, currentization or evidence publication is
available through this Browser owner.
"""
from dataclasses import asdict, dataclass
from hashlib import sha256
from html import escape
from http import HTTPStatus
import json
import re
from urllib.parse import urlencode

from kronos.browser.intraday_machine_controls import table_controls, CONTROLS_CSS, CONTROLS_JS
from kronos.browser.intraday_machine_history import MACHINE_HISTORY_ROUTE, RUN
from kronos.browser.product_routes import BrowserRouteResponse
from kronos.browser.intraday_chart_preview import _PreviewStore
from kronos.intraday.review import ReviewError, ReviewFailure
from kronos.intraday.review_persistence import IntradayReviewStore
from kronos.intraday.review_mcx_paired_persistence import IntradayMcxPairedReviewStore
from kronos.intraday.visual_reconciliation_v2_persistence import VisualReconciliationStore

WO08_STATUS_ROUTE = '/status/intraday-wo08/v1'
HISTORY_ROUTE = '/intraday/review/history'
HISTORY_ARTIFACT_ROUTE = '/intraday/review/history/artifact'
RETIREMENT_REASON = 'INTRADAY_WO07F_RETIRED_FOR_NEW_PRODUCTION'
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,255}\Z')


@dataclass(frozen=True)
class MachineOpportunitySnapshot:
    probables_run_identity: str | None
    assessments: tuple
    state: str

    def assessment_state(self, result):
        value = next((row for row in self.assessments
                      if row['probable_result_identity'] == result.result_identity), None)
        return self.state if value is None else value['disposition']


class IntradayWo08Projection:
    def __init__(self, store, probables):
        from kronos.intraday.wo08_assessment_store import Wo08AssessmentStore
        from kronos.intraday.probables_v2_persistence import ProbablesV2Store
        if type(store) is not Wo08AssessmentStore or type(probables) is not ProbablesV2Store:
            raise TypeError('WO08_BROWSER_DEPENDENCIES_REQUIRED')
        self.store, self.probables = store, probables

    def status_document(self):
        before = self.probables.load_current()
        pointer = self.store.current_pointer()
        rows = self.store.current_run()
        prices = {}
        for run_identity in {row.data['run_identity'] for row in rows}:
            companion = self.probables.load_assessment_observations(run_identity)
            for observation in (() if companion is None else companion.observations):
                prices[observation.admission_identity] = observation
        projected = []
        for row in rows:
            data = row.data
            price = prices.get(data['probable_result_identity'])
            if price is not None and (price.run_identity != data['run_identity']
                    or price.canonical_subject_identity != data['subject']
                    or price.market_session_identity != data['session_identity']
                    or price.direction != data['direction']):
                raise ValueError('WO08_ASSESSMENT_PRICE_BINDING_INVALID')
            projected.append({'identity': row.identity, 'integrity': row.integrity,
                **{key: value for key, value in data.items() if key != 'source_document'},
                'assessment_price': None if price is None or price.assessment_price is None else str(price.assessment_price),
                'assessment_price_time': None if price is None or price.assessment_time is None else price.assessment_time.isoformat(),
                'assessment_price_source': None if price is None else price.assessment_source_identity,
                'assessment_price_authority': 'PRICE_NOT_RETAINED' if price is None else price.classification.value})
        after = self.probables.load_current()
        if before != after or pointer != self.store.current_pointer():
            raise ValueError('WO08_PAGE_SOURCE_CHANGED')
        current = None if before is None else before.run_identity
        state = ('NOT_YET_ASSESSED' if pointer is None else
                 'SOURCE_LINEAGE_CURRENT' if pointer['run_identity'] == current else 'SUPERSEDED')
        return {'authority_owner': 'INTRADAY_WO08', 'currentness': state,
                'operational_session_eligibility': 'NOT_ASSESSED',
                'current_probables_run_identity': current, 'current_pointer': pointer,
                'assessments': tuple(projected),
                'provider_calls': 0, 'calculations': 0,
                'chart_analyst_required': False, 'wo07f_new_work_authority': 'RETIRED',
                'trading_authority': 'NONE'}

    def opportunity_snapshot(self, *, expected_run):
        document = self.status_document()
        if document['current_probables_run_identity'] != expected_run:
            raise ValueError('WO08_PAGE_SOURCE_CHANGED')
        pointer = document['current_pointer']
        rows = document['assessments'] if document['currentness'] == 'SOURCE_LINEAGE_CURRENT' else ()
        return MachineOpportunitySnapshot(expected_run, rows, document['currentness'])


_MACHINE_REVIEW_CSS = """
.main:has(.machine-review) .title h1{font-size:22px;line-height:1.2}
.main:has(.machine-review) .title p{font-size:11px}
.main:has(.machine-review) .topbar{min-height:74px;height:auto;padding-top:15px;padding-bottom:15px}
.machine-review{font-size:12px;line-height:1.45;min-width:0}
.machine-review h2{font-size:16px;margin:0 0 8px}.machine-review h3{font-size:15px;margin:10px 0 6px}
.machine-review p{margin:6px 0}.machine-review .method{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:12px 0;color:var(--muted);font-size:11px;overflow-wrap:anywhere}
.machine-review .chip{display:inline-block;border:1px solid #426076;border-radius:4px;padding:2px 6px;font-size:10px;color:#dce8f0}
.machine-review .paper{color:#ffd57a;border-color:#756034}
.machine-review table{width:100%;border-collapse:collapse;table-layout:fixed;font-size:11px}
.machine-review .assessment-table-scroll{max-width:100%;overflow-x:auto}
.machine-review .assessment-table-scroll:focus-visible{outline:2px solid #50b7ff;outline-offset:2px}
.machine-review th{text-align:left;color:#aebfca;font-size:10px;font-weight:600;padding:8px 5px;border-bottom:1px solid #375365}
.machine-review td{padding:8px 5px;vertical-align:top;overflow-wrap:anywhere;border-bottom:1px solid #223d50}
.machine-review th.security{width:22%}.machine-review th.direction{width:7%}.machine-review th.score{width:7%}.machine-review th.criterion{width:6%}.machine-review th.status{width:18%}.machine-review th.watch{width:16%}
.machine-review .sub{display:block;font-size:10px;color:var(--muted);margin-top:3px}.machine-review .yes{color:#60dfa0}.machine-review .no{color:#ffb68c}.machine-review .unknown{color:#bacbd7}
.machine-review details{border:1px solid #29475b;border-radius:6px;margin:10px 0;padding:0 10px;background:rgba(8,25,39,.5)}
.machine-review summary{cursor:pointer;min-height:32px;display:list-item;align-content:center;font-size:11px;color:#bcd6e8;overflow-wrap:anywhere}
.machine-review summary:focus-visible{outline:2px solid #50b7ff;outline-offset:2px}
.machine-review .row-detail td{padding:0;border:0}.machine-review .row-detail details{margin:0 0 5px;border-top:0;border-radius:0 0 5px 5px}
.machine-review .facts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px;margin:8px 0}.machine-review .facts div{min-width:0;overflow-wrap:anywhere}.machine-review .facts span{display:block;font-size:10px;color:var(--muted)}
.machine-review .criteria-detail{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin:10px 0}.machine-review .criterion-detail{min-width:0;border-left:2px solid #426076;padding:5px 8px;overflow-wrap:anywhere;font-size:11px}
.machine-review pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:10px;max-height:360px;overflow:auto}
.machine-review .empty{display:block;min-height:0;text-align:left;padding:20px 16px;border:1px solid #29475b;border-radius:7px;margin:12px 0}.machine-review .empty strong{font-size:13px}.machine-review .empty p{color:var(--muted)}
.machine-review .secondary{font-size:11px;color:var(--muted)}
@media(max-width:1050px){.machine-review table{table-layout:auto;min-width:900px}.machine-review th,.machine-review td{padding:7px 3px}.machine-review .facts,.machine-review .criteria-detail{grid-template-columns:1fr 1fr}}
"""


def _machine_table(rows, readiness, *, candidate=None, retained=False, current_assessments=(), secondary_ids=(), diagnostic=False, controls=True):
    from kronos.intraday.sponsor_presentation import security_name, waiting_for, CRITERION_NAMES, criterion_explanation, opportunity_label
    details = readiness.get('analysis_details', {})
    cards = {details.get(item.readiness_identity, {}).get('A. MACHINE WO08 ASSESSMENT', {}).get('identity'): item
             for item in readiness.get('cards', ()) if item.source_authority == 'WO08'}
    body = []
    for row in rows:
        card = cards.get(row['identity'])
        observation = {} if card is None else details.get(card.readiness_identity, {}).get('F. EXPERIMENTAL OBSERVATION', {})
        states = {c.get('criterion_id', c.get('criterion')): c for c in row['criteria']}
        explanations = []
        for which in ('I1', 'I2', 'I3', 'I4', 'I5'):
            c = states.get(which, {'state': 'MISSING', 'reason_codes': ['CRITERION_NOT_RETAINED']})
            explanations.append('<div class="criterion-detail"><strong>' + which + ' — ' + CRITERION_NAMES[which]
                + '</strong><p>' + escape(criterion_explanation(which, row.get('direction'))) + '</p><span class="sub">'
                + escape(c['state']) + ' · ' + escape(', '.join(c.get('reason_codes', ())) or c.get('rule', c['state']))
                + '</span><pre>' + escape(json.dumps(c.get('evidence', {}), indent=2, default=str)) + '</pre></div>')
        missing = ', '.join(k for k, c in states.items() if c['state'] not in {'SATISFIED', 'DETERMINISTICALLY_ESTABLISHED'}) or 'NONE'
        score = ('Unavailable' if card is None or card.readiness_state == 'READINESS_UNAVAILABLE'
                 or any(c['state'] in {'UNAVAILABLE', 'MISSING'} for c in states.values()) else card.score)
        state = 'NOT_YET_PUBLISHED' if card is None else card.readiness_state
        label = ('5/5 Now' if state in {'BUY_NOW', 'SELL_NOW'} else '4/5 Ready' if state in {'BUY_READY', 'SELL_READY'} else
                 'Awaiting assessment evidence' if state == 'READINESS_UNAVAILABLE' else
                 'Not admitted' if row.get('failure_reason') == 'PROBABLES_NOT_ADMITTED' else 'Under consideration')
        if not retained and opportunity_label(card) is not None:
            label = opportunity_label(card)
        if score == 'Unavailable':
            label = 'Awaiting assessment evidence'
        bindings = observation.get('selective_watch', ())
        watch = 'RETAINED WATCH' if bindings else 'NOT_RETAINED'
        monitoring = observation.get('monitoring') or dict(state='UNAVAILABLE', reason='Authoritative monitoring state is unavailable.')
        if retained and row['identity'] not in current_assessments:
            monitoring = dict(state='INACTIVE', reason='Retained evidence is not a current opportunity.')
        first = observation.get('first_five_at')
        reason = row.get('failure_reason') or row['disposition']
        contract = row.get('exact_mcx_contract_identity')
        price = 'UNAVAILABLE' if row.get('assessment_price') is None else str(row['assessment_price'])
        identity = escape(row['probable_result_identity'], quote=True)
        secondary = row['identity'] in secondary_ids
        attributes = ' data-secondary-review="' + ('true' if secondary else 'false') + '"'
        evidence_status = ('Retained evidence' if retained and row['identity'] not in current_assessments
                           else 'Current eligible assessment')
        score_match = re.fullmatch(r'([0-5])\s*/\s*5', score)
        control_data = dict(security=security_name(row['subject']) + ' · ' + row['subject'] + ' · ' + (contract or ''),
            direction=str(row.get('direction') or 'UNAVAILABLE'),
            score=score_match.group(1) if score_match else ('NOT_APPLICABLE' if score == 'NOT_APPLICABLE' else 'UNAVAILABLE'),
            status=label + ' · ' + state + ' · ' + evidence_status,
            waiting=[CRITERION_NAMES[k] for k, c in states.items() if k in CRITERION_NAMES
                     and c['state'] not in {'SATISFIED', 'DETERMINISTICALLY_ESTABLISHED'}] or ['No outstanding criteria'],
            monitoring=monitoring['state'], price=price, secondary=secondary)
        control_attributes = ' data-assessment-controls="' + escape(json.dumps(control_data), quote=True) + '"'
        prefix = 'diagnostic' if diagnostic else 'review'
        focus = ' tabindex="-1"' if candidate == row['probable_result_identity'] else ''
        body.append('<tr id="' + prefix + '-candidate-' + identity + '"' + focus + attributes + control_attributes + '><td><strong>'
            + escape(security_name(row['subject'])) + '</strong>'
            + ('<span id="review-candidate-' + identity + '"></span>' if diagnostic and not secondary else '')
            + ('<span class="chip">SECONDARY REVIEW</span>' if secondary else '')
            + '<span class="sub">' + escape(row['market_family'])
            + ('' if contract is None else ' · ' + escape(contract)) + '</span></td><td>'
            + escape(str(row.get('direction') or 'Unavailable')) + '</td><td>' + escape(score.replace(' / ', '/'))
            + '</td><td><strong>' + escape(label) + '</strong><span class="sub">' + escape(evidence_status) + '</span></td><td>' + escape(waiting_for(row['criteria']))
            + '</td><td><strong>' + escape(monitoring['state']) + '</strong><span class="sub">' + escape(monitoring['reason'])
            + ('' if not monitoring.get('since') else '<span class="sub">Since · ' + escape(monitoring['since']) + '</span>')
            + '</span></td><td>Assessment Price · ' + escape(price)
            + ('<span class="sub">First-five · ' + escape(str(first)) + '</span>' if first is not None and not retained else '')
            + '</td></tr>')
        facts = [('Machine security', row['subject']), ('Method / version', str(row['methodology_identity']) + ' / ' + str(row['methodology_version'])),
            ('Assessment Price · this admission', price + ' · ' + str(row.get('assessment_price_time') or 'time unavailable')),
            ('Price authority / source', str(row.get('assessment_price_authority') or 'PRICE_NOT_RETAINED') + ' · ' + str(row.get('assessment_price_source') or 'UNAVAILABLE')),
            ('First-five', 'NOT_RETAINED' if first is None else str(first)),
            ('Analysis boundary', row['analysis_boundary']), ('Session', row['session_identity']),
            ('WO09 state', state), ('Watch evidence', watch), ('Missing', missing)]
        levels = row.get('experimental_watch_levels') or {}
        level_text = '; '.join(k + ': ' + str(v) for k, v in levels.items() if v is not None)
        body.append('<tr class="row-detail"' + attributes + '><td colspan="7"><details><summary>Criterion details · waiting for '
            + escape(waiting_for(row['criteria'])) + '</summary><p>Only a separately authorized ordinary Analysis can reassess completed evidence. '
            + 'WebSocket observations are advisory only; they cannot establish 5/5 or trigger Analysis.</p>'
            + ('<p>Retained advisory levels · ' + escape(level_text) + '. These are not completed-candle confirmation.</p>' if level_text else '')
            + '<div class="criteria-detail">' + ''.join(explanations) + '</div><details><summary>Technical details · '
            + escape(reason) + '</summary><div class="facts">' + ''.join('<div><span>' + escape(k)
            + '</span>' + escape(str(v)) + '</div>' for k, v in facts) + '</div><p>'
            + ('Advisory wake hint retained — awaiting completed Analysis.' if observation.get('advisory_wake_hints') else '')
            + '</p><details><summary>Method and evidence</summary><pre>'
            + escape(json.dumps(dict(assessment=row, wo09=None if card is None else details.get(card.readiness_identity)), indent=2, default=str))
            + '</pre></details></details></details></td></tr>')
    control_id = 'diagnostic-controls' if diagnostic else 'review-controls'
    population = 'Complete Diagnostics population' if diagnostic else 'Current Secondary Review population'
    return ('<div class="assessment-browser" data-assessment-browser data-population="' + population + '">'
        + (table_controls(control_id, diagnostic=diagnostic) if controls else '')
        + '<div class="assessment-table-scroll" role="region" tabindex="0" aria-label="'
        + ('Retained' if retained else 'Current') + ' assessment columns"><table aria-label="WO08 machine assessments"><thead><tr>'
        + ''.join('<th scope="col">' + c + '</th>' for c in ('Security', 'Direction', 'Score', 'Status', 'Waiting for', 'Monitoring', 'Assessment Price'))
        + '</tr></thead><tbody>' + ''.join(body) + '</tbody></table></div></div>')


def _duration_text(microseconds):
    if type(microseconds) is not int or microseconds < 0:
        return 'Duration unavailable'
    seconds = (microseconds + 500000) // 1000000
    minutes, seconds = divmod(seconds, 60)
    return f'{minutes}m {seconds}s' if minutes else f'{seconds}s'


def _analysis_history(control):
    from kronos.browser.intraday_views import _status_time
    rows = control.get('recent_analysis_history', ())
    body = ''.join('<li>' + escape(_status_time(row.get('boundary') or row.get('completed_at')))
        + ' · ' + escape(str(row.get('result', 'Unavailable')).replace('_', ' ').title())
        + ' · ' + ('Population unavailable' if row.get('analysed_population') is None else
            str(row['analysed_population']) + ' analysed')
        + ' · ' + _duration_text(row.get('duration_microseconds'))
        + (' · <a href="' + escape(MACHINE_HISTORY_ROUTE + '?' + urlencode({'run': row['run_identity']}), quote=True)
            + '">View historical assessments</a>' if type(row.get('run_identity')) is str and RUN.fullmatch(row['run_identity']) else '')
        + '<details><summary>Exact operation timing</summary><pre>'
        + escape(json.dumps(row, indent=2, default=str)) + '</pre></details></li>' for row in rows)
    return '<details><summary>Analysis History · recent retained attempts</summary><ul>' + (
        body or '<li>Duration unavailable · No retained operation timing.</li>') + '</ul></details>'


def _latest_attempt_summary(control):
    """One validated history entry supplies every field; never use success pointers."""
    from kronos.browser.intraday_views import _status_time
    rows = control.get('recent_analysis_history', ())
    row = rows[0] if rows else {}
    bound = bool(row.get('provenance_identity') and row.get('operation_accounting_identity')
                 and row.get('duration_authority') == 'RETAINED_OPERATION_ACCOUNTING')
    population = row.get('analysed_population') if bound else None
    return ('<aside class="machine-review latest-analysis" aria-label="Latest retained Analysis attempt">'
        + '<strong>Latest retained Analysis attempt</strong><p>Boundary · '
        + escape(_status_time(row.get('boundary'))) + ' · Completed · '
        + escape(_status_time(row.get('completed_at'))) + '</p><p>'
        + escape(str(row.get('result') or 'Result unavailable').replace('_', ' ').title())
        + ' · ' + _duration_text(row.get('duration_microseconds') if bound else None)
        + ' · ' + (str(population) + ' analysed' if type(population) is int and population >= 0 else 'Population unavailable')
        + '</p><p class="secondary">Retained operation timing; current opportunity eligibility is checked separately.</p></aside>')


def _analysis_boundary_text(rows):
    from kronos.browser.intraday_views import _status_time
    return _status_time(None if not rows else rows[0].get('analysis_boundary'))


def _opportunity_body(status, readiness, *, candidate=None, opportunities_only=False):
    from kronos.browser.intraday_views import _readiness_body
    from kronos.intraday.sponsor_presentation import opportunity_label
    rows = status['assessments']
    operational = readiness.get('operational_summary')
    current_ids = (None if operational is None or operational.ready is None or operational.now is None
                   else set(operational.current_readiness))
    current_assessments = {readiness.get('analysis_details', {}).get(identity, {}).get('A. MACHINE WO08 ASSESSMENT', {}).get('identity')
        for identity in current_ids or ()}
    current, considered, other = [], [], []
    cards = {readiness.get("analysis_details", {}).get(card.readiness_identity, {}).get(
        "A. MACHINE WO08 ASSESSMENT", {}).get("identity"): card
        for card in readiness.get("cards", ()) if card.source_authority == "WO08"}
    for row in rows:
        eligible = status['currentness'] == 'SOURCE_LINEAGE_CURRENT' and current_ids is not None and row['identity'] in current_assessments
        card = cards.get(row['identity'])
        admitted_current = (eligible and row.get('probables_state') in {'LONG_PROBABLE', 'SHORT_PROBABLE'}
            and card is not None and card.instrument == row['subject']
            and card.direction == row.get('direction') and card.direction in {'LONG', 'SHORT'}
            and card.probables_run_identity == row.get('run_identity'))
        if admitted_current:
            considered.append(row)
        (current if admitted_current and opportunity_label(cards.get(row['identity'])) is not None else other).append(row)
    admitted = [row for row in rows if row.get('probables_state') in {'LONG_PROBABLE', 'SHORT_PROBABLE'}]
    unavailable = [row for row in rows if row.get('probables_state') not in {'LONG_PROBABLE', 'SHORT_PROBABLE'}
                   and 'UNAVAILABLE' in str(row.get('probables_state', ''))]
    not_admitted = len(rows) - len(admitted) - len(unavailable)
    labels = [opportunity_label(cards[row['identity']]) for row in current]
    known = operational is not None and operational.ready is not None and operational.now is not None
    count_values = (('READY', labels.count('READY')), ('NOW', labels.count('NOW'))) if opportunities_only else (
        ('ANALYSED', len(rows)), ('SECONDARY REVIEW', len(considered)),
        ('NEAR READY', labels.count('NEAR READY')), ('READY', labels.count('READY')), ('NOW', labels.count('NOW')))
    funnel = '<div class="facts attention-funnel" aria-label="Sponsor opportunity funnel">' + ''.join(
        '<div><span>' + label + '</span><strong>' + (str(value) if known or label == 'ANALYSED' else '—')
        + '</strong></div>' for label, value in count_values) + '</div>'
    if not opportunities_only:
        funnel += '<details><summary>Analysis accounting · ' + str(len(rows)) + ' analysed</summary>'
        funnel += '<div class="facts" aria-label="Analysis funnel">' + ''.join(
            '<div><span>' + label + '</span><strong>' + str(value) + '</strong></div>' for label, value in (
                ('Analysed', len(rows)), ('Considered', '—' if not known else len(considered)),
                ('Not Admitted', not_admitted), ('Unavailable', len(unavailable)))) + '</div></details>'
    primary = [row for row in current if opportunity_label(cards.get(row['identity'])) in {'READY', 'NOW'}] if opportunities_only else considered
    secondary_ids = {row['identity'] for row in considered}
    if opportunities_only:
        diagnostic_panel = '<p><a href="/intraday/review#intraday-diagnostics">View assessment and complete Diagnostics in Review</a></p>'
    else:
        diagnostic_rows = sorted(rows, key=lambda row: row['identity'] not in secondary_ids)
        diagnostic_panel = ('<details id="intraday-diagnostics"><summary>Diagnostics / Full Analysis · ' + str(len(rows))
            + '</summary><p class="secondary">Complete retained population; ordering is not a trading rank. Not Admitted / Unavailable / Retained.</p>'
            + _machine_table(diagnostic_rows, readiness, candidate=candidate, retained=True,
                current_assessments=secondary_ids, secondary_ids=secondary_ids, diagnostic=True)
            + '</details>')
    method = next((row for row in current), next(iter(rows), None))
    method_text = ('KRONOS-INTRADAY-WO08-EXPERIMENTAL-PULLBACK-PAPER / 0.1.0' if method is None else str(method['methodology_identity']) + ' / ' + str(method['methodology_version']))
    scope = ('Current opportunity eligibility unavailable' if operational is None or operational.ready is None
             else 'Current session verified' if operational.state == 'CURRENT_SESSION_VERIFIED'
             else 'No current session opportunities')
    body = ('<section class="machine-review">'
        + funnel + '<p class="secondary">Retained Analysis boundary · '
        + escape(_analysis_boundary_text(rows)) + '</p>'
        + '<div class="method"><span class="chip paper">EXPERIMENTAL PAPER</span><span class="chip">'
        + escape(scope) + '</span><details><summary>Method · Technical details</summary>' + escape(method_text) + '</details></div>'
        + (_machine_table(primary, readiness, candidate=candidate,
                secondary_ids=() if opportunities_only else secondary_ids, controls=not opportunities_only) if primary else
            ('<div class="empty"><strong>No current READY/NOW opportunities.</strong><p>Other assessments remain in Review.</p></div>' if opportunities_only else
             '<div class="empty"><strong>No current Secondary Review assessments.</strong><p>Retained evidence remains readable in Diagnostics.</p></div>'))
        + diagnostic_panel
        + '<details><summary>Method, status and authority</summary><div class="secondary">'
        + '<p>Source lineage · ' + escape(status['currentness']) + '. Source lineage alone does not establish current session eligibility.</p>'
        + '<p>WO08 supplies I1–I5. WO09 owns readiness. Chart Analyst is not required for new Intraday work. '
        + 'Uncommissioned and unavailable criteria fail closed; they are not analytical negatives.</p>'
        + '<p>Yes = established; No = negative; Gap = outstanding; N/A = unavailable; N/C = not commissioned. '
        + 'Expand a row for the exact criterion state and reason.</p>'
        + '<p>Experimental PAPER only. Predictive usefulness is not established. Sponsor PAPER and Observation decisions remain separate. '
        + 'No automatic position, LIVE or broker authority. Assessment Price is the retained admission observation for the displayed run, never the experimental P measurement or a replacement for the original opportunity price. First-five is the first retained prospective observation, not the first market instant.</p>'
        + '</div></details><details><summary>Historical Chart Analyst Evidence</summary>'
        + '<p class="secondary">RETIRED FOR NEW INTRADAY PRODUCTION · HISTORICAL EVIDENCE RETAINED</p>'
        + '<p><a href="' + HISTORY_ROUTE + '">View retained Question Packs, Answers and WO07F reconciliations</a></p>'
        + (_readiness_body(dict(active_attention=(), historical_cards=readiness.get('historical_cards', ()),
            historical_analysis_details=readiness.get('historical_analysis_details', {}))) if readiness.get('historical_cards') else '')
        + '</details></section>')
    return body


def render_machine_review(snapshot, status, readiness, *, candidate=None):
    from kronos.browser.views import render_browser_page
    from kronos.browser.intraday_views import _INTRADAY_CSS, _intraday_tabs
    return render_browser_page(title='Intraday — Machine Review', subtitle='Current opportunity detail and complete retained Analysis evidence',
        snapshot=snapshot, active_nav='Intraday', active_tab='Review',
        body=_intraday_tabs(False, active='review')
             + '<p><a href="' + MACHINE_HISTORY_ROUTE + '">Machine Assessment History — historical only</a></p>'
             + _opportunity_body(status, readiness, candidate=candidate)
             + '<script>' + CONTROLS_JS + '</script>',
        extra_styles=_INTRADAY_CSS + _MACHINE_REVIEW_CSS + CONTROLS_CSS)


def render_sponsor_opportunities(snapshot, status, readiness, *, market_availability=(), refresh_status=None, latest_evaluable_run=None):
    from kronos.browser.views import render_browser_page
    from kronos.browser.intraday_views import (_INTRADAY_CSS, _INTRADAY_STATISTICS_CSS, _intraday_tabs,
        _render_market_availability, _status_time)
    enabled = (snapshot.provider_state.value == 'CONNECTED'
        and (not market_availability or any(item.available for item in market_availability)))
    control = refresh_status or {}
    attempt = control.get('last_refresh_attempt') or {}
    boundary = None if latest_evaluable_run is None else latest_evaluable_run.analysis_boundary.isoformat()
    retained_date = _status_time(boundary)
    freshness = _latest_attempt_summary(control) + _analysis_history(control) + ('<details><summary>Last retained successful Analysis boundary ' + escape(retained_date)
        + '</summary><p>Last refresh attempt · ' + escape(_status_time(attempt.get('attempted_at')))
        + ' · ' + escape(str(attempt.get('outcome') or 'Not yet run')) + '</p>'
        + '<p>Retained Analysis is evidence of its original boundary. Current opportunity eligibility is checked separately.</p></details>')
    body = (_intraday_tabs(enabled, statistics=True) + _render_market_availability(market_availability)
        + freshness + _opportunity_body(status, readiness, opportunities_only=True))
    return render_browser_page(title='Intraday Opportunities', subtitle='Ready · Now — current governed PAPER opportunities',
        snapshot=snapshot, active_nav='Intraday', active_tab='Opportunities', body=body,
        extra_styles=_INTRADAY_CSS + _INTRADAY_STATISTICS_CSS + _MACHINE_REVIEW_CSS)



class _HistoricalLegacyStore(IntradayReviewStore):
    _read = staticmethod(_PreviewStore._read)


class _HistoricalPairedStore(IntradayMcxPairedReviewStore):
    _read = staticmethod(_PreviewStore._read)


class _HistoricalReconciliationStore(VisualReconciliationStore):
    _read = staticmethod(_PreviewStore._read)


class IntradayVisualHistory:
    """Immutable-identity reads; never require or change a current Review pointer."""
    def __init__(self, review, paired, reconciliation):
        self.review = _PreviewStore(review.root)
        self.legacy = _HistoricalLegacyStore(review.root.parent / 'review-v1')
        self.paired = _HistoricalPairedStore(paired.root)
        self.reconciliation = _HistoricalReconciliationStore(reconciliation.root)

    def _catalogue(self):
        return {
            'legacy-cycle': (self.legacy, 'cycles', self.legacy.load_cycle),
            'legacy-question': (self.legacy, 'question-packs', self.legacy.load_pack),
            'legacy-answer': (self.legacy, 'answer-packs', self.legacy.load_answer_pack),
            'legacy-visual': (self.legacy, 'visual-evidence', self.legacy.load_visual_evidence),
            'legacy-chart': (self.legacy, 'chart-revisions', self.legacy.load_chart),
            'nse-cycle': (self.review, 'cycles', self.review.load_cycle),
            'nse-question': (self.review, 'question-packs', self.review.load_pack),
            'nse-chart': (self.review, 'chart-revisions', self.review.load_chart),
            'nse-visual': (self.review, 'visual-evidence', self.review.load_visual_evidence),
            'nse-question-pdf': (self.review, 'question-transports', self.review.load_transport),
            'mcx-question': (self.paired, 'review-packs', self.paired.load_pack),
            'mcx-answer': (self.paired, 'answer-packs', self.paired.load_answer),
            'mcx-visual': (self.paired, 'imported-visual-evidence', self.paired.load_evidence),
            'mcx-question-pdf': (self.paired, 'transports', self.paired.load_transport),
            'mcx-chart': (self.paired, 'chart-revisions', self.paired.load_chart),
            'wo07f': (self.reconciliation, 'records', self.reconciliation.load),
        }

    def render(self, snapshot):
        from kronos.browser.views import render_browser_page
        from kronos.browser.intraday_views import _INTRADAY_CSS, _intraday_tabs
        groups = []
        for kind, (store, namespace, _loader) in self._catalogue().items():
            directory = store.root / namespace
            if any(p.is_symlink() for p in (directory, *directory.parents)):
                raise ValueError('HISTORICAL_VISUAL_PATH_INVALID')
            links = []
            for path in sorted(directory.glob('*.json')):
                identity = path.stem
                if path.is_symlink() or not _ID.fullmatch(identity):
                    raise ValueError('HISTORICAL_VISUAL_PATH_INVALID')
                href = HISTORY_ARTIFACT_ROUTE + '?' + urlencode({'kind': kind, 'identity': identity})
                links.append('<li><a style="overflow-wrap:anywhere" href="' + escape(href, quote=True) + '">' + escape(identity) + '</a></li>')
            if links:
                groups.append('<details><summary>' + escape(kind.replace('-', ' ').upper())
                              + ' · ' + str(len(links)) + '</summary><ul>' + ''.join(links) + '</ul></details>')
        body = (_intraday_tabs(False, active='review') + '<h2>Historical visual evidence</h2>'
                + '<p>RETIRED FOR NEW INTRADAY PRODUCTION · HISTORICAL EVIDENCE RETAINED</p>'
                + '<p>These immutable artifacts describe their original runs. They confer no new production authority.</p>'
                + (''.join(groups) or '<p>No retained historical visual artifacts.</p>'))
        return render_browser_page(title='Intraday — Historical Visual Evidence', subtitle='Read-only retained evidence.',
                                   snapshot=snapshot, active_nav='Intraday', active_tab='Review', body=body,
                                   extra_styles=_INTRADAY_CSS)

    def artifact(self, query):
        if set(query) != {'kind', 'identity'} or any(type(v) is not list or len(v) != 1 for v in query.values()):
            raise ValueError('HISTORICAL_VISUAL_REQUEST_INVALID')
        kind, identity = query['kind'][0], query['identity'][0]
        if type(identity) is not str or not _ID.fullmatch(identity) or kind not in self._catalogue():
            raise ValueError('HISTORICAL_VISUAL_REQUEST_INVALID')
        _store, _namespace, loader = self._catalogue()[kind]
        value = loader(identity)
        if kind == 'legacy-chart':
            return BrowserRouteResponse(self.legacy.load_chart_bytes(value), content_type=value.media_type)
        if kind == 'mcx-chart':
            suffix = '.png' if value.media_type == 'image/png' else '.jpg'
            raw = self.paired.load_bytes('chart-binaries', value.chart_artifact_identity, suffix)
            if len(raw) != value.byte_count or sha256(raw).hexdigest() != value.payload_sha256:
                raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
            return BrowserRouteResponse(raw, content_type=value.media_type)
        if kind == 'mcx-question-pdf':
            raw = self.paired.load_bytes('question-pdfs', value.transport_identity, '.pdf')
            if sha256(raw).hexdigest() != value.question_pdf_sha256:
                raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
            return BrowserRouteResponse(raw, content_type='application/pdf')
        if kind == 'nse-chart':
            return BrowserRouteResponse(self.review.load_chart_bytes(value), content_type=value.media_type)
        if kind == 'nse-question-pdf':
            return BrowserRouteResponse(self.review.load_transport_question_pdf(value), content_type='application/pdf')
        document = asdict(value)
        if kind == 'nse-visual':
            # The immutable visual artifact retains accepted Answer lineage. Where
            # original Answer bytes exist, expose them only after exact hash binding.
            name = value.review_pack_identity + '-' + value.answer_source_sha256
            path = self.review.root / 'answer-transports' / (name + '.json')
            if path.exists():
                raw = self.review._read(path)
                if sha256(raw).hexdigest() != value.answer_source_sha256:
                    raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
                document['retained_answer'] = json.loads(raw)
        return BrowserRouteResponse(json.dumps(document, indent=2, default=str),
                                    content_type='application/json; charset=utf-8')
