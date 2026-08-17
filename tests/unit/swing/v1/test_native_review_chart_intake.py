from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from kronos.application.swing_native_review import NativeReviewWorkflow
from kronos.swing.v1.evidence_store import (
    LocalTradingViewEvidenceStore,
    TradingViewEvidenceStoreError,
)
from kronos.swing.v1.chart_analyst_v2 import (
    ChartAnalystV2Error,
    ChartAnalystV2FailureCode,
)
from kronos.swing.v1.native_readiness import NativeReadinessState
from kronos.swing.v1.native_review import NativeReviewEvidenceStore
from kronos.swing.v1.tradingview import ChartTimeframe
from kronos.swing.v1.visual_evidence_v2 import (
    VisualEvidenceSubjectKind,
    VisualObservationStatus,
    VisualQuestionRouting,
    VisualQuestionV2,
)
from tests.unit.swing.v1.test_native_review import _evidence_run
from tests.unit.swing.v1.test_native_review_mcx_reference import _run_with_probables
from tests.unit.swing.v1.test_visual_evidence_v2 import _observation, _response


NOW = datetime(2026, 8, 16, 10, 0, tzinfo=UTC)


class _VisualV2Provider:
    provider_identity = "FIXTURE_VISUAL_V2"

    def __init__(self) -> None:
        self.requests = []

    def analyze(self, request):  # type: ignore[no-untyped-def]
        self.requests.append(request)
        replacements = {}
        for question, routing in request.routing:
            if routing is VisualQuestionRouting.YES:
                replacements[question] = _observation(
                    request,
                    question,
                    status=VisualObservationStatus.OBSERVED,
                    observation=(
                        "EXPECTED INSTRUMENT AND TIMEFRAME VISIBLE"
                        if question is VisualQuestionV2.VISUAL_CHART_VALIDATION
                        else "VISIBLE FACTUAL EVIDENCE"
                    ),
                )
        return _response(request, replacements)


class _FailGoldVisualV2Provider(_VisualV2Provider):
    def analyze(self, request):  # type: ignore[no-untyped-def]
        if request.requirement.canonical_instrument == "GOLDM":
            raise RuntimeError("fixture provider failure")
        return super().analyze(request)


class _InvalidSchemaVisualV2Provider(_VisualV2Provider):
    def analyze(self, request):  # type: ignore[no-untyped-def]
        self.requests.append(request)
        raise ChartAnalystV2Error(ChartAnalystV2FailureCode.INVALID_SCHEMA)


class _FailSecondRequestOnceVisualV2Provider(_VisualV2Provider):
    def __init__(self) -> None:
        super().__init__()
        self.failed = False

    def analyze(self, request):  # type: ignore[no-untyped-def]
        if len(self.requests) == 1 and not self.failed:
            self.failed = True
            self.requests.append(request)
            raise ChartAnalystV2Error(
                ChartAnalystV2FailureCode.UNAVAILABLE
            )
        return super().analyze(request)


def _workflow(tmp_path: Path, *, mcx: bool = False):  # type: ignore[no-untyped-def]
    if mcx:
        facts, run = _run_with_probables("GOLDM")
    else:
        facts, run, _ = _evidence_run()
    provider = _VisualV2Provider()
    chart_store = LocalTradingViewEvidenceStore(
        tmp_path / "shared-evidence", clock=lambda: NOW
    )
    workflow = NativeReviewWorkflow(
        NativeReviewEvidenceStore(tmp_path / "native-review"),
        chart_store=chart_store,
        visual_v2_provider=provider,
        clock=lambda: NOW,
    )
    workflow.prepare(run, facts)
    return workflow, provider, run


def _upload_native_composite(
    workflow: NativeReviewWorkflow, instrument: str
) -> None:
    workflow.upload_chart(
        instrument=instrument,
        content_type="image/png",
        original_bytes=b"\x89PNG\r\n\x1a\ncomposite",
    )


def test_one_composite_revision_binds_directly_and_routes_four_v2_timeframes(
    tmp_path: Path,
) -> None:
    workflow, provider, run = _workflow(tmp_path)
    requirement = workflow.snapshot().requirements[0]
    _upload_native_composite(workflow, requirement.canonical_instrument)

    snapshot = workflow.snapshot()
    assert len(snapshot.chart_packages) == 1
    package = snapshot.chart_packages[0]
    assert package.missing_required_timeframes == ()
    assert len(package.active_revisions) == 1
    assert package.active_revisions[0].timeframe is ChartTimeframe.COMPOSITE
    assert package.binding.native_run_identity == run.run_identity
    assert package.binding.native_assessment_sha256 == (
        requirement.thesis.native_assessment_sha256
    )
    assert package.binding.subject_kind == "NATIVE"
    assert not hasattr(package.binding, "layer1_assessment")
    assert not hasattr(package.binding, "daily_control_probable_identity")
    assert all(
        item.swing_analysis_run_identity == run.run_identity
        for item in package.active_revisions
    )

    result = workflow.analyze(requirement.canonical_instrument)

    assert len(provider.requests) == 4
    assert {item.timeframe.value for item in provider.requests} == {
        "1W", "1D", "4H", "1H"
    }
    assert all(
        item.question_set_identity == "SWING-V1-VISUAL-QUESTION-SET-V2"
        for item in provider.requests
    )
    assert len({item.chart_revision_sha256 for item in provider.requests}) == 1
    assert len({item.chart_identity for item in provider.requests}) == 1
    assert result.readiness is NativeReadinessState.READY_FOR_TRADE_CONSTRUCTION
    assert workflow.step31_eligible_readiness() == (result,)
    assert len(workflow.snapshot().visual_v2_results) == 4
    assert len(workflow.snapshot().layer2_records) == 1


