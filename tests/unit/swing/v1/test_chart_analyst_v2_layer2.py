import json
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest

from kronos.swing.v1.chart_analyst_v2 import (
    OPENAI_CHART_ANALYST_V2_PROVIDER_ID,
    ChartAnalystProduct,
    ChartAnalystV2Response,
    chart_analyst_v2_response_from_dict,
    chart_analyst_v2_response_to_dict,
)
from kronos.swing.v1.chart_analyst_v2_integrity import (
    ChartAnalystV2OutputIntegrityError,
)
from kronos.swing.v1.chart_analyst_v2_layer2 import (
    CHART_ANALYST_V2_OPERATIONAL_AUTHORITY,
    ChartAnalystV2Layer2State,
    KronosLayer2ReconciliationState,
    chart_analyst_v2_layer2_record_from_dict,
    chart_analyst_v2_layer2_record_to_dict,
    integrate_chart_analyst_v2_layer2,
)
from kronos.swing.v1.evidence_store import LocalTradingViewEvidenceStore
from kronos.swing.v1.layer2 import ClearAirState, ReadinessState
from kronos.swing.v1.models import V1Setup
from kronos.swing.v1.tradingview import (
    ChartTimeframe,
    build_tradingview_review_requirements,
)
from tests.unit.swing.v1.test_chart_analyst_v2 import _analysis
from tests.unit.swing.v1.test_swing_v1_slice3 import _classified_run


_NOW = datetime(2026, 8, 13, 13, 0, tzinfo=UTC)
_IMAGE = b"\x89PNG\r\n\x1a\n4f-layer2-four-pane"
_IMAGE_HASH = sha256(_IMAGE).hexdigest()
_PARENT_RUN = "SWING-RUN-0000000000000000000000000000004F"
_HAL_FIXTURE = (
    Path(__file__).parents[3]
    / "fixtures"
    / "swing"
    / "v1"
    / "chart_analyst_v2_4f_hal_b19bb599.json"
)


def _context(
    instrument: str = "NAUKRI",
    *,
    product: ChartAnalystProduct = ChartAnalystProduct.NSE,
):  # type: ignore[no-untyped-def]
    run = _classified_run({(instrument, V1Setup.PULLBACK_CONTINUATION)})
    requirement = build_tradingview_review_requirements(
        run,
        swing_analysis_run_identity=_PARENT_RUN,
    )[0]
    source = next(
        item for item in run.instruments
        if item.canonical_identity == instrument
    )
    assessments = tuple(
        item for item in source.assessments
        if item.setup is V1Setup.PULLBACK_CONTINUATION
    )
    analysis = _valid_analysis(instrument, product)
    response = ChartAnalystV2Response(
        provider_identity=OPENAI_CHART_ANALYST_V2_PROVIDER_ID,
        model_identity="gpt-5.6",
        request_timestamp=_NOW,
        run_identity=requirement.run_identity,
        swing_analysis_run_identity=requirement.swing_analysis_run_identity,
        analysis=analysis,
    )
    return run, requirement, assessments, response


