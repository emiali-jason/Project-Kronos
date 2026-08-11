from dataclasses import FrozenInstanceError, fields, replace
from datetime import date

import pytest

from kronos.swing.candidate_ranking import (
    SWING_PHASE1_CANDIDATE_RANKING_POLICY_ID,
    CandidateRanking,
    rank_trade_plans,
)
from kronos.swing.trade_plan import (
    TradePlan,
    TradePlanFailure,
    TradePlanStatus,
    build_trade_plan,
)
from kronos.swing.zero import SwingDirection, SwingSetup
from tests.unit.swing.test_swing_trade_plan import (
    _breakout_long,
    _candidate,
    _pullback_long,
)


def _plan(
    identity: str,
    ratio: float,
    *,
    setup: SwingSetup = SwingSetup.PULLBACK_CONTINUATION,
    direction: SwingDirection = SwingDirection.LONG,
    candidate_suffix: str = "",
    asset: str = "equity",
) -> TradePlan:
    candles = (
        _pullback_long()
        if setup is SwingSetup.PULLBACK_CONTINUATION
        else _breakout_long()
    )
    plan = build_trade_plan(
        _candidate(setup, direction, identity=identity, asset=asset),
        candles,
    )
    return replace(
        plan,
        candidate_identity=plan.candidate_identity + candidate_suffix,
        reward_per_unit=plan.risk_per_unit * ratio,
        risk_reward=ratio,
    )


def _not_actionable(identity: str, *, setup: SwingSetup = SwingSetup.PULLBACK_CONTINUATION) -> TradePlan:
    plan = _plan(identity, 1.0, setup=setup)
    return replace(
        plan,
        status=TradePlanStatus.NOT_ACTIONABLE,
        failure=TradePlanFailure.NO_VALID_STRUCTURAL_TARGET,
        reward_per_unit=0.0,
        risk_reward=None,
    )


def _invalid(identity: str) -> TradePlan:
    plan = _plan(identity, 1.0)
    return replace(
        plan,
        status=TradePlanStatus.INVALID,
        failure=TradePlanFailure.INVALID_STOP_GEOMETRY,
        risk_per_unit=0.0,
        reward_per_unit=0.0,
        risk_reward=None,
    )


def test_policy_identity_is_exact() -> None:
    result = rank_trade_plans(())
    assert result.policy_id == "SWING-PHASE1-V0-CANDIDATE-RANKING-POLICY"
    assert result.policy_id == SWING_PHASE1_CANDIDATE_RANKING_POLICY_ID


def test_actionable_enters_ranking() -> None:
    plan = _plan("A", 1.0)
    assert rank_trade_plans((plan,)).ranked_actionable[0].trade_plan is plan


def test_not_actionable_does_not_enter_ranking() -> None:
    result = rank_trade_plans((_not_actionable("A"),))
    assert result.ranked_actionable == ()


def test_not_actionable_is_preserved_by_identity() -> None:
    plan = _not_actionable("A")
    assert rank_trade_plans((plan,)).preserved_not_actionable == (plan,)


def test_invalid_is_preserved_by_identity() -> None:
    plan = _invalid("A")
    assert rank_trade_plans((plan,)).preserved_invalid == (plan,)


def test_every_input_reconciles_exactly_once() -> None:
    plans = (_plan("A", 2.0), _not_actionable("B"), _invalid("C"))
    result = rank_trade_plans(plans)
    reconciled = (
        tuple(item.trade_plan for item in result.ranked_actionable)
        + result.preserved_not_actionable
        + result.preserved_invalid
    )
    assert result.input_count == len(reconciled) == len(plans)
    assert set(reconciled) == set(plans)


def test_higher_risk_reward_ranks_first() -> None:
    result = rank_trade_plans((_plan("LOW", 0.1), _plan("HIGH", 2.0)))
    assert [item.canonical_identity for item in result.ranked_actionable] == [
        "HIGH",
        "LOW",
    ]


def test_equal_ratio_uses_canonical_identity() -> None:
    result = rank_trade_plans((_plan("B", 1.0), _plan("A", 1.0)))
    assert [item.canonical_identity for item in result.ranked_actionable] == ["A", "B"]


