"""Deterministic measurement functions for Swing V1 Layer-1 evidence."""

from __future__ import annotations

import math
import statistics

from kronos.provider.contracts.market_data import HistoricalCandle
from kronos.swing.universe import SwingUniverseAssetClass
from kronos.swing.v1.models import (
    CandleEvidence,
    EvidenceAvailability,
    FuturesPositioningEvidence,
    FuturesPositioningInterpretation,
    GapContextEvidence,
    ImpulseCandidateEvidence,
    ImpulseMaturityEvidence,
    MovingAverageEvidence,
    PivotCandidate,
    PivotKind,
    RelativeContextEvidence,
    StructuralAlternative,
    StructuralEvidence,
    StructuralState,
    V1Direction,
    V1Setup,
    VolatilityEvidence,
    VolumeEvidence,
)


_SMA20 = 20
_SMA50 = 50
_SMA200 = 200
_SLOPE_BARS = 5
_ATR_PERIOD = 14
_CONSOLIDATION_WINDOW = 10
_SMA20_HISTORY_REQUIREMENT = 25
_SMA50_HISTORY_REQUIREMENT = 55
_SMA200_HISTORY_REQUIREMENT = 200
_IMPULSE_SELECTION_POLICY = "MAX_RANGE_ATR_THEN_EARLIEST_INDEX"
_FUTURES_OI_FUTURE_DEPENDENCY = (
    "CONTRACT_IDENTITY_EXPIRY_ROLL_ADJUSTED_OI_SERIES"
)


def structural_evidence(
    candles: tuple[HistoricalCandle, ...],
) -> StructuralEvidence:
    """Retain both approved research alternatives without choosing one."""

    alternatives = tuple(_structural_alternative(candles, radius) for radius in (1, 2))
    states = tuple(
        item.state
        for item in alternatives
        if item.availability is EvidenceAvailability.AVAILABLE
    )
    consensus = states[0] if len(states) == 2 and states[0] is states[1] else None
    complete = len(states) == 2
    agree = complete and len(set(states)) == 1
    disagree = complete and len(set(states)) != 1
    availability = (
        EvidenceAvailability.AVAILABLE
        if states
        else EvidenceAvailability.UNAVAILABLE
    )
    return StructuralEvidence(
        availability,
        alternatives,
        consensus,
        complete,
        agree,
        disagree,
    )


def moving_average_evidence(
    candles: tuple[HistoricalCandle, ...],
) -> MovingAverageEvidence:
    """Measure available MA facts and retain longer-history gaps explicitly."""

    closes = tuple(item.close for item in candles)
    sma20 = _sma(closes, _SMA20)
    sma50 = _sma(closes, _SMA50)
    sma200 = _sma(closes, _SMA200)
    prior20 = _sma(closes[:-_SLOPE_BARS], _SMA20)
    prior50 = _sma(closes[:-_SLOPE_BARS], _SMA50)
    if sma20 is None or prior20 is None:
        return MovingAverageEvidence(
            sma20_availability=EvidenceAvailability.UNAVAILABLE,
            sma50_availability=EvidenceAvailability.UNAVAILABLE,
            sma200_availability=EvidenceAvailability.UNAVAILABLE,
            completed_history_count=len(candles),
            sma20_required_candles=_SMA20_HISTORY_REQUIREMENT,
            sma50_required_candles=_SMA50_HISTORY_REQUIREMENT,
            sma200_required_candles=_SMA200_HISTORY_REQUIREMENT,
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
        )

    crosses = 0
    for index in range(_SMA20, len(candles)):
        current_sma = statistics.fmean(closes[index - _SMA20 + 1 : index + 1])
        previous_sma = statistics.fmean(closes[index - _SMA20 : index])
        current_side = candles[index].close - current_sma
        previous_side = candles[index - 1].close - previous_sma
        crosses += current_side * previous_side < 0.0

    recent_sides = tuple(
        candles[index].close
        - statistics.fmean(closes[index - _SMA20 + 1 : index + 1])
        for index in range(max(_SMA20 - 1, len(candles) - 5), len(candles))
    )
    persistent = bool(recent_sides) and (
        all(item > 0.0 for item in recent_sides)
        or all(item < 0.0 for item in recent_sides)
    )
    current = candles[-1]
    labels = []
    if current.low <= sma20 <= current.high:
        labels.append("SMA20_TOUCHED")
        if current.close > sma20:
            labels.append("SMA20_SUPPORT_INTERACTION")
        elif current.close < sma20:
            labels.append("SMA20_REJECTION_INTERACTION")
    retained_sma50 = sma50 if prior50 is not None else None
    return MovingAverageEvidence(
        sma20_availability=EvidenceAvailability.AVAILABLE,
        sma50_availability=_availability(retained_sma50),
        sma200_availability=_availability(sma200),
        completed_history_count=len(candles),
        sma20_required_candles=_SMA20_HISTORY_REQUIREMENT,
        sma50_required_candles=_SMA50_HISTORY_REQUIREMENT,
        sma200_required_candles=_SMA200_HISTORY_REQUIREMENT,
        sma20=sma20,
        sma50=retained_sma50,
        sma200=sma200,
        sma20_direction=_direction(sma20, prior20),
        sma50_direction=_direction(retained_sma50, prior50),
        price_vs_sma20=_relative(current.close, sma20),
        price_vs_sma50=_relative(current.close, retained_sma50),
        crisscross20_count=crosses,
        persistent_separation20=persistent,
        interaction_labels=tuple(labels),
    )


