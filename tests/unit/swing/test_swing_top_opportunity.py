from dataclasses import FrozenInstanceError, fields, replace

import pytest

from kronos.swing.candidate_ranking import rank_trade_plans
from kronos.swing.top_opportunity import (
    ATTENTION_RISK_REWARD_STANDARD,
    MAXIMUM_TOP_OPPORTUNITIES,
    SWING_PHASE1_TOP_OPPORTUNITY_POLICY_ID,
    AttentionEligibility,
    TopOpportunitySelection,
    select_top_opportunities,
)
from kronos.swing.trade_plan import TradePlanStatus
from kronos.swing.zero import SwingDirection, SwingSetup
from tests.unit.swing.test_swing_candidate_ranking import (
    _invalid,
    _not_actionable,
    _plan,
)


def _selection(*plans):  # type: ignore[no-untyped-def]
    return select_top_opportunities(rank_trade_plans(plans))


def test_policy_identity_and_constants_are_exact() -> None:
    result = _selection()
    assert result.policy_id == "SWING-PHASE1-V0-TOP-OPPORTUNITY-POLICY"
    assert result.policy_id == SWING_PHASE1_TOP_OPPORTUNITY_POLICY_ID
    assert ATTENTION_RISK_REWARD_STANDARD == 1.0
    assert result.maximum_opportunities == MAXIMUM_TOP_OPPORTUNITIES == 2


@pytest.mark.parametrize("ratio", [1.000001, 2.5])
def test_actionable_above_standard_is_attention_eligible(ratio: float) -> None:
    result = _selection(_plan("A", ratio))
    assert result.attention_eligible[0].eligibility is AttentionEligibility.ATTENTION_ELIGIBLE


def test_actionable_exactly_at_standard_is_attention_eligible() -> None:
    result = _selection(_plan("A", 1.0))
    assert result.attention_eligible[0].ranked_plan.risk_reward == 1.0


@pytest.mark.parametrize("ratio", [0.999999, 0.8, 0.000001])
def test_actionable_below_standard_is_preserved_below_attention(ratio: float) -> None:
    plan = _plan("A", ratio)
    result = _selection(plan)
    assert result.attention_eligible == ()
    assert result.below_attention_standard[0].ranked_plan.trade_plan is plan
    assert result.below_attention_standard[0].explanation == (
        "ACTIONABLE but R:R < 1.00 attention standard"
    )


def test_not_actionable_is_not_attention_eligible_and_is_preserved() -> None:
    plan = _not_actionable("A")
    result = _selection(plan)
    assert result.attention_eligible == ()
    assert result.preserved_not_actionable == (plan,)


def test_invalid_is_preserved_separately() -> None:
    plan = _invalid("A")
    assert _selection(plan).preserved_invalid == (plan,)


def test_stage7_trade_plan_status_never_changes() -> None:
    plan = _plan("A", 0.8)
    _selection(plan)
    assert plan.status is TradePlanStatus.ACTIONABLE


def test_zero_eligible_returns_zero_selected() -> None:
    result = _selection(_plan("A", 0.8), _not_actionable("B"))
    assert result.selected_top_opportunities == ()


def test_one_eligible_returns_one_selected_and_preserves_empty_slot() -> None:
    result = _selection(_plan("A", 1.1), _plan("B", 0.9))
    assert len(result.selected_top_opportunities) == 1
    assert result.selected_top_opportunities[0].position == 1


def test_two_eligible_returns_two_selected() -> None:
    result = _selection(_plan("A", 2.0), _plan("B", 1.0))
    assert [item.attention_entry.canonical_identity for item in result.selected_top_opportunities] == ["A", "B"]


def test_three_or_more_eligible_never_selects_more_than_two() -> None:
    result = _selection(_plan("A", 3.0), _plan("B", 2.0), _plan("C", 1.0))
    assert len(result.selected_top_opportunities) == 2
    assert [item.attention_entry.canonical_identity for item in result.selected_top_opportunities] == ["A", "B"]


def test_no_fallback_when_only_one_plan_is_eligible() -> None:
    result = _selection(_plan("A", 2.0), _plan("B", 0.999999))
    assert len(result.selected_top_opportunities) == 1
    assert result.below_attention_standard[0].ranked_plan.canonical_identity == "B"


def test_threshold_never_relaxes_for_best_available_plan() -> None:
    result = _selection(_plan("A", 0.99), _plan("B", 0.98))
    assert result.selected_top_opportunities == ()


