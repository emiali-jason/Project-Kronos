from dataclasses import FrozenInstanceError, fields
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from kronos.provider.contracts.instrument import (
    InstrumentRecord,
    InstrumentResolutionError,
    InstrumentResolutionFailure,
)
from kronos.provider.contracts.market_data import HistoricalCandle
from kronos.swing.daily_data import build_swing_daily_dataset
from kronos.swing.universe import enabled_swing_phase1_universe
from kronos.swing.v1 import (
    BenchmarkRelationship,
    EvidenceAvailability,
    ProbableClassification,
    ReconciliationState,
    TradingViewContextGateState,
    V0V1ComparisonClassification,
    V1BenchmarkMap,
    V1Setup,
    analyze_v1_layer1,
    build_v0_v1_layer1_comparison,
)
from kronos.swing.v1.models import V1Layer1Assessment
from kronos.swing.v1.policies import (
    SWING_V1_LAYER1_POLICY_BUNDLE_ID,
    SWING_V1_LAYER1_POLICY_IDS,
)
from kronos.swing.zero import SWING_ZERO_POLICY_ID, SwingState


_KOLKATA = ZoneInfo("Asia/Kolkata")
_NOW = datetime(2026, 8, 12, 12, 0, tzinfo=_KOLKATA)
_BULLISH_WAVES = (
    100.0,
    102.0,
    105.0,
    103.0,
    101.0,
    104.0,
    108.0,
    106.0,
    104.0,
    107.0,
    111.0,
    109.0,
    107.0,
    110.0,
    114.0,
    112.0,
    110.0,
    113.0,
    117.0,
    115.0,
    113.0,
    116.0,
    120.0,
    118.0,
    116.0,
    119.0,
    123.0,
    121.0,
    119.0,
    126.0,
)


def _instrument(identity: str) -> InstrumentRecord:
    commodity = identity in {
        "GOLDM",
        "SILVERM",
        "COPPER",
        "CRUDEOIL",
        "NATURALGAS",
    }
    return InstrumentRecord(
        provider="KITE",
        exchange="MCX" if commodity else "NSE",
        segment="MCX-FUT" if commodity else "NSE",
        trading_symbol=f"{identity}26AUGFUT" if commodity else identity,
        name=identity,
        instrument_type="FUT" if commodity else "EQ",
        expiry=date(2026, 8, 28) if commodity else None,
    )


def _candles(
    closes: tuple[float, ...] = _BULLISH_WAVES,
    *,
    end_date: date = date(2026, 8, 11),
    volume: int = 1_000,
) -> tuple[HistoricalCandle, ...]:
    start = end_date - timedelta(days=len(closes) - 1)
    return tuple(
        HistoricalCandle(
            timestamp=datetime.combine(
                start + timedelta(days=index),
                datetime.min.time(),
                tzinfo=_KOLKATA,
            ),
            open=close - 0.5,
            high=close + 1.0,
            low=close - 1.0,
            close=close,
            volume=volume + index,
        )
        for index, close in enumerate(closes)
    )


def _dataset(*, resolve=None, historical=None):  # type: ignore[no-untyped-def]
    return build_swing_daily_dataset(
        enabled_swing_phase1_universe(),
        resolve_instrument=resolve
        or (lambda member: _instrument(member.canonical_identity)),
        historical_candles=historical or (lambda _request: _candles()),
        now=_NOW,
    )


def _benchmark_map() -> V1BenchmarkMap:
    return V1BenchmarkMap(
        tuple(
            BenchmarkRelationship(member.canonical_identity, "NIFTY")
            for member in enabled_swing_phase1_universe()
            if member.asset_class.value == "NSE_EQUITY"
        )
    )


def _assessment(result, identity: str, setup: V1Setup):  # type: ignore[no-untyped-def]
    instrument = next(
        item for item in result.instruments if item.canonical_identity == identity
    )
    return next(item for item in instrument.assessments if item.setup is setup)


