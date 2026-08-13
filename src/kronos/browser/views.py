"""Escaped server-rendered views for the KRONOS Browser V1 workstation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from html import escape
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from kronos.application.swing_opportunities import (
    AnalysisState,
    BrowserWorkspaceSnapshot,
    MarketPanel,
    OpportunitySnapshot,
    ProviderConnectionState,
    V1ProbableSnapshot,
)
from kronos.application.live_monitoring_e2e import (
    LiveMonitoringTestResult,
    LiveMonitoringTestState,
)
from kronos.application.swing_v1_review import (
    ChartAnalysisState,
    InstrumentChartAnalysisSnapshot,
    V1ReviewWorkflowSnapshot,
)
from kronos.configuration.openai_chart_analyst import (
    ChartAnalystConnectionStatus,
    ChartAnalystV2ActivationStatus,
)
from kronos.provider.contracts.monitoring import MonitoringConnectionState
from kronos.browser.v1_analysis_status import (
    batch_analysis_status,
    instrument_analysis_status,
)
from kronos.swing.run_identity import (
    LEGACY_UNBOUND_SWING_RUN_ID,
    is_swing_analysis_run_id,
)
from kronos.swing.v1.step32 import (
    CandidateLifecycle,
    CandidateLifecycleState,
    ObjectiveModelState,
    ObjectiveModelTrade,
    RiskApproval,
    SponsorDecision,
    SponsorPosition,
)
from kronos.swing.v1.trade_construction import SwingV1TradeCandidate


_NAVIGATION = (
    ("Dashboard", "/dashboard", "home"),
    ("Swing", "/swing/opportunities", "swing"),
    ("Intraday", "/intraday", "bolt"),
    ("Theta Earners", "/theta-earners", "theta"),
    ("Trading Journal", "/journal", "journal"),
    ("Portfolio", "/portfolio", "portfolio"),
    ("Reports", "/reports", "reports"),
    ("Settings", "/settings", "settings"),
)
_KOLKATA = ZoneInfo("Asia/Kolkata")

_CSS = r"""
:root{color-scheme:dark;--bg:#03101c;--panel:#071827;--panel2:#0a1e30;--line:#1b3549;--text:#f2f7fb;--muted:#92a8b9;--blue:#2c9cff;--green:#2ed477;--red:#ff5c63;--amber:#f6b73c;--violet:#bc7cff}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 78% 0,#0a2237 0,#03101c 38%,#020b14 100%);color:var(--text);font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;min-height:100vh}
a{color:inherit;text-decoration:none}.app{display:grid;grid-template-columns:218px 1fr;min-height:100vh}.sidebar{position:sticky;top:0;height:100vh;border-right:1px solid var(--line);background:rgba(3,15,26,.96);padding:22px 14px;display:flex;flex-direction:column}.brand{display:flex;align-items:center;gap:11px;font-size:25px;font-weight:800;letter-spacing:.04em;padding:2px 9px 22px}.brandmark{width:35px;height:35px;border-radius:8px;background:linear-gradient(135deg,#50b7ff,#1769c8);display:grid;place-items:center;font-weight:900}.nav{display:grid;gap:7px}.nav a{display:flex;gap:12px;align-items:center;padding:12px 13px;border-radius:8px;color:#d7e4ee}.nav a:hover,.nav a.active{background:#0c3962;color:#fff}.nav .icon{width:19px;color:#6bb9ff;text-align:center}.system{margin-top:auto;border:1px solid var(--line);border-radius:9px;padding:13px;color:var(--muted);font-size:12px}.system strong{display:block;color:var(--green);margin-bottom:6px}.main{min-width:0}.topbar{height:78px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:0 28px;background:rgba(3,15,26,.78);backdrop-filter:blur(12px)}.title h1{font-size:27px;margin:0}.title p{margin:2px 0 0;color:var(--muted)}.kite{display:flex;align-items:center;gap:12px}.dot{width:9px;height:9px;border-radius:50%;background:var(--muted);box-shadow:0 0 14px currentColor}.dot.CONNECTED{background:var(--green)}.dot.CONNECTING{background:var(--amber)}.dot.ERROR{background:var(--red)}button,.button{border:1px solid #246295;background:#0b2b47;color:#e9f5ff;padding:9px 14px;border-radius:7px;font:inherit;font-weight:650;cursor:pointer}button.primary{background:linear-gradient(135deg,#178ddf,#1466b4);border-color:#35a9f5}button:disabled{opacity:.45;cursor:not-allowed}.tabs{display:flex;align-items:center;gap:22px;border-bottom:1px solid var(--line);padding:0 28px;height:61px}.tabs a{height:61px;display:flex;align-items:center;color:var(--muted);border-bottom:2px solid transparent}.tabs a.active{color:#fff;border-color:var(--blue)}.badge{font-size:11px;border-radius:999px;padding:2px 7px;background:#172b3a;margin-left:6px}.toolbar{margin-left:auto}.content{padding:22px 28px 40px}.status-grid{display:grid;grid-template-columns:repeat(6,minmax(120px,1fr));gap:10px;margin-bottom:18px}.metric{border:1px solid var(--line);background:linear-gradient(150deg,rgba(12,35,55,.9),rgba(5,20,33,.92));border-radius:9px;padding:13px}.metric label{display:block;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.05em}.metric strong{display:block;font-size:20px;margin-top:4px}.panels{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(350px,.8fr);gap:16px}.market-panel{border:1px solid var(--line);background:rgba(6,23,37,.86);border-radius:11px;padding:16px;min-height:390px}.panel-heading{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line);padding-bottom:11px;margin-bottom:13px}.panel-heading h2{margin:0;font-size:17px;color:var(--blue)}.panel-heading span{font-size:12px;color:var(--muted)}.opportunity{border:1px solid #21425c;border-radius:10px;background:linear-gradient(145deg,#0a2033,#071622);padding:13px;margin-top:10px;box-shadow:0 12px 28px rgba(0,0,0,.16)}.opp-head{display:flex;align-items:center;gap:10px}.opp-identity{min-width:0}.opp-identity h3{font-size:20px;margin:0}.setup-family{display:block;color:var(--muted);font-size:12px;margin-top:1px}.direction{margin-left:auto;border:1px solid currentColor;padding:3px 8px;border-radius:6px;font-size:12px;font-weight:750}.direction-long{color:var(--green)}.direction-short{color:var(--red)}.summary-reason{color:#c9d8e3;margin:10px 0}.summary-footer{display:flex;align-items:center;justify-content:space-between;gap:12px;border-top:1px solid var(--line);padding-top:10px}.summary-rr{color:var(--muted);font-size:12px}.summary-rr strong{color:var(--green);font-size:15px;margin-left:3px}.rank{display:grid;place-items:center;width:29px;height:29px;background:#0c4f83;border-radius:6px;color:#8dd0ff;font-weight:800}.opp-head h3{font-size:22px;margin:0}.pill{border:1px solid #176741;color:var(--green);padding:3px 8px;border-radius:6px;font-size:12px}.trade-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin:15px 0}.field{border-left:1px solid var(--line);padding-left:10px}.field:first-child{border-left:0;padding-left:0}.field label{display:block;color:var(--muted);font-size:11px}.field strong{display:block;margin-top:3px}.positive{color:var(--green)}.negative{color:var(--red)}.why{border-top:1px solid var(--line);padding-top:12px;color:#c9d8e3}.risk{color:#f0b8ba;font-size:13px}.opp-actions{display:flex;justify-content:flex-end;margin-top:14px}.empty{display:grid;place-items:center;min-height:270px;text-align:center;color:var(--muted);padding:30px}.empty strong{display:block;color:#dce8f0;font-size:17px;margin-bottom:6px}.error{border:1px solid #793b40;background:#2c151c;color:#ffc3c6;border-radius:8px;padding:11px 14px;margin-bottom:16px}.workspace{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(330px,.7fr);gap:16px}.workspace section{border:1px solid var(--line);background:rgba(6,23,37,.88);border-radius:10px;padding:17px}.workspace h2{margin:0 0 13px;font-size:17px;color:var(--blue)}.workspace h3{margin:18px 0 8px;font-size:13px;text-transform:uppercase;letter-spacing:.05em;color:#7ec7ff}.workspace ul{margin:7px 0;padding-left:19px}.plan-strip{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.plan-strip div{background:#081c2c;border:1px solid var(--line);border-radius:7px;padding:10px}.plan-strip label{display:block;color:var(--muted);font-size:11px}.chart-placeholder{min-height:260px;display:grid;place-items:center;border:1px dashed #31506a!important;color:var(--muted);text-align:center}.technical{font-size:12px;color:var(--muted)}.placeholder{min-height:65vh;display:grid;place-items:center;text-align:center}.placeholder div{border:1px solid var(--line);background:var(--panel);border-radius:12px;padding:38px;max-width:520px}.placeholder h2{margin-top:0}.footer{padding:0 28px 22px;color:#698294;font-size:12px;text-align:right}
.status-grid{grid-template-columns:repeat(8,minmax(110px,1fr))}.global-empty{border:1px solid var(--line);background:#071827;color:var(--muted);border-radius:9px;padding:12px 14px;margin-bottom:16px}
.status-strip{display:flex;align-items:center;flex-wrap:wrap;border:1px solid var(--line);background:rgba(7,24,39,.72);border-radius:8px;padding:8px 10px;margin-bottom:14px}.status-item{display:flex;align-items:baseline;gap:6px;padding:0 14px;border-left:1px solid var(--line);white-space:nowrap;font-size:12px}.status-item:first-child{border-left:0;padding-left:2px}.status-item span{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.05em}.status-item strong{font-size:13px;font-weight:650}.status-item.status-top strong{color:var(--blue)}
.status-strip{position:relative}.eligible-control{display:block}.eligible-control summary{display:flex;align-items:baseline;gap:6px;cursor:pointer;list-style:none}.eligible-control summary::-webkit-details-marker{display:none}.eligible-control summary:focus-visible{outline:1px solid var(--blue);outline-offset:4px}.eligible-control>summary strong{color:var(--blue)}.eligible-panel{position:absolute;z-index:20;top:calc(100% + 6px);left:0;right:0;white-space:normal;border:1px solid #28506c;background:#071827;border-radius:9px;padding:14px;box-shadow:0 18px 45px rgba(0,0,0,.45)}.eligible-heading{display:flex;align-items:center;justify-content:space-between;gap:12px}.eligible-heading h2{font-size:15px;letter-spacing:.05em;margin:0;color:var(--blue)}.eligible-standard{color:var(--muted);font-size:11px;margin:3px 0 10px}.eligible-list{display:grid;gap:7px}.eligible-row{display:grid;grid-template-columns:42px minmax(120px,1fr) 70px minmax(150px,1fr) 70px 110px auto;align-items:center;gap:10px;border-top:1px solid var(--line);padding:8px 0}.eligible-row:first-child{border-top:0}.eligible-rank{color:#8dd0ff;font-weight:750}.eligible-instrument{font-weight:750}.eligible-setup{color:var(--muted);font-size:12px}.eligible-selection{font-size:11px;font-weight:750}.eligible-selection.selected{color:var(--green)}.eligible-selection.not-selected{color:var(--muted)}.eligible-reason{grid-column:2/-1;color:var(--muted);font-size:11px}.eligible-empty{color:var(--muted);padding:9px 0 3px}
.panels{grid-template-columns:repeat(2,minmax(0,1fr))}
.review-note{border:1px solid #5d4b25;background:#231d11;color:#f6d997;border-radius:8px;padding:11px 14px;margin-bottom:14px}.chart-intake-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(265px,1fr));gap:12px}.chart-intake-card{border:1px solid var(--line);background:rgba(6,23,37,.88);border-radius:10px;padding:14px}.chart-intake-card h2{font-size:17px;color:var(--blue);margin:0 0 10px}.chart-slot{display:grid;gap:7px}.chart-slot+.chart-slot{margin-top:10px;padding-top:10px;border-top:1px solid var(--line)}.chart-paste-target{min-height:118px;border:1px dashed #38617e;border-radius:8px;background:#04131f;display:grid;place-items:center;text-align:center;padding:10px;cursor:text;overflow:hidden}.chart-paste-target:focus,.chart-paste-target.replace-ready{outline:2px solid var(--blue);outline-offset:1px;border-color:transparent}.chart-paste-target.received{grid-template-columns:98px 1fr;text-align:left;border-style:solid;cursor:text}.chart-paste-target img{width:98px;height:82px;border-radius:6px;object-fit:cover;background:#020b14}.paste-key{display:block;color:var(--blue);font-size:22px;font-weight:800}.chart-paste-target small,.chart-received span{display:block;color:var(--muted);font-size:11px}.chart-received strong{color:var(--green)}.chart-slot-actions{display:flex;align-items:center;gap:6px;flex-wrap:wrap}.chart-slot-actions button,.chart-slot-actions .file-choice{padding:6px 9px;font-size:12px}.chart-slot-actions form{display:inline}.file-choice{border:0;background:transparent;color:var(--muted);cursor:pointer;text-decoration:underline;text-underline-offset:3px}.chart-file{position:absolute;width:1px;height:1px;opacity:0;pointer-events:none}.analyze-all{display:flex;justify-content:flex-end;margin-top:16px}.analyze-all button{min-width:150px}
.analysis-batch{display:flex;align-items:center;justify-content:space-between;gap:12px;border:1px solid var(--line);background:#071827;border-radius:9px;padding:10px 13px;margin-bottom:12px}.analysis-batch span{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.05em}.analysis-batch strong{font-size:13px;color:#dce8f0}.analysis-run-times{text-align:right}.analysis-run-times strong,.analysis-run-times small{display:block}.analysis-run-times small{margin-top:2px;color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.04em}.chart-intake-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px}.chart-intake-card .chart-intake-head h2{margin:0}.analysis-state{border:1px solid #31506a;border-radius:999px;padding:3px 7px;font-size:10px;font-weight:800;white-space:nowrap;color:var(--muted)}.analysis-state.analyzing{border-color:#2b78ad;color:#8dd0ff}.analysis-state.analyzed{border-color:#176741;color:var(--green)}.analysis-state.context-incomplete{border-color:#82631f;color:var(--amber)}.analysis-state.analysis-failed{border-color:#793b40;color:var(--red)}
.four-chart-label{display:block;color:#dce8f0;font-size:11px;font-weight:800;letter-spacing:.05em}.four-chart-timeframes{display:block;color:var(--muted);font-size:10px;margin-top:2px}.v1-context-result{border-top:1px solid var(--line);margin-top:12px;padding-top:10px;display:grid;gap:6px}.v1-context-row{display:grid;grid-template-columns:96px minmax(0,1fr);gap:8px;font-size:11px}.v1-context-row span{color:var(--muted);text-transform:uppercase;letter-spacing:.04em}.v1-context-row strong{font-weight:700}.v1-context-row .supportive{color:var(--green)}.v1-context-row .partial,.v1-context-row .incomplete{color:var(--amber)}.v1-context-row .contradictory{color:var(--red)}.shadow-authority{color:var(--muted);font-size:10px;text-align:right;margin-top:9px;letter-spacing:.04em}
.configuration{max-width:760px;border:1px solid var(--line);background:rgba(6,23,37,.88);border-radius:11px;padding:20px}.configuration-head{display:flex;align-items:center;justify-content:space-between;gap:16px;border-bottom:1px solid var(--line);padding-bottom:14px;margin-bottom:16px}.configuration-head h2{margin:0;color:var(--blue)}.configuration-state{display:flex;align-items:center;justify-content:space-between;gap:16px;margin:10px 0}.connection-status{border:1px solid #246295;border-radius:999px;padding:5px 10px;font-size:12px;font-weight:800}.connection-status.CONNECTED{border-color:#176741;color:var(--green)}.connection-status.CONNECTION-FAILED{border-color:#793b40;color:var(--red)}.credential-form{display:grid;gap:10px;margin-top:18px;padding-top:16px;border-top:1px solid var(--line)}.credential-form label{font-weight:700}.credential-form input{width:100%;border:1px solid #31506a;background:#04131f;color:var(--text);border-radius:7px;padding:11px 12px;font:inherit}.credential-form input:focus{outline:2px solid var(--blue);outline-offset:1px}.configuration-actions{display:flex;gap:10px;align-items:center;margin-top:16px}.configuration-note{color:var(--muted);font-size:12px;margin:9px 0 0}
.step32-workflow{margin-top:16px;border:1px solid var(--line);background:rgba(6,23,37,.88);border-radius:10px;padding:16px}.step32-head{display:flex;align-items:center;gap:10px;border-bottom:1px solid var(--line);padding-bottom:10px}.step32-head h2{margin:0;font-size:18px}.step32-grid{display:grid;grid-template-columns:1.4fr .8fr .8fr;gap:12px;margin-top:12px}.step32-block{border-left:1px solid var(--line);padding-left:12px}.step32-block:first-child{border-left:0;padding-left:0}.step32-block h3{margin:0 0 8px;color:var(--muted);font-size:11px;letter-spacing:.06em;text-transform:uppercase}.step32-values{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}.step32-value label{display:block;color:var(--muted);font-size:10px}.step32-value strong{font-size:13px}.decision-options{display:flex;gap:5px;flex-wrap:wrap}.decision-option{border:1px solid var(--line);border-radius:6px;padding:4px 7px;color:var(--muted);font-size:11px}.decision-option.selected{border-color:var(--blue);color:#dff1ff}.model-position{display:grid;gap:7px}.model-position div{display:flex;justify-content:space-between;gap:8px;font-size:12px}.model-position span{color:var(--muted)}
@media(max-width:1050px){.status-grid{grid-template-columns:repeat(3,1fr)}.panels,.workspace{grid-template-columns:1fr}.market-panel{min-height:260px}}
@media(min-width:761px){.panels{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:760px){.app{grid-template-columns:1fr}.sidebar{position:static;height:auto}.nav{grid-template-columns:repeat(2,1fr)}.system{display:none}.topbar{height:auto;padding:18px;align-items:flex-start;gap:14px}.tabs{overflow:auto;padding:0 18px}.content{padding:18px}.status-grid{grid-template-columns:repeat(2,1fr)}.trade-grid,.plan-strip{grid-template-columns:1fr 1fr}.kite{flex-wrap:wrap;justify-content:flex-end}.chart-intake-list{grid-template-columns:1fr}}
"""


def render_opportunities(snapshot: BrowserWorkspaceSnapshot) -> str:
    left = tuple(
        item for item in snapshot.v1_probables
        if item.panel is MarketPanel.EQUITIES_INDICES
    )
    right = tuple(
        item for item in snapshot.v1_probables
        if item.panel is MarketPanel.COMMODITIES
    )
    body = _analysis_run_strip(snapshot) + _v1_status_metrics(snapshot)
    if not snapshot.v1_probables:
        body += (
            '<div class="global-empty">'
            "No V1 Probables were found for this analysis."
            "</div>"
        )
    if snapshot.provider_failure or snapshot.analysis_failure:
        body += '<div class="error">' + escape(
            snapshot.provider_failure or snapshot.analysis_failure
        ) + "</div>"
    body += '<div class="panels">'
    body += _v1_probable_panel("EQUITIES + INDICES", left)
    body += _v1_probable_panel("COMMODITIES", right)
    body += "</div>"
    return _page(
        title="Swing Opportunities",
        subtitle="Current immutable Swing V1 Layer-1 Probables.",
        snapshot=snapshot,
        active_nav="Swing",
        active_tab="Opportunities",
        body=body,
    )


def _v1_status_metrics(snapshot: BrowserWorkspaceSnapshot) -> str:
    equities = sum(
        item.panel is MarketPanel.EQUITIES_INDICES
        for item in snapshot.v1_probables
    )
    commodities = len(snapshot.v1_probables) - equities
    return (
        '<div class="status-grid">'
        f'<div class="metric"><label>Universe</label><strong>{snapshot.universe_count}</strong></div>'
        f'<div class="metric"><label>V1 Probables</label><strong>{len(snapshot.v1_probables)}</strong></div>'
        f'<div class="metric"><label>Equities + Indices</label><strong>{equities}</strong></div>'
        f'<div class="metric"><label>Commodities</label><strong>{commodities}</strong></div>'
        f'<div class="metric"><label>Analysis boundary</label><strong>{escape(_analysis_boundary_time(snapshot))}</strong></div>'
        '</div>'
    )


def _v1_probable_panel(
    title: str,
    probables: tuple[V1ProbableSnapshot, ...],
) -> str:
    cards = "".join(
        '<article class="opportunity"><div class="opp-head">'
        f'<div class="opp-identity"><h3>{escape(item.instrument)}</h3>'
        f'<span class="setup-family">{escape(", ".join(_operator_setup(value.value) for value in item.setups))}</span></div>'
        f'<span class="direction direction-{escape(item.directions[0].value.lower())}">'
        f'{escape(" / ".join(value.value for value in item.directions))}</span>'
        '</div></article>'
        for item in probables
    )
    if not cards:
        cards = (
            '<div class="empty"><div><strong>No V1 Probables</strong>'
            "No instrument in this panel currently meets V1 Layer-1 probable policy."
            "</div></div>"
        )
    return (
        '<section class="market-panel"><div class="panel-heading">'
        f'<h2>{escape(title)}</h2><span>{len(probables)} V1 Probables</span>'
        f'</div>{cards}</section>'
    )


def _operator_setup(value: str) -> str:
    return value.replace("_", " ").title()


@dataclass(frozen=True, slots=True)
class Step32SponsorWorkflowView:
    instrument: str
    direction: str
    setup: str
    entry: Decimal
    stop: Decimal
    invalidation: Decimal
    target: Decimal
    risk_reward: Decimal
    risk: str
    sponsor_decision: str
    current_state: str
    model_state: str
    sponsor_position_state: str
    kite_monitoring: str
    trade_monitoring: str


def build_step32_sponsor_workflow_view(
    candidate: SwingV1TradeCandidate,
    risk: RiskApproval,
    lifecycle: CandidateLifecycle,
    *,
    decision: SponsorDecision | None = None,
    model: ObjectiveModelTrade | None = None,
    position: SponsorPosition | None = None,
    monitoring_state: MonitoringConnectionState = MonitoringConnectionState.DISCONNECTED,
) -> Step32SponsorWorkflowView:
    if (
        risk.candidate_id != candidate.candidate_id
        or lifecycle.candidate_id != candidate.candidate_id
        or (decision is not None and decision.candidate_id != candidate.candidate_id)
        or (model is not None and model.candidate_id != candidate.candidate_id)
        or (position is not None and position.candidate_id != candidate.candidate_id)
    ):
        raise ValueError("STEP32_BROWSER_BINDING_INVALID")
    if model is None:
        current = {
            CandidateLifecycleState.WAITING_FOR_RISK: "Waiting for Risk",
            CandidateLifecycleState.WAITING_FOR_ENTRY: "Waiting for Entry",
            CandidateLifecycleState.RISK_REJECTED: "Risk Rejected",
            CandidateLifecycleState.STALE: "Stale",
            CandidateLifecycleState.PRE_ENTRY_INVALIDATED: "Pre-Entry Invalidated",
            CandidateLifecycleState.RECONCILIATION_REQUIRED_PRE_ENTRY: "Reconciliation Required",
        }[lifecycle.state]
        model_state = "NOT ACTIVE"
    else:
        current = {
            ObjectiveModelState.ACTIVE: "Active",
            ObjectiveModelState.RECONCILIATION_REQUIRED: "Reconciliation Required",
            ObjectiveModelState.CLOSED: "Closed",
        }[model.state]
        model_state = model.state.value.replace("MODEL_TRADE_", "").replace("_", " ")
    return Step32SponsorWorkflowView(
        candidate.canonical_instrument,
        candidate.direction,
        candidate.setup_family.replace("_", " ").title(),
        _required_decimal(candidate.entry_price),
        _required_decimal(candidate.stop_price),
        _required_decimal(candidate.invalidation_level_or_reference),
        _required_decimal(candidate.target_price),
        _required_decimal(candidate.risk_reward_ratio),
        risk.state.value.removeprefix("RISK_").replace("_", " "),
        "NO DECISION RECORDED" if decision is None else decision.mode.value,
        current,
        model_state,
        "NONE" if position is None else f"{position.mode.value} · {position.state.value}",
        monitoring_state.value.replace("_", " "),
        "RECONCILIATION REQUIRED"
        if model is not None and model.state is ObjectiveModelState.RECONCILIATION_REQUIRED
        else "MONITORING OK"
        if monitoring_state is MonitoringConnectionState.CONNECTED
        else "RECONCILIATION REQUIRED",
    )


def render_step32_sponsor_workflow(view: Step32SponsorWorkflowView) -> str:
    options = "".join(
        '<span class="decision-option'
        + (' selected' if view.sponsor_decision == mode else '')
        + f'">{mode}</span>'
        for mode in ("LIVE", "PAPER", "IGNORE")
    )
    values = "".join(
        '<div class="step32-value"><label>' + escape(label) + '</label><strong>'
        + escape(_decimal_number(value)) + '</strong></div>'
        for label, value in (
            ("Entry", view.entry),
            ("Stop", view.stop),
            ("Invalidation", view.invalidation),
            ("Target", view.target),
            ("R:R", view.risk_reward),
        )
    )
    return (
        '<section class="step32-workflow"><div class="step32-head">'
        f'<h2>{escape(view.instrument)} — {escape(view.direction)}</h2>'
        f'<span class="setup-family">{escape(view.setup)}</span></div>'
        '<div class="step32-grid"><div class="step32-block"><h3>Trade Plan</h3>'
        f'<div class="step32-values">{values}</div></div>'
        '<div class="step32-block"><h3>Risk</h3>'
        f'<strong>{escape(view.risk)}</strong><h3>Your Decision</h3>'
        f'<div class="decision-options">{options}</div></div>'
        '<div class="step32-block"><h3>Current State</h3>'
        f'<strong>{escape(view.current_state)}</strong><div class="model-position">'
        f'<div><span>Kite Monitoring</span><strong>{escape(view.kite_monitoring)}</strong></div>'
        f'<div><span>Trade Monitoring</span><strong>{escape(view.trade_monitoring)}</strong></div>'
        f'<div><span>KRONOS Model</span><strong>{escape(view.model_state)}</strong></div>'
        f'<div><span>Your Position</span><strong>{escape(view.sponsor_position_state)}</strong></div>'
        '</div></div></div></section>'
    )


def render_workspace(
    snapshot: BrowserWorkspaceSnapshot,
    opportunity: OpportunitySnapshot,
    step32: Step32SponsorWorkflowView | None = None,
) -> str:
    plan = (
        '<div class="plan-strip">'
        + _plan_field("Entry", _number(opportunity.entry))
        + _plan_field("Stop", _number(opportunity.stop), "negative")
        + _plan_field("Target 1", _number(opportunity.target_1), "positive")
        + _plan_field("Risk : Reward", _number(opportunity.risk_reward), "positive")
        + "</div>"
    )
    thesis = "".join(f"<li>{escape(item)}</li>" for item in opportunity.thesis_invalidation)
    evidence_for = "".join(f"<li>{escape(item)}</li>" for item in opportunity.evidence_for)
    evidence_against = "".join(
        f"<li>{escape(item)}</li>" for item in opportunity.evidence_against_or_risks
    ) or "<li>No additional risk evidence was published.</li>"
    body = "".join((
        '<div class="workspace"><div><section><div class="opp-head"><span class="rank">',
        f"{opportunity.position}</span><h2>{escape(opportunity.instrument)}</h2>",
        f'<span class="pill">{escape(opportunity.direction)} · {escape(opportunity.setup)}</span>',
        f'<span class="pill">{escape(opportunity.state)}</span></div>',
        '<h3>Trade Plan</h3>',
        plan,
        f'<p><strong>Entry condition:</strong> {escape(opportunity.entry_condition)}</p>',
        f'<p><strong>Risk:</strong> {_number(opportunity.risk)} &nbsp; ',
        f'<strong>Reward:</strong> {_number(opportunity.reward)}</p>',
        '<h3>Thesis Invalidation</h3><ul>',
        thesis,
        '</ul></section><section style="margin-top:16px"><h2>Why KRONOS selected it</h2>',
        f'<p>{escape(opportunity.why)}</p><h3>Evidence For</h3><ul>{evidence_for}</ul>',
        f'<h3>Evidence Against / Risks</h3><ul>{evidence_against}</ul>',
        f'<h3>What Needs To Happen Next</h3><p>{escape(opportunity.next_required_event)}</p>',
        '</section>',
        "" if step32 is None else render_step32_sponsor_workflow(step32),
        '</div><div><section class="chart-placeholder"><div>',
        '<strong>Chart reserved for Stage 10</strong><br>TradingView integration is not implemented.',
        '</div></section><section class="technical" style="margin-top:16px">',
        '<h2>Technical details</h2>',
        f'<p>Observation boundary<br><strong>{_date(opportunity.observation_boundary)}</strong></p>',
        f'<p>Swing Zero<br><strong>{escape(opportunity.swing_zero_policy)}</strong></p>',
        f'<p>Trade Plan<br><strong>{escape(opportunity.trade_plan_policy)}</strong></p>',
        f'<p>Ranking<br><strong>{escape(opportunity.ranking_policy)}</strong></p>',
        f'<p>Top Opportunity<br><strong>{escape(opportunity.top_opportunity_policy)}</strong></p>',
        f'<p>Data freshness<br><strong>{_date(snapshot.completed_at)}</strong></p>',
        '</section></div></div>',
    ))
    return _page(
        title=escape(opportunity.instrument),
        subtitle="Complete Swing opportunity evidence and Trade Plan.",
        snapshot=snapshot,
        active_nav="Swing",
        active_tab="Opportunities",
        body=body,
        back_link='<a class="button" href="/swing/opportunities">← Back to opportunities</a>',
    )


def render_v1_review(
    snapshot: BrowserWorkspaceSnapshot,
    review: V1ReviewWorkflowSnapshot,
) -> str:
    if review.layer1_run is None:
        body = (
            '<div class="review-note">Run the daily analysis first, then prepare the '
            'chart list.</div>'
            + _v1_run_control(snapshot, review)
        )
    elif not review.requirements:
        body = (
            _v1_run_control(snapshot, review)
            + '<div class="global-empty">No instruments currently need charts.</div>'
        )
    else:
        batch = batch_analysis_status(review)
        preflight_notice = ""
        if review.batch_preflight_failure is not None:
            guidance = (
                "Enable it in Settings before analysis."
                if review.batch_preflight_failure.value
                == "CHART ANALYST V2 DISABLED"
                else "Review Settings before analysis."
            )
            preflight_notice = (
                '<div class="review-note batch-preflight"><strong>'
                f'{escape(review.batch_preflight_failure.value)}</strong><br>'
                f'{escape(guidance)}</div>'
            )
        body = (
            _v1_run_control(snapshot, review)
            + preflight_notice
            + '<div class="analysis-batch"><span>Chart analysis</span>'
            f'<strong id="analysis-batch-status">{escape("WAITING" if review.batch_preflight_failure else batch.label)}</strong></div>'
            + '<div class="chart-intake-list">'
        )
        slot_index = 0
        for requirement, package in zip(
            review.requirements,
            review.packages,
            strict=True,
        ):
            active = {item.timeframe: item for item in package.active_revisions}
            analysis = review.analysis_for(requirement.canonical_instrument)
            if analysis is None:
                raise ValueError("V1_ANALYSIS_STATUS_INVALID")
            analysis_status = instrument_analysis_status(analysis.state)
            analysis_class = analysis_status.lower().replace(" ", "-")
            slots = ""
            for timeframe in requirement.required_timeframes:
                slot_index += 1
                revision = active.get(timeframe)
                query = urlencode({
                    "instrument": requirement.canonical_instrument,
                    "timeframe": timeframe.value,
                })
                target_id = f"chart-slot-{slot_index}"
                file_id = f"chart-file-{slot_index}"
                received_class = " received" if revision is not None else ""
                if revision is None:
                    target_content = (
                        '<div><span class="paste-key">⌘V</span>'
                        '<strong>Click, then paste</strong>'
                        '<span class="four-chart-label">4-CHART</span>'
                        '<span class="four-chart-timeframes">1W · 1D · 4H · 1H</span></div>'
                    )
                    received_actions = ""
                else:
                    preview_query = urlencode({
                        "instrument": requirement.canonical_instrument,
                        "timeframe": timeframe.value,
                        "sha256": revision.sha256,
                    })
                    target_content = (
                        f'<img src="/swing/v1/chart-preview?{escape(preview_query)}" alt="">'
                        '<div class="chart-received"><strong>Chart received</strong>'
                        '<span class="four-chart-label">4-CHART</span>'
                        '<span class="four-chart-timeframes">1W · 1D · 4H · 1H</span></div>'
                    )
                    received_actions = (
                        f'<button class="replace-chart" type="button" data-target="{target_id}">Replace</button>'
                        f'<form method="post" action="/swing/v1/chart/remove?{escape(query)}">'
                        '<button type="submit">Remove</button></form>'
                    )
                slots += (
                    '<div class="chart-slot">'
                    f'<div id="{target_id}" class="chart-paste-target{received_class}" '
                    'role="button" tabindex="0" '
                    f'aria-label="Paste four-chart screenshot for '
                    f'{escape(requirement.canonical_instrument)}" '
                    f'data-upload-url="/swing/v1/chart?{escape(query)}">{target_content}</div>'
                    '<div class="chart-slot-actions">'
                    f'{received_actions}<label class="file-choice" for="{file_id}">Choose File</label>'
                    f'<input id="{file_id}" class="chart-file" type="file" '
                    'accept="image/png,image/jpeg,image/webp" '
                    f'data-target="{target_id}"></div></div>'
                )
            body += (
                '<article class="chart-intake-card">'
                '<div class="chart-intake-head">'
                f'<h2>{escape(requirement.canonical_instrument)}</h2>'
                f'<span class="analysis-state {escape(analysis_class)}" '
                f'data-analysis-instrument="{escape(requirement.canonical_instrument)}">'
                f'{escape(analysis_status)}</span></div>{slots}'
            )
            body += _v1_context_result(requirement, analysis)
            if (
                package.active_revisions
                and is_swing_analysis_run_id(
                    review.swing_analysis_run_identity or ""
                )
            ):
                one_query = urlencode({
                    "instrument": requirement.canonical_instrument,
                })
                body += (
                    '<form class="validate-one" method="post" '
                    f'action="/swing/v1/analyze-one?{escape(one_query)}">'
                    '<button type="submit">Validate One Chart</button></form>'
                )
            body += '</article>'
        body += "</div>"
        analysis_allowed = review.all_required_charts_present and any(
            item.state is ChartAnalysisState.READY_TO_ANALYZE
            for item in review.analyses
        )
        if analysis_allowed:
            body += (
                '<form class="analyze-all" method="post" action="/swing/v1/analyze">'
                '<button class="primary" type="submit">Analyze Charts</button></form>'
            )
        body += '<div class="shadow-authority">SHADOW / VALIDATION ONLY</div>'
        body += _chart_upload_script()
        if analysis_allowed:
            body += _chart_analysis_status_script()
    return _page(
        title="V1 Review",
        subtitle="Copy a chart image, click its target, and paste with ⌘V.",
        snapshot=snapshot,
        active_nav="Swing",
        active_tab="V1 Review",
        body=body,
    )


def _v1_context_result(requirement, analysis: InstrumentChartAnalysisSnapshot) -> str:  # type: ignore[no-untyped-def]
    setups = " · ".join(
        f"{item.setup.value.replace('_', ' ').title()} {item.direction.value}"
        for item in requirement.probable_setups
    )
    layer2 = analysis.v2_layer2
    context = (
        {
            "AGREE": "SUPPORTIVE",
            "COMPATIBLE_PARTIAL": "PARTIAL",
            "CONTRADICT": "CONTRADICTORY",
            "CONTEXT_INCOMPLETE": "INCOMPLETE",
        }[layer2.reconciliation.value]
        if layer2 is not None
        else "INCOMPLETE"
        if analysis.state in {
            ChartAnalysisState.CONTEXT_INCOMPLETE,
            ChartAnalysisState.CHART_ANALYSIS_UNAVAILABLE,
        }
        else "WAITING"
    )
    readiness = (
        analysis.readiness.state.value.replace("_", " ")
        if analysis.readiness is not None
        else "CONTEXT INCOMPLETE"
        if analysis.state in {
            ChartAnalysisState.CONTEXT_INCOMPLETE,
            ChartAnalysisState.CHART_ANALYSIS_UNAVAILABLE,
        }
        else "WAITING"
    )
    reason, need = _v1_governed_reason(analysis)
    return (
        '<div class="v1-context-result">'
        f'<div class="v1-context-row"><span>Layer-1</span><strong>{escape(setups)}</strong></div>'
        '<div class="v1-context-row"><span>Chart context</span>'
        f'<strong class="{escape(context.lower())}">{escape(context)}</strong></div>'
        '<div class="v1-context-row"><span>Readiness</span>'
        f'<strong>{escape(readiness)}</strong></div>'
        f'<div class="v1-context-row"><span>Key reason</span><strong>{escape(reason)}</strong></div>'
        f'<div class="v1-context-row"><span>Need</span><strong>{escape(need)}</strong></div>'
        '</div>'
    )


def _v1_governed_reason(
    analysis: InstrumentChartAnalysisSnapshot,
) -> tuple[str, str]:
    failure = analysis.failure_code.value if analysis.failure_code is not None else ""
    if "IDENTITY_MISMATCH" in failure:
        return "CHART DOES NOT MATCH RUN", "REPLACE CHART"
    if "SCHEMA_INVALID" in failure:
        return "CHART EVIDENCE INVALID", "REPLACE CHART"
    if "RESPONSE_INCOMPLETE" in failure or "LOW_CONFIDENCE" in failure:
        return "CHART UNREADABLE", "REPLACE CHART"
    if analysis.state is ChartAnalysisState.CHART_ANALYSIS_UNAVAILABLE:
        return "ANALYSIS PROVIDER UNAVAILABLE", "TRY AGAIN WHEN AVAILABLE"
    if analysis.state is ChartAnalysisState.CHARTS_REQUIRED:
        return "CHART REQUIRED", "PASTE 4-CHART SCREENSHOT"
    if analysis.state is ChartAnalysisState.READY_TO_ANALYZE:
        return "CHART RECEIVED", "ANALYZE CHARTS"
    if analysis.state is ChartAnalysisState.ANALYZING_CHART_CONTEXT:
        return "KRONOS ANALYSIS IN PROGRESS", "WAIT"
    if analysis.readiness is None:
        return "CONTEXT NOT YET AVAILABLE", "REVIEW CHART"
    reason = analysis.readiness.primary_reason.replace("_", " ")
    if analysis.readiness.state.value == "READY_FOR_TRADE_CONSTRUCTION":
        return reason, "ELIGIBLE FOR STEP 31 HANDOFF"
    evidence = (
        analysis.readiness.unresolved_evidence
        or analysis.readiness.contradicting_evidence
    )
    if evidence:
        need = evidence[0].replace("_", " ")
    elif analysis.readiness.state.value == "CONTEXT_INCOMPLETE":
        need = "REPLACE CHART"
    else:
        need = reason
    return reason, need


def render_settings(
    snapshot: BrowserWorkspaceSnapshot,
    chart_analyst_status: ChartAnalystConnectionStatus,
    activation_status: ChartAnalystV2ActivationStatus,
    live_monitoring: LiveMonitoringTestResult | None = None,
    live_monitoring_instruments: tuple[str, ...] = (),
) -> str:
    if (
        type(chart_analyst_status) is not ChartAnalystConnectionStatus
        or type(activation_status) is not ChartAnalystV2ActivationStatus
    ):
        raise TypeError("CHART_ANALYST_STATUS_INVALID")
    status_class = chart_analyst_status.value.replace(" ", "-")
    activation_action = (
        "disable"
        if activation_status is ChartAnalystV2ActivationStatus.ENABLED
        else "enable"
    )
    activation_label = "Disable" if activation_action == "disable" else "Enable"
    monitoring = live_monitoring or LiveMonitoringTestResult(
        LiveMonitoringTestState.NOT_TESTED
    )
    selected = monitoring.instrument or (
        live_monitoring_instruments[0] if live_monitoring_instruments else ""
    )
    options = "".join(
        '<option'
        + (' selected' if item == selected else '')
        + f'>{escape(item)}</option>'
        for item in live_monitoring_instruments
    )
    proof = ""
    if monitoring.state is LiveMonitoringTestState.PASS:
        proof = (
            '<div class="configuration-note"><strong>LIVE MONITORING: PASS</strong><br>'
            f'Instrument: {escape(monitoring.instrument or "—")}<br>'
            'Provider: KITE<br>Market data received: YES<br>DOMAIN-002: ACCEPTED<br>'
            f'Observed at: {escape(monitoring.observed_at.isoformat() if monitoring.observed_at else "—")}</div>'
        )
    elif monitoring.state is LiveMonitoringTestState.CONNECTED_NO_DATA:
        proof = (
            '<div class="configuration-note"><strong>CONNECTED — NO LIVE MARKET DATA</strong><br>'
            'Live Kite E2E remains: PENDING</div>'
        )
    elif monitoring.state is LiveMonitoringTestState.FAIL:
        proof = (
            '<div class="configuration-note"><strong>LIVE MONITORING: FAIL</strong><br>'
            f'{escape(monitoring.safe_reason.replace("_", " "))}</div>'
        )
    disabled = (
        " disabled"
        if snapshot.provider_state is not ProviderConnectionState.CONNECTED
        or monitoring.state is LiveMonitoringTestState.TESTING
        else ""
    )
    body = (
        f'<div id="live-monitoring-state" data-state="{escape(monitoring.state.value)}">'
        '<section class="configuration"><div class="configuration-head">'
        '<h2>Kite Live Monitoring</h2></div>'
        '<div class="configuration-state"><span>Kite</span>'
        f'<strong>● {escape(snapshot.provider_state.value)}</strong></div>'
        '<div class="configuration-state"><span>Live monitoring</span>'
        f'<strong>{escape(monitoring.state.value)}</strong></div>'
        '<form method="post" action="/settings/kite/live-monitoring/test">'
        '<label for="live-monitoring-instrument">Instrument</label>'
        f'<select id="live-monitoring-instrument" name="instrument" required>{options}</select>'
        f'<button class="primary" type="submit"{disabled}>TEST LIVE MONITORING</button>'
        f'</form>{proof}</section></div>'
        '<section class="configuration"><div class="configuration-head">'
        '<h2>OpenAI Chart Analyst</h2>'
        '</div><div class="configuration-state"><span>Credential</span>'
        f'<strong class="connection-status {escape(status_class)}">'
        f'{escape(chart_analyst_status.value)}</strong></div>'
        '<div class="configuration-state"><span>Chart Analyst V2</span>'
        f'<strong>{escape(activation_status.value)}</strong></div>'
        f'<form method="post" action="/settings/chart-analyst/{activation_action}">'
        f'<button type="submit">{activation_label} Chart Analyst V2</button></form>'
        '<form class="credential-form" method="post" '
        'action="/settings/chart-analyst/credential" autocomplete="off">'
        '<label for="chart-analyst-api-key">OpenAI API key</label>'
        '<input id="chart-analyst-api-key" name="api_key" type="password" '
        'autocomplete="off" spellcheck="false" minlength="8" maxlength="512" required>'
        '<div><button class="primary" type="submit">Save credential</button></div>'
        '</form><p class="configuration-note">The saved credential is protected by '
        'the KRONOS secure credential boundary and is never displayed again.</p>'
        '<div class="configuration-actions"><form method="post" '
        'action="/settings/chart-analyst/test">'
        '<button type="submit">Test Connection</button></form></div></section>'
        '<script>const liveInitial=document.getElementById("live-monitoring-state").dataset.state;'
        'setInterval(async()=>{try{const r=await fetch("/status",{cache:"no-store"});'
        'if(!r.ok)return;const s=await r.json();if(s.live_monitoring!==liveInitial)'
        'location.reload();}catch(_e){}},1000);</script>'
    )
    return _page(
        title="Settings",
        subtitle="Protected local configuration for approved KRONOS capabilities.",
        snapshot=snapshot,
        active_nav="Settings",
        active_tab="",
        body=body,
    )


def render_placeholder(
    snapshot: BrowserWorkspaceSnapshot,
    title: str,
    *,
    active_nav: str,
    active_tab: str = "",
) -> str:
    body = (
        '<div class="placeholder"><div><h2>' + escape(title) + "</h2>"
        "<p>This workspace is reserved by the frozen KRONOS experience but is "
        "not implemented in Browser V1.</p></div></div>"
    )
    return _page(
        title=title,
        subtitle="Clearly reserved; no unavailable functionality is simulated.",
        snapshot=snapshot,
        active_nav=active_nav,
        active_tab=active_tab,
        body=body,
    )


def _page(
    *,
    title: str,
    subtitle: str,
    snapshot: BrowserWorkspaceSnapshot,
    active_nav: str,
    active_tab: str,
    body: str,
    back_link: str = "",
) -> str:
    nav = "".join(
        f'<a class="{"active" if name == active_nav else ""}" href="{href}">'
        f'<span class="icon">{_icon(icon)}</span>{escape(name)}</a>'
        for name, href, icon in _NAVIGATION
    )
    tabs = ""
    if active_nav == "Swing":
        tabs = '<nav class="tabs">' + "".join(
            _tab_link(name, href, active_tab)
            for name, href in (
                ("Opportunities", "/swing/opportunities"),
                ("V1 Review", "/swing/v1-review"),
                ("Active", "/swing/active"),
                ("Paper", "/swing/paper"),
                ("Ignored", "/swing/ignored"),
                ("Closed", "/swing/closed"),
            )
        ) + '<div class="toolbar">' + _analysis_form(snapshot) + "</div></nav>"
    signature = "|".join((
        snapshot.provider_state.value,
        snapshot.analysis_state.value,
        snapshot.completed_at.isoformat() if snapshot.completed_at else "",
    ))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)} · KRONOS</title><style>{_CSS}</style></head>
<body data-status-signature="{escape(signature)}"><div class="app"><aside class="sidebar">
<div class="brand"><span class="brandmark">K</span> KRONOS</div><nav class="nav">{nav}</nav>
<div class="system"><strong>● LOCAL · READ ONLY</strong>Provider capability stays inside this process.<br>Order capability: NONE</div>
</aside><main class="main"><header class="topbar"><div class="title">{back_link}<h1>{escape(title)}</h1><p>{escape(subtitle)}</p></div>
<div class="kite"><span class="dot {snapshot.provider_state.value}"></span><strong>Kite: {snapshot.provider_state.value}</strong>{_connect_form(snapshot)}</div></header>
{tabs}<div class="content">{body}</div><div class="footer">KRONOS Browser V1 · Local Mode</div></main></div>
<script>const initial=document.body.dataset.statusSignature;setInterval(async()=>{{try{{const r=await fetch('/status',{{cache:'no-store'}});if(!r.ok)return;const s=await r.json();const next=[s.provider,s.analysis,s.completed_at||''].join('|');if(next!==initial)location.reload();}}catch(_e){{}}}},1500);</script>
</body></html>"""


def _connect_form(snapshot: BrowserWorkspaceSnapshot) -> str:
    if snapshot.provider_state is ProviderConnectionState.CONNECTED:
        return '<form method="post" action="/provider/disconnect"><button>Disconnect</button></form>'
    disabled = " disabled" if snapshot.provider_state is ProviderConnectionState.CONNECTING else ""
    return f'<form method="post" action="/provider/connect"><button class="primary"{disabled}>Connect</button></form>'


def _tab_link(name: str, href: str, active_tab: str) -> str:
    css_class = "active" if name == active_tab else ""
    badge = (
        ""
        if name in {"Opportunities", "V1 Review"}
        else '<span class="badge">Placeholder</span>'
    )
    return f'<a class="{css_class}" href="{href}">{escape(name)}{badge}</a>'


def _analysis_form(snapshot: BrowserWorkspaceSnapshot) -> str:
    disabled = ""
    if (
        snapshot.provider_state is not ProviderConnectionState.CONNECTED
        or snapshot.analysis_state is AnalysisState.RUNNING
    ):
        disabled = " disabled"
    label = "Refresh Analysis" if snapshot.completed_at else "Run Swing Analysis"
    return f'<form method="post" action="/swing/analysis"><button{disabled}>{label}</button></form>'


def _analysis_run_strip(snapshot: BrowserWorkspaceSnapshot) -> str:
    if not is_swing_analysis_run_id(snapshot.swing_analysis_run_identity):
        return ""
    return (
        '<div class="analysis-batch"><span>Market analysis</span>'
        '<div class="analysis-run-times">'
        f'<strong>{escape(_operator_run_label(snapshot))}</strong>'
        f'<small>{escape(_analysis_boundary_label(snapshot))}</small>'
        '</div></div>'
    )


def _operator_run_label(snapshot: BrowserWorkspaceSnapshot) -> str:
    identity = snapshot.swing_analysis_run_identity
    if not is_swing_analysis_run_id(identity):
        return "NOT AVAILABLE"
    if snapshot.run_created_at is None:
        return f"RUN {identity[-8:]} · RUN TIME UNKNOWN"
    created = snapshot.run_created_at.astimezone(_KOLKATA)
    return f"RUN {identity[-8:]} · RUN AT {created.strftime('%d %b %Y %H:%M').upper()}"


def _analysis_boundary_label(snapshot: BrowserWorkspaceSnapshot) -> str:
    if snapshot.observation_boundary is None:
        return "ANALYSIS BOUNDARY NOT AVAILABLE"
    return f"ANALYSIS BOUNDARY {_analysis_boundary_time(snapshot).upper()}"


def _analysis_boundary_time(snapshot: BrowserWorkspaceSnapshot) -> str:
    if snapshot.observation_boundary is None:
        return "—"
    boundary = snapshot.observation_boundary.astimezone(_KOLKATA)
    return boundary.strftime("%d %b %Y · %H:%M %Z")


def _v1_run_control(
    snapshot: BrowserWorkspaceSnapshot,
    review: V1ReviewWorkflowSnapshot,
) -> str:
    disabled = "" if snapshot.analysis_state is AnalysisState.READY else " disabled"
    if review.layer1_run is None:
        return (
            '<form method="post" action="/swing/v1/layer1" style="margin-bottom:14px">'
            f'<button{disabled}>Prepare chart list</button></form>'
        )
    current = review.swing_analysis_run_identity
    if current == snapshot.swing_analysis_run_identity:
        return _analysis_run_strip(snapshot)
    legacy = current == LEGACY_UNBOUND_SWING_RUN_ID
    note = (
        "LEGACY REVIEW — VALIDATION ONLY"
        if legacy
        else "NEW ANALYSIS AVAILABLE"
    )
    return (
        f'<div class="review-note"><strong>{note}</strong><br>'
        "The current charts remain preserved. Move only when you are ready.</div>"
        '<form method="post" action="/swing/v1/load-latest" style="margin-bottom:14px">'
        f'<button{disabled}>Load latest review</button></form>'
    )


def _chart_upload_script() -> str:
    return """<script>
const acceptedCharts=new Set(['image/png','image/jpeg','image/webp']);
async function receiveChart(target,file){
  if(!file||!acceptedCharts.has(file.type)){alert('Paste or choose a PNG, JPEG, or WebP image.');return;}
  target.setAttribute('aria-busy','true');
  try{const response=await fetch(target.dataset.uploadUrl,{method:'POST',headers:{'Content-Type':file.type},body:file});
    if(!response.ok)throw new Error();location.reload();
  }catch(_error){target.removeAttribute('aria-busy');alert('Chart could not be accepted.');}
}
for(const target of document.querySelectorAll('.chart-paste-target')){
  target.addEventListener('click',()=>target.focus());
  target.addEventListener('paste',event=>{
    const items=event.clipboardData&&Array.from(event.clipboardData.items||[]);
    const image=items&&items.find(item=>item.kind==='file'&&acceptedCharts.has(item.type));
    if(!image){alert('No supported chart image was found on the clipboard.');return;}
    event.preventDefault();receiveChart(target,image.getAsFile());
  });
}
for(const button of document.querySelectorAll('.replace-chart')){
  button.addEventListener('click',()=>{
    const target=document.getElementById(button.dataset.target);if(!target)return;
    target.classList.add('replace-ready');target.focus();
  });
}
for(const input of document.querySelectorAll('.chart-file')){
  input.addEventListener('change',()=>{
    const target=document.getElementById(input.dataset.target);
    const file=input.files&&input.files[0];if(target&&file)receiveChart(target,file);
  });
}
</script>"""


def _chart_analysis_status_script() -> str:
    return """<script>
const analysisForm=document.querySelector('.analyze-all');
const analysisBatch=document.getElementById('analysis-batch-status');
let analysisPoll=null;
function setInstrumentAnalysisStatus(instrument,status){
  const target=Array.from(document.querySelectorAll('[data-analysis-instrument]'))
    .find(item=>item.dataset.analysisInstrument===instrument);
  if(!target)return;
  target.textContent=status;
  target.classList.remove('waiting','analyzing','analyzed','context-incomplete','analysis-failed');
  target.classList.add(status.toLowerCase().replaceAll(' ','-'));
}
async function refreshAnalysisStatus(){
  try{
    const response=await fetch('/swing/v1/status',{cache:'no-store'});
    if(!response.ok)return;
    const state=await response.json();
    if(analysisBatch)analysisBatch.textContent=state.batch;
    for(const item of state.instruments)setInstrumentAnalysisStatus(item.instrument,item.status);
    if(state.complete&&analysisPoll){clearInterval(analysisPoll);analysisPoll=null;location.reload();}
  }catch(_error){}
}
if(analysisForm){
  analysisForm.addEventListener('submit',async event=>{
    event.preventDefault();
    const button=analysisForm.querySelector('button');
    if(button)button.disabled=true;
    const waiting=document.querySelector('.analysis-state.waiting');
    if(waiting)setInstrumentAnalysisStatus(waiting.dataset.analysisInstrument,'ANALYZING');
    const total=document.querySelectorAll('[data-analysis-instrument]').length;
    if(analysisBatch)analysisBatch.textContent=`ANALYZING 0 / ${total}`;
    analysisPoll=setInterval(refreshAnalysisStatus,500);
    try{
      const response=await fetch(analysisForm.action,{method:'POST'});
      if(!response.ok)throw new Error();
      await refreshAnalysisStatus();
    }catch(_error){
      if(analysisPoll){clearInterval(analysisPoll);analysisPoll=null;}
      if(analysisBatch)analysisBatch.textContent='ANALYSIS FAILED';
    }finally{
      if(button)button.disabled=false;
    }
  });
}
</script>"""


def _status_metrics(snapshot: BrowserWorkspaceSnapshot) -> str:
    metrics = (
        ("Universe", str(snapshot.universe_count), ""),
        ("Qualified", str(snapshot.qualified_count), ""),
        ("Actionable", str(snapshot.actionable_count), ""),
    )
    return '<div class="status-strip">' + "".join(
        f'<div class="status-item {css_class}"><span>{escape(label)}</span>'
        f'<strong>{escape(value)}</strong></div>'
        for label, value, css_class in metrics
    ) + _eligible_control(snapshot) + (
        '<div class="status-item status-top"><span>Top</span><strong>'
        f'{len(snapshot.opportunities)}/2</strong></div></div>'
    )


def _eligible_control(snapshot: BrowserWorkspaceSnapshot) -> str:
    if snapshot.eligible_plans:
        rows = "".join(_eligible_row(item) for item in snapshot.eligible_plans)
    else:
        rows = (
            '<div class="eligible-empty">'
            "No Trade Plans currently meet the Swing attention standard."
            "</div>"
        )
    return (
        '<details class="eligible-control status-item"><summary>'
        f'<span>Eligible</span><strong>{snapshot.attention_eligible_count}</strong>'
        '</summary><div class="eligible-panel"><div class="eligible-heading">'
        '<h2>ATTENTION ELIGIBLE</h2>'
        f'<strong>{snapshot.attention_eligible_count}</strong></div>'
        '<p class="eligible-standard">Attention standard: ACTIONABLE + R:R &gt;= 1.00</p>'
        f'<div class="eligible-list">{rows}</div></div></details>'
    )


def _eligible_row(item) -> str:  # type: ignore[no-untyped-def]
    opportunity = item.opportunity
    direction_class = (
        "direction-long" if opportunity.direction == "LONG" else "direction-short"
    )
    selection_class = (
        "selected" if item.selection_status == "SELECTED" else "not-selected"
    )
    reason = ""
    if item.selection_status == "NOT SELECTED":
        reason = f'<div class="eligible-reason">{escape(item.selection_reason)}</div>'
    return (
        '<div class="eligible-row">'
        f'<span class="eligible-rank">#{item.stage8_rank}</span>'
        f'<span class="eligible-instrument">{escape(opportunity.instrument)}</span>'
        f'<span class="direction {direction_class}">{escape(opportunity.direction)}</span>'
        f'<span class="eligible-setup">{escape(opportunity.setup.replace("_", " ").title())}</span>'
        f'<strong>{_number(opportunity.risk_reward)}</strong>'
        f'<span class="eligible-selection {selection_class}">{escape(item.selection_status)}</span>'
        f'<a class="button" href="/swing/eligible/{item.stage8_rank}">Open Workspace</a>'
        f'{reason}</div>'
    )


def _market_panel(
    title: str,
    subtitle: str,
    opportunities: tuple[OpportunitySnapshot, ...],
) -> str:
    cards = "".join(_opportunity_card(item) for item in opportunities)
    if not cards:
        cards = (
            '<div class="empty"><div><strong>No qualifying opportunity</strong>'
            "No Swing opportunities in this panel meet the current global attention standard."
            "</div></div>"
        )
    return (
        '<section class="market-panel"><div class="panel-heading"><h2>'
        + escape(title) + "</h2><span>" + escape(subtitle) + "</span></div>"
        + cards + "</section>"
    )


def _opportunity_card(item: OpportunitySnapshot) -> str:
    direction_class = (
        "direction-long" if item.direction == "LONG" else "direction-short"
    )
    setup_family = item.setup.replace("_", " ").title()
    return f"""<article class="opportunity"><div class="opp-head"><span class="rank">{item.position}</span>
<div class="opp-identity"><h3>{escape(item.instrument)}</h3><span class="setup-family">{escape(setup_family)}</span></div>
<span class="direction {direction_class}">{escape(item.direction)}</span></div>
<p class="summary-reason">{escape(item.why)}</p>
<div class="summary-footer"><span class="summary-rr">R:R <strong>{_number(item.risk_reward)}</strong></span>
<a class="button" href="/swing/opportunities/{item.position}">Open Workspace →</a></div></article>"""


def _plan_field(label: str, value: str, css_class: str = "") -> str:
    return (
        '<div class="field"><label>' + escape(label) + "</label><strong class=\""
        + escape(css_class) + '\">' + escape(value) + "</strong></div>"
    )


def _number(value: float) -> str:
    return f"{value:,.4f}".rstrip("0").rstrip(".")


def _decimal_number(value: Decimal) -> str:
    return f"{value:f}".rstrip("0").rstrip(".") if "." in f"{value:f}" else f"{value:f}"


def _required_decimal(value: Decimal | None) -> Decimal:
    if value is None:
        raise ValueError("STEP32_BROWSER_GEOMETRY_UNAVAILABLE")
    return value


def _date(value) -> str:  # type: ignore[no-untyped-def]
    return "—" if value is None else value.strftime("%d %b %Y · %H:%M %Z")


def _icon(name: str) -> str:
    return {
        "home": "⌂", "swing": "↗", "bolt": "ϟ", "theta": "Σ",
        "journal": "▤", "portfolio": "▣", "reports": "▥", "settings": "⚙",
    }[name]


__all__ = [
    "Step32SponsorWorkflowView",
    "build_step32_sponsor_workflow_view",
    "render_opportunities",
    "render_placeholder",
    "render_settings",
    "render_step32_sponsor_workflow",
    "render_v1_review",
    "render_workspace",
]
