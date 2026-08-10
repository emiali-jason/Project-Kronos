from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, timedelta

import pytest

from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.market_data import (
    HistoricalCandle,
    HistoricalCandleRequest,
    HistoricalInterval,
)
from kronos.swing.zero import (
    SWING_ZERO_POLICY_ID,
    SwingAnalysisError,
    SwingAnalysisFailure,
    SwingDirection,
    SwingSetup,
    SwingState,
    analyze_swing_zero,
)


_START = datetime(2026, 7, 1, tzinfo=UTC)
_INSTRUMENT = InstrumentRecord(
    provider="ZERODHA_KITE",
    exchange="MCX",
    segment="MCX-FUT",
    trading_symbol="GOLDM26AUGFUT",
    name="GOLDM",
    instrument_type="FUT",
    expiry=date(2026, 8, 28),
)


def _request(
    interval: HistoricalInterval = HistoricalInterval.DAY,
) -> HistoricalCandleRequest:
    return HistoricalCandleRequest(
        instrument=_INSTRUMENT,
        start=_START,
        end=_START + timedelta(days=40),
        interval=interval,
    )


def _candles(
    closes: list[float],
    *,
    spreads: list[tuple[float, float]] | None = None,
) -> tuple[HistoricalCandle, ...]:
    if spreads is None:
        spreads = [(1.0, 1.0)] * len(closes)
    return tuple(
        HistoricalCandle(
            timestamp=_START + timedelta(days=index),
            open=float(close),
            high=float(close + upper),
            low=float(close - lower),
            close=float(close),
            volume=1_000 + index,
        )
        for index, (close, (upper, lower)) in enumerate(zip(closes, spreads))
    )


def _evidence(assessment: object) -> dict[str, str]:
    return {
        key: value
        for item in assessment.evidence_for  # type: ignore[attr-defined]
        for key, value in (item.split("=", 1),)
    }


def _bullish_pullback_closes(state: SwingState) -> list[float]:
    if state is SwingState.NO_SETUP:
        return [100.0 + index for index in range(25)]
    if state is SwingState.FORMING:
        return [100.0 + index for index in range(20)] + [
            120.0,
            121.0,
            120.0,
            121.0,
            121.5,
        ]
    return [100.0 + index for index in range(19)] + [
        117.0,
        119.0,
        120.0,
        121.0,
        122.0,
        124.0,
    ]


def _bearish_pullback_closes(state: SwingState) -> list[float]:
    if state is SwingState.NO_SETUP:
        return [200.0 - index for index in range(25)]
    if state is SwingState.FORMING:
        return [200.0 - index for index in range(20)] + [
            180.0,
            179.0,
            180.0,
            179.0,
            178.5,
        ]
    return [200.0 - index for index in range(19)] + [
        183.0,
        181.0,
        180.0,
        179.0,
        178.0,
        176.0,
    ]


def _assert_trade_plan_absent(assessments: tuple[object, ...]) -> None:
    for assessment in assessments:
        assert assessment.entry_zone is None  # type: ignore[attr-defined]
        assert assessment.invalidation is None  # type: ignore[attr-defined]
        assert assessment.stop is None  # type: ignore[attr-defined]
        assert assessment.targets is None  # type: ignore[attr-defined]
        assert assessment.risk_reward is None  # type: ignore[attr-defined]


def test_shared_sma20_slope_and_bullish_trend_are_exact() -> None:
    results = analyze_swing_zero(_request(), _candles([100.0 + i for i in range(25)]))

    facts = _evidence(results[0])
    assert facts["current_sma20"] == "114.5"
    assert facts["sma20_five_bars_earlier"] == "109.5"
    assert facts["trend"] == "BULLISH"


@pytest.mark.parametrize(
    ("closes", "expected"),
    [
        ([200.0 - i for i in range(25)], "BEARISH"),
        ([100.0] * 25, "NEUTRAL"),
    ],
)
def test_bearish_and_neutral_trend_are_symmetric(
    closes: list[float],
    expected: str,
) -> None:
    results = analyze_swing_zero(_request(), _candles(closes))

    assert _evidence(results[0])["trend"] == expected


def test_simple_atr14_uses_true_range() -> None:
    results = analyze_swing_zero(_request(), _candles([100.0] * 25))

    assert _evidence(results[1])["preceding_atr14"] == "2"