def volume_evidence(
    candles: tuple[HistoricalCandle, ...],
    setup: V1Setup,
) -> VolumeEvidence:
    """Return setup-aware volume measurements without production cutoffs."""

    volumes = tuple(item.volume for item in candles)
    if len(volumes) < 21 or any(item <= 0 for item in volumes[-21:]):
        return VolumeEvidence(
            availability=EvidenceAvailability.UNAVAILABLE,
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
            reason="POSITIVE_COMPLETED_VOLUME_HISTORY_UNAVAILABLE",
        )
    current = volumes[-1]
    baseline = volumes[-21:-1]
    relative_mean = current / statistics.fmean(baseline)
    relative_median = current / statistics.median(baseline)
    percentile = sum(item <= current for item in baseline) / len(baseline)
    if setup is V1Setup.CONSOLIDATION_BREAKOUT:
        comparison_mean = statistics.fmean(volumes[-11:-1])
        return VolumeEvidence(
            availability=EvidenceAvailability.AVAILABLE,
            current_volume=current,
            normal_mean_volume=statistics.fmean(baseline),
            normal_median_volume=statistics.median(baseline),
            comparison_mean_volume=comparison_mean,
            comparison_role="CONSOLIDATION_MEAN",
            relative_mean=relative_mean,
            relative_median=relative_median,
            percentile20=percentile,
            breakout_vs_consolidation_mean=current / comparison_mean,
            resumption_vs_pullback_mean=None,
            pullback_vs_prior_impulse_mean=None,
            measurement_only=True,
            policy_interpretation="POLICY_UNRESOLVED_NO_THRESHOLD",
            reason=None,
        )
    comparison_mean = statistics.fmean(volumes[-6:-1])
    return VolumeEvidence(
        availability=EvidenceAvailability.AVAILABLE,
        current_volume=current,
        normal_mean_volume=statistics.fmean(baseline),
        normal_median_volume=statistics.median(baseline),
        comparison_mean_volume=comparison_mean,
        comparison_role="PULLBACK_MEAN",
        relative_mean=relative_mean,
        relative_median=relative_median,
        percentile20=percentile,
        breakout_vs_consolidation_mean=None,
        resumption_vs_pullback_mean=current / comparison_mean,
        pullback_vs_prior_impulse_mean=(
            comparison_mean / statistics.fmean(volumes[-11:-6])
        ),
        measurement_only=True,
        policy_interpretation="POLICY_UNRESOLVED_NO_THRESHOLD",
        reason=None,
    )


