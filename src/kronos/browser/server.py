"""Loopback-only HTTP transport for KRONOS Browser V1."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import re
from threading import Thread
from urllib.parse import parse_qs, urlsplit

from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.application.intraday_workstation import IntradayEvidenceWorkstation
from kronos.application.swing_v1_browser import SwingV1BrowserOperationalization
from kronos.application.swing_v1_review import (
    SwingV1ReviewWorkflow,
    V1BatchPreflightFailure,
)
from kronos.application.swing_native_review import NativeReviewWorkflow
from kronos.configuration.apple_keychain import (
    AppleKeychainApiKeySource,
    AppleKeychainCredentialPresenceProbe,
    AppleKeychainCredentialProvisioner,
    run_security_framework_provisioning,
    run_security_framework_subprocess,
    run_security_presence_subprocess,
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
    render_legacy_opportunities,
    render_opportunities,
    render_intraday_workstation,
    render_placeholder,
    render_settings,
    render_trade_journal,
    render_shadow_validation,
    render_mtf_fact_diagnostics,
    render_native_discovery,
    render_trade_candidates,
    render_v1_review,
)
from kronos.browser.v1_analysis_status import analysis_status_payload
from kronos.browser.restart_control import BrowserBackendRestartControl
from kronos.swing.v1.evidence_store import (
    LocalTradingViewEvidenceStore,
    TradingViewEvidenceStoreError,
)
from kronos.swing.run_provenance import LocalSwingRunProvenanceStore
from kronos.swing.v1.chart_analyst_v2_store import LocalChartAnalystV2Store
from kronos.swing.v1.tradingview import ChartTimeframe
from kronos.swing.v1.step32 import SponsorDecisionMode
from kronos.swing.v1.native_sponsor_decision import SponsorTradeChoice
from kronos.swing.v1.native_active_trade_lifecycle import TradeExitReason
from kronos.swing.v1.shadow_mtf import ShadowInstrumentAssessment
from kronos.swing.v1.validation_evidence import ShadowValidationEvidenceStore
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


_LOOPBACK_HOST = "127.0.0.1"
_MAX_CREDENTIAL_FORM_BYTES = 4096
_WORKSPACE_ROUTE = re.compile(r"/swing/opportunities/([1-2])\Z")
_LOG = logging.getLogger(__name__)
_ELIGIBLE_WORKSPACE_ROUTE = re.compile(r"/swing/eligible/([1-9][0-9]*)\Z")
_TRADE_CANDIDATE_ROUTE = re.compile(
    r"/swing/trade-candidates/([0-9a-f]{16})\Z"
)
_TRADE_CANDIDATE_DECISION_ROUTE = re.compile(
    r"/swing/trade-candidates/([0-9a-f]{16})/decision\Z"
)
_PLACEHOLDERS = {
    "/dashboard": ("Dashboard", "Dashboard", ""),
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
        intraday_workstation: IntradayEvidenceWorkstation | None = None,
        step32_workflow: SwingV1BrowserOperationalization | None = None,
        shadow_assessments: tuple[ShadowInstrumentAssessment, ...] = (),
        shadow_evidence_store: ShadowValidationEvidenceStore | None = None,
        native_review: NativeReviewWorkflow | None = None,
    ) -> None:
        effective_shadow_store = (
            shadow_evidence_store or application.shadow_evidence_store()
        )
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
                intraday_workstation is not None
                and type(intraday_workstation) is not IntradayEvidenceWorkstation
            )
            or (
                step32_workflow is not None
                and type(step32_workflow) is not SwingV1BrowserOperationalization
            )
            or type(shadow_assessments) is not tuple
            or any(type(item) is not ShadowInstrumentAssessment for item in shadow_assessments)
            or (
                effective_shadow_store is not None
                and type(effective_shadow_store) is not ShadowValidationEvidenceStore
            )
            or (
                native_review is not None
                and type(native_review) is not NativeReviewWorkflow
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
        self.intraday_workstation = (
            intraday_workstation or IntradayEvidenceWorkstation()
        )
        self.step32_workflow = (
            step32_workflow or SwingV1BrowserOperationalization()
        )
        self.shadow_assessments = shadow_assessments
        self.shadow_evidence_store = effective_shadow_store
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
                if self.shadow_evidence_store is not None:
                    try:
                        self.application.restore_shadow_run(
                            self.shadow_evidence_store.load_run(parent_run)
                        )
                    except ValueError:
                        pass
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
        native_review_store = NativeReviewEvidenceStore()
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
        super().__init__(address, _BrowserHandler)

    def current_shadow_assessments(self) -> tuple[ShadowInstrumentAssessment, ...]:
        retained = self.application.shadow_assessments()
        return retained if retained else self.shadow_assessments

    def server_close(self) -> None:
        self.application.close()
        if self.restart_control is not None:
            self.restart_control.remove()
        super().server_close()


class _BrowserHandler(BaseHTTPRequestHandler):
    server: KronosBrowserServer

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path == "/":
            self._redirect("/swing/opportunities")
            return
        if path == "/intraday":
            snapshot = self.server.application.snapshot()
            query = parse_qs(urlsplit(self.path).query)
            selected = query.get("instrument", [None])[0]
            self._html(render_intraday_workstation(
                snapshot,
                self.server.intraday_workstation.snapshot(selected),
            ))
            return
        if path == "/swing/opportunities":
            snapshot, discovery = (
                self.server.application.opportunities_projection()
            )
            self._html(render_opportunities(
                snapshot,
                discovery,
                self.server.native_review.snapshot(),
            ))
            return
        snapshot = self.server.application.snapshot()
        if path == "/swing/layer1-history":
            self._html(render_legacy_opportunities(snapshot))
            return
        if path == "/swing/v1-review":
            self._html(render_v1_review(
                snapshot,
                self.server.v1_review.snapshot(),
                self.server.native_review.snapshot(),
            ))
            return
        if path == "/swing/shadow-validation":
            self._html(render_shadow_validation(
                snapshot,
                self.server.current_shadow_assessments(),
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
            if set(query).difference({"filter"}) or len(selected) != 1:
                self._text(HTTPStatus.BAD_REQUEST, "Journal filter is invalid.")
                return
            self._html(render_trade_journal(
                snapshot,
                self.server.native_review.journal_snapshot(),
                selected_filter=selected[0],
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
        if path == "/provider/connect":
            self.server.application.connect_provider()
            self._redirect("/swing/opportunities")
            return
        if path == "/provider/disconnect":
            self.server.application.disconnect_provider()
            self._redirect("/swing/opportunities")
            return
        if path == "/swing/analysis":
            self.server.application.run_analysis()
            self._redirect("/swing/opportunities")
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
        if path == "/swing/shadow-observation":
            self._record_shadow_observation()
            return
        if path == "/settings/chart-analyst/credential":
            self._receive_chart_analyst_credential()
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

    def _record_shadow_observation(self) -> None:
        query = parse_qs(urlsplit(self.path).query, strict_parsing=True)
        runs = query.get("run", ())
        instruments = query.get("instrument", ())
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0]
        try:
            content_length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            content_length = 0
        if (
            self.server.shadow_evidence_store is None
            or set(query) != {"run", "instrument"}
            or len(runs) != 1
            or len(instruments) != 1
            or content_type.lower() != "application/x-www-form-urlencoded"
            or not 0 < content_length <= 1024
        ):
            self._text(HTTPStatus.CONFLICT, "Shadow observation is not available.")
            return
        matching = tuple(
            item for item in self.server.current_shadow_assessments()
            if item.run_identity == runs[0]
            and item.canonical_instrument == instruments[0]
        )
        try:
            fields = parse_qs(
                self.rfile.read(content_length).decode("utf-8"),
                strict_parsing=True,
            )
            observations = fields.get("observation", ())
            if set(fields) != {"observation"} or len(observations) != 1 or len(matching) != 1:
                raise ValueError
            self.server.shadow_evidence_store.record_sponsor_observation(
                matching[0], observations[0]
            )
        except (UnicodeDecodeError, ValueError):
            self._text(HTTPStatus.CONFLICT, "Shadow observation was not recorded.")
            return
        self._redirect("/swing/shadow-validation")

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
            self.server.native_review.upload_review_answer()
        except (PdfReviewTransportError, TradingViewEvidenceStoreError, OSError, ValueError):
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
    intraday_workstation: IntradayEvidenceWorkstation | None = None,
    step32_workflow: SwingV1BrowserOperationalization | None = None,
    shadow_assessments: tuple[ShadowInstrumentAssessment, ...] = (),
    shadow_evidence_store: ShadowValidationEvidenceStore | None = None,
    native_review: NativeReviewWorkflow | None = None,
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
        shadow_assessments,
        shadow_evidence_store,
        native_review,
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


__all__ = ["KronosBrowserServer", "create_browser_server"]
