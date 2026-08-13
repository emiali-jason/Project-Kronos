from dataclasses import fields, replace
from datetime import datetime
import json
from pathlib import Path

import pytest

from kronos.provider.contracts.market_data import HistoricalCandle
from kronos.swing.v1 import (
    EvidenceAvailability,
    FuturesPositioningInterpretation,
    ProbableClassification,
    ReconciliationState,
    TradingViewContextGateState,
    V1Setup,
    analyze_v1_layer1,
    interpret_futures_positioning,
)
from kronos.swing.v1.models import MovingAverageEvidence
from kronos.swing.v1.policies import (
    IMPULSE_TIE_POLICY_REVIEW,
    SWING_V1_LAYER1_POLICY_BUNDLE_ID,
    SWING_V1_LAYER1_POLICY_IDS,
)
from tests.unit.swing.v1.test_swing_v1_layer1 import (
    _assessment,
    _candles,
    _benchmark_map,
    _dataset,
)


_ETERNAL_FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "fixtures"
    / "swing"
    / "v1"
    / "ETERNAL_2026-08-11.json"
)


def _eternal_candles() -> tuple[HistoricalCandle, ...]:
    payload = json.loads(_ETERNAL_FIXTURE.read_text(encoding="utf-8"))
    assert payload["fixture"] == "ETERNAL_IMPULSE_TIE"
    assert payload["observation_boundary"] == "2026-08-11T00:00:00+05:30"
    return tuple(
        HistoricalCandle(
            timestamp=datetime.fromisoformat(item["timestamp"]),
            open=float(item["open"]),
            high=float(item["high"]),
            low=float(item["low"]),
            close=float(item["close"]),
            volume=int(item["volume"]),
        )
        for item in payload["candles"]
    )


def test_policy_unresolved_and_evidence_incomplete_reconcile_distinctly() -> None:
    baseline = _assessment(
        analyze_v1_layer1(_dataset(), benchmark_map=_benchmark_map()),
        "IOC",
        V1Setup.PULLBACK_CONTINUATION,
    )
    unresolved = replace(
        baseline,
        classification=ProbableClassification.POLICY_UNRESOLVED,
        reconciliation=ReconciliationState.POLICY_UNRESOLVED,
        context_gate=TradingViewContextGateState.NOT_ELIGIBLE_UNLESS_PROBABLE,
    )
    incomplete = replace(
        baseline,
        classification=ProbableClassification.EVIDENCE_INCOMPLETE,
        reconciliation=ReconciliationState.EVIDENCE_INCOMPLETE,
        context_gate=TradingViewContextGateState.NOT_ELIGIBLE_UNLESS_PROBABLE,
    )

    assert unresolved.reconciliation is ReconciliationState.POLICY_UNRESOLVED
    assert incomplete.reconciliation is ReconciliationState.EVIDENCE_INCOMPLETE
    with pytest.raises(ValueError, match="V1_LAYER1_ASSESSMENT_INVALID"):
        replace(unresolved, reconciliation=ReconciliationState.EVIDENCE_INCOMPLETE)


def test_classifier_uses_incomplete_only_for_missing_structural_alternative() -> None:
    one_definition_only = tuple(
        float(100 + index + (2 if index % 2 else 0))
        for index in range(25)
    )
    disagreement = (
        103.0,
        99.0,
        96.0,
        93.0,
        90.0,
        94.0,
        97.0,
        100.0,
        104.0,
        101.0,
        99.0,
        102.0,
        98.0,
        102.0,
        106.0,
        102.0,
        100.0,
        102.0,
        98.0,
        101.0,
        103.0,
        107.0,
        110.0,
        107.0,
        111.0,
    )
    incomplete_result = analyze_v1_layer1(
        _dataset(historical=lambda _request: _candles(one_definition_only))
    )
    unresolved_result = analyze_v1_layer1(
        _dataset(historical=lambda _request: _candles(disagreement))
    )
    incomplete = _assessment(
        incomplete_result,
        "IOC",
        V1Setup.PULLBACK_CONTINUATION,
    )
    unresolved = _assessment(
        unresolved_result,
        "IOC",
        V1Setup.PULLBACK_CONTINUATION,
    )

    assert incomplete.structural.alternatives_complete is False
    assert incomplete.structural.alternatives_disagree is False
    assert incomplete.classification is ProbableClassification.EVIDENCE_INCOMPLETE
    assert incomplete.reconciliation is ReconciliationState.EVIDENCE_INCOMPLETE
    assert unresolved.structural.alternatives_complete is True
    assert unresolved.structural.alternatives_disagree is True
    assert unresolved.classification is ProbableClassification.POLICY_UNRESOLVED
    assert unresolved.reconciliation is ReconciliationState.POLICY_UNRESOLVED


def test_structural_alternatives_retain_positive_agreement_and_provenance() -> None:
    assessment = _assessment(
        analyze_v1_layer1(_dataset()),
        "IOC",
        V1Setup.PULLBACK_CONTINUATION,
    )

    assert assessment.structural.alternatives_agree is True
    assert assessment.structural.alternatives_disagree is False
    assert tuple(item.radius for item in assessment.structural.alternatives) == (1, 2)
    assert all(
        item.definition_id == f"FRACTAL_UNIQUE_EXTREME_RADIUS_{item.radius}"
        and item.swing_highs
        and item.swing_lows
        for item in assessment.structural.alternatives
    )


