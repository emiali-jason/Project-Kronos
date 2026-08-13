import json
from pathlib import Path
from threading import Thread

from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.application.swing_v1_review import (
    SwingV1ReviewWorkflow,
    V1BatchPreflightFailure,
)
from kronos.browser.server import create_browser_server
from kronos.configuration.openai_chart_analyst import (
    ChartAnalystV2ActivationService,
    OpenAIChartAnalystCredentialService,
)
from kronos.swing.v1.chart_analyst_v2 import ChartAnalystV2Response
from kronos.swing.v1.evidence_store import LocalTradingViewEvidenceStore
from kronos.swing.v1.models import V1Setup
from kronos.swing.v1.tradingview import ChartTimeframe
from tests.unit.application.test_swing_opportunities import _Provider, _ready
from tests.unit.browser.test_browser_chart_analyst_credentials import (
    _CapabilityTester,
    _ProtectedBackend,
    _origin_headers,
)
from tests.unit.browser.test_browser_server import _request
from tests.unit.swing.v1.test_chart_analyst_v2_layer2 import _valid_analysis
from tests.unit.swing.v1.test_swing_v1_slice3 import _classified_run
from tests.unit.swing.v1.test_swing_v1_slice4 import _IMAGE, _NOW


_PARENT_RUN = "SWING-RUN-00000000000000000000000000000044"


class _NoNetworkV2Provider:
    provider_identity = "OPENAI_CHART_ANALYST_V2_PROVIDER"
    model_configured = True
    question_set_available = True
    configuration_ready = True

    def __init__(self) -> None:
        self.calls = 0

    def analyze(self, request):  # type: ignore[no-untyped-def]
        self.calls += 1
        return ChartAnalystV2Response(
            provider_identity=self.provider_identity,
            model_identity="gpt-test",
            request_timestamp=request.request_timestamp,
            run_identity=request.run_identity,
            swing_analysis_run_identity=request.swing_analysis_run_identity,
            analysis={
                **_valid_analysis(request.instrument, request.product),
                "image_sha256": request.image_sha256,
            },
        )


