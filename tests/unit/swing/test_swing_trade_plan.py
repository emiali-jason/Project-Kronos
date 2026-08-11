from dataclasses import FrozenInstanceError, fields, replace
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.market_data import HistoricalCandle
from kronos.swing.candidate_validation import SwingCandidate
from kronos.swing.trade_plan import (
    SWING_PHASE1_TRADE_PLAN_POLICY_ID,
    TradePlan,
    TradePlanConstructionError,
    TradePlanFailure,
    TradePlanStatus,
    build_trade_plan,
)
from kronos.swing.zero import (
    SWING_ZERO_POLICY_ID,
    SwingAssessment,
    SwingDirection,
    SwingSetup,
    SwingState,
)


_KOLKATA = ZoneInfo("Asia/Kolkata")
_BOUNDARY = datetime(2026, 8, 7, tzinfo=_KOLKATA)


def _instrument(identity: str = "TEST", *, asset: str = "equity") -> InstrumentRecord:
    if asset == "commodity":
        return InstrumentRecord(
            "KITE", "MCX", "MCX-FUT", f"{identity}26AUGFUT", identity, "FUT", date(2026, 8, 28)
        )
    if asset == "index":
        return InstrumentRecord("KITE", "NSE", "INDICES", identity, identity, "INDEX", None)
    return InstrumentRecord("KITE", "NSE", "NSE", identity, identity, "EQ", None)


def _candidate(
    setup: SwingSetup,
    direction: SwingDirection,
    *,
    identity: str = "TEST",
    asset: str = "equity",
) -> SwingCandidate:
    instrument = _instrument(identity, asset=asset)
    assessment = SwingAssessment(
        instrument=instrument,
        observation_boundary=_BOUNDARY,
        rule_set_version=SWING_ZERO_POLICY_ID,
        direction=direction,
        setup=setup,
        state=SwingState.QUALIFIED,
        why="Frozen qualified setup evidence.",
        evidence_for=("qualification=true",),
        evidence_against_or_risks=(),
    )
    return SwingCandidate(
        canonical_identity=identity,
        setup=setup,
        direction=direction,
        observation_boundary=_BOUNDARY,
        rule_set_version=SWING_ZERO_POLICY_ID,
        assessment=assessment,
    )


def _candle(index: int, *, open_: float, high: float, low: float, close: float) -> HistoricalCandle:
    return HistoricalCandle(
        timestamp=_BOUNDARY - timedelta(days=29 - index),
        open=float(open_),
        high=float(high),
        low=float(low),
        close=float(close),
        volume=1_000 + index,
    )


def _base() -> list[HistoricalCandle]:
    return [
        _candle(index, open_=100.0, high=101.0, low=99.0, close=100.0)
        for index in range(30)
    ]


def _pullback_long(*, invalid_stop: bool = False, bad_target: bool = False) -> tuple[HistoricalCandle, ...]:
    candles = _base()
    target_high = 110.0 if bad_target else 150.0
    candles[10] = _candle(10, open_=100.0, high=target_high, low=99.0, close=100.0)
    pullback_low = 121.0 if invalid_stop else 95.0
    for index in range(24, 29):
        candles[index] = _candle(index, open_=122.0, high=123.0, low=pullback_low, close=122.0)
    candles[29] = _candle(29, open_=110.0, high=120.0, low=109.0, close=115.0)
    return tuple(candles)


def _pullback_short(*, invalid_stop: bool = False, bad_target: bool = False) -> tuple[HistoricalCandle, ...]:
    candles = _base()
    target_low = 90.0 if bad_target else 50.0
    candles[10] = _candle(10, open_=100.0, high=101.0, low=target_low, close=100.0)
    pullback_high = 79.0 if invalid_stop else 105.0
    for index in range(24, 29):
        candles[index] = _candle(index, open_=78.0, high=pullback_high, low=77.0, close=78.0)
    candles[29] = _candle(29, open_=90.0, high=91.0, low=80.0, close=85.0)
    return tuple(candles)


def _breakout_long(*, invalid_stop: bool = False, zero_reward: bool = False) -> tuple[HistoricalCandle, ...]:
    candles = _base()
    for index in range(19, 29):
        candles[index] = _candle(index, open_=105.0, high=110.0, low=100.0, close=105.0)
    if invalid_stop:
        candles[29] = _candle(29, open_=120.0, high=120.0, low=120.0, close=120.0)
    elif zero_reward:
        candles[29] = _candle(29, open_=111.0, high=120.0, low=110.0, close=111.0)
    else:
        candles[29] = _candle(29, open_=112.0, high=115.0, low=100.0, close=112.0)
    return tuple(candles)


