from __future__ import annotations

from hashlib import sha256
from datetime import timedelta

import pytest

from kronos.application import swing_opportunities as opportunities
from kronos.application.swing_v1_review import SwingV1ReviewWorkflow
from kronos.swing.run_identity import LEGACY_UNBOUND_SWING_RUN_ID
from kronos.swing.v1.chart_analyst_v2 import ChartAnalystV2Response
from kronos.swing.v1.evidence_store import LocalTradingViewEvidenceStore
from kronos.swing.v1.models import V1Setup
from kronos.swing.v1.tradingview import ChartTimeframe
from tests.unit.swing.v1.test_chart_analyst_v2 import _analysis
from tests.unit.swing.v1.test_swing_v1_slice3 import _classified_run
from tests.unit.swing.v1.test_swing_v1_slice4 import _IMAGE, _NOW
from tests.unit.application.test_swing_opportunities import (
    _Provider,
    _immediate,
    _real_completed,
)


_PARENT_A = "SWING-RUN-0000000000000000000000000000000A"
_PARENT_B = "SWING-RUN-0000000000000000000000000000000B"


class _CountingV2Provider:
    provider_identity = "OPENAI_CHART_ANALYST_V2_PROVIDER"

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
            analysis=_analysis(request),
        )


def _run(*instruments: str):  # type: ignore[no-untyped-def]
    return _classified_run({
        (instrument, V1Setup.PULLBACK_CONTINUATION)
        for instrument in instruments
    })


def _upload(workflow: SwingV1ReviewWorkflow, instrument: str = "NAUKRI") -> str:
    revision = workflow.upload(
        instrument=instrument,
        timeframe=ChartTimeframe.DAILY,
        content_type="image/png",
        original_bytes=_IMAGE,
    )
    return revision.sha256


def test_same_parent_can_own_distinct_v0_and_v1_projection_identities(tmp_path) -> None:  # type: ignore[no-untyped-def]
    run = _run("NAUKRI")
    workflow = SwingV1ReviewWorkflow(LocalTradingViewEvidenceStore(tmp_path))
    review = workflow.publish_layer1(
        run,
        swing_analysis_run_identity=_PARENT_A,
    )

    assert review.swing_analysis_run_identity == _PARENT_A
    assert review.layer1_run.run_identity != "ANALYSIS-000001"
    assert review.requirements[0].swing_analysis_run_identity == _PARENT_A


