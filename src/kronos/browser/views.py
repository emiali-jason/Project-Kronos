"""Escaped server-rendered views for the KRONOS Browser V1 workstation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from html import escape
from urllib.parse import quote, urlencode
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
from kronos.application.notifications import (
    ManagedNotification,
    NotificationProduct,
    NotificationState,
    NotificationWorkspaceSnapshot,
)
from kronos.application.notification_centre import (
    SponsorNotificationAction,
    SponsorNotificationFilter,
    SponsorNotificationProjection,
    SponsorNotificationRecord,
    SponsorNotificationState,
)
from kronos.application.swing_ux10 import (
    Ux10NotificationRecord,
    Ux10NotificationSnapshot,
)
from kronos.application.swing_refresh_reminder import (
    K5RefreshReminderSnapshot,
    RefreshReminderState,
)
from kronos.application.swing_v1_review import (
    ChartAnalysisState,
    InstrumentChartAnalysisSnapshot,
    V1ReviewWorkflowSnapshot,
)
from kronos.application.swing_native_review import (
    NativeAnalysisDetailsProjection,
    NativeReviewAnalysisState,
    NativeReviewRunState,
    NativeReviewWorkflowSnapshot,
)
from kronos.application.swing_progression_watch import SwingProgressionWatchSnapshot
from kronos.application.swing_visual_v3_live import SwingVisualV3LiveSnapshot
from kronos.application.swing_mcx_supporting_context import (
    McxSupportingContextSnapshot,
)
from kronos.application.swing_trade_window import (
    NativeTradeWindowProjection,
    TradeWindowState,
)
from kronos.swing.v1.pdf_visual_review_v3_live import VisualV3AnswerImportState
from kronos.application.swing_v1_browser import (
    BrowserCandidateRecord,
    BrowserStep32Snapshot,
)
from kronos.configuration.openai_chart_analyst import (
    ChartAnalystConnectionStatus,
    ChartAnalystV2ActivationStatus,
)
from kronos.integrations.telegram import (
    TelegramConfigurationState,
    TelegramConfigurationStatus,
    TelegramPrivateChatCandidate,
)
from kronos.provider.contracts.monitoring import MonitoringConnectionState
from kronos.market.calendar import CalendarCoverageHealth, CalendarCoverageStatus
from kronos.browser.v1_analysis_status import (
    batch_analysis_status,
    instrument_analysis_status,
)
from kronos.browser.swing_readiness_presentation import (
    present_native_readiness,
)
from kronos.browser.swing_v3_presentation import V3SponsorEvidencePresentation
from kronos.browser.dashboard import SponsorDashboardProjection
from kronos.browser.reports import (
    HistoricalReportRecord,
    HistoricalReportsProjection,
    ReportFamily,
    ReportProduct,
    ReportView,
)
from kronos.swing.v1.analytical_promotion import Kr370AnalyticalClassification
from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.reference_facts import (
    CPR_CALCULATION_POLICY_IDENTITY,
    CPR_CALCULATION_POLICY_VERSION,
    REFERENCE_MACHINE_FACT_SCHEMA,
    REFERENCE_POLICY_IDENTITY,
    REFERENCE_POLICY_VERSION,
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
from kronos.swing.v1.visual_evidence_v3 import VISUAL_QUESTION_SET_V3_VERSION
from kronos.swing.v1.native_trade_construction import TradePlanRecord, TradePlanStatus
from kronos.swing.v1.native_sponsor_decision import (
    SponsorInitiationResult,
    SponsorInitiationState,
)
from kronos.swing.v1.native_active_trade_lifecycle import (
    ActiveLifecycleState,
    ActiveTradeLifecycleSnapshot,
)
from kronos.swing.v1.native_trade_journal import (
    JournalRecordType,
    TradeJournalSnapshot,
)
from kronos.swing.v1.observation_research_ledger import (
    ObservationLinkKind,
    ObservationResearchProjectionV1,
)
from kronos.swing.v1.observation_research_ledger_v2 import (
    ObservationMode,
    ObservationOperationalHandoffV2,
    ObservationOperationalRoute,
    WebSocketPresentationState,
)
from kronos.swing.v1.mtf_facts import SameRunMtfFactSnapshot
from kronos.swing.v1.relative_context import (
    RelativeContextApplicability,
    RelativeContextRecord,
    RelativeContextRun,
    RelativeContextState,
    directional_relative_context,
)
from kronos.swing.v1.mcx_supporting_context import (
    MCX_CONTEXT_INSTRUMENT_FAMILIES,
    McxSupportingContextRecord,
)
from kronos.swing.v1.native_discovery import (
    NativeDiscoveryRun,
    NativeDiscoveryStatus,
    NativeProductPath,
)
from kronos.swing.v1.native_readiness import (
    LevelAvailability,
    NativeLayer2ReadinessRecord,
    NativeReadinessState,
)
from kronos.swing.v1.progression_watch import (
    ProgressionRequirementState,
    ProgressionWatchState,
    tradingview_instruction,
)


_NAVIGATION = (
    ("Dashboard", "/dashboard", "home"),
    ("Swing", "/swing/opportunities", "swing"),
    ("Intraday", "/intraday", "bolt"),
    ("Theta Earners", "/theta-earners", "theta"),
    ("Notifications", "/notifications", "notifications"),
    ("Trading Journal", "/journal", "journal"),
    ("Portfolio", "/portfolio", "portfolio"),
    ("Reports", "/reports", "reports"),
    ("Settings", "/settings", "settings"),
)
_KOLKATA = ZoneInfo("Asia/Kolkata")

_CSS = r"""
.notification-centre-head{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin-bottom:10px}.notification-centre-products,.notification-centre-filters{display:flex;gap:6px}.notification-centre-head .button,.notification-centre-filters .button{padding:5px 9px;font-size:10px}.notification-centre-head .active,.notification-centre-filters .active{background:#0c4f83;border-color:#2c9cff}.notification-centre-ws{border:1px solid var(--line);border-radius:999px;padding:4px 9px;font-size:10px;font-weight:850}.notification-centre-ws.connected{color:var(--green);border-color:#176741}.notification-centre-ws.disconnected{color:var(--red);border-color:#793b40}.notification-centre-ws.idle{color:var(--muted)}.notification-centre-count{color:var(--muted);font-size:10px}.notification-centre-tools{display:flex;align-items:center;gap:7px;margin:8px 0 10px}.notification-centre-search{width:min(280px,100%);border:1px solid #31506a;background:#04131f;color:var(--text);border-radius:7px;padding:7px 9px}.notification-centre-notice{border:1px solid #31506a;background:#082038;border-radius:7px;padding:7px 9px;margin:8px 0;color:#b9d9ef;font-size:10px}.notification-centre-row{display:grid;grid-template-columns:62px 62px minmax(90px,130px) minmax(180px,1fr) auto auto;align-items:center;gap:8px;border-top:1px solid var(--line);padding:8px 9px;font-size:10px}.notification-centre-row:first-child{border-top:0}.notification-centre-row:hover{background:#0a2134}.notification-centre-state{font-weight:850}.notification-centre-state.live{color:var(--green)}.notification-centre-state.expired{color:var(--muted)}.notification-centre-row.failure .notification-centre-message{color:var(--red)}.notification-centre-time,.notification-centre-next{color:var(--muted)}.notification-centre-subject{font-weight:800}.notification-centre-message{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.notification-centre-actions{display:flex;gap:5px}.notification-centre-actions form{display:inline}.notification-centre-actions button,.notification-centre-actions .button{padding:4px 7px;font-size:9px;min-width:0}.notification-icon{font-size:13px}.notification-centre-list{border:1px solid var(--line);border-radius:8px;background:rgba(6,23,37,.88);overflow:hidden}.notification-centre-detail{grid-column:1/-1}.notification-centre-detail summary{cursor:pointer;color:var(--muted);font-size:9px}.notification-centre-confirm summary{list-style:none;border:1px solid #31506a;border-radius:6px;padding:4px 7px;cursor:pointer}.notification-centre-confirm summary::-webkit-details-marker{display:none}.notification-centre-confirm div{position:absolute;z-index:10;background:#071827;border:1px solid var(--line);border-radius:7px;padding:9px}.notification-centre-pagination{display:flex;justify-content:flex-end;align-items:center;gap:7px;margin-top:9px;color:var(--muted);font-size:10px}@media(max-width:850px){.notification-centre-row{grid-template-columns:60px 58px minmax(80px,1fr) auto}.notification-centre-message{grid-column:1/4}.notification-centre-next{grid-column:1/4}.notification-centre-actions{grid-column:4;grid-row:1/4}.notification-centre-tools{align-items:stretch;flex-wrap:wrap}}
:root{color-scheme:dark;--bg:#03101c;--panel:#071827;--panel2:#0a1e30;--line:#1b3549;--text:#f2f7fb;--muted:#92a8b9;--blue:#2c9cff;--green:#2ed477;--red:#ff5c63;--amber:#f6b73c;--violet:#bc7cff}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 78% 0,#0a2237 0,#03101c 38%,#020b14 100%);color:var(--text);font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;min-height:100vh}
a{color:inherit;text-decoration:none}.app{display:grid;grid-template-columns:218px 1fr;min-height:100vh}.sidebar{position:sticky;top:0;height:100vh;border-right:1px solid var(--line);background:rgba(3,15,26,.96);padding:22px 14px;display:flex;flex-direction:column}.brand{display:flex;align-items:center;gap:11px;font-size:25px;font-weight:800;letter-spacing:.04em;padding:2px 9px 22px}.brandmark{width:35px;height:35px;border-radius:8px;background:linear-gradient(135deg,#50b7ff,#1769c8);display:grid;place-items:center;font-weight:900}.nav{display:grid;gap:7px}.nav a{display:flex;gap:12px;align-items:center;padding:12px 13px;border-radius:8px;color:#d7e4ee}.nav a:hover,.nav a.active{background:#0c3962;color:#fff}.nav .icon{width:19px;color:#6bb9ff;text-align:center}.system{margin-top:auto;border:1px solid var(--line);border-radius:9px;padding:13px;color:var(--muted);font-size:12px}.system strong{display:block;color:var(--green);margin-bottom:6px}.main{min-width:0}.topbar{height:78px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:0 28px;background:rgba(3,15,26,.78);backdrop-filter:blur(12px)}.title h1{font-size:27px;margin:0}.title p{margin:2px 0 0;color:var(--muted)}.kite{display:flex;align-items:center;gap:12px}.dot{width:9px;height:9px;border-radius:50%;background:var(--muted);box-shadow:0 0 14px currentColor}.dot.CONNECTED{background:var(--green)}.dot.CONNECTING{background:var(--amber)}.dot.ERROR{background:var(--red)}button,.button{border:1px solid #246295;background:#0b2b47;color:#e9f5ff;padding:9px 14px;border-radius:7px;font:inherit;font-weight:650;cursor:pointer}button.primary{background:linear-gradient(135deg,#178ddf,#1466b4);border-color:#35a9f5}button:disabled{opacity:.45;cursor:not-allowed}.tabs{display:flex;align-items:center;gap:22px;border-bottom:1px solid var(--line);padding:0 28px;height:61px}.tabs a{height:61px;display:flex;align-items:center;color:var(--muted);border-bottom:2px solid transparent}.tabs a.active{color:#fff;border-color:var(--blue)}.badge{font-size:11px;border-radius:999px;padding:2px 7px;background:#172b3a;margin-left:6px}.toolbar{margin-left:auto}.content{padding:22px 28px 40px}.status-grid{display:grid;grid-template-columns:repeat(6,minmax(120px,1fr));gap:10px;margin-bottom:18px}.metric{border:1px solid var(--line);background:linear-gradient(150deg,rgba(12,35,55,.9),rgba(5,20,33,.92));border-radius:9px;padding:13px}.metric label{display:block;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.05em}.metric strong{display:block;font-size:20px;margin-top:4px}.panels{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(350px,.8fr);gap:16px}.market-panel{border:1px solid var(--line);background:rgba(6,23,37,.86);border-radius:11px;padding:16px;min-height:390px}.panel-heading{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line);padding-bottom:11px;margin-bottom:13px}.panel-heading h2{margin:0;font-size:17px;color:var(--blue)}.panel-heading span{font-size:12px;color:var(--muted)}.opportunity{border:1px solid #21425c;border-radius:10px;background:linear-gradient(145deg,#0a2033,#071622);padding:13px;margin-top:10px;box-shadow:0 12px 28px rgba(0,0,0,.16)}.opp-head{display:flex;align-items:center;gap:10px}.opp-identity{min-width:0}.opp-identity h3{font-size:20px;margin:0}.setup-family{display:block;color:var(--muted);font-size:12px;margin-top:1px}.direction{margin-left:auto;border:1px solid currentColor;padding:3px 8px;border-radius:6px;font-size:12px;font-weight:750}.direction-long{color:var(--green)}.direction-short{color:var(--red)}.summary-reason{color:#c9d8e3;margin:10px 0}.summary-footer{display:flex;align-items:center;justify-content:space-between;gap:12px;border-top:1px solid var(--line);padding-top:10px}.summary-rr{color:var(--muted);font-size:12px}.summary-rr strong{color:var(--green);font-size:15px;margin-left:3px}.rank{display:grid;place-items:center;width:29px;height:29px;background:#0c4f83;border-radius:6px;color:#8dd0ff;font-weight:800}.opp-head h3{font-size:22px;margin:0}.pill{border:1px solid #176741;color:var(--green);padding:3px 8px;border-radius:6px;font-size:12px}.trade-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin:15px 0}.field{border-left:1px solid var(--line);padding-left:10px}.field:first-child{border-left:0;padding-left:0}.field label{display:block;color:var(--muted);font-size:11px}.field strong{display:block;margin-top:3px}.positive{color:var(--green)}.negative{color:var(--red)}.why{border-top:1px solid var(--line);padding-top:12px;color:#c9d8e3}.risk{color:#f0b8ba;font-size:13px}.opp-actions{display:flex;justify-content:flex-end;margin-top:14px}.empty{display:grid;place-items:center;min-height:270px;text-align:center;color:var(--muted);padding:30px}.empty strong{display:block;color:#dce8f0;font-size:17px;margin-bottom:6px}.error{border:1px solid #793b40;background:#2c151c;color:#ffc3c6;border-radius:8px;padding:11px 14px;margin-bottom:16px}.workspace{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(330px,.7fr);gap:16px}.workspace section{border:1px solid var(--line);background:rgba(6,23,37,.88);border-radius:10px;padding:17px}.workspace h2{margin:0 0 13px;font-size:17px;color:var(--blue)}.workspace h3{margin:18px 0 8px;font-size:13px;text-transform:uppercase;letter-spacing:.05em;color:#7ec7ff}.workspace ul{margin:7px 0;padding-left:19px}.plan-strip{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.plan-strip div{background:#081c2c;border:1px solid var(--line);border-radius:7px;padding:10px}.plan-strip label{display:block;color:var(--muted);font-size:11px}.chart-placeholder{min-height:260px;display:grid;place-items:center;border:1px dashed #31506a!important;color:var(--muted);text-align:center}.technical{font-size:12px;color:var(--muted)}.placeholder{min-height:65vh;display:grid;place-items:center;text-align:center}.placeholder div{border:1px solid var(--line);background:var(--panel);border-radius:12px;padding:38px;max-width:520px}.placeholder h2{margin-top:0}.footer{padding:0 28px 22px;color:#698294;font-size:12px;text-align:right}
.status-grid{grid-template-columns:repeat(8,minmax(110px,1fr))}.global-empty{border:1px solid var(--line);background:#071827;color:var(--muted);border-radius:9px;padding:12px 14px;margin-bottom:16px}
.exit-control{margin-top:12px;border-top:1px solid var(--line);padding-top:10px}.exit-control summary{cursor:pointer;color:#f0b8ba;font-weight:750;list-style:none}.exit-control summary::-webkit-details-marker{display:none}.exit-confirm{margin-top:9px}.exit-confirm p{margin:0 0 9px;color:var(--muted)}.exit-actions{display:flex;gap:7px}.exit-actions button{border-color:#793b40;background:#2c151c;color:#ffc3c6}.exit-cancel{display:inline-block;border:1px solid var(--line);border-radius:7px;padding:9px 12px;color:var(--muted)}
.brandmark{display:block;flex:0 0 35px;width:35px;height:35px;border-radius:8px;background:transparent;object-fit:cover}.brandword{white-space:nowrap}
.status-strip{display:flex;align-items:center;flex-wrap:wrap;border:1px solid var(--line);background:rgba(7,24,39,.72);border-radius:8px;padding:8px 10px;margin-bottom:14px}.status-item{display:flex;align-items:baseline;gap:6px;padding:0 14px;border-left:1px solid var(--line);white-space:nowrap;font-size:12px}.status-item:first-child{border-left:0;padding-left:2px}.status-item span{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.05em}.status-item strong{font-size:13px;font-weight:650}.status-item.status-top strong{color:var(--blue)}
.status-strip{position:relative}.eligible-control{display:block}.eligible-control summary{display:flex;align-items:baseline;gap:6px;cursor:pointer;list-style:none}.eligible-control summary::-webkit-details-marker{display:none}.eligible-control summary:focus-visible{outline:1px solid var(--blue);outline-offset:4px}.eligible-control>summary strong{color:var(--blue)}.eligible-panel{position:absolute;z-index:20;top:calc(100% + 6px);left:0;right:0;white-space:normal;border:1px solid #28506c;background:#071827;border-radius:9px;padding:14px;box-shadow:0 18px 45px rgba(0,0,0,.45)}.eligible-heading{display:flex;align-items:center;justify-content:space-between;gap:12px}.eligible-heading h2{font-size:15px;letter-spacing:.05em;margin:0;color:var(--blue)}.eligible-standard{color:var(--muted);font-size:11px;margin:3px 0 10px}.eligible-list{display:grid;gap:7px}.eligible-row{display:grid;grid-template-columns:42px minmax(120px,1fr) 70px minmax(150px,1fr) 70px 110px auto;align-items:center;gap:10px;border-top:1px solid var(--line);padding:8px 0}.eligible-row:first-child{border-top:0}.eligible-rank{color:#8dd0ff;font-weight:750}.eligible-instrument{font-weight:750}.eligible-setup{color:var(--muted);font-size:12px}.eligible-selection{font-size:11px;font-weight:750}.eligible-selection.selected{color:var(--green)}.eligible-selection.not-selected{color:var(--muted)}.eligible-reason{grid-column:2/-1;color:var(--muted);font-size:11px}.eligible-empty{color:var(--muted);padding:9px 0 3px}
.panels{grid-template-columns:repeat(2,minmax(0,1fr))}
.review-note{border:1px solid #5d4b25;background:#231d11;color:#f6d997;border-radius:8px;padding:11px 14px;margin-bottom:14px}.chart-intake-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(265px,1fr));gap:12px}.chart-intake-card{border:1px solid var(--line);background:rgba(6,23,37,.88);border-radius:10px;padding:12px}.chart-intake-card h2{font-size:18px;color:var(--blue);margin:0}.native-direction-badge{border:1px solid currentColor;border-radius:6px;padding:3px 8px;font-size:11px;font-weight:850}.native-chart-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.native-chart-grid .chart-slot+.chart-slot{margin:0;padding:0;border:0}.chart-slot{display:grid;gap:7px}.chart-slot+.chart-slot{margin-top:10px;padding-top:10px;border-top:1px solid var(--line)}.chart-paste-target{min-height:82px;border:1px dashed #38617e;border-radius:8px;background:#04131f;display:grid;place-items:center;text-align:center;padding:8px;cursor:text;overflow:hidden}.chart-paste-target:focus,.chart-paste-target.replace-ready{outline:2px solid var(--blue);outline-offset:1px;border-color:transparent}.chart-paste-target.received{grid-template-columns:64px 1fr;text-align:left;border-style:solid;cursor:text}.chart-paste-target img{width:64px;height:52px;border-radius:5px;object-fit:cover;background:#020b14}.paste-key{display:block;color:var(--blue);font-size:19px;font-weight:800}.chart-paste-target small,.chart-received span{display:block;color:var(--muted);font-size:10px}.chart-received strong{color:var(--green)}.chart-slot-actions{display:flex;align-items:center;gap:6px;flex-wrap:wrap}.chart-slot-actions button,.chart-slot-actions .file-choice{padding:5px 8px;font-size:11px}.chart-slot-actions form{display:inline}.file-choice{border:0;background:transparent;color:var(--muted);cursor:pointer;text-decoration:underline;text-underline-offset:3px}.chart-file{position:absolute;width:1px;height:1px;opacity:0;pointer-events:none}.analyze-all{display:flex;justify-content:flex-end;margin-top:16px}.analyze-all button{min-width:150px}.native-analysis-all{display:flex;align-items:center;justify-content:space-between;gap:12px;border:1px solid var(--line);background:#071827;border-radius:9px;padding:10px 12px;margin:10px 0}.native-analysis-all div strong,.native-analysis-all div span{display:block}.native-analysis-all div span{color:var(--muted);font-size:11px;margin-top:2px}.native-batch-results{display:grid;gap:3px;border:1px solid var(--line);border-radius:8px;padding:8px 11px;margin-bottom:10px;color:var(--muted);font-size:10px}.native-batch-results strong{color:#dce8f0}.native-diagnostics{border-top:1px solid var(--line);margin-top:8px;padding-top:7px;font-size:10px}.native-diagnostics summary{color:var(--muted);cursor:pointer;font-weight:750}.native-diagnostics .v1-context-row{margin-top:6px;grid-template-columns:82px minmax(0,1fr);overflow-wrap:anywhere}
.analysis-batch{display:flex;align-items:center;justify-content:space-between;gap:12px;border:1px solid var(--line);background:#071827;border-radius:9px;padding:10px 13px;margin-bottom:12px}.analysis-batch span{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.05em}.analysis-batch strong{font-size:13px;color:#dce8f0}.analysis-run-times{text-align:right}.analysis-run-times strong,.analysis-run-times small{display:block}.analysis-run-times small{margin-top:2px;color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.04em}.chart-intake-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px}.chart-intake-card .chart-intake-head h2{margin:0}.analysis-state{border:1px solid #31506a;border-radius:999px;padding:3px 7px;font-size:10px;font-weight:800;white-space:nowrap;color:var(--muted)}.analysis-state.analyzing{border-color:#2b78ad;color:#8dd0ff}.analysis-state.analyzed{border-color:#176741;color:var(--green)}.analysis-state.context-incomplete{border-color:#82631f;color:var(--amber)}.analysis-state.analysis-failed{border-color:#793b40;color:var(--red)}
.four-chart-label{display:block;color:#dce8f0;font-size:11px;font-weight:800;letter-spacing:.05em}.four-chart-timeframes{display:block;color:var(--muted);font-size:10px;margin-top:2px}.v1-context-result{border-top:1px solid var(--line);margin-top:12px;padding-top:10px;display:grid;gap:6px}.v1-context-row{display:grid;grid-template-columns:96px minmax(0,1fr);gap:8px;font-size:11px}.v1-context-row span{color:var(--muted);text-transform:uppercase;letter-spacing:.04em}.v1-context-row strong{font-weight:700}.v1-context-row .supportive{color:var(--green)}.v1-context-row .partial,.v1-context-row .incomplete{color:var(--amber)}.v1-context-row .contradictory{color:var(--red)}.shadow-authority{color:var(--muted);font-size:10px;text-align:right;margin-top:9px;letter-spacing:.04em}
.shadow-banner{border:1px solid #82631f;background:#241d0a;color:var(--amber);border-radius:8px;padding:8px 11px;margin-bottom:12px;font-size:11px;font-weight:800;letter-spacing:.05em}.shadow-list{display:grid;gap:10px}.shadow-card{border:1px solid var(--line);background:rgba(6,23,37,.88);border-radius:9px;padding:12px}.shadow-card summary{cursor:pointer;list-style:none;display:grid;grid-template-columns:minmax(150px,1fr) repeat(3,auto);gap:12px;align-items:center}.shadow-card summary::-webkit-details-marker{display:none}.shadow-state{color:var(--blue);font-weight:800}.shadow-comparison{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:12px}.shadow-side{border-top:1px solid var(--line);padding-top:9px}.shadow-side h3{font-size:10px;color:var(--muted);letter-spacing:.06em;margin:0 0 7px}.shadow-timeframes{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px}.shadow-timeframe{border:1px solid var(--line);border-radius:6px;padding:7px}.shadow-timeframe span,.shadow-wait span{display:block;color:var(--muted);font-size:9px;letter-spacing:.05em}.shadow-timeframe strong{font-size:11px}.shadow-wait{margin-top:10px;border-left:2px solid var(--blue);padding:7px 9px;background:#061a29}.shadow-observation{display:flex;gap:7px;margin-top:10px}.shadow-observation input{flex:1;border:1px solid #31506a;background:#04131f;color:var(--text);border-radius:6px;padding:7px 9px}.remainder-tag{color:var(--amber);font-size:10px;margin-top:7px}
.one-minute{display:grid;gap:12px}.one-minute h3{margin:0 0 5px;color:var(--muted);font-size:10px;letter-spacing:.07em}.one-minute-status{font-size:16px;color:var(--blue)}.one-minute p{margin:2px 0;color:#cfdee8}.one-minute-facts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}.one-minute-fact{border:1px solid var(--line);border-radius:6px;padding:7px 9px;font-size:11px}.one-minute-wait{border-left:2px solid var(--amber);background:#211b0e;padding:8px 10px}.one-minute details{border-top:1px solid var(--line);padding-top:9px}.one-minute summary{cursor:pointer;color:var(--muted);font-size:11px}.native-trade-plan{margin-top:12px;border:1px solid #28506a;border-radius:8px;background:#0b1923;padding:12px}.native-trade-plan h3{margin:0;color:var(--blue);font-size:13px}.native-trade-plan-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-top:10px}.native-trade-plan-grid div{border:1px solid var(--line);border-radius:6px;padding:8px}.native-trade-plan-grid span{display:block;color:var(--muted);font-size:9px;letter-spacing:.08em}.native-trade-plan-grid strong{display:block;margin-top:3px;font-size:14px}.native-trade-plan .why{margin:10px 0 0;color:#cfdee8;font-size:11px}
.journal-filters{display:flex;gap:7px;margin-bottom:12px}.journal-filters .button{font-size:11px;padding:6px 10px}.journal-filters .button.primary{background:#0c4f83;border-color:#2c9cff}
.journal-head{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:12px}.journal-products{display:flex;gap:6px}.journal-products .button{padding:6px 12px;font-size:11px}.journal-products .active{background:#0c4f83;border-color:#2c9cff}.journal-date{color:var(--muted);font-size:11px}.journal-ws{margin-left:auto;border:1px solid var(--line);border-radius:999px;padding:4px 9px;font-size:10px;font-weight:850}.journal-ws.CONNECTED{color:var(--green);border-color:#176741}.journal-ws.DISCONNECTED{color:var(--red);border-color:#793b40}.journal-ws.IDLE{color:var(--muted)}.journal-toolbar{display:flex;align-items:center;gap:8px;margin-bottom:12px}.journal-search{width:min(300px,100%);border:1px solid #31506a;background:#04131f;color:var(--text);border-radius:7px;padding:8px 10px}.journal-section{border:1px solid var(--line);border-radius:10px;background:rgba(6,23,37,.86);margin-top:12px;overflow:hidden}.journal-section.paper{border-left:3px solid #6588e8}.journal-section.live{border-left:3px solid #2ed477}.journal-section.observation{border-left:3px solid #37b8d8}.journal-section-head{display:flex;align-items:baseline;justify-content:space-between;gap:10px;padding:11px 13px;border-bottom:1px solid var(--line)}.journal-section-head h2{font-size:13px;letter-spacing:.07em;margin:0}.journal-section-head span{color:var(--muted);font-size:10px}.journal-table-wrap{overflow-x:auto}.journal-table{width:100%;border-collapse:collapse;font-size:11px}.journal-table th,.journal-table td{padding:8px 9px;text-align:left;white-space:nowrap;border-top:1px solid rgba(27,53,73,.65)}.journal-table tr:first-child td{border-top:0}.journal-table th{color:var(--muted);font-size:9px;letter-spacing:.05em;text-transform:uppercase}.journal-table tbody tr:hover{background:#0a2134}.journal-table a{color:#dce8f0;font-weight:800}.journal-side.LONG{color:var(--green)}.journal-side.SHORT{color:var(--red)}.journal-pnl.positive{color:var(--green)}.journal-pnl.negative{color:var(--red)}.journal-monitor.ACTIVE{color:var(--green)}.journal-monitor.INTERRUPTED{color:var(--red)}.journal-detail{margin-top:12px;border:1px solid #28506a;border-radius:9px;background:#071827;padding:13px}.journal-detail h2{margin:0 0 10px;color:var(--blue);font-size:15px}.journal-detail-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}.journal-detail-grid div{border:1px solid var(--line);border-radius:6px;padding:8px}.journal-detail-grid span{display:block;color:var(--muted);font-size:9px;text-transform:uppercase}.journal-detail-grid strong{display:block;margin-top:3px;font-size:12px}.journal-reports{margin-left:auto}@media(max-width:760px){.journal-ws{margin-left:0}.journal-detail-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
.reports-head{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:10px}.reports-products,.reports-views,.reports-quick{display:flex;gap:6px;flex-wrap:wrap}.reports-head .button,.reports-views .button,.reports-quick .button{padding:5px 9px;font-size:10px}.reports-head .active,.reports-views .active{background:#0c4f83;border-color:#2c9cff}.reports-date{color:var(--muted);font-size:10px}.reports-layout{display:grid;grid-template-columns:minmax(0,1fr) 245px;gap:12px;margin-top:12px}.reports-main{min-width:0}.reports-filter{border:1px solid var(--line);border-radius:9px;background:rgba(6,23,37,.88);padding:12px;height:max-content}.reports-filter h2{margin:0 0 9px;font-size:12px;color:var(--blue)}.reports-filter label{display:block;color:var(--muted);font-size:9px;margin-top:7px;text-transform:uppercase}.reports-filter input,.reports-filter select{width:100%;border:1px solid #31506a;background:#04131f;color:var(--text);border-radius:6px;padding:7px 8px;margin-top:3px}.reports-filter-actions{display:flex;gap:6px;margin-top:10px;flex-wrap:wrap}.reports-filter-actions button,.reports-filter-actions .button{padding:6px 8px;font-size:10px}.reports-summary{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:7px;margin-bottom:10px}.reports-metric{border:1px solid var(--line);border-radius:7px;background:#071827;padding:8px}.reports-metric span{display:block;color:var(--muted);font-size:8px;letter-spacing:.06em}.reports-metric strong{display:block;margin-top:2px;font-size:14px}.reports-chart{display:flex;gap:8px;align-items:flex-end;min-height:72px;border:1px solid var(--line);border-radius:8px;background:#061421;padding:10px;margin-bottom:10px}.reports-bar{flex:1;min-width:70px}.reports-bar span{display:block;color:var(--muted);font-size:9px}.reports-bar strong{display:block;color:#dce8f0;font-size:13px}.reports-bar i{display:block;height:5px;margin-top:5px;border-radius:4px;background:var(--blue)}.reports-bar.paper i{background:#6588e8}.reports-bar.live i{background:#2ed477}.reports-bar.observation i{background:#37b8d8}.reports-table-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:9px}.reports-table{width:100%;border-collapse:collapse;font-size:10px}.reports-table th,.reports-table td{text-align:left;white-space:nowrap;padding:8px;border-top:1px solid var(--line)}.reports-table th{border-top:0;color:var(--muted);font-size:8px;letter-spacing:.05em}.reports-table tbody tr:hover{background:#0a2134}.reports-family.paper{color:#9bb0ff}.reports-family.live{color:var(--green)}.reports-family.paper_observation{color:#58d2ea}.reports-pnl.positive{color:var(--green)}.reports-pnl.negative{color:var(--red)}.reports-pagination{display:flex;align-items:center;justify-content:flex-end;gap:7px;margin-top:9px;color:var(--muted);font-size:10px}.reports-detail{margin-bottom:10px}.reports-unavailable{color:var(--muted);font-size:9px;margin:7px 0}.reports-export-note{color:var(--muted);font-size:9px;margin-top:8px}@media(max-width:900px){.reports-layout{grid-template-columns:1fr}.reports-filter{order:-1}.reports-summary{grid-template-columns:repeat(3,minmax(0,1fr))}}
.mtf-fact-banner{border:1px solid #28506c;background:#071f32;color:#8dd0ff;border-radius:8px;padding:8px 11px;margin-bottom:12px;font-size:11px;font-weight:800}.mtf-fact-list{display:grid;gap:8px}.mtf-fact-card{border:1px solid var(--line);background:rgba(6,23,37,.88);border-radius:8px;padding:10px}.mtf-fact-card summary{cursor:pointer;display:flex;justify-content:space-between;gap:12px}.mtf-fact-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px;margin-top:9px}.mtf-fact-timeframe{border:1px solid var(--line);border-radius:6px;padding:8px;min-width:0}.mtf-fact-timeframe h3{margin:0 0 5px;color:var(--blue);font-size:12px}.mtf-fact-timeframe p{margin:2px 0;font-size:10px;color:var(--muted);overflow-wrap:anywhere}.mtf-fact-timeframe strong{color:var(--text)}
.configuration{max-width:760px;border:1px solid var(--line);background:rgba(6,23,37,.88);border-radius:11px;padding:20px}.configuration-head{display:flex;align-items:center;justify-content:space-between;gap:16px;border-bottom:1px solid var(--line);padding-bottom:14px;margin-bottom:16px}.configuration-head h2{margin:0;color:var(--blue)}.configuration-state{display:flex;align-items:center;justify-content:space-between;gap:16px;margin:10px 0}.connection-status{border:1px solid #246295;border-radius:999px;padding:5px 10px;font-size:12px;font-weight:800}.connection-status.CONNECTED{border-color:#176741;color:var(--green)}.connection-status.CONNECTION-FAILED{border-color:#793b40;color:var(--red)}.credential-form{display:grid;gap:10px;margin-top:18px;padding-top:16px;border-top:1px solid var(--line)}.credential-form label{font-weight:700}.credential-form input{width:100%;border:1px solid #31506a;background:#04131f;color:var(--text);border-radius:7px;padding:11px 12px;font:inherit}.credential-form input:focus{outline:2px solid var(--blue);outline-offset:1px}.configuration-actions{display:flex;gap:10px;align-items:center;margin-top:16px}.configuration-note{color:var(--muted);font-size:12px;margin:9px 0 0}.engineering-diagnostics{margin-bottom:16px}.read-only-badge{border:1px solid #31506a;border-radius:999px;color:#8dd0ff;font-size:10px;font-weight:850;letter-spacing:.08em;padding:4px 8px}.diagnostic-intro{color:var(--muted);font-size:12px;margin:0 0 13px}.diagnostic-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px}.diagnostic-card{display:flex;flex-direction:column;min-height:122px;border:1px solid var(--line);border-radius:8px;background:#061421;padding:11px}.diagnostic-card:hover{border-color:#2c6f9e;background:#082038}.diagnostic-card small{color:#8dd0ff;font-size:9px;font-weight:800;letter-spacing:.08em}.diagnostic-card strong{font-size:12px;margin-top:7px}.diagnostic-card span{color:var(--muted);font-size:11px;margin-top:5px}.diagnostic-card b{color:var(--blue);font-size:11px;margin-top:auto;padding-top:9px}@media(max-width:760px){.diagnostic-grid{grid-template-columns:1fr}}
.step32-workflow{margin-top:16px;border:1px solid var(--line);background:rgba(6,23,37,.88);border-radius:10px;padding:16px}.step32-head{display:flex;align-items:center;gap:10px;border-bottom:1px solid var(--line);padding-bottom:10px}.step32-head h2{margin:0;font-size:18px}.step32-grid{display:grid;grid-template-columns:1.2fr .8fr .8fr .9fr;gap:12px;margin-top:12px}.step32-block{border-left:1px solid var(--line);padding-left:12px}.step32-block:first-child{border-left:0;padding-left:0}.step32-block h3{margin:0 0 8px;color:var(--muted);font-size:11px;letter-spacing:.06em;text-transform:uppercase}.step32-values{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;margin-top:10px}.step32-value label{display:block;color:var(--muted);font-size:10px}.step32-value strong{font-size:13px}.step32-context{display:grid;gap:7px;font-size:12px}.step32-context span{display:block;color:var(--muted);font-size:10px}.decision-options{display:flex;gap:5px;flex-wrap:wrap}.decision-option{border:1px solid var(--line);border-radius:6px;padding:5px 8px;color:var(--muted);font-size:11px;background:#081c2c}.decision-option.selected{border-color:var(--blue);color:#dff1ff}.decision-time{color:var(--muted);font-size:10px;margin-top:7px}.model-position{display:grid;gap:7px;margin-top:9px}.model-position div{display:flex;justify-content:space-between;gap:8px;font-size:12px}.model-position span{color:var(--muted)}.workflow-list{display:grid;gap:12px}.workflow-card{border:1px solid var(--line);background:rgba(6,23,37,.88);border-radius:10px;padding:14px}.workflow-card-head{display:flex;align-items:center;gap:10px}.workflow-card-head h2{margin:0;font-size:18px}.workflow-card-state{margin-left:auto;color:var(--blue);font-size:11px;font-weight:800}.workflow-card-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin:12px 0}.workflow-card-grid label{display:block;color:var(--muted);font-size:10px}.workflow-card-actions{display:flex;justify-content:flex-end}.action-required{border:1px solid #8a4c26;background:#2d1b0f;color:#ffd59c;border-radius:7px;padding:9px 11px;margin-top:10px;font-weight:750}.workflow-empty{border:1px solid var(--line);background:rgba(6,23,37,.88);border-radius:10px;padding:30px;text-align:center;color:var(--muted)}
.native-chart-grid.single{grid-template-columns:1fr}
.analysis-details{display:grid;gap:12px;max-width:1180px}.analysis-section{border:1px solid var(--line);background:rgba(6,23,37,.88);border-radius:10px;padding:16px}.analysis-section h2{margin:0 0 10px;color:var(--blue);font-size:15px}.analysis-facts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.analysis-fact{border-left:2px solid #28506a;padding:5px 9px;font-size:11px}.analysis-fact span{display:block;color:var(--muted);font-size:9px;letter-spacing:.06em;text-transform:uppercase}.analysis-table{width:100%;border-collapse:collapse;font-size:11px}.analysis-table th,.analysis-table td{text-align:left;vertical-align:top;border-top:1px solid var(--line);padding:7px}.analysis-table th{color:var(--muted);font-size:9px;letter-spacing:.05em}.analysis-decision{font-size:18px;font-weight:800}.analysis-next{border-left:3px solid var(--amber)}
.mcx-context-strip{display:flex;align-items:center;gap:10px;flex-wrap:wrap;border:1px solid var(--line);background:rgba(6,23,37,.88);border-radius:8px;padding:7px 10px;margin:8px 0;font-size:10px}.mcx-context-strip>strong{color:var(--blue);letter-spacing:.06em}.mcx-context-slot{display:flex;align-items:center;gap:7px;flex-wrap:wrap}.mcx-context-slot b{font-size:9px}.mcx-context-slot form{display:inline}.mcx-context-status{color:var(--muted)}.mcx-context-error{display:grid;gap:1px;border-left:2px solid var(--red);padding-left:7px;color:#ffb1b6}.mcx-context-error strong{font-size:9px}.mcx-context-error span{font-size:9px;color:#e8c2c4}.mcx-context-prep{position:relative}.mcx-context-prep>summary{color:var(--blue);cursor:pointer;font-weight:800}.mcx-context-targets{display:grid;grid-template-columns:repeat(2,minmax(180px,1fr));gap:8px;position:absolute;z-index:5;top:24px;left:0;width:min(440px,75vw);padding:9px;border:1px solid var(--line);border-radius:8px;background:#071827;box-shadow:0 10px 30px #010812}.mcx-context-targets h3{margin:0 0 5px;font-size:10px;color:#dce8f0}.mcx-context-targets .chart-paste-target{min-height:68px}.mcx-context-targets .chart-slot-actions{margin-top:4px}@media(max-width:700px){.mcx-context-targets{grid-template-columns:1fr;position:fixed;left:12px;right:12px;top:auto;width:auto}}
.missing-evidence{display:block;color:var(--amber);font-size:10px;margin-top:5px}.missing-evidence strong{color:#ffd98c}.blocker-list{margin:8px 0 0;padding-left:18px;color:var(--muted);font-size:11px}
.native-opportunity{padding:10px 11px;margin-top:7px}.native-opportunity .opp-head{gap:8px}.native-opportunity .opp-identity h3{font-size:18px;line-height:1.2}.native-opportunity .setup-family{font-size:11px;margin-top:0}.native-opportunity .direction{padding:2px 7px;font-size:11px}.native-opportunity .summary-reason{font-size:11px;line-height:1.35;margin:6px 0}.native-opportunity .summary-footer{align-items:flex-end;gap:7px;padding-top:7px}.native-opportunity .summary-rr{flex:1 1 220px;min-width:0;font-size:11px;line-height:1.35;overflow-wrap:anywhere}.native-opportunity .summary-rr>strong{font-size:12px}.native-opportunity .missing-evidence{font-size:9px;line-height:1.3;margin-top:3px}.native-opportunity-actions{display:flex;flex:0 1 auto;justify-content:flex-end;gap:5px;flex-wrap:wrap}.native-opportunity-actions .button{display:inline-flex;align-items:center;min-height:27px;padding:4px 8px;font-size:10px;line-height:1.15;white-space:nowrap}
.kr370-state{display:inline-flex;align-items:center;border:1px solid currentColor;border-radius:6px;padding:2px 7px;font-size:11px;font-weight:850;letter-spacing:.035em}.kr370-state-now{color:#d8ffea;border-color:#34dc88;background:#12623e;box-shadow:0 0 16px rgba(52,220,136,.18)}.kr370-state-ready{color:#77e6a9;border-color:#248a59;background:rgba(23,103,65,.16)}.kr370-state-potential{color:#ffd57a;border-color:#82631f;background:#2a210c}.kr370-state-no-setup{color:#ff9a9f;border-color:#793b40;background:#2c151c}.kr370-state-unavailable{color:#a9b8c3;border-color:#465866;background:#111d25}.kr370-card-line{display:block;color:var(--muted);font-size:9px;margin-top:4px;letter-spacing:.035em}.kr370-card-line strong{color:#dce8f0}.analysis-decision.kr370-state{font-size:18px;padding:4px 9px;margin-bottom:9px}
.progression-summary{display:block;color:var(--muted);font-size:9px;margin-top:3px;text-transform:uppercase;letter-spacing:.04em}.progression-list{display:grid;gap:8px}.progression-row{display:grid;grid-template-columns:20px 1fr;gap:8px;border-top:1px solid var(--line);padding-top:8px}.progression-row:first-child{border-top:0;padding-top:0}.progression-marker{color:var(--blue);font-weight:800}.progression-state{display:block;color:var(--amber);font-size:9px;font-weight:800;letter-spacing:.06em;margin-top:2px}.progression-row small{display:block;color:var(--muted);font-size:10px;margin-top:4px}.progression-row form{margin-top:7px}.progression-row details{margin-top:7px}.progression-row details .analysis-fact{margin-top:5px}
.notification-tabs{display:flex;gap:7px;margin-bottom:12px}.notification-tabs .button{padding:6px 11px;font-size:11px}.notification-tabs .active{background:#0c4f83;border-color:#2c9cff}.notification-action-centre{border:1px solid #8a4c26;background:#21170f;border-radius:9px;padding:11px 13px;margin-bottom:12px}.notification-action-centre h2{margin:0 0 5px;color:#ffd59c;font-size:13px}.notification-action-centre p{margin:0;color:var(--muted);font-size:11px}.notification-list{display:grid;gap:9px}.notification-row{border:1px solid var(--line);background:rgba(6,23,37,.88);border-radius:9px;padding:12px}.notification-head{display:flex;align-items:center;gap:9px}.notification-head h2{font-size:18px;margin:0}.notification-product{color:var(--blue);font-size:10px;font-weight:800}.notification-state{margin-left:auto;border:1px solid currentColor;border-radius:999px;padding:3px 8px;font-size:10px;font-weight:800}.notification-state.ACTIVE{color:var(--green)}.notification-state.TRIGGERED{color:var(--amber)}.notification-state.INACTIVE{color:var(--muted)}.notification-state.STALE{color:var(--red)}.notification-condition{margin:7px 0 4px;font-weight:750}.notification-trigger{border-left:2px solid var(--amber);padding:6px 9px;margin:8px 0;background:#211a0d}.notification-trigger strong,.notification-trigger span{display:block}.notification-trigger span{color:var(--amber);font-size:11px}.notification-trigger small{color:#ffd59c}.notification-meta{display:flex;gap:12px;flex-wrap:wrap;color:var(--muted);font-size:10px}.notification-actions{display:flex;align-items:flex-start;gap:6px;flex-wrap:wrap;margin-top:9px}.notification-actions form{display:inline}.notification-actions button,.notification-actions .button{padding:5px 8px;font-size:10px}.notification-confirm summary{list-style:none;border:1px solid #246295;background:#0b2b47;color:#e9f5ff;padding:5px 8px;border-radius:7px;font-size:10px;font-weight:650;cursor:pointer}.notification-confirm summary::-webkit-details-marker{display:none}.notification-confirm div{position:absolute;z-index:10;max-width:330px;border:1px solid var(--line);background:#071827;padding:10px;border-radius:8px;box-shadow:0 12px 30px rgba(0,0,0,.45)}.notification-confirm p{margin:0 0 7px;color:var(--muted);font-size:11px}.notification-history{margin-top:8px;border-top:1px solid var(--line);padding-top:7px}.notification-history summary{cursor:pointer;color:var(--muted);font-size:10px}.notification-history ul{margin:6px 0 0;padding-left:18px;color:var(--muted);font-size:10px}
.dashboard-section-title{display:flex;align-items:baseline;justify-content:space-between;margin:0 0 10px}.dashboard-section-title h2{margin:0;font-size:13px;letter-spacing:.08em;color:#dce8f0}.dashboard-section-title span{color:var(--muted);font-size:10px}.strategy-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;min-height:330px}.strategy-card{display:flex;flex-direction:column;min-width:0;border:1px solid var(--strategy-line);border-radius:11px;padding:15px;background:linear-gradient(150deg,var(--strategy-tint),rgba(5,20,33,.92));box-shadow:inset 0 1px 0 var(--strategy-glow),0 14px 32px rgba(0,0,0,.14)}.strategy-card.swing{--strategy-line:#256da4;--strategy-tint:rgba(19,73,112,.3);--strategy-glow:rgba(80,183,255,.2);--strategy-accent:#50b7ff}.strategy-card.intraday{--strategy-line:#24714a;--strategy-tint:rgba(24,91,60,.24);--strategy-glow:rgba(46,212,119,.16);--strategy-accent:#43dc88}.strategy-card.theta{--strategy-line:#60458a;--strategy-tint:rgba(73,48,108,.27);--strategy-glow:rgba(188,124,255,.16);--strategy-accent:#bc7cff}.strategy-card.fundamental{--strategy-line:#786020;--strategy-tint:rgba(100,77,20,.25);--strategy-glow:rgba(246,183,60,.15);--strategy-accent:#f6c85f}.strategy-card h3{margin:0;color:var(--strategy-accent);font-size:16px;letter-spacing:.05em}.strategy-counts{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin:13px 0}.strategy-count{border:1px solid var(--strategy-line);border-radius:7px;padding:7px}.strategy-count span{display:block;color:var(--muted);font-size:9px;letter-spacing:.08em}.strategy-count strong{display:block;font-size:20px;margin-top:1px}.strategy-groups{display:grid;gap:7px}.strategy-group{border-top:1px solid rgba(146,168,185,.18);padding-top:6px}.strategy-group span{display:block;color:var(--muted);font-size:9px;letter-spacing:.06em}.strategy-instruments{display:flex;flex-wrap:wrap;gap:4px;margin-top:4px}.strategy-instruments a{border:1px solid var(--strategy-line);border-radius:999px;padding:2px 6px;font-size:10px}.strategy-instruments a:hover{background:var(--strategy-tint)}.strategy-empty{color:var(--muted);font-size:11px;margin:auto 0;text-align:center}.strategy-footer{margin-top:auto;padding-top:13px}.strategy-footer a,.strategy-footer span{color:var(--strategy-accent);font-size:10px;font-weight:800;letter-spacing:.05em}.strategy-footer span{opacity:.55}.attention-centre{margin-top:18px}.attention-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.attention-panel{border:1px solid var(--line);border-radius:10px;background:rgba(6,23,37,.82);padding:13px;min-height:158px}.attention-panel h3{margin:0 0 9px;font-size:12px;color:#dce8f0;letter-spacing:.06em}.dashboard-alert,.dashboard-issue{display:grid;gap:2px;border-top:1px solid var(--line);padding:7px 0;font-size:10px}.dashboard-alert:first-of-type,.dashboard-issue:first-of-type{border-top:0}.dashboard-alert{grid-template-columns:90px 58px minmax(0,1fr) 92px}.dashboard-alert strong{color:#dce8f0}.dashboard-alert span,.dashboard-issue span{color:var(--muted)}.dashboard-alert-state{color:var(--amber)!important;text-align:right}.dashboard-alert-state small{display:block;color:var(--muted);font-size:8px}.attention-footer{display:block;color:var(--blue);font-size:10px;font-weight:800;margin-top:8px}.dashboard-status{margin:14px 0 0}.dashboard-status .status-item{flex:1 1 auto}.dashboard-read-only{color:var(--muted);font-size:9px;text-align:right;margin-top:7px;letter-spacing:.06em}
.ux10-row{border-color:#226da3;background:linear-gradient(100deg,rgba(8,42,69,.96),rgba(5,24,39,.96))}.ux10-row.priority-high{box-shadow:inset 3px 0 #47b7ff}.ux10-event{color:#8dd0ff;font-size:10px;font-weight:850;letter-spacing:.06em}.ux10-action{color:#c4e8ff;font-size:11px;margin-top:7px}.telegram-options{display:grid;gap:7px;margin:10px 0}.telegram-option{display:flex;align-items:center;gap:8px;border:1px solid var(--line);padding:8px;border-radius:7px}
@media(max-width:1200px){.strategy-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:1050px){.status-grid{grid-template-columns:repeat(3,1fr)}.strategy-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.panels,.workspace{grid-template-columns:1fr}.attention-grid{grid-template-columns:1fr}.step32-grid{grid-template-columns:1fr}.step32-block{border-left:0;border-top:1px solid var(--line);padding:10px 0 0}.step32-block:first-child{border-top:0;padding-top:0}.market-panel{min-height:260px}}
@media(min-width:761px){.panels{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:760px){.app{grid-template-columns:1fr}.sidebar{position:static;height:auto}.nav{grid-template-columns:repeat(2,1fr)}.system{display:none}.topbar{height:auto;padding:18px;align-items:flex-start;gap:14px}.tabs{overflow:auto;padding:0 18px}.content{padding:18px}.status-grid,.strategy-grid{grid-template-columns:1fr}.trade-grid,.plan-strip{grid-template-columns:1fr 1fr}.kite{flex-wrap:wrap;justify-content:flex-end}.chart-intake-list,.native-chart-grid{grid-template-columns:1fr}.dashboard-alert{grid-template-columns:1fr}.dashboard-alert-state{text-align:left}}
"""


def render_dashboard(
    snapshot: BrowserWorkspaceSnapshot,
    dashboard: SponsorDashboardProjection,
) -> str:
    """Render one read-only derivative Sponsor strategy command centre."""

    if type(dashboard) is not SponsorDashboardProjection:
        raise TypeError("SPONSOR_DASHBOARD_PROJECTION_INVALID")
    swing = _dashboard_swing_card(dashboard)
    inactive = (
        _dashboard_inactive_strategy(
            "INTRADAY", "intraday", "/intraday", "VIEW INTRADAY →"
        )
        + _dashboard_inactive_strategy(
            "THETA EARNERS", "theta", "/theta-earners", "VIEW THETA EARNERS →"
        )
        + _dashboard_inactive_strategy("FUNDAMENTAL", "fundamental", None, None)
    )
    strategy = (
        '<section><div class="dashboard-section-title"><h2>STRATEGY SUMMARY</h2>'
        '<span>CURRENT AUTHORITATIVE RECORDS</span></div>'
        f'<div class="strategy-grid">{swing}{inactive}</div></section>'
    )
    alerts = (
        "".join(
            '<div class="dashboard-alert"><strong>' + escape(item.instrument)
            + '</strong><span>' + escape(item.strategy) + '</span><span>'
            + escape(item.condition) + '</span><span class="dashboard-alert-state">'
            + escape(item.state.value) + '<small>'
            + escape(item.observed_at.astimezone(_KOLKATA).strftime("%H:%M IST"))
            + '</small></span></div>'
            for item in dashboard.active_alerts
        )
        or '<div class="strategy-empty">NO ACTIVE ALERTS</div>'
    )
    issues = (
        "".join(
            '<div class="dashboard-issue"><strong>' + escape(item.summary)
            + '</strong><span>' + escape(item.identity.replace("_", " "))
            + '</span></div>'
            for item in dashboard.issues
        )
        or '<div class="strategy-empty">NO CURRENT SYSTEM / DATA ISSUES</div>'
    )
    attention = (
        '<section class="attention-centre"><div class="dashboard-section-title">'
        '<h2>ATTENTION CENTRE</h2><span>FACTUAL CURRENT STATE</span></div>'
        '<div class="attention-grid"><div class="attention-panel"><h3>ACTIVE ALERTS</h3>'
        + alerts + '<a class="attention-footer" href="/notifications">VIEW ALL ALERTS →</a>'
        '</div><div class="attention-panel"><h3>SYSTEM / DATA ISSUES</h3>'
        + issues + '</div></div></section>'
    )
    last = (
        "NOT AVAILABLE"
        if dashboard.last_successful_analysis is None
        else dashboard.last_successful_analysis.astimezone(_KOLKATA).strftime(
            "%d %b %Y · %H:%M IST"
        ).upper()
    )
    status = (
        '<div class="status-strip dashboard-status">'
        '<div class="status-item"><span>SYSTEM STATUS</span><strong>'
        + escape(dashboard.system_status) + '</strong></div>'
        '<div class="status-item"><span>DATA STATUS</span><strong>'
        + escape(dashboard.data_status) + '</strong></div>'
        '<div class="status-item"><span>ANALYSIS</span><strong>'
        + escape(dashboard.analysis_status) + '</strong></div>'
        '<div class="status-item"><span>LAST SUCCESSFUL ANALYSIS</span><strong>'
        + escape(last) + '</strong></div></div>'
        '<div class="dashboard-read-only">READ-ONLY DERIVATIVE SURFACE · '
        'NO ANALYTICAL, TRADING OR EXECUTION AUTHORITY</div>'
    )
    return _page(
        title="Strategy Command Centre",
        subtitle="Current governed strategy attention and system state.",
        snapshot=snapshot,
        active_nav="Dashboard",
        active_tab="",
        body=strategy + attention + status,
    )


def _dashboard_swing_card(dashboard: SponsorDashboardProjection) -> str:
    classifications = (
        (Kr370AnalyticalClassification.BUY_NOW, "BUY NOW"),
        (Kr370AnalyticalClassification.SELL_NOW, "SELL NOW"),
        (Kr370AnalyticalClassification.BUY_READY, "BUY READY"),
        (Kr370AnalyticalClassification.SELL_READY, "SELL READY"),
    )
    groups = []
    for state, label in classifications:
        values = tuple(
            item for item in dashboard.swing_opportunities
            if item.classification is state
        )
        if not values:
            continue
        instruments = "".join(
            '<a href="/swing/analysis-details/' + escape(item.run_identity) + '/'
            + quote(item.instrument, safe="") + '">' + escape(item.instrument) + '</a>'
            for item in values
        )
        groups.append(
            '<div class="strategy-group"><span>' + label
            + '</span><div class="strategy-instruments">' + instruments + '</div></div>'
        )
    if not dashboard.swing_summary_available:
        content = '<div class="strategy-empty">CURRENT SWING RESULTS UNAVAILABLE</div>'
    elif not groups:
        content = (
            '<div class="strategy-empty">NO BUY/SELL NOW OR READY OPPORTUNITIES</div>'
        )
    else:
        content = '<div class="strategy-groups">' + "".join(groups) + '</div>'
    return (
        '<article class="strategy-card swing"><h3>SWING</h3>'
        '<div class="strategy-counts"><div class="strategy-count"><span>NOW</span><strong>'
        + str(dashboard.now_count) + '</strong></div><div class="strategy-count">'
        '<span>READY</span><strong>' + str(dashboard.ready_count) + '</strong></div></div>'
        + content + '<div class="strategy-footer"><a href="/swing/opportunities">'
        'VIEW SWING →</a></div></article>'
    )


def _dashboard_inactive_strategy(
    title: str,
    css_class: str,
    href: str | None,
    action: str | None,
) -> str:
    footer = (
        '<span>RESERVED</span>'
        if href is None or action is None
        else '<a href="' + href + '">' + action + '</a>'
    )
    return (
        '<article class="strategy-card ' + css_class + '"><h3>' + title + '</h3>'
        '<div class="strategy-empty">SUMMARY NOT YET ACTIVATED</div>'
        '<div class="strategy-footer">' + footer + '</div></article>'
    )


def render_opportunities(
    snapshot: BrowserWorkspaceSnapshot,
    discovery: NativeDiscoveryRun | None = None,
    review: NativeReviewWorkflowSnapshot | None = None,
    progression: SwingProgressionWatchSnapshot | None = None,
    visual_v3: tuple[V3SponsorEvidencePresentation, ...] = (),
    trade_windows: tuple[NativeTradeWindowProjection, ...] = (),
    refresh_reminders: K5RefreshReminderSnapshot | None = None,
    projection_revision: str | None = None,
) -> str:
    """Render the current successful Native Discovery opportunity population."""

    if discovery is not None and type(discovery) is not NativeDiscoveryRun:
        raise TypeError("NATIVE_OPPORTUNITIES_DISCOVERY_INVALID")
    if review is not None and type(review) is not NativeReviewWorkflowSnapshot:
        raise TypeError("NATIVE_OPPORTUNITIES_REVIEW_INVALID")
    if progression is not None and type(progression) is not SwingProgressionWatchSnapshot:
        raise TypeError("NATIVE_OPPORTUNITIES_PROGRESSION_INVALID")
    if type(visual_v3) is not tuple or any(
        type(item) is not V3SponsorEvidencePresentation for item in visual_v3
    ):
        raise TypeError("NATIVE_OPPORTUNITIES_V3_PRESENTATION_INVALID")
    if type(trade_windows) is not tuple or any(
        type(item) is not NativeTradeWindowProjection for item in trade_windows
    ):
        raise TypeError("NATIVE_OPPORTUNITIES_TRADE_WINDOW_INVALID")
    if (
        refresh_reminders is not None
        and type(refresh_reminders) is not K5RefreshReminderSnapshot
    ):
        raise TypeError("NATIVE_OPPORTUNITIES_REFRESH_REMINDERS_INVALID")
    body = _analysis_run_strip(snapshot)
    if discovery is None:
        body += (
            '<div class="global-empty"><strong>Native Discovery unavailable</strong><br>'
            'Run Swing Analysis to publish a successful Native opportunity population. '
            'Legacy Layer-1 evidence is not substituted.</div>'
        )
    else:
        counts = {
            state: sum(item.status is state for item in discovery.assessments)
            for state in NativeDiscoveryStatus
        }
        probables = tuple(
            item for item in discovery.assessments
            if item.status is NativeDiscoveryStatus.PROBABLE
        )
        body += _native_opportunity_metrics(counts)
        if not probables:
            body += (
                '<div class="global-empty">No Native Probables were found in the '
                'current successful analysis.</div>'
            )
        equities = tuple(
            item for item in probables if item.product_path is NativeProductPath.NSE
        )
        commodities = tuple(
            item for item in probables if item.product_path is NativeProductPath.MCX
        )
        body += '<div class="panels">'
        body += _native_opportunity_panel(
            "EQUITIES + INDICES", equities, review, progression, visual_v3,
            trade_windows, refresh_reminders,
        )
        body += _native_opportunity_panel(
            "COMMODITIES", commodities, review, progression, visual_v3,
            trade_windows, refresh_reminders,
        )
        body += "</div>"
    return _page(
        title="Swing Opportunities",
        subtitle="Current successful KRONOS Native Discovery opportunities.",
        snapshot=snapshot,
        active_nav="Swing",
        active_tab="Opportunities",
        body=body,
        swing_projection_revision=projection_revision,
    )


def render_legacy_opportunities(snapshot: BrowserWorkspaceSnapshot) -> str:
    """Render preserved Layer-1 evidence on a clearly historical surface."""

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
        title="Layer-1 History",
        subtitle="Historical Swing V1 Layer-1 validation evidence; not the current Native opportunity population.",
        snapshot=snapshot,
        active_nav="Swing",
        active_tab="Layer-1 History",
        body=body,
    )


def _native_opportunity_metrics(counts: dict[NativeDiscoveryStatus, int]) -> str:
    return (
        '<div class="status-strip">'
        f'<div class="status-item status-top"><span>PROBABLE</span><strong>{counts[NativeDiscoveryStatus.PROBABLE]}</strong></div>'
        f'<div class="status-item"><span>FORMING / WATCH</span><strong>{counts[NativeDiscoveryStatus.FORMING_WATCH]}</strong></div>'
        f'<div class="status-item"><span>NO CURRENT OPPORTUNITY</span><strong>{counts[NativeDiscoveryStatus.NO_CURRENT_OPPORTUNITY]}</strong></div>'
        f'<div class="status-item"><span>UNAVAILABLE</span><strong>{counts[NativeDiscoveryStatus.UNAVAILABLE]}</strong></div>'
        '</div>'
    )


def _native_opportunity_panel(
    title, probables, review, progression=None, visual_v3=(), trade_windows=(),
    refresh_reminders=None,
) -> str:  # type: ignore[no-untyped-def]
    cards = "".join(
        _native_opportunity_card(
            item, review, progression, visual_v3, trade_windows, refresh_reminders
        )
        for item in probables
    )
    if not cards:
        cards = (
            '<div class="empty"><div><strong>No Native Probables</strong>'
            'No instrument in this market group currently has Native PROBABLE status.'
            '</div></div>'
        )
    return (
        '<section class="market-panel"><div class="panel-heading">'
        f'<h2>{escape(title)}</h2><span>{len(probables)} Native Probables</span>'
        f'</div>{cards}</section>'
    )


def _native_opportunity_card(
    item,
    review: NativeReviewWorkflowSnapshot | None,
    progression=None,
    visual_v3=(),
    trade_windows=(),
    refresh_reminders=None,
) -> str:  # type: ignore[no-untyped-def]
    review_run_identity = None if review is None else review.native_run_identity
    readiness_records = () if review is None else review.readiness_records
    outcomes = () if review is None else review.analysis_outcomes
    packages = () if review is None else review.chart_packages
    requirements = () if review is None else review.requirements
    visual_results = () if review is None else review.visual_v2_results
    readiness = next(
        (
            record for record in readiness_records
            if record.run_identity == item.run_identity
            and record.canonical_instrument == item.canonical_instrument
            and record.native_assessment_sha256 == item.result_sha256
        ),
        None,
    )
    outcome = next(
        (
            value for value in outcomes
            if review_run_identity == item.run_identity
            and value.canonical_instrument == item.canonical_instrument
        ),
        None,
    )
    package = next(
        (
            value for value in packages
            if value.binding.native_run_identity == item.run_identity
            and value.binding.native_assessment_sha256 == item.result_sha256
        ),
        None,
    )
    requirement = next(
        (
            value for value in requirements
            if value.native_run_identity == item.run_identity
            and value.canonical_instrument == item.canonical_instrument
            and value.thesis.native_assessment_sha256 == item.result_sha256
        ),
        None,
    )
    bound_visual = tuple(
        value for value in visual_results
        if value.native_run_identity == item.run_identity
        and value.native_canonical_instrument == item.canonical_instrument
        and value.native_assessment_sha256 == item.result_sha256
    )
    sponsor_readiness = (
        present_native_readiness(readiness, requirement, bound_visual)
        if readiness is not None and requirement is not None else None
    )
    v3 = next((
        value for value in visual_v3
        if value.run_identity == item.run_identity
        and value.canonical_instrument == item.canonical_instrument
        and value.native_assessment_sha256 == item.result_sha256
    ), None)
    trade_window = next((
        value for value in trade_windows
        if value.native_run_identity == item.run_identity
        and value.canonical_instrument == item.canonical_instrument
        and value.native_assessment_sha256 == item.result_sha256
    ), None)
    review_status = (
        v3.sponsor_status
        if v3 is not None
        else
        sponsor_readiness.status
        if sponsor_readiness is not None
        else outcome.state.value.replace("_", " ")
        if outcome is not None
        else "CHART RECEIVED"
        if package is not None and not package.missing_required_timeframes
        else "REVIEW REQUIRED"
    )
    context = " · ".join((
        f"1W {item.weekly_state.value}",
        f"1D {item.daily_state.value}",
        f"4H {item.four_hour_state.value}",
        f"1H {item.one_hour_state.value}",
    )).replace("_", " ")
    direction = item.direction.value
    missing = (
        '<small class="missing-evidence">Missing evidence: <strong>'
        + escape(" · ".join(sponsor_readiness.missing_evidence))
        + '</strong></small>'
        if v3 is None
        and sponsor_readiness is not None and sponsor_readiness.missing_evidence
        else ""
    )
    progression_items = (
        () if progression is None else progression.for_instrument(item.canonical_instrument)
    )
    outstanding = sum(
        value.state is not ProgressionRequirementState.SATISFIED
        for value in progression_items
    )
    watchable = sum(
        value.state in {
            ProgressionRequirementState.WATCH_AVAILABLE,
            ProgressionRequirementState.WATCH_ACTIVE,
        }
        for value in progression_items
    )
    progression_summary = (
        '<small class="progression-summary">Requirements to progress · <strong>'
        + str(outstanding) + ' outstanding · ' + str(watchable)
        + ' watchable</strong></small>'
        if progression_items and (outstanding or watchable) and (
            v3 is None or v3.kr370 is None
        ) else ""
    )
    active_watch_summary = "".join(
        '<small class="progression-summary"><strong>WATCHING · '
        + escape(value.condition_identity.replace("_", " "))
        + '</strong> · LIVE MONITORING ACTIVE</small>'
        for value in progression_items
        if value.state is ProgressionRequirementState.WATCH_ACTIVE
    )
    kr370_summary = (
        "" if v3 is None or v3.kr370 is None
        else _kr370_opportunity_summary(
            v3.kr370,
            None if refresh_reminders is None else refresh_reminders.for_instrument(
                item.run_identity, item.canonical_instrument
            ),
        )
    )
    kr370_state = None if v3 is None else v3.kr370
    state_value = (
        escape(review_status)
        if kr370_state is None else
        '<span class="kr370-state '
        + _kr370_state_class(kr370_state) + '">'
        + escape(_kr370_state_label(kr370_state)) + '</span>'
    )
    trade_window_action = (
        ""
        if trade_window is None
        or trade_window.kr370_classification not in {"BUY_NOW", "SELL_NOW"}
        else
        f'<a class="button" href="/swing/trade-window/{escape(item.run_identity)}/'
        f'{quote(item.canonical_instrument, safe="")}">Open Trade Window →</a>'
    )
    return (
        '<article class="opportunity native-opportunity"><div class="opp-head">'
        f'<div class="opp-identity"><h3>{escape(item.canonical_instrument)}</h3>'
        f'<span class="setup-family">{escape(item.opportunity_identity.value.replace("_", " "))}</span></div>'
        f'<span class="direction direction-{escape(direction.lower())}">{escape(direction)}</span>'
        '</div><p class="summary-reason">' + escape(context) + '</p>'
        '<div class="summary-footer"><span class="summary-rr">'
        + ('KR-370' if v3 is not None and v3.kr370 is not None
           else 'Chart / reference status' if v3 is not None else 'Review')
        + ' · <strong>'
        + state_value + '</strong>' + missing + progression_summary
        + active_watch_summary + kr370_summary + '</span>'
        '<span class="native-opportunity-actions"><a class="button" href="/swing/v1-review">Open Native Review →</a>'
        f'<a class="button" href="/swing/analysis-details/{escape(item.run_identity)}/'
        f'{quote(item.canonical_instrument, safe="")}">View Analysis Details →</a>'
        + trade_window_action + '</span>'
        '</div></article>'
    )


def _kr370_opportunity_summary(value, reminder=None) -> str:  # type: ignore[no-untyped-def]
    state = _kr370_state_label(value)
    if value.not_evaluable_reason is not None:
        return '<small class="kr370-card-line">Required evidence is unavailable</small>'
    if state == "NO SETUP":
        return (
            '<small class="kr370-card-line">'
            + escape(_kr370_no_setup_reason(value.hard_gate_reason)) + '</small>'
        )
    if value.all_criteria_satisfied:
        return (
            '<small class="kr370-card-line"><strong>'
            'ALL PROMOTION CRITERIA SATISFIED</strong></small>'
        )
    remaining = len(value.missing_criteria)
    count = (
        '<small class="kr370-card-line"><strong>' + str(remaining)
        + (' CRITERION' if remaining == 1 else ' CRITERIA')
        + ' REMAINING</strong></small>'
    )
    missing = " · ".join(
        _kr370_criterion_name(item) for item in value.missing_criteria
    )
    waiting = (
        "Waiting for: " + missing if state in {"BUY READY", "SELL READY"}
        else "Missing: " + missing
    )
    condition = (
        ""
        if value.next_promotion_condition is None
        else '<small class="kr370-card-line">Next exact condition: <strong>'
        + escape(value.next_promotion_condition) + '</strong></small>'
    )
    alert = (
        '<small class="kr370-card-line"><strong>'
        'REFRESH ANALYSIS AFTER NEXT COMPLETED 1H</strong></small>'
        if value.watchability == "No Automated Alert Available"
        and tuple(value.missing_criteria) == ("K5 NON EXTENSION",)
        else '<small class="kr370-card-line"><strong>NO AUTOMATED ALERT AVAILABLE</strong></small>'
        if value.watchability == "No Automated Alert Available"
        else ""
    )
    reminder_state = ""
    if reminder is not None:
        label = (
            "REMINDER SET"
            if reminder.state is RefreshReminderState.PENDING
            else "REMINDER SENT"
        )
        reminder_state = (
            '<small class="kr370-card-line"><strong>' + label + ' · '
            + reminder.next_eligible_completed_1h_boundary.astimezone(_KOLKATA).strftime(
                "%d %b %H:%M IST"
            ).upper() + '</strong></small>'
        )
    return (
        count + '<small class="kr370-card-line">' + escape(waiting) + '</small>'
        + condition + alert + reminder_state
    )


def _kr370_state_label(value) -> str:  # type: ignore[no-untyped-def]
    if value.not_evaluable_reason is not None:
        return "NOT EVALUABLE"
    return value.classification.partition(" — ")[0]


def _kr370_state_class(value) -> str:  # type: ignore[no-untyped-def]
    label = _kr370_state_label(value)
    if label in {"BUY NOW", "SELL NOW"}:
        return "kr370-state-now"
    if label in {"BUY READY", "SELL READY"}:
        return "kr370-state-ready"
    if label in {"POTENTIAL BUY SETUP", "POTENTIAL SELL SETUP"}:
        return "kr370-state-potential"
    if label == "NO SETUP":
        return "kr370-state-no-setup"
    return "kr370-state-unavailable"


def _kr370_criterion_name(value: str) -> str:
    return {
        "K1 1H DIRECTIONAL PROGRESSION": "1H Progression",
        "K2 1H CPR ACCEPTANCE": "1H CPR Clearance",
        "K3 IMMEDIATE PATH CLEARANCE": "Path Clearance",
        "K4 SETUP QUALITY": "Setup Quality",
        "K5 NON EXTENSION": "Extension",
    }.get(value, "Governed Criterion")


def _kr370_no_setup_reason(value: str | None) -> str:
    return {
        "V3 1 1H MESSY CHOPPY": "Messy/choppy 1H price action",
        "AFFIRMATIVE GOVERNED DIRECTIONAL CONFLICT":
            "Conflicting 1H directional evidence",
        "NATIVE THESIS INVALIDATED OR STRUCTURAL FAILURE":
            "Native thesis invalidated or structure failed",
        "NSE WEEKLY OPPOSING": "Weekly context opposes the setup",
        "NSE WEEKLY UNAVAILABLE MANDATORY": "Required weekly context is unavailable",
        "INVALID EXACT EVIDENCE BINDING": "Current governed evidence could not be bound",
    }.get((value or "").upper(), "Current KR-370 criteria do not establish a setup")


def _relative_context_review(
    record: RelativeContextRecord | None, direction: str
) -> str:
    if record is None or (
        record.applicability is RelativeContextApplicability.NOT_APPLICABLE
    ):
        return ""
    values = []
    for fact in record.horizons:
        if fact.relative_state is RelativeContextState.UNAVAILABLE:
            values.append(
                f"{fact.timeframe.value} UNAVAILABLE · "
                + " · ".join(item.value for item in fact.reason_codes)
            )
            continue
        interpretation = directional_relative_context(
            fact.relative_state, direction
        ).value.replace("_", " ")
        values.append(
            f"{fact.timeframe.value} {_signed_pct(fact.relative_return_pct)} · "
            f"{fact.relative_state.value} · {interpretation}"
        )
    return (
        '<div class="v1-context-row"><span>Relative strength vs NIFTY</span>'
        '<strong>' + "<br>".join(escape(value) for value in values)
        + '<br><small>SUPPORTING CONTEXT ONLY · NON-VETO</small></strong></div>'
    )


def _relative_context_details(
    record: RelativeContextRecord | None, direction: str
) -> str:
    if record is None:
        return ""
    if record.applicability is RelativeContextApplicability.NOT_APPLICABLE:
        reason = record.horizons[0].reason_codes[0].value.replace("_", " ")
        return (
            '<section class="analysis-section"><h2>RELATIVE STRENGTH VS NIFTY</h2>'
            '<p><strong>NOT APPLICABLE</strong> · ' + escape(reason) + '</p>'
            '<p class="technical">Supporting context only · no decision or trade authority.</p>'
            '</section>'
        )
    rows = ""
    for fact in record.horizons:
        if fact.relative_state is RelativeContextState.UNAVAILABLE:
            rows += (
                '<tr><td>' + escape(fact.timeframe.value)
                + '</td><td colspan="4">UNAVAILABLE · '
                + escape(" · ".join(item.value for item in fact.reason_codes))
                + '</td></tr>'
            )
            continue
        interpretation = directional_relative_context(
            fact.relative_state, direction
        ).value.replace("_", " ")
        rows += (
            '<tr><td>' + escape(fact.timeframe.value) + '</td><td>'
            + escape(_signed_pct(fact.stock_return_pct)) + '</td><td>'
            + escape(_signed_pct(fact.benchmark_return_pct)) + '</td><td>'
            + escape(_signed_pct(fact.relative_return_pct)) + '</td><td>'
            + escape(fact.relative_state.value + " · " + interpretation)
            + '</td></tr>'
        )
    return (
        '<section class="analysis-section"><h2>RELATIVE STRENGTH VS NIFTY</h2>'
        '<table class="analysis-table"><thead><tr><th>Horizon</th><th>Stock return</th>'
        '<th>NIFTY return</th><th>Relative return</th><th>State</th></tr></thead><tbody>'
        + rows + '</tbody></table><p class="technical">SUPPORTING CONTEXT ONLY · '
        'NON-VETO · NO DISCOVERY, READINESS, TRADE OR EXECUTION AUTHORITY.</p></section>'
    )


def _signed_pct(value: float | None) -> str:
    return "UNAVAILABLE" if value is None else f"{value:+.2f}%"


def render_native_analysis_details(
    snapshot: BrowserWorkspaceSnapshot,
    details: NativeAnalysisDetailsProjection,
    progression: SwingProgressionWatchSnapshot | None = None,
    visual_v3: V3SponsorEvidencePresentation | None = None,
    trade_window: NativeTradeWindowProjection | None = None,
    mcx_context: McxSupportingContextRecord | None = None,
    relative_context: RelativeContextRecord | None = None,
) -> str:
    """Render governed evidence without recalculation or authority."""

    if relative_context is not None and (
        type(relative_context) is not RelativeContextRecord
        or relative_context.run_identity != details.assessment.run_identity
        or relative_context.canonical_instrument
        != details.assessment.canonical_instrument
    ):
        raise ValueError("NATIVE_ANALYSIS_DETAILS_RELATIVE_CONTEXT_BINDING_INVALID")

    if visual_v3 is not None:
        if (
            type(visual_v3) is not V3SponsorEvidencePresentation
            or visual_v3.run_identity != details.assessment.run_identity
            or visual_v3.canonical_instrument
            != details.assessment.canonical_instrument
            or visual_v3.native_assessment_sha256
            != details.assessment.result_sha256
        ):
            raise ValueError("NATIVE_ANALYSIS_DETAILS_V3_BINDING_INVALID")
        return _render_native_analysis_details_v3(
            snapshot, details, progression, visual_v3, trade_window, mcx_context,
            relative_context,
        )

    item = details.assessment
    thesis = details.requirement.thesis
    native_facts = [
        ("Instrument", item.canonical_instrument),
        ("Direction", item.direction.value),
        ("Opportunity", item.opportunity_identity.value.replace("_", " ")),
        ("1W context", item.weekly_state.value.replace("_", " ")),
        ("1D regime", item.daily_state.value.replace("_", " ")),
        ("4H opportunity", item.four_hour_state.value.replace("_", " ")),
        ("1H progression", item.one_hour_state.value.replace("_", " ")),
        ("Operative anchor", f"{thesis.operative_anchor_identity} · {thesis.operative_anchor_price:g}"),
        ("Why PROBABLE", " · ".join(code.replace("_", " ") for code in item.reason_codes)),
    ]
    native_facts.extend((name.replace("_", " "), f"{value:g}") for name, value in item.factual_levels)
    native_facts.extend(
        (
            f"{name.replace('_', ' ')} volume",
            f"current {current} · prior-20 mean {mean:g}"
            if mean is not None else f"current {current} · prior-20 mean unavailable",
        )
        for name, current, mean in item.volume_facts
    )
    visual_rows = "".join(
        '<tr><td>' + escape(result.timeframe.value) + '</td><td>'
        + escape(observation.question_id.value) + '</td><td>'
        + escape(observation.observation_status.value) + '</td><td>'
        + escape(observation.observation) + '</td><td>'
        + escape(_visual_level(observation)) + '</td></tr>'
        for result in details.visual_v2_results
        for observation in result.observations
    ) or '<tr><td colspan="5">Governed Visual V2 evidence is not yet available.</td></tr>'
    layer2 = details.layer2_record
    readiness = details.readiness_record
    if layer2 is None and readiness is None:
        reconciliation = '<p>Deterministic Layer-2 reconciliation is not yet available.</p>'
    elif layer2 is None:
        conditions = readiness.conditions
        reconciliation = (
            '<p><strong>PERSISTED READINESS CONDITIONS</strong></p>'
            f'<p>Thesis intact: {escape(conditions.thesis_intact.value.replace("_", " "))} · '
            f'Evidence completeness: {escape(conditions.evidence_completeness.value.replace("_", " "))}</p>'
            f'<p>Pullback: {escape(conditions.pullback_condition.value.replace("_", " "))} · '
            f'Retest: {escape(conditions.retest_condition.value.replace("_", " "))} · '
            f'Obstacle: {escape(conditions.obstacle_condition.value.replace("_", " "))} · '
            f'Deterioration: {escape(conditions.deterioration_condition.value.replace("_", " "))} · '
            f'Failure: {escape(conditions.failure_condition.value.replace("_", " "))}</p>'
        )
    else:
        states = " · ".join(
            f"{timeframe.value} {state.value.replace('_', ' ')}"
            for timeframe, state in layer2.evidence.timeframe_states
        )
        reconciliation = (
            f'<p><strong>{escape(layer2.reconciliation.value.replace("_", " "))}</strong></p>'
            f'<p>{escape(states)}</p><p>Thesis intact: {"YES" if layer2.native_thesis_unchanged else "NO"}</p>'
            f'<p>Material unresolved evidence: {escape(" · ".join(layer2.contradictions) or "NONE")}</p>'
        )
    if readiness is None:
        decision = "REVIEW REQUIRED"
        reason = "No persisted Readiness decision is available for this evidence cycle."
        next_step = "Candidate remains stopped until the governed Review cycle establishes a Readiness decision."
    else:
        sponsor_readiness = present_native_readiness(
            readiness, details.requirement, details.visual_v2_results
        )
        decision = sponsor_readiness.status
        reason = readiness.primary_reason.replace("_", " ")
        next_step = _governed_next_step(readiness.readiness.value)
    review_pack = details.review_pack_record
    technical = [
        ("Native run", item.run_identity),
        ("Native assessment", item.result_sha256),
        ("Analysis boundary", item.factual_boundaries[-1][1].isoformat() if item.factual_boundaries else "UNAVAILABLE"),
        ("Review Pack", review_pack.review_pack_id if review_pack else "NOT CREATED"),
        ("Review observation boundary", review_pack.observation_boundary.isoformat() if review_pack else "UNAVAILABLE"),
        ("Chart revisions", " · ".join(result.chart_revision_sha256 for result in details.visual_v2_results) or "NOT RECEIVED"),
        ("Evidence hashes", " · ".join(result.evidence_sha256 for result in details.visual_v2_results) or "NOT ANALYZED"),
        ("Provider", " · ".join(item.provider_provenance)),
        ("Native policy", f"{item.policy_identity} {item.policy_version}"),
        ("Visual V2", f"{details.visual_v2_results[0].question_set_identity} {details.visual_v2_results[0].question_set_version}" if details.visual_v2_results else "NOT ANALYZED"),
        ("Readiness policy", f"{readiness.readiness_policy_identity} {readiness.readiness_policy_version}" if readiness else "NOT AVAILABLE"),
        ("Internal readiness", readiness.readiness.value if readiness else "NOT AVAILABLE"),
        (
            "Detailed blockers",
            " · ".join(sponsor_readiness.blocker_details)
            if readiness is not None and sponsor_readiness.blocker_details
            else "NONE",
        ),
    ]
    body = (
        '<p><a class="button" href="/swing/opportunities">← Back to Opportunities</a></p>'
        '<div class="analysis-details">'
        + _analysis_disclosure("A. WHAT KITE / NATIVE DISCOVERY SAYS", native_facts)
        + _relative_context_details(relative_context, item.direction.value)
        + '<details class="analysis-section"><summary>B. WHAT THE TRADINGVIEW CHART / CHART ANALYST SAYS</summary>'
        '<table class="analysis-table"><thead><tr><th>Timeframe</th><th>Question</th><th>Status</th><th>Observation</th><th>Level</th></tr></thead><tbody>'
        + visual_rows + '</tbody></table></details>'
        + '<section class="analysis-section"><h2>C. WHAT KRONOS RECONCILED</h2>' + reconciliation + '</section>'
        + '<section class="analysis-section"><h2>D. CURRENT DECISION</h2><div class="analysis-decision">'
        + escape(decision) + '</div>'
        + (
            '<p class="missing-evidence">Missing evidence: <strong>'
            + escape(" · ".join(sponsor_readiness.missing_evidence))
            + '</strong></p>'
            if readiness is not None and sponsor_readiness.missing_evidence else ""
        )
        + '<p>' + escape(reason) + '</p></section>'
        + _progression_requirements_section(item.canonical_instrument, progression)
        + '<section class="analysis-section analysis-next"><h2>F. WHAT HAPPENS NEXT</h2><p>' + escape(next_step) + '</p></section>'
        + _mcx_context_details(item.canonical_instrument, mcx_context)
        + '<details class="analysis-section"><summary>G. TECHNICAL EVIDENCE</summary><div class="analysis-facts">'
        + _analysis_fact_rows(technical) + '</div></details></div>'
    )
    return _page(
        title=f"{item.canonical_instrument} Analysis Details",
        subtitle="Governed evidence chain for the current immutable Native analysis.",
        snapshot=snapshot,
        active_nav="Swing",
        active_tab="Opportunities",
        body=body,
    )


def _render_native_analysis_details_v3(
    snapshot: BrowserWorkspaceSnapshot,
    details: NativeAnalysisDetailsProjection,
    progression: SwingProgressionWatchSnapshot | None,
    visual_v3: V3SponsorEvidencePresentation,
    trade_window: NativeTradeWindowProjection | None,
    mcx_context: McxSupportingContextRecord | None,
    relative_context: RelativeContextRecord | None,
) -> str:
    item = details.assessment
    thesis = details.requirement.thesis
    native_facts = [
        ("Instrument", item.canonical_instrument),
        ("Direction", item.direction.value),
        ("Opportunity", item.opportunity_identity.value.replace("_", " ")),
        ("1W context", item.weekly_state.value.replace("_", " ")),
        ("1D regime", item.daily_state.value.replace("_", " ")),
        ("4H opportunity", item.four_hour_state.value.replace("_", " ")),
        ("1H progression", item.one_hour_state.value.replace("_", " ")),
        ("Operative anchor", f"{thesis.operative_anchor_identity} · {_sponsor_price(thesis.operative_anchor_price)}"),
        ("Why probable", " · ".join(code.replace("_", " ") for code in item.reason_codes)),
    ]
    visual_rows = "".join(
        '<tr><td>' + escape(value.timeframe) + '</td><td>CPR relationship</td><td>'
        + escape(value.cpr_observation) + '</td></tr>'
        + '<tr><td>' + escape(value.timeframe) + '</td><td>Reference interaction</td><td>'
        + escape(value.reference_observation) + '</td></tr>'
        + '<tr><td>' + escape(value.timeframe) + '</td><td>Nearby technical structures</td><td>'
        + escape(value.clustering_observation) + (
            ' Components: ' + escape(" · ".join(value.clustering_components))
            if value.clustering_components else ""
        ) + '</td></tr>'
        for value in visual_v3.visual_facts
    )
    reconciled = "".join(_v3_timeframe_reconciliation(
        machine, visual_v3.visual_for(machine.timeframe)
    ) for machine in visual_v3.machine_facts)
    technical = [
        ("Native run", visual_v3.run_identity),
        ("Native assessment", visual_v3.native_assessment_sha256),
        ("Analysis boundary", details.assessment.factual_boundaries[-1][1].isoformat() if details.assessment.factual_boundaries else "UNAVAILABLE"),
        ("Review Pack", visual_v3.review_pack_identity or "NOT CREATED"),
        ("Visual question set", f"{visual_v3.question_set_identity} {visual_v3.question_set_version}"),
        ("Machine-fact contract", REFERENCE_MACHINE_FACT_SCHEMA),
        ("Reference policy", f"{REFERENCE_POLICY_IDENTITY} {REFERENCE_POLICY_VERSION}"),
        ("Calculation policy", f"{CPR_CALCULATION_POLICY_IDENTITY} {CPR_CALCULATION_POLICY_VERSION}"),
        ("Machine fact identities", " · ".join(value.integrity_sha256 for value in visual_v3.machine_facts)),
        ("Visual evidence identities", " · ".join(value.evidence_sha256 for value in visual_v3.visual_facts)),
        ("Readiness identity", visual_v3.readiness_identity),
        ("Internal readiness", visual_v3.readiness),
        ("Reference-period identities", " · ".join(f"{value.timeframe} {value.reference_period_identity}" for value in visual_v3.machine_facts)),
        ("Watch identities", _watch_identities(item.canonical_instrument, progression)),
    ]
    promotion = visual_v3.kr370
    kr370_summary = ""
    kr370_audit = ""
    if promotion is not None:
        summary = [
            ("Classification", promotion.classification),
            ("Direction", promotion.direction),
            ("K score", promotion.score),
            ("Missing criteria", " · ".join(promotion.missing_criteria) or "NONE"),
            ("Hard gate", promotion.hard_gate_reason or "NONE"),
            ("Evidence status", promotion.not_evaluable_reason or "EVALUABLE"),
            ("Next exact promotion condition", promotion.next_promotion_condition or "NONE"),
            ("Watch state", promotion.watchability),
        ]
        kr370_summary = (
            '<section class="analysis-section"><h2>KR-370 ANALYTICAL PROMOTION</h2>'
            '<div class="analysis-decision kr370-state '
            + _kr370_state_class(promotion) + '">'
            + escape(_kr370_state_label(promotion))
            + '</div><div class="analysis-facts">'
            + _analysis_fact_rows(summary) + '</div>'
            + (
                '<p><strong>ALL KR-370 PROMOTION CRITERIA SATISFIED</strong></p>'
                if promotion.all_criteria_satisfied else ""
            )
            + '</section>'
        )
        kr370_audit = (
            '<h3>KR-370 criterion audit</h3><table class="analysis-table">'
            '<thead><tr><th>Criterion</th><th>State</th><th>Reason</th></tr></thead><tbody>'
            + ''.join(
                '<tr><td>' + escape(name) + '</td><td>' + escape(state)
                + '</td><td>' + escape(reason) + '</td></tr>'
                for name, state, reason in promotion.criteria
            ) + '</tbody></table>'
        )
        technical.append(("KR-370 promotion identity", promotion.integrity_sha256))
    trade_window_summary = ""
    if trade_window is not None:
        trade_window_summary = (
            '<section class="analysis-section"><h2>STEP-31 / TRADE WINDOW</h2>'
            '<div class="analysis-facts">'
            + _analysis_fact_rows([
                ("Handoff status", trade_window.state.value.replace("_", " ")),
                ("Trade record", (
                    trade_window.trade_plan.trade_plan_id
                    if trade_window.trade_plan is not None else "NOT AVAILABLE"
                )),
                ("Risk", trade_window.risk_state.replace("_", " ")),
                ("Entry timing", trade_window.kr380_entry_timing_state),
            ]) + '</div>'
            + (
                '<p><a class="button" href="/swing/trade-window/'
                + escape(trade_window.native_run_identity) + '/'
                + quote(trade_window.canonical_instrument, safe="")
                + '">Open Trade Window →</a></p>'
                if trade_window.kr370_classification in {"BUY_NOW", "SELL_NOW"}
                else ""
            ) + '</section>'
        )
    body = (
        '<p><a class="button" href="/swing/opportunities">← Back to Opportunities</a></p>'
        '<div class="analysis-details">'
        + kr370_summary
        + trade_window_summary
        + _analysis_disclosure("A. WHAT KITE / NATIVE DISCOVERY SAYS", native_facts)
        + _relative_context_details(relative_context, item.direction.value)
        + '<details class="analysis-section"><summary>B. WHAT THE TRADINGVIEW CHART / CHART ANALYST SAYS</summary>'
        '<p class="technical">Independent chart observations; KRONOS numerical facts are shown separately.</p>'
        '<table class="analysis-table"><thead><tr><th>Timeframe</th><th>Observation</th><th>Chart Analyst evidence</th></tr></thead><tbody>'
        + visual_rows + '</tbody></table></details>'
        + '<section class="analysis-section"><h2>C. WHAT KRONOS RECONCILED</h2>'
        '<p class="technical">KRONOS numerical facts and independent chart observations retain separate authority.</p>'
        + reconciled + '</section>'
        + '<section class="analysis-section"><h2>D. CURRENT DECISION</h2>'
        '<div class="analysis-decision">' + escape(visual_v3.sponsor_status) + '</div>'
        '<p>' + escape(visual_v3.readiness_reason) + '</p></section>'
        + _progression_requirements_section(
            item.canonical_instrument, progression,
            hide_satisfied=promotion is not None,
            promotion_complete=(
                promotion is not None and promotion.all_criteria_satisfied
            ),
        )
        + '<section class="analysis-section analysis-next"><h2>F. WHAT HAPPENS NEXT</h2><p>'
        + escape(_v3_next_step(item.canonical_instrument, progression, visual_v3.next_step))
        + '</p></section>'
        + _mcx_context_details(item.canonical_instrument, mcx_context)
        + '<details class="analysis-section"><summary>G. TECHNICAL EVIDENCE</summary><div class="analysis-facts">'
        + _analysis_fact_rows(technical) + '</div>' + kr370_audit
        + '</details></div>'
    )
    return _page(
        title=f"{item.canonical_instrument} Analysis Details",
        subtitle="Governed V3 evidence chain for the current immutable Native analysis.",
        snapshot=snapshot,
        active_nav="Swing",
        active_tab="Opportunities",
        body=body,
    )


_TRADE_WINDOW_CSS = r"""
.trade-window-shell{max-width:1440px;margin:0 auto}.trade-window-back{margin:0 0 12px}
.trade-window-grid{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(340px,.85fr);gap:14px;align-items:start}
.trade-window-column{display:grid;gap:10px}.trade-panel{background:linear-gradient(155deg,rgba(15,27,46,.96),rgba(8,16,29,.98));border:1px solid #263a55;border-radius:11px;padding:12px;box-shadow:0 10px 24px rgba(0,0,0,.18);font-size:.88rem}
.trade-panel h2{font-size:.72rem;letter-spacing:.13em;color:#8fa6c3;margin:0 0 9px}.trade-panel p{margin:7px 0;line-height:1.45}.trade-decision-head{display:flex;align-items:center;justify-content:space-between;gap:12px}.trade-instrument{font-size:1.22rem;margin:0;color:#f2f6fb}.trade-direction{font-size:.72rem;letter-spacing:.12em}.trade-direction.long{color:#63d59b}.trade-direction.short{color:#ff7e86}.trade-now{display:inline-flex;padding:6px 10px;border-radius:999px;font-weight:800;letter-spacing:.08em;font-size:.76rem;background:#102f27;color:#72e0a8;border:1px solid #277154}.trade-now.sell{background:#351a22;color:#ff969c;border-color:#7d3340}
.trade-semantics{color:#aebdd0;font-size:.8rem}.trade-math-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px}.trade-math{background:#0a1525;border:1px solid #223650;border-radius:8px;padding:8px;min-width:0}.trade-math span{display:block;color:#7890ad;font-size:.62rem;letter-spacing:.09em;text-transform:uppercase;margin-bottom:3px}.trade-math strong{font-size:.88rem;color:#edf4fc}.trade-math.adverse{border-color:#6b4650;background:#101826}.trade-math.adverse strong{color:#e7b2b7}
.trade-status-row{display:grid;grid-template-columns:1fr 1fr;gap:7px}.trade-status{background:#0a1525;border:1px solid #243751;border-radius:8px;padding:8px}.trade-status span{display:block;color:#7890ad;font-size:.62rem;letter-spacing:.09em;margin-bottom:4px}.trade-status strong{font-size:.78rem}.severity-green{border-color:#296a51}.severity-green strong{color:#71dba8}.severity-amber{border-color:#7a6026}.severity-amber strong{color:#f2c66f}.severity-muted{border-color:#4d5360}.severity-muted strong{color:#c3cad4}.severity-red{border-color:#9a3946;background:#27141a}.severity-red strong{color:#ff7f89}.trade-warning{border:1px solid #9a3946;background:linear-gradient(145deg,#31171e,#1b1117);border-radius:10px;padding:11px;margin-top:9px;color:#ffd5d8}.trade-warning-title{display:block;color:#ff7681;font-weight:900;letter-spacing:.1em;font-size:.76rem;margin-bottom:6px}.trade-warning ul{margin:5px 0 0;padding-left:20px}
.decision-cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px}.decision-card{display:flex;flex-direction:column;min-width:0;min-height:112px;border:1px solid #2d425f;background:#0b1728;border-radius:10px;padding:10px}.decision-card.paper{border-color:#4d55a9}.decision-card.live{border-color:#277154}.decision-card.ignore{border-color:#806125}.decision-card h3{font-size:.75rem;margin:0 0 5px;letter-spacing:.06em}.decision-card p{font-size:.74rem;color:#9fb0c5;flex:1}.decision-card select{box-sizing:border-box;min-width:0;width:100%}.decision-card .button{width:100%;margin-top:7px}.decision-card.live .button{background:#1e6a4d;border-color:#2b946d}.decision-card.ignore .button{background:#624c1e;border-color:#8e6c2b}.decision-explainer{font-size:.76rem;color:#9fb0c5}.trade-ack{display:flex;gap:7px;align-items:flex-start;font-size:.72rem;color:#ffd2d5;margin:7px 0}.trade-entry{border-color:#3c5578}.trade-entry-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px;margin:9px 0}.trade-entry label{display:block;font-size:.72rem;color:#9fb0c5}.trade-entry input,.trade-entry select{width:100%;box-sizing:border-box;margin-top:4px}.manual-boundary{border-left:3px solid #4c9c78;padding-left:9px;color:#b9d8ca;font-size:.78rem}.trade-context-grid{display:grid;grid-template-columns:1fr 1fr;gap:7px}.trade-context-grid div{background:#0a1525;border-radius:8px;padding:8px}.trade-context-grid span{display:block;color:#7890ad;font-size:.62rem;letter-spacing:.08em}.trade-context-grid strong{font-size:.77rem;word-break:break-word}.trade-next{border-color:#315a80}.trade-next strong{color:#85c8ff;letter-spacing:.04em}.trade-error{border-color:#9a3946;background:#2b151b}.trade-error h2,.trade-error strong{color:#ff8b94}.trade-blocked{border-color:#465369;background:#111b2a}.trade-blocked strong{color:#c3cbd7}.paper-observation-track{border-color:#4c64a9;background:linear-gradient(145deg,#111b35,#17152d)}.paper-observation-track h2,.paper-observation-track strong{color:#9ccaff}.paper-track-boundary{font-size:.74rem;color:#aeb8d7}.paper-track-boundary strong{color:#c7b4ff}.paper-track-confirm{color:#c7d8f2}.trade-compact-details summary{font-size:.72rem;letter-spacing:.08em;color:#8fa6c3;cursor:pointer}.trade-lifecycle-line{display:flex;justify-content:space-between;gap:12px;border-top:1px solid #20334b;padding:7px 0;font-size:.76rem}.trade-lifecycle-line:first-of-type{border-top:0}.trade-muted{color:#91a2b7}.trade-actions-recorded{border:1px solid #34506f;background:#0c1a2d;border-radius:9px;padding:10px}.trade-actions-recorded strong{color:#dbe9f8}.trade-panel .why{font-size:.76rem}
@media(max-width:980px){.trade-window-grid{grid-template-columns:1fr}.trade-math-grid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:620px){.decision-cards,.trade-entry-grid,.trade-status-row,.trade-context-grid{grid-template-columns:1fr}.trade-math-grid{grid-template-columns:1fr 1fr}.trade-decision-head{align-items:flex-start;flex-direction:column}}
"""


def render_native_trade_window(
    snapshot: BrowserWorkspaceSnapshot,
    projection: NativeTradeWindowProjection,
    *,
    workflow_error: tuple[str, str] | None = None,
) -> str:
    """Render a compact Sponsor Trade Window from persisted governed facts."""

    if type(projection) is not NativeTradeWindowProjection:
        raise TypeError("NATIVE_TRADE_WINDOW_PROJECTION_INVALID")
    if workflow_error is not None and (
        type(workflow_error) is not tuple
        or len(workflow_error) != 2
        or any(type(item) is not str or not item for item in workflow_error)
    ):
        raise TypeError("TRADE_WINDOW_WORKFLOW_ERROR_INVALID")

    plan = projection.trade_plan
    observation = projection.step31_observation
    attempt = projection.latest_construction_attempt
    attempt_failed = attempt is not None and attempt.result.value == "FAILED"
    heading = projection.kr370_classification.replace("_", " ")
    notice = (
        "Analytical promotion is complete. This is not an entry trigger or an order instruction."
        if projection.kr370_classification in {"BUY_NOW", "SELL_NOW"}
        else "Trade construction is not eligible for this analytical state."
    )

    warning_labels = {
        "TARGET_BELOW_ENTRY": "Target is at or below Entry for a LONG thesis.",
        "TARGET_ABOVE_ENTRY": "Target is at or above Entry for a SHORT thesis.",
        "NON_POSITIVE_REWARD": "Reward is zero or negative.",
        "NON_POSITIVE_RISK": "Risk geometry is zero or negative.",
        "RR_UNFAVOURABLE": "Risk/reward is unfavourable under governed policy.",
        "TARGET_UNAVAILABLE": "Target evidence is unavailable.",
        "STOP_UNAVAILABLE": "Stop evidence is unavailable.",
        "ENTRY_UNAVAILABLE": "Entry evidence is unavailable.",
        "STRUCTURAL_GEOMETRY_WARNING": "Structural invalidation evidence is incomplete.",
    }
    warning_codes = {
        item.value for item in observation.warnings
    } if observation is not None else set()

    def money(value: object) -> str:
        return "UNAVAILABLE" if value is None else "₹" + _number(value)

    if observation is not None:
        ratio = (
            "UNAVAILABLE"
            if observation.risk_reward_state.value == "UNAVAILABLE"
            else "INVALID"
            if observation.risk_reward_state.value == "INVALID"
            else "1 : " + _number(observation.risk_reward_ratio)
        )
        math_values = (
            ("Entry", money(observation.entry), "ENTRY_UNAVAILABLE"),
            ("Stop", money(observation.stop), "STOP_UNAVAILABLE"),
            ("Target", money(observation.canonical_target), "TARGET_UNAVAILABLE"),
            ("Invalidation", money(observation.invalidation_reference), "STRUCTURAL_GEOMETRY_WARNING"),
            ("Risk", money(observation.risk_per_unit), "NON_POSITIVE_RISK"),
            ("Reward", money(observation.reward_per_unit), "NON_POSITIVE_REWARD"),
            ("R:R", ratio, "RR_UNFAVOURABLE"),
        )
        mathematics = (
            '<section class="trade-panel"><h2>TRADE MATHEMATICS</h2>'
            + ('<p class="trade-muted">TRADE GEOMETRY AVAILABLE</p>' if plan is not None else '')
            + '<div class="trade-math-grid">'
            + ''.join(
                '<div class="trade-math'
                + (' adverse' if adverse in warning_codes or (
                    label == "Target" and warning_codes.intersection({
                        "TARGET_BELOW_ENTRY", "TARGET_ABOVE_ENTRY"
                    })
                ) else '')
                + '"><span>' + escape(label) + '</span><strong>'
                + escape(value) + '</strong></div>'
                for label, value, adverse in math_values
            )
            + '</div></section>'
        )
        severity = observation.severity.value.lower()
        warnings = (
            '<p class="trade-muted">No Step-31 geometry warnings.</p>'
            if not observation.warnings
            else '<div class="trade-warning"><span class="trade-warning-title">'
            + escape(
                "RED · COMPLETE WARNING"
                if observation.severity.value == "RED"
                else observation.severity.value + " · STEP-31 WARNING"
            )
            + '</span><ul>'
            + ''.join(
                '<li>' + escape(warning_labels[item.value]) + '</li>'
                for item in observation.warnings
            )
            + '</ul></div>'
        )
        assessment = (
            '<section class="trade-panel"><h2>STEP-31 ASSESSMENT</h2>'
            '<div class="trade-status-row"><div class="trade-status severity-'
            + escape(severity) + '"><span>WARNING SEVERITY</span><strong>'
            + escape(observation.severity.value) + '</strong></div>'
            '<div class="trade-status"><span>GEOMETRY STATUS</span><strong>'
            + escape(observation.geometry_status.value.replace("_", " "))
            + '</strong></div></div>' + warnings + '</section>'
        )
    elif plan is not None:
        mathematics = (
            '<section class="trade-panel"><h2>TRADE MATHEMATICS</h2>'
            '<p class="trade-muted">TRADE GEOMETRY AVAILABLE</p>'
            '<div class="trade-math-grid">'
            + ''.join(
                '<div class="trade-math"><span>' + escape(label)
                + '</span><strong>' + escape(value) + '</strong></div>'
                for label, value in (
                    ("Entry", money(plan.entry)), ("Stop", money(plan.stop)),
                    ("Target", money(plan.canonical_target)),
                    ("Invalidation", money(plan.invalidation_reference)),
                    ("R:R", "1 : " + _number(plan.risk_reward_ratio)),
                )
            ) + '</div></section>'
        )
        assessment = ''
    else:
        failure_code = attempt.safe_failure_code if attempt_failed else projection.reason
        failure_reason = attempt.safe_bounded_reason if attempt_failed else projection.reason.replace("_", " ")
        if failure_code == "KITE_READ_ONLY_CAPABILITY_UNAVAILABLE":
            failure_title = "KITE CONNECTION REQUIRED"
            failure_reason = "Connect Kite before constructing the Trade Plan."
        elif failure_code == "GEOMETRY_INVALID":
            failure_title = "GEOMETRY INVALID"
            failure_reason = "No valid governed trade geometry is available for this opportunity."
        else:
            failure_title = failure_code.replace("_", " ")
        retry = failure_code in {
            "GEOMETRY_INVALID", "STEP31_EVALUATION_NOT_COMPLETED",
            "KITE_READ_ONLY_CAPABILITY_UNAVAILABLE",
            "TRADE_PLAN_CONSTRUCTION_UNAVAILABLE",
        }
        mathematics = (
            '<section class="trade-panel trade-error"><h2>TRADE PLAN NOT CONSTRUCTED</h2>'
            '<strong>' + escape(failure_title) + '</strong><p>'
            + escape(failure_reason or "Trade Plan construction is unavailable.") + '</p>'
            + (
                '<p><strong>Stage</strong> · '
                + escape(attempt.stage.value.replace("_", " ")) + '</p>'
                if attempt_failed else ''
            )
            + (
                '<form method="post" action="/swing/trade-window/construct">'
                + ''.join(
                    '<input type="hidden" name="' + escape(name) + '" value="'
                    + escape(value) + '">'
                    for name, value in (
                        ("run_identity", projection.native_run_identity),
                        ("canonical_instrument", projection.canonical_instrument),
                        ("native_assessment_sha256", projection.native_assessment_sha256),
                    )
                )
                + '<button class="button primary" type="submit">'
                + ("EVALUATE TRADE MATHEMATICS" if failure_code == "GEOMETRY_INVALID" else "CONSTRUCT TRADE PLAN")
                + '</button></form>'
                if projection.kr370_classification in {"BUY_NOW", "SELL_NOW"} and retry
                else ''
            ) + '</section>'
        )
        assessment = ''

    decision_hidden = ''
    if observation is not None:
        decision_hidden = ''.join(
            '<input type="hidden" name="' + escape(name) + '" value="'
            + escape(value) + '">'
            for name, value in (
                ("run_identity", projection.native_run_identity),
                ("canonical_instrument", projection.canonical_instrument),
                ("native_assessment_sha256", projection.native_assessment_sha256),
                ("observation_evidence_id", observation.observation_evidence_id),
            )
        )
    reason_select = (
        '<label class="why">Optional reason <select name="reason">'
        '<option value="">NONE</option><option value="AGREE_WITH_KRONOS">AGREE WITH KRONOS</option>'
        '<option value="POOR_RR">POOR R:R</option><option value="STEP31_WARNING">STEP-31 WARNING</option>'
        '<option value="MARKET_CONTEXT">MARKET CONTEXT</option><option value="PERSONAL_RISK_LIMIT">PERSONAL RISK LIMIT</option>'
        '<option value="TESTING_SETUP">TESTING SETUP</option><option value="OTHER">OTHER</option>'
        '</select></label>'
    )

    controls = ''
    if observation is not None and projection.sponsor_observation_controls_available:
        red_ack = (
            '<label class="trade-ack"><input type="checkbox" name="warning_acknowledged" value="YES" required>'
            '<span>I acknowledge the RED Step-31 warning and choose this Sponsor observation decision.</span></label>'
            if observation.severity.value == "RED" else ''
        )
        cards = []
        for mode, css, explanation in (
            ("PAPER", "paper", "I will take this as a paper trade."),
            ("LIVE", "live", "I will take this as a live trade."),
            ("IGNORE", "ignore", "I choose to ignore this opportunity."),
        ):
            acknowledgement = red_ack if mode != "IGNORE" else ''
            cards.append(
                '<form class="decision-card ' + css + '" method="post" action="/swing/trade-window/observation-decision">'
                + decision_hidden + '<input type="hidden" name="mode" value="' + mode + '">'
                + '<h3>' + mode + (' TRADE' if mode != "IGNORE" else '') + '</h3><p>'
                + escape(explanation) + '</p>' + acknowledgement + reason_select
                + '<button class="button" type="submit">SELECT ' + mode + '</button></form>'
            )
        risk_warning = (
            '<p class="trade-warning"><strong>YOUR DECISION WILL BE RECORDED FOR OBSERVATION.</strong><br>'
            'POSITION ACTIVATION WILL REMAIN BLOCKED BY DOMAIN-007 RISK.</p>'
            if projection.risk_state in {"RISK_REJECTED", "RISK_UNAVAILABLE"}
            else ''
        )
        controls = (
            '<p class="decision-explainer">These controls record Sponsor judgment. '
            'They do not guarantee position activation.</p>'
            + risk_warning + '<div class="decision-cards">' + ''.join(cards) + '</div>'
        )
    elif observation is None and projection.sponsor_observation_decision_id is None:
        controls = '<p class="trade-muted">Trustworthy Step-31 evidence is required before a Sponsor observation decision.</p>'

    choice = projection.sponsor_observation_choice
    pending = projection.activation_disposition == "PENDING_ENTRY_CONFIRMATION"
    entry_workflow = ''
    if pending and choice in {"PAPER", "LIVE"} and plan is not None:
        activation_hidden = ''.join(
            '<input type="hidden" name="' + escape(name) + '" value="'
            + escape(value) + '">'
            for name, value in (
                ("run_identity", projection.native_run_identity),
                ("canonical_instrument", projection.canonical_instrument),
                ("native_assessment_sha256", projection.native_assessment_sha256),
                ("decision_identity", projection.sponsor_observation_decision_id or ''),
                ("mode", choice),
            )
        )
        entry_facts = (
            '<div class="trade-entry-grid">'
            + ''.join(
                '<div class="trade-math"><span>' + label + '</span><strong>' + escape(value) + '</strong></div>'
                for label, value in (
                    ("Direction", projection.direction), ("Planned Entry", money(plan.entry)),
                    ("Stop", money(plan.stop)), ("Target", money(plan.canonical_target)),
                    ("Risk", projection.risk_state.replace("_", " ")),
                    ("Step-31", observation.severity.value if observation is not None else "UNAVAILABLE"),
                )
            ) + '</div>'
        )
        if choice == "PAPER":
            fields = (
                '<div class="trade-status"><span>QUANTITY</span><strong>ONE LOT</strong></div>'
                '<label class="trade-ack"><input type="checkbox" name="entry_confirmed" value="YES" required>'
                '<span>Confirm one-lot PAPER activation. No broker fill, actual P&amp;L or actual R is manufactured.</span></label>'
            )
        else:
            fields = (
                '<p class="manual-boundary"><strong>MANUAL EXECUTION</strong><br>'
                'KRONOS records Sponsor-attested facts. KRONOS will not place, modify or cancel an order.</p>'
                '<div class="trade-entry-grid"><label>Sponsor actual entry'
                '<input name="actual_entry" inputmode="decimal" required></label>'
                '<label>Lots<input name="lots" inputmode="numeric" required></label></div>'
                '<label class="trade-ack"><input type="checkbox" name="manual_execution_confirmed" value="YES" required>'
                '<span>I confirm this LIVE entry was executed manually outside KRONOS broker authority.</span></label>'
            )
        entry_workflow = (
            '<section class="trade-panel trade-entry"><h2>' + choice + ' TRADE ENTRY</h2>'
            '<form method="post" action="/swing/trade-window/activate">'
            + activation_hidden + entry_facts + fields
            + '<button class="button primary" type="submit">CONFIRM ' + choice + ' ENTRY</button>'
            '</form></section>'
        )
    elif choice in {"PAPER", "LIVE"} and projection.activation_disposition.startswith("BLOCKED_"):
        entry_workflow = (
            ''
            if choice == "PAPER"
            else (
                '<section class="trade-panel trade-blocked"><h2>LIVE TRADE ENTRY</h2>'
                '<strong>NOT AVAILABLE</strong><p>POSITION ACTIVATION · BLOCKED</p><p>Reason · '
                + escape(projection.activation_reason.replace("_", " ")) + '</p></section>'
            )
        )

    track_hidden = ''.join(
        '<input type="hidden" name="' + escape(name) + '" value="'
        + escape(value) + '">'
        for name, value in (
            ("run_identity", projection.native_run_identity),
            ("canonical_instrument", projection.canonical_instrument),
            ("native_assessment_sha256", projection.native_assessment_sha256),
            ("decision_identity", projection.sponsor_observation_decision_id or ""),
        )
    )
    track_values = (
        '<div class="trade-status-row"><div class="trade-status"><span>ENTRY REFERENCE</span><strong>'
        + escape(money(projection.paper_observation_entry_reference))
        + '</strong></div><div class="trade-status"><span>ENTRY STATE</span><strong>'
        + escape(projection.paper_observation_entry_state.replace("_", " "))
        + '</strong></div></div><div class="trade-status-row"><div class="trade-status"><span>STOP</span><strong>'
        + escape(money(projection.paper_observation_stop))
        + '</strong></div><div class="trade-status"><span>TARGET</span><strong>'
        + escape(money(projection.paper_observation_target))
        + '</strong></div></div>'
    )
    if projection.paper_observation_track_start_available:
        paper_track = (
            '<section class="trade-panel paper-observation-track"><h2>PAPER OBSERVATION TRACK</h2>'
            '<strong>AVAILABLE</strong><p class="paper-track-boundary">Research-only factual path observation. '
            'This creates no Sponsor Position, Risk permission, fill, P&amp;L, actual R or broker instruction.</p>'
            + track_values
            + '<form method="post" action="/swing/trade-window/paper-observation/start">'
            + track_hidden
            + '<label class="trade-ack paper-track-confirm"><input type="checkbox" name="track_confirmed" value="YES" required>'
            '<span>Start a non-position PAPER Observation Track from this exact blocked decision and Step-31 geometry.</span></label>'
            '<button class="button primary" type="submit">START PAPER OBSERVATION</button>'
            '</form></section>'
        )
    elif projection.paper_observation_track_id is not None:
        observed = (
            "UNAVAILABLE"
            if projection.paper_observation_last_fact_at is None
            else projection.paper_observation_last_fact_at.astimezone(_KOLKATA).strftime(
                "%d %b %Y · %H:%M:%S IST"
            )
        )
        paper_track = (
            '<section class="trade-panel paper-observation-track"><h2>PAPER OBSERVATION TRACK</h2>'
            '<div class="trade-status-row"><div class="trade-status"><span>TRACK</span><strong>'
            + escape(projection.paper_observation_track_state.replace("_", " "))
            + '</strong></div><div class="trade-status"><span>MONITORING</span><strong>'
            + escape(projection.paper_observation_monitoring_state.replace("_", " "))
            + '</strong></div></div>' + track_values
            + '<div class="trade-status"><span>FACTUAL OUTCOME</span><strong>'
            + escape(projection.paper_observation_outcome_state.replace("_", " "))
            + '</strong></div><p class="paper-track-boundary"><strong>Research evidence only.</strong> '
            'No position, order, fill, P&amp;L or actual R is created.<br>Last factual observation · '
            + escape(observed) + '<br>Monitoring · '
            + escape(projection.paper_observation_monitoring_reason.replace("_", " "))
            + '</p></section>'
        )
    elif projection.paper_observation_track_state == "NOT REQUIRED":
        paper_track = (
            '<section class="trade-panel paper-observation-track"><h2>PAPER OBSERVATION TRACK</h2>'
            '<strong>NOT REQUIRED</strong><p class="paper-track-boundary">A governed Sponsor Position was activated; '
            'a duplicate non-position Track is not created.</p></section>'
        )
    else:
        paper_track = ''

    sponsor = (
        '<section class="trade-panel"><h2>SPONSOR DECISION</h2>'
        '<div class="trade-actions-recorded"><strong>'
        + escape(projection.sponsor_observation_decision_state)
        + '</strong><p class="decision-explainer">Decision is recorded as an OBSERVATION. '
        'It does not by itself activate a position.</p></div>'
        + controls + '</section>'
    )
    activation = (
        '<section class="trade-panel'
        + (' trade-blocked' if projection.activation_disposition.startswith("BLOCKED_") else '')
        + '"><h2>POSITION ACTIVATION</h2>'
        '<div class="trade-status-row"><div class="trade-status"><span>DISPOSITION</span><strong>'
        + escape(projection.activation_disposition.replace("_", " "))
        + '</strong></div><div class="trade-status"><span>SPONSOR POSITION</span><strong>'
        + escape(projection.sponsor_position_state.replace("_", " "))
        + '</strong></div></div><p class="why">Reason · '
        + escape(projection.activation_reason.replace("_", " "))
        + '</p><div class="trade-status"><span>MONITORING</span><strong>'
        + escape(projection.sponsor_monitoring_state) + '</strong></div></section>'
    )

    risk_class = "severity-green" if projection.risk_state == "RISK_APPROVED" else "severity-muted" if projection.risk_state in {"RISK_REJECTED", "RISK_UNAVAILABLE"} else "severity-amber"
    risk = (
        '<section class="trade-panel"><h2>RISK</h2><div class="trade-status ' + risk_class
        + '"><span>RISK STATUS</span><strong>' + escape(projection.risk_state.replace("_", " "))
        + '</strong></div><p class="why"><strong>Reason</strong> · '
        + escape(projection.risk_reason.replace("_", " "))
        + '<br><strong>Position activation</strong> · '
        + escape("PERMITTED" if projection.risk_state == "RISK_APPROVED" else "BLOCKED")
        + '</p></section>'
    )
    timing_label = {
        "NO_TRIGGER": "WAITING FOR ENTRY TRIGGER",
        "LONG_ENTRY_TRIGGERED": "ENTRY TRIGGERED — LONG",
        "SHORT_ENTRY_TRIGGERED": "ENTRY TRIGGERED — SHORT",
    }.get(projection.kr380_entry_timing_state, projection.kr380_entry_timing_state.replace("_", " "))
    timing_model = (
        '<section class="trade-panel"><h2>ENTRY TIMING &amp; MODEL</h2>'
        '<div class="trade-lifecycle-line"><span>KR-380 ENTRY TIMING</span><strong>'
        + escape(timing_label) + '</strong></div>'
        '<div class="trade-lifecycle-line"><span>OBJECTIVE MODEL</span><strong>'
        + escape(projection.model_lifecycle_state.replace("_", " ")) + '</strong></div>'
        '<p class="why">Objective model state is separate from Sponsor judgment and position ownership.</p></section>'
    )

    if projection.sponsor_observation_decision_id is None:
        next_step = "SPONSOR OBSERVATION DECISION REQUIRED."
    elif pending:
        next_step = "CONFIRM " + (choice or "SPONSOR") + " TRADE ENTRY."
    elif projection.activation_disposition.startswith("BLOCKED_"):
        next_step = (
            "START PAPER OBSERVATION TRACK OR RETAIN THE BLOCKED DECISION."
            if projection.paper_observation_track_start_available
            else "MONITOR PAPER OBSERVATION TRACK."
            if projection.paper_observation_track_id is not None
            else (choice or "SPONSOR") + " DECISION RECORDED · ACTIVATION BLOCKED."
        )
    elif choice == "IGNORE":
        next_step = "OPPORTUNITY IGNORED · OBJECTIVE OBSERVATION CONTINUES."
    elif projection.activation_disposition == "ACTIVATED":
        next_step = "MONITOR ACTIVE POSITION."
    else:
        next_step = "REVIEW CURRENT GOVERNED STATE."
    updated = (
        "UNAVAILABLE"
        if projection.last_updated_at is None
        else projection.last_updated_at.astimezone(_KOLKATA).strftime("%d %b %Y · %H:%M IST")
    )
    context = (
        '<section class="trade-panel"><h2>KEY CONTEXT</h2><div class="trade-context-grid">'
        + ''.join(
            '<div><span>' + escape(label) + '</span><strong>' + escape(value) + '</strong></div>'
            for label, value in (
                ("Run", projection.native_run_identity[-12:]),
                ("Review", "CURRENT NATIVE REVIEW"),
                ("KR-370", projection.kr370_classification),
                ("Instrument", projection.canonical_instrument),
                ("Direction", projection.direction),
                ("Last Updated", updated),
            )
        ) + '</div></section>'
    )
    next_panel = '<section class="trade-panel trade-next"><h2>NEXT STEP</h2><strong>' + escape(next_step) + '</strong></section>'
    journal = (
        '<section class="trade-panel"><h2>JOURNAL</h2>'
        + (
            '<a class="button primary" href="/journal?record=' + escape(projection.journal_record_id)
            + '">OPEN JOURNAL</a>'
            if projection.journal_record_id is not None
            else '<p class="trade-muted">No journal record is manufactured before its governed event.</p>'
        ) + '</section>'
    )
    provenance = (
        '<details class="trade-panel trade-compact-details"><summary>GOVERNED PROVENANCE</summary>'
        '<div class="analysis-facts">' + _analysis_fact_rows([
            ("Native run", projection.native_run_identity),
            ("Native assessment", projection.native_assessment_sha256),
            ("KR-370 state", projection.kr370_classification),
            ("Step-31 plan", plan.trade_plan_id if plan is not None else "NOT AVAILABLE"),
            ("Step-31 observation", observation.observation_evidence_id if observation is not None else "NOT AVAILABLE"),
            ("Risk result", projection.risk_result_id or "NOT AVAILABLE"),
            ("Observation decision", projection.sponsor_observation_decision_id or "NOT AVAILABLE"),
            ("Decision-time snapshot", projection.sponsor_observation_snapshot_id or "NOT AVAILABLE"),
            ("Activation disposition", projection.activation_disposition),
            ("Paper Observation Track", projection.paper_observation_track_id or projection.paper_observation_track_state),
            ("Sponsor position", projection.sponsor_position_id or "NOT AVAILABLE"),
            ("Step-33 journal", projection.journal_record_id or "NOT AVAILABLE"),
            ("Continuity binding", "EXACT CURRENT" if not projection.continuity_warnings else "FAIL CLOSED · " + " · ".join(projection.continuity_warnings)),
        ]) + '</div></details>'
    )
    error = (
        '' if workflow_error is None else
        '<section class="trade-panel trade-error"><h2>' + escape(workflow_error[0])
        + '</h2><p>' + escape(workflow_error[1]) + '</p></section>'
    )
    attempt_notice = (
        '' if not attempt_failed or plan is None else
        '<section class="trade-panel trade-error"><h2>CONSTRUCTION FOLLOW-UP INCOMPLETE</h2><strong>'
        + escape((attempt.safe_failure_code or "TRADE_PLAN_CONSTRUCTION_UNAVAILABLE").replace("_", " "))
        + '</strong><p>' + escape(attempt.safe_bounded_reason or "A downstream governed stage is unavailable.")
        + '</p></section>'
    )
    decision_header = (
        '<section class="trade-panel"><div class="trade-decision-head"><div><h1 class="trade-instrument">'
        + escape(projection.canonical_instrument) + '</h1><span class="trade-direction '
        + escape(projection.direction.lower()) + '">' + escape(projection.direction)
        + '</span></div><span class="trade-now'
        + (' sell' if projection.kr370_classification == "SELL_NOW" else '') + '">'
        + escape(heading) + '</span></div><p class="trade-semantics">' + escape(notice) + '</p></section>'
    )
    body = (
        '<div class="trade-window-shell"><p class="trade-window-back"><a class="button" href="/swing/opportunities">← Back to Opportunities</a></p>'
        + error + '<div class="trade-window-grid"><div class="trade-window-column">'
        + decision_header + attempt_notice + mathematics + assessment + risk + timing_model
        + '</div><aside class="trade-window-column">' + sponsor + activation + paper_track
        + entry_workflow + next_panel + context + journal + provenance + '</aside></div></div>'
    )
    return _page(
        title=f"{projection.canonical_instrument} Trade Window",
        subtitle="Sponsor decision, governed trade evidence and separate entry activation.",
        snapshot=snapshot,
        active_nav="Swing",
        active_tab="Opportunities",
        body=body,
        extra_styles=_TRADE_WINDOW_CSS,
    )
def _v3_timeframe_reconciliation(machine, visual) -> str:  # type: ignore[no-untyped-def]
    if machine.availability == "AVAILABLE":
        numerical = (
            '<div class="analysis-facts">'
            + _analysis_fact_rows([
                ("Reference period", machine.reference_period),
                ("BC", machine.bc or "UNAVAILABLE"),
                ("CP", machine.cp or "UNAVAILABLE"),
                ("TC", machine.tc or "UNAVAILABLE"),
                ("Reference High", machine.reference_high or "UNAVAILABLE"),
                ("Reference Low", machine.reference_low or "UNAVAILABLE"),
            ]) + '</div>'
        )
    else:
        numerical = (
            '<p class="missing-evidence"><strong>Numerical reference not available.</strong> '
            + escape(machine.unavailable_explanation or "The governed fact is unavailable.")
            + '</p>'
        )
    components = (
        '<p><strong>Identified components:</strong> '
        + escape(" · ".join(visual.clustering_components)) + '</p>'
        if visual.clustering_components else ""
    )
    return (
        '<div class="analysis-section"><h3>' + escape(machine.timeframe)
        + ' · ' + escape(machine.reference_period) + '</h3>'
        '<p><strong>KRONOS NUMERICAL FACTS</strong></p>' + numerical
        + '<p><strong>CHART OBSERVATION</strong></p><p>'
        + escape(visual.cpr_observation) + '</p><p>'
        + escape(visual.reference_observation) + '</p><p>'
        + escape(visual.clustering_observation) + '</p>' + components + '</div>'
    )


def _watch_identities(
    instrument: str, progression: SwingProgressionWatchSnapshot | None
) -> str:
    if progression is None:
        return "NONE"
    values = tuple(
        watch.watch_id for watch in progression.watches
        if watch.requirement.canonical_instrument == instrument
    )
    return " · ".join(values) or "NONE"


def _v3_next_step(
    instrument: str,
    progression: SwingProgressionWatchSnapshot | None,
    fallback: str,
) -> str:
    if progression is None:
        return fallback
    watches = tuple(
        item for item in progression.watches
        if item.requirement.canonical_instrument == instrument
    )
    if any(item.state is ProgressionWatchState.TRIGGERED for item in watches):
        return "The watch condition has been reached. Reassessment is required. No trade has been authorized."
    if any(item.state is ProgressionWatchState.ACTIVE for item in watches):
        return "KRONOS is monitoring this condition. If reached, the candidate will require reassessment."
    if any(
        item.state is ProgressionRequirementState.WATCH_AVAILABLE
        for item in progression.for_instrument(instrument)
    ):
        return "You may activate a KRONOS watch for the governed outstanding progression condition."
    return fallback


def _progression_requirements_section(
    instrument: str,
    progression: SwingProgressionWatchSnapshot | None,
    *,
    hide_satisfied: bool = False,
    promotion_complete: bool = False,
) -> str:
    requirements = () if progression is None else progression.for_instrument(instrument)
    if hide_satisfied:
        requirements = tuple(
            item for item in requirements
            if item.state is not ProgressionRequirementState.SATISFIED
        )
    if not requirements:
        content = (
            '<p><strong>ALL KR-370 PROMOTION CRITERIA SATISFIED</strong></p>'
            if hide_satisfied and promotion_complete else
            '<p>No unresolved countable KR-370 criterion. See the hard-gate or evidence status above.</p>'
            if hide_satisfied else
            '<p>Governed progression requirements are not available for this current candidate.</p>'
        )
    else:
        rows = []
        for requirement in requirements:
            watch = None if progression is None else progression.watch_for(requirement.requirement_id)
            state = requirement.state.value.replace("_", " ")
            summary = _progression_summary(requirement)
            detail = ""
            if watch is not None and watch.state is ProgressionWatchState.TRIGGERED:
                state = "REASSESSMENT REQUIRED"
                detail = (
                    '<small>Watch condition reached. No trade has been authorized.</small>'
                )
            elif watch is not None and watch.state is ProgressionWatchState.STALE:
                state = "NOT WATCHABLE"
                detail = '<small>Original analytical identity is stale; watch was not rebound.</small>'
            elif requirement.state is ProgressionRequirementState.WATCH_AVAILABLE:
                instruction = tradingview_instruction(requirement)
                detail = (
                    '<form method="post" action="/swing/progression-watch/activate">'
                    '<input type="hidden" name="requirement_id" value="'
                    + escape(requirement.requirement_id) + '">'
                    '<button class="button" type="submit">Activate Watch</button></form>'
                    '<details><summary>TradingView alert instruction</summary>'
                    + ''.join(
                        '<div class="analysis-fact"><span>' + escape(label)
                        + '</span><strong>' + escape(value) + '</strong></div>'
                        for label, value in instruction
                    ) + '</details>'
                )
            elif requirement.state is ProgressionRequirementState.WATCH_ACTIVE:
                detail = (
                    '<small>Live monitoring active · completed governed bars only. Activated '
                    + escape(watch.activated_at.isoformat() if watch is not None else "UNKNOWN")
                    + '.</small>'
                )
            marker = "✓" if requirement.state is ProgressionRequirementState.SATISFIED else "○"
            rows.append(
                '<div class="progression-row"><span class="progression-marker">'
                + marker + '</span><div><strong>' + escape(summary)
                + '</strong><span class="progression-state">' + escape(state)
                + '</span>' + detail + '</div></div>'
            )
        content = ''.join(rows)
    return (
        '<section class="analysis-section"><h2>E. REQUIREMENTS TO PROGRESS</h2>'
        '<p><strong>WHAT KRONOS IS WAITING FOR</strong></p>'
        '<p class="technical">Satisfaction requests the next governed reassessment; it does not authorize a trade.</p>'
        '<div class="progression-list">' + content + '</div></section>'
    )


def _progression_summary(requirement) -> str:  # type: ignore[no-untyped-def]
    if (
        requirement.state in {
            ProgressionRequirementState.WATCH_AVAILABLE,
            ProgressionRequirementState.WATCH_ACTIVE,
            ProgressionRequirementState.ALREADY_SATISFIED,
        }
        and requirement.timeframe is not None
        and requirement.comparator is not None
        and requirement.price is not None
    ):
        relation = (
            "ABOVE"
            if requirement.comparator.value == "BAR_CLOSE_ABOVE"
            else "BELOW"
        )
        return (
            f"WATCH FOR · {requirement.timeframe.value} CLOSE {relation} "
            f"{_sponsor_price(requirement.price)}"
        )
    return requirement.summary


def _analysis_disclosure(title: str, facts: list[tuple[str, str]]) -> str:
    return (
        '<details class="analysis-section"><summary>'
        + escape(title)
        + '</summary><div class="analysis-facts">'
        + _analysis_fact_rows(facts)
        + '</div></details>'
    )


def _analysis_fact_rows(facts: list[tuple[str, str]]) -> str:
    return "".join('<div class="analysis-fact"><span>' + escape(label) + '</span><strong>' + escape(value) + '</strong></div>' for label, value in facts)


def _visual_level(observation) -> str:  # type: ignore[no-untyped-def]
    if observation.level_availability.value != "AVAILABLE":
        return observation.level_availability.value
    if observation.price is not None:
        return f"{observation.price:g}"
    return f"{observation.zone_low:g}–{observation.zone_high:g}"


def _governed_next_step(readiness: str) -> str:
    return {
        "READY_FOR_TRADE_CONSTRUCTION": "This persisted decision permits governed Step 31 Trade Construction.",
        "INVALIDATED": "The candidate is discarded from the current trade path; no further action is permitted.",
        "CONTEXT_INCOMPLETE": "The candidate remains stopped pending established governed evidence.",
        "WAIT_PULLBACK_DEVELOPING": "No further action; the governed pullback condition remains developing.",
        "WAIT_RETEST_DEVELOPING": "No further action; the governed retest condition remains developing.",
        "WAIT_OBSTACLE_CLEARANCE": "No further action; the governed obstacle remains unresolved.",
        "EXTENDED_DO_NOT_CHASE": "No further action; the persisted decision prohibits chasing this extension.",
        "WEAKENING": "No further action; the persisted evidence identifies weakening.",
    }[readiness]


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
    browser_key: str
    instrument: str
    direction: str
    setup: str
    entry: Decimal
    stop: Decimal
    invalidation: Decimal
    target: Decimal
    risk_reward: Decimal
    trade_plan_status: str
    risk: str
    risk_reason: str
    risk_constraints: tuple[str, ...]
    risk_permits_entry: bool
    sponsor_decision: str
    sponsor_decision_timestamp: str
    current_state: str
    model_state: str
    sponsor_position_state: str
    kite_monitoring: str
    trade_monitoring: str
    close_reason: str
    action_required: bool
    readiness: str
    key_reason: str
    next_step: str
    target_constraint: str
    entry_status: str


def build_step32_sponsor_workflow_view(
    candidate: SwingV1TradeCandidate,
    risk: RiskApproval,
    lifecycle: CandidateLifecycle,
    *,
    decision: SponsorDecision | None = None,
    model: ObjectiveModelTrade | None = None,
    position: SponsorPosition | None = None,
    monitoring_state: MonitoringConnectionState = MonitoringConnectionState.DISCONNECTED,
    readiness_state: str = "",
    readiness_reason: str = "",
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
        BrowserCandidateRecord(candidate).browser_key,
        candidate.canonical_instrument,
        candidate.direction,
        candidate.setup_family.replace("_", " ").title(),
        _required_decimal(candidate.entry_price),
        _required_decimal(candidate.stop_price),
        _required_decimal(candidate.invalidation_level_or_reference),
        _required_decimal(candidate.target_price),
        _required_decimal(candidate.risk_reward_ratio),
        candidate.construction_status.value.removeprefix("TRADE_CONSTRUCTION_"),
        risk.state.value.removeprefix("RISK_").replace("_", " "),
        risk.reason.replace("_", " "),
        tuple(
            f"{name.replace('_', ' ').title()}: {_decimal_number(value)}"
            for name, value in (
                ("maximum quantity", risk.constraints.maximum_quantity),
                ("maximum notional", risk.constraints.maximum_notional),
                ("maximum capital at risk", risk.constraints.maximum_capital_at_risk),
                ("maximum margin", risk.constraints.maximum_margin),
                ("maximum exposure", risk.constraints.maximum_exposure),
                ("maximum concentration", risk.constraints.maximum_concentration),
            )
            if value is not None
        ),
        risk.permits_entry,
        "NOT SELECTED" if decision is None else decision.mode.value,
        "" if decision is None else decision.decided_at.astimezone(_KOLKATA).strftime(
            "%d %b %Y %H:%M IST"
        ),
        current,
        model_state,
        "NONE" if position is None else f"{position.mode.value} · {position.state.value}",
        "NOT STARTED"
        if not risk.permits_entry
        else monitoring_state.value.replace("_", " "),
        "NOT STARTED"
        if not risk.permits_entry
        else "RECONCILIATION REQUIRED"
        if model is not None and model.state is ObjectiveModelState.RECONCILIATION_REQUIRED
        else "MONITORING OK"
        if monitoring_state is MonitoringConnectionState.CONNECTED
        else "RECONCILIATION REQUIRED",
        "" if model is None or model.close_reason is None else model.close_reason.value.replace("_", " "),
        (
            model is not None
            and model.state is ObjectiveModelState.CLOSED
            and decision is not None
            and decision.mode.value == "LIVE"
            and (position is None or position.state.value != "CLOSED")
        ),
        readiness_state or "READY FOR TRADE PLAN",
        readiness_reason.replace("_", " ") or "AUTHORITATIVE REVIEW COMPLETE",
        (
            risk.reason.replace("_", " ")
            if not risk.permits_entry
            else "MONITOR ENTRY"
            if model is None
            else "MONITOR OBJECTIVE MODEL"
            if model.state is not ObjectiveModelState.CLOSED
            else "—"
        ),
        (
            "MATERIAL CHART BARRIER"
            if candidate.material_barrier_status.value == "TARGET_TRUNCATED"
            else "—"
        ),
        (
            "WAITING"
            if model is None
            else f"TRIGGERED · {model.activated_at.astimezone(_KOLKATA).strftime('%d %b %Y %H:%M IST')}"
        ),
    )


def render_step32_sponsor_workflow(view: Step32SponsorWorkflowView) -> str:
    options = (
        ""
        if not view.risk_permits_entry
        else "".join(
            '<form method="post" action="/swing/trade-candidates/'
            + escape(view.browser_key)
            + '/decision"><input type="hidden" name="mode" value="'
            + mode
            + '"><button class="decision-option'
            + (' selected' if view.sponsor_decision == mode else '')
            + f'" type="submit">{mode}</button></form>'
            for mode in ("LIVE", "PAPER", "IGNORE")
        )
    )
    decision = (
        ""
        if not view.risk_permits_entry
        else '<h3>Your Decision</h3><div class="decision-options">'
        + options
        + "</div><div class=\"decision-time\">"
        + escape(
            "NOT SELECTED"
            if view.sponsor_decision == "NOT SELECTED"
            else f"{view.sponsor_decision} · {view.sponsor_decision_timestamp}"
        )
        + "</div>"
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
    action_required = (
        '<div class="action-required">ACTION REQUIRED — KRONOS MODEL CLOSED'
        f'{" — " + escape(view.close_reason) if view.close_reason else ""}. '
        'CHECK / MANAGE YOUR LIVE POSITION.</div>'
        if view.action_required
        else ""
    )
    constraints = (
        ""
        if not view.risk_constraints
        else '<div class="step32-context"><span>Constraints</span><strong>'
        + escape(" · ".join(view.risk_constraints))
        + "</strong></div>"
    )
    context = (
        '<div class="step32-block"><h3>Context</h3><div class="step32-context">'
        f'<div><span>Readiness</span><strong>{escape(view.readiness)}</strong></div>'
        f'<div><span>Key reason</span><strong>{escape(view.key_reason)}</strong></div>'
        f'<div><span>Next step</span><strong>{escape(view.next_step)}</strong></div>'
        f'<div><span>Target constrained by</span><strong>{escape(view.target_constraint)}</strong></div>'
        '</div></div>'
    )
    return (
        '<section class="step32-workflow"><div class="step32-head">'
        f'<h2>{escape(view.instrument)} — {escape(view.direction)}</h2>'
        f'<span class="setup-family">{escape(view.setup)}</span></div>'
        '<div class="step32-grid"><div class="step32-block"><h3>Trade Plan</h3>'
        f'<strong>{escape(view.trade_plan_status)}</strong>'
        f'<div class="step32-values">{values}</div>'
        f'<div class="step32-context"><span>Entry status</span><strong>{escape(view.entry_status)}</strong></div></div>'
        f'{context}'
        '<div class="step32-block"><h3>Risk</h3>'
        f'<strong>RISK {escape(view.risk)}</strong>'
        f'<div class="muted">{escape(view.risk_reason)}</div>{constraints}{decision}</div>'
        '<div class="step32-block"><h3>Current State</h3>'
        f'<strong>{escape(view.current_state)}</strong><div class="model-position">'
        f'<div><span>Kite Monitoring</span><strong>{escape(view.kite_monitoring)}</strong></div>'
        f'<div><span>Trade Monitoring</span><strong>{escape(view.trade_monitoring)}</strong></div>'
        f'<div><span>KRONOS Model</span><strong>{escape(view.model_state)}</strong></div>'
        f'<div><span>Your Position</span><strong>{escape(view.sponsor_position_state)}</strong></div>'
        f'</div></div></div>{action_required}</section>'
    )


def render_trade_candidates(
    snapshot: BrowserWorkspaceSnapshot,
    workflow: BrowserStep32Snapshot,
) -> str:
    body = _workflow_failure(workflow) + _workflow_cards(
        workflow.trade_candidates,
        empty_message=(
            "No instruments from the current chart review are ready for a Trade Plan."
        ),
    )
    return _page(
        title="Trade Candidates",
        subtitle="Canonical Trade Plans and their current Risk state.",
        snapshot=snapshot,
        active_nav="Swing",
        active_tab="Trade Candidates",
        body=body,
    )


def render_active_candidates(
    snapshot: BrowserWorkspaceSnapshot,
    workflow: BrowserStep32Snapshot,
    native_lifecycle: ActiveTradeLifecycleSnapshot | None = None,
    *,
    active_monitoring_position_ids: tuple[str, ...] = (),
) -> str:
    native = _native_active_lifecycle(
        native_lifecycle, active_monitoring_position_ids
    )
    legacy = _workflow_cards(
        workflow.active,
        empty_message="No objective model trades are currently active.",
    )
    return _page(
        title="Active",
        subtitle="Sponsor Paper and Live positions under governed factual observation.",
        snapshot=snapshot,
        active_nav="Swing",
        active_tab="Active",
        body=native + '<details class="native-diagnostics"><summary>LEGACY STEP-32 MODEL LIFECYCLE</summary>' + legacy + '</details>',
    )


def render_closed_candidates(
    snapshot: BrowserWorkspaceSnapshot,
    workflow: BrowserStep32Snapshot,
    native_lifecycle: ActiveTradeLifecycleSnapshot | None = None,
) -> str:
    native = _native_closed_lifecycle(native_lifecycle)
    legacy = _workflow_cards(
        workflow.closed,
        empty_message="No objective model trades have closed.",
    )
    return _page(
        title="Closed",
        subtitle="Factual Paper and Sponsor-attested Live closure records.",
        snapshot=snapshot,
        active_nav="Swing",
        active_tab="Closed",
        body=native + '<details class="native-diagnostics"><summary>LEGACY STEP-32 MODEL LIFECYCLE</summary>' + legacy + '</details>',
    )


def render_reports(
    snapshot: BrowserWorkspaceSnapshot,
    projection: HistoricalReportsProjection,
    *,
    selected_record_id: str | None = None,
) -> str:
    """Render the factual historical book without research or trading authority."""

    query = projection.query
    product_tabs = ''.join(
        '<a class="button ' + ('active' if query.product is item else '')
        + '" href="/reports?' + urlencode({"product": item.value}) + '">'
        + item.value + '</a>'
        for item in (ReportProduct.SWING, ReportProduct.INTRADAY)
    )
    if query.product is ReportProduct.INTRADAY:
        return _page(
            title="Reports", subtitle="Historical trading and observation evidence.",
            snapshot=snapshot, active_nav="Reports", active_tab="",
            body=(
                '<div class="reports-head"><div class="reports-products">'
                + product_tabs + '</div></div><div class="workflow-empty">'
                '<strong>INTRADAY REPORTS</strong><br>NOT YET OPERATIONAL</div>'
            ),
        )
    base = _reports_params(projection)
    view_tabs = ''.join(
        '<a class="button ' + ('active' if query.view is item else '')
        + '" href="/reports?' + urlencode(base | {"view": item.value, "page": 1})
        + '">' + item.value.replace('_', ' ') + '</a>'
        for item in ReportView
    )
    governed = (
        "GOVERNED DATE UNAVAILABLE" if projection.governed_current_trading_date is None
        else projection.governed_current_trading_date.strftime("%d %b %Y").upper()
    )
    header = (
        '<div class="reports-head"><div class="reports-products">' + product_tabs
        + '</div><span class="reports-date">' + governed + '</span>'
        '<a class="button journal-reports" href="/journal">TRADING JOURNAL</a></div>'
        '<div class="reports-views">' + view_tabs + '</div>'
    )
    overview = projection.overview
    metrics = (
        ("Records", str(overview.records)),
        ("Paper", str(overview.paper_positions)),
        ("Live", str(overview.live_positions)),
        ("Observations", str(overview.paper_observations)),
        ("Completed", str(overview.completed_records)),
        ("Net P/L", "UNAVAILABLE" if overview.net_pnl is None else "₹" + _number(overview.net_pnl)),
    )
    summary = '<div class="reports-summary">' + ''.join(
        '<div class="reports-metric"><span>' + escape(label) + '</span><strong>'
        + escape(value) + '</strong></div>' for label, value in metrics
    ) + '</div>'
    maximum = max(
        1, overview.paper_positions, overview.live_positions,
        overview.paper_observations,
    )
    chart = '<div class="reports-chart" aria-label="Factual records by mode">' + ''.join(
        '<div class="reports-bar ' + style + '"><span>' + label + '</span><strong>'
        + str(value) + '</strong><i style="width:' + str(round(value / maximum * 100))
        + '%"></i></div>'
        for label, value, style in (
            ("PAPER RECORDS", overview.paper_positions, "paper"),
            ("LIVE RECORDS", overview.live_positions, "live"),
            ("PAPER OBSERVATIONS", overview.paper_observations, "observation"),
        )
    ) + '</div>'
    unsupported = (
        '<p class="reports-unavailable">WIN RATE · AVERAGE R · MAX DRAWDOWN · '
        'DAILY P/L · EFFECTIVENESS: UNAVAILABLE — NOT GOVERNED IN SWING V1.</p>'
    )
    detail = next(
        (item for item in projection.records if item.record_identity == selected_record_id),
        None,
    )
    detail_view = '' if detail is None else _report_detail(detail)
    table = _reports_table(projection)
    filters = _reports_filter_panel(projection)
    return _page(
        title="Reports", subtitle="Historical trading and observation evidence.",
        snapshot=snapshot, active_nav="Reports", active_tab="",
        body=(
            header + '<div class="reports-layout"><main class="reports-main">'
            + summary + chart + unsupported + detail_view + table
            + '</main>' + filters + '</div>'
        ),
    )


def _reports_params(projection: HistoricalReportsProjection) -> dict[str, object]:
    query = projection.query
    values: dict[str, object] = {
        "product": query.product.value, "view": query.view.value,
        "search": query.instrument, "status": query.status, "page": query.page,
    }
    if query.from_date is not None:
        values["from"] = query.from_date.isoformat()
    if query.to_date is not None:
        values["to"] = query.to_date.isoformat()
    if query.direction is not None:
        values["direction"] = query.direction.value
    return values


def _reports_filter_panel(projection: HistoricalReportsProjection) -> str:
    query = projection.query
    hidden = (
        '<input type="hidden" name="product" value="' + query.product.value + '">'
        '<input type="hidden" name="view" value="' + query.view.value + '">'
    )
    quick = ''.join(
        '<a class="button" href="/reports?' + urlencode({
            "product": query.product.value, "view": query.view.value, "quick": item,
        }) + '">' + item.replace('_', ' ') + '</a>'
        for item in ("TODAY", "7D", "30D", "THIS_MONTH")
    )
    direction_options = '<option value="">ALL</option>' + ''.join(
        '<option value="' + item.value + '"'
        + (' selected' if query.direction is item else '') + '>' + item.value + '</option>'
        for item in V1Direction
    )
    export_params = urlencode(_reports_params(projection) | {"page": 1})
    return (
        '<aside class="reports-filter"><h2>FILTER & EXPORT</h2>'
        '<div class="reports-quick">' + quick + '</div>'
        '<form method="get" action="/reports">' + hidden
        + '<label>From<input type="date" name="from" value="'
        + ('' if query.from_date is None else query.from_date.isoformat()) + '"></label>'
        + '<label>To<input type="date" name="to" value="'
        + ('' if query.to_date is None else query.to_date.isoformat()) + '"></label>'
        + '<label>Instrument<input name="search" maxlength="80" value="'
        + escape(query.instrument) + '" placeholder="Search instrument..."></label>'
        + '<label>Direction<select name="direction">' + direction_options + '</select></label>'
        + '<label>Status / outcome<input name="status" maxlength="80" value="'
        + escape(query.status) + '"></label><div class="reports-filter-actions">'
        + '<button type="submit">APPLY</button><a class="button" href="/reports?product=SWING">CLEAR</a>'
        '</div></form><div class="reports-filter-actions">'
        + '<a class="button" href="/reports/export.xlsx?' + export_params + '">EXCEL</a>'
        + '<a class="button" href="/reports/export.csv?' + export_params + '">CSV</a>'
        + '<a class="button" href="/reports/export.json?' + export_params + '">JSON</a>'
        '</div><p class="reports-export-note">Exports preserve selected filters, evidence family, '
        'and unavailable values. No performance analytics.</p></aside>'
    )


def _reports_table(projection: HistoricalReportsProjection) -> str:
    if not projection.page_records:
        message = (
            "NO HISTORICAL RECORDS" if projection.total_records == 0 and not any((
                projection.query.from_date, projection.query.to_date,
                projection.query.instrument, projection.query.direction,
                projection.query.status,
            )) else "NO RECORDS MATCH THESE FILTERS"
        )
        return '<div class="workflow-empty"><strong>' + message + '</strong></div>'
    rows = ''.join(_report_row(item, projection) for item in projection.page_records)
    pagination = ''
    if projection.page_count > 1:
        links = []
        for label, page in (
            ("PREVIOUS", projection.query.page - 1),
            ("NEXT", projection.query.page + 1),
        ):
            if 1 <= page <= projection.page_count:
                links.append(
                    '<a class="button" href="/reports?'
                    + urlencode(_reports_params(projection) | {"page": page})
                    + '">' + label + '</a>'
                )
        pagination = (
            '<div class="reports-pagination"><span>PAGE '
            + str(projection.query.page) + ' / ' + str(projection.page_count)
            + '</span>' + ''.join(links) + '</div>'
        )
    return (
        '<div class="reports-table-wrap"><table class="reports-table"><thead><tr>'
        '<th>Date</th><th>Time</th><th>Instrument</th><th>Side</th><th>Family</th><th>Status</th>'
        '<th>Entry</th><th>Exit</th><th>P/L</th><th>Target</th><th>SL</th>'
        '<th>Position Outcome</th><th>Track Outcome</th></tr></thead><tbody>'
        + rows + '</tbody></table></div>' + pagination
    )


def _report_row(
    item: HistoricalReportRecord, projection: HistoricalReportsProjection
) -> str:
    params = _reports_params(projection) | {"record": item.record_identity}
    pnl = "—" if item.pnl is None else "₹" + _number(item.pnl)
    return (
        '<tr><td>' + item.record_date.isoformat() + '</td><td>'
        + item.relevant_timestamp.astimezone(_KOLKATA).strftime("%H:%M IST")
        + '</td><td><a href="/reports?'
        + urlencode(params) + '"><strong>' + escape(item.instrument) + '</strong></a></td>'
        '<td class="journal-side ' + item.direction.value + '">' + item.direction.value + '</td>'
        '<td class="reports-family ' + item.family.value.lower() + '">' + item.family.value.replace('_', ' ') + '</td>'
        '<td>' + escape(item.status) + '</td><td>' + _report_value(item.entry) + '</td>'
        '<td>' + _report_value(item.exit) + '</td><td class="reports-pnl '
        + ('positive' if (item.pnl or 0) > 0 else 'negative' if (item.pnl or 0) < 0 else '')
        + '">' + pnl + '</td><td>' + _report_value(item.target) + '</td><td>'
        + _report_value(item.stop) + '</td><td>' + escape(item.sponsor_position_outcome)
        + '</td><td>' + escape(item.paper_track_outcome) + '</td></tr>'
    )


def _report_detail(item: HistoricalReportRecord) -> str:
    values = (
        ("Family", item.family.value.replace('_', ' ')), ("Status", item.status),
        ("Completed / exited at", item.relevant_timestamp.astimezone(_KOLKATA).strftime(
            "%d %b %Y · %H:%M IST"
        )),
        ("Decision", item.decision_identity), ("Step-31 severity", item.step31_severity),
        ("Risk at decision", item.risk_state), ("Activation", item.activation_disposition),
        ("Entry / observation entry", _report_value(item.entry)), ("Exit", _report_value(item.exit)),
        ("P/L", "—" if item.pnl is None else "₹" + _number(item.pnl)),
        ("Target", _report_value(item.target)), ("Stop", _report_value(item.stop)),
        ("Sponsor Position outcome", item.sponsor_position_outcome),
        ("Paper Track outcome", item.paper_track_outcome),
        ("Objective model", item.objective_outcome),
    )
    fields = ''.join(
        '<div><span>' + escape(label) + '</span><strong>' + escape(value) + '</strong></div>'
        for label, value in values
    )
    return (
        '<section class="journal-detail reports-detail"><h2>' + escape(item.instrument)
        + ' · HISTORICAL DETAIL</h2><div class="journal-detail-grid">' + fields
        + '</div><details class="native-diagnostics"><summary>GOVERNED EVIDENCE</summary>'
        '<div class="v1-context-row"><span>Record</span><strong>' + escape(item.record_identity)
        + '</strong></div><div class="v1-context-row"><span>Contract</span><strong>'
        + escape(item.source_contract_identity + ' / ' + item.source_contract_version)
        + '</strong></div></details></section>'
    )


def _report_value(value: Decimal | None) -> str:
    return "—" if value is None else _number(value)


def render_trade_journal(
    snapshot: BrowserWorkspaceSnapshot,
    journal: TradeJournalSnapshot,
    *,
    operational: tuple[ObservationOperationalHandoffV2, ...] | None = None,
    operational_websocket_state: WebSocketPresentationState | None = None,
    governed_trading_date: date | None = None,
    selected_product: str = "SWING",
    search: str = "",
    selected_record_id: str | None = None,
    selected_filter: str = "ALL",
    observations: tuple[ObservationResearchProjectionV1, ...] = (),
    observation_choice: str = "ALL",
    observation_activation: str = "ALL",
    observation_severity: str = "ALL",
) -> str:
    """Render the operational Sponsor book or the preserved research surface."""

    if operational is None:
        return _render_trade_journal_research(
            snapshot,
            journal,
            selected_filter=selected_filter,
            selected_record_id=selected_record_id,
            observations=observations,
            observation_choice=observation_choice,
            observation_activation=observation_activation,
            observation_severity=observation_severity,
        )
    return _render_operational_trade_journal(
        snapshot,
        operational,
        websocket_state=operational_websocket_state,
        governed_trading_date=governed_trading_date,
        selected_product=selected_product,
        search=search,
        selected_record_id=selected_record_id,
    )


def _render_operational_trade_journal(
    snapshot: BrowserWorkspaceSnapshot,
    records: tuple[ObservationOperationalHandoffV2, ...],
    *,
    websocket_state: WebSocketPresentationState | None,
    governed_trading_date: date | None,
    selected_product: str,
    search: str,
    selected_record_id: str | None,
) -> str:
    product = selected_product if selected_product in {"SWING", "INTRADAY"} else "SWING"
    tabs = (
        '<div class="journal-products">'
        + ''.join(
            '<a class="button ' + ('active' if item == product else '')
            + '" href="/journal?product=' + item + '">' + item + '</a>'
            for item in ("SWING", "INTRADAY")
        ) + '</div>'
    )
    if product == "INTRADAY":
        body = (
            '<div class="journal-head">' + tabs + '</div>'
            '<div class="workflow-empty"><strong>INTRADAY JOURNAL</strong><br>'
            'NOT YET OPERATIONAL</div>'
        )
        return _page(
            title="Trading Journal", subtitle="Current operational book.",
            snapshot=snapshot, active_nav="Trading Journal", active_tab="",
            body=body,
        )

    current = tuple(
        item for item in records
        if item.operational_route is not ObservationOperationalRoute.HISTORICAL
    )
    needle = search.strip().casefold()
    if needle:
        current = tuple(item for item in current if needle in item.instrument.casefold())
    current = tuple(sorted(current, key=_journal_order_key))
    websocket = websocket_state or (
        current[0].websocket_state
        if current else WebSocketPresentationState.IDLE
    )
    date_text = (
        "GOVERNED DATE UNAVAILABLE"
        if governed_trading_date is None else governed_trading_date.strftime("%d %b %Y").upper()
    )
    header = (
        '<div class="journal-head">' + tabs
        + '<span class="journal-date">' + escape(date_text) + '</span>'
        + '<span class="journal-ws ' + websocket.value + '">WS '
        + ('○ ' if websocket is WebSocketPresentationState.IDLE else '● ')
        + websocket.value + '</span></div>'
        '<form class="journal-toolbar" method="get" action="/journal">'
        '<input type="hidden" name="product" value="SWING">'
        '<input class="journal-search" name="search" value="' + escape(search)
        + '" placeholder="Search instrument..." aria-label="Search instrument">'
        '<button type="submit">SEARCH</button>'
        '<a class="button journal-reports" href="/reports">VIEW HISTORICAL REPORTS</a>'
        '</form>'
    )
    paper = tuple(
        item for item in current
        if item.mode is ObservationMode.PAPER
        and item.sponsor_position_identity is not None
        and item.activation_disposition.value == "ACTIVATED"
    )
    live = tuple(
        item for item in current
        if item.mode is ObservationMode.LIVE
        and item.sponsor_position_identity is not None
        and item.activation_disposition.value == "ACTIVATED"
    )
    observations = tuple(
        item for item in current
        if item.mode is ObservationMode.PAPER_OBSERVATION
        and item.paper_track_identity is not None
    )
    detail = next(
        (item for item in current if item.decision_identity == selected_record_id),
        None,
    )
    content = ''.join((
        _journal_position_section("PAPER TRADES", "paper", paper),
        _journal_position_section("LIVE TRADES", "live", live),
        _journal_observation_section(observations),
    ))
    if not paper and not live and not observations:
        content = (
            '<div class="workflow-empty"><strong>NO ACTIVE SWING TRADES OR OBSERVATIONS</strong><br>'
            'Historical records remain available in Reports.</div>'
        )
    if detail is not None:
        content = _journal_detail(detail) + content
    content += (
        '<details class="native-diagnostics"><summary>GOVERNED EVIDENCE</summary>'
        '<a class="button" href="/journal?view=research">OPEN HISTORICAL RESEARCH LEDGER</a>'
        '</details>'
    )
    return _page(
        title="Trading Journal", subtitle="Current operational book.",
        snapshot=snapshot, active_nav="Trading Journal", active_tab="",
        body=header + content,
    )


def _journal_order_key(item: ObservationOperationalHandoffV2) -> tuple[object, ...]:
    active = item.operational_route is ObservationOperationalRoute.ACTIVE
    relevant = item.completion_timestamp or item.decision_timestamp
    return (0 if active else 1, -relevant.timestamp(), item.decision_identity)


def _journal_status(item: ObservationOperationalHandoffV2) -> str:
    if item.operational_route is ObservationOperationalRoute.COMPLETED_CURRENT_TRADING_DAY:
        return "COMPLETE TODAY" if item.mode is ObservationMode.PAPER_OBSERVATION else "EXITED TODAY"
    if item.monitoring_state in {"INTERRUPTED", "MONITORING_UNAVAILABLE"}:
        return "MONITORING INTERRUPTED"
    if item.mode is ObservationMode.PAPER_OBSERVATION:
        if item.paper_track_state == "COMPLETE":
            return "COMPLETE TODAY"
        if item.paper_track_outcome == "OUTCOME_NOT_ESTABLISHED":
            return "OUTCOME NOT ESTABLISHED"
    return "ACTIVE"


def _journal_value(value: Decimal | None, *, money: bool = False) -> str:
    if value is None:
        return "—"
    return ("₹" if money else "") + _number(value)


def _journal_distance(item: ObservationOperationalHandoffV2, target: bool) -> str:
    state = item.distance_to_target_state if target else item.distance_to_stop_state
    value = item.distance_to_target if target else item.distance_to_stop
    if state != "AVAILABLE":
        return state.replace("_", " ") if state != "UNAVAILABLE" else "—"
    return _journal_value(value)


def _journal_monitoring(item: ObservationOperationalHandoffV2) -> str:
    state = item.monitoring_state
    if state in {"ACTIVE", "CONNECTED"}:
        return "● ACTIVE"
    if state in {"INTERRUPTED", "MONITORING_UNAVAILABLE", "DISCONNECTED"}:
        return "● INTERRUPTED"
    return "○ NOT ACTIVE"


def _journal_position_section(
    title: str, style: str, records: tuple[ObservationOperationalHandoffV2, ...]
) -> str:
    active = sum(item.operational_route is ObservationOperationalRoute.ACTIVE for item in records)
    exited = len(records) - active
    summary = f"{active} ACTIVE · {exited} EXITED TODAY"
    rows = ''.join(
        '<tr><td><a href="/journal?product=SWING&amp;record=' + escape(item.decision_identity)
        + '">' + escape(item.instrument) + '</a></td>'
        '<td class="journal-side ' + item.direction.value + '">' + item.direction.value + '</td>'
        '<td>' + escape(_journal_status(item)) + '</td>'
        '<td>' + _journal_value(item.entry) + '</td><td>' + _journal_value(item.current_ltp) + '</td>'
        '<td class="journal-pnl ' + ('positive' if (item.position_gross_pnl or 0) > 0 else 'negative' if (item.position_gross_pnl or 0) < 0 else '') + '">'
        + _journal_value(item.position_gross_pnl, money=True) + '</td>'
        '<td>' + _journal_value(item.target) + '</td><td>' + escape(_journal_distance(item, True)) + '</td>'
        '<td>' + _journal_value(item.stop) + '</td><td>' + escape(_journal_distance(item, False)) + '</td>'
        '<td class="journal-monitor ' + escape(item.monitoring_state) + '">' + escape(_journal_monitoring(item)) + '</td></tr>'
        for item in records
    ) or '<tr><td colspan="11">No current ' + escape(title.lower()) + '.</td></tr>'
    return (
        '<section class="journal-section ' + style + '"><div class="journal-section-head"><h2>'
        + escape(title) + '</h2><span>' + summary + '</span></div><div class="journal-table-wrap">'
        '<table class="journal-table"><thead><tr><th>Instrument</th><th>Side</th><th>Status</th>'
        '<th>Entry</th><th>LTP</th><th>P/L</th><th>Target</th><th>Distance Target</th>'
        '<th>SL</th><th>Distance SL</th><th>Monitoring</th></tr></thead><tbody>'
        + rows + '</tbody></table></div></section>'
    )


def _journal_observation_section(
    records: tuple[ObservationOperationalHandoffV2, ...]
) -> str:
    active = sum(item.operational_route is ObservationOperationalRoute.ACTIVE for item in records)
    complete = len(records) - active
    rows = ''.join(
        '<tr><td><a href="/journal?product=SWING&amp;record=' + escape(item.decision_identity)
        + '">' + escape(item.instrument) + '</a></td>'
        '<td class="journal-side ' + item.direction.value + '">' + item.direction.value + '</td>'
        '<td>' + escape(_journal_status(item)) + '</td><td>' + _journal_value(item.entry) + '</td>'
        '<td>' + _journal_value(item.current_ltp) + '</td><td>' + _journal_value(item.target) + '</td>'
        '<td>' + escape(_journal_distance(item, True)) + '</td><td>' + _journal_value(item.stop) + '</td>'
        '<td>' + escape(_journal_distance(item, False)) + '</td><td>'
        + escape(item.paper_track_latest_event + ' · ' + item.paper_track_outcome) + '</td>'
        '<td class="journal-monitor ' + escape(item.monitoring_state) + '">' + escape(_journal_monitoring(item)) + '</td></tr>'
        for item in records
    ) or '<tr><td colspan="11">No current paper observations.</td></tr>'
    return (
        '<section class="journal-section observation"><div class="journal-section-head"><h2>PAPER OBSERVATIONS</h2>'
        '<span>' + str(active) + ' ACTIVE · ' + str(complete) + ' COMPLETE TODAY</span></div>'
        '<div class="journal-table-wrap"><table class="journal-table"><thead><tr><th>Instrument</th>'
        '<th>Side</th><th>Track Status</th><th>Observation Entry</th><th>LTP</th><th>Target</th>'
        '<th>Distance Target</th><th>SL</th><th>Distance SL</th><th>Latest Event / Outcome</th>'
        '<th>Monitoring</th></tr></thead><tbody>' + rows + '</tbody></table></div></section>'
    )


def _journal_detail(item: ObservationOperationalHandoffV2) -> str:
    values = (
        ("Sponsor Decision", item.mode.value), ("Step-31 severity", item.step31_severity.value),
        ("Risk at decision", item.risk_state), ("Position activation", item.activation_disposition.value),
        ("Observation / actual entry", _journal_value(item.entry)), ("LTP", _journal_value(item.current_ltp)),
        ("Stop", _journal_value(item.stop)), ("Target", _journal_value(item.target)),
        ("Latest event", item.paper_track_latest_event), ("Track outcome", item.paper_track_outcome),
        ("Monitoring", _journal_monitoring(item)), ("Status", _journal_status(item)),
    )
    fields = ''.join(
        '<div><span>' + escape(label) + '</span><strong>' + escape(value) + '</strong></div>'
        for label, value in values
    )
    evidence = (
        '<details class="native-diagnostics"><summary>GOVERNED EVIDENCE</summary>'
        '<div class="v1-context-row"><span>Decision</span><strong>'
        + escape(item.decision_identity) + '</strong></div><div class="v1-context-row"><span>Projection</span><strong>'
        + escape(item.projection_contract_identity + ' / ' + item.projection_contract_version)
        + '</strong></div></details>'
    )
    return '<section class="journal-detail"><h2>' + escape(item.instrument) + ' · READ-ONLY DETAIL</h2><div class="journal-detail-grid">' + fields + '</div>' + evidence + '</section>'


def _render_trade_journal_research(
    snapshot: BrowserWorkspaceSnapshot,
    journal: TradeJournalSnapshot,
    *,
    selected_filter: str = "ALL",
    selected_record_id: str | None = None,
    observations: tuple[ObservationResearchProjectionV1, ...] = (),
    observation_choice: str = "ALL",
    observation_activation: str = "ALL",
    observation_severity: str = "ALL",
) -> str:
    """Render Step-33 history and factual analytics, never active-trade authority."""

    selected_filter = selected_filter if selected_filter in {"ALL", "PAPER", "LIVE", "IGNORED"} else "ALL"
    records = tuple(
        item for item in journal.records
        if (
            selected_record_id is not None
            and item.journal_record_id == selected_record_id
        )
        or (
            selected_record_id is None
            and (
                selected_filter == "ALL"
                or (selected_filter == "IGNORED" and item.record_type is JournalRecordType.IGNORED_OPPORTUNITY)
                or item.mode.value == selected_filter
            )
        )
    )
    analytics = journal.analytics
    metrics = (
        ("Completed", str(analytics.total_completed_trades)),
        ("Paper", str(analytics.paper_trades)),
        ("Live", str(analytics.live_trades)),
        ("Ignored", str(analytics.ignored_opportunities)),
        ("Win rate", "—" if analytics.win_rate is None else _number(analytics.win_rate) + "%"),
        ("Gross P&L", "₹" + _number(analytics.total_gross_pnl)),
        ("Total realised R", _number(analytics.total_realised_r) + "R"),
    )
    filters = '<div class="journal-filters">' + "".join(
        '<a class="button ' + ("primary" if name == selected_filter else "")
        + '" href="/journal?filter=' + name + '">' + name + '</a>'
        for name in ("ALL", "PAPER", "LIVE", "IGNORED")
    ) + "</div>"
    summary = '<div class="status-strip">' + "".join(
        '<div class="status-item"><span>' + escape(label) + '</span><strong>'
        + escape(value) + '</strong></div>' for label, value in metrics
    ) + "</div>"
    validation = journal.validation
    validation_view = (
        '<details class="native-diagnostics"><summary>KRONOS VALIDATION EVIDENCE</summary>'
        + "".join(
            '<div class="v1-context-row"><span>' + escape(label) + '</span><strong>'
            + escape(str(value)) + '</strong></div>'
            for label, value in (
                ("Opportunities reviewed", validation.opportunities_reviewed),
                ("Ready for construction", validation.ready_for_trade_construction),
                ("Trade Plans", validation.trade_plans_produced),
                ("Paper decisions", validation.paper_decisions),
                ("Live decisions", validation.live_decisions),
                ("Ignore decisions", validation.ignore_decisions),
                ("Paper Entries", validation.paper_entries_triggered),
                ("Paper closed", validation.paper_trades_closed),
                ("Live closed", validation.live_trades_closed),
                ("Unresolved events", validation.unresolved_lifecycle_events),
                ("Monitoring outages", validation.monitoring_outages),
            )
        ) + '</details>'
    )
    if not records:
        rows = '<div class="workflow-empty">No journal records match this view.</div>'
    else:
        cards = []
        for item in records:
            ignored = item.record_type is JournalRecordType.IGNORED_OPPORTUNITY
            title = item.mode.value + " · " + item.instrument + " · " + item.direction.value
            primary = (
                (("Exit reason", item.exit_reason or "—"),
                 ("Actual Entry", "₹" + _number(item.actual_entry)),
                 ("Actual Exit", "₹" + _number(item.actual_exit)),
                 ("Gross P&L", "₹" + _number(item.gross_pnl)),
                 ("Realised R", _number(item.realised_r) + "R"),
                 ("Holding", _duration(item.holding_duration_seconds)))
                if not ignored else
                (("Decision", "IGNORE"), ("Position", "NONE"),
                 ("Entry", "—"), ("Exit", "—"), ("Gross P&L", "—"),
                 ("Outcome", "NOT APPLICABLE"))
            )
            values = "".join(
                '<div><span>' + escape(label) + '</span><strong>' + escape(value) + '</strong></div>'
                for label, value in primary
            )
            detail = "".join(
                '<div class="v1-context-row"><span>' + escape(label) + '</span><strong>'
                + escape(value) + '</strong></div>'
                for label, value in (
                    ("Setup", item.setup_identity),
                    ("Readiness", item.readiness_state),
                    ("Model Entry", "₹" + _number(item.model_entry)),
                    ("Model Stop", "₹" + _number(item.model_stop)),
                    ("Invalidation", "₹" + _number(item.analytical_invalidation)),
                    ("Model Target", "₹" + _number(item.model_target)),
                    ("Model R:R", _number(item.model_risk_reward)),
                    ("Actual Entry", "—" if item.actual_entry is None else "₹" + _number(item.actual_entry)),
                    ("Actual Exit", "—" if item.actual_exit is None else "₹" + _number(item.actual_exit)),
                    ("Accounting", item.accounting_basis),
                    ("Commentary", item.commentary),
                    ("Record", item.journal_record_id),
                )
            )
            cards.append(
                '<section class="native-trade-plan"><h3>' + escape(title) + '</h3>'
                '<div class="native-trade-plan-grid">' + values + '</div>'
                '<details class="native-diagnostics"><summary>MODEL, ACTUAL & PROVENANCE</summary>'
                + detail + '</details></section>'
            )
        rows = "".join(cards)
    observation_view = _observation_research_view(
        observations,
        observation_choice=observation_choice,
        observation_activation=observation_activation,
        observation_severity=observation_severity,
    )
    return _page(
        title="Trading Journal",
        subtitle=(
            "Prospective observation research plus the independently governed "
            "completed-trade and ignored-opportunity Journal."
        ),
        snapshot=snapshot,
        active_nav="Trading Journal",
        active_tab="",
        body=observation_view + filters + summary + validation_view + rows,
    )


def _observation_research_view(
    observations: tuple[ObservationResearchProjectionV1, ...],
    *, observation_choice: str, observation_activation: str,
    observation_severity: str,
) -> str:
    """Render evidence rows without deriving research or performance metrics."""

    def href(choice: str, activation: str, severity: str) -> str:
        return (
            "/journal?observation_choice=" + choice
            + "&observation_activation=" + activation
            + "&observation_severity=" + severity
        )

    choice_filters = "".join(
        '<a class="button ' + ("primary" if item == observation_choice else "")
        + '" href="' + href(item, observation_activation, observation_severity)
        + '">' + item + "</a>"
        for item in ("ALL", "LIVE", "PAPER", "IGNORE")
    )
    activation_filters = "".join(
        '<a class="button ' + ("primary" if item == observation_activation else "")
        + '" href="' + href(observation_choice, item, observation_severity)
        + '">' + item + "</a>"
        for item in ("ALL", "ACTIVATED", "BLOCKED")
    )
    severity_filters = "".join(
        '<a class="button ' + ("primary" if item == observation_severity else "")
        + '" href="' + href(observation_choice, observation_activation, item)
        + '">' + item + "</a>"
        for item in ("ALL", "GREEN", "AMBER", "RED")
    )
    controls = (
        '<div class="journal-filters">' + choice_filters + "</div>"
        '<div class="journal-filters">' + activation_filters + "</div>"
        '<div class="journal-filters">' + severity_filters + "</div>"
    )
    counts = (
        ("Observations", len(observations)),
        ("Live", sum(item.record.choice.value == "LIVE" for item in observations)),
        ("Paper", sum(item.record.choice.value == "PAPER" for item in observations)),
        ("Ignore", sum(item.record.choice.value == "IGNORE" for item in observations)),
        ("Activated", sum(item.source.activation.disposition.value == "ACTIVATED" for item in observations)),
        ("Blocked", sum(item.source.activation.disposition.value.startswith("BLOCKED_") for item in observations)),
    )
    count_view = '<div class="status-strip">' + "".join(
        '<div class="status-item"><span>' + escape(label) + '</span><strong>'
        + str(value) + "</strong></div>" for label, value in counts
    ) + "</div>"
    if not observations:
        rows = '<div class="workflow-empty">No prospective Sponsor observation records match this view.</div>'
    else:
        cards = []
        for item in observations:
            source = item.source
            snapshot = source.snapshot
            activation = source.activation
            objective = tuple(
                link for link in item.links
                if link.kind in {
                    ObservationLinkKind.KR380_ENTRY_OUTCOME,
                    ObservationLinkKind.KR390_OBJECTIVE_MODEL,
                    ObservationLinkKind.OBJECTIVE_MODEL_OUTCOME,
                }
            )
            position = tuple(
                link for link in item.links
                if link.kind in {
                    ObservationLinkKind.SPONSOR_POSITION,
                    ObservationLinkKind.SPONSOR_POSITION_OUTCOME,
                }
            )
            headline = " · ".join((
                source.decision.choice.value,
                snapshot.canonical_instrument,
                snapshot.direction.value,
                snapshot.step31_severity.value,
            ))
            primary = "".join(
                '<div><span>' + escape(label) + '</span><strong>'
                + escape(value) + "</strong></div>"
                for label, value in (
                    ("Decision", source.decision.choice.value),
                    ("Activation", activation.disposition.value),
                    ("KR-370", snapshot.kr370_state),
                    ("Decision time", snapshot.snapshot_timestamp.isoformat()),
                    ("Objective outcome", "AVAILABLE" if item.objective_outcome_available else "UNAVAILABLE"),
                    ("Sponsor-position outcome", "AVAILABLE" if item.sponsor_position_outcome_available else "UNAVAILABLE"),
                )
            )
            decision_detail = "".join(
                '<div class="v1-context-row"><span>' + escape(label) + '</span><strong>'
                + escape(value) + "</strong></div>"
                for label, value in (
                    ("Run", snapshot.native_run_identity),
                    ("Assessment SHA", snapshot.native_assessment_sha256),
                    ("Snapshot", snapshot.snapshot_identity),
                    ("Snapshot SHA", snapshot.integrity_sha256),
                    ("KR-370 decision", snapshot.kr370_state),
                    *tuple(
                        (identity, state)
                        for identity, state in snapshot.kr370_criteria
                    ),
                    ("Decision time", snapshot.snapshot_timestamp.isoformat()),
                    ("Entry", "UNAVAILABLE" if snapshot.entry is None else _number(snapshot.entry)),
                    ("Stop", "UNAVAILABLE" if snapshot.stop is None else _number(snapshot.stop)),
                    ("Target", "UNAVAILABLE" if snapshot.target is None else _number(snapshot.target)),
                    ("Risk distance", "UNAVAILABLE" if snapshot.risk_distance is None else _number(snapshot.risk_distance)),
                    ("Reward distance", "UNAVAILABLE" if snapshot.reward_distance is None else _number(snapshot.reward_distance)),
                    ("R:R", "UNAVAILABLE" if snapshot.risk_reward_ratio is None else _number(snapshot.risk_reward_ratio)),
                    ("Step-31 severity", snapshot.step31_severity.value),
                    ("Step-31 warnings", " · ".join(snapshot.step31_warnings) or "NONE"),
                    ("Risk at decision", snapshot.risk_state),
                    ("Risk identity", snapshot.risk_identity or "UNAVAILABLE"),
                    ("Sponsor decision", source.decision.choice.value),
                    ("Sponsor reason", "UNAVAILABLE" if source.decision.sponsor_reason is None else source.decision.sponsor_reason.value),
                    ("Activation disposition", activation.disposition.value),
                    ("MCX supporting context", snapshot.mcx_supporting_context_identity or "NOT APPLICABLE / UNAVAILABLE"),
                )
            )
            objective_detail = "".join(
                '<div class="v1-context-row"><span>' + escape(link.kind.value) + '</span><strong>'
                + escape(link.source_state + " · " + link.source_record_identity) + "</strong></div>"
                for link in objective
            ) or '<p>Objective-model evidence is unavailable. No outcome is manufactured.</p>'
            position_detail = "".join(
                '<div class="v1-context-row"><span>' + escape(link.kind.value) + '</span><strong>'
                + escape(link.source_state + " · " + link.source_record_identity) + "</strong></div>"
                for link in position
            ) or '<p>Sponsor Position evidence is unavailable or not applicable.</p>'
            cards.append(
                '<section class="native-trade-plan"><h3>' + escape(headline) + "</h3>"
                '<div class="native-trade-plan-grid">' + primary + "</div>"
                '<details class="native-diagnostics"><summary>DECISION-TIME EVIDENCE</summary>'
                + decision_detail + "</details>"
                '<details class="native-diagnostics"><summary>OBJECTIVE MODEL</summary>'
                + objective_detail + "</details>"
                '<details class="native-diagnostics"><summary>SPONSOR POSITION</summary>'
                + position_detail + "</details></section>"
            )
        rows = "".join(cards)
    return (
        '<section class="native-review-section"><h2>OBSERVATION RESEARCH</h2>'
        '<p>Prospective Sponsor decisions and later factual links. No performance analytics or methodology authority.</p>'
        + controls + count_view + rows + "</section>"
        '<details class="native-diagnostics"><summary>EXISTING STEP-33 TRADING JOURNAL</summary>'
        '<p>The historical completed-trade Journal remains independently governed below.</p></details>'
    )


def _native_active_lifecycle(
    snapshot: ActiveTradeLifecycleSnapshot | None,
    active_monitoring_position_ids: tuple[str, ...] = (),
) -> str:
    if snapshot is None or not snapshot.active:
        return '<div class="workflow-empty">No Native Paper or Live positions are currently active.</div>'
    notifications = {item.notification_id: item for item in snapshot.notifications}
    cards = []
    for position in snapshot.active:
        label = {
            ActiveLifecycleState.PAPER_ARMED: "PAPER · WAITING FOR ENTRY",
            ActiveLifecycleState.PAPER_ACTIVE: "PAPER ACTIVE",
            ActiveLifecycleState.LIVE_ACTIVE: "LIVE ACTIVE",
            ActiveLifecycleState.EVENT_UNRESOLVED: "EVENT UNRESOLVED",
            ActiveLifecycleState.MONITORING_UNAVAILABLE: "MONITORING UNAVAILABLE",
        }.get(position.state, position.state.value.replace("_", " "))
        current = "—" if position.last_observed_price is None else "₹" + _number(position.last_observed_price)
        actual = "—" if position.actual_entry is None else "₹" + _number(position.actual_entry)
        pnl = "—"
        if position.actual_entry is not None and position.last_observed_price is not None:
            move = (
                position.last_observed_price - position.actual_entry
                if position.direction.value == "LONG"
                else position.actual_entry - position.last_observed_price
            )
            pnl = "₹" + _number(move * position.underlying_quantity)
        alerts = "".join(
            '<div class="action-required">' + escape(notifications[item].message) + '</div>'
            for item in position.outstanding_notification_ids if item in notifications
        )
        values = "".join(
            '<div><span>' + escape(name) + '</span><strong>' + escape(value) + '</strong></div>'
            for name, value in (
                ("Instrument", position.canonical_instrument + " · " + position.direction.value),
                ("Lots", str(position.lots)), ("Model Entry", "₹" + _number(position.model_entry)),
                ("Actual Entry", actual), ("Stop", "₹" + _number(position.stop)),
                ("Target", "₹" + _number(position.target)), ("Current", current),
                ("Unrealised P&L", pnl), ("Model R:R", "1 : " + _number(position.model_risk_reward)),
            )
        )
        controls = ""
        if position.state is ActiveLifecycleState.PAPER_ACTIVE:
            controls = (
                '<form method="post" action="/swing/v1/native-lifecycle/paper-exit?position='
                + escape(position.position_id) + '"><button type="submit">EXIT</button></form>'
            )
        elif position.state is ActiveLifecycleState.LIVE_ACTIVE:
            controls = (
                '<form method="post" action="/swing/v1/native-lifecycle/live-exit?position='
                + escape(position.position_id) + '"><label>Actual broker Exit'
                '<input required name="actual_exit" inputmode="decimal"></label>'
                '<label>Reason<select name="reason">'
                '<option>SPONSOR_EXIT_AFTER_TARGET_NOTIFICATION</option>'
                '<option>SPONSOR_EXIT_AFTER_STOP_NOTIFICATION</option>'
                '<option>SPONSOR_EXIT_AFTER_INVALIDATION_NOTIFICATION</option>'
                '<option>SPONSOR_MANUAL_EXIT</option></select></label>'
                '<button type="submit">RECORD EXIT</button></form>'
            )
        monitoring = (
            '<div class="analysis-decision">LIVE MONITORING · SL + TARGET</div>'
            if position.position_id in active_monitoring_position_ids
            else '<div class="analysis-decision">MONITORING NOT ACTIVE</div>'
        )
        cards.append(
            '<section class="native-trade-plan"><h3>' + escape(label) + '</h3>'
            '<div class="native-trade-plan-grid">' + values + '</div>'
            + monitoring + alerts + controls + '</section>'
        )
    return "".join(cards)


def _native_closed_lifecycle(snapshot: ActiveTradeLifecycleSnapshot | None) -> str:
    if snapshot is None or not snapshot.closures:
        return '<div class="workflow-empty">No Native Paper or Live positions have closed.</div>'
    return "".join(
        '<section class="native-trade-plan"><h3>'
        + escape(item.mode.value + " CLOSED · " + item.instrument + " · " + item.direction.value)
        + '</h3><div class="native-trade-plan-grid">'
        + "".join(
            '<div><span>' + escape(label) + '</span><strong>' + escape(value) + '</strong></div>'
            for label, value in (
                ("Model Entry", "₹" + _number(item.model_entry)),
                ("Actual Entry", "₹" + _number(item.actual_entry)),
                ("Actual Exit", "₹" + _number(item.actual_exit)),
                ("Stop", "₹" + _number(item.stop)), ("Target", "₹" + _number(item.target)),
                ("Exit reason", item.exit_reason.value.replace("_", " ")),
                ("P&L", "₹" + _number(item.gross_pnl)),
                ("Result", _number(item.percentage_result) + "%"),
                ("Realised R", _number(item.realised_r) + "R"),
                ("Model R:R", "1 : " + _number(item.model_risk_reward)),
                ("Holding", str(item.holding_duration_seconds) + " seconds"),
            )
        )
        + '</div><p class="why">' + escape(item.commentary) + '</p></section>'
        for item in snapshot.closures
    )


def render_candidate_workspace(
    snapshot: BrowserWorkspaceSnapshot,
    record: BrowserCandidateRecord,
) -> str:
    view = _step32_view_for_record(record)
    if view is None:
        candidate = record.candidate
        body = (
            '<section class="step32-workflow"><div class="step32-head">'
            f'<h2>{escape(candidate.canonical_instrument)} — '
            f'{escape(candidate.direction)}</h2>'
            f'<span class="setup-family">{escape(_operator_setup(candidate.setup_family))}</span>'
            '</div><div class="error"><strong>TRADE PLAN INCOMPLETE</strong><br>'
            f'{escape(_sponsor_reason(candidate.integrity_reason))}</div></section>'
        )
    else:
        body = render_step32_sponsor_workflow(view)
    return _page(
        title=record.candidate.canonical_instrument,
        subtitle="Trade Candidate lifecycle workspace.",
        snapshot=snapshot,
        active_nav="Swing",
        active_tab=(
            "Closed"
            if record.objective_model is not None
            and record.objective_model.state is ObjectiveModelState.CLOSED
            else "Active"
            if record.objective_model is not None
            else "Trade Candidates"
        ),
        body=body,
        back_link='<a class="button" href="/swing/trade-candidates">← Back</a>',
    )


def _workflow_failure(workflow: BrowserStep32Snapshot) -> str:
    if not workflow.synchronization_failure:
        return ""
    return (
        '<div class="error">Trade Candidate production is unavailable. '
        'The review remains preserved and no candidate was created.</div>'
    )


def _workflow_cards(
    records: tuple[BrowserCandidateRecord, ...],
    *,
    empty_message: str,
) -> str:
    if not records:
        return f'<div class="workflow-empty">{escape(empty_message)}</div>'
    cards = []
    for record in records:
        candidate = record.candidate
        view = _step32_view_for_record(record)
        state = "TRADE PLAN INCOMPLETE" if view is None else view.current_state.upper()
        risk = "RISK UNAVAILABLE" if view is None else f"RISK {view.risk}"
        values = "".join(
            '<div><label>' + escape(label) + '</label><strong>'
            + escape(_optional_decimal(value)) + '</strong></div>'
            for label, value in (
                ("Entry", candidate.entry_price),
                ("Stop", candidate.stop_price),
                ("Target", candidate.target_price),
                ("R:R", candidate.risk_reward_ratio),
            )
        )
        close = (
            '<div><label>Close</label><strong>'
            + escape(
                record.objective_model.close_reason.value.replace("_", " ")
                if record.objective_model is not None
                and record.objective_model.close_reason is not None
                else "—"
            )
            + "</strong></div>"
        )
        action = (
            '<div class="action-required">ACTION REQUIRED — CHECK / MANAGE YOUR LIVE POSITION</div>'
            if record.action_required
            else ""
        )
        cards.append(
            '<article class="workflow-card"><div class="workflow-card-head">'
            f'<h2>{escape(candidate.canonical_instrument)} — {escape(candidate.direction)}</h2>'
            f'<span class="setup-family">{escape(_operator_setup(candidate.setup_family))}</span>'
            f'<span class="workflow-card-state">{escape(state)}</span></div>'
            f'<div class="workflow-card-grid">{values}{close}</div>'
            f'<div class="muted">{escape(risk)}</div>{action}'
            '<div class="workflow-card-actions"><a class="button" href="/swing/trade-candidates/'
            f'{escape(record.browser_key)}">Open Workspace</a></div></article>'
        )
    return '<div class="workflow-list">' + "".join(cards) + "</div>"


def _step32_view_for_record(
    record: BrowserCandidateRecord,
) -> Step32SponsorWorkflowView | None:
    if record.risk is None or record.lifecycle is None:
        return None
    return build_step32_sponsor_workflow_view(
        record.candidate,
        record.risk,
        record.lifecycle,
        decision=record.sponsor_decision,
        model=record.objective_model,
        position=record.sponsor_position,
        monitoring_state=record.monitoring_state,
        readiness_state=record.readiness_state,
        readiness_reason=record.readiness_reason,
    )


def _optional_decimal(value: Decimal | None) -> str:
    return "—" if value is None else _decimal_number(value)


def _sponsor_reason(value: str) -> str:
    return value.replace("_", " ").strip() or "REVIEW REQUIRED"


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


def _mcx_context_strip(snapshot: McxSupportingContextSnapshot) -> str:
    required = snapshot.trading_date_required
    parts = [
        '<div class="mcx-context-strip"><strong>MCX CONTEXT · SUPPORTING ONLY</strong>',
        '<span>' + escape(snapshot.trading_date.isoformat()) + '</span>',
    ]
    for slot in snapshot.slots:
        statuses = {
            item.family.value: (
                f"VALID REV{item.revision}" if item.revision is not None
                else "IMAGE STAGED" if item.image_staged
                else item.availability.value.replace("_", " ")
            ) for item in slot.families
        }
        slot_query = urlencode({"slot": slot.slot.value})
        targets = ""
        for family_status in slot.families:
            family = family_status.family
            query = urlencode({"slot": slot.slot.value, "family": family.value})
            target_id = f"mcx-context-{slot.slot.value.lower()}-{family.value.lower()}"
            file_id = f"{target_id}-file"
            if family_status.image_sha256 is None:
                content = (
                    '<div><span class="paste-key">⌘V</span>'
                    '<strong>Click, then paste</strong>'
                    '<small>TradingView PNG or JPEG</small></div>'
                )
                actions = ""
                received_class = ""
            else:
                preview = urlencode({
                    "slot": slot.slot.value,
                    "family": family.value,
                    "sha256": family_status.image_sha256,
                })
                content = (
                    f'<img src="/swing/mcx-context/image-preview?{escape(preview)}" alt="">'
                    '<div class="chart-received"><strong>Image received</strong>'
                    f'<span>{escape(family.value.title())} context</span></div>'
                )
                actions = (
                    f'<button class="replace-chart" type="button" data-target="{target_id}">Replace</button>'
                    f'<form method="post" action="/swing/mcx-context/image/remove?{escape(query)}">'
                    '<button type="submit">Remove</button></form>'
                )
                received_class = " received"
            targets += "".join((
                '<div class="chart-slot"><h3>', escape(family.value),
                ' CONTEXT</h3>',
                f'<div id="{target_id}" class="chart-paste-target{received_class}" ',
                'role="button" tabindex="0" ',
                f'aria-label="Paste {escape(family.value.title())} TradingView context image" ',
                f'data-upload-url="/swing/mcx-context/image?{escape(query)}">{content}</div>',
                '<div class="chart-slot-actions">', actions,
                f'<label class="file-choice" for="{file_id}">Choose File</label>',
                f'<input id="{file_id}" class="chart-file" type="file" ',
                'accept="image/png,image/jpeg" ',
                f'data-target="{target_id}"></div></div>',
            ))
        open_preparation = (
            " open"
            if any(item.image_staged for item in slot.families)
            and not all(item.revision is not None for item in slot.families)
            else ""
        )
        parts.append(
            '<span class="mcx-context-slot"><b>' + slot.slot.value + '</b>'
            '<span class="mcx-context-status">Metals ' + escape(statuses["METALS"])
            + ' · Energy ' + escape(statuses["ENERGY"]) + '</span>'
            f'<details class="mcx-context-prep"{open_preparation}><summary>PREPARE</summary>'
            '<div class="mcx-context-targets">' + targets + '</div></details>'
            '<form method="post" action="/swing/mcx-context/question-pack?'
            + escape(slot_query) + '"><button type="submit"'
            + ("" if required and all(item.image_staged for item in slot.families) else " disabled")
            + '>CREATE PDF</button></form>'
            '<form method="post" action="/swing/mcx-context/answer?'
            + escape(slot_query) + '"><button type="submit"'
            + ("" if required and slot.question_pack is not None else " disabled")
            + '>UPLOAD ANSWER</button></form>'
            + _mcx_context_failure(slot.last_error)
            + '</span>'
        )
    parts.append('</div>')
    return "".join(parts)


def _mcx_context_failure(error) -> str:  # type: ignore[no-untyped-def]
    if error is None:
        return ""
    if (
        error.family is None
        or error.panel_id is None
        or error.failed_field is None
        or error.expected is None
        or error.observed is None
    ):
        return (
            '<span class="mcx-context-error"><strong>MCX CONTEXT INVALID</strong>'
            '<span>' + escape(error.machine_code.replace("_", " "))
            + '</span></span>'
        )
    return (
        '<span class="mcx-context-error"><strong>MCX CONTEXT INVALID</strong>'
        '<span>' + escape(error.family.value) + ' · ' + escape(error.panel_id)
        + ' · ' + escape(error.failed_field.replace("_", " "))
        + ' MISMATCH</span><span>Expected: ' + escape(error.expected)
        + '</span><span>Observed: ' + escape(error.observed) + '</span></span>'
    )


def _mcx_context_details(
    canonical_instrument: str,
    record: McxSupportingContextRecord | None,
) -> str:
    family = MCX_CONTEXT_INSTRUMENT_FAMILIES.get(canonical_instrument)
    if family is None:
        return ""
    if record is None:
        return (
            '<section class="analysis-section"><h2>DAILY SUPPORTING CONTEXT</h2>'
            '<p>NOT AVAILABLE AT ASSESSMENT TIME</p>'
            '<p>SUPPORTING EVIDENCE ONLY · NO KR-370 CONSEQUENCE.</p></section>'
        )
    rows = "".join(
        '<tr><td>' + escape(item.panel_id) + '</td><td>'
        + escape(item.observed_identity) + '</td><td>'
        + escape(item.observed_timeframe) + '</td><td>'
        + escape(item.direction.value) + '</td><td>'
        + escape(item.structural_condition.value) + '</td><td>'
        + escape(item.evidence_quality.value) + '</td></tr>'
        for item in record.panels
    )
    alignment = ""
    if record.wti_brent_alignment is not None:
        alignment = (
            '<p>WTI / Brent: <strong>' + record.wti_brent_alignment.value
            + '</strong> · Natural Gas 1D / 4H: <strong>'
            + record.natural_gas_alignment.value + '</strong></p>'
        )
    return (
        '<details class="analysis-section"><summary>DAILY SUPPORTING CONTEXT · '
        + record.family.value + ' · ' + record.slot.value + ' · REV'
        + str(record.revision) + '</summary><p>Imported '
        + escape(record.imported_at.isoformat()) + '</p>'
        '<table class="analysis-table"><thead><tr><th>Panel</th><th>Identity</th>'
        '<th>Timeframe</th><th>Direction</th><th>Structure</th><th>Quality</th>'
        '</tr></thead><tbody>' + rows + '</tbody></table>' + alignment
        + '<p>SUPPORTING EVIDENCE ONLY · NO KR-370 CONSEQUENCE.</p></details>'
    )


def render_v1_review(
    snapshot: BrowserWorkspaceSnapshot,
    review: V1ReviewWorkflowSnapshot,
    native_review: NativeReviewWorkflowSnapshot | None = None,
    visual_v3_live: SwingVisualV3LiveSnapshot | None = None,
    mcx_context: McxSupportingContextSnapshot | None = None,
    relative_context: RelativeContextRun | None = None,
) -> str:
    if (
        native_review is not None
        and native_review.state is NativeReviewRunState.REVIEW_REQUIRED
    ):
        body = (
            _analysis_run_strip(snapshot)
            + _native_review_requirements(
                native_review, visual_v3_live, relative_context
            )
        )
    elif review.layer1_run is None:
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
        if analysis_allowed:
            body += _chart_analysis_status_script()
    if (
        native_review is not None
        and native_review.state is NativeReviewRunState.NOT_PREPARED
        and snapshot.swing_analysis_run_identity is not None
    ):
        body = (
            '<form class="native-review-control" method="post" '
            'action="/swing/v1/native-review-refresh">'
            '<button class="primary">REFRESH REVIEW</button></form>'
            + body
        )
    if mcx_context is not None:
        body = _mcx_context_strip(mcx_context) + body
    body += _chart_upload_script()
    return _page(
        title="Review",
        subtitle="Copy a chart image, click its target, and paste with ⌘V.",
        snapshot=snapshot,
        active_nav="Swing",
        active_tab="Review",
        body=body,
    )


def _native_review_requirements(
    review: NativeReviewWorkflowSnapshot,
    visual_v3_live: SwingVisualV3LiveSnapshot | None = None,
    relative_context: RelativeContextRun | None = None,
) -> str:
    cards = ""
    slot_index = 0
    chart_ready = sum(
        1
        for requirement in review.requirements
        if all(
            not package.missing_required_timeframes
            for package in review.chart_packages
            if package.binding.native_assessment_sha256
            == requirement.thesis.native_assessment_sha256
            and package.binding.subject_kind == "NATIVE"
        )
        and any(
            package.binding.native_assessment_sha256
            == requirement.thesis.native_assessment_sha256
            and package.binding.subject_kind == "NATIVE"
            for package in review.chart_packages
        )
    )
    batch = (
        '<div class="native-analysis-all"><div><strong>Native Review</strong>'
        f'<span>{chart_ready} chart-complete candidate(s)</span></div>'
        '<div class="chart-slot-actions">'
        '<form method="post" action="/swing/v1/native-review-refresh">'
        '<button type="submit">REFRESH REVIEW</button></form>'
        '<form method="post" action="/swing/v1/native-review-pack">'
        '<button class="primary" type="submit"'
        + ('' if chart_ready else ' disabled title="At least one candidate needs a valid composite chart"')
        + '>CREATE ALL REVIEW PDF</button></form></div></div>'
    )
    if review.refresh_status is not None:
        batch += '<div class="review-note"><strong>' + escape(review.refresh_status) + '</strong></div>'
    if visual_v3_live is not None:
        v3_pack = (
            visual_v3_live.review_pack if visual_v3_live.current_run else None
        )
        v3_import = (
            visual_v3_live.answer_imports[-1]
            if visual_v3_live.answer_imports and visual_v3_live.current_run
            else None
        )
        if v3_pack is None:
            pdf_controls = (
                '<div class="native-analysis-all pdf-review-control"><div>'
                '<strong>PDF VISUAL REVIEW · V3</strong>'
                '<span>NO V3 REVIEW PACK · QUESTION SET '
                + escape(VISUAL_QUESTION_SET_V3_VERSION)
                + '</span></div></div>'
            )
        else:
            status = (
                "WAITING FOR CHART ANALYST"
                if v3_import is None
                else v3_import.state.value.replace("_", " ")
            )
            scope = (
                v3_pack.candidate_packs[0].canonical_instrument + " ONLY"
                if v3_pack.scope == "INDIVIDUAL"
                else "ALL ELIGIBLE CANDIDATES"
            )
            pdf_controls = (
                '<div class="native-analysis-all pdf-review-control"><div>'
                '<strong>PDF VISUAL REVIEW · V3 CURRENT REVIEW PACK</strong><span>'
                + escape(v3_pack.question_filename)
                + '<br>' + escape(v3_pack.question_set_identity)
                + ' ' + escape(v3_pack.question_set_version)
                + '<br>SCOPE: ' + escape(scope)
                + '<br>STATUS: ' + escape(status) + '</span></div>'
                '<form method="post" action="/swing/v1/native-review-answer">'
                '<button class="primary" type="submit">UPLOAD ANSWER</button>'
                '</form></div>'
            )
            if v3_pack.skipped:
                pdf_controls += (
                    '<div class="review-note"><strong>V3 REVIEW PACK CREATED · '
                    + str(len(v3_pack.candidate_packs))
                    + ' CANDIDATE(S) INCLUDED</strong><br>SKIPPED: '
                    + ' · '.join(
                        escape(instrument + " — " + reason)
                        for instrument, reason in v3_pack.skipped
                    ) + '</div>'
                )
            if v3_import is not None and not v3_import.consumed:
                failure_title = (
                    "V3 ANSWER IMPORT FAILED"
                    if v3_import.state
                    is VisualV3AnswerImportState.ANSWER_IMPORT_FAILED
                    else "V3 ANSWER PACK REJECTED"
                )
                pdf_controls += (
                    '<div class="review-note batch-preflight"><strong>'
                    + failure_title + '</strong><br>'
                    + escape(" · ".join(v3_import.reasons)) + '</div>'
                )
    else:
        pack = review.review_pack_record
        latest_import = review.answer_import_records[-1] if review.answer_import_records else None
        if pack is None:
            pdf_controls = (
                '<div class="native-analysis-all pdf-review-control"><div>'
                '<strong>PDF VISUAL REVIEW</strong><span>NO REVIEW PACK</span></div></div>'
            )
        else:
            answer_status = (
                "WAITING FOR CHART ANALYST"
                if latest_import is None
                else latest_import.state.value.replace("_", " ")
            )
            if review.review_pack_superseded:
                answer_status = "SUPERSEDED FOR CURRENT REVIEW"
            scope = (
                pack.candidates[0].canonical_instrument + " ONLY"
                if review.review_pack_scope == "INDIVIDUAL"
                else "ALL ELIGIBLE CANDIDATES"
            )
            pdf_controls = (
                '<div class="native-analysis-all pdf-review-control"><div>'
                '<strong>PDF VISUAL REVIEW · CURRENT REVIEW PACK</strong>'
                '<span>' + escape(pack.question_filename)
                + '<br>SCOPE: ' + escape(scope)
                + '<br>STATUS: ' + escape(answer_status) + '</span></div>'
                '<form method="post" action="/swing/v1/native-review-answer">'
                '<button class="primary" type="submit"'
                + (' disabled title="Create a current Review Pack first"' if review.review_pack_superseded else '')
                + '>UPLOAD ANSWER</button></form></div>'
            )
            if review.review_pack_skipped:
                pdf_controls += (
                    '<div class="review-note"><strong>REVIEW PACK CREATED · '
                    + str(len(pack.candidates)) + ' CANDIDATE(S) INCLUDED</strong><br>SKIPPED: '
                    + ' · '.join(
                        escape(instrument + " — " + reason)
                        for instrument, reason in review.review_pack_skipped
                    ) + '</div>'
                )
            if latest_import is not None and not latest_import.consumed:
                pdf_controls += (
                    '<div class="review-note batch-preflight"><strong>ANSWER PACK REJECTED</strong><br>'
                    + escape(" · ".join(latest_import.validation_reasons))
                    + '</div>'
                )
    batch += pdf_controls
    for requirement in sorted(
        review.requirements,
        key=lambda value: value.canonical_instrument,
    ):
        thesis = requirement.thesis
        relative = (
            None
            if relative_context is None
            or relative_context.run_identity != thesis.native_run_identity
            else relative_context.record(thesis.canonical_instrument)
        )
        reference = requirement.mcx_reference
        reference_result = next(
            (
                item for item in review.reference_results
                if reference is not None and item.requirement == reference
            ),
            None,
        )
        visual_results = tuple(
            item for item in review.visual_v2_results
            if item.native_run_identity == requirement.native_run_identity
            and item.native_assessment_sha256 == thesis.native_assessment_sha256
            and item.native_canonical_instrument == thesis.canonical_instrument
        )
        validation_diagnostics = tuple(
            item for item in review.visual_v2_diagnostics
            if item.native_run_identity == requirement.native_run_identity
            and item.canonical_instrument == thesis.canonical_instrument
        )
        readiness = next(
            (
                item for item in review.readiness_records
                if item.native_assessment_sha256 == thesis.native_assessment_sha256
            ),
            None,
        )
        trade_plan = max(
            (
                item for item in review.trade_plans
                if item.native_assessment_sha256 == thesis.native_assessment_sha256
                and item.readiness_record_sha256
                == (readiness.result_sha256 if readiness is not None else "")
            ),
            key=lambda item: (item.created_at, item.trade_plan_id),
            default=None,
        )
        sponsor_initiation = next(
            (
                item for item in review.sponsor_initiations
                if item.decision is not None
                and trade_plan is not None
                and item.decision.trade_plan_id == trade_plan.trade_plan_id
            ),
            None,
        )
        outcome = next(
            (
                item for item in review.analysis_outcomes
                if item.canonical_instrument == thesis.canonical_instrument
            ),
            None,
        )
        anchor = (
            f"{thesis.operative_anchor_identity.replace('_', ' ')} · "
            f"{thesis.operative_anchor_price:g}"
        )
        packages = tuple(
            item for item in review.chart_packages
            if item.binding.native_assessment_sha256
            == thesis.native_assessment_sha256
        )
        visible_packages = tuple(
            item for item in packages
            if not (
                reference is not None
                and item.binding.subject_kind == "REFERENCE"
            )
        )
        chart_intake = (
            '<h3>TRADINGVIEW CHARTS</h3><div class="native-chart-grid'
            + (' single' if len(visible_packages) == 1 else '')
            + '">'
        )
        for package in packages:
            subject = package.binding.subject_kind.lower()
            if reference is not None and subject == "reference":
                # One immutable composite is shared by the Native and approved
                # reference roles; the second role is evidence, not a second
                # Sponsor upload control.
                continue
            revision = (
                package.active_revisions[0]
                if package.active_revisions else None
            )
            subject_results = tuple(
                item for item in visual_results
                if (
                    item.subject_kind.value.startswith("NATIVE")
                    if subject == "native"
                    else item.subject_kind.value.startswith("REFERENCE")
                )
            )
            if reference is not None and subject == "native":
                subject_results = visual_results
            slot_index += 1
            chart_intake += _native_chart_slot(
                requirement.canonical_instrument,
                package.binding.required_timeframes,
                subject,
                package.binding.chart_subject_identity,
                revision,
                subject_results,
                slot_index,
                shared_reference=reference,
            )
        chart_intake += '</div>'
        native_packages = tuple(
            item for item in packages if item.binding.subject_kind == "NATIVE"
        )
        all_received = bool(native_packages) and all(
            not item.missing_required_timeframes for item in native_packages
        )
        query = urlencode({"instrument": requirement.canonical_instrument})
        pdf_action = (
            '<form class="validate-one" method="post" '
            f'action="/swing/v1/native-review-pack?{escape(query)}">'
            '<button class="primary" type="submit"'
            + ('' if all_received else ' disabled title="Paste the required composite chart first"')
            + ('>CREATE PDF</button></form>' if all_received else '>CHART REQUIRED</button></form>')
        )
        v3_complete = (
            visual_v3_live is not None
            and thesis.canonical_instrument
            in visual_v3_live.completed_instruments
        )
        review_state = (
            "V3 REVIEW EVIDENCE IMPORTED" if v3_complete
            else "REVIEW EVIDENCE IMPORTED" if readiness is not None
            else "CHART READY" if all_received
            else "CHART REQUIRED"
        )
        review_class = (
            "analyzed" if v3_complete or readiness is not None or all_received else ""
        )
        direction_class = (
            "direction-long" if thesis.direction.value == "LONG"
            else "direction-short"
        )
        cards += (
            '<article class="chart-intake-card">'
            '<div class="chart-intake-head"><h2>'
            + escape(thesis.canonical_instrument)
            + '</h2><span class="native-direction-badge '
            + direction_class + '">' + escape(thesis.direction.value)
            + '</span><span class="analysis-state ' + review_class + '">'
            + escape(review_state) + '</span></div>'
            '<div class="v1-context-result">'
            '<div class="v1-context-row"><span>Opportunity</span><strong>'
            + escape(thesis.opportunity_identity.value.replace("_", " "))
            + '</strong></div><div class="v1-context-row"><span>Native context</span><strong>'
            + escape(f"{thesis.weekly_state.value} · {thesis.daily_state.value}".replace("_", " "))
            + '<br>'
            + escape(f"{thesis.four_hour_state.value} · {thesis.one_hour_state.value}".replace("_", " "))
            + '</strong></div>'
            + _relative_context_review(relative, thesis.direction.value)
            + (
                ''
                if reference is None
                else '<div class="v1-context-row"><span>Reference</span><strong>'
                + escape(f"{reference.reference_market.value} · {reference.reference_symbol}")
                + '</strong></div><div class="v1-context-row"><span>Reference status</span><strong>'
                + escape(
                    reference_result.status.value
                    if reference_result is not None else "REQUIRED"
                )
                + '</strong></div><div class="v1-context-row"><span>Reference evidence</span><strong>'
                + escape(
                    "RECEIVED"
                    if reference_result is not None
                    and reference_result.status.value in {
                        "RECEIVED", "ANALYZED"
                    }
                    else "UNAVAILABLE"
                )
                + '</strong></div><div class="v1-context-row"><span>Reference consequence</span><strong>'
                + escape(
                    reference_result.evidence_state.value
                    if reference_result is not None else "UNAVAILABLE"
                )
                + '</strong></div><div class="v1-context-row"><span>Binding</span><strong>'
                + escape(
                    reference_result.binding_status
                    if reference_result is not None else "SAME RUN REQUIREMENT"
                )
                + '</strong></div>'
            )
            + chart_intake
            + pdf_action
            + (
                ""
                if v3_complete else
                _native_one_minute_review(
                    readiness, requirement, visual_results, reference_result
                )
                if readiness is not None else
                _visual_v2_diagnostics(visual_results)
            )
            + (
                _native_trade_plan(
                    trade_plan,
                    step32_eligible=trade_plan.trade_plan_id in review.step32_eligible_plan_ids,
                    initiation=sponsor_initiation,
                )
                if trade_plan is not None else ""
            )
            + _native_analysis_details(
                requirement, packages, visual_results, anchor,
                validation_diagnostics, outcome,
            )
            + '</div></article>'
        )
    return (
        '<div class="shadow-banner">NATIVE PROBABLE · REVIEW INPUT AUTHORITY · '
        'NO TRADE OR EXECUTION AUTHORITY</div>'
        + batch + '<div class="chart-intake-list">' + cards + '</div>'
    )


def _native_chart_slot(
    instrument,
    required_timeframes,
    subject,
    subject_identity,
    revision,
    results,
    slot_index,
    *,
    shared_reference=None,
) -> str:  # type: ignore[no-untyped-def]
    query = urlencode({
        "instrument": instrument,
        "subject": subject,
    })
    target_id = f"native-chart-slot-{slot_index}"
    file_id = f"native-chart-file-{slot_index}"
    panel_labels = (
        ("COMEX 1D", "COMEX 4H", "COMEX 1H", f"MCX {instrument} 1H")
        if shared_reference is not None and subject == "native"
        else tuple(
            "1D" if item.value == "DAILY" else item.value
            for item in required_timeframes
        )
    )
    required = " · ".join(panel_labels)
    chart_label = (
        f"{instrument} TRADINGVIEW COMPOSITE"
        if shared_reference is not None and subject == "native"
        else "TRADINGVIEW 4-CHART IMAGE"
        if subject == "native"
        else "REFERENCE COMPOSITE IMAGE"
    )
    if revision is None:
        content = (
            '<div><span class="paste-key">⌘V</span><strong>PASTE / UPLOAD CHART</strong>'
            f'<span>{escape(chart_label)} · MISSING</span>'
            f'<span>Required panels: {escape(required)}</span></div>'
        )
        actions = ""
        received_class = ""
    else:
        preview = urlencode({
            "instrument": instrument,
            "subject": subject,
            "sha256": revision.sha256,
        })
        status = "RECEIVED"
        panel_statuses = []
        for label in panel_labels:
            lookup_label = label.rsplit(" ", 1)[-1]
            reference_panel = label.startswith("COMEX ") or label.startswith("NYMEX ")
            result = next(
                (
                    item for item in results
                    if item.timeframe.value == lookup_label
                    and item.chart_revision_sha256 == revision.sha256
                    and (
                        item.subject_kind.value.startswith("REFERENCE")
                        if reference_panel
                        else item.subject_kind.value.startswith("NATIVE")
                    )
                ),
                None,
            )
            if result is None:
                continue
            validation = next(
                item for item in result.observations
                if item.question_id.value == "VISUAL_CHART_VALIDATION"
            )
            state = {
                "OBSERVED": "VALID",
                "PARTIAL": "PARTIAL",
                "INVALID": "INVALID",
                "UNAVAILABLE": "PARTIAL",
                "NOT_VISIBLE": "PARTIAL",
                "NOT_APPLICABLE": "INVALID",
            }[validation.observation_status.value]
            panel_statuses.append((label, state))
        if panel_statuses:
            states = {state for _, state in panel_statuses}
            status = (
                "ANALYZED · INVALID" if "INVALID" in states
                else "ANALYZED · PARTIAL"
                if len(panel_statuses) != len(panel_labels) or "PARTIAL" in states
                else "ANALYZED · VALID"
            )
        panel_summary = (
            " · ".join(f"{label} {state}" for label, state in panel_statuses)
            if panel_statuses else f"Required panels: {required}"
        )
        content = (
            f'<img src="/swing/v1/native-chart-preview?{escape(preview)}" alt="">'
            f'<div class="chart-received"><strong>{escape(chart_label)} · {escape(status)}</strong>'
            f'<span>{escape(subject_identity)}</span>'
            f'<span>{escape(panel_summary)}</span></div>'
        )
        actions = (
            f'<button class="replace-chart" type="button" data-target="{target_id}">Replace</button>'
            f'<form method="post" action="/swing/v1/native-chart/remove?{escape(query)}">'
            '<button type="submit">Remove</button></form>'
        )
        received_class = " received"
    return (
        '<div class="chart-slot">'
        f'<div id="{target_id}" class="chart-paste-target{received_class}" '
        'role="button" tabindex="0" '
        f'aria-label="Paste composite {escape(subject)} chart for {escape(instrument)}" '
        f'data-upload-url="/swing/v1/native-chart?{escape(query)}">{content}</div>'
        f'<div class="chart-slot-actions">{actions}'
        f'<label class="file-choice" for="{file_id}">Choose File</label>'
        f'<input id="{file_id}" class="chart-file" type="file" '
        'accept="image/png,image/jpeg,image/webp" '
        f'data-target="{target_id}"></div></div>'
    )


def _native_analysis_details(
    requirement, packages, visual_results, anchor, validation_diagnostics, outcome
) -> str:  # type: ignore[no-untyped-def]
    thesis = requirement.thesis
    revisions = tuple(
        revision
        for package in packages
        for revision in package.active_revisions
    )
    evidence = tuple(item.evidence_sha256 for item in visual_results)
    diagnostic_rows = "".join(
        '<div class="v1-context-row"><span>Validation failure</span><strong>'
        + escape(
            f"{item.timeframe.value} · ATTEMPT {item.attempt} · "
            f"{item.validation_stage.value} · {item.validation_error_code}"
        )
        + '<br>'
        + escape(
            f"{item.structural_path} · expected: {item.expected_constraint} · "
            f"received: {item.received_shape} · {item.retry_disposition}"
        )
        + '</strong></div>'
        for item in validation_diagnostics
    )
    api_status = (
        '<div class="v1-context-row"><span>Historical API status</span><strong>'
        + escape(outcome.state.value.replace("_", " ") + " · " + outcome.sponsor_reason)
        + '</strong></div>'
        if outcome is not None else ''
    )
    return (
        '<details class="native-diagnostics"><summary>ANALYSIS DETAILS / DIAGNOSTICS</summary>'
        '<div class="v1-context-row"><span>Run</span><strong>'
        + escape(thesis.native_run_identity)
        + '</strong></div><div class="v1-context-row"><span>Assessment</span><strong>'
        + escape(thesis.native_assessment_sha256)
        + '</strong></div><div class="v1-context-row"><span>Anchor</span><strong>'
        + escape(anchor)
        + '</strong></div><div class="v1-context-row"><span>Chart revision</span><strong>'
        + escape(" · ".join(item.sha256 for item in revisions) or "NOT RECEIVED")
        + '</strong></div><div class="v1-context-row"><span>V2 evidence</span><strong>'
        + escape(" · ".join(evidence) or "NOT ANALYZED")
        + '</strong></div><div class="v1-context-row"><span>Provider provenance</span><strong>'
        + escape(" · ".join(thesis.provider_provenance))
        + '</strong></div><div class="v1-context-row"><span>Calendar provenance</span><strong>'
        + escape(" · ".join(thesis.calendar_provenance))
        + '</strong></div>'
        + api_status
        + diagnostic_rows
        + '</details>'
    )


def _native_one_minute_review(
    record: NativeLayer2ReadinessRecord,
    requirement,
    visual_results,
    reference_result,
) -> str:  # type: ignore[no-untyped-def]
    thesis = requirement.thesis
    sponsor_readiness = present_native_readiness(
        record, requirement, visual_results
    )
    status = sponsor_readiness.status
    direction = thesis.direction.value.lower()
    opportunity = thesis.opportunity_identity.value.replace("_", " ").lower()
    support = (
        "Independent evidence preserves the Native thesis."
        if record.conditions.thesis_intact.value == "YES"
        else "Required evidence does not establish an intact Native thesis."
    )
    blocking = {
        NativeReadinessState.READY_FOR_TRADE_CONSTRUCTION: "No approved Readiness block remains.",
        NativeReadinessState.WAIT_PULLBACK_DEVELOPING: "The governed 4H pullback remains in development.",
        NativeReadinessState.WAIT_RETEST_DEVELOPING: "The authoritative retest remains unresolved.",
        NativeReadinessState.WAIT_OBSTACLE_CLEARANCE: "An authoritative adverse obstacle still requires resolution.",
        NativeReadinessState.EXTENDED_DO_NOT_CHASE: "The opportunity is materially extended from relevant structure.",
        NativeReadinessState.WEAKENING: "Deterministic progression has meaningfully deteriorated.",
        NativeReadinessState.INVALIDATED: "Authoritative deterministic evidence has failed the current thesis.",
        NativeReadinessState.CONTEXT_INCOMPLETE: (
            "Required chart levels remain unconfirmed."
            if status == "CHART LEVELS NOT CONFIRMED"
            else "More governed Review evidence is required."
        ),
    }[record.readiness]
    facts = [
        f"Operative anchor · {thesis.operative_anchor_identity.replace('_', ' ')} · {thesis.operative_anchor_price:g}",
        f"Native context · {thesis.daily_state.value.replace('_', ' ')} · {thesis.four_hour_state.value.replace('_', ' ')}",
    ]
    if record.conditions.obstacle_condition.value != "NONE":
        evidence = next(
            (item for item in record.conditions.evidence if item.condition_identity == "OBSTACLE"),
            None,
        )
        level = "LEVEL UNAVAILABLE" if evidence is None else _condition_level(evidence)
        facts.append(f"Obstacle · {record.conditions.obstacle_condition.value.replace('_', ' ')} · {level}")
    if record.conditions.pine_condition.value == "CONTRADICTS":
        facts.append("Pine · visible evidence contradicts the Native thesis")
    if record.conditions.reference_condition.value == "CONTRADICTS":
        facts.append("Reference market · contradiction retained for Review")
    facts = facts[:4]
    wait = ""
    if record.readiness in {
        NativeReadinessState.WAIT_PULLBACK_DEVELOPING,
        NativeReadinessState.WAIT_RETEST_DEVELOPING,
        NativeReadinessState.WAIT_OBSTACLE_CLEARANCE,
        NativeReadinessState.EXTENDED_DO_NOT_CHASE,
        NativeReadinessState.WEAKENING,
    }:
        next_item = record.conditions.next_condition
        description = (
            "AUTHORITATIVE REVIEW EVENT UNAVAILABLE · LEVEL UNAVAILABLE"
            if next_item is None
            else f"{next_item.required_event.replace('_', ' ')} · {_next_level(next_item)}"
        )
        wait = (
            '<div class="one-minute-wait"><h3>WHAT AM I WAITING FOR?</h3><strong>'
            + escape(description)
            + '</strong><small>REVIEW AGAIN — NOT AN ENTRY TRIGGER</small></div>'
        )
    next_step = (
        '<p><strong>NEXT: STEP 31 TRADE CONSTRUCTION</strong></p>'
        if record.readiness is NativeReadinessState.READY_FOR_TRADE_CONSTRUCTION
        else ""
    )
    missing = (
        '<p class="missing-evidence">Missing evidence: <strong>'
        + escape(" · ".join(sponsor_readiness.missing_evidence))
        + '</strong></p>'
        if sponsor_readiness.missing_evidence else ""
    )
    blocker_details = (
        '<div class="v1-context-row"><span>Detailed blockers</span><strong>'
        + escape(" · ".join(sponsor_readiness.blocker_details))
        + '</strong></div>'
        if sponsor_readiness.blocker_details else ""
    )
    return (
        '<section class="one-minute"><div><h3>WHY THIS TRADE?</h3><p>'
        + escape(f"Native {direction} {opportunity} opportunity.")
        + '</p><p>' + escape(support + " " + blocking) + '</p></div>'
        '<div><h3>STATUS NOW</h3><strong class="one-minute-status">'
        + escape(status) + '</strong>' + missing + '</div><div><h3>WHAT MATTERS?</h3>'
        '<div class="one-minute-facts">'
        + ''.join('<div class="one-minute-fact">' + escape(item) + '</div>' for item in facts)
        + '</div></div>' + wait + next_step
        + '<details><summary>ANALYSIS DETAILS</summary>'
        + '<div class="v1-context-row"><span>Conditions</span><strong>'
        + escape(" · ".join((
            record.conditions.pullback_condition.value,
            record.conditions.retest_condition.value,
            record.conditions.extension_condition.value,
            record.conditions.deterioration_condition.value,
            record.conditions.failure_condition.value,
            record.conditions.obstacle_condition.value,
        )))
        + '</strong></div><div class="v1-context-row"><span>Reason</span><strong>'
        + escape(record.primary_reason)
        + '</strong></div><div class="v1-context-row"><span>Internal readiness</span><strong>'
        + escape(record.readiness.value)
        + '</strong></div><div class="v1-context-row"><span>Record</span><strong>'
        + escape(record.result_sha256)
        + '</strong></div>'
        + blocker_details
        + _visual_v2_diagnostics(visual_results)
        + (
            "" if reference_result is None else
            '<div class="v1-context-row"><span>Reference</span><strong>'
            + escape(reference_result.evidence_state.value) + '</strong></div>'
        )
        + '</details></section>'
    )


def _native_trade_plan(
    record: TradePlanRecord,
    *,
    step32_eligible: bool = False,
    initiation: SponsorInitiationResult | None = None,
) -> str:
    """Render immutable Step-31 geometry without Sponsor-decision authority."""

    if type(record) is not TradePlanRecord:
        raise TypeError("TRADE_PLAN_RECORD_INVALID")
    if record.geometry_viability is TradePlanStatus.TRADE_PLAN_UNAVAILABLE:
        return (
            '<section class="native-trade-plan"><h3>TRADE PLAN UNAVAILABLE</h3>'
            '<p class="why">' + escape(record.unavailable_reason.value.replace("_", " "))
            + '</p></section>'
        )
    currency = lambda value: "₹" + _number(value)  # noqa: E731
    constrained = (
        " · TARGET CONSTRAINED BY REVIEWED MATERIAL BARRIER"
        if record.material_barrier_identity is not None else ""
    )
    result = (
        '<section class="native-trade-plan"><h3>'
        + escape(f"{record.canonical_instrument} · {record.native_direction.value} · TRADE PLAN READY")
        + '</h3><div class="native-trade-plan-grid">'
        + '<div><span>ENTRY</span><strong>' + escape(currency(record.entry)) + '</strong></div>'
        + '<div><span>STOP</span><strong>' + escape(currency(record.stop)) + '</strong></div>'
        + '<div><span>TARGET</span><strong>' + escape(currency(record.canonical_target)) + '</strong></div>'
        + '<div><span>R:R</span><strong>1 : ' + escape(_number(record.risk_reward_ratio)) + '</strong></div>'
        + '</div><p class="why"><strong>ENTRY CONDITION</strong> · '
        + escape(record.entry_condition.replace("_", " "))
        + '<br><strong>INVALIDATION</strong> · '
        + escape(record.invalidation_condition.replace("_", " "))
        + ' · ' + escape(currency(record.invalidation_reference))
        + '<br><strong>WHY THESE LEVELS</strong> · Entry from qualification structure · '
        + 'Stop from governing structure · Target from setup-native structure'
        + escape(constrained)
        + '</p></section>'
    )
    if initiation is not None:
        position = initiation.position
        detail = "NO POSITION"
        if position is not None:
            detail = (
                f"{position.lots} LOT(S) · MODEL ENTRY ₹{_number(position.model_entry)}"
                + ("" if position.actual_entry is None else f" · ACTUAL ENTRY ₹{_number(position.actual_entry)}")
                + f" · STOP ₹{_number(position.stop)} · TARGET ₹{_number(position.target)}"
            )
        label = {
            SponsorInitiationState.PAPER_ARMED: "PAPER ARMED · WAITING FOR ENTRY",
            SponsorInitiationState.PAPER_ACTIVE: "PAPER ACTIVE",
            SponsorInitiationState.LIVE_ACTIVE: "LIVE ACTIVE · KRONOS MONITORING ONLY · BROKER EXECUTION MANUAL",
            SponsorInitiationState.IGNORED: "IGNORED",
            SponsorInitiationState.WAITING_FOR_RISK: "WAITING FOR RISK",
            SponsorInitiationState.DECISION_UNAVAILABLE: "DECISION UNAVAILABLE",
        }[initiation.state]
        return result + '<section class="native-trade-plan"><h3>' + escape(label) + '</h3><p class="why">' + escape(detail) + '</p></section>'
    if not step32_eligible:
        return result
    action = '/swing/v1/native-trade-decision?plan=' + escape(record.trade_plan_id)
    controls = (
        '<section class="native-trade-plan"><h3>SPONSOR TRADE DECISION</h3>'
        '<div class="native-trade-plan-grid"><div><span>PAPER</span><strong>1 LOT · LOCKED</strong>'
        f'<form method="post" action="{action}"><input type="hidden" name="mode" value="PAPER"><button type="submit">GO</button></form></div>'
        '<div><span>LIVE</span><strong>MANUAL BROKER EXECUTION</strong>'
        f'<form method="post" action="{action}"><input type="hidden" name="mode" value="LIVE">'
        '<label>Actual Entry<input required name="actual_entry" inputmode="decimal"></label>'
        '<label>Lots<input required name="lots" type="number" min="1" step="1"></label><button type="submit">GO</button></form></div>'
        '<div><span>IGNORE</span><strong>CONFIRM EXACT PLAN</strong>'
        f'<form method="post" action="{action}"><input type="hidden" name="mode" value="IGNORE"><button type="submit">IGNORE</button></form></div></div></section>'
    )
    return result + controls


def _condition_level(value) -> str:  # type: ignore[no-untyped-def]
    if value.level_availability is LevelAvailability.LEVEL_UNAVAILABLE:
        return "LEVEL UNAVAILABLE"
    if value.price is not None:
        return f"{value.price:g}"
    if value.zone_low is not None and value.zone_high is not None:
        return f"{value.zone_low:g}–{value.zone_high:g}"
    return "LEVEL UNAVAILABLE"


def _next_level(value) -> str:  # type: ignore[no-untyped-def]
    if value.level_availability is LevelAvailability.LEVEL_UNAVAILABLE:
        return "LEVEL UNAVAILABLE"
    if value.price is not None:
        return f"{value.reference_identity} {value.price:g}"
    if value.zone_low is not None and value.zone_high is not None:
        return f"{value.reference_identity} {value.zone_low:g}–{value.zone_high:g}"
    return "LEVEL UNAVAILABLE"


def _visual_v2_diagnostics(results) -> str:  # type: ignore[no-untyped-def]
    if not results:
        return (
            '<div class="v1-context-row"><span>Visual Evidence V2</span>'
            '<strong>NOT ANALYZED</strong></div>'
        )
    rows = ""
    for result in results:
        unavailable = sum(
            item.level_availability.value == "LEVEL_UNAVAILABLE"
            for item in result.observations
        )
        rows += (
            '<div class="v1-context-row"><span>V2 '
            + escape(result.subject_identity + " · " + result.timeframe.value)
            + '</span><strong>ANALYZED · '
            + str(len(result.observations))
            + ' OBS · '
            + str(unavailable)
            + ' LEVEL UNAVAILABLE</strong></div>'
            '<div class="v1-context-row"><span>Question set</span><strong>'
            + escape(result.question_set_identity)
            + '</strong></div><div class="v1-context-row"><span>Chart revision</span><strong>'
            + escape(result.chart_revision_sha256)
            + '</strong></div><div class="v1-context-row"><span>Evidence integrity</span><strong>'
            + escape(result.evidence_sha256)
            + '</strong></div>'
        )
    return rows


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
        return reason, "READY FOR TRADE PLAN"
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


def render_mtf_fact_diagnostics(
    snapshot: BrowserWorkspaceSnapshot,
    facts: SameRunMtfFactSnapshot | None,
) -> str:
    """Render factual same-run MTF diagnostics without candidate semantics."""

    if facts is not None and type(facts) is not SameRunMtfFactSnapshot:
        raise TypeError("MTF_FACT_DIAGNOSTIC_VIEW_INVALID")
    if facts is None:
        body = '<div class="global-empty">Current governed MTF facts are not available for this run.</div>'
    else:
        cards = ""
        for instrument in facts.instruments:
            timeframes = ""
            for item in instrument.timeframes:
                pivots = " · ".join(
                    f"R{series.radius} H{len(series.swing_highs)}/L{len(series.swing_lows)}"
                    for series in item.structural_measurements
                )
                bucket = "" if item.bucket_class is None else f" · {item.bucket_class}"
                timeframes += (
                    '<div class="mtf-fact-timeframe"><h3>'
                    + escape(item.timeframe.value + bucket)
                    + '</h3><p>Boundary <strong>'
                    + escape(item.observation_boundary.isoformat())
                    + '</strong></p><p>OHLCV <strong>'
                    + escape(
                        f"{item.open:g} / {item.high:g} / {item.low:g} / "
                        f"{item.close:g} / {item.volume}"
                    )
                    + '</strong></p><p>Structure facts '
                    + escape(pivots)
                    + '</p><p>Calendar '
                    + escape(f"{item.calendar_identity} v{item.calendar_version}")
                    + '</p><p>Session '
                    + escape(item.session_identity)
                    + '</p><p>Source '
                    + escape(
                        f"{item.source_provider_identity} · {item.source_interval} · "
                        f"{item.source_market_data_boundary.isoformat()}"
                    )
                    + '</p></div>'
                )
            cards += (
                '<details class="mtf-fact-card"><summary><strong>'
                + escape(instrument.canonical_instrument)
                + '</strong><span>'
                + escape(instrument.exchange)
                + '</span></summary><div class="mtf-fact-grid">'
                + timeframes
                + '</div></details>'
            )
        body = (
            '<div class="mtf-fact-banner">CURRENT GOVERNED MTF FACTS · '
            '98 INSTRUMENTS · FACTUAL ONLY · NO CANDIDATE AUTHORITY · '
            'QUOTE CONTEXT SEPARATE</div><div class="technical">Run '
            + escape(facts.run_identity)
            + ' · Provider provenance '
            + escape(facts.provider_source_identity)
            + '</div><div class="mtf-fact-list">'
            + cards
            + '</div>'
        )
    return _page(
        title="Current MTF Data",
        subtitle="Latest completed governed 1W / 1D / 4H / 1H factual evidence.",
        snapshot=snapshot,
        active_nav="Swing",
        active_tab="MTF Data",
        body=body,
    )


def render_native_discovery(
    snapshot: BrowserWorkspaceSnapshot,
    discovery: NativeDiscoveryRun | None,
) -> str:
    """Render Daily Control beside the separate KRONOS-native MTF authority."""

    if discovery is not None and type(discovery) is not NativeDiscoveryRun:
        raise TypeError("NATIVE_DISCOVERY_VIEW_INVALID")
    if discovery is None:
        body = (
            '<div class="global-empty">KRONOS Native MTF evidence is not '
            'available for this run.</div>'
        )
    else:
        counts = {
            state: sum(item.status is state for item in discovery.assessments)
            for state in NativeDiscoveryStatus
        }
        cards = ""
        for item in discovery.assessments:
            control = (
                " · ".join(item.daily_control_probable_identities)
                if item.daily_control_probable_identities
                else "NO DAILY CONTROL PROBABLE"
            )
            anchor = (
                "NONE"
                if item.operative_anchor is None
                else (
                    f"{item.operative_anchor.anchor_type.value} · "
                    f"{item.operative_anchor.price:g}"
                )
            )
            levels = " · ".join(
                f"{name} {value:g}" for name, value in item.factual_levels
            ) or "NONE"
            cards += (
                '<details class="shadow-card"><summary><strong>'
                + escape(item.canonical_instrument)
                + '</strong><span>'
                + escape(item.direction.value)
                + '</span><span class="shadow-state">'
                + escape(item.status.value.replace("_", " / "))
                + '</span><span>Inspect</span></summary>'
                '<div class="shadow-comparison"><div class="shadow-side">'
                '<h3>DAILY CONTROL</h3><strong>'
                + escape(control)
                + '</strong></div><div class="shadow-side"><h3>KRONOS NATIVE MTF</h3><strong>'
                + escape(
                    "NONE"
                    if item.opportunity_identity is None
                    else item.opportunity_identity.value
                )
                + '</strong><p>'
                + escape(item.reason_codes[-1].replace("_", " "))
                + '</p></div></div><div class="shadow-timeframes">'
                + ''.join(
                    '<div class="shadow-timeframe"><span>' + label
                    + '</span><strong>' + escape(value.replace("_", " "))
                    + '</strong></div>'
                    for label, value in (
                        ("1W", item.weekly_state.value),
                        ("1D", item.daily_state.value),
                        ("4H", item.four_hour_state.value),
                        ("1H", item.one_hour_state.value),
                    )
                )
                + '</div><div class="shadow-comparison"><div class="shadow-side">'
                '<h3>OPERATIVE ANCHOR</h3><p>' + escape(anchor)
                + '</p><h3>FACTUAL LEVELS</h3><p>' + escape(levels)
                + '</p></div><div class="shadow-side"><h3>SOURCE / RUN</h3><p>'
                + escape(item.run_identity + " · " + item.provider_source_identity)
                + '</p><h3>PRODUCT PATH</h3><p>'
                + escape(item.product_path.value)
                + '</p></div></div></details>'
            )
        body = (
            '<div class="mtf-fact-banner">ACTIVE VALIDATION · DAILY CONTROL VS '
            'KRONOS NATIVE MTF · DISCOVERY ONLY · NO READINESS OR EXECUTION AUTHORITY'
            '</div><div class="technical">Run '
            + escape(discovery.run_identity)
            + ' · Probable '
            + str(counts[NativeDiscoveryStatus.PROBABLE])
            + ' · Forming / Watch '
            + str(counts[NativeDiscoveryStatus.FORMING_WATCH])
            + ' · No current opportunity '
            + str(counts[NativeDiscoveryStatus.NO_CURRENT_OPPORTUNITY])
            + ' · Unavailable '
            + str(counts[NativeDiscoveryStatus.UNAVAILABLE])
            + '</div><div class="shadow-list">' + cards + '</div>'
        )
    return _page(
        title="Control vs KRONOS Native MTF",
        subtitle="Native Discovery remains separate from Daily Control and historical Shadow V0.",
        snapshot=snapshot,
        active_nav="Swing",
        active_tab="Control vs Native",
        body=body,
    )


_SETTINGS_CSS = r"""
.topbar .title h1{font-size:24px}.topbar .title p{font-size:12px}
.settings-control-centre{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;align-items:start}
.settings-control-centre .configuration{max-width:none;min-width:0;padding:14px;border-radius:9px;font-size:12px}
.settings-control-centre .configuration-head{gap:10px;padding-bottom:9px;margin-bottom:10px}
.settings-control-centre .configuration-head h2{font-size:15px;letter-spacing:.02em}
.settings-control-centre .configuration-head small{display:block;color:var(--muted);font-size:10px;margin-top:2px}
.settings-control-centre .configuration-state{gap:10px;margin:6px 0;font-size:11px}
.settings-control-centre .configuration-state span{color:var(--muted)}
.settings-control-centre .configuration-state strong{font-size:11px;text-align:right}
.settings-status{display:inline-flex;align-items:center;justify-content:flex-end;gap:6px;color:#dce8f0}
.settings-status-dot{width:6px;height:6px;border-radius:50%;background:currentColor;flex:0 0 6px}
.settings-control-centre .settings-status-dot,.settings-control-centre .settings-status-text{color:inherit}
.settings-status-positive{color:var(--green)}
.settings-status-negative{color:var(--red)}
.settings-status-attention{color:var(--amber)}
.settings-status-neutral{color:#b9c9d5}
.settings-control-centre .configuration-note,.settings-control-centre .diagnostic-intro{font-size:10px;line-height:1.45}
.settings-control-centre button,.settings-control-centre .button{font-size:11px;padding:7px 9px}
.settings-control-centre label{font-size:11px}.settings-control-centre select{font-size:11px;padding:7px 9px}
.settings-control-centre .credential-form{gap:7px;margin-top:10px;padding-top:10px}
.settings-control-centre .credential-form input{font-size:11px;padding:8px 9px}
.settings-control-centre .configuration-actions{gap:7px;margin-top:10px;flex-wrap:wrap}
.settings-card{position:relative;overflow:hidden}.settings-card:before{content:"";position:absolute;inset:0 auto 0 0;width:3px;background:var(--card-accent)}
.settings-kite{--card-accent:#39b99a;background:linear-gradient(145deg,rgba(8,39,38,.94),rgba(6,23,37,.91))}
.settings-telegram{--card-accent:#39b99a;background:linear-gradient(145deg,rgba(8,39,38,.94),rgba(6,23,37,.91))}
.settings-calendar{--card-accent:#3b91e8;background:linear-gradient(145deg,rgba(8,31,58,.96),rgba(6,23,37,.91))}
.settings-openai{--card-accent:#c06acb;background:linear-gradient(145deg,rgba(48,22,53,.94),rgba(6,23,37,.91))}
.settings-engineering{--card-accent:#d8a542;background:linear-gradient(145deg,rgba(48,36,12,.92),rgba(6,23,37,.91));grid-column:span 2}
.settings-security{--card-accent:#4ca8a9;background:linear-gradient(145deg,rgba(13,40,45,.94),rgba(6,23,37,.91));grid-column:1/-1}
.settings-control-centre .connection-status{font-size:10px;padding:3px 7px}
.settings-control-centre details.advanced{border-top:1px solid var(--line);margin-top:11px;padding-top:9px}
.settings-control-centre details.advanced>summary{cursor:pointer;color:#b9d3e6;font-size:10px;font-weight:800;letter-spacing:.06em;list-style:none}
.settings-control-centre details.advanced>summary::-webkit-details-marker{display:none}
.settings-control-centre .diagnostic-grid{gap:7px}.settings-control-centre .diagnostic-card{min-height:94px;padding:9px}
.settings-control-centre .diagnostic-card strong{font-size:11px}.settings-control-centre .diagnostic-card span{font-size:10px}
.settings-control-centre .safety-warning{border:1px solid #8a6430;background:#2a1e0d;color:#f3d391;border-radius:7px;padding:8px;margin-top:9px;font-size:10px}
.settings-control-centre .safety-warning strong{display:block;font-size:11px}.settings-control-centre .danger-zone{border-top:1px solid #663b42;margin-top:11px;padding-top:9px}
.settings-control-centre .danger-zone summary{color:#ef9ea4}.settings-control-centre .danger-zone button{border-color:#793b40;background:#2c151c;color:#ffc3c6}
.settings-security-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px}.settings-security-grid div{border-left:1px solid var(--line);padding-left:9px}.settings-security-grid div:first-child{border-left:0;padding-left:0}.settings-security-grid span,.settings-security-grid strong{display:block}.settings-security-grid span{color:var(--muted);font-size:9px;letter-spacing:.05em}.settings-security-grid strong{font-size:11px;margin-top:3px}
.topbar .dot.DISCONNECTED,.topbar .dot.ERROR{background:var(--red)}
@media(max-width:1100px){.settings-control-centre{grid-template-columns:repeat(2,minmax(0,1fr))}.settings-engineering{grid-column:span 1}.settings-security{grid-column:1/-1}.settings-security-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:700px){.settings-control-centre{grid-template-columns:1fr}.settings-engineering,.settings-security{grid-column:auto}.settings-security-grid{grid-template-columns:1fr}.settings-security-grid div{border-left:0;border-top:1px solid var(--line);padding:7px 0 0}.settings-security-grid div:first-child{border-top:0;padding-top:0}}
"""


def _settings_status(
    value: str,
    tone: str,
    *,
    connection: bool = False,
    wrap_text: bool = False,
) -> str:
    """Render one textual Settings fact with a restrained, non-authoritative cue."""

    classes = f"settings-status settings-status-{tone}"
    if connection:
        classes += " connection-status"
    text = (
        f'<span class="settings-status-text"> {escape(value)}</span>'
        if wrap_text
        else escape(value)
    )
    return (
        f'<strong class="{classes}"><span class="settings-status-dot" '
        f'aria-hidden="true"></span>{text}</strong>'
    )


def render_settings(
    snapshot: BrowserWorkspaceSnapshot,
    chart_analyst_status: ChartAnalystConnectionStatus,
    activation_status: ChartAnalystV2ActivationStatus,
    live_monitoring: LiveMonitoringTestResult | None = None,
    live_monitoring_instruments: tuple[str, ...] = (),
    market_calendar_health: tuple[CalendarCoverageHealth, ...] = (),
    telegram_status: TelegramConfigurationStatus | None = None,
    telegram_candidates: tuple[TelegramPrivateChatCandidate, ...] = (),
    kite_active_watch_count: int = 0,
) -> str:
    if (
        type(chart_analyst_status) is not ChartAnalystConnectionStatus
        or type(activation_status) is not ChartAnalystV2ActivationStatus
    ):
        raise TypeError("CHART_ANALYST_STATUS_INVALID")
    activation_action = (
        "disable"
        if activation_status is ChartAnalystV2ActivationStatus.ENABLED
        else "enable"
    )
    activation_label = "Disable" if activation_action == "disable" else "Enable"
    monitoring = live_monitoring or LiveMonitoringTestResult(
        LiveMonitoringTestState.NOT_TESTED
    )
    provider_tone = {
        ProviderConnectionState.CONNECTED: "positive",
        ProviderConnectionState.CONNECTING: "attention",
        ProviderConnectionState.DISCONNECTED: "negative",
        ProviderConnectionState.ERROR: "negative",
    }[snapshot.provider_state]
    monitoring_tone = {
        LiveMonitoringTestState.PASS: "positive",
        LiveMonitoringTestState.TESTING: "attention",
        LiveMonitoringTestState.CONNECTED_NO_DATA: "attention",
        LiveMonitoringTestState.FAIL: "negative",
        LiveMonitoringTestState.NOT_TESTED: "neutral",
    }[monitoring.state]
    chart_analyst_tone = {
        ChartAnalystConnectionStatus.CONNECTED: "positive",
        ChartAnalystConnectionStatus.CONNECTION_FAILED: "negative",
        ChartAnalystConnectionStatus.NOT_CONFIGURED: "neutral",
    }[chart_analyst_status]
    activation_tone = (
        "positive"
        if activation_status is ChartAnalystV2ActivationStatus.ENABLED
        else "neutral"
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
    calendar_tones = {
        CalendarCoverageStatus.CURRENT: "positive",
        CalendarCoverageStatus.EXPIRING: "attention",
        CalendarCoverageStatus.EXPIRED: "negative",
    }
    calendar_rows = "".join(
        '<div class="configuration-state"><span>'
        f'{escape(item.exchange)} VALID THROUGH {item.valid_through.strftime("%d %b %Y").upper()}'
        '</span>'
        + _settings_status(item.status.value, calendar_tones[item.status])
        + '</div>'
        for item in market_calendar_health
    )
    calendar_section = (
        '<section class="configuration settings-card settings-calendar">'
        '<div class="configuration-head"><div><h2>MARKET CALENDAR</h2>'
        '<small>DOMAIN-008 Market Calendar</small></div></div>'
        f'{calendar_rows or "<p class=configuration-note>Calendar health unavailable.</p>"}'
        '</section>'
    )
    diagnostics_section = (
        '<section class="configuration settings-card settings-engineering engineering-diagnostics" id="engineering-diagnostics">'
        '<div class="configuration-head"><h2><span aria-hidden="true">⚙</span> '
        'Engineering &amp; Diagnostics</h2><span class="read-only-badge">READ ONLY</span>'
        '</div><p class="diagnostic-intro">Read-only technical and historical '
        'evidence for KRONOS diagnostics.</p><div class="diagnostic-grid">'
        '<a class="diagnostic-card" href="/swing/layer1-history">'
        '<small>SWING</small><strong>LAYER-1 HISTORY</strong>'
        '<span>Historical Layer-1 validation evidence.</span><b>OPEN →</b></a>'
        '<a class="diagnostic-card" href="/swing/native-discovery">'
        '<small>SWING</small><strong>CONTROL VS NATIVE</strong>'
        '<span>Control/native comparison and validation evidence.</span><b>OPEN →</b></a>'
        '<a class="diagnostic-card" href="/swing/mtf-diagnostics">'
        '<small>SWING</small><strong>MTF DATA</strong>'
        '<span>Governed multi-timeframe factual evidence.</span><b>OPEN →</b></a>'
        '</div></section>'
    )
    telegram_section = ""
    if telegram_status is not None:
        candidates = "".join(
            '<label class="telegram-option"><input type="radio" name="selection_id" '
            f'value="{escape(item.selection_id)}" required>{escape(item.display_identity)}</label>'
            for item in telegram_candidates
        )
        confirmation = (
            '<form method="post" action="/settings/telegram/private-chat/confirm">'
            f'<div class="telegram-options">{candidates}</div>'
            '<button type="submit">CONFIRM PRIVATE CHAT</button></form>'
            if candidates else ""
        )
        telegram_connected = (
            telegram_status.delivery_enabled
            and telegram_status.token_configured
            and telegram_status.private_chat_configured
        )
        telegram_state = (
            "CONNECTED"
            if telegram_status.state is TelegramConfigurationState.READY
            else telegram_status.state.value
        )
        telegram_tone = {
            TelegramConfigurationState.READY: "positive",
            TelegramConfigurationState.DISCONNECTED: "negative",
            TelegramConfigurationState.CONNECTION_FAILED: "negative",
            TelegramConfigurationState.PRIVATE_CHAT_REQUIRED: "attention",
            TelegramConfigurationState.TOKEN_CONFIGURED: "attention",
            TelegramConfigurationState.NOT_CONFIGURED: "neutral",
        }[telegram_status.state]
        everyday_actions = (
            '<form method="post" action="/settings/telegram/disconnect">'
            '<button type="submit">DISCONNECT</button></form>'
            '<form method="post" action="/settings/telegram/test">'
            '<button type="submit">TEST TELEGRAM</button></form>'
            if telegram_connected else (
                '<form method="post" action="/settings/telegram/connect">'
                '<button class="primary" type="submit">CONNECT</button></form>'
                if telegram_status.token_configured and telegram_status.private_chat_configured
                else ''
            )
        )
        telegram_section = (
            '<section class="configuration settings-card settings-telegram">'
            '<div class="configuration-head"><div><h2>TELEGRAM NOTIFICATIONS</h2>'
            '<small>Telegram Notifications · delivery only</small></div></div>'
            '<div class="configuration-state"><span>Status</span>'
            + _settings_status(telegram_state, telegram_tone, wrap_text=True)
            + '</div><div class="configuration-state"><span>Bot Token</span>'
            + _settings_status(
                "CONFIGURED · ••••••••"
                if telegram_status.token_configured
                else "TELEGRAM · NOT CONFIGURED",
                "positive" if telegram_status.token_configured else "neutral",
            )
            + '</div><div class="configuration-state"><span>Private chat</span>'
            + _settings_status(
                "CONFIRMED"
                if telegram_status.private_chat_configured
                else "TELEGRAM · NOT CONFIGURED",
                "positive" if telegram_status.private_chat_configured else "neutral",
            )
            + '</div><div class="configuration-state"><span>Destination</span><strong>'
            + ('PRIVATE CHAT 1' if telegram_status.private_chat_configured else 'NOT CONFIGURED')
            + '</strong></div><div class="configuration-actions">' + everyday_actions + '</div>'
            '<details class="advanced"' + (' open' if not telegram_status.token_configured else '') + '>'
            '<summary>ADVANCED SETUP ▾</summary>'
            '<form class="credential-form" method="post" action="/settings/telegram/token" '
            'autocomplete="off"><label for="telegram-bot-token">Bot Token</label>'
            '<input id="telegram-bot-token" name="bot_token" type="password" '
            'autocomplete="off" spellcheck="false" minlength="20" maxlength="96" required>'
            '<div><button class="primary" type="submit">SAVE TELEGRAM TOKEN</button></div></form>'
            '<div class="configuration-actions"><form method="post" '
            'action="/settings/telegram/private-chat/discover">'
            '<button type="submit">DISCOVER PRIVATE CHAT</button></form>'
            + ('' if telegram_connected else '<button type="button" disabled>TEST TELEGRAM</button>')
            + '</div>'
            + confirmation
            + ('<details class="danger-zone"><summary>REMOVE TELEGRAM CONFIGURATION</summary>'
               '<p class="configuration-note">Removes the Keychain token and confirmed private destination.</p>'
               '<form method="post" action="/settings/telegram/remove?confirm=REMOVE">'
               '<button type="submit">CONFIRM REMOVE CONFIGURATION</button></form></details>'
               if telegram_status.token_configured or telegram_status.private_chat_configured else '')
            + '<p class="configuration-note">Only an explicitly confirmed private chat '
            'can receive governed KRONOS notifications. Tokens and chat identifiers are '
            'never displayed.</p></details>'
            + (f'<p class="configuration-note">{escape(telegram_status.safe_detail)}</p>'
               if telegram_status.safe_detail else "")
            + '</section>'
        )
    kite_controls = (
        '<form method="post" action="/provider/connect"><button class="primary" type="submit">CONNECT</button></form>'
        if snapshot.provider_state is not ProviderConnectionState.CONNECTED else (
            '<div class="safety-warning"><strong>LIVE MONITORING IS ACTIVE</strong>'
            'Disconnecting Kite will interrupt active watches and may create a monitoring gap requiring reconciliation.'
            '<span> Continue?</span>'
            '<form method="post" action="/provider/disconnect">'
            '<input type="hidden" name="confirm_active" value="YES">'
            '<button type="submit">CONTINUE · DISCONNECT</button></form></div>'
            if kite_active_watch_count else
            '<form method="post" action="/provider/disconnect"><button type="submit">DISCONNECT</button></form>'
        )
    )
    kite_section = (
        f'<section id="kite-market-data" class="configuration settings-card settings-kite" data-state="{escape(monitoring.state.value)}">'
        '<div class="configuration-head"><div><h2>KITE / MARKET DATA</h2>'
        '<small>Kite Live Monitoring · governed read-only Provider</small></div></div>'
        '<div class="configuration-state"><span>Kite</span>'
        + _settings_status(
            snapshot.provider_state.value, provider_tone, wrap_text=True
        )
        + '</div>'
        '<div class="configuration-state"><span>Live monitoring</span>'
        + _settings_status(monitoring.state.value, monitoring_tone)
        + '</div>'
        '<div class="configuration-actions">' + kite_controls + '</div>'
        '<form class="credential-form" method="post" action="/settings/kite/live-monitoring/test">'
        '<label for="live-monitoring-instrument">Instrument</label>'
        f'<select id="live-monitoring-instrument" name="instrument" required>{options}</select>'
        f'<button class="primary" type="submit"{disabled}>TEST LIVE MONITORING</button>'
        f'</form>{proof}</section>'
    )
    openai_section = (
        '<section class="configuration settings-card settings-openai"><div class="configuration-head">'
        '<div><h2>OPENAI / CHART ANALYST</h2><small>OpenAI Chart Analyst · governed visual review</small></div>'
        '</div><div class="configuration-state"><span>Credential</span>'
        + _settings_status(
            chart_analyst_status.value, chart_analyst_tone, connection=True
        )
        + '</div>'
        '<div class="configuration-state"><span>Chart Analyst V2</span>'
        + _settings_status(activation_status.value, activation_tone)
        + '</div>'
        '<div class="configuration-actions">'
        f'<form method="post" action="/settings/chart-analyst/{activation_action}">'
        f'<button type="submit">{activation_label} Chart Analyst V2</button></form>'
        '<form method="post" action="/settings/chart-analyst/test">'
        '<button type="submit">Test Connection</button></form></div>'
        '<details class="advanced"><summary>ADVANCED SETUP ▾</summary>'
        '<form class="credential-form" method="post" '
        'action="/settings/chart-analyst/credential" autocomplete="off">'
        '<label for="chart-analyst-api-key">OpenAI API key</label>'
        '<input id="chart-analyst-api-key" name="api_key" type="password" '
        'autocomplete="off" spellcheck="false" minlength="8" maxlength="512" required>'
        '<div><button class="primary" type="submit">Save credential</button></div>'
        '</form><p class="configuration-note">The saved credential is protected by '
        'the KRONOS secure credential boundary and is never displayed again.</p></details></section>'
    )
    security_section = (
        '<section class="configuration settings-card settings-security"><div class="configuration-head">'
        '<div><h2>SYSTEM &amp; SECURITY</h2><small>Bounded factual runtime authority</small></div>'
        '<span class="read-only-badge">READ ONLY</span></div><div class="settings-security-grid">'
        '<div><span>MODE</span><strong>LOCAL · READ ONLY</strong></div>'
        '<div><span>PROVIDER CAPABILITY</span><strong>INSIDE THIS PROCESS</strong></div>'
        '<div><span>ORDER CAPABILITY</span><strong>NONE</strong></div>'
        '<div><span>DATA VISIBILITY</span><strong>LOCAL ONLY</strong></div>'
        '<div><span>CREDENTIAL STORAGE</span><strong>KEYCHAIN / SECURE BOUNDARY</strong></div>'
        '</div></section>'
    )
    body = (
        '<div class="settings-control-centre">' + kite_section + telegram_section
        + calendar_section + openai_section + diagnostics_section + security_section
        + '</div><script>const liveInitial=document.getElementById("kite-market-data").dataset.state;'
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
        extra_styles=_SETTINGS_CSS,
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


def render_notifications(
    snapshot: BrowserWorkspaceSnapshot,
    notifications: NotificationWorkspaceSnapshot,
    *,
    selected_product: NotificationProduct | None = None,
    ux10: Ux10NotificationSnapshot | None = None,
    operational: SponsorNotificationProjection | None = None,
    notice: str = "",
) -> str:
    """Render one durable management surface over product-owned records."""

    if type(notifications) is not NotificationWorkspaceSnapshot:
        raise TypeError("NOTIFICATION_WORKSPACE_INVALID")
    if selected_product is not None and type(selected_product) is not NotificationProduct:
        raise TypeError("NOTIFICATION_PRODUCT_FILTER_INVALID")
    if operational is not None:
        if type(operational) is not SponsorNotificationProjection:
            raise TypeError("SPONSOR_NOTIFICATION_PROJECTION_INVALID")
        return _render_operational_notifications(snapshot, operational, notice)
    if selected_product is NotificationProduct.INTRADAY:
        return _render_intraday_notifications(snapshot)
    tabs = '<nav class="notification-tabs">' + "".join(
        f'<a class="button{" active" if selected_product is product else ""}" href="{href}">{label}</a>'
        for label, href, product in (
            ("ALL", "/notifications", None),
            ("SWING", "/notifications/swing", NotificationProduct.SWING),
            ("INTRADAY", "/notifications/intraday", NotificationProduct.INTRADAY),
        )
    ) + "</nav>"
    records = notifications.for_product(selected_product)
    action_required = tuple(
        item for item in records
        if item.state is NotificationState.TRIGGERED
    )
    action_centre = ""
    if action_required:
        instruments = ", ".join(item.instrument for item in action_required)
        action_centre = (
            '<section class="notification-action-centre"><h2>ACTION CENTRE · '
            f'{len(action_required)} REASSESSMENT REQUIRED</h2><p>{escape(instruments)} · '
            'One governed trigger event is projected here and in its durable record.</p></section>'
        )
    ux10_records = (
        ()
        if ux10 is None or selected_product is NotificationProduct.INTRADAY
        else ux10.records
    )
    ux10_body = "".join(_ux10_notification_row(item) for item in ux10_records)
    if records or ux10_body:
        body = '<div class="notification-list">' + "".join(
            _notification_row(item) for item in records
        ) + ux10_body + "</div>"
    else:
        message = {
            None: "No notifications.",
            NotificationProduct.SWING: "No active Swing watches.",
            NotificationProduct.INTRADAY: "No Intraday notifications. Intraday alert policy has not been manufactured.",
        }[selected_product]
        body = f'<div class="global-empty">{escape(message)}</div>'
    watch_refresh = (
        f'<script>const notificationRevision="{notifications.revision + (ux10.revision if ux10 else "")}";'
        'setInterval(async()=>{try{const r=await fetch("/notifications/status",{cache:"no-store"});'
        'if(!r.ok)return;const s=await r.json();if(s.revision!==notificationRevision)location.reload();'
        '}catch(_e){}},1500);</script>'
    )
    return _page(
        title="Notifications",
        subtitle="Durable product-segregated watch and alert management.",
        snapshot=snapshot,
        active_nav="Notifications",
        active_tab="",
        body=tabs + action_centre + body + watch_refresh,
    )


def _render_operational_notifications(
    snapshot: BrowserWorkspaceSnapshot,
    projection: SponsorNotificationProjection,
    notice: str,
) -> str:
    query = projection.query
    centre = projection.snapshot
    products = (
        '<div class="notification-centre-products">'
        '<a class="button active" href="/notifications/swing">SWING</a>'
        '<a class="button" href="/notifications/intraday">INTRADAY</a></div>'
    )
    ws = centre.websocket_state
    ws_dot = "○" if ws == "IDLE" else "●"
    header = (
        '<div class="notification-centre-head">' + products
        + '<span class="notification-centre-ws ' + ws.lower() + '">WS '
        + ws_dot + ' ' + ws + '</span>'
        + '<span class="notification-centre-count">LIVE ' + str(centre.live_count) + '</span>'
        + '<span class="notification-centre-count">EXPIRED ' + str(centre.expired_count) + '</span>'
    )
    if centre.expired_count:
        header += (
            '<details class="notification-centre-confirm"><summary '
            'title="DELETE EXPIRED NOTIFICATIONS" aria-label="DELETE EXPIRED NOTIFICATIONS">'
            '🗑 DELETE EXPIRED</summary><div><p>DELETE '
            + str(centre.expired_count) + ' EXPIRED SWING NOTIFICATIONS?</p>'
            '<form method="post" action="/notifications/delete-expired">'
            '<input type="hidden" name="product" value="SWING">'
            '<input type="hidden" name="confirm" value="DELETE">'
            '<button type="submit">CONFIRM DELETE EXPIRED</button></form></div></details>'
        )
    header += '</div>'
    filters = '<div class="notification-centre-filters">' + ''.join(
        '<a class="button ' + ('active' if query.state is item else '')
        + '" href="/notifications/swing?' + urlencode({
            "state": item.value, "search": query.search,
        }) + '">' + item.value + '</a>'
        for item in SponsorNotificationFilter
    ) + '</div>'
    search = (
        '<form class="notification-centre-tools" method="get" action="/notifications/swing">'
        '<input type="hidden" name="state" value="' + query.state.value + '">'
        '<input class="notification-centre-search" name="search" maxlength="80" value="'
        + escape(query.search) + '" placeholder="Search notifications..." '
        'aria-label="Search notifications"><button type="submit">SEARCH</button></form>'
    )
    message = '' if not notice else '<div class="notification-centre-notice">' + escape(notice) + '</div>'
    rows = ''.join(_operational_notification_row(item) for item in projection.page_records)
    listing = (
        '<div class="global-empty">NO NOTIFICATIONS MATCH THIS VIEW</div>'
        if not projection.page_records
        else '<div class="notification-centre-list">' + rows + '</div>'
    )
    pagination = ''
    if projection.page_count > 1:
        links = []
        for label, page in (("PREVIOUS", query.page - 1), ("NEXT", query.page + 1)):
            if 1 <= page <= projection.page_count:
                links.append(
                    '<a class="button" href="/notifications/swing?'
                    + urlencode({
                        "state": query.state.value, "search": query.search, "page": page,
                    }) + '">' + label + '</a>'
                )
        pagination = (
            '<div class="notification-centre-pagination"><span>PAGE '
            + str(query.page) + ' / ' + str(projection.page_count) + '</span>'
            + ''.join(links) + '</div>'
        )
    polling = (
        '<script>const notificationRevision="' + centre.revision + '";'
        'setInterval(async()=>{try{const r=await fetch("/notifications/status",{cache:"no-store"});'
        'if(!r.ok)return;const s=await r.json();if(s.revision!==notificationRevision)location.reload();'
        '}catch(_e){}},1500);</script>'
    )
    return _page(
        title="Notifications", subtitle="Current operational alerts and reminders.",
        snapshot=snapshot, active_nav="Notifications", active_tab="",
        body=header + filters + search + message + listing + pagination + polling,
    )


def _render_intraday_notifications(snapshot: BrowserWorkspaceSnapshot) -> str:
    return _page(
        title="Notifications", subtitle="Current operational alerts and reminders.",
        snapshot=snapshot, active_nav="Notifications", active_tab="",
        body=(
            '<div class="notification-centre-head"><div class="notification-centre-products">'
            '<a class="button" href="/notifications/swing">SWING</a>'
            '<a class="button active" href="/notifications/intraday">INTRADAY</a></div>'
            '<span class="notification-centre-ws idle">WS — NOT AVAILABLE</span></div>'
            '<div class="workflow-empty"><strong>INTRADAY NOTIFICATIONS</strong><br>'
            'No Intraday notifications — NOT YET OPERATIONAL<br>'
            '<small>Intraday alert policy has not been manufactured.</small></div>'
        ),
    )


def _operational_notification_row(item: SponsorNotificationRecord) -> str:
    time = item.updated_at.astimezone(_KOLKATA).strftime("%H:%M")
    subject = item.instrument or "SYSTEM"
    next_reminder = (
        '' if item.next_reminder_at is None else
        'NEXT ' + item.next_reminder_at.astimezone(_KOLKATA).strftime("%H:%M")
        + ' · ×' + str(item.reminder_count)
    )
    actions = []
    if item.state is SponsorNotificationState.LIVE:
        if item.action is SponsorNotificationAction.REFRESH:
            actions.append(
                '<form method="post" action="/notifications/refresh">'
                + _notification_lifecycle_hidden(item)
                + '<button type="submit">REFRESH</button></form>'
            )
        elif item.action is SponsorNotificationAction.OPEN and item.action_path:
            actions.append('<a class="button" href="' + escape(item.action_path) + '">OPEN</a>')
    if item.state is SponsorNotificationState.EXPIRED and item.reactivatable:
        actions.append(
            '<form method="post" action="/notifications/reactivate">'
            + _notification_lifecycle_hidden(item)
            + '<button class="notification-icon" type="submit" title="RE-ACTIVATE NOTIFICATION" '
            'aria-label="RE-ACTIVATE NOTIFICATION">♻</button></form>'
        )
    actions.append(
        '<form method="post" action="/notifications/dismiss">'
        + _notification_lifecycle_hidden(item)
        + '<button class="notification-icon" type="submit" title="DELETE NOTIFICATION" '
        'aria-label="DELETE NOTIFICATION">🗑</button></form>'
    )
    history = ''.join(
        '<li>' + escape(event.event_type) + ' · '
        + event.occurred_at.astimezone(_KOLKATA).strftime("%d %b %Y %H:%M IST")
        + '</li>' for event in item.history
    )
    failure = ' failure' if item.family.value == "FAILURE_OPERABILITY" and item.state is SponsorNotificationState.LIVE else ''
    return (
        '<article class="notification-centre-row' + failure + '">'
        '<span class="notification-centre-state ' + item.state.value.lower() + '">'
        + item.state.value + '</span><span class="notification-centre-time">' + time + '</span>'
        '<span class="notification-centre-subject">' + escape(subject) + '</span>'
        '<span class="notification-centre-message" title="' + escape(item.summary) + '">'
        + escape(item.summary) + '</span><span class="notification-centre-next">'
        + escape(next_reminder) + '</span><span class="notification-centre-actions">'
        + ''.join(actions) + '</span><details class="notification-centre-detail">'
        '<summary>GOVERNED EVIDENCE · ' + escape(item.notification_type.replace('_', ' '))
        + '</summary><ul>' + history + '</ul></details></article>'
    )


def _notification_lifecycle_hidden(item: SponsorNotificationRecord) -> str:
    return (
        '<input type="hidden" name="notification_id" value="'
        + item.notification_identity + '"><input type="hidden" name="revision" value="'
        + item.integrity_sha256 + '">'
    )


def _ux10_notification_row(item: Ux10NotificationRecord) -> str:
    occurred = item.created_at.astimezone(_KOLKATA).strftime("%d %b %Y · %H:%M IST")
    instrument = item.instrument or "SYSTEM"
    direction = f" · {item.direction}" if item.direction else ""
    lifecycle_mode = (
        f'<span>{escape(item.lifecycle_mode)}</span>' if item.lifecycle_mode else ""
    )
    telegram_delivery = (
        "PENDING SETUP"
        if item.telegram_delivery_state.value == "NOT_CONFIGURED"
        else item.telegram_delivery_state.value.replace("_", " ")
    )
    return (
        f'<article class="notification-row ux10-row priority-{escape(item.priority.value.lower())}">'
        '<div class="notification-head"><span class="notification-product">KRONOS · SWING</span>'
        f'<h2>{escape(instrument + direction)}</h2>'
        f'<span class="notification-state">{escape(item.priority.value)}</span></div>'
        f'<div class="ux10-event">{escape(item.notification_type.value.replace("_", " "))}</div>'
        f'<p class="notification-condition">{escape(item.summary)}</p>'
        f'<div class="ux10-action">{escape(item.action)}</div>'
        '<div class="notification-meta">'
        f'<span>{escape(item.family.value.replace("_", " "))}</span>'
        f'{lifecycle_mode}'
        f'<span>{escape(occurred)}</span>'
        f'<span>TELEGRAM {escape(telegram_delivery)}</span>'
        '</div></article>'
    )


def _notification_row(item: ManagedNotification) -> str:
    direction_class = "direction-long" if item.direction == "LONG" else "direction-short"
    activated = item.activated_at.astimezone(_KOLKATA).strftime("%d %b %Y · %H:%M IST")
    triggered = ""
    if item.state is NotificationState.TRIGGERED:
        trigger_time = (
            item.triggered_at.astimezone(_KOLKATA).strftime("%d %b %Y · %H:%M IST")
            if item.triggered_at else "UNAVAILABLE"
        )
        triggered = (
            '<div class="notification-trigger"><strong>PROMOTION WATCH REACHED</strong>'
            f'<small>{escape(item.trigger_summary or item.condition_summary)}</small>'
            '<span>REASSESSMENT REQUIRED</span>'
            '<small>NO TRADE HAS BEEN AUTHORIZED</small>'
            f'<small>Triggered {escape(trigger_time)}</small></div>'
        )
    monitoring = ""
    if item.state is NotificationState.ACTIVE and not item.monitoring_active:
        monitoring = (
            '<div class="notification-trigger"><strong>PROVIDER MONITORING UNAVAILABLE</strong>'
            '<small>The durable watch remains active but no Provider session is attached. '
            'Reconnect Kite to restore valid monitoring.</small></div>'
        )
    exact_details = (
        '<span class="button">ANALYSIS DETAILS UNAVAILABLE · STALE SOURCE</span>'
        if item.state is NotificationState.STALE
        else (
            f'<a class="button" href="/swing/analysis-details/{escape(item.source_run_identity)}/'
            f'{quote(item.instrument, safe="")}">VIEW ANALYSIS DETAILS →</a>'
        )
    )
    controls = [exact_details]
    if item.state is NotificationState.ACTIVE:
        controls.append(_notification_confirmation(
            item.source_identity, "deactivate", "DEACTIVATE",
            "Monitoring stops. The analytical candidate and immutable history remain preserved.",
        ))
    elif item.state is NotificationState.INACTIVE:
        controls.append(
            '<form method="post" action="/notifications/watch/reactivate">'
            f'<input type="hidden" name="watch_id" value="{escape(item.source_identity)}">'
            '<button type="submit">REACTIVATE</button></form>'
        )
    controls.append(_notification_confirmation(
        item.source_identity, "delete", "DELETE",
        "The notification disappears from this workspace. Required audit history is preserved.",
    ))
    history = "".join(
        f'<li>{escape(event.event_type)} · '
        f'{escape(event.occurred_at.astimezone(_KOLKATA).strftime("%d %b %Y %H:%M IST"))}</li>'
        for event in item.history
    )
    return (
        f'<article class="notification-row" data-watch-id="{escape(item.source_identity)}">'
        '<div class="notification-head">'
        f'<h2>{escape(item.instrument)}</h2><strong class="notification-product">{escape(item.product.value)}</strong>'
        f'<span class="direction {direction_class}">{escape(item.direction)}</span>'
        f'<span class="notification-state {escape(item.state.value)}">{escape(item.state.value)}</span></div>'
        f'<div class="notification-condition">{escape(item.condition_summary)}</div>{triggered}{monitoring}'
        '<div class="notification-meta">'
        f'<span>{escape(item.timeframe)} · {escape(item.comparator)}</span>'
        f'<span>Level {escape(item.authoritative_level)}</span>'
        f'<span>Activated {escape(activated)}</span>'
        f'<span>Source {escape(item.source_run_identity)}</span></div>'
        f'<div class="notification-actions">{"".join(controls)}</div>'
        f'<details class="notification-history"><summary>WATCH HISTORY · {len(item.history)} EVENTS</summary>'
        f'<ul>{history}</ul></details></article>'
    )


def _notification_confirmation(
    watch_id: str, action: str, label: str, explanation: str,
) -> str:
    return (
        '<details class="notification-confirm"><summary>' + escape(label) + '</summary><div>'
        f'<p>{escape(explanation)}</p><form method="post" action="/notifications/watch/{escape(action)}">'
        f'<input type="hidden" name="watch_id" value="{escape(watch_id)}">'
        f'<button type="submit">CONFIRM {escape(label)}</button></form></div></details>'
    )


def render_intraday_workstation(
    snapshot: BrowserWorkspaceSnapshot,
    intraday: object,
) -> str:
    """Compatibility shim; Intraday owns the implementation."""

    from kronos.browser.intraday_views import (
        render_intraday_workstation as render_product_workstation,
    )

    return render_product_workstation(snapshot, intraday)  # type: ignore[arg-type]


def _page(
    *,
    title: str,
    subtitle: str,
    snapshot: BrowserWorkspaceSnapshot,
    active_nav: str,
    active_tab: str,
    body: str,
    back_link: str = "",
    extra_styles: str = "",
    swing_projection_revision: str | None = None,
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
                ("Review", "/swing/v1-review"),
                ("Trade Candidates", "/swing/trade-candidates"),
                ("Active", "/swing/active"),
                ("Closed", "/swing/closed"),
            )
        )
        if active_tab not in {"Layer-1 History", "Control vs Native", "MTF Data"}:
            tabs += '<div class="toolbar">' + _analysis_form(snapshot) + "</div>"
        tabs += "</nav>"
    signature_parts = [
        snapshot.provider_state.value,
        snapshot.analysis_state.value,
        snapshot.completed_at.isoformat() if snapshot.completed_at else "",
    ]
    projection_attribute = ""
    if swing_projection_revision is not None:
        signature_parts.append(swing_projection_revision)
        projection_attribute = (
            ' data-swing-projection-revision="'
            + escape(swing_projection_revision)
            + '"'
        )
    signature = "|".join(signature_parts)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)} · KRONOS</title><link rel="icon" type="image/png" sizes="64x64" href="/favicon.png"><style>{_CSS}{extra_styles}</style></head>
<body data-status-signature="{escape(signature)}"{projection_attribute}><div class="app"><aside class="sidebar">
<div class="brand"><img class="brandmark" src="/assets/brand/kronos-brand-mark.png" alt="KRONOS" title="KRONOS" width="35" height="35"><span class="brandword">KRONOS</span></div><nav class="nav">{nav}</nav>
<div class="system"><strong>● LOCAL · READ ONLY</strong>Provider capability stays inside this process.<br>Order capability: NONE
<details class="exit-control"><summary>EXIT KRONOS</summary><div class="exit-confirm"><p><b>EXIT KRONOS?</b><br>This will safely stop KRONOS and its runtime services.<br>No trade or broker order will be created.</p><div class="exit-actions"><a class="exit-cancel" href="">CANCEL</a><form method="post" action="/control/exit"><button type="submit">EXIT KRONOS</button></form></div></div></details></div>
</aside><main class="main"><header class="topbar"><div class="title">{back_link}<h1>{escape(title)}</h1><p>{escape(subtitle)}</p></div>
<div class="kite"><span class="dot {snapshot.provider_state.value}"></span><strong>Kite: {snapshot.provider_state.value}</strong>{_connect_form(snapshot)}</div></header>
{tabs}<div class="content">{body}</div><div class="footer">KRONOS Browser V1 · Local Mode</div></main></div>
<script>const initial=document.body.dataset.statusSignature;const swingRevision=document.body.dataset.swingProjectionRevision;setInterval(async()=>{{try{{const r=await fetch('/status',{{cache:'no-store'}});if(!r.ok)return;const parts=[s.provider,s.analysis,s.completed_at||''];if(swingRevision!==undefined)parts.push(s.swing_projection_revision||'');if(parts.join('|')!==initial)location.reload();}}catch(_e){{}}}},1500);</script>
</body></html>"""


def render_browser_page(
    *,
    title: str,
    subtitle: str,
    snapshot: BrowserWorkspaceSnapshot,
    active_nav: str,
    active_tab: str,
    body: str,
    back_link: str = "",
    extra_styles: str = "",
) -> str:
    """Stable shared page shell for independently owned product views."""

    return _page(
        title=title,
        subtitle=subtitle,
        snapshot=snapshot,
        active_nav=active_nav,
        active_tab=active_tab,
        body=body,
        back_link=back_link,
        extra_styles=extra_styles,
    )


def _connect_form(snapshot: BrowserWorkspaceSnapshot) -> str:
    if snapshot.provider_state is ProviderConnectionState.CONNECTED:
        return '<form method="post" action="/provider/disconnect"><button>Disconnect</button></form>'
    disabled = " disabled" if snapshot.provider_state is ProviderConnectionState.CONNECTING else ""
    return f'<form method="post" action="/provider/connect"><button class="primary"{disabled}>Connect</button></form>'


def _tab_link(name: str, href: str, active_tab: str) -> str:
    css_class = "active" if name == active_tab else ""
    badge = (
        ""
        if name in {
            "Opportunities", "Review", "Trade Candidates", "Active", "Closed",
        }
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
    if snapshot.completed_at is None:
        return ""
    completed = snapshot.completed_at.astimezone(_KOLKATA)
    return (
        '<div class="analysis-batch"><span>Market analysis</span>'
        '<div class="analysis-run-times"><strong>LAST SUCCESSFUL ANALYSIS · '
        f'{escape(completed.strftime("%d %b %Y %H:%M %Z").upper())}'
        '</strong></div></div>'
    )


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


def _native_analysis_status_script() -> str:
    return """<script>
for(const form of document.querySelectorAll('form[action^="/swing/v1/native-analyze"]')){
  form.addEventListener('submit',async event=>{
    event.preventDefault();
    const button=form.querySelector('button');
    if(button)button.disabled=true;
    const all=form.action.endsWith('/swing/v1/native-analyze-all');
    const cards=all
      ? Array.from(document.querySelectorAll('.chart-intake-card')).filter(card=>{
          const action=card.querySelector('form.validate-one button');
          return action&&!action.disabled;
        })
      : [form.closest('.chart-intake-card')].filter(Boolean);
    for(const card of cards){
      const state=card.querySelector('.analysis-state');
      if(state){
        state.textContent='ANALYZING';
        state.className='analysis-state analyzing';
      }
    }
    try{
      const response=await fetch(form.action,{method:'POST',redirect:'follow'});
      if(!response.ok)throw new Error();
      location.reload();
    }catch(_error){
      for(const card of cards){
        const state=card.querySelector('.analysis-state');
        if(state){
          state.textContent='ANALYSIS FAILED';
          state.className='analysis-state analysis-failed';
        }
      }
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


def _sponsor_price(value: float) -> str:
    return "₹" + _number(value)


def _duration(seconds: int | None) -> str:
    if seconds is None:
        return "—"
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60
    values = []
    if days:
        values.append(f"{days}d")
    if hours:
        values.append(f"{hours}h")
    if minutes or not values:
        values.append(f"{minutes}m")
    return " ".join(values)


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
        "notifications": "◉", "journal": "▤", "portfolio": "▣",
        "reports": "▥", "settings": "⚙",
    }[name]


__all__ = [
    "Step32SponsorWorkflowView",
    "build_step32_sponsor_workflow_view",
    "render_dashboard",
    "render_browser_page",
    "render_opportunities",
    "render_native_analysis_details",
    "render_native_trade_window",
    "render_notifications",
    "render_reports",
    "render_trade_journal",
    "render_placeholder",
    "render_settings",
    "render_mtf_fact_diagnostics",
    "render_native_discovery",
    "render_step32_sponsor_workflow",
    "render_v1_review",
    "render_workspace",
]