def _breakout_short(*, invalid_stop: bool = False) -> tuple[HistoricalCandle, ...]:
    candles = _base()
    for index in range(19, 29):
        candles[index] = _candle(index, open_=95.0, high=100.0, low=90.0, close=95.0)
    if invalid_stop:
        candles[29] = _candle(29, open_=80.0, high=80.0, low=80.0, close=80.0)
    else:
        candles[29] = _candle(29, open_=88.0, high=100.0, low=85.0, close=88.0)
    return tuple(candles)


@pytest.mark.parametrize(
    ("direction", "candles", "entry", "stop", "target", "risk", "reward"),
    [
        (SwingDirection.LONG, _pullback_long(), 120.0, 95.0, 150.0, 25.0, 30.0),
        (SwingDirection.SHORT, _pullback_short(), 80.0, 105.0, 50.0, 25.0, 30.0),
    ],
)
def test_pullback_actionable_is_exact(
    direction: SwingDirection,
    candles: tuple[HistoricalCandle, ...],
    entry: float,
    stop: float,
    target: float,
    risk: float,
    reward: float,
) -> None:
    plan = build_trade_plan(_candidate(SwingSetup.PULLBACK_CONTINUATION, direction), candles)

    assert plan.status is TradePlanStatus.ACTIONABLE
    assert plan.canonical_identity == "TEST"
    assert (plan.entry, plan.stop, plan.target_1) == (entry, stop, target)
    assert (plan.risk_per_unit, plan.reward_per_unit, plan.risk_reward) == (risk, reward, reward / risk)


@pytest.mark.parametrize(
    ("direction", "candles", "entry", "stop", "target"),
    [
        (SwingDirection.LONG, _breakout_long(), 115.0, 100.0, 120.0),
        (SwingDirection.SHORT, _breakout_short(), 85.0, 100.0, 80.0),
    ],
)
def test_breakout_actionable_is_exact(
    direction: SwingDirection,
    candles: tuple[HistoricalCandle, ...],
    entry: float,
    stop: float,
    target: float,
) -> None:
    plan = build_trade_plan(_candidate(SwingSetup.CONSOLIDATION_BREAKOUT, direction), candles)

    assert plan.status is TradePlanStatus.ACTIONABLE
    assert (plan.entry, plan.stop, plan.target_1) == (entry, stop, target)


@pytest.mark.parametrize(
    ("setup", "direction", "candles"),
    [
        (SwingSetup.PULLBACK_CONTINUATION, SwingDirection.LONG, _pullback_long(invalid_stop=True)),
        (SwingSetup.PULLBACK_CONTINUATION, SwingDirection.SHORT, _pullback_short(invalid_stop=True)),
        (SwingSetup.CONSOLIDATION_BREAKOUT, SwingDirection.LONG, _breakout_long(invalid_stop=True)),
        (SwingSetup.CONSOLIDATION_BREAKOUT, SwingDirection.SHORT, _breakout_short(invalid_stop=True)),
    ],
)
def test_invalid_stop_geometry_is_typed_and_never_replaced(
    setup: SwingSetup,
    direction: SwingDirection,
    candles: tuple[HistoricalCandle, ...],
) -> None:
    plan = build_trade_plan(_candidate(setup, direction), candles)

    assert plan.status is TradePlanStatus.INVALID
    assert plan.failure is TradePlanFailure.INVALID_STOP_GEOMETRY
    assert plan.risk_per_unit <= 0.0
    assert plan.risk_reward is None


@pytest.mark.parametrize(
    ("direction", "candles"),
    [
        (SwingDirection.LONG, _pullback_long(bad_target=True)),
        (SwingDirection.SHORT, _pullback_short(bad_target=True)),
    ],
)
def test_pullback_structural_target_wrong_side_is_not_actionable(
    direction: SwingDirection,
    candles: tuple[HistoricalCandle, ...],
) -> None:
    plan = build_trade_plan(_candidate(SwingSetup.PULLBACK_CONTINUATION, direction), candles)

    assert plan.status is TradePlanStatus.NOT_ACTIONABLE
    assert plan.failure is TradePlanFailure.NO_VALID_STRUCTURAL_TARGET
    assert plan.reward_per_unit <= 0.0
    assert plan.risk_reward is None


