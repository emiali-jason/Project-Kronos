"""TradingView review contracts for the human-in-the-loop Swing V1 gate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Iterable

from kronos.swing.v1.models import (
    EvidenceAvailability,
    ProbableClassification,
    V1Direction,
    V1Layer1Assessment,
    V1Layer1Run,
    V1Setup,
)
from kronos.swing.run_identity import (
    LEGACY_UNBOUND_SWING_RUN_ID,
    is_swing_run_binding,
)


TRADINGVIEW_CHART_TEMPLATE_ID = "KRONOS-TV-SWING-V1-CANDIDATE@1"
TRADINGVIEW_UPLOAD_SOURCE = "SPONSOR_TRADINGVIEW_UPLOAD"
TRADINGVIEW_RETENTION_CLASS = "TRADINGVIEW_EVIDENCE"
DATA_ALIGNMENT_REVIEW = "DATA_ALIGNMENT_REVIEW"


class ChartTimeframe(StrEnum):
    DAILY = "DAILY"
    FOUR_HOUR = "4H"
    ONE_HOUR = "1H"


class TradingViewReviewStatus(StrEnum):
    TRADINGVIEW_REVIEW_REQUIRED = "TRADINGVIEW_REVIEW_REQUIRED"
    CONTEXT_INCOMPLETE = "CONTEXT_INCOMPLETE"
    TRADINGVIEW_CONTEXT_RECEIVED = "TRADINGVIEW_CONTEXT_RECEIVED"


class TradingViewIndicator(StrEnum):
    SMA20 = "SMA20"
    SMA50 = "SMA50"
    SMA200 = "SMA200"


class Layer2Provenance(StrEnum):
    RAW_TRADINGVIEW_CHART = "RAW_TRADINGVIEW_CHART"
    SPONSOR_RECORDED = "SPONSOR_RECORDED"
    PINE_DISPLAY = "PINE_DISPLAY"


class Layer2StructureState(StrEnum):
    HH_HL = "HH_HL"
    LH_LL = "LH_LL"
    MIXED_UNCLEAR = "MIXED_UNCLEAR"


@dataclass(frozen=True, slots=True)
class PriceStructureVisualEvidence:
    availability: EvidenceAvailability
    provenance: tuple[Layer2Provenance, ...]
    state: Layer2StructureState | None

    def __post_init__(self) -> None:
        if (
            type(self.availability) is not EvidenceAvailability
            or type(self.provenance) is not tuple
            or (self.state is not None and type(self.state) is not Layer2StructureState)
            or (
                self.availability is EvidenceAvailability.AVAILABLE
                and (not self.provenance or self.state is None)
            )
            or (
                self.availability is not EvidenceAvailability.AVAILABLE
                and self.state is not None
            )
        ):
            raise ValueError("TRADINGVIEW_PRICE_STRUCTURE_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class ReferenceLevelVisualEvidence:
    availability: EvidenceAvailability
    provenance: tuple[Layer2Provenance, ...]
    cpr: str | None
    previous_day_high: str | None
    previous_day_low: str | None
    previous_week_high: str | None
    previous_week_low: str | None

    def __post_init__(self) -> None:
        facts = (
            self.cpr,
            self.previous_day_high,
            self.previous_day_low,
            self.previous_week_high,
            self.previous_week_low,
        )
        if (
            type(self.availability) is not EvidenceAvailability
            or type(self.provenance) is not tuple
            or (
                self.availability is EvidenceAvailability.AVAILABLE
                and (not self.provenance or all(item is None for item in facts))
            )
            or (
                self.availability is not EvidenceAvailability.AVAILABLE
                and any(item is not None for item in facts)
            )
        ):
            raise ValueError("TRADINGVIEW_REFERENCE_LEVEL_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class ChartIndicatorExpectation:
    indicator: TradingViewIndicator
    semantic_label: str
    source: str
    cosmetic_colour: str | None
    required_evidence: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            type(self.indicator) is not TradingViewIndicator
            or self.semantic_label != self.indicator.value
            or self.source != "TRADINGVIEW"
            or not self.required_evidence
            or len(set(self.required_evidence)) != len(self.required_evidence)
        ):
            raise ValueError("TRADINGVIEW_INDICATOR_EXPECTATION_INVALID")


@dataclass(frozen=True, slots=True)
class TradingViewChartTemplate:
    template_identity: str
    version: int
    indicators: tuple[ChartIndicatorExpectation, ...]
    colour_is_semantic_identity: bool = False

    def __post_init__(self) -> None:
        if (
            self.template_identity != TRADINGVIEW_CHART_TEMPLATE_ID
            or self.version != 1
            or tuple(item.indicator for item in self.indicators)
            != tuple(TradingViewIndicator)
            or self.colour_is_semantic_identity
        ):
            raise ValueError("TRADINGVIEW_CHART_TEMPLATE_INVALID")


DEFAULT_TRADINGVIEW_CHART_TEMPLATE = TradingViewChartTemplate(
    template_identity=TRADINGVIEW_CHART_TEMPLATE_ID,
    version=1,
    indicators=tuple(
        ChartIndicatorExpectation(
            indicator=indicator,
            semantic_label=indicator.value,
            source="TRADINGVIEW",
            cosmetic_colour={
                TradingViewIndicator.SMA20: None,
                TradingViewIndicator.SMA50: "RED",
                TradingViewIndicator.SMA200: "WHITE",
            }[indicator],
            required_evidence=(
                "VISIBLE_OR_UNAVAILABLE",
                "DIRECTION_OR_SLOPE",
                "PRICE_RELATIONSHIP",
                "SUPPORT_RESISTANCE_INTERACTION",
                "CRISSCROSS_BEHAVIOUR",
            ),
        )
        for indicator in TradingViewIndicator
    ),
)


@dataclass(frozen=True, slots=True)
class TradingViewContextPolicy:
    """Daily is invariant; supporting timeframes are explicitly configured."""

    supporting_timeframes: tuple[ChartTimeframe, ...] = ()

    def __post_init__(self) -> None:
        if (
            type(self.supporting_timeframes) is not tuple
            or ChartTimeframe.DAILY in self.supporting_timeframes
            or len(set(self.supporting_timeframes)) != len(self.supporting_timeframes)
            or any(
                timeframe not in {ChartTimeframe.FOUR_HOUR, ChartTimeframe.ONE_HOUR}
                for timeframe in self.supporting_timeframes
            )
        ):
            raise ValueError("TRADINGVIEW_CONTEXT_POLICY_INVALID")

    @property
    def required_timeframes(self) -> tuple[ChartTimeframe, ...]:
        return (ChartTimeframe.DAILY, *self.supporting_timeframes)


@dataclass(frozen=True, slots=True)
class ProbableSetupLink:
    assessment_identity: str
    setup: V1Setup
    direction: V1Direction

    def __post_init__(self) -> None:
        if (
            not self.assessment_identity
            or type(self.setup) is not V1Setup
            or self.direction not in {V1Direction.LONG, V1Direction.SHORT}
        ):
            raise ValueError("TRADINGVIEW_PROBABLE_SETUP_LINK_INVALID")


@dataclass(frozen=True, slots=True)
class TradingViewReviewRequirement:
    run_identity: str
    canonical_instrument: str
    observation_boundary: datetime
    probable_setups: tuple[ProbableSetupLink, ...]
    required_timeframes: tuple[ChartTimeframe, ...]
    chart_template_identity: str
    context_status: TradingViewReviewStatus
    swing_analysis_run_identity: str = LEGACY_UNBOUND_SWING_RUN_ID

    def __post_init__(self) -> None:
        if (
            not self.run_identity
            or not is_swing_run_binding(self.swing_analysis_run_identity)
            or not self.canonical_instrument
            or self.observation_boundary.tzinfo is None
            or self.observation_boundary.utcoffset() is None
            or not self.probable_setups
            or len(set(item.assessment_identity for item in self.probable_setups))
            != len(self.probable_setups)
            or not self.required_timeframes
            or self.required_timeframes[0] is not ChartTimeframe.DAILY
            or len(set(self.required_timeframes)) != len(self.required_timeframes)
            or self.chart_template_identity != TRADINGVIEW_CHART_TEMPLATE_ID
            or type(self.context_status) is not TradingViewReviewStatus
        ):
            raise ValueError("TRADINGVIEW_REVIEW_REQUIREMENT_INVALID")


def build_tradingview_review_requirements(
    run: V1Layer1Run,
    *,
    context_policy: TradingViewContextPolicy = TradingViewContextPolicy(),
    swing_analysis_run_identity: str = LEGACY_UNBOUND_SWING_RUN_ID,
) -> tuple[TradingViewReviewRequirement, ...]:
    """Collapse all probable setup assessments to one requirement per instrument."""

    if (
        type(run) is not V1Layer1Run
        or type(context_policy) is not TradingViewContextPolicy
        or not is_swing_run_binding(swing_analysis_run_identity)
    ):
        raise ValueError("TRADINGVIEW_REVIEW_REQUEST_INVALID")
    requirements: list[TradingViewReviewRequirement] = []
    for instrument in run.instruments:
        probable = tuple(
            assessment
            for assessment in instrument.assessments
            if assessment.classification is ProbableClassification.PROBABLE_CANDIDATE
        )
        if not probable:
            continue
        requirements.append(
            TradingViewReviewRequirement(
                run_identity=run.run_identity,
                canonical_instrument=instrument.canonical_identity,
                observation_boundary=run.observation_boundary,
                probable_setups=tuple(_setup_link(item) for item in probable),
                required_timeframes=context_policy.required_timeframes,
                chart_template_identity=TRADINGVIEW_CHART_TEMPLATE_ID,
                context_status=TradingViewReviewStatus.TRADINGVIEW_REVIEW_REQUIRED,
                swing_analysis_run_identity=swing_analysis_run_identity,
            )
        )
    return tuple(requirements)


def _setup_link(assessment: V1Layer1Assessment) -> ProbableSetupLink:
    return ProbableSetupLink(
        assessment_identity="|".join((
            assessment.canonical_identity,
            assessment.setup.value,
            assessment.direction.value,
            assessment.observation_boundary.isoformat(),
        )),
        setup=assessment.setup,
        direction=assessment.direction,
    )


@dataclass(frozen=True, slots=True)
class Layer2CategoryEvidence:
    availability: EvidenceAvailability
    provenance: tuple[Layer2Provenance, ...]
    observations: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            type(self.availability) is not EvidenceAvailability
            or type(self.provenance) is not tuple
            or type(self.observations) is not tuple
            or len(set(self.provenance)) != len(self.provenance)
            or len(set(self.observations)) != len(self.observations)
            or (
                self.availability is EvidenceAvailability.AVAILABLE
                and not self.provenance
            )
        ):
            raise ValueError("TRADINGVIEW_LAYER2_CATEGORY_INVALID")


@dataclass(frozen=True, slots=True)
class MovingAverageVisualEvidence:
    indicator: TradingViewIndicator
    timeframe: ChartTimeframe
    availability: EvidenceAvailability
    provenance: tuple[Layer2Provenance, ...]
    direction_or_slope: str | None
    price_relationship: str | None
    support_resistance_interaction: str | None
    crisscross_behaviour: str | None

    def __post_init__(self) -> None:
        facts = (
            self.direction_or_slope,
            self.price_relationship,
            self.support_resistance_interaction,
            self.crisscross_behaviour,
        )
        if (
            type(self.indicator) is not TradingViewIndicator
            or type(self.timeframe) is not ChartTimeframe
            or type(self.availability) is not EvidenceAvailability
            or type(self.provenance) is not tuple
            or (
                self.availability is EvidenceAvailability.AVAILABLE
                and (not self.provenance or all(value is None for value in facts))
            )
            or (
                self.availability is not EvidenceAvailability.AVAILABLE
                and any(value is not None for value in facts)
            )
        ):
            raise ValueError("TRADINGVIEW_MOVING_AVERAGE_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class TradingViewLayer2Evidence:
    """Structured evidence independent of screenshots; no aggregate score."""

    run_identity: str
    canonical_instrument: str
    observation_boundary: datetime
    template_identity: str
    price_structure: PriceStructureVisualEvidence
    moving_averages: tuple[MovingAverageVisualEvidence, ...]
    reference_levels: ReferenceLevelVisualEvidence
    structural_support_resistance: Layer2CategoryEvidence
    candle_behaviour: Layer2CategoryEvidence
    pine_display: Layer2CategoryEvidence
    contradictions: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not self.run_identity
            or not self.canonical_instrument
            or self.observation_boundary.tzinfo is None
            or self.observation_boundary.utcoffset() is None
            or self.template_identity != TRADINGVIEW_CHART_TEMPLATE_ID
            or type(self.price_structure) is not PriceStructureVisualEvidence
            or type(self.reference_levels) is not ReferenceLevelVisualEvidence
            or any(
                type(value) is not Layer2CategoryEvidence
                for value in (
                    self.structural_support_resistance,
                    self.candle_behaviour,
                    self.pine_display,
                )
            )
            or type(self.moving_averages) is not tuple
            or any(type(value) is not MovingAverageVisualEvidence for value in self.moving_averages)
            or type(self.contradictions) is not tuple
            or len(set(self.contradictions)) != len(self.contradictions)
        ):
            raise ValueError("TRADINGVIEW_LAYER2_EVIDENCE_INVALID")


def pending_layer2_evidence(
    requirement: TradingViewReviewRequirement,
) -> TradingViewLayer2Evidence:
    def unavailable() -> Layer2CategoryEvidence:
        return Layer2CategoryEvidence(EvidenceAvailability.UNAVAILABLE, (), ())

    return TradingViewLayer2Evidence(
        run_identity=requirement.run_identity,
        canonical_instrument=requirement.canonical_instrument,
        observation_boundary=requirement.observation_boundary,
        template_identity=requirement.chart_template_identity,
        price_structure=PriceStructureVisualEvidence(
            EvidenceAvailability.UNAVAILABLE,
            (),
            None,
        ),
        moving_averages=tuple(
            MovingAverageVisualEvidence(
                indicator,
                timeframe,
                EvidenceAvailability.UNAVAILABLE,
                (),
                None,
                None,
                None,
                None,
            )
            for timeframe in requirement.required_timeframes
            for indicator in TradingViewIndicator
        ),
        reference_levels=ReferenceLevelVisualEvidence(
            EvidenceAvailability.UNAVAILABLE,
            (),
            None,
            None,
            None,
            None,
            None,
        ),
        structural_support_resistance=unavailable(),
        candle_behaviour=unavailable(),
        pine_display=unavailable(),
        contradictions=(),
    )


def missing_timeframes(
    requirement: TradingViewReviewRequirement,
    received: Iterable[ChartTimeframe],
) -> tuple[ChartTimeframe, ...]:
    received_set = set(received)
    return tuple(item for item in requirement.required_timeframes if item not in received_set)


__all__ = [
    "ChartTimeframe",
    "DATA_ALIGNMENT_REVIEW",
    "DEFAULT_TRADINGVIEW_CHART_TEMPLATE",
    "Layer2CategoryEvidence",
    "Layer2Provenance",
    "Layer2StructureState",
    "MovingAverageVisualEvidence",
    "PriceStructureVisualEvidence",
    "ProbableSetupLink",
    "TRADINGVIEW_CHART_TEMPLATE_ID",
    "TRADINGVIEW_RETENTION_CLASS",
    "TRADINGVIEW_UPLOAD_SOURCE",
    "ReferenceLevelVisualEvidence",
    "TradingViewChartTemplate",
    "TradingViewContextPolicy",
    "TradingViewIndicator",
    "TradingViewLayer2Evidence",
    "TradingViewReviewRequirement",
    "TradingViewReviewStatus",
    "build_tradingview_review_requirements",
    "missing_timeframes",
    "pending_layer2_evidence",
]
