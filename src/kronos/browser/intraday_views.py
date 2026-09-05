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
from kronos.browser.intraday_market_availability import IntradayMarketAvailability
from kronos.browser.views import render_browser_page
from kronos.intraday.contracts import CandleCompletion, IntradayTimeframe
from kronos.intraday.discovery import FactFamily
from kronos.intraday.probables import ProbablesRun, ProbableReason, ProbableState
from kronos.intraday.probables_v2 import (
    PROBABLES_V2_METHODOLOGY_IDENTITY,
    PROBABLES_V2_SUCCESSOR_METHODOLOGY_CHECKSUM as PROBABLES_V2_METHODOLOGY_CHECKSUM,
    PROBABLES_V2_SUCCESSOR_METHODOLOGY_VERSION as PROBABLES_V2_METHODOLOGY_VERSION,
    PROBABLES_V2_SUCCESSOR_PUBLICATION_IDENTITY as PROBABLES_V2_PUBLICATION_IDENTITY,
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


from kronos.intraday.review_persistence import MAX_CHART_BYTES

_KOLKATA = ZoneInfo("Asia/Kolkata")


_INTRADAY_CSS = r"""
.intraday-opportunity-review{display:flex;flex-wrap:wrap;justify-content:space-between;gap:10px;margin-top:10px;font-size:11px}.intraday-opportunity-review strong{color:var(--green)}.intraday-review-v2-card:target{outline:2px solid var(--green);scroll-margin-top:16px}.intraday-review-focus-notice{color:var(--amber);overflow-wrap:anywhere}
@media(max-width:760px){.app,.sidebar,.main,.topbar,.content{min-width:0;max-width:100%}.nav{grid-template-columns:repeat(2,minmax(0,1fr))}.nav a,.title,.kite{min-width:0}.title h1,.title p,.intraday-warning,.intraday-review-v2-control,.intraday-review-v2-head{overflow-wrap:anywhere}.topbar{align-items:flex-start;flex-direction:column}.intraday-review-v2-grid,.intraday-review-list{grid-template-columns:minmax(0,1fr)}.intraday-review-v2-card,.intraday-review-v2-control,.intraday-review-v2-head{min-width:0}.intraday-review-v2-control{flex-wrap:wrap}.intraday-review-currentness-facts{grid-template-columns:minmax(0,1fr)}.intraday-opportunity-review a{padding:8px 0}}

.intraday-card{border:1px solid var(--line);background:#071827;border-radius:12px;padding:18px;max-width:760px}.intraday-card h2{margin:0;color:var(--green)}.intraday-card .event{border-top:1px solid var(--line);padding:10px 0}.intraday-card .detail-link{display:inline-block;margin-top:10px;color:var(--green);font-weight:800}.intraday-status{color:var(--muted);margin:8px 0 14px}.intraday-status strong{color:var(--green)}
.intraday-warning{display:flex;justify-content:space-between;gap:16px;border:1px solid #82631f;background:#231d11;color:#f6d997;border-radius:8px;padding:12px 14px;margin-bottom:14px}.intraday-selector{display:flex;align-items:center;gap:10px;margin-bottom:14px}.intraday-selector label{font-weight:700}.intraday-selector select{border:1px solid #31506a;background:#04131f;color:var(--text);border-radius:7px;padding:9px 12px}.intraday-panel{border:1px solid var(--line);background:rgba(6,23,37,.88);border-radius:10px;padding:15px;margin-bottom:14px;min-width:0}.intraday-panel h2{margin:0 0 12px;color:var(--blue);font-size:17px}.intraday-panel h3{margin:14px 0 7px;color:var(--muted);font-size:11px;text-transform:uppercase}.intraday-facts{display:grid;grid-template-columns:minmax(140px,.35fr) minmax(0,1fr);margin:0}.intraday-facts dt,.intraday-facts dd{padding:6px 8px;border-top:1px solid var(--line);margin:0;overflow-wrap:anywhere}.intraday-facts dt{color:var(--muted)}.intraday-timeframes{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.incomplete-observation{display:grid;gap:5px;margin-top:11px;border:1px dashed #82631f;border-radius:7px;padding:9px;color:#f6d997}.incomplete-observation span{color:var(--muted);overflow-wrap:anywhere}.intraday-context{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.intraday-table{width:100%;border-collapse:collapse;font-size:12px}.intraday-table th,.intraday-table td{text-align:left;vertical-align:top;padding:8px;border-bottom:1px solid var(--line);overflow-wrap:anywhere}.intraday-table th{color:var(--muted);white-space:nowrap}.table-scroll{overflow:auto}.intraday-unavailable{color:var(--muted)}.intraday-unavailable strong{color:var(--amber)}
.intraday-discovery-header{border:1px solid var(--line);background:#071827;border-radius:9px;padding:13px 15px;margin-bottom:12px}.intraday-discovery-header h2{font-size:17px;color:var(--green);margin:0 0 5px}.intraday-discovery-header p{margin:3px 0;color:var(--muted);font-size:12px}.intraday-discovery-table{width:100%;border-collapse:collapse;font-size:12px}.intraday-discovery-table th,.intraday-discovery-table td{padding:7px 8px;border-bottom:1px solid var(--line);text-align:left}.intraday-discovery-table th{font-size:10px;color:var(--muted);text-transform:uppercase}.intraday-state-ready{color:var(--green)}.intraday-state-held{color:var(--amber)}.intraday-failure{border:1px solid #81502a;background:#26170d;color:#f0c08e;border-radius:7px;padding:9px 11px;margin-bottom:12px}.intraday-methodology{border:1px solid var(--line);background:#071827;color:#c2d2dd;border-radius:7px;padding:8px 11px;margin-bottom:12px;font-size:11px}.intraday-methodology strong{color:var(--green)}.intraday-detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.intraday-tabs{margin:-22px -28px 22px}.intraday-tabs a.active{border-color:var(--green)}.intraday-tab{height:61px;display:flex;align-items:center;color:var(--muted);border-bottom:2px solid transparent;white-space:nowrap}.intraday-refresh-state{margin-left:8px;color:var(--muted);font-size:10px}.intraday-summary .status-top strong{color:var(--green)}.intraday-market-panels{grid-template-columns:repeat(2,minmax(0,1fr))}.intraday-market-panels .panel-heading h2{color:var(--green)}.intraday-market-panels .market-panel{min-height:330px}.intraday-market-panels .empty{min-height:110px}.intraday-market-accounting{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px;margin:-8px 0 14px}.intraday-market-accounting div{border:1px solid var(--line);border-radius:7px;background:#071827;padding:8px}.intraday-market-accounting span{display:block;color:var(--muted);font-size:8px;text-transform:uppercase;letter-spacing:.05em}.intraday-market-accounting strong{display:block;margin-top:2px;font-size:14px}.intraday-opportunities-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px;align-items:start}.intraday-market-group{border:1px solid var(--line);background:rgba(6,23,37,.86);border-radius:11px;padding:16px;min-width:0}.intraday-market-heading{display:flex;align-items:baseline;justify-content:space-between;gap:10px;border-bottom:1px solid var(--line);padding-bottom:10px}.intraday-market-heading h2{margin:0;color:var(--green);font-size:17px}.intraday-market-heading span{color:var(--muted);font-size:11px}.intraday-direction-group{margin-top:14px}.intraday-direction-group>h3{margin:0;color:#dce8f0;font-size:12px;letter-spacing:.08em}.intraday-direction-group>p{margin:3px 0 0;color:var(--muted);font-size:10px}.intraday-direction-empty{border:1px dashed var(--line);border-radius:8px;color:var(--muted);font-size:11px;margin-top:8px;padding:11px;text-align:center}.intraday-market-empty{border-left:2px solid var(--amber);color:var(--muted);font-size:10px;margin:12px 0 0;padding:6px 9px}.intraday-probable .opp-identity h4{font-size:18px;margin:0}.intraday-probable .summary-reason{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:7px}.intraday-card-fact{border-left:1px solid var(--line);padding-left:7px;min-width:0}.intraday-card-fact:first-child{border-left:0;padding-left:0}.intraday-card-fact span{display:block;color:var(--muted);font-size:8px;text-transform:uppercase;letter-spacing:.04em}.intraday-card-fact strong{display:block;margin-top:2px;font-size:11px;overflow-wrap:anywhere}.intraday-card-fact small{display:block;margin-top:2px;color:var(--muted);font-size:8px;overflow-wrap:anywhere}.intraday-probable .summary-rr strong{color:#dce8f0}.intraday-probables-diagnostics{border:1px solid var(--line);background:#071827;border-radius:9px;margin-top:14px;padding:10px 12px}.intraday-probables-diagnostics>summary{cursor:pointer;color:var(--muted);font-size:10px;font-weight:800;letter-spacing:.05em}.intraday-diagnostic-list{display:grid;max-height:360px;overflow:auto;margin-top:9px}.intraday-diagnostic-row{display:grid;grid-template-columns:minmax(140px,.7fr) minmax(110px,.4fr) minmax(170px,.7fr) minmax(220px,1.3fr);gap:8px;border-top:1px solid var(--line);padding:7px 0;font-size:9px}.intraday-diagnostic-row strong{color:#dce8f0}.intraday-diagnostic-row span{color:var(--muted);overflow-wrap:anywhere}.intraday-panel-footer{display:flex;flex-wrap:wrap;gap:7px 14px;border-top:1px solid var(--line);margin-top:13px;padding-top:10px;color:var(--muted);font-size:10px}.intraday-panel-footer strong{color:#dce8f0}.intraday-unavailable-list{display:grid;gap:6px;margin-top:10px}.intraday-unavailable-subject{display:flex;justify-content:space-between;gap:10px;border-top:1px solid var(--line);padding-top:6px;color:var(--muted);font-size:11px}.intraday-unavailable-subject strong{color:var(--amber)}.intraday-analysis-context{display:flex;align-items:flex-start;gap:12px;border:1px solid var(--line);background:#071827;border-radius:8px;margin-top:14px;padding:8px 10px}.intraday-analysis-context>strong{flex:0 0 auto;color:var(--green);font-size:10px;text-transform:uppercase;letter-spacing:.05em}.intraday-analysis-context-detail{display:flex;align-items:center;flex-wrap:wrap;gap:5px 12px;color:var(--muted);font-size:8px;white-space:normal}.intraday-analysis-context-detail span{padding-left:12px;border-left:1px solid var(--line)}
.intraday-availability-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-bottom:12px}.intraday-availability-card{border:1px solid var(--line);border-radius:9px;background:#071827;padding:11px 13px}.intraday-availability-card span{display:block;color:var(--muted);font-size:9px;letter-spacing:.06em}.intraday-availability-card strong{display:block;margin-top:4px;color:#dce8f0;font-size:12px}.intraday-availability-card.available{border-color:#2d765d}.intraday-availability-card.available strong{color:var(--green)}.intraday-availability-card.closed strong,.intraday-availability-card.pre-market strong{color:var(--amber)}.intraday-freshness{border:1px solid var(--line);border-radius:9px;background:#061725;padding:11px 13px;margin-bottom:12px}.intraday-freshness h2{margin:0 0 8px;color:var(--green);font-size:13px}.intraday-freshness-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px 14px}.intraday-freshness-grid span{color:var(--muted);font-size:9px}.intraday-freshness-grid strong{display:block;color:#dce8f0;font-size:11px;margin-top:2px}.intraday-prior-projection{border:1px solid #82631f;background:#231d11;color:#f6d997;border-radius:8px;padding:10px 12px;margin-bottom:12px}.intraday-prior-projection strong{display:block}.intraday-prior-projection span{display:block;color:#d7c79b;font-size:10px;margin-top:3px}
.intraday-review-toolbar{display:flex;align-items:center;gap:9px;flex-wrap:wrap;border:1px solid var(--line);background:#071827;border-radius:9px;padding:10px;margin-bottom:12px}.intraday-review-toolbar form{margin:0}.intraday-review-toolbar .future-action{opacity:.62}.intraday-review-toolbar-note{color:var(--muted);font-size:10px}.intraday-batch-result{border:1px solid #2d765d;background:#08261e;border-radius:9px;padding:10px 12px;margin-bottom:12px}.intraday-batch-result h2{color:var(--green);font-size:13px;margin:0 0 6px}.intraday-batch-accounting{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px}.intraday-batch-accounting span,.intraday-batch-members span{font-size:10px;color:var(--muted)}.intraday-batch-members{display:flex;flex-wrap:wrap;gap:5px 12px;margin-top:7px}.intraday-review-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:12px}.intraday-review-card{border:1px solid var(--line);background:#071827;border-radius:10px;padding:14px;min-width:0}.intraday-review-card h2{margin:0;color:var(--green);font-size:18px}.intraday-review-head{display:flex;justify-content:space-between;gap:14px;align-items:center}.intraday-review-required{display:inline-block;margin-top:7px;color:#f6d997;font-size:10px;font-weight:850}.intraday-probable-context{border-top:1px solid var(--line);border-bottom:1px solid var(--line);padding:8px 0;margin:9px 0;color:#d9e6df;font-size:10px}.intraday-probable-context strong{display:block;color:var(--green);font-size:9px;text-transform:uppercase;margin-bottom:3px}.intraday-review-section-title{color:var(--muted);font-size:9px;font-weight:850;letter-spacing:.05em;margin:10px 0 6px}.intraday-review-status{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px;margin:12px 0}.intraday-review-status div{border:1px solid var(--line);border-radius:6px;padding:7px}.intraday-review-status span{display:block;color:var(--muted);font-size:8px;text-transform:uppercase}.intraday-review-status strong{font-size:10px;overflow-wrap:anywhere}.intraday-review-actions{display:grid;gap:8px}.intraday-drop{display:grid;place-items:center;text-align:center;min-height:160px;border:2px dashed #3d836b;border-radius:9px;padding:16px;color:var(--muted);cursor:pointer;outline:none}.intraday-drop:hover,.intraday-drop:focus-visible{border-color:var(--green);background:#09251d;box-shadow:0 0 0 3px rgba(46,212,119,.14)}.intraday-drop .paste-key{display:grid;place-items:center;width:46px;height:36px;border:1px solid #3d836b;border-radius:7px;color:var(--green);font-size:18px;font-weight:900}.intraday-drop strong{color:#e9f7f0;font-size:13px;margin-top:7px}.intraday-drop span{display:block;font-size:10px}.intraday-drop .required-panels{margin-top:7px}.intraday-chart-input{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}.intraday-file-choice{justify-self:start;display:inline-block;border:1px solid #246a52;border-radius:7px;padding:7px 10px;color:#dff7eb;font-size:10px;font-weight:750;cursor:pointer}.intraday-file-choice:hover,.intraday-file-choice:focus-visible{border-color:var(--green);outline:2px solid rgba(46,212,119,.25)}.intraday-review-actions form{margin:0}.intraday-review-lineage{font-size:9px;color:var(--muted);overflow-wrap:anywhere}.intraday-review-diagnostics{font-size:9px;color:var(--muted)}.intraday-review-diagnostics summary{cursor:pointer}.intraday-review-config{margin-top:14px;border:1px solid var(--line);border-radius:7px;padding:9px;color:var(--muted);font-size:9px;overflow-wrap:anywhere}
.intraday-drop{cursor:text;overflow:hidden}.intraday-drop.replace-ready{border-color:var(--green);background:#09251d;box-shadow:0 0 0 3px rgba(46,212,119,.14)}.intraday-drop.received{min-height:82px;border-style:solid}.intraday-chart-received strong{color:var(--green)}.intraday-chart-received span{color:var(--muted)}.intraday-chart-slot-actions{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
@media(max-width:900px){.intraday-detail-grid{grid-template-columns:1fr}.intraday-probable .summary-reason{grid-template-columns:repeat(3,minmax(0,1fr))}.intraday-diagnostic-row{grid-template-columns:minmax(120px,.7fr) minmax(100px,.4fr) minmax(160px,1fr)}.intraday-diagnostic-row span:last-child{grid-column:1/-1}}
@media(max-width:760px){.intraday-tabs{margin:-18px -18px 18px;padding:0 18px;gap:13px;overflow:auto}.intraday-tabs .toolbar{margin-left:0}.intraday-timeframes,.intraday-context,.intraday-availability-grid,.intraday-freshness-grid{grid-template-columns:1fr}.intraday-warning,.intraday-selector{align-items:flex-start;flex-direction:column}.intraday-facts{grid-template-columns:1fr}.intraday-facts dd{padding-top:0}.intraday-market-panels,.intraday-opportunities-grid{grid-template-columns:1fr}.intraday-market-accounting{grid-template-columns:repeat(2,minmax(0,1fr))}.intraday-probable .summary-reason{grid-template-columns:repeat(2,minmax(0,1fr))}.intraday-diagnostic-row{grid-template-columns:1fr}.intraday-diagnostic-row span:last-child{grid-column:auto}.intraday-analysis-context{align-items:flex-start}.intraday-analysis-context-detail{flex-wrap:wrap;white-space:normal}.intraday-review-list{grid-template-columns:1fr}.intraday-batch-accounting{grid-template-columns:repeat(2,minmax(0,1fr))}.intraday-review-status{grid-template-columns:1fr}.intraday-review-toolbar{align-items:stretch;flex-direction:column}.intraday-review-toolbar button{width:100%}}
"""

_REVIEW_V2_CSS = r"""
.intraday-review-v2{border:1px solid #31506a;background:#061725;border-radius:10px;padding:15px;margin-bottom:16px}.intraday-review-v2-head{display:flex;justify-content:space-between;align-items:flex-start;gap:14px}.intraday-review-v2-head h2{margin:0;color:var(--green);font-size:17px}.intraday-review-v2-head p{margin:4px 0;color:var(--muted);font-size:11px}.intraday-review-v2-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:12px}.intraday-review-v2-card{border:1px solid var(--line);border-radius:8px;padding:12px;background:#071827}.intraday-review-v2-card h3{margin:0;color:#dce8f0}.intraday-review-v2-card .phase-a{display:inline-block;margin:7px 0;color:var(--amber);font-weight:800}.intraday-review-v2-control{display:flex;align-items:center;gap:12px;margin-top:12px}.intraday-review-v2-control span{color:var(--muted);font-size:10px;overflow-wrap:anywhere}@media(max-width:760px){.intraday-review-v2-grid{grid-template-columns:1fr}.intraday-review-v2-head{display:block}}
.intraday-review-currentness{border:1px solid var(--line);border-radius:8px;background:#071827;margin-top:12px;padding:10px 12px}.intraday-review-currentness strong{color:var(--green)}.intraday-review-currentness.outdated{border-color:#82631f}.intraday-review-currentness.outdated strong{color:#f6d997}.intraday-review-currentness.invalid{border-color:#81502a}.intraday-review-currentness.invalid strong{color:#f0c08e}.intraday-review-currentness-facts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:5px 12px;margin-top:7px;color:var(--muted);font-size:10px}.intraday-review-currentness-facts span{overflow-wrap:anywhere}@media(max-width:760px){.intraday-review-currentness-facts{grid-template-columns:1fr}}

.intraday-drop.intraday-drop-empty{display:flex;justify-content:space-between;gap:10px;min-height:88px;padding:12px;text-align:left;cursor:default}.intraday-drop-empty .intraday-intake-copy{min-width:0}.intraday-drop-empty strong{display:block;margin:0;font-size:11px;overflow-wrap:anywhere}.intraday-drop-empty .required-panels{margin-top:6px}.intraday-drop-empty .intraday-chart-slot-actions{flex-shrink:0}.intraday-drop-empty .intraday-chart-slot-actions:focus-within .intraday-file-choice{outline:2px solid var(--green);outline-offset:2px}
@media(max-width:760px){.intraday-drop.intraday-drop-empty{min-height:96px;padding:10px;gap:8px}.intraday-drop-empty .intraday-file-choice{padding:9px 8px}}
"""


def render_intraday_workstation(
    snapshot: BrowserWorkspaceSnapshot,
    intraday: IntradayWorkstationSnapshot | IntradayDiscoverySnapshot,
    *,
    market_availability: tuple[IntradayMarketAvailability, ...] = (),
    refresh_status: dict[str, object] | None = None,
    latest_evaluable_run: ProbablesRunV2 | None = None,
    review_v2: IntradayReviewV2Snapshot | None = None,
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
            refresh_enabled=(
                snapshot.provider_state.value == "CONNECTED"
                and (
                    not market_availability
                    or any(item.available for item in market_availability)
                )
            ),
            market_availability=market_availability,
            refresh_status=refresh_status,
            latest_evaluable_run=latest_evaluable_run,
            review_v2=review_v2,
        ),
        extra_styles=_INTRADAY_CSS,
    )