def test_eternal_equal_strength_opposite_impulses_are_retained_and_reviewed() -> None:
    candles = _eternal_candles()

    def historical(request):  # type: ignore[no-untyped-def]
        if request.instrument.trading_symbol == "ETERNAL":
            return candles
        return candles

    result = analyze_v1_layer1(
        _dataset(historical=historical),
        benchmark_map=_benchmark_map(),
    )
    assessment = _assessment(result, "ETERNAL", V1Setup.PULLBACK_CONTINUATION)
    impulse = assessment.impulse_maturity
    tied = tuple(
        item
        for item in impulse.candidates
        if item.candidate_identity in impulse.tied_candidate_identities
    )

    assert tuple(item.candle_index for item in tied) == (15, 19)
    assert tied[0].range_atr == tied[1].range_atr
    assert tuple(item.direction.value for item in tied) == ("SHORT", "LONG")
    assert impulse.selection_policy == "MAX_RANGE_ATR_THEN_EARLIEST_INDEX"
    assert impulse.impulse_candle_index == 15
    assert impulse.selected_candidate_identity == tied[0].candidate_identity
    assert impulse.tie_policy_review is True
    assert "impulse_tie_policy" in impulse.unresolved_fields
    assert IMPULSE_TIE_POLICY_REVIEW in assessment.unresolved_policies
    assert assessment.classification is ProbableClassification.NOT_SUPPORTED
    assert assessment.reasons == (
        "IMPULSE_TIE_SELECTED_DIRECTION_DOES_NOT_ALIGN",
    )


def test_ma_contract_has_no_generic_availability_and_declares_history() -> None:
    assessment = _assessment(
        analyze_v1_layer1(_dataset()),
        "IOC",
        V1Setup.PULLBACK_CONTINUATION,
    )
    moving_average = assessment.moving_average

    assert "availability" not in {item.name for item in fields(MovingAverageEvidence)}
    assert moving_average.completed_history_count == 30
    assert moving_average.sma20_required_candles == 25
    assert moving_average.sma50_required_candles == 55
    assert moving_average.sma200_required_candles == 200
    assert moving_average.sma20_availability is EvidenceAvailability.AVAILABLE
    assert moving_average.sma50_availability is EvidenceAvailability.UNAVAILABLE
    assert moving_average.sma200_availability is EvidenceAvailability.UNAVAILABLE


def test_volume_measurements_are_separate_from_unfrozen_interpretation() -> None:
    result = analyze_v1_layer1(_dataset())
    pullback = _assessment(result, "IOC", V1Setup.PULLBACK_CONTINUATION).volume
    breakout = _assessment(result, "IOC", V1Setup.CONSOLIDATION_BREAKOUT).volume

    assert pullback.current_volume == 1029
    assert pullback.normal_mean_volume == pytest.approx(1018.5)
    assert pullback.comparison_mean_volume == pytest.approx(1026)
    assert pullback.comparison_role == "PULLBACK_MEAN"
    assert breakout.comparison_role == "CONSOLIDATION_MEAN"
    assert pullback.measurement_only is True
    assert pullback.policy_interpretation == "POLICY_UNRESOLVED_NO_THRESHOLD"


def test_volatility_has_setup_role_but_no_directional_authority() -> None:
    result = analyze_v1_layer1(_dataset())
    pullback = _assessment(result, "IOC", V1Setup.PULLBACK_CONTINUATION)
    breakout = _assessment(result, "IOC", V1Setup.CONSOLIDATION_BREAKOUT)

    assert pullback.volatility.setup_role == "SUPPORTING_EVIDENCE"
    assert breakout.volatility.setup_role == "SETUP_QUALITY_EVIDENCE"
    assert pullback.volatility.directional_authority is False
    assert breakout.volatility.directional_authority is False


@pytest.mark.parametrize(
    ("price", "oi", "expected"),
    (
        (1.0, 1, FuturesPositioningInterpretation.LONG_BUILDUP),
        (-1.0, 1, FuturesPositioningInterpretation.SHORT_BUILDUP),
        (1.0, -1, FuturesPositioningInterpretation.SHORT_COVERING),
        (-1.0, -1, FuturesPositioningInterpretation.LONG_UNWINDING),
    ),
)
def test_futures_oi_vocabulary_requires_roll_safe_facts(
    price: float,
    oi: int,
    expected: FuturesPositioningInterpretation,
) -> None:
    assert interpret_futures_positioning(price, oi, roll_normalized=False) is None
    assert interpret_futures_positioning(price, oi, roll_normalized=True) is expected


def test_each_assessment_retains_the_complete_policy_identity() -> None:
    result = analyze_v1_layer1(_dataset())

    assert all(
        assessment.policy_bundle == SWING_V1_LAYER1_POLICY_BUNDLE_ID
        and assessment.policy_ids == SWING_V1_LAYER1_POLICY_IDS
        for instrument in result.instruments
        for assessment in instrument.assessments
    )