def candle_evidence(
    candles: tuple[HistoricalCandle, ...],
) -> CandleEvidence:
    """Describe the current completed candle without named-pattern authority."""

    if len(candles) < 15:
        return _unavailable_candle("INSUFFICIENT_COMPLETED_HISTORY")
    current = candles[-1]
    previous = candles[-2]
    span = current.high - current.low
    current_atr = _atr(candles)
    if span <= 0.0 or current_atr is None or current_atr <= 0.0:
        return _unavailable_candle("NON_POSITIVE_RANGE_OR_ATR")
    body = abs(current.close - current.open)
    upper = current.high - max(current.open, current.close)
    lower = min(current.open, current.close) - current.low
    preceding = candles[-(_CONSOLIDATION_WINDOW + 1) : -1]
    range_high = max(item.high for item in preceding)
    range_low = min(item.low for item in preceding)
    previous_span = previous.high - previous.low
    labels = [
        "EXPANSION"
        if span > previous_span
        else "CONTRACTION"
        if span < previous_span
        else "UNCHANGED_RANGE"
    ]
    if current.close > previous.high:
        labels.append("ACCEPTANCE_ABOVE_PREVIOUS_HIGH")
    if current.close < previous.low:
        labels.append("ACCEPTANCE_BELOW_PREVIOUS_LOW")
    if current.high > range_high and current.close <= range_high:
        labels.append("REJECTION_ABOVE_PRECEDING_RANGE")
    if current.low < range_low and current.close >= range_low:
        labels.append("REJECTION_BELOW_PRECEDING_RANGE")
    if current.open == current.close:
        labels.append("INDECISION_EXACT_DOJI")
    if range_low <= current.close <= range_high:
        labels.append("CLOSE_BACK_INSIDE_PRECEDING_RANGE")
    return CandleEvidence(
        EvidenceAvailability.AVAILABLE,
        span,
        body,
        body / span,
        upper / span,
        lower / span,
        (current.close - current.low) / span,
        span / current_atr,
        tuple(labels),
        False,
        None,
    )


def volatility_evidence(
    candles: tuple[HistoricalCandle, ...],
    setup: V1Setup,
) -> VolatilityEvidence:
    """Measure normalized range behavior without a production quality gate."""

    ranges = tuple(item.high - item.low for item in candles)
    current_atr = _atr(candles)
    if len(ranges) < 20 or current_atr is None or current_atr <= 0.0:
        return VolatilityEvidence(
            availability=EvidenceAvailability.UNAVAILABLE,
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
            reason="INSUFFICIENT_COMPLETED_RANGE_HISTORY",
        )
    current = ranges[-1]
    percentile = sum(item <= current for item in ranges[-20:-1]) / 19
    common = dict(
        availability=EvidenceAvailability.AVAILABLE,
        range_atr_ratio=current / current_atr,
        nr4=current == min(ranges[-4:]),
        nr7=current == min(ranges[-7:]),
        inside_day=(
            candles[-1].high <= candles[-2].high
            and candles[-1].low >= candles[-2].low
        ),
        range_percentile20=percentile,
        short_vs_long=statistics.fmean(ranges[-5:])
        / statistics.fmean(ranges[-20:]),
        measurement_only=True,
        setup_role=(
            "SUPPORTING_EVIDENCE"
            if setup is V1Setup.PULLBACK_CONTINUATION
            else "SETUP_QUALITY_EVIDENCE"
        ),
        directional_authority=False,
        reason=None,
    )
    if setup is V1Setup.PULLBACK_CONTINUATION:
        return VolatilityEvidence(
            **common,
            prebreak_short_vs_long=None,
            breakout_vs_prebreak=None,
            close_vs_preceding_range=None,
        )
    preceding = candles[-(_CONSOLIDATION_WINDOW + 1) : -1]
    range_high = max(item.high for item in preceding)
    range_low = min(item.low for item in preceding)
    return VolatilityEvidence(
        **common,
        prebreak_short_vs_long=statistics.fmean(ranges[-6:-1])
        / statistics.fmean(ranges[-20:-6]),
        breakout_vs_prebreak=current / statistics.fmean(ranges[-6:-1]),
        close_vs_preceding_range=(
            "ABOVE"
            if candles[-1].close > range_high
            else "BELOW"
            if candles[-1].close < range_low
            else "INSIDE"
        ),
    )


def futures_positioning_evidence(
    asset_class: SwingUniverseAssetClass,
) -> FuturesPositioningEvidence:
    """Preserve the current OI/roll gap rather than fabricate continuity."""

    if asset_class is not SwingUniverseAssetClass.MCX_COMMODITY:
        return FuturesPositioningEvidence(
            EvidenceAvailability.NOT_APPLICABLE,
            None,
            None,
            None,
            None,
            None,
            _FUTURES_OI_FUTURE_DEPENDENCY,
            "NON_FUTURES_ANALYTICAL_SUBJECT",
        )
    return FuturesPositioningEvidence(
        EvidenceAvailability.UNAVAILABLE,
        None,
        None,
        None,
        None,
        False,
        _FUTURES_OI_FUTURE_DEPENDENCY,
        "HISTORICAL_DAILY_CONTRACT_HAS_NO_OI_AND_ROLL_NORMALIZATION_IS_UNRESOLVED",
    )


