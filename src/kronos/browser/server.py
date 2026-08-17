"""Loopback-only HTTP transport for KRONOS Browser V1."""

from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
from threading import Thread
from urllib.parse import parse_qs, urlsplit

from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.application.intraday_workstation import IntradayEvidenceWorkstation
from kronos.application.swing_v1_review import (
    SwingV1ReviewWorkflow,
    V1BatchPreflightFailure,
)
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
from kronos.integrations.openai_chart_analyst import (
    OpenAIChartAnalystCapabilityProbe,
    OpenAIChartAnalystV2Config,
    OpenAIChartAnalystV2Provider,
    UrllibOpenAIResponsesTransport,
)
from kronos.browser.views import (
    render_opportunities,
    render_intraday_workstation,
    render_placeholder,
    render_settings,
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


_LOOPBACK_HOST = "127.0.0.1"
_MAX_CREDENTIAL_FORM_BYTES = 4096
_WORKSPACE_ROUTE = re.compile(r"/swing/opportunities/([1-2])\Z")
_ELIGIBLE_WORKSPACE_ROUTE = re.compile(r"/swing/eligible/([1-9][0-9]*)\Z")
_PLACEHOLDERS = {
    "/dashboard": ("Dashboard", "Dashboard", ""),
    "/theta-earners": ("Theta Earners", "Theta Earners", ""),
    "/journal": ("Trading Journal", "Trading Journal", ""),
    "/portfolio": ("Portfolio", "Portfolio", ""),
    "/reports": ("Reports", "Reports", ""),
    "/swing/active": ("Active", "Swing", "Active"),
    "/swing/paper": ("Paper", "Swing", "Paper"),
    "/swing/ignored": ("Ignored", "Swing", "Ignored"),
    "/swing/closed": ("Closed", "Swing", "Closed"),
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
                intraday_workstation is not None
                and type(intraday_workstation) is not IntradayEvidenceWorkstation
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
        if v1_review is not None:
            self.v1_review = v1_review
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
        super().__init__(address, _BrowserHandler)

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
        snapshot = self.server.application.snapshot()
        if path == "/intraday":
            query = parse_qs(urlsplit(self.path).query)
            selected = query.get("instrument", [None])[0]
            self._html(render_intraday_workstation(
                snapshot,
                self.server.intraday_workstation.snapshot(selected),
            ))
            return
        if path == "/swing/opportunities":
            self._html(render_opportunities(snapshot))
            return
        if path == "/swing/v1-review":
            self._html(render_v1_review(snapshot, self.server.v1_review.snapshot()))
            return
        if path == "/swing/v1/chart-preview":
            self._v1_chart_preview()
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
        self._text(HTTPStatus.NOT_FOUND, "Not found.")

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