def render_intraday_operational_readiness(
    snapshot: BrowserWorkspaceSnapshot,
    status: dict[str, object],
) -> str:
    """Render exact source states and WO-B review classifications side by side."""

    reviews = status.get("reviews")
    review_items = reviews if type(reviews) in {tuple, list} else ()
    cards = "".join(
        _wo_b_review_card(item) for item in review_items if type(item) is dict
    )
    if not cards:
        cards = (
            '<div class="empty"><div><strong>'
            + escape(_wo16_value(status.get("restoration_state")))
            + "</strong><br>No current admitted opportunity review is available.</div></div>"
        )
    current_reason = status.get("failure_reason")
    current_failure_html = (
        '<section class="intraday-failure wo-b-failure" aria-label="Current review failure">'
        "<strong>Current review failure</strong><br>Status: "
        + escape(_wo16_value(status.get("restoration_state")))
        + "<br>Reason: " + escape(current_reason) + "</section>"
        if type(current_reason) is str and current_reason else ""
    )
    failures = status.get("latest_failures")
    failure_items = failures if type(failures) in {tuple, list} else ()
    failure_html = "".join(
        '<div class="intraday-failure wo-b-failure"><strong>Latest persisted WO-B failure · '
        + escape(_wo16_value(item.get("candidate_identity")))
        + "</strong><br>" + escape(_wo16_value(item.get("stage")))
        + " · " + escape(_wo16_value(item.get("reason")))
        + " · " + escape(_wo16_value(item.get("failed_at"))) + "</div>"
        for item in failure_items if type(item) is dict
    )
    body = (
        _intraday_tabs(False, active="wo-b")
        + '<div class="intraday-warning"><strong>OPERATIONAL READINESS REVIEW</strong>'
        "<span>READ-ONLY CROSS-DOMAIN COMPOSITION<br>"
        "NO GLOBAL READINESS, EXECUTION, POSITION, MONITORING OR BROKER AUTHORITY</span></div>"
        + current_failure_html + cards + failure_html
        + '<div class="intraday-review-config"><strong>Product:</strong> '
        + escape(_wo16_value(status.get("product_identity"))) + " / "
        + escape(_wo16_value(status.get("product_version")))
        + "<br><strong>Policy:</strong> "
        + escape(_wo16_value(status.get("policy_identity"))) + " / "
        + escape(_wo16_value(status.get("policy_version")))
        + "<br><strong>Runtime:</strong> "
        + ("LOADED" if status.get("runtime_loaded") is True else "UNAVAILABLE")
        + " · " + escape(_wo16_value(status.get("restoration_state")))
        + " · Operation " + escape(_wo16_value(status.get("operation_state")))
        + "<br><strong>Boundary:</strong> Browser GET composes persisted facts in memory; "
        + "it invokes no producer and writes no evidence.</div>"
    )
    return render_browser_page(
        title="Intraday Operational Readiness Review",
        subtitle="Current source truth and deterministic stage classification.",
        snapshot=snapshot,
        active_nav="Intraday",
        active_tab="Operational Review",
        body=body,
        extra_styles=_INTRADAY_CSS + _WO_B_CSS,
    )


def _wo_b_summary(status: dict[str, object]) -> str:
    reviews = status.get("reviews")
    count = len(reviews) if type(reviews) in {tuple, list} else 0
    return (
        '<section class="intraday-panel wo-b-summary"><h2>Operational Readiness Review</h2>'
        "<p>Current admitted opportunities reviewed: <strong>" + str(count)
        + "</strong> · " + escape(_wo16_value(status.get("restoration_state")))
        + '</p><a class="detail-link" href="/intraday/operational-review">'
        "Inspect source states and next governed stages →</a></section>"
    )


