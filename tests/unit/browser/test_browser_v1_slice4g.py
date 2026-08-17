from dataclasses import asdict, replace
from datetime import UTC, datetime
import pytest

from kronos.application.swing_v1_review import (
    STEP31_V1_HANDOFF_SCHEMA_ID,
    ChartAnalysisState,
    SwingV1ReviewWorkflow,
)
from kronos.browser.views import render_legacy_opportunities, render_v1_review
from kronos.swing.v1.chart_analyst_v2 import (
    OPENAI_CHART_ANALYST_V2_PROVIDER_ID,
    ChartAnalystV2Response,
)
from kronos.swing.v1.evidence_store import LocalTradingViewEvidenceStore
from kronos.swing.v1.layer2 import ReadinessState
from kronos.swing.v1.models import V1Setup
from kronos.swing.v1.tradingview import ChartTimeframe
from tests.unit.application.test_swing_opportunities import _ready
from tests.unit.browser.test_browser_views import _v1_probable
from tests.unit.swing.v1.test_chart_analyst_v2_layer2 import _valid_analysis
from tests.unit.swing.v1.test_swing_v1_slice3 import _classified_run


_NOW = datetime(2026, 8, 13, 5, 1, tzinfo=UTC)
_PARENT_RUN = "SWING-RUN-0000000000000000000000000000004A"
_IMAGE_A = b"\x89PNG\r\n\x1a\n4g-four-chart-a"
_IMAGE_B = b"\x89PNG\r\n\x1a\n4g-four-chart-b"


class _V2Provider:
    provider_identity = OPENAI_CHART_ANALYST_V2_PROVIDER_ID
    model_configured = True
    question_set_available = True
    configuration_ready = True

    def __init__(
        self,
        *,
        extended: frozenset[str] = frozenset(),
        invalid_integrity: frozenset[str] = frozenset(),
    ) -> None:
        self.calls = []
        self.extended = extended
        self.invalid_integrity = invalid_integrity

    def analyze(self, request):  # type: ignore[no-untyped-def]
        self.calls.append(request)
        analysis = _valid_analysis(request.instrument, request.product)
        analysis["image_sha256"] = request.image_sha256
        if request.instrument in self.extended:
            analysis["overall_observation"]["setup_phase"] = "EXTENDED"
            analysis["timeframes"]["1D"][
                "maturity_extension_chase_risk"
            ]["move_maturity"] = "EXTENDED"
        if request.instrument in self.invalid_integrity:
            analysis["timeframes"]["1D"]["pine_workstation"]["trend"] = (
                "NOT A VALID WORKSTATION TRANSCRIPTION"
            )
        return ChartAnalystV2Response(
            provider_identity=self.provider_identity,
            model_identity="gpt-test",
            request_timestamp=request.request_timestamp,
            run_identity=request.run_identity,
            swing_analysis_run_identity=request.swing_analysis_run_identity,
            analysis=analysis,
        )


def _workflow(tmp_path, provider, instruments=("NAUKRI",)):  # type: ignore[no-untyped-def]
    run = _classified_run({
        (instrument, V1Setup.PULLBACK_CONTINUATION)
        for instrument in instruments
    })
    workflow = SwingV1ReviewWorkflow(
        LocalTradingViewEvidenceStore(tmp_path, clock=lambda: _NOW),
        chart_analyst_v2_provider=provider,
        clock=lambda: _NOW,
    )
    workflow.publish_layer1(
        run,
        swing_analysis_run_identity=_PARENT_RUN,
    )
    return run, workflow


def test_fresh_run_keeps_opportunities_review_and_run_times_consistent(tmp_path) -> None:  # type: ignore[no-untyped-def]
    _, workflow = _workflow(tmp_path, _V2Provider(), ("NAUKRI", "TITAN"))
    snapshot = replace(
        _ready(),
        swing_analysis_run_identity=_PARENT_RUN,
        run_created_at=_NOW,
        completed_at=_NOW,
        observation_boundary=workflow.snapshot().layer1_run.observation_boundary,
        v1_probables=(_v1_probable("NAUKRI"), _v1_probable("TITAN")),
    )

    opportunities = render_legacy_opportunities(snapshot)
    review = render_v1_review(snapshot, workflow.snapshot())

    assert {item.instrument for item in snapshot.v1_probables} == {
        item.canonical_instrument for item in workflow.snapshot().requirements
    }
    assert "LAST SUCCESSFUL ANALYSIS · 13 AUG 2026 10:31 IST" in review
    assert "RUN 0000004A" not in review
    assert "ANALYSIS BOUNDARY" not in review
    assert "NAUKRI" in opportunities and "NAUKRI" in review


