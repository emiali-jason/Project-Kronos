"""Executable Swing Zero V0 classification policy."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import math

from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.market_data import (
    HistoricalCandle,
    HistoricalCandleRequest,
    HistoricalInterval,
)


SWING_ZERO_POLICY_ID = "SWING-ZERO-V0-CLASSIFICATION-POLICY"
MINIMUM_LOOKBACK = 25
_SMA_PERIOD = 20
_SMA_SLOPE_BARS = 5
_PULLBACK_WINDOW = 5
_ATR_PERIOD = 14
_CONSOLIDATION_WINDOW = 10
_CONSOLIDATION_ATR_MULTIPLE = 2.5


class SwingDirection(StrEnum):
    """Direction assigned by one setup-family evaluation."""

    LONG = "LONG"
    SHORT = "SHORT"
    NONE = "NONE"


class SwingSetup(StrEnum):
    """Frozen Swing Zero setup identities."""

    PULLBACK_CONTINUATION = "PULLBACK_CONTINUATION"
    CONSOLIDATION_BREAKOUT = "CONSOLIDATION_BREAKOUT"
    NONE = "NONE"


class SwingState(StrEnum):
    """Frozen Swing Zero setup states."""

    NO_SETUP = "NO_SETUP"
    FORMING = "FORMING"
    QUALIFIED = "QUALIFIED"


class SwingTrend(StrEnum):
    """Deterministic SMA20 trend classification."""

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class SwingAnalysisFailure(StrEnum):
    """Typed fail-closed Swing Zero input failures."""

    INVALID_REQUEST = "INVALID_REQUEST"
    INTERVAL_NOT_DAILY = "INTERVAL_NOT_DAILY"
    INSUFFICIENT_LOOKBACK = "INSUFFICIENT_LOOKBACK"
    MALFORMED_OBSERVATION = "MALFORMED_OBSERVATION"
    DUPLICATE_OBSERVATION_BOUNDARY = "DUPLICATE_OBSERVATION_BOUNDARY"
    NON_MONOTONIC_OBSERVATIONS = "NON_MONOTONIC_OBSERVATIONS"
    INCOMPLETE_OBSERVATION = "INCOMPLETE_OBSERVATION"
    DATA_QUALITY_UNAVAILABLE = "DATA_QUALITY_UNAVAILABLE"


class SwingAnalysisError(RuntimeError):
    """Swing failure retaining no Provider payload or implementation detail."""

    def __init__(self, failure: SwingAnalysisFailure) -> None:
        self.failure = failure
        super().__init__(failure.value)


@dataclass(frozen=True, slots=True)
class SwingAssessment:
    """Immutable result for one independently evaluated setup family."""

    instrument: InstrumentRecord
    observation_boundary: datetime
    rule_set_version: str
    direction: SwingDirection
    setup: SwingSetup
    state: SwingState
    why: str
    evidence_for: tuple[str, ...]
    evidence_against_or_risks: tuple[str, ...]
    entry_zone: None = None
    invalidation: None = None
    stop: None = None
    targets: None = None
    risk_reward: None = None
    next_required_event: str | None = None

    def __post_init__(self) -> None:
        if (
            type(self.instrument) is not InstrumentRecord
            or not _aware(self.observation_boundary)
            or self.rule_set_version != SWING_ZERO_POLICY_ID
            or type(self.direction) is not SwingDirection
            or type(self.setup) is not SwingSetup
            or self.setup is SwingSetup.NONE
            or type(self.state) is not SwingState
            or not self.why
            or type(self.evidence_for) is not tuple
            or type(self.evidence_against_or_risks) is not tuple
            or any(not item for item in self.evidence_for)
            or any(not item for item in self.evidence_against_or_risks)
            or any(
                value is not None
                for value in (
                    self.entry_zone,
                    self.invalidation,
                    self.stop,
                    self.targets,
                    self.risk_reward,
                )
            )
        ):
            raise ValueError("SWING_ASSESSMENT_INVALID")


@dataclass(frozen=True, slots=True)
class _SharedFacts:
    current_close: float
    current_sma20: float
    prior_sma20: float
    trend: SwingTrend


def analyze_swing_zero(
    request: HistoricalCandleRequest,
    candles: Sequence[HistoricalCandle],
) -> tuple[SwingAssessment, SwingAssessment]:
    """Evaluate both frozen V0 setup families without ranking either result."""

    observations = _validated_observations(request, candles)
    shared = _shared_facts(observations)
    return (
        _evaluate_pullback(request.instrument, observations, shared),
        _evaluate_breakout(request.instrument, observations, shared),
    )


def _validated_observations(
    request: HistoricalCandleRequest,
    candles: Sequence[HistoricalCandle],
) -> tuple[HistoricalCandle, ...]:
    if type(request) is not HistoricalCandleRequest:
        raise SwingAnalysisError(SwingAnalysisFailure.INVALID_REQUEST)
    if request.interval is not HistoricalInterval.DAY:
        raise SwingAnalysisError(SwingAnalysisFailure.INTERVAL_NOT_DAILY)
    if isinstance(candles, (str, bytes)) or not isinstance(candles, Sequence):
        raise SwingAnalysisError(SwingAnalysisFailure.MALFORMED_OBSERVATION)
    observations = tuple(candles)
    if len(observations) < MINIMUM_LOOKBACK:
        raise SwingAnalysisError(SwingAnalysisFailure.INSUFFICIENT_LOOKBACK)
    if any(type(candle) is not HistoricalCandle for candle in observations):
        raise SwingAnalysisError(SwingAnalysisFailure.MALFORMED_OBSERVATION)

    timestamps = tuple(candle.timestamp for candle in observations)
    if len(set(timestamps)) != len(timestamps):
        raise SwingAnalysisError(
            SwingAnalysisFailure.DUPLICATE_OBSERVATION_BOUNDARY
        )
    if any(
        current <= previous
        for previous, current in zip(timestamps, timestamps[1:])
    ):
        raise SwingAnalysisError(SwingAnalysisFailure.NON_MONOTONIC_OBSERVATIONS)
    for candle in observations:
        _validate_represented_state(candle)
        _validate_ohlc(candle)
    return observations


def _validate_represented_state(candle: HistoricalCandle) -> None:
    completed = getattr(candle, "completed", True)
    if type(completed) is not bool or not completed:
        raise SwingAnalysisError(SwingAnalysisFailure.INCOMPLETE_OBSERVATION)
    quality = getattr(candle, "data_quality", "VALID")
    if quality not in {"VALID", "AVAILABLE"}:
        raise SwingAnalysisError(SwingAnalysisFailure.DATA_QUALITY_UNAVAILABLE)


def _validate_ohlc(candle: HistoricalCandle) -> None:
    prices = (candle.open, candle.high, candle.low, candle.close)
    if (
        any(type(value) is not float or not math.isfinite(value) for value in prices)
        or any(value < 0.0 for value in prices)
        or candle.high < max(candle.open, candle.low, candle.close)
        or candle.low > min(candle.open, candle.high, candle.close)
    ):
        raise SwingAnalysisError(SwingAnalysisFailure.MALFORMED_OBSERVATION)


def _shared_facts(candles: tuple[HistoricalCandle, ...]) -> _SharedFacts:
    current_sma20 = _sma(candles, len(candles) - 1, _SMA_PERIOD)
    prior_sma20 = _sma(
        candles,
        len(candles) - 1 - _SMA_SLOPE_BARS,
        _SMA_PERIOD,
    )
    current_close = candles[-1].close
    if current_close > current_sma20 and current_sma20 > prior_sma20:
        trend = SwingTrend.BULLISH
    elif current_close < current_sma20 and current_sma20 < prior_sma20:
        trend = SwingTrend.BEARISH
    else:
        trend = SwingTrend.NEUTRAL
    return _SharedFacts(current_close, current_sma20, prior_sma20, trend)


def _evaluate_pullback(
    instrument: InstrumentRecord,
    candles: tuple[HistoricalCandle, ...],
    shared: _SharedFacts,
) -> SwingAssessment:
    current = candles[-1]
    previous = candles[-2]
    preceding_window = tuple(
        range(len(candles) - _PULLBACK_WINDOW - 1, len(candles) - 1)
    )
    current_window = tuple(
        range(len(candles) - _PULLBACK_WINDOW, len(candles))
    )
    preceding_bullish = _orderly_pullback(candles, preceding_window, bullish=True)
    preceding_bearish = _orderly_pullback(candles, preceding_window, bullish=False)
    current_bullish = _orderly_pullback(candles, current_window, bullish=True)
    current_bearish = _orderly_pullback(candles, current_window, bullish=False)

    common = _common_evidence(shared)
    if (
        shared.trend is SwingTrend.BULLISH
        and preceding_bullish
        and current.close > previous.high
    ):
        return _assessment(
            instrument=instrument,
            boundary=current.timestamp,
            direction=SwingDirection.LONG,
            setup=SwingSetup.PULLBACK_CONTINUATION,
            state=SwingState.QUALIFIED,
            why="Bullish trend continued above the previous-day high after an orderly preceding five-bar pullback.",
            evidence=common
            + (
                "preceding_pullback_bullish=true",
                f"previous_day_high={_number(previous.high)}",
                "continuation=above_previous_day_high",
            ),
            risks=(),
            next_event=None,
        )
    if (
        shared.trend is SwingTrend.BEARISH
        and preceding_bearish
        and current.close < previous.low
    ):
        return _assessment(
            instrument=instrument,
            boundary=current.timestamp,
            direction=SwingDirection.SHORT,
            setup=SwingSetup.PULLBACK_CONTINUATION,
            state=SwingState.QUALIFIED,
            why="Bearish trend continued below the previous-day low after an orderly preceding five-bar pullback.",
            evidence=common
            + (
                "preceding_pullback_bearish=true",
                f"previous_day_low={_number(previous.low)}",
                "continuation=below_previous_day_low",
            ),
            risks=(),
            next_event=None,
        )
    if shared.trend is SwingTrend.BULLISH and current_bullish:
        return _assessment(
            instrument=instrument,
            boundary=current.timestamp,
            direction=SwingDirection.LONG,
            setup=SwingSetup.PULLBACK_CONTINUATION,
            state=SwingState.FORMING,
            why="An orderly bullish pullback is forming without completed continuation confirmation.",
            evidence=common
            + (
                "current_pullback_bullish=true",
                f"previous_day_high={_number(previous.high)}",
            ),
            risks=("continuation_confirmation_absent",),
            next_event="Completed Daily close above previous-day high",
        )
    if shared.trend is SwingTrend.BEARISH and current_bearish:
        return _assessment(
            instrument=instrument,
            boundary=current.timestamp,
            direction=SwingDirection.SHORT,
            setup=SwingSetup.PULLBACK_CONTINUATION,
            state=SwingState.FORMING,
            why="An orderly bearish pullback is forming without completed continuation confirmation.",
            evidence=common
            + (
                "current_pullback_bearish=true",
                f"previous_day_low={_number(previous.low)}",
            ),
            risks=("continuation_confirmation_absent",),
            next_event="Completed Daily close below previous-day low",
        )
    return _assessment(
        instrument=instrument,
        boundary=current.timestamp,
        direction=SwingDirection.NONE,
        setup=SwingSetup.PULLBACK_CONTINUATION,
        state=SwingState.NO_SETUP,
        why="The frozen trend-and-orderly-pullback conditions are not currently satisfied.",
        evidence=common
        + (
            f"preceding_pullback_bullish={_boolean(preceding_bullish)}",
            f"preceding_pullback_bearish={_boolean(preceding_bearish)}",
            f"current_pullback_bullish={_boolean(current_bullish)}",
            f"current_pullback_bearish={_boolean(current_bearish)}",
        ),
        risks=("setup_conditions_absent",),
        next_event=None,
    )


def _evaluate_breakout(
    instrument: InstrumentRecord,
    candles: tuple[HistoricalCandle, ...],
    shared: _SharedFacts,
) -> SwingAssessment:
    current = candles[-1]
    preceding = candles[-(_CONSOLIDATION_WINDOW + 1) : -1]
    range_high = max(candle.high for candle in preceding)
    range_low = min(candle.low for candle in preceding)
    range_width = range_high - range_low
    preceding_atr14 = _atr(candles, len(candles) - 2, _ATR_PERIOD)
    consolidated = range_width <= _CONSOLIDATION_ATR_MULTIPLE * preceding_atr14
    evidence = _common_evidence(shared) + (
        f"range_high={_number(range_high)}",
        f"range_low={_number(range_low)}",
        f"range_width={_number(range_width)}",
        f"preceding_atr14={_number(preceding_atr14)}",
        f"consolidation={_boolean(consolidated)}",
    )
    if consolidated and current.close > range_high:
        return _assessment(
            instrument=instrument,
            boundary=current.timestamp,
            direction=SwingDirection.LONG,
            setup=SwingSetup.CONSOLIDATION_BREAKOUT,
            state=SwingState.QUALIFIED,
            why="The completed close broke above the preceding ten-bar consolidation range.",
            evidence=evidence + ("breakout=above_range",),
            risks=(),
            next_event=None,
        )
    if consolidated and current.close < range_low:
        return _assessment(
            instrument=instrument,
            boundary=current.timestamp,
            direction=SwingDirection.SHORT,
            setup=SwingSetup.CONSOLIDATION_BREAKOUT,
            state=SwingState.QUALIFIED,
            why="The completed close broke below the preceding ten-bar consolidation range.",
            evidence=evidence + ("breakout=below_range",),
            risks=(),
            next_event=None,
        )
    if consolidated and range_low <= current.close <= range_high:
        return _assessment(
            instrument=instrument,
            boundary=current.timestamp,
            direction=SwingDirection.NONE,
            setup=SwingSetup.CONSOLIDATION_BREAKOUT,
            state=SwingState.FORMING,
            why="The completed close remains inside the preceding ten-bar consolidation range.",
            evidence=evidence + ("breakout=inside_range",),
            risks=("completed_breakout_absent",),
            next_event="Completed Daily close outside prior ten-bar range",
        )
    return _assessment(
        instrument=instrument,
        boundary=current.timestamp,
        direction=SwingDirection.NONE,
        setup=SwingSetup.CONSOLIDATION_BREAKOUT,
        state=SwingState.NO_SETUP,
        why="The preceding ten-bar range is not a frozen-policy consolidation.",
        evidence=evidence + ("breakout=not_applicable",),
        risks=("consolidation_condition_absent",),
        next_event=None,
    )


def _orderly_pullback(
    candles: tuple[HistoricalCandle, ...],
    indexes: tuple[int, ...],
    *,
    bullish: bool,
) -> bool:
    closes = tuple(candles[index].close for index in indexes)
    preceding_closes = tuple(candles[index - 1].close for index in indexes)
    averages = tuple(_sma(candles, index, _SMA_PERIOD) for index in indexes)
    if bullish:
        return any(
            close < prior for close, prior in zip(closes, preceding_closes)
        ) and all(close >= average for close, average in zip(closes, averages))
    return any(
        close > prior for close, prior in zip(closes, preceding_closes)
    ) and all(close <= average for close, average in zip(closes, averages))


def _sma(
    candles: tuple[HistoricalCandle, ...],
    end_index: int,
    period: int,
) -> float:
    start = end_index - period + 1
    return sum(candle.close for candle in candles[start : end_index + 1]) / period


def _atr(
    candles: tuple[HistoricalCandle, ...],
    end_index: int,
    period: int,
) -> float:
    true_ranges = []
    for index in range(end_index - period + 1, end_index + 1):
        candle = candles[index]
        previous_close = candles[index - 1].close
        true_ranges.append(
            max(
                candle.high - candle.low,
                abs(candle.high - previous_close),
                abs(candle.low - previous_close),
            )
        )
    return sum(true_ranges) / period


def _common_evidence(shared: _SharedFacts) -> tuple[str, ...]:
    return (
        f"current_close={_number(shared.current_close)}",
        f"current_sma20={_number(shared.current_sma20)}",
        f"sma20_five_bars_earlier={_number(shared.prior_sma20)}",
        f"trend={shared.trend.value}",
    )


def _assessment(
    *,
    instrument: InstrumentRecord,
    boundary: datetime,
    direction: SwingDirection,
    setup: SwingSetup,
    state: SwingState,
    why: str,
    evidence: tuple[str, ...],
    risks: tuple[str, ...],
    next_event: str | None,
) -> SwingAssessment:
    return SwingAssessment(
        instrument=instrument,
        observation_boundary=boundary,
        rule_set_version=SWING_ZERO_POLICY_ID,
        direction=direction,
        setup=setup,
        state=state,
        why=why,
        evidence_for=evidence,
        evidence_against_or_risks=risks,
        next_required_event=next_event,
    )


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _number(value: float) -> str:
    return format(value, ".10g")


def _boolean(value: bool) -> str:
    return "true" if value else "false"


__all__ = [
    "MINIMUM_LOOKBACK",
    "SWING_ZERO_POLICY_ID",
    "SwingAnalysisError",
    "SwingAnalysisFailure",
    "SwingAssessment",
    "SwingDirection",
    "SwingSetup",
    "SwingState",
    "SwingTrend",
    "analyze_swing_zero",
]