def test_same_instrument_eligible_plans_group_into_one_entry() -> None:
    result = _selection(
        _plan("A", 2.0, setup=SwingSetup.PULLBACK_CONTINUATION),
        _plan("A", 1.5, setup=SwingSetup.CONSOLIDATION_BREAKOUT),
    )
    assert len(result.grouped_instruments) == 1
    assert len(result.selected_top_opportunities) == 1


def test_highest_stage8_ranked_plan_is_representative() -> None:
    higher = _plan("A", 2.0, setup=SwingSetup.PULLBACK_CONTINUATION)
    lower = _plan("A", 1.5, setup=SwingSetup.CONSOLIDATION_BREAKOUT)
    result = _selection(lower, higher)
    assert result.grouped_instruments[0].representative_plan.ranked_plan.trade_plan is higher


def test_supporting_plan_children_remain_independent_and_original() -> None:
    higher = _plan("A", 2.0, setup=SwingSetup.PULLBACK_CONTINUATION)
    lower = _plan("A", 1.5, setup=SwingSetup.CONSOLIDATION_BREAKOUT)
    group = _selection(higher, lower).grouped_instruments[0]
    assert group.representative_plan.ranked_plan.trade_plan is higher
    assert group.supporting_plans[0].ranked_plan.trade_plan is lower


def test_supporting_plan_does_not_consume_second_slot() -> None:
    result = _selection(
        _plan("A", 3.0, setup=SwingSetup.PULLBACK_CONTINUATION),
        _plan("A", 2.0, setup=SwingSetup.CONSOLIDATION_BREAKOUT),
        _plan("B", 1.5),
    )
    assert [item.attention_entry.canonical_identity for item in result.selected_top_opportunities] == ["A", "B"]


def test_no_risk_reward_addition_or_averaging_fields_exist() -> None:
    result = _selection(
        _plan("A", 3.0, setup=SwingSetup.PULLBACK_CONTINUATION),
        _plan("A", 1.0, setup=SwingSetup.CONSOLIDATION_BREAKOUT),
    )
    group_names = {field.name for field in fields(type(result.grouped_instruments[0]))}
    assert "summed_risk_reward" not in group_names
    assert "average_risk_reward" not in group_names
    assert result.grouped_instruments[0].representative_plan.ranked_plan.risk_reward == 3.0


def test_stage8_order_is_reused_without_independent_reranking() -> None:
    ranking = rank_trade_plans((_plan("B", 2.0), _plan("A", 3.0)))
    result = select_top_opportunities(ranking)
    assert result.ranked_input is ranking
    assert [item.representative_plan.position for item in result.selected_top_opportunities] == [1, 2]


def test_cutoff_ties_reuse_stage8_identity_order_and_do_not_expand() -> None:
    result = _selection(_plan("C", 1.0), _plan("A", 1.0), _plan("B", 1.0))
    assert [item.attention_entry.canonical_identity for item in result.selected_top_opportunities] == ["A", "B"]
    assert len(result.selected_top_opportunities) == 2


def test_no_long_short_quota() -> None:
    result = _selection(
        _plan("A", 3.0, direction=SwingDirection.SHORT),
        _plan("B", 2.0, direction=SwingDirection.SHORT),
        _plan("C", 1.5, direction=SwingDirection.LONG),
    )
    assert [item.trade_plan.direction for item in result.selected_top_opportunities] == [
        SwingDirection.SHORT,
        SwingDirection.SHORT,
    ]


def test_no_asset_class_quota() -> None:
    result = _selection(
        _plan("GOLDM", 3.0, asset="commodity"),
        _plan("COPPER", 2.0, asset="commodity"),
        _plan("EQ", 1.5, asset="equity"),
    )
    assert [item.trade_plan.canonical_identity for item in result.selected_top_opportunities] == ["GOLDM", "COPPER"]


def test_no_setup_family_quota() -> None:
    result = _selection(
        _plan("A", 3.0, setup=SwingSetup.PULLBACK_CONTINUATION),
        _plan("B", 2.0, setup=SwingSetup.PULLBACK_CONTINUATION),
        _plan("C", 1.5, setup=SwingSetup.CONSOLIDATION_BREAKOUT),
    )
    assert all(
        item.trade_plan.setup is SwingSetup.PULLBACK_CONTINUATION
        for item in result.selected_top_opportunities
    )


def test_below_attention_actionable_population_is_preserved_in_stage8_order() -> None:
    low = _plan("LOW", 0.1)
    medium = _plan("MEDIUM", 0.8)
    result = _selection(low, medium)
    assert [item.ranked_plan.trade_plan for item in result.below_attention_standard] == [medium, low]


