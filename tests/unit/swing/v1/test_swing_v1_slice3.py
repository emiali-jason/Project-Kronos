from dataclasses import replace
from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from kronos.application.swing_v1_review import (
    SwingV1ReviewWorkflow,
    V1ReviewRunState,
)
from kronos.swing.v1 import (
    ChartTimeframe,
    DEFAULT_TRADINGVIEW_CHART_TEMPLATE,
    EvidenceAvailability,
    LocalTradingViewEvidenceStore,
    ProbableClassification,
    ReconciliationState,
    TradingViewContextGateState,
    TradingViewContextPolicy,
    TradingViewIndicator,
    TradingViewReviewStatus,
    V1Direction,
    V1Setup,
    analyze_v1_layer1,
    build_tradingview_review_requirements,
    pending_layer2_evidence,
)
from kronos.swing.v1.evidence_store import TradingViewEvidenceStoreError
from tests.unit.swing.v1.test_swing_v1_layer1 import _dataset


_NOW = datetime(2026, 8, 12, 15, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
_PNG_A = b"\x89PNG\r\n\x1a\noriginal-chart-a"
_PNG_B = b"\x89PNG\r\n\x1a\nreplacement-chart-b"
_FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "fixtures"
    / "swing"
    / "v1"
    / "same98_tradingview_requirements.json"
)


def _classified_run(
    probable: set[tuple[str, V1Setup]],
):  # type: ignore[no-untyped-def]
    run = analyze_v1_layer1(_dataset())
    instruments = []
    for instrument in run.instruments:
        assessments = []
        for assessment in instrument.assessments:
            if (instrument.canonical_identity, assessment.setup) in probable:
                assessments.append(
                    replace(assessment, direction=V1Direction.SHORT)
                    if instrument.canonical_identity == "ADANIPORTS"
                    else assessment
                )
            else:
                assessments.append(replace(
                    assessment,
                    classification=ProbableClassification.NOT_SUPPORTED,
                    reconciliation=ReconciliationState.FAILED,
                    context_gate=TradingViewContextGateState.NOT_ELIGIBLE_UNLESS_PROBABLE,
                ))
        instruments.append(replace(instrument, assessments=tuple(assessments)))
    return replace(run, instruments=tuple(instruments))


def _same98_reference_run():  # type: ignore[no-untyped-def]
    return _classified_run({
        ("NAUKRI", V1Setup.PULLBACK_CONTINUATION),
        ("NAUKRI", V1Setup.CONSOLIDATION_BREAKOUT),
        ("TITAN", V1Setup.PULLBACK_CONTINUATION),
        ("TITAN", V1Setup.CONSOLIDATION_BREAKOUT),
        ("ADANIPORTS", V1Setup.PULLBACK_CONTINUATION),
    })


def test_same98_fixture_collapses_five_assessments_to_three_requests() -> None:
    expected = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    run = _same98_reference_run()
    requirements = build_tradingview_review_requirements(run)

    assert run.probable_count == expected["probable_assessment_count"] == 5
    assert len(requirements) == expected["unique_probable_instrument_count"] == 3
    assert [item.canonical_instrument for item in requirements] == [
        "NAUKRI",
        "TITAN",
        "ADANIPORTS",
    ]
    actual = {
        item.canonical_instrument: {
            f"{link.setup.value}|{link.direction.value}"
            for link in item.probable_setups
        }
        for item in requirements
    }
    assert actual == {
        item["instrument"]: set(item["setups"])
        for item in expected["requirements"]
    }
    assert all(item.required_timeframes == (ChartTimeframe.DAILY,) for item in requirements)


@pytest.mark.parametrize(
    "classification,reconciliation",
    (
        (ProbableClassification.NOT_SUPPORTED, ReconciliationState.FAILED),
        (ProbableClassification.POLICY_UNRESOLVED, ReconciliationState.POLICY_UNRESOLVED),
        (ProbableClassification.EVIDENCE_INCOMPLETE, ReconciliationState.EVIDENCE_INCOMPLETE),
    ),
)
def test_non_probable_classifications_never_request_tradingview(
    classification: ProbableClassification,
    reconciliation: ReconciliationState,
) -> None:
    run = _classified_run(set())
    first = run.instruments[0]
    altered = replace(
        first.assessments[0],
        classification=classification,
        reconciliation=reconciliation,
        context_gate=TradingViewContextGateState.NOT_ELIGIBLE_UNLESS_PROBABLE,
    )
    run = replace(
        run,
        instruments=(replace(first, assessments=(altered, first.assessments[1])), *run.instruments[1:]),
    )
    assert build_tradingview_review_requirements(run) == ()


