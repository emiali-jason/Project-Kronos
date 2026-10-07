"""Loopback-only HTTP transport for KRONOS Browser V1."""

from __future__ import annotations

from collections.abc import Callable
import base64
import binascii
from contextlib import nullcontext
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from email.parser import BytesParser
from email.policy import default as email_policy
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from hashlib import sha256
from html import escape
import json
import logging
from pathlib import Path
import re
from threading import BoundedSemaphore, Lock, RLock, Thread, local
from time import monotonic
from urllib.parse import parse_qs, quote, unquote, urlencode, urlsplit
from uuid import uuid4

from kronos.application.paper_observation_tracking import paper_monitoring_failure_reason
from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.common.maintenance_admission import MaintenanceAdmissionCoordinator
from kronos.common.request_diagnostics import (
    RequestDiagnostics, bind_trace, current_trace, diagnostic_context, diagnostic_lock,
    diagnostic_operation, diagnostic_stage, safe_call, start_trace,
)
from kronos.application.provider_instrument_master_operation import (
    ProviderInstrumentMasterOperationalComposition,
    p1_operational_result_document,
)
from kronos.application.swing_progression_watch import (
    SwingProgressionWatchSnapshot,
    SwingProgressionWatchWorkflow,
)
from kronos.application.notifications import (
    NotificationProduct,
)
from kronos.application.notification_centre import (
    SponsorNotificationCentre,
    SponsorNotificationFilter,
    SponsorNotificationLifecycleStore,
    SponsorNotificationQuery,
    project_sponsor_notifications,
)
from kronos.application.intraday_wo09_notifications import Wo09NotificationSource
from kronos.application.swing_notifications import (
    project_swing_notification_workspace, monitoring_indicator, notification_revision,
)
from kronos.application.swing_ux10 import (
    SwingUx10NotificationService,
    Ux10NotificationStore,
)
from kronos.application.swing_refresh_reminder import (
    K5RefreshReminderStore,
    SwingK5RefreshReminderWorkflow,
)
from kronos.application.shared_monitoring import SharedSwingMonitoringHub
from kronos.application.swing_v1_browser import SwingV1BrowserOperationalization
from kronos.application.swing_v1_review import (
    SwingV1ReviewWorkflow,
    V1BatchPreflightFailure,
)
from kronos.application.swing_native_review import (
    NativeAnalysisDetailsProjection,
    NativeReviewWorkflow,
    project_native_analysis_details,
)
from kronos.application.swing_visual_v3 import CompletedVisualV3Review, SwingVisualV3ReviewCycle
from kronos.swing.v1.analytical_promotion import Kr370AnalyticalPromotionRecord
from kronos.swing.v1.analytical_promotion_v2 import V2PromotionRecord
from kronos.application.swing_visual_v3_live import SwingVisualV3LiveWorkflow, NativeReviewIntakeWorkflow
from kronos.application.swing_bulk_import import (
    DEFAULT_BULK_IMPORT_ROOT,
    SwingBulkImportOwner,
    SwingBulkImportStore,
)
from kronos.application.swing_mcx_supporting_context import (
    McxSupportingContextWorkflow,
)
from kronos.application.swing_mcx_integrated import SwingMcxIntegratedWorkflow
from kronos.application.swing_mcx_v1_operations import SwingMcxV1OperationalControl
from kronos.swing.v1.mcx_contract_profile import McxFamily
from kronos.swing.v1.mcx_contract_selection import McxSelectionRole
from kronos.application.swing_trade_window import (
    LocalTradePlanConstructionDiagnosticStore,
    SwingTradeWindowWorkflow,
    TradePlanConstructionAttemptResult,
    TradePlanConstructionStage,
    TRADE_PLAN_CONSTRUCTION_SAFE_FAILURES,
    build_current_trade_construction_evidence,
)
from kronos.swing.v1.observation_research_ledger_v2 import (
    with_completion_trading_dates,
    CurrentMarketFactV2,
    websocket_presentation_state,
)
from kronos.application.live_monitoring_e2e import (
    resolve_governed_monitoring_instrument,
)
from kronos.configuration.apple_keychain import (
    AppleKeychainApiKeySource,
    AppleKeychainCredentialRemover,
    AppleKeychainCredentialSource,
    AppleKeychainCredentialPresenceProbe,
    AppleKeychainCredentialProvisioner,
    run_security_framework_provisioning,
    run_security_framework_removal,
    run_security_framework_subprocess,
    run_security_presence_subprocess,
)
from kronos.integrations.telegram import (
    TELEGRAM_PROVIDER,
    TelegramConfigurationService,
    TelegramDeliveryControlStore,
    UrllibTelegramBotApiTransport,
)
from kronos.configuration.openai_chart_analyst import (
    ChartAnalystConnectionStatus,
    ChartAnalystV2ActivationService,
    ChartAnalystV2ActivationStatus,
    OPENAI_CHART_ANALYST_CREDENTIAL_REF,
    OPENAI_CHART_ANALYST_PROVIDER,
    OpenAIChartAnalystCredentialService,
)
from kronos.configuration.pdf_visual_review import (
    PdfVisualReviewConfiguration,
    default_mcx_supporting_context_directories,
    load_or_provision_pdf_visual_review_configuration,
)
from kronos.integrations.openai_chart_analyst import (
    OpenAIChartAnalystCapabilityProbe,
    OpenAIChartAnalystV2Config,
    OpenAIChartAnalystV2Provider,
    OpenAIVisualEvidenceV2Config,
    OpenAIVisualEvidenceV2Provider,
    UrllibOpenAIResponsesTransport,
)
from kronos.browser.views import (
    ANSWER_REJECTION_EXPLANATIONS,
    render_active_candidates,
    render_candidate_workspace,
    render_closed_candidates,
    render_dashboard,
    render_legacy_opportunities,
    render_opportunities,
    render_placeholder,
    render_settings,
    render_trade_journal,
    render_mtf_fact_diagnostics,
    render_native_discovery,
    render_native_analysis_details,
    render_native_trade_window,
    render_notifications,
    render_swing_notification_evidence,
    render_reports,
    render_trade_candidates,
    render_v1_review,
    render_browser_page,
)
from kronos.browser.reports import (
    ReportProduct,
    ReportsQuery,
    ReportView,
    export_reports_csv,
    export_reports_json,
    export_reports_xlsx,
    project_historical_reports,
    reports_excel_filename,
)
from kronos.browser.dashboard import project_sponsor_dashboard
from kronos.browser.v1_analysis_status import analysis_status_payload
from kronos.browser.swing_readiness_presentation import present_native_readiness
from kronos.browser.swing_v3_presentation import present_visual_v3_review
from kronos.browser.restart_control import BrowserBackendRestartControl
from kronos.browser.product_routes import (
    BrowserGetRequest,
    BrowserPostRequest,
    ProductBrowserRoutes,
    default_product_browser_routes,
)
from kronos.browser.intraday_discovery_control import (
    IntradayDiscoveryOperationalControl,
)
from kronos.browser.intraday_historical_control import (
    IntradayHistoricalQualificationOperationalControl,
)
from kronos.swing.v1.evidence_store import (
    LocalTradingViewEvidenceStore,
    TradingViewEvidenceStoreError,
)
from kronos.swing.run_provenance import LocalSwingRunProvenanceStore
from kronos.swing.v1.chart_analyst_v2_store import LocalChartAnalystV2Store
from kronos.swing.v1.tradingview import ChartTimeframe
from kronos.swing.v1.step32 import SponsorDecisionMode
from kronos.swing.v1.native_sponsor_decision import SponsorTradeChoice
from kronos.swing.v1.native_entry_timing import (
    EcpcV2Blocker,
    EcpcV2Outcome,
    LocalKr380V2Store,
    LocalObjectiveModelV1Store,
    LocalPortfolioStateV1Store,
    LocalRiskPermissionV1Store,
)
from kronos.swing.v1.mtf_facts import FactualTimeframe
from kronos.swing.v1.mcx_contract_profile import MCX_SWING_FAMILIES
from kronos.instrument.facts import publish_instrument_context
from kronos.swing.universe import enabled_swing_phase1_universe
from kronos.swing.v1.native_active_trade_lifecycle import TradeExitReason
from kronos.swing.v1.native_review import NativeReviewEvidenceStore
from kronos.swing.v1.review_evidence_binding import ReviewMutationPrecondition, ReviewEvidenceError, canonical, strict_json
from kronos.swing.v1.review_evidence_store import ReviewEvidenceStore
from kronos.swing.v1.visual_evidence_v2 import (
    LocalVisualEvidenceV2DiagnosticStore,
    VisualEvidenceSubjectKind,
)
from kronos.swing.v1.pdf_visual_review import (
    PdfReviewRecordStore,
    PdfReviewTransportError,
    PdfVisualReviewTransport,
)
from kronos.swing.v1.native_readiness_v3 import NativeLayer2ReadinessV3Store
from kronos.swing.v1.pdf_visual_review_v3_live import (
    VisualV3PdfRecordStore,
    VisualV3PdfReviewTransport,
)
from kronos.swing.v1.visual_evidence_v3 import LocalVisualEvidenceV3Store
from kronos.swing.v1.kr370_step31_handoff import LocalKr370Step31HandoffStore
from kronos.swing.v1.mcx_supporting_context import (
    McxContextFamily,
    McxContextSlot,
    McxSupportingContextStore,
)
from kronos.swing.v1.mcx_supporting_context_pdf import (
    McxContextPdfStore,
    McxContextPdfTransport,
)
from kronos.swing.v1.native_trade_construction import LocalTradePlanStore
from kronos.swing.v1.step31_observation import LocalStep31ObservationStore
from kronos.swing.v1.sponsor_observation_decision import (
    LocalSponsorObservationDecisionStore,
    SponsorActivationDisposition,
    SponsorObservationReason,
)
from kronos.swing.v1.observation_research_ledger import ObservationResearchQueryV1
from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.step31_observation import Step31WarningSeverity
from kronos.swing.v1.progression_watch import (
    derive_kr370_progression_requirements,
    derive_kr370_v2_progression_requirements,
    derive_progression_requirements,
    derive_v3_progression_requirements,
)


_LOOPBACK_HOST = "127.0.0.1"
_MAX_CREDENTIAL_FORM_BYTES = 4096
_MAX_PRODUCT_POST_BYTES = 25 * 1024 * 1024
_MAX_ACTIVE_BROWSER_REQUESTS = 32
_BRAND_ASSET_ROOT = (
    Path(__file__).resolve().parents[3] / "assets" / "images" / "brand"
)
_BRAND_MARK_ASSET = _BRAND_ASSET_ROOT / "kronos-brand-mark.png"
_SIDEBAR_MARK_ASSET = _BRAND_ASSET_ROOT / "kronos-sidebar-mark.png"
_FAVICON_ASSET = _BRAND_ASSET_ROOT / "kronos-favicon.png"
_WORKSPACE_ROUTE = re.compile(r"/swing/opportunities/([1-2])\Z")
_LOG = logging.getLogger(__name__)
_ELIGIBLE_WORKSPACE_ROUTE = re.compile(r"/swing/eligible/([1-9][0-9]*)\Z")
_TRADE_CANDIDATE_ROUTE = re.compile(
    r"/swing/trade-candidates/([0-9a-f]{16})\Z"
)
_ANALYSIS_DETAILS_ROUTE = re.compile(
    r"/swing/analysis-details/(SWING-RUN-[A-F0-9]{32})/([^/]+)\Z"
)
_TRADE_WINDOW_ROUTE = re.compile(
    r"/swing/trade-window/(SWING-RUN-[A-F0-9]{32})/([^/]+)\Z"
)
_TRADE_CANDIDATE_DECISION_ROUTE = re.compile(
    r"/swing/trade-candidates/([0-9a-f]{16})/decision\Z"
)
_PLACEHOLDERS = {
    "/theta-earners": ("Theta Earners", "Theta Earners", ""),
    "/portfolio": ("Portfolio", "Portfolio", ""),
    "/swing/paper": ("Paper", "Swing", "Paper"),
    "/swing/ignored": ("Ignored", "Swing", "Ignored"),
}


