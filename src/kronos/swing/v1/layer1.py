"""Swing V1 Layer-1 probable discovery and complete evidence retention."""

from __future__ import annotations

from datetime import datetime

from kronos.provider.contracts.market_data import HistoricalCandle
from kronos.swing.daily_data import (
    SwingDailyDataset,
    SwingDailySeries,
    SwingDailyStatus,
)
from kronos.swing.universe import SwingUniverseAssetClass
from kronos.swing.v1.evidence import (
    candle_evidence,
    futures_positioning_evidence,
    gap_context_evidence,
    impulse_maturity_evidence,
    moving_average_evidence,
    relative_context_evidence,
    structural_evidence,
    volatility_evidence,
    volume_evidence,
)
from kronos.swing.v1.interfaces import V1BenchmarkMap
from kronos.swing.v1.models import (
    CandleEvidence,
    EvidenceAvailability,
    FuturesPositioningEvidence,
    GapContextEvidence,
    ImpulseMaturityEvidence,
    MovingAverageEvidence,
    ProbableClassification,
    ReconciliationState,
    RelativeContextEvidence,
    StructuralEvidence,
    StructuralAlternative,
    StructuralState,
    TradingViewContextGateState,
    V1Direction,
    V1InstrumentLayer1Evidence,
    V1Layer1Assessment,
    V1Layer1Run,
    V1Setup,
    VolatilityEvidence,
    VolumeEvidence,
)
from kronos.swing.v1.policies import (
    IMPULSE_TIE_POLICY_REVIEW,
    SWING_V1_LAYER1_POLICY_BUNDLE_ID,
    SWING_V1_LAYER1_POLICY_IDS,
)


def analyze_v1_layer1(
    dataset: SwingDailyDataset,
    *,
    benchmark_map: V1BenchmarkMap | None = None,
) -> V1Layer1Run:
    """Analyze all 98 members without V0-population or later-stage leakage."""

    if (
        type(dataset) is not SwingDailyDataset
        or dataset.requested_count != 98
        or (benchmark_map is not None and type(benchmark_map) is not V1BenchmarkMap)
    ):
        raise ValueError("V1_LAYER1_REQUEST_INVALID")
    ready_boundaries = tuple(
        record.observation_boundary
        for record in dataset.records
        if record.status is SwingDailyStatus.READY
        and record.observation_boundary is not None
    )
    if not ready_boundaries:
        raise ValueError("V1_LAYER1_REQUEST_INVALID")
    boundary = min(ready_boundaries)
    benchmark_series = {
        record.canonical_identity: tuple(
            candle for candle in record.candles if candle.timestamp <= boundary
        )
        for record in dataset.records
        if record.status is SwingDailyStatus.READY
        and record.canonical_identity in {"NIFTY", "BANK NIFTY"}
    }
    instruments = tuple(
        _analyze_record(
            record,
            boundary,
            benchmark_map=benchmark_map,
            benchmark_series=benchmark_series,
        )
        for record in dataset.records
    )
    return V1Layer1Run(
        run_identity=(
            f"{SWING_V1_LAYER1_POLICY_BUNDLE_ID}@{boundary.isoformat()}"
        ),
        observation_boundary=boundary,
        policy_bundle=SWING_V1_LAYER1_POLICY_BUNDLE_ID,
        policy_ids=SWING_V1_LAYER1_POLICY_IDS,
        instruments=instruments,
    )


