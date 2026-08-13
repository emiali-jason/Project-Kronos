"""Immutable provider-neutral contracts for Swing V1 Layer-1 evidence."""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime
from enum import StrEnum
import math

from kronos.swing.universe import SwingUniverseAssetClass
from kronos.swing.v1.policies import (
    SWING_V1_LAYER1_POLICY_BUNDLE_ID,
    SWING_V1_LAYER1_POLICY_IDS,
)


class EvidenceAvailability(StrEnum):
    """Availability of one evidence dimension without fabricated continuity."""

    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class V1Setup(StrEnum):
    """The two approved Swing V1 setup families."""

    PULLBACK_CONTINUATION = "PULLBACK_CONTINUATION"
    CONSOLIDATION_BREAKOUT = "CONSOLIDATION_BREAKOUT"


class V1Direction(StrEnum):
    """Direction of a V1 setup hypothesis."""

    LONG = "LONG"
    SHORT = "SHORT"
    NONE = "NONE"


class PivotKind(StrEnum):
    """Kind of deterministic structural pivot candidate."""

    HIGH = "HIGH"
    LOW = "LOW"


class StructuralState(StrEnum):
    """Descriptive structural state produced by one pivot alternative."""

    BULLISH_HH_HL = "BULLISH_HH_HL"
    BEARISH_LH_LL = "BEARISH_LH_LL"
    MIXED_UNCLEAR = "MIXED_UNCLEAR"
    EVIDENCE_INCOMPLETE = "EVIDENCE_INCOMPLETE"


class ProbableClassification(StrEnum):
    """Non-production outcome of V1 probable formation."""

    PROBABLE_CANDIDATE = "PROBABLE_CANDIDATE"
    EVIDENCE_INCOMPLETE = "EVIDENCE_INCOMPLETE"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    POLICY_UNRESOLVED = "POLICY_UNRESOLVED"


class ReconciliationState(StrEnum):
    """Layer-1 reconciliation state; context itself remains outside this slice."""

    READY_FOR_CONTEXT = "READY_FOR_CONTEXT"
    POLICY_UNRESOLVED = "POLICY_UNRESOLVED"
    EVIDENCE_INCOMPLETE = "EVIDENCE_INCOMPLETE"
    FAILED = "FAILED"


class TradingViewContextGateState(StrEnum):
    """Future context-gate state; no TradingView evidence is ingested here."""

    TRADINGVIEW_CONTEXT_PENDING = "TRADINGVIEW_CONTEXT_PENDING"
    NOT_ELIGIBLE_UNLESS_PROBABLE = "NOT_ELIGIBLE_UNLESS_PROBABLE"


@dataclass(frozen=True, slots=True)
class PivotCandidate:
    """One deterministic pivot candidate retained with its source coordinates."""

    kind: PivotKind
    candle_index: int
    timestamp: datetime
    value: float

    def __post_init__(self) -> None:
        if (
            type(self.kind) is not PivotKind
            or type(self.candle_index) is not int
            or self.candle_index < 0
            or not _aware(self.timestamp)
            or not _finite(self.value)
        ):
            raise ValueError("V1_PIVOT_CANDIDATE_INVALID")


@dataclass(frozen=True, slots=True)
class StructuralAlternative:
    """One retained deterministic pivot definition, never silently preferred."""

    definition_id: str
    radius: int
    availability: EvidenceAvailability
    state: StructuralState
    swing_highs: tuple[PivotCandidate, ...]
    swing_lows: tuple[PivotCandidate, ...]

    def __post_init__(self) -> None:
        incomplete = self.state is StructuralState.EVIDENCE_INCOMPLETE
        if (
            type(self.definition_id) is not str
            or not self.definition_id
            or type(self.radius) is not int
            or self.radius < 1
            or type(self.availability) is not EvidenceAvailability
            or type(self.state) is not StructuralState
            or type(self.swing_highs) is not tuple
            or type(self.swing_lows) is not tuple
            or any(item.kind is not PivotKind.HIGH for item in self.swing_highs)
            or any(item.kind is not PivotKind.LOW for item in self.swing_lows)
            or incomplete
            != (self.availability is EvidenceAvailability.UNAVAILABLE)
        ):
            raise ValueError("V1_STRUCTURAL_ALTERNATIVE_INVALID")


