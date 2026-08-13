"""Deterministic Sponsor-reviewed TradingView consumption and V1 Readiness."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import math
import re

from kronos.swing.v1.models import (
    EvidenceAvailability,
    StructuralState,
    V1Direction,
    V1Layer1Assessment,
)
from kronos.swing.v1.policies import (
    SWING_V1_CLEAR_AIR_POLICY_ID,
    SWING_V1_OPTIONS_BARRIER_POLICY_ID,
    SWING_V1_PRICE_BARRIER_POLICY_ID,
    SWING_V1_READINESS_ASSESSMENT_POLICY_ID,
    SWING_V1_TRADINGVIEW_CONTEXT_POLICY_ID,
)
from kronos.swing.v1.tradingview import (
    ChartTimeframe,
    DATA_ALIGNMENT_REVIEW,
    TRADINGVIEW_CHART_TEMPLATE_ID,
    TradingViewReviewRequirement,
)


class ExtractionState(StrEnum):
    CONSUMED = "CONSUMED"
    CONTEXT_INCOMPLETE = "CONTEXT_INCOMPLETE"


class ExtractionProvenance(StrEnum):
    SPONSOR_REVIEWED_MANUAL = "SPONSOR_REVIEWED_MANUAL"
    AI_CHART_ANALYST = "AI_CHART_ANALYST"


class ObservationCategory(StrEnum):
    PRICE_STRUCTURE = "PRICE_STRUCTURE"
    SMA20 = "SMA20"
    SMA50 = "SMA50"
    SMA200 = "SMA200"
    CANDLE_BEHAVIOUR = "CANDLE_BEHAVIOUR"
    VOLUME_CONTEXT = "VOLUME_CONTEXT"
    REFERENCE_LEVELS = "REFERENCE_LEVELS"
    STRUCTURAL_LEVELS = "STRUCTURAL_LEVELS"
    PRICE_DEVELOPMENT = "PRICE_DEVELOPMENT"
    PINE = "PINE"


class EvidenceReconciliationState(StrEnum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    MIXED = "MIXED"
    UNAVAILABLE = "UNAVAILABLE"


class BarrierDirectionalRelevance(StrEnum):
    ADVERSE_PATH = "ADVERSE_PATH"
    PROTECTIVE_CONTEXT = "PROTECTIVE_CONTEXT"
    MIXED_OR_UNCLEAR = "MIXED_OR_UNCLEAR"


class BarrierSignificance(StrEnum):
    MAJOR = "MAJOR"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


class OptionsOIBarrierAvailability(StrEnum):
    UNAVAILABLE = "UNAVAILABLE"
    AVAILABLE = "AVAILABLE"


class ClearAirState(StrEnum):
    CLEAR = "CLEAR"
    PARTIALLY_OBSTRUCTED = "PARTIALLY_OBSTRUCTED"
    MAJOR_BARRIER_PRESENT = "MAJOR_BARRIER_PRESENT"
    UNKNOWN = "UNKNOWN"


class ReadinessState(StrEnum):
    READY_FOR_TRADE_CONSTRUCTION = "READY_FOR_TRADE_CONSTRUCTION"
    WAIT_PULLBACK_DEVELOPING = "WAIT_PULLBACK_DEVELOPING"
    WAIT_RETEST_DEVELOPING = "WAIT_RETEST_DEVELOPING"
    EXTENDED_DO_NOT_CHASE = "EXTENDED_DO_NOT_CHASE"
    WEAKENING = "WEAKENING"
    INVALIDATED = "INVALIDATED"
    CONTEXT_INCOMPLETE = "CONTEXT_INCOMPLETE"


_REQUIRED_CATEGORIES = tuple(ObservationCategory)
_STRUCTURE_VALUES = {"HH_HL", "LH_LL", "MIXED_UNCLEAR"}
_MA_SLOPES = {"RISING", "FALLING", "FLAT", "UNCLEAR"}
_MA_RELATIONSHIPS = {"ABOVE", "BELOW", "INTERACTING", "UNCLEAR"}
_MA_INTERACTIONS = {"SUPPORT", "REJECTION", "RESPECT", "NONE", "UNCLEAR"}
_MA_CRISSCROSS = {"REPEATED", "CLEAN_SEPARATION", "LIMITED", "UNCLEAR"}
_CANDLE_VALUES = {
    "ACCEPTANCE",
    "REJECTION",
    "INDECISION",
    "CLOSE_BACK_INSIDE_RANGE",
    "ACCEPTED_OUTSIDE_STRUCTURE",
    "RETEST_DEVELOPING",
    "RETEST_HELD",
    "WEAK_FOLLOW_THROUGH",
    "FAILED_BREAK",
}
_VOLUME_VALUES = {
    "RESUMPTION_PARTICIPATION_SIZEABLE",
    "COUNTERTREND_PARTICIPATION_QUIETER",
    "BREAK_PARTICIPATION_INCREASED",
    "WEAK_PARTICIPATION",
    "QUALITATIVE_MIXED",
    "UNCLEAR",
}
_DEVELOPMENT_VALUES = {
    "ORDERLY_PULLBACK_DEVELOPING",
    "RETEST_DEVELOPING",
    "EXTENDED_FROM_STRUCTURE",
    "WEAKENING_FOLLOW_THROUGH",
    "SETUP_INVALIDATED",
    "READY_CONTEXT",
    "UNCLEAR",
}
_LEVEL_IDENTITIES = {
    "CPR",
    "PDH",
    "PDL",
    "PWH",
    "PWL",
    "VISIBLE_SUPPORT",
    "VISIBLE_RESISTANCE",
    "SWING_HIGH",
    "SWING_LOW",
    "RANGE_HIGH",
    "RANGE_LOW",
    "BREAKOUT_LOCATION",
    "BREAKDOWN_LOCATION",
    "UNAVAILABLE",
}
_LEVEL_VALUES = {
    "SUPPORT|MAJOR",
    "SUPPORT|PARTIAL",
    "RESISTANCE|MAJOR",
    "RESISTANCE|PARTIAL",
    "INTERACTING|PARTIAL",
    "VISIBLE_NOT_RELEVANT|PARTIAL",
    "UNCLEAR|UNKNOWN",
}


@dataclass(frozen=True, slots=True)
class ChartRevisionIdentity:
    timeframe: ChartTimeframe
    source_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.timeframe) is not ChartTimeframe
            or re.fullmatch(r"[0-9a-f]{64}", self.source_sha256) is None
        ):
            raise ValueError("V1_CHART_REVISION_IDENTITY_INVALID")


@dataclass(frozen=True, slots=True)
class ExtractedChartObservation:
    run_identity: str
    canonical_instrument: str
    observation_boundary: datetime
    timeframe: ChartTimeframe
    chart_template_identity: str
    source_screenshot_sha256: str
    category: ObservationCategory
    semantic_identity: str
    evidence_value: str
    availability: EvidenceAvailability
    extraction_provenance: ExtractionProvenance
    price: float | None = None
    zone_low: float | None = None
    zone_high: float | None = None
    correlation_key: str | None = None

    def __post_init__(self) -> None:
        if (
            not self.run_identity
            or not self.canonical_instrument
            or not _aware(self.observation_boundary)
            or type(self.timeframe) is not ChartTimeframe
            or self.chart_template_identity != TRADINGVIEW_CHART_TEMPLATE_ID
            or re.fullmatch(r"[0-9a-f]{64}", self.source_screenshot_sha256) is None
            or type(self.category) is not ObservationCategory
            or not re.fullmatch(r"[A-Z0-9_ -]{1,128}", self.semantic_identity)
            or type(self.availability) is not EvidenceAvailability
            or type(self.extraction_provenance) is not ExtractionProvenance
            or any(value is not None and not _finite(value) for value in (self.price, self.zone_low, self.zone_high))
            or ((self.zone_low is None) != (self.zone_high is None))
            or (
                self.zone_low is not None
                and self.zone_high is not None
                and self.zone_low > self.zone_high
            )
            or (
                self.correlation_key is not None
                and re.fullmatch(r"[A-Z0-9_.:-]{1,128}", self.correlation_key) is None
            )
            or not _observation_value_valid(self)
        ):
            raise ValueError("V1_EXTRACTED_CHART_OBSERVATION_INVALID")


@dataclass(frozen=True, slots=True)
class TradingViewStructuredEvidence:
    run_identity: str
    canonical_instrument: str
    observation_boundary: datetime
    chart_template_identity: str
    observations: tuple[ExtractedChartObservation, ...]
    source_revisions: tuple[ChartRevisionIdentity, ...]
    policy_identity: str = SWING_V1_TRADINGVIEW_CONTEXT_POLICY_ID

    def __post_init__(self) -> None:
        keys = tuple(
            (item.timeframe, item.category, item.semantic_identity)
            for item in self.observations
        )
        if (
            not self.run_identity
            or not self.canonical_instrument
            or not _aware(self.observation_boundary)
            or self.chart_template_identity != TRADINGVIEW_CHART_TEMPLATE_ID
            or type(self.observations) is not tuple
            or not self.observations
            or len(set(keys)) != len(keys)
            or type(self.source_revisions) is not tuple
            or not self.source_revisions
            or len({item.timeframe for item in self.source_revisions})
            != len(self.source_revisions)
            or self.policy_identity != SWING_V1_TRADINGVIEW_CONTEXT_POLICY_ID
            or any(
                item.run_identity != self.run_identity
                or item.canonical_instrument != self.canonical_instrument
                or item.observation_boundary != self.observation_boundary
                or item.chart_template_identity != self.chart_template_identity
                for item in self.observations
            )
        ):
            raise ValueError("V1_TRADINGVIEW_STRUCTURED_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class TradingViewExtractionResult:
    state: ExtractionState
    evidence: TradingViewStructuredEvidence | None
    missing: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            type(self.state) is not ExtractionState
            or (self.evidence is not None and type(self.evidence) is not TradingViewStructuredEvidence)
            or type(self.missing) is not tuple
            or len(set(self.missing)) != len(self.missing)
            or (self.state is ExtractionState.CONSUMED) != (self.evidence is not None)
            or (self.state is ExtractionState.CONSUMED and self.missing)
            or (self.state is ExtractionState.CONTEXT_INCOMPLETE and not self.missing)
        ):
            raise ValueError("V1_TRADINGVIEW_EXTRACTION_RESULT_INVALID")


@dataclass(frozen=True, slots=True)
class BarrierEvidence:
    correlation_key: str
    source_categories: tuple[ObservationCategory, ...]
    semantic_identities: tuple[str, ...]
    directional_relevance: BarrierDirectionalRelevance
    timeframe: ChartTimeframe
    significance: BarrierSignificance
    price: float | None
    zone_low: float | None
    zone_high: float | None
    source_hashes: tuple[str, ...]
    policy_identity: str = SWING_V1_PRICE_BARRIER_POLICY_ID

    def __post_init__(self) -> None:
        if (
            not re.fullmatch(r"[A-Z0-9_.:-]{1,128}", self.correlation_key)
            or not self.source_categories
            or len(set(self.source_categories)) != len(self.source_categories)
            or not self.semantic_identities
            or type(self.directional_relevance) is not BarrierDirectionalRelevance
            or type(self.timeframe) is not ChartTimeframe
            or type(self.significance) is not BarrierSignificance
            or any(value is not None and not _finite(value) for value in (self.price, self.zone_low, self.zone_high))
            or ((self.zone_low is None) != (self.zone_high is None))
            or not self.source_hashes
            or any(re.fullmatch(r"[0-9a-f]{64}", item) is None for item in self.source_hashes)
            or self.policy_identity != SWING_V1_PRICE_BARRIER_POLICY_ID
        ):
            raise ValueError("V1_BARRIER_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class OptionsOIBarrierEvidence:
    availability: OptionsOIBarrierAvailability
    barriers: tuple[BarrierEvidence, ...]
    reason: str | None
    policy_identity: str = SWING_V1_OPTIONS_BARRIER_POLICY_ID

    def __post_init__(self) -> None:
        if (
            type(self.availability) is not OptionsOIBarrierAvailability
            or type(self.barriers) is not tuple
            or self.policy_identity != SWING_V1_OPTIONS_BARRIER_POLICY_ID
            or (
                self.availability is OptionsOIBarrierAvailability.UNAVAILABLE
                and (self.barriers or self.reason != "TRUSTED_OPTIONS_OI_NOT_WIRED")
            )
        ):
            raise ValueError("V1_OPTIONS_OI_BARRIER_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class ClearAirEvidence:
    state: ClearAirState
    barriers: tuple[BarrierEvidence, ...]
    policy_identity: str = SWING_V1_CLEAR_AIR_POLICY_ID

    def __post_init__(self) -> None:
        if (
            type(self.state) is not ClearAirState
            or type(self.barriers) is not tuple
            or self.policy_identity != SWING_V1_CLEAR_AIR_POLICY_ID
        ):
            raise ValueError("V1_CLEAR_AIR_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class ReadinessAssessment:
    run_identity: str
    canonical_instrument: str
    observation_boundary: datetime
    probable_assessment_identities: tuple[str, ...]
    state: ReadinessState
    primary_reason: str
    supporting_evidence: tuple[str, ...]
    contradicting_evidence: tuple[str, ...]
    unresolved_evidence: tuple[str, ...]
    provenance: tuple[str, ...]
    policy_identity: str = SWING_V1_READINESS_ASSESSMENT_POLICY_ID
    policy_status: str = "CANDIDATE / NOT FROZEN"

    def __post_init__(self) -> None:
        if (
            not self.run_identity
            or not self.canonical_instrument
            or not _aware(self.observation_boundary)
            or not self.probable_assessment_identities
            or type(self.state) is not ReadinessState
            or not re.fullmatch(r"[A-Z][A-Z0-9_]{2,127}", self.primary_reason)
            or any(type(item) is not tuple for item in (
                self.supporting_evidence,
                self.contradicting_evidence,
                self.unresolved_evidence,
                self.provenance,
            ))
            or self.policy_identity != SWING_V1_READINESS_ASSESSMENT_POLICY_ID
            or self.policy_status != "CANDIDATE / NOT FROZEN"
        ):
            raise ValueError("V1_READINESS_ASSESSMENT_INVALID")


@dataclass(frozen=True, slots=True)
class Layer2ReviewRecord:
    structured_evidence: TradingViewStructuredEvidence
    structure_reconciliation: EvidenceReconciliationState
    sma20_reconciliation: EvidenceReconciliationState
    volume_reconciliation: EvidenceReconciliationState
    barriers: tuple[BarrierEvidence, ...]
    options_oi: OptionsOIBarrierEvidence
    clear_air: ClearAirEvidence
    readiness: ReadinessAssessment

    def __post_init__(self) -> None:
        if (
            type(self.structured_evidence) is not TradingViewStructuredEvidence
            or type(self.structure_reconciliation) is not EvidenceReconciliationState
            or type(self.sma20_reconciliation) is not EvidenceReconciliationState
            or type(self.volume_reconciliation) is not EvidenceReconciliationState
            or type(self.barriers) is not tuple
            or type(self.options_oi) is not OptionsOIBarrierEvidence
            or type(self.clear_air) is not ClearAirEvidence
            or type(self.readiness) is not ReadinessAssessment
        ):
            raise ValueError("V1_LAYER2_REVIEW_RECORD_INVALID")


def extract_tradingview_evidence(
    requirement: TradingViewReviewRequirement,
    revisions: tuple[ChartRevisionIdentity, ...],
    observations: tuple[ExtractedChartObservation, ...],
    *,
    template_identity: str,
) -> TradingViewExtractionResult:
    """Validate manual observations against immutable latest chart identities."""

    if type(requirement) is not TradingViewReviewRequirement:
        raise ValueError("V1_EXTRACTION_REQUIREMENT_INVALID")
    if template_identity != requirement.chart_template_identity:
        return TradingViewExtractionResult(
            ExtractionState.CONTEXT_INCOMPLETE,
            None,
            ("CHART_TEMPLATE_UNIDENTIFIED",),
        )
    revision_by_timeframe = {item.timeframe: item for item in revisions}
    missing = [
        f"CHART_{timeframe.value}_MISSING"
        for timeframe in requirement.required_timeframes
        if timeframe not in revision_by_timeframe
    ]
    for timeframe in requirement.required_timeframes:
        categories = {
            item.category
            for item in observations
            if item.timeframe is timeframe
        }
        missing.extend(
            f"{timeframe.value}_{category.value}_UNRECORDED"
            for category in _REQUIRED_CATEGORIES
            if category not in categories
        )
    if missing:
        return TradingViewExtractionResult(
            ExtractionState.CONTEXT_INCOMPLETE,
            None,
            tuple(missing),
        )
    for item in observations:
        revision = revision_by_timeframe.get(item.timeframe)
        if (
            item.run_identity != requirement.run_identity
            or item.canonical_instrument != requirement.canonical_instrument
            or item.observation_boundary != requirement.observation_boundary
            or item.chart_template_identity != requirement.chart_template_identity
            or revision is None
            or item.source_screenshot_sha256 != revision.source_sha256
        ):
            raise ValueError("V1_EXTRACTION_PROVENANCE_BINDING_MISMATCH")
    evidence = TradingViewStructuredEvidence(
        run_identity=requirement.run_identity,
        canonical_instrument=requirement.canonical_instrument,
        observation_boundary=requirement.observation_boundary,
        chart_template_identity=requirement.chart_template_identity,
        observations=observations,
        source_revisions=revisions,
    )
    return TradingViewExtractionResult(ExtractionState.CONSUMED, evidence, ())


def build_layer2_review_record(
    requirement: TradingViewReviewRequirement,
    assessments: tuple[V1Layer1Assessment, ...],
    structured: TradingViewStructuredEvidence,
) -> Layer2ReviewRecord:
    if not assessments or any(
        item.canonical_identity != requirement.canonical_instrument
        for item in assessments
    ):
        raise ValueError("V1_LAYER2_ASSESSMENT_BINDING_INVALID")
    structure = reconcile_structure(assessments[0], structured)
    sma20 = reconcile_sma20(assessments[0], structured)
    volume = reconcile_volume(assessments[0], structured)
    barriers = build_price_barriers(structured, requirement.probable_setups[0].direction)
    options = unavailable_options_oi()
    barrier_context_available = any(
        item.availability is EvidenceAvailability.AVAILABLE
        for item in structured.observations
        if item.category in {
            ObservationCategory.REFERENCE_LEVELS,
            ObservationCategory.STRUCTURAL_LEVELS,
            ObservationCategory.SMA20,
            ObservationCategory.SMA50,
            ObservationCategory.SMA200,
        }
    )
    clear_air = synthesize_clear_air(
        barriers,
        barrier_context_available=barrier_context_available,
    )
    readiness = assess_readiness(
        requirement,
        structured,
        structure,
        sma20,
        volume,
        barriers,
        clear_air,
    )
    return Layer2ReviewRecord(
        structured,
        structure,
        sma20,
        volume,
        barriers,
        options,
        clear_air,
        readiness,
    )


def reconcile_structure(
    layer1: V1Layer1Assessment,
    structured: TradingViewStructuredEvidence,
) -> EvidenceReconciliationState:
    observation = _daily(structured, ObservationCategory.PRICE_STRUCTURE)
    if observation.availability is not EvidenceAvailability.AVAILABLE:
        return EvidenceReconciliationState.UNAVAILABLE
    layer1_state = layer1.structural.consensus
    if layer1_state is None or layer1_state is StructuralState.MIXED_UNCLEAR:
        return EvidenceReconciliationState.MIXED
    if observation.evidence_value == "MIXED_UNCLEAR":
        return EvidenceReconciliationState.MIXED
    expected = (
        "HH_HL"
        if layer1_state is StructuralState.BULLISH_HH_HL
        else "LH_LL"
        if layer1_state is StructuralState.BEARISH_LH_LL
        else None
    )
    return (
        EvidenceReconciliationState.SUPPORTS
        if observation.evidence_value == expected
        else EvidenceReconciliationState.CONTRADICTS
    )


def reconcile_sma20(
    layer1: V1Layer1Assessment,
    structured: TradingViewStructuredEvidence,
) -> EvidenceReconciliationState:
    observation = _daily(structured, ObservationCategory.SMA20)
    if (
        observation.availability is not EvidenceAvailability.AVAILABLE
        or layer1.moving_average.sma20_availability is not EvidenceAvailability.AVAILABLE
    ):
        return EvidenceReconciliationState.UNAVAILABLE
    slope, relationship, _, _ = observation.evidence_value.split("|")
    expected_slope = {
        "UP": "RISING",
        "DOWN": "FALLING",
        "FLAT": "FLAT",
    }.get(layer1.moving_average.sma20_direction)
    expected_relationship = layer1.moving_average.price_vs_sma20
    return (
        EvidenceReconciliationState.SUPPORTS
        if slope == expected_slope and relationship == expected_relationship
        else EvidenceReconciliationState.CONTRADICTS
    )


def reconcile_volume(
    layer1: V1Layer1Assessment,
    structured: TradingViewStructuredEvidence,
) -> EvidenceReconciliationState:
    observation = _daily(structured, ObservationCategory.VOLUME_CONTEXT)
    if (
        observation.availability is not EvidenceAvailability.AVAILABLE
        or layer1.volume.availability is not EvidenceAvailability.AVAILABLE
    ):
        return EvidenceReconciliationState.UNAVAILABLE
    if observation.evidence_value in {
        "RESUMPTION_PARTICIPATION_SIZEABLE",
        "COUNTERTREND_PARTICIPATION_QUIETER",
        "BREAK_PARTICIPATION_INCREASED",
    }:
        return EvidenceReconciliationState.SUPPORTS
    return EvidenceReconciliationState.MIXED


def build_price_barriers(
    structured: TradingViewStructuredEvidence,
    direction: V1Direction,
) -> tuple[BarrierEvidence, ...]:
    candidates = [
        item
        for item in structured.observations
        if item.availability is EvidenceAvailability.AVAILABLE
        and item.correlation_key is not None
        and item.category in {
            ObservationCategory.REFERENCE_LEVELS,
            ObservationCategory.STRUCTURAL_LEVELS,
            ObservationCategory.SMA20,
            ObservationCategory.SMA50,
            ObservationCategory.SMA200,
        }
        and _barrier_side(item) is not None
    ]
    grouped: dict[str, list[ExtractedChartObservation]] = {}
    for item in candidates:
        grouped.setdefault(item.correlation_key or "", []).append(item)
    barriers = []
    for key, group in grouped.items():
        sides = {_barrier_side(item) for item in group}
        side = next(iter(sides)) if len(sides) == 1 else None
        relevance = _directional_relevance(direction, side)
        significances = {_barrier_significance(item) for item in group}
        significance = (
            BarrierSignificance.MAJOR
            if BarrierSignificance.MAJOR in significances
            else BarrierSignificance.PARTIAL
            if BarrierSignificance.PARTIAL in significances
            else BarrierSignificance.UNKNOWN
        )
        prices = tuple(item.price for item in group if item.price is not None)
        zone_lows = tuple(item.zone_low for item in group if item.zone_low is not None)
        zone_highs = tuple(item.zone_high for item in group if item.zone_high is not None)
        barriers.append(BarrierEvidence(
            correlation_key=key,
            source_categories=tuple(dict.fromkeys(item.category for item in group)),
            semantic_identities=tuple(dict.fromkeys(item.semantic_identity for item in group)),
            directional_relevance=relevance,
            timeframe=group[0].timeframe,
            significance=significance,
            price=prices[0] if prices and len(set(prices)) == 1 else None,
            zone_low=min(zone_lows) if zone_lows else None,
            zone_high=max(zone_highs) if zone_highs else None,
            source_hashes=tuple(dict.fromkeys(item.source_screenshot_sha256 for item in group)),
        ))
    return tuple(barriers)


def unavailable_options_oi() -> OptionsOIBarrierEvidence:
    return OptionsOIBarrierEvidence(
        OptionsOIBarrierAvailability.UNAVAILABLE,
        (),
        "TRUSTED_OPTIONS_OI_NOT_WIRED",
    )


def synthesize_clear_air(
    barriers: tuple[BarrierEvidence, ...],
    *,
    barrier_context_available: bool = True,
) -> ClearAirEvidence:
    adverse = tuple(
        item
        for item in barriers
        if item.directional_relevance is BarrierDirectionalRelevance.ADVERSE_PATH
    )
    state = (
        ClearAirState.UNKNOWN
        if not barrier_context_available
        else ClearAirState.CLEAR
        if not adverse
        else ClearAirState.MAJOR_BARRIER_PRESENT
        if any(item.significance is BarrierSignificance.MAJOR for item in adverse)
        else ClearAirState.PARTIALLY_OBSTRUCTED
        if any(item.significance is BarrierSignificance.PARTIAL for item in adverse)
        else ClearAirState.UNKNOWN
    )
    return ClearAirEvidence(state, barriers)


def assess_readiness(
    requirement: TradingViewReviewRequirement,
    structured: TradingViewStructuredEvidence,
    structure: EvidenceReconciliationState,
    sma20: EvidenceReconciliationState,
    volume: EvidenceReconciliationState,
    barriers: tuple[BarrierEvidence, ...],
    clear_air: ClearAirEvidence,
) -> ReadinessAssessment:
    development = _daily(structured, ObservationCategory.PRICE_DEVELOPMENT)
    candle = _daily(structured, ObservationCategory.CANDLE_BEHAVIOUR)
    ma_values = tuple(
        _daily(structured, category)
        for category in (
            ObservationCategory.SMA20,
            ObservationCategory.SMA50,
            ObservationCategory.SMA200,
        )
    )
    supporting: list[str] = []
    contradicting: list[str] = []
    unresolved: list[str] = []
    if structure is EvidenceReconciliationState.SUPPORTS:
        supporting.append("TRADINGVIEW_STRUCTURE_SUPPORTS_LAYER1")
    elif structure is EvidenceReconciliationState.CONTRADICTS:
        contradicting.append("TRADINGVIEW_STRUCTURE_CONTRADICTS_LAYER1")
    else:
        unresolved.append(f"STRUCTURE_{structure.value}")
    if sma20 is EvidenceReconciliationState.SUPPORTS:
        supporting.append("TRADINGVIEW_SMA20_ALIGNED")
    elif sma20 is EvidenceReconciliationState.CONTRADICTS:
        contradicting.append(DATA_ALIGNMENT_REVIEW)
    else:
        unresolved.append("SMA20_RECONCILIATION_UNAVAILABLE")
    if volume is EvidenceReconciliationState.SUPPORTS:
        supporting.append("TRADINGVIEW_VOLUME_CONTEXT_SUPPORTIVE")
    elif volume is EvidenceReconciliationState.UNAVAILABLE:
        unresolved.append("TRADINGVIEW_VOLUME_CONTEXT_UNAVAILABLE")
    if any(
        item.availability is EvidenceAvailability.AVAILABLE
        and item.evidence_value.split("|")[-1] == "REPEATED"
        for item in ma_values[:2]
    ):
        contradicting.append("REPEATED_SMA20_SMA50_CRISSCROSS")
    if clear_air.state is ClearAirState.CLEAR:
        supporting.append("CLEAR_AIR_TO_FUTURE_CONSTRUCTION")
    elif clear_air.state is not ClearAirState.UNKNOWN:
        contradicting.append(clear_air.state.value)
    else:
        unresolved.append("CLEAR_AIR_UNKNOWN")

    development_value = development.evidence_value
    candle_value = candle.evidence_value
    if development.availability is not EvidenceAvailability.AVAILABLE:
        state = ReadinessState.CONTEXT_INCOMPLETE
        reason = "PRICE_DEVELOPMENT_CONTEXT_UNAVAILABLE"
    elif development_value == "SETUP_INVALIDATED" or (
        structure is EvidenceReconciliationState.CONTRADICTS
        and candle_value in {"CLOSE_BACK_INSIDE_RANGE", "FAILED_BREAK"}
    ):
        state = ReadinessState.INVALIDATED
        reason = "SETUP_OR_BREAK_CONTEXT_FAILED"
    elif development_value == "EXTENDED_FROM_STRUCTURE":
        state = ReadinessState.EXTENDED_DO_NOT_CHASE
        reason = "MOVE_EXTENDED_FROM_STRUCTURE"
    elif development_value == "ORDERLY_PULLBACK_DEVELOPING":
        state = ReadinessState.WAIT_PULLBACK_DEVELOPING
        reason = "ORDERLY_PULLBACK_STILL_DEVELOPING"
    elif development_value == "RETEST_DEVELOPING":
        state = ReadinessState.WAIT_RETEST_DEVELOPING
        reason = "STRUCTURE_RETEST_STILL_DEVELOPING"
    elif development_value == "WEAKENING_FOLLOW_THROUGH" or (
        "REPEATED_SMA20_SMA50_CRISSCROSS" in contradicting
    ):
        state = ReadinessState.WEAKENING
        reason = "FOLLOW_THROUGH_OR_TREND_QUALITY_WEAKENING"
    elif (
        development_value == "READY_CONTEXT"
        and structure is EvidenceReconciliationState.SUPPORTS
        and sma20 is EvidenceReconciliationState.SUPPORTS
        and candle_value in {"ACCEPTANCE", "ACCEPTED_OUTSIDE_STRUCTURE", "RETEST_HELD"}
        and volume is EvidenceReconciliationState.SUPPORTS
        and clear_air.state is ClearAirState.CLEAR
        and not contradicting
    ):
        state = ReadinessState.READY_FOR_TRADE_CONSTRUCTION
        reason = "ALL_CANDIDATE_READINESS_CONTEXT_SUPPORTS_PROGRESSION"
    else:
        state = ReadinessState.WEAKENING
        reason = "CONTEXT_PRESENT_BUT_NOT_CLEANLY_READY"
    return ReadinessAssessment(
        run_identity=requirement.run_identity,
        canonical_instrument=requirement.canonical_instrument,
        observation_boundary=requirement.observation_boundary,
        probable_assessment_identities=tuple(
            item.assessment_identity for item in requirement.probable_setups
        ),
        state=state,
        primary_reason=reason,
        supporting_evidence=tuple(supporting),
        contradicting_evidence=tuple(contradicting),
        unresolved_evidence=tuple(unresolved),
        provenance=tuple(item.source_sha256 for item in structured.source_revisions),
    )


def context_incomplete_readiness(
    requirement: TradingViewReviewRequirement,
    missing: tuple[str, ...],
) -> ReadinessAssessment:
    return ReadinessAssessment(
        run_identity=requirement.run_identity,
        canonical_instrument=requirement.canonical_instrument,
        observation_boundary=requirement.observation_boundary,
        probable_assessment_identities=tuple(
            item.assessment_identity for item in requirement.probable_setups
        ),
        state=ReadinessState.CONTEXT_INCOMPLETE,
        primary_reason="MANDATORY_TRADINGVIEW_CONTEXT_INCOMPLETE",
        supporting_evidence=(),
        contradicting_evidence=(),
        unresolved_evidence=missing,
        provenance=(),
    )


def _observation_value_valid(item: ExtractedChartObservation) -> bool:
    if item.availability is not EvidenceAvailability.AVAILABLE:
        return (
            item.evidence_value == "UNAVAILABLE"
            and item.price is None
            and item.zone_low is None
            and item.correlation_key is None
        )
    if item.category is ObservationCategory.PRICE_STRUCTURE:
        return item.semantic_identity == "TRADINGVIEW_STRUCTURE" and item.evidence_value in _STRUCTURE_VALUES
    if item.category in {ObservationCategory.SMA20, ObservationCategory.SMA50, ObservationCategory.SMA200}:
        parts = item.evidence_value.split("|")
        return (
            item.semantic_identity == item.category.value
            and len(parts) == 4
            and parts[0] in _MA_SLOPES
            and parts[1] in _MA_RELATIONSHIPS
            and parts[2] in _MA_INTERACTIONS
            and parts[3] in _MA_CRISSCROSS
        )
    if item.category is ObservationCategory.CANDLE_BEHAVIOUR:
        return item.semantic_identity == "CANDLE_CONTEXT" and item.evidence_value in _CANDLE_VALUES
    if item.category is ObservationCategory.VOLUME_CONTEXT:
        return item.semantic_identity == "VOLUME_CONTEXT" and item.evidence_value in _VOLUME_VALUES
    if item.category is ObservationCategory.PRICE_DEVELOPMENT:
        return item.semantic_identity == "PRICE_DEVELOPMENT" and item.evidence_value in _DEVELOPMENT_VALUES
    if item.category in {ObservationCategory.REFERENCE_LEVELS, ObservationCategory.STRUCTURAL_LEVELS}:
        return item.semantic_identity in _LEVEL_IDENTITIES and item.evidence_value in _LEVEL_VALUES
    if item.category is ObservationCategory.PINE:
        return (
            item.semantic_identity == "PINE_DISPLAY"
            and re.fullmatch(r"DISPLAY:[A-Z0-9_ .,:;()/-]{1,160}", item.evidence_value) is not None
        )
    return False


def _daily(
    structured: TradingViewStructuredEvidence,
    category: ObservationCategory,
) -> ExtractedChartObservation:
    matches = tuple(
        item
        for item in structured.observations
        if item.timeframe is ChartTimeframe.DAILY and item.category is category
    )
    if not matches:
        raise ValueError("V1_REQUIRED_DAILY_OBSERVATION_MISSING")
    if category in {ObservationCategory.REFERENCE_LEVELS, ObservationCategory.STRUCTURAL_LEVELS}:
        available = next(
            (item for item in matches if item.availability is EvidenceAvailability.AVAILABLE),
            None,
        )
        return available or matches[0]
    if len(matches) != 1:
        raise ValueError("V1_SINGLETON_DAILY_OBSERVATION_INVALID")
    return matches[0]


def _barrier_side(item: ExtractedChartObservation) -> str | None:
    if item.category in {ObservationCategory.REFERENCE_LEVELS, ObservationCategory.STRUCTURAL_LEVELS}:
        return item.evidence_value.split("|")[0]
    if item.category in {ObservationCategory.SMA20, ObservationCategory.SMA50, ObservationCategory.SMA200}:
        interaction = item.evidence_value.split("|")[2]
        return "SUPPORT" if interaction in {"SUPPORT", "RESPECT"} else "RESISTANCE" if interaction == "REJECTION" else None
    return None


def _barrier_significance(item: ExtractedChartObservation) -> BarrierSignificance:
    if item.category in {ObservationCategory.REFERENCE_LEVELS, ObservationCategory.STRUCTURAL_LEVELS}:
        return BarrierSignificance(item.evidence_value.split("|")[1])
    return (
        BarrierSignificance.MAJOR
        if item.category is ObservationCategory.SMA200
        else BarrierSignificance.PARTIAL
    )


def _directional_relevance(
    direction: V1Direction,
    side: str | None,
) -> BarrierDirectionalRelevance:
    if side not in {"SUPPORT", "RESISTANCE"}:
        return BarrierDirectionalRelevance.MIXED_OR_UNCLEAR
    adverse = (
        direction is V1Direction.LONG and side == "RESISTANCE"
    ) or (
        direction is V1Direction.SHORT and side == "SUPPORT"
    )
    return (
        BarrierDirectionalRelevance.ADVERSE_PATH
        if adverse
        else BarrierDirectionalRelevance.PROTECTIVE_CONTEXT
    )


def _aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def _finite(value: object) -> bool:
    return type(value) is float and math.isfinite(value)


def layer2_record_to_dict(record: Layer2ReviewRecord) -> dict[str, object]:
    if type(record) is not Layer2ReviewRecord:
        raise ValueError("V1_LAYER2_RECORD_SERIALIZATION_INVALID")
    structured = record.structured_evidence
    return {
        "schema": "KRONOS_SWING_V1_LAYER2_REVIEW_V1",
        "structured_evidence": {
            "run_identity": structured.run_identity,
            "canonical_instrument": structured.canonical_instrument,
            "observation_boundary": structured.observation_boundary.isoformat(),
            "chart_template_identity": structured.chart_template_identity,
            "policy_identity": structured.policy_identity,
            "source_revisions": [
                {
                    "timeframe": item.timeframe.value,
                    "source_sha256": item.source_sha256,
                }
                for item in structured.source_revisions
            ],
            "observations": [_observation_to_dict(item) for item in structured.observations],
        },
        "structure_reconciliation": record.structure_reconciliation.value,
        "sma20_reconciliation": record.sma20_reconciliation.value,
        "volume_reconciliation": record.volume_reconciliation.value,
        "barriers": [_barrier_to_dict(item) for item in record.barriers],
        "options_oi": {
            "availability": record.options_oi.availability.value,
            "barriers": [_barrier_to_dict(item) for item in record.options_oi.barriers],
            "reason": record.options_oi.reason,
            "policy_identity": record.options_oi.policy_identity,
        },
        "clear_air": {
            "state": record.clear_air.state.value,
            "barriers": [_barrier_to_dict(item) for item in record.clear_air.barriers],
            "policy_identity": record.clear_air.policy_identity,
        },
        "readiness": _readiness_to_dict(record.readiness),
        "final_trade_construction": "NOT_IMPLEMENTED",
        "final_risk_reward": "NOT_CALCULATED",
        "ranking": "NOT_PERFORMED",
    }


def layer2_record_from_dict(payload: object) -> Layer2ReviewRecord:
    if type(payload) is not dict or payload.get("schema") != "KRONOS_SWING_V1_LAYER2_REVIEW_V1":
        raise ValueError("V1_LAYER2_RECORD_DESERIALIZATION_INVALID")
    try:
        raw = payload["structured_evidence"]
        structured = TradingViewStructuredEvidence(
            run_identity=raw["run_identity"],
            canonical_instrument=raw["canonical_instrument"],
            observation_boundary=datetime.fromisoformat(raw["observation_boundary"]),
            chart_template_identity=raw["chart_template_identity"],
            observations=tuple(_observation_from_dict(item) for item in raw["observations"]),
            source_revisions=tuple(
                ChartRevisionIdentity(
                    ChartTimeframe(item["timeframe"]),
                    item["source_sha256"],
                )
                for item in raw["source_revisions"]
            ),
            policy_identity=raw["policy_identity"],
        )
        options_raw = payload["options_oi"]
        clear_raw = payload["clear_air"]
        return Layer2ReviewRecord(
            structured_evidence=structured,
            structure_reconciliation=EvidenceReconciliationState(payload["structure_reconciliation"]),
            sma20_reconciliation=EvidenceReconciliationState(payload["sma20_reconciliation"]),
            volume_reconciliation=EvidenceReconciliationState(payload["volume_reconciliation"]),
            barriers=tuple(_barrier_from_dict(item) for item in payload["barriers"]),
            options_oi=OptionsOIBarrierEvidence(
                OptionsOIBarrierAvailability(options_raw["availability"]),
                tuple(_barrier_from_dict(item) for item in options_raw["barriers"]),
                options_raw["reason"],
                options_raw["policy_identity"],
            ),
            clear_air=ClearAirEvidence(
                ClearAirState(clear_raw["state"]),
                tuple(_barrier_from_dict(item) for item in clear_raw["barriers"]),
                clear_raw["policy_identity"],
            ),
            readiness=_readiness_from_dict(payload["readiness"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("V1_LAYER2_RECORD_DESERIALIZATION_INVALID") from error


def _observation_to_dict(item: ExtractedChartObservation) -> dict[str, object]:
    return {
        "run_identity": item.run_identity,
        "canonical_instrument": item.canonical_instrument,
        "observation_boundary": item.observation_boundary.isoformat(),
        "timeframe": item.timeframe.value,
        "chart_template_identity": item.chart_template_identity,
        "source_screenshot_sha256": item.source_screenshot_sha256,
        "category": item.category.value,
        "semantic_identity": item.semantic_identity,
        "evidence_value": item.evidence_value,
        "availability": item.availability.value,
        "extraction_provenance": item.extraction_provenance.value,
        "price": item.price,
        "zone_low": item.zone_low,
        "zone_high": item.zone_high,
        "correlation_key": item.correlation_key,
    }


def _observation_from_dict(item: object) -> ExtractedChartObservation:
    if type(item) is not dict:
        raise ValueError("V1_LAYER2_OBSERVATION_DESERIALIZATION_INVALID")
    return ExtractedChartObservation(
        run_identity=item["run_identity"],
        canonical_instrument=item["canonical_instrument"],
        observation_boundary=datetime.fromisoformat(item["observation_boundary"]),
        timeframe=ChartTimeframe(item["timeframe"]),
        chart_template_identity=item["chart_template_identity"],
        source_screenshot_sha256=item["source_screenshot_sha256"],
        category=ObservationCategory(item["category"]),
        semantic_identity=item["semantic_identity"],
        evidence_value=item["evidence_value"],
        availability=EvidenceAvailability(item["availability"]),
        extraction_provenance=ExtractionProvenance(item["extraction_provenance"]),
        price=item["price"],
        zone_low=item["zone_low"],
        zone_high=item["zone_high"],
        correlation_key=item["correlation_key"],
    )


def _barrier_to_dict(item: BarrierEvidence) -> dict[str, object]:
    return {
        "correlation_key": item.correlation_key,
        "source_categories": [value.value for value in item.source_categories],
        "semantic_identities": list(item.semantic_identities),
        "directional_relevance": item.directional_relevance.value,
        "timeframe": item.timeframe.value,
        "significance": item.significance.value,
        "price": item.price,
        "zone_low": item.zone_low,
        "zone_high": item.zone_high,
        "source_hashes": list(item.source_hashes),
        "policy_identity": item.policy_identity,
    }


def _barrier_from_dict(item: object) -> BarrierEvidence:
    if type(item) is not dict:
        raise ValueError("V1_LAYER2_BARRIER_DESERIALIZATION_INVALID")
    return BarrierEvidence(
        correlation_key=item["correlation_key"],
        source_categories=tuple(ObservationCategory(value) for value in item["source_categories"]),
        semantic_identities=tuple(item["semantic_identities"]),
        directional_relevance=BarrierDirectionalRelevance(item["directional_relevance"]),
        timeframe=ChartTimeframe(item["timeframe"]),
        significance=BarrierSignificance(item["significance"]),
        price=item["price"],
        zone_low=item["zone_low"],
        zone_high=item["zone_high"],
        source_hashes=tuple(item["source_hashes"]),
        policy_identity=item["policy_identity"],
    )


def _readiness_to_dict(item: ReadinessAssessment) -> dict[str, object]:
    return {
        "run_identity": item.run_identity,
        "canonical_instrument": item.canonical_instrument,
        "observation_boundary": item.observation_boundary.isoformat(),
        "probable_assessment_identities": list(item.probable_assessment_identities),
        "state": item.state.value,
        "primary_reason": item.primary_reason,
        "supporting_evidence": list(item.supporting_evidence),
        "contradicting_evidence": list(item.contradicting_evidence),
        "unresolved_evidence": list(item.unresolved_evidence),
        "provenance": list(item.provenance),
        "policy_identity": item.policy_identity,
        "policy_status": item.policy_status,
    }


def _readiness_from_dict(item: object) -> ReadinessAssessment:
    if type(item) is not dict:
        raise ValueError("V1_LAYER2_READINESS_DESERIALIZATION_INVALID")
    return ReadinessAssessment(
        run_identity=item["run_identity"],
        canonical_instrument=item["canonical_instrument"],
        observation_boundary=datetime.fromisoformat(item["observation_boundary"]),
        probable_assessment_identities=tuple(item["probable_assessment_identities"]),
        state=ReadinessState(item["state"]),
        primary_reason=item["primary_reason"],
        supporting_evidence=tuple(item["supporting_evidence"]),
        contradicting_evidence=tuple(item["contradicting_evidence"]),
        unresolved_evidence=tuple(item["unresolved_evidence"]),
        provenance=tuple(item["provenance"]),
        policy_identity=item["policy_identity"],
        policy_status=item["policy_status"],
    )


__all__ = [
    "BarrierDirectionalRelevance",
    "BarrierEvidence",
    "BarrierSignificance",
    "ChartRevisionIdentity",
    "ClearAirEvidence",
    "ClearAirState",
    "EvidenceReconciliationState",
    "ExtractedChartObservation",
    "ExtractionProvenance",
    "ExtractionState",
    "Layer2ReviewRecord",
    "ObservationCategory",
    "OptionsOIBarrierAvailability",
    "OptionsOIBarrierEvidence",
    "ReadinessAssessment",
    "ReadinessState",
    "TradingViewExtractionResult",
    "TradingViewStructuredEvidence",
    "assess_readiness",
    "build_layer2_review_record",
    "build_price_barriers",
    "context_incomplete_readiness",
    "extract_tradingview_evidence",
    "layer2_record_from_dict",
    "layer2_record_to_dict",
    "reconcile_sma20",
    "reconcile_structure",
    "reconcile_volume",
    "synthesize_clear_air",
    "unavailable_options_oi",
]