def _analyze_record(
    record: SwingDailySeries,
    boundary: datetime,
    *,
    benchmark_map: V1BenchmarkMap | None,
    benchmark_series: dict[str, tuple[HistoricalCandle, ...]],
) -> V1InstrumentLayer1Evidence:
    if record.status is not SwingDailyStatus.READY:
        reason = (
            record.failure.value
            if record.failure is not None
            else "COMPLETED_DAILY_SERIES_UNAVAILABLE"
        )
        return _unavailable_instrument(
            record.canonical_identity,
            record.asset_class,
            boundary,
            reason,
        )
    candles = tuple(
        candle for candle in record.candles if candle.timestamp <= boundary
    )
    if not candles:
        return _unavailable_instrument(
            record.canonical_identity,
            record.asset_class,
            boundary,
            "COMMON_BOUNDARY_SERIES_UNAVAILABLE",
        )
    benchmark = (
        benchmark_map.benchmark_for(record.canonical_identity)
        if benchmark_map is not None
        else None
    )
    try:
        assessments = tuple(
            _analyze_setup(
                record.canonical_identity,
                record.asset_class,
                boundary,
                candles,
                setup,
                benchmark,
                benchmark_series.get(benchmark) if benchmark is not None else None,
            )
            for setup in (
                V1Setup.PULLBACK_CONTINUATION,
                V1Setup.CONSOLIDATION_BREAKOUT,
            )
        )
    except Exception:
        return _unavailable_instrument(
            record.canonical_identity,
            record.asset_class,
            boundary,
            "UNEXPECTED_LAYER1_ANALYSIS_FAILURE",
        )
    return V1InstrumentLayer1Evidence(
        record.canonical_identity,
        record.asset_class,
        assessments,
    )


def _analyze_setup(
    canonical_identity: str,
    asset_class: SwingUniverseAssetClass,
    boundary: datetime,
    candles: tuple[HistoricalCandle, ...],
    setup: V1Setup,
    benchmark: str | None,
    benchmark_candles: tuple[HistoricalCandle, ...] | None,
) -> V1Layer1Assessment:
    structural = structural_evidence(candles)
    moving_average = moving_average_evidence(candles)
    volume = volume_evidence(candles, setup)
    candle = candle_evidence(candles)
    volatility = volatility_evidence(candles, setup)
    futures_positioning = futures_positioning_evidence(asset_class)
    impulse_maturity = impulse_maturity_evidence(candles, setup)
    relative_context = relative_context_evidence(
        candles,
        asset_class,
        benchmark,
        benchmark_candles,
    )
    gap_context = gap_context_evidence(candles)
    classification, direction, reasons = _form_probable(
        setup,
        structural,
        moving_average,
        candle,
        volatility,
        impulse_maturity,
    )
    reconciliation = {
        ProbableClassification.PROBABLE_CANDIDATE: (
            ReconciliationState.READY_FOR_CONTEXT
        ),
        ProbableClassification.POLICY_UNRESOLVED: (
            ReconciliationState.POLICY_UNRESOLVED
        ),
        ProbableClassification.EVIDENCE_INCOMPLETE: (
            ReconciliationState.EVIDENCE_INCOMPLETE
        ),
        ProbableClassification.NOT_SUPPORTED: ReconciliationState.FAILED,
    }[classification]
    evidence = {
        "volume": volume,
        "candle": candle,
        "volatility": volatility,
        "futures_positioning": futures_positioning,
        "impulse_maturity": impulse_maturity,
        "relative_context": relative_context,
        "gap_context": gap_context,
    }
    missing = tuple(
        name.upper()
        for name, item in evidence.items()
        if item.availability is EvidenceAvailability.UNAVAILABLE
    )
    if structural.availability is EvidenceAvailability.UNAVAILABLE:
        missing = ("STRUCTURAL", *missing)
    if moving_average.sma20_availability is EvidenceAvailability.UNAVAILABLE:
        missing = ("MOVING_AVERAGE_SMA20", *missing)
    unresolved = ["PRODUCTION_PIVOT_DEFINITION_NOT_FROZEN"]
    if moving_average.sma50_availability is EvidenceAvailability.UNAVAILABLE:
        unresolved.append("SMA50_HISTORY_NOT_RETAINED_BY_CURRENT_FACT_BUNDLE")
    if moving_average.sma200_availability is EvidenceAvailability.UNAVAILABLE:
        unresolved.append("SMA200_HISTORY_NOT_RETAINED_BY_CURRENT_FACT_BUNDLE")
    if impulse_maturity.unresolved_fields:
        unresolved.append("PULLBACK_SEQUENCE_POLICY_NOT_FROZEN")
    if impulse_maturity.tie_policy_review:
        unresolved.append(IMPULSE_TIE_POLICY_REVIEW)
    if futures_positioning.availability is EvidenceAvailability.UNAVAILABLE:
        unresolved.append("FUTURES_OI_ROLL_NORMALIZATION_NOT_IMPLEMENTED")
        unresolved.append("FUTURES_OI_POLICY_UNRESOLVED")
    if relative_context.availability is EvidenceAvailability.UNAVAILABLE:
        unresolved.append("RELATIVE_CONTEXT_INPUT_OR_POLICY_INCOMPLETE")
    return V1Layer1Assessment(
        canonical_identity=canonical_identity,
        asset_class=asset_class,
        observation_boundary=boundary,
        setup=setup,
        direction=direction,
        classification=classification,
        reconciliation=reconciliation,
        policy_bundle=SWING_V1_LAYER1_POLICY_BUNDLE_ID,
        policy_ids=SWING_V1_LAYER1_POLICY_IDS,
        structural=structural,
        moving_average=moving_average,
        volume=volume,
        candle=candle,
        volatility=volatility,
        futures_positioning=futures_positioning,
        impulse_maturity=impulse_maturity,
        relative_context=relative_context,
        gap_context=gap_context,
        reasons=reasons,
        missing_evidence=missing,
        unresolved_policies=tuple(unresolved),
        context_gate=(
            TradingViewContextGateState.TRADINGVIEW_CONTEXT_PENDING
            if classification is ProbableClassification.PROBABLE_CANDIDATE
            else TradingViewContextGateState.NOT_ELIGIBLE_UNLESS_PROBABLE
        ),
    )