def test_equal_ratio_and_identity_use_setup_identity() -> None:
    pullback = _plan("A", 1.0, setup=SwingSetup.PULLBACK_CONTINUATION)
    breakout = _plan("A", 1.0, setup=SwingSetup.CONSOLIDATION_BREAKOUT)
    result = rank_trade_plans((pullback, breakout))
    assert [item.setup for item in result.ranked_actionable] == [
        SwingSetup.CONSOLIDATION_BREAKOUT,
        SwingSetup.PULLBACK_CONTINUATION,
    ]


def test_equal_ratio_identity_and_setup_use_direction() -> None:
    long = _plan("A", 1.0, direction=SwingDirection.LONG)
    short = _plan("A", 1.0, direction=SwingDirection.SHORT)
    result = rank_trade_plans((short, long))
    assert [item.direction for item in result.ranked_actionable] == [
        SwingDirection.LONG,
        SwingDirection.SHORT,
    ]


def test_final_exact_tie_uses_candidate_identity() -> None:
    z = _plan("A", 1.0, candidate_suffix="|Z")
    a = _plan("A", 1.0, candidate_suffix="|A")
    result = rank_trade_plans((z, a))
    assert [item.candidate_identity for item in result.ranked_actionable] == sorted(
        (z.candidate_identity, a.candidate_identity)
    )


def test_tie_breakers_do_not_create_score() -> None:
    result = rank_trade_plans((_plan("B", 1.0), _plan("A", 1.0)))
    assert all(not hasattr(item, "score") for item in result.ranked_actionable)
    assert "score" not in {field.name for field in fields(CandidateRanking)}


def test_repeated_ranking_is_deterministic() -> None:
    plans = (_plan("B", 1.0), _plan("A", 2.0), _not_actionable("C"))
    assert rank_trade_plans(plans) == rank_trade_plans(plans)
    assert hash(rank_trade_plans(plans)) == hash(rank_trade_plans(plans))


def test_input_collection_and_plans_are_not_mutated() -> None:
    plans = [_plan("B", 1.0), _plan("A", 2.0)]
    before = tuple(plans)
    rank_trade_plans(plans)
    assert tuple(plans) == before


def test_original_immutable_trade_plan_reference_is_preserved() -> None:
    plan = _plan("A", 1.0)
    ranked = rank_trade_plans((plan,)).ranked_actionable[0]
    assert ranked.trade_plan is plan


def test_ranking_result_is_immutable() -> None:
    result = rank_trade_plans((_plan("A", 1.0),))
    with pytest.raises((FrozenInstanceError, AttributeError)):
        result.input_count = 2  # type: ignore[misc]


def test_no_minimum_ratio_gate_and_low_positive_ratio_remains_ranked() -> None:
    result = rank_trade_plans((_plan("LOW", 0.000001),))
    assert result.ranked_actionable[0].risk_reward == 0.000001
    assert not hasattr(result, "minimum_risk_reward")


def test_no_setup_family_preference() -> None:
    pullback = _plan("P", 0.5, setup=SwingSetup.PULLBACK_CONTINUATION)
    breakout = _plan("B", 0.4, setup=SwingSetup.CONSOLIDATION_BREAKOUT)
    result = rank_trade_plans((breakout, pullback))
    assert result.ranked_actionable[0].trade_plan is pullback


def test_no_direction_preference() -> None:
    short = _plan("S", 0.5, direction=SwingDirection.SHORT)
    long = _plan("L", 0.4, direction=SwingDirection.LONG)
    result = rank_trade_plans((long, short))
    assert result.ranked_actionable[0].trade_plan is short


def test_no_asset_class_preference() -> None:
    commodity = _plan("GOLDM", 0.5, asset="commodity")
    equity = _plan("EQ", 0.4, asset="equity")
    index = _plan("NIFTY", 0.3, asset="index")
    result = rank_trade_plans((index, equity, commodity))
    assert [item.trade_plan for item in result.ranked_actionable] == [
        commodity,
        equity,
        index,
    ]


def test_no_confidence_or_pine_input() -> None:
    names = {field.name for field in fields(CandidateRanking)} | {
        field.name for field in fields(type(rank_trade_plans((_plan("A", 1.0),)).ranked_actionable[0]))
    }
    assert "confidence" not in names
    assert "pine" not in names
    assert "readiness" not in names


