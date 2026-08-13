"""Same-facts application orchestration for V0 and Swing V1 Layer 1."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from kronos.swing.daily_data import SwingDailyDataset
from kronos.swing.market_assessment import (
    SwingInstrumentAssessments,
    SwingMarketAssessment,
    assess_swing_market,
)
from kronos.swing.zero import SwingDirection, SwingSetup, SwingState
from kronos.swing.v1.interfaces import V1BenchmarkMap
from kronos.swing.v1.layer1 import analyze_v1_layer1
from kronos.swing.v1.models import (
    ProbableClassification,
    V1Direction,
    V1Layer1Assessment,
    V1Layer1Run,
    V1Setup,
)


class V0V1ComparisonClassification(StrEnum):
    """Minimum shadow-comparison classes plus explicit incomplete input."""

    V0_QUALIFIED_V1_SUPPORTS = "V0_QUALIFIED_V1_SUPPORTS"
    V0_QUALIFIED_V1_CONTRADICTION = "V0_QUALIFIED_V1_CONTRADICTION"
    V0_NONQUALIFIED_V1_PROBABLE = "V0_NONQUALIFIED_V1_PROBABLE"
    BOTH_REJECT_OR_INSUFFICIENT = "BOTH_REJECT_OR_INSUFFICIENT"
    V1_POLICY_UNRESOLVED = "V1_POLICY_UNRESOLVED"
    COMPARISON_INPUT_INCOMPLETE = "COMPARISON_INPUT_INCOMPLETE"


@dataclass(frozen=True, slots=True)
class V0V1SetupComparison:
    """Side-by-side classification for one identity and setup family."""

    canonical_identity: str
    setup: V1Setup
    classification: V0V1ComparisonClassification
    v0_state: SwingState | None
    v0_direction: SwingDirection | None
    v1_assessment: V1Layer1Assessment

    def __post_init__(self) -> None:
        if (
            type(self.canonical_identity) is not str
            or not self.canonical_identity
            or type(self.setup) is not V1Setup
            or type(self.classification) is not V0V1ComparisonClassification
            or (self.v0_state is not None and type(self.v0_state) is not SwingState)
            or (
                self.v0_direction is not None
                and type(self.v0_direction) is not SwingDirection
            )
            or type(self.v1_assessment) is not V1Layer1Assessment
            or self.v1_assessment.canonical_identity != self.canonical_identity
            or self.v1_assessment.setup is not self.setup
            or ((self.v0_state is None) != (self.v0_direction is None))
        ):
            raise ValueError("SWING_V0_V1_SETUP_COMPARISON_INVALID")


@dataclass(frozen=True, slots=True)
class SwingV0V1Layer1Comparison:
    """Unchanged V0 control and additive V1 output over one fact boundary."""

    v0_control: SwingMarketAssessment
    v1_layer1: V1Layer1Run
    setup_comparisons: tuple[V0V1SetupComparison, ...]
    same_market_facts: bool

    def __post_init__(self) -> None:
        if (
            type(self.v0_control) is not SwingMarketAssessment
            or type(self.v1_layer1) is not V1Layer1Run
            or type(self.setup_comparisons) is not tuple
            or len(self.setup_comparisons) != 196
            or any(
                type(item) is not V0V1SetupComparison
                for item in self.setup_comparisons
            )
            or self.same_market_facts is not True
            or self.v0_control.observation_boundary
            != self.v1_layer1.observation_boundary
            or self.v0_control.requested_count != 98
            or len(self.v1_layer1.instruments) != 98
        ):
            raise ValueError("SWING_V0_V1_LAYER1_COMPARISON_INVALID")


def build_v0_v1_layer1_comparison(
    dataset: SwingDailyDataset,
    *,
    benchmark_map: V1BenchmarkMap | None = None,
) -> SwingV0V1Layer1Comparison:
    """Run V0 unchanged, then V1 Layer 1, over the same immutable dataset."""

    if type(dataset) is not SwingDailyDataset:
        raise ValueError("SWING_V0_V1_LAYER1_COMPARISON_REQUEST_INVALID")
    v0_control = assess_swing_market(dataset)
    v1_layer1 = analyze_v1_layer1(dataset, benchmark_map=benchmark_map)
    v0_by_identity = {
        item.canonical_identity: item for item in v0_control.instruments
    }
    comparisons = tuple(
        _compare_setup(
            v1_assessment,
            v0_by_identity[v1_instrument.canonical_identity],
        )
        for v1_instrument in v1_layer1.instruments
        for v1_assessment in v1_instrument.assessments
    )
    return SwingV0V1Layer1Comparison(
        v0_control,
        v1_layer1,
        comparisons,
        True,
    )


def _compare_setup(
    v1_assessment: V1Layer1Assessment,
    v0_instrument: SwingInstrumentAssessments,
) -> V0V1SetupComparison:
    v0_setup = (
        SwingSetup.PULLBACK_CONTINUATION
        if v1_assessment.setup is V1Setup.PULLBACK_CONTINUATION
        else SwingSetup.CONSOLIDATION_BREAKOUT
    )
    v0_assessment = next(
        (
            item
            for item in v0_instrument.assessments
            if item.setup is v0_setup
        ),
        None,
    )
    if v0_assessment is None or (
        v1_assessment.classification
        is ProbableClassification.EVIDENCE_INCOMPLETE
    ):
        classification = V0V1ComparisonClassification.COMPARISON_INPUT_INCOMPLETE
    elif (
        v1_assessment.classification
        is ProbableClassification.POLICY_UNRESOLVED
    ):
        classification = V0V1ComparisonClassification.V1_POLICY_UNRESOLVED
    elif v0_assessment.state is SwingState.QUALIFIED:
        v1_direction = _v1_to_v0_direction(v1_assessment.direction)
        classification = (
            V0V1ComparisonClassification.V0_QUALIFIED_V1_SUPPORTS
            if v1_assessment.classification
            is ProbableClassification.PROBABLE_CANDIDATE
            and v1_direction is v0_assessment.direction
            else V0V1ComparisonClassification.V0_QUALIFIED_V1_CONTRADICTION
        )
    elif (
        v1_assessment.classification
        is ProbableClassification.PROBABLE_CANDIDATE
    ):
        classification = V0V1ComparisonClassification.V0_NONQUALIFIED_V1_PROBABLE
    else:
        classification = V0V1ComparisonClassification.BOTH_REJECT_OR_INSUFFICIENT
    return V0V1SetupComparison(
        canonical_identity=v1_assessment.canonical_identity,
        setup=v1_assessment.setup,
        classification=classification,
        v0_state=v0_assessment.state if v0_assessment is not None else None,
        v0_direction=(
            v0_assessment.direction if v0_assessment is not None else None
        ),
        v1_assessment=v1_assessment,
    )


def _v1_to_v0_direction(direction: V1Direction) -> SwingDirection:
    return {
        V1Direction.LONG: SwingDirection.LONG,
        V1Direction.SHORT: SwingDirection.SHORT,
        V1Direction.NONE: SwingDirection.NONE,
    }[direction]


__all__ = [
    "SwingV0V1Layer1Comparison",
    "V0V1ComparisonClassification",
    "V0V1SetupComparison",
    "build_v0_v1_layer1_comparison",
]