def _valid_analysis(
    instrument: str,
    product: ChartAnalystProduct,
) -> dict[str, object]:
    value = _analysis()
    value.update({
        "instrument": instrument,
        "product": product.value,
        "image_sha256": _IMAGE_HASH,
        "expected_timeframes_present": {
            "1W": "YES", "1D": "YES", "4H": "YES", "1H": "YES",
        },
        "overall_image_readability": "GOOD",
    })
    for timeframe in value["timeframes"].values():
        timeframe["readability"] = "GOOD"
        timeframe["pine_workstation"]["trend"] = "Bullish"
    daily = value["timeframes"]["1D"]
    daily["market_structure"].update({
        "structure": "BULLISH",
        "higher_highs_visible": "YES",
        "higher_lows_visible": "YES",
        "lower_highs_visible": "NO",
        "lower_lows_visible": "NO",
        "structure_condition": "PRESERVED",
        "recent_swing_high": 110.0,
        "recent_swing_low": 90.0,
    })
    for moving_average in daily["moving_averages"].values():
        moving_average.update({
            "price_relation": "ABOVE",
            "slope": "RISING",
            "role": "SUPPORT",
        })
    daily["candlestick_evidence"].update({
        "material_candle_evidence": "STRONG_BULLISH_CLOSE",
        "candle_acceptance": "ACCEPTED",
    })
    daily["breakout_breakdown_retest"].update({
        "break_state": "CONFIRMED",
        "break_direction": "BULLISH",
        "close_beyond_structure": "YES",
        "returned_inside_range": "NO",
        "retest_state": "NONE",
    })
    daily["volume_participation"].update({
        "volume_context": "SUPPORTIVE",
        "volume_with_impulse": "EXPANDING",
        "volume_during_pullback": "CONTRACTING",
        "volume_on_break": "SUPPORTIVE",
        "participation_deteriorating": "NO",
    })
    daily["support_resistance_barriers"].update({
        "nearest_visible_support": 90.0,
        "nearest_visible_resistance": "NONE",
        "major_swing_barrier_present": "NO",
        "ma_or_reference_barrier_present": "NO",
        "barrier_direction": "BELOW_PRICE",
        "visible_room_for_continuation": "GOOD",
    })
    daily["continuation_pattern"].update({
        "continuation_pattern": "BREAKOUT_CONTINUATION",
        "continuation_status": "CONFIRMED",
        "continuation_direction": "BULLISH",
    })
    daily["pullback"].update({
        "pullback_present": "NO",
        "pullback_quality": "NONE",
        "pullback_depth": "SHALLOW",
        "impulse_structure_retained": "YES",
    })
    daily.update({
        "post_impulse_behaviour": "IMMEDIATE_CONTINUATION",
        "post_impulse_progress": "CONTINUING",
        "weakening_failure_evidence": "NONE",
        "resumption_evidence": "STRONG",
    })
    daily["maturity_extension_chase_risk"].update({
        "move_maturity": "DEVELOPING",
        "chase_risk": "LOW",
    })
    value["overall_observation"].update({
        "setup_visually_exists": "YES",
        "setup_direction": "BULLISH",
        "setup_phase": "DEVELOPING",
        "most_material_positive_evidence": "Structure and continuation evidence remain visible.",
        "most_material_negative_evidence": "No material negative evidence is visible.",
        "overall_determinability": "GOOD",
    })
    return value


def _integrate(
    response: ChartAnalystV2Response,
    requirement,  # type: ignore[no-untyped-def]
    assessments,  # type: ignore[no-untyped-def]
):  # type: ignore[no-untyped-def]
    return integrate_chart_analyst_v2_layer2(
        requirement,
        assessments,
        response,
        source_image_sha256=_IMAGE_HASH,
    )


def test_valid_v2_evidence_replays_existing_chain_and_preserves_layer1() -> None:
    run, requirement, assessments, response = _context()
    original_assessments = deepcopy(assessments)

    record = _integrate(response, requirement, assessments)

    assert assessments == original_assessments
    assert run.probable_count == 1
    assert record.state is ChartAnalystV2Layer2State.SHADOW_COMPLETE
    assert record.reconciliation is KronosLayer2ReconciliationState.AGREE
    assert record.readiness.state is ReadinessState.READY_FOR_TRADE_CONSTRUCTION
    assert record.layer2_record is not None
    assert record.layer2_record.clear_air.state is ClearAirState.CLEAR
    assert record.operational_authority == CHART_ANALYST_V2_OPERATIONAL_AUTHORITY
    assert not hasattr(response, "readiness")


@pytest.mark.parametrize(
    ("mutation", "expected"),
    (
        ("PARTIAL", KronosLayer2ReconciliationState.COMPATIBLE_PARTIAL),
        ("CONTRADICT", KronosLayer2ReconciliationState.CONTRADICT),
        ("INCOMPLETE", KronosLayer2ReconciliationState.CONTEXT_INCOMPLETE),
    ),
)
def test_kronos_reconciliation_states_are_deterministic(
    mutation: str,
    expected: KronosLayer2ReconciliationState,
) -> None:
    _, requirement, assessments, response = _context()
    analysis = deepcopy(response.analysis)
    daily = analysis["timeframes"]["1D"]
    if mutation == "PARTIAL":
        daily["volume_participation"]["volume_context"] = "MIXED"
    elif mutation == "CONTRADICT":
        daily["market_structure"].update({
            "structure": "BEARISH",
            "higher_highs_visible": "NO",
            "higher_lows_visible": "NO",
            "lower_highs_visible": "YES",
            "lower_lows_visible": "YES",
        })
        daily["pine_workstation"]["trend"] = "Bearish"
    else:
        daily["moving_averages"]["SMA20"]["slope"] = "UNDETERMINABLE"
    altered = replace(response, analysis=analysis)

    record = _integrate(altered, requirement, assessments)

    assert record.reconciliation is expected
    if mutation == "CONTRADICT":
        assert "STRUCTURE_CONTRADICTS_LAYER1" in record.contradictions
    if mutation == "INCOMPLETE":
        assert record.state is ChartAnalystV2Layer2State.CONTEXT_INCOMPLETE
        assert record.readiness.state is ReadinessState.CONTEXT_INCOMPLETE