def test_breakout_non_positive_reward_is_not_actionable() -> None:
    plan = build_trade_plan(
        _candidate(SwingSetup.CONSOLIDATION_BREAKOUT, SwingDirection.LONG),
        _breakout_long(zero_reward=True),
    )

    assert plan.status is TradePlanStatus.NOT_ACTIONABLE
    assert plan.failure is TradePlanFailure.NO_VALID_STRUCTURAL_TARGET
    assert plan.reward_per_unit == 0.0


def test_no_minimum_rr_gate_applies() -> None:
    candles = list(_pullback_long())
    candles[10] = _candle(10, open_=100.0, high=120.1, low=99.0, close=100.0)
    plan = build_trade_plan(
        _candidate(SwingSetup.PULLBACK_CONTINUATION, SwingDirection.LONG),
        tuple(candles),
    )

    assert plan.status is TradePlanStatus.ACTIONABLE
    assert 0.0 < plan.risk_reward < 0.01  # type: ignore[operator]


def test_entry_zone_target_two_position_sizing_and_ranking_are_absent() -> None:
    plan = build_trade_plan(
        _candidate(SwingSetup.PULLBACK_CONTINUATION, SwingDirection.LONG),
        _pullback_long(),
    )

    assert plan.entry_zone is None
    assert plan.target_2 is None
    assert not hasattr(plan, "position_size")
    assert not hasattr(plan, "rank")
    assert not hasattr(plan, "score")


def test_trade_plan_is_immutable_and_preserves_original_assessment_identity() -> None:
    candidate = _candidate(SwingSetup.PULLBACK_CONTINUATION, SwingDirection.LONG)
    plan = build_trade_plan(candidate, _pullback_long())

    assert plan.original_assessment is candidate.assessment
    with pytest.raises((FrozenInstanceError, AttributeError)):
        plan.entry = 1.0  # type: ignore[misc]
    assert candidate.assessment.entry_zone is None
    assert candidate.assessment.stop is None
    assert candidate.assessment.targets is None


def test_repeated_construction_is_deterministic() -> None:
    candidate = _candidate(SwingSetup.PULLBACK_CONTINUATION, SwingDirection.LONG)
    candles = _pullback_long()

    assert build_trade_plan(candidate, candles) == build_trade_plan(candidate, candles)
    assert hash(build_trade_plan(candidate, candles)) == hash(build_trade_plan(candidate, candles))


def test_setup_native_calculation_inputs_remain_distinct() -> None:
    pullback = build_trade_plan(
        _candidate(SwingSetup.PULLBACK_CONTINUATION, SwingDirection.LONG),
        _pullback_long(),
    )
    breakout = build_trade_plan(
        _candidate(SwingSetup.CONSOLIDATION_BREAKOUT, SwingDirection.LONG),
        _breakout_long(),
    )

    assert any(item.startswith("pullback_structural_low=") for item in pullback.calculation_inputs)
    assert any(item.startswith("range_width=") for item in breakout.calculation_inputs)
    assert pullback.thesis_invalidation != breakout.thesis_invalidation


@pytest.mark.parametrize("asset", ["equity", "index", "commodity"])
def test_same_policy_applies_across_asset_classes(asset: str) -> None:
    plan = build_trade_plan(
        _candidate(SwingSetup.PULLBACK_CONTINUATION, SwingDirection.LONG, asset=asset),
        _pullback_long(),
    )

    assert plan.status is TradePlanStatus.ACTIONABLE
    assert plan.trade_plan_policy_version == SWING_PHASE1_TRADE_PLAN_POLICY_ID


def test_missing_or_wrong_boundary_evidence_fails_closed() -> None:
    candidate = _candidate(SwingSetup.PULLBACK_CONTINUATION, SwingDirection.LONG)
    with pytest.raises(TradePlanConstructionError) as short:
        build_trade_plan(candidate, _pullback_long()[-25:])
    assert short.value.failure is TradePlanFailure.EVIDENCE_UNAVAILABLE

    wrong = list(_pullback_long())
    wrong[-1] = replace(wrong[-1], timestamp=_BOUNDARY - timedelta(days=1))
    with pytest.raises(TradePlanConstructionError) as boundary:
        build_trade_plan(candidate, wrong)
    assert boundary.value.failure is TradePlanFailure.EVIDENCE_UNAVAILABLE


def test_contract_has_only_policy_fields_and_no_second_target_model() -> None:
    names = {field.name for field in fields(TradePlan)}

    assert "target_1" in names
    assert "target_2" in names
    assert "position_size" not in names
    assert "ranking" not in names
    assert "minimum_risk_reward" not in names
