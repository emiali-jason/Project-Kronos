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
        after = self.probables.load_current()
        if before != after or pointer != self.store.current_pointer():
            raise ValueError('WO08_PAGE_SOURCE_CHANGED')
        current = None if before is None else before.run_identity
        state = ('NOT_YET_ASSESSED' if pointer is None else
                 'SOURCE_LINEAGE_CURRENT' if pointer['run_identity'] == current else 'SUPERSEDED')
        return {'authority_owner': 'INTRADAY_WO08', 'currentness': state,
                'operational_session_eligibility': 'NOT_ASSESSED',
                'current_probables_run_identity': current, 'current_pointer': pointer,
                'assessments': tuple({'identity': row.identity, 'integrity': row.integrity,
                                      **{key: value for key, value in row.data.items() if key != 'source_document'}} for row in rows),
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


def render_machine_review(snapshot, status, readiness, *, candidate=None):
    from kronos.browser.views import render_browser_page
    from kronos.browser.intraday_views import _INTRADAY_CSS, _intraday_tabs, _readiness_body
    cards = []
    for row in status['assessments']:
        downstream = next((card for card in readiness.get('cards', ())
                           if card.source_authority == 'WO08' and card.instrument == row['subject']
                           and card.probables_run_identity == row['run_identity']), None)
        readiness_text = ('NOT_YET_PUBLISHED' if downstream is None else
                          downstream.readiness_state + ' · ' + downstream.score + ' · ' + downstream.monitorability_state)
        criteria = ''.join('<tr><th>' + escape(str(c.get('criterion_id', c.get('criterion', ''))))
                           + '</th><td>' + escape(str(c['state'])) + '</td><td>'
                           + escape(', '.join(c['reason_codes'])) + '</td></tr>'
                           for c in row['criteria'])
        focus = ' tabindex="-1"' if candidate == row['probable_result_identity'] else ''
        cards.append('<article class="intraday-review-v2-card" id="review-candidate-'
                     + escape(row['probable_result_identity'], quote=True) + '"' + focus + '><h3>'
                     + escape(row['subject']) + '</h3><p>' + escape(str(row['market_family']))
                     + ' · ' + escape(str(row['direction'] or 'UNAVAILABLE')) + '</p><strong>'
                     + escape(row['disposition']) + '</strong><p>WO09 readiness · ' + escape(readiness_text) + '</p><p>Analysis · '
                     + escape(str(row['analysis_boundary'])) + '<br>Session · '
                     + escape(str(row['session_identity'])) + '</p><div class="table-scroll">'
                     + '<table class="intraday-table"><thead><tr><th>Criterion</th><th>Assessment</th>'
                     + '<th>Reason</th></tr></thead><tbody>' + criteria + '</tbody></table></div>'
                     + '<p>Failure stage · ' + escape(str(row['failure_stage'] or 'NONE'))
                     + '<br>Failure reason · ' + escape(str(row['failure_reason'] or 'NONE'))
                     + '</p><details><summary>Method and evidence</summary><pre>'
                     + escape(json.dumps(row, indent=2, default=str)) + '</pre></details></article>')
    empty = '<p>No machine assessment is retained for this Analysis. Run ordinary Analysis to acquire new facts.</p>'
    body = (_intraday_tabs(False, active='review')
            + '<div class="intraday-warning"><strong>MACHINE WO08 ASSESSMENT</strong>'
            + '<span>Analytical assessment only. WO09 owns readiness; Sponsor PAPER and Observation decisions remain separate.</span></div>'
            + '<section class="intraday-review-v2"><h2>Intraday machine assessment</h2><p>Source lineage · <strong>'
            + escape(status['currentness']) + '</strong>. Chart Analyst is not required for new Intraday work.</p>'
            + '<p>Session and operational eligibility are not assessed by this view; downstream admission retains those checks.</p>'
            + '<p>Uncommissioned or unavailable criteria fail closed; they are not analytical negatives.</p>'
            + '<div class="intraday-review-v2-grid">' + (''.join(cards) or empty) + '</div></section>'
            + _readiness_body(readiness)
            + '<section class="intraday-review-config"><h2>Historical visual evidence</h2>'
            + '<p>RETIRED FOR NEW INTRADAY PRODUCTION · HISTORICAL EVIDENCE RETAINED</p>'
            + '<a href="' + HISTORY_ROUTE + '">View retained Question Packs, Answers and WO07F reconciliations</a></section>')
    return render_browser_page(title='Intraday — Machine Review', subtitle='WO08 assessment and separate WO09 readiness.',
                               snapshot=snapshot, active_nav='Intraday', active_tab='Review', body=body,
                               extra_styles=_INTRADAY_CSS)


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