def test_four_chart_intake_replacement_hashing_and_cache_reuse(tmp_path) -> None:  # type: ignore[no-untyped-def]
    provider = _V2Provider()
    _, workflow = _workflow(tmp_path, provider)
    first = workflow.upload(
        instrument="NAUKRI",
        timeframe=ChartTimeframe.DAILY,
        content_type="image/png",
        original_bytes=_IMAGE_A,
    )
    workflow.analyze_all_chart_context()
    workflow.analyze_all_chart_context()

    assert len(provider.calls) == 1
    assert workflow.snapshot().analysis_for("NAUKRI").state is (
        ChartAnalysisState.ANALYSIS_COMPLETE
    )

    second = workflow.upload(
        instrument="NAUKRI",
        timeframe=ChartTimeframe.DAILY,
        content_type="image/png",
        original_bytes=_IMAGE_B,
    )
    assert second.sha256 != first.sha256
    assert workflow.snapshot().analysis_for("NAUKRI").state is (
        ChartAnalysisState.READY_TO_ANALYZE
    )
    workflow.analyze_all_chart_context()
    assert len(provider.calls) == 2


def test_successful_4f_result_is_compact_and_has_no_openai_authority_leakage(tmp_path) -> None:  # type: ignore[no-untyped-def]
    _, workflow = _workflow(tmp_path, _V2Provider())
    workflow.upload(
        instrument="NAUKRI",
        timeframe=ChartTimeframe.DAILY,
        content_type="image/png",
        original_bytes=_IMAGE_A,
    )
    workflow.analyze_all_chart_context()

    rendered = render_v1_review(_ready(), workflow.snapshot())

    for expected in (
        "4-CHART",
        "1W · 1D · 4H · 1H",
        "Pullback Continuation LONG",
        "SUPPORTIVE",
        "READY FOR TRADE CONSTRUCTION",
        "ALL CANDIDATE READINESS CONTEXT SUPPORTS PROGRESSION",
        "READY FOR TRADE PLAN",
        "SHADOW / VALIDATION ONLY",
    ):
        assert expected in rendered
    assert ">DAILY<" not in rendered
    for forbidden in (
        "pine_vs_chart",
        "thesis_behaviour",
        "BUY NOW",
        "SELL NOW",
        "raw JSON",
        "input_tokens",
        "Entry",
        "Stop",
        "Target",
        "R:R",
    ):
        assert forbidden not in rendered


def test_integrity_failure_is_actionable_context_incomplete_without_exception(tmp_path) -> None:  # type: ignore[no-untyped-def]
    _, workflow = _workflow(
        tmp_path,
        _V2Provider(invalid_integrity=frozenset({"NAUKRI"})),
    )
    workflow.upload(
        instrument="NAUKRI",
        timeframe=ChartTimeframe.DAILY,
        content_type="image/png",
        original_bytes=_IMAGE_A,
    )

    workflow.analyze_all_chart_context()
    rendered = render_v1_review(_ready(), workflow.snapshot())

    assert workflow.snapshot().analysis_for("NAUKRI").state is (
        ChartAnalysisState.CONTEXT_INCOMPLETE
    )
    assert "CHART EVIDENCE INVALID" in rendered
    assert "REPLACE CHART" in rendered
    assert "Traceback" not in rendered