@dataclass(frozen=True, slots=True)
class StructuralEvidence:
    """All approved structural alternatives plus their agreement state."""

    availability: EvidenceAvailability
    alternatives: tuple[StructuralAlternative, ...]
    consensus: StructuralState | None
    alternatives_complete: bool
    alternatives_agree: bool
    alternatives_disagree: bool

    def __post_init__(self) -> None:
        complete = tuple(
            item
            for item in self.alternatives
            if item.availability is EvidenceAvailability.AVAILABLE
        )
        expected_availability = (
            EvidenceAvailability.AVAILABLE
            if complete
            else EvidenceAvailability.UNAVAILABLE
        )
        expected_consensus = (
            complete[0].state
            if len(complete) == 2 and complete[0].state is complete[1].state
            else None
        )
        expected_complete = len(complete) == 2
        expected_agreement = (
            expected_complete and complete[0].state is complete[1].state
        )
        expected_disagreement = (
            expected_complete and complete[0].state is not complete[1].state
        )
        if (
            type(self.availability) is not EvidenceAvailability
            or self.availability is EvidenceAvailability.NOT_APPLICABLE
            or type(self.alternatives) is not tuple
            or len(self.alternatives) != 2
            or any(type(item) is not StructuralAlternative for item in self.alternatives)
            or tuple(item.radius for item in self.alternatives) != (1, 2)
            or any(
                item.definition_id
                != f"FRACTAL_UNIQUE_EXTREME_RADIUS_{item.radius}"
                for item in self.alternatives
            )
            or (
                self.consensus is not None
                and type(self.consensus) is not StructuralState
            )
            or self.consensus is StructuralState.EVIDENCE_INCOMPLETE
            or type(self.alternatives_complete) is not bool
            or type(self.alternatives_agree) is not bool
            or type(self.alternatives_disagree) is not bool
            or self.availability is not expected_availability
            or self.consensus is not expected_consensus
            or self.alternatives_complete is not expected_complete
            or self.alternatives_agree is not expected_agreement
            or self.alternatives_disagree is not expected_disagreement
        ):
            raise ValueError("V1_STRUCTURAL_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class MovingAverageEvidence:
    """Trend-quality facts; longer-history gaps remain explicit."""

    sma20_availability: EvidenceAvailability
    sma50_availability: EvidenceAvailability
    sma200_availability: EvidenceAvailability
    completed_history_count: int
    sma20_required_candles: int
    sma50_required_candles: int
    sma200_required_candles: int
    sma20: float | None
    sma50: float | None
    sma200: float | None
    sma20_direction: str | None
    sma50_direction: str | None
    price_vs_sma20: str | None
    price_vs_sma50: str | None
    crisscross20_count: int | None
    persistent_separation20: bool | None
    interaction_labels: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            any(
                type(item) is not EvidenceAvailability
                for item in (
                    self.sma20_availability,
                    self.sma50_availability,
                    self.sma200_availability,
                )
            )
            or EvidenceAvailability.NOT_APPLICABLE
            in {
                self.sma20_availability,
                self.sma50_availability,
                self.sma200_availability,
            }
            or type(self.completed_history_count) is not int
            or self.completed_history_count < 0
            or self.sma20_required_candles != 25
            or self.sma50_required_candles != 55
            or self.sma200_required_candles != 200
            or not _ma_component_valid(
                self.sma20_availability,
                self.sma20,
                self.completed_history_count,
                self.sma20_required_candles,
            )
            or not _ma_component_valid(
                self.sma50_availability,
                self.sma50,
                self.completed_history_count,
                self.sma50_required_candles,
            )
            or not _ma_component_valid(
                self.sma200_availability,
                self.sma200,
                self.completed_history_count,
                self.sma200_required_candles,
            )
            or (
                self.sma20_availability is EvidenceAvailability.AVAILABLE
                and self.sma20_direction is None
            )
            or (
                self.sma50_availability is EvidenceAvailability.AVAILABLE
                and self.sma50_direction is None
            )
            or any(
                type(item) is float and not math.isfinite(item)
                for item in (
                    self.sma20,
                    self.sma50,
                    self.sma200,
                )
            )
            or type(self.interaction_labels) is not tuple
        ):
            raise ValueError("V1_MOVING_AVERAGE_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class VolumeEvidence:
    """Setup-aware descriptive volume measurements with no threshold authority."""

    availability: EvidenceAvailability
    current_volume: int | None
    normal_mean_volume: float | None
    normal_median_volume: float | None
    comparison_mean_volume: float | None
    comparison_role: str | None
    relative_mean: float | None
    relative_median: float | None
    percentile20: float | None
    breakout_vs_consolidation_mean: float | None
    resumption_vs_pullback_mean: float | None
    pullback_vs_prior_impulse_mean: float | None
    measurement_only: bool
    policy_interpretation: str
    reason: str | None

    def __post_init__(self) -> None:
        if (
            not _valid_evidence_dataclass(self)
            or (
                self.current_volume is not None
                and (type(self.current_volume) is not int or self.current_volume < 0)
            )
            or self.comparison_role
            not in {None, "PULLBACK_MEAN", "CONSOLIDATION_MEAN"}
            or self.measurement_only is not True
            or self.policy_interpretation != "POLICY_UNRESOLVED_NO_THRESHOLD"
        ):
            raise ValueError("V1_VOLUME_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class CandleEvidence:
    """Completed-candle morphology and deterministic contextual labels."""

    availability: EvidenceAvailability
    range: float | None
    body: float | None
    body_ratio: float | None
    upper_shadow_ratio: float | None
    lower_shadow_ratio: float | None
    close_location: float | None
    range_atr_ratio: float | None
    interpretations: tuple[str, ...]
    named_patterns_create_trades: bool
    reason: str | None

    def __post_init__(self) -> None:
        if not _valid_evidence_dataclass(self) or self.named_patterns_create_trades:
            raise ValueError("V1_CANDLE_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class VolatilityEvidence:
    """Descriptive contraction and expansion measurements."""

    availability: EvidenceAvailability
    range_atr_ratio: float | None
    nr4: bool | None
    nr7: bool | None
    inside_day: bool | None
    range_percentile20: float | None
    short_vs_long: float | None
    prebreak_short_vs_long: float | None
    breakout_vs_prebreak: float | None
    close_vs_preceding_range: str | None
    measurement_only: bool
    setup_role: str
    directional_authority: bool
    reason: str | None

    def __post_init__(self) -> None:
        if (
            not _valid_evidence_dataclass(self)
            or self.measurement_only is not True
            or self.setup_role
            not in {"SUPPORTING_EVIDENCE", "SETUP_QUALITY_EVIDENCE"}
            or self.directional_authority is not False
        ):
            raise ValueError("V1_VOLATILITY_EVIDENCE_INVALID")


class FuturesPositioningInterpretation(StrEnum):
    """Approved price/OI vocabulary without trader-identity claims."""

    LONG_BUILDUP = "LONG_BUILDUP"
    SHORT_BUILDUP = "SHORT_BUILDUP"
    SHORT_COVERING = "SHORT_COVERING"
    LONG_UNWINDING = "LONG_UNWINDING"


@dataclass(frozen=True, slots=True)
class FuturesPositioningEvidence:
    """Futures OI evidence with explicit roll-normalization availability."""

    availability: EvidenceAvailability
    price_change: float | None
    open_interest_change: int | None
    interpretation: FuturesPositioningInterpretation | None
    multi_session_persistence: int | None
    roll_normalized: bool | None
    future_dependency: str
    reason: str | None

    def __post_init__(self) -> None:
        if (
            not _valid_evidence_dataclass(self)
            or (
                self.interpretation is not None
                and type(self.interpretation)
                is not FuturesPositioningInterpretation
            )
            or self.future_dependency
            != "CONTRACT_IDENTITY_EXPIRY_ROLL_ADJUSTED_OI_SERIES"
        ):
            raise ValueError("V1_FUTURES_POSITIONING_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class ImpulseCandidateEvidence:
    """One retained deterministic impulse candidate and its exact identity."""

    candidate_identity: str
    candle_index: int
    timestamp: datetime
    direction: V1Direction
    range_atr: float
    body_quality: float
    close_quality: float
    volume: int

    def __post_init__(self) -> None:
        if (
            type(self.candidate_identity) is not str
            or not self.candidate_identity
            or type(self.candle_index) is not int
            or self.candle_index < 0
            or not _aware(self.timestamp)
            or type(self.direction) is not V1Direction
            or self.direction is V1Direction.NONE
            or not _finite(self.range_atr)
            or self.range_atr <= 0.0
            or not _finite(self.body_quality)
            or not 0.0 <= self.body_quality <= 1.0
            or not _finite(self.close_quality)
            or not 0.0 <= self.close_quality <= 1.0
            or type(self.volume) is not int
            or self.volume < 0
        ):
            raise ValueError("V1_IMPULSE_CANDIDATE_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class ImpulseMaturityEvidence:
    """Pullback maturity measurements with unresolved sequence policy retained."""

    availability: EvidenceAvailability
    candidates: tuple[ImpulseCandidateEvidence, ...]
    selected_candidate_identity: str | None
    tied_candidate_identities: tuple[str, ...]
    selection_policy: str
    tie_policy_review: bool
    impulse_candle_index: int | None
    impulse_direction: V1Direction | None
    impulse_range_atr: float | None
    impulse_body_quality: float | None
    impulse_close_quality: float | None
    impulse_volume: int | None
    bars_since_impulse: int | None
    trend_leg_age: int | None
    pullback_depth_fraction: float | None
    fraction_of_impulse_retained: float | None
    pullback_bar_count: int | None
    pullback_sequence_number: int | None
    prior_pullbacks_in_leg: int | None
    unresolved_fields: tuple[str, ...]
    measurement_only: bool
    reason: str | None

    def __post_init__(self) -> None:
        selected = tuple(
            item
            for item in self.candidates
            if item.candidate_identity == self.selected_candidate_identity
        )
        max_strength = (
            max(item.range_atr for item in self.candidates)
            if self.candidates
            else None
        )
        expected_tied = tuple(
            item.candidate_identity
            for item in self.candidates
            if item.range_atr == max_strength
        )
        if (
            not _valid_evidence_dataclass(self)
            or type(self.candidates) is not tuple
            or any(type(item) is not ImpulseCandidateEvidence for item in self.candidates)
            or type(self.tied_candidate_identities) is not tuple
            or any(not item for item in self.tied_candidate_identities)
            or self.tied_candidate_identities != expected_tied
            or self.selection_policy != "MAX_RANGE_ATR_THEN_EARLIEST_INDEX"
            or type(self.tie_policy_review) is not bool
            or (
                self.availability is EvidenceAvailability.AVAILABLE
                and (
                    len(selected) != 1
                    or not self.candidates
                    or selected[0].candle_index
                    != min(
                        item.candle_index
                        for item in self.candidates
                        if item.candidate_identity
                        in self.tied_candidate_identities
                    )
                    or self.impulse_candle_index != selected[0].candle_index
                    or self.impulse_direction is not selected[0].direction
                    or self.impulse_range_atr != selected[0].range_atr
                    or self.impulse_body_quality != selected[0].body_quality
                    or self.impulse_close_quality != selected[0].close_quality
                    or self.impulse_volume != selected[0].volume
                )
            )
            or (
                self.availability is not EvidenceAvailability.AVAILABLE
                and (self.selected_candidate_identity is not None or self.candidates)
            )
            or self.tie_policy_review
            != (
                len(self.tied_candidate_identities) > 1
                and len(
                    {
                        item.direction
                        for item in self.candidates
                        if item.candidate_identity in self.tied_candidate_identities
                    }
                )
                > 1
            )
        ):
            raise ValueError("V1_IMPULSE_MATURITY_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class RelativeContextEvidence:
    """Matched benchmark context with no automatic market veto."""

    availability: EvidenceAvailability
    benchmark: str | None
    aligned_sessions: int | None
    instrument_return: float | None
    benchmark_return: float | None
    return_difference: float | None
    interpretation: str | None
    automatic_market_veto: bool
    reason: str | None

    def __post_init__(self) -> None:
        if not _valid_evidence_dataclass(self) or self.automatic_market_veto:
            raise ValueError("V1_RELATIVE_CONTEXT_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class GapContextEvidence:
    """Gap and abnormal-move context without setup or veto authority."""

    availability: EvidenceAvailability
    gap_atr: float | None
    abnormal_range_atr: float | None
    distance_from_20bar_structure_atr: float | None
    acceptance: str | None
    news_event_causation: str
    standalone_setup: bool
    automatic_veto: bool
    reason: str | None

    def __post_init__(self) -> None:
        if (
            not _valid_evidence_dataclass(self)
            or self.news_event_causation != "DEFERRED"
            or self.standalone_setup
            or self.automatic_veto
        ):
            raise ValueError("V1_GAP_CONTEXT_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class V1Layer1Assessment:
    """Complete Layer-1 record for one instrument and one setup family."""

    canonical_identity: str
    asset_class: SwingUniverseAssetClass
    observation_boundary: datetime
    setup: V1Setup
    direction: V1Direction
    classification: ProbableClassification
    reconciliation: ReconciliationState
    policy_bundle: str
    policy_ids: tuple[str, ...]
    structural: StructuralEvidence
    moving_average: MovingAverageEvidence
    volume: VolumeEvidence
    candle: CandleEvidence
    volatility: VolatilityEvidence
    futures_positioning: FuturesPositioningEvidence
    impulse_maturity: ImpulseMaturityEvidence
    relative_context: RelativeContextEvidence
    gap_context: GapContextEvidence
    reasons: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    unresolved_policies: tuple[str, ...]
    context_gate: TradingViewContextGateState

    def __post_init__(self) -> None:
        if (
            type(self.canonical_identity) is not str
            or not self.canonical_identity
            or type(self.asset_class) is not SwingUniverseAssetClass
            or not _aware(self.observation_boundary)
            or type(self.setup) is not V1Setup
            or type(self.direction) is not V1Direction
            or type(self.classification) is not ProbableClassification
            or type(self.reconciliation) is not ReconciliationState
            or self.policy_bundle != SWING_V1_LAYER1_POLICY_BUNDLE_ID
            or self.policy_ids != SWING_V1_LAYER1_POLICY_IDS
            or any(
                type(getattr(self, name)) is not expected
                for name, expected in _ASSESSMENT_EVIDENCE_TYPES.items()
            )
            or any(
                type(value) is not tuple
                for value in (
                    self.reasons,
                    self.missing_evidence,
                    self.unresolved_policies,
                )
            )
            or any(
                not item
                for collection in (
                    self.reasons,
                    self.missing_evidence,
                    self.unresolved_policies,
                )
                for item in collection
            )
            or any(
                len(set(collection)) != len(collection)
                for collection in (
                    self.reasons,
                    self.missing_evidence,
                    self.unresolved_policies,
                )
            )
            or type(self.context_gate) is not TradingViewContextGateState
            or (
                self.classification is ProbableClassification.PROBABLE_CANDIDATE
                and (
                    self.reconciliation is not ReconciliationState.READY_FOR_CONTEXT
                    or self.context_gate
                    is not TradingViewContextGateState.TRADINGVIEW_CONTEXT_PENDING
                )
            )
            or (
                self.classification is not ProbableClassification.PROBABLE_CANDIDATE
                and self.context_gate
                is not TradingViewContextGateState.NOT_ELIGIBLE_UNLESS_PROBABLE
            )
            or self.reconciliation is not _expected_reconciliation(
                self.classification
            )
        ):
            raise ValueError("V1_LAYER1_ASSESSMENT_INVALID")


_ASSESSMENT_EVIDENCE_TYPES = {
    "structural": StructuralEvidence,
    "moving_average": MovingAverageEvidence,
    "volume": VolumeEvidence,
    "candle": CandleEvidence,
    "volatility": VolatilityEvidence,
    "futures_positioning": FuturesPositioningEvidence,
    "impulse_maturity": ImpulseMaturityEvidence,
    "relative_context": RelativeContextEvidence,
    "gap_context": GapContextEvidence,
}


@dataclass(frozen=True, slots=True)
class V1InstrumentLayer1Evidence:
    """Exactly two complete setup records for one canonical universe member."""

    canonical_identity: str
    asset_class: SwingUniverseAssetClass
    assessments: tuple[V1Layer1Assessment, ...]

    def __post_init__(self) -> None:
        if (
            type(self.canonical_identity) is not str
            or not self.canonical_identity
            or type(self.asset_class) is not SwingUniverseAssetClass
            or type(self.assessments) is not tuple
            or any(type(item) is not V1Layer1Assessment for item in self.assessments)
            or tuple(item.setup for item in self.assessments)
            != (
                V1Setup.PULLBACK_CONTINUATION,
                V1Setup.CONSOLIDATION_BREAKOUT,
            )
            or any(
                item.canonical_identity != self.canonical_identity
                or item.asset_class is not self.asset_class
                for item in self.assessments
            )
        ):
            raise ValueError("V1_INSTRUMENT_LAYER1_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class V1Layer1Run:
    """Complete deterministic Layer-1 output for the approved 98-member universe."""

    run_identity: str
    observation_boundary: datetime
    policy_bundle: str
    policy_ids: tuple[str, ...]
    instruments: tuple[V1InstrumentLayer1Evidence, ...]

    def __post_init__(self) -> None:
        identities = tuple(item.canonical_identity for item in self.instruments)
        if (
            self.run_identity
            != f"{SWING_V1_LAYER1_POLICY_BUNDLE_ID}@{self.observation_boundary.isoformat()}"
            or not _aware(self.observation_boundary)
            or self.policy_bundle != SWING_V1_LAYER1_POLICY_BUNDLE_ID
            or self.policy_ids != SWING_V1_LAYER1_POLICY_IDS
            or type(self.instruments) is not tuple
            or len(self.instruments) != 98
            or len(set(identities)) != 98
            or any(type(item) is not V1InstrumentLayer1Evidence for item in self.instruments)
            or any(
                assessment.observation_boundary != self.observation_boundary
                or assessment.policy_bundle != self.policy_bundle
                or assessment.policy_ids != self.policy_ids
                for item in self.instruments
                for assessment in item.assessments
            )
        ):
            raise ValueError("V1_LAYER1_RUN_INVALID")

    @property
    def assessment_count(self) -> int:
        return sum(len(item.assessments) for item in self.instruments)

    @property
    def probable_count(self) -> int:
        return sum(
            assessment.classification
            is ProbableClassification.PROBABLE_CANDIDATE
            for item in self.instruments
            for assessment in item.assessments
        )

    @property
    def unresolved_count(self) -> int:
        return sum(
            assessment.classification
            in {
                ProbableClassification.POLICY_UNRESOLVED,
                ProbableClassification.EVIDENCE_INCOMPLETE,
            }
            for item in self.instruments
            for assessment in item.assessments
        )


def _valid_evidence_dataclass(value: object) -> bool:
    availability = getattr(value, "availability", None)
    if type(availability) is not EvidenceAvailability:
        return False
    for field in fields(value):
        item = getattr(value, field.name)
        if type(item) is float and not math.isfinite(item):
            return False
        if field.name.endswith("_count") and item is not None:
            if type(item) is not int or item < 0:
                return False
    return True


def _ma_component_valid(
    availability: EvidenceAvailability,
    value: float | None,
    completed_history_count: int,
    required_candles: int,
) -> bool:
    if availability is EvidenceAvailability.AVAILABLE:
        return _finite(value) and completed_history_count >= required_candles
    return value is None


def _expected_reconciliation(
    classification: ProbableClassification,
) -> ReconciliationState:
    return {
        ProbableClassification.PROBABLE_CANDIDATE: (
            ReconciliationState.READY_FOR_CONTEXT
        ),
        ProbableClassification.POLICY_UNRESOLVED: (
            ReconciliationState.POLICY_UNRESOLVED
        ),
        ProbableClassification.EVIDENCE_INCOMPLETE: (
            ReconciliationState.EVIDENCE_INCOMPLETE
        ),
        ProbableClassification.NOT_SUPPORTED: ReconciliationState.FAILED,
    }[classification]


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _finite(value: object) -> bool:
    return type(value) is float and math.isfinite(value)


__all__ = [
    "CandleEvidence",
    "EvidenceAvailability",
    "FuturesPositioningEvidence",
    "FuturesPositioningInterpretation",
    "GapContextEvidence",
    "ImpulseMaturityEvidence",
    "ImpulseCandidateEvidence",
    "MovingAverageEvidence",
    "PivotCandidate",
    "PivotKind",
    "ProbableClassification",
    "ReconciliationState",
    "RelativeContextEvidence",
    "StructuralAlternative",
    "StructuralEvidence",
    "StructuralState",
    "TradingViewContextGateState",
    "V1Direction",
    "V1InstrumentLayer1Evidence",
    "V1Layer1Assessment",
    "V1Layer1Run",
    "V1Setup",
    "VolatilityEvidence",
    "VolumeEvidence",
]