def _wo_b_review_card(item: dict[str, object]) -> str:
    rows = item.get("items")
    review_rows = rows if type(rows) in {tuple, list} else ()
    table = "".join(
        "<tr><td>" + escape(_wo16_value(row.get("source_boundary")))
        + "</td><td><strong>" + escape(_wo16_value(row.get("source_state")))
        + "</strong><br>" + escape(_wo16_value(row.get("source_reason")))
        + "</td><td>" + escape(_wo16_value(row.get("classification")))
        + "</td><td>" + escape(_wo16_value(row.get("next_governed_stage")))
        + "</td></tr>"
        for row in review_rows if type(row) is dict
    )
    references = item.get("source_references")
    reference_items = references if type(references) in {tuple, list} else ()
    details = "".join(
        "<li><strong>" + escape(_wo16_value(ref.get("source_boundary")))
        + "</strong> · " + escape(_wo16_value(ref.get("artifact_identity")))
        + " · " + escape(_wo16_value(ref.get("schema")))
        + " · " + escape(_wo16_value(ref.get("policy")))
        + " · " + escape(_wo16_value(ref.get("observed_at")))
        + " · current " + escape(_wo16_value(ref.get("current")))
        + " · superseded " + escape(_wo16_value(ref.get("superseded"))) + "</li>"
        for ref in reference_items if type(ref) is dict
    )
    attention = (
        '<span class="status neutral">SPONSOR ATTENTION AVAILABLE</span>'
        if item.get("sponsor_attention_available") is True else ""
    )
    return (
        '<article class="wo-b-card"><div class="panel-head"><div><h2>'
        + escape(_wo16_value(item.get("canonical_subject_identity")))
        + "</h2><p>" + escape(_wo16_value(item.get("market_family")))
        + " · " + escape(_wo16_value(item.get("direction")))
        + " · instrument " + escape(_wo16_value(item.get("canonical_instrument_identity")))
        + " · contract " + escape(_wo16_value(item.get("active_contract_identity")))
        + "</p></div>" + attention + "</div>"
        '<div class="table-wrap"><table class="intraday-table"><thead><tr>'
        "<th>Boundary</th><th>Exact Source State / Reason</th>"
        "<th>WO-B Classification</th><th>Next Governed Stage</th>"
        "</tr></thead><tbody>" + table + "</tbody></table></div>"
        '<details class="wo-b-details"><summary>Exact identities and currentness</summary><ul>'
        + details + "</ul><p>Candidate "
        + escape(_wo16_value(item.get("candidate_identity"))) + " · Run "
        + escape(_wo16_value(item.get("analysis_run_identity"))) + " · Review "
        + escape(_wo16_value(item.get("review_snapshot_identity"))) + " · Boundary "
        + escape(_wo16_value(item.get("review_boundary"))) + "</p></details></article>"
    )