def test_multiple_plans_for_one_instrument_remain_independent() -> None:
    pullback = _plan("HDFCBANK", 1.0, setup=SwingSetup.PULLBACK_CONTINUATION)
    breakout = _plan("HDFCBANK", 2.0, setup=SwingSetup.CONSOLIDATION_BREAKOUT)
    result = rank_trade_plans((pullback, breakout))
    assert tuple(item.trade_plan for item in result.ranked_actionable) == (
        breakout,
        pullback,
    )


def test_instrument_grouping_exposes_one_attention_identity_with_plan_children() -> None:
    plans = (
        _plan("HDFCBANK", 1.0, setup=SwingSetup.PULLBACK_CONTINUATION),
        _plan("HDFCBANK", 2.0, setup=SwingSetup.CONSOLIDATION_BREAKOUT),
        _plan("AXISBANK", 1.5),
    )
    result = rank_trade_plans(plans)
    hdfc = next(group for group in result.instrument_groups if group.canonical_identity == "HDFCBANK")
    assert len(hdfc.plans) == 2
    assert len(result.instrument_groups) == 2


def test_zero_actionable_plans_is_valid() -> None:
    result = rank_trade_plans((_not_actionable("A"), _invalid("B")))
    assert result.ranked_actionable == ()
    assert result.instrument_groups == ()


def test_one_actionable_plan_does_not_force_second_result() -> None:
    result = rank_trade_plans((_plan("A", 1.0), _not_actionable("B")))
    assert len(result.ranked_actionable) == 1


def test_no_top_selection_contract_is_produced() -> None:
    result = rank_trade_plans((_plan("A", 2.0), _plan("B", 1.0)))
    assert not hasattr(result, "top")
    assert not hasattr(result, "selected")
    assert not hasattr(result, "opportunities")


def test_duplicate_candidate_identity_fails_closed() -> None:
    plan = _plan("A", 1.0)
    with pytest.raises(ValueError, match="TRADE_PLAN_COLLECTION_INVALID"):
        rank_trade_plans((plan, plan))


@pytest.mark.parametrize("invalid", [None, object(), "plans", b"plans"])
def test_malformed_collection_fails_closed(invalid: object) -> None:
    with pytest.raises(ValueError, match="TRADE_PLAN_COLLECTION_INVALID"):
        rank_trade_plans(invalid)  # type: ignore[arg-type]


def test_frozen_stage7_population_produces_approved_real_order_and_history() -> None:
    actionable = (
        _plan("HDFCBANK", 2.83333333333, setup=SwingSetup.CONSOLIDATION_BREAKOUT, direction=SwingDirection.SHORT),
        _plan("AXISBANK", 0.805882352941, direction=SwingDirection.SHORT),
        _plan("ADANIENT", 0.365517241379, direction=SwingDirection.SHORT),
        _plan("TCS", 0.283434650456, direction=SwingDirection.LONG),
        _plan("SRF", 0.269811320755, direction=SwingDirection.SHORT),
        _plan("LUPIN", 0.063829787234, direction=SwingDirection.SHORT),
    )
    preserved = (
        _not_actionable("JUBLFOOD"),
        _not_actionable("MOTHERSON"),
        _not_actionable("M&M"),
        _not_actionable("BHARATFORG"),
        _not_actionable("HDFCBANK"),
        _not_actionable("HINDALCO"),
    )
    result = rank_trade_plans(tuple(reversed(actionable)) + preserved)

    assert [item.canonical_identity for item in result.ranked_actionable] == [
        "HDFCBANK",
        "AXISBANK",
        "ADANIENT",
        "TCS",
        "SRF",
        "LUPIN",
    ]
    assert [item.risk_reward for item in result.ranked_actionable] == [
        2.83333333333,
        0.805882352941,
        0.365517241379,
        0.283434650456,
        0.269811320755,
        0.063829787234,
    ]
    assert [plan.canonical_identity for plan in result.preserved_not_actionable] == [
        "JUBLFOOD",
        "MOTHERSON",
        "M&M",
        "BHARATFORG",
        "HDFCBANK",
        "HINDALCO",
    ]
    assert result.input_count == 12
    assert result.preserved_invalid == ()