def _server(
    tmp_path: Path,
    *,
    credential_stored: bool,
    enabled: bool,
):  # type: ignore[no-untyped-def]
    provider = _NoNetworkV2Provider()
    workflow = SwingV1ReviewWorkflow(
        LocalTradingViewEvidenceStore(tmp_path / "evidence", clock=lambda: _NOW),
        chart_analyst_v2_provider=provider,
        clock=lambda: _NOW,
    )
    workflow.publish_layer1(
        _classified_run({("NAUKRI", V1Setup.PULLBACK_CONTINUATION)}),
        swing_analysis_run_identity=_PARENT_RUN,
    )
    workflow.upload(
        instrument="NAUKRI",
        timeframe=ChartTimeframe.DAILY,
        content_type="image/png",
        original_bytes=_IMAGE,
    )
    backend = _ProtectedBackend()
    backend.stored = credential_stored
    credentials = OpenAIChartAnalystCredentialService(
        provisioner=backend,
        presence_probe=backend,
        capability_tester=_CapabilityTester(),
    )
    activation = ChartAnalystV2ActivationService(tmp_path / "activation.json")
    activation.set_enabled(enabled)
    application = SwingOpportunitiesApplication(_Provider, initial_snapshot=_ready())
    server = create_browser_server(
        application,
        port=0,
        v1_review=workflow,
        chart_analyst_credentials=credentials,
        chart_analyst_activation=activation,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, workflow, provider


def test_connected_but_disabled_blocks_whole_batch_before_provider_calls(
    tmp_path: Path,
) -> None:
    server, thread, workflow, provider = _server(
        tmp_path,
        credential_stored=True,
        enabled=False,
    )
    try:
        status, _, _ = _request(
            server,
            "POST",
            "/swing/v1/analyze",
            headers=_origin_headers(server),
        )
        assert status == 303
        assert provider.calls == 0
        review = workflow.snapshot()
        assert review.batch_preflight_failure is (
            V1BatchPreflightFailure.CHART_ANALYST_V2_DISABLED
        )
        assert review.analyses[0].state.value == "READY_TO_ANALYZE"

        payload = json.loads(_request(server, "GET", "/swing/v1/status")[2])
        assert payload["batch"] == "CHART ANALYST V2 DISABLED"
        assert payload["instruments"] == [
            {"instrument": "NAUKRI", "status": "WAITING"}
        ]
        rendered = _request(server, "GET", "/swing/v1-review")[2]
        assert rendered.count("CHART ANALYST V2 DISABLED") == 1
        assert "Enable it in Settings before analysis." in rendered
        assert ">ANALYSIS FAILED</span>" not in rendered
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_connected_and_enabled_permits_analysis(tmp_path: Path) -> None:
    server, thread, workflow, provider = _server(
        tmp_path,
        credential_stored=True,
        enabled=True,
    )
    try:
        status, _, _ = _request(
            server,
            "POST",
            "/swing/v1/analyze",
            headers=_origin_headers(server),
        )
        assert status == 303
        assert provider.calls == 1
        review = workflow.snapshot()
        assert review.batch_preflight_failure is None
        assert review.analyses[0].state.value == "ANALYSIS_COMPLETE"
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_enabled_without_credential_fails_closed_before_provider_calls(
    tmp_path: Path,
) -> None:
    server, thread, workflow, provider = _server(
        tmp_path,
        credential_stored=False,
        enabled=True,
    )
    try:
        status, _, _ = _request(
            server,
            "POST",
            "/swing/v1/analyze",
            headers=_origin_headers(server),
        )
        assert status == 303
        assert provider.calls == 0
        assert workflow.snapshot().batch_preflight_failure is (
            V1BatchPreflightFailure.OPENAI_NOT_CONNECTED
        )
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_single_chart_validation_calls_only_the_selected_instrument(
    tmp_path: Path,
) -> None:
    provider = _NoNetworkV2Provider()
    workflow = SwingV1ReviewWorkflow(
        LocalTradingViewEvidenceStore(tmp_path / "evidence", clock=lambda: _NOW),
        chart_analyst_v2_provider=provider,
        clock=lambda: _NOW,
    )
    workflow.publish_layer1(
        _classified_run({
            ("NAUKRI", V1Setup.PULLBACK_CONTINUATION),
            ("TITAN", V1Setup.PULLBACK_CONTINUATION),
        }),
        swing_analysis_run_identity=_PARENT_RUN,
    )
    for instrument, image in (
        ("NAUKRI", _IMAGE),
        ("TITAN", b"\x89PNG\r\n\x1a\ntitan-four-pane"),
    ):
        workflow.upload(
            instrument=instrument,
            timeframe=ChartTimeframe.DAILY,
            content_type="image/png",
            original_bytes=image,
        )
    backend = _ProtectedBackend()
    backend.stored = True
    credentials = OpenAIChartAnalystCredentialService(
        provisioner=backend,
        presence_probe=backend,
        capability_tester=_CapabilityTester(),
    )
    activation = ChartAnalystV2ActivationService(tmp_path / "activation.json")
    activation.set_enabled(True)
    application = SwingOpportunitiesApplication(_Provider, initial_snapshot=_ready())
    server = create_browser_server(
        application,
        port=0,
        v1_review=workflow,
        chart_analyst_credentials=credentials,
        chart_analyst_activation=activation,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        rendered = _request(server, "GET", "/swing/v1-review")[2]
        assert rendered.count("Validate One Chart") == 2

        status, headers, _ = _request(
            server,
            "POST",
            "/swing/v1/analyze-one?instrument=TITAN",
            headers=_origin_headers(server),
        )
        assert status == 303
        assert headers["Location"] == "/swing/v1-review"
        assert provider.calls == 1
        assert workflow.snapshot().analysis_for("NAUKRI").state.value == (
            "READY_TO_ANALYZE"
        )
        assert workflow.snapshot().analysis_for("TITAN").state.value == (
            "ANALYSIS_COMPLETE"
        )
    finally:
        server.shutdown(); server.server_close(); thread.join()