_WO_B_CSS = r"""
.wo-b-summary{margin-top:16px}.wo-b-summary p{color:var(--muted)}.wo-b-summary strong{color:var(--green)}
.wo-b-failure{min-width:0;overflow-wrap:anywhere}
.wo-b-card{border:1px solid var(--line);border-radius:12px;padding:14px;margin-bottom:14px;background:var(--panel);min-width:0}
.wo-b-card h2{margin:0;color:var(--green)}.wo-b-card p{color:var(--muted);overflow-wrap:anywhere}.wo-b-details{margin-top:12px;color:var(--muted);font-size:10px}.wo-b-details summary{cursor:pointer;color:#dce8f0}.wo-b-details li{margin:5px 0;overflow-wrap:anywhere}
@media(max-width:760px){.app,.sidebar,.main,.topbar,.content,.wo-b-card{width:100%;min-width:0;max-width:100%}.nav{grid-template-columns:repeat(2,minmax(0,1fr))}.nav a,.title,.kite,.wo-b-card .panel-head>div{min-width:0}.nav a,.title h1,.title p,.intraday-warning{overflow-wrap:anywhere}.topbar,.wo-b-card .panel-head{align-items:flex-start;flex-direction:column}.kite{justify-content:flex-start}.wo-b-card .table-wrap{width:100%;max-width:100%;overflow-x:auto}.wo-b-card table{min-width:680px}}
"""


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
    review_v2_status: dict[str, object] | None = None,
    focused_candidate: str | None = None,
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
        + _review_v2_projection(
            review_v2, available_probables_v2_run, review_v2_status, focused_candidate
        )
        + ("" if review_v2 is not None and not review.candidates else (
        '<div class="intraday-review-toolbar"><form method="post" action="/intraday/review/question-packs">'
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
        ))
        + _review_upload_script()
        + _review_v2_chart_script()
        + _review_v2_control_script()
        + '<script>window.addEventListener("pageshow",()=>{requestAnimationFrame(()=>{'
        'const card=document.getElementById(location.hash.slice(1));'
        'if(card&&card.classList.contains("intraday-review-v2-card")){'
        'card.focus({preventScroll:true});card.scrollIntoView({block:"start"});}'
        '});});</script>'
    )
    return render_browser_page(
        title="Intraday Native Review",
        subtitle="Exact-current Probables · one complete TradingView composite per candidate.",
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


def render_intraday_wo13(
    snapshot: BrowserWorkspaceSnapshot,
    status: dict[str, object],
) -> str:
    """Render only the restored authoritative WO-13 Trade Plan projection."""

    plan = status.get("current_plan")
    if type(plan) is not dict:
        content = (
            '<div class="empty"><div><strong>'
            + escape(str(status.get("restoration_state", "NOT_YET_RUN")))
            + "</strong><br>No persisted WO-13 Step-31 Trade Plan.</div></div>"
        )
    else:
        availability = plan.get("field_availability", [])
        availability_rows = "".join(
            "<tr><td>" + escape(str(item.get("field", "UNAVAILABLE")))
            + "</td><td>" + escape(str(item.get("availability", "UNAVAILABLE")))
            + "</td><td>" + escape(str(item.get("reason", "UNAVAILABLE")))
            + "</td></tr>"
            for item in availability
            if type(item) is dict
        )
        warnings = plan.get("warnings", [])
        warning_text = _list_text(warnings)
        content = (
            '<section class="panel"><div class="panel-head"><div><h2>'
            + escape(str(plan.get("canonical_subject_identity", "UNAVAILABLE")))
            + "</h2><p>" + escape(str(plan.get("market_family", "UNAVAILABLE")))
            + " · " + escape(str(plan.get("direction", "UNAVAILABLE")))
            + " · " + escape(str(plan.get("setup_family", "UNAVAILABLE")))
            + '</p></div><span class="status neutral">'
            + escape(str(plan.get("geometry_availability", "UNAVAILABLE")))
            + "</span></div>"
            '<dl class="detail-list"><dt>Analysis boundary / phase</dt><dd>'
            + escape(str(plan.get("analysis_boundary", "UNAVAILABLE"))) + " · "
            + escape(str(plan.get("phase", "UNAVAILABLE")))
            + "</dd><dt>Instrument / actual contract</dt><dd>"
            + escape(str(plan.get("instrument_identity", "UNAVAILABLE"))) + " · "
            + escape(_wo13_value(plan.get("actual_contract_identity")))
            + "</dd><dt>Entry Reference</dt><dd>"
            + escape(_wo13_value(plan.get("entry_reference")))
            + "</dd><dt>Entry Condition</dt><dd>"
            + escape(_wo13_value(plan.get("entry_condition")))
            + "</dd><dt>Stop</dt><dd>"
            + escape(_wo13_value(plan.get("stop"))) + " · "
            + escape(_wo13_value(plan.get("stop_structural_basis")))
            + "</dd><dt>Thesis Invalidation</dt><dd>"
            + escape(_wo13_value(plan.get("thesis_invalidation_reference"))) + " · "
            + escape(_wo13_value(plan.get("thesis_invalidation_event")))
            + "</dd><dt>Setup-native Target</dt><dd>"
            + escape(_wo13_value(plan.get("setup_native_target")))
            + "</dd><dt>Canonical Target</dt><dd>"
            + escape(_wo13_value(plan.get("canonical_target"))) + " · "
            + escape(_wo13_value(plan.get("target_structural_basis")))
            + "</dd><dt>Constraining Objective / Confluence</dt><dd>"
            + escape(_wo13_value(plan.get("constraining_objective")))
            + "</dd><dt>Risk Distance</dt><dd>"
            + escape(_wo13_value(plan.get("risk_distance")))
            + "</dd><dt>Reward Distance</dt><dd>"
            + escape(_wo13_value(plan.get("reward_distance")))
            + "</dd><dt>Model R:R</dt><dd>"
            + escape(_wo13_value(plan.get("model_rr")))
            + "</dd><dt>Mathematical warnings</dt><dd>" + escape(warning_text)
            + "</dd></dl>"
            '<div class="table-wrap"><table><thead><tr><th>Geometry field</th>'
            "<th>Availability</th><th>Persisted reason</th></tr></thead><tbody>"
            + availability_rows + "</tbody></table></div></section>"
            '<section class="panel"><div class="panel-head"><div><h2>Lineage / Policy</h2>'
            "<p>Persisted immutable identities; Browser performs no reconstruction.</p>"
            '</div><span class="status neutral">READ ONLY</span></div>'
            '<dl class="detail-list"><dt>Trade Plan</dt><dd>'
            + escape(str(plan.get("trade_plan_identity", "UNAVAILABLE")))
            + "</dd><dt>Source WO-12 result</dt><dd>"
            + escape(str(plan.get("source_wo12_result_identity", "UNAVAILABLE")))
            + "</dd><dt>WO-13 handoff</dt><dd>"
            + escape(str(plan.get("source_handoff_identity", "UNAVAILABLE")))
            + "</dd><dt>Policy</dt><dd>"
            + escape(str(plan.get("policy_identity", "UNAVAILABLE"))) + " / "
            + escape(str(plan.get("policy_version", "UNAVAILABLE"))) + " / "
            + escape(str(plan.get("policy_checksum", "UNAVAILABLE")))
            + "</dd><dt>Current pointer</dt><dd>"
            + escape(str(plan.get("pointer_identity", "UNAVAILABLE")))
            + "</dd><dt>Supersession lineage</dt><dd>"
            + escape(_wo13_value(plan.get("supersession_lineage_identity")))
            + "</dd></dl></section>"
        )
    last = status.get("last_operation")
    if type(last) is dict and last.get("failure_reason") is not None:
        last_operation = (
            '<section class="intraday-panel intraday-unavailable"><h2>Last Operation Failure</h2>'
            "<strong>" + escape(str(last.get("outcome", "FAILED"))) + "</strong><p>"
            + escape(str(last.get("failure_stage", "UNAVAILABLE"))) + " · "
            + escape(str(last.get("failure_reason", "WO13_OPERATION_FAILED")))
            + "</p></section>"
        )
    else:
        last_operation = ""
    body = (
        _intraday_tabs(False, active="wo13")
        + '<div class="intraday-warning"><strong>WO-13 STEP-31 TRADE CONSTRUCTION</strong>'
        "<span>ANALYTICAL GEOMETRY ONLY · NO TIMING, RISK, SPONSOR OR EXECUTION AUTHORITY</span></div>"
        + content + last_operation
        + '<div class="intraday-review-config"><strong>Control:</strong> '
        + escape(str(status.get("control_identity", "UNAVAILABLE"))) + " / "
        + escape(str(status.get("control_version", "UNAVAILABLE")))
        + "<br><strong>Runtime:</strong> "
        + ("LOADED" if status.get("runtime_loaded") is True else "UNAVAILABLE")
        + " · " + escape(str(status.get("restoration_state", "UNAVAILABLE")))
        + " · Operation " + escape(str(status.get("operation_state", "UNAVAILABLE")))
        + "<br><strong>Authority boundary:</strong> This page answers what geometry Step-31 constructed; it does not recommend or execute a trade."
        + "</div>"
    )
    return render_browser_page(
        title="Intraday WO-13",
        subtitle="Persisted Step-31 Trade Plan; rendering performs no geometry work.",
        snapshot=snapshot,
        active_nav="Intraday",
        active_tab="WO-13",
        body=body,
        extra_styles=_INTRADAY_CSS,
    )


def render_intraday_wo14(
    snapshot: BrowserWorkspaceSnapshot,
    status: dict[str, object],
) -> str:
    """Render restored WO-14 loss/exposure facts without permission semantics."""

    observation = status.get("current_observation")
    if type(observation) is not dict:
        content = (
            '<div class="empty"><div><strong>'
            + escape(str(status.get("restoration_state", "NOT_YET_RUN")))
            + "</strong><br>No persisted WO-14 risk/loss observation.</div></div>"
        )
    else:
        availability = observation.get("field_availability", [])
        availability_rows = "".join(
            "<tr><td>" + escape(str(item.get("field", "UNAVAILABLE")))
            + "</td><td>" + escape(str(item.get("availability", "UNAVAILABLE")))
            + "</td><td>" + escape(str(item.get("reason", "UNAVAILABLE")))
            + "</td></tr>"
            for item in availability
            if type(item) is dict
        )
        family = str(observation.get("market_family", "UNAVAILABLE"))
        family_note = (
            "Underlying point risk is independent factual context; monetary execution-vehicle risk remains unavailable."
            if family == "NSE_INDEX"
            else "Exact active-contract economics only; no external reference market is a sizing authority."
            if family == "MCX"
            else "Stock-local loss/exposure facts only."
        )
        content = (
            '<section class="panel"><div class="panel-head"><div><h2>'
            + escape(str(observation.get("canonical_subject_identity", "UNAVAILABLE")))
            + "</h2><p>" + escape(family) + " · "
            + escape(str(observation.get("direction", "UNAVAILABLE")))
            + " · " + escape(str(observation.get("setup_family", "UNAVAILABLE")))
            + '</p></div><span class="status neutral">'
            + escape(str(observation.get("state", "RISK_UNAVAILABLE")))
            + "</span></div>"
            '<dl class="detail-list"><dt>Structural risk / price unit</dt><dd>'
            + escape(_wo14_value(observation.get("structural_risk_per_price_unit")))
            + "</dd><dt>Risk per share</dt><dd>"
            + escape(_wo14_value(observation.get("risk_per_share")))
            + "</dd><dt>Underlying point risk</dt><dd>"
            + escape(_wo14_value(observation.get("underlying_point_risk")))
            + "</dd><dt>Monetary risk / tradable unit</dt><dd>"
            + escape(_wo14_value(observation.get("monetary_risk_per_tradable_unit")))
            + "</dd><dt>Reference quantity / semantics</dt><dd>"
            + escape(_wo14_value(observation.get("reference_quantity"))) + " · "
            + escape(_wo14_value(observation.get("reference_quantity_semantics")))
            + " · source "
            + escape(_wo14_value(observation.get("reference_quantity_source_identity")))
            + "</dd><dt>Loss at Stop</dt><dd>"
            + escape(_wo14_value(observation.get("loss_at_stop")))
            + "</dd><dt>Reference notional</dt><dd>"
            + escape(_wo14_value(observation.get("reference_notional")))
            + "</dd><dt>Capital reference / fraction</dt><dd>"
            + escape(_wo14_value(observation.get("capital_reference"))) + " · "
            + escape(_wo14_value(observation.get("capital_at_risk_fraction")))
            + " · source "
            + escape(_wo14_value(observation.get("capital_source_identity")))
            + "</dd><dt>Existing / aggregate open risk</dt><dd>"
            + escape(_wo14_value(observation.get("existing_open_risk"))) + " · "
            + escape(_wo14_value(observation.get("aggregate_open_risk_after_reference")))
            + " · source "
            + escape(_wo14_value(observation.get("portfolio_source_identity")))
            + "</dd><dt>Margin context</dt><dd>"
            + escape(_wo14_value(observation.get("margin_context")))
            + " · source "
            + escape(_wo14_value(observation.get("margin_source_identity")))
            + "</dd><dt>Monetary currency</dt><dd>"
            + escape(_wo14_value(observation.get("currency")))
            + "</dd><dt>WO-13 Model R:R (context only)</dt><dd>"
            + escape(_wo14_value(observation.get("model_rr")))
            + "</dd><dt>Alert severity</dt><dd>"
            + escape(str(observation.get("alert_severity", "UNCLASSIFIED")))
            + "</dd><dt>Market-family treatment</dt><dd>" + escape(family_note)
            + "</dd><dt>Unavailable reasons</dt><dd>"
            + escape(_list_text(observation.get("unavailable_reasons")))
            + "</dd></dl>"
            '<div class="table-wrap"><table><thead><tr><th>Risk field</th>'
            "<th>Availability</th><th>Persisted reason</th></tr></thead><tbody>"
            + availability_rows + "</tbody></table></div></section>"
            '<section class="panel"><div class="panel-head"><div><h2>Lineage / Policy</h2>'
            "<p>Immutable WO-13 binding and persisted factual provenance.</p>"
            '</div><span class="status neutral">READ ONLY</span></div>'
            '<dl class="detail-list"><dt>WO-14 observation</dt><dd>'
            + escape(str(observation.get("observation_identity", "UNAVAILABLE")))
            + "</dd><dt>WO-13 Trade Plan</dt><dd>"
            + escape(str(observation.get("trade_plan_identity", "UNAVAILABLE")))
            + "</dd><dt>Instrument / actual contract</dt><dd>"
            + escape(str(observation.get("instrument_identity", "UNAVAILABLE"))) + " · "
            + escape(_wo14_value(observation.get("actual_contract_identity")))
            + "</dd><dt>Analysis boundary</dt><dd>"
            + escape(str(observation.get("analysis_boundary", "UNAVAILABLE")))
            + "</dd><dt>Policy</dt><dd>"
            + escape(str(observation.get("policy_identity", "UNAVAILABLE"))) + " / "
            + escape(str(observation.get("policy_version", "UNAVAILABLE")))
            + "</dd><dt>Authority</dt><dd>"
            + escape(str(observation.get("authority", "RISK_OBSERVATION_ONLY")))
            + "</dd><dt>Current pointer</dt><dd>"
            + escape(str(observation.get("pointer_identity", "UNAVAILABLE")))
            + "</dd></dl></section>"
        )
    last = status.get("last_operation")
    if type(last) is dict and last.get("failure_reason") is not None:
        last_operation = (
            '<section class="intraday-panel intraday-unavailable"><h2>Last Operation Failure</h2>'
            "<strong>" + escape(str(last.get("outcome", "FAILED"))) + "</strong><p>"
            + escape(str(last.get("failure_stage", "UNAVAILABLE"))) + " · "
            + escape(str(last.get("failure_reason", "WO14_OPERATION_FAILED")))
            + "</p></section>"
        )
    else:
        last_operation = ""
    body = (
        _intraday_tabs(False, active="wo14")
        + '<div class="intraday-warning"><strong>WO-14 DOMAIN-007 LOSS / EXPOSURE OBSERVATION</strong>'
        "<span>ADVISORY FACTS ONLY · NO TRADE, TIMING, QUANTITY, SPONSOR OR EXECUTION AUTHORITY</span></div>"
        + content + last_operation
        + '<div class="intraday-review-config"><strong>Control:</strong> '
        + escape(str(status.get("control_identity", "UNAVAILABLE"))) + " / "
        + escape(str(status.get("control_version", "UNAVAILABLE")))
        + "<br><strong>Runtime:</strong> "
        + ("LOADED" if status.get("runtime_loaded") is True else "UNAVAILABLE")
        + " · " + escape(str(status.get("restoration_state", "UNAVAILABLE")))
        + " · Operation " + escape(str(status.get("operation_state", "UNAVAILABLE")))
        + "<br><strong>Boundary:</strong> This page reports available risk/loss facts for one immutable WO-13 plan. It provides no timing or trade consequence."
        + "</div>"
    )
    return render_browser_page(
        title="Intraday WO-14",
        subtitle="Persisted DOMAIN-007 advisory observation; rendering performs no calculation.",
        snapshot=snapshot,
        active_nav="Intraday",
        active_tab="WO-14",
        body=body,
        extra_styles=_INTRADAY_CSS,
    )


def render_intraday_wo15(
    snapshot: BrowserWorkspaceSnapshot,
    status: dict[str, object],
) -> str:
    """Render persisted WO-15 timing evidence without timing recomputation."""

    current = status.get("current_timing")
    if type(current) is not dict:
        content = (
            '<div class="empty"><div><strong>'
            + escape(str(status.get("restoration_state", "NOT_YET_RUN")))
            + "</strong><br>No persisted WO-15 completed-5M timing evidence.</div></div>"
        )
    else:
        result = _dict(current.get("timing_result"))
        telemetry = _dict(current.get("telemetry"))
        handoff = _dict(current.get("timing_handoff"))
        pointer = _dict(current.get("current_pointer"))
        operation = _dict(current.get("operation"))
        atr = _dict(telemetry.get("atr14"))
        latency = _dict(telemetry.get("latency"))
        timing = (
            '<section class="panel wo15-current"><div class="panel-head"><div><h2>'
            + escape(_wo15_value(current.get("canonical_subject_identity")))
            + "</h2><p>" + escape(_wo15_value(current.get("market_family")))
            + " · " + escape(_wo15_value(current.get("direction")))
            + " · " + escape(_wo15_value(current.get("setup_family")))
            + '</p></div><span class="status neutral">'
            + escape(_wo15_value(result.get("current_state")))
            + "</span></div><dl class=\"detail-list\">"
            "<dt>Prior state / transition cause</dt><dd>"
            + escape(_wo15_value(result.get("prior_state"))) + " · "
            + escape(_wo15_value(result.get("cause")))
            + "</dd><dt>Qualification path</dt><dd>"
            + escape(_wo15_value(result.get("qualification_path")))
            + "</dd><dt>Evidence boundary</dt><dd>"
            + escape(_wo15_value(result.get("observation_boundary")))
            + "</dd><dt>Completed 5M close / Entry Reference</dt><dd>"
            + escape(_wo15_value(current.get("completed_five_minute_close")))
            + " · " + escape(_wo15_value(current.get("entry_reference")))
            + "</dd><dt>Timing cycle</dt><dd>"
            + escape(_wo15_value(result.get("timing_cycle_id")))
            + "</dd><dt>Observation / transition</dt><dd>"
            + escape(_wo15_value(_nested(result, "cycle_evaluation", "observation", "observation_identity")))
            + " · "
            + escape(_wo15_value(_nested(result, "cycle_evaluation", "transition", "transition_identity")))
            + "</dd></dl></section>"
        )
        telemetry_panel = (
            '<section class="panel wo15-telemetry"><div class="panel-head"><div>'
            "<h2>WO-15C Advisory Research Telemetry</h2>"
            "<p>Research-only factual measurements; no timing consequence.</p>"
            '</div><span class="status neutral">RESEARCH ONLY</span></div>'
            '<dl class="detail-list"><dt>Directional / absolute extension</dt><dd>'
            + escape(_wo15_value(telemetry.get("directional_extension"))) + " · "
            + escape(_wo15_value(telemetry.get("absolute_extension")))
            + "</dd><dt>ATR-14 availability / value</dt><dd>"
            + escape(_wo15_value(atr.get("availability"))) + " · "
            + escape(_wo15_value(atr.get("value")))
            + "</dd><dt>Normalized directional extension</dt><dd>"
            + escape(_wo15_value(telemetry.get("normalized_directional_extension")))
            + "</dd><dt>Severity</dt><dd>"
            + escape(_wo15_value(telemetry.get("extension_severity")))
            + "</dd><dt>Maximum favourable / adverse / pre-qualification</dt><dd>"
            + escape(_wo15_value(telemetry.get("maximum_favourable_extension"))) + " · "
            + escape(_wo15_value(telemetry.get("maximum_adverse_distance"))) + " · "
            + escape(_wo15_value(telemetry.get("maximum_extension_before_qualification")))
            + "</dd><dt>Retest occurred</dt><dd>"
            + escape(_wo15_value(telemetry.get("retest_occurred")))
            + "</dd><dt>Latency seconds</dt><dd>"
            + escape(_wo15_value(latency.get("plan_to_first_evaluation"))) + " · "
            + escape(_wo15_value(latency.get("first_evaluation_to_qualification")))
            + "</dd><dt>Research references</dt><dd>"
            + escape(_wo15_list(telemetry.get("research_references")))
            + "</dd></dl></section>"
        )
        handoff_panel = (
            '<section class="panel wo15-handoff"><div class="panel-head"><div>'
            "<h2>Timing Handoff</h2><p>Immutable timing evidence boundary.</p>"
            '</div><span class="status neutral">'
            + escape(_wo15_value(handoff.get("current_state")))
            + '</span></div><dl class="detail-list"><dt>Identity / integrity</dt><dd>'
            + escape(_wo15_value(handoff.get("handoff_identity"))) + " · "
            + escape(_wo15_value(handoff.get("handoff_integrity")))
            + "</dd><dt>Predecessor / supersession</dt><dd>"
            + escape(_wo15_value(handoff.get("predecessor_handoff_identity"))) + " · "
            + escape(_wo15_value(handoff.get("supersession_lineage_identity")))
            + "</dd><dt>Research references</dt><dd>"
            + escape(_wo15_list(handoff.get("research_references")))
            + "</dd><dt>WO-14 audit context</dt><dd>"
            + escape(_wo15_value(handoff.get("wo14_observation_identity")))
            + " · RISK OBSERVATION ONLY"
            + "</dd><dt>Downstream authorities</dt><dd>Sponsor "
            + escape(_wo15_value(handoff.get("sponsor_decision_authority")))
            + " · PAPER " + escape(_wo15_value(handoff.get("paper_authority")))
            + " · LIVE " + escape(_wo15_value(handoff.get("live_authority")))
            + " · Position " + escape(_wo15_value(handoff.get("position_authority")))
            + " · Broker " + escape(_wo15_value(handoff.get("broker_authority")))
            + "</dd></dl></section>"
        )
        lineage = (
            '<section class="panel wo15-lineage"><div class="panel-head"><div><h2>Lineage / Policy</h2>'
            "<p>Persisted identities; Browser performs no reconstruction.</p>"
            '</div><span class="status neutral">READ ONLY</span></div>'
            '<dl class="detail-list"><dt>WO-13 Trade Plan / integrity</dt><dd>'
            + escape(_wo15_value(current.get("wo13_trade_plan_identity"))) + " · "
            + escape(_wo15_value(current.get("wo13_trade_plan_integrity")))
            + "</dd><dt>Instrument / actual contract / roll</dt><dd>"
            + escape(_wo15_value(current.get("instrument_identity"))) + " · "
            + escape(_wo15_value(current.get("actual_contract_identity"))) + " · "
            + escape(_wo15_value(current.get("roll_lineage_identity")))
            + "</dd><dt>Session / calendar</dt><dd>"
            + escape(_wo15_value(current.get("session_identity"))) + " · "
            + escape(_wo15_value(current.get("calendar_identity"))) + " / "
            + escape(_wo15_value(current.get("calendar_version")))
            + "</dd><dt>Policy</dt><dd>"
            + escape(_wo15_value(_nested(result, "policy", "policy_identity"))) + " / "
            + escape(_wo15_value(_nested(result, "policy", "policy_version"))) + " / "
            + escape(_wo15_value(_nested(result, "policy", "policy_checksum")))
            + "</dd><dt>Operation</dt><dd>"
            + escape(_wo15_value(operation.get("operation_identity"))) + " · "
            + escape(_wo15_value(operation.get("outcome")))
            + "</dd><dt>Timing result</dt><dd>"
            + escape(_wo15_value(result.get("result_identity")))
            + "</dd><dt>Current pointer / supersession</dt><dd>"
            + escape(_wo15_value(pointer.get("pointer_identity"))) + " · "
            + escape(_wo15_value(pointer.get("supersession_lineage_identity")))
            + "</dd></dl></section>"
        )
        content = '<div class="wo15-grid">' + timing + telemetry_panel + handoff_panel + lineage + "</div>"

    history = status.get("timing_history")
    history_rows = ""
    if type(history) is list:
        history_rows = "".join(
            "<tr><td>" + escape(_wo15_value(item.get("event")))
            + "</td><td>" + escape(_wo15_value(item.get("boundary")))
            + "</td><td>" + escape(_wo15_value(item.get("evidence_identity")))
            + "</td><td>" + escape(_wo15_value(item.get("timing_cycle_id")))
            + "</td></tr>"
            for item in history if type(item) is dict
        )
    history_panel = (
        '<section class="panel wo15-history"><div class="panel-head"><div><h2>Immutable Timing History</h2>'
        "<p>Persisted milestone order; complete evidence remains in the WO-15 store.</p>"
        '</div><span class="status neutral">' + str(len(history) if type(history) is list else 0)
        + " EVENTS</span></div><div class=\"table-wrap\"><table><thead><tr><th>Event</th>"
        "<th>Boundary</th><th>Evidence</th><th>Cycle</th></tr></thead><tbody>"
        + (history_rows or '<tr><td colspan="4">UNAVAILABLE</td></tr>')
        + "</tbody></table></div></section>"
    )
    last = status.get("last_operation")
    persisted_failure = status.get("latest_persisted_failure")
    failure = ""
    if type(last) is dict and last.get("failure_reason") is not None:
        failure += _wo15_failure("Last Operation Failure", last)
    if type(persisted_failure) is dict:
        failure += _wo15_failure("Latest Persisted Failure", persisted_failure)
    body = (
        _intraday_tabs(False, active="wo15")
        + '<div class="intraday-warning"><strong>WO-15 COMPLETED-5M ENTRY TIMING</strong>'
        "<span>TIMING EVIDENCE ONLY<br>NO SPONSOR, PAPER, LIVE, POSITION, EXECUTION OR BROKER AUTHORITY</span></div>"
        + content + history_panel + failure
        + '<div class="intraday-review-config"><strong>Control:</strong> '
        + escape(str(status.get("control_identity", "UNAVAILABLE"))) + " / "
        + escape(str(status.get("control_version", "UNAVAILABLE")))
        + "<br><strong>Runtime:</strong> "
        + ("LOADED" if status.get("runtime_loaded") is True else "UNAVAILABLE")
        + " · " + escape(str(status.get("restoration_state", "UNAVAILABLE")))
        + " · Operation " + escape(str(status.get("operation_state", "UNAVAILABLE")))
        + "<br><strong>Boundary:</strong> An explicit exact-contract POST is the only operation seam; startup and GET are inert."
        + "</div>"
    )
    return render_browser_page(
        title="Intraday WO-15",
        subtitle="Persisted completed-5M timing evidence; rendering performs no timing work.",
        snapshot=snapshot,
        active_nav="Intraday",
        active_tab="WO-15",
        body=body,
        extra_styles=_INTRADAY_CSS + _WO15_CSS,
    )


def render_intraday_wo16(
    snapshot: BrowserWorkspaceSnapshot,
    status: dict[str, object],
) -> str:
    """Render restored WO-16 decisions without creating or evaluating facts."""

    currents = status.get("current_decisions")
    current_items = currents if type(currents) is list else []
    cards = "".join(
        _wo16_current_card(item) for item in current_items if type(item) is dict
    )
    if not cards:
        cards = (
            '<div class="empty"><div><strong>'
            + escape(_wo16_value(status.get("restoration_state")))
            + "</strong><br>No persisted WO-16 Sponsor decision is current.</div></div>"
        )

    history = status.get("decision_history")
    history_items = history if type(history) is list else []
    history_rows = "".join(
        "<tr><td>" + escape(_wo16_value(item.get("canonical_subject_identity")))
        + "</td><td>" + escape(_wo16_value(item.get("choice")))
        + "</td><td>" + escape(_wo16_value(item.get("decision_timestamp")))
        + "</td><td>" + escape(_wo16_value(item.get("decision_identity")))
        + "</td><td>" + escape(_wo16_value(item.get("predecessor_decision_identity")))
        + "</td></tr>"
        for item in history_items if type(item) is dict
    )
    history_panel = (
        '<section class="panel wo16-history"><div class="panel-head"><div>'
        "<h2>Immutable Decision History</h2>"
        "<p>Append-only Sponsor choices; prior decisions are never rewritten.</p>"
        '</div><span class="status neutral">'
        + str(len(history_items))
        + ' RECORDS</span></div><div class="table-wrap"><table><thead><tr>'
        "<th>Subject</th><th>Choice</th><th>Timestamp</th><th>Decision</th>"
        "<th>Predecessor</th></tr></thead><tbody>"
        + (history_rows or '<tr><td colspan="5">UNAVAILABLE</td></tr>')
        + "</tbody></table></div></section>"
    )

    failures = status.get("latest_persisted_failures")
    failure_items = failures if type(failures) is list else []
    failure_cards = "".join(
        _wo16_failure("Latest Persisted Failure", item)
        for item in failure_items if type(item) is dict
    )
    last = status.get("last_operation")
    if type(last) is dict and last.get("failure_reason") is not None:
        failure_cards = _wo16_failure("Last Operation Failure", last) + failure_cards

    choices = ""
    if status.get("decision_controls_available") is True:
        choices = (
            '<section class="panel wo16-choices"><div class="panel-head"><div>'
            "<h2>Sponsor Decision</h2><p>Exact current qualified lineage only.</p>"
            '</div><span class="status neutral">EXPLICIT ACTION</span></div>'
            '<div class="wo16-choice-row"><button type="button" data-choice="PAPER">'
            "PAPER</button><button type=\"button\" data-choice=\"LIVE\">LIVE</button>"
            '<button type="button" data-choice="IGNORE">IGNORE</button></div></section>'
        )

    body = (
        _intraday_tabs(False, active="wo16")
        + '<div class="intraday-warning"><strong>WO-16 SPONSOR DECISION</strong>'
        "<span>EXPLICIT INTENT AND FACTUAL LIFECYCLE ADMISSION ONLY<br>"
        "NO POSITION, FILL, QUANTITY, EXECUTION OR BROKER AUTHORITY</span></div>"
        + choices
        + '<div class="wo16-current-list">' + cards + "</div>"
        + history_panel + failure_cards
        + '<div class="intraday-review-config"><strong>Policy:</strong> '
        + escape(_wo16_value(status.get("policy_identity"))) + " / "
        + escape(_wo16_value(status.get("policy_version"))) + " / "
        + escape(_wo16_value(status.get("policy_checksum")))
        + "<br><strong>Runtime:</strong> "
        + ("LOADED" if status.get("runtime_loaded") is True else "UNAVAILABLE")
        + " · " + escape(_wo16_value(status.get("restoration_state")))
        + " · Operation " + escape(_wo16_value(status.get("operation_state")))
        + "<br><strong>Restoration failure:</strong> "
        + escape(_wo16_value(status.get("failure_reason")))
        + "<br><strong>Decision vocabulary:</strong> PAPER · LIVE · IGNORE"
        + "<br><strong>Boundary:</strong> The exact governed JSON POST is the only "
        + "Sponsor operation seam. Startup and GET are inert.</div>"
    )
    return render_browser_page(
        title="Intraday WO-16",
        subtitle=(
            "Persisted Sponsor decision and lifecycle-admission evidence; "
            "rendering performs no upstream work."
        ),
        snapshot=snapshot,
        active_nav="Intraday",
        active_tab="WO-16",
        body=body,
        extra_styles=_INTRADAY_CSS + _WO16_CSS,
    )


def render_intraday_wo17(
    snapshot: BrowserWorkspaceSnapshot,
    status: dict[str, object],
) -> str:
    """Render persisted WO-17 position and lifecycle facts only."""

    currents = status.get("current_positions")
    current_items = currents if type(currents) is list else []
    cards = "".join(
        _wo17_current_card(item) for item in current_items if type(item) is dict
    )
    if not cards:
        cards = (
            '<div class="empty"><div><strong>'
            + escape(_wo16_value(status.get("restoration_state")))
            + "</strong><br>No persisted WO-17 position evidence is current.</div></div>"
        )
    history = status.get("position_history")
    history_items = history if type(history) is list else []
    history_rows = "".join(
        "<tr><td>" + escape(_wo16_value(item.get("canonical_subject_identity")))
        + "</td><td>" + escape(_wo16_value(item.get("position_state")))
        + "</td><td>" + escape(_wo16_value(item.get("monitoring_availability")))
        + "</td><td>" + escape(_wo16_value(item.get("closure_state")))
        + "</td><td>" + escape(_wo16_value(item.get("published_at")))
        + "</td></tr>"
        for item in history_items if type(item) is dict
    )
    failures = status.get("latest_persisted_failures")
    failure_items = failures if type(failures) is list else []
    failure_cards = "".join(
        _wo16_failure("Latest Persisted Failure", item)
        for item in failure_items if type(item) is dict
    )
    last = status.get("last_operation")
    if type(last) is dict and last.get("failure_reason") is not None:
        failure_cards = _wo16_failure("Last Operation Failure", last) + failure_cards
    monitoring = _dict(status.get("monitoring"))
    body = (
        _intraday_tabs(False, active="wo17")
        + '<div class="intraday-warning"><strong>FACTUAL POSITION EVIDENCE AND READ-ONLY MONITORING ONLY</strong>'
        "<span>PAPER EVIDENCE IS MODEL EVIDENCE · LIVE EVIDENCE IS SPONSOR-ATTESTED<br>"
        "NO BROKER ORDER, BROKER FILL, QUANTITY, FEES, MONETARY P&amp;L OR REALISED-R AUTHORITY</span></div>"
        + '<div class="wo17-current-list">' + cards + "</div>"
        + '<section class="panel wo17-history"><div class="panel-head"><div>'
        "<h2>Immutable Lifecycle History</h2><p>Current state, history and latest failure remain separate.</p>"
        '</div><span class="status neutral">' + str(len(history_items))
        + ' RECORDS</span></div><div class="table-wrap"><table><thead><tr>'
        "<th>Subject</th><th>Position</th><th>Monitoring</th><th>Closure</th><th>Published</th>"
        "</tr></thead><tbody>" + (history_rows or '<tr><td colspan="5">UNAVAILABLE</td></tr>')
        + "</tbody></table></div></section>" + failure_cards
        + '<div class="intraday-review-config"><strong>Policy:</strong> '
        + escape(_wo16_value(status.get("policy_identity"))) + " / "
        + escape(_wo16_value(status.get("policy_version"))) + " / "
        + escape(_wo16_value(status.get("policy_checksum")))
        + "<br><strong>Runtime:</strong> "
        + ("LOADED" if status.get("runtime_loaded") is True else "UNAVAILABLE")
        + " · " + escape(_wo16_value(status.get("restoration_state")))
        + " · Operation " + escape(_wo16_value(status.get("operation_state")))
        + "<br><strong>Monitoring:</strong> " + escape(_wo16_value(monitoring.get("state")))
        + " · bindings " + escape(str(len(monitoring.get("bindings", [])) if type(monitoring.get("bindings")) is list else 0))
        + "<br><strong>Notification-worthy events:</strong> facts only; not delivery confirmations."
        + "<br><strong>Boundary:</strong> startup and GET are inert. Exact governed POST is the only Sponsor operation seam.</div>"
    )
    return render_browser_page(
        title="Intraday WO-17",
        subtitle="Persisted position evidence and read-only lifecycle monitoring.",
        snapshot=snapshot,
        active_nav="Intraday",
        active_tab="WO-17",
        body=body,
        extra_styles=_INTRADAY_CSS + _WO17_CSS,
    )


def _wo17_current_card(item: dict[str, object]) -> str:
    plan = _dict(item.get("trade_plan"))
    risk = _dict(item.get("risk_observation"))
    timing = _dict(item.get("timing_handoff"))
    decision = _dict(item.get("sponsor_decision"))
    admission = _dict(item.get("lifecycle_admission"))
    entry = _dict(item.get("entry_evidence"))
    closure = _dict(item.get("closure"))
    assessments = item.get("lifecycle_assessments")
    assessment_items = assessments if type(assessments) is list else []
    latest_assessment = _dict(assessment_items[-1]) if assessment_items else {}
    return (
        '<article class="wo17-current"><div class="panel-head"><div><h2>'
        + escape(_wo16_value(item.get("canonical_subject_identity")))
        + "</h2><p>" + escape(_wo16_value(item.get("market_family")))
        + " · " + escape(_wo16_value(plan.get("direction")))
        + '</p></div><span class="status neutral">'
        + escape(_wo16_value(item.get("position_state"))) + "</span></div>"
        '<div class="wo17-grid">'
        + _wo16_panel("WO-13 Trade Plan", (("Identity", plan.get("trade_plan_identity")), ("Entry", plan.get("entry_reference")), ("Stop", plan.get("stop")), ("Target", plan.get("canonical_target"))))
        + _wo16_panel("WO-14 Advisory Risk Observation", (("Identity", risk.get("observation_identity")), ("State", risk.get("state")), ("Permission / veto", "NONE / NONE")))
        + _wo16_panel("WO-15 Timing Handoff", (("Identity", timing.get("handoff_identity")), ("State", timing.get("current_state")), ("Evidence boundary", timing.get("evidence_boundary"))))
        + _wo16_panel("WO-16 Decision and Admission", (("Decision identity", decision.get("decision_identity")), ("Decision", decision.get("choice")), ("Admission identity", admission.get("admission_identity")), ("Admission", admission.get("disposition"))))
        + _wo16_panel("Position Evidence", (("Role", item.get("position_evidence_role")), ("Entry price", entry.get("entry_price")), ("Entry timestamp", entry.get("entry_timestamp")), ("Broker fill", "UNAVAILABLE")))
        + _wo16_panel("Lifecycle Observation", (("Monitoring", item.get("monitoring_availability")), ("Assessment", latest_assessment.get("assessment_code")), ("Stop observed", latest_assessment.get("stop_observed")), ("Target observed", latest_assessment.get("target_observed")), ("Invalidation observed", latest_assessment.get("invalidation_observed"))))
        + _wo16_panel("Closure / Exit", (("Closure", closure.get("closure_state")), ("Exit price", closure.get("exit_price")), ("Exit timestamp", closure.get("exit_timestamp")), ("Attestation", item.get("live_exit_attestation"))))
        + _wo16_panel("Session and Exact Lineage", (("Session", item.get("session_identity")), ("Trading date", item.get("trading_date")), ("Instrument", item.get("instrument_identity")), ("Actual contract", item.get("actual_contract_identity")), ("Contract expiry", item.get("contract_expiry")), ("Roll lineage", item.get("roll_lineage_identity"))))
        + _wo16_panel("Economics and Delivery", (("Quantity", "UNAVAILABLE"), ("Fees", "UNAVAILABLE"), ("Monetary P&L", "UNAVAILABLE"), ("Realised R", "UNAVAILABLE"), ("Notifications delivered", "NO"), ("Broker order", "NONE")))
        + "</div></article>"
    )


_WO17_CSS = r"""
.wo17-current{border:1px solid var(--line);border-radius:12px;padding:14px;margin-bottom:14px;background:var(--panel)}
.wo17-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.wo17-grid .panel{min-width:0}
.wo17-grid dd,.wo17-history td{overflow-wrap:anywhere}.wo17-history{margin-top:14px}
@media(max-width:760px){.wo17-grid{grid-template-columns:1fr}.wo17-history .table-wrap{overflow-x:auto}.wo17-history table{min-width:680px}}
"""


def _wo16_current_card(item: dict[str, object]) -> str:
    plan = _dict(item.get("trade_plan"))
    risk = _dict(item.get("risk_observation"))
    timing = _dict(item.get("timing_handoff"))
    session = _dict(item.get("session"))
    decision = _dict(item.get("sponsor_decision"))
    admission = _dict(item.get("lifecycle_admission"))
    pointer = _dict(item.get("current_pointer"))
    return (
        '<article class="wo16-current"><div class="panel-head"><div><h2>'
        + escape(_wo16_value(item.get("canonical_subject_identity")))
        + "</h2><p>" + escape(_wo16_value(item.get("market_family")))
        + " · " + escape(_wo16_value(plan.get("direction")))
        + " · " + escape(_wo16_value(plan.get("setup_family")))
        + '</p></div><span class="status neutral">'
        + escape(_wo16_value(decision.get("choice"))) + "</span></div>"
        '<div class="wo16-grid">'
        + _wo16_panel("WO-13 Trade Plan", (
            ("Identity", plan.get("trade_plan_identity")),
            ("Entry Reference", plan.get("entry_reference")),
            ("Stop", plan.get("stop")),
            ("Canonical Target", plan.get("canonical_target")),
            ("Model R:R", plan.get("model_rr")),
        ))
        + _wo16_panel("WO-14 Risk Observation — ADVISORY ONLY", (
            ("Identity", risk.get("observation_identity")),
            ("State", risk.get("state")),
            ("Authority", risk.get("authority")),
            ("Permission / veto", "NONE / NONE"),
        ))
        + _wo16_panel("WO-15 Timing Handoff", (
            ("Identity", timing.get("handoff_identity")),
            ("State", timing.get("current_state")),
            ("Qualification path", timing.get("qualification_path")),
            ("Completed-5M boundary", timing.get("evidence_boundary")),
        ))
        + _wo16_panel("WO-16 Sponsor Decision", (
            ("Decision", decision.get("decision_identity")),
            ("Choice", decision.get("choice")),
            ("Source", decision.get("source")),
            ("Timestamp", decision.get("decision_timestamp")),
        ))
        + _wo16_panel("Lifecycle Admission", (
            ("Admission", admission.get("admission_identity")),
            ("Disposition", admission.get("disposition")),
            ("Reason", admission.get("reason")),
            ("Position consequence", admission.get("position_consequence")),
        ))
        + _wo16_panel("Current Session and Lineage", (
            ("Session", session.get("session_identity")),
            ("Trading date", item.get("trading_date")),
            ("Instrument", item.get("instrument_identity")),
            ("Actual contract", item.get("actual_contract_identity")),
            ("Roll lineage", item.get("roll_lineage_identity")),
            ("Current pointer", pointer.get("pointer_identity")),
        ))
        + _wo16_panel("Actual Position Facts", (
            ("Position created", "NO"),
            ("Broker order placed", "NO"),
            ("Fill", item.get("actual_fill")),
            ("Quantity", item.get("quantity")),
            ("P&L", item.get("pnl")),
            ("Realised R", item.get("realised_r")),
        ))
        + "</div></article>"
    )


def _wo16_panel(title: str, values: tuple[tuple[str, object], ...]) -> str:
    facts = "".join(
        "<dt>" + escape(label) + "</dt><dd>" + escape(_wo16_value(value))
        + "</dd>" for label, value in values
    )
    return '<section class="panel"><h3>' + escape(title) + "</h3><dl>" + facts + "</dl></section>"


def _wo16_failure(title: str, value: dict[str, object]) -> str:
    return (
        '<section class="intraday-panel intraday-unavailable wo16-failure"><h2>'
        + escape(title) + "</h2><strong>FAILED</strong><p>"
        + escape(_wo16_value(value.get("failure_stage") or value.get("stage")))
        + " · "
        + escape(_wo16_value(value.get("failure_reason") or value.get("reason")))
        + "</p></section>"
    )


def _wo16_value(value: object) -> str:
    return "UNAVAILABLE" if value is None else str(value)


_WO16_CSS = r"""
.wo16-current{border:1px solid var(--line);border-radius:12px;padding:14px;
margin-bottom:14px;background:var(--panel)}
.wo16-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.wo16-grid .panel{min-width:0}
.wo16-grid dd,.wo16-history td{overflow-wrap:anywhere}
.wo16-history,.wo16-failure,.wo16-choices{margin-top:14px}
.wo16-choice-row{display:flex;gap:10px;flex-wrap:wrap}
@media(max-width:760px){.wo16-grid{grid-template-columns:1fr}
.wo16-history .table-wrap{overflow-x:auto}.wo16-history table{min-width:760px}}
"""


def _dict(value: object) -> dict[str, object]:
    return value if type(value) is dict else {}


def _nested(value: dict[str, object], *path: str) -> object:
    current: object = value
    for key in path:
        if type(current) is not dict:
            return None
        current = current.get(key)
    return current


def _wo15_value(value: object) -> str:
    return "UNAVAILABLE" if value is None else str(value)


def _wo15_list(value: object) -> str:
    if type(value) is not list or not value:
        return "UNAVAILABLE"
    return " · ".join(
        str(item.get("reference_identity", "UNAVAILABLE"))
        if type(item) is dict else str(item) for item in value
    )


def _wo15_failure(title: str, value: dict[str, object]) -> str:
    return (
        '<section class="intraday-panel intraday-unavailable wo15-failure"><h2>'
        + escape(title) + "</h2><strong>"
        + escape(_wo15_value(value.get("outcome") or "FAILED")) + "</strong><p>"
        + escape(_wo15_value(value.get("failure_stage") or value.get("stage")))
        + " · " + escape(_wo15_value(value.get("failure_reason") or value.get("reason")))
        + "</p></section>"
    )


_WO15_CSS = r"""
.wo15-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.wo15-grid .panel{min-width:0}.wo15-grid dd,.wo15-history td{overflow-wrap:anywhere}.wo15-telemetry{border-color:#6b5f31}.wo15-handoff{border-color:#315d54}.wo15-history{margin-top:14px}.wo15-failure{margin-top:14px}@media(max-width:760px){.wo15-grid{grid-template-columns:1fr}.wo15-history .table-wrap{overflow-x:auto}.wo15-history table{min-width:680px}}
"""


def _wo13_value(value: object) -> str:
    return "UNAVAILABLE" if value is None else str(value)


def _wo14_value(value: object) -> str:
    return "UNAVAILABLE" if value is None else str(value)


def _list_text(value: object) -> str:
    return ", ".join(str(item) for item in value) if type(value) is list and value else "NONE"


def _review_v2_projection(
    snapshot: IntradayReviewV2Snapshot | None,
    available_run: ProbablesRunV2 | None,
    status: dict[str, object] | None,
    focused_candidate: str | None = None,
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
    currentness = "NO_CURRENT_PROBABLES" if status is None else str(
        status.get("currentness_state", "NO_CURRENT_PROBABLES")
    )
    current_review_run = None if status is None else status.get(
        "current_review_probables_run_identity"
    )
    current_review_boundary = None if status is None else status.get(
        "current_review_analysis_boundary"
    )
    current_review_count = 0 if status is None else status.get(
        "current_review_candidate_count", 0
    )
    current_probables_count = 0 if status is None else status.get(
        "current_probables_candidate_count", 0
    )
    banner_label = {
        "REVIEW_CURRENT": "REVIEW CURRENT",
        "REVIEW_ABSENT": "NEW PROBABLES AVAILABLE",
        "NEW_PROBABLES_AVAILABLE": "NEW PROBABLES AVAILABLE",
        "NO_REVIEW_CANDIDATES": "NO REVIEW CANDIDATES",
        "INTEGRITY_INVALID": "REVIEW CURRENTNESS UNAVAILABLE",
    }.get(currentness, "NO CURRENT PROBABLES AVAILABLE")
    banner_class = (
        "outdated"
        if currentness in {"REVIEW_ABSENT", "NEW_PROBABLES_AVAILABLE"}
        else "invalid"
        if currentness == "INTEGRITY_INVALID"
        else "current"
    )
    currentness_banner = (
        '<div class="intraday-review-currentness ' + banner_class + '"><strong>'
        + escape(banner_label) + '</strong><div class="intraday-review-currentness-facts">'
        '<span>LATEST PROBABLES · '
        + escape(
            "UNAVAILABLE"
            if available_run is None
            else _ist_time(available_run.analysis_boundary)
        )
        + ' · ' + escape(str(current_probables_count)) + ' candidates<br>'
        + escape("UNAVAILABLE" if available_run is None else available_run.run_identity)
        + '</span><span>CURRENT REVIEW · '
        + escape(_review_v2_status_time(current_review_boundary))
        + ' · ' + escape(str(current_review_count)) + ' candidates<br>'
        + escape("UNAVAILABLE" if current_review_run is None else str(current_review_run))
        + '</span></div></div>'
    )
    focus_notice = ""
    if focused_candidate is not None and not any(
        item.probable_result_identity == focused_candidate for item in snapshot.candidates
    ):
        in_latest = available_run is not None and any(
            item.result_identity == focused_candidate
            and item.state in {ProbableState.LONG_PROBABLE, ProbableState.SHORT_PROBABLE}
            for item in available_run.results
        )
        focus_notice = (
            '<p class="intraday-review-focus-notice" role="status">'
            + ("Candidate is in latest Probables but not current Review. Load Fresh Review required."
               if in_latest else "Requested candidate is not in latest Probables or current Review.")
            + '</p>'
        )
    control = ""
    if (
        available_run is not None
        and currentness in {"REVIEW_ABSENT", "NEW_PROBABLES_AVAILABLE"}
        and bool(current_probables_count)
    ):
        methodology = available_run.methodology
        control = (
            '<div class="intraday-review-v2-control"><button type="button" '
            'id="intraday-create-review-v2" data-run="'
            + escape(available_run.run_identity, quote=True)
            + '" data-methodology="' + escape(methodology.methodology_identity, quote=True)
            + '" data-methodology-version="' + escape(methodology.methodology_version, quote=True)
            + '" data-methodology-publication="' + escape(methodology.publication_identity, quote=True)
            + '" data-methodology-checksum="' + escape(methodology.payload_checksum, quote=True)
            + '">LOAD FRESH REVIEW</button><span>Review intake only · exact current persisted run · '
            + escape(available_run.run_identity) + '</span></div>'
        )
    elif currentness == "REVIEW_CURRENT":
        control = (
            '<div class="intraday-review-v2-control"><button type="button" disabled>'
            'REVIEW CURRENT</button><span>No duplicate Review intake will be created.</span></div>'
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
        + str(len(snapshot.candidates)) + '</span></div>' + currentness_banner + focus_notice + control
        + '<div class="intraday-review-v2-grid">'
        + empty + '</div>' + phase_b + '</section>'
    )


def _review_v2_status_time(value: object) -> str:
    if type(value) is not str:
        return "UNAVAILABLE"
    try:
        return _ist_time(datetime.fromisoformat(value))
    except ValueError:
        return "UNAVAILABLE"


def _review_v2_candidate(item, slot_index: int) -> str:  # type: ignore[no-untyped-def]
    target_identity = f"intraday-v2-chart-slot-{slot_index}"
    input_identity = f"intraday-v2-chart-file-{slot_index}"
    cycle = quote(item.cycle_identity, safe="")
    if item.chart_revision_ordinal is None:
        chart_content = (
            '<div class="intraday-intake-copy"><strong>PASTE TRADINGVIEW CHART</strong>'
            '<span class="required-panels">Cmd+V / Ctrl+V · ONE COMPOSITE</span></div>'
        )
        received_class = ""
        replace_action = ""
    else:
        chart_content = (
            '<div class="intraday-chart-received"><strong>TRADINGVIEW COMPOSITE · RECEIVED</strong>'
            '<span>' + escape(item.canonical_subject_identity) + '</span><span>Chart Revision · REV '
            + f"{item.chart_revision_ordinal:03d}"
            + '</span></div>'
        )
        received_class = " received"
        replace_action = (
            '<button class="intraday-replace-chart" type="button" data-target="'
            + target_identity + '">Replace</button>'
        )
    file_choice = (
        '<div class="intraday-chart-slot-actions">' + replace_action
        + '<label class="intraday-file-choice" for="' + input_identity + '">Choose File</label>'
        '<input id="' + input_identity + '" class="intraday-chart-input" type="file" '
        'accept="image/png,image/jpeg" aria-label="Choose one complete TradingView composite" '
        'data-target="' + target_identity + '"></div>'
    )
    empty_chart = item.chart_revision_ordinal is None
    upload = (
        '<div class="intraday-review-section-title">TRADINGVIEW CHARTS</div>'
        '<div id="' + target_identity + '" class="intraday-drop'
        + (' intraday-drop-empty' if empty_chart else received_class)
        + '" role="group" tabindex="0" aria-label="Paste or choose one TradingView composite for '
        + escape(item.canonical_subject_identity)
        + '" data-review-v2-chart="true" data-upload-url="' + REVIEW_V2_CHART_ROUTE + '?cycle=' + cycle + '">'
        + chart_content + (file_choice if empty_chart else '') + '</div>'
        + ('' if empty_chart else file_choice)
        + '<p id="' + target_identity + '-feedback" role="status" aria-live="polite" hidden></p>'
    )
    return (
        '<article class="intraday-review-v2-card" tabindex="-1" id="review-candidate-'
        + escape(item.probable_result_identity, quote=True) + '"><h3>'
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
        'const d=await r.json();if(!r.ok||d.outcome!=="COMPLETE"||'
        '! ["CURRENTIZED","ALREADY_CURRENT"].includes(d.currentization_state))'
        'throw new Error("Reload Review to check the exact current Probables.");location.reload();}'
        'catch(e){b.disabled=false;window.alert("Review intake currentization failed: "+String(e));}});})();</script>'
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


def _review_v2_chart_script() -> str:
    """Explicit image-only paste; original bytes share the file intake path."""
    script = r"""<script>
(()=>{
const accepted=new Set(['image/png','image/jpeg']);
const failures=new Set(['NO_IMAGE_IN_CLIPBOARD','UNSUPPORTED_IMAGE_TYPE','AMBIGUOUS_CLIPBOARD_IMAGES',
 'IMAGE_TOO_LARGE','INVALID_CANDIDATE_BINDING','STALE_REVIEW_CYCLE','INVALID_CHART_IMAGE','CHART_PERSISTENCE_FAILURE']);
function report(target,reason){
 const feedback=document.getElementById(target.id+'-feedback');
 if(feedback){feedback.hidden=false;feedback.textContent=failures.has(reason)?reason:'CHART_PERSISTENCE_FAILURE';}
}
async function receive(target,file){
 if(target.getAttribute('aria-busy')==='true')return;
 if(!file){report(target,'NO_IMAGE_IN_CLIPBOARD');return;}
 if(!accepted.has(file.type)){report(target,'UNSUPPORTED_IMAGE_TYPE');return;}
 if(file.size>__MAX_CHART_BYTES__){report(target,'IMAGE_TOO_LARGE');return;}
 const url=new URL(target.dataset.uploadUrl,location.href);
 if(url.origin!==location.origin||url.pathname!=='__CHART_ROUTE__'||
    url.searchParams.getAll('cycle').length!==1||[...url.searchParams.keys()].length!==1){
   report(target,'INVALID_CANDIDATE_BINDING');return;}
 const cycle=url.searchParams.get('cycle');
 target.setAttribute('aria-busy','true');
 try{
  const response=await fetch(url.pathname+url.search,{method:'POST',headers:{'Content-Type':file.type},body:file});
  const result=await response.json();
  if(!response.ok){report(target,result.reason);return;}
  if(result.outcome!=='CHART_RECEIVED'||result.cycle_identity!==cycle){report(target,'INVALID_CANDIDATE_BINDING');return;}
  const card=target.closest('.intraday-review-v2-card');
  if(card)history.replaceState(null,'',location.pathname+location.search+'#'+card.id);
  location.reload();
 }catch(_error){report(target,'CHART_PERSISTENCE_FAILURE');}
 finally{target.removeAttribute('aria-busy');}
}
for(const target of document.querySelectorAll('[data-review-v2-chart]')){
 target.addEventListener('click',()=>target.focus());
 target.addEventListener('paste',event=>{
  event.preventDefault();
  if(document.activeElement!==target){report(target,'INVALID_CANDIDATE_BINDING');return;}
  const files=Array.from(event.clipboardData?.items||[]).filter(item=>item.kind==='file');
  if(files.length===0){report(target,'NO_IMAGE_IN_CLIPBOARD');return;}
  if(files.length!==1){report(target,'AMBIGUOUS_CLIPBOARD_IMAGES');return;}
  if(!accepted.has(files[0].type)){report(target,'UNSUPPORTED_IMAGE_TYPE');return;}
  receive(target,files[0].getAsFile());
 });
}
for(const input of document.querySelectorAll('.intraday-chart-input')){
 const target=document.getElementById(input.dataset.target);
 if(!target?.hasAttribute('data-review-v2-chart'))continue;
 input.addEventListener('change',()=>{
  if(input.files?.length===1)receive(target,input.files[0]);
  else if(input.files?.length>1)report(target,'AMBIGUOUS_CLIPBOARD_IMAGES');
 });
}
})();</script>"""
    return script.replace("__MAX_CHART_BYTES__", str(MAX_CHART_BYTES)).replace("__CHART_ROUTE__", REVIEW_V2_CHART_ROUTE)


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
  if(target.hasAttribute('data-review-v2-chart'))continue;
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
  if(document.getElementById(input.dataset.target)?.hasAttribute('data-review-v2-chart'))continue;
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
    market_availability: tuple[IntradayMarketAvailability, ...] = (),
    refresh_status: dict[str, object] | None = None,
    latest_evaluable_run: ProbablesRunV2 | None = None,
    review_v2: IntradayReviewV2Snapshot | None = None,
) -> str:
    if isinstance(snapshot, IntradayDiscoverySnapshot):
        return _render_discovery_triage(
            snapshot,
            refresh_enabled=refresh_enabled,
            market_availability=market_availability,
            refresh_status=refresh_status,
            latest_evaluable_run=latest_evaluable_run,
            review_v2=review_v2,
        )
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
    market_availability: tuple[IntradayMarketAvailability, ...] = (),
    refresh_status: dict[str, object] | None = None,
    latest_evaluable_run: ProbablesRunV2 | None = None,
    review_v2: IntradayReviewV2Snapshot | None = None,
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
            market_availability=market_availability,
            refresh_status=refresh_status,
            latest_evaluable_run=latest_evaluable_run,
            review_v2=review_v2,
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
            + _render_market_availability(market_availability)
            + _render_analysis_freshness(
                market_availability,
                refresh_status,
                current_run=None,
                latest_evaluable_run=latest_evaluable_run,
            )
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
    market_availability: tuple[IntradayMarketAvailability, ...] = (),
    refresh_status: dict[str, object] | None = None,
    latest_evaluable_run: ProbablesRunV2 | None = None,
    review_v2: IntradayReviewV2Snapshot | None = None,
) -> str:
    """Project persisted V2 facts only; no analytical recomputation occurs."""

    current_run = run
    current_is_evaluable = current_run.diagnostics.evaluable_count > 0
    projection_run = (
        current_run
        if current_is_evaluable
        else latest_evaluable_run
    )
    reference_only = (
        projection_run is not None
        and projection_run.run_identity != current_run.run_identity
    )
    presented_run = current_run if projection_run is None else projection_run
    diagnostics = presented_run.diagnostics
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
        for item in presented_run.results
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
    diagnostics_results = tuple(
        item for item in current_run.results if item not in admitted
    )
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
    current_review = (
        review_v2 if review_v2 is not None
        and review_v2.probables_run_identity == presented_run.run_identity else None
    )
    market_groups = (
        '<div class="intraday-opportunities-grid" data-layout="equity-left-mcx-right">'
        + _render_v2_market_group("EQUITY / INDEX", equity, members, current_review)
        + _render_v2_market_group("MCX", mcx, members, current_review)
        + "</div>"
    )
    phase_counts = " · ".join(
        f"{phase.value} {count}" for phase, count in diagnostics.phase_counts if count
    ) or "PHASE UNAVAILABLE"
    prior_projection = ""
    if reference_only:
        prior_projection = (
            '<div class="intraday-prior-projection"><strong>'
            'PRIOR SESSION / REFERENCE ONLY</strong><span>Original analysis timestamp: '
            + escape(_ist_time(presented_run.analysis_boundary))
            + ' · Original trading date: '
            + escape(presented_run.analysis_boundary.astimezone(_KOLKATA).date().isoformat())
            + '</span><span>STALE — NOT NEWLY QUALIFIED OR ACTIONABLE TODAY</span></div>'
        )
    current_diagnostic_note = ""
    if not current_is_evaluable:
        current_diagnostic_note = (
            '<details class="intraday-probables-diagnostics"><summary>'
            'TECHNICAL DIAGNOSTICS</summary><p class="intraday-status">'
            'NO EVALUABLE PHASE · Current refresh produced zero evaluable instruments. '
            'The immutable prior evaluable projection, if present, remains separate.</p></details>'
        )
    return (
        _intraday_tabs(refresh_enabled)
        + _render_market_availability(market_availability)
        + _render_analysis_freshness(
            market_availability,
            refresh_status,
            current_run=current_run,
            latest_evaluable_run=latest_evaluable_run,
        )
        + '<div class="analysis-batch"><span>Market analysis</span>'
        '<div class="analysis-run-times"><strong>'
        + escape(
            "NOT YET EVALUABLE — WAITING FOR MARKET WINDOW"
            if not current_is_evaluable
            else last
        )
        + '</strong></div></div>'
        + failure
        + prior_projection
        + metric_html
        + '<div class="intraday-methodology"><strong>'
        + escape(presented_run.methodology.methodology_identity)
        + ' · ' + escape(presented_run.methodology.methodology_version)
        + '</strong> · ' + escape(_ist_time(presented_run.analysis_boundary))
        + ' · ' + escape(phase_counts)
        + '. Phase-aware admission for deeper review only; no score, rank, confidence, trading, Risk or broker authority.</div>'
        + market_accounting
        + market_groups
        + current_diagnostic_note
        + _render_v2_diagnostics(diagnostics_results, members)
    )


def _render_market_availability(
    market_availability: tuple[IntradayMarketAvailability, ...],
) -> str:
    if not market_availability:
        return ""
    cards = "".join(
        '<article class="intraday-availability-card '
        + escape(item.state.value.lower().replace("_", "-"))
        + '"><span>' + escape(item.market_family) + '</span><strong>'
        + escape(item.display) + '</strong></article>'
        for item in market_availability
    )
    return '<div class="intraday-availability-grid">' + cards + "</div>"


def _render_analysis_freshness(
    market_availability: tuple[IntradayMarketAvailability, ...],
    refresh_status: dict[str, object] | None,
    *,
    current_run: ProbablesRunV2 | None,
    latest_evaluable_run: ProbablesRunV2 | None,
) -> str:
    if (
        not market_availability
        and refresh_status is None
        and latest_evaluable_run is None
    ):
        return ""
    status = {} if refresh_status is None else refresh_status
    attempt = status.get("last_refresh_attempt")
    if type(attempt) is dict:
        attempt_time = _status_time(attempt.get("attempted_at"))
        attempt_outcome = _plain(str(attempt.get("outcome") or "UNAVAILABLE"))
        last_attempt = attempt_time + " · " + attempt_outcome
    else:
        last_attempt = "NOT YET RUN"
    evaluable = latest_evaluable_run
    if current_run is not None and current_run.diagnostics.evaluable_count > 0:
        evaluable = current_run
    last_evaluable = (
        "NOT YET AVAILABLE"
        if evaluable is None
        else _ist_time(evaluable.analysis_boundary)
    )
    available = tuple(item.market_family for item in market_availability if item.available)
    if not market_availability:
        current_window = "UNAVAILABLE"
    elif not available:
        current_window = "REFRESH UNAVAILABLE — NO MARKET IS CURRENTLY EVALUABLE"
    else:
        current_window = "REFRESH AVAILABLE FOR: " + " + ".join(available)
    if current_run is None:
        analysis_status = "NOT YET RUN"
    elif current_run.diagnostics.evaluable_count == 0:
        analysis_status = "NOT YET EVALUABLE — WAITING FOR MARKET WINDOW"
    else:
        analysis_status = "EVALUABLE ANALYSIS AVAILABLE"
    facts = (
        ("Last refresh attempt", last_attempt),
        ("Last successful evaluable analysis", last_evaluable),
        ("Current market window", current_window),
        ("Current analysis status", analysis_status),
    )
    return (
        '<section class="intraday-freshness"><h2>ANALYSIS FRESHNESS</h2>'
        '<div class="intraday-freshness-grid">'
        + "".join(
            '<div><span>' + escape(label) + '</span><strong>'
            + escape(value) + '</strong></div>'
            for label, value in facts
        )
        + "</div></section>"
    )


def _status_time(value: object) -> str:
    if not isinstance(value, str):
        return "UNAVAILABLE"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return "UNAVAILABLE"
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return "UNAVAILABLE"
    return _ist_time(parsed)


def _opportunity_review_status(result, snapshot) -> str:  # type: ignore[no-untyped-def]
    """Present exact current Review facts; never infer analytical readiness."""
    candidate = next((item for item in (() if snapshot is None else snapshot.candidates)
                      if item.probable_result_identity == result.result_identity), None)
    if candidate is None:
        return "NOT LOADED"
    if candidate.chart_state == "CHART_REQUIRED":
        return "CHART REQUIRED"
    facts = [candidate.chart_state.replace("_", " ")]
    if candidate.question_pack_state != "ABSENT":
        facts.append("QUESTION PACK " + candidate.question_pack_state.replace("_", " "))
    facts.append("ANSWER " + candidate.answer_state.replace("_", " "))
    return " · ".join(facts)


def _probable_v2_card(result, sponsor_label: str, review_v2=None) -> str:  # type: ignore[no-untyped-def]
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
    nifty, nifty_detail = _probable_v2_nifty_projection(result)
    reason = " · ".join(_plain(item.value) for item in result.reasons)
    review_status = _opportunity_review_status(result, review_v2)
    target = quote(result.result_identity, safe="")
    review_href = "/intraday/review?candidate=" + target + "#review-candidate-" + target
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
        + _card_fact("NIFTY", nifty, detail=nifty_detail)
        + '</div><div class="summary-footer"><span class="summary-rr">Result <strong>'
        + escape(_plain(result.state.value))
        + '</strong></span><span>' + escape(reason) + '</span></div>'
        + '<div class="intraday-opportunity-review"><span>Review · <strong>'
        + escape(review_status) + '</strong></span><a class="detail-link" href="'
        + escape(review_href, quote=True) + '">Open Native Review →</a></div></article>'
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


def _render_v2_market_group(title: str, results, members, review_v2=None) -> str:  # type: ignore[no-untyped-def]
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
        + _render_v2_direction_group("LONG", long_results, members, review_v2)
        + _render_v2_direction_group("SHORT", short_results, members, review_v2)
        + '</section>'
    )


