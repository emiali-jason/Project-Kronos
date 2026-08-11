"""Deterministic Swing Phase 1 V0 Top-Opportunity selection."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from kronos.swing.candidate_ranking import CandidateRanking, RankedTradePlan
from kronos.swing.trade_plan import TradePlan


SWING_PHASE1_TOP_OPPORTUNITY_POLICY_ID = (
    "SWING-PHASE1-V0-TOP-OPPORTUNITY-POLICY"
)
ATTENTION_RISK_REWARD_STANDARD = 1.0
MAXIMUM_TOP_OPPORTUNITIES = 2


class AttentionEligibility(StrEnum):
    """Stage-9 attention classification without changing Trade Plan status."""

    ATTENTION_ELIGIBLE = "ATTENTION_ELIGIBLE"
    BELOW_ATTENTION_STANDARD = "BELOW_ATTENTION_STANDARD"


@dataclass(frozen=True, slots=True)
class AttentionPlan:
    """One Stage-8-ranked ACTIONABLE plan and its Stage-9 classification."""

    ranked_plan: RankedTradePlan
    eligibility: AttentionEligibility
    explanation: str

    def __post_init__(self) -> None:
        if type(self.ranked_plan) is not RankedTradePlan:
            raise ValueError("ATTENTION_PLAN_INVALID")
        eligible = self.ranked_plan.risk_reward >= ATTENTION_RISK_REWARD_STANDARD
        if (
            type(self.eligibility) is not AttentionEligibility
            or not self.explanation
            or eligible
            != (self.eligibility is AttentionEligibility.ATTENTION_ELIGIBLE)
        ):
            raise ValueError("ATTENTION_PLAN_INVALID")


@dataclass(frozen=True, slots=True)
class InstrumentAttentionEntry:
    """One canonical instrument with a representative and supporting plans."""

    canonical_identity: str
    representative_plan: AttentionPlan
    supporting_plans: tuple[AttentionPlan, ...]

    def __post_init__(self) -> None:
        if type(self.representative_plan) is not AttentionPlan:
            raise ValueError("INSTRUMENT_ATTENTION_ENTRY_INVALID")
        plans = (self.representative_plan,) + self.supporting_plans
        if (
            type(self.canonical_identity) is not str
            or not self.canonical_identity
            or type(self.supporting_plans) is not tuple
            or any(type(plan) is not AttentionPlan for plan in plans)
            or any(
                plan.eligibility is not AttentionEligibility.ATTENTION_ELIGIBLE
                or plan.ranked_plan.canonical_identity != self.canonical_identity
                for plan in plans
            )
            or any(
                plan.ranked_plan.position
                <= self.representative_plan.ranked_plan.position
                for plan in self.supporting_plans
            )
            or tuple(
                sorted(
                    self.supporting_plans,
                    key=lambda plan: plan.ranked_plan.position,
                )
            )
            != self.supporting_plans
        ):
            raise ValueError("INSTRUMENT_ATTENTION_ENTRY_INVALID")


@dataclass(frozen=True, slots=True)
class TopOpportunity:
    """One selected canonical instrument and its original plan evidence."""

    position: int
    attention_entry: InstrumentAttentionEntry
    selection_explanation: str
    policy_id: str

    def __post_init__(self) -> None:
        if (
            type(self.position) is not int
            or self.position < 1
            or type(self.attention_entry) is not InstrumentAttentionEntry
            or not self.selection_explanation
            or self.policy_id != SWING_PHASE1_TOP_OPPORTUNITY_POLICY_ID
        ):
            raise ValueError("TOP_OPPORTUNITY_INVALID")

    @property
    def representative_plan(self) -> RankedTradePlan:
        return self.attention_entry.representative_plan.ranked_plan

    @property
    def trade_plan(self) -> TradePlan:
        return self.representative_plan.trade_plan


@dataclass(frozen=True, slots=True)
class TopOpportunitySelection:
    """Complete Stage-9 selection and preservation result."""

    policy_id: str
    ranked_input: CandidateRanking
    attention_eligible: tuple[AttentionPlan, ...]
    below_attention_standard: tuple[AttentionPlan, ...]
    grouped_instruments: tuple[InstrumentAttentionEntry, ...]
    selected_top_opportunities: tuple[TopOpportunity, ...]
    preserved_not_actionable: tuple[TradePlan, ...]
    preserved_invalid: tuple[TradePlan, ...]
    maximum_opportunities: int

    def __post_init__(self) -> None:
        classified = self.attention_eligible + self.below_attention_standard
        classified_ranked = tuple(plan.ranked_plan for plan in classified)
        grouped = tuple(
            plan
            for entry in self.grouped_instruments
            for plan in (entry.representative_plan,) + entry.supporting_plans
        )
        selected_entries = tuple(
            opportunity.attention_entry
            for opportunity in self.selected_top_opportunities
        )
        if (
            self.policy_id != SWING_PHASE1_TOP_OPPORTUNITY_POLICY_ID
            or type(self.ranked_input) is not CandidateRanking
            or any(
                type(collection) is not tuple
                for collection in (
                    self.attention_eligible,
                    self.below_attention_standard,
                    self.grouped_instruments,
                    self.selected_top_opportunities,
                    self.preserved_not_actionable,
                    self.preserved_invalid,
                )
            )
            or self.maximum_opportunities != MAXIMUM_TOP_OPPORTUNITIES
            or len(self.selected_top_opportunities) > self.maximum_opportunities
            or tuple(
                sorted(classified_ranked, key=lambda plan: plan.position)
            )
            != self.ranked_input.ranked_actionable
            or any(
                plan.eligibility is not AttentionEligibility.ATTENTION_ELIGIBLE
                for plan in self.attention_eligible
            )
            or any(
                plan.eligibility
                is not AttentionEligibility.BELOW_ATTENTION_STANDARD
                for plan in self.below_attention_standard
            )
            or tuple(
                sorted(grouped, key=lambda plan: plan.ranked_plan.position)
            )
            != self.attention_eligible
            or selected_entries
            != self.grouped_instruments[: self.maximum_opportunities]
            or tuple(
                opportunity.position
                for opportunity in self.selected_top_opportunities
            )
            != tuple(range(1, len(self.selected_top_opportunities) + 1))
            or self.preserved_not_actionable
            != self.ranked_input.preserved_not_actionable
            or self.preserved_invalid != self.ranked_input.preserved_invalid
        ):
            raise ValueError("TOP_OPPORTUNITY_SELECTION_INVALID")


def select_top_opportunities(ranking: CandidateRanking) -> TopOpportunitySelection:
    """Apply the absolute Stage-9 attention standard to Stage-8 order."""

    if type(ranking) is not CandidateRanking:
        raise ValueError("CANDIDATE_RANKING_INVALID")

    assessments = tuple(
        AttentionPlan(
            ranked_plan=ranked,
            eligibility=(
                AttentionEligibility.ATTENTION_ELIGIBLE
                if ranked.risk_reward >= ATTENTION_RISK_REWARD_STANDARD
                else AttentionEligibility.BELOW_ATTENTION_STANDARD
            ),
            explanation=(
                "ACTIONABLE and R:R >= 1.00 attention standard"
                if ranked.risk_reward >= ATTENTION_RISK_REWARD_STANDARD
                else "ACTIONABLE but R:R < 1.00 attention standard"
            ),
        )
        for ranked in ranking.ranked_actionable
    )
    eligible = tuple(
        plan
        for plan in assessments
        if plan.eligibility is AttentionEligibility.ATTENTION_ELIGIBLE
    )
    below = tuple(
        plan
        for plan in assessments
        if plan.eligibility is AttentionEligibility.BELOW_ATTENTION_STANDARD
    )
    identities = tuple(
        dict.fromkeys(plan.ranked_plan.canonical_identity for plan in eligible)
    )
    groups = tuple(
        InstrumentAttentionEntry(
            canonical_identity=identity,
            representative_plan=next(
                plan
                for plan in eligible
                if plan.ranked_plan.canonical_identity == identity
            ),
            supporting_plans=tuple(
                plan
                for plan in eligible
                if plan.ranked_plan.canonical_identity == identity
            )[1:],
        )
        for identity in identities
    )
    selected = tuple(
        TopOpportunity(
            position=position,
            attention_entry=entry,
            selection_explanation=(
                "Selected from attention-eligible canonical instruments by "
                "representative Stage-8 rank"
            ),
            policy_id=SWING_PHASE1_TOP_OPPORTUNITY_POLICY_ID,
        )
        for position, entry in enumerate(
            groups[:MAXIMUM_TOP_OPPORTUNITIES],
            start=1,
        )
    )
    return TopOpportunitySelection(
        policy_id=SWING_PHASE1_TOP_OPPORTUNITY_POLICY_ID,
        ranked_input=ranking,
        attention_eligible=eligible,
        below_attention_standard=below,
        grouped_instruments=groups,
        selected_top_opportunities=selected,
        preserved_not_actionable=ranking.preserved_not_actionable,
        preserved_invalid=ranking.preserved_invalid,
        maximum_opportunities=MAXIMUM_TOP_OPPORTUNITIES,
    )


__all__ = [
    "ATTENTION_RISK_REWARD_STANDARD",
    "MAXIMUM_TOP_OPPORTUNITIES",
    "SWING_PHASE1_TOP_OPPORTUNITY_POLICY_ID",
    "AttentionEligibility",
    "AttentionPlan",
    "InstrumentAttentionEntry",
    "TopOpportunity",
    "TopOpportunitySelection",
    "select_top_opportunities",
]