def interpret_futures_positioning(
    price_change: float,
    open_interest_change: int,
    *,
    roll_normalized: bool,
) -> FuturesPositioningInterpretation | None:
    """Apply approved vocabulary only after roll-normalized facts are proven."""

    if (
        type(price_change) is not float
        or not math.isfinite(price_change)
        or type(open_interest_change) is not int
        or type(roll_normalized) is not bool
        or not roll_normalized
        or price_change == 0.0
        or open_interest_change == 0
    ):
        return None
    if price_change > 0.0 and open_interest_change > 0:
        return FuturesPositioningInterpretation.LONG_BUILDUP
    if price_change < 0.0 and open_interest_change > 0:
        return FuturesPositioningInterpretation.SHORT_BUILDUP
    if price_change > 0.0 and open_interest_change < 0:
        return FuturesPositioningInterpretation.SHORT_COVERING
    return FuturesPositioningInterpretation.LONG_UNWINDING


def impulse_maturity_evidence(
    candles: tuple[HistoricalCandle, ...],
    setup: V1Setup,
) -> ImpulseMaturityEvidence:
    """Retain a deterministic impulse candidate and unresolved sequence fields."""

    if setup is not V1Setup.PULLBACK_CONTINUATION:
        return ImpulseMaturityEvidence(
            availability=EvidenceAvailability.NOT_APPLICABLE,
            candidates=(),
            selected_candidate_identity=None,
            tied_candidate_identities=(),
            selection_policy=_IMPULSE_SELECTION_POLICY,
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
            unresolved_fields=(),
            measurement_only=True,
            reason="BREAKOUT_SETUP",
        )
    current_atr = _atr(candles)
    if current_atr is None or current_atr <= 0.0 or len(candles) < 15:
        return ImpulseMaturityEvidence(
            availability=EvidenceAvailability.UNAVAILABLE,
            candidates=(),
            selected_candidate_identity=None,
            tied_candidate_identities=(),
            selection_policy=_IMPULSE_SELECTION_POLICY,
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
            reason="INSUFFICIENT_IMPULSE_HISTORY",
        )
    candidates: list[ImpulseCandidateEvidence] = []
    for index in range(max(1, len(candles) - 15), len(candles) - 1):
        candle = candles[index]
        span = candle.high - candle.low
        if span > 0.0:
            direction = (
                V1Direction.LONG
                if candle.close >= candle.open
                else V1Direction.SHORT
            )
            candidates.append(
                ImpulseCandidateEvidence(
                    candidate_identity=(
                        f"IMPULSE@{index}@{candle.timestamp.isoformat()}"
                    ),
                    candle_index=index,
                    timestamp=candle.timestamp,
                    direction=direction,
                    range_atr=span / current_atr,
                    body_quality=abs(candle.close - candle.open) / span,
                    close_quality=(
                        (candle.close - candle.low) / span
                        if direction is V1Direction.LONG
                        else (candle.high - candle.close) / span
                    ),
                    volume=candle.volume,
                )
            )
    if not candidates:
        return ImpulseMaturityEvidence(
            availability=EvidenceAvailability.UNAVAILABLE,
            candidates=(),
            selected_candidate_identity=None,
            tied_candidate_identities=(),
            selection_policy=_IMPULSE_SELECTION_POLICY,
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
            reason="NO_POSITIVE_RANGE_IMPULSE_CANDIDATE",
        )
    max_strength = max(item.range_atr for item in candidates)
    tied = tuple(item for item in candidates if item.range_atr == max_strength)
    selected = min(tied, key=lambda item: item.candle_index)
    index = selected.candle_index
    impulse = candles[index]
    direction = selected.direction
    later = candles[index + 1 :]
    if direction is V1Direction.LONG:
        peak = max((impulse.high, *(item.high for item in later)))
        denominator = peak - impulse.low
        depth = (peak - candles[-1].close) / denominator if denominator > 0.0 else None
    else:
        peak = min((impulse.low, *(item.low for item in later)))
        denominator = impulse.high - peak
        depth = (candles[-1].close - peak) / denominator if denominator > 0.0 else None
    retained = None if depth is None else 1.0 - depth
    age = len(candles) - 1 - index
    tie_policy_review = len({item.direction for item in tied}) > 1
    unresolved_fields = [
        "pullback_sequence_number",
        "prior_pullbacks_in_leg",
    ]
    if tie_policy_review:
        unresolved_fields.append("impulse_tie_policy")
    return ImpulseMaturityEvidence(
        availability=EvidenceAvailability.AVAILABLE,
        candidates=tuple(candidates),
        selected_candidate_identity=selected.candidate_identity,
        tied_candidate_identities=tuple(
            item.candidate_identity for item in tied
        ),
        selection_policy=_IMPULSE_SELECTION_POLICY,
        tie_policy_review=tie_policy_review,
        impulse_candle_index=index,
        impulse_direction=direction,
        impulse_range_atr=selected.range_atr,
        impulse_body_quality=selected.body_quality,
        impulse_close_quality=selected.close_quality,
        impulse_volume=impulse.volume,
        bars_since_impulse=age,
        trend_leg_age=age,
        pullback_depth_fraction=depth,
        fraction_of_impulse_retained=retained,
        pullback_bar_count=len(later),
        pullback_sequence_number=None,
        prior_pullbacks_in_leg=None,
        unresolved_fields=tuple(unresolved_fields),
        measurement_only=True,
        reason=None,
    )