def _form_probable(
    setup: V1Setup,
    structural: StructuralEvidence,
    moving_average: MovingAverageEvidence,
    candle: CandleEvidence,
    volatility: VolatilityEvidence,
    impulse: ImpulseMaturityEvidence,
) -> tuple[ProbableClassification, V1Direction, tuple[str, ...]]:
    """Apply exact relational facts only; introduce no learned numeric cutoff."""

    if (
        structural.availability is EvidenceAvailability.UNAVAILABLE
        or not structural.alternatives_complete
        or moving_average.sma20_availability is EvidenceAvailability.UNAVAILABLE
        or candle.availability is EvidenceAvailability.UNAVAILABLE
        or volatility.availability is EvidenceAvailability.UNAVAILABLE
    ):
        return (
            ProbableClassification.EVIDENCE_INCOMPLETE,
            V1Direction.NONE,
            ("CORE_LAYER1_EVIDENCE_UNAVAILABLE",),
        )
    if structural.consensus is StructuralState.BULLISH_HH_HL:
        structural_direction = V1Direction.LONG
    elif structural.consensus is StructuralState.BEARISH_LH_LL:
        structural_direction = V1Direction.SHORT
    elif structural.consensus is StructuralState.MIXED_UNCLEAR:
        return (
            ProbableClassification.NOT_SUPPORTED,
            V1Direction.NONE,
            ("STRUCTURE_MIXED_OR_UNCLEAR",),
        )
    else:
        return (
            ProbableClassification.POLICY_UNRESOLVED,
            V1Direction.NONE,
            ("STRUCTURAL_ALTERNATIVES_DO_NOT_AGREE",),
        )
    ma_direction = (
        V1Direction.LONG
        if moving_average.sma20_direction == "UP"
        and moving_average.price_vs_sma20 == "ABOVE"
        else V1Direction.SHORT
        if moving_average.sma20_direction == "DOWN"
        and moving_average.price_vs_sma20 == "BELOW"
        else V1Direction.NONE
    )
    if ma_direction is not structural_direction:
        return (
            ProbableClassification.POLICY_UNRESOLVED,
            V1Direction.NONE,
            ("STRUCTURE_AND_SMA20_TREND_QUALITY_DO_NOT_ALIGN",),
        )
    if setup is V1Setup.CONSOLIDATION_BREAKOUT:
        required_location = (
            "ABOVE" if structural_direction is V1Direction.LONG else "BELOW"
        )
        setup_event = volatility.close_vs_preceding_range == required_location
        event_reason = "COMPLETED_CLOSE_OUTSIDE_PRECEDING_TEN_BAR_RANGE"
    else:
        required_label = (
            "ACCEPTANCE_ABOVE_PREVIOUS_HIGH"
            if structural_direction is V1Direction.LONG
            else "ACCEPTANCE_BELOW_PREVIOUS_LOW"
        )
        setup_event = (
            required_label in candle.interpretations
            and impulse.availability is EvidenceAvailability.AVAILABLE
            and impulse.impulse_direction is structural_direction
        )
        event_reason = "COMPLETED_CONTINUATION_ACCEPTANCE_AFTER_IMPULSE_CANDIDATE"
    if not setup_event:
        reason = (
            "IMPULSE_TIE_SELECTED_DIRECTION_DOES_NOT_ALIGN"
            if setup is V1Setup.PULLBACK_CONTINUATION
            and impulse.tie_policy_review
            and required_label in candle.interpretations
            and impulse.impulse_direction is not structural_direction
            else "SETUP_SPECIFIC_EVENT_NOT_OBSERVED"
        )
        return (
            ProbableClassification.NOT_SUPPORTED,
            structural_direction,
            (reason,),
        )
    return (
        ProbableClassification.PROBABLE_CANDIDATE,
        structural_direction,
        (
            "STRUCTURAL_ALTERNATIVES_AGREE",
            "SMA20_TREND_QUALITY_ALIGNS",
            event_reason,
        ),
    )