class KronosBrowserServer(ThreadingHTTPServer):
    connection_governance = None
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = _MAX_ACTIVE_BROWSER_REQUESTS

    def __init__(
        self,
        address: tuple[str, int],
        application: SwingOpportunitiesApplication,
        v1_review: SwingV1ReviewWorkflow | None = None,
        chart_analyst_credentials: OpenAIChartAnalystCredentialService | None = None,
        chart_analyst_activation: ChartAnalystV2ActivationService | None = None,
        restart_control: BrowserBackendRestartControl | None = None,
        intraday_workstation: object | None = None,
        step32_workflow: SwingV1BrowserOperationalization | None = None,
        native_review: NativeReviewWorkflow | None = None,
        product_routes: ProductBrowserRoutes | None = None,
        progression_watches: SwingProgressionWatchWorkflow | None = None,
        visual_v3: SwingVisualV3ReviewCycle | None = None,
        visual_v3_live: SwingVisualV3LiveWorkflow | None = None,
        trade_window: SwingTradeWindowWorkflow | None = None,
        telegram: TelegramConfigurationService | None = None,
        ux10_notifications: SwingUx10NotificationService | None = None,
        refresh_reminders: SwingK5RefreshReminderWorkflow | None = None,
        notification_centre: SponsorNotificationCentre | None = None,
        provider_instrument_master_operation: (
            ProviderInstrumentMasterOperationalComposition | None
        ) = None,
        intraday_discovery_control: IntradayDiscoveryOperationalControl | None = None,
        intraday_historical_control: (
            IntradayHistoricalQualificationOperationalControl | None
        ) = None,
        mcx_supporting_context: McxSupportingContextWorkflow | None = None,
        intraday_wo09_notification_sources: (
            Callable[[], tuple[Wo09NotificationSource, ...]] | None
        ) = None,
        provider_login_navigation: object | None = None,
        bulk_import_root: Path | None = None,
        mcx_slice3: SwingMcxIntegratedWorkflow | None = None,
        mcx_v1_control: SwingMcxV1OperationalControl | None = None,
        native_intake: NativeReviewIntakeWorkflow | None = None,
        mcx_v1_composition_factory: Callable | None = None,
        swing_research_control: SwingResearchControl | None = None,
    ) -> None:
        # The research workbook imports the Browser package. Resolve its
        # composition only when constructing a server, after module import.
        from kronos.application.swing_research_control import SwingResearchControl
        if (
            address[0] != _LOOPBACK_HOST
            or not isinstance(application, SwingOpportunitiesApplication)
            or (v1_review is not None and type(v1_review) is not SwingV1ReviewWorkflow)
            or (
                chart_analyst_credentials is not None
                and type(chart_analyst_credentials)
                is not OpenAIChartAnalystCredentialService
            )
            or (
                chart_analyst_activation is not None
                and type(chart_analyst_activation)
                is not ChartAnalystV2ActivationService
            )
            or (
                restart_control is not None
                and type(restart_control) is not BrowserBackendRestartControl
            )
            or (
                step32_workflow is not None
                and type(step32_workflow) is not SwingV1BrowserOperationalization
            )
            or (
                native_review is not None
                and type(native_review) is not NativeReviewWorkflow
            )
            or (product_routes is not None and type(product_routes) is not ProductBrowserRoutes)
            or (product_routes is not None and intraday_workstation is not None)
            or (
                progression_watches is not None
                and type(progression_watches) is not SwingProgressionWatchWorkflow
            )
            or (
                visual_v3 is not None
                and type(visual_v3) is not SwingVisualV3ReviewCycle
            )
            or (
                visual_v3_live is not None
                and type(visual_v3_live) is not SwingVisualV3LiveWorkflow
            )
            or (
                trade_window is not None
                and type(trade_window) is not SwingTradeWindowWorkflow
            )
            or (
                refresh_reminders is not None
                and type(refresh_reminders) is not SwingK5RefreshReminderWorkflow
            )
            or (
                notification_centre is not None
                and type(notification_centre) is not SponsorNotificationCentre
            )
            or (
                provider_instrument_master_operation is not None
                and type(provider_instrument_master_operation)
                is not ProviderInstrumentMasterOperationalComposition
            )
            or (
                intraday_discovery_control is not None
                and type(intraday_discovery_control)
                is not IntradayDiscoveryOperationalControl
            )
            or (
                intraday_historical_control is not None
                and type(intraday_historical_control)
                is not IntradayHistoricalQualificationOperationalControl
            )
            or (
                mcx_supporting_context is not None
                and type(mcx_supporting_context) is not McxSupportingContextWorkflow
            )
            or (
                intraday_wo09_notification_sources is not None
                and not callable(intraday_wo09_notification_sources)
            )
            or (
                provider_login_navigation is not None
                and not callable(
                    getattr(provider_login_navigation, "take_redirect", None)
                )
            )
            or (bulk_import_root is not None and type(bulk_import_root) is not Path)
            or (mcx_slice3 is not None and type(mcx_slice3) is not SwingMcxIntegratedWorkflow)
            or (mcx_v1_control is not None
                and type(mcx_v1_control) is not SwingMcxV1OperationalControl)
            or (native_intake is not None
                and type(native_intake) is not NativeReviewIntakeWorkflow)
            or (swing_research_control is not None
                and type(swing_research_control) is not SwingResearchControl)
        ):
            raise ValueError("BROWSER_SERVER_MUST_BIND_LOOPBACK")
        config = OpenAIChartAnalystV2Config.from_environment()
        transport, default_credentials = _openai_chart_analyst_security(config)
        self.application = application
        # Fixture-injected isolated integration only. Production composition
        # supplies no owner and both routes fail closed.
        self.mcx_slice3 = mcx_slice3
        self.mcx_v1_control = mcx_v1_control
        self.chart_analyst_credentials = (
            chart_analyst_credentials or default_credentials
        )
        self.chart_analyst_activation = (
            chart_analyst_activation or ChartAnalystV2ActivationService()
        )
        self.restart_control = restart_control
        self.connection_governance = getattr(application, "connection_governance", None)
        self.provider_instrument_master_operation = (
            provider_instrument_master_operation
        )
        self.intraday_discovery_control = intraday_discovery_control
        self.intraday_historical_control = intraday_historical_control
        self._shutdown_lock = Lock()
        self._domain_close_lock = Lock()
        self._domain_closed = False
        self._monitoring_quiesced = False
        self.maintenance_admission = MaintenanceAdmissionCoordinator()
        self.application.bind_maintenance_admission(self.maintenance_admission)
        if self.mcx_v1_control is not None:
            self.mcx_v1_control.bind_maintenance_admission(
                self.maintenance_admission)
        self._sponsor_tickets = local()
        self._swing_projection_lock = Lock()
        self._answer_notice_lock = Lock()
        self._native_chart_stage_lock = Lock()
        self._answer_notices = {}
        self._sponsor_restoration_lock = RLock()
        self._shutdown_started = False
        self._active_sponsor_work = 0
        self._next_lifecycle_pulse = 0.0
        self.product_routes = (
            product_routes
            if product_routes is not None
            else default_product_browser_routes(
                intraday_workstation=intraday_workstation,
            )
        )
        self.step32_workflow = (
            step32_workflow or SwingV1BrowserOperationalization()
        )
        self.progression_watches = progression_watches or SwingProgressionWatchWorkflow()
        self.progression_watches.bind_maintenance_admission(self.maintenance_admission)
        self.application.register_progression_watch_workflow(self.progression_watches)
        if v1_review is not None:
            self.v1_review = v1_review
            evidence_store = LocalTradingViewEvidenceStore(
                v1_review.evidence_root
            )
        else:
            evidence_store = LocalTradingViewEvidenceStore()
            self.v1_review = SwingV1ReviewWorkflow(
                evidence_store,
                chart_analyst_v2_provider=OpenAIChartAnalystV2Provider(
                    config,
                    store=LocalChartAnalystV2Store(),
                    transport=transport,
                    activation_probe=self.chart_analyst_activation.enabled,
                ),
            )
            recovered = evidence_store.latest_review_run()
            if recovered is not None:
                parent_run, layer1_run = recovered
                provenance = LocalSwingRunProvenanceStore().load(parent_run)
                self.v1_review.publish_layer1(
                    layer1_run,
                    swing_analysis_run_identity=parent_run,
                )
                self.application.restore_v1_review_projection(
                    layer1_run,
                    provenance,
                )
                mtf_store = self.application.mtf_fact_evidence_store()
                if mtf_store is not None:
                    try:
                        self.application.restore_mtf_fact_snapshot(
                            mtf_store.load(parent_run)
                        )
                    except ValueError:
                        pass
                native_store = self.application.native_discovery_evidence_store()
                if native_store is not None:
                    try:
                        self.application.restore_native_discovery_run(
                            native_store.load(parent_run)
                        )
                    except ValueError:
                        pass
                self.step32_workflow.synchronize_review(self.v1_review)
        native_review_store = (
            NativeReviewEvidenceStore()
            if native_review is None
            else NativeReviewEvidenceStore(native_review.evidence_root)
        )
        visual_v2_diagnostic_store = LocalVisualEvidenceV2DiagnosticStore(
            native_review_store.root / "visual-v2-diagnostics"
        )
        self.native_review = native_review or NativeReviewWorkflow(
            native_review_store,
            chart_store=evidence_store,
            visual_v2_provider=OpenAIVisualEvidenceV2Provider(
                OpenAIVisualEvidenceV2Config(
                    enabled=config.enabled,
                    model_identity=config.model_identity,
                    request_timeout_seconds=config.request_timeout_seconds,
                    maximum_retries=config.maximum_retries,
                ),
                transport=transport,
                diagnostic_store=visual_v2_diagnostic_store,
            ),
            visual_v2_diagnostic_store=visual_v2_diagnostic_store,
            pdf_transport=PdfVisualReviewTransport(
                load_or_provision_pdf_visual_review_configuration(),
                PdfReviewRecordStore(native_review_store.root / "pdf-transport-v0"),
                clock=lambda: datetime.now(UTC),
            ),
        )
        governed_review_root = self.native_review.evidence_root
        if mcx_supporting_context is None:
            context_questions, context_answers = (
                default_mcx_supporting_context_directories()
            )
            context_root = governed_review_root / "mcx-supporting-context-v1"
            context_pdf_store = McxContextPdfStore(context_root / "pdf-transport")
            mcx_supporting_context = McxSupportingContextWorkflow(
                McxSupportingContextStore(context_root / "records"),
                McxContextPdfTransport(
                    PdfVisualReviewConfiguration(
                        context_questions, context_answers
                    ),
                    context_pdf_store,
                    clock=lambda: datetime.now(UTC),
                ),
                intake_store=ReviewEvidenceStore(governed_review_root),
                publication_source=self.application,
            )
        self.mcx_supporting_context = mcx_supporting_context
        receipt_status = self.application.publication_status()
        receipt_intake_enabled = (receipt_status["control"] is not None or receipt_status["reconciliation_unavailable"])
        if visual_v3_live is not None:
            if visual_v3 is not None and visual_v3_live.cycle is not visual_v3:
                raise ValueError("VISUAL_V3_LIFECYCLE_MISMATCH")
            self.visual_v3_live = visual_v3_live
            self.visual_v3 = visual_v3_live.cycle
        else:
            self.visual_v3 = visual_v3 or SwingVisualV3ReviewCycle(
                LocalVisualEvidenceV3Store(governed_review_root / "visual-v3"),
                NativeLayer2ReadinessV3Store(
                    governed_review_root / "layer2-readiness-v3"
                ),
            )
            self.visual_v3_live = SwingVisualV3LiveWorkflow(
                self.visual_v3,
                VisualV3PdfReviewTransport(
                    load_or_provision_pdf_visual_review_configuration(),
                    VisualV3PdfRecordStore(
                        governed_review_root / "pdf-transport-v3"
                    ),
                    clock=lambda: datetime.now(UTC),
                ),
                recover_historical=not receipt_intake_enabled,
            )
        if (native_intake is not None
                and (not receipt_intake_enabled
                     or native_intake.application is not self.application
                     or native_intake.native_review is not self.native_review
                     or native_intake.live is not self.visual_v3_live
                     or native_intake.store.root != governed_review_root)):
            raise ValueError("MCX_V1_NATIVE_INTAKE_MISMATCH")
        self.native_intake = (native_intake or NativeReviewIntakeWorkflow(
            self.application, self.native_review, self.visual_v3_live,
            ReviewEvidenceStore(governed_review_root))
            if receipt_intake_enabled or mcx_v1_composition_factory is not None else None)
        if (self.mcx_v1_control is not None
                and (self.mcx_slice3 is not self.mcx_v1_control.workflow
                     or self.native_review is not self.mcx_v1_control.native_review
                     or self.native_intake is not self.mcx_v1_control.review_owner)):
            raise ValueError("MCX_V1_BROWSER_OWNER_MISMATCH")
        self.bulk_import = None
        self.trade_window = trade_window or SwingTradeWindowWorkflow(
            LocalKr370Step31HandoffStore(
                governed_review_root / "kr370-step31-handoff-v1"
            ),
            LocalTradePlanStore(governed_review_root / "trade-construction-v0"),
            LocalPortfolioStateV1Store(
                governed_review_root / "portfolio-state-v1"
            ),
            LocalRiskPermissionV1Store(
                governed_review_root / "domain-007-risk-permission-v1"
            ),
            LocalKr380V2Store(governed_review_root / "kr380-entry-outcome-v2"),
            LocalObjectiveModelV1Store(
                governed_review_root / "objective-model-v1"
            ),
            LocalTradePlanConstructionDiagnosticStore(
                governed_review_root / "trade-plan-construction-diagnostics-v1"
            ),
            LocalStep31ObservationStore(
                governed_review_root / "step31-observation-v1"
            ),
            LocalSponsorObservationDecisionStore(
                governed_review_root / "sponsor-observation-decision-v1"
            ),
        )
        self.telegram = telegram or _telegram_security()
        self.provider_login_navigation = provider_login_navigation
        self.swing_monitoring_hub = SharedSwingMonitoringHub()
        self.swing_monitoring_hub.bind_maintenance_admission(self.maintenance_admission)
        self.swing_monitoring_hub.maintenance_governance = self.connection_governance
        self.swing_monitoring_hub.set_connection_listener(
            lambda state: self.ux10_notifications.observe_connection_state(
                "SHARED-SWING-MONITORING", "SWING MONITORING", state
            )
        )
        self.progression_watches.set_shared_monitoring_hub(self.swing_monitoring_hub)
        self.native_review.set_shared_monitoring_hub(self.swing_monitoring_hub)
        self.trade_window.set_shared_monitoring_hub(self.swing_monitoring_hub)
        self.ux10_notifications = ux10_notifications or SwingUx10NotificationService(
            Ux10NotificationStore(governed_review_root / "ux10-notifications-v1"),
            telegram=self.telegram,
            maintenance_admission=self.maintenance_admission,
        )
        self.refresh_reminders = refresh_reminders or SwingK5RefreshReminderWorkflow(
            K5RefreshReminderStore(
                governed_review_root / "refresh-analysis-reminders-v1"
            ),
            notification_listener=lambda reminder: (
                self.ux10_notifications.observe_refresh_analysis_reminder(
                    reminder
                ).notification_id
            ),
            maintenance_admission=self.maintenance_admission,
        )
        self.notification_centre = notification_centre or SponsorNotificationCentre(
            SponsorNotificationLifecycleStore(
                governed_review_root / "notification-centre-v1"
            ),
            reminder_boundary_resolver=self.refresh_reminders.next_repeat_boundary,
        )
        self.intraday_wo09_notification_sources = (
            intraday_wo09_notification_sources or (lambda: ())
        )
        self.progression_watches.set_ux10_listeners(
            watch_listener=self.ux10_notifications.observe_progression_watch,
            connection_listener=lambda *_values: None,
        )
        self.native_review.set_ux10_lifecycle_event_listener(
            self.ux10_notifications.observe_lifecycle_event
        )
        self.mcx_v1_composition = None
        if mcx_v1_composition_factory is not None:
            if self.mcx_v1_control is not None or self.mcx_slice3 is not None:
                raise ValueError("MCX_V1_COMPOSITION_CONFLICT")
            from kronos.application.swing_mcx_v1_composition import SwingMcxV1Composition
            composition = mcx_v1_composition_factory(self)
            if type(composition) is not SwingMcxV1Composition:
                raise ValueError("MCX_V1_COMPOSITION_INVALID")
            self.mcx_v1_composition = composition
            self.mcx_v1_control = composition.control
        native_run = self.application.native_discovery_run()
        mtf_facts = self.application.mtf_fact_snapshot()
        self.native_review_run = native_run
        self.native_review_facts = mtf_facts
        if native_run is not None and mtf_facts is not None:
            try:
                self.native_review.restore(native_run, mtf_facts)
            except ValueError:
                pass
            try:
                if self.native_intake is not None and self.native_intake.has_control():
                    self.native_intake.restore()
                else:
                    self.visual_v3_live.restore(
                        self.native_review.snapshot(), mtf_facts, self.native_review.original_chart_bytes)
            except (ValueError, PdfReviewTransportError, TradingViewEvidenceStoreError):
                # Versioned V3 restoration is fail-closed. Historical V2 remains
                # independently restorable and is never converted as recovery.
                pass
        self.native_review.bind_restored_v3_readiness(
            tuple(item.readiness for item in self.visual_v3.completed_snapshot()))
        self.trade_window.restore(self.visual_v3.completed_snapshot())
        self.native_review.journal_snapshot()
        self.trade_window.synchronize_downstream(self.native_review.snapshot())
        self._next_swing_journal_reconciliation = 0.0
        self._swing_step33_reconciliation_failure: str | None = None
        self._swing_v2_reconciliation_failure: str | None = None
        self.reconcile_progression()
        self._request_slots = BoundedSemaphore(_MAX_ACTIVE_BROWSER_REQUESTS)
        self._request_capacity_lock = Lock()
        self._active_request_count = 0
        self._request_capacity_refusals = 0
        self.request_diagnostics = RequestDiagnostics()
        self._diagnostic_requests = {}
        self.application.register_sponsor_operability_restorer(
            self.restore_sponsor_operability
        )
        self.restore_sponsor_operability()
        if not (self.connection_governance and self.connection_governance.maintenance_active):
            self.ux10_notifications.retry_pending()
        self._swing_projection_revision_value = (
            self._derive_swing_projection_revision()
        )
        if self.native_intake is not None:
            self.native_intake.configure_page_revision(
                lambda projection: self._derive_swing_projection_revision(
                    native_intake_projection=projection))
        self.application.register_analysis_reconciliation(
            self.reconcile_swing,
            (
                None
                if self.native_intake is None
                else self.native_intake.successor_page_transition
            ),
            review_owner=self.native_intake,
        )
        if swing_research_control is None:
            from kronos.application.swing_prospective_research import (
                CANONICAL_ROOT as SWING_RESEARCH_ROOT, SwingProspectiveResearchApplication,
            )
            from kronos.application.swing_research_integration import SwingResearchEventCapture
            from kronos.application.swing_research_inbox import SwingResearchInbox
            from kronos.application.swing_nse_equity_basis import NseEquityBasisStore
            from kronos.swing.v1.prospective_research import ProspectiveResearchStore
            from kronos.application.swing_research_authority import ResearchReleaseVerifier
            research = SwingProspectiveResearchApplication(
                store=ProspectiveResearchStore(SWING_RESEARCH_ROOT / "evidence"),
                publication_root=SWING_RESEARCH_ROOT)
            capture = SwingResearchEventCapture(
                research, require_commissioning=True,
                inbox=SwingResearchInbox(SWING_RESEARCH_ROOT / "capture-inbox"))
            swing_research_control = SwingResearchControl(
                application=self.application, intake=self.native_intake,
                research=research, capture=capture,
                calendar=self.application.governed_calendar_publisher(),
                native_review=self.native_review, trade_window=self.trade_window,
                mcx_control=self.mcx_v1_control,
                equity_basis=NseEquityBasisStore(SWING_RESEARCH_ROOT / "equity-basis"),
                release_verifier=ResearchReleaseVerifier(
                    Path(__file__).resolve().parents[3],
                    lambda: (None if self.connection_governance is None else
                             self.connection_governance.process.loaded_revision)))
        self.swing_research_control = swing_research_control
        capture = swing_research_control.capture
        self._research_owner_bindings = []
        def bind_research_owner(owner, callback):
            owner.register_research_capture(callback)
            self._research_owner_bindings.append((owner, callback))
        bind_research_owner(self.application,
            lambda bundle: (None if not capture.capture_enabled() or bundle.continuity is None else
                            capture.retain_admission_event(
                                bundle.continuity.contribution,
                                ticks=self.swing_monitoring_hub.latest_market_ticks)))
        if self.native_intake is not None:
            bind_research_owner(self.native_intake,
                lambda promotion: None if not capture.capture_enabled() else capture.retain_v2_event(
                    self.application.committed_continuity().contribution,
                    promotion, ticks=self.swing_monitoring_hub.latest_market_ticks))
        def capture_owner_event(kind, value):
            if not capture.capture_enabled():
                return
            capture.retain_owner_event(kind, value)
        bind_research_owner(self.native_review, capture_owner_event)
        bind_research_owner(self.trade_window, capture_owner_event)
        if self.mcx_v1_control is not None:
            bind_research_owner(self.mcx_v1_control, capture_owner_event)
        if self.native_intake is not None:
            self.native_intake.prepare_page_state()
        if self.native_intake is not None:
            runtime_root = bulk_import_root
            if runtime_root is None:
                runtime_root = (DEFAULT_BULK_IMPORT_ROOT if native_review is None else
                    governed_review_root.parent / "runtime" / "swing-bulk-import-v1")
            self.bulk_import = SwingBulkImportOwner(
                SwingBulkImportStore(runtime_root), self.native_intake,
                completion=self._complete_bulk_import,
            )
            self.bulk_import.bind_maintenance_admission(self.maintenance_admission)
        self._swing_notification_lock = RLock()
        self._swing_notification_failure = None
        self.synchronize_swing_notifications()
        super().__init__(address, _BrowserHandler)
        if self.bulk_import is not None:
            self.bulk_import.start()

    def retain_answer_notice(self, code, market=None, instrument=None, *, confirmed_no_import=True,
                             validation_only=False, validation_passed=False,
                             selected_filename=None):
        """Bounded, short-lived browser presentation only; no evidence persistence."""
        known = type(code) is str and (code in ANSWER_REJECTION_EXPLANATIONS
                                      or code == "ANSWER_BINDING_CURRENT")
        reason = code if known else "REVIEW_INTAKE_UNAVAILABLE"
        confirmed = bool(known and confirmed_no_import)
        filename = (selected_filename if type(selected_filename) is str
                    and 0 < len(selected_filename) <= 255
                    and not any(ord(char) < 32 for char in selected_filename)
                    else None)
        identifier = uuid4().hex
        diagnostic = None if confirmed else "D-" + uuid4().hex[:12]
        with self._answer_notice_lock:
            now = monotonic()
            self._answer_notices = {key: value for key, value in self._answer_notices.items()
                                    if now - value[0] <= 600}
            while len(self._answer_notices) >= 64:
                self._answer_notices.pop(next(iter(self._answer_notices)))
            self._answer_notices[identifier] = (now, dict(code=reason,
                market=market if market in {"NSE", "MCX"} else None,
                instrument=instrument if type(instrument) is str and len(instrument) <= 64
                    and instrument.isascii() and all(char.isalnum() or char in "&._- " for char in instrument)
                    else None,
                confirmed_no_import=confirmed, diagnostic_id=diagnostic,
                validation_only=bool(validation_only),
                validation_passed=bool(validation_only and validation_passed),
                selected_filename=filename))
        return identifier

    def answer_notice(self, identifier):
        if type(identifier) is not str or re.fullmatch(r"[0-9a-f]{32}", identifier) is None:
            return None
        with self._answer_notice_lock:
            retained = self._answer_notices.get(identifier)
            return None if retained is None or monotonic() - retained[0] > 600 else retained[1]

    def process_request(self, request, client_address) -> None:  # type: ignore[no-untyped-def]
        """Admit a bounded number of request owners before creating threads."""

        trace = start_trace(self.request_diagnostics)
        if not self._request_slots.acquire(blocking=False):
            if trace is not None:
                trace.outcome = "CAPACITY_REFUSED"
                trace.emit("REFUSED")  # request line has not been parsed: UNKNOWN
            with self._request_capacity_lock:
                self._request_capacity_refusals += 1
            body = b'{"failure":"BROWSER_REQUEST_CAPACITY_UNAVAILABLE"}'
            response = (
                b"HTTP/1.1 503 Service Unavailable\r\n"
                b"Content-Type: application/json; charset=utf-8\r\n"
                b"Cache-Control: no-store\r\n"
                b"Connection: close\r\n"
                + (b"" if trace is None else f"X-Kronos-Request-ID: {trace.identity}\r\n".encode("ascii"))
                + f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
                + body
            )
            try:
                request.sendall(response)
                if trace is not None:
                    trace.response(503)
            except BaseException as error:
                if trace is not None:
                    trace.failure(error)
                raise
            finally:
                try:
                    self.shutdown_request(request)
                finally:
                    if trace is not None:
                        trace.finish()
            return
        with self._request_capacity_lock:
            self._active_request_count += 1
            self._diagnostic_requests[id(request)] = trace
        if trace is not None:
            trace.emit("ADMITTED")
        try:
            super().process_request(request, client_address)
        except BaseException as error:
            if trace is not None:
                trace.failure(error)
            self._finish_request_owner(request)
            raise

    def process_request_thread(self, request, client_address) -> None:  # type: ignore[no-untyped-def]
        with self._request_capacity_lock:
            trace = self._diagnostic_requests.get(id(request))
        try:
            with bind_trace(trace):
                if trace is not None:
                    trace.emit("THREAD_STARTED")
                super().process_request_thread(request, client_address)
        finally:
            self._finish_request_owner(request)

    def finish_request(self, request, client_address) -> None:  # type: ignore[no-untyped-def]
        trace = current_trace()
        try:
            super().finish_request(request, client_address)
            if trace is not None:
                trace.emit("HANDLER_RETURNED")
        except BaseException as error:
            if trace is not None:
                trace.failure(error)
            raise

    def _finish_request_owner(self, request) -> None:
        with self._request_capacity_lock:
            self._active_request_count -= 1
            trace = self._diagnostic_requests.pop(id(request), None)
        self._request_slots.release()
        if trace is not None:
            trace.finish()  # ownership released before best-effort diagnostics

    def request_capacity_status(self) -> dict[str, int | str]:
        """Return local admission facts without waiting on application work."""

        with self._request_capacity_lock:
            return {
                "state": (
                    "SATURATED"
                    if self._active_request_count >= _MAX_ACTIVE_BROWSER_REQUESTS
                    else "AVAILABLE"
                ),
                "active": self._active_request_count,
                "maximum": _MAX_ACTIVE_BROWSER_REQUESTS,
                "refusals": self._request_capacity_refusals,
            }

    def service_actions(self) -> None:
        ticket = self.maintenance_admission.admit("SERVER_PULSE")
        if ticket is None:
            super().service_actions()
            return
        try:
            self._service_actions_admitted()
        finally:
            ticket.release()
        super().service_actions()

    def _service_actions_admitted(self) -> None:
        # Reuse the admitted server maintenance pulse. Notification GETs never
        # synchronize sources, expire cards or append reminder history.
        if hasattr(self, "_swing_notification_lock"):
            with self._swing_notification_lock:
                try:
                    self._synchronize_swing_notifications_owned()
                    self._swing_notification_failure = None
                except (ValueError, OSError, TypeError, RuntimeError):
                    self._swing_notification_failure = "SWING_NOTIFICATION_SOURCE_UNAVAILABLE"
                # Intraday owner-approved legacy relocation. Construction is not
                # a legacy-mode signal: the launcher attaches its modern owner
                # after creating this server. Never invoke this fallback in GET.
                if getattr(self, "intraday_notifications", None) is None:
                    try:
                        self.notification_centre.synchronize_wo09(
                            self.intraday_wo09_notification_sources(),
                            websocket_state=self.swing_notification_status().websocket_state)
                        self._legacy_notification_failure = None
                    except (ValueError, OSError, TypeError, KeyError, RuntimeError):
                        self._legacy_notification_failure = "LEGACY_WO09_NOTIFICATION_SOURCE_UNAVAILABLE"
        housekeeping = getattr(self, "housekeeping", None)
        if housekeeping is not None:
            try:
                housekeeping.trigger_periodic()
            except (ValueError, OSError, TypeError, RuntimeError):
                housekeeping.record_trigger_failure()
        lifecycle = getattr(self, "intraday_lifecycle", None)
        observed = monotonic()
        if lifecycle is not None and observed >= self._next_lifecycle_pulse:
            self._next_lifecycle_pulse = observed + 0.5
            try:
                lifecycle.request_pulse()
            except (ValueError, OSError, TypeError, KeyError, RuntimeError):
                lifecycle.last_failure = "WO11_RUNTIME_SERVICE_UNAVAILABLE"
        if observed >= self._next_swing_journal_reconciliation:
            self._next_swing_journal_reconciliation = observed + 5.0
            try:
                self.native_review.journal_snapshot()
            except (ValueError, OSError, TypeError, KeyError):
                self._swing_step33_reconciliation_failure = "SOURCE_UNAVAILABLE"
            else:
                self._swing_step33_reconciliation_failure = None
            try:
                self.trade_window.reconcile_journal_read_models()
            except (ValueError, OSError, TypeError, KeyError):
                self._swing_v2_reconciliation_failure = "SOURCE_UNAVAILABLE"
            else:
                self._swing_v2_reconciliation_failure = None

    def server_close(self) -> None:
        self._close_domain_owners()
        research_close = getattr(self.swing_research_control, "close", None)
        if callable(research_close):
            research_close()
        for owner, callback in reversed(getattr(self, "_research_owner_bindings", ())):
            owner.clear_research_capture(callback)
        if self.restart_control is not None:
            self.restart_control.remove()
        super().server_close()
        drain = self.maintenance_admission.snapshot()
        if drain["state"] == "STOPPING":
            self.maintenance_admission.closed(drain["generation"])

    def _close_domain_owners(self, *, bulk_timeout_seconds: float = 30,
                             require_proof: bool = False) -> None:
        """Complete domain cleanup before a successful maintenance handoff."""
        with self._domain_close_lock:
            if self._domain_closed:
                return
            self._close_domain_owners_once(bulk_timeout_seconds, require_proof)
            self._domain_closed = True

    def _quiesce_monitoring_producers(self) -> None:
        """Detach producers while accepted callbacks can still finish."""
        with self._domain_close_lock:
            if self._monitoring_quiesced:
                return
            self.progression_watches.close_monitoring()
            self.native_review.close()
            self.trade_window.close_monitoring()
            self.swing_monitoring_hub.close()
            self.application.close()
            self._monitoring_quiesced = True

    def _close_domain_owners_once(self, bulk_timeout_seconds: float,
                                  require_proof: bool) -> None:
        housekeeping = getattr(self, "housekeeping", None)
        if housekeeping is not None:
            result = (housekeeping.shutdown(timeout_seconds=bulk_timeout_seconds)
                      if require_proof else housekeeping.shutdown())
            if require_proof and (not isinstance(result, dict)
                                  or result.get("lifecycle_state") != "STOPPED"):
                raise RuntimeError("MAINTENANCE_HOUSEKEEPING_NOT_DRAINED")
        bulk_import = getattr(self, "bulk_import", None)
        if bulk_import is not None:
            if require_proof:
                bulk_import.close(timeout_seconds=bulk_timeout_seconds)
            else:
                bulk_import.close()
        notifications = getattr(self, "intraday_notifications", None)
        if notifications is not None:
            if require_proof:
                notifications.close(wait=False)
            else:
                notifications.close()
        lifecycle = getattr(self, "intraday_lifecycle", None)
        if lifecycle is not None:
            lifecycle.shutdown()
        wo17_monitoring = getattr(self, "intraday_wo17_monitoring", None)
        if wo17_monitoring is not None:
            wo17_monitoring.shutdown()
        # Governed maintenance quiesces these producers before its final drain.
        if not self._monitoring_quiesced:
            self.application.close()
        self.refresh_reminders.close()
        self.ux10_notifications.close()
        if not self._monitoring_quiesced:
            self.progression_watches.close_monitoring()
            self.native_review.close()
            self.trade_window.close_monitoring()
            self.swing_monitoring_hub.close()
        self.step32_workflow.close()
        mcx_control = getattr(self, "mcx_v1_control", None)
        if mcx_control is not None:
            mcx_control.close()
        provider_runtime = getattr(self, "provider_runtime", None)
        if require_proof and provider_runtime is not None:
            provider_runtime.end_kronos_session()

    def _complete_bulk_import(self) -> None:
        """Publish projections only after the durable application work completes."""
        try:
            scope = (nullcontext() if self.native_intake is None else
                     self.native_intake.reconciliation_scope())
            with scope:
                self.trade_window.restore(self.visual_v3.completed_snapshot())
                self.refresh_swing_projection_revision()
        except (OSError, TypeError, ValueError):
            _LOG.warning("swing_bulk_import projection_refresh_unavailable")

    def progression_snapshot(self) -> SwingProgressionWatchSnapshot:
        """Observational access: no retention, notifications or monitoring."""
        return self.progression_watches.snapshot()

    def reconcile_swing(self):
        """Fence the entire reconciliation, including work before preparation."""
        scope = (nullcontext() if self.native_intake is None else
                 self.native_intake.reconciliation_scope())
        with scope:
            self._reconcile_swing_prepared()

    def _reconcile_swing_prepared(self):
        """Explicit committed-analysis or authorized downstream mutation boundary."""
        run = self.application.native_discovery_run()
        facts = self.application.mtf_fact_snapshot()
        if run is not None and facts is not None and run.run_identity == facts.run_identity:
            self.native_review_run, self.native_review_facts = run, facts
        self._synchronize_trade_window()
        self.native_review.journal_snapshot()
        self.reconcile_progression()
        if self.native_intake is None:
            self.refresh_swing_projection_revision()
            return
        generation = self.native_intake.prepare_page_generation()
        if generation is None:
            failure = self.native_intake.page_state_status()["failure"]
            raise ValueError(failure or "SWING_PAGE_PREPARATION_UNAVAILABLE")
        projection = self.native_intake.prepared_page_projection(generation)
        revision = self._derive_swing_projection_revision(
            native_intake_projection=projection
        )
        if not self.native_intake.publish_page_generation(generation):
            failure = self.native_intake.page_state_status()["failure"]
            raise ValueError(failure or "SWING_PAGE_PREPARATION_UNAVAILABLE")
        # Legacy field is retained for compositions without an intake owner.
        # Configured Review readers use the capsule, not this independent field.
        with self._swing_projection_lock:
            self._swing_projection_revision_value = revision

    def swing_notification_status(self):
        """Read-only Swing polling; never projects/retains Intraday sources."""
        websocket = websocket_presentation_state(
            monitoring_required=self.swing_monitoring_hub.subscription_count > 0,
            connection_state=self.swing_monitoring_hub.connection_state)
        return self.notification_centre.snapshot(product="SWING", websocket_state=websocket.value)

    def reconcile_progression(self) -> SwingProgressionWatchSnapshot:
        """Project UX-08 requirements from one immutable Native/Review binding."""

        _, run = self.application.opportunities_projection()
        review = self.native_review.snapshot()
        if run is None or review.native_run_identity != run.run_identity:
            self.refresh_reminders.synchronize(None, (), {})
            return self.progression_watches.synchronize(None, ())
        requirements = []
        promotions = []
        for assessment in run.assessments:
            if assessment.status.value != "PROBABLE":
                continue
            review_requirement = review.requirement_for(
                assessment.canonical_instrument
            )
            if (
                review_requirement is None
                or review_requirement.thesis.native_assessment_sha256
                != assessment.result_sha256
            ):
                continue
            completed_v3 = (
                None
                if self.visual_v3 is None
                else self.visual_v3.completed_for(
                    run.run_identity, assessment.canonical_instrument
                )
            )
            if completed_v3 is not None:
                if completed_v3.promotion_v2 is not None:
                    if self.native_intake is None or (
                        self.native_intake.v2_for(
                            run.run_identity, assessment.canonical_instrument
                        ) != completed_v3.promotion_v2
                    ):
                        raise ValueError("KR370_V2_PROGRESSION_CURRENTNESS_INVALID")
                    promotions.append(completed_v3.promotion_v2)
                    requirements.extend(
                        derive_kr370_v2_progression_requirements(
                            completed_v3.promotion_v2
                        )
                    )
                    continue
                if completed_v3.promotion is not None:
                    promotions.append(completed_v3.promotion)
                    requirements.extend(
                        derive_kr370_progression_requirements(
                            completed_v3.promotion
                        )
                    )
                    continue
                requirements.extend(derive_v3_progression_requirements(
                    requirement=completed_v3.requirement,
                    machine_facts=completed_v3.mtf_snapshot.instrument(
                        assessment.canonical_instrument
                    ).reference_facts,
                    visual=completed_v3.responses,
                    readiness=completed_v3.readiness,
                    provenance=tuple(dict.fromkeys((
                        *assessment.provider_provenance,
                        *assessment.calendar_provenance,
                        assessment.policy_identity,
                        completed_v3.readiness.binding_policy_identity,
                        completed_v3.readiness.question_set_identity,
                    ))),
                ))
                continue
            readiness = next((
                item for item in review.readiness_records
                if item.run_identity == run.run_identity
                and item.canonical_instrument == assessment.canonical_instrument
                and item.native_assessment_sha256 == assessment.result_sha256
            ), None)
            visual = tuple(
                item for item in review.visual_v2_results
                if item.native_run_identity == run.run_identity
                and item.native_canonical_instrument == assessment.canonical_instrument
                and item.native_assessment_sha256 == assessment.result_sha256
            )
            missing = ()
            if readiness is not None:
                missing = present_native_readiness(
                    readiness, review_requirement, visual
                ).missing_evidence
            boundary = max(
                (value for _, value in assessment.factual_boundaries),
                default=run.observed_at,
            )
            requirements.extend(derive_progression_requirements(
                canonical_instrument=assessment.canonical_instrument,
                direction=assessment.direction,
                native_run_identity=run.run_identity,
                native_assessment_sha256=assessment.result_sha256,
                source_analytical_state=(
                    readiness.readiness.value
                    if readiness is not None else "REVIEW_REQUIRED"
                ),
                observation_boundary=boundary,
                provenance=tuple(dict.fromkeys((
                    *assessment.provider_provenance,
                    *assessment.calendar_provenance,
                    assessment.policy_identity,
                ))),
                readiness=readiness,
                missing_evidence=missing,
            ))
        snapshot = self.progression_watches.synchronize(
            run.run_identity, tuple(requirements)
        )
        self.ux10_notifications.observe_promotions(tuple(promotions))
        self.refresh_reminders.synchronize(
            run.run_identity,
            tuple(promotions),
            {
                item.canonical_instrument: item.product_path.name
                for item in run.assessments
            },
        )
        watchable = tuple(
            item.requirement_id for item in snapshot.requirements
            if item.state.value == "WATCH_AVAILABLE"
            and item.source_analytical_state in {"BUY_READY", "SELL_READY"}
        )
        if watchable:
            self.application.auto_activate_progression_watches(watchable)
            snapshot = self.progression_watches.snapshot()
            for watch in snapshot.watches:
                if watch.state.value == "ACTIVE":
                    self.ux10_notifications.observe_progression_monitoring_activation(
                        watch
                    )
        return snapshot

    def sponsor_notification_snapshot(self):  # type: ignore[no-untyped-def]
        """Compatibility read: the maintenance owner composes durable state."""
        return self.swing_notification_status()

    def synchronize_swing_notifications(self):
        with self._swing_notification_lock:
            return self._synchronize_swing_notifications_owned()

    def _synchronize_swing_notifications_owned(self):
        """Single existing maintenance owner; Swing-only persistence boundary."""

        progression = self.progression_snapshot()
        watches = project_swing_notification_workspace(progression)
        hidden = {watch.watch_id for watch in progression.watches if watch.workspace_hidden}
        ux10 = self.ux10_notifications.snapshot()
        ux10 = type(ux10)(tuple(event for event in ux10.records
            if not (event.family.value == "PROMOTION_WATCH" and event.watch_identity in hidden)))
        try:
            run, _ = self.application.current_run_control_authority()
        except (OSError, ValueError):
            run = None
        websocket = websocket_presentation_state(
            monitoring_required=self.swing_monitoring_hub.subscription_count > 0,
            connection_state=self.swing_monitoring_hub.connection_state,
        )
        self.notification_centre.synchronize(
            watches,
            ux10,
            current_run_identity=None if run is None else run.run_identity,
            websocket_state=websocket.value,
        )
        return self.notification_centre.snapshot(product="SWING", websocket_state=websocket.value)

    def swing_notification_indicators(self, centre):
        events = {item.notification_id: item for item in self.ux10_notifications.snapshot().records}
        indicators = {}
        for item in centre.records:
            evidence = None
            if item.source_kind == "UX08_WATCH":
                evidence = self.progression_watches.notification_monitoring_evidence(item.source_identity)
            elif item.source_kind == "UX10_EVENT":
                event = events.get(item.source_identity)
                if event is not None:
                    if event.notification_type.value in {"STOP_LEVEL_TOUCHED", "TARGET_LEVEL_TOUCHED",
                            "REFRESH_ANALYSIS_REMINDER", "WEBSOCKET_RESTORED"}:
                        indicators[item.notification_identity] = "NOT_REQUIRED"
                        continue
                    if event.notification_type.value == "ACTIVE_TRADE_MONITORING_ACTIVATED":
                        evidence = self.native_review.notification_monitoring_evidence(event.lifecycle_event_identity)
                    elif event.watch_identity is not None:
                        evidence = self.progression_watches.notification_monitoring_evidence(event.watch_identity)
            indicators[item.notification_identity] = monitoring_indicator(evidence)
        return indicators

    def swing_notification_evidence(self, kind, identity):
        """Resolve the requested retained identity, never substitute current run."""
        if kind == "UX08_WATCH":
            watch = next((w for w in self.progression_snapshot().watches if w.watch_id == identity), None)
            binding = None if watch is None else dict(kind="PROGRESSION_WATCH",
                watch_identity=watch.watch_id, run_identity=watch.requirement.native_run_identity,
                instrument=watch.requirement.canonical_instrument,
                requirement_identity=watch.requirement.requirement_id, state=watch.state.value,
                event_identities=[event.event_id for event in watch.history])
            event = None
        else:
            event = next((e for e in self.ux10_notifications.snapshot().records if e.notification_id == identity), None)
            binding = None if event is None else self.ux10_notifications.evidence(identity)
        try:
            run, _ = self.application.current_run_control_authority()
        except (OSError, ValueError):
            run = None
        retained_run = (binding or {}).get("run_identity") or (None if event is None else event.run_identity)
        currentness = ("CURRENT RUN" if run is not None and retained_run == run.run_identity
            else "HISTORICAL RUN" if retained_run is not None and run is not None
            else "CURRENTNESS UNAVAILABLE" if retained_run is not None else "RETAINED EVENT")
        return dict(kind=kind, identity=identity, currentness=currentness,
            upstream=binding, upstream_status="RETAINED SOURCE BINDING" if binding else "UPSTREAM EVIDENCE UNAVAILABLE",
            notification_event=None if event is None else dict(notification_id=event.notification_id,
                source_event_identity=event.source_event_identity, run_identity=event.run_identity,
                instrument=event.instrument, watch_identity=event.watch_identity,
                trade_identity=event.trade_identity, lifecycle_event_identity=event.lifecycle_event_identity,
                delivery=event.telegram_delivery_state.value,
                attempt_identity=event.delivery_attempt_identity))

    def active_live_monitoring_count(self) -> int:
        """Count owned live subscriptions without changing retained watch truth."""

        return (
            self.progression_watches.active_monitoring_count
            + self.native_review.active_monitoring_count
            + self.trade_window.active_monitoring_count
        )

    @staticmethod
    def _presentation_promotion_binding(completed, current):  # type: ignore[no-untyped-def]
        """Return true only for a validated pre-V2 review with no V2 authority."""

        if current is None and completed.promotion_v2 is None:
            try:
                if type(completed.promotion) is not Kr370AnalyticalPromotionRecord:
                    raise ValueError
                completed.promotion.__post_init__()
                completed.__post_init__()
            except (AttributeError, KeyError, TypeError, ValueError) as error:
                raise ValueError("V2_PROMOTION_PRESENTATION_BINDING_INVALID") from error
            return True
        if type(current) is not V2PromotionRecord or completed.promotion_v2 != current:
            raise ValueError("V2_PROMOTION_PRESENTATION_BINDING_INVALID")
        try:
            current.__post_init__()
            completed.__post_init__()
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            raise ValueError("V2_PROMOTION_PRESENTATION_BINDING_INVALID") from error
        return False

    def visual_v3_presentations(self):  # type: ignore[no-untyped-def]
        _, current_run = self.application.opportunities_projection()
        result = []
        for item in self.visual_v3.completed_snapshot():
            is_current_v2 = (self.native_intake is not None and current_run is not None
                             and item.requirement.native_run_identity == current_run.run_identity)
            if is_current_v2:
                if not self.native_intake.downstream_applicable(item):
                    continue
                current = self.native_intake.v2_for(
                    item.requirement.native_run_identity, item.requirement.canonical_instrument)
                self._presentation_promotion_binding(item, current)
            relative = None
            if is_current_v2 and item.promotion_v2 is not None and (
                    item.promotion_v2.value["source"]["asset_class"] == "NSE_EQUITY"):
                relative = self.relative_context_for_run(item.requirement.native_run_identity)
            result.append(present_visual_v3_review(
                item, relative_context=relative))
        return tuple(result)

    def current_v2_promotions(self, discovery, *, prepared=None):  # type: ignore[no-untyped-def]
        """Read exact current owner decisions without evaluating or restoring them."""
        if self.native_intake is None or discovery is None:
            return ()
        records = []
        for assessment in discovery.assessments:
            if assessment.status.value != "PROBABLE":
                continue
            if prepared is None:
                record = self.native_intake.v2_for(
                    discovery.run_identity, assessment.canonical_instrument)
            else:
                record = self.native_intake.v2_for(
                    discovery.run_identity, assessment.canonical_instrument,
                    _response=prepared)
            if record is None:
                completed = self.visual_v3.completed_for(
                    discovery.run_identity, assessment.canonical_instrument)
                if completed is not None and completed.promotion_v2 is not None:
                    raise ValueError("V2_PROMOTION_PRESENTATION_BINDING_INVALID")
                continue
            if type(record) is not V2PromotionRecord:
                raise ValueError("V2_PROMOTION_PRESENTATION_VERSION_INVALID")
            try:
                record.__post_init__()
            except (AttributeError, KeyError, TypeError, ValueError) as error:
                raise ValueError("V2_PROMOTION_PRESENTATION_BINDING_INVALID") from error
            source = record.value["source"]
            if (source["native_run_identity"] != discovery.run_identity
                    or source["canonical_instrument"] != assessment.canonical_instrument
                    or source["native_assessment_sha256"] != assessment.result_sha256):
                raise ValueError("V2_PROMOTION_PRESENTATION_BINDING_INVALID")
            completed = self.visual_v3.completed_for(
                discovery.run_identity, assessment.canonical_instrument)
            if source["market"] == "NSE" and (
                    completed is None or completed.promotion_v2 != record):
                raise ValueError("V2_PROMOTION_PRESENTATION_BINDING_INVALID")
            records.append(record)
        if len({item.value["source"]["canonical_instrument"] for item in records}) != len(records):
            raise ValueError("V2_PROMOTION_PRESENTATION_AMBIGUOUS")
        return tuple(records)

    def selected_opportunity_presentations(self, discovery, *, prepared=None,
                                           authority_is_current=lambda: True):
        """Select exact displayed identities after a coherent restoration boundary."""

        # Authentication completion deliberately precedes Sponsor restoration.
        # The terminal Provider-state refresh can therefore request this page
        # while restoration is publishing downstream Trade Window state.  Wait
        # at the restoration boundary; never reinterpret that bounded interval
        # as a stale selected contract.
        with diagnostic_lock(self._sponsor_restoration_lock, "RESTORATION_LOCK"):
            with diagnostic_stage("SELECTED_PRESENTATIONS"):
                return KronosBrowserServer._selected_opportunity_presentations(
                    self,
                    discovery,
                    prepared=prepared,
                    authority_is_current=authority_is_current,
                )

    def _selected_opportunity_presentations(self, discovery, *, prepared=None,
                                            authority_is_current=lambda: True):
        """Project one exact publication; identity changes still fail closed."""
        visual, windows = [], []
        if discovery is None:
            return (), ()
        relative_loader = getattr(self, "relative_context_for_run", None)
        relative_run = (relative_loader(discovery.run_identity)
                        if callable(relative_loader) else None)
        for assessment in discovery.assessments:
            if assessment.status.value != "PROBABLE":
                continue
            key = (discovery.run_identity, assessment.canonical_instrument)
            completed = self.visual_v3.completed_for(*key)
            legacy_v1_only = False
            selected_v2 = None
            if completed is not None:
                try:
                    if type(completed) is not CompletedVisualV3Review:
                        raise ValueError
                    completed.__post_init__()
                    requirement = completed.requirement
                    if (requirement.native_run_identity, requirement.canonical_instrument) != key:
                        raise ValueError
                except (AttributeError, KeyError, TypeError, ValueError) as error:
                    raise ValueError("SWING_TRADE_WINDOW_SELECTION_CORRUPT") from error
                if requirement.thesis.native_assessment_sha256 != assessment.result_sha256:
                    raise ValueError("SWING_TRADE_WINDOW_SELECTION_STALE")
                if self.native_intake is None or self.native_intake.downstream_applicable(
                        completed, _response=prepared):
                    if self.native_intake is not None:
                        selected = (self.native_intake.v2_for(*key) if prepared is None
                                    else self.native_intake.v2_for(*key, _response=prepared))
                        legacy_v1_only = self._presentation_promotion_binding(
                            completed, selected)
                        selected_v2 = None if legacy_v1_only else selected
                    visual.append(present_visual_v3_review(
                        completed,
                        relative_context=(
                            relative_run
                            if selected_v2 is not None and selected_v2.value["source"][
                                "asset_class"] == "NSE_EQUITY"
                            else None
                        ),
                    ))
            # The Trade Window owner selects independently. The Visual V3 cache
            # above cannot authorize or select its retained completion record.
            with diagnostic_stage("TRADE_WINDOW"):
                window = (None if legacy_v1_only else self.trade_window.project_selected(
                    *key, assessment.result_sha256,
                    authority_is_current=authority_is_current))
            if window is not None:
                windows.append(window)
        return tuple(visual), tuple(windows)

    def swing_projection_revision(self) -> str:
        """Return the last atomically published Swing presentation revision."""

        if self.native_intake is not None:
            return self.native_intake.page_revision()
        with self._swing_projection_lock:
            return self._swing_projection_revision_value

    def refresh_swing_projection_revision(self) -> str:
        """Publish a revision only after a governed state-changing route succeeds."""

        if self.native_intake is not None:
            if not self.native_intake.prepare_page_state():
                raise ValueError(self.native_intake.page_state_status()["failure"]
                                 or "SWING_PAGE_PREPARATION_UNAVAILABLE")
            return self.native_intake.page_revision()
        revision = self._derive_swing_projection_revision()
        with self._swing_projection_lock:
            self._swing_projection_revision_value = revision
        return revision

    def _derive_swing_projection_revision(
        self, *, native_intake_projection=None
    ) -> str:
        """Derive deterministic presentation metadata from restored authority.

        The revision is derived only from immutable, restored V3/KR-370 records
        for the current Native run.  It is presentation synchronization metadata;
        it neither evaluates analysis nor advances any domain state.
        """

        _, discovery = self.application.opportunities_projection()
        run_identity = None if discovery is None else discovery.run_identity
        completed = tuple(
            item for item in self.visual_v3.completed_snapshot()
            if item.requirement.native_run_identity == run_identity
        )
        payload = {
            "native_run_identity": run_identity,
            "completed": [
                {
                    "canonical_instrument": item.requirement.canonical_instrument,
                    "native_assessment_sha256": (
                        item.requirement.thesis.native_assessment_sha256
                    ),
                    "readiness_identity": item.readiness.result_sha256,
                    "review_pack_identity": (
                        None if item.review_pack is None
                        else item.review_pack.review_pack_id
                    ),
                    "promotion_identity": (
                        None if item.promotion is None
                        else item.promotion.integrity_sha256
                    ),
                }
                for item in sorted(
                    completed,
                    key=lambda value: value.requirement.canonical_instrument,
                )
            ],
        }
        if self.native_intake is not None:
            intake = (
                self.native_intake.snapshot()
                if native_intake_projection is None
                else native_intake_projection
            )
            workspace = intake.get("workspace")
            payload["native_intake"] = {
                **intake,
                # Continuity belongs to the immutable manifest represented in
                # workspace; do not serialize domain objects as incidental text.
                "rows": [{key: value for key, value in row.items() if key != "continuity"}
                         for row in intake["rows"]],
                "workspace": None if workspace is None else {
                    **workspace, "analysis_time": workspace["analysis_time"].isoformat()},
            }
        return sha256(
            json.dumps(
                payload, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()

    def relative_context_for_run(self, run_identity: str):  # type: ignore[no-untyped-def]
        """Restore only exact-run supporting context; never select global latest."""

        current = self.application.relative_context_run()
        if current is not None and current.run_identity == run_identity:
            return current
        store = self.application.relative_context_evidence_store()
        if store is None:
            return None
        try:
            return store.load(run_identity)
        except ValueError:
            return None

    def _provider_capability(self):  # type: ignore[no-untyped-def]
        capability_getter = getattr(
            self.application, "authenticated_read_only_capability", None
        )
        capability = capability_getter() if callable(capability_getter) else None
        if capability is None or getattr(capability, "active", False) is not True:
            raise ValueError("KITE_READ_ONLY_CAPABILITY_UNAVAILABLE")
        return capability

    def _execution_context(
        self, capability: object, canonical_instrument: str
    ):  # type: ignore[no-untyped-def]
        record = resolve_governed_monitoring_instrument(
            capability, canonical_instrument, datetime.now().astimezone().date()
        )
        member = next(
            (
                item for item in enabled_swing_phase1_universe()
                if item.canonical_identity == canonical_instrument
            ),
            None,
        )
        if member is None:
            raise ValueError("GOVERNED_INSTRUMENT_INVALID")
        context = publish_instrument_context(
            canonical_instrument, member.asset_class.value, record
        )
        return record, context

    def _operability_context(self, canonical_instrument: str):  # type: ignore[no-untyped-def]
        capability = self._provider_capability()
        record, context = self._execution_context(capability, canonical_instrument)
        return capability, record, context

    def _synchronize_trade_window(self) -> None:
        review = self.native_review.snapshot()
        self.trade_window.synchronize_downstream(review)
        self.trade_window.synchronize_sponsor_monitoring(
            self.native_review.active_lifecycle_monitoring_ids
        )

    def construct_current_trade_plan(
        self,
        run_identity: str,
        canonical_instrument: str,
        native_assessment_sha256: str,
    ):
        """Perform the bounded production composition behind the Sponsor action."""
        # The HTTP form is not the only possible caller. No MCX attempt,
        # Provider lookup or durable Step-31 record may precede commissioning.
        if canonical_instrument in MCX_SWING_FAMILIES:
            raise ValueError("MCX_STEP31_NOT_COMMISSIONED")
        attempt_timestamp = datetime.now(UTC)
        attempt_identity = sha256(
            (
                f"{run_identity}:{canonical_instrument}:{native_assessment_sha256}:"
                f"{attempt_timestamp.isoformat()}:{uuid4().hex}"
            ).encode("utf-8")
        ).hexdigest()
        stage = TradePlanConstructionStage.CURRENT_BINDING
        try:
            _, discovery = self.application.opportunities_projection()
            if discovery is None or discovery.run_identity != run_identity:
                raise ValueError("CURRENT_NATIVE_RUN_MISMATCH")
            assessment = next((
                item for item in discovery.assessments
                if item.canonical_instrument == canonical_instrument
                and item.result_sha256 == native_assessment_sha256
            ), None)
            completed = self.visual_v3.completed_for(
                run_identity, canonical_instrument
            )
            if (
                assessment is None
                or completed is None
                or (self.native_intake is None and completed.promotion is None)
                or (self.native_intake is not None and completed.promotion_v2 is None)
                or completed.requirement.thesis.native_assessment_sha256
                != native_assessment_sha256
                or (self.native_intake is not None and not self.native_intake.downstream_applicable(completed))
            ):
                raise ValueError("CURRENT_NATIVE_ASSESSMENT_MISMATCH")
            if self.native_intake is not None:
                current_v2 = self.native_intake.v2_for(run_identity, canonical_instrument)
                if current_v2 is None or current_v2 != completed.promotion_v2:
                    raise ValueError("CURRENT_V2_PROMOTION_STALE")

            stage = TradePlanConstructionStage.PROVIDER_CAPABILITY
            capability = self._provider_capability()
            stage = TradePlanConstructionStage.EXECUTION_CONTEXT
            instrument, context = self._execution_context(
                capability, canonical_instrument
            )
            projection = self.trade_window.project(run_identity, canonical_instrument)
            if projection is None or projection.trade_plan is None:
                stage = TradePlanConstructionStage.EVIDENCE_PACKAGE
                evidence = build_current_trade_construction_evidence(completed)

                def retain_stage(value: TradePlanConstructionStage) -> None:
                    nonlocal stage
                    stage = value

                if self.native_intake is not None and self.native_intake.v2_for(
                    run_identity, canonical_instrument
                ) != completed.promotion_v2:
                    raise ValueError("CURRENT_V2_PROMOTION_STALE")
                projection = self.trade_window.construct(
                    completed,
                    evidence,
                    context,
                    current_run_identity=run_identity,
                    current_analysis_boundary=completed.readiness.analysis_boundary,
                    created_at=attempt_timestamp,
                    stage_listener=retain_stage,
                )
            plan = projection.trade_plan
            if plan is None:
                if projection.step31_observation is not None:
                    self.trade_window.retain_construction_attempt(
                        attempt_identity=attempt_identity,
                        run_identity=run_identity,
                        canonical_instrument=canonical_instrument,
                        native_assessment_sha256=native_assessment_sha256,
                        attempt_timestamp=attempt_timestamp,
                        stage=stage,
                        result=TradePlanConstructionAttemptResult.SUCCEEDED,
                    )
                    return self.trade_window.project(
                        run_identity, canonical_instrument
                    )
                self._retain_trade_plan_attempt(
                    attempt_identity,
                    run_identity,
                    canonical_instrument,
                    native_assessment_sha256,
                    attempt_timestamp,
                    stage,
                    projection.reason,
                )
                return self.trade_window.project(run_identity, canonical_instrument)

            stage = TradePlanConstructionStage.PORTFOLIO_STATE
            review = self.native_review.snapshot()
            self.trade_window.publish_current_portfolio_state(
                review,
                native_run_identity=run_identity,
                as_of_boundary=plan.observation_boundary,
            )
            stage = TradePlanConstructionStage.DOMAIN007_RISK
            risk = self.trade_window.evaluate_current_risk(
                run_identity, canonical_instrument, evaluated_at=datetime.now(UTC)
            )
            if risk.permits_entry:
                stage = TradePlanConstructionStage.ECPC_KR380
                self.native_review.bind_operability_inputs(
                    plan, risk, context, v3_readiness=completed.readiness)
                self.trade_window.mark_sponsor_controls_available(plan.trade_plan_id)
                one_hour = completed.mtf_snapshot.instrument(
                    canonical_instrument
                ).fact(FactualTimeframe.ONE_HOUR)
                binding = "KR380-MONITORING-" + sha256(
                    f"{plan.trade_plan_id}:{one_hour.session_identity}".encode("utf-8")
                ).hexdigest()
                current = self.trade_window.project(run_identity, canonical_instrument)
                if current is None or current.kr380_entry_outcome_id is None:
                    self.trade_window.evaluate_current_entry_timing(
                        run_identity,
                        canonical_instrument,
                        session_identity=one_hour.session_identity,
                        observation_boundary=one_hour.observation_boundary,
                        ecpc_outcome=EcpcV2Outcome.PENDING,
                        ecpc_blockers=(
                            EcpcV2Blocker.EXECUTION_CONFIRMATION_PENDING,
                        ),
                        previous=None,
                        current=None,
                        evaluated_at=datetime.now(UTC),
                        monitoring_binding_id=binding,
                    )
                try:
                    self.trade_window.start_current_entry_monitoring(
                        run_identity,
                        canonical_instrument,
                        capability=capability,
                        instrument=instrument,
                        session_identity=one_hour.session_identity,
                        observation_boundary=one_hour.observation_boundary,
                        ecpc_outcome=EcpcV2Outcome.PENDING,
                        ecpc_blockers=(
                            EcpcV2Blocker.EXECUTION_CONFIRMATION_PENDING,
                        ),
                    )
                except ValueError as error:
                    _LOG.warning("KR380 monitoring not active: %s", error)
            self._synchronize_trade_window()
            self.trade_window.retain_construction_attempt(
                attempt_identity=attempt_identity,
                run_identity=run_identity,
                canonical_instrument=canonical_instrument,
                native_assessment_sha256=native_assessment_sha256,
                attempt_timestamp=attempt_timestamp,
                stage=stage,
                result=TradePlanConstructionAttemptResult.SUCCEEDED,
            )
        except (UnicodeDecodeError, ValueError) as error:
            self._retain_trade_plan_attempt(
                attempt_identity,
                run_identity,
                canonical_instrument,
                native_assessment_sha256,
                attempt_timestamp,
                stage,
                str(error),
            )
        return self.trade_window.project(run_identity, canonical_instrument)

    def _retain_trade_plan_attempt(
        self,
        attempt_identity: str,
        run_identity: str,
        canonical_instrument: str,
        native_assessment_sha256: str,
        attempt_timestamp: datetime,
        stage: TradePlanConstructionStage,
        raw_code: str,
    ) -> None:
        code, reason = _safe_trade_plan_construction_failure(stage, raw_code)
        self.trade_window.retain_construction_attempt(
            attempt_identity=attempt_identity,
            run_identity=run_identity,
            canonical_instrument=canonical_instrument,
            native_assessment_sha256=native_assessment_sha256,
            attempt_timestamp=attempt_timestamp,
            stage=stage,
            result=TradePlanConstructionAttemptResult.FAILED,
            safe_failure_code=code,
            safe_bounded_reason=reason,
        )

    def restore_sponsor_operability(self, completed_capability: object | None = None) -> None:
        """Restore persisted controls and shared monitoring without creating analysis."""

        with diagnostic_operation(self):
            with diagnostic_lock(self._sponsor_restoration_lock, "RESTORATION_LOCK"):
                if self.connection_governance and self.connection_governance.maintenance_active:
                    return
                with diagnostic_stage("SPONSOR_RESTORATION"):
                    self._restore_sponsor_operability(completed_capability)

    def _restore_sponsor_operability(self, completed_capability: object | None) -> None:
        capability_getter = getattr(
            self.application, "authenticated_read_only_capability", None
        )
        capability = capability_getter() if callable(capability_getter) else None
        if completed_capability is not None and capability is not completed_capability:
            return
        if capability is None or getattr(capability, "active", False) is not True:
            self.monitoring_restoration_state = "DEFERRED_PROVIDER_DISCONNECTED"
            self._synchronize_trade_window()
            return
        self.monitoring_restoration_state = "RESTORATION_ATTEMPTED_SEE_OWNER_EVIDENCE"
        for plan, risk in self.trade_window.sponsor_control_restoration_inputs():
            if not risk.permits_entry:
                continue
            try:
                _, _, context = self._operability_context(
                    plan.canonical_instrument
                )
                self.native_review.bind_operability_inputs(plan, risk, context)
                self.trade_window.mark_sponsor_controls_available(plan.trade_plan_id)
            except Exception as error:
                _LOG.warning("Sponsor operability restoration not active: %s", paper_monitoring_failure_reason(error))
                continue
        try:
            self.trade_window.restore_current_entry_monitoring(
                capability, resolve_governed_monitoring_instrument
            )
        except Exception as error:
            _LOG.warning("KR380 restoration not active: %s", paper_monitoring_failure_reason(error))
        try:
            committed = self.application.committed_continuity()
            committed_identity = (
                None if committed is None else
                committed.contribution.integrity_sha256
            )

            def current_paper_authority(track):
                if committed is None:
                    return None
                row = next((
                    item for item in committed.contribution.rows
                    if item.canonical_instrument == track.canonical_instrument
                ), None)
                if (
                    row is None
                    or row.opportunity_id is None
                    or row.material_revision is None
                    or row.source_binding is None
                ):
                    return None
                try:
                    return self.trade_window.prepare_paper_observation_monitoring_authority(
                        committed.contribution.native_run.run_identity,
                        track.canonical_instrument,
                        opportunity_identity=row.opportunity_id,
                        material_revision=row.material_revision,
                        source_binding=row.source_binding,
                    )
                except (TypeError, ValueError):
                    return None

            def paper_generation_is_current() -> bool:
                current = self.application.committed_continuity()
                return (
                    self.application.authenticated_read_only_capability()
                    is capability
                    and current is not None
                    and current.contribution.integrity_sha256
                    == committed_identity
                )

            self.trade_window.restore_paper_observation_monitoring(
                capability,
                lambda instrument: resolve_governed_monitoring_instrument(
                    capability, instrument, datetime.now().astimezone().date()
                ),
                current_paper_authority,
                paper_generation_is_current,
            )
            self.monitoring_restoration_state = (
                self.trade_window.paper_observation_restoration_status()
            )
        except Exception as error:
            _LOG.warning("Paper observation restoration not active: %s", paper_monitoring_failure_reason(error))
        try:
            restored = self.native_review.restore_lifecycle_monitoring(
                capability,
                lambda instrument: resolve_governed_monitoring_instrument(
                    capability, instrument, datetime.now().astimezone().date()
                ),
            )
        except Exception as error:
            restored = ()
            _LOG.warning("Active lifecycle restoration not active: %s", paper_monitoring_failure_reason(error))
        lifecycle = self.native_review.snapshot().active_lifecycle
        for position_id in restored:
            position = next(
                item for item in lifecycle.active if item.position_id == position_id
            )
            self.ux10_notifications.observe_active_trade_monitoring_activation(
                position
            )
        self._synchronize_trade_window()

    def native_review_version(self) -> str:
        """Select by the persisted current Review identity, never module presence."""

        if self.visual_v3_live.restoration_error is not None:
            # Failed V3 restoration must not silently activate historical V2.
            return "V3"
        review = self.native_review.snapshot()
        run_identity = review.native_run_identity
        if self.visual_v3_live.is_current_run(run_identity):
            return "V3"
        historical = review.review_pack_record
        if (
            historical is not None
            and historical.native_run_identity == run_identity
            and not review.review_pack_superseded
        ):
            return "V2"
        return "V3"

    def admit_sponsor_work(self) -> bool:
        """Atomically reject new state-changing work after exit begins."""

        ticket = self.maintenance_admission.admit("BROWSER_POST")
        if ticket is None:
            return False
        with self._shutdown_lock:
            if self._shutdown_started:
                accepted = False
            else:
                self._active_sponsor_work += 1
                self._sponsor_tickets.current = ticket
                accepted = True
        if not accepted:
            ticket.release()
        return accepted

    def finish_sponsor_work(self) -> None:
        with self._shutdown_lock:
            self._active_sponsor_work -= 1
        ticket = getattr(self._sponsor_tickets, "current", None)
        self._sponsor_tickets.current = None
        if ticket is None:
            raise ValueError("MAINTENANCE_BROWSER_OWNER_MISSING")
        ticket.release()

    @staticmethod
    def _work_owner_idle(status: dict[str, object] | None) -> bool:
        if status is None:
            return False
        return (
            status.get("state") in {"IDLE", "SAME_PROCESS"}
            and not status.get("generation")
            and int(status.get("owned_workers", status.get("owned_work_count", 0))) == 0
            and int(status.get("queued_items", status.get("queued_jobs", 0))) == 0
        )

    @staticmethod
    def _analysis_execution_drained(status: dict[str, object] | None) -> bool:
        """A failed result is history; only proved resource completion is idle."""
        if status is None:
            return False
        if status.get("state") != "FAILED":
            return (KronosBrowserServer._work_owner_idle(status)
                    and status.get("cleanup_state", "COMPLETE") == "COMPLETE")
        return (
            status.get("cleanup_state") == "COMPLETE"
            and "pid" in status and status["pid"] is None
            and "generation" in status and status["generation"] is None
            and type(status.get("owned_workers")) is int
            and status["owned_workers"] == 0
            and type(status.get("queued_jobs")) is int
            and status["queued_jobs"] == 0
        )

    def maintenance_replacement_idle(self, *, allow_drainable: bool = False) -> bool:
        """Recheck every shared work owner immediately before a handoff."""

        try:
            snapshot = self.application.snapshot()
            counted = (self.maintenance_admission.snapshot()["owners"]
                       if allow_drainable else {})
            def owned(kind: str) -> bool:
                return allow_drainable and int(counted.get(kind, 0)) > 0

            analysis_owned = owned("SWING_ANALYSIS")
            connection_owned = (owned("PROVIDER_CONNECTION")
                or owned("SPONSOR_RESTORATION") or owned("PROVIDER_CALLBACK"))
            if (
                (self._active_sponsor_work and not allow_drainable)
                or (allow_drainable and self._active_sponsor_work
                    and counted.get("BROWSER_POST", 0) < self._active_sponsor_work)
                or (snapshot.provider_state.value == "CONNECTING"
                    and not connection_owned)
                or (snapshot.analysis_state.value == "RUNNING"
                    and not analysis_owned)
                or (self.application.live_monitoring_result().state.value == "TESTING"
                    and not owned("MONITORING_CALLBACK"))
                or any(
                    outcome.state.value == "ANALYZING" and not analysis_owned
                    for outcome in self.native_review.snapshot().analysis_outcomes
                )
            ):
                return False
            for status, drained in (
                (self.application.analysis_work_status(), self._work_owner_idle),
                (self.application.analysis_execution_status(),
                 KronosBrowserServer._analysis_execution_drained),
            ):
                if not drained(status):
                    if (not analysis_owned or status is None
                            or status.get("state") not in {
                                "ADMITTING", "RUNNING", "PUBLISHING", "RECONCILING",
                                "CANCELLATION_REQUESTED", "STARTING", "PREPARED",
                                "COMMITTING", "COMPLETED",
                            }
                            or not int(status.get("owned_workers",
                                                  status.get("owned_work_count", 0)))):
                        return False
            connection = self.application.connection_attempt_status()
            if connection is not None and (
                connection.get("worker_active")
                or connection.get("resources_pending")
                or connection.get("restoration_worker_active")
                or connection.get("cleanup_state") != "COMPLETE"
            ) and not connection_owned:
                return False
            restoration = self.application.sponsor_operability_restoration_status()
            if (restoration.get("state") in {"PENDING", "RUNNING"}
                    and not owned("SPONSOR_RESTORATION")):
                return False
            monitoring = self.swing_monitoring_hub.status_document()
            mcx_control = getattr(self, "mcx_v1_control", None)
            mcx_worker = (None if mcx_control is None else
                          mcx_control.worker_status())
            if (mcx_worker is not None and int(mcx_worker["pending"])
                    and (not allow_drainable
                         or counted.get("MONITORING_CALLBACK", 0)
                            < int(mcx_worker["pending"]))):
                return False
            if not allow_drainable and any(
                int(monitoring.get(field, 0))
                for field in (
                    "session_count", "active_session_count", "owner_count",
                    "subscription_count",
                )
            ):
                return False
            lifecycle = getattr(self, "intraday_lifecycle", None)
            if lifecycle is not None:
                status = lifecycle.work_status()
                if not self._work_owner_idle(status) and (
                    not allow_drainable or status.get("continuity") == "INCOMPLETE"
                    or status.get("state") == "FAILED"
                    or counted.get("WO11", 0) == 0
                ):
                    return False
            wo17 = getattr(self, "intraday_wo17_monitoring", None)
            if wo17 is not None:
                status = wo17.work_status()
                if not self._work_owner_idle(status) and (
                    not allow_drainable or status.get("continuity") == "INCOMPLETE"
                    or status.get("state") == "FAILED"
                    or counted.get("WO17", 0) == 0
                ):
                    return False
            housekeeping = getattr(self, "housekeeping", None)
            if housekeeping is not None:
                house = housekeeping.status_document()
                busy = (
                    house.get("lifecycle_state") != "IDLE"
                    or house.get("shutdown_requested")
                    or house.get("pass_active")
                    or int(house.get("owned_workers", 0))
                )
                if busy and (not allow_drainable
                             or counted.get("HOUSEKEEPING", 0) == 0):
                    return False
            bulk_import = getattr(self, "bulk_import", None)
            if bulk_import is not None and bulk_import.work_status().get("batch_active"):
                if not allow_drainable or counted.get("BULK_IMPORT", 0) == 0:
                    return False
        except (AttributeError, KeyError, TypeError, ValueError):
            return False
        return True

    def _maintenance_final_owner_proof(self) -> bool:
        """Fail closed on missing or incomplete final cleanup facts."""
        try:
            if self.maintenance_admission.snapshot()["owners"]:
                return False
            if self._active_sponsor_work or not self._domain_closed:
                return False
            lifecycle = self.intraday_lifecycle.work_status()
            wo17 = self.intraday_wo17_monitoring.work_status()
            if any(int(status[field]) for status in (lifecycle, wo17)
                   for field in ("owned_workers", "queued_items")):
                return False
            if any(status["state"] == "FAILED" for status in (lifecycle, wo17)):
                return False
            if any(status["continuity"] == "INCOMPLETE" for status in
                   (lifecycle, wo17)):
                return False
            house = self.housekeeping.status_document()
            if (house["lifecycle_state"] != "STOPPED"
                or int(house["owned_workers"]) or house["pass_active"]):
                return False
            bulk = self.bulk_import.work_status() if self.bulk_import is not None else None
            if (bulk is not None and (bulk["state"] != "STOPPED"
                                      or bulk["batch_active"]
                                      or self.bulk_import.store.list_incomplete())):
                return False
            notifications = self.intraday_notifications.maintenance_status()
            if not notifications["closed"] or notifications["scheduled"]:
                return False
            ux10 = self.ux10_notifications.maintenance_status()
            if not ux10["closed"] or int(ux10["retry_callbacks"]):
                return False
            monitoring = self.swing_monitoring_hub.status_document()
            if (any(int(monitoring[field]) for field in
                    ("session_count", "owner_count", "subscription_count"))
                or monitoring["transport_cleanup"]["state"] != "COMPLETE"):
                return False
            mcx_control = getattr(self, "mcx_v1_control", None)
            if (mcx_control is not None
                    and int(mcx_control.worker_status()["pending"])):
                return False
            provider = self.provider_runtime.read_only_status()
            if (provider["cleanup_state"] != "COMPLETE"
                or int(provider["owned_work_count"])
                or int(provider["retained_lease_count"])
                or int(provider["unresolved_cleanup_count"])):
                return False
            connection = self.application.connection_attempt_status()
            if connection is not None and any(connection.get(field) for field in
                                              ("worker_active", "resources_pending",
                                               "restoration_worker_active")):
                return False
            restoration = self.application.sponsor_operability_restoration_status()
            if restoration.get("state") in {"PENDING", "RUNNING"}:
                return False
            self._maintenance_notification_checkpoint = (
                self.intraday_notifications.checkpoint(certify_durable=True)
            )
            if not self._work_owner_idle(self.application.analysis_work_status()):
                return False
            if not KronosBrowserServer._analysis_execution_drained(
                    self.application.analysis_execution_status()):
                return False
        except (AttributeError, KeyError, TypeError, ValueError, OSError):
            return False
        return True

    def _maintenance_drain_attestation(self) -> dict[str, object]:
        """Capture only bounded zero-owner facts for the signed handoff."""
        if (not self._work_owner_idle(self.application.analysis_work_status())
                or not KronosBrowserServer._analysis_execution_drained(
                    self.application.analysis_execution_status())):
            raise ValueError("MAINTENANCE_DRAIN_ATTESTATION_NOT_ZERO")
        lifecycle = self.intraday_lifecycle.work_status()
        wo17 = self.intraday_wo17_monitoring.work_status()
        house = self.housekeeping.status_document()
        bulk = self.bulk_import.work_status() if self.bulk_import is not None else None
        notifications = self.intraday_notifications.maintenance_status()
        monitoring = self.swing_monitoring_hub.status_document()
        provider = self.provider_runtime.read_only_status()
        mcx_control = getattr(self, "mcx_v1_control", None)
        mcx_worker = (None if mcx_control is None else
                      mcx_control.worker_status())
        # MCX is a local zero-work precondition, not a V2 wire-schema extension.
        if mcx_worker is not None and int(mcx_worker["pending"]) != 0:
            raise ValueError("MAINTENANCE_DRAIN_ATTESTATION_NOT_ZERO")
        counts = {
            "coordinator_owners": sum(self.maintenance_admission.snapshot()["owners"].values()),
            "wo11_owned": int(lifecycle["owned_workers"]),
            "wo11_queued": int(lifecycle["queued_items"]),
            "wo17_owned": int(wo17["owned_workers"]),
            "wo17_queued": int(wo17["queued_items"]),
            "housekeeping_owned": int(house["owned_workers"]),
            "bulk_owned": int(bulk["batch_active"]) if bulk is not None else 0,
            "notification_scheduled": int(notifications["scheduled"]),
            "monitoring_sessions": int(monitoring["session_count"]),
            "provider_owned": int(provider["owned_work_count"]),
            "provider_leases": int(provider["retained_lease_count"]),
        }
        if any(value != 0 for value in counts.values()):
            raise ValueError("MAINTENANCE_DRAIN_ATTESTATION_NOT_ZERO")
        checkpoint = self.intraday_notifications.checkpoint()
        if checkpoint != getattr(self, "_maintenance_notification_checkpoint", None):
            raise ValueError("MAINTENANCE_NOTIFICATION_CHECKPOINT_CHANGED")
        counts["notification_checkpoint"] = checkpoint
        return counts

    def _complete_governed_shutdown(self, generation: str,
                                    runtime_identity: str,
                                    drain_seconds: float = 10.0) -> None:
        """Drain without holding the coordinator or Browser shutdown lock."""
        admission = self.maintenance_admission
        deadline = monotonic() + drain_seconds
        try:
            state = admission.snapshot()["state"]
            if state == "FENCED":
                admission.draining(generation)
            elif state != "DRAINING":
                raise ValueError("MAINTENANCE_STATE_CONFLICT")
            if not admission.wait_for_zero(generation, max(0.0, deadline - monotonic())):
                return
            if not self.maintenance_replacement_idle(allow_drainable=True):
                admission.fail(generation, "OWNER_PROOF_UNAVAILABLE")
                return
            finalizer = admission.finalizer(generation)
            try:
                with finalizer.activate():
                    self._quiesce_monitoring_producers()
            finally:
                finalizer.release()
            if not admission.wait_for_zero(generation, max(0.0, deadline - monotonic())):
                return
            finalizer = admission.finalizer(generation)
            try:
                with finalizer.activate():
                    self._close_domain_owners(
                        bulk_timeout_seconds=max(0.0, deadline - monotonic()),
                        require_proof=True,
                    )
            finally:
                finalizer.release()
            if not admission.wait_for_zero(generation, max(0.0, deadline - monotonic())):
                return
            if monotonic() >= deadline or not self._maintenance_final_owner_proof():
                admission.fail(generation, "CLEANUP_UNRESOLVED")
                return
            control = self.restart_control
            if control is None or not control.owns_current_process():
                admission.fail(generation, "OWNER_PROOF_UNAVAILABLE")
                return
            governance = self.connection_governance
            loaded_revision = None if governance is None else governance.process.loaded_revision
            if (not callable(getattr(control, "maintenance_drain_handoff", None))
                    or type(loaded_revision) is not str
                    or re.fullmatch(r"[a-f0-9]{40}", loaded_revision) is None):
                admission.fail(generation, "HANDOFF_FAILED")
                return
            drain = self._maintenance_drain_attestation()
            admission.ready(generation)
            try:
                control.maintenance_drain_handoff(
                    generation, runtime_identity, loaded_revision, drain
                )
            except (OSError, RuntimeError, TypeError, ValueError):
                admission.fail(generation, "HANDOFF_FAILED")
                return
            admission.stopping(generation)
        except (OSError, RuntimeError, TypeError, ValueError):
            if admission.snapshot()["state"] != "FAILED_FENCED":
                admission.fail(generation, "CLEANUP_UNRESOLVED")
            return
        self.shutdown()

    def begin_sponsor_shutdown(self) -> str:
        """Claim one bounded shutdown after proving this process owns the runtime."""

        with self._shutdown_lock:
            if self._shutdown_started:
                return "ALREADY_SHUTTING_DOWN"
            if (
                self.restart_control is None
                or not self.restart_control.owns_current_process()
            ):
                return "RUNTIME_OWNERSHIP_UNVERIFIED"
            if self._active_sponsor_work:
                return "SPONSOR_WORK_IN_PROGRESS"
            snapshot = self.application.snapshot()
            if (
                snapshot.analysis_state.value == "RUNNING"
                or snapshot.provider_state.value == "CONNECTING"
                or self.application.live_monitoring_result().state.value == "TESTING"
                or any(
                    outcome.state.value == "ANALYZING"
                    for outcome in self.native_review.snapshot().analysis_outcomes
                )
            ):
                return "SPONSOR_WORK_IN_PROGRESS"
            bulk_import = getattr(self, "bulk_import", None)
            if (bulk_import is not None
                    and bulk_import.work_status().get("batch_active")):
                return "SPONSOR_WORK_IN_PROGRESS"
            if self.connection_governance is not None:
                try:
                    self.application.enter_controlled_maintenance(sha256(uuid4().bytes).hexdigest())
                except (OSError, ValueError):
                    return "MAINTENANCE_GOVERNANCE_UNAVAILABLE"
            self._shutdown_started = True
            return "SHUTDOWN_ACCEPTED"


class _BrowserHandler(BaseHTTPRequestHandler):
    server: KronosBrowserServer

    def setup(self) -> None:
        super().setup()
        # Delegate the original stream operations and HTTP parser unchanged;
        # measure buffered/socket header reads without retaining their bytes.
        original = self.rfile
        class TimedReader:
            def readline(wrapper, *args, **kwargs):
                with diagnostic_stage("REQUEST_HEADERS", "WAIT"):
                    try:
                        value = original.readline(*args, **kwargs)
                    except BaseException as error:
                        trace = current_trace()
                        if trace is not None:
                            trace.failure(error)
                        raise
                    if not value and current_trace() is not None:
                        current_trace().emit("EOF")
                    return value

            def __getattr__(wrapper, name):
                return getattr(original, name)
        self.rfile = TimedReader()

    def parse_request(self) -> bool:
        result = super().parse_request()
        trace = current_trace()
        if trace is not None:
            safe_call(trace.parsed, getattr(self, "command", "UNKNOWN"), getattr(self, "path", ""))
        return result

    def send_response(self, code, message=None) -> None:
        trace = current_trace()
        if trace is not None:
            trace.response(code)
        super().send_response(code, message)
        if trace is not None:
            self.send_header("X-Kronos-Request-ID", trace.identity)

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path == "/swing/research":
            self._swing_research_page()
            return
        if path == "/swing/mcx-contract-offer":
            self._mcx_contract_offer()
            return
        if path == "/swing/mcx-v1":
            self._mcx_v1_workspace()
            return
        if path == "/swing/mcx-v1/observation":
            self._mcx_observation_receipt()
            return
        if path == "/runtime/request-diagnostics":
            # Keep the bounded operational ring out of the launcher's 64 KiB
            # status contract, and do not acquire any application owner lock.
            self._json(safe_call(self.server.request_diagnostics.snapshot) or {
                "schema": "KRONOS_REQUEST_DIAGNOSTICS_V1", "state": "UNAVAILABLE",
            })
            return
        if path == "/assets/brand/kronos-brand-mark.png":
            self._png_asset(_BRAND_MARK_ASSET)
            return
        if path == "/assets/brand/kronos-sidebar-mark.png":
            self._png_asset(_SIDEBAR_MARK_ASSET)
            return
        if path == "/favicon.png":
            self._png_asset(_FAVICON_ASSET)
            return
        if path == "/":
            self._redirect("/swing/opportunities")
            return
        if path == "/swing":
            self._redirect("/swing/opportunities")
            return
        if path == "/control/provider-instrument-master/status":
            self._provider_instrument_master_status()
            return
        if path == "/control/intraday-discovery/status":
            self._intraday_discovery_status()
            return
        if path == "/control/intraday-historical-qualification/status":
            self._intraday_historical_status()
            return
        if path == "/swing/v1/bulk-import-status":
            owner = self.server.bulk_import
            query = parse_qs(urlsplit(self.path).query, strict_parsing=True)
            if (owner is None or set(query) != {"batch"}
                    or len(query["batch"]) != 1):
                self._text(HTTPStatus.NOT_FOUND, "Bulk import status not found.")
                return
            try:
                status = owner.presentation(query["batch"][0])
            except (OSError, ValueError):
                status = None
            if status is None:
                self._text(HTTPStatus.NOT_FOUND, "Bulk import status not found.")
            else:
                self._json(status)
            return
        product_response = self.server.product_routes.dispatch_get(
            BrowserGetRequest(
                path=path,
                query=parse_qs(urlsplit(self.path).query),
            ),
            self.server.application.snapshot,
        )
        if product_response is not None:
            self._respond(
                product_response.status,
                (
                    product_response.body.encode("utf-8")
                    if type(product_response.body) is str
                    else product_response.body
                ),
                product_response.content_type,
                filename=product_response.filename,
            )
            return
        if path == "/dashboard":
            try:
                snapshot, discovery = self.server.application.opportunities_projection()
                notifications = project_swing_notification_workspace(
                    self.server.progression_snapshot())
                promotions_v2 = self.server.current_v2_promotions(discovery)
                promotions = (() if self.server.native_intake is not None else tuple(
                    item.promotion for item in self.server.visual_v3.completed_snapshot()
                    if item.promotion is not None))
                body = render_dashboard(snapshot, project_sponsor_dashboard(
                    snapshot, discovery, promotions, notifications,
                    self.server.ux10_notifications.snapshot(),
                    promotions_v2=promotions_v2))
                _, latest = self.server.application.opportunities_projection()
                if (latest is not discovery or
                        promotions_v2 != self.server.current_v2_promotions(discovery)):
                    raise ValueError("V2_PROMOTION_PRESENTATION_STALE")
                self._html(body)
            except (OSError, ValueError) as error:
                self._swing_page_unavailable(error)
            return
        if path == "/notifications/status":
            product = parse_qs(urlsplit(self.path).query).get("product", ["SWING"])[0]
            centre = (self.server.notification_centre.snapshot(product="INTRADAY") if product == "INTRADAY"
                      else self.server.swing_notification_status())
            indicators = {} if product == "INTRADAY" else self.server.swing_notification_indicators(centre)
            self._json({
                "revision": centre.revision if product == "INTRADAY" else notification_revision(centre, indicators),
                "count": len(centre.visible),
                "live": centre.live_count,
                "expired": centre.expired_count,
                "websocket": centre.websocket_state,
            })
            return
        if path == "/swing/opportunities":
            intake = self.server.native_intake
            try:
                response = intake.page_response() if intake is not None else nullcontext()
                with diagnostic_context(response, "INTAKE_ENTER", "INTAKE_EXIT") as prepared:
                    with diagnostic_stage("PUBLICATION"):
                        snapshot, discovery, continuity, publication = (
                            self.server.application.opportunities_bundle_projection())
                        publication = deepcopy(publication)
                    def current():
                        with diagnostic_stage("CURRENTNESS"):
                            _, native, bound_continuity, status = self.server.application.opportunities_bundle_projection()
                            return native is discovery and bound_continuity is continuity and status == publication
                    visual_v3, trade_windows = self.server.selected_opportunity_presentations(
                        discovery, prepared=prepared, authority_is_current=current)
                    with diagnostic_stage("V2_SELECTION"):
                        promotions_v2 = self.server.current_v2_promotions(
                            discovery, prepared=prepared)
                    with diagnostic_stage("RENDER_INPUTS"):
                        inputs = (
                            snapshot, discovery, self.server.native_review.snapshot(),
                            self.server.progression_snapshot(), visual_v3, trade_windows,
                            self.server.refresh_reminders.snapshot(), self.server.swing_projection_revision(),
                            continuity, publication,
                            None if intake is None else intake.snapshot(_response=prepared))
                    with diagnostic_stage("RENDER"):
                        body = render_opportunities(*inputs, promotions_v2=promotions_v2)
                    with diagnostic_stage("CURRENTNESS"):
                        if (not current() or promotions_v2 !=
                                self.server.current_v2_promotions(discovery, prepared=prepared)):
                            raise ValueError("REVIEW_BINDING_STALE")
                with diagnostic_stage("RESPONSE_WRITE"):
                    self._html(body)
            except (OSError, ValueError) as error:
                self._swing_page_unavailable(error)
            return
        notification_evidence = re.fullmatch(r"/notifications/swing/evidence/(UX08_WATCH|UX10_EVENT)/([0-9a-f]{64})", path)
        if notification_evidence:
            document = self.server.swing_notification_evidence(*notification_evidence.groups())
            self._html(render_swing_notification_evidence(self.server.application.snapshot(), document))
            return
        if path in {"/notifications", "/notifications/swing", "/notifications/intraday"}:
            selected = {
                "/notifications": NotificationProduct.SWING,
                "/notifications/swing": NotificationProduct.SWING,
                "/notifications/intraday": NotificationProduct.INTRADAY,
            }[path]
            query_values = parse_qs(
                urlsplit(self.path).query, keep_blank_values=True
            )
            allowed = {"state", "search", "page", "notice"}
            try:
                if set(query_values).difference(allowed) or any(
                    len(value) != 1 for value in query_values.values()
                ):
                    raise ValueError
                notification_query = SponsorNotificationQuery(
                    state=SponsorNotificationFilter(
                        query_values.get("state", ["ALL"])[0]
                    ),
                    search=query_values.get("search", [""])[0],
                    page=int(query_values.get("page", ["1"])[0]),
                )
                notice = query_values.get("notice", [""])[0]
                if len(notice) > 96:
                    raise ValueError
            except (TypeError, ValueError):
                self._text(HTTPStatus.BAD_REQUEST, "Notification filter is invalid.")
                return
            centre = (self.server.notification_centre.snapshot(product="INTRADAY")
                      if selected is NotificationProduct.INTRADAY else self.server.sponsor_notification_snapshot())
            # Product selection cannot display or dismiss another product's cards.
            centre = type(centre)(tuple(r for r in centre.records if r.product == selected.value), centre.websocket_state)
            operational = project_sponsor_notifications(centre, notification_query)
            service = getattr(self.server, "intraday_notifications", None)
            indicators = {r.notification_identity: service.indicator(json.loads(r.intraday_details))
                          if service is not None and r.intraday_details else "UNAVAILABLE"
                          for r in centre.records} if selected is NotificationProduct.INTRADAY else self.server.swing_notification_indicators(centre)
            self._html(render_notifications(
                self.server.application.snapshot(),
                project_swing_notification_workspace(self.server.progression_snapshot()),
                selected_product=selected,
                ux10=self.server.ux10_notifications.snapshot(),
                operational=operational,
                notice=notice,
                intraday_indicators=indicators,
                swing_revision=(None if selected is NotificationProduct.INTRADAY
                    else notification_revision(centre, indicators)),
            ))
            return
        details_match = _ANALYSIS_DETAILS_ROUTE.fullmatch(path)
        if details_match:
            run_identity = details_match.group(1)
            instrument = unquote(details_match.group(2))
            intake = self.server.native_intake
            try:
                with intake.page_response() if intake is not None else nullcontext() as prepared:
                    snapshot, discovery, continuity, publication = (
                        self.server.application.opportunities_bundle_projection())
                    publication = deepcopy(publication)
                    if discovery is None or discovery.run_identity != run_identity:
                        details = None
                    else:
                        assessments = tuple(item for item in discovery.assessments
                            if item.canonical_instrument == instrument
                            and item.status.value == "PROBABLE")
                        if len(assessments) > 1:
                            raise ValueError("REVIEW_BINDING_STALE")
                        if not assessments:
                            details = None
                        elif intake is None:
                            details = project_native_analysis_details(
                                discovery, self.server.native_review.snapshot(),
                                run_identity, instrument)
                            if details is None:
                                raise ValueError("REVIEW_BINDING_STALE")
                        else:
                            # The retained successor generation owns this run's
                            # requirements. The historical mutable Review is not
                            # prepared by an observational GET.
                            authority = prepared.authority
                            context = prepared.context
                            if (authority is None or authority.native is not discovery
                                    or context is None or context[2].native_run_identity != run_identity):
                                raise ValueError("REVIEW_BINDING_STALE")
                            requirements = tuple(item for item in context[2].requirements
                                if item.native_run_identity == run_identity
                                and item.canonical_instrument == instrument)
                            if (len(requirements) != 1 or requirements[0].thesis.native_assessment_sha256
                                    != assessments[0].result_sha256):
                                raise ValueError("REVIEW_BINDING_STALE")
                            details = NativeAnalysisDetailsProjection(
                                assessments[0], requirements[0], (), None, None, (), None)
                    if details is None:
                        body = None
                    else:
                        def current():
                            _, native, bound_continuity, status = (
                                self.server.application.opportunities_bundle_projection())
                            return (native is discovery and bound_continuity is continuity
                                    and status == publication)

                        if intake is not None and not current():
                            raise ValueError("REVIEW_BINDING_STALE")
                        continuity_row = None
                        if continuity is not None:
                            contribution = continuity.contribution
                            contribution.validate()
                            if contribution.native_run != discovery:
                                raise ValueError("REVIEW_BINDING_STALE")
                            matches = tuple(item for item in contribution.rows
                                if item.canonical_instrument == instrument)
                            if len(matches) > 1:
                                raise ValueError("REVIEW_BINDING_STALE")
                            continuity_row = matches[0] if matches else None
                        promotions_v2 = self.server.current_v2_promotions(discovery)
                        selected_v2 = next((item for item in promotions_v2
                            if item.value["source"]["canonical_instrument"] == instrument
                            and item.value["source"]["native_assessment_sha256"]
                            == details.assessment.result_sha256), None)
                        if intake is None:
                            presentations = self.server.visual_v3_presentations()
                            windows = ()
                        else:
                            presentations, windows = self.server.selected_opportunity_presentations(
                                discovery, prepared=prepared, authority_is_current=current)
                        v3 = next((value for value in presentations
                            if value.run_identity == run_identity
                            and value.canonical_instrument == instrument
                            and value.native_assessment_sha256 == details.assessment.result_sha256), None)
                        if (selected_v2 is not None and selected_v2.value["source"]["market"] == "NSE"
                                and v3 is None):
                            raise ValueError("V2_PROMOTION_PRESENTATION_BINDING_INVALID")
                        relative_run = self.server.relative_context_for_run(run_identity)
                        if intake is None:
                            window = (None if v3 is not None and v3.kr370 is not None
                                and v3.kr370_v2 is None else
                                self.server.trade_window.project(run_identity, instrument))
                        else:
                            window = next((item for item in windows
                                if item.native_run_identity == run_identity
                                and item.canonical_instrument == instrument
                                and item.native_assessment_sha256 == details.assessment.result_sha256), None)
                        body = render_native_analysis_details(
                            snapshot, details, self.server.progression_snapshot(), v3,
                            window, self.server.mcx_supporting_context.context_for(
                                instrument, assessment_boundary=discovery.observed_at),
                            None if relative_run is None else relative_run.record(instrument),
                            promotion_v2=selected_v2, continuity=continuity_row)
                        if not current():
                            raise ValueError("REVIEW_BINDING_STALE")
                        if promotions_v2 != self.server.current_v2_promotions(discovery):
                            raise ValueError("V2_PROMOTION_PRESENTATION_BINDING_INVALID")
                if body is None:
                    self._text(HTTPStatus.NOT_FOUND, "Analysis Details not found.")
                else:
                    self._html(body)
            except (AttributeError, KeyError, OSError, TypeError, ValueError) as error:
                self._swing_page_unavailable(error)
            return
        trade_window_match = _TRADE_WINDOW_ROUTE.fullmatch(path)
        if trade_window_match:
            projection = self.server.trade_window.project(
                trade_window_match.group(1), unquote(trade_window_match.group(2))
            )
            if projection is None:
                self._text(HTTPStatus.NOT_FOUND, "Trade Window not found.")
                return
            self._html(render_native_trade_window(
                self.server.application.snapshot(), projection
            ))
            return
        snapshot = self.server.application.snapshot()
        if path == "/swing/layer1-history":
            self._html(render_legacy_opportunities(snapshot))
            return
        if path == "/swing/v1-review":
            intake = self.server.native_intake
            notice_query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
            notice = (self.server.answer_notice(notice_query["answer_notice"][0])
                      if set(notice_query).issubset({"answer_notice", "bulk_import"})
                      and "answer_notice" in notice_query
                      and len(notice_query["answer_notice"]) == 1 else None)
            bulk_identity = (notice_query["bulk_import"][0]
                if set(notice_query).issubset({"answer_notice", "bulk_import"})
                and "bulk_import" in notice_query
                and len(notice_query["bulk_import"]) == 1 else None)
            try:
                bulk_status = (None if self.server.bulk_import is None else
                    self.server.bulk_import.presentation(bulk_identity))
            except (OSError, ValueError):
                bulk_status = None
            try:
                with intake.page_response() if intake is not None else nullcontext() as prepared:
                    review = self.server.native_review.snapshot()
                    _, discovery = self.server.application.opportunities_projection()
                    promotions_v2 = self.server.current_v2_promotions(discovery)
                    body = render_v1_review(
                        snapshot, self.server.v1_review.snapshot(), review,
                        (self.server.visual_v3_live.snapshot(review.native_run_identity)
                         if intake is None and self.server.native_review_version() == "V3" else None),
                        self.server.mcx_supporting_context.snapshot(),
                        self.server.relative_context_for_run(review.native_run_identity)
                        if intake is None and review.native_run_identity is not None else None,
                        None if intake is None else intake.snapshot(_response=prepared),
                        answer_notice=notice, bulk_import=bulk_status,
                        promotions_v2=promotions_v2)
                    _, latest = self.server.application.opportunities_projection()
                    if (latest is not discovery or promotions_v2 !=
                            self.server.current_v2_promotions(discovery)):
                        raise ValueError("V2_PROMOTION_PRESENTATION_STALE")
                self._html(body)
            except (OSError, ValueError) as error:
                self._swing_page_unavailable(error)
            return
        if path == "/swing/mtf-diagnostics":
            self._html(render_mtf_fact_diagnostics(
                snapshot,
                self.server.application.mtf_fact_snapshot(),
            ))
            return
        if path == "/swing/native-discovery":
            self._html(render_native_discovery(
                snapshot,
                self.server.application.native_discovery_run(),
            ))
            return
        if path == "/swing/trade-candidates":
            self._html(render_trade_candidates(
                snapshot,
                self.server.step32_workflow.snapshot(),
            ))
            return
        if path == "/swing/active":
            review = self.server.native_review.snapshot()
            self._html(render_active_candidates(
                snapshot,
                self.server.step32_workflow.snapshot(),
                review.active_lifecycle,
                active_monitoring_position_ids=(
                    self.server.native_review.active_lifecycle_monitoring_ids
                ),
            ))
            return
        if path == "/swing/closed":
            self._html(render_closed_candidates(
                snapshot,
                self.server.step32_workflow.snapshot(),
                self.server.native_review.snapshot().active_lifecycle,
            ))
            return
        if path == "/portfolio":
            from kronos.browser.views import render_portfolio
            query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
            if set(query) - {"product", "search", "direction", "monitoring"} or any(len(v) != 1 for v in query.values()):
                self._text(HTTPStatus.BAD_REQUEST, "Portfolio filter is invalid.")
                return
            product = query.get("product", ["SWING"])[0]
            search = query.get("search", [""])[0]
            direction = query.get("direction", [""])[0]
            monitoring = query.get("monitoring", [""])[0]
            if (product not in {"SWING", "INTRADAY"} or len(search) > 80 or direction not in {"", "LONG", "SHORT"}
                    or monitoring not in {"", "LIVE", "INTERRUPTED", "IDLE", "UNAVAILABLE"}):
                self._text(HTTPStatus.BAD_REQUEST, "Portfolio filter is invalid.")
                return
            books = getattr(self.server, "intraday_books", None)
            try:
                rows = () if product == "SWING" or books is None else books.portfolio(
                    search=search, direction=direction, monitoring=monitoring)
            except (ValueError, KeyError, TypeError, OSError):
                self._text(HTTPStatus.SERVICE_UNAVAILABLE, "Intraday exposure source unavailable.")
                return
            self._html(render_portfolio(snapshot, rows, product=product, search=search,
                                        direction=direction, monitoring=monitoring))
            return
        if path in {
            "/reports",
            "/reports/export.xlsx",
            "/reports/export.csv",
            "/reports/export.json",
        }:
            query_values = parse_qs(
                urlsplit(self.path).query, keep_blank_values=True
            )
            allowed = {
                "product", "view", "from", "to", "quick", "search",
                "direction", "status", "page", "record", "exit_reason", "completeness",
            }
            if set(query_values).difference(allowed) or any(
                len(value) != 1 for value in query_values.values()
            ):
                self._text(HTTPStatus.BAD_REQUEST, "Reports filter is invalid.")
                return
            try:
                product = ReportProduct(query_values.get("product", ["SWING"])[0])
                view = ReportView(query_values.get("view", ["OVERVIEW"])[0])
                governed_date = (self.server.application.current_swing_trading_date()
                                 if product is ReportProduct.SWING else None)
                quick = query_values.get("quick", [""])[0]
                from_value = query_values.get("from", [""])[0]
                to_value = query_values.get("to", [""])[0]
                from_date = date.fromisoformat(from_value) if from_value else None
                to_date = date.fromisoformat(to_value) if to_value else None
                if quick:
                    if governed_date is None:
                        raise ValueError("REPORT_GOVERNED_CURRENT_DATE_UNAVAILABLE")
                    if quick == "TODAY":
                        from_date = to_date = governed_date
                    elif quick == "7D":
                        from_date, to_date = governed_date - timedelta(days=6), governed_date
                    elif quick == "30D":
                        from_date, to_date = governed_date - timedelta(days=29), governed_date
                    elif quick == "THIS_MONTH":
                        from_date = governed_date.replace(day=1)
                        to_date = governed_date
                    else:
                        raise ValueError
                direction_value = query_values.get("direction", [""])[0]
                reports_query = ReportsQuery(
                    product=product,
                    view=view,
                    from_date=from_date,
                    to_date=to_date,
                    instrument=query_values.get("search", [""])[0],
                    direction=(
                        None if not direction_value else V1Direction(direction_value)
                    ),
                    status=query_values.get("status", [""])[0],
                    page=int(query_values.get("page", ["1"])[0]),
                    exit_reason=query_values.get("exit_reason", [""])[0],
                    completeness=query_values.get("completeness", [""])[0],
                )
                selected_record = query_values.get("record", [None])[0]
                if selected_record is not None and len(selected_record) > 160:
                    raise ValueError
            except (TypeError, ValueError):
                self._text(HTTPStatus.BAD_REQUEST, "Reports filter is invalid.")
                return
            if reports_query.product is ReportProduct.INTRADAY:
                from kronos.browser.reports import project_intraday_reports
                books = getattr(self.server, "intraday_books", None)
                try:
                    rows = () if books is None else books.snapshot()
                    projection = project_intraday_reports(rows, reports_query)
                except (ValueError, OSError, KeyError, TypeError):
                    self._text(HTTPStatus.SERVICE_UNAVAILABLE, "Intraday factual source unavailable.")
                    return
            else:
                # Reconciliation belongs to the admitted server pulse. A readable
                # cache cannot override either owner's retained failure state.
                if self.server._swing_step33_reconciliation_failure is not None:
                    self._text(HTTPStatus.SERVICE_UNAVAILABLE,
                               "Swing Step-33 reconciliation unavailable; Reports history currentness is unknown.")
                    return
                if self.server._swing_v2_reconciliation_failure is not None:
                    self._text(HTTPStatus.SERVICE_UNAVAILABLE,
                               "Swing V2 reconciliation unavailable; Reports history currentness is unknown.")
                    return
                try:
                    preliminary = self.server.trade_window.observation_operational_handoffs_v2(
                        governed_current_trading_date=governed_date,
                    )
                    operational = with_completion_trading_dates(
                        preliminary, governed_date,
                        self.server.application.swing_trading_date_for,
                    )
                    journal = self.server.native_review.journal_current_snapshot()
                except (ValueError, OSError, KeyError, TypeError):
                    self._text(HTTPStatus.SERVICE_UNAVAILABLE,
                               "Swing Reports source evidence unavailable; records are not empty.")
                    return
                # An admitted reconciliation may have failed while these reads
                # were in progress. Do not publish the previously readable cache.
                if self.server._swing_step33_reconciliation_failure is not None:
                    self._text(HTTPStatus.SERVICE_UNAVAILABLE,
                               "Swing Step-33 reconciliation unavailable; Reports history currentness is unknown.")
                    return
                if self.server._swing_v2_reconciliation_failure is not None:
                    self._text(HTTPStatus.SERVICE_UNAVAILABLE,
                               "Swing V2 reconciliation unavailable; Reports history currentness is unknown.")
                    return
                projection = project_historical_reports(
                    operational,
                    journal,
                    reports_query,
                    governed_current_trading_date=governed_date,
                )
            if path == "/reports/export.xlsx":
                generated_at = datetime.now(UTC)
                self._respond(
                    HTTPStatus.OK,
                    export_reports_xlsx(projection, generated_at=generated_at),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    filename=reports_excel_filename(projection, generated_at),
                )
                return
            if path == "/reports/export.csv":
                self._respond(
                    HTTPStatus.OK, export_reports_csv(projection),
                    "text/csv; charset=utf-8",
                )
                return
            if path == "/reports/export.json":
                self._respond(
                    HTTPStatus.OK, export_reports_json(projection),
                    "application/json; charset=utf-8",
                )
                return
            self._html(render_reports(
                snapshot, projection, selected_record_id=selected_record
            ))
            return
        if path == "/journal":
            query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
            product = query.get("product", ["SWING"])
            search = query.get("search", [""])
            view = query.get("view", ["operational"])
            selected = query.get("filter", ["ALL"])
            selected_record = query.get("record", [None])
            observation_choice = query.get("observation_choice", ["ALL"])
            observation_activation = query.get("observation_activation", ["ALL"])
            observation_severity = query.get("observation_severity", ["ALL"])
            truth = query.get("truth", ["ALL"])
            status = query.get("status", ["ALL"])
            monitoring = query.get("monitoring", ["ALL"])
            scope = query.get("scope", ["ALL"])
            if (
                set(query).difference({
                    "product", "search", "view",
                    "filter", "record", "observation_choice",
                    "observation_activation", "observation_severity",
                    "truth", "status", "monitoring", "scope",
                })
                or len(product) != 1
                or len(search) != 1
                or len(view) != 1
                or product[0] not in {"SWING", "INTRADAY"}
                or view[0] not in {"operational", "research"}
                or len(search[0]) > 80
                or len(selected) != 1
                or len(selected_record) != 1
                or len(observation_choice) != 1
                or len(observation_activation) != 1
                or len(observation_severity) != 1
                or len(truth) != 1
                or len(status) != 1
                or len(monitoring) != 1
                or len(scope) != 1
            ):
                self._text(HTTPStatus.BAD_REQUEST, "Journal filter is invalid.")
                return
            if product[0] == "INTRADAY":
                allowed_truth = {"ALL", "PAPER_POSITION", "PAPER_OBSERVATION", "NONE", "DO_NOTHING"}
                allowed_monitoring = {"ALL", "LIVE", "INTERRUPTED", "IDLE", "NOT_REQUIRED", "UNAVAILABLE"}
                if (view[0] != "operational" or truth[0] not in allowed_truth
                        or monitoring[0] not in allowed_monitoring
                        or scope[0] not in {"ALL", "CURRENT", "HISTORY"}
                        or len(status[0]) > 80):
                    self._text(HTTPStatus.BAD_REQUEST, "Journal filter is invalid.")
                    return
                journal = getattr(self.server, "intraday_journal", None)
                if journal is None:
                    self._text(HTTPStatus.SERVICE_UNAVAILABLE, "Intraday Journal is unavailable.")
                    return
                projection = journal.snapshot(search=search[0], truth=truth[0], status=status[0],
                                              monitoring=monitoring[0], scope=scope[0])
                self._html(render_trade_journal(
                    snapshot, None, operational=(),
                    selected_product="INTRADAY", search=search[0], selected_record_id=selected_record[0],
                    intraday=projection, intraday_filters={"truth": truth[0], "status": status[0],
                                                          "monitoring": monitoring[0], "scope": scope[0]},
                ))
                return
            try:
                observation_query = ObservationResearchQueryV1(
                    choices=(
                        () if observation_choice[0] == "ALL"
                        else (SponsorTradeChoice(observation_choice[0]),)
                    ),
                    dispositions=(
                        () if observation_activation[0] == "ALL"
                        else tuple(
                            item for item in SponsorActivationDisposition
                            if (
                                observation_activation[0] == "ACTIVATED"
                                and item is SponsorActivationDisposition.ACTIVATED
                            ) or (
                                observation_activation[0] == "BLOCKED"
                                and item.value.startswith("BLOCKED_")
                            )
                        )
                    ),
                    severities=(
                        () if observation_severity[0] == "ALL"
                        else (Step31WarningSeverity(observation_severity[0]),)
                    ),
                )
                if observation_activation[0] not in {"ALL", "ACTIVATED", "BLOCKED"}:
                    raise ValueError
            except ValueError:
                self._text(HTTPStatus.BAD_REQUEST, "Journal filter is invalid.")
                return
            if view[0] == "operational":
                source_status = (
                    self.server._swing_step33_reconciliation_failure
                    or self.server._swing_v2_reconciliation_failure
                    or "AVAILABLE"
                )
                try:
                    governed_date = self.server.application.current_swing_trading_date()
                except ValueError:
                    governed_date = None
                    operational = ()
                    source_status = "DATE_UNAVAILABLE"
                else:
                    facts: dict[str, CurrentMarketFactV2] = {}
                    for tick in self.server.swing_monitoring_hub.latest_market_ticks:
                        for identity in {
                            tick.instrument.name,
                            tick.instrument.trading_symbol,
                        }:
                            if identity:
                                facts[identity] = CurrentMarketFactV2(
                                    identity,
                                    tick.last_price,
                                    tick.observed_at,
                                    tick.source,
                                    True,
                                )
                    try:
                        preliminary = self.server.trade_window.observation_operational_handoffs_v2(
                            current_facts=facts,
                            governed_current_trading_date=governed_date,
                        )
                        current_records = with_completion_trading_dates(
                            preliminary, governed_date,
                            self.server.application.swing_trading_date_for,
                        )
                        operational = tuple(
                            replace(item, monitoring_state=owner[0],
                                    monitoring_session_identity=owner[1],
                                    monitoring_observation_identity=owner[2])
                            for item in current_records
                            for owner in [(
                                self.server.trade_window.paper_observation_journal_monitoring_evidence(
                                    item.paper_track_identity)
                                if item.paper_track_identity is not None else
                                self.server.native_review.journal_position_monitoring_evidence(
                                    item.sponsor_position_identity)
                                if item.sponsor_position_identity is not None else
                                ("UNKNOWN", None, None)
                            )]
                        )
                        mcx = getattr(self.server, 'mcx_v1_control', None)
                        if mcx is not None:
                            from kronos.application.swing_mcx_journal import mcx_journal_handoffs
                            mcx_rows = mcx_journal_handoffs(mcx, governed_date)
                            existing_positions = {item.sponsor_position_identity for item in operational}
                            if any(item.sponsor_position_identity in existing_positions for item in mcx_rows):
                                raise ValueError('MCX_JOURNAL_DUPLICATE_POSITION')
                            operational += mcx_rows
                    except (ValueError, OSError, KeyError, TypeError):
                        operational = ()
                        source_status = "SOURCE_UNAVAILABLE"
                try:
                    journal = self.server.native_review.journal_current_snapshot()
                except (ValueError, OSError, KeyError, TypeError):
                    source_status = "SOURCE_UNAVAILABLE"
                    journal = None
                if journal is not None:
                    by_position = {
                        (record.native_run_identity, record.sponsor_position_id,
                         record.trade_plan_id):
                        record.journal_record_id
                        for record in journal.records
                        if record.sponsor_position_id is not None
                    }
                    operational = tuple(replace(
                        item, step33_record_identity=by_position.get((
                            item.native_run_identity, item.sponsor_position_identity,
                            item.trade_plan_identity,
                        )),
                    ) for item in operational)
                self._html(render_trade_journal(
                    snapshot,
                    journal,
                    operational=operational,
                    operational_source_status=source_status,
                    operational_websocket_state=websocket_presentation_state(
                        monitoring_required=(
                            self.server.swing_monitoring_hub.subscription_count > 0
                        ),
                        connection_state=(
                            self.server.swing_monitoring_hub.connection_state
                        ),
                    ),
                    governed_trading_date=governed_date,
                    selected_product=product[0],
                    search=search[0],
                    selected_record_id=selected_record[0],
                ))
                return
            if self.server._swing_step33_reconciliation_failure is not None:
                self._text(HTTPStatus.SERVICE_UNAVAILABLE,
                           "Swing Step-33 reconciliation unavailable; retained history currentness is unknown.")
                return
            try:
                journal = self.server.native_review.journal_current_snapshot()
                observations = self.server.trade_window.observation_research_snapshot(
                    observation_query
                )
            except (ValueError, OSError, KeyError, TypeError):
                self._text(HTTPStatus.SERVICE_UNAVAILABLE,
                           "Swing Journal source evidence unavailable; records are not empty.")
                return
            self._html(render_trade_journal(
                snapshot,
                journal,
                selected_filter=selected[0],
                selected_record_id=selected_record[0],
                observations=observations,
                observation_choice=observation_choice[0],
                observation_activation=observation_activation[0],
                observation_severity=observation_severity[0],
            ))
            return
        candidate_match = _TRADE_CANDIDATE_ROUTE.fullmatch(path)
        if candidate_match:
            record = self.server.step32_workflow.snapshot().record_for_browser_key(
                candidate_match.group(1)
            )
            if record is None:
                self._text(HTTPStatus.NOT_FOUND, "Trade Candidate not found.")
                return
            self._html(render_candidate_workspace(snapshot, record))
            return
        if path == "/swing/v1/chart-preview":
            self._v1_chart_preview()
            return
        if path == "/swing/v1/native-chart-preview":
            self._native_chart_preview()
            return
        if path == "/swing/v1/native-request-pdf":
            self._native_intake_pdf()
            return
        if path == "/swing/mcx-context/image-preview":
            self._mcx_context_image_preview()
            return
        if path == "/swing/v1/status":
            self._json(analysis_status_payload(self.server.v1_review.snapshot()))
            return
        if path == "/settings":
            self._html(
                render_settings(
                    snapshot,
                    self.server.chart_analyst_credentials.status(),
                    self.server.chart_analyst_activation.status(),
                    self.server.application.live_monitoring_result(),
                    self.server.application.live_monitoring_instruments(),
                    self.server.application.market_calendar_health(),
                    self.server.telegram.status(),
                    self.server.telegram.private_chat_candidates(),
                    self.server.active_live_monitoring_count(),
                )
            )
            return
        match = _WORKSPACE_ROUTE.fullmatch(path)
        if match:
            self._text(
                HTTPStatus.NOT_FOUND,
                "V0 workspaces are reference-only and are not in the active workflow.",
            )
            return
        eligible_match = _ELIGIBLE_WORKSPACE_ROUTE.fullmatch(path)
        if eligible_match:
            self._text(
                HTTPStatus.NOT_FOUND,
                "V0 workspaces are reference-only and are not in the active workflow.",
            )
            return
        if path == "/runtime/status":
            from kronos.browser.runtime_state import status_document
            payload = status_document(self.server)
            # This observational marker distinguishes a fenced-drain-capable
            # predecessor from older binaries before the launcher can stop it.
            payload["maintenance_drain"] = self.server.maintenance_admission.snapshot()
            payload["maintenance_claim"] = (
                "DRAINABLE" if self.server.maintenance_replacement_idle(
                    allow_drainable=True) else "BLOCKED"
            )
            payload["paper_observation_compact"] = self.server.trade_window.paper_observation_compact_status()
            lifecycle = getattr(self.server, "intraday_lifecycle", None)
            if lifecycle is not None:
                payload["intraday_wo11_work"] = lifecycle.work_status()
            wo17 = getattr(self.server, "intraday_wo17_monitoring", None)
            if wo17 is not None:
                payload["intraday_wo17_work"] = wo17.work_status()
            housekeeping = getattr(self.server, "housekeeping", None)
            if housekeeping is not None:
                payload["housekeeping"] = housekeeping.status_document()
            bulk_import = getattr(self.server, "bulk_import", None)
            if bulk_import is not None:
                payload["swing_bulk_import"] = bulk_import.work_status()
            payload["analysis_work"] = dict(
                self.server.application.analysis_work_status()
            )
            payload["analysis_execution"] = dict(
                self.server.application.analysis_execution_status()
            )
            self._json(payload)
            return
        if path == "/status":
            diagnostic = self.server.application.analysis_diagnostic()
            live_monitoring = self.server.application.live_monitoring_result()
            payload: dict[str, object] = {
                "service": "KRONOS_BROWSER_V1",
                "provider": snapshot.provider_state.value,
                "analysis": snapshot.analysis_state.value,
                "completed_at": (
                    snapshot.completed_at.isoformat() if snapshot.completed_at else None
                ),
                "swing_projection_revision": (
                    self.server.swing_projection_revision()
                ),
                "v1_probables": len(snapshot.v1_probables),
                "analysis_diagnostic": None,
                "live_monitoring": live_monitoring.state.value,
            }
            maintenance_drain = self.server.maintenance_admission.snapshot()
            if maintenance_drain["state"] != "OPEN":
                payload["maintenance_drain"] = maintenance_drain
            payload["paper_observation_compact"] = self.server.trade_window.paper_observation_compact_status()
            lifecycle = getattr(self.server, "intraday_lifecycle", None)
            if lifecycle is not None:
                payload["intraday_wo11_work"] = lifecycle.work_status()
            wo17 = getattr(self.server, "intraday_wo17_monitoring", None)
            if wo17 is not None:
                payload["intraday_wo17_work"] = wo17.work_status()
            housekeeping = getattr(self.server, "housekeeping", None)
            if housekeeping is not None:
                payload["housekeeping"] = housekeeping.status_document()
            bulk_import = getattr(self.server, "bulk_import", None)
            if bulk_import is not None:
                payload["swing_bulk_import"] = bulk_import.work_status()
            publication = self.server.application.publication_status()
            if publication["control"] is not None:
                payload["swing_publication"] = publication
            if self.server.connection_governance is not None:
                payload["maintenance"] = self.server.connection_governance.maintenance_status()
                payload["runtime_ready"] = (self.server.connection_governance.startup_state == "READY"
                    and not self.server.connection_governance.maintenance_active
                    and not self.server.connection_governance.shutting_down)
            if diagnostic is not None:
                payload["analysis_diagnostic"] = {
                    "attempt_id": diagnostic.attempt_id,
                    "timestamp": diagnostic.timestamp.isoformat(),
                    "failing_stage": diagnostic.failing_stage.value,
                    "exception_class": diagnostic.exception_class,
                    "sanitized_summary": diagnostic.sanitized_summary,
                    "canonical_instrument": diagnostic.canonical_instrument,
                    "completed_instrument_count": diagnostic.completed_instrument_count,
                    "observation_boundary": (
                        diagnostic.observation_boundary.isoformat()
                        if diagnostic.observation_boundary else None
                    ),
                    "provider_capability_active": diagnostic.provider_capability_active,
                }
            self._json(payload)
            return
        placeholder = _PLACEHOLDERS.get(path)
        if placeholder:
            title, nav, tab = placeholder
            self._html(render_placeholder(snapshot, title, active_nav=nav, active_tab=tab))
            return
        self._text(HTTPStatus.NOT_FOUND, "Not found.")

    def do_POST(self) -> None:  # noqa: N802
        self._connection_received_at = datetime.now().astimezone().isoformat()
        path = urlsplit(self.path).path
        if path == "/control/shutdown":
            self._graceful_backend_shutdown()
            return
        if not self._same_origin():
            if path == "/provider/connect" and not self._audit_rejected_connection():
                return
            self._text(HTTPStatus.FORBIDDEN, "Request rejected.")
            return
        if path == "/control/exit":
            self._sponsor_exit()
            return
        if not self.server.admit_sponsor_work():
            if path == "/provider/connect" and not self._audit_rejected_connection():
                return
            self._text(HTTPStatus.SERVICE_UNAVAILABLE, "KRONOS is shutting down.")
            return
        try:
            with self.server._sponsor_tickets.current.activate():
                self._swing_post_failed = False
                self._dispatch_post(path)
                if (path.startswith("/swing/") and path not in {
                        "/swing/analysis", "/swing/reconcile",
                        "/swing/research/update",
                        "/swing/v1/native-chart", "/swing/v1/native-chart/remove",
                        "/swing/mcx-contract-choice", "/swing/mcx-reserved-analysis",
                        "/swing/mcx-v1/reserve", "/swing/mcx-v1/plan", "/swing/mcx-v1/observe",
                        "/swing/mcx-v1/paper", "/swing/mcx-v1/live",
                        "/swing/mcx-v1/paper-exit", "/swing/mcx-v1/live-exit"}
                        and not self._swing_post_failed):
                    # Read requests never enter this explicit mutation boundary.
                    self.server.application.reconcile_committed_analysis()
        finally:
            self.server.finish_sponsor_work()

    def _swing_research_page(self) -> None:
        """Presentation reads retained status only; no capture or Provider call."""
        try:
            status = self.server.swing_research_control.status()
        except (OSError, ValueError):
            self._text(HTTPStatus.SERVICE_UNAVAILABLE, "Swing research evidence unavailable.")
            return
        query = parse_qs(urlsplit(self.path).query)
        outcome = query.get("outcome", [""])[0]
        remaining = query.get("remaining", [""])[0]
        permitted = {"PUBLISHED", "ALREADY_UP_TO_DATE", "ALREADY_APPLIED",
                     "CATCHUP_INCOMPLETE", "CALENDAR_UNAVAILABLE",
                     "ACQUISITION_UNAVAILABLE"}
        notice = ("<p>Latest update: " + escape(outcome) +
                  (" · Remaining candle requests: " + escape(remaining)
                   if remaining.isdecimal() else "") + "</p>"
                  if outcome in permitted else "")
        months = ", ".join(escape(month) for month in status["verified_months"]) or "None"
        pending = (status["admission_capture"] or status["v2_capture"]
                   or status.get("decision_capture") or status.get("observation_capture")
                   or status.get("mcx_capture") or "None")
        operation = uuid4().hex
        commissioned = status.get("commissioned_at")
        running = status.get("operation") or {}
        operation_notice = ("<p>Update " + escape(str(running.get("operation_identity", "")))
                            + ": " + escape(str(running.get("state", "")))
                            + " · " + escape(str(running.get("phase", "")))
                            + (" · Result: " + escape(str(running["outcome"]))
                               if running.get("outcome") else "") + "</p>"
                            if running else "")
        body = ("<section class=\"panel\"><h2>Prospective Swing research</h2>"
                "<p>Research only. The update acquires missing, exact-contract historical "
                "candles through the current read-only Provider capability and publishes "
                "verified monthly workbooks. It does not admit or manage trades.</p>"
                + notice
                + operation_notice
                + "<p>Admitted origins: " + str(status["origins"])
                + " · V2 milestones: " + str(status["milestones"])
                + " · Verified months: " + months + "</p>"
                + "<p>Capture replay needed: " + escape(pending) + "</p>"
                + ("<p>Release commissioning required before updates.</p>"
                   if commissioned is None else "")
                + '<form method="post" action="/swing/research/update">'
                + '<input type="hidden" name="operation_identity" value="' + operation + '">'
                + '<button type="submit"' + (" disabled" if commissioned is None else "")
                + '>UPDATE SWING RESEARCH</button></form></section>')
        self._html(render_browser_page(
            title="Swing Research", subtitle="Explicit prospective direction research",
            snapshot=self.server.application.snapshot(), active_nav="Swing",
            active_tab="Opportunities", body=body,
            back_link='<a href="/swing/opportunities">← Opportunities</a>'))

    def _swing_research_update(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", ""))
            if (not 0 < length <= 256 or self.headers.get("Content-Type", "").split(";", 1)[0]
                    != "application/x-www-form-urlencoded"):
                raise ValueError("SWING_RESEARCH_REQUEST_INVALID")
            fields = parse_qs(self.rfile.read(length).decode("ascii"), strict_parsing=True)
            if (set(fields) != {"operation_identity"}
                    or len(fields["operation_identity"]) != 1
                    or re.fullmatch(r"[0-9a-f]{32}", fields["operation_identity"][0]) is None):
                raise ValueError("SWING_RESEARCH_REQUEST_INVALID")
            admitted = self.server.swing_research_control.submit_update(
                fields["operation_identity"][0],
                self.server._sponsor_tickets.current)
        except (OSError, ValueError, TypeError):
            self._swing_post_failed = True
            self._text(HTTPStatus.SERVICE_UNAVAILABLE,
                       "Swing research source or acquisition unavailable; verified workbooks retained.")
            return
        self._redirect("/swing/research?" + urlencode({
            "operation": admitted["operation_identity"]}))

    def _swing_research_authority(self, path: str) -> None:
        """Explicit same-origin, authenticated, counted release/data-owner operations."""
        control = self.server.restart_control
        if (control is None or not control.owns_current_process()
                or self.headers.get("Host") != f"{_LOOPBACK_HOST}:{self.server.server_port}"
                or not control.authorized(
                    process_id=self.headers.get("X-Kronos-Backend-Pid"),
                    token=self.headers.get("X-Kronos-Restart-Token"))):
            self._text(HTTPStatus.FORBIDDEN, "Request rejected.")
            return
        self._swing_post_failed = True  # Never trigger analysis reconciliation.
        try:
            import base64
            def unique(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError("SWING_RESEARCH_REQUEST_INVALID")
                    result[key] = value
                return result
            length = int(self.headers.get("Content-Length", ""))
            if (not 0 < length <= 1500000 or urlsplit(self.path).query
                    or self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json"):
                raise ValueError("SWING_RESEARCH_REQUEST_INVALID")
            fields = json.loads(self.rfile.read(length), object_pairs_hook=unique)
            owner = self.server.swing_research_control
            if path == "/control/swing-research/commission":
                if set(fields) != {"release_identity", "source_manifest_sha256", "manifest_base64"}:
                    raise ValueError("SWING_RESEARCH_REQUEST_INVALID")
                receipt = owner.commission(
                    release_identity=fields["release_identity"],
                    source_manifest_sha256=fields["source_manifest_sha256"],
                    manifest_bytes=base64.b64decode(fields["manifest_base64"], validate=True))
                result = {"receipt_identity": receipt.identity, "commissioned_at": receipt.data["commissioned_at"]}
            else:
                if set(fields) != {"attestation", "csv_base64"}:
                    raise ValueError("SWING_RESEARCH_REQUEST_INVALID")
                identity = owner.import_actions(fields["attestation"],
                    base64.b64decode(fields["csv_base64"], validate=True))
                result = {"report_identity": identity}
        except (OSError, ValueError, TypeError, KeyError):
            self._text(HTTPStatus.CONFLICT, "Swing research authority rejected; evidence retained.")
            return
        self._json(result)

    def _dispatch_post(self, path: str) -> None:
        if path in {"/control/swing-research/commission", "/control/swing-research/corporate-actions/import"}:
            self._swing_research_authority(path)
            return
        if path == "/swing/research/update":
            self._swing_research_update()
            return
        if path == "/swing/mcx-v1/observe":
            self._mcx_observe()
            return
        if path in {"/swing/mcx-v1/reserve", "/swing/mcx-v1/plan"}:
            self._mcx_v1_composition_action(path)
            return
        if path in {"/swing/mcx-v1/paper", "/swing/mcx-v1/live",
                    "/swing/mcx-v1/paper-exit", "/swing/mcx-v1/live-exit"}:
            self._mcx_v1_record_action(path)
            return
        if path == "/swing/mcx-contract-choice":
            self._mcx_contract_choice()
            return
        if path == "/swing/mcx-reserved-analysis":
            self._mcx_reserved_analysis()
            return
        governance = self.server.connection_governance
        if path == "/control/maintenance/exit":
            reference = self._connection_action_reference()
            if governance is None or not governance.exit_maintenance(reference):
                self._text(HTTPStatus.CONFLICT, "Maintenance transition rejected.")
            else:
                self._redirect("/swing/opportunities")
            return
        if path == "/control/intraday-live-shadow/successor-epoch/v1":
            self._commission_shadow_successor()
            return
        if path == "/control/intraday-live-shadow/compatibility-restoration/v1":
            self._restore_shadow_compatibility()
            return
        if governance and governance.maintenance_active and path != "/provider/connect":
            self._text(HTTPStatus.SERVICE_UNAVAILABLE, "Controlled maintenance is active.")
            return
        if path == "/journal/intraday/delete":
            journal = getattr(self.server, "intraday_journal", None)
            if journal is None:
                self._text(HTTPStatus.SERVICE_UNAVAILABLE, "Intraday Journal is unavailable.")
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 2048:
                    raise ValueError
                fields = parse_qs(self.rfile.read(size).decode("ascii"), strict_parsing=True)
                if set(fields) != {"journal_identity", "revision_identity", "action_identity"} or any(len(v) != 1 for v in fields.values()):
                    raise ValueError
                journal.suppress(journal_identity=fields["journal_identity"][0],
                                 revision_identity=fields["revision_identity"][0],
                                 action_identity=fields["action_identity"][0])
            except (UnicodeError, ValueError, OSError):
                self._text(HTTPStatus.CONFLICT, "Journal presentation suppression rejected.")
                return
            self._redirect("/journal?product=INTRADAY")
            return
        if self.server.product_routes.owns_post(path):
            self._dispatch_product_post(path)
            return
        if path == "/control/intraday-discovery":
            self._run_intraday_discovery()
            return

        if path == "/control/intraday-historical-qualification":
            self._run_intraday_historical_qualification()
            return
        if path == "/control/provider-instrument-master":
            self._run_provider_instrument_master()
            return
        if path == "/provider/connect":
            try:
                if governance is None:
                    admitted = self.server.application.connect_provider()
                else:
                    admitted = self.server.application.connect_provider(action_reference=self._connection_action_reference(),
                        request_route="/provider/connect", received_at=self._connection_received_at)
            except (OSError, ValueError):
                self._text(HTTPStatus.SERVICE_UNAVAILABLE, "Provider connection not admitted.")
                return
            navigation = getattr(self.server, "provider_login_navigation", None)
            if admitted and navigation is not None:
                status = self.server.application.connection_attempt_status()
                generation = None if status is None else status.get("generation")
                remaining = (
                    None if status is None else status.get("remaining_seconds")
                )
                try:
                    location = navigation.take_redirect(
                        generation, timeout_seconds=remaining
                    )
                except (RuntimeError, TypeError, ValueError):
                    location = None
                if location is None:
                    self._text(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "Provider login navigation unavailable.",
                    )
                    return
                try:
                    self._redirect(location)
                finally:
                    location = ""
                return
            self._redirect("/swing/opportunities")
            return
        if path == "/provider/disconnect":
            self._disconnect_provider()
            return
        if path == "/swing/analysis":
            self.server.application.run_analysis()
            self._redirect("/swing/opportunities")
            return
        if path == "/swing/reconcile":
            self.server.application.reconcile_committed_analysis()
            self._redirect("/swing/opportunities")
            return
        if path == "/swing/progression-watch/activate":
            self._activate_progression_watch()
            return
        if path == "/swing/trade-window/construct":
            self._construct_native_trade_plan()
            return
        if path == "/swing/trade-window/observation-decision":
            self._record_sponsor_observation_decision()
            return
        if path == "/swing/trade-window/activate":
            self._activate_sponsor_observation_entry()
            return
        if path == "/swing/trade-window/paper-observation/start":
            self._start_paper_observation_track()
            return
        if path == "/notifications/watch/deactivate":
            self._manage_progression_watch("deactivate")
            return
        if path == "/notifications/watch/reactivate":
            self._manage_progression_watch("reactivate")
            return
        if path == "/notifications/watch/delete":
            self._manage_progression_watch("delete")
            return
        if path == "/notifications/dismiss":
            self._manage_notification_lifecycle("dismiss")
            return
        if path == "/notifications/delete-expired":
            self._manage_notification_lifecycle("delete-expired")
            return
        if path == "/notifications/reactivate":
            self._manage_notification_lifecycle("reactivate")
            return
        if path == "/notifications/refresh":
            self._refresh_from_notification()
            return
        if path == "/swing/v1/layer1":
            evidence = self.server.application.completed_analysis_evidence()
            if evidence is None:
                self._text(HTTPStatus.CONFLICT, "Completed daily evidence is required.")
                return
            try:
                self.server.v1_review.prepare_layer1_run(
                    evidence.v1_layer1_run,
                    swing_analysis_run_identity=(
                        evidence.swing_analysis_run_identity
                    ),
                )
            except ValueError:
                self._text(
                    HTTPStatus.CONFLICT,
                    "The existing review is frozen. Load the latest review explicitly.",
                )
                return
            self._redirect("/swing/v1-review")
            return
        if path == "/swing/v1/native-review":
            native_run = self.server.native_review_run
            facts = self.server.native_review_facts
            if native_run is None or facts is None:
                self._text(
                    HTTPStatus.CONFLICT,
                    "Complete same-run Native evidence is required.",
                )
                return
            try:
                self.server.native_review.prepare(native_run, facts)
            except ValueError:
                self._text(
                    HTTPStatus.CONFLICT,
                    "Native Review preparation was rejected.",
                )
                return
            self._redirect("/swing/v1-review")
            return
        if path == "/swing/v1/native-review-refresh":
            self._refresh_native_review()
            return
        if path == "/swing/v1/load-latest":
            evidence = self.server.application.completed_analysis_evidence()
            if evidence is None:
                self._text(HTTPStatus.CONFLICT, "Completed daily evidence is required.")
                return
            self.server.v1_review.load_latest_layer1(
                evidence.v1_layer1_run,
                swing_analysis_run_identity=evidence.swing_analysis_run_identity,
            )
            self._redirect("/swing/v1-review")
            return
        if path == "/swing/v1/chart":
            self._receive_v1_chart()
            return
        if path == "/swing/v1/chart/remove":
            self._remove_v1_chart()
            return
        if path == "/swing/v1/analyze":
            self._analyze_v1_charts()
            return
        if path == "/swing/v1/analyze-one":
            self._analyze_one_v1_chart()
            return
        if path == "/swing/v1/native-chart":
            self._receive_native_chart()
            return
        if path == "/swing/v1/native-chart/remove":
            self._remove_native_chart()
            return
        if path == "/swing/v1/native-analyze":
            self._analyze_native_review()
            return
        if path == "/swing/v1/native-analyze-all":
            self._analyze_all_native_reviews()
            return
        if path == "/swing/v1/native-review-pack":
            self._generate_native_review_pack()
            return
        if path == "/swing/v1/native-review-answer":
            self._upload_native_review_answer()
            return
        if path == "/swing/v1/native-review-answer/validate":
            self._validate_selected_native_review_answer()
            return
        if path == "/swing/v1/native-review-handoff":
            self._native_intake_mutation("HANDOFF")
            return
        if path == "/swing/mcx-context/image":
            self._receive_mcx_context_image()
            return
        if path == "/swing/mcx-context/image/remove":
            self._remove_mcx_context_image()
            return
        if path == "/swing/mcx-context/question-pack":
            self._create_mcx_context_question_pack()
            return
        if path == "/swing/mcx-context/answer":
            self._upload_mcx_context_answer()
            return
        if path == "/swing/v1/native-trade-decision":
            self._record_native_sponsor_decision()
            return
        if path == "/swing/v1/native-lifecycle/paper-exit":
            self._exit_native_paper_position()
            return
        if path == "/swing/v1/native-lifecycle/live-exit":
            self._record_native_live_exit()
            return
        if path == "/settings/chart-analyst/credential":
            self._receive_chart_analyst_credential()
            return
        if path == "/settings/telegram/token":
            self._receive_telegram_token()
            return
        if path == "/settings/telegram/private-chat/discover":
            self._discover_telegram_private_chat()
            return
        if path == "/settings/telegram/private-chat/confirm":
            self._confirm_telegram_private_chat()
            return
        if path == "/settings/telegram/test":
            self._test_telegram()
            return
        if path == "/settings/telegram/connect":
            self._connect_telegram()
            return
        if path == "/settings/telegram/disconnect":
            self._disconnect_telegram()
            return
        if path == "/settings/telegram/remove":
            self._remove_telegram_configuration()
            return
        if path == "/settings/kite/live-monitoring/test":
            self._test_live_monitoring()
            return
        if path == "/settings/chart-analyst/test":
            self.server.chart_analyst_credentials.test_connection()
            self._redirect("/settings")
            return
        if path == "/settings/chart-analyst/enable":
            self._set_chart_analyst_activation(True)
            return
        if path == "/settings/chart-analyst/disable":
            self._set_chart_analyst_activation(False)
            return
        decision_match = _TRADE_CANDIDATE_DECISION_ROUTE.fullmatch(path)
        if decision_match:
            self._record_sponsor_decision(decision_match.group(1))
            return
        self._text(HTTPStatus.NOT_FOUND, "Not found.")

    def _commission_shadow_successor(self) -> None:
        # Separate maintenance-only contract. Never opens normal product dispatch.
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if (urlsplit(self.path).query or self.headers.get('Content-Type', '').split(';')[0] != 'application/json'
                    or not 0 < length <= 4096):
                raise ValueError('SHADOW_EPOCH_REQUEST_INVALID')
            payload = json.loads(self.rfile.read(length))
            with self.server._shutdown_lock:
                snapshot = self.server.application.snapshot()
                idle = (not self.server._shutdown_started and self.server._active_sponsor_work == 1
                    and snapshot.analysis_state.value != 'RUNNING' and snapshot.provider_state.value != 'CONNECTING'
                    and self.server.application.live_monitoring_result().state.value != 'TESTING'
                    and not any(x.state.value == 'ANALYZING' for x in self.server.native_review.snapshot().analysis_outcomes))
                governance = self.server.connection_governance
                result = self.server.product_routes.commission_shadow_successor(payload,
                    maintenance=bool(governance and governance.maintenance_active), idle=idle)
            self._respond(HTTPStatus.OK, json.dumps(result).encode(), 'application/json')
        except Exception:
            self._respond(HTTPStatus.CONFLICT, b'{"outcome":"REJECTED","failure":"SHADOW_SUCCESSOR_COMMISSIONING_REJECTED"}', 'application/json')

    def _restore_shadow_compatibility(self) -> None:
        # Separate maintenance-only contract. It cannot reach commissioning.
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if (urlsplit(self.path).query or self.headers.get("Content-Type", "").split(";")[0] != "application/json"
                    or not 0 < length <= 65536):
                raise ValueError("SHADOW_COMPATIBILITY_RESTORATION_REQUEST_INVALID")
            payload = json.loads(self.rfile.read(length))
            with self.server._shutdown_lock:
                snapshot = self.server.application.snapshot()
                idle = (not self.server._shutdown_started and self.server._active_sponsor_work == 1
                    and snapshot.analysis_state.value != "RUNNING" and snapshot.provider_state.value != "CONNECTING"
                    and self.server.application.live_monitoring_result().state.value != "TESTING"
                    and not any(x.state.value == "ANALYZING" for x in self.server.native_review.snapshot().analysis_outcomes))
                governance = self.server.connection_governance
                result = self.server.product_routes.restore_shadow_compatibility(payload,
                    maintenance=bool(governance and governance.maintenance_active), idle=idle)
            self._respond(HTTPStatus.OK, json.dumps(result).encode(), "application/json")
        except Exception:
            self._respond(HTTPStatus.CONFLICT,
                b'{"outcome":"REJECTED","failure":"SHADOW_COMPATIBILITY_RESTORATION_REJECTED"}',
                "application/json")

    def _dispatch_product_post(self, path: str) -> None:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            query = parse_qs(urlsplit(self.path).query, strict_parsing=True)
        except ValueError:
            self._text(HTTPStatus.BAD_REQUEST, "Product request rejected.")
            return
        if content_length < 0 or content_length > _MAX_PRODUCT_POST_BYTES:
            self._text(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Product request size is invalid.")
            return
        body = self.rfile.read(content_length)
        if len(body) != content_length:
            self._text(HTTPStatus.BAD_REQUEST, "Product request rejected.")
            return
        response = self.server.product_routes.dispatch_post(
            BrowserPostRequest(
                path=path,
                query=query,
                content_type=self.headers.get("Content-Type", "").split(";", 1)[0].lower(),
                body=body,
            ),
            self.server.application.snapshot,
        )
        if response is None:
            self._text(HTTPStatus.NOT_FOUND, "Not found.")
            return
        self._respond(
            response.status,
            response.body.encode("utf-8"),
            response.content_type,
        )

    def _provider_instrument_master_status(self) -> None:
        operation = self.server.provider_instrument_master_operation
        if operation is None:
            self._text(HTTPStatus.NOT_FOUND, "Not found.")
            return
        query = urlsplit(self.path).query
        if not query:
            self._json({
                "context_availability": operation.context_availability().value,
            })
            return
        try:
            fields = parse_qs(
                query,
                keep_blank_values=True,
                strict_parsing=True,
            )
            values = fields.get("operation_identity", ())
            if set(fields) != {"operation_identity"} or len(values) != 1:
                raise ValueError
            result = operation.result(values[0])
        except ValueError:
            self._text(HTTPStatus.BAD_REQUEST, "Request rejected.")
            return
        if result is None:
            self._text(HTTPStatus.NOT_FOUND, "Operation not found.")
            return
        self._json(p1_operational_result_document(result))

    def _intraday_discovery_status(self) -> None:
        control = self.server.intraday_discovery_control
        if control is None:
            self._text(HTTPStatus.NOT_FOUND, "Not found.")
            return
        if not self._exact_loopback_host():
            self._text(HTTPStatus.FORBIDDEN, "Request rejected.")
            return
        if urlsplit(self.path).query:
            self._text(HTTPStatus.BAD_REQUEST, "Request rejected.")
            return
        self._json(control.status_document())

    def _intraday_historical_status(self) -> None:
        control = self.server.intraday_historical_control
        if control is None:
            self._text(HTTPStatus.NOT_FOUND, "Not found.")
            return
        if not self._exact_loopback_host():
            self._text(HTTPStatus.FORBIDDEN, "Request rejected.")
            return
        if urlsplit(self.path).query:
            self._text(HTTPStatus.BAD_REQUEST, "Request rejected.")
            return
        self._json(control.status_document())

    def _run_intraday_discovery(self) -> None:
        control = self.server.intraday_discovery_control
        try:
            content_length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            content_length = 0
        if (
            control is None
            or urlsplit(self.path).query
            or self.headers.get("Content-Type", "").split(";", 1)[0].lower()
            != "application/json"
            or not 0 < content_length <= 512
        ):
            self._text(HTTPStatus.BAD_REQUEST, "Request rejected.")
            return
        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            result = control.execute_document(payload)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            self._text(HTTPStatus.BAD_REQUEST, "Request rejected.")
            return
        self._json(result)

    def _run_intraday_historical_qualification(self) -> None:
        control = self.server.intraday_historical_control
        try:
            content_length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            content_length = 0
        if (
            control is None
            or urlsplit(self.path).query
            or self.headers.get("Content-Type", "").split(";", 1)[0].lower()
            != "application/json"
            or not 0 < content_length <= 4096
        ):
            self._text(HTTPStatus.BAD_REQUEST, "Request rejected.")
            return
        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            result = control.execute_document(payload)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            self._text(HTTPStatus.BAD_REQUEST, "Request rejected.")
            return
        self._json(result)

    def _run_provider_instrument_master(self) -> None:
        operation = self.server.provider_instrument_master_operation
        try:
            content_length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            content_length = 0
        if (
            operation is None
            or urlsplit(self.path).query
            or self.headers.get("Content-Type", "").split(";", 1)[0].lower()
            != "application/x-www-form-urlencoded"
            or not 0 < content_length <= 192
        ):
            self._text(HTTPStatus.BAD_REQUEST, "Request rejected.")
            return
        try:
            fields = parse_qs(
                self.rfile.read(content_length).decode("utf-8"),
                strict_parsing=True,
            )
            values = fields.get("operation_identity", ())
            if set(fields) != {"operation_identity"} or len(values) != 1:
                raise ValueError
            result = operation.run(operation_identity=values[0])
        except (UnicodeDecodeError, ValueError):
            self._text(HTTPStatus.BAD_REQUEST, "Request rejected.")
            return
        self._json(p1_operational_result_document(result))

    def _activate_progression_watch(self) -> None:
        if urlsplit(self.path).query:
            self._text(HTTPStatus.BAD_REQUEST, "Watch activation rejected.")
            return
        try:
            content_length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            content_length = 0
        if (
            self.headers.get("Content-Type", "").split(";", 1)[0].lower()
            != "application/x-www-form-urlencoded"
            or not 0 < content_length <= 128
        ):
            self._text(HTTPStatus.BAD_REQUEST, "Watch activation rejected.")
            return
        try:
            fields = parse_qs(
                self.rfile.read(content_length).decode("utf-8"),
                strict_parsing=True,
            )
            values = fields.get("requirement_id", ())
            if (
                set(fields) != {"requirement_id"}
                or len(values) != 1
                or re.fullmatch(r"[0-9a-f]{64}", values[0]) is None
                or not self.server.application.activate_progression_watch(values[0])
            ):
                raise ValueError
            for watch in self.server.progression_watches.snapshot().watches:
                if (
                    watch.requirement.requirement_id == values[0]
                    and watch.state.value == "ACTIVE"
                ):
                    self.server.ux10_notifications.observe_progression_monitoring_activation(
                        watch
                    )
        except (UnicodeDecodeError, ValueError):
            self._text(HTTPStatus.CONFLICT, "Progression watch is not available.")
            return
        self._redirect("/swing/opportunities")

    def _manage_progression_watch(self, action: str) -> None:
        if urlsplit(self.path).query:
            self._text(HTTPStatus.BAD_REQUEST, "Notification action rejected.")
            return
        try:
            content_length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            content_length = 0
        if (
            self.headers.get("Content-Type", "").split(";", 1)[0].lower()
            != "application/x-www-form-urlencoded"
            or not 0 < content_length <= 128
        ):
            self._text(HTTPStatus.BAD_REQUEST, "Notification action rejected.")
            return
        try:
            fields = parse_qs(
                self.rfile.read(content_length).decode("utf-8"),
                strict_parsing=True,
            )
            values = fields.get("watch_id", ())
            operation = getattr(
                self.server.application,
                f"{action}_progression_watch",
            )
            if (
                set(fields) != {"watch_id"}
                or len(values) != 1
                or re.fullmatch(r"[0-9a-f]{64}", values[0]) is None
            ):
                raise ValueError
            with self.server._swing_notification_lock:
                if not operation(values[0]):
                    raise ValueError
                if action == "delete":
                    # Legacy watch management explicitly hides its source. Its
                    # corresponding presentation cards follow that action; the
                    # centre's own dismissal never invokes this owner workflow.
                    source_ids = {values[0]} | {event.notification_id
                        for event in self.server.ux10_notifications.snapshot().records
                        if event.watch_identity == values[0]
                        and event.family.value == "PROMOTION_WATCH"}
                    for item in self.server.notification_centre.snapshot(product="SWING").records:
                        if item.source_identity in source_ids and not item.dismissed:
                            self.server.notification_centre.dismiss(
                                item.notification_identity, item.integrity_sha256)
        except (AttributeError, UnicodeDecodeError, ValueError):
            self._text(HTTPStatus.CONFLICT, "Notification action is not available.")
            return
        self._redirect("/notifications")

    def _manage_notification_lifecycle(self, action: str) -> None:
        if urlsplit(self.path).query:
            self._notification_redirect("NOTIFICATION ACTION REJECTED")
            return
        try:
            content_length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            content_length = 0
        if (
            self.headers.get("Content-Type", "").split(";", 1)[0].lower()
            != "application/x-www-form-urlencoded"
            or not 0 < content_length <= 320
        ):
            self._notification_redirect("NOTIFICATION ACTION REJECTED")
            return
        try:
            fields = parse_qs(
                self.rfile.read(content_length).decode("utf-8"),
                strict_parsing=True,
            )
            if action == "delete-expired":
                if fields not in ({"product": ["SWING"], "confirm": ["DELETE"]}, {"product": ["INTRADAY"], "confirm": ["DELETE"]}):
                    raise ValueError("NOTIFICATION_DELETE_EXPIRED_CONFIRMATION_INVALID")
                count = self.server.notification_centre.dismiss_expired(product=fields["product"][0])
                self._notification_redirect(f"DELETED {count} EXPIRED NOTIFICATIONS", product=fields["product"][0])
                return
            if set(fields) != {"notification_id", "revision"}:
                raise ValueError("NOTIFICATION_ACTION_FIELDS_INVALID")
            identities = fields["notification_id"]
            revisions = fields["revision"]
            if (
                len(identities) != 1 or len(revisions) != 1
                or re.fullmatch(r"[0-9a-f]{64}", identities[0]) is None
                or re.fullmatch(r"[0-9a-f]{64}", revisions[0]) is None
            ):
                raise ValueError("NOTIFICATION_ACTION_BINDING_INVALID")
            record = self.server.notification_centre.record(identities[0])
            if record is None:
                raise ValueError("NOTIFICATION_NOT_FOUND")
            if action == "dismiss":
                self.server.notification_centre.dismiss(identities[0], revisions[0])
                self._notification_redirect("NOTIFICATION DELETED", product=record.product)
                return
            if action != "reactivate":
                raise ValueError("NOTIFICATION_ACTION_INVALID")
            _, run = self.server.application.opportunities_projection()
            source_valid = (
                record.notification_type == "REFRESH_ANALYSIS_REMINDER"
                and run is not None
                and run.run_identity == record.source_run_identity
            )
            self.server.notification_centre.reactivate(
                identities[0], revisions[0], source_valid=source_valid
            )
            self._notification_redirect("NOTIFICATION RE-ACTIVATED")
        except (AttributeError, UnicodeDecodeError, ValueError):
            self._notification_redirect("CANNOT RE-ACTIVATE OR DELETE · SOURCE STATE CHANGED")

    def _notification_redirect(self, notice: str, product: str = "SWING") -> None:
        self._redirect("/notifications/" + product.lower() + "?" + urlencode({"notice": notice}))

    def _refresh_from_notification(self) -> None:
        try:
            record = self._notification_bound_record()
            _, run = self.server.application.opportunities_projection()
            if (
                record.dismissed
                or record.state.value != "LIVE"
                or record.action.value != "REFRESH"
                or run is None
                or run.run_identity != record.source_run_identity
            ):
                raise ValueError("NOTIFICATION_REFRESH_STATE_INVALID")
            self.server.application.run_analysis()
        except (AttributeError, UnicodeDecodeError, ValueError):
            self._notification_redirect(
                "REFRESH NOT STARTED · NOTIFICATION STATE CHANGED"
            )
            return
        self._redirect("/swing/opportunities")

    def _notification_bound_record(self):  # type: ignore[no-untyped-def]
        if urlsplit(self.path).query:
            raise ValueError("NOTIFICATION_ACTION_QUERY_INVALID")
        try:
            content_length = int(self.headers.get("Content-Length", ""))
        except ValueError as error:
            raise ValueError("NOTIFICATION_ACTION_LENGTH_INVALID") from error
        if (
            self.headers.get("Content-Type", "").split(";", 1)[0].lower()
            != "application/x-www-form-urlencoded"
            or not 0 < content_length <= 320
        ):
            raise ValueError("NOTIFICATION_ACTION_REQUEST_INVALID")
        fields = parse_qs(
            self.rfile.read(content_length).decode("utf-8"), strict_parsing=True,
        )
        if set(fields) != {"notification_id", "revision"} or any(
            len(value) != 1 for value in fields.values()
        ):
            raise ValueError("NOTIFICATION_ACTION_FIELDS_INVALID")
        identity = fields["notification_id"][0]
        revision = fields["revision"][0]
        if (
            re.fullmatch(r"[0-9a-f]{64}", identity) is None
            or re.fullmatch(r"[0-9a-f]{64}", revision) is None
        ):
            raise ValueError("NOTIFICATION_ACTION_BINDING_INVALID")
        record = self.server.notification_centre.record(identity)
        if record is None or record.integrity_sha256 != revision:
            raise ValueError("NOTIFICATION_STALE_REVISION")
        return record

    def _sponsor_exit(self) -> None:
        if self.headers.get("Content-Length") not in {None, "0"}:
            self._text(HTTPStatus.BAD_REQUEST, "Request rejected.")
            return
        result = self.server.begin_sponsor_shutdown()
        if result not in {"SHUTDOWN_ACCEPTED", "ALREADY_SHUTTING_DOWN"}:
            self._text(
                HTTPStatus.CONFLICT,
                "KRONOS COULD NOT EXIT CLEANLY\n"
                f"Safe shutdown was not confirmed: {result}.\n"
                "No unrelated process was terminated.",
            )
            return
        body = (
            "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>KRONOS is shutting down</title></head>"
            "<body><main><h1>KRONOS IS SHUTTING DOWN SAFELY</h1>"
            "<p>You may close this window.<br>Launch KRONOS.app to start again.</p>"
            "</main></body></html>"
        ).encode("utf-8")
        self.send_response(HTTPStatus.ACCEPTED)
        self._security_headers()
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()
        if result == "SHUTDOWN_ACCEPTED":
            Thread(
                target=self.server.shutdown,
                name="kronos-sponsor-exit",
                daemon=True,
            ).start()

    def _record_sponsor_decision(self, candidate_id: str) -> None:
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0]
        try:
            content_length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            content_length = 0
        if (
            content_type.lower() != "application/x-www-form-urlencoded"
            or not 0 < content_length <= 64
        ):
            self._text(HTTPStatus.BAD_REQUEST, "Request rejected.")
            return
        try:
            fields = parse_qs(
                self.rfile.read(content_length).decode("utf-8"),
                strict_parsing=True,
            )
            modes = fields.get("mode", ())
            if set(fields) != {"mode"} or len(modes) != 1:
                raise ValueError
            mode = SponsorDecisionMode(modes[0])
            candidate = self.server.step32_workflow.snapshot().record_for_browser_key(candidate_id)
            if candidate is None:
                raise ValueError("SPONSOR_CANDIDATE_NOT_CURRENT")
            if candidate.candidate.canonical_instrument in MCX_SWING_FAMILIES:
                self._text(HTTPStatus.CONFLICT, "MCX_STEP31_NOT_COMMISSIONED")
                return
            self.server.step32_workflow.record_sponsor_choice(
                candidate_id,
                mode,
            )
        except (UnicodeDecodeError, ValueError):
            self._text(HTTPStatus.CONFLICT, "Sponsor decision is not available.")
            return
        self._redirect(f"/swing/trade-candidates/{candidate_id}")

    def _record_native_sponsor_decision(self) -> None:
        try:
            query = parse_qs(urlsplit(self.path).query, strict_parsing=True)
            plans = query.get("plan", ())
            content_length = int(self.headers.get("Content-Length", ""))
        except (ValueError, TypeError):
            self._text(HTTPStatus.BAD_REQUEST, "Request rejected.")
            return
        if (
            set(query) != {"plan"} or len(plans) != 1
            or self.headers.get("Content-Type", "").split(";", 1)[0].lower()
            != "application/x-www-form-urlencoded"
            or not 0 < content_length <= 256
        ):
            self._text(HTTPStatus.BAD_REQUEST, "Request rejected.")
            return
        try:
            fields = parse_qs(
                self.rfile.read(content_length).decode("utf-8"),
                keep_blank_values=True, strict_parsing=True,
            )
            modes = fields.get("mode", ())
            if len(modes) != 1:
                raise ValueError
            mode = SponsorTradeChoice(modes[0])
            if mode is SponsorTradeChoice.LIVE:
                if set(fields) != {"mode", "actual_entry", "lots"}:
                    raise ValueError
                actual_entry = Decimal(fields["actual_entry"][0])
                lots_text = fields["lots"][0]
                if not re.fullmatch(r"[1-9][0-9]*", lots_text):
                    raise ValueError
                lots = int(lots_text)
            else:
                if set(fields) != {"mode"}:
                    raise ValueError
                actual_entry, lots = None, None
            plan = next((item for item in self.server.native_review.snapshot().trade_plans
                         if item.trade_plan_id == plans[0]), None)
            if plan is None:
                raise ValueError("SPONSOR_PLAN_NOT_CURRENT")
            if plan.canonical_instrument in MCX_SWING_FAMILIES:
                self._text(HTTPStatus.CONFLICT, "MCX_STEP31_NOT_COMMISSIONED")
                return
            result = self.server.native_review.initiate_sponsor_decision(
                plans[0], mode, actual_live_entry=actual_entry, live_lots=lots,
            )
            if result.decision is None:
                raise ValueError(result.reason)
            if result.position is not None:
                capability, instrument, _ = self.server._operability_context(
                    result.position.canonical_instrument
                )
                if not self.server.native_review.lifecycle_monitoring_active(
                    result.position.position_id
                ):
                    self.server.native_review.attach_lifecycle_monitoring(
                        result.position.position_id, capability, instrument
                    )
                lifecycle = self.server.native_review.snapshot().active_lifecycle
                active = next(
                    item for item in lifecycle.active
                    if item.position_id == result.position.position_id
                )
                self.server.ux10_notifications.observe_active_trade_monitoring_activation(
                    active
                )
            self.server._synchronize_trade_window()
        except (UnicodeDecodeError, ValueError, InvalidOperation):
            self._text(HTTPStatus.CONFLICT, "Sponsor decision is not available.")
            return
        decision = result.decision
        assert decision is not None
        self._redirect(
            "/swing/trade-window/"
            + decision.native_run_identity
            + "/"
            + quote(decision.canonical_instrument, safe="")
        )

    def _record_sponsor_observation_decision(self) -> None:
        """Record explicit observation intent without activating a position."""

        try:
            content_length = int(self.headers.get("Content-Length", ""))
            if (
                self.headers.get("Content-Type", "").split(";", 1)[0].lower()
                != "application/x-www-form-urlencoded"
                or not 0 < content_length <= 4096
            ):
                raise ValueError("SPONSOR_OBSERVATION_REQUEST_INVALID")
            fields = parse_qs(
                self.rfile.read(content_length).decode("utf-8"),
                keep_blank_values=True,
                strict_parsing=True,
            )
            allowed = {
                "run_identity", "canonical_instrument", "native_assessment_sha256",
                "observation_evidence_id", "mode", "warning_acknowledged",
                "reason",
            }
            if not set(fields).issubset(allowed):
                raise ValueError("SPONSOR_OBSERVATION_REQUEST_INVALID")
            required = {
                "run_identity", "canonical_instrument", "native_assessment_sha256",
                "observation_evidence_id", "mode",
            }
            if not required.issubset(fields) or any(
                len(values) != 1 for values in fields.values()
            ):
                raise ValueError("SPONSOR_OBSERVATION_REQUEST_INVALID")
            run_identity = fields["run_identity"][0]
            instrument = fields["canonical_instrument"][0]
            assessment = fields["native_assessment_sha256"][0]
            observation_id = fields["observation_evidence_id"][0]
            choice = SponsorTradeChoice(fields["mode"][0])
            if instrument in MCX_SWING_FAMILIES:
                self._text(HTTPStatus.CONFLICT, "MCX_STEP31_NOT_COMMISSIONED")
                return
            acknowledged = fields.get("warning_acknowledged", [""])[0] == "YES"
            reason_text = fields.get("reason", [""])[0]
            reason = None if not reason_text else SponsorObservationReason(reason_text)
            if self.server.native_intake is not None:
                completed = self.server.visual_v3.completed_for(run_identity, instrument)
                current_v2 = self.server.native_intake.v2_for(run_identity, instrument)
                if (completed is None or current_v2 is None
                        or completed.promotion_v2 != current_v2
                        or current_v2.value["promotion_state"] not in {"BUY_NOW", "SELL_NOW"}):
                    raise ValueError("SPONSOR_OBSERVATION_V2_CURRENT_BINDING_INVALID")
            projection = self.server.trade_window.project(run_identity, instrument)
            _, current = self.server.application.opportunities_projection()
            if (
                projection is None
                or projection.step31_observation is None
                or current is None
                or current.run_identity != run_identity
                or projection.native_assessment_sha256 != assessment
                or projection.step31_observation.observation_evidence_id
                != observation_id
            ):
                raise ValueError("SPONSOR_OBSERVATION_CURRENT_BINDING_INVALID")

            risk_state = projection.risk_state
            existing_decision_id = None
            position_id = None
            if choice is SponsorTradeChoice.IGNORE:
                disposition = SponsorActivationDisposition.NOT_APPLICABLE_IGNORE
            elif risk_state == "RISK_REJECTED":
                disposition = SponsorActivationDisposition.BLOCKED_RISK_REJECTED
            elif risk_state == "RISK_UNAVAILABLE":
                disposition = SponsorActivationDisposition.BLOCKED_RISK_UNAVAILABLE
            elif risk_state == "RISK_CONSTRAINED":
                disposition = SponsorActivationDisposition.BLOCKED_CONSTRAINT
            elif projection.trade_plan is None:
                disposition = SponsorActivationDisposition.BLOCKED_MISSING_VALID_PLAN
            else:
                disposition = SponsorActivationDisposition.PENDING_ENTRY_CONFIRMATION

            context_record = self.server.mcx_supporting_context.context_for(
                instrument,
                assessment_boundary=projection.step31_observation.observation_boundary,
            )
            self.server.trade_window.record_sponsor_observation_choice(
                run_identity,
                instrument,
                assessment,
                observation_id,
                choice,
                disposition,
                current_run_identity=current.run_identity,
                decided_at=datetime.now(UTC),
                warning_acknowledged=acknowledged,
                sponsor_reason=reason,
                risk_identity=projection.risk_result_id,
                risk_state=risk_state,
                existing_sponsor_decision_identity=existing_decision_id,
                sponsor_position_identity=position_id,
                mcx_supporting_context_identity=(
                    None if context_record is None else context_record.record_id
                ),
                mcx_supporting_context_sha256=(
                    None if context_record is None else context_record.integrity_sha256
                ),
            )
            self.server._synchronize_trade_window()
        except (UnicodeDecodeError, ValueError, InvalidOperation):
            self._trade_window_conflict(
                locals().get("run_identity"),
                locals().get("instrument"),
                "SPONSOR DECISION NOT AVAILABLE",
                "The current opportunity evidence is stale, incomplete, or already final. Refresh Analysis before trying again.",
            )
            return
        self._redirect(
            "/swing/trade-window/" + run_identity + "/" + quote(instrument, safe="")
        )

    def _activate_sponsor_observation_entry(self) -> None:
        """Confirm PAPER/LIVE entry after a separately persisted Sponsor choice."""

        try:
            content_length = int(self.headers.get("Content-Length", ""))
            if (
                self.headers.get("Content-Type", "").split(";", 1)[0].lower()
                != "application/x-www-form-urlencoded"
                or not 0 < content_length <= 4096
            ):
                raise ValueError("SPONSOR_ENTRY_REQUEST_INVALID")
            fields = parse_qs(
                self.rfile.read(content_length).decode("utf-8"),
                keep_blank_values=True,
                strict_parsing=True,
            )
            allowed = {
                "run_identity", "canonical_instrument", "native_assessment_sha256",
                "decision_identity", "mode", "entry_confirmed",
                "manual_execution_confirmed", "actual_entry", "lots",
            }
            required = {
                "run_identity", "canonical_instrument", "native_assessment_sha256",
                "decision_identity", "mode",
            }
            if (
                not set(fields).issubset(allowed)
                or not required.issubset(fields)
                or any(len(values) != 1 for values in fields.values())
            ):
                raise ValueError("SPONSOR_ENTRY_REQUEST_INVALID")
            run_identity = fields["run_identity"][0]
            instrument = fields["canonical_instrument"][0]
            assessment = fields["native_assessment_sha256"][0]
            decision_identity = fields["decision_identity"][0]
            choice = SponsorTradeChoice(fields["mode"][0])
            if instrument in MCX_SWING_FAMILIES:
                self._text(HTTPStatus.CONFLICT, "MCX_STEP31_NOT_COMMISSIONED")
                return
            if self.server.native_intake is not None:
                completed = self.server.visual_v3.completed_for(run_identity, instrument)
                current_v2 = self.server.native_intake.v2_for(run_identity, instrument)
                if (completed is None or current_v2 is None
                        or completed.promotion_v2 != current_v2
                        or current_v2.value["promotion_state"] not in {"BUY_NOW", "SELL_NOW"}):
                    raise ValueError("SPONSOR_ENTRY_V2_CURRENT_BINDING_INVALID")
            projection = self.server.trade_window.project(run_identity, instrument)
            _, current = self.server.application.opportunities_projection()
            if (
                projection is None
                or projection.trade_plan is None
                or current is None
                or current.run_identity != run_identity
                or projection.native_assessment_sha256 != assessment
                or projection.sponsor_observation_decision_id != decision_identity
                or projection.sponsor_observation_choice != choice.value
                or projection.activation_disposition
                != SponsorActivationDisposition.PENDING_ENTRY_CONFIRMATION.value
                or projection.risk_state != "RISK_APPROVED"
            ):
                raise ValueError("SPONSOR_ENTRY_CURRENT_BINDING_INVALID")
            actual_entry = None
            lots = None
            if choice is SponsorTradeChoice.PAPER:
                if fields.get("entry_confirmed", [""])[0] != "YES":
                    raise ValueError("PAPER_ENTRY_CONFIRMATION_REQUIRED")
                if set(fields).difference(required | {"entry_confirmed"}):
                    raise ValueError("SPONSOR_ENTRY_REQUEST_INVALID")
            elif choice is SponsorTradeChoice.LIVE:
                if fields.get("manual_execution_confirmed", [""])[0] != "YES":
                    raise ValueError("LIVE_MANUAL_EXECUTION_CONFIRMATION_REQUIRED")
                actual_entry = Decimal(fields.get("actual_entry", [""])[0])
                if not actual_entry.is_finite() or actual_entry <= 0:
                    raise ValueError("LIVE_POSITIVE_ENTRY_REQUIRED")
                lots_text = fields.get("lots", [""])[0]
                if not re.fullmatch(r"[1-9][0-9]*", lots_text):
                    raise ValueError("LIVE_POSITIVE_INTEGER_LOTS_REQUIRED")
                lots = int(lots_text)
                if set(fields).difference(
                    required | {"manual_execution_confirmed", "actual_entry", "lots"}
                ):
                    raise ValueError("SPONSOR_ENTRY_REQUEST_INVALID")
            else:
                raise ValueError("SPONSOR_ENTRY_CHOICE_INVALID")

            result = self.server.native_review.initiate_sponsor_decision(
                projection.trade_plan.trade_plan_id,
                choice,
                actual_live_entry=actual_entry,
                live_lots=lots,
            )
            if result.decision is None or result.position is None:
                raise ValueError(result.reason)
            self.server.trade_window.finalize_sponsor_observation_activation(
                run_identity,
                instrument,
                decision_identity,
                choice,
                disposition=SponsorActivationDisposition.ACTIVATED,
                existing_sponsor_decision_identity=result.decision.decision_id,
                sponsor_position_identity=result.position.position_id,
                recorded_at=datetime.now(UTC),
            )
            capability, governed_instrument, _ = self.server._operability_context(
                result.position.canonical_instrument
            )
            if not self.server.native_review.lifecycle_monitoring_active(
                result.position.position_id
            ):
                self.server.native_review.attach_lifecycle_monitoring(
                    result.position.position_id, capability, governed_instrument
                )
                lifecycle = self.server.native_review.snapshot().active_lifecycle
                active = next(
                    item for item in lifecycle.active
                    if item.position_id == result.position.position_id
                )
                self.server.ux10_notifications.observe_active_trade_monitoring_activation(
                    active
                )
            self.server._synchronize_trade_window()
        except (UnicodeDecodeError, ValueError, InvalidOperation):
            self._trade_window_conflict(
                locals().get("run_identity"),
                locals().get("instrument"),
                "ENTRY NOT ACTIVATED",
                "Entry confirmation is invalid, stale, or blocked. The recorded Sponsor observation decision has been preserved.",
            )
            return
        self._redirect(
            "/swing/trade-window/" + run_identity + "/" + quote(instrument, safe="")
        )

    def _start_paper_observation_track(self) -> None:
        """Start research-only PAPER path tracking after explicit confirmation."""

        run_identity = instrument = None
        try:
            content_length = int(self.headers.get("Content-Length", ""))
            if (
                self.headers.get("Content-Type", "").split(";", 1)[0].lower()
                != "application/x-www-form-urlencoded"
                or not 0 < content_length <= 2048
            ):
                raise ValueError("PAPER_OBSERVATION_START_REQUEST_INVALID")
            fields = parse_qs(
                self.rfile.read(content_length).decode("utf-8"),
                strict_parsing=True,
            )
            required = {
                "run_identity",
                "canonical_instrument",
                "native_assessment_sha256",
                "decision_identity",
                "track_confirmed",
            }
            if set(fields) != required or any(
                len(values) != 1 for values in fields.values()
            ):
                raise ValueError("PAPER_OBSERVATION_START_REQUEST_INVALID")
            run_identity = fields["run_identity"][0]
            instrument = fields["canonical_instrument"][0]
            assessment = fields["native_assessment_sha256"][0]
            decision_identity = fields["decision_identity"][0]
            if instrument in MCX_SWING_FAMILIES:
                self._text(HTTPStatus.CONFLICT, "MCX_STEP31_NOT_COMMISSIONED")
                return
            if fields["track_confirmed"][0] != "YES":
                raise ValueError("PAPER_OBSERVATION_START_CONFIRMATION_REQUIRED")
            projection = self.server.trade_window.project(run_identity, instrument)
            _, current, continuity, _ = (
                self.server.application.opportunities_bundle_projection()
            )
            row = None if continuity is None else next((
                item for item in continuity.contribution.rows
                if item.canonical_instrument == instrument
            ), None)
            if (
                projection is None
                or current is None
                or row is None
                or row.opportunity_id is None
                or row.material_revision is None
                or row.source_binding is None
                or current.run_identity != run_identity
                or projection.native_assessment_sha256 != assessment
                or projection.sponsor_observation_decision_id != decision_identity
                or projection.sponsor_observation_choice != "PAPER"
                or not projection.paper_observation_track_start_available
                or not projection.activation_disposition.startswith("BLOCKED_")
            ):
                raise ValueError("PAPER_OBSERVATION_TRACK_CURRENT_BINDING_INVALID")
            authority = self.server.trade_window.prepare_paper_observation_monitoring_authority(
                run_identity,
                instrument,
                opportunity_identity=row.opportunity_id,
                material_revision=row.material_revision,
                source_binding=row.source_binding,
            )
            authority_token = (
                continuity.integrity_sha256,
                row.opportunity_id,
                row.material_revision,
                row.material_fingerprint,
                row.source_binding,
                authority,
            )

            def authority_is_current() -> bool:
                committed = self.server.application.committed_continuity()
                if committed is None:
                    return False
                candidate = next((
                    item for item in committed.contribution.rows
                    if item.canonical_instrument == instrument
                ), None)
                if candidate is None:
                    return False
                try:
                    prepared = self.server.trade_window.prepare_paper_observation_monitoring_authority(
                        committed.contribution.native_run.run_identity,
                        instrument,
                        opportunity_identity=candidate.opportunity_id,
                        material_revision=candidate.material_revision,
                        source_binding=candidate.source_binding,
                    )
                except (TypeError, ValueError):
                    return False
                return (
                    committed.contribution.integrity_sha256,
                    candidate.opportunity_id,
                    candidate.material_revision,
                    candidate.material_fingerprint,
                    candidate.source_binding,
                    prepared,
                ) == authority_token
            track = self.server.trade_window.start_paper_observation_track(
                run_identity,
                instrument,
                assessment,
                decision_identity,
                current_run_identity=current.run_identity,
                started_at=datetime.now(UTC),
                monitoring_authority=authority,
                authority_is_current=authority_is_current,
            )
            try:
                capability, governed_instrument, _ = self.server._operability_context(
                    instrument
                )
                self.server.trade_window.attach_paper_observation_monitoring(
                    track.track.track_identity,
                    capability,
                    governed_instrument,
                    current_authority=authority,
                    authority_is_current=authority_is_current,
                )
            except Exception as error:
                self.server.trade_window.record_paper_observation_monitoring_failure(
                    track.track.track_identity, paper_monitoring_failure_reason(error)
                )
            self.server._synchronize_trade_window()
        except (UnicodeDecodeError, ValueError):
            self._trade_window_conflict(
                run_identity,
                instrument,
                "PAPER OBSERVATION TRACK NOT STARTED",
                "The exact blocked PAPER decision is stale, unavailable, already tracked, or was not explicitly confirmed.",
            )
            return
        self._redirect(
            "/swing/trade-window/" + run_identity + "/" + quote(instrument, safe="")
        )

    def _trade_window_conflict(
        self,
        run_identity: object,
        instrument: object,
        title: str,
        reason: str,
    ) -> None:
        projection = (
            self.server.trade_window.project(run_identity, instrument)
            if type(run_identity) is str and type(instrument) is str
            else None
        )
        if projection is None:
            self._redirect("/swing/opportunities")
            return
        self._html(render_native_trade_window(
            self.server.application.snapshot(),
            projection,
            workflow_error=(title, reason),
        ))

    def _construct_native_trade_plan(self) -> None:
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0]
        try:
            content_length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            content_length = 0
        if content_type.lower() != "application/x-www-form-urlencoded" or not 0 < content_length <= 512:
            self._text(HTTPStatus.BAD_REQUEST, "Request rejected.")
            return
        run_identity = instrument = assessment = None
        try:
            body = self.rfile.read(content_length).decode("utf-8")
            fields = parse_qs(body, strict_parsing=True)
            candidates = {
                key: value[0]
                for key, value in fields.items()
                if len(value) == 1
            }
            run_identity = candidates.get("run_identity")
            instrument = candidates.get("canonical_instrument")
            assessment = candidates.get("native_assessment_sha256")
            if set(fields) != {
                "run_identity", "canonical_instrument", "native_assessment_sha256"
            } or any(len(value) != 1 for value in fields.values()):
                raise ValueError
            assert run_identity is not None and instrument is not None and assessment is not None
            if (
                re.fullmatch(r"SWING-RUN-[A-F0-9]{32}", run_identity) is None
                or re.fullmatch(r"[A-Z0-9&._ -]{1,64}", instrument) is None
                or re.fullmatch(r"[0-9a-f]{64}", assessment) is None
            ):
                raise ValueError
            # Direct, stale and replayed MCX forms all fail before Provider
            # work or a durable construction attempt while Step-31 is held.
            if instrument in MCX_SWING_FAMILIES:
                mcx_fields = parse_qs(
                    body, strict_parsing=True, keep_blank_values=True,
                )
                if set(mcx_fields) != set(fields) or any(
                    len(values) != 1 for values in mcx_fields.values()
                ):
                    raise ValueError
                self._text(HTTPStatus.CONFLICT, "MCX_STEP31_NOT_COMMISSIONED")
                return
            self.server.construct_current_trade_plan(
                run_identity, instrument, assessment
            )
        except (UnicodeDecodeError, ValueError):
            if instrument in MCX_SWING_FAMILIES:
                self._text(HTTPStatus.BAD_REQUEST, "Request rejected.")
                return
            if (
                isinstance(run_identity, str)
                and isinstance(instrument, str)
                and isinstance(assessment, str)
                and re.fullmatch(r"SWING-RUN-[A-F0-9]{32}", run_identity)
                and re.fullmatch(r"[A-Z0-9&._ -]{1,64}", instrument)
                and re.fullmatch(r"[0-9a-f]{64}", assessment)
            ):
                occurred_at = datetime.now(UTC)
                self.server._retain_trade_plan_attempt(
                    sha256(
                        f"{run_identity}:{instrument}:{assessment}:{occurred_at.isoformat()}:{uuid4().hex}".encode()
                    ).hexdigest(),
                    run_identity,
                    instrument,
                    assessment,
                    occurred_at,
                    TradePlanConstructionStage.REQUEST_PARSE,
                    "TRADE_PLAN_REQUEST_INVALID",
                )
                self._redirect(
                    f"/swing/trade-window/{run_identity}/{quote(instrument, safe='')}"
                )
                return
            self._text(HTTPStatus.BAD_REQUEST, "Request rejected.")
            return
        self._redirect(
            f"/swing/trade-window/{run_identity}/{quote(instrument, safe='')}"
        )

    def _exit_native_paper_position(self) -> None:
        try:
            query = parse_qs(urlsplit(self.path).query, strict_parsing=True)
            positions = query.get("position", ())
            content_length = int(self.headers.get("Content-Length", "0"))
            if set(query) != {"position"} or len(positions) != 1 or content_length != 0:
                raise ValueError
            self.server.native_review.exit_paper_position_current(positions[0])
        except (TypeError, ValueError):
            self._text(HTTPStatus.CONFLICT, "Current authoritative market observation is unavailable.")
            return
        self._redirect("/swing/closed")

    def _record_native_live_exit(self) -> None:
        try:
            query = parse_qs(urlsplit(self.path).query, strict_parsing=True)
            positions = query.get("position", ())
            content_length = int(self.headers.get("Content-Length", ""))
            if (
                set(query) != {"position"} or len(positions) != 1
                or self.headers.get("Content-Type", "").split(";", 1)[0].lower()
                != "application/x-www-form-urlencoded"
                or not 0 < content_length <= 256
            ):
                raise ValueError
            fields = parse_qs(
                self.rfile.read(content_length).decode("utf-8"),
                strict_parsing=True,
            )
            if set(fields) != {"actual_exit", "reason"} or any(len(value) != 1 for value in fields.values()):
                raise ValueError
            actual_exit = Decimal(fields["actual_exit"][0])
            reason = TradeExitReason(fields["reason"][0])
            closure = self.server.native_review.record_live_exit(
                positions[0], actual_exit=actual_exit, exit_reason=reason,
            )
            if closure is None:
                raise ValueError
        except (UnicodeDecodeError, InvalidOperation, TypeError, ValueError):
            self._text(HTTPStatus.CONFLICT, "Sponsor-attested actual Exit was not recorded.")
            return
        self._redirect("/swing/closed")

    def _graceful_backend_shutdown(self) -> None:
        control = self.server.restart_control
        if (
            control is None
            or self.headers.get("Host")
            != f"{_LOOPBACK_HOST}:{self.server.server_port}"
            or self.headers.get("Content-Length") not in {None, "0"}
            or not control.authorized(
                process_id=self.headers.get("X-Kronos-Backend-Pid"),
                token=self.headers.get("X-Kronos-Restart-Token"),
            )
        ):
            self._text(HTTPStatus.FORBIDDEN, "Request rejected.")
            return
        governance = self.server.connection_governance
        if governance is not None:
            generation = self.headers.get("X-Kronos-Maintenance-Generation")
            if generation is None:
                self._text(HTTPStatus.CONFLICT, "Governed maintenance launcher required.")
                return
            claimed = False
            try:
                if (not control.owns_current_process()
                        or not self.server.maintenance_replacement_idle(
                            allow_drainable=True)):
                    raise ValueError("MAINTENANCE_WORK_IN_PROGRESS")
                if not self.server.maintenance_admission.claim(generation):
                    raise ValueError("MAINTENANCE_GENERATION_CONFLICT")
                claimed = True
                with self.server._shutdown_lock:
                    if self.server._shutdown_started:
                        raise ValueError("MAINTENANCE_ALREADY_SHUTTING_DOWN")
                    self.server._shutdown_started = True
                self.server.application.enter_controlled_maintenance(generation)
                self.server.maintenance_admission.draining(generation)
            except (OSError, ValueError):
                if claimed:
                    self.server.maintenance_admission.fail(
                        generation, "OWNER_PROOF_UNAVAILABLE"
                    )
                self._text(HTTPStatus.CONFLICT, "Maintenance validation failed.")
                return
        self.send_response(HTTPStatus.ACCEPTED)
        self._security_headers()
        body = (b'{"status":"DRAINING"}' if governance is not None
                else b'{"status":"STOPPING"}')
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()
        Thread(
            target=(self.server.shutdown if governance is None else
                    lambda: self.server._complete_governed_shutdown(
                        generation, governance.process.runtime_identity
                    )),
            name="kronos-browser-maintenance-drain",
            daemon=True,
        ).start()

    def _receive_chart_analyst_credential(self) -> None:
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0]
        try:
            content_length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            content_length = 0
        if (
            content_type.lower() != "application/x-www-form-urlencoded"
            or not 0 < content_length <= _MAX_CREDENTIAL_FORM_BYTES
        ):
            self._text(HTTPStatus.BAD_REQUEST, "Request rejected.")
            return

        raw = self.rfile.read(content_length)
        encoded = ""
        fields: dict[str, list[str]] = {}
        api_key = ""
        try:
            encoded = raw.decode("utf-8")
            fields = parse_qs(
                encoded,
                keep_blank_values=True,
                strict_parsing=True,
            )
            if set(fields) != {"api_key"} or len(fields["api_key"]) != 1:
                raise ValueError("CHART_ANALYST_CREDENTIAL_FORM_INVALID")
            api_key = fields["api_key"][0]
            self.server.chart_analyst_credentials.configure(api_key)
        except (UnicodeDecodeError, ValueError):
            self._text(HTTPStatus.BAD_REQUEST, "Request rejected.")
            return
        finally:
            api_key = ""
            for values in fields.values():
                values.clear()
            fields.clear()
            encoded = ""
            raw = b""
        self._redirect("/settings")

    def _disconnect_provider(self) -> None:
        content_length = self.headers.get("Content-Length")
        confirmed = False
        if content_length not in {None, "0"}:
            try:
                length = int(content_length)
            except ValueError:
                length = 0
            if (
                self.headers.get("Content-Type", "").split(";", 1)[0].lower()
                == "application/x-www-form-urlencoded"
                and 0 < length <= 128
            ):
                try:
                    fields = parse_qs(
                        self.rfile.read(length).decode("utf-8"),
                        strict_parsing=True,
                    )
                except (UnicodeDecodeError, ValueError):
                    fields = {}
                confirmed = fields == {"confirm_active": ["YES"]}
        if self.server.active_live_monitoring_count() and not confirmed:
            self._redirect("/settings#kite-market-data")
            return
        if self.server.application.disconnect_provider():
            self.server.trade_window.close_monitoring()
            self.server.trade_window.mark_paper_observation_monitoring_unavailable(
                "PROVIDER_DISCONNECTED"
            )
        self._redirect("/swing/opportunities")

    def _receive_telegram_token(self) -> None:
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0]
        try:
            content_length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            content_length = 0
        if (
            content_type.lower() != "application/x-www-form-urlencoded"
            or not 0 < content_length <= _MAX_CREDENTIAL_FORM_BYTES
        ):
            self._text(HTTPStatus.BAD_REQUEST, "Request rejected.")
            return
        raw = self.rfile.read(content_length)
        token = ""
        fields: dict[str, list[str]] = {}
        try:
            fields = parse_qs(
                raw.decode("utf-8"), keep_blank_values=True, strict_parsing=True
            )
            if set(fields) != {"bot_token"} or len(fields["bot_token"]) != 1:
                raise ValueError
            token = fields["bot_token"][0]
            self.server.telegram.configure_token(token)
        except (UnicodeDecodeError, ValueError):
            self._text(HTTPStatus.BAD_REQUEST, "Request rejected.")
            return
        finally:
            token = ""
            for values in fields.values():
                values.clear()
            fields.clear()
            raw = b""
        self._redirect("/settings")

    def _discover_telegram_private_chat(self) -> None:
        if self.headers.get("Content-Length") not in {None, "0"}:
            self._text(HTTPStatus.BAD_REQUEST, "Request rejected.")
            return
        try:
            self.server.telegram.discover_private_chats()
        except Exception:
            pass
        self._redirect("/settings")

    def _confirm_telegram_private_chat(self) -> None:
        try:
            content_length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            content_length = 0
        if (
            self.headers.get("Content-Type", "").split(";", 1)[0].lower()
            != "application/x-www-form-urlencoded"
            or not 0 < content_length <= 256
        ):
            self._text(HTTPStatus.BAD_REQUEST, "Request rejected.")
            return
        try:
            fields = parse_qs(
                self.rfile.read(content_length).decode("utf-8"), strict_parsing=True
            )
            values = fields.get("selection_id", ())
            if (
                set(fields) != {"selection_id"}
                or len(values) != 1
                or re.fullmatch(r"[0-9a-f]{64}", values[0]) is None
            ):
                raise ValueError
            self.server.telegram.confirm_private_chat(values[0])
        except (UnicodeDecodeError, ValueError):
            self._text(HTTPStatus.BAD_REQUEST, "Request rejected.")
            return
        self._redirect("/settings")

    def _test_telegram(self) -> None:
        if self.headers.get("Content-Length") not in {None, "0"}:
            self._text(HTTPStatus.BAD_REQUEST, "Request rejected.")
            return
        self.server.telegram.test()
        self._redirect("/settings")

    def _connect_telegram(self) -> None:
        if self.headers.get("Content-Length") not in {None, "0"}:
            self._text(HTTPStatus.BAD_REQUEST, "Request rejected.")
            return
        status = self.server.telegram.connect()
        if status.delivery_enabled:
            self.server.ux10_notifications.retry_pending()
        self._redirect("/settings")

    def _disconnect_telegram(self) -> None:
        if self.headers.get("Content-Length") not in {None, "0"}:
            self._text(HTTPStatus.BAD_REQUEST, "Request rejected.")
            return
        self.server.telegram.disconnect()
        self._redirect("/settings")

    def _remove_telegram_configuration(self) -> None:
        if (
            self.headers.get("Content-Length") not in {None, "0"}
            or urlsplit(self.path).query != "confirm=REMOVE"
        ):
            self._text(HTTPStatus.BAD_REQUEST, "Request rejected.")
            return
        self.server.telegram.remove_configuration()
        self._redirect("/settings")

    def _set_chart_analyst_activation(self, enabled: bool) -> None:
        if self.headers.get("Content-Length") not in {None, "0"}:
            self._text(HTTPStatus.BAD_REQUEST, "Request rejected.")
            return
        try:
            self.server.chart_analyst_activation.set_enabled(enabled)
        except Exception:
            self._text(HTTPStatus.CONFLICT, "Configuration could not be saved.")
            return
        self._redirect("/settings")

    def _test_live_monitoring(self) -> None:
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0]
        try:
            content_length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            content_length = 0
        if (
            content_type.lower() != "application/x-www-form-urlencoded"
            or not 0 < content_length <= 256
        ):
            self._text(HTTPStatus.BAD_REQUEST, "Request rejected.")
            return
        try:
            fields = parse_qs(
                self.rfile.read(content_length).decode("utf-8"),
                keep_blank_values=True,
                strict_parsing=True,
            )
            instruments = fields.get("instrument", ())
            if set(fields) != {"instrument"} or len(instruments) != 1:
                raise ValueError
            self.server.application.test_live_monitoring(instruments[0])
        except (UnicodeDecodeError, ValueError):
            self._text(HTTPStatus.BAD_REQUEST, "Request rejected.")
            return
        self._redirect("/settings")

    def _receive_v1_chart(self) -> None:
        try:
            query = parse_qs(urlsplit(self.path).query, strict_parsing=True)
        except ValueError:
            self._text(HTTPStatus.BAD_REQUEST, "Chart binding is invalid.")
            return
        instrument_values = query.get("instrument", ())
        timeframe_values = query.get("timeframe", ())
        if (
            set(query) != {"instrument", "timeframe"}
            or len(instrument_values) != 1
            or len(timeframe_values) != 1
        ):
            self._text(HTTPStatus.BAD_REQUEST, "Chart binding is invalid.")
            return
        try:
            timeframe = ChartTimeframe(timeframe_values[0])
        except ValueError:
            self._text(HTTPStatus.BAD_REQUEST, "Chart timeframe is invalid.")
            return
        try:
            content_length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            content_length = 0
        if not 0 < content_length <= 25 * 1024 * 1024:
            self._text(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Chart size is invalid.")
            return
        payload = self.rfile.read(content_length)
        try:
            self.server.v1_review.upload(
                instrument=instrument_values[0],
                timeframe=timeframe,
                content_type=self.headers.get("Content-Type", ""),
                original_bytes=payload,
            )
        except (ValueError, TradingViewEvidenceStoreError):
            self._text(HTTPStatus.BAD_REQUEST, "Chart upload rejected.")
            return
        self._redirect("/swing/v1-review")

    def _remove_v1_chart(self) -> None:
        try:
            query = parse_qs(urlsplit(self.path).query, strict_parsing=True)
        except ValueError:
            self._text(HTTPStatus.BAD_REQUEST, "Chart binding is invalid.")
            return
        instrument_values = query.get("instrument", ())
        timeframe_values = query.get("timeframe", ())
        if (
            set(query) != {"instrument", "timeframe"}
            or len(instrument_values) != 1
            or len(timeframe_values) != 1
        ):
            self._text(HTTPStatus.BAD_REQUEST, "Chart binding is invalid.")
            return
        try:
            timeframe = ChartTimeframe(timeframe_values[0])
            self.server.v1_review.remove_chart(
                instrument=instrument_values[0],
                timeframe=timeframe,
            )
        except (ValueError, TradingViewEvidenceStoreError):
            self._text(HTTPStatus.BAD_REQUEST, "Chart removal rejected.")
            return
        self._redirect("/swing/v1-review")

    def _v1_chart_preview(self) -> None:
        try:
            query = parse_qs(urlsplit(self.path).query, strict_parsing=True)
        except ValueError:
            self._text(HTTPStatus.BAD_REQUEST, "Chart preview binding is invalid.")
            return
        instrument_values = query.get("instrument", ())
        timeframe_values = query.get("timeframe", ())
        sha256_values = query.get("sha256", ())
        if (
            set(query) != {"instrument", "timeframe", "sha256"}
            or len(instrument_values) != 1
            or len(timeframe_values) != 1
            or len(sha256_values) != 1
            or re.fullmatch(r"[0-9a-f]{64}", sha256_values[0]) is None
        ):
            self._text(HTTPStatus.BAD_REQUEST, "Chart preview binding is invalid.")
            return
        try:
            timeframe = ChartTimeframe(timeframe_values[0])
            revision, payload = self.server.v1_review.active_chart(
                instrument=instrument_values[0],
                timeframe=timeframe,
                sha256=sha256_values[0],
            )
        except (ValueError, TradingViewEvidenceStoreError, OSError):
            self._text(HTTPStatus.NOT_FOUND, "Chart preview unavailable.")
            return
        self._respond(HTTPStatus.OK, payload, revision.content_type)

    @staticmethod
    def _native_subject(value: str) -> VisualEvidenceSubjectKind:
        try:
            return {
                "native": VisualEvidenceSubjectKind.NATIVE,
                "reference": VisualEvidenceSubjectKind.REFERENCE,
            }[value]
        except KeyError as error:
            raise ValueError("NATIVE_CHART_SUBJECT_INVALID") from error

    def _native_intake_mutation(self, operation):
        if operation in {"STAGE", "REMOVE"}:
            # The chart write and successor-page publication form one Browser
            # operation. A second candidate waits for the new page generation.
            with self.server._native_chart_stage_lock:
                return self._native_intake_mutation_inner(operation)
        return self._native_intake_mutation_inner(operation)

    def _native_intake_mutation_inner(self, operation):
        workflow = self.server.native_intake
        market, expected = None, None
        import_committed = False
        acceptance_marker = None
        bulk_identity = None
        try:
            if workflow is None:
                raise ReviewEvidenceError("REVIEW_CONTRACT_UNSUPPORTED")
            query = parse_qs(urlsplit(self.path).query, strict_parsing=True)
            allowed = {"market", "expected", "instrument", "role"} if operation in {"STAGE", "REMOVE"} else {"market", "expected"}
            if set(query) - allowed or any(len(values) != 1 for values in query.values()) or "market" not in query:
                raise ValueError
            market = query["market"][0]
            length = int(self.headers.get("Content-Length", "0"))
            if operation == "STAGE":
                if not 0 < length <= 25 * 1024 * 1024 or "expected" not in query:
                    raise ValueError
                encoded = query["expected"][0]
            else:
                if not 0 <= length <= 256 * 1024:
                    raise ValueError
                fields = parse_qs(self.rfile.read(length).decode("utf-8"), strict_parsing=True) if length else {}
                if fields:
                    if set(fields) != {"expected"} or len(fields["expected"]) != 1 or "expected" in query:
                        raise ValueError
                    encoded = fields["expected"][0]
                else:
                    encoded = query["expected"][0]
            expected = strict_json(encoded)
            if operation in {"STAGE", "REMOVE"}:
                if not {"instrument", "role"}.issubset(query):
                    raise ValueError
                selection = workflow.stage(market, query["instrument"][0], query["role"][0], expected,
                    image=self.rfile.read(length) if operation == "STAGE" else None,
                    content_type=self.headers.get("Content-Type", "") if operation == "STAGE" else None,
                    reject_exact_replay=operation == "STAGE" and market == "NSE")
            elif operation == "GENERATE":
                publication = workflow.generate(market, expected)
                workflow.export_question(market, publication)
            elif operation == "IMPORT":
                acceptance_marker = self._answer_acceptance_marker(workflow, market, expected)
                if self.server.bulk_import is None:
                    raise ReviewEvidenceError("REVIEW_CONTRACT_UNSUPPORTED")
                admitted, _created = self.server.bulk_import.admit_from_directory(
                    market, expected)
                bulk_identity = admitted["batch_identity"]
            elif operation == "HANDOFF":
                _, facts, _ = workflow._context()
                history = workflow.store.native_acceptance_history(market, facts.run_identity)
                if not history:
                    raise ReviewEvidenceError("REVIEW_ACCEPTANCE_INCOMPLETE")
                for receipt in history[0].receipts:
                    if receipt.binding.value["canonical_instrument"] in expected:
                        workflow.handoff(history[0], receipt, expected=expected)
                self.server.trade_window.restore(self.server.visual_v3.completed_snapshot())
                self.server.refresh_swing_projection_revision()
            else:
                raise ValueError
        except ReviewEvidenceError as error:
            unchanged_acceptance = (acceptance_marker is not None and
                acceptance_marker == self._answer_acceptance_marker(workflow, market, expected))
            if operation == "IMPORT" and import_committed:
                self._redirect_answer_rejection(None, market, expected, confirmed_no_import=False)
                return
            inline_payload_rejection = (
                operation == "STAGE"
                and "application/json" in self.headers.get("Accept", "")
            )
            if (workflow is not None and market in {"NSE", "MCX"}
                    and type(expected) is dict):
                if not inline_payload_rejection:
                    for instrument in expected:
                        workflow.errors[(market, instrument)] = error.code
                if not (inline_payload_rejection and error.code in {
                        "REVIEW_ACCEPTANCE_INCOMPLETE", "REVIEW_CHART_ALREADY_CURRENT"}):
                    try:
                        workflow.prepare_page_state()
                    except (OSError, ValueError):
                        if operation == "IMPORT":
                            self._redirect_answer_rejection(None, market, expected, confirmed_no_import=False)
                            return
                        raise
            if operation == "STAGE" and "application/json" in self.headers.get("Accept", ""):
                self._json({"outcome": "REJECTED", "reason": error.code}, status=HTTPStatus.CONFLICT)
            elif operation == "IMPORT":
                self._redirect_answer_rejection(error.code, market, expected,
                                                confirmed_no_import=unchanged_acceptance)
            else:
                self._text(HTTPStatus.CONFLICT,
                    "Review intake did not complete. Check the exact current Review workspace and its required chart/Answer package. "
                    "Retained evidence has not been rebound.\nReason: " + error.code)
            return
        except (OSError, ValueError, TypeError, KeyError):
            if workflow is not None and operation != "IMPORT":
                workflow.prepare_page_state()
            if operation == "STAGE" and "application/json" in self.headers.get("Accept", ""):
                self._json({"outcome": "REJECTED", "reason": "REVIEW_INTAKE_UNAVAILABLE"},
                           status=HTTPStatus.BAD_REQUEST)
            elif operation == "IMPORT":
                self._redirect_answer_rejection(None, market, expected, confirmed_no_import=False)
            else:
                self._text(HTTPStatus.BAD_REQUEST,
                    "Review intake is unavailable for this request. Return to the current Review workspace before retrying.\n"
                    "Reason: REVIEW_INTAKE_UNAVAILABLE")
            return
        except Exception:
            if operation != "IMPORT":
                raise
            self._redirect_answer_rejection(None, market, expected, confirmed_no_import=False)
            return
        if operation == "IMPORT":
            self._redirect("/swing/v1-review?" + urlencode({
                "bulk_import": bulk_identity,
            }))
            return
        try:
            page_ready = workflow.prepare_page_state()
        except (OSError, ValueError):
            if operation != "IMPORT":
                raise
            self._redirect_answer_rejection(None, market, expected, confirmed_no_import=False)
            return
        if operation == "STAGE" and "application/json" in self.headers.get("Accept", ""):
            if not page_ready:
                self._json({"outcome": "CHART_RECEIVED_PAGE_UNAVAILABLE",
                            "reason": workflow.page_state_status()["failure"]},
                           status=HTTPStatus.CONFLICT)
                return
            self._json({"outcome": "CHART_RECEIVED", "market": market,
                        "instrument": query["instrument"][0], "role": query["role"][0],
                        "selection_identity": selection["selection_sha256"],
                        "chart_sha256": selection["image"]["sha256"]})
            return
        self._redirect("/swing/v1-review")

    def _redirect_answer_rejection(self, code, market=None, expected=None, *, confirmed_no_import=True):
        instrument = next(iter(expected)) if type(expected) is dict and len(expected) == 1 else None
        notice = self.server.retain_answer_notice(code, market, instrument,
                                                  confirmed_no_import=confirmed_no_import)
        self._swing_post_failed = True
        self._redirect("/swing/v1-review?answer_notice=" + notice)

    def _selected_answer_form(self):
        """Read one bounded multipart PDF and its exact mutation envelope."""
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= 128 * 1024 * 1024 + 512 * 1024:
            raise ValueError("SELECTED_ANSWER_REQUEST_INVALID")
        content_type = self.headers.get("Content-Type", "")
        if not content_type.lower().startswith("multipart/form-data;"):
            raise ValueError("SELECTED_ANSWER_REQUEST_INVALID")
        header = content_type.encode("ascii", "strict")
        message = BytesParser(policy=email_policy).parsebytes(
            b"Content-Type: " + header + b"\r\nMIME-Version: 1.0\r\n\r\n"
            + self.rfile.read(length)
        )
        if not message.is_multipart():
            raise ValueError("SELECTED_ANSWER_REQUEST_INVALID")
        fields = {}
        for part in message.iter_parts():
            if part.get_content_disposition() != "form-data":
                raise ValueError("SELECTED_ANSWER_REQUEST_INVALID")
            name = part.get_param("name", header="content-disposition")
            if name not in {"expected", "answer_pdf"} or name in fields:
                raise ValueError("SELECTED_ANSWER_REQUEST_INVALID")
            payload = part.get_payload(decode=True)
            if type(payload) is not bytes:
                raise ValueError("SELECTED_ANSWER_REQUEST_INVALID")
            fields[name] = (part.get_filename(), part.get_content_type(), payload)
        if set(fields) != {"expected", "answer_pdf"}:
            raise ValueError("SELECTED_ANSWER_REQUEST_INVALID")
        expected_name, _, expected_bytes = fields["expected"]
        filename, pdf_type, pdf = fields["answer_pdf"]
        if expected_name is not None or len(expected_bytes) > 256 * 1024:
            raise ValueError("SELECTED_ANSWER_REQUEST_INVALID")
        if (type(filename) is not str or not filename or len(filename) > 255
                or filename in {".", ".."} or Path(filename).name != filename
                or "/" in filename or "\\" in filename
                or any(ord(char) < 32 for char in filename)
                or pdf_type != "application/pdf"):
            raise ValueError("SELECTED_ANSWER_REQUEST_INVALID")
        return strict_json(expected_bytes.decode("utf-8", "strict")), filename, pdf

    def _validate_selected_native_review_answer(self) -> None:
        """Present a non-admitting exact-current check of the selected bytes."""
        workflow = self.server.native_intake
        market = None
        filename = None
        try:
            query = parse_qs(urlsplit(self.path).query, strict_parsing=True)
            if set(query) != {"market"} or len(query["market"]) != 1:
                raise ValueError("SELECTED_ANSWER_REQUEST_INVALID")
            market = query["market"][0]
            expected, filename, pdf = self._selected_answer_form()
            if workflow is None:
                raise ReviewEvidenceError("REVIEW_CONTRACT_UNSUPPORTED")
            workflow.validate_selected_answer(market, expected, pdf)
        except ReviewEvidenceError as error:
            notice = self.server.retain_answer_notice(
                error.code, market, validation_only=True,
                selected_filename=filename,
            )
        except (OSError, UnicodeError, ValueError):
            notice = self.server.retain_answer_notice(
                "REVIEW_INTAKE_UNAVAILABLE", market,
                confirmed_no_import=False, validation_only=True,
                selected_filename=filename,
            )
        else:
            notice = self.server.retain_answer_notice(
                "ANSWER_BINDING_CURRENT", market,
                validation_only=True, validation_passed=True,
                selected_filename=filename,
            )
        self._swing_post_failed = True
        self._redirect("/swing/v1-review?answer_notice=" + notice)

    @staticmethod
    def _answer_acceptance_marker(workflow, market, expected):
        """Observe the exact acceptance pointer around an Answer POST, without recovery."""
        if workflow is None or market not in {"NSE", "MCX"} or type(expected) is not dict or not expected:
            return None
        first = next(iter(expected.values()))
        run = first.get("expected_run_identity") if type(first) is dict else None
        if type(run) is not str or not run:
            return None
        key = sha256(canonical(["NATIVE_REVIEW", market, run])).hexdigest()
        path = workflow.store.root / "acceptance-current" / (key + ".json")
        try:
            if path.is_symlink():
                return None
            with path.open("rb") as stream:
                payload = stream.read(4097)
            return payload if len(payload) <= 4096 else None
        except FileNotFoundError:
            return b""
        except OSError:
            return None

    def _native_intake_preview(self):
        try:
            workflow = self.server.native_intake
            query = parse_qs(urlsplit(self.path).query, strict_parsing=True)
            if set(query) != {"market", "instrument", "role", "selection"} or any(len(v) != 1 for v in query.values()):
                raise ValueError
            requirement = workflow._requirements(query["market"][0], (query["instrument"][0],))[0]
            selected = workflow._selection(requirement, query["role"][0])
            if selected is None or selected["selection_sha256"] != query["selection"][0]:
                raise ValueError
            payload = workflow.store.native_chart_bytes(selected)
        except (OSError, ValueError, TypeError, KeyError):
            self._text(HTTPStatus.NOT_FOUND, "Native chart preview unavailable.")
            return
        self._respond(HTTPStatus.OK, payload, selected["image"]["content_type"])

    def _native_intake_pdf(self):
        try:
            query = parse_qs(urlsplit(self.path).query, strict_parsing=True)
            if self.server.native_intake is None or set(query) != {"market", "publication"} or any(len(v) != 1 for v in query.values()):
                raise ValueError
            payload = self.server.native_intake.question_bytes(query["market"][0], query["publication"][0])
        except (OSError, ValueError, TypeError, KeyError):
            self._text(HTTPStatus.NOT_FOUND, "Question PDF unavailable.")
            return
        self._respond(HTTPStatus.OK, payload, "application/pdf")

    def _native_chart_query(
        self, *, preview: bool = False
    ) -> tuple[str, VisualEvidenceSubjectKind, str | None]:
        query = parse_qs(urlsplit(self.path).query, strict_parsing=True)
        expected = {"instrument", "subject"}
        if preview:
            expected.add("sha256")
        if set(query) != expected or any(len(query[item]) != 1 for item in expected):
            raise ValueError("NATIVE_CHART_BINDING_INVALID")
        digest = query["sha256"][0] if preview else None
        if digest is not None and re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError("NATIVE_CHART_REVISION_INVALID")
        return (
            query["instrument"][0],
            self._native_subject(query["subject"][0]),
            digest,
        )

    def _receive_native_chart(self) -> None:
        if self.server.native_intake is not None:
            self._native_intake_mutation("STAGE")
            return
        try:
            instrument, subject, _ = self._native_chart_query()
            content_length = int(self.headers.get("Content-Length", ""))
        except (TypeError, ValueError):
            self._text(HTTPStatus.BAD_REQUEST, "Native chart binding is invalid.")
            return
        if not 0 < content_length <= 25 * 1024 * 1024:
            self._text(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Chart size is invalid.")
            return
        payload = self.rfile.read(content_length)
        try:
            self.server.native_review.upload_chart(
                instrument=instrument,
                subject_kind=subject,
                content_type=self.headers.get("Content-Type", ""),
                original_bytes=payload,
            )
        except (ValueError, TradingViewEvidenceStoreError):
            self._text(HTTPStatus.BAD_REQUEST, "Native chart upload rejected.")
            return
        self._redirect("/swing/v1-review")

    def _mcx_context_slot_query(
        self, *, with_family: bool,
    ) -> tuple[McxContextSlot, McxContextFamily | None]:
        query = parse_qs(urlsplit(self.path).query, strict_parsing=True)
        expected = {"slot", "family"} if with_family else {"slot"}
        if self.server.mcx_supporting_context.publication_source is not None:
            expected.add("expected")
        if set(query) != expected or any(len(query[key]) != 1 for key in expected):
            raise ValueError("MCX_CONTEXT_BINDING_INVALID")
        return (
            McxContextSlot(query["slot"][0]),
            McxContextFamily(query["family"][0]) if with_family else None,
        )

    def _mcx_context_mutation(self, slot, operation, **values):
        workflow = self.server.mcx_supporting_context
        if workflow.publication_source is not None:
            query = parse_qs(urlsplit(self.path).query, strict_parsing=True)
            raw = query.get("expected", ())
            if len(raw) != 1 or len(raw[0]) > 8192:
                raise ReviewEvidenceError("REVIEW_PRECONDITION_INVALID")
            precondition = ReviewMutationPrecondition.create(strict_json(raw[0]))
            return workflow.mutate_intake(slot, operation, precondition, **values)
        # Explicitly injected historical workflow, never a successor fallback.
        if operation == "STAGE":
            return workflow.stage_image(slot=slot, **values)
        if operation == "REMOVE":
            return workflow.remove_image(slot=slot, **values)
        if operation == "GENERATE":
            return workflow.create_question_pack(slot)
        return workflow.upload_answer(slot)

    def _receive_mcx_context_image(self) -> None:
        try:
            slot, family = self._mcx_context_slot_query(with_family=True)
            length = int(self.headers.get("Content-Length", ""))
            if family is None or not 0 < length <= 25 * 1024 * 1024:
                raise ValueError
            self._mcx_context_mutation(
                slot, "STAGE", family=family,
                content_type=self.headers.get("Content-Type", ""),
                payload=self.rfile.read(length),
            )
        except ReviewEvidenceError as error:
            self._text(HTTPStatus.CONFLICT, error.code)
            return
        except (ValueError, PdfReviewTransportError):
            self._text(HTTPStatus.BAD_REQUEST, "MCX supporting-context image rejected.")
            return
        self._redirect("/swing/v1-review")

    def _remove_mcx_context_image(self) -> None:
        try:
            slot, family = self._mcx_context_slot_query(with_family=True)
            if family is None or self.headers.get("Content-Length") not in {None, "0"}:
                raise ValueError
            self._mcx_context_mutation(
                slot, "REMOVE", family=family,
            )
        except ReviewEvidenceError as error:
            self._text(HTTPStatus.CONFLICT, error.code)
            return
        except (ValueError, PdfReviewTransportError):
            self._text(HTTPStatus.BAD_REQUEST, "MCX supporting-context image removal rejected.")
            return
        self._redirect("/swing/v1-review")

    def _mcx_context_image_preview(self) -> None:
        try:
            query = parse_qs(urlsplit(self.path).query, strict_parsing=True)
            if set(query) != {"slot", "family", "sha256"} or any(
                len(query[key]) != 1 for key in query
            ):
                raise ValueError
            value, payload = self.server.mcx_supporting_context.current_image(
                slot=McxContextSlot(query["slot"][0]),
                family=McxContextFamily(query["family"][0]),
                image_sha256=query["sha256"][0],
            )
        except (OSError, ValueError, PdfReviewTransportError):
            self._text(HTTPStatus.NOT_FOUND, "MCX supporting-context image preview unavailable.")
            return
        self._respond(HTTPStatus.OK, payload, value.content_type)

    def _create_mcx_context_question_pack(self) -> None:
        try:
            slot, _ = self._mcx_context_slot_query(with_family=False)
            if self.headers.get("Content-Length") not in {None, "0"}:
                raise ValueError
            self._mcx_context_mutation(slot, "GENERATE")
        except ReviewEvidenceError as error:
            self._text(HTTPStatus.CONFLICT, error.code)
            return
        except (ValueError, PdfReviewTransportError):
            self._redirect("/swing/v1-review")
            return
        self._redirect("/swing/v1-review")

    def _upload_mcx_context_answer(self) -> None:
        try:
            slot, _ = self._mcx_context_slot_query(with_family=False)
            if self.headers.get("Content-Length") not in {None, "0"}:
                raise ValueError
            self._mcx_context_mutation(slot, "IMPORT")
        except ReviewEvidenceError as error:
            self._text(HTTPStatus.CONFLICT, error.code)
            return
        except (ValueError, PdfReviewTransportError):
            self._redirect("/swing/v1-review")
            return
        self._redirect("/swing/v1-review")

    def _remove_native_chart(self) -> None:
        if self.server.native_intake is not None:
            self._native_intake_mutation("REMOVE")
            return
        try:
            instrument, subject, _ = self._native_chart_query()
            self.server.native_review.remove_chart(
                instrument=instrument,
                subject_kind=subject,
            )
        except (ValueError, TradingViewEvidenceStoreError):
            self._text(HTTPStatus.BAD_REQUEST, "Native chart removal rejected.")
            return
        self._redirect("/swing/v1-review")

    def _native_chart_preview(self) -> None:
        if self.server.native_intake is not None:
            self._native_intake_preview()
            return
        try:
            instrument, subject, digest = self._native_chart_query(
                preview=True
            )
            revision, payload = self.server.native_review.active_chart(
                instrument=instrument,
                subject_kind=subject,
                sha256=digest or "",
            )
        except (ValueError, TradingViewEvidenceStoreError, OSError):
            self._text(HTTPStatus.NOT_FOUND, "Native chart preview unavailable.")
            return
        self._respond(HTTPStatus.OK, payload, revision.content_type)

    def _analyze_native_review(self) -> None:
        try:
            query = parse_qs(urlsplit(self.path).query, strict_parsing=True)
            instruments = query.get("instrument", ())
            if set(query) != {"instrument"} or len(instruments) != 1:
                raise ValueError
        except (
            TypeError,
            ValueError,
        ):
            self._text(HTTPStatus.BAD_REQUEST, "Native analysis request rejected.")
            return
        instrument = instruments[0]
        _LOG.info("native_review endpoint_received action=individual instrument=%s", instrument)
        try:
            binding_valid = self.server.native_review.analysis_binding_valid(instrument)
        except (TradingViewEvidenceStoreError, TypeError, ValueError):
            self._text(HTTPStatus.BAD_REQUEST, "Native analysis request rejected.")
            return
        preflight_reason = (
            "CREDENTIAL UNAVAILABLE"
            if self.server.chart_analyst_credentials.status()
            is not ChartAnalystConnectionStatus.CONNECTED
            else "ANALYSIS PROVIDER UNAVAILABLE"
            if self.server.chart_analyst_activation.status()
            is not ChartAnalystV2ActivationStatus.ENABLED
            else "CHART BINDING INVALID"
            if not binding_valid
            else ""
        )
        if preflight_reason:
            self.server.native_review.record_analysis_failure(
                instrument, preflight_reason
            )
            _LOG.warning(
                "native_review preflight_failed instrument=%s reason=%s",
                instrument,
                preflight_reason.replace(" ", "_"),
            )
            self._redirect("/swing/v1-review")
            return
        try:
            self.server.native_review.analyze(instrument)
        except Exception as error:
            _LOG.warning(
                "native_review endpoint_failed action=individual instrument=%s exception=%s",
                instrument,
                type(error).__name__,
            )
            self._redirect("/swing/v1-review")
            return
        _LOG.info("native_review endpoint_returned action=individual instrument=%s", instrument)
        self._redirect("/swing/v1-review")

    def _analyze_all_native_reviews(self) -> None:
        if urlsplit(self.path).query:
            self._text(HTTPStatus.BAD_REQUEST, "Native analysis request rejected.")
            return
        _LOG.info("native_review endpoint_received action=all")
        preflight_reason = (
            "CREDENTIAL UNAVAILABLE"
            if self.server.chart_analyst_credentials.status()
            is not ChartAnalystConnectionStatus.CONNECTED
            else "ANALYSIS PROVIDER UNAVAILABLE"
            if self.server.chart_analyst_activation.status()
            is not ChartAnalystV2ActivationStatus.ENABLED
            else ""
        )
        if preflight_reason:
            for requirement in self.server.native_review.snapshot().requirements:
                if self.server.native_review.analysis_binding_valid(
                    requirement.canonical_instrument
                ):
                    self.server.native_review.record_analysis_failure(
                        requirement.canonical_instrument,
                        preflight_reason,
                    )
            _LOG.warning(
                "native_review preflight_failed action=all reason=%s",
                preflight_reason.replace(" ", "_"),
            )
            self._redirect("/swing/v1-review")
            return
        try:
            self.server.native_review.analyze_all()
        except Exception as error:
            _LOG.warning(
                "native_review endpoint_failed action=all exception=%s",
                type(error).__name__,
            )
            self._redirect("/swing/v1-review")
            return
        _LOG.info("native_review endpoint_returned action=all")
        self._redirect("/swing/v1-review")

    def _generate_native_review_pack(self) -> None:
        if self.server.native_intake is not None:
            self._native_intake_mutation("GENERATE")
            return
        query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
        if set(query) - {"instrument"} or any(len(value) != 1 for value in query.values()):
            self._text(HTTPStatus.BAD_REQUEST, "Review Pack request rejected.")
            return
        instrument = query.get("instrument", [None])[0]
        if instrument == "":
            self._text(HTTPStatus.BAD_REQUEST, "Review Pack request rejected.")
            return
        try:
            if self.server.native_review_version() == "V3":
                facts = self.server.native_review_facts
                if facts is None:
                    raise PdfReviewTransportError(
                        "VISUAL_V3_MACHINE_SNAPSHOT_UNAVAILABLE"
                    )
                self.server.visual_v3_live.generate(
                    self.server.native_review.snapshot(),
                    facts,
                    self.server.native_review.original_chart_bytes,
                    instrument,
                )
            else:
                self.server.native_review.generate_review_pack(instrument)
        except (PdfReviewTransportError, TradingViewEvidenceStoreError, OSError):
            self._redirect("/swing/v1-review")
            return
        self._redirect("/swing/v1-review")

    def _refresh_native_review(self) -> None:
        if urlsplit(self.path).query:
            self._text(HTTPStatus.BAD_REQUEST, "Review refresh rejected.")
            return
        native_run = self.server.application.native_discovery_run()
        facts = self.server.application.mtf_fact_snapshot()
        if native_run is None or facts is None:
            self.server.native_review.record_refresh_unavailable()
            self._redirect("/swing/v1-review")
            return
        try:
            self.server.native_review.refresh(native_run, facts)
        except ValueError:
            self.server.native_review.record_refresh_unavailable()
            self._redirect("/swing/v1-review")
            return
        self.server.native_review_run = native_run
        self.server.native_review_facts = facts
        self._redirect("/swing/v1-review")

    def _upload_native_review_answer(self) -> None:
        if self.server.native_intake is not None:
            self._native_intake_mutation("IMPORT")
            return
        if urlsplit(self.path).query:
            self._redirect_answer_rejection(None, confirmed_no_import=False)
            return
        try:
            if self.server.native_review_version() == "V3":
                facts = self.server.native_review_facts
                if facts is None:
                    raise PdfReviewTransportError(
                        "VISUAL_V3_MACHINE_SNAPSHOT_UNAVAILABLE"
                    )
                self.server.visual_v3_live.upload(
                    self.server.native_review.snapshot(),
                    facts,
                    self.server.native_review.original_chart_bytes,
                )
                self.server.trade_window.restore(
                    self.server.visual_v3.completed_snapshot()
                )
                self.server.progression_snapshot()
                self.server.refresh_swing_projection_revision()
            else:
                self.server.native_review.upload_review_answer()
        except (
            PdfReviewTransportError,
            TradingViewEvidenceStoreError,
            OSError,
            TypeError,
            ValueError,
        ) as error:
            self._redirect_answer_rejection(str(error))
            return
        self._redirect("/swing/v1-review")

    def _analyze_v1_charts(self) -> None:
        if urlsplit(self.path).query:
            self._text(HTTPStatus.BAD_REQUEST, "Chart analysis binding is invalid.")
            return
        if self.server.v1_review.uses_chart_analyst_v2:
            failure = self._chart_analyst_v2_preflight_failure()
            if failure is not None:
                self.server.v1_review.record_batch_preflight_failure(failure)
                self._redirect("/swing/v1-review")
                return
            self.server.v1_review.clear_batch_preflight_failure()
        try:
            self.server.v1_review.analyze_all_chart_context()
            self.server.step32_workflow.synchronize_review(
                self.server.v1_review
            )
        except (ValueError, TradingViewEvidenceStoreError):
            self._text(
                HTTPStatus.CONFLICT,
                "Chart analysis is not available for this evidence set.",
            )
            return
        self._redirect("/swing/v1-review")

    def _analyze_one_v1_chart(self) -> None:
        try:
            query = parse_qs(urlsplit(self.path).query, strict_parsing=True)
        except ValueError:
            query = {}
        instrument_values = query.get("instrument", ())
        if set(query) != {"instrument"} or len(instrument_values) != 1:
            self._text(HTTPStatus.BAD_REQUEST, "Chart validation binding is invalid.")
            return
        instrument = instrument_values[0]
        if not self.server.v1_review.uses_chart_analyst_v2:
            self._text(HTTPStatus.CONFLICT, "Chart Analyst V2 is unavailable.")
            return
        failure = self._chart_analyst_v2_preflight_failure(instrument)
        if failure is not None:
            self.server.v1_review.record_batch_preflight_failure(failure)
            self._redirect("/swing/v1-review")
            return
        self.server.v1_review.clear_batch_preflight_failure()
        try:
            self.server.v1_review.analyze_chart_context(instrument, force=True)
            self.server.step32_workflow.synchronize_review(
                self.server.v1_review
            )
        except (ValueError, TradingViewEvidenceStoreError):
            self._text(
                HTTPStatus.CONFLICT,
                "Chart validation is not available for this evidence set.",
            )
            return
        self._redirect("/swing/v1-review")

    def _chart_analyst_v2_preflight_failure(
        self,
        instrument: str | None = None,
    ) -> V1BatchPreflightFailure | None:
        if (
            self.server.chart_analyst_credentials.status()
            is not ChartAnalystConnectionStatus.CONNECTED
        ):
            return V1BatchPreflightFailure.OPENAI_NOT_CONNECTED
        if (
            self.server.chart_analyst_activation.status()
            is not ChartAnalystV2ActivationStatus.ENABLED
        ):
            return V1BatchPreflightFailure.CHART_ANALYST_V2_DISABLED
        if not self.server.v1_review.chart_analyst_v2_model_configured:
            return V1BatchPreflightFailure.MODEL_NOT_SUPPORTED
        if not self.server.v1_review.chart_analyst_v2_question_set_available:
            return V1BatchPreflightFailure.QUESTION_SET_UNAVAILABLE
        binding_valid = (
            self.server.v1_review.chart_analyst_v2_run_binding_valid()
            if instrument is None
            else self.server.v1_review.chart_analyst_v2_instrument_binding_valid(
                instrument
            )
        )
        if not binding_valid:
            return V1BatchPreflightFailure.RUN_BINDING_INVALID
        return None

    def _mcx_v1_workspace(self) -> None:
        composition = getattr(self.server, "mcx_v1_composition", None)
        if composition is None:
            self._text(HTTPStatus.CONFLICT, "MCX_STEP31_NOT_COMMISSIONED")
            return
        try:
            from kronos.browser.views import render_mcx_v1_workspace
            if urlsplit(self.path).query:
                raise ValueError("MCX_V1_QUERY_INVALID")
            projection = composition.projection()
            snapshots = composition.retained_snapshots()
            self._html(render_mcx_v1_workspace(projection, snapshots))
        except (OSError, ValueError):
            self._text(HTTPStatus.CONFLICT, "MCX V1 workspace unavailable.")

    def _mcx_observation_receipt(self) -> None:
        try:
            query = parse_qs(urlsplit(self.path).query, strict_parsing=True,
                             keep_blank_values=True)
            if set(query) != {'operation'} or len(query['operation']) != 1:
                raise ValueError('MCX_OBSERVATION_QUERY_INVALID')
            composition = getattr(self.server, 'mcx_v1_composition', None)
            if composition is None:
                raise ValueError('MCX_OBSERVATION_OWNER_UNAVAILABLE')
            self._json(composition.observation.read(query['operation'][0]))
        except (OSError, ValueError, KeyError, TypeError):
            self._text(HTTPStatus.CONFLICT, 'MCX observation receipt unavailable or incomplete.')

    def _mcx_observe(self) -> None:
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if (urlsplit(self.path).query or not 0 < length <= 1024
                    or self.headers.get('Content-Type') != 'application/x-www-form-urlencoded'):
                raise ValueError('MCX_OBSERVATION_FORM_INVALID')
            fields = parse_qs(self.rfile.read(length).decode('ascii'),
                              strict_parsing=True, keep_blank_values=True)
            expected = {'operation', 'run', 'family', 'selection_sha256', 'publication_sha256'}
            if set(fields) != expected or any(len(x) != 1 or not x[0] for x in fields.values()):
                raise ValueError('MCX_OBSERVATION_FORM_INVALID')
            composition = getattr(self.server, 'mcx_v1_composition', None)
            if composition is None:
                raise ValueError('MCX_OBSERVATION_OWNER_UNAVAILABLE')
            value = {key: values[0] for key, values in fields.items()}
            value['family'] = McxFamily(value['family'])
            self._json(composition.observation.observe(**value))
        except (OSError, UnicodeError, ValueError, KeyError, TypeError):
            self._text(HTTPStatus.CONFLICT, 'MCX observation rejected; inspect its retained receipt before any further action.')

    def _mcx_v1_composition_action(self, path: str) -> None:
        composition = getattr(self.server, "mcx_v1_composition", None)
        if composition is None:
            self._text(HTTPStatus.CONFLICT, "MCX_STEP31_NOT_COMMISSIONED")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if (urlsplit(self.path).query or not 0 < length <= 1024
                    or self.headers.get("Content-Type") != "application/x-www-form-urlencoded"):
                raise ValueError("MCX_V1_FORM_INVALID")
            fields = parse_qs(self.rfile.read(length).decode("ascii"),
                              strict_parsing=True, keep_blank_values=True)
            expected = ({"snapshot", "master_sha256", "publication_sha256"}
                        if path.endswith("/reserve") else {"run", "family", "handoff_sha256"})
            if set(fields) != expected or any(len(values) != 1 or not values[0]
                                             for values in fields.values()):
                raise ValueError("MCX_V1_FORM_INVALID")
            value = {key: values[0] for key, values in fields.items()}
            if path.endswith("/reserve"):
                composition.reserve(value["snapshot"], value["master_sha256"],
                                    value["publication_sha256"])
            else:
                composition.prepare_plan(value["run"], McxFamily(value["family"]),
                                         value["handoff_sha256"])
        except (OSError, UnicodeError, ValueError, KeyError, TypeError):
            self._text(HTTPStatus.CONFLICT, "MCX V1 operation rejected.")
            return
        self._redirect("/swing/mcx-v1")

    def _mcx_v1_record_action(self, path: str) -> None:
        """Strict loopback Sponsor record routes; no broker order operation."""
        governance = getattr(self.server, "connection_governance", None)
        if governance is not None and governance.maintenance_active:
            self._text(HTTPStatus.SERVICE_UNAVAILABLE, "Controlled maintenance is active.")
            return
        control = getattr(self.server, "mcx_v1_control", None)
        if control is None:
            self._text(HTTPStatus.CONFLICT, "MCX_STEP31_NOT_COMMISSIONED")
            return
        if urlsplit(self.path).query:
            self._text(HTTPStatus.BAD_REQUEST, "MCX V1 request rejected.")
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
            if (self.headers.get("Content-Type", "").split(";", 1)[0].lower()
                    != "application/x-www-form-urlencoded"
                    or not 0 < length <= 1_500_000):
                raise ValueError("MCX_V1_FORM_INVALID")
            fields = parse_qs(self.rfile.read(length).decode("utf-8"),
                              keep_blank_values=True, strict_parsing=True)
            common = {"run", "family", "plan", "plan_sha256"}
            exit_common = {"position", "position_sha256"}
            fill = {"contract", "expiry", "lots", "fill_price", "fill_at",
                    "broker_evidence_id", "broker_evidence_sha256",
                    "broker_evidence_b64"}
            expected = {
                "/swing/mcx-v1/paper": common,
                "/swing/mcx-v1/live": common | fill,
                "/swing/mcx-v1/paper-exit": exit_common,
                "/swing/mcx-v1/live-exit": exit_common | fill | {"reason"},
            }[path]
            if set(fields) != expected or any(
                    len(values) != 1 or not values[0] for values in fields.values()):
                raise ValueError("MCX_V1_FORM_INVALID")
            value = {name: values[0] for name, values in fields.items()}
            if "lots" in value and re.fullmatch(r"[1-9][0-9]*", value["lots"]) is None:
                raise ValueError("MCX_V1_LOTS_INVALID")
            if "broker_evidence_b64" in value and len(value["broker_evidence_b64"]) > 1_400_000:
                raise ValueError("MCX_V1_EVIDENCE_TOO_LARGE")
            now = datetime.now(UTC)
            if path in {"/swing/mcx-v1/paper", "/swing/mcx-v1/live"}:
                family = McxFamily(value["family"])
                if path == "/swing/mcx-v1/paper":
                    control.admit_paper(
                        run=value["run"], family=family,
                        plan_id=value["plan"],
                        plan_sha256=value["plan_sha256"], decided_at=now)
                else:
                    evidence = base64.b64decode(
                        value["broker_evidence_b64"], validate=True)
                    control.record_manual_live_entry(
                        run=value["run"], family=family,
                        plan_id=value["plan"],
                        plan_sha256=value["plan_sha256"],
                        contract=value["contract"], expiry=value["expiry"],
                        lots=int(value["lots"]),
                        fill_price=Decimal(value["fill_price"]),
                        fill_at=datetime.fromisoformat(value["fill_at"]),
                        evidence_id=value["broker_evidence_id"],
                        evidence_sha256=value["broker_evidence_sha256"],
                        evidence_bytes=evidence, attested_at=now)
            elif path == "/swing/mcx-v1/paper-exit":
                control.paper_exit(value["position"], value["position_sha256"])
            else:
                evidence = base64.b64decode(
                    value["broker_evidence_b64"], validate=True)
                control.record_manual_live_exit(
                    position_id=value["position"],
                    expected_hash=value["position_sha256"],
                    contract=value["contract"], expiry=value["expiry"],
                    lots=int(value["lots"]),
                    fill_price=Decimal(value["fill_price"]),
                    fill_at=datetime.fromisoformat(value["fill_at"]),
                    evidence_id=value["broker_evidence_id"],
                    evidence_sha256=value["broker_evidence_sha256"],
                    evidence_bytes=evidence,
                    reason=TradeExitReason(value["reason"]), attested_at=now)
        except (UnicodeDecodeError, ValueError, TypeError, OverflowError,
                InvalidOperation,
                binascii.Error, KeyError):
            self._text(HTTPStatus.CONFLICT, "MCX V1 request rejected.")
            return
        self._redirect("/swing/mcx-v1" if getattr(self.server, "mcx_v1_composition", None)
                       is not None else "/swing/opportunities")

    def _mcx_contract_offer(self) -> None:
        workflow = self.server.mcx_slice3
        if workflow is None:
            self._text(HTTPStatus.CONFLICT, "MCX_STEP31_NOT_COMMISSIONED")
            return
        try:
            query = parse_qs(urlsplit(self.path).query, strict_parsing=True)
            if set(query) != {"family"} or len(query["family"]) != 1:
                raise ValueError("MCX_OFFER_QUERY_INVALID")
            family = McxFamily(query["family"][0])
            reserved = True
            if getattr(self.server, 'mcx_v1_composition', None) is not None:
                workflow._current()
                reserved = workflow.publication.status()['latest_attempt']['state'] == 'RUNNING'
                offer = workflow.offers[family]
            else:
                offer = workflow.offer(family)
        except (OSError, ValueError, KeyError):
            self._text(HTTPStatus.CONFLICT, "MCX_CONTRACT_OFFER_UNAVAILABLE")
            return
        forms = []
        displayed_at = workflow.clock() if callable(getattr(workflow, "clock", None)) else offer.observed_at
        if offer.selection_policy == "MCX_V1_ADVISORY_SELECTION":
            # Retained offers stay immutable. A later GET can display expiry
            # without persisting a transition or silently substituting a future.
            for symbol, reasons in offer.withheld_contracts:
                forms.append(f'<p>WITHHELD: {escape(symbol)}; '
                             f'{escape(", ".join(reasons))}</p>')
            for role, fact in ((McxSelectionRole.NEAR, offer.near),
                               (McxSelectionRole.NEXT_ELIGIBLE,
                                offer.next_eligible)):
                if fact is None:
                    continue
                reasons = fact.v1_reasons(displayed_at)
                forms.append(
                    f'<p>{escape(role.value)}: '
                    f'{escape(fact.instrument.trading_symbol)} '
                    f'({fact.instrument.expiry.isoformat()}); '
                    f'authenticated master acquired '
                    f'{escape(fact.snapshot_acquired_at.isoformat() if fact.snapshot_acquired_at else "UNKNOWN")}; '
                    f'snapshot {escape(fact.provider_snapshot_identity or "UNKNOWN")}; '
                    f'{escape(", ".join(reasons) if reasons else "listed; broker restrictions UNKNOWN")}'
                    '</p>')
        for role in offer.selectable(displayed_at) if reserved else ():
            chosen = offer.near if role is McxSelectionRole.NEAR else offer.next_eligible
            if chosen is None:
                continue
            forms.append(
                '<form method="post" action="/swing/mcx-contract-choice">'
                f'<input type="hidden" name="run" value="{escape(offer.run_identity)}">'
                f'<input type="hidden" name="family" value="{escape(family.value)}">'
                f'<input type="hidden" name="role" value="{escape(role.value)}">'
                f'<input type="hidden" name="offer_sha256" value="{offer.offer_sha256}">'
                f'<button type="submit">Select {escape(role.value)} '
                f'{escape(chosen.instrument.trading_symbol)} '
                f'({chosen.instrument.expiry.isoformat()})</button></form>'
            )
        # Only an isolated composition installs this owner. The production
        # default remains the server-side commissioning hold.
        try:
            handoff = workflow.process_handoff() if reserved else None
        except (OSError, ValueError, KeyError):
            handoff = None
        if handoff is not None:
            forms.append(
                '<form method="post" action="/swing/mcx-reserved-analysis">'
                f'<input type="hidden" name="run" value="{escape(offer.run_identity)}">'
                f'<input type="hidden" name="handoff_sha256" value="{handoff.integrity_sha256}">'
                '<button type="submit">Start reserved analysis</button></form>'
            )
        self._html(
            '<!doctype html><html><head><title>MCX contract choice</title></head><body>'
            f'<h1>{escape(family.value)} contract choice</h1>'
            f'<p>{"Reserved" if reserved else "Published"} run {escape(offer.run_identity)}; '
            f'{offer.days_to_verified_expiry} calendar days to '
            f'{"listed Provider" if offer.selection_policy == "MCX_V1_ADVISORY_SELECTION" else "verified"} near expiry.</p>'
            + "".join(forms) +
            '<p>Choice precedes contract-specific candles and Review. '
            'MCX Step-31 remains uncommissioned.</p></body></html>'
        )

    def _mcx_contract_choice(self) -> None:
        workflow = self.server.mcx_slice3
        if workflow is None:
            self._text(HTTPStatus.CONFLICT, "MCX_STEP31_NOT_COMMISSIONED")
            return
        try:
            if self.headers.get("Content-Type") != "application/x-www-form-urlencoded":
                raise ValueError("MCX_CHOICE_CONTENT_TYPE_INVALID")
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 1024:
                raise ValueError("MCX_CHOICE_BODY_INVALID")
            fields = parse_qs(self.rfile.read(size).decode("ascii"),
                              strict_parsing=True, keep_blank_values=True)
            if set(fields) != {"run", "family", "role", "offer_sha256"} or any(
                len(values) != 1 for values in fields.values()
            ):
                raise ValueError("MCX_CHOICE_FORM_INVALID")
            if fields["run"][0] != workflow.run_identity:
                raise ValueError("MCX_CHOICE_RUN_STALE")
            family = McxFamily(fields["family"][0])
            role = McxSelectionRole(fields["role"][0])
            workflow.choose(family, role, fields["offer_sha256"][0],
                            recorded_at=workflow.clock())
        except (OSError, UnicodeError, ValueError, KeyError):
            self._text(HTTPStatus.CONFLICT, "MCX_CONTRACT_CHOICE_REJECTED")
            return
        self._redirect("/swing/mcx-contract-offer?" + urlencode({"family": family.value}))

    def _mcx_reserved_analysis(self) -> None:
        workflow = self.server.mcx_slice3
        if workflow is None:
            self._text(HTTPStatus.CONFLICT, "MCX_STEP31_NOT_COMMISSIONED")
            return
        try:
            if self.headers.get("Content-Type") != "application/x-www-form-urlencoded":
                raise ValueError("MCX_ANALYSIS_CONTENT_TYPE_INVALID")
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 512:
                raise ValueError("MCX_ANALYSIS_BODY_INVALID")
            fields = parse_qs(self.rfile.read(size).decode("ascii"),
                              strict_parsing=True, keep_blank_values=True)
            if set(fields) != {"run", "handoff_sha256"} or any(
                len(values) != 1 for values in fields.values()
            ):
                raise ValueError("MCX_ANALYSIS_FORM_INVALID")
            handoff = workflow.process_handoff()
            if (fields["run"][0] != workflow.run_identity
                    or fields["handoff_sha256"][0] != handoff.integrity_sha256):
                raise ValueError("MCX_ANALYSIS_HANDOFF_STALE")
            if not self.server.application.run_analysis(workflow):
                raise ValueError("MCX_ANALYSIS_ADMISSION_UNAVAILABLE")
        except (OSError, UnicodeError, ValueError, KeyError):
            self._text(HTTPStatus.CONFLICT, "MCX_RESERVED_ANALYSIS_REJECTED")
            return
        self._redirect("/swing/opportunities")

    def _same_origin(self) -> bool:
        if not self._exact_loopback_host():
            return False
        authority = f"{_LOOPBACK_HOST}:{self.server.server_port}"
        origin = self.headers.get("Origin")
        return origin == f"http://{authority}"

    def _exact_loopback_host(self) -> bool:
        return self.headers.get("Host") == (
            f"{_LOOPBACK_HOST}:{self.server.server_port}"
        )

    def _audit_rejected_connection(self) -> bool:
        # Even a rejected Provider request has a durable audit final write.
        # It must either own a ticket or leave no governed record after fence.
        ticket = self.server.maintenance_admission.admit("PROVIDER_CALLBACK")
        if ticket is None:
            self._text(HTTPStatus.SERVICE_UNAVAILABLE, "Provider connection not admitted.")
            return False
        governance = self.server.connection_governance
        try:
            if governance is not None:
                request = governance.request(received_at=self._connection_received_at)
                governance.result(request, "admission", "REJECTED")
        except (OSError, ValueError):
            self._text(HTTPStatus.SERVICE_UNAVAILABLE, "Provider connection not admitted.")
            return False
        finally:
            ticket.release()
        return True

    def _connection_action_reference(self) -> str | None:
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 <= size <= 256:
                raise ValueError
            if size == 0:
                return None
            fields = parse_qs(self.rfile.read(size).decode("ascii"), strict_parsing=True)
            if set(fields) != {"action_reference"} or len(fields["action_reference"]) != 1:
                raise ValueError
            return fields["action_reference"][0]
        except (UnicodeError, ValueError):
            return None

    def _swing_page_unavailable(self, error):
        reason = NativeReviewIntakeWorkflow._reason(error, "REVIEW_BINDING_UNAVAILABLE")
        intake = self.server.native_intake
        if intake is not None and reason == "SWING_PUBLICATION_BUNDLE_INVALID":
            # Preserve the existing unavailable-workspace presentation. No
            # selected evidence, historical projection or intake control is used.
            snapshot, native, _, publication = self.server.application.opportunities_bundle_projection()
            publication = deepcopy(publication)
            unavailable = intake.unavailable(error)
            if urlsplit(self.path).path == "/swing/opportunities" and native is not None:
                body = render_opportunities(snapshot, native, native_intake=unavailable)
            else:
                body = render_v1_review(snapshot, self.server.v1_review.snapshot(), native_intake=unavailable)
            _, current, _, status = self.server.application.opportunities_bundle_projection()
            if current is native and status == publication:
                self._html(body)
                return
            reason = "REVIEW_BINDING_STALE"
        self._text(HTTPStatus.CONFLICT, "Swing page unavailable. Reason: " + reason)

    def _html(self, body: str) -> None:
        self._respond(HTTPStatus.OK, body.encode("utf-8"), "text/html; charset=utf-8")

    def _png_asset(self, path: Path) -> None:
        try:
            payload = path.read_bytes()
        except OSError:
            self._text(HTTPStatus.NOT_FOUND, "Brand asset not found.")
            return
        self._respond(HTTPStatus.OK, payload, "image/png")

    def _json(
        self, payload: dict[str, object], *, status: HTTPStatus = HTTPStatus.OK,
    ) -> None:
        self._respond(
            status,
            json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def _text(self, status: HTTPStatus, body: str) -> None:
        if status >= HTTPStatus.BAD_REQUEST:
            self._swing_post_failed = True
        self._respond(status, body.encode("utf-8"), "text/plain; charset=utf-8")

    def _redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self._security_headers()
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _respond(
        self,
        status: HTTPStatus,
        body: bytes,
        content_type: str,
        *,
        filename: str | None = None,
    ) -> None:
        if content_type.startswith("text/html"):
            from kronos.browser.runtime_state import decorate_html
            body = decorate_html(body.decode("utf-8"), self.server.connection_governance).encode("utf-8")
        self.send_response(status)
        self._security_headers()
        self.send_header("Content-Type", content_type)
        if filename is not None:
            if re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", filename) is None:
                raise ValueError("DOWNLOAD_FILENAME_INVALID")
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _security_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'unsafe-inline'; "
            "script-src 'unsafe-inline'; img-src 'self' data:; "
            "frame-ancestors 'none'; form-action 'self' "
            "https://kite.zerodha.com/connect/login "
            "http://127.0.0.1:8765/kite/callback",
        )
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")

    def log_message(self, _format: str, *_args: object) -> None:
        return


def create_browser_server(
    application: SwingOpportunitiesApplication,
    *,
    port: int = 8947,
    v1_review: SwingV1ReviewWorkflow | None = None,
    chart_analyst_credentials: OpenAIChartAnalystCredentialService | None = None,
    chart_analyst_activation: ChartAnalystV2ActivationService | None = None,
    restart_control: BrowserBackendRestartControl | None = None,
    intraday_workstation: object | None = None,
    step32_workflow: SwingV1BrowserOperationalization | None = None,
    native_review: NativeReviewWorkflow | None = None,
    product_routes: ProductBrowserRoutes | None = None,
    progression_watches: SwingProgressionWatchWorkflow | None = None,
    visual_v3: SwingVisualV3ReviewCycle | None = None,
    visual_v3_live: SwingVisualV3LiveWorkflow | None = None,
    trade_window: SwingTradeWindowWorkflow | None = None,
    telegram: TelegramConfigurationService | None = None,
    ux10_notifications: SwingUx10NotificationService | None = None,
    refresh_reminders: SwingK5RefreshReminderWorkflow | None = None,
    notification_centre: SponsorNotificationCentre | None = None,
    provider_instrument_master_operation: (
        ProviderInstrumentMasterOperationalComposition | None
    ) = None,
    intraday_discovery_control: IntradayDiscoveryOperationalControl | None = None,
    intraday_historical_control: (
        IntradayHistoricalQualificationOperationalControl | None
    ) = None,
    mcx_supporting_context: McxSupportingContextWorkflow | None = None,
    intraday_wo09_notification_sources: (
        Callable[[], tuple[Wo09NotificationSource, ...]] | None
    ) = None,
    provider_login_navigation: object | None = None,
    bulk_import_root: Path | None = None,
    mcx_slice3: SwingMcxIntegratedWorkflow | None = None,
    mcx_v1_control: SwingMcxV1OperationalControl | None = None,
    native_intake: NativeReviewIntakeWorkflow | None = None,
    mcx_v1_composition_factory: Callable | None = None,
    swing_research_control: SwingResearchControl | None = None,
) -> KronosBrowserServer:
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("BROWSER_SERVER_PORT_INVALID")
    return KronosBrowserServer(
        (_LOOPBACK_HOST, port),
        application,
        v1_review,
        chart_analyst_credentials,
        chart_analyst_activation,
        restart_control,
        intraday_workstation,
        step32_workflow,
        native_review,
        product_routes,
        progression_watches,
        visual_v3,
        visual_v3_live,
        trade_window,
        telegram,
        ux10_notifications,
        refresh_reminders,
        notification_centre,
        provider_instrument_master_operation,
        intraday_discovery_control,
        intraday_historical_control,
        mcx_supporting_context,
        intraday_wo09_notification_sources,
        provider_login_navigation,
        bulk_import_root,
        mcx_slice3,
        mcx_v1_control,
        native_intake,
        mcx_v1_composition_factory,
        swing_research_control,
    )


def _openai_chart_analyst_security(
    config: OpenAIChartAnalystV2Config,
) -> tuple[UrllibOpenAIResponsesTransport, OpenAIChartAnalystCredentialService]:
    source = AppleKeychainApiKeySource(
        provider=OPENAI_CHART_ANALYST_PROVIDER,
        runner=run_security_framework_subprocess,
    )
    transport = UrllibOpenAIResponsesTransport(
        credential_source=source,
        credential_ref=OPENAI_CHART_ANALYST_CREDENTIAL_REF,
    )
    credentials = OpenAIChartAnalystCredentialService(
        provisioner=AppleKeychainCredentialProvisioner(
            provider=OPENAI_CHART_ANALYST_PROVIDER,
            runner=run_security_framework_provisioning,
        ),
        presence_probe=AppleKeychainCredentialPresenceProbe(
            provider=OPENAI_CHART_ANALYST_PROVIDER,
            runner=run_security_presence_subprocess,
        ),
        capability_tester=OpenAIChartAnalystCapabilityProbe(
            transport=transport,
            model_identity=config.model_identity,
        ),
    )
    return transport, credentials


def _safe_trade_plan_construction_failure(
    stage: TradePlanConstructionStage,
    raw_code: str,
) -> tuple[str, str]:
    code = (
        raw_code
        if raw_code in TRADE_PLAN_CONSTRUCTION_SAFE_FAILURES
        else "TRADE_PLAN_CONSTRUCTION_UNAVAILABLE"
    )
    if stage is TradePlanConstructionStage.PROVIDER_CAPABILITY:
        code = "KITE_READ_ONLY_CAPABILITY_UNAVAILABLE"
    return code, TRADE_PLAN_CONSTRUCTION_SAFE_FAILURES[code]


def _telegram_security() -> TelegramConfigurationService:
    provisioner = AppleKeychainCredentialProvisioner(
        provider=TELEGRAM_PROVIDER,
        runner=run_security_framework_provisioning,
    )
    presence = AppleKeychainCredentialPresenceProbe(
        provider=TELEGRAM_PROVIDER,
        runner=run_security_presence_subprocess,
    )
    return TelegramConfigurationService(
        provisioner=provisioner,
        presence_probe=presence,
        remover=AppleKeychainCredentialRemover(
            provider=TELEGRAM_PROVIDER,
            runner=run_security_framework_removal,
        ),
        delivery_control=TelegramDeliveryControlStore(),
        token_source=AppleKeychainCredentialSource(
            provider=TELEGRAM_PROVIDER,
            runner=run_security_framework_subprocess,
        ),
        chat_source=AppleKeychainApiKeySource(
            provider=TELEGRAM_PROVIDER,
            runner=run_security_framework_subprocess,
        ),
        transport=UrllibTelegramBotApiTransport(),
    )


__all__ = ["KronosBrowserServer", "create_browser_server"]