def test_layer1_reconciles_exactly_98_members_and_196_setup_records() -> None:
    result = analyze_v1_layer1(_dataset(), benchmark_map=_benchmark_map())

    assert len(result.instruments) == 98
    assert result.assessment_count == 196
    assert result.policy_bundle == SWING_V1_LAYER1_POLICY_BUNDLE_ID
    assert result.policy_ids == SWING_V1_LAYER1_POLICY_IDS
    assert all(
        tuple(item.setup for item in instrument.assessments)
        == (
            V1Setup.PULLBACK_CONTINUATION,
            V1Setup.CONSOLIDATION_BREAKOUT,
        )
        for instrument in result.instruments
    )
    assert all(
        (
            item.context_gate
            is TradingViewContextGateState.TRADINGVIEW_CONTEXT_PENDING
        )
        == (
            item.classification
            is ProbableClassification.PROBABLE_CANDIDATE
        )
        for instrument in result.instruments
        for item in instrument.assessments
    )


def test_layer1_is_deterministic_immutable_and_retains_both_pivot_alternatives() -> None:
    dataset = _dataset()
    first = analyze_v1_layer1(dataset)
    second = analyze_v1_layer1(dataset)
    assessment = _assessment(
        first,
        "IOC",
        V1Setup.CONSOLIDATION_BREAKOUT,
    )

    assert first == second
    assert hash(first) == hash(second)
    assert tuple(item.radius for item in assessment.structural.alternatives) == (1, 2)
    assert all(
        item.definition_id.startswith("FRACTAL_UNIQUE_EXTREME_RADIUS_")
        for item in assessment.structural.alternatives
    )
    with pytest.raises(FrozenInstanceError):
        assessment.classification = ProbableClassification.NOT_SUPPORTED  # type: ignore[misc]


def test_v1_probable_population_is_independent_of_v0_qualified_population() -> None:
    comparison = build_v0_v1_layer1_comparison(
        _dataset(),
        benchmark_map=_benchmark_map(),
    )
    v0 = next(
        item
        for item in comparison.v0_control.instruments
        if item.canonical_identity == "IOC"
    ).assessments[1]
    v1 = _assessment(
        comparison.v1_layer1,
        "IOC",
        V1Setup.CONSOLIDATION_BREAKOUT,
    )

    assert v0.state is not SwingState.QUALIFIED
    assert v1.classification is ProbableClassification.PROBABLE_CANDIDATE
    assert v1.reconciliation is ReconciliationState.READY_FOR_CONTEXT
    assert comparison.v1_layer1.probable_count > 0
    side_by_side = next(
        item
        for item in comparison.setup_comparisons
        if item.canonical_identity == "IOC"
        and item.setup is V1Setup.CONSOLIDATION_BREAKOUT
    )
    assert (
        side_by_side.classification
        is V0V1ComparisonClassification.V0_NONQUALIFIED_V1_PROBABLE
    )
    assert side_by_side.v0_state is v0.state
    assert side_by_side.v1_assessment is v1


def test_complete_evidence_retains_available_unavailable_and_not_applicable() -> None:
    result = analyze_v1_layer1(_dataset(), benchmark_map=_benchmark_map())
    equity = _assessment(result, "IOC", V1Setup.PULLBACK_CONTINUATION)
    index = _assessment(result, "NIFTY", V1Setup.PULLBACK_CONTINUATION)
    commodity = _assessment(result, "GOLDM", V1Setup.PULLBACK_CONTINUATION)

    assert equity.structural.availability is EvidenceAvailability.AVAILABLE
    assert equity.moving_average.sma20_availability is EvidenceAvailability.AVAILABLE
    assert equity.moving_average.sma50_availability is EvidenceAvailability.UNAVAILABLE
    assert equity.moving_average.sma200_availability is EvidenceAvailability.UNAVAILABLE
    assert equity.volume.availability is EvidenceAvailability.AVAILABLE
    assert equity.candle.availability is EvidenceAvailability.AVAILABLE
    assert equity.volatility.availability is EvidenceAvailability.AVAILABLE
    assert equity.relative_context.availability is EvidenceAvailability.AVAILABLE
    assert index.relative_context.availability is EvidenceAvailability.NOT_APPLICABLE
    assert commodity.futures_positioning.availability is EvidenceAvailability.UNAVAILABLE
    assert "FUTURES_OI_ROLL_NORMALIZATION_NOT_IMPLEMENTED" in (
        commodity.unresolved_policies
    )