def test_openai_reconciliation_claims_and_pine_decision_have_no_authority() -> None:
    _, requirement, assessments, response = _context()
    baseline = _integrate(response, requirement, assessments)
    analysis = deepcopy(response.analysis)
    analysis["pine_vs_chart"].update({
        "pine_vs_visible_chart": "CONTRADICT",
        "contradiction_reason": "Provider says contradict; KRONOS must independently replay evidence.",
    })
    analysis["thesis_behaviour"].update({
        "relationship": "CONTRADICTS_THESIS",
        "thesis_behaviour_reason": "Provider thesis wording cannot determine KRONOS reconciliation.",
    })
    analysis["timeframes"]["1D"]["pine_workstation"]["decision"] = "AVOID"
    altered = _integrate(replace(response, analysis=analysis), requirement, assessments)

    assert altered.reconciliation is baseline.reconciliation
    assert altered.contradictions == baseline.contradictions
    assert altered.readiness == baseline.readiness


def test_barriers_retain_image_provenance_and_clear_air_is_kronos_owned() -> None:
    _, requirement, assessments, response = _context()
    analysis = deepcopy(response.analysis)
    barriers = analysis["timeframes"]["1D"]["support_resistance_barriers"]
    barriers.update({
        "nearest_visible_resistance": 120.0,
        "major_swing_barrier_present": "YES",
        "barrier_direction": "ABOVE_PRICE",
        "visible_room_for_continuation": "BLOCKED",
    })

    record = _integrate(replace(response, analysis=analysis), requirement, assessments)

    assert record.layer2_record is not None
    assert record.layer2_record.barriers
    assert all(_IMAGE_HASH in item.source_hashes for item in record.layer2_record.barriers)
    assert record.layer2_record.clear_air.state is ClearAirState.MAJOR_BARRIER_PRESENT
    assert record.readiness.state is not ReadinessState.READY_FOR_TRADE_CONSTRUCTION


@pytest.mark.parametrize("binding", ("run", "image", "instrument"))
def test_wrong_run_image_or_instrument_binding_is_rejected(binding: str) -> None:
    _, requirement, assessments, response = _context()
    if binding == "run":
        response = replace(response, run_identity="WRONG-RUN")
        source_hash = _IMAGE_HASH
    elif binding == "image":
        source_hash = "f" * 64
    else:
        analysis = deepcopy(response.analysis)
        analysis["instrument"] = "TITAN"
        response = replace(response, analysis=analysis)
        source_hash = _IMAGE_HASH
    with pytest.raises(ValueError, match="BINDING_INVALID"):
        integrate_chart_analyst_v2_layer2(
            requirement,
            assessments,
            response,
            source_image_sha256=source_hash,
        )


def test_wrong_question_set_version_and_invalid_integrity_never_reach_4f() -> None:
    _, _, _, response = _context()
    payload = chart_analyst_v2_response_to_dict(response)
    payload["analysis"]["question_set_version"] = "2.1"
    with pytest.raises(ValueError, match="RESPONSE_INVALID"):
        chart_analyst_v2_response_from_dict(payload)

    invalid = deepcopy(response.analysis)
    invalid["timeframes"]["1H"]["pine_workstation"]["quality"] = "Bullish"
    with pytest.raises(ChartAnalystV2OutputIntegrityError):
        replace(response, analysis=invalid)

    truncated = deepcopy(response.analysis)
    truncated["thesis_behaviour"]["thesis_behaviour_reason"] = (
        "The bounded reason is visibly cut at the post-"
    )
    with pytest.raises(ChartAnalystV2OutputIntegrityError):
        replace(response, analysis=truncated)