def test_pullback_qualification_uses_preceding_five_bar_window() -> None:
    closes = [100.0 + i for i in range(19)] + [117.0, 119.0, 120.0, 121.0, 122.0, 124.0]
    pullback, _ = analyze_swing_zero(_request(), _candles(closes))

    assert pullback.setup is SwingSetup.PULLBACK_CONTINUATION
    assert pullback.state is SwingState.QUALIFIED
    assert pullback.direction is SwingDirection.LONG
    assert "preceding_pullback_bullish=true" in pullback.evidence_for
    assert "continuation=above_previous_day_high" in pullback.evidence_for


def test_bearish_pullback_qualification_is_symmetric() -> None:
    closes = [200.0 - i for i in range(19)] + [183.0, 181.0, 180.0, 179.0, 178.0, 176.0]
    pullback, _ = analyze_swing_zero(_request(), _candles(closes))

    assert pullback.state is SwingState.QUALIFIED
    assert pullback.direction is SwingDirection.SHORT
    assert "preceding_pullback_bearish=true" in pullback.evidence_for
    assert "continuation=below_previous_day_low" in pullback.evidence_for


def test_breakout_range_excludes_current_candle() -> None:
    closes = [100.0] * 24 + [102.0]
    spreads = [(1.0, 1.0)] * 24 + [(98.0, 52.0)]
    _, breakout = analyze_swing_zero(_request(), _candles(closes, spreads=spreads))

    assert breakout.state is SwingState.QUALIFIED
    assert breakout.direction is SwingDirection.LONG
    facts = _evidence(breakout)
    assert facts["range_high"] == "101"
    assert facts["range_low"] == "99"


def test_consolidation_atr_reference_excludes_current_candle() -> None:
    closes = [100.0] * 25
    spreads = [(1.0, 1.0)] * 25
    spreads[14] = (10.0, 10.0)
    spreads[-1] = (100.0, 50.0)
    _, breakout = analyze_swing_zero(_request(), _candles(closes, spreads=spreads))

    assert breakout.state is SwingState.NO_SETUP
    assert _evidence(breakout)["preceding_atr14"] == "3.285714286"


def test_setup_families_are_evaluated_independently() -> None:
    closes = [100.0 + i for i in range(14)] + [
        119.0,
        119.5,
        120.0,
        120.5,
        121.0,
        121.5,
        121.0,
        121.5,
        122.0,
        122.5,
        124.0,
    ]
    pullback, breakout = analyze_swing_zero(_request(), _candles(closes))

    assert pullback.state is SwingState.QUALIFIED
    assert breakout.state is SwingState.QUALIFIED
    assert pullback.setup is SwingSetup.PULLBACK_CONTINUATION
    assert breakout.setup is SwingSetup.CONSOLIDATION_BREAKOUT


def test_assessments_are_deterministic_and_trade_plan_remains_absent() -> None:
    candles = _candles([100.0] * 25)

    first = analyze_swing_zero(_request(), candles)
    second = analyze_swing_zero(_request(), candles)

    assert first == second
    for assessment in first:
        assert assessment.rule_set_version == SWING_ZERO_POLICY_ID
        assert assessment.entry_zone is None
        assert assessment.invalidation is None
        assert assessment.stop is None
        assert assessment.targets is None
        assert assessment.risk_reward is None


def test_swing_assessment_is_immutable() -> None:
    assessment = analyze_swing_zero(_request(), _candles([100.0] * 25))[0]

    with pytest.raises(FrozenInstanceError):
        assessment.state = SwingState.QUALIFIED  # type: ignore[misc]


def test_insufficient_lookback_is_typed_failure_not_no_setup() -> None:
    with pytest.raises(SwingAnalysisError) as captured:
        analyze_swing_zero(_request(), _candles([100.0] * 24))

    assert captured.value.failure is SwingAnalysisFailure.INSUFFICIENT_LOOKBACK


def test_non_daily_interval_fails_closed() -> None:
    with pytest.raises(SwingAnalysisError) as captured:
        analyze_swing_zero(
            _request(HistoricalInterval.SIXTY_MINUTE),
            _candles([100.0] * 25),
        )

    assert captured.value.failure is SwingAnalysisFailure.INTERVAL_NOT_DAILY