def _render_v2_direction_group(direction: str, results, members, review_v2=None) -> str:  # type: ignore[no-untyped-def]
    cards = "".join(
        _probable_v2_card(item, _v2_member_label(item, members), review_v2) for item in results
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
    failure = ""
    provenance = None if member is None else getattr(
        member, "failure_provenance", None
    )
    if provenance is not None:
        timeframe = (
            "NOT_APPLICABLE"
            if provenance.required_timeframe is None
            else provenance.required_timeframe.value
        )
        interval = provenance.expected_candle_interval or "NOT_APPLICABLE"
        failure = (
            " · Machine fact failure: "
            + provenance.failure_stage.value
            + " / "
            + provenance.required_component.value
            + " / "
            + timeframe
            + " / "
            + interval
            + " / "
            + provenance.availability_failure.value
            + " / "
            + provenance.sanitized_failure_code
        )
    return (
        '<div class="intraday-diagnostic-row"><strong>'
        + escape(_v2_member_label(result, members)) + '</strong><span>'
        + escape(state) + '</span><span>' + escape(family)
        + ' · Semantic direction (diagnostic) ' + escape(direction)
        + '</span><span>' + escape(reasons + failure) + '</span></div>'
    )


def _probable_v2_nifty_projection(result) -> tuple[str, str | None]:  # type: ignore[no-untyped-def]
    nifty_applicability = getattr(result, "nifty_applicability", None)
    if (
        nifty_applicability is not None
        and nifty_applicability.value == "NOT_APPLICABLE"
    ):
        return "NOT APPLICABLE", None
    phase = None if result.phase is None else result.phase.value
    if phase in {
        "STRUCTURE",
        "FIRST_CURRENT_SESSION_1H",
        "CURRENT_SESSION_ESTABLISHED",
    }:
        return "NOT EVALUATED IN THIS PHASE", "OPENING LINEAGE RETAINED"
    if result.nifty_relationship is not None:
        return result.nifty_relationship.value, None
    return "UNAVAILABLE", None


def _card_fact(label: str, value: str, *, detail: str | None = None) -> str:
    return (
        '<span class="intraday-card-fact"><span>' + escape(label)
        + '</span><strong>' + escape(value) + '</strong>'
        + ("" if detail is None else '<small>' + escape(detail) + '</small>')
        + '</span>'
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
        '<a class="' + ('active' if active == 'wo13' else '') + '" href="/intraday/wo13">WO-13</a>'
        '<a class="' + ('active' if active == 'wo14' else '') + '" href="/intraday/wo14">WO-14</a>'
        '<a class="' + ('active' if active == 'wo15' else '') + '" href="/intraday/wo15">WO-15</a>'
        '<a class="' + ('active' if active == 'wo16' else '') + '" href="/intraday/wo16">WO-16</a>'
        '<a class="' + ('active' if active == 'wo17' else '') + '" href="/intraday/wo17">WO-17</a>'
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
    failure = item.failure_provenance
    failure_detail = ""
    if failure is not None:
        failure_detail = (
            '<details class="intraday-probables-diagnostics"><summary>'
            'MACHINE-FACT FAILURE PROVENANCE</summary>'
            + _facts((
                ("Failure stage", failure.failure_stage.value),
                ("Required component", failure.required_component.value),
                (
                    "Required timeframe",
                    "NOT APPLICABLE"
                    if failure.required_timeframe is None
                    else failure.required_timeframe.value,
                ),
                (
                    "Expected interval",
                    failure.expected_candle_interval or "NOT APPLICABLE",
                ),
                ("Availability / completion", failure.availability_failure.value),
                ("Sanitized failure code", failure.sanitized_failure_code),
                ("Provider symbol binding", failure.provider_symbol_binding or "UNAVAILABLE"),
                ("Trading date", failure.trading_date.isoformat()),
                ("Session", failure.market_session_identity),
                ("Operation", failure.operation_identity),
                ("Policy", failure.policy_identity + " / " + failure.policy_version),
                ("Integrity", failure.integrity_hash),
            ))
            + '</details>'
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
    return header + lineage + failure_detail + factual + detail


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
    "render_intraday_wo13",
    "render_intraday_wo14",
    "render_intraday_wo15",
    "render_intraday_wo16",
    "render_intraday_wo17",
    "render_intraday_workstation",
]