def test_undeterminable_critical_evidence_is_context_incomplete() -> None:
    _, requirement, assessments, response = _context()
    analysis = deepcopy(response.analysis)
    analysis["timeframes"]["1D"]["volume_participation"]["volume_context"] = "UNDETERMINABLE"

    record = _integrate(replace(response, analysis=analysis), requirement, assessments)

    assert record.state is ChartAnalystV2Layer2State.CONTEXT_INCOMPLETE
    assert "1D_VOLUME_CONTEXT_UNDETERMINABLE" in record.missing_required_evidence
    assert record.layer2_record is None


def test_nse_and_mcx_product_contexts_are_isolated() -> None:
    _, requirement, assessments, response = _context(
        "GOLDM",
        product=ChartAnalystProduct.MCX,
    )
    assert _integrate(response, requirement, assessments).state is (
        ChartAnalystV2Layer2State.SHADOW_COMPLETE
    )
    wrong = deepcopy(response.analysis)
    wrong["product"] = ChartAnalystProduct.NSE.value
    with pytest.raises(ValueError, match="ELIGIBILITY_INVALID"):
        _integrate(replace(response, analysis=wrong), requirement, assessments)


def test_codec_store_restart_and_audit_reconstruction(tmp_path: Path) -> None:
    _, requirement, assessments, response = _context()
    record = _integrate(response, requirement, assessments)
    payload = chart_analyst_v2_layer2_record_to_dict(record)
    assert chart_analyst_v2_layer2_record_from_dict(payload) == record
    assert payload["raw_output_provenance"]["image_sha256"] == _IMAGE_HASH
    assert payload["production_authority"] == "NONE"
    assert payload["openai_readiness_authority"] == "NONE"
    assert payload["pine_readiness_authority"] == "NONE"

    store = LocalTradingViewEvidenceStore(tmp_path, clock=lambda: _NOW)
    store.retain_upload(
        requirement,
        selected_instrument=requirement.canonical_instrument,
        selected_timeframe=ChartTimeframe.DAILY,
        content_type="image/png",
        original_bytes=_IMAGE,
    )
    store.retain_chart_analyst_v2_layer2(requirement, record)

    restarted = LocalTradingViewEvidenceStore(tmp_path, clock=lambda: _NOW)
    assert restarted.chart_analyst_v2_layer2_for(requirement) == record


def test_b19bb599_hal_controlled_fixture_replays_as_shadow() -> None:
    fixture = json.loads(_HAL_FIXTURE.read_text(encoding="utf-8"))
    _, requirement, assessments, response = _context("HAL")
    analysis = deepcopy(response.analysis)
    analysis.update({
        "expected_timeframes_present": fixture["expected_timeframes_present"],
        "overall_image_readability": fixture["overall_image_readability"],
        "overall_observation": fixture["overall_observation"],
    })
    analysis["timeframes"]["1D"] = fixture["daily"]

    record = _integrate(replace(response, analysis=analysis), requirement, assessments)

    assert fixture["source_run"] == "B19BB599"
    assert record.state is ChartAnalystV2Layer2State.SHADOW_COMPLETE
    assert record.readiness.state is ReadinessState.EXTENDED_DO_NOT_CHASE
    assert record.layer2_record is not None
    assert record.layer2_record.clear_air.state is ClearAirState.MAJOR_BARRIER_PRESENT
    assert record.operational_authority == "SHADOW / VALIDATION ONLY"


def test_same98_instrument_collapsing_is_unchanged() -> None:
    run = _classified_run({
        ("NAUKRI", V1Setup.PULLBACK_CONTINUATION),
        ("NAUKRI", V1Setup.CONSOLIDATION_BREAKOUT),
        ("TITAN", V1Setup.PULLBACK_CONTINUATION),
    })
    requirements = build_tradingview_review_requirements(
        run,
        swing_analysis_run_identity=_PARENT_RUN,
    )
    assert run.probable_count == 3
    assert [item.canonical_instrument for item in requirements] == ["NAUKRI", "TITAN"]
