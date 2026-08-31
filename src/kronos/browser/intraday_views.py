"""Escaped HTML body for the read-only Intraday evidence workstation."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from html import escape
from urllib.parse import quote
from zoneinfo import ZoneInfo

from kronos.application.intraday_review import (
    IntradayAnswerBatchResult,
    IntradayAnswerImportResult,
    IntradayReviewBatchResult,
    IntradayReviewSnapshot,
)
from kronos.application.intraday_review_v2 import IntradayReviewV2Snapshot
from kronos.application.intraday_native_visual_reconciliation import (
    ReconciliationBatchResult,
    ReconciliationCandidateSnapshot,
    ReconciliationMemberResult,
    ReconciliationSnapshot,
)
from kronos.application.intraday_discovery import (
    IntradayDiscoveryMemberSnapshot,
    IntradayDiscoverySnapshot,
)
from kronos.application.intraday_workstation import IntradayWorkstationSnapshot
from kronos.application.swing_opportunities import BrowserWorkspaceSnapshot
from kronos.browser.views import render_browser_page
from kronos.intraday.contracts import CandleCompletion, IntradayTimeframe
from kronos.intraday.discovery import FactFamily
from kronos.intraday.probables import ProbablesRun, ProbableReason, ProbableState
from kronos.intraday.probables_v2 import (
    PROBABLES_V2_METHODOLOGY_CHECKSUM,
    PROBABLES_V2_METHODOLOGY_IDENTITY,
    PROBABLES_V2_METHODOLOGY_VERSION,
    PROBABLES_V2_PUBLICATION_IDENTITY,
    ProbablesRunV2,
)
from kronos.intraday.refresh_v2 import (
    REFRESH_V2_OPERATION_TYPE,
    REFRESH_V2_REQUEST_IDENTITY,
    REFRESH_V2_REQUEST_VERSION,
    REFRESH_V2_ROUTE,
    RefreshV2SourceClass,
)
from kronos.intraday.review_answer import AnswerImportState
from kronos.intraday.review_v2_operation import (
    REVIEW_V2_CREATE_REQUEST_IDENTITY,
    REVIEW_V2_CREATE_REQUEST_VERSION,
    REVIEW_V2_CREATE_ROUTE,
    ReviewV2OperationSource,
)
from kronos.intraday.review_v2 import (
    REVIEW_V2_ANSWER_IMPORT_ROUTE,
    REVIEW_V2_CHART_ROUTE,
)
from kronos.intraday.review_v2_transport import REVIEW_V2_QUESTION_TRANSPORT_ROUTE
from kronos.intraday.telemetry import TelemetryType


_KOLKATA = ZoneInfo("Asia/Kolkata")


_INTRADAY_CSS = r"""
.intraday-card{border:1px solid var(--line);background:#071827;border-radius:12px;padding:18px;max-width:760px}.intraday-card h2{margin:0;color:var(--green)}.intraday-card .event{border-top:1px solid var(--line);padding:10px 0}.intraday-card .detail-link{display:inline-block;margin-top:10px;color:var(--green);font-weight:800}.intraday-status{color:var(--muted);margin:8px 0 14px}.intraday-status strong{color:var(--green)}
.intraday-warning{display:flex;justify-content:space-between;gap:16px;border:1px solid #82631f;background:#231d11;color:#f6d997;border-radius:8px;padding:12px 14px;margin-bottom:14px}.intraday-selector{display:flex;align-items:center;gap:10px;margin-bottom:14px}.intraday-selector label{font-weight:700}.intraday-selector select{border:1px solid #31506a;background:#04131f;color:var(--text);border-radius:7px;padding:9px 12px}.intraday-panel{border:1px solid var(--line);background:rgba(6,23,37,.88);border-radius:10px;padding:15px;margin-bottom:14px;min-width:0}.intraday-panel h2{margin:0 0 12px;color:var(--blue);font-size:17px}.intraday-panel h3{margin:14px 0 7px;color:var(--muted);font-size:11px;text-transform:uppercase}.intraday-facts{display:grid;grid-template-columns:minmax(140px,.35fr) minmax(0,1fr);margin:0}.intraday-facts dt,.intraday-facts dd{padding:6px 8px;border-top:1px solid var(--line);margin:0;overflow-wrap:anywhere}.intraday-facts dt{color:var(--muted)}.intraday-timeframes{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.incomplete-observation{display:grid;gap:5px;margin-top:11px;border:1px dashed #82631f;border-radius:7px;padding:9px;color:#f6d997}.incomplete-observation span{color:var(--muted);overflow-wrap:anywhere}.intraday-context{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.intraday-table{width:100%;border-collapse:collapse;font-size:12px}.intraday-table th,.intraday-table td{text-align:left;vertical-align:top;padding:8px;border-bottom:1px solid var(--line);overflow-wrap:anywhere}.intraday-table th{color:var(--muted);white-space:nowrap}.table-scroll{overflow:auto}.intraday-unavailable{color:var(--muted)}.intraday-unavailable strong{color:var(--amber)}
.intraday-discovery-header{border:1px solid var(--line);background:#071827;border-radius:9px;padding:13px 15px;margin-bottom:12px}.intraday-discovery-header h2{font-size:17px;color:var(--green);margin:0 0 5px}.intraday-discovery-header p{margin:3px 0;color:var(--muted);font-size:12px}.intraday-discovery-table{width:100%;border-collapse:collapse;font-size:12px}.intraday-discovery-table th,.intraday-discovery-table td{padding:7px 8px;border-bottom:1px solid var(--line);text-align:left}.intraday-discovery-table th{font-size:10px;color:var(--muted);text-transform:uppercase}.intraday-state-ready{color:var(--green)}.intraday-state-held{color:var(--amber)}.intraday-failure{border:1px solid #81502a;background:#26170d;color:#f0c08e;border-radius:7px;padding:9px 11px;margin-bottom:12px}.intraday-methodology{border:1px solid var(--line);background:#071827;color:#c2d2dd;border-radius:7px;padding:8px 11px;margin-bottom:12px;font-size:11px}.intraday-methodology strong{color:var(--green)}.intraday-detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.intraday-tabs{margin:-22px -28px 22px}.intraday-tabs a.active{border-color:var(--green)}.intraday-tab{height:61px;display:flex;align-items:center;color:var(--muted);border-bottom:2px solid transparent;white-space:nowrap}.intraday-refresh-state{margin-left:8px;color:var(--muted);font-size:10px}.intraday-summary .status-top strong{color:var(--green)}.intraday-market-panels{grid-template-columns:repeat(2,minmax(0,1fr))}.intraday-market-panels .panel-heading h2{color:var(--green)}.intraday-market-panels .market-panel{min-height:330px}.intraday-market-panels .empty{min-height:110px}.intraday-market-accounting{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px;margin:-8px 0 14px}.intraday-market-accounting div{border:1px solid var(--line);border-radius:7px;background:#071827;padding:8px}.intraday-market-accounting span{display:block;color:var(--muted);font-size:8px;text-transform:uppercase;letter-spacing:.05em}.intraday-market-accounting strong{display:block;margin-top:2px;font-size:14px}.intraday-opportunities-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px;align-items:start}.intraday-market-group{border:1px solid var(--line);background:rgba(6,23,37,.86);border-radius:11px;padding:16px;min-width:0}.intraday-market-heading{display:flex;align-items:baseline;justify-content:space-between;gap:10px;border-bottom:1px solid var(--line);padding-bottom:10px}.intraday-market-heading h2{margin:0;color:var(--green);font-size:17px}.intraday-market-heading span{color:var(--muted);font-size:11px}.intraday-direction-group{margin-top:14px}.intraday-direction-group>h3{margin:0;color:#dce8f0;font-size:12px;letter-spacing:.08em}.intraday-direction-group>p{margin:3px 0 0;color:var(--muted);font-size:10px}.intraday-direction-empty{border:1px dashed var(--line);border-radius:8px;color:var(--muted);font-size:11px;margin-top:8px;padding:11px;text-align:center}.intraday-market-empty{border-left:2px solid var(--amber);color:var(--muted);font-size:10px;margin:12px 0 0;padding:6px 9px}.intraday-probable .opp-identity h4{font-size:18px;margin:0}.intraday-probable .summary-reason{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:7px}.intraday-card-fact{border-left:1px solid var(--line);padding-left:7px;min-width:0}.intraday-card-fact:first-child{border-left:0;padding-left:0}.intraday-card-fact span{display:block;color:var(--muted);font-size:8px;text-transform:uppercase;letter-spacing:.04em}.intraday-card-fact strong{display:block;margin-top:2px;font-size:11px;overflow-wrap:anywhere}.intraday-probable .summary-rr strong{color:#dce8f0}.intraday-probables-diagnostics{border:1px solid var(--line);background:#071827;border-radius:9px;margin-top:14px;padding:10px 12px}.intraday-probables-diagnostics>summary{cursor:pointer;color:var(--muted);font-size:10px;font-weight:800;letter-spacing:.05em}.intraday-diagnostic-list{display:grid;max-height:360px;overflow:auto;margin-top:9px}.intraday-diagnostic-row{display:grid;grid-template-columns:minmax(140px,.7fr) minmax(110px,.4fr) minmax(170px,.7fr) minmax(220px,1.3fr);gap:8px;border-top:1px solid var(--line);padding:7px 0;font-size:9px}.intraday-diagnostic-row strong{color:#dce8f0}.intraday-diagnostic-row span{color:var(--muted);overflow-wrap:anywhere}.intraday-panel-footer{display:flex;flex-wrap:wrap;gap:7px 14px;border-top:1px solid var(--line);margin-top:13px;padding-top:10px;color:var(--muted);font-size:10px}.intraday-panel-footer strong{color:#dce8f0}.intraday-unavailable-list{display:grid;gap:6px;margin-top:10px}.intraday-unavailable-subject{display:flex;justify-content:space-between;gap:10px;border-top:1px solid var(--line);padding-top:6px;color:var(--muted);font-size:11px}.intraday-unavailable-subject strong{color:var(--amber)}.intraday-analysis-context{display:flex;align-items:flex-start;gap:12px;border:1px solid var(--line);background:#071827;border-radius:8px;margin-top:14px;padding:8px 10px}.intraday-analysis-context>strong{flex:0 0 auto;color:var(--green);font-size:10px;text-transform:uppercase;letter-spacing:.05em}.intraday-analysis-context-detail{display:flex;align-items:center;flex-wrap:wrap;gap:5px 12px;color:var(--muted);font-size:8px;white-space:normal}.intraday-analysis-context-detail span{padding-left:12px;border-left:1px solid var(--line)}
.intraday-review-toolbar{display:flex;align-items:center;gap:9px;flex-wrap:wrap;border:1px solid var(--line);background:#071827;border-radius:9px;padding:10px;margin-bottom:12px}.intraday-review-toolbar form{margin:0}.intraday-review-toolbar .future-action{opacity:.62}.intraday-review-toolbar-note{color:var(--muted);font-size:10px}.intraday-batch-result{border:1px solid #2d765d;background:#08261e;border-radius:9px;padding:10px 12px;margin-bottom:12px}.intraday-batch-result h2{color:var(--green);font-size:13px;margin:0 0 6px}.intraday-batch-accounting{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px}.intraday-batch-accounting span,.intraday-batch-members span{font-size:10px;color:var(--muted)}.intraday-batch-members{display:flex;flex-wrap:wrap;gap:5px 12px;margin-top:7px}.intraday-review-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:12px}.intraday-review-card{border:1px solid var(--line);background:#071827;border-radius:10px;padding:14px;min-width:0}.intraday-review-card h2{margin:0;color:var(--green);font-size:18px}.intraday-review-head{display:flex;justify-content:space-between;gap:14px;align-items:center}.intraday-review-required{display:inline-block;margin-top:7px;color:#f6d997;font-size:10px;font-weight:850}.intraday-probable-context{border-top:1px solid var(--line);border-bottom:1px solid var(--line);padding:8px 0;margin:9px 0;color:#d9e6df;font-size:10px}.intraday-probable-context strong{display:block;color:var(--green);font-size:9px;text-transform:uppercase;margin-bottom:3px}.intraday-review-section-title{color:var(--muted);font-size:9px;font-weight:850;letter-spacing:.05em;margin:10px 0 6px}.intraday-review-status{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px;margin:12px 0}.intraday-review-status div{border:1px solid var(--line);border-radius:6px;padding:7px}.intraday-review-status span{display:block;color:var(--muted);font-size:8px;text-transform:uppercase}.intraday-review-status strong{font-size:10px;overflow-wrap:anywhere}.intraday-review-actions{display:grid;gap:8px}.intraday-drop{display:grid;place-items:center;text-align:center;min-height:160px;border:2px dashed #3d836b;border-radius:9px;padding:16px;color:var(--muted);cursor:pointer;outline:none}.intraday-drop:hover,.intraday-drop:focus-visible{border-color:var(--green);background:#09251d;box-shadow:0 0 0 3px rgba(46,212,119,.14)}.intraday-drop .paste-key{display:grid;place-items:center;width:46px;height:36px;border:1px solid #3d836b;border-radius:7px;color:var(--green);font-size:18px;font-weight:900}.intraday-drop strong{color:#e9f7f0;font-size:13px;margin-top:7px}.intraday-drop span{display:block;font-size:10px}.intraday-drop .required-panels{margin-top:7px}.intraday-chart-input{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}.intraday-file-choice{justify-self:start;display:inline-block;border:1px solid #246a52;border-radius:7px;padding:7px 10px;color:#dff7eb;font-size:10px;font-weight:750;cursor:pointer}.intraday-file-choice:hover,.intraday-file-choice:focus-visible{border-color:var(--green);outline:2px solid rgba(46,212,119,.25)}.intraday-review-actions form{margin:0}.intraday-review-lineage{font-size:9px;color:var(--muted);overflow-wrap:anywhere}.intraday-review-diagnostics{font-size:9px;color:var(--muted)}.intraday-review-diagnostics summary{cursor:pointer}.intraday-review-config{margin-top:14px;border:1px solid var(--line);border-radius:7px;padding:9px;color:var(--muted);font-size:9px;overflow-wrap:anywhere}
.intraday-drop{cursor:text;overflow:hidden}.intraday-drop.replace-ready{border-color:var(--green);background:#09251d;box-shadow:0 0 0 3px rgba(46,212,119,.14)}.intraday-drop.received{min-height:82px;border-style:solid}.intraday-chart-received strong{color:var(--green)}.intraday-chart-received span{color:var(--muted)}.intraday-chart-slot-actions{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
@media(max-width:900px){.intraday-detail-grid{grid-template-columns:1fr}.intraday-probable .summary-reason{grid-template-columns:repeat(3,minmax(0,1fr))}.intraday-diagnostic-row{grid-template-columns:minmax(120px,.7fr) minmax(100px,.4fr) minmax(160px,1fr)}.intraday-diagnostic-row span:last-child{grid-column:1/-1}}
@media(max-width:760px){.intraday-tabs{margin:-18px -18px 18px;padding:0 18px;gap:13px;overflow:auto}.intraday-tabs .toolbar{margin-left:0}.intraday-timeframes,.intraday-context{grid-template-columns:1fr}.intraday-warning,.intraday-selector{align-items:flex-start;flex-direction:column}.intraday-facts{grid-template-columns:1fr}.intraday-facts dd{padding-top:0}.intraday-market-panels,.intraday-opportunities-grid{grid-template-columns:1fr}.intraday-market-accounting{grid-template-columns:repeat(2,minmax(0,1fr))}.intraday-probable .summary-reason{grid-template-columns:repeat(2,minmax(0,1fr))}.intraday-diagnostic-row{grid-template-columns:1fr}.intraday-diagnostic-row span:last-child{grid-column:auto}.intraday-analysis-context{align-items:flex-start}.intraday-analysis-context-detail{flex-wrap:wrap;white-space:normal}.intraday-review-list{grid-template-columns:1fr}.intraday-batch-accounting{grid-template-columns:repeat(2,minmax(0,1fr))}.intraday-review-status{grid-template-columns:1fr}.intraday-review-toolbar{align-items:stretch;flex-direction:column}.intraday-review-toolbar button{width:100%}}
"""

_REVIEW_V2_CSS = r"""
.intraday-review-v2{border:1px solid #31506a;background:#061725;border-radius:10px;padding:15px;margin-bottom:16px}.intraday-review-v2-head{display:flex;justify-content:space-between;align-items:flex-start;gap:14px}.intraday-review-v2-head h2{margin:0;color:var(--green);font-size:17px}.intraday-review-v2-head p{margin:4px 0;color:var(--muted);font-size:11px}.intraday-review-v2-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:12px}.intraday-review-v2-card{border:1px solid var(--line);border-radius:8px;padding:12px;background:#071827}.intraday-review-v2-card h3{margin:0;color:#dce8f0}.intraday-review-v2-card .phase-a{display:inline-block;margin:7px 0;color:var(--amber);font-weight:800}.intraday-review-v2-control{display:flex;align-items:center;gap:12px;margin-top:12px}.intraday-review-v2-control span{color:var(--muted);font-size:10px;overflow-wrap:anywhere}@media(max-width:760px){.intraday-review-v2-grid{grid-template-columns:1fr}.intraday-review-v2-head{display:block}}
"""


def render_intraday_workstation(
    snapshot: BrowserWorkspaceSnapshot,
    intraday: IntradayWorkstationSnapshot | IntradayDiscoverySnapshot,
) -> str:
    """Render the complete Intraday page through the stable Browser shell."""

    return render_browser_page(
        title="Intraday Opportunities — Native Discovery",
        subtitle="Native Discovery — governed facts, complete accounting, no trading authority.",
        snapshot=snapshot,
        active_nav="Intraday",
        active_tab="",
        body=render_intraday_triage(
            intraday,
            refresh_enabled=snapshot.provider_state.value == "CONNECTED",
        ),
        extra_styles=_INTRADAY_CSS,
    )


def render_intraday_detail(
    snapshot: BrowserWorkspaceSnapshot,
    intraday: IntradayWorkstationSnapshot | IntradayDiscoverySnapshot,
) -> str:
    if isinstance(intraday, IntradayDiscoverySnapshot):
        selected = intraday.selected_member
        identity = "Member" if selected is None else selected.sponsor_label
        body = '<p><a href="/intraday">← Intraday triage</a></p>' + _render_discovery_detail(intraday)
        subtitle = f"{identity} — governed factual evidence; no trading conclusion."
    else:
        body = '<p><a href="/intraday">← Intraday triage</a></p>' + render_intraday_body(intraday)
        subtitle = "Immutable factual evidence; no trading conclusion."
    return render_browser_page(
        title="Intraday Detailed Evidence",
        subtitle=subtitle,
        snapshot=snapshot,
        active_nav="Intraday",
        active_tab="",
        body=body,
        extra_styles=_INTRADAY_CSS,
    )


def render_intraday_review(
    snapshot: BrowserWorkspaceSnapshot,
    review: IntradayReviewSnapshot,
    reconciliation: ReconciliationSnapshot | None = None,
    *,
    batch_result: IntradayReviewBatchResult | None = None,
    answer_result: IntradayAnswerImportResult | None = None,
    answer_batch_result: IntradayAnswerBatchResult | None = None,
    reconciliation_result: ReconciliationMemberResult | None = None,
    reconciliation_batch_result: ReconciliationBatchResult | None = None,
    review_v2: IntradayReviewV2Snapshot | None = None,
    available_probables_v2_run: ProbablesRunV2 | None = None,
) -> str:
    """Render persisted exact-current Review and WO-10 analytical state."""

    reconciled = {} if reconciliation is None else {
        item.probable_result_identity: item for item in reconciliation.candidates
    }
    ordered_candidates = tuple(sorted(review.candidates, key=_review_presentation_sort_key))
    cards = (
        "".join(
            _review_candidate(
                item,
                reconciled.get(item.probable_result_identity),
                slot_index,
            )
            for slot_index, item in enumerate(ordered_candidates, start=1)
        )
        if review.candidates
        else '<div class="empty"><div><strong>Zero current Review candidates</strong>'
        'Only exact-current Long/Short Probables are eligible.</div></div>'
    )
    ready_count = sum(item.chart_revision_identity is not None for item in review.candidates)
    batch_feedback = "" if batch_result is None else _review_batch_result(batch_result)
    answer_feedback = (
        "" if answer_result is None and answer_batch_result is None
        else _answer_import_result(answer_result, answer_batch_result)
    )
    reconciliation_feedback = _reconciliation_result(
        reconciliation_result, reconciliation_batch_result
    )
    current_batch = (
        ""
        if review.current_batch_identity is None
        else '<span class="intraday-review-toolbar-note"><strong>QUESTION PACK:</strong> '
        + escape(review.current_batch_filename or review.current_batch_identity)
        + '<br><strong>EXPECTED ANSWER:</strong> '
        + escape(review.current_batch_answer_filename or "UNAVAILABLE")
        + '<br><strong>Candidates:</strong> '
        + str(review.current_batch_candidate_count)
        + "</span>"
    )
    body = (
        _intraday_tabs(False, active="review")
        + '<div class="intraday-warning"><strong>NATIVE + VISUAL REVIEW</strong>'
        '<span>ANALYTICAL READINESS ONLY · NO ENTRY, TRADE, RISK OR BROKER AUTHORITY</span></div>'
        + _review_v2_projection(review_v2, available_probables_v2_run)
        + '<div class="intraday-review-toolbar"><form method="post" action="/intraday/review/question-packs">'
        '<button class="primary" type="submit"'
        + (" disabled" if ready_count == 0 else "")
        + '>CREATE ALL REVIEW PDF</button></form>'
        '<form method="post" action="/intraday/review/answers"><button type="submit"'
        + (" disabled" if not any(item.review_pack_identity is not None for item in review.candidates) else "")
        + '>UPLOAD ALL ANSWERS</button></form>'
        '<label class="intraday-file-choice" tabindex="0" for="intraday-batch-answer">CHOOSE COMBINED ANSWER</label>'
        '<input id="intraday-batch-answer" class="intraday-batch-answer-input" type="file" accept="application/json,.json" '
        'data-review-batch-answer-upload="/intraday/review/answers">'
        '<form method="post" action="/intraday/review/reconcile-all"><button type="submit"'
        + (" disabled" if not any(item.visual_evidence_identity is not None for item in reconciled.values()) else "")
        + '>RECONCILE ALL READY REVIEWS</button></form>'
        '<span class="intraday-review-toolbar-note">Chart ready · '
        + str(ready_count) + " / " + str(len(review.candidates)) + "</span>"
        + current_batch + "</div>"
        + batch_feedback + answer_feedback + reconciliation_feedback
        + '<div class="intraday-review-list">' + cards + '</div>'
        '<div class="intraday-review-config"><strong>Question outbox:</strong> '
        + escape(review.question_outbox)
        + '<br><strong>Answer inbox:</strong> '
        + escape(review.answer_inbox)
        + ' · Expected combined Answer: ' + escape(review.current_batch_answer_filename or "CREATE REVIEW PDF FIRST")
        + ' · Governed JSON Answer Pack import ACTIVE</div>'
        + _review_upload_script()
        + _review_v2_control_script()
    )
    return render_browser_page(
        title="Intraday Native Review",
        subtitle="Exact-current Probables · manual 1D | 1H | 15M | 5M chart intake.",
        snapshot=snapshot,
        active_nav="Intraday",
        active_tab="Review",
        body=body,
        extra_styles=_INTRADAY_CSS + _REVIEW_V2_CSS,
    )


def render_intraday_wo10(
    snapshot: BrowserWorkspaceSnapshot,
    status: dict[str, object],
) -> str:
    """Render restored WO-10 V2 state without evaluation or acquisition."""

    family_sections: list[str] = []
    for family in status.get("families", []):
        if type(family) is not dict:
            continue
        results = family.get("results", [])
        cards = "".join(_wo10_result_card(item) for item in results if type(item) is dict)
        if not cards:
            cards = (
                '<div class="empty"><div><strong>'
                + escape(str(family.get("state", "NOT_YET_RUN")))
                + "</strong><br>No restored WO-10 V2 result for this family.</div></div>"
            )
        family_sections.append(
            '<section class="panel"><div class="panel-head"><div><h2>'
            + escape(str(family.get("market_family", "UNAVAILABLE")))
            + "</h2><p>Restored persisted analytical reconciliation only.</p></div>"
            '<span class="status neutral">'
            + escape(str(family.get("state", "UNAVAILABLE")))
            + "</span></div>"
            + cards
            + "</section>"
        )
    body = (
        _intraday_tabs(False, active="wo10")
        + '<div class="intraday-warning"><strong>WO-10 ANALYTICAL RECONCILIATION</strong>'
        "<span>READ-ONLY RESTORED STATE · EXPLICIT SPONSOR CONTROL ONLY</span></div>"
        + "".join(family_sections)
        + '<div class="intraday-review-config"><strong>Contract:</strong> '
        + escape(str(status.get("request_contract_identity", "UNAVAILABLE")))
        + " / "
        + escape(str(status.get("request_contract_version", "UNAVAILABLE")))
        + "<br><strong>Active operation:</strong> "
        + escape(str(status.get("active_operation_identity") or "NONE"))
        + "</div>"
    )
    return render_browser_page(
        title="Intraday WO-10",
        subtitle="Persisted family results; rendering performs no analytical work.",
        snapshot=snapshot,
        active_nav="Intraday",
        active_tab="WO-10",
        body=body,
        extra_styles=_INTRADAY_CSS,
    )


def _wo10_result_card(item: dict[str, object]) -> str:
    state = str(item.get("state", "CONTEXT_INCOMPLETE"))
    consequence = (
        "Eligible to progress beyond WO-10 analytical reconciliation."
        if state == "PROMOTION_READY"
        else "Retained WO-10 analytical state."
    )
    reasons = item.get("reasons", [])
    reason_text = ", ".join(str(value) for value in reasons) if type(reasons) is list else "UNAVAILABLE"
    return (
        '<article class="intraday-review-card"><div class="intraday-review-card-head">'
        "<div><strong>" + escape(str(item.get("canonical_subject_identity", "UNAVAILABLE")))
        + "</strong><br><span>" + escape(str(item.get("market_family", "UNAVAILABLE")))
        + " · Direction " + escape(str(item.get("inherited_direction", "UNAVAILABLE")))
        + '</span></div><span class="status neutral">' + escape(state) + "</span></div>"
        + "<p>" + escape(consequence) + "</p>"
        '<dl class="detail-list"><dt>Policy</dt><dd>'
        + escape(str(item.get("policy_identity", "UNAVAILABLE"))) + " / "
        + escape(str(item.get("policy_version", "UNAVAILABLE")))
        + "</dd><dt>Source run</dt><dd>" + escape(str(item.get("source_probables_run_identity", "UNAVAILABLE")))
        + "</dd><dt>Boundary / phase</dt><dd>" + escape(str(item.get("analysis_boundary", "UNAVAILABLE")))
        + " · " + escape(str(item.get("persisted_phase", "UNAVAILABLE")))
        + "</dd><dt>Reason codes</dt><dd>" + escape(reason_text or "NONE")
        + "</dd><dt>Evidence lineage</dt><dd>" + escape(str(item.get("evidence_snapshot_identity", "UNAVAILABLE")))
        + "</dd><dt>Result identity</dt><dd>" + escape(str(item.get("result_identity", "UNAVAILABLE")))
        + "</dd></dl></article>"
    )


def render_intraday_wo11(
    snapshot: BrowserWorkspaceSnapshot,
    status: dict[str, object],
) -> str:
    """Render persisted WO-11 publication state without collation or evaluation."""

    publication = status.get("publication")
    if type(publication) is not dict:
        content = (
            '<div class="empty"><div><strong>'
            + escape(str(status.get("state", "NOT_YET_PUBLISHED")))
            + "</strong><br>No persisted WO-11 promotion publication.</div></div>"
        )
    else:
        members = publication.get("members", [])
        family_sections = []
        for family in ("NSE_EQUITY", "NSE_INDEX", "MCX"):
            family_members = [
                item for item in members
                if type(item) is dict and item.get("market_family") == family
            ] if type(members) is list else []
            cards = "".join(_wo11_member_card(item) for item in family_members)
            family_sections.append(
                '<section class="panel"><div class="panel-head"><div><h2>'
                + escape(family)
                + "</h2><p>Exact WO-10 lineage; presentation order has no authority.</p></div>"
                '<span class="status neutral">'
                + (str(len(family_members)) if family_members else "ABSENT")
                + "</span></div>"
                + (cards or '<div class="empty"><div>NOT YET PUBLISHED</div></div>')
                + "</section>"
            )
        state_counts = publication.get("state_counts", {})
        state_text = " · ".join(
            f"{name} {count}" for name, count in state_counts.items()
        ) if type(state_counts) is dict else "UNAVAILABLE"
        batches = publication.get("source_wo10_batches", [])
        batch_text = " | ".join(str(item) for item in batches) if type(batches) is list else "UNAVAILABLE"
        content = (
            '<section class="panel"><div class="panel-head"><div><h2>Publication</h2>'
            '<p>Zero-discretion validation, collation and publication.</p></div>'
            '<span class="status neutral">LOADED</span></div>'
            '<dl class="detail-list"><dt>Identity</dt><dd>'
            + escape(str(publication.get("publication_identity", "UNAVAILABLE")))
            + "</dd><dt>Boundary</dt><dd>"
            + escape(str(publication.get("publication_boundary", "UNAVAILABLE")))
            + "</dd><dt>Source WO-10 batches</dt><dd>" + escape(batch_text)
            + "</dd><dt>Members / eligible</dt><dd>"
            + escape(str(publication.get("member_count", 0))) + " / "
            + escape(str(publication.get("eligible_count", 0)))
            + "</dd><dt>Seven-state population</dt><dd>" + escape(state_text)
            + "</dd></dl></section>"
            + "".join(family_sections)
        )
    body = (
        _intraday_tabs(False, active="wo11")
        + '<div class="intraday-warning"><strong>WO-11 PROMOTION PUBLICATION</strong>'
        "<span>PRE-KR-370 · READ-ONLY RESTORED STATE · NO ENTRY OR TRADE AUTHORITY</span></div>"
        + content
        + '<div class="intraday-review-config"><strong>Contract:</strong> '
        + escape(str(status.get("publication_contract_identity", "UNAVAILABLE")))
        + " / " + escape(str(status.get("publication_contract_version", "UNAVAILABLE")))
        + "<br><strong>Active operation:</strong> "
        + escape(str(status.get("active_operation_identity") or "NONE"))
        + "</div>"
    )
    return render_browser_page(
        title="Intraday WO-11",
        subtitle="Persisted exact WO-10 results and mechanical downstream eligibility.",
        snapshot=snapshot,
        active_nav="Intraday",
        active_tab="WO-11",
        body=body,
        extra_styles=_INTRADAY_CSS,
    )


def _wo11_member_card(item: dict[str, object]) -> str:
    reasons = item.get("wo10_reasons", [])
    reason_text = ", ".join(str(value) for value in reasons) if type(reasons) is list else "UNAVAILABLE"
    return (
        '<article class="intraday-review-card"><div class="intraday-review-card-head"><div><strong>'
        + escape(str(item.get("canonical_subject_identity", "UNAVAILABLE")))
        + "</strong><br><span>Direction "
        + escape(str(item.get("inherited_direction", "UNAVAILABLE")))
        + '</span></div><span class="status neutral">'
        + escape(str(item.get("wo10_state", "UNAVAILABLE")))
        + '</span></div><dl class="detail-list"><dt>Eligibility</dt><dd>'
        + escape(str(item.get("downstream_eligibility", "UNAVAILABLE")))
        + "</dd><dt>Reason codes</dt><dd>" + escape(reason_text or "NONE")
        + "</dd><dt>Policy</dt><dd>"
        + escape(str(item.get("wo10_policy_identity", "UNAVAILABLE"))) + " / "
        + escape(str(item.get("wo10_policy_version", "UNAVAILABLE")))
        + "</dd><dt>WO-10 result</dt><dd>"
        + escape(str(item.get("wo10_result_identity", "UNAVAILABLE")))
        + "</dd><dt>WO-11 member</dt><dd>"
        + escape(str(item.get("member_identity", "UNAVAILABLE")))
        + "</dd></dl></article>"
    )


def render_intraday_wo12(
    snapshot: BrowserWorkspaceSnapshot,
    status: dict[str, object],
) -> str:
    """Render restored four-criterion analytical promotion without evaluation."""

    restored = status.get("restored_result")
    if type(restored) is not dict:
        content = (
            '<div class="empty"><div><strong>'
            + escape(str(status.get("state", "NOT_YET_RUN")))
            + "</strong><br>No persisted WO-12 V2 analytical-promotion result.</div></div>"
        )
    else:
        criteria = restored.get("criteria", [])
        criterion_rows = "".join(
            "<tr><td>" + escape(str(item.get("identity", "UNAVAILABLE")))
            + "</td><td>" + escape(str(item.get("state", "UNAVAILABLE")))
            + "</td><td>" + escape(str(item.get("reason", "UNAVAILABLE")))
            + "</td></tr>"
            for item in criteria
            if type(item) is dict
        )
        unavailable = restored.get("unavailable_criteria", [])
        gates = restored.get("hard_gates", [])
        content = (
            '<section class="panel"><div class="panel-head"><div><h2>'
            + escape(str(restored.get("canonical_subject_identity", "UNAVAILABLE")))
            + "</h2><p>" + escape(str(restored.get("market_family", "UNAVAILABLE")))
            + " · Direction " + escape(str(restored.get("inherited_direction", "UNAVAILABLE")))
            + '</p></div><span class="status neutral">'
            + escape(str(restored.get("classification", "NO_SETUP")))
            + "</span></div>"
            '<dl class="detail-list"><dt>Source WO-11 publication</dt><dd>'
            + escape(str(restored.get("source_wo11_publication_identity", "UNAVAILABLE")))
            + "</dd><dt>Source WO-11 member</dt><dd>"
            + escape(str(restored.get("source_wo11_member_identity", "UNAVAILABLE")))
            + "</dd><dt>Boundary / phase</dt><dd>"
            + escape(str(restored.get("analysis_boundary", "UNAVAILABLE")))
            + " · " + escape(str(restored.get("phase", "UNAVAILABLE")))
            + "</dd><dt>Satisfied criteria</dt><dd>"
            + escape(str(restored.get("satisfied_count", 0))) + " / 4"
            + "</dd><dt>Unavailable criteria</dt><dd>"
            + escape(_list_text(unavailable))
            + "</dd><dt>Hard gate</dt><dd>" + escape(_list_text(gates))
            + "</dd><dt>WO-13 eligibility</dt><dd>"
            + escape(str(restored.get("wo13_eligibility", "NOT_ELIGIBLE_FOR_WO13_STEP31")))
            + "</dd><dt>Policy</dt><dd>"
            + escape(str(restored.get("policy_identity", "UNAVAILABLE"))) + " / "
            + escape(str(restored.get("policy_version", "UNAVAILABLE")))
            + "</dd><dt>Result identity / integrity</dt><dd>"
            + escape(str(restored.get("result_identity", "UNAVAILABLE"))) + " · "
            + escape(str(restored.get("result_integrity", "UNAVAILABLE")))
            + "</dd></dl>"
            '<div class="table-wrap"><table><thead><tr><th>Criterion</th><th>State</th>'
            "<th>Factual reason</th></tr></thead><tbody>" + criterion_rows
            + "</tbody></table></div></section>"
        )
    body = (
        _intraday_tabs(False, active="wo12")
        + '<div class="intraday-warning"><strong>WO-12 KR-370 ANALYTICAL PROMOTION</strong>'
        "<span>FOUR COMPLETED-15M CRITERIA · READ-ONLY RESTORED STATE · EXPLICIT SPONSOR CONTROL ONLY</span></div>"
        + content
        + '<div class="intraday-review-config"><strong>Contract:</strong> '
        + escape(str(status.get("request_contract_identity", "UNAVAILABLE")))
        + " / " + escape(str(status.get("request_contract_version", "UNAVAILABLE")))
        + "<br><strong>Active operation:</strong> "
        + escape(str(status.get("active_operation_identity") or "NONE"))
        + "<br><strong>Progression boundary:</strong> Only NOW classifications are eligible to progress to WO-13 / Step 31 Trade Construction."
        + "</div>"
    )
    return render_browser_page(
        title="Intraday WO-12",
        subtitle="Persisted four-criterion analytical promotion; rendering performs no analytical work.",
        snapshot=snapshot,
        active_nav="Intraday",
        active_tab="WO-12",
        body=body,
        extra_styles=_INTRADAY_CSS,
    )


def _list_text(value: object) -> str:
    return ", ".join(str(item) for item in value) if type(value) is list and value else "NONE"


def _review_v2_projection(
    snapshot: IntradayReviewV2Snapshot | None,
    available_run: ProbablesRunV2 | None,
) -> str:
    if snapshot is None:
        return ""
    cards = "".join(
        _review_v2_candidate(item, index)
        for index, item in enumerate(snapshot.candidates, start=1)
    )
    empty = (
        '<div class="empty"><div><strong>No V2 Review cycles created</strong>'
        'Phase A requires an explicit Sponsor operation against one exact persisted run.'
        '</div></div>'
        if not cards else cards
    )
    control = ""
    if available_run is not None:
        methodology = available_run.methodology
        control = (
            '<div class="intraday-review-v2-control"><button type="button" '
            'id="intraday-create-review-v2" data-run="'
            + escape(available_run.run_identity, quote=True)
            + '" data-methodology="' + escape(methodology.methodology_identity, quote=True)
            + '" data-methodology-version="' + escape(methodology.methodology_version, quote=True)
            + '" data-methodology-publication="' + escape(methodology.publication_identity, quote=True)
            + '" data-methodology-checksum="' + escape(methodology.payload_checksum, quote=True)
            + '">CREATE V2 REVIEW CYCLES</button><span>Exact persisted run · '
            + escape(available_run.run_identity) + '</span></div>'
        )
    phase_b = ""
    if snapshot.candidates and all(item.chart_state == "CHART_READY" for item in snapshot.candidates):
        if snapshot.question_transport_identity is None:
            phase_b = (
                '<form class="intraday-review-v2-control" method="post" action="'
                + REVIEW_V2_QUESTION_TRANSPORT_ROUTE
                + '"><button type="submit">CREATE V2 COMBINED QUESTION PDF</button>'
                '<span>Exact V2 cycles · charts · packs · one transport</span></form>'
            )
        else:
            phase_b = (
                '<div class="intraday-review-v2-control"><strong>V2 QUESTION TRANSPORT READY</strong>'
                '<span>CURRENT QUESTION PACK: ' + escape(snapshot.question_filename or "")
                + '<br>EXPECTED ANSWER: ' + escape(snapshot.expected_answer_filename or "")
                + '<br>CANDIDATES: ' + str(len(snapshot.candidates))
                + '<br>Transport · ' + escape(snapshot.question_transport_identity)
                + '</span><label class="intraday-file-choice" tabindex="0" '
                'for="intraday-v2-batch-answer">UPLOAD V2 ANSWERS</label>'
                '<input id="intraday-v2-batch-answer" class="intraday-batch-answer-input" '
                'type="file" accept="application/json,.json" '
                'data-review-v2-batch-answer-upload="'
                + REVIEW_V2_ANSWER_IMPORT_ROUTE
                + '"></div>'
            )
    return (
        '<section class="intraday-review-v2"><div class="intraday-review-v2-head"><div>'
        '<h2>PHASE-A REVIEW · PROBABLES V2/V2.1</h2>'
        '<p>Review Cycle → Chart Required. Review Packs and Question Packs begin only after real chart intake.</p>'
        '</div><span class="intraday-review-toolbar-note">Cycles · '
        + str(len(snapshot.candidates)) + '</span></div><div class="intraday-review-v2-grid">'
        + empty + '</div>' + control + phase_b + '</section>'
    )


def _review_v2_candidate(item, slot_index: int) -> str:  # type: ignore[no-untyped-def]
    target_identity = f"intraday-v2-chart-slot-{slot_index}"
    input_identity = f"intraday-v2-chart-file-{slot_index}"
    cycle = quote(item.cycle_identity, safe="")
    if item.chart_revision_ordinal is None:
        chart_content = (
            '<div><span class="paste-key">⌘V</span><strong>PASTE / UPLOAD CHART</strong>'
            '<span>TRADINGVIEW 4-CHART IMAGE · MISSING</span>'
            '<span class="required-panels">Required: 1D · 1H · 15M · 5M</span></div>'
        )
        received_class = ""
        replace_action = ""
    else:
        chart_content = (
            '<div class="intraday-chart-received"><strong>TRADINGVIEW 4-CHART IMAGE · RECEIVED</strong>'
            '<span>' + escape(item.canonical_subject_identity) + '</span><span>Chart Revision · REV '
            + f"{item.chart_revision_ordinal:03d}"
            + '</span></div>'
        )
        received_class = " received"
        replace_action = (
            '<button class="intraday-replace-chart" type="button" data-target="'
            + target_identity + '">Replace</button>'
        )
    upload = (
        '<div class="intraday-review-section-title">TRADINGVIEW CHARTS</div>'
        '<div id="' + target_identity + '" class="intraday-drop' + received_class
        + '" role="button" tabindex="0" aria-label="Paste TradingView 1D 1H 15M 5M chart composite for '
        + escape(item.canonical_subject_identity)
        + '" data-upload-url="' + REVIEW_V2_CHART_ROUTE + '?cycle=' + cycle + '">'
        + chart_content + '</div><div class="intraday-chart-slot-actions">'
        + replace_action
        + '<label class="intraday-file-choice" for="' + input_identity + '">Choose File</label>'
        '<input id="' + input_identity + '" class="intraday-chart-input" type="file" '
        'accept="image/png,image/jpeg" aria-label="Choose 1D 1H 15M 5M chart composite" '
        'data-target="' + target_identity + '"></div>'
    )
    return (
        '<article class="intraday-review-v2-card"><h3>'
        + escape(item.sponsor_label)
        + '</h3><span class="direction '
        + ("direction-long" if item.direction == "LONG" else "direction-short")
        + '">' + escape(item.direction) + '</span><br><span class="phase-a">'
        + escape(item.chart_state.replace("_", " ")) + '</span>'
        + '<p class="intraday-review-lineage">Canonical subject · '
        + escape(item.canonical_subject_identity)
        + '<br>Methodology · ' + escape(item.methodology_identity) + " / "
        + escape(item.methodology_version)
        + '<br>Source analysis boundary · ' + escape(_ist_time(item.analysis_boundary))
        + '<br>Phase · ' + escape(item.phase)
        + '<br>Review · ' + escape(item.review_state.replace("_", " "))
        + '<br>Review Pack · ' + escape(item.review_pack_state.replace("_", " "))
        + '<br>Question Pack · ' + escape(item.question_pack_state.replace("_", " "))
        + '<br>Answer · ' + escape(item.answer_state.replace("_", " "))
        + '<br>Visual Identity · ' + escape(item.visual_identity_state.replace("_", " "))
        + '<br>Visual Evidence · ' + escape(item.visual_evidence_state.replace("_", " "))
        + ("" if item.nifty_applicability is None else '<br>NIFTY · ' + escape(item.nifty_applicability))
        + ("" if item.mcx_commissioning_state is None else '<br>MCX commissioning · ' + escape(item.mcx_commissioning_state))
        + '</p>' + upload
        + '<details class="intraday-review-diagnostics"><summary>V2 LINEAGE</summary>'
        + 'Cycle · ' + escape(item.cycle_identity)
        + '<br>Probables Result · ' + escape(item.probable_result_identity)
        + ("" if item.chart_revision_identity is None else '<br>Chart Revision · ' + escape(item.chart_revision_identity))
        + ("" if item.answer_pack_identity is None else '<br>Answer Pack · ' + escape(item.answer_pack_identity))
        + ("" if item.visual_evidence_identity is None else '<br>Visual Evidence · ' + escape(item.visual_evidence_identity))
        + ("" if item.observed_visible_subject_identity is None else '<br>Observed identity · ' + escape(item.observed_visible_subject_identity))
        + ("" if item.resolved_canonical_subject_identity is None else '<br>Resolved canonical · ' + escape(item.resolved_canonical_subject_identity))
        + ("" if item.visual_identity_publication_version is None else '<br>DOMAIN-001 publication · ' + escape(item.visual_identity_publication_identity or "") + ' / ' + escape(item.visual_identity_publication_version))
        + '</details></article>'
    )
def _review_v2_control_script() -> str:
    return (
        '<script>(()=>{const b=document.getElementById("intraday-create-review-v2");'
        'if(!b)return;b.addEventListener("click",async()=>{b.disabled=true;'
        'const now=new Date();const stamp=now.toISOString().replace(/[^0-9A-Z]/gi,"").toUpperCase();'
        'const suffix=crypto.getRandomValues(new Uint32Array(1))[0].toString(16).toUpperCase().padStart(8,"0");'
        'const payload={request_identity:`INTRADAY-REVIEW-V2-${stamp}-${suffix}`,'
        'probables_run_identity:b.dataset.run,expected_methodology_identity:b.dataset.methodology,'
        'expected_methodology_version:b.dataset.methodologyVersion,'
        'expected_methodology_publication_identity:b.dataset.methodologyPublication,'
        'expected_methodology_checksum:b.dataset.methodologyChecksum,requested_at:now.toISOString(),'
        'source:"' + ReviewV2OperationSource.SPONSOR_BROWSER_CONTROL.value + '",'
        'contract_identity:"' + REVIEW_V2_CREATE_REQUEST_IDENTITY + '",'
        'contract_version:"' + REVIEW_V2_CREATE_REQUEST_VERSION + '"};'
        'try{const r=await fetch("' + REVIEW_V2_CREATE_ROUTE + '",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});'
        'if(!r.ok)throw new Error(await r.text());location.assign("/intraday/review");}'
        'catch(e){b.disabled=false;window.alert("V2 Review request failed: "+String(e));}});})();</script>'
    )


def _review_candidate(
    item,
    reconciliation: ReconciliationCandidateSnapshot | None,
    slot_index: int,
) -> str:
    direction_class = "direction-long" if item.direction == "LONG" else "direction-short"
    result = quote(item.probable_result_identity, safe="")
    target_identity = f"intraday-chart-slot-{slot_index}"
    input_identity = f"intraday-chart-file-{slot_index}"
    chart_state = (
        "CHART REQUIRED"
        if item.chart_revision_ordinal is None
        else f"CHART READY · REV {item.chart_revision_ordinal:03d}"
    )
    pack_state = "NOT CREATED" if item.review_pack_identity is None else "CREATED"
    if item.chart_revision_ordinal is None:
        chart_content = (
            '<div><span class="paste-key">⌘V</span><strong>PASTE / UPLOAD CHART</strong>'
            '<span>TRADINGVIEW 4-CHART IMAGE · MISSING</span>'
            '<span class="required-panels">Required: 1D · 1H · 15M · 5M</span></div>'
        )
        chart_actions = ""
        received_class = ""
    else:
        chart_content = (
            '<div class="intraday-chart-received"><strong>TRADINGVIEW 4-CHART IMAGE · RECEIVED</strong>'
            '<span>' + escape(item.canonical_subject_identity) + '</span>'
            f'<span>Chart Revision · REV {item.chart_revision_ordinal:03d}</span></div>'
        )
        chart_actions = (
            '<button class="intraday-replace-chart" type="button" data-target="'
            + target_identity + '">Replace</button>'
        )
        received_class = " received"
    action = (
        '<div class="intraday-review-section-title">TRADINGVIEW CHARTS</div>'
        '<div id="' + target_identity + '" class="intraday-drop' + received_class
        + '" role="button" tabindex="0" aria-label="Paste TradingView 1D 1H 15M 5M chart composite for '
        + escape(item.canonical_subject_identity)
        + '" data-upload-url="/intraday/review/chart?result=' + result + '">'
        + chart_content + '</div><div class="intraday-chart-slot-actions">'
        + chart_actions
        + '<label class="intraday-file-choice" for="' + input_identity + '">Choose File</label>'
        '<input id="' + input_identity + '" class="intraday-chart-input" type="file" '
        'accept="image/png,image/jpeg" aria-label="Choose 1D 1H 15M 5M chart composite" '
        'data-target="' + target_identity + '"></div>'
    )
    if item.cycle_identity is not None:
        cycle = quote(item.cycle_identity, safe="")
        if item.chart_revision_ordinal is not None:
            action += (
                '<form method="post" action="/intraday/review/question-pack?cycle='
                + cycle
                + '"><button type="submit">CREATE PDF</button></form>'
            )
        if item.review_pack_filename is not None:
            action += '<span class="intraday-review-lineage">' + escape(item.review_pack_filename) + '</span>'
            action += (
                '<form method="post" action="/intraday/review/answer?cycle=' + cycle
                + '"><button type="submit">IMPORT EXPECTED INBOX ANSWER</button></form>'
                '<label class="intraday-file-choice" tabindex="0" for="answer-' + input_identity
                + '">UPLOAD ANSWER</label><input id="answer-' + input_identity
                + '" class="intraday-chart-input" type="file" accept="application/json,.json" '
                + 'data-review-answer-upload="/intraday/review/answer?cycle=' + cycle + '">'
                '<span class="intraday-review-lineage">Expected Answer · '
                + escape(item.answer_filename or "UNAVAILABLE") + '</span>'
            )
        if item.visual_evidence_identity is not None:
            action += (
                '<form method="post" action="/intraday/review/reconcile?cycle=' + cycle
                + '"><button type="submit">RECONCILE REVIEW</button></form>'
            )
    analytical = "" if reconciliation is None else _analytical_projection(reconciliation)
    return (
        '<article class="intraday-review-card"><div class="intraday-review-head"><h2>'
        + escape(item.canonical_subject_identity)
        + '</h2><span class="direction ' + direction_class + '">' + escape(item.direction)
        + '</span></div><span class="intraday-review-required">REVIEW REQUIRED</span>'
        '<div class="intraday-probable-context"><strong>PROBABLE CONTEXT</strong>1H '
        + escape(item.one_hour_context) + " · 15M " + escape(item.fifteen_minute_context)
        + " · COHERENCE " + escape(item.coherence_context)
        + " · PARTICIPATION " + escape(item.participation_state)
        + '</div><div class="intraday-review-status">'
        + _review_status("Chart", chart_state)
        + _review_status("Visual Evidence", item.visual_state.replace("_", " "))
        + _review_status("Question Pack", pack_state)
        + _review_status("Answer", item.answer_state.replace("_", " "))
        + '</div><p class="intraday-review-lineage">Analysis boundary · '
        + escape(_ist_time(item.observation_boundary))
        + '</p><div class="intraday-review-actions">' + action + '</div>'
        '<details class="intraday-review-diagnostics"><summary>IDENTITY / DIAGNOSTICS</summary>Probables · '
        + escape(item.probables_run_identity)
        + ('<br>Observed visible identity · ' + escape(item.observed_visible_subject_identity) if item.observed_visible_subject_identity else '')
        + ('<br>Visual Evidence · ' + escape(item.visual_evidence_identity) if item.visual_evidence_identity else '')
        + ('<br>Review Cycle · ' + escape(item.cycle_identity) if item.cycle_identity else '')
        + '</details>' + _visual_answer_projection(item.visual_answers) + analytical + '</article>'
    )


def _review_presentation_sort_key(item) -> tuple[str, str]:  # type: ignore[no-untyped-def]
    identity = item.canonical_subject_identity
    for prefix in ("NSE-EQ-", "NSE-INDEX-", "MCX-SUBJECT-"):
        if identity.startswith(prefix):
            identity = identity.removeprefix(prefix)
            break
    return identity.casefold(), identity


def _analytical_projection(item: ReconciliationCandidateSnapshot) -> str:
    conditions = (
        '<span class="intraday-review-lineage">None</span>'
        if not item.remaining_conditions
        else "".join(
            '<span class="intraday-review-lineage"><strong>' + escape(identity)
            + '</strong> · ' + escape(classification) + ' · ' + escape(question) + '</span>'
            for identity, classification, question in item.remaining_conditions
        )
    )
    facts = "".join(
        '<tr><td>' + escape(question) + '</td><td>' + escape(status) + '</td><td>'
        + escape(answer) + '</td><td>' + escape(relationship) + '</td><td>' + escape(role)
        + '</td></tr>'
        for question, status, answer, relationship, role in item.facts
    )
    return (
        '<div class="intraday-review-section-title">RECONCILIATION / ANALYTICAL STATE</div>'
        '<div class="intraday-review-status">'
        + _review_status("Review", item.review_state.replace("_", " "))
        + _review_status("Readiness", item.readiness_state.replace("_", " "))
        + _review_status("Promotion", item.promotion_state.replace("_", " "))
        + '</div><div class="intraday-review-actions"><strong class="intraday-review-lineage">REMAINING / ADVERSE CONDITIONS</strong>'
        + conditions + '</div>'
        + ("" if not facts else '<details class="intraday-review-diagnostics"><summary>NATIVE / VISUAL RECONCILIATION FACTS</summary>'
           '<div class="table-scroll"><table class="intraday-table"><thead><tr><th>Question</th><th>Status</th><th>Visual observation</th><th>Relationship</th><th>Role</th></tr></thead><tbody>'
           + facts + '</tbody></table></div></details>')
    )


def _review_batch_result(result: IntradayReviewBatchResult) -> str:
    members = "".join(
        '<span><strong>' + escape(item.canonical_subject_identity) + "</strong> · "
        + escape(item.state.value.replace("_", " "))
        + (" · " + escape(item.detail) if item.detail is not None else "")
        + "</span>"
        for item in result.members
    )
    return (
        '<section class="intraday-batch-result"><h2>CREATE ALL REVIEW PDF · '
        + escape(result.state.value.replace("_", " "))
        + '</h2><div class="intraday-batch-accounting">'
        + f"<span>Created <strong>{result.created_count}</strong></span>"
        + f"<span>Reused <strong>{result.reused_count}</strong></span>"
        + f"<span>Skipped <strong>{result.skipped_count}</strong></span>"
        + f"<span>Failed <strong>{result.failed_count}</strong></span>"
        + '</div><div class="intraday-batch-members">' + members + "</div>"
        + (
            ""
            if result.batch_filename is None
            else '<p class="intraday-review-lineage">Combined Sponsor PDF · '
            + escape(result.batch_filename) + "</p>"
        )
        + (
            ""
            if result.batch_error is None
            else '<p class="intraday-review-lineage">Batch transport · '
            + escape(result.batch_error) + "</p>"
        )
        + "</section>"
    )


def _review_status(label: str, value: str) -> str:
    return '<div><span>' + escape(label) + '</span><strong>' + escape(value) + '</strong></div>'


def _visual_answer_projection(answers: tuple[tuple[str, str, str, str], ...]) -> str:
    if not answers:
        return ""
    rows = "".join(
        '<tr><th>' + escape(question) + '</th><td>' + escape(status.replace("_", " "))
        + '</td><td>' + escape(answer.replace("_", " ")) + '</td><td>' + escape(basis) + '</td></tr>'
        for question, status, answer, basis in answers
    )
    return (
        '<details class="intraday-review-diagnostics"><summary>IMPORTED Q1-Q10 VISUAL EVIDENCE</summary>'
        '<div class="table-scroll"><table class="intraday-table"><thead><tr><th>Q</th><th>Status</th>'
        '<th>Answer</th><th>Visible basis</th></tr></thead><tbody>' + rows + '</tbody></table></div></details>'
    )


def _answer_import_result(
    individual: IntradayAnswerImportResult | None,
    batch: IntradayAnswerBatchResult | None,
) -> str:
    members = (individual,) if individual is not None else (() if batch is None else batch.members)
    rows = "".join(
        '<span><strong>' + escape(item.canonical_subject_identity) + '</strong> · '
        + escape(item.state.value.replace("_", " "))
        + (' · ' + escape(item.detail) if item.detail else '') + '</span>'
        for item in members
    )
    if batch is None:
        summary = "INDIVIDUAL ANSWER IMPORT"
    elif batch.transport_state == "MISSING":
        return (
            '<section class="intraday-batch-result"><h2>COMBINED ANSWER: MISSING</h2>'
            '<div class="intraday-batch-members"><span><strong>Expected:</strong> '
            + escape(batch.answer_filename or "UNAVAILABLE")
            + '</span><span><strong>Candidates:</strong> '
            + str(batch.eligible_candidates)
            + '</span></div></section>'
        )
    else:
        summary = (
            f"BATCH ANSWER FOUND · {batch.transport_state} · Candidates {batch.eligible_candidates} · Files {batch.files_discovered} · "
            f"Imported {batch.count(AnswerImportState.IMPORTED)} · "
            f"Already imported {batch.count(AnswerImportState.ALREADY_IMPORTED)} · "
            f"Missing {batch.count(AnswerImportState.MISSING)} · "
            f"Invalid {batch.count(AnswerImportState.INVALID)} · "
            f"Identity mismatch {batch.count(AnswerImportState.IDENTITY_MISMATCH)} · "
            f"Schema invalid {batch.count(AnswerImportState.SCHEMA_INVALID)} · "
            f"Conflict {batch.count(AnswerImportState.CONFLICT)} · "
            f"Extra {batch.extra_candidates} · Duplicate {batch.duplicate_candidates}"
        )
    return (
        '<section class="intraday-batch-result"><h2>' + escape(summary)
        + '</h2><div class="intraday-batch-members">' + rows + '</div></section>'
    )


def _reconciliation_result(
    individual: ReconciliationMemberResult | None,
    batch: ReconciliationBatchResult | None,
) -> str:
    if individual is None and batch is None:
        return ""
    members = (individual,) if individual is not None else batch.members
    rows = "".join(
        '<span><strong>' + escape(item.canonical_subject_identity) + '</strong> · '
        + escape(item.state.value.replace("_", " "))
        + ("" if item.review_state is None else " · " + escape(item.review_state.replace("_", " ")))
        + ("" if item.readiness_state is None else " · " + escape(item.readiness_state.replace("_", " ")))
        + ("" if item.detail is None else " · " + escape(item.detail)) + '</span>'
        for item in members
    )
    return (
        '<section class="intraday-batch-result"><h2>'
        + ("INDIVIDUAL RECONCILIATION" if individual is not None else "RECONCILE ALL READY REVIEWS")
        + '</h2><div class="intraday-batch-members">' + rows + '</div></section>'
    )


def _review_upload_script() -> str:
    return """<script>
(()=>{
const acceptedCharts=new Set(['image/png','image/jpeg']);
async function receiveChart(target,file){
  if(!file||!acceptedCharts.has(file.type)){alert('Paste or choose a PNG or JPEG image.');return;}
  target.setAttribute('aria-busy','true');
  try{const response=await fetch(target.dataset.uploadUrl,{method:'POST',headers:{'Content-Type':file.type},body:file});
    if(!response.ok)throw new Error();location.reload();
  }catch(_error){target.removeAttribute('aria-busy');alert('Chart could not be accepted.');}
}
for(const target of document.querySelectorAll('.intraday-drop')){
  target.addEventListener('click',()=>target.focus());
  target.addEventListener('paste',event=>{
    const items=event.clipboardData&&Array.from(event.clipboardData.items||[]);
    const image=items&&items.find(item=>item.kind==='file'&&acceptedCharts.has(item.type));
    if(!image){alert('No supported chart image was found on the clipboard.');return;}
    event.preventDefault();receiveChart(target,image.getAsFile());
  });
}
for(const button of document.querySelectorAll('.intraday-replace-chart')){
  button.addEventListener('click',()=>{
    const target=document.getElementById(button.dataset.target);if(!target)return;
    target.classList.add('replace-ready');target.focus();
  });
}
for(const input of document.querySelectorAll('.intraday-chart-input')){
  input.addEventListener('change',()=>{
    const target=document.getElementById(input.dataset.target);
    const file=input.files&&input.files[0];if(target&&file)receiveChart(target,file);
  });
}
document.querySelectorAll('[data-review-answer-upload]').forEach(input=>{
  input.addEventListener('change',async()=>{
    const file=input.files[0];
    if(!file||(!file.name.toLowerCase().endsWith('.json')&&!['application/json','text/json'].includes(file.type))){alert('Choose a JSON Answer Pack.');return;}
    const response=await fetch(input.dataset.reviewAnswerUpload,{method:'POST',headers:{'Content-Type':'application/json'},body:file});
    if(!response.ok){alert('Answer upload rejected.');return;}
    document.open();document.write(await response.text());document.close();
  });
});
document.querySelectorAll('[data-review-batch-answer-upload]').forEach(input=>{
  input.addEventListener('change',async()=>{
    const file=input.files[0];
    if(!file||(!file.name.toLowerCase().endsWith('.json')&&!['application/json','text/json'].includes(file.type))){alert('Choose one combined JSON Answer Pack.');return;}
    const uploadUrl=input.dataset.reviewBatchAnswerUpload+'?filename='+encodeURIComponent(file.name);
    const response=await fetch(uploadUrl,{method:'POST',headers:{'Content-Type':'application/json'},body:file});
    if(!response.ok){alert('Combined Answer upload rejected.');return;}
    document.open();document.write(await response.text());document.close();
  });
});
document.querySelectorAll('[data-review-v2-batch-answer-upload]').forEach(input=>{
  input.addEventListener('change',async()=>{
    const file=input.files[0];
    if(!file||(!file.name.toLowerCase().endsWith('.json')&&!['application/json','text/json'].includes(file.type))){alert('Choose one combined V2 JSON Answer Pack.');return;}
    const response=await fetch(input.dataset.reviewV2BatchAnswerUpload,{method:'POST',headers:{'Content-Type':'application/json'},body:file});
    if(!response.ok){alert('V2 combined Answer upload rejected.');return;}
    document.open();document.write(await response.text());document.close();
  });
});
})();
</script>"""


def render_intraday_triage(
    snapshot: IntradayWorkstationSnapshot | IntradayDiscoverySnapshot,
    *,
    refresh_enabled: bool = False,
) -> str:
    if isinstance(snapshot, IntradayDiscoverySnapshot):
        return _render_discovery_triage(snapshot, refresh_enabled=refresh_enabled)
    warning = ('<div class="intraday-warning"><strong>ENGINEERING / EVIDENCE</strong>'
               '<span>NO TRADING CONCLUSION — EVIDENCE WORKSTATION</span></div>')
    if snapshot.selected_instrument is None:
        return warning + _unavailable(
            "RELIANCE",
            snapshot.runtime_detail or "UNAVAILABLE — no governed DOMAIN-001 publication.",
        )
    identity = snapshot.selected_instrument.canonical.canonical_instrument_id
    state = snapshot.availability
    if snapshot.evidence is None:
        label = "DATA INCOMPLETE" if state == "DATA_INCOMPLETE" else "UNAVAILABLE"
        return warning + (
            '<section class="intraday-card"><h2>' + escape(identity) + '</h2>'
            '<p class="intraday-status"><strong>' + label + '</strong> — '
            + escape(snapshot.runtime_detail or "Governed evidence is unavailable.") + '</p></section>'
        )
    bundle = snapshot.evidence
    events = []
    for timeframe in (IntradayTimeframe.FIFTEEN_MINUTES, IntradayTimeframe.FIVE_MINUTES):
        evidence = next((item for item in bundle.structural_evidence if item.timeframe is timeframe), None)
        fact = _latest_fact(() if evidence is None else evidence.facts)
        value = "No factual structural event" if fact is None else fact.fact_type.value
        events.append(f'<div class="event"><strong>{timeframe.value}</strong> · {escape(value)}</div>')
    participation = "UNAVAILABLE"
    for evidence in bundle.shadow_telemetry:
        for measure in evidence.measures:
            if measure.telemetry_type is TelemetryType.RECENT_VOLUME_COMPARISON:
                values = {item.name: item.value for item in measure.values}
                ratio = values.get("volume_ratio")
                if ratio is not None:
                    participation = f"5M volume ratio {format(ratio, 'f')} · {measure.comparison.value}"
    return warning + (
        '<p class="intraday-status">Latest completed factual event — '
        '<strong>PRESENTATION SELECTION ONLY</strong></p>'
        '<section class="intraday-card"><h2>' + escape(identity) + '</h2>'
        + ''.join(events) + '<div class="event"><strong>Participation</strong> · '
        + escape(participation) + '</div><a class="detail-link" href="/intraday/evidence/'
        + escape(identity) + '">DETAILED EVIDENCE →</a></section>'
    )


def _render_discovery_triage(
    snapshot: IntradayDiscoverySnapshot,
    *,
    refresh_enabled: bool,
) -> str:
    last = _analysis_time(snapshot.last_successful_analysis)
    failure_text = {
        "PUBLICATION_STALE": (
            "Discovery could not run because the selected observation boundary "
            "predates the active Intraday universe publication."
        ),
    }.get(snapshot.current_failure, _plain(snapshot.current_failure or ""))
    failure = "" if snapshot.current_failure is None else (
        '<div class="intraday-failure"><strong>CURRENT RUN FAILURE</strong> · '
        + escape(failure_text) + "</div>"
    )
    probable_snapshot = snapshot.probables
    if probable_snapshot is not None and probable_snapshot.current_failure is not None:
        failure += (
            '<div class="intraday-failure"><strong>CURRENT PROBABLES FAILURE</strong> · '
            + escape(_plain(probable_snapshot.current_failure))
            + " · last successful Probables remain preserved.</div>"
        )
    probable_run = None if probable_snapshot is None else probable_snapshot.run
    probable_v2_snapshot = snapshot.probables_v2
    probable_v2_run = (
        None if probable_v2_snapshot is None else probable_v2_snapshot.run
    )
    if probable_v2_snapshot is not None and probable_v2_snapshot.current_failure is not None:
        detail = probable_v2_snapshot.failure_detail
        detail_projection = ""
        if detail is not None:
            affected = detail.affected_canonical_subject_identity or "NOT IDENTIFIED"
            detail_projection = (
                "<br>Stage: " + escape(_plain(detail.operation_stage))
                + " · Reason: " + escape(_plain(detail.typed_reason_code))
                + " · Affected: " + escape(affected)
                + " · Diagnostic ID: " + escape(detail.failure_identity)
            )
        failure += (
            '<div class="intraday-failure"><strong>PROBABLES REFRESH FAILURE</strong> · '
            + escape(_plain(probable_v2_snapshot.current_failure))
            + detail_projection
            + " · exact last successful V2 evidence remains preserved.</div>"
        )
    if probable_v2_run is not None:
        return _render_probables_v2_triage(
            snapshot,
            probable_v2_run,
            refresh_enabled=refresh_enabled,
            last=last,
            failure=failure,
        )
    if probable_v2_snapshot is not None:
        legacy = (
            " LEGACY V1 LAST SUCCESSFUL ANALYSIS · "
            + _ist_time(probable_run.observation_boundary)
            + ". V1 evidence is retained separately for history and is not "
            "the commissioned V2 analysis."
            if probable_run is not None
            else ""
        )
        return (
            _intraday_tabs(refresh_enabled)
            + failure
            + '<div class="intraday-methodology"><strong>PHASE-AWARE V2 · '
            'NOT YET RUN</strong> No commissioned V2 analytical run is loaded.'
            + escape(legacy)
            + ' Explicit Sponsor Refresh is required; no population or candidate '
            'result is projected.</div>'
        )
    if probable_snapshot is None:
        metrics = (
            ("Universe", snapshot.universe_count),
            ("Long Probables", 0),
            ("Short Probables", 0),
            ("Not Admitted", 0),
            ("Unavailable", snapshot.prerequisite_unavailable_count),
            ("Population", "—"),
        )
        probable_note = (
            '<div class="intraday-methodology"><strong>Candidate-admission methodology '
            'is not yet commissioned.</strong> Factual availability is not an opportunity; '
            'no candidates are manufactured for presentation.</div>'
        )
    elif probable_run is None:
        metrics = (
            ("Universe", snapshot.universe_count),
            ("Long Probables", 0),
            ("Short Probables", 0),
            ("Not Admitted", 0),
            ("Unavailable", snapshot.prerequisite_unavailable_count),
            ("Population", "—"),
        )
        probable_note = (
            '<div class="intraday-methodology"><strong>V0 Probables methodology '
            'commissioned.</strong> No successful governed Probables run is loaded. '
            'Browser refresh does not create an analytical run.</div>'
        )
    else:
        diagnostics = probable_run.diagnostics
        metrics = (
            ("Universe", diagnostics.starting_population),
            ("Long Probables", diagnostics.long_probables),
            ("Short Probables", diagnostics.short_probables),
            ("Not Admitted", diagnostics.not_admitted_count),
            ("Unavailable", diagnostics.unavailable_count),
            ("Population", diagnostics.population_bucket.value),
        )
        probable_note = (
            '<div class="intraday-methodology"><strong>V0 Probables methodology · '
            + escape(probable_run.methodology_version)
            + '</strong> · Last successful analysis '
            + escape(_ist_time(probable_run.observation_boundary))
            + '. Probable means selected for deeper review only; no trading authority.</div>'
        )
    metric_html = '<div class="status-strip intraday-summary">' + "".join(
        '<div class="status-item' + (' status-top' if label == 'Population' else '')
        + '"><span>' + escape(label) + '</span><strong>' + escape(str(value))
        + "</strong></div>"
        for label, value in metrics
    ) + "</div>"
    available = tuple(item for item in snapshot.members if item.prerequisite_ready)
    probable_members = tuple(
        item for item in available
        if item.probable_result is not None
        and item.probable_result.state in (
            ProbableState.LONG_PROBABLE,
            ProbableState.SHORT_PROBABLE,
        )
    )
    unavailable = tuple(
        item for item in snapshot.members
        if not item.prerequisite_ready
        or (
            item.probable_result is not None
            and item.probable_result.state is ProbableState.UNAVAILABLE
        )
    )
    not_admitted = tuple(
        item for item in snapshot.members
        if item.probable_result is not None
        and item.probable_result.state is ProbableState.NOT_ADMITTED
    )
    equity_probables = tuple(item for item in probable_members if item.market_family != "MCX")
    mcx_probables = tuple(item for item in probable_members if item.market_family == "MCX")
    equity_unavailable = tuple(item for item in unavailable if item.market_family != "MCX")
    mcx_unavailable = tuple(item for item in unavailable if item.market_family == "MCX")
    equity_not_admitted = tuple(item for item in not_admitted if item.market_family != "MCX")
    mcx_not_admitted = tuple(item for item in not_admitted if item.market_family == "MCX")
    diagnostics = None if probable_run is None else probable_run.diagnostics
    return (
        _intraday_tabs(refresh_enabled)
        + '<div class="analysis-batch"><span>Market analysis</span>'
        '<div class="analysis-run-times"><strong>' + escape(last) + '</strong></div></div>'
        + failure
        + metric_html
        + probable_note
        + '<div class="panels intraday-market-panels">'
        + _probables_panel(
            "EQUITIES + INDICES",
            equity_probables,
            equity_unavailable,
            not_admitted=len(equity_not_admitted),
            conflicting=_conflicting_count(equity_not_admitted),
            population="—" if diagnostics is None else diagnostics.population_bucket.value,
            show_unavailable_members=False,
        )
        + _probables_panel(
            "COMMODITIES (MCX)",
            mcx_probables,
            mcx_unavailable,
            not_admitted=len(mcx_not_admitted),
            conflicting=_conflicting_count(mcx_not_admitted),
            population="—" if diagnostics is None else diagnostics.population_bucket.value,
            show_unavailable_members=True,
        )
        + "</div>"
        + _analysis_context(snapshot, probable_run)
    )


def _probable_card(item: IntradayDiscoveryMemberSnapshot) -> str:
    result = item.probable_result
    if result is None:
        return ""
    direction = "UNAVAILABLE" if result.direction is None else result.direction.value
    direction_class = "direction-long" if direction == "LONG" else "direction-short"
    detail = f'/intraday/evidence/{quote(item.canonical_identity, safe="")}'
    return (
        '<article class="opportunity native-opportunity intraday-probable"><div class="opp-head">'
        '<div class="opp-identity"><h3>' + escape(item.sponsor_label) + '</h3>'
        '<span class="setup-family">' + escape(item.canonical_identity) + '</span></div>'
        '<span class="direction ' + direction_class + '">' + escape(direction) + '</span></div>'
        '<div class="summary-reason">'
        + _card_fact("Factual state", "FACTS COMPLETE")
        + _card_fact("1H regime", direction)
        + _card_fact("15M structure", direction)
        + _card_fact("Coherence", direction)
        + _card_fact("Participation", _plain(result.participation_state))
        + '</div><div class="summary-footer"><span class="summary-rr">Selection state '
        '<strong>' + escape(_plain(result.state.value)) + '</strong></span>'
        '<div class="native-opportunity-actions"><a class="button" href="'
        + detail + '">DETAIL →</a></div></div></article>'
    )


def _render_probables_v2_triage(
    snapshot: IntradayDiscoverySnapshot,
    run: ProbablesRunV2,
    *,
    refresh_enabled: bool,
    last: str,
    failure: str,
) -> str:
    """Project persisted V2 facts only; no analytical recomputation occurs."""

    diagnostics = run.diagnostics
    metrics = (
        ("Universe", diagnostics.starting_population),
        ("Long Probables", diagnostics.long_probables),
        ("Short Probables", diagnostics.short_probables),
        ("Not Admitted", diagnostics.not_admitted_count),
        ("Unavailable", diagnostics.unavailable_count),
        ("Population", diagnostics.population_bucket.value),
    )
    metric_html = '<div class="status-strip intraday-summary">' + "".join(
        '<div class="status-item' + (' status-top' if label == 'Population' else '')
        + '"><span>' + escape(label) + '</span><strong>' + escape(str(value))
        + "</strong></div>"
        for label, value in metrics
    ) + "</div>"
    members = {item.canonical_identity: item for item in snapshot.members}
    admitted_states = {ProbableState.LONG_PROBABLE, ProbableState.SHORT_PROBABLE}
    admitted = tuple(
        item
        for item in run.results
        if item.state in admitted_states
        and item.canonical_subject_identity in members
        and members[item.canonical_subject_identity].market_family
        in {"NSE_EQUITY", "NSE_INDEX", "MCX"}
    )
    equity = tuple(
        item
        for item in admitted
        if members[item.canonical_subject_identity].market_family
        in {"NSE_EQUITY", "NSE_INDEX"}
    )
    mcx = tuple(
        item
        for item in admitted
        if members[item.canonical_subject_identity].market_family == "MCX"
    )
    diagnostics_results = tuple(item for item in run.results if item not in admitted)
    equity_long = sum(item.state is ProbableState.LONG_PROBABLE for item in equity)
    equity_short = sum(item.state is ProbableState.SHORT_PROBABLE for item in equity)
    mcx_long = sum(item.state is ProbableState.LONG_PROBABLE for item in mcx)
    mcx_short = sum(item.state is ProbableState.SHORT_PROBABLE for item in mcx)
    market_accounting = (
        '<div class="intraday-market-accounting">'
        + _market_accounting_fact("Equity / Index Long", equity_long)
        + _market_accounting_fact("Equity / Index Short", equity_short)
        + _market_accounting_fact("MCX Long", mcx_long)
        + _market_accounting_fact("MCX Short", mcx_short)
        + "</div>"
    )
    market_groups = (
        '<div class="intraday-opportunities-grid" data-layout="equity-left-mcx-right">'
        + _render_v2_market_group("EQUITY / INDEX", equity, members)
        + _render_v2_market_group("MCX", mcx, members)
        + "</div>"
    )
    phase_counts = " · ".join(
        f"{phase.value} {count}" for phase, count in diagnostics.phase_counts if count
    ) or "NO EVALUABLE PHASE"
    return (
        _intraday_tabs(refresh_enabled)
        + '<div class="analysis-batch"><span>Market analysis</span>'
        '<div class="analysis-run-times"><strong>' + escape(last) + '</strong></div></div>'
        + failure
        + metric_html
        + '<div class="intraday-methodology"><strong>'
        + escape(run.methodology.methodology_identity)
        + ' · ' + escape(run.methodology.methodology_version)
        + '</strong> · ' + escape(_ist_time(run.analysis_boundary))
        + ' · ' + escape(phase_counts)
        + '. Phase-aware admission for deeper review only; no score, rank, confidence, trading, Risk or broker authority.</div>'
        + market_accounting
        + market_groups
        + _render_v2_diagnostics(diagnostics_results, members)
    )


def _probable_v2_card(result, sponsor_label: str) -> str:  # type: ignore[no-untyped-def]
    if result.state not in {ProbableState.LONG_PROBABLE, ProbableState.SHORT_PROBABLE}:
        return ""
    direction = "UNAVAILABLE" if result.direction is None else result.direction.value
    direction_class = (
        "direction-long"
        if result.state is ProbableState.LONG_PROBABLE
        else "direction-short"
    )
    provenance = {
        "OPENING": "PRIOR-SESSION CONTEXT",
        "STRUCTURE": "PRIOR-SESSION CONTEXT",
        "FIRST_CURRENT_SESSION_1H": "FIRST-CURRENT",
        "CURRENT_SESSION_ESTABLISHED": "ESTABLISHED-CURRENT",
    }.get("" if result.phase is None else result.phase.value, "UNAVAILABLE")
    nifty_applicability = getattr(result, "nifty_applicability", None)
    nifty = "NOT APPLICABLE" if (
        nifty_applicability is not None
        and nifty_applicability.value == "NOT_APPLICABLE"
    ) else (
        "UNAVAILABLE"
        if result.nifty_relationship is None
        else result.nifty_relationship.value
    )
    reason = " · ".join(_plain(item.value) for item in result.reasons)
    return (
        '<article class="opportunity native-opportunity intraday-probable"><div class="opp-head">'
        '<div class="opp-identity"><h4>' + escape(sponsor_label) + '</h4>'
        '<span class="setup-family">' + escape(result.canonical_subject_identity) + '</span></div>'
        '<span class="direction ' + direction_class + '">' + escape(direction) + '</span></div>'
        '<div class="summary-reason">'
        + _card_fact("Methodology", result.methodology_version)
        + _card_fact("Phase", "UNAVAILABLE" if result.phase is None else result.phase.value)
        + _card_fact("Boundary", _ist_time(result.analysis_boundary))
        + _card_fact("1H provenance", provenance)
        + _card_fact("NIFTY", nifty)
        + '</div><div class="summary-footer"><span class="summary-rr">Result <strong>'
        + escape(_plain(result.state.value))
        + '</strong></span><span>' + escape(reason) + '</span></div></article>'
    )


def _market_accounting_fact(label: str, value: int) -> str:
    return (
        '<div><span>' + escape(label) + '</span><strong>'
        + escape(str(value)) + '</strong></div>'
    )


def _v2_member_label(result, members) -> str:  # type: ignore[no-untyped-def]
    member = members.get(result.canonical_subject_identity)
    if member is None:
        return result.canonical_subject_identity
    return member.sponsor_label


def _v2_result_sort_key(result, members) -> tuple[str, str, str]:  # type: ignore[no-untyped-def]
    label = _v2_member_label(result, members)
    return (label.casefold(), label, result.canonical_subject_identity)


def _render_v2_market_group(title: str, results, members) -> str:  # type: ignore[no-untyped-def]
    long_results = tuple(
        sorted(
            (item for item in results if item.state is ProbableState.LONG_PROBABLE),
            key=lambda item: _v2_result_sort_key(item, members),
        )
    )
    short_results = tuple(
        sorted(
            (item for item in results if item.state is ProbableState.SHORT_PROBABLE),
            key=lambda item: _v2_result_sort_key(item, members),
        )
    )
    total = len(long_results) + len(short_results)
    market_class = "intraday-market-mcx" if title == "MCX" else "intraday-market-equity"
    empty = (
        '<p class="intraday-market-empty">No current admitted '
        + escape(title if title == "MCX" else title.title()) + ' Probables.</p>'
        if total == 0 else ""
    )
    return (
        '<section class="intraday-market-group ' + market_class + '">'
        '<div class="intraday-market-heading"><h2>' + escape(title) + '</h2><span>'
        + escape(str(total)) + ' admitted Probables</span></div>'
        + empty
        + _render_v2_direction_group("LONG", long_results, members)
        + _render_v2_direction_group("SHORT", short_results, members)
        + '</section>'
    )


def _render_v2_direction_group(direction: str, results, members) -> str:  # type: ignore[no-untyped-def]
    cards = "".join(
        _probable_v2_card(item, _v2_member_label(item, members)) for item in results
    )
    if not cards:
        cards = (
            '<div class="intraday-direction-empty">No current '
            + escape(direction.title()) + ' Probables</div>'
        )
    return (
        '<section class="intraday-direction-group intraday-direction-'
        + direction.casefold() + '"><h3>' + escape(direction) + '</h3>'
        '<p>Alphabetical by Sponsor-facing name</p>' + cards + '</section>'
    )


def _render_v2_diagnostics(results, members) -> str:  # type: ignore[no-untyped-def]
    ordered = sorted(results, key=lambda item: _v2_result_sort_key(item, members))
    rows = "".join(_render_v2_diagnostic_row(item, members) for item in ordered)
    if not rows:
        rows = '<p class="intraday-status">No excluded V2 population diagnostics.</p>'
    return (
        '<details class="intraday-probables-diagnostics"><summary>DIAGNOSTICS · '
        + escape(str(len(ordered)))
        + ' excluded from Sponsor opportunities</summary><div class="intraday-diagnostic-list">'
        + rows + '</div></details>'
    )


def _render_v2_diagnostic_row(result, members) -> str:  # type: ignore[no-untyped-def]
    state = _plain(result.state.value)
    direction = "UNAVAILABLE" if result.direction is None else result.direction.value
    reasons = " · ".join(_plain(item.value) for item in result.reasons) or "NO REASON"
    member = members.get(result.canonical_subject_identity)
    family = "UNKNOWN" if member is None else member.market_family
    return (
        '<div class="intraday-diagnostic-row"><strong>'
        + escape(_v2_member_label(result, members)) + '</strong><span>'
        + escape(state) + '</span><span>' + escape(family)
        + ' · Semantic direction (diagnostic) ' + escape(direction)
        + '</span><span>' + escape(reasons) + '</span></div>'
    )


def _card_fact(label: str, value: str) -> str:
    return (
        '<span class="intraday-card-fact"><span>' + escape(label)
        + '</span><strong>' + escape(value) + '</strong></span>'
    )


def _conflicting_count(
    members: tuple[IntradayDiscoveryMemberSnapshot, ...],
) -> int:
    return sum(
        ProbableReason.DIRECTION_CONFLICTING in item.probable_result.reasons
        for item in members
        if item.probable_result is not None
    )


def _probables_panel(
    title: str,
    probable_members: tuple[IntradayDiscoveryMemberSnapshot, ...],
    unavailable_members: tuple[IntradayDiscoveryMemberSnapshot, ...],
    *,
    not_admitted: int,
    conflicting: int,
    population: str,
    show_unavailable_members: bool,
) -> str:
    cards = "".join(_probable_card(item) for item in probable_members)
    if not cards:
        cards = (
            '<div class="empty"><div><strong>Zero current Probables</strong>'
            'No governed Long or Short Probable is present in this panel.</div></div>'
        )
    unavailable = ""
    if show_unavailable_members and unavailable_members:
        unavailable = '<div class="intraday-unavailable-list">' + "".join(
            '<div class="intraday-unavailable-subject"><strong>'
            + escape(item.sponsor_label) + '</strong><span>'
            + escape(_plain(item.reasons[0].value)) + '</span></div>'
            for item in unavailable_members
        ) + '</div>'
    footer = (
        '<div class="intraday-panel-footer"><span>Probables <strong>'
        + str(len(probable_members)) + '</strong></span><span>Not Admitted <strong>'
        + str(not_admitted) + '</strong></span><span>Unavailable <strong>'
        + str(len(unavailable_members)) + '</strong></span><span>Conflicting <strong>'
        + str(conflicting) + '</strong></span><span>Population <strong>'
        + escape(population) + '</strong></span></div>'
    )
    return (
        '<section class="market-panel"><div class="panel-heading"><h2>'
        + escape(title) + '</h2><span>' + str(len(probable_members))
        + ' current Probables</span></div>' + cards + unavailable + footer + '</section>'
    )


def _analysis_context(
    snapshot: IntradayDiscoverySnapshot,
    probable_run: ProbablesRun | None,
) -> str:
    observation = (
        snapshot.last_successful_analysis
        if probable_run is None
        else probable_run.observation_boundary
    )
    methodology_identity = "NOT COMMISSIONED"
    methodology_version = "—"
    population = "—"
    if probable_run is not None:
        methodology_identity = probable_run.methodology_identity
        methodology_version = probable_run.methodology_version
        population = probable_run.diagnostics.population_bucket.value
    completion = {
        timeframe: any(_completed(item, timeframe) for item in snapshot.members)
        for timeframe in (
            IntradayTimeframe.DAILY,
            IntradayTimeframe.ONE_HOUR,
            IntradayTimeframe.FIFTEEN_MINUTES,
            IntradayTimeframe.FIVE_MINUTES,
        )
    }
    values = (
        ("Observation Boundary", "UNAVAILABLE" if observation is None else _ist_time(observation)),
        ("Completed 1D", _availability(completion[IntradayTimeframe.DAILY])),
        ("Completed 1H", _availability(completion[IntradayTimeframe.ONE_HOUR])),
        ("Completed 15M", _availability(completion[IntradayTimeframe.FIFTEEN_MINUTES])),
        ("Completed 5M", _availability(completion[IntradayTimeframe.FIVE_MINUTES])),
        ("Universe", snapshot.universe_identity + " · " + snapshot.universe_version),
        (
            "Reconciliation",
            snapshot.reconciliation_identity + " · " + snapshot.reconciliation_version,
        ),
        ("Methodology", methodology_identity + " · " + methodology_version),
        ("Population", population),
    )
    return (
        '<section class="intraday-analysis-context"><strong>Analysis Context</strong>'
        '<div class="intraday-analysis-context-detail">'
        + "".join('<span><b>' + escape(label) + '</b> · ' + escape(value) + '</span>' for label, value in values)
        + '</div></section>'
    )


def _completed(item: IntradayDiscoveryMemberSnapshot, timeframe: IntradayTimeframe) -> bool:
    bundle = item.machine_fact_bundle
    return bundle is not None and any(
        fact.family is FactFamily.GOVERNED_COMPLETED_OHLCV
        and fact.timeframe is timeframe
        and fact.completed_candle is True
        for fact in bundle.evidence
    )


def _availability(value: bool) -> str:
    return "GOVERNED" if value else "UNAVAILABLE"


def _analysis_time(value: datetime | None) -> str:
    if value is None:
        return "NO SUCCESSFUL DISCOVERY RUN AVAILABLE"
    return "LAST SUCCESSFUL ANALYSIS · " + _ist_time(value)


def _ist_time(value: datetime) -> str:
    return value.astimezone(_KOLKATA).strftime("%d %b %Y %H:%M IST").upper()


def _intraday_tabs(refresh_enabled: bool, *, active: str = "opportunities") -> str:
    disabled = "" if refresh_enabled else " disabled"
    return (
        '<nav class="tabs intraday-tabs" aria-label="Intraday workflow">'
        '<a class="' + ('active' if active == 'opportunities' else '') + '" href="/intraday">Opportunities</a>'
        '<a class="' + ('active' if active == 'review' else '') + '" href="/intraday/review">Review</a>'
        '<a class="' + ('active' if active == 'wo10' else '') + '" href="/intraday/wo10">WO-10</a>'
        '<a class="' + ('active' if active == 'wo11' else '') + '" href="/intraday/wo11">WO-11</a>'
        '<a class="' + ('active' if active == 'wo12' else '') + '" href="/intraday/wo12">WO-12</a>'
        '<span class="intraday-tab">Trade Candidates</span>'
        '<span class="intraday-tab">Active</span>'
        '<span class="intraday-tab">Closed</span>'
        '<div class="toolbar"><button type="button" id="intraday-refresh-analysis"'
        + disabled + '>Refresh Analysis · V2 Phase-Aware</button><span class="intraday-refresh-state" '
        'id="intraday-refresh-state" aria-live="polite"></span></div></nav>'
        + _refresh_script()
    )


def _refresh_script() -> str:
    return """<script>
const intradayRefresh=document.getElementById('intraday-refresh-analysis');
const intradayRefreshState=document.getElementById('intraday-refresh-state');
if(intradayRefresh&&!intradayRefresh.disabled){
  intradayRefresh.addEventListener('click',async()=>{
    intradayRefresh.disabled=true;
    intradayRefreshState.textContent='REFRESHING';
    try{
      const boundary=new Date().toISOString();
      const response=await fetch('""" + REFRESH_V2_ROUTE + """',{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({
          request_identity:`INTRADAY-V2-REFRESH-${Date.now()}`,
          observation_boundary:boundary,
          request_created_at:boundary,
          source_class:'""" + RefreshV2SourceClass.SPONSOR_BROWSER_CONTROL.value + """',
          contract_identity:'""" + REFRESH_V2_REQUEST_IDENTITY + """',
          contract_version:'""" + REFRESH_V2_REQUEST_VERSION + """',
          methodology_identity:'""" + PROBABLES_V2_METHODOLOGY_IDENTITY + """',
          methodology_version:'""" + PROBABLES_V2_METHODOLOGY_VERSION + """',
          methodology_publication_identity:'""" + PROBABLES_V2_PUBLICATION_IDENTITY + """',
          methodology_checksum:'""" + PROBABLES_V2_METHODOLOGY_CHECKSUM + """',
          operation_type:'""" + REFRESH_V2_OPERATION_TYPE + """'
        })
      });
      if(!response.ok)throw new Error();
      location.reload();
    }catch(_error){
      intradayRefreshState.textContent='REFRESH FAILED';
      intradayRefresh.disabled=false;
    }
  });
}
</script>"""


def _render_discovery_detail(snapshot: IntradayDiscoverySnapshot) -> str:
    item = snapshot.selected_member
    if item is None:
        return _unavailable("Intraday member", "The governed member was not found.")
    reasons = ", ".join(_plain(reason.value) for reason in item.reasons)
    probable = item.probable_result
    probable_state = "NOT YET ANALYSED" if probable is None else _plain(probable.state.value)
    probable_reason = "UNAVAILABLE" if probable is None else ", ".join(
        _plain(reason.value) for reason in probable.reasons
    )
    header = (
        '<section class="intraday-discovery-header"><h2>' + escape(item.sponsor_label)
        + '</h2><p>' + escape(item.canonical_identity) + " · "
        + escape(item.market_family) + '</p></section><div class="intraday-detail-grid">'
        + '<section class="intraday-panel"><h2>Identity / Availability</h2>'
        + _facts((
            ("Canonical identity", item.canonical_identity),
            ("Analysis contract", item.analysis_contract or "NOT APPLICABLE"),
            ("Contract expiry", item.contract_expiry or "NOT APPLICABLE"),
            ("Active binding", item.active_binding_identity or "NOT APPLICABLE"),
            ("Factual prerequisite", "AVAILABLE" if item.prerequisite_ready else "UNAVAILABLE"),
            ("Machine facts", "AVAILABLE" if item.machine_facts_available else "NOT AVAILABLE"),
            ("Discovery state", _plain(item.candidate_state.value)),
            ("Probables state", probable_state),
            ("Probables reason", probable_reason),
            ("Reason", reasons),
            ("Execution eligibility", "NOT ESTABLISHED"),
        )) + "</section>"
    )
    bundle = item.machine_fact_bundle
    if bundle is None:
        factual = _unavailable(
            "Timeframe completeness / factual evidence",
            "No completed machine-fact bundle is retained for this member.",
        )
    else:
        rows = "".join(_row((
            "SESSION" if fact.timeframe is None else fact.timeframe.value,
            _plain(fact.family.value),
            "COMPLETED" if fact.completed_candle is True else "FACTUAL",
            fact.fact_version,
        )) for fact in bundle.evidence)
        factual = _table_panel(
            "Timeframe completeness / evidence",
            ("Timeframe", "Fact family", "Boundary", "Version"), rows,
        )
    rich = item.evidence
    if rich is None:
        detail = (
            _unavailable("Previous Session / PDH / PDL")
            + _unavailable("Classic Pivots / CPR")
            + _unavailable("Structure / Volume / Distance / R:R telemetry")
        )
    else:
        structural = {value.timeframe: value for value in rich.structural_evidence}
        detail = _session_panel(rich.composition)
        detail += '<div class="intraday-timeframes">' + "".join(
            _timeframe_panel(
                value.reconciliation,
                structural.get(value.reconciliation.timeframe),
            )
            for value in rich.composition.evidence
        ) + "</div>"
        detail += _context_panels(rich.slice1e_context)
        detail += _structure_panel(rich.structural_evidence)
        detail += _telemetry_panels(rich.shadow_telemetry)
    source = "UNAVAILABLE" if bundle is None else " | ".join(bundle.source_identities)
    probable_lineage = () if probable is None else (
        ("Methodology", f"{probable.methodology_identity} / {probable.methodology_version}"),
        ("Probable result identity", probable.result_identity),
        ("Narrow CPR fact", probable.lineage.narrow_cpr_fact_identity or "UNAVAILABLE"),
        ("1H fact", probable.lineage.one_hour_fact_identity or "UNAVAILABLE"),
        ("15M fact", probable.lineage.fifteen_minute_fact_identity or "UNAVAILABLE"),
        ("Coherence fact", probable.lineage.coherence_fact_identity or "UNAVAILABLE"),
        ("Participation", probable.participation_state),
    )
    lineage = '<section class="intraday-panel"><h2>Evidence / Timestamp</h2>' + _facts((
        (
            "Observation boundary",
            "UNAVAILABLE" if item.observation_boundary is None
            else item.observation_boundary.isoformat(),
        ),
        (
            "Machine-fact contract",
            "UNAVAILABLE" if bundle is None
            else f"{bundle.schema_identity} / {bundle.bundle_version}",
        ),
        ("Source identities", source),
        *probable_lineage,
    )) + "</section></div>"
    return header + lineage + factual + detail


def _plain(value: str) -> str:
    return value.replace("_", " ").title()


def _latest_fact(facts):  # type: ignore[no-untyped-def]
    return None if not facts else max(
        facts,
        key=lambda item: (
            item.confirmation_boundary or item.end_boundary or item.start_boundary
            or item.observation_boundary.observed_at,
            item.fact_id,
        ),
    )


def render_intraday_body(snapshot: IntradayWorkstationSnapshot) -> str:
    selected_id = (
        "" if snapshot.selected_instrument is None
        else snapshot.selected_instrument.canonical.canonical_instrument_id
    )
    options = "".join(
        f'<option value="{escape(item.canonical.canonical_instrument_id)}"'
        f'{" selected" if item.canonical.canonical_instrument_id == selected_id else ""}>'
        f'{escape(item.canonical.canonical_instrument_id)}</option>'
        for item in snapshot.instruments
    )
    selector = (
        '<form class="intraday-selector" method="get" action="/intraday">'
        '<label for="instrument">Canonical Instrument</label>'
        f'<select id="instrument" name="instrument">{options}</select>'
        '<button type="submit">Inspect evidence</button></form>'
        if options else '<p class="intraday-unavailable">UNAVAILABLE — no governed DOMAIN-001 publication.</p>'
    )
    body = (
        '<div class="intraday-warning"><strong>ENGINEERING / EVIDENCE</strong>'
        '<span>NO TRADING CONCLUSION — EVIDENCE WORKSTATION</span></div>' + selector
    )
    if snapshot.selected_instrument is None:
        return body + _unavailable("Instrument / Session")
    body += _instrument_panel(snapshot)
    if snapshot.evidence is None:
        return body + _unavailable(
            "Factual Evidence",
            "No retained governed composition exists for this instrument.",
        )
    bundle = snapshot.evidence
    body += _session_panel(bundle.composition)
    structural = {item.timeframe: item for item in bundle.structural_evidence}
    body += '<div class="intraday-timeframes">'
    for evidence in bundle.composition.evidence:
        item = structural.get(evidence.reconciliation.timeframe)
        body += _timeframe_panel(evidence.reconciliation, item)
    body += "</div>"
    body += _context_panels(bundle.slice1e_context)
    body += _structure_panel(bundle.structural_evidence)
    body += _telemetry_panels(bundle.shadow_telemetry)
    body += _provenance_panel(snapshot)
    return body


def _instrument_panel(snapshot: IntradayWorkstationSnapshot) -> str:
    instrument = snapshot.selected_instrument
    assert instrument is not None
    canonical = instrument.canonical
    binding = instrument.provider_binding
    provider = (
        _facts((
            ("Binding", instrument.binding_status.value),
            ("Provider", "UNAVAILABLE" if binding is None else binding.provider),
            ("Provider Symbol", "UNAVAILABLE" if binding is None else binding.provider_symbol),
            ("Tick Size", _optional(canonical.canonical_tick_size)),
            ("Lot Size", "UNAVAILABLE" if canonical.canonical_lot_size is None else str(canonical.canonical_lot_size)),
            ("Price Precision", "UNAVAILABLE" if canonical.canonical_price_precision is None else str(canonical.canonical_price_precision)),
        ))
    )
    return (
        '<section class="intraday-panel"><h2>Instrument Identity</h2>'
        '<h3>Canonical</h3>' + _facts((
            ("Instrument", canonical.canonical_instrument_id),
            ("Exchange", canonical.exchange),
            ("Segment", canonical.segment),
            ("Instrument Type", canonical.instrument_type),
            ("Publication", instrument.publication_identity),
        )) + '<h3>Provider Binding (separate)</h3>' + provider + "</section>"
    )


def _session_panel(composition) -> str:  # type: ignore[no-untyped-def]
    session = composition.market_session
    schedule = session.schedule
    completeness = (
        "DATA_INCOMPLETE"
        if any(item.reconciliation.result.value == "DATA_INCOMPLETE" for item in composition.evidence)
        else "UNAVAILABLE"
        if any(item.reconciliation.result.value == "UNAVAILABLE" for item in composition.evidence)
        else "AVAILABLE"
    )
    windows = "UNAVAILABLE" if schedule is None else ", ".join(
        f"{item.opens_at.isoformat()} → {item.closes_at.isoformat()}"
        for item in schedule.windows
    ) or "NONE"
    return (
        '<section class="intraday-panel"><h2>Market / Session — DOMAIN-008</h2>'
        + _facts((
            ("Trading Date", session.trading_date.isoformat()),
            ("Exchange", session.exchange),
            ("Session Identity", "UNAVAILABLE" if schedule is None else schedule.session_id),
            ("Session Status", session.state.value),
            ("Session Windows", windows),
            ("Market Availability", "AVAILABLE" if session.availability else "UNAVAILABLE"),
            ("Observation Boundary", session.observed_at.isoformat()),
            ("Calendar Version", "UNAVAILABLE" if schedule is None else schedule.source_version),
            ("Data Completeness", completeness),
            ("Session End", str(session.session_end).upper()),
        )) + "</section>"
    )


def _timeframe_panel(reconciliation, structural) -> str:  # type: ignore[no-untyped-def]
    completed = reconciliation.structural_candles
    latest = completed[-1] if completed else None
    incomplete = tuple(
        item for item in reconciliation.observations
        if item.completion is CandleCompletion.INCOMPLETE
    )
    latest_text = "UNAVAILABLE" if latest is None else (
        f"{latest.boundary.start.isoformat()} → {latest.boundary.end.isoformat()}"
    )
    ohlcv = "UNAVAILABLE" if latest is None else (
        f"O {_number(latest.open)} · H {_number(latest.high)} · "
        f"L {_number(latest.low)} · C {_number(latest.close)} · V {latest.volume}"
    )
    missing = ", ".join(item.start.isoformat() for item in reconciliation.missing_boundaries) or "NONE"
    current = "NONE" if not incomplete else " | ".join(
        f"{item.boundary.start.isoformat()} · O {_number(item.open)} · H {_number(item.high)} · "
        f"L {_number(item.low)} · C {_number(item.close)} · V {item.volume}"
        for item in incomplete
    )
    return (
        '<section class="intraday-panel timeframe"><h2>'
        + escape(reconciliation.timeframe.value) + " Evidence</h2>"
        + _facts((
            ("Data Completeness", reconciliation.result.value),
            ("Availability", reconciliation.availability.value),
            ("Completed Candle Count", str(len(completed))),
            ("Latest Completed Boundary", latest_text),
            ("Latest Completed OHLCV", ohlcv),
            ("Missing Boundaries", missing),
            ("Structural Fact Count", str(0 if structural is None else len(structural.facts))),
        ))
        + '<div class="incomplete-observation"><strong>CURRENT INCOMPLETE OBSERVATION</strong><span>'
        + escape(current) + "</span></div></section>"
    )


def _context_panels(context) -> str:  # type: ignore[no-untyped-def]
    if context is None:
        return _unavailable("Previous Session / Classic Pivots / CPR")
    previous = context.previous_session
    pivots = context.classic_pivots
    cpr = context.cpr
    relationships = " | ".join(
        f"{item.reference_identity}: {item.relationship.value}"
        for item in context.price_relationships
    ) or "UNAVAILABLE"
    return (
        '<div class="intraday-context">'
        '<section class="intraday-panel"><h2>Previous Session</h2>' + _facts((
            ("Availability", previous.availability.value),
            ("Previous Session High / PDH", _optional(previous.pdh)),
            ("Previous Session Low / PDL", _optional(previous.pdl)),
            ("Previous Session Close", _optional(previous.close)),
        )) + "</section>"
        '<section class="intraday-panel"><h2>Classic Pivots</h2>' + _facts((
            ("Convention", pivots.evidence_family),
            ("R4", _optional(pivots.r4)), ("R3", _optional(pivots.r3)),
            ("R2", _optional(pivots.r2)), ("R1", _optional(pivots.r1)),
            ("P", _optional(pivots.p)), ("S1", _optional(pivots.s1)),
            ("S2", _optional(pivots.s2)), ("S3", _optional(pivots.s3)),
            ("S4", _optional(pivots.s4)),
        )) + "</section>"
        '<section class="intraday-panel"><h2>CPR</h2>' + _facts((
            ("Convention", cpr.evidence_family),
            ("CPR Upper", _optional(cpr.upper)),
            ("CPR Lower", _optional(cpr.lower)),
            ("CPR Width", _optional(cpr.width)),
            ("CPR Pivot", _optional(cpr.pivot)),
            ("Current vs Prior CPR", "UNAVAILABLE" if cpr.relationship_to_prior is None else cpr.relationship_to_prior.value),
            ("Current-price Relationships", relationships),
        )) + "</section></div>"
    )


def _structure_panel(evidence) -> str:  # type: ignore[no-untyped-def]
    if not evidence:
        return _unavailable("Structural Facts")
    rows = ""
    for item in evidence:
        for barrier in item.barriers:
            rows += _row((
                item.timeframe.value, "STRUCTURAL_BARRIER", barrier.reference_name,
                _optional(barrier.price), barrier.availability.value,
            ))
        for fact in item.facts:
            values = ", ".join(f"{value.name}={_number(value.value)}" for value in fact.values) or "—"
            attributes = ", ".join(f"{value.name}={value.value}" for value in fact.attributes)
            detail = values if not attributes else f"{values}; {attributes}"
            rows += _row((
                fact.timeframe.value, fact.fact_type.value, fact.direction.value,
                detail, fact.availability.value,
            ))
    if not rows:
        rows = '<tr><td colspan="5">No structural facts retained.</td></tr>'
    return _table_panel(
        "Structural Facts", ("Timeframe", "Fact", "Direction", "Values / Relationships", "Availability"), rows
    )


def _telemetry_panels(evidence) -> str:  # type: ignore[no-untyped-def]
    volume_rows = ""
    extension_rows = ""
    for item in evidence:
        for measure in item.measures:
            values = ", ".join(f"{value.name}={_number(value.value)}" for value in measure.values) or "—"
            attrs = ", ".join(f"{value.name}={value.value}" for value in measure.attributes)
            detail = values if not attrs else f"{values}; {attrs}"
            row = _row((
                item.timeframe.value, measure.telemetry_type.value,
                measure.comparison.value, detail, measure.availability.value,
            ))
            if measure.telemetry_type in {
                TelemetryType.VOLUME_OBSERVATION,
                TelemetryType.RECENT_VOLUME_COMPARISON,
                TelemetryType.SESSION_VOLUME_COMPARISON,
            }:
                volume_rows += row
            else:
                extension_rows += row
    return (
        _table_panel(
            "Volume / Participation — Shadow Telemetry",
            ("Timeframe", "Measure", "Exact Comparison", "Raw / Derived Values", "Availability"),
            volume_rows or '<tr><td colspan="5">UNAVAILABLE</td></tr>',
        )
        + _table_panel(
            "Extension / Reward-Risk — Shadow Telemetry",
            ("Timeframe", "Measure", "Comparison", "Explicit Inputs / Values", "Availability"),
            extension_rows or '<tr><td colspan="5">UNAVAILABLE</td></tr>',
        )
    )


def _provenance_panel(snapshot: IntradayWorkstationSnapshot) -> str:
    bundle = snapshot.evidence
    assert bundle is not None
    rows = "".join(
        _row((
            item.reconciliation.timeframe.value,
            item.reconciliation.provenance.provider,
            item.reconciliation.provenance.source_identity,
            item.reconciliation.provenance.source_version,
            item.reconciliation.provenance.retrieved_at.isoformat(),
        )) for item in bundle.composition.evidence
    )
    identities = _facts((
        ("Run ID", bundle.composition.run.run_id),
        ("Mapping Identity", bundle.composition.instrument.mapping_identity),
        ("Observation Boundary", bundle.composition.run.observation_boundary.observed_at.isoformat()),
        ("Factual Evidence IDs", " | ".join(item.evidence_id for item in bundle.composition.evidence)),
        ("Shadow Telemetry IDs", " | ".join(item.evidence_id for item in bundle.shadow_telemetry) or "UNAVAILABLE"),
    ))
    table = _table_panel(
        "Provenance / Availability",
        ("Timeframe", "Provider", "Source Identity", "Version", "Retrieved"), rows,
    )
    return '<section class="intraday-panel intraday-wide"><h2>Evidence Identities</h2>' + identities + "</section>" + table


def _facts(items: tuple[tuple[str, str], ...]) -> str:
    return '<dl class="intraday-facts">' + "".join(
        f"<dt>{escape(label)}</dt><dd>{escape(value)}</dd>" for label, value in items
    ) + "</dl>"


def _table_panel(title: str, headings: tuple[str, ...], rows: str) -> str:
    return (
        '<section class="intraday-panel intraday-wide"><h2>' + escape(title) + "</h2>"
        '<div class="table-scroll"><table class="intraday-table"><thead><tr>'
        + "".join(f"<th>{escape(item)}</th>" for item in headings)
        + "</tr></thead><tbody>" + rows + "</tbody></table></div></section>"
    )


def _row(values: tuple[str, ...]) -> str:
    return "<tr>" + "".join(f"<td>{escape(item)}</td>" for item in values) + "</tr>"


def _unavailable(title: str, detail: str = "Governed evidence is unavailable.") -> str:
    return (
        '<section class="intraday-panel intraday-unavailable"><h2>' + escape(title)
        + "</h2><strong>UNAVAILABLE</strong><p>" + escape(detail) + "</p></section>"
    )


def _number(value: Decimal) -> str:
    return format(value, "f")


def _optional(value: Decimal | None) -> str:
    return "UNAVAILABLE" if value is None else _number(value)


__all__ = [
    "render_intraday_body",
    "render_intraday_detail",
    "render_intraday_triage",
    "render_intraday_wo10",
    "render_intraday_wo11",
    "render_intraday_wo12",
    "render_intraday_workstation",
]