def test_not_actionable_population_is_preserved_in_input_order() -> None:
    first = _not_actionable("B")
    second = _not_actionable("A")
    assert _selection(first, second).preserved_not_actionable == (first, second)


def test_input_ranking_result_is_not_mutated() -> None:
    ranking = rank_trade_plans((_plan("A", 2.0), _plan("B", 0.8)))
    before = hash(ranking)
    select_top_opportunities(ranking)
    assert hash(ranking) == before


def test_original_trade_plans_are_preserved_by_identity() -> None:
    eligible = _plan("A", 2.0)
    below = _plan("B", 0.8)
    result = _selection(eligible, below)
    assert result.selected_top_opportunities[0].trade_plan is eligible
    assert result.below_attention_standard[0].ranked_plan.trade_plan is below


def test_repeated_selection_is_deterministic() -> None:
    ranking = rank_trade_plans((_plan("A", 2.0), _plan("B", 0.8)))
    assert select_top_opportunities(ranking) == select_top_opportunities(ranking)
    assert hash(select_top_opportunities(ranking)) == hash(select_top_opportunities(ranking))


def test_selection_result_is_immutable() -> None:
    result = _selection(_plan("A", 2.0))
    with pytest.raises((FrozenInstanceError, AttributeError)):
        result.maximum_opportunities = 3  # type: ignore[misc]


def test_no_pine_predecision_or_execution_state_is_present() -> None:
    names = {field.name.lower() for field in fields(TopOpportunitySelection)}
    prohibited = {
        "pine",
        "confidence",
        "pre_decision",
        "live",
        "paper",
        "ignore",
        "execution",
        "position_size",
        "monitoring",
    }
    assert names.isdisjoint(prohibited)


@pytest.mark.parametrize("invalid", [None, object(), (), "ranking"])
def test_malformed_ranking_fails_closed(invalid: object) -> None:
    with pytest.raises(ValueError, match="CANDIDATE_RANKING_INVALID"):
        select_top_opportunities(invalid)  # type: ignore[arg-type]


def test_frozen_stage8_ranking_selects_only_real_hdfcbank_opportunity() -> None:
    hdfc = replace(
        _plan(
            "HDFCBANK",
            2.83333333333,
            setup=SwingSetup.CONSOLIDATION_BREAKOUT,
            direction=SwingDirection.SHORT,
        ),
        entry=728.2,
        entry_condition="Subsequent session trades BELOW Entry",
        stop=736.0,
        thesis_invalidation=(
            "Completed Daily Close >= original Consolidation Range Low 732",
        ),
        target_1=706.1,
        risk_per_unit=7.8,
        reward_per_unit=22.1,
    )
    actionable = (
        hdfc,
        _plan("AXISBANK", 0.805882352941, direction=SwingDirection.SHORT),
        _plan("ADANIENT", 0.365517241379, direction=SwingDirection.SHORT),
        _plan("TCS", 0.283434650456, direction=SwingDirection.LONG),
        _plan("SRF", 0.269811320755, direction=SwingDirection.SHORT),
        _plan("LUPIN", 0.063829787234, direction=SwingDirection.SHORT),
    )
    not_actionable = tuple(
        _not_actionable(identity)
        for identity in (
            "JUBLFOOD",
            "MOTHERSON",
            "M&M",
            "BHARATFORG",
            "HDFCBANK",
            "HINDALCO",
        )
    )
    result = _selection(*(actionable + not_actionable))
    opportunity = result.selected_top_opportunities[0]

    assert len(result.attention_eligible) == 1
    assert len(result.below_attention_standard) == 5
    assert len(result.selected_top_opportunities) == 1
    assert opportunity.attention_entry.canonical_identity == "HDFCBANK"
    assert opportunity.representative_plan.position == 1
    assert opportunity.trade_plan.setup is SwingSetup.CONSOLIDATION_BREAKOUT
    assert opportunity.trade_plan.direction is SwingDirection.SHORT
    assert opportunity.trade_plan.entry == 728.2
    assert opportunity.trade_plan.entry_condition == "Subsequent session trades BELOW Entry"
    assert opportunity.trade_plan.stop == 736.0
    assert opportunity.trade_plan.thesis_invalidation == (
        "Completed Daily Close >= original Consolidation Range Low 732",
    )
    assert opportunity.trade_plan.target_1 == 706.1
    assert opportunity.trade_plan.risk_per_unit == 7.8
    assert opportunity.trade_plan.reward_per_unit == 22.1
    assert opportunity.trade_plan.risk_reward == 2.83333333333
    assert len(result.preserved_not_actionable) == 6
