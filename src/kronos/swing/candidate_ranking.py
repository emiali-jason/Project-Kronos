"""Deterministic Swing Phase 1 V0 candidate ranking."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import math

from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.swing.trade_plan import TradePlan, TradePlanStatus
from kronos.swing.zero import SwingDirection, SwingSetup


SWING_PHASE1_CANDIDATE_RANKING_POLICY_ID = (
    "SWING-PHASE1-V0-CANDIDATE-RANKING-POLICY"
)


@dataclass(frozen=True, slots=True)
class RankedTradePlan:
    """One ACTIONABLE plan at its deterministic relative rank."""

    position: int
    canonical_instrument: InstrumentRecord
    canonical_identity: str
    candidate_identity: str
    setup: SwingSetup
    direction: SwingDirection
    risk_reward: float
    trade_plan: TradePlan
    policy_id: str

    def __post_init__(self) -> None:
        plan = self.trade_plan
        if (
            type(self.position) is not int
            or self.position < 1
            or type(plan) is not TradePlan
            or plan.status is not TradePlanStatus.ACTIONABLE
            or plan.risk_reward is None
            or type(self.risk_reward) is not float
            or not math.isfinite(self.risk_reward)
            or self.risk_reward <= 0.0
            or self.canonical_instrument is not plan.canonical_instrument
            or self.canonical_identity != plan.canonical_identity
            or self.candidate_identity != plan.candidate_identity
            or self.setup is not plan.setup
            or self.direction is not plan.direction
            or self.risk_reward != plan.risk_reward
            or self.policy_id != SWING_PHASE1_CANDIDATE_RANKING_POLICY_ID
        ):
            raise ValueError("RANKED_TRADE_PLAN_INVALID")


@dataclass(frozen=True, slots=True)
class InstrumentAttentionGroup:
    """One attention identity with one or more independently ranked plans."""

    canonical_identity: str
    plans: tuple[RankedTradePlan, ...]

    def __post_init__(self) -> None:
        if (
            type(self.canonical_identity) is not str
            or not self.canonical_identity
            or type(self.plans) is not tuple
            or not self.plans
            or any(type(plan) is not RankedTradePlan for plan in self.plans)
            or any(
                plan.canonical_identity != self.canonical_identity
                for plan in self.plans
            )
            or tuple(sorted(self.plans, key=lambda plan: plan.position))
            != self.plans
        ):
            raise ValueError("INSTRUMENT_ATTENTION_GROUP_INVALID")


@dataclass(frozen=True, slots=True)
class CandidateRanking:
    """Complete Stage-8 reconciliation without Stage-9 selection authority."""

    policy_id: str
    input_count: int
    ranked_actionable: tuple[RankedTradePlan, ...]
    preserved_not_actionable: tuple[TradePlan, ...]
    preserved_invalid: tuple[TradePlan, ...]
    instrument_groups: tuple[InstrumentAttentionGroup, ...]

    def __post_init__(self) -> None:
        ranked_plans = tuple(item.trade_plan for item in self.ranked_actionable)
        all_plans = (
            ranked_plans
            + self.preserved_not_actionable
            + self.preserved_invalid
        )
        grouped = tuple(
            item
            for group in self.instrument_groups
            for item in group.plans
        )
        if (
            self.policy_id != SWING_PHASE1_CANDIDATE_RANKING_POLICY_ID
            or type(self.input_count) is not int
            or self.input_count < 0
            or any(
                type(collection) is not tuple
                for collection in (
                    self.ranked_actionable,
                    self.preserved_not_actionable,
                    self.preserved_invalid,
                    self.instrument_groups,
                )
            )
            or any(
                type(item) is not RankedTradePlan
                for item in self.ranked_actionable
            )
            or any(
                type(plan) is not TradePlan
                for plan in self.preserved_not_actionable
                + self.preserved_invalid
            )
            or tuple(item.position for item in self.ranked_actionable)
            != tuple(range(1, len(self.ranked_actionable) + 1))
            or tuple(
                sorted(
                    self.ranked_actionable,
                    key=lambda item: _ranking_key(item.trade_plan),
                )
            )
            != self.ranked_actionable
            or any(
                plan.status is not TradePlanStatus.NOT_ACTIONABLE
                for plan in self.preserved_not_actionable
            )
            or any(
                plan.status is not TradePlanStatus.INVALID
                for plan in self.preserved_invalid
            )
            or len(all_plans) != self.input_count
            or len({plan.candidate_identity for plan in all_plans})
            != self.input_count
            or tuple(sorted(grouped, key=lambda item: item.position))
            != self.ranked_actionable
        ):
            raise ValueError("CANDIDATE_RANKING_INVALID")


def rank_trade_plans(plans: Sequence[TradePlan]) -> CandidateRanking:
    """Rank ACTIONABLE plans by R:R and reconcile every Stage-7 input."""

    if isinstance(plans, (str, bytes)) or not isinstance(plans, Sequence):
        raise ValueError("TRADE_PLAN_COLLECTION_INVALID")
    inputs = tuple(plans)
    if (
        any(type(plan) is not TradePlan for plan in inputs)
        or len({plan.candidate_identity for plan in inputs}) != len(inputs)
    ):
        raise ValueError("TRADE_PLAN_COLLECTION_INVALID")

    actionable = tuple(
        sorted(
            (plan for plan in inputs if plan.status is TradePlanStatus.ACTIONABLE),
            key=_ranking_key,
        )
    )
    ranked = tuple(
        RankedTradePlan(
            position=position,
            canonical_instrument=plan.canonical_instrument,
            canonical_identity=plan.canonical_identity,
            candidate_identity=plan.candidate_identity,
            setup=plan.setup,
            direction=plan.direction,
            risk_reward=plan.risk_reward,  # type: ignore[arg-type]
            trade_plan=plan,
            policy_id=SWING_PHASE1_CANDIDATE_RANKING_POLICY_ID,
        )
        for position, plan in enumerate(actionable, start=1)
    )
    identities = tuple(dict.fromkeys(item.canonical_identity for item in ranked))
    groups = tuple(
        InstrumentAttentionGroup(
            canonical_identity=identity,
            plans=tuple(
                item for item in ranked if item.canonical_identity == identity
            ),
        )
        for identity in identities
    )
    return CandidateRanking(
        policy_id=SWING_PHASE1_CANDIDATE_RANKING_POLICY_ID,
        input_count=len(inputs),
        ranked_actionable=ranked,
        preserved_not_actionable=tuple(
            plan for plan in inputs
            if plan.status is TradePlanStatus.NOT_ACTIONABLE
        ),
        preserved_invalid=tuple(
            plan for plan in inputs if plan.status is TradePlanStatus.INVALID
        ),
        instrument_groups=groups,
    )


def _ranking_key(plan: TradePlan) -> tuple[float, str, str, str, str]:
    ratio = plan.risk_reward
    if ratio is None:
        raise ValueError("ACTIONABLE_RISK_REWARD_UNAVAILABLE")
    return (
        -ratio,
        plan.canonical_identity,
        plan.setup.value,
        plan.direction.value,
        plan.candidate_identity,
    )


__all__ = [
    "SWING_PHASE1_CANDIDATE_RANKING_POLICY_ID",
    "CandidateRanking",
    "InstrumentAttentionGroup",
    "RankedTradePlan",
    "rank_trade_plans",
]