def test_duplicate_and_non_monotonic_boundaries_fail_closed() -> None:
    candles = list(_candles([100.0] * 25))
    candles[12] = HistoricalCandle(
        timestamp=candles[11].timestamp,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        volume=1_012,
    )
    with pytest.raises(SwingAnalysisError) as duplicate:
        analyze_swing_zero(_request(), candles)
    assert (
        duplicate.value.failure
        is SwingAnalysisFailure.DUPLICATE_OBSERVATION_BOUNDARY
    )

    candles = list(_candles([100.0] * 25))
    candles[11], candles[12] = candles[12], candles[11]
    with pytest.raises(SwingAnalysisError) as non_monotonic:
        analyze_swing_zero(_request(), candles)
    assert non_monotonic.value.failure is SwingAnalysisFailure.NON_MONOTONIC_OBSERVATIONS


def test_malformed_observation_fails_closed() -> None:
    candles: list[object] = list(_candles([100.0] * 25))
    candles[4] = {"close": 100.0}

    with pytest.raises(SwingAnalysisError) as captured:
        analyze_swing_zero(_request(), candles)  # type: ignore[arg-type]

    assert captured.value.failure is SwingAnalysisFailure.MALFORMED_OBSERVATION


def test_invalid_numeric_observation_fails_closed() -> None:
    candles = list(_candles([100.0] * 25))
    malformed = object.__new__(HistoricalCandle)
    object.__setattr__(malformed, "timestamp", candles[4].timestamp)
    object.__setattr__(malformed, "open", 100.0)
    object.__setattr__(malformed, "high", 101.0)
    object.__setattr__(malformed, "low", 99.0)
    object.__setattr__(malformed, "close", float("nan"))
    object.__setattr__(malformed, "volume", 1_004)
    candles[4] = malformed

    with pytest.raises(SwingAnalysisError) as captured:
        analyze_swing_zero(_request(), candles)

    assert captured.value.failure is SwingAnalysisFailure.MALFORMED_OBSERVATION


@pytest.mark.parametrize(
    ("direction", "state"),
    [
        (SwingDirection.LONG, SwingState.NO_SETUP),
        (SwingDirection.LONG, SwingState.FORMING),
        (SwingDirection.LONG, SwingState.QUALIFIED),
        (SwingDirection.SHORT, SwingState.NO_SETUP),
        (SwingDirection.SHORT, SwingState.FORMING),
        (SwingDirection.SHORT, SwingState.QUALIFIED),
    ],
)
def test_step10_pullback_classification_matrix(
    direction: SwingDirection,
    state: SwingState,
) -> None:
    closes = (
        _bullish_pullback_closes(state)
        if direction is SwingDirection.LONG
        else _bearish_pullback_closes(state)
    )

    pullback, _ = analyze_swing_zero(_request(), _candles(closes))

    assert pullback.state is state
    expected_direction = direction if state is not SwingState.NO_SETUP else SwingDirection.NONE
    assert pullback.direction is expected_direction
    if state is SwingState.FORMING:
        assert pullback.next_required_event is not None
        assert "continuation_confirmation_absent" in pullback.evidence_against_or_risks
    if state is SwingState.QUALIFIED:
        boundary_fact = (
            "continuation=above_previous_day_high"
            if direction is SwingDirection.LONG
            else "continuation=below_previous_day_low"
        )
        assert boundary_fact in pullback.evidence_for


@pytest.mark.parametrize(
    ("current_close", "expected_state", "expected_direction"),
    [
        (100.0, SwingState.FORMING, SwingDirection.NONE),
        (102.0, SwingState.QUALIFIED, SwingDirection.LONG),
        (98.0, SwingState.QUALIFIED, SwingDirection.SHORT),
    ],
)
def test_step10_consolidation_classification_matrix(
    current_close: float,
    expected_state: SwingState,
    expected_direction: SwingDirection,
) -> None:
    _, breakout = analyze_swing_zero(
        _request(),
        _candles([100.0] * 24 + [current_close]),
    )

    assert breakout.state is expected_state
    assert breakout.direction is expected_direction
    facts = _evidence(breakout)
    assert facts["range_high"] == "101"
    assert facts["range_low"] == "99"
    assert facts["range_width"] == "2"
    assert facts["preceding_atr14"] == "2"


def test_step10_no_consolidation_is_no_setup() -> None:
    spreads = [(1.0, 1.0)] * 25
    spreads[14] = (10.0, 10.0)

    _, breakout = analyze_swing_zero(
        _request(),
        _candles([100.0] * 25, spreads=spreads),
    )

    assert breakout.state is SwingState.NO_SETUP
    assert _evidence(breakout)["consolidation"] == "false"


