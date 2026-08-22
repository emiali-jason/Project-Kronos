"""Loopback-only HTTP transport for KRONOS Browser V1."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import re
from threading import Lock, Thread
from urllib.parse import parse_qs, unquote, urlsplit

from kronos.application.swing_opportunities import SwingOpportunitiesApplication
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
from kronos.application.swing_notifications import project_swing_notification_workspace
from kronos.application.swing_ux10 import (
    SwingUx10NotificationService,
    Ux10NotificationStore,
)
from kronos.application.shared_monitoring import SharedSwingMonitoringHub
from kronos.application.swing_v1_browser import SwingV1BrowserOperationalization
from kronos.application.swing_v1_review import (
    SwingV1ReviewWorkflow,
    V1BatchPreflightFailure,
)
from kronos.application.swing_native_review import (
    NativeReviewWorkflow,
    project_native_analysis_details,
)
from kronos.application.swing_visual_v3 import SwingVisualV3ReviewCycle
from kronos.application.swing_visual_v3_live import SwingVisualV3LiveWorkflow
from kronos.application.swing_trade_window import SwingTradeWindowWorkflow
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
    render_trade_candidates,
    render_v1_review,
)
from kronos.browser.dashboard import project_sponsor_dashboard
from kronos.browser.v1_analysis_status import analysis_status_payload
from kronos.browser.swing_readiness_presentation import present_native_readiness
from kronos.browser.swing_v3_presentation import present_visual_v3_review
from kronos.browser.restart_control import BrowserBackendRestartControl
from kronos.browser.product_routes import (
    BrowserGetRequest,
    ProductBrowserRoutes,
    default_product_browser_routes,
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
    LocalKr380V2Store,
    LocalObjectiveModelV1Store,
    LocalPortfolioStateV1Store,
    LocalRiskPermissionV1Store,
)
from kronos.swing.v1.native_active_trade_lifecycle import TradeExitReason
from kronos.swing.v1.native_review import NativeReviewEvidenceStore
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
from kronos.swing.v1.native_trade_construction import LocalTradePlanStore
from kronos.swing.v1.progression_watch import (
    derive_kr370_progression_requirements,
    derive_progression_requirements,
    derive_v3_progression_requirements,
)


_LOOPBACK_HOST = "127.0.0.1"
_MAX_CREDENTIAL_FORM_BYTES = 4096
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
    "/reports": ("Reports", "Reports", ""),
    "/swing/paper": ("Paper", "Swing", "Paper"),
    "/swing/ignored": ("Ignored", "Swing", "Ignored"),
}


class KronosBrowserServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

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
        provider_instrument_master_operation: (
            ProviderInstrumentMasterOperationalComposition | None
        ) = None,
    ) -> None:
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
                provider_instrument_master_operation is not None
                and type(provider_instrument_master_operation)
                is not ProviderInstrumentMasterOperationalComposition
            )
        ):
            raise ValueError("BROWSER_SERVER_MUST_BIND_LOOPBACK")
        config = OpenAIChartAnalystV2Config.from_environment()
        transport, default_credentials = _openai_chart_analyst_security(config)
        self.application = application
        self.chart_analyst_credentials = (
            chart_analyst_credentials or default_credentials
        )
        self.chart_analyst_activation = (
            chart_analyst_activation or ChartAnalystV2ActivationService()
        )
        self.restart_control = restart_control
        self.provider_instrument_master_operation = (
            provider_instrument_master_operation
        )
        self._shutdown_lock = Lock()
        self._shutdown_started = False
        self._active_sponsor_work = 0
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
            )
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
        )
        self.telegram = telegram or _telegram_security()
        self.swing_monitoring_hub = SharedSwingMonitoringHub()
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
        )
        self.progression_watches.set_ux10_listeners(
            watch_listener=self.ux10_notifications.observe_progression_watch,
            connection_listener=lambda *_values: None,
        )
        self.native_review.set_ux10_lifecycle_event_listener(
            self.ux10_notifications.observe_lifecycle_event
        )
        native_run = self.application.native_discovery_run()
        mtf_facts = self.application.mtf_fact_snapshot()
        native_store = self.application.native_discovery_evidence_store()
        mtf_store = self.application.mtf_fact_evidence_store()
        if native_store is not None and mtf_store is not None:
            latest_native = native_store.latest()
            if (
                latest_native is not None
                and (
                    native_run is None
                    or latest_native.observed_at > native_run.observed_at
                )
            ):
                try:
                    latest_facts = mtf_store.load(latest_native.run_identity)
                except ValueError:
                    pass
                else:
                    native_run = latest_native
                    mtf_facts = latest_facts
        self.native_review_run = native_run
        self.native_review_facts = mtf_facts
        if native_run is not None and mtf_facts is not None:
            try:
                self.native_review.restore(native_run, mtf_facts)
            except ValueError:
                pass
            try:
                self.visual_v3_live.restore(
                    self.native_review.snapshot(),
                    mtf_facts,
                    self.native_review.original_chart_bytes,
                )
            except (ValueError, PdfReviewTransportError, TradingViewEvidenceStoreError):
                # Versioned V3 restoration is fail-closed. Historical V2 remains
                # independently restorable and is never converted as recovery.
                pass
        self.trade_window.restore(self.visual_v3.completed_snapshot())
        self.trade_window.synchronize_downstream(self.native_review.snapshot())
        self.progression_snapshot()
        self.ux10_notifications.retry_pending()
        super().__init__(address, _BrowserHandler)

    def server_close(self) -> None:
        self.progression_watches.close_monitoring()
        self.native_review.close()
        self.trade_window.close_monitoring()
        self.swing_monitoring_hub.close()
        self.step32_workflow.close()
        self.application.close()
        if self.restart_control is not None:
            self.restart_control.remove()
        super().server_close()

    def progression_snapshot(self) -> SwingProgressionWatchSnapshot:
        """Project UX-08 requirements from one immutable Native/Review binding."""

        _, run = self.application.opportunities_projection()
        review = self.native_review.snapshot()
        if run is None or review.native_run_identity != run.run_identity:
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
        watchable = tuple(
            item.requirement_id for item in snapshot.requirements
            if item.state.value == "WATCH_AVAILABLE"
            and item.source_analytical_state in {"BUY_READY", "SELL_READY"}
        )
        if watchable:
            self.application.auto_activate_progression_watches(watchable)
            snapshot = self.progression_watches.snapshot()
        return snapshot

    def active_live_monitoring_count(self) -> int:
        """Count owned live subscriptions without changing retained watch truth."""

        return (
            self.progression_watches.active_monitoring_count
            + self.native_review.active_monitoring_count
        )

    def visual_v3_presentations(self):  # type: ignore[no-untyped-def]
        return tuple(
            present_visual_v3_review(item)
            for item in self.visual_v3.completed_snapshot()
        )

    def native_review_version(self) -> str:
        """Select by the persisted current Review identity, never module presence."""

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

        with self._shutdown_lock:
            if self._shutdown_started:
                return False
            self._active_sponsor_work += 1
            return True

    def finish_sponsor_work(self) -> None:
        with self._shutdown_lock:
            self._active_sponsor_work -= 1

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
            self._shutdown_started = True
            return "SHUTDOWN_ACCEPTED"


class _BrowserHandler(BaseHTTPRequestHandler):
    server: KronosBrowserServer

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path == "/":
            self._redirect("/swing/opportunities")
            return
        if path == "/swing":
            self._redirect("/swing/opportunities")
            return
        if path == "/control/provider-instrument-master/status":
            self._provider_instrument_master_status()
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
                product_response.body.encode("utf-8"),
                product_response.content_type,
            )
            return
        if path == "/dashboard":
            snapshot, discovery = self.server.application.opportunities_projection()
            notifications = project_swing_notification_workspace(
                self.server.progression_snapshot()
            )
            promotions = tuple(
                item.promotion
                for item in self.server.visual_v3.completed_snapshot()
                if item.promotion is not None
            )
            self._html(render_dashboard(
                snapshot,
                project_sponsor_dashboard(
                    snapshot, discovery, promotions, notifications,
                    self.server.ux10_notifications.snapshot(),
                ),
            ))
            return
        if path == "/notifications/status":
            projected = project_swing_notification_workspace(
                self.server.progression_snapshot()
            )
            self._json({
                "revision": projected.revision + self.server.ux10_notifications.snapshot().revision,
                "count": len(projected.records) + len(self.server.ux10_notifications.snapshot().records),
                "action_required": len(projected.action_required),
            })
            return
        if path == "/swing/opportunities":
            self.server.trade_window.synchronize_downstream(
                self.server.native_review.snapshot()
            )
            snapshot, discovery = (
                self.server.application.opportunities_projection()
            )
            self._html(render_opportunities(
                snapshot,
                discovery,
                self.server.native_review.snapshot(),
                self.server.progression_snapshot(),
                self.server.visual_v3_presentations(),
                self.server.trade_window.projections(),
            ))
            return
        if path in {"/notifications", "/notifications/swing", "/notifications/intraday"}:
            selected = {
                "/notifications": None,
                "/notifications/swing": NotificationProduct.SWING,
                "/notifications/intraday": NotificationProduct.INTRADAY,
            }[path]
            self._html(render_notifications(
                self.server.application.snapshot(),
                project_swing_notification_workspace(self.server.progression_snapshot()),
                selected_product=selected,
                ux10=self.server.ux10_notifications.snapshot(),
            ))
            return
        details_match = _ANALYSIS_DETAILS_ROUTE.fullmatch(path)
        if details_match:
            self.server.trade_window.synchronize_downstream(
                self.server.native_review.snapshot()
            )
            snapshot, discovery = self.server.application.opportunities_projection()
            details = (
                None
                if discovery is None
                else project_native_analysis_details(
                    discovery,
                    self.server.native_review.snapshot(),
                    details_match.group(1),
                    unquote(details_match.group(2)),
                )
            )
            if details is None:
                self._text(HTTPStatus.NOT_FOUND, "Analysis Details not found.")
                return
            v3 = next((
                value for value in self.server.visual_v3_presentations()
                if value.run_identity == details.assessment.run_identity
                and value.canonical_instrument
                == details.assessment.canonical_instrument
                and value.native_assessment_sha256
                == details.assessment.result_sha256
            ), None)
            self._html(render_native_analysis_details(
                snapshot,
                details,
                self.server.progression_snapshot(),
                v3,
                self.server.trade_window.project(
                    details.assessment.run_identity,
                    details.assessment.canonical_instrument,
                ),
            ))
            return
        trade_window_match = _TRADE_WINDOW_ROUTE.fullmatch(path)
        if trade_window_match:
            self.server.trade_window.synchronize_downstream(
                self.server.native_review.snapshot()
            )
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
            review = self.server.native_review.snapshot()
            self._html(render_v1_review(
                snapshot,
                self.server.v1_review.snapshot(),
                review,
                (
                    self.server.visual_v3_live.snapshot(
                        review.native_run_identity
                    )
                    if self.server.native_review_version() == "V3"
                    else None
                ),
            ))
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
            self._html(render_active_candidates(
                snapshot,
                self.server.step32_workflow.snapshot(),
                self.server.native_review.snapshot().active_lifecycle,
            ))
            return
        if path == "/swing/closed":
            self._html(render_closed_candidates(
                snapshot,
                self.server.step32_workflow.snapshot(),
                self.server.native_review.snapshot().active_lifecycle,
            ))
            return
        if path == "/journal":
            query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
            selected = query.get("filter", ["ALL"])
            selected_record = query.get("record", [None])
            if (
                set(query).difference({"filter", "record"})
                or len(selected) != 1
                or len(selected_record) != 1
            ):
                self._text(HTTPStatus.BAD_REQUEST, "Journal filter is invalid.")
                return
            self._html(render_trade_journal(
                snapshot,
                self.server.native_review.journal_snapshot(),
                selected_filter=selected[0],
                selected_record_id=selected_record[0],
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
                "v1_probables": len(snapshot.v1_probables),
                "analysis_diagnostic": None,
                "live_monitoring": live_monitoring.state.value,
            }
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
        path = urlsplit(self.path).path
        if path == "/control/shutdown":
            self._graceful_backend_shutdown()
            return
        if not self._same_origin():
            self._text(HTTPStatus.FORBIDDEN, "Request rejected.")
            return
        if path == "/control/exit":
            self._sponsor_exit()
            return
        if not self.server.admit_sponsor_work():
            self._text(HTTPStatus.SERVICE_UNAVAILABLE, "KRONOS is shutting down.")
            return
        try:
            self._dispatch_post(path)
        finally:
            self.server.finish_sponsor_work()

    def _dispatch_post(self, path: str) -> None:
        if path == "/control/provider-instrument-master":
            self._run_provider_instrument_master()
            return
        if path == "/provider/connect":
            self.server.application.connect_provider()
            self._redirect("/swing/opportunities")
            return
        if path == "/provider/disconnect":
            self._disconnect_provider()
            return
        if path == "/swing/analysis":
            self.server.application.run_analysis()
            self._redirect("/swing/opportunities")
            return
        if path == "/swing/progression-watch/activate":
            self._activate_progression_watch()
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
                or not operation(values[0])
            ):
                raise ValueError
        except (AttributeError, UnicodeDecodeError, ValueError):
            self._text(HTTPStatus.CONFLICT, "Notification action is not available.")
            return
        self._redirect("/notifications")

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
            result = self.server.native_review.initiate_sponsor_decision(
                plans[0], mode, actual_live_entry=actual_entry, live_lots=lots,
            )
            if result.decision is None:
                raise ValueError(result.reason)
        except (UnicodeDecodeError, ValueError, InvalidOperation):
            self._text(HTTPStatus.CONFLICT, "Sponsor decision is not available.")
            return
        self._redirect("/swing/v1-review")

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
        self.send_response(HTTPStatus.ACCEPTED)
        self._security_headers()
        body = b'{"status":"STOPPING"}'
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()
        Thread(
            target=self.server.shutdown,
            name="kronos-browser-shutdown",
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
        self.server.application.disconnect_provider()
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

    def _remove_native_chart(self) -> None:
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
        native_store = self.server.application.native_discovery_evidence_store()
        mtf_store = self.server.application.mtf_fact_evidence_store()
        if native_store is not None and mtf_store is not None:
            latest = native_store.latest()
            if (
                latest is not None
                and (
                    native_run is None
                    or latest.observed_at > native_run.observed_at
                )
            ):
                try:
                    latest_facts = mtf_store.load(latest.run_identity)
                except ValueError:
                    pass
                else:
                    native_run = latest
                    facts = latest_facts
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
        if urlsplit(self.path).query:
            self._text(HTTPStatus.BAD_REQUEST, "Answer Pack request rejected.")
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
            else:
                self.server.native_review.upload_review_answer()
        except (
            PdfReviewTransportError,
            TradingViewEvidenceStoreError,
            OSError,
            TypeError,
            ValueError,
        ):
            self._redirect("/swing/v1-review")
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

    def _same_origin(self) -> bool:
        authority = f"{_LOOPBACK_HOST}:{self.server.server_port}"
        if self.headers.get("Host") != authority:
            return False
        origin = self.headers.get("Origin")
        return origin == f"http://{authority}"

    def _html(self, body: str) -> None:
        self._respond(HTTPStatus.OK, body.encode("utf-8"), "text/html; charset=utf-8")

    def _json(self, payload: dict[str, object]) -> None:
        self._respond(
            HTTPStatus.OK,
            json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def _text(self, status: HTTPStatus, body: str) -> None:
        self._respond(status, body.encode("utf-8"), "text/plain; charset=utf-8")

    def _redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self._security_headers()
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _respond(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self._security_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _security_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'; form-action 'self'")
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
    provider_instrument_master_operation: (
        ProviderInstrumentMasterOperationalComposition | None
    ) = None,
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
        provider_instrument_master_operation,
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