def test_layer1_retains_exact_descriptive_measurements_without_score_authority() -> None:
    result = analyze_v1_layer1(_dataset(), benchmark_map=_benchmark_map())
    pullback = _assessment(result, "IOC", V1Setup.PULLBACK_CONTINUATION)
    breakout = _assessment(result, "IOC", V1Setup.CONSOLIDATION_BREAKOUT)

    assert pullback.volume.relative_mean == pytest.approx(1029 / 1018.5)
    assert pullback.volume.relative_median == pytest.approx(1029 / 1018.5)
    assert pullback.volume.percentile20 == 1.0
    assert pullback.volume.resumption_vs_pullback_mean == pytest.approx(1029 / 1026)
    assert "ACCEPTANCE_ABOVE_PREVIOUS_HIGH" in pullback.candle.interpretations
    assert pullback.candle.named_patterns_create_trades is False
    assert breakout.volatility.close_vs_preceding_range == "ABOVE"
    assert breakout.volatility.measurement_only is True
    assert breakout.relative_context.interpretation == "NEUTRAL_MIXED"
    assert breakout.relative_context.automatic_market_veto is False
    assert breakout.gap_context.news_event_causation == "DEFERRED"
    assert breakout.gap_context.standalone_setup is False
    assert breakout.gap_context.automatic_veto is False


def test_unavailable_daily_input_still_retains_two_complete_failed_records() -> None:
    def resolve(member):  # type: ignore[no-untyped-def]
        if member.canonical_identity == "IOC":
            raise InstrumentResolutionError(InstrumentResolutionFailure.NO_MATCH)
        return _instrument(member.canonical_identity)

    comparison = build_v0_v1_layer1_comparison(_dataset(resolve=resolve))
    v1 = next(
        item
        for item in comparison.v1_layer1.instruments
        if item.canonical_identity == "IOC"
    )

    assert comparison.v0_control.assessment_count == 194
    assert comparison.v1_layer1.assessment_count == 196
    assert len(comparison.setup_comparisons) == 196
    assert len(v1.assessments) == 2
    assert all(
        item.classification is ProbableClassification.EVIDENCE_INCOMPLETE
        and item.reconciliation is ReconciliationState.EVIDENCE_INCOMPLETE
        and item.context_gate
        is TradingViewContextGateState.NOT_ELIGIBLE_UNLESS_PROBABLE
        and item.structural.availability is EvidenceAvailability.UNAVAILABLE
        and item.missing_evidence
        for item in v1.assessments
    )
    assert all(
        item.classification
        is V0V1ComparisonClassification.COMPARISON_INPUT_INCOMPLETE
        for item in comparison.setup_comparisons
        if item.canonical_identity == "IOC"
    )


def test_same_dataset_uses_one_exact_boundary_for_v0_and_v1() -> None:
    def historical(request):  # type: ignore[no-untyped-def]
        end = (
            date(2026, 8, 10)
            if request.instrument.exchange == "MCX"
            else date(2026, 8, 11)
        )
        return _candles(end_date=end)

    comparison = build_v0_v1_layer1_comparison(_dataset(historical=historical))

    assert comparison.same_market_facts is True
    assert comparison.v0_control.observation_boundary == (
        comparison.v1_layer1.observation_boundary
    )
    assert comparison.v1_layer1.observation_boundary.date() == date(2026, 8, 10)
    assert comparison.v0_control.run_identity.startswith(SWING_ZERO_POLICY_ID)


def test_slice1_contract_has_no_later_stage_geometry_or_ranking_fields() -> None:
    names = {item.name for item in fields(V1Layer1Assessment)}

    assert not names.intersection(
        {
            "entry",
            "entry_zone",
            "invalidation",
            "stop",
            "target",
            "targets",
            "risk_reward",
            "viability",
            "rank",
            "readiness",
            "top_opportunity",
            "tradingview_evidence",
        }
    )
    assert not names.intersection(
        {
            "instrument_token",
            "provider_token",
            "request_token",
            "access_token",
            "kite_client",
            "raw_provider_record",
        }
    )