def test_restart_recovers_chart_hash_4f_reconciliation_and_readiness(tmp_path) -> None:  # type: ignore[no-untyped-def]
    provider = _V2Provider()
    run, workflow = _workflow(tmp_path, provider)
    revision = workflow.upload(
        instrument="NAUKRI",
        timeframe=ChartTimeframe.DAILY,
        content_type="image/png",
        original_bytes=_IMAGE_A,
    )
    workflow.analyze_all_chart_context()

    restarted = SwingV1ReviewWorkflow(
        LocalTradingViewEvidenceStore(tmp_path, clock=lambda: _NOW),
        chart_analyst_v2_provider=provider,
        clock=lambda: _NOW,
    )
    parent, recovered_run = LocalTradingViewEvidenceStore(
        tmp_path, clock=lambda: _NOW
    ).latest_review_run()
    assert parent == _PARENT_RUN
    assert recovered_run == run
    recovered = restarted.publish_layer1(
        recovered_run,
        swing_analysis_run_identity=parent,
    )

    assert recovered.packages[0].active_revisions[0].sha256 == revision.sha256
    assert recovered.analyses[0].state is ChartAnalysisState.ANALYSIS_COMPLETE
    assert recovered.analyses[0].v2_layer2 is not None
    assert recovered.analyses[0].readiness.state is (
        ReadinessState.READY_FOR_TRADE_CONSTRUCTION
    )
    restarted.analyze_all_chart_context()
    assert len(provider.calls) == 1


def test_new_run_does_not_destroy_old_chart_bound_review(tmp_path) -> None:  # type: ignore[no-untyped-def]
    provider = _V2Provider()
    old_run, old = _workflow(tmp_path, provider)
    old.upload(
        instrument="NAUKRI",
        timeframe=ChartTimeframe.DAILY,
        content_type="image/png",
        original_bytes=_IMAGE_A,
    )
    old.analyze_all_chart_context()

    new_parent = "SWING-RUN-0000000000000000000000000000004B"
    new_run = _classified_run({("TITAN", V1Setup.PULLBACK_CONTINUATION)})
    with pytest.raises(ValueError, match="V1_REVIEW_IMMUTABLE_RUN"):
        old.publish_layer1(new_run, swing_analysis_run_identity=new_parent)
    assert LocalTradingViewEvidenceStore(
        tmp_path, clock=lambda: _NOW
    ).latest_review_run()[0] == _PARENT_RUN
    old.load_latest_layer1(new_run, swing_analysis_run_identity=new_parent)
    assert old.snapshot().requirements[0].canonical_instrument == "TITAN"
    assert old.snapshot().packages[0].active_revisions == ()

    recovered_old = SwingV1ReviewWorkflow(
        LocalTradingViewEvidenceStore(tmp_path, clock=lambda: _NOW),
        chart_analyst_v2_provider=provider,
        clock=lambda: _NOW,
    )
    recovered_old.publish_layer1(
        old_run,
        swing_analysis_run_identity=_PARENT_RUN,
    )
    assert recovered_old.snapshot().analyses[0].state is (
        ChartAnalysisState.ANALYSIS_COMPLETE
    )


def test_step31_handoff_contains_only_v1_ready_shadow_eligibility(tmp_path) -> None:  # type: ignore[no-untyped-def]
    provider = _V2Provider(extended=frozenset({"TITAN"}))
    _, workflow = _workflow(tmp_path, provider, ("NAUKRI", "TITAN"))
    for instrument, image in (("NAUKRI", _IMAGE_A), ("TITAN", _IMAGE_B)):
        workflow.upload(
            instrument=instrument,
            timeframe=ChartTimeframe.DAILY,
            content_type="image/png",
            original_bytes=image,
        )
    workflow.analyze_all_chart_context()

    handoff = workflow.step31_eligibility_handoff()
    payload = asdict(handoff)

    assert handoff.schema_identity == STEP31_V1_HANDOFF_SCHEMA_ID
    assert handoff.operational_authority == "SHADOW / VALIDATION ONLY"
    assert tuple(item.canonical_instrument for item in handoff.eligible_instruments) == (
        "NAUKRI",
    )
    assert handoff.eligible_instruments[0].readiness_state is (
        ReadinessState.READY_FOR_TRADE_CONSTRUCTION
    )
    for forbidden in ("entry", "stop", "target", "risk_reward", "rank", "webhook"):
        assert forbidden not in str(payload).lower()
