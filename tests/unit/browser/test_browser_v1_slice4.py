from kronos.application.swing_v1_review import SwingV1ReviewWorkflow
from kronos.browser.views import render_v1_review
from threading import Event, Thread

from kronos.swing.v1.chart_evidence import ManualChartEvidenceProvider
from kronos.swing.v1.chart_analyst_v2 import (
    ChartAnalystV2Error,
    ChartAnalystV2FailureCode,
    ChartAnalystV2Response,
)
from kronos.swing.v1.evidence_store import LocalTradingViewEvidenceStore
from kronos.swing.v1.models import V1Setup
from kronos.swing.v1.tradingview import ChartTimeframe
from tests.unit.application.test_swing_opportunities import _ready
from tests.unit.browser.test_browser_server import _request, _running_server
from tests.unit.swing.v1.test_swing_v1_slice3 import _classified_run
from tests.unit.swing.v1.test_swing_v1_slice4 import _IMAGE, _NOW, _response
from tests.unit.swing.v1.test_chart_analyst_v2_layer2 import _valid_analysis


_PARENT_RUN = "SWING-RUN-00000000000000000000000000000003"


class _BoundResponseProvider:
    provider_identity = "MANUAL_CHART_EVIDENCE_PROVIDER"

    def analyze(self, request):  # type: ignore[no-untyped-def]
        return _response(request)