def test_every_refresh_analysis_allocates_a_new_parent_run(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    allocated = iter((_PARENT_A, _PARENT_B))
    captured: list[str] = []
    application = opportunities.SwingOpportunitiesApplication(
        _Provider,
        background_runner=_immediate,
        swing_run_identity_factory=lambda: next(allocated),
    )
    assert application.connect_provider()

    def fail_after_capture(*_args, **kwargs):  # type: ignore[no-untyped-def]
        captured.append(kwargs["swing_analysis_run_identity"])
        raise RuntimeError("SAFE_TEST_FAILURE")

    monkeypatch.setattr(
        opportunities,
        "build_completed_swing_analysis",
        fail_after_capture,
    )
    assert application.run_analysis()
    assert application.run_analysis()
    assert captured == [_PARENT_A, _PARENT_B]


def test_every_refresh_records_a_new_execution_time_independent_of_boundary(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    timestamps = iter((_NOW, _NOW, _NOW + timedelta(minutes=44), _NOW))
    captured = []
    application = opportunities.SwingOpportunitiesApplication(
        _Provider,
        clock=lambda: next(timestamps),
        background_runner=_immediate,
        swing_run_identity_factory=iter((_PARENT_A, _PARENT_B)).__next__,
    )
    assert application.connect_provider()

    def fail_after_capture(*_args, **kwargs):  # type: ignore[no-untyped-def]
        captured.append((
            kwargs["swing_analysis_run_identity"],
            kwargs["run_created_at"],
            kwargs["now"],
        ))
        raise RuntimeError("SAFE_TEST_FAILURE")

    monkeypatch.setattr(
        opportunities,
        "build_completed_swing_analysis",
        fail_after_capture,
    )
    assert application.run_analysis()
    assert application.run_analysis()

    assert captured == [
        (_PARENT_A, _NOW, _NOW),
        (_PARENT_B, _NOW + timedelta(minutes=44), _NOW + timedelta(minutes=44)),
    ]


def test_active_opportunities_and_review_share_exact_v1_projection(
    monkeypatch,
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    completed = _real_completed(monkeypatch)
    evidence = completed.evidence
    workspace = completed.workspace
    workflow = SwingV1ReviewWorkflow(LocalTradingViewEvidenceStore(tmp_path))

    review = workflow.prepare_layer1_run(
        evidence.v1_layer1_run,
        swing_analysis_run_identity=evidence.swing_analysis_run_identity,
    )

    assert workspace.swing_analysis_run_identity == review.swing_analysis_run_identity
    assert workspace.v1_layer1_run_identity == review.layer1_run.run_identity
    assert tuple(item.instrument for item in workspace.v1_probables) == tuple(
        item.canonical_instrument for item in review.requirements
    )


def test_review_is_immutable_until_explicit_latest_load_and_old_chart_survives(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    store = LocalTradingViewEvidenceStore(tmp_path, clock=lambda: _NOW)
    workflow = SwingV1ReviewWorkflow(store)
    first = _run("NAUKRI")
    second = _run("TITAN")
    workflow.publish_layer1(first, swing_analysis_run_identity=_PARENT_A)
    image_hash = _upload(workflow)

    with pytest.raises(ValueError, match="V1_REVIEW_IMMUTABLE_RUN"):
        workflow.publish_layer1(second, swing_analysis_run_identity=_PARENT_B)
    assert workflow.snapshot().requirements[0].canonical_instrument == "NAUKRI"
    assert workflow.snapshot().packages[0].active_revisions[0].sha256 == image_hash

    workflow.load_latest_layer1(second, swing_analysis_run_identity=_PARENT_B)
    assert workflow.snapshot().requirements[0].canonical_instrument == "TITAN"
    restarted_old = SwingV1ReviewWorkflow(store)
    recovered = restarted_old.publish_layer1(
        first,
        swing_analysis_run_identity=_PARENT_A,
    )
    assert recovered.packages[0].active_revisions[0].sha256 == image_hash


def test_parent_scoped_store_rejects_cross_run_chart_inheritance(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = LocalTradingViewEvidenceStore(tmp_path, clock=lambda: _NOW)
    run = _run("NAUKRI")
    first = SwingV1ReviewWorkflow(store)
    first.publish_layer1(run, swing_analysis_run_identity=_PARENT_A)
    assert _upload(first) == sha256(_IMAGE).hexdigest()

    second = SwingV1ReviewWorkflow(store)
    review = second.publish_layer1(run, swing_analysis_run_identity=_PARENT_B)
    assert review.packages[0].active_revisions == ()
    assert review.packages[0].missing_required_timeframes == (ChartTimeframe.DAILY,)


def test_openai_cannot_start_for_legacy_unbound_review(tmp_path) -> None:  # type: ignore[no-untyped-def]
    provider = _CountingV2Provider()
    workflow = SwingV1ReviewWorkflow(
        LocalTradingViewEvidenceStore(tmp_path, clock=lambda: _NOW),
        chart_analyst_v2_provider=provider,
        clock=lambda: _NOW,
    )
    workflow.publish_layer1(
        _run("NAUKRI"),
        swing_analysis_run_identity=LEGACY_UNBOUND_SWING_RUN_ID,
    )
    _upload(workflow)

    with pytest.raises(ValueError, match="CHART_ANALYST_V2_RUN_BINDING_INVALID"):
        workflow.analyze_chart_context("NAUKRI")
    assert provider.calls == 0


def test_openai_request_and_result_retain_parent_projection_chart_binding(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    provider = _CountingV2Provider()
    workflow = SwingV1ReviewWorkflow(
        LocalTradingViewEvidenceStore(tmp_path, clock=lambda: _NOW),
        chart_analyst_v2_provider=provider,
        clock=lambda: _NOW,
    )
    run = _run("NAUKRI")
    workflow.publish_layer1(run, swing_analysis_run_identity=_PARENT_A)
    image_hash = _upload(workflow)

    result = workflow.analyze_chart_context("NAUKRI")

    assert provider.calls == 1
    assert result.v2_evidence is not None
    assert result.v2_evidence.swing_analysis_run_identity == _PARENT_A
    assert result.v2_evidence.run_identity == run.run_identity
    assert result.v2_evidence.instrument == "NAUKRI"
    assert result.v2_evidence.image_sha256 == image_hash