def test_missing_composite_wrong_instrument_and_revision_fail_closed(
    tmp_path: Path,
) -> None:
    workflow, provider, _ = _workflow(tmp_path)
    instrument = workflow.snapshot().requirements[0].canonical_instrument
    assert not workflow.analysis_binding_valid(instrument)
    with pytest.raises(ValueError, match="REQUIRED_CHARTS_MISSING"):
        workflow.analyze(instrument)
    assert provider.requests == []
    workflow.upload_chart(
        instrument=instrument,
        content_type="image/png",
        original_bytes=b"\x89PNG\r\n\x1a\none",
    )
    assert workflow.analysis_binding_valid(instrument)
    with pytest.raises(ValueError, match="REQUIREMENT_UNAVAILABLE"):
        workflow.upload_chart(
            instrument="WRONG",
            content_type="image/png",
            original_bytes=b"\x89PNG\r\n\x1a\nwrong",
        )
    with pytest.raises((ValueError, TradingViewEvidenceStoreError)):
        workflow.active_chart(
            instrument=instrument,
            sha256="f" * 64,
        )


def test_non_ready_result_never_enters_step31(tmp_path: Path) -> None:
    workflow, provider, _ = _workflow(tmp_path)
    instrument = workflow.snapshot().requirements[0].canonical_instrument
    _upload_native_composite(workflow, instrument)

    original = provider.analyze

    def incomplete(request):  # type: ignore[no-untyped-def]
        response = original(request)
        if request.timeframe.value == "4H":
            validation = next(
                item for item in response.observations
                if item.question_id is VisualQuestionV2.VISUAL_CHART_VALIDATION
            )
            response = replace(
                response,
                observations=tuple(
                    replace(
                        item,
                        observation_status=VisualObservationStatus.PARTIAL,
                        observation="CHART PARTIALLY READABLE",
                        ambiguity_reason="IDENTITY NOT FULLY VISIBLE",
                    )
                    if item is validation else item
                    for item in response.observations
                ),
            )
        return response

    provider.analyze = incomplete
    result = workflow.analyze(instrument)
    assert result.readiness is NativeReadinessState.CONTEXT_INCOMPLETE
    assert workflow.step31_eligible_readiness() == ()


def test_mcx_one_upload_binds_native_and_approved_reference_roles(tmp_path: Path) -> None:
    workflow, provider, _ = _workflow(tmp_path, mcx=True)
    requirement = workflow.snapshot().requirements[0]
    packages = workflow.snapshot().chart_packages
    assert len(packages) == 2
    native = next(item for item in packages if item.binding.subject_kind == "NATIVE")
    reference = next(
        item for item in packages if item.binding.subject_kind == "REFERENCE"
    )
    assert native.binding.canonical_instrument == "GOLDM"
    assert reference.binding.chart_subject_identity == "COMEX:GC1!"
    assert reference.binding.required_timeframes == (ChartTimeframe.DAILY,)
    workflow.upload_chart(
        instrument="GOLDM",
        content_type="image/png",
        original_bytes=b"\x89PNG\r\n\x1a\nmcx-composite",
    )
    packages = workflow.snapshot().chart_packages
    native = next(item for item in packages if item.binding.subject_kind == "NATIVE")
    reference = next(item for item in packages if item.binding.subject_kind == "REFERENCE")
    assert native.active_revisions[0].sha256 == reference.active_revisions[0].sha256
    assert (
        native.active_revisions[0].relative_path
        == reference.active_revisions[0].relative_path
    )
    assert workflow.analysis_binding_valid("GOLDM")
    workflow.analyze("GOLDM")
    assert len(provider.requests) == 5
    assert len({item.chart_revision_sha256 for item in provider.requests}) == 1
    with pytest.raises(ValueError, match="MCX_REFERENCE_NOT_REQUIRED"):
        nse, _, _ = _workflow(tmp_path / "nse")
        nse.upload_chart(
            instrument=nse.snapshot().requirements[0].canonical_instrument,
            subject_kind=VisualEvidenceSubjectKind.REFERENCE,
            content_type="image/png",
            original_bytes=b"\x89PNG\r\n\x1a\nreference",
        )