class _BlockingV2Provider:
    provider_identity = "OPENAI_CHART_ANALYST_V2_PROVIDER"

    def __init__(self, *, outcomes=None) -> None:  # type: ignore[no-untyped-def]
        self.entered = Event()
        self.release = Event()
        self.outcomes = outcomes or {}
        self.responses = {}

    def analyze(self, request):  # type: ignore[no-untyped-def]
        self.entered.set()
        self.release.wait(timeout=3)
        failure = self.outcomes.get(request.instrument)
        if failure is not None:
            raise ChartAnalystV2Error(failure)
        response = ChartAnalystV2Response(
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
        self.responses[(request.run_identity, request.instrument, request.image_sha256)] = response
        return response

    def retained_response(self, **binding):  # type: ignore[no-untyped-def]
        return self.responses.get((
            binding["run_identity"],
            binding["instrument"],
            binding["image_sha256"],
        ))


def test_browser_chart_intake_exposes_one_analysis_action_without_internal_states(tmp_path) -> None:  # type: ignore[no-untyped-def]
    run = _classified_run({("NAUKRI", V1Setup.PULLBACK_CONTINUATION)})
    workflow = SwingV1ReviewWorkflow(
        LocalTradingViewEvidenceStore(tmp_path, clock=lambda: _NOW),
        chart_evidence_provider=ManualChartEvidenceProvider((_response(),)),
        clock=lambda: _NOW,
    )
    requested = render_v1_review(_ready(), workflow.publish_layer1(run))
    assert "Click, then paste" in requested
    assert "Analyze Charts" not in requested

    workflow.upload(
        instrument="NAUKRI",
        timeframe=ChartTimeframe.DAILY,
        content_type="image/png",
        original_bytes=_IMAGE,
    )
    ready = render_v1_review(_ready(), workflow.snapshot())
    assert ready.count("Analyze Charts") == 1
    assert 'action="/swing/v1/analyze"' in ready

    workflow.analyze_all_chart_context()
    complete = render_v1_review(_ready(), workflow.snapshot())
    assert workflow.snapshot().analysis_for("NAUKRI").readiness.state.value.replace(
        "_", " "
    ) in complete
    for hidden_detail in ("ANALYSIS_COMPLETE", "Risk : Reward", "Final Trade"):
        assert hidden_detail not in complete


def test_browser_provider_unavailable_is_context_incomplete_and_has_no_trade_geometry(tmp_path) -> None:  # type: ignore[no-untyped-def]
    workflow = SwingV1ReviewWorkflow(
        LocalTradingViewEvidenceStore(tmp_path, clock=lambda: _NOW),
        clock=lambda: _NOW,
    )
    workflow.publish_layer1(_classified_run({("NAUKRI", V1Setup.PULLBACK_CONTINUATION)}))
    workflow.upload(
        instrument="NAUKRI",
        timeframe=ChartTimeframe.DAILY,
        content_type="image/png",
        original_bytes=_IMAGE,
    )
    workflow.analyze_chart_context("NAUKRI")

    rendered = render_v1_review(_ready(), workflow.snapshot())
    assert "Chart received" in rendered
    assert "CHART ANALYSIS UNAVAILABLE" not in rendered
    assert "CONTEXT INCOMPLETE" in rendered
    assert "ANALYSIS PROVIDER UNAVAILABLE" in rendered
    assert "Entry" not in rendered
    assert "Target" not in rendered
    assert "R:R" not in rendered


def test_browser_analyze_route_invokes_complete_chart_set_from_one_action(tmp_path) -> None:  # type: ignore[no-untyped-def]
    workflow = SwingV1ReviewWorkflow(
        LocalTradingViewEvidenceStore(tmp_path, clock=lambda: _NOW),
        chart_evidence_provider=ManualChartEvidenceProvider((_response(),)),
        clock=lambda: _NOW,
    )
    workflow.publish_layer1(_classified_run({("NAUKRI", V1Setup.PULLBACK_CONTINUATION)}))
    workflow.upload(
        instrument="NAUKRI",
        timeframe=ChartTimeframe.DAILY,
        content_type="image/png",
        original_bytes=_IMAGE,
    )
    server, thread = _running_server(_ready(), v1_review=workflow)
    try:
        authority = f"127.0.0.1:{server.server_port}"
        status, headers, _ = _request(
            server,
            "POST",
            "/swing/v1/analyze",
            headers={"Host": authority, "Origin": f"http://{authority}"},
        )
        assert status == 303
        assert headers["Location"] == "/swing/v1-review"
        assert workflow.snapshot().analysis_for("NAUKRI").state.value == "ANALYSIS_COMPLETE"
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_browser_analyze_route_fails_closed_until_every_chart_is_present(tmp_path) -> None:  # type: ignore[no-untyped-def]
    workflow = SwingV1ReviewWorkflow(
        LocalTradingViewEvidenceStore(tmp_path, clock=lambda: _NOW),
        chart_evidence_provider=ManualChartEvidenceProvider((_response(),)),
        clock=lambda: _NOW,
    )
    workflow.publish_layer1(_classified_run({
        ("NAUKRI", V1Setup.PULLBACK_CONTINUATION),
        ("TITAN", V1Setup.PULLBACK_CONTINUATION),
    }), swing_analysis_run_identity=_PARENT_RUN)
    workflow.upload(
        instrument="NAUKRI",
        timeframe=ChartTimeframe.DAILY,
        content_type="image/png",
        original_bytes=_IMAGE,
    )
    server, thread = _running_server(_ready(), v1_review=workflow)
    try:
        authority = f"127.0.0.1:{server.server_port}"
        status, _, _ = _request(
            server,
            "POST",
            "/swing/v1/analyze",
            headers={"Host": authority, "Origin": f"http://{authority}"},
        )
        assert status == 409
        assert workflow.snapshot().analysis_for("NAUKRI").state.value == "READY_TO_ANALYZE"
        assert workflow.snapshot().analysis_for("TITAN").state.value == "CHARTS_REQUIRED"
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_one_browser_analyze_action_processes_every_unique_instrument(tmp_path) -> None:  # type: ignore[no-untyped-def]
    workflow = SwingV1ReviewWorkflow(
        LocalTradingViewEvidenceStore(tmp_path, clock=lambda: _NOW),
        chart_evidence_provider=_BoundResponseProvider(),
        clock=lambda: _NOW,
    )
    workflow.publish_layer1(_classified_run({
        ("NAUKRI", V1Setup.PULLBACK_CONTINUATION),
        ("TITAN", V1Setup.PULLBACK_CONTINUATION),
    }))
    for instrument, image in (
        ("NAUKRI", _IMAGE),
        ("TITAN", b"\x89PNG\r\n\x1a\ntitan-chart"),
    ):
        workflow.upload(
            instrument=instrument,
            timeframe=ChartTimeframe.DAILY,
            content_type="image/png",
            original_bytes=image,
        )
    server, thread = _running_server(_ready(), v1_review=workflow)
    try:
        authority = f"127.0.0.1:{server.server_port}"
        status, headers, _ = _request(
            server,
            "POST",
            "/swing/v1/analyze",
            headers={"Host": authority, "Origin": f"http://{authority}"},
        )
        assert status == 303
        assert headers["Location"] == "/swing/v1-review"
        assert {
            item.canonical_instrument: item.state.value
            for item in workflow.snapshot().analyses
        } == {"NAUKRI": "ANALYSIS_COMPLETE", "TITAN": "ANALYSIS_COMPLETE"}
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_v2_batch_progress_and_completion_are_visible(tmp_path) -> None:  # type: ignore[no-untyped-def]
    provider = _BlockingV2Provider()
    workflow = SwingV1ReviewWorkflow(
        LocalTradingViewEvidenceStore(tmp_path, clock=lambda: _NOW),
        chart_analyst_v2_provider=provider,
        clock=lambda: _NOW,
    )
    workflow.publish_layer1(_classified_run({
        ("NAUKRI", V1Setup.PULLBACK_CONTINUATION),
        ("TITAN", V1Setup.PULLBACK_CONTINUATION),
    }), swing_analysis_run_identity=_PARENT_RUN)
    for instrument, image in (
        ("NAUKRI", _IMAGE),
        ("TITAN", b"\x89PNG\r\n\x1a\ntitan-chart"),
    ):
        workflow.upload(
            instrument=instrument,
            timeframe=ChartTimeframe.DAILY,
            content_type="image/png",
            original_bytes=image,
        )
    waiting = render_v1_review(_ready(), workflow.snapshot())
    assert "WAITING 0 / 2" in waiting
    assert waiting.count(">WAITING</span>") == 2

    analysis_thread = Thread(target=workflow.analyze_all_chart_context)
    analysis_thread.start()
    assert provider.entered.wait(timeout=2)
    running = render_v1_review(_ready(), workflow.snapshot())
    assert "ANALYZING 0 / 2" in running
    assert ">ANALYZING</span>" in running
    assert ">WAITING</span>" in running

    provider.release.set()
    analysis_thread.join(timeout=3)
    complete = render_v1_review(_ready(), workflow.snapshot())
    assert "2 / 2 ANALYZED" in complete
    assert complete.count(">ANALYZED</span>") == 2


def test_v2_incomplete_and_failure_are_visible_without_internals(tmp_path) -> None:  # type: ignore[no-untyped-def]
    provider = _BlockingV2Provider(outcomes={
        "TITAN": ChartAnalystV2FailureCode.INVALID_SCHEMA,
        "POWERGRID": ChartAnalystV2FailureCode.UNAVAILABLE,
    })
    provider.release.set()
    workflow = SwingV1ReviewWorkflow(
        LocalTradingViewEvidenceStore(tmp_path, clock=lambda: _NOW),
        chart_analyst_v2_provider=provider,
        clock=lambda: _NOW,
    )
    workflow.publish_layer1(_classified_run({
        ("NAUKRI", V1Setup.PULLBACK_CONTINUATION),
        ("TITAN", V1Setup.PULLBACK_CONTINUATION),
        ("POWERGRID", V1Setup.PULLBACK_CONTINUATION),
    }), swing_analysis_run_identity=_PARENT_RUN)
    for index, instrument in enumerate(("NAUKRI", "TITAN", "POWERGRID"), 1):
        workflow.upload(
            instrument=instrument,
            timeframe=ChartTimeframe.DAILY,
            content_type="image/png",
            original_bytes=b"\x89PNG\r\n\x1a\n" + bytes([index]),
        )
    workflow.analyze_all_chart_context()
    rendered = render_v1_review(_ready(), workflow.snapshot())
    assert "1 / 3 ANALYZED — 1 INCOMPLETE — 1 FAILED" in rendered
    assert ">CONTEXT INCOMPLETE</span>" in rendered
    assert ">ANALYSIS FAILED</span>" in rendered
    for forbidden in ("input_tokens", "output_tokens", "prompt", "api_key", "Traceback"):
        assert forbidden not in rendered


def test_analysis_status_endpoint_is_sanitized(tmp_path) -> None:  # type: ignore[no-untyped-def]
    workflow = SwingV1ReviewWorkflow(LocalTradingViewEvidenceStore(tmp_path))
    workflow.publish_layer1(_classified_run({
        ("NAUKRI", V1Setup.PULLBACK_CONTINUATION),
    }))
    server, thread = _running_server(_ready(), v1_review=workflow)
    try:
        status, _, body = _request(server, "GET", "/swing/v1/status")
        assert status == 200
        payload = __import__("json").loads(body)
        assert set(payload) == {"batch", "finished", "total", "complete", "instruments"}
        assert set(payload["instruments"][0]) == {"instrument", "status"}
        assert "token" not in body.lower()
        assert "prompt" not in body.lower()
        assert "credential" not in body.lower()
    finally:
        server.shutdown(); server.server_close(); thread.join()