def _unavailable_instrument(
    canonical_identity: str,
    asset_class: SwingUniverseAssetClass,
    boundary: datetime,
    reason: str,
) -> V1InstrumentLayer1Evidence:
    return V1InstrumentLayer1Evidence(
        canonical_identity,
        asset_class,
        tuple(
            _unavailable_assessment(
                canonical_identity,
                asset_class,
                boundary,
                setup,
                reason,
            )
            for setup in (
                V1Setup.PULLBACK_CONTINUATION,
                V1Setup.CONSOLIDATION_BREAKOUT,
            )
        ),
    )


def _unavailable_assessment(
    canonical_identity: str,
    asset_class: SwingUniverseAssetClass,
    boundary: datetime,
    setup: V1Setup,
    reason: str,
) -> V1Layer1Assessment:
    unavailable = EvidenceAvailability.UNAVAILABLE
    structural = StructuralEvidence(
        unavailable,
        tuple(
            _empty_structural_alternative(radius) for radius in (1, 2)
        ),
        None,
        False,
        False,
        False,
    )
    return V1Layer1Assessment(
        canonical_identity=canonical_identity,
        asset_class=asset_class,
        observation_boundary=boundary,
        setup=setup,
        direction=V1Direction.NONE,
        classification=ProbableClassification.EVIDENCE_INCOMPLETE,
        reconciliation=ReconciliationState.EVIDENCE_INCOMPLETE,
        policy_bundle=SWING_V1_LAYER1_POLICY_BUNDLE_ID,
        policy_ids=SWING_V1_LAYER1_POLICY_IDS,
        structural=structural,
        moving_average=MovingAverageEvidence(
            sma20_availability=unavailable,
            sma50_availability=unavailable,
            sma200_availability=unavailable,
            completed_history_count=0,
            sma20_required_candles=25,
            sma50_required_candles=55,
            sma200_required_candles=200,
            sma20=None,
            sma50=None,
            sma200=None,
            sma20_direction=None,
            sma50_direction=None,
            price_vs_sma20=None,
            price_vs_sma50=None,
            crisscross20_count=None,
            persistent_separation20=None,
            interaction_labels=(),
        ),
        volume=VolumeEvidence(
            availability=unavailable,
            current_volume=None,
            normal_mean_volume=None,
            normal_median_volume=None,
            comparison_mean_volume=None,
            comparison_role=None,
            relative_mean=None,
            relative_median=None,
            percentile20=None,
            breakout_vs_consolidation_mean=None,
            resumption_vs_pullback_mean=None,
            pullback_vs_prior_impulse_mean=None,
            measurement_only=True,
            policy_interpretation="POLICY_UNRESOLVED_NO_THRESHOLD",
            reason=reason,
        ),
        candle=CandleEvidence(
            unavailable,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            (),
            False,
            reason,
        ),
        volatility=VolatilityEvidence(
            availability=unavailable,
            range_atr_ratio=None,
            nr4=None,
            nr7=None,
            inside_day=None,
            range_percentile20=None,
            short_vs_long=None,
            prebreak_short_vs_long=None,
            breakout_vs_prebreak=None,
            close_vs_preceding_range=None,
            measurement_only=True,
            setup_role=(
                "SUPPORTING_EVIDENCE"
                if setup is V1Setup.PULLBACK_CONTINUATION
                else "SETUP_QUALITY_EVIDENCE"
            ),
            directional_authority=False,
            reason=reason,
        ),
        futures_positioning=FuturesPositioningEvidence(
            availability=unavailable,
            price_change=None,
            open_interest_change=None,
            interpretation=None,
            multi_session_persistence=None,
            roll_normalized=None,
            future_dependency=(
                "CONTRACT_IDENTITY_EXPIRY_ROLL_ADJUSTED_OI_SERIES"
            ),
            reason=reason,
        ),
        impulse_maturity=ImpulseMaturityEvidence(
            availability=unavailable,
            candidates=(),
            selected_candidate_identity=None,
            tied_candidate_identities=(),
            selection_policy="MAX_RANGE_ATR_THEN_EARLIEST_INDEX",
            tie_policy_review=False,
            impulse_candle_index=None,
            impulse_direction=None,
            impulse_range_atr=None,
            impulse_body_quality=None,
            impulse_close_quality=None,
            impulse_volume=None,
            bars_since_impulse=None,
            trend_leg_age=None,
            pullback_depth_fraction=None,
            fraction_of_impulse_retained=None,
            pullback_bar_count=None,
            pullback_sequence_number=None,
            prior_pullbacks_in_leg=None,
            unresolved_fields=(
                "pullback_sequence_number",
                "prior_pullbacks_in_leg",
            ),
            measurement_only=True,
            reason=reason,
        ),
        relative_context=RelativeContextEvidence(
            unavailable,
            None,
            None,
            None,
            None,
            None,
            None,
            False,
            reason,
        ),
        gap_context=GapContextEvidence(
            unavailable,
            None,
            None,
            None,
            None,
            "DEFERRED",
            False,
            False,
            reason,
        ),
        reasons=(reason,),
        missing_evidence=(
            "STRUCTURAL",
            "MOVING_AVERAGE",
            "VOLUME",
            "CANDLE",
            "VOLATILITY",
            "FUTURES_POSITIONING",
            "IMPULSE_MATURITY",
            "RELATIVE_CONTEXT",
            "GAP_CONTEXT",
        ),
        unresolved_policies=("LAYER1_INPUT_UNAVAILABLE",),
        context_gate=TradingViewContextGateState.NOT_ELIGIBLE_UNLESS_PROBABLE,
    )


def _empty_structural_alternative(radius: int) -> StructuralAlternative:
    return StructuralAlternative(
        f"FRACTAL_UNIQUE_EXTREME_RADIUS_{radius}",
        radius,
        EvidenceAvailability.UNAVAILABLE,
        StructuralState.EVIDENCE_INCOMPLETE,
        (),
        (),
    )


__all__ = ["analyze_v1_layer1"]
