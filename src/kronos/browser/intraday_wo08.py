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
@media(max-width:1050px){.machine-review table{table-layout:auto}.machine-review th,.machine-review td{padding:7px 3px}.machine-review .facts,.machine-review .criteria-detail{grid-template-columns:1fr 1fr}}
"""


def _machine_table(rows, readiness, *, candidate=None, retained=False):
    details = readiness.get('analysis_details', {})
    body = []
    for row in rows:
        card = next((item for item in readiness.get('cards', ())
            if item.source_authority == 'WO08'
            and details.get(item.readiness_identity, {}).get('A. MACHINE WO08 ASSESSMENT', {}).get('identity') == row['identity']), None)
        observation = {} if card is None else details.get(card.readiness_identity, {}).get('F. EXPERIMENTAL OBSERVATION', {})
        states = {c.get('criterion_id', c.get('criterion')): c for c in row['criteria']}
        cells, explanations = [], []
        labels = {'SATISFIED': ('Yes', 'yes'), 'DETERMINISTICALLY_ESTABLISHED': ('Yes', 'yes'),
            'OUTSTANDING': ('Gap', 'no'), 'DETERMINISTICALLY_NEGATIVE': ('No', 'no'),
            'UNAVAILABLE': ('N/A', 'unknown'), 'NOT_COMMISSIONED': ('N/C', 'unknown')}
        for which in ('I1', 'I2', 'I3', 'I4', 'I5'):
            c = states.get(which, {'state': 'MISSING', 'reason_codes': ['CRITERION_NOT_RETAINED']})
            state = c['state']
            label, css = labels.get(state, (state, 'unknown'))
            reason = ', '.join(c.get('reason_codes', ())) or c.get('rule', state)
            cells.append('<td class="' + css + '" title="' + escape(state, quote=True) + '">' + escape(label) + '</td>')
            explanations.append('<div class="criterion-detail"><strong>' + which + ' · ' + escape(state)
                + '</strong><p>' + escape(reason) + '</p><span class="sub">Current · '
                + escape(str('UNAVAILABLE' if c.get('current_value') is None else c['current_value'])) + '</span></div>')
        missing = ', '.join(k for k, c in states.items() if c['state'] not in {'SATISFIED', 'DETERMINISTICALLY_ESTABLISHED'}) or 'NONE'
        score = 'NOT_PUBLISHED' if card is None else card.score
        state = 'NOT_YET_PUBLISHED' if card is None else card.readiness_state
        label = ('READY_FIVE · 5/5 NOW' if state in {'BUY_NOW', 'SELL_NOW'} else
                 'READY_FOUR · 4/5 READY' if state in {'BUY_READY', 'SELL_READY'} else state)
        bindings = observation.get('selective_watch', ())
        watch = 'RETAINED WATCH' if bindings else 'NOT_RETAINED'
        first = observation.get('first_five_at')
        reason = row.get('failure_reason') or row['disposition']
        contract = row.get('exact_mcx_contract_identity')
        price = 'UNAVAILABLE' if row.get('assessment_price') is None else str(row['assessment_price'])
        identity = escape(row['probable_result_identity'], quote=True)
        focus = ' tabindex="-1"' if candidate == row['probable_result_identity'] else ''
        body.append('<tr id="review-candidate-' + identity + '"' + focus + '><td><strong>'
            + escape(row['subject']) + '</strong><span class="sub">' + escape(row['market_family'])
            + ('' if contract is None else ' · ' + escape(contract)) + '</span><span class="sub">Assessment Price · ' + escape(price) + '</span></td><td>'
            + escape(str(row.get('direction') or 'UNAVAILABLE')) + '</td><td>' + escape(score)
            + '</td>' + ''.join(cells) + '<td><strong>' + escape(label) + '</strong><span class="sub">'
            + escape('RETAINED · NOT CURRENT' if retained else state) + '</span><span class="sub">First-five · ' + escape(str(first or 'NOT_RETAINED')) + '</span></td><td>'
            + escape(watch) + '<span class="sub">Missing · ' + escape(missing) + '</span></td></tr>')
        facts = [('Method / version', str(row['methodology_identity']) + ' / ' + str(row['methodology_version'])),
            ('Assessment Price · this admission', price + ' · ' + str(row.get('assessment_price_time') or 'time unavailable')),
            ('Price authority / source', str(row.get('assessment_price_authority') or 'PRICE_NOT_RETAINED') + ' · ' + str(row.get('assessment_price_source') or 'UNAVAILABLE')),
            ('First-five', 'NOT_RETAINED' if first is None else str(first)),
            ('Analysis boundary', row['analysis_boundary']), ('Session', row['session_identity']),
            ('WO09 pointer state', 'NOT_PUBLISHED' if card is None else card.monitorability_state)]
        body.append('<tr class="row-detail"><td colspan="10"><details><summary>Criterion details · '
            + escape(reason) + '</summary><div class="facts">' + ''.join('<div><span>' + escape(k)
            + '</span>' + escape(str(v)) + '</div>' for k, v in facts) + '</div><div class="criteria-detail">'
            + ''.join(explanations) + '</div><p class="secondary">Selective watch · ' + escape(watch)
            + '. Retained evidence only; current watch delivery is not asserted. '
            + ('Advisory wake hint retained — awaiting completed Analysis.' if observation.get('advisory_wake_hints') else '')
            + '</p><details><summary>Method and evidence</summary><pre>'
            + escape(json.dumps(dict(assessment=row, wo09=None if card is None else details.get(card.readiness_identity)), indent=2, default=str))
            + '</pre></details></details></td></tr>')
    return ('<table aria-label="WO08 machine assessments"><thead><tr><th class="security" scope="col">Security / market</th>'
        + '<th class="direction" scope="col">Direction</th><th class="score" scope="col">Score</th>'
        + ''.join('<th class="criterion" scope="col">' + c + '</th>' for c in ('I1','I2','I3','I4','I5'))
        + '<th class="status" scope="col">WO09 status</th><th class="watch" scope="col">Watch / missing</th>'
        + '</tr></thead><tbody>' + ''.join(body) + '</tbody></table>')


def render_machine_review(snapshot, status, readiness, *, candidate=None):
    from kronos.browser.views import render_browser_page
    from kronos.browser.intraday_views import _INTRADAY_CSS, _intraday_tabs, _readiness_body
    rows = status['assessments']
    operational = readiness.get('operational_summary')
    current_ids = None if operational is None else set(operational.current_readiness)
    current_assessments = {readiness.get('analysis_details', {}).get(identity, {}).get('A. MACHINE WO08 ASSESSMENT', {}).get('identity')
        for identity in current_ids or ()}
    current, other = [], []
    for row in rows:
        eligible = status['currentness'] == 'SOURCE_LINEAGE_CURRENT' and current_ids is not None and row['identity'] in current_assessments
        (current if eligible and row.get('probables_state') in {'LONG_PROBABLE','SHORT_PROBABLE'} else other).append(row)
    method = next((row for row in current), next(iter(rows), None))
    method_text = ('KRONOS-INTRADAY-WO08-EXPERIMENTAL-PULLBACK-PAPER / 0.1.0' if method is None else str(method['methodology_identity']) + ' / ' + str(method['methodology_version']))
    scope = 'Session eligibility not assessed' if operational is None else operational.state.replace('_', ' ')
    body = (_intraday_tabs(False, active='review') + '<section class="machine-review">'
        + '<div class="method"><span class="chip paper">EXPERIMENTAL PAPER</span><span>' + escape(method_text)
        + '</span><span class="chip">' + escape(scope) + '</span></div>'
        + (_machine_table(current, readiness, candidate=candidate) if current else
            '<div class="empty"><strong>NO CURRENT MACHINE ASSESSMENT</strong><p>Run Analysis to evaluate current opportunities.</p></div>')
        + ('<details><summary>Other / retained assessments · ' + str(len(other)) + '</summary><p class="secondary">'
            + 'Non-admitted, superseded or session-unverified evidence; not current opportunities.</p>'
            + _machine_table(other, readiness, candidate=candidate, retained=True) + '</details>' if other else '')
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
    return render_browser_page(title='Intraday — Machine Review', subtitle='Current machine assessment · WO08 / WO09',
        snapshot=snapshot, active_nav='Intraday', active_tab='Review', body=body,
        extra_styles=_INTRADAY_CSS + _MACHINE_REVIEW_CSS)


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
                links.append('<li><a href="' + escape(href, quote=True) + '">' + escape(identity) + '</a></li>')
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