def relative_context_evidence(
    candles: tuple[HistoricalCandle, ...],
    asset_class: SwingUniverseAssetClass,
    benchmark: str | None,
    benchmark_candles: tuple[HistoricalCandle, ...] | None,
) -> RelativeContextEvidence:
    """Measure matched benchmark context when mapping and aligned facts exist."""

    if asset_class is SwingUniverseAssetClass.MCX_COMMODITY:
        return RelativeContextEvidence(
            EvidenceAvailability.UNAVAILABLE,
            None,
            None,
            None,
            None,
            None,
            None,
            False,
            "COMMODITY_BENCHMARK_ARCHITECTURE_UNRESOLVED",
        )
    if asset_class is SwingUniverseAssetClass.NSE_INDEX:
        return RelativeContextEvidence(
            EvidenceAvailability.NOT_APPLICABLE,
            None,
            None,
            None,
            None,
            None,
            None,
            False,
            "INDEX_IS_CONTEXT_SERIES",
        )
    if benchmark is None or benchmark_candles is None:
        return RelativeContextEvidence(
            EvidenceAvailability.UNAVAILABLE,
            benchmark,
            None,
            None,
            None,
            None,
            None,
            False,
            "RELIABLE_MATCHED_BENCHMARK_UNAVAILABLE",
        )
    subject = {item.timestamp: item.close for item in candles}
    reference = {item.timestamp: item.close for item in benchmark_candles}
    common = sorted(set(subject) & set(reference))
    if len(common) < 20:
        return RelativeContextEvidence(
            EvidenceAvailability.UNAVAILABLE,
            benchmark,
            len(common),
            None,
            None,
            None,
            None,
            False,
            "INSUFFICIENT_ALIGNED_BENCHMARK_HISTORY",
        )
    start, end = common[-20], common[-1]
    subject_return = subject[end] / subject[start] - 1.0
    benchmark_return = reference[end] / reference[start] - 1.0
    difference = subject_return - benchmark_return
    return RelativeContextEvidence(
        EvidenceAvailability.AVAILABLE,
        benchmark,
        20,
        subject_return,
        benchmark_return,
        difference,
        (
            "RELATIVE_STRENGTH"
            if difference > 0.0
            else "RELATIVE_WEAKNESS"
            if difference < 0.0
            else "NEUTRAL_MIXED"
        ),
        False,
        None,
    )


def gap_context_evidence(
    candles: tuple[HistoricalCandle, ...],
) -> GapContextEvidence:
    """Measure gaps and distance from ordinary structure without trade authority."""

    current_atr = _atr(candles)
    if len(candles) < 21 or current_atr is None or current_atr <= 0.0:
        return GapContextEvidence(
            EvidenceAvailability.UNAVAILABLE,
            None,
            None,
            None,
            None,
            "DEFERRED",
            False,
            False,
            "INSUFFICIENT_COMPLETED_GAP_HISTORY",
        )
    current, previous = candles[-1], candles[-2]
    recent = candles[-21:-1]
    recent_high = max(item.high for item in recent)
    recent_low = min(item.low for item in recent)
    distance = (
        0.0
        if recent_low <= current.close <= recent_high
        else min(abs(current.close - recent_low), abs(current.close - recent_high))
    )
    return GapContextEvidence(
        EvidenceAvailability.AVAILABLE,
        (current.open - previous.close) / current_atr,
        (current.high - current.low) / current_atr,
        distance / current_atr,
        (
            "UP"
            if current.close > current.open
            else "DOWN"
            if current.close < current.open
            else "NEUTRAL"
        ),
        "DEFERRED",
        False,
        False,
        None,
    )


