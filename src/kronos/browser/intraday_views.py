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
from kronos.intraday.review_answer import AnswerImportState
from kronos.intraday.telemetry import TelemetryType


_KOLKATA = ZoneInfo("Asia/Kolkata")


_INTRADAY_CSS = r"""
.intraday-card{border:1px solid var(--line);background:#071827;border-radius:12px;padding:18px;max-width:760px}.intraday-card h2{margin:0;color:var(--green)}.intraday-card .event{border-top:1px solid var(--line);padding:10px 0}.intraday-card .detail-link{display:inline-block;margin-top:10px;color:var(--green);font-weight:800}.intraday-status{color:var(--muted);margin:8px 0 14px}.intraday-status strong{color:var(--green)}
.intraday-warning{display:flex;justify-content:space-between;gap:16px;border:1px solid #82631f;background:#231d11;color:#f6d997;border-radius:8px;padding:12px 14px;margin-bottom:14px}.intraday-selector{display:flex;align-items:center;gap:10px;margin-bottom:14px}.intraday-selector label{font-weight:700}.intraday-selector select{border:1px solid #31506a;background:#04131f;color:var(--text);border-radius:7px;padding:9px 12px}.intraday-panel{border:1px solid var(--line);background:rgba(6,23,37,.88);border-radius:10px;padding:15px;margin-bottom:14px;min-width:0}.intraday-panel h2{margin:0 0 12px;color:var(--blue);font-size:17px}.intraday-panel h3{margin:14px 0 7px;color:var(--muted);font-size:11px;text-transform:uppercase}.intraday-facts{display:grid;grid-template-columns:minmax(140px,.35fr) minmax(0,1fr);margin:0}.intraday-facts dt,.intraday-facts dd{padding:6px 8px;border-top:1px solid var(--line);margin:0;overflow-wrap:anywhere}.intraday-facts dt{color:var(--muted)}.intraday-timeframes{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.incomplete-observation{display:grid;gap:5px;margin-top:11px;border:1px dashed #82631f;border-radius:7px;padding:9px;color:#f6d997}.incomplete-observation span{color:var(--muted);overflow-wrap:anywhere}.intraday-context{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.intraday-table{width:100%;border-collapse:collapse;font-size:12px}.intraday-table th,.intraday-table td{text-align:left;vertical-align:top;padding:8px;border-bottom:1px solid var(--line);overflow-wrap:anywhere}.intraday-table th{color:var(--muted);white-space:nowrap}.table-scroll{overflow:auto}.intraday-unavailable{color:var(--muted)}.intraday-unavailable strong{color:var(--amber)}
.intraday-discovery-header{border:1px solid var(--line);background:#071827;border-radius:9px;padding:13px 15px;margin-bottom:12px}.intraday-discovery-header h2{font-size:17px;color:var(--green);margin:0 0 5px}.intraday-discovery-header p{margin:3px 0;color:var(--muted);font-size:12px}.intraday-discovery-table{width:100%;border-collapse:collapse;font-size:12px}.intraday-discovery-table th,.intraday-discovery-table td{padding:7px 8px;border-bottom:1px solid var(--line);text-align:left}.intraday-discovery-table th{font-size:10px;color:var(--muted);text-transform:uppercase}.intraday-state-ready{color:var(--green)}.intraday-state-held{color:var(--amber)}.intraday-failure{border:1px solid #81502a;background:#26170d;color:#f0c08e;border-radius:7px;padding:9px 11px;margin-bottom:12px}.intraday-methodology{border:1px solid var(--line);background:#071827;color:#c2d2dd;border-radius:7px;padding:8px 11px;margin-bottom:12px;font-size:11px}.intraday-methodology strong{color:var(--green)}.intraday-detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.intraday-tabs{margin:-22px -28px 22px}.intraday-tabs a.active{border-color:var(--green)}.intraday-tab{height:61px;display:flex;align-items:center;color:var(--muted);border-bottom:2px solid transparent;white-space:nowrap}.intraday-refresh-state{margin-left:8px;color:var(--muted);font-size:10px}.intraday-summary .status-top strong{color:var(--green)}.intraday-market-panels{grid-template-columns:repeat(2,minmax(0,1fr))}.intraday-market-panels .panel-heading h2{color:var(--green)}.intraday-market-panels .market-panel{min-height:330px}.intraday-market-panels .empty{min-height:110px}.intraday-probable .summary-reason{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:7px}.intraday-card-fact{border-left:1px solid var(--line);padding-left:7px;min-width:0}.intraday-card-fact:first-child{border-left:0;padding-left:0}.intraday-card-fact span{display:block;color:var(--muted);font-size:8px;text-transform:uppercase;letter-spacing:.04em}.intraday-card-fact strong{display:block;margin-top:2px;font-size:11px;overflow-wrap:anywhere}.intraday-probable .summary-rr strong{color:#dce8f0}.intraday-panel-footer{display:flex;flex-wrap:wrap;gap:7px 14px;border-top:1px solid var(--line);margin-top:13px;padding-top:10px;color:var(--muted);font-size:10px}.intraday-panel-footer strong{color:#dce8f0}.intraday-unavailable-list{display:grid;gap:6px;margin-top:10px}.intraday-unavailable-subject{display:flex;justify-content:space-between;gap:10px;border-top:1px solid var(--line);padding-top:6px;color:var(--muted);font-size:11px}.intraday-unavailable-subject strong{color:var(--amber)}.intraday-analysis-context{display:flex;align-items:flex-start;gap:12px;border:1px solid var(--line);background:#071827;border-radius:8px;margin-top:14px;padding:8px 10px}.intraday-analysis-context>strong{flex:0 0 auto;color:var(--green);font-size:10px;text-transform:uppercase;letter-spacing:.05em}.intraday-analysis-context-detail{display:flex;align-items:center;flex-wrap:wrap;gap:5px 12px;color:var(--muted);font-size:8px;white-space:normal}.intraday-analysis-context-detail span{padding-left:12px;border-left:1px solid var(--line)}
.intraday-review-toolbar{display:flex;align-items:center;gap:9px;flex-wrap:wrap;border:1px solid var(--line);background:#071827;border-radius:9px;padding:10px;margin-bottom:12px}.intraday-review-toolbar form{margin:0}.intraday-review-toolbar .future-action{opacity:.62}.intraday-review-toolbar-note{color:var(--muted);font-size:10px}.intraday-batch-result{border:1px solid #2d765d;background:#08261e;border-radius:9px;padding:10px 12px;margin-bottom:12px}.intraday-batch-result h2{color:var(--green);font-size:13px;margin:0 0 6px}.intraday-batch-accounting{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px}.intraday-batch-accounting span,.intraday-batch-members span{font-size:10px;color:var(--muted)}.intraday-batch-members{display:flex;flex-wrap:wrap;gap:5px 12px;margin-top:7px}.intraday-review-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:12px}.intraday-review-card{border:1px solid var(--line);background:#071827;border-radius:10px;padding:14px;min-width:0}.intraday-review-card h2{margin:0;color:var(--green);font-size:18px}.intraday-review-head{display:flex;justify-content:space-between;gap:14px;align-items:center}.intraday-review-required{display:inline-block;margin-top:7px;color:#f6d997;font-size:10px;font-weight:850}.intraday-probable-context{border-top:1px solid var(--line);border-bottom:1px solid var(--line);padding:8px 0;margin:9px 0;color:#d9e6df;font-size:10px}.intraday-probable-context strong{display:block;color:var(--green);font-size:9px;text-transform:uppercase;margin-bottom:3px}.intraday-review-section-title{color:var(--muted);font-size:9px;font-weight:850;letter-spacing:.05em;margin:10px 0 6px}.intraday-review-status{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px;margin:12px 0}.intraday-review-status div{border:1px solid var(--line);border-radius:6px;padding:7px}.intraday-review-status span{display:block;color:var(--muted);font-size:8px;text-transform:uppercase}.intraday-review-status strong{font-size:10px;overflow-wrap:anywhere}.intraday-review-actions{display:grid;gap:8px}.intraday-drop{display:grid;place-items:center;text-align:center;min-height:160px;border:2px dashed #3d836b;border-radius:9px;padding:16px;color:var(--muted);cursor:pointer;outline:none}.intraday-drop:hover,.intraday-drop:focus-visible{border-color:var(--green);background:#09251d;box-shadow:0 0 0 3px rgba(46,212,119,.14)}.intraday-drop .paste-key{display:grid;place-items:center;width:46px;height:36px;border:1px solid #3d836b;border-radius:7px;color:var(--green);font-size:18px;font-weight:900}.intraday-drop strong{color:#e9f7f0;font-size:13px;margin-top:7px}.intraday-drop span{display:block;font-size:10px}.intraday-drop .required-panels{margin-top:7px}.intraday-chart-input{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}.intraday-file-choice{justify-self:start;display:inline-block;border:1px solid #246a52;border-radius:7px;padding:7px 10px;color:#dff7eb;font-size:10px;font-weight:750;cursor:pointer}.intraday-file-choice:hover,.intraday-file-choice:focus-visible{border-color:var(--green);outline:2px solid rgba(46,212,119,.25)}.intraday-review-actions form{margin:0}.intraday-review-lineage{font-size:9px;color:var(--muted);overflow-wrap:anywhere}.intraday-review-diagnostics{font-size:9px;color:var(--muted)}.intraday-review-diagnostics summary{cursor:pointer}.intraday-review-config{margin-top:14px;border:1px solid var(--line);border-radius:7px;padding:9px;color:var(--muted);font-size:9px;overflow-wrap:anywhere}
@media(max-width:900px){.intraday-detail-grid{grid-template-columns:1fr}.intraday-probable .summary-reason{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:760px){.intraday-tabs{margin:-18px -18px 18px;padding:0 18px;gap:13px;overflow:auto}.intraday-tabs .toolbar{margin-left:0}.intraday-timeframes,.intraday-context{grid-template-columns:1fr}.intraday-warning,.intraday-selector{align-items:flex-start;flex-direction:column}.intraday-facts{grid-template-columns:1fr}.intraday-facts dd{padding-top:0}.intraday-market-panels{grid-template-columns:1fr}.intraday-probable .summary-reason{grid-template-columns:repeat(2,minmax(0,1fr))}.intraday-analysis-context{align-items:flex-start}.intraday-analysis-context-detail{flex-wrap:wrap;white-space:normal}.intraday-review-list{grid-template-columns:1fr}.intraday-batch-accounting{grid-template-columns:repeat(2,minmax(0,1fr))}.intraday-review-status{grid-template-columns:1fr}.intraday-review-toolbar{align-items:stretch;flex-direction:column}.intraday-review-toolbar button{width:100%}}
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
) -> str:
    """Render persisted exact-current Review and WO-10 analytical state."""

    reconciled = {} if reconciliation is None else {
        item.probable_result_identity: item for item in reconciliation.candidates
    }
    cards = (
        "".join(_review_candidate(item, reconciled.get(item.probable_result_identity)) for item in review.candidates)
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
        else '<span class="intraday-review-toolbar-note">Current batch · '
        + escape(review.current_batch_filename or review.current_batch_identity)
        + "</span>"
    )
    body = (
        _intraday_tabs(False, active="review")
        + '<div class="intraday-warning"><strong>NATIVE + VISUAL REVIEW</strong>'
        '<span>ANALYTICAL READINESS ONLY · NO ENTRY, TRADE, RISK OR BROKER AUTHORITY</span></div>'
        '<div class="intraday-review-toolbar"><form method="post" action="/intraday/review/question-packs">'
        '<button class="primary" type="submit"'
        + (" disabled" if ready_count == 0 else "")
        + '>CREATE ALL REVIEW PDF</button></form>'
        '<form method="post" action="/intraday/review/answers"><button type="submit"'
        + (" disabled" if not any(item.review_pack_identity is not None for item in review.candidates) else "")
        + '>UPLOAD ALL ANSWERS</button></form>'
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
        + '<br><strong>Future Answer inbox:</strong> '
        + escape(review.answer_inbox)
        + ' · Governed JSON Answer Pack import ACTIVE</div>'
        + _review_upload_script()
    )
    return render_browser_page(
        title="Intraday Native Review",
        subtitle="Exact-current Probables · manual 1D | 1H | 15M | 5M chart intake.",
        snapshot=snapshot,
        active_nav="Intraday",
        active_tab="Review",
        body=body,
        extra_styles=_INTRADAY_CSS,
    )


def _review_candidate(
    item, reconciliation: ReconciliationCandidateSnapshot | None  # type: ignore[no-untyped-def]
) -> str:
    direction_class = "direction-long" if item.direction == "LONG" else "direction-short"
    if item.cycle_identity is None:
        action = (
            '<form method="post" action="/intraday/review/start?result='
            + quote(item.probable_result_identity, safe="")
            + '"><button type="submit">START REVIEW</button></form>'
        )
        chart_state = "NOT CREATED"
        pack_state = "NOT CREATED"
    else:
        cycle = quote(item.cycle_identity, safe="")
        input_identity = "intraday-chart-" + item.cycle_identity.rsplit("-", 1)[-1][:12]
        chart_state = (
            "CHART REQUIRED"
            if item.chart_revision_ordinal is None
            else f"CHART READY · REV {item.chart_revision_ordinal:03d}"
        )
        pack_state = "NOT CREATED" if item.review_pack_identity is None else "CREATED"
        action = (
            '<div class="intraday-review-section-title">TRADINGVIEW CHARTS</div>'
            '<div class="intraday-drop" role="button" tabindex="0" aria-label="Paste TradingView 1D 1H 15M 5M chart composite for '
            + escape(item.canonical_subject_identity)
            + '" data-review-upload="/intraday/review/chart?cycle='
            + cycle
            + '"><span class="paste-key">⌘V</span><strong>PASTE / UPLOAD</strong>'
            '<span>TRADINGVIEW 4-CHART IMAGE</span><span class="required-panels">Required: 1D · 1H · 15M · 5M</span></div>'
            '<label class="intraday-file-choice" tabindex="0" for="' + input_identity + '">CHOOSE IMAGE FILE</label>'
            '<input id="' + input_identity + '" class="intraday-chart-input" type="file" accept="image/png,image/jpeg" '
            'aria-label="Choose 1D 1H 15M 5M chart composite" data-review-file-target="' + input_identity + '-target">'
        )
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
    else:
        summary = (
            f"UPLOAD ALL ANSWERS · Eligible {batch.eligible_candidates} · Discovered {batch.files_discovered} · "
            f"Imported {batch.count(AnswerImportState.IMPORTED)} · "
            f"Already imported {batch.count(AnswerImportState.ALREADY_IMPORTED)} · "
            f"Missing {batch.count(AnswerImportState.MISSING)} · "
            f"Invalid {batch.count(AnswerImportState.INVALID)} · "
            f"Identity mismatch {batch.count(AnswerImportState.IDENTITY_MISMATCH)} · "
            f"Schema invalid {batch.count(AnswerImportState.SCHEMA_INVALID)} · "
            f"Conflict {batch.count(AnswerImportState.CONFLICT)}"
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
async function uploadReviewChart(target,file){
  const accepted=new Set(['image/png','image/jpeg']);
  if(!file||!accepted.has(file.type)){alert('Paste or choose a PNG or JPEG chart image.');return;}
  const response=await fetch(target.dataset.reviewUpload,{method:'POST',headers:{'Content-Type':file.type},body:file});
  if(!response.ok){alert('Chart upload rejected.');return;}
  document.open();document.write(await response.text());document.close();
}
document.querySelectorAll('[data-review-upload]').forEach(target=>{
  const input=target.parentElement.querySelector('input[data-review-file-target]');
  if(input)input.addEventListener('change',()=>uploadReviewChart(target,input.files[0]));
  target.addEventListener('click',()=>target.focus());
  target.addEventListener('dragover',event=>event.preventDefault());
  target.addEventListener('drop',event=>{event.preventDefault();uploadReviewChart(target,event.dataTransfer.files[0]);});
  target.addEventListener('paste',event=>{const item=[...(event.clipboardData?.items||[])].find(value=>value.kind==='file'&&['image/png','image/jpeg'].includes(value.type));if(!item){alert('No supported chart image was found on the clipboard.');return;}event.preventDefault();uploadReviewChart(target,item.getAsFile());});
});
document.querySelectorAll('[data-review-answer-upload]').forEach(input=>{
  input.addEventListener('change',async()=>{
    const file=input.files[0];
    if(!file||(!file.name.toLowerCase().endsWith('.json')&&!['application/json','text/json'].includes(file.type))){alert('Choose a JSON Answer Pack.');return;}
    const response=await fetch(input.dataset.reviewAnswerUpload,{method:'POST',headers:{'Content-Type':'application/json'},body:file});
    if(!response.ok){alert('Answer upload rejected.');return;}
    document.open();document.write(await response.text());document.close();
  });
});
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
        '<span class="intraday-tab">Trade Candidates</span>'
        '<span class="intraday-tab">Active</span>'
        '<span class="intraday-tab">Closed</span>'
        '<div class="toolbar"><button type="button" id="intraday-refresh-analysis"'
        + disabled + '>Refresh Analysis</button><span class="intraday-refresh-state" '
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
      const response=await fetch('/control/intraday-discovery',{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({
          request_identity:`INTRADAY-REFRESH-${Date.now()}`,
          observation_boundary:new Date().toISOString()
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
    "render_intraday_workstation",
]