def test_daily_is_required_and_supporting_timeframes_are_explicitly_configurable() -> None:
    run = _classified_run({("NAUKRI", V1Setup.PULLBACK_CONTINUATION)})
    default = build_tradingview_review_requirements(run)[0]
    supported = build_tradingview_review_requirements(
        run,
        context_policy=TradingViewContextPolicy((ChartTimeframe.FOUR_HOUR,)),
    )[0]
    assert default.required_timeframes == (ChartTimeframe.DAILY,)
    assert supported.required_timeframes == (
        ChartTimeframe.DAILY,
        ChartTimeframe.FOUR_HOUR,
    )


def test_template_uses_indicator_semantics_and_structured_pine_is_separate() -> None:
    template = DEFAULT_TRADINGVIEW_CHART_TEMPLATE
    assert template.colour_is_semantic_identity is False
    assert tuple(item.indicator for item in template.indicators) == tuple(TradingViewIndicator)
    assert next(item for item in template.indicators if item.indicator is TradingViewIndicator.SMA50).cosmetic_colour == "RED"
    assert next(item for item in template.indicators if item.indicator is TradingViewIndicator.SMA200).cosmetic_colour == "WHITE"

    requirement = build_tradingview_review_requirements(_same98_reference_run())[0]
    structured = pending_layer2_evidence(requirement)
    assert structured.pine_display.availability is EvidenceAvailability.UNAVAILABLE
    assert len(structured.moving_averages) == 3
    assert structured.price_structure is not structured.pine_display
    assert not hasattr(structured, "score")


def test_upload_binding_original_preservation_revisions_and_duplicate_handling(
    tmp_path: Path,
) -> None:
    requirement = build_tradingview_review_requirements(_same98_reference_run())[0]
    store = LocalTradingViewEvidenceStore(tmp_path, clock=lambda: _NOW)

    with pytest.raises(TradingViewEvidenceStoreError, match="INSTRUMENT_BINDING_MISMATCH"):
        store.retain_upload(
            requirement,
            selected_instrument="TITAN",
            selected_timeframe=ChartTimeframe.DAILY,
            content_type="image/png",
            original_bytes=_PNG_A,
        )
    with pytest.raises(TradingViewEvidenceStoreError, match="TIMEFRAME_NOT_REQUESTED"):
        store.retain_upload(
            requirement,
            selected_instrument=requirement.canonical_instrument,
            selected_timeframe=ChartTimeframe.ONE_HOUR,
            content_type="image/png",
            original_bytes=_PNG_A,
        )

    first = store.retain_upload(
        requirement,
        selected_instrument=requirement.canonical_instrument,
        selected_timeframe=ChartTimeframe.DAILY,
        content_type="image/png",
        original_bytes=_PNG_A,
    )
    with pytest.raises(TradingViewEvidenceStoreError, match="DUPLICATE_UPLOAD"):
        store.retain_upload(
            requirement,
            selected_instrument=requirement.canonical_instrument,
            selected_timeframe=ChartTimeframe.DAILY,
            content_type="image/png",
            original_bytes=_PNG_A,
        )
    second = store.retain_upload(
        requirement,
        selected_instrument=requirement.canonical_instrument,
        selected_timeframe=ChartTimeframe.DAILY,
        content_type="image/png",
        original_bytes=_PNG_B,
    )

    assert (first.revision, second.revision) == (1, 2)
    assert first.relative_path != second.relative_path
    assert store.original_bytes(first) == _PNG_A
    assert store.original_bytes(second) == _PNG_B
    package = store.package_for(requirement)
    assert package.context_status is TradingViewReviewStatus.TRADINGVIEW_CONTEXT_RECEIVED
    assert package.active_revisions == (second,)
    with pytest.raises(TradingViewEvidenceStoreError, match="INSTRUMENT_BINDING_MISMATCH"):
        store.remove_active_chart(
            requirement,
            selected_instrument="TITAN",
            selected_timeframe=ChartTimeframe.DAILY,
        )
    store.remove_active_chart(
        requirement,
        selected_instrument=requirement.canonical_instrument,
        selected_timeframe=ChartTimeframe.DAILY,
    )
    removed = store.package_for(requirement)
    assert removed.active_revisions == ()
    assert removed.revisions == (first, second)
    assert removed.context_status is TradingViewReviewStatus.TRADINGVIEW_REVIEW_REQUIRED
    reactivated = store.retain_upload(
        requirement,
        selected_instrument=requirement.canonical_instrument,
        selected_timeframe=ChartTimeframe.DAILY,
        content_type="image/png",
        original_bytes=_PNG_A,
    )
    assert reactivated == first
    assert store.package_for(requirement).active_revisions == (first,)
    assert len(store.package_for(requirement).revisions) == 2
    structured = tmp_path / store.package_for(requirement).structured_evidence_path
    assert structured.exists()
    assert json.loads(structured.read_text())["extraction_status"] == "DEFERRED_TO_SLICE_4"