def test_intraday_range_penetration_without_close_outside_remains_forming() -> None:
    spreads = [(1.0, 1.0)] * 24 + [(5.0, 5.0)]

    _, breakout = analyze_swing_zero(
        _request(),
        _candles([100.0] * 25, spreads=spreads),
    )

    assert breakout.state is SwingState.FORMING
    assert _evidence(breakout)["breakout"] == "inside_range"


def test_one_setup_may_form_while_the_other_is_no_setup() -> None:
    closes = _bullish_pullback_closes(SwingState.FORMING)

    pullback, breakout = analyze_swing_zero(_request(), _candles(closes))

    assert pullback.state is SwingState.FORMING
    assert breakout.state is SwingState.NO_SETUP


def test_malformed_ohlc_relation_fails_closed() -> None:
    candles = list(_candles([100.0] * 25))
    malformed = object.__new__(HistoricalCandle)
    object.__setattr__(malformed, "timestamp", candles[4].timestamp)
    object.__setattr__(malformed, "open", 100.0)
    object.__setattr__(malformed, "high", 99.0)
    object.__setattr__(malformed, "low", 98.0)
    object.__setattr__(malformed, "close", 100.0)
    object.__setattr__(malformed, "volume", 1_004)
    candles[4] = malformed

    with pytest.raises(SwingAnalysisError) as captured:
        analyze_swing_zero(_request(), candles)

    assert captured.value.failure is SwingAnalysisFailure.MALFORMED_OBSERVATION


class _ExtendedObservation(HistoricalCandle):
    """Foreign represented state must not bypass the Provider V2 contract."""


@pytest.mark.parametrize(
    ("attribute", "value"),
    [
        ("completed", False),
        ("data_quality", "UNAVAILABLE"),
        ("instrument", "DIFFERENT-INSTRUMENT"),
    ],
)
def test_extended_quality_or_identity_representation_fails_closed(
    attribute: str,
    value: object,
) -> None:
    candles: list[HistoricalCandle] = list(_candles([100.0] * 25))
    extended = object.__new__(_ExtendedObservation)
    for field in ("timestamp", "open", "high", "low", "close", "volume"):
        object.__setattr__(extended, field, getattr(candles[4], field))
    object.__setattr__(extended, attribute, value)
    candles[4] = extended

    with pytest.raises(SwingAnalysisError) as captured:
        analyze_swing_zero(_request(), candles)

    assert captured.value.failure is SwingAnalysisFailure.MALFORMED_OBSERVATION


def test_repeated_evaluation_preserves_equal_bytes_and_evidence() -> None:
    candles = _candles(_bullish_pullback_closes(SwingState.QUALIFIED))

    first = analyze_swing_zero(_request(), candles)
    second = analyze_swing_zero(_request(), candles)

    assert first == second
    assert repr(first).encode() == repr(second).encode()
    assert tuple(item.evidence_for for item in first) == tuple(
        item.evidence_for for item in second
    )


def test_representative_explanations_publish_rule_facts() -> None:
    forming, _ = analyze_swing_zero(
        _request(),
        _candles(_bullish_pullback_closes(SwingState.FORMING)),
    )
    _, qualified = analyze_swing_zero(
        _request(),
        _candles([100.0] * 24 + [102.0]),
    )

    forming_facts = _evidence(forming)
    assert {
        "current_close",
        "current_sma20",
        "sma20_five_bars_earlier",
        "trend",
        "current_pullback_bullish",
        "previous_day_high",
    } <= forming_facts.keys()
    qualified_facts = _evidence(qualified)
    assert {
        "range_high",
        "range_low",
        "range_width",
        "preceding_atr14",
        "breakout",
    } <= qualified_facts.keys()
    assert forming.why
    assert qualified.why


def test_trade_plan_is_absent_across_step10_classification_paths() -> None:
    scenarios = [
        _candles(_bullish_pullback_closes(state))
        for state in SwingState
    ] + [
        _candles(_bearish_pullback_closes(state))
        for state in SwingState
    ] + [
        _candles([100.0] * 24 + [close])
        for close in (98.0, 100.0, 102.0)
    ]

    for candles in scenarios:
        _assert_trade_plan_absent(analyze_swing_zero(_request(), candles))