def test_analyze_all_processes_complete_candidate_and_skips_missing_independently(
    tmp_path: Path,
) -> None:
    facts, run = _run_with_probables("GOLDM", "CRUDEOIL")
    provider = _VisualV2Provider()
    workflow = NativeReviewWorkflow(
        NativeReviewEvidenceStore(tmp_path / "native-review"),
        chart_store=LocalTradingViewEvidenceStore(tmp_path / "charts"),
        visual_v2_provider=provider,
        clock=lambda: NOW,
    )
    workflow.prepare(run, facts)
    workflow.upload_chart(
        instrument="GOLDM",
        content_type="image/png",
        original_bytes=b"\x89PNG\r\n\x1a\ngoldm",
    )
    outcomes = workflow.analyze_all()

    assert [(item.canonical_instrument, item.disposition) for item in outcomes] == [
        ("GOLDM", "SUCCESS"),
        ("CRUDEOIL", "SKIPPED"),
    ]
    assert len(provider.requests) == 5
    snapshot = workflow.snapshot()
    assert len(snapshot.readiness_records) == 1
    assert snapshot.readiness_records[0].canonical_instrument == "GOLDM"


def test_analyze_all_failure_does_not_hide_other_candidate_or_fabricate_review(
    tmp_path: Path,
) -> None:
    facts, run = _run_with_probables("GOLDM", "CRUDEOIL")
    provider = _FailGoldVisualV2Provider()
    workflow = NativeReviewWorkflow(
        NativeReviewEvidenceStore(tmp_path / "native-review"),
        chart_store=LocalTradingViewEvidenceStore(tmp_path / "charts"),
        visual_v2_provider=provider,
        clock=lambda: NOW,
    )
    workflow.prepare(run, facts)
    for instrument in ("GOLDM", "CRUDEOIL"):
        workflow.upload_chart(
            instrument=instrument,
            content_type="image/png",
            original_bytes=b"\x89PNG\r\n\x1a\n" + instrument.encode(),
        )

    outcomes = workflow.analyze_all()

    assert [(item.canonical_instrument, item.disposition) for item in outcomes] == [
        ("GOLDM", "FAILED"),
        ("CRUDEOIL", "SUCCESS"),
    ]
    snapshot = workflow.snapshot()
    assert {item.canonical_instrument for item in snapshot.readiness_records} == {
        "CRUDEOIL"
    }


def test_provider_schema_failure_is_sanitized_and_never_fabricates_readiness(
    tmp_path: Path,
) -> None:
    facts, run, probable = _evidence_run()
    provider = _InvalidSchemaVisualV2Provider()
    workflow = NativeReviewWorkflow(
        NativeReviewEvidenceStore(tmp_path / "native-review"),
        chart_store=LocalTradingViewEvidenceStore(tmp_path / "charts"),
        visual_v2_provider=provider,
        clock=lambda: NOW,
    )
    workflow.prepare(run, facts)
    _upload_native_composite(workflow, probable.canonical_instrument)

    with pytest.raises(ChartAnalystV2Error):
        workflow.analyze(probable.canonical_instrument)

    snapshot = workflow.snapshot()
    assert snapshot.readiness_records == ()
    assert snapshot.analysis_outcomes[0].state.value == "ANALYSIS_FAILED"
    assert snapshot.analysis_outcomes[0].sponsor_reason == (
        "SCHEMA VALIDATION FAILED"
    )
    assert "CHART_ANALYST_V2_SCHEMA_INVALID" not in (
        snapshot.analysis_outcomes[0].sponsor_reason
    )


def test_retry_reuses_persisted_timeframe_and_requests_only_missing_evidence(
    tmp_path: Path,
) -> None:
    facts, run, probable = _evidence_run()
    provider = _FailSecondRequestOnceVisualV2Provider()
    workflow = NativeReviewWorkflow(
        NativeReviewEvidenceStore(tmp_path / "native-review"),
        chart_store=LocalTradingViewEvidenceStore(tmp_path / "charts"),
        visual_v2_provider=provider,
        clock=lambda: NOW,
    )
    workflow.prepare(run, facts)
    _upload_native_composite(workflow, probable.canonical_instrument)

    with pytest.raises(ChartAnalystV2Error):
        workflow.analyze(probable.canonical_instrument)
    assert len(workflow.snapshot().visual_v2_results) == 1
    assert [request.timeframe.value for request in provider.requests] == [
        "1W",
        "1D",
    ]

    result = workflow.analyze(probable.canonical_instrument)

    assert result.readiness is NativeReadinessState.READY_FOR_TRADE_CONSTRUCTION
    assert [request.timeframe.value for request in provider.requests] == [
        "1W",
        "1D",
        "1D",
        "4H",
        "1H",
    ]
    assert len(workflow.snapshot().visual_v2_results) == 4