def test_store_and_workflow_recover_package_across_browser_restart(tmp_path: Path) -> None:
    run = _classified_run({("NAUKRI", V1Setup.PULLBACK_CONTINUATION)})
    first = SwingV1ReviewWorkflow(LocalTradingViewEvidenceStore(tmp_path, clock=lambda: _NOW))
    snapshot = first.publish_layer1(run)
    first.upload(
        instrument="NAUKRI",
        timeframe=ChartTimeframe.DAILY,
        content_type="image/png",
        original_bytes=_PNG_A,
    )
    assert snapshot.run_state is V1ReviewRunState.TRADINGVIEW_REVIEW_REQUIRED

    restarted = SwingV1ReviewWorkflow(LocalTradingViewEvidenceStore(tmp_path, clock=lambda: _NOW))
    restored = restarted.publish_layer1(run)
    assert restored.packages[0].context_status is TradingViewReviewStatus.TRADINGVIEW_CONTEXT_RECEIVED
    assert restored.packages[0].revisions[0].byte_count == len(_PNG_A)


def test_partial_supporting_timeframe_package_is_context_incomplete(
    tmp_path: Path,
) -> None:
    run = _classified_run({("NAUKRI", V1Setup.PULLBACK_CONTINUATION)})
    workflow = SwingV1ReviewWorkflow(
        LocalTradingViewEvidenceStore(tmp_path, clock=lambda: _NOW),
        context_policy=TradingViewContextPolicy((ChartTimeframe.FOUR_HOUR,)),
    )
    workflow.publish_layer1(run)
    workflow.upload(
        instrument="NAUKRI",
        timeframe=ChartTimeframe.DAILY,
        content_type="image/png",
        original_bytes=_PNG_A,
    )
    partial = workflow.snapshot().packages[0]
    assert partial.context_status is TradingViewReviewStatus.CONTEXT_INCOMPLETE
    assert partial.missing_required_timeframes == (ChartTimeframe.FOUR_HOUR,)

    workflow.upload(
        instrument="NAUKRI",
        timeframe=ChartTimeframe.FOUR_HOUR,
        content_type="image/png",
        original_bytes=_PNG_B,
    )
    complete = workflow.snapshot().packages[0]
    assert complete.context_status is TradingViewReviewStatus.TRADINGVIEW_CONTEXT_RECEIVED
    assert complete.missing_required_timeframes == ()


@pytest.mark.parametrize("count", (0, 1, 3))
def test_workflow_handles_zero_one_and_many_probable_instruments(
    tmp_path: Path,
    count: int,
) -> None:
    probable = {
        (identity, V1Setup.PULLBACK_CONTINUATION)
        for identity in ("NAUKRI", "TITAN", "ADANIPORTS")[:count]
    }
    workflow = SwingV1ReviewWorkflow(LocalTradingViewEvidenceStore(tmp_path))
    snapshot = workflow.publish_layer1(_classified_run(probable))
    assert len(snapshot.requirements) == count
    assert snapshot.run_state is (
        V1ReviewRunState.NO_TRADINGVIEW_REVIEW_REQUIRED
        if count == 0
        else V1ReviewRunState.TRADINGVIEW_REVIEW_REQUIRED
    )