def _structural_alternative(
    candles: tuple[HistoricalCandle, ...],
    radius: int,
) -> StructuralAlternative:
    highs, lows = _pivots(candles, radius)
    retained_highs = highs[-3:]
    retained_lows = lows[-3:]
    if len(highs) < 2 or len(lows) < 2:
        return StructuralAlternative(
            f"FRACTAL_UNIQUE_EXTREME_RADIUS_{radius}",
            radius,
            EvidenceAvailability.UNAVAILABLE,
            StructuralState.EVIDENCE_INCOMPLETE,
            retained_highs,
            retained_lows,
        )
    higher_high = highs[-1].value > highs[-2].value
    lower_high = highs[-1].value < highs[-2].value
    higher_low = lows[-1].value > lows[-2].value
    lower_low = lows[-1].value < lows[-2].value
    state = (
        StructuralState.BULLISH_HH_HL
        if higher_high and higher_low
        else StructuralState.BEARISH_LH_LL
        if lower_high and lower_low
        else StructuralState.MIXED_UNCLEAR
    )
    return StructuralAlternative(
        f"FRACTAL_UNIQUE_EXTREME_RADIUS_{radius}",
        radius,
        EvidenceAvailability.AVAILABLE,
        state,
        retained_highs,
        retained_lows,
    )


def _pivots(
    candles: tuple[HistoricalCandle, ...],
    radius: int,
) -> tuple[tuple[PivotCandidate, ...], tuple[PivotCandidate, ...]]:
    highs = []
    lows = []
    for index in range(radius, len(candles) - radius):
        window = candles[index - radius : index + radius + 1]
        current = candles[index]
        if current.high == max(item.high for item in window) and sum(
            item.high == current.high for item in window
        ) == 1:
            highs.append(PivotCandidate(PivotKind.HIGH, index, current.timestamp, current.high))
        if current.low == min(item.low for item in window) and sum(
            item.low == current.low for item in window
        ) == 1:
            lows.append(PivotCandidate(PivotKind.LOW, index, current.timestamp, current.low))
    return tuple(highs), tuple(lows)


def _atr(
    candles: tuple[HistoricalCandle, ...],
    period: int = _ATR_PERIOD,
) -> float | None:
    end = len(candles) - 1
    if end < period:
        return None
    values = []
    for index in range(end - period + 1, end + 1):
        candle = candles[index]
        previous_close = candles[index - 1].close
        values.append(
            max(
                candle.high - candle.low,
                abs(candle.high - previous_close),
                abs(candle.low - previous_close),
            )
        )
    return statistics.fmean(values)


def _sma(values: tuple[float, ...], period: int) -> float | None:
    return statistics.fmean(values[-period:]) if len(values) >= period else None


def _availability(value: object) -> EvidenceAvailability:
    return (
        EvidenceAvailability.AVAILABLE
        if value is not None
        else EvidenceAvailability.UNAVAILABLE
    )


def _direction(current: float | None, previous: float | None) -> str | None:
    if current is None or previous is None:
        return None
    return "UP" if current > previous else "DOWN" if current < previous else "FLAT"


def _relative(price: float, average: float | None) -> str | None:
    if average is None:
        return None
    return "ABOVE" if price > average else "BELOW" if price < average else "AT"


def _unavailable_candle(reason: str) -> CandleEvidence:
    return CandleEvidence(
        EvidenceAvailability.UNAVAILABLE,
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
    )


__all__ = [
    "candle_evidence",
    "futures_positioning_evidence",
    "gap_context_evidence",
    "impulse_maturity_evidence",
    "interpret_futures_positioning",
    "moving_average_evidence",
    "relative_context_evidence",
    "structural_evidence",
    "volatility_evidence",
    "volume_evidence",
]
