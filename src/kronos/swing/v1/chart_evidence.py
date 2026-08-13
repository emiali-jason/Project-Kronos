"""Provider-neutral, versioned chart-evidence contract for Swing V1.

Providers interpret a retained chart image.  They do not decide Readiness or
construct a trade.  This module deliberately contains no provider API details.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import math
import re
from typing import Protocol, runtime_checkable

from kronos.swing.v1.layer2 import (
    ChartRevisionIdentity,
    ExtractedChartObservation,
    ExtractionProvenance,
    ObservationCategory,
)
from kronos.swing.v1.models import EvidenceAvailability, V1Direction
from kronos.swing.v1.tradingview import ChartTimeframe, TRADINGVIEW_CHART_TEMPLATE_ID


CHART_QUESTION_SET_V1_ID = "SWING-V1-CHART-QUESTION-SET-V1"
CHART_EVIDENCE_SCHEMA_V1_ID = "KRONOS-SWING-V1-CHART-EVIDENCE-V1"
MANUAL_CHART_EVIDENCE_PROVIDER_ID = "MANUAL_CHART_EVIDENCE_PROVIDER"
OPENAI_CHART_EVIDENCE_PROVIDER_ID = "OPENAI_CHART_EVIDENCE_PROVIDER"


class ChartEvidenceAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    UNDETERMINABLE = "UNDETERMINABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class IdentityConsistency(StrEnum):
    CONSISTENT = "CONSISTENT"
    INCONSISTENT = "INCONSISTENT"
    UNDETERMINABLE = "UNDETERMINABLE"


class PriceStructureValue(StrEnum):
    HH_HL = "HH_HL"
    LH_LL = "LH_LL"
    MIXED_UNCLEAR = "MIXED_UNCLEAR"
    UNDETERMINABLE = "UNDETERMINABLE"


class TernaryVisibleState(StrEnum):
    YES = "YES"
    NO = "NO"
    UNDETERMINABLE = "UNDETERMINABLE"


class MovingAverageSlope(StrEnum):
    RISING = "RISING"
    FALLING = "FALLING"
    FLAT = "FLAT"
    UNCLEAR = "UNCLEAR"
    NOT_VISIBLE = "NOT_VISIBLE"


class PriceRelationship(StrEnum):
    ABOVE = "ABOVE"
    BELOW = "BELOW"
    INTERACTING = "INTERACTING"
    UNDETERMINABLE = "UNDETERMINABLE"


class MovingAverageInteraction(StrEnum):
    SUPPORT = "SUPPORT"
    RESISTANCE = "RESISTANCE"
    CRISSCROSS = "CRISSCROSS"
    NONE = "NONE"
    UNDETERMINABLE = "UNDETERMINABLE"


class CrisscrossBehaviour(StrEnum):
    REPEATED = "REPEATED"
    CLEAN_SEPARATION = "CLEAN_SEPARATION"
    LIMITED = "LIMITED"
    UNDETERMINABLE = "UNDETERMINABLE"


class CandleAcceptanceState(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    INDECISION = "INDECISION"
    RETEST_DEVELOPING = "RETEST_DEVELOPING"
    RETEST_HELD = "RETEST_HELD"
    CLOSE_BACK_INSIDE = "CLOSE_BACK_INSIDE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNDETERMINABLE = "UNDETERMINABLE"


class VolumeTrend(StrEnum):
    INCREASING = "INCREASING"
    DECREASING = "DECREASING"
    MIXED = "MIXED"
    UNDETERMINABLE = "UNDETERMINABLE"


class ParticipationState(StrEnum):
    SIZEABLE = "SIZEABLE"
    QUIETER = "QUIETER"
    INCREASED = "INCREASED"
    WEAK = "WEAK"
    MIXED = "MIXED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNDETERMINABLE = "UNDETERMINABLE"


class ReferenceLevelIdentity(StrEnum):
    CPR = "CPR"
    PDH = "PDH"
    PDL = "PDL"
    PWH = "PWH"
    PWL = "PWL"
    VISIBLE_SUPPORT = "VISIBLE_SUPPORT"
    VISIBLE_RESISTANCE = "VISIBLE_RESISTANCE"
    SWING_HIGH = "SWING_HIGH"
    SWING_LOW = "SWING_LOW"
    RANGE_HIGH = "RANGE_HIGH"
    RANGE_LOW = "RANGE_LOW"
    BREAKOUT_LOCATION = "BREAKOUT_LOCATION"
    BREAKDOWN_LOCATION = "BREAKDOWN_LOCATION"


class LevelInteraction(StrEnum):
    SUPPORT = "SUPPORT"
    RESISTANCE = "RESISTANCE"
    INTERACTING = "INTERACTING"
    VISIBLE_NOT_RELEVANT = "VISIBLE_NOT_RELEVANT"
    UNDETERMINABLE = "UNDETERMINABLE"


class LevelSignificance(StrEnum):
    MAJOR = "MAJOR"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


class BarrierPresence(StrEnum):
    YES = "YES"
    NO = "NO"
    UNDETERMINABLE = "UNDETERMINABLE"


class BarrierRelativeLocation(StrEnum):
    ABOVE_PRICE = "ABOVE_PRICE"
    BELOW_PRICE = "BELOW_PRICE"
    INTERACTING = "INTERACTING"
    UNDETERMINABLE = "UNDETERMINABLE"


class ContradictionCode(StrEnum):
    STRUCTURE_OPPOSES_LAYER1 = "STRUCTURE_OPPOSES_LAYER1"
    SMA20_OPPOSES_LAYER1 = "SMA20_OPPOSES_LAYER1"
    VOLUME_NOT_SUPPORTIVE = "VOLUME_NOT_SUPPORTIVE"
    CANDLE_REJECTION = "CANDLE_REJECTION"
    BARRIER_IN_THESIS_PATH = "BARRIER_IN_THESIS_PATH"
    PINE_DISPLAY_CONTRADICTS_THESIS = "PINE_DISPLAY_CONTRADICTS_THESIS"


class ChartQuestionId(StrEnum):
    CHART_INSTRUMENT_IDENTITY = "CHART_INSTRUMENT_IDENTITY"
    CHART_TIMEFRAME_IDENTITY = "CHART_TIMEFRAME_IDENTITY"
    CHART_TEMPLATE_IDENTITY = "CHART_TEMPLATE_IDENTITY"
    PRICE_STRUCTURE = "PRICE_STRUCTURE"
    VISIBLE_SWINGS = "VISIBLE_SWINGS"
    RANGE_OR_CONSOLIDATION = "RANGE_OR_CONSOLIDATION"
    BREAKOUT_OR_BREAKDOWN = "BREAKOUT_OR_BREAKDOWN"
    SMA20 = "SMA20"
    SMA50 = "SMA50"
    SMA200 = "SMA200"
    CANDLE_ACCEPTANCE = "CANDLE_ACCEPTANCE"
    VOLUME_CONTEXT = "VOLUME_CONTEXT"
    REFERENCE_LEVELS = "REFERENCE_LEVELS"
    BARRIERS = "BARRIERS"
    PINE_DISPLAY = "PINE_DISPLAY"
    CONTRADICTIONS = "CONTRADICTIONS"


FROZEN_CHART_QUESTION_SET_V1 = tuple(ChartQuestionId)


class ChartEvidenceProviderFailureCode(StrEnum):
    DISABLED = "PROVIDER_DISABLED"
    UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    TIMEOUT = "PROVIDER_TIMEOUT"
    REFUSAL = "PROVIDER_REFUSAL"
    INCOMPLETE = "PROVIDER_RESPONSE_INCOMPLETE"
    INVALID_SCHEMA = "PROVIDER_SCHEMA_INVALID"
    IDENTITY_MISMATCH = "PROVIDER_IDENTITY_MISMATCH"
    LOW_CONFIDENCE = "PROVIDER_CONTEXT_UNDETERMINABLE"


class ChartEvidenceProviderError(RuntimeError):
    def __init__(self, code: ChartEvidenceProviderFailureCode) -> None:
        if type(code) is not ChartEvidenceProviderFailureCode:
            raise TypeError("CHART_EVIDENCE_PROVIDER_FAILURE_INVALID")
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class ChartThesisContext:
    direction: V1Direction
    setup: str
    layer1_structure: str
    layer1_sma20_slope: str
    layer1_price_vs_sma20: str
    layer1_volume_context: str

    def __post_init__(self) -> None:
        if (
            self.direction not in {V1Direction.LONG, V1Direction.SHORT}
            or not _code(self.setup)
            or not _code(self.layer1_structure)
            or not _code(self.layer1_sma20_slope)
            or not _code(self.layer1_price_vs_sma20)
            or not _code(self.layer1_volume_context)
        ):
            raise ValueError("CHART_THESIS_CONTEXT_INVALID")


@dataclass(frozen=True, slots=True)
class ChartEvidenceRequest:
    run_identity: str
    canonical_instrument: str
    timeframe: ChartTimeframe
    observation_boundary: datetime
    chart_template_identity: str
    question_set_identity: str
    request_timestamp: datetime
    source_image_sha256: str
    content_type: str
    original_image: bytes
    thesis_context: ChartThesisContext

    def __post_init__(self) -> None:
        if (
            not self.run_identity
            or not self.canonical_instrument
            or type(self.timeframe) is not ChartTimeframe
            or not _aware(self.observation_boundary)
            or self.chart_template_identity != TRADINGVIEW_CHART_TEMPLATE_ID
            or self.question_set_identity != CHART_QUESTION_SET_V1_ID
            or not _aware(self.request_timestamp)
            or re.fullmatch(r"[0-9a-f]{64}", self.source_image_sha256) is None
            or self.content_type not in {"image/png", "image/jpeg", "image/webp"}
            or type(self.original_image) is not bytes
            or not self.original_image
            or sha256(self.original_image).hexdigest() != self.source_image_sha256
            or type(self.thesis_context) is not ChartThesisContext
        ):
            raise ValueError("CHART_EVIDENCE_REQUEST_INVALID")


@dataclass(frozen=True, slots=True)
class IdentityEvidence:
    availability: ChartEvidenceAvailability
    observed_value: str
    consistency: IdentityConsistency

    def __post_init__(self) -> None:
        if (
            type(self.availability) is not ChartEvidenceAvailability
            or type(self.observed_value) is not str
            or len(self.observed_value) > 128
            or type(self.consistency) is not IdentityConsistency
            or (
                self.availability is ChartEvidenceAvailability.AVAILABLE
                and (
                    not self.observed_value.strip()
                    or self.consistency is IdentityConsistency.UNDETERMINABLE
                )
            )
            or (
                self.availability is not ChartEvidenceAvailability.AVAILABLE
                and (
                    self.observed_value != ""
                    or self.consistency is not IdentityConsistency.UNDETERMINABLE
                )
            )
        ):
            raise ValueError("CHART_IDENTITY_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class PriceStructureEvidence:
    availability: ChartEvidenceAvailability
    value: PriceStructureValue
    swing_highs: tuple[float, ...]
    swing_lows: tuple[float, ...]
    consolidation_visible: TernaryVisibleState
    breakout_visible: TernaryVisibleState
    breakdown_visible: TernaryVisibleState

    def __post_init__(self) -> None:
        if (
            type(self.availability) is not ChartEvidenceAvailability
            or type(self.value) is not PriceStructureValue
            or type(self.swing_highs) is not tuple
            or type(self.swing_lows) is not tuple
            or any(not _finite(item) for item in (*self.swing_highs, *self.swing_lows))
            or type(self.consolidation_visible) is not TernaryVisibleState
            or type(self.breakout_visible) is not TernaryVisibleState
            or type(self.breakdown_visible) is not TernaryVisibleState
            or (
                self.availability is ChartEvidenceAvailability.AVAILABLE
                and self.value is PriceStructureValue.UNDETERMINABLE
            )
            or (
                self.availability is not ChartEvidenceAvailability.AVAILABLE
                and (
                    self.value is not PriceStructureValue.UNDETERMINABLE
                    or self.swing_highs
                    or self.swing_lows
                    or self.consolidation_visible is not TernaryVisibleState.UNDETERMINABLE
                    or self.breakout_visible is not TernaryVisibleState.UNDETERMINABLE
                    or self.breakdown_visible is not TernaryVisibleState.UNDETERMINABLE
                )
            )
        ):
            raise ValueError("CHART_PRICE_STRUCTURE_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class MovingAverageChartEvidence:
    indicator: str
    availability: ChartEvidenceAvailability
    slope: MovingAverageSlope
    price_relationship: PriceRelationship
    interaction: MovingAverageInteraction
    crisscross: CrisscrossBehaviour

    def __post_init__(self) -> None:
        unavailable = self.availability is not ChartEvidenceAvailability.AVAILABLE
        if (
            self.indicator not in {"SMA20", "SMA50", "SMA200"}
            or type(self.availability) is not ChartEvidenceAvailability
            or type(self.slope) is not MovingAverageSlope
            or type(self.price_relationship) is not PriceRelationship
            or type(self.interaction) is not MovingAverageInteraction
            or type(self.crisscross) is not CrisscrossBehaviour
            or (
                self.availability is ChartEvidenceAvailability.AVAILABLE
                and self.slope is MovingAverageSlope.NOT_VISIBLE
            )
            or (
                unavailable
                and not (
                    self.slope in {MovingAverageSlope.NOT_VISIBLE, MovingAverageSlope.UNCLEAR}
                    and self.price_relationship is PriceRelationship.UNDETERMINABLE
                    and self.interaction is MovingAverageInteraction.UNDETERMINABLE
                    and self.crisscross is CrisscrossBehaviour.UNDETERMINABLE
                )
            )
        ):
            raise ValueError("CHART_MOVING_AVERAGE_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class CandleChartEvidence:
    availability: ChartEvidenceAvailability
    state: CandleAcceptanceState

    def __post_init__(self) -> None:
        if (
            type(self.availability) is not ChartEvidenceAvailability
            or type(self.state) is not CandleAcceptanceState
            or (
                self.availability is ChartEvidenceAvailability.AVAILABLE
                and self.state in {
                    CandleAcceptanceState.UNDETERMINABLE,
                    CandleAcceptanceState.NOT_APPLICABLE,
                }
            )
            or (
                self.availability is ChartEvidenceAvailability.NOT_APPLICABLE
                and self.state is not CandleAcceptanceState.NOT_APPLICABLE
            )
            or (
                self.availability in {
                    ChartEvidenceAvailability.UNAVAILABLE,
                    ChartEvidenceAvailability.UNDETERMINABLE,
                }
                and self.state is not CandleAcceptanceState.UNDETERMINABLE
            )
        ):
            raise ValueError("CHART_CANDLE_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class VolumeChartEvidence:
    availability: ChartEvidenceAvailability
    trend: VolumeTrend
    trend_direction_participation: ParticipationState
    pullback_participation: ParticipationState
    breakout_participation: ParticipationState

    def __post_init__(self) -> None:
        values = (
            self.trend_direction_participation,
            self.pullback_participation,
            self.breakout_participation,
        )
        if (
            type(self.availability) is not ChartEvidenceAvailability
            or type(self.trend) is not VolumeTrend
            or any(type(item) is not ParticipationState for item in values)
            or (
                self.availability is ChartEvidenceAvailability.AVAILABLE
                and self.trend is VolumeTrend.UNDETERMINABLE
            )
            or (
                self.availability is not ChartEvidenceAvailability.AVAILABLE
                and (
                    self.trend is not VolumeTrend.UNDETERMINABLE
                    or any(item is not ParticipationState.UNDETERMINABLE for item in values)
                )
            )
        ):
            raise ValueError("CHART_VOLUME_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class ReferenceLevelChartEvidence:
    identity: ReferenceLevelIdentity
    availability: ChartEvidenceAvailability
    interaction: LevelInteraction
    significance: LevelSignificance
    price: float | None
    zone_low: float | None
    zone_high: float | None

    def __post_init__(self) -> None:
        if (
            type(self.identity) is not ReferenceLevelIdentity
            or type(self.availability) is not ChartEvidenceAvailability
            or type(self.interaction) is not LevelInteraction
            or type(self.significance) is not LevelSignificance
            or any(item is not None and not _finite(item) for item in (self.price, self.zone_low, self.zone_high))
            or ((self.zone_low is None) != (self.zone_high is None))
            or (self.zone_low is not None and self.zone_high is not None and self.zone_low > self.zone_high)
            or (
                self.availability is not ChartEvidenceAvailability.AVAILABLE
                and (
                    self.interaction is not LevelInteraction.UNDETERMINABLE
                    or self.price is not None
                    or self.zone_low is not None
                )
            )
        ):
            raise ValueError("CHART_REFERENCE_LEVEL_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class BarrierChartEvidence:
    presence: BarrierPresence
    identity: ReferenceLevelIdentity
    interaction: LevelInteraction
    significance: LevelSignificance
    relative_location: BarrierRelativeLocation
    source: str
    price: float | None

    def __post_init__(self) -> None:
        if (
            type(self.presence) is not BarrierPresence
            or type(self.identity) is not ReferenceLevelIdentity
            or type(self.interaction) is not LevelInteraction
            or type(self.significance) is not LevelSignificance
            or type(self.relative_location) is not BarrierRelativeLocation
            or self.source not in {"REFERENCE_LEVEL", "STRUCTURAL_LEVEL", "SMA20", "SMA50", "SMA200"}
            or (self.price is not None and not _finite(self.price))
            or (
                self.presence is not BarrierPresence.YES
                and (
                    self.interaction is not LevelInteraction.UNDETERMINABLE
                    or self.relative_location is not BarrierRelativeLocation.UNDETERMINABLE
                    or self.price is not None
                )
            )
        ):
            raise ValueError("CHART_BARRIER_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class PineChartEvidence:
    availability: ChartEvidenceAvailability
    displayed_text: str

    def __post_init__(self) -> None:
        if (
            type(self.availability) is not ChartEvidenceAvailability
            or type(self.displayed_text) is not str
            or len(self.displayed_text) > 160
            or (
                self.availability is ChartEvidenceAvailability.AVAILABLE
                and not self.displayed_text.strip()
            )
            or (
                self.availability is not ChartEvidenceAvailability.AVAILABLE
                and self.displayed_text != ""
            )
        ):
            raise ValueError("CHART_PINE_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class ChartEvidenceResponse:
    schema_identity: str
    provider_identity: str
    model_identity: str
    question_set_identity: str
    request_timestamp: datetime
    run_identity: str
    canonical_instrument: str
    timeframe: ChartTimeframe
    observation_boundary: datetime
    chart_template_identity: str
    source_image_sha256: str
    instrument_identity: IdentityEvidence
    timeframe_identity: IdentityEvidence
    template_identity: IdentityEvidence
    price_structure: PriceStructureEvidence
    moving_averages: tuple[MovingAverageChartEvidence, ...]
    candle: CandleChartEvidence
    volume: VolumeChartEvidence
    reference_levels: tuple[ReferenceLevelChartEvidence, ...]
    barriers: tuple[BarrierChartEvidence, ...]
    pine: PineChartEvidence
    contradictions: tuple[ContradictionCode, ...]
    undeterminable_questions: tuple[ChartQuestionId, ...]

    def __post_init__(self) -> None:
        if (
            self.schema_identity != CHART_EVIDENCE_SCHEMA_V1_ID
            or not _provider_code(self.provider_identity)
            or not self.model_identity
            or len(self.model_identity) > 128
            or self.question_set_identity != CHART_QUESTION_SET_V1_ID
            or not _aware(self.request_timestamp)
            or not self.run_identity
            or not self.canonical_instrument
            or type(self.timeframe) is not ChartTimeframe
            or not _aware(self.observation_boundary)
            or self.chart_template_identity != TRADINGVIEW_CHART_TEMPLATE_ID
            or re.fullmatch(r"[0-9a-f]{64}", self.source_image_sha256) is None
            or type(self.instrument_identity) is not IdentityEvidence
            or type(self.timeframe_identity) is not IdentityEvidence
            or type(self.template_identity) is not IdentityEvidence
            or type(self.price_structure) is not PriceStructureEvidence
            or type(self.moving_averages) is not tuple
            or tuple(item.indicator for item in self.moving_averages) != ("SMA20", "SMA50", "SMA200")
            or type(self.candle) is not CandleChartEvidence
            or type(self.volume) is not VolumeChartEvidence
            or type(self.reference_levels) is not tuple
            or any(type(item) is not ReferenceLevelChartEvidence for item in self.reference_levels)
            or type(self.barriers) is not tuple
            or any(type(item) is not BarrierChartEvidence for item in self.barriers)
            or type(self.pine) is not PineChartEvidence
            or type(self.contradictions) is not tuple
            or any(type(item) is not ContradictionCode for item in self.contradictions)
            or len(set(self.contradictions)) != len(self.contradictions)
            or type(self.undeterminable_questions) is not tuple
            or any(type(item) is not ChartQuestionId for item in self.undeterminable_questions)
            or len(set(self.undeterminable_questions)) != len(self.undeterminable_questions)
        ):
            raise ValueError("CHART_EVIDENCE_RESPONSE_INVALID")

    def validate_binding(self, request: ChartEvidenceRequest) -> None:
        if (
            type(request) is not ChartEvidenceRequest
            or self.request_timestamp != request.request_timestamp
            or self.run_identity != request.run_identity
            or self.canonical_instrument != request.canonical_instrument
            or self.timeframe is not request.timeframe
            or self.observation_boundary != request.observation_boundary
            or self.chart_template_identity != request.chart_template_identity
            or self.source_image_sha256 != request.source_image_sha256
            or self.question_set_identity != request.question_set_identity
            or self.instrument_identity.observed_value != request.canonical_instrument
            or self.timeframe_identity.observed_value != request.timeframe.value
            or self.template_identity.observed_value != request.chart_template_identity
        ):
            raise ChartEvidenceProviderError(ChartEvidenceProviderFailureCode.IDENTITY_MISMATCH)

    def require_usable_context(self) -> None:
        identities = (self.instrument_identity, self.timeframe_identity, self.template_identity)
        if any(
            item.availability is not ChartEvidenceAvailability.AVAILABLE
            or item.consistency is not IdentityConsistency.CONSISTENT
            for item in identities
        ):
            raise ChartEvidenceProviderError(ChartEvidenceProviderFailureCode.IDENTITY_MISMATCH)
        critical = (
            self.price_structure.availability,
            *(item.availability for item in self.moving_averages),
            self.candle.availability,
            self.volume.availability,
        )
        if any(item is not ChartEvidenceAvailability.AVAILABLE for item in critical):
            raise ChartEvidenceProviderError(ChartEvidenceProviderFailureCode.LOW_CONFIDENCE)
        if self.undeterminable_questions and any(
            item in {
                ChartQuestionId.PRICE_STRUCTURE,
                ChartQuestionId.SMA20,
                ChartQuestionId.SMA50,
                ChartQuestionId.SMA200,
                ChartQuestionId.CANDLE_ACCEPTANCE,
                ChartQuestionId.VOLUME_CONTEXT,
            }
            for item in self.undeterminable_questions
        ):
            raise ChartEvidenceProviderError(ChartEvidenceProviderFailureCode.LOW_CONFIDENCE)


@runtime_checkable
class ChartEvidenceProvider(Protocol):
    @property
    def provider_identity(self) -> str: ...

    def analyze(self, request: ChartEvidenceRequest) -> ChartEvidenceResponse: ...


class ManualChartEvidenceProvider:
    """Validation provider returning Sponsor-reviewed responses by image hash."""

    def __init__(self, responses: tuple[ChartEvidenceResponse, ...]) -> None:
        if type(responses) is not tuple or not responses:
            raise ValueError("MANUAL_CHART_EVIDENCE_RESPONSES_INVALID")
        self._responses = {item.source_image_sha256: item for item in responses}
        if len(self._responses) != len(responses):
            raise ValueError("MANUAL_CHART_EVIDENCE_RESPONSES_INVALID")

    @property
    def provider_identity(self) -> str:
        return MANUAL_CHART_EVIDENCE_PROVIDER_ID

    def analyze(self, request: ChartEvidenceRequest) -> ChartEvidenceResponse:
        response = self._responses.get(request.source_image_sha256)
        if response is None:
            raise ChartEvidenceProviderError(ChartEvidenceProviderFailureCode.UNAVAILABLE)
        response.validate_binding(request)
        response.require_usable_context()
        return response


def response_to_observations(
    response: ChartEvidenceResponse,
) -> tuple[ExtractedChartObservation, ...]:
    """Normalize observations without allowing the provider to choose Readiness."""

    response.require_usable_context()
    base = {
        "run_identity": response.run_identity,
        "canonical_instrument": response.canonical_instrument,
        "observation_boundary": response.observation_boundary,
        "timeframe": response.timeframe,
        "chart_template_identity": response.chart_template_identity,
        "source_screenshot_sha256": response.source_image_sha256,
        "extraction_provenance": (
            ExtractionProvenance.SPONSOR_REVIEWED_MANUAL
            if response.provider_identity == MANUAL_CHART_EVIDENCE_PROVIDER_ID
            else ExtractionProvenance.AI_CHART_ANALYST
        ),
    }
    observations: list[ExtractedChartObservation] = [
        _observation(
            base,
            ObservationCategory.PRICE_STRUCTURE,
            "TRADINGVIEW_STRUCTURE",
            response.price_structure.value.value,
            response.price_structure.availability,
        )
    ]
    for item in response.moving_averages:
        interaction = {
            MovingAverageInteraction.RESISTANCE: "REJECTION",
            MovingAverageInteraction.CRISSCROSS: "NONE",
            MovingAverageInteraction.UNDETERMINABLE: "UNCLEAR",
        }.get(item.interaction, item.interaction.value)
        crisscross = (
            "UNCLEAR"
            if item.crisscross is CrisscrossBehaviour.UNDETERMINABLE
            else item.crisscross.value
        )
        relationship = (
            "UNCLEAR"
            if item.price_relationship is PriceRelationship.UNDETERMINABLE
            else item.price_relationship.value
        )
        slope = "UNCLEAR" if item.slope is MovingAverageSlope.NOT_VISIBLE else item.slope.value
        observations.append(_observation(
            base,
            ObservationCategory(item.indicator),
            item.indicator,
            "|".join((slope, relationship, interaction, crisscross)),
            item.availability,
            correlation_key=f"{response.timeframe.value}.{item.indicator}",
        ))
    observations.append(_observation(
        base,
        ObservationCategory.CANDLE_BEHAVIOUR,
        "CANDLE_CONTEXT",
        _candle_value(response.candle.state),
        response.candle.availability,
    ))
    observations.append(_observation(
        base,
        ObservationCategory.VOLUME_CONTEXT,
        "VOLUME_CONTEXT",
        _volume_value(response.volume),
        response.volume.availability,
    ))

    reference_levels = tuple(
        item for item in response.reference_levels
        if item.availability is ChartEvidenceAvailability.AVAILABLE
    )
    if reference_levels:
        observations.extend(
            _level_observation(base, ObservationCategory.REFERENCE_LEVELS, item, index)
            for index, item in enumerate(reference_levels, 1)
        )
    else:
        observations.append(_unavailable_observation(base, ObservationCategory.REFERENCE_LEVELS, "UNAVAILABLE"))

    visible_barriers = tuple(item for item in response.barriers if item.presence is BarrierPresence.YES)
    if visible_barriers:
        observations.extend(
            _barrier_observation(base, item, index)
            for index, item in enumerate(visible_barriers, 1)
        )
    else:
        observations.append(_unavailable_observation(base, ObservationCategory.STRUCTURAL_LEVELS, "UNAVAILABLE"))

    development = _deterministic_price_development(response.candle)
    if development is None:
        observations.append(_unavailable_observation(base, ObservationCategory.PRICE_DEVELOPMENT, "PRICE_DEVELOPMENT"))
    else:
        observations.append(_observation(
            base,
            ObservationCategory.PRICE_DEVELOPMENT,
            "PRICE_DEVELOPMENT",
            development,
            ChartEvidenceAvailability.AVAILABLE,
        ))

    pine_text = _pine_value(response.pine.displayed_text)
    if response.pine.availability is ChartEvidenceAvailability.AVAILABLE and pine_text is not None:
        observations.append(_observation(
            base,
            ObservationCategory.PINE,
            "PINE_DISPLAY",
            f"DISPLAY:{pine_text}",
            ChartEvidenceAvailability.AVAILABLE,
        ))
    else:
        observations.append(_unavailable_observation(base, ObservationCategory.PINE, "PINE_DISPLAY"))
    return tuple(observations)


def chart_revision(response: ChartEvidenceResponse) -> ChartRevisionIdentity:
    return ChartRevisionIdentity(response.timeframe, response.source_image_sha256)


def chart_evidence_response_to_dict(response: ChartEvidenceResponse) -> dict[str, object]:
    return {
        "schema_identity": response.schema_identity,
        "provider_identity": response.provider_identity,
        "model_identity": response.model_identity,
        "question_set_identity": response.question_set_identity,
        "request_timestamp": response.request_timestamp.isoformat(),
        "run_identity": response.run_identity,
        "canonical_instrument": response.canonical_instrument,
        "timeframe": response.timeframe.value,
        "observation_boundary": response.observation_boundary.isoformat(),
        "chart_template_identity": response.chart_template_identity,
        "source_image_sha256": response.source_image_sha256,
        "instrument_identity": _identity_to_dict(response.instrument_identity),
        "timeframe_identity": _identity_to_dict(response.timeframe_identity),
        "template_identity": _identity_to_dict(response.template_identity),
        "price_structure": {
            "availability": response.price_structure.availability.value,
            "value": response.price_structure.value.value,
            "swing_highs": list(response.price_structure.swing_highs),
            "swing_lows": list(response.price_structure.swing_lows),
            "consolidation_visible": response.price_structure.consolidation_visible.value,
            "breakout_visible": response.price_structure.breakout_visible.value,
            "breakdown_visible": response.price_structure.breakdown_visible.value,
        },
        "moving_averages": [
            {
                "indicator": item.indicator,
                "availability": item.availability.value,
                "slope": item.slope.value,
                "price_relationship": item.price_relationship.value,
                "interaction": item.interaction.value,
                "crisscross": item.crisscross.value,
            }
            for item in response.moving_averages
        ],
        "candle": {"availability": response.candle.availability.value, "state": response.candle.state.value},
        "volume": {
            "availability": response.volume.availability.value,
            "trend": response.volume.trend.value,
            "trend_direction_participation": response.volume.trend_direction_participation.value,
            "pullback_participation": response.volume.pullback_participation.value,
            "breakout_participation": response.volume.breakout_participation.value,
        },
        "reference_levels": [_reference_to_dict(item) for item in response.reference_levels],
        "barriers": [_barrier_to_dict(item) for item in response.barriers],
        "pine": {"availability": response.pine.availability.value, "displayed_text": response.pine.displayed_text},
        "contradictions": [item.value for item in response.contradictions],
        "undeterminable_questions": [item.value for item in response.undeterminable_questions],
    }


def chart_evidence_response_from_dict(payload: object) -> ChartEvidenceResponse:
    if type(payload) is not dict:
        raise ValueError("CHART_EVIDENCE_RESPONSE_SCHEMA_INVALID")
    try:
        _expect_keys(payload, {
            "schema_identity", "provider_identity", "model_identity",
            "question_set_identity", "request_timestamp", "run_identity",
            "canonical_instrument", "timeframe", "observation_boundary",
            "chart_template_identity", "source_image_sha256",
            "instrument_identity", "timeframe_identity", "template_identity",
            "price_structure", "moving_averages", "candle", "volume",
            "reference_levels", "barriers", "pine", "contradictions",
            "undeterminable_questions",
        })
        structure = payload["price_structure"]
        volume = payload["volume"]
        candle = payload["candle"]
        pine = payload["pine"]
        _expect_keys(structure, {
            "availability", "value", "swing_highs", "swing_lows",
            "consolidation_visible", "breakout_visible", "breakdown_visible",
        })
        _expect_keys(candle, {"availability", "state"})
        _expect_keys(volume, {
            "availability", "trend", "trend_direction_participation",
            "pullback_participation", "breakout_participation",
        })
        _expect_keys(pine, {"availability", "displayed_text"})
        return ChartEvidenceResponse(
            schema_identity=payload["schema_identity"],
            provider_identity=payload["provider_identity"],
            model_identity=payload["model_identity"],
            question_set_identity=payload["question_set_identity"],
            request_timestamp=datetime.fromisoformat(payload["request_timestamp"]),
            run_identity=payload["run_identity"],
            canonical_instrument=payload["canonical_instrument"],
            timeframe=ChartTimeframe(payload["timeframe"]),
            observation_boundary=datetime.fromisoformat(payload["observation_boundary"]),
            chart_template_identity=payload["chart_template_identity"],
            source_image_sha256=payload["source_image_sha256"],
            instrument_identity=_identity_from_dict(payload["instrument_identity"]),
            timeframe_identity=_identity_from_dict(payload["timeframe_identity"]),
            template_identity=_identity_from_dict(payload["template_identity"]),
            price_structure=PriceStructureEvidence(
                ChartEvidenceAvailability(structure["availability"]),
                PriceStructureValue(structure["value"]),
                tuple(float(item) for item in structure["swing_highs"]),
                tuple(float(item) for item in structure["swing_lows"]),
                TernaryVisibleState(structure["consolidation_visible"]),
                TernaryVisibleState(structure["breakout_visible"]),
                TernaryVisibleState(structure["breakdown_visible"]),
            ),
            moving_averages=tuple(_moving_average_from_dict(item) for item in payload["moving_averages"]),
            candle=CandleChartEvidence(
                ChartEvidenceAvailability(candle["availability"]),
                CandleAcceptanceState(candle["state"]),
            ),
            volume=VolumeChartEvidence(
                ChartEvidenceAvailability(volume["availability"]),
                VolumeTrend(volume["trend"]),
                ParticipationState(volume["trend_direction_participation"]),
                ParticipationState(volume["pullback_participation"]),
                ParticipationState(volume["breakout_participation"]),
            ),
            reference_levels=tuple(_reference_from_dict(item) for item in payload["reference_levels"]),
            barriers=tuple(_barrier_from_dict(item) for item in payload["barriers"]),
            pine=PineChartEvidence(
                ChartEvidenceAvailability(pine["availability"]),
                pine["displayed_text"],
            ),
            contradictions=tuple(ContradictionCode(item) for item in payload["contradictions"]),
            undeterminable_questions=tuple(ChartQuestionId(item) for item in payload["undeterminable_questions"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("CHART_EVIDENCE_RESPONSE_SCHEMA_INVALID") from error


def chart_evidence_provider_schema() -> dict[str, object]:
    """Strict schema supplied to external providers; provenance is adapter-owned."""

    availability = [item.value for item in ChartEvidenceAvailability]
    obj = lambda properties: {  # noqa: E731
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }
    identity = obj({
        "availability": {"type": "string", "enum": availability},
        "observed_value": {"type": "string"},
        "consistency": {"type": "string", "enum": [item.value for item in IdentityConsistency]},
    })
    nullable_number = {"type": ["number", "null"]}
    reference = obj({
        "identity": {"type": "string", "enum": [item.value for item in ReferenceLevelIdentity]},
        "availability": {"type": "string", "enum": availability},
        "interaction": {"type": "string", "enum": [item.value for item in LevelInteraction]},
        "significance": {"type": "string", "enum": [item.value for item in LevelSignificance]},
        "price": nullable_number,
        "zone_low": nullable_number,
        "zone_high": nullable_number,
    })
    barrier = obj({
        "presence": {"type": "string", "enum": [item.value for item in BarrierPresence]},
        "identity": {"type": "string", "enum": [item.value for item in ReferenceLevelIdentity]},
        "interaction": {"type": "string", "enum": [item.value for item in LevelInteraction]},
        "significance": {"type": "string", "enum": [item.value for item in LevelSignificance]},
        "relative_location": {"type": "string", "enum": [item.value for item in BarrierRelativeLocation]},
        "source": {"type": "string", "enum": ["REFERENCE_LEVEL", "STRUCTURAL_LEVEL", "SMA20", "SMA50", "SMA200"]},
        "price": nullable_number,
    })
    return obj({
        "instrument_identity": identity,
        "timeframe_identity": identity,
        "template_identity": identity,
        "price_structure": obj({
            "availability": {"type": "string", "enum": availability},
            "value": {"type": "string", "enum": [item.value for item in PriceStructureValue]},
            "swing_highs": {"type": "array", "items": {"type": "number"}},
            "swing_lows": {"type": "array", "items": {"type": "number"}},
            "consolidation_visible": {"type": "string", "enum": [item.value for item in TernaryVisibleState]},
            "breakout_visible": {"type": "string", "enum": [item.value for item in TernaryVisibleState]},
            "breakdown_visible": {"type": "string", "enum": [item.value for item in TernaryVisibleState]},
        }),
        "moving_averages": {"type": "array", "items": obj({
            "indicator": {"type": "string", "enum": ["SMA20", "SMA50", "SMA200"]},
            "availability": {"type": "string", "enum": availability},
            "slope": {"type": "string", "enum": [item.value for item in MovingAverageSlope]},
            "price_relationship": {"type": "string", "enum": [item.value for item in PriceRelationship]},
            "interaction": {"type": "string", "enum": [item.value for item in MovingAverageInteraction]},
            "crisscross": {"type": "string", "enum": [item.value for item in CrisscrossBehaviour]},
        })},
        "candle": obj({
            "availability": {"type": "string", "enum": availability},
            "state": {"type": "string", "enum": [item.value for item in CandleAcceptanceState]},
        }),
        "volume": obj({
            "availability": {"type": "string", "enum": availability},
            "trend": {"type": "string", "enum": [item.value for item in VolumeTrend]},
            "trend_direction_participation": {"type": "string", "enum": [item.value for item in ParticipationState]},
            "pullback_participation": {"type": "string", "enum": [item.value for item in ParticipationState]},
            "breakout_participation": {"type": "string", "enum": [item.value for item in ParticipationState]},
        }),
        "reference_levels": {"type": "array", "items": reference},
        "barriers": {"type": "array", "items": barrier},
        "pine": obj({
            "availability": {"type": "string", "enum": availability},
            "displayed_text": {"type": "string"},
        }),
        "contradictions": {"type": "array", "items": {"type": "string", "enum": [item.value for item in ContradictionCode]}},
        "undeterminable_questions": {"type": "array", "items": {"type": "string", "enum": [item.value for item in ChartQuestionId]}},
    })


def _identity_to_dict(item: IdentityEvidence) -> dict[str, str]:
    return {
        "availability": item.availability.value,
        "observed_value": item.observed_value,
        "consistency": item.consistency.value,
    }


def _identity_from_dict(item: object) -> IdentityEvidence:
    if type(item) is not dict:
        raise ValueError("CHART_IDENTITY_SCHEMA_INVALID")
    _expect_keys(item, {"availability", "observed_value", "consistency"})
    return IdentityEvidence(
        ChartEvidenceAvailability(item["availability"]),
        item["observed_value"],
        IdentityConsistency(item["consistency"]),
    )


def _moving_average_from_dict(item: object) -> MovingAverageChartEvidence:
    if type(item) is not dict:
        raise ValueError("CHART_MA_SCHEMA_INVALID")
    _expect_keys(item, {
        "indicator", "availability", "slope", "price_relationship",
        "interaction", "crisscross",
    })
    return MovingAverageChartEvidence(
        item["indicator"],
        ChartEvidenceAvailability(item["availability"]),
        MovingAverageSlope(item["slope"]),
        PriceRelationship(item["price_relationship"]),
        MovingAverageInteraction(item["interaction"]),
        CrisscrossBehaviour(item["crisscross"]),
    )


def _reference_to_dict(item: ReferenceLevelChartEvidence) -> dict[str, object]:
    return {
        "identity": item.identity.value,
        "availability": item.availability.value,
        "interaction": item.interaction.value,
        "significance": item.significance.value,
        "price": item.price,
        "zone_low": item.zone_low,
        "zone_high": item.zone_high,
    }


def _reference_from_dict(item: object) -> ReferenceLevelChartEvidence:
    if type(item) is not dict:
        raise ValueError("CHART_REFERENCE_SCHEMA_INVALID")
    _expect_keys(item, {
        "identity", "availability", "interaction", "significance",
        "price", "zone_low", "zone_high",
    })
    return ReferenceLevelChartEvidence(
        ReferenceLevelIdentity(item["identity"]),
        ChartEvidenceAvailability(item["availability"]),
        LevelInteraction(item["interaction"]),
        LevelSignificance(item["significance"]),
        _optional_float(item["price"]),
        _optional_float(item["zone_low"]),
        _optional_float(item["zone_high"]),
    )


def _barrier_to_dict(item: BarrierChartEvidence) -> dict[str, object]:
    return {
        "presence": item.presence.value,
        "identity": item.identity.value,
        "interaction": item.interaction.value,
        "significance": item.significance.value,
        "relative_location": item.relative_location.value,
        "source": item.source,
        "price": item.price,
    }


def _barrier_from_dict(item: object) -> BarrierChartEvidence:
    if type(item) is not dict:
        raise ValueError("CHART_BARRIER_SCHEMA_INVALID")
    _expect_keys(item, {
        "presence", "identity", "interaction", "significance",
        "relative_location", "source", "price",
    })
    return BarrierChartEvidence(
        BarrierPresence(item["presence"]),
        ReferenceLevelIdentity(item["identity"]),
        LevelInteraction(item["interaction"]),
        LevelSignificance(item["significance"]),
        BarrierRelativeLocation(item["relative_location"]),
        item["source"],
        _optional_float(item["price"]),
    )


def _observation(
    base: dict[str, object],
    category: ObservationCategory,
    identity: str,
    value: str,
    availability: ChartEvidenceAvailability,
    **extra: object,
) -> ExtractedChartObservation:
    internal_availability = (
        EvidenceAvailability.AVAILABLE
        if availability is ChartEvidenceAvailability.AVAILABLE
        else EvidenceAvailability.UNAVAILABLE
    )
    if internal_availability is EvidenceAvailability.UNAVAILABLE:
        value = "UNAVAILABLE"
        extra = {}
    return ExtractedChartObservation(
        **base,
        category=category,
        semantic_identity=identity,
        evidence_value=value,
        availability=internal_availability,
        **extra,
    )


def _unavailable_observation(
    base: dict[str, object],
    category: ObservationCategory,
    identity: str,
) -> ExtractedChartObservation:
    return _observation(base, category, identity, "UNAVAILABLE", ChartEvidenceAvailability.UNAVAILABLE)


def _level_observation(
    base: dict[str, object],
    category: ObservationCategory,
    item: ReferenceLevelChartEvidence,
    index: int,
) -> ExtractedChartObservation:
    interaction = "UNCLEAR" if item.interaction is LevelInteraction.UNDETERMINABLE else item.interaction.value
    significance = (
        LevelSignificance.UNKNOWN
        if interaction == "UNCLEAR"
        else LevelSignificance.PARTIAL
        if interaction in {"INTERACTING", "VISIBLE_NOT_RELEVANT"}
        else item.significance
    )
    return _observation(
        base,
        category,
        item.identity.value,
        f"{interaction}|{significance.value}",
        item.availability,
        price=item.price,
        zone_low=item.zone_low,
        zone_high=item.zone_high,
        correlation_key=f"{base['timeframe']}.{item.identity.value}.{index}",
    )


def _barrier_observation(
    base: dict[str, object],
    item: BarrierChartEvidence,
    index: int,
) -> ExtractedChartObservation:
    interaction = (
        "UNCLEAR"
        if item.interaction is LevelInteraction.UNDETERMINABLE
        else item.interaction.value
    )
    significance = (
        "UNKNOWN"
        if interaction == "UNCLEAR"
        else "PARTIAL"
        if interaction in {"INTERACTING", "VISIBLE_NOT_RELEVANT"}
        else item.significance.value
    )
    return _observation(
        base,
        ObservationCategory.STRUCTURAL_LEVELS,
        item.identity.value,
        f"{interaction}|{significance}",
        ChartEvidenceAvailability.AVAILABLE,
        price=item.price,
        correlation_key=f"{base['timeframe']}.BARRIER.{item.identity.value}.{index}",
    )


def _candle_value(value: CandleAcceptanceState) -> str:
    return {
        CandleAcceptanceState.ACCEPTED: "ACCEPTANCE",
        CandleAcceptanceState.REJECTED: "REJECTION",
        CandleAcceptanceState.CLOSE_BACK_INSIDE: "CLOSE_BACK_INSIDE_RANGE",
    }.get(value, value.value)


def _volume_value(value: VolumeChartEvidence) -> str:
    if value.breakout_participation is ParticipationState.INCREASED:
        return "BREAK_PARTICIPATION_INCREASED"
    if value.trend_direction_participation is ParticipationState.SIZEABLE:
        return "RESUMPTION_PARTICIPATION_SIZEABLE"
    if value.pullback_participation is ParticipationState.QUIETER:
        return "COUNTERTREND_PARTICIPATION_QUIETER"
    if ParticipationState.WEAK in {
        value.trend_direction_participation,
        value.pullback_participation,
        value.breakout_participation,
    }:
        return "WEAK_PARTICIPATION"
    return "QUALITATIVE_MIXED"


def _deterministic_price_development(value: CandleChartEvidence) -> str | None:
    if value.availability is not ChartEvidenceAvailability.AVAILABLE:
        return None
    return {
        CandleAcceptanceState.ACCEPTED: "READY_CONTEXT",
        CandleAcceptanceState.RETEST_HELD: "READY_CONTEXT",
        CandleAcceptanceState.RETEST_DEVELOPING: "RETEST_DEVELOPING",
        CandleAcceptanceState.REJECTED: "WEAKENING_FOLLOW_THROUGH",
        CandleAcceptanceState.CLOSE_BACK_INSIDE: "SETUP_INVALIDATED",
        CandleAcceptanceState.INDECISION: "WEAKENING_FOLLOW_THROUGH",
    }.get(value.state)


def _pine_value(value: str) -> str | None:
    normalized = re.sub(r"\s+", " ", value.strip().upper())
    return normalized if re.fullmatch(r"[A-Z0-9_ .,:;()/-]{1,160}", normalized) else None


def _optional_float(value: object) -> float | None:
    return None if value is None else float(value)


def _aware(value: datetime) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _finite(value: object) -> bool:
    return type(value) is float and math.isfinite(value)


def _code(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[A-Z0-9_]{1,128}", value) is not None


def _provider_code(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[A-Z0-9_.:-]{3,128}", value) is not None


def _expect_keys(value: object, expected: set[str]) -> None:
    if type(value) is not dict or set(value) != expected:
        raise ValueError("CHART_EVIDENCE_RESPONSE_SCHEMA_INVALID")


__all__ = [
    "BarrierChartEvidence",
    "BarrierPresence",
    "BarrierRelativeLocation",
    "CHART_EVIDENCE_SCHEMA_V1_ID",
    "CHART_QUESTION_SET_V1_ID",
    "CandleAcceptanceState",
    "CandleChartEvidence",
    "ChartEvidenceAvailability",
    "ChartEvidenceProvider",
    "ChartEvidenceProviderError",
    "ChartEvidenceProviderFailureCode",
    "ChartEvidenceRequest",
    "ChartEvidenceResponse",
    "ChartQuestionId",
    "ChartThesisContext",
    "ContradictionCode",
    "CrisscrossBehaviour",
    "FROZEN_CHART_QUESTION_SET_V1",
    "IdentityConsistency",
    "IdentityEvidence",
    "LevelInteraction",
    "LevelSignificance",
    "MANUAL_CHART_EVIDENCE_PROVIDER_ID",
    "ManualChartEvidenceProvider",
    "MovingAverageChartEvidence",
    "MovingAverageInteraction",
    "MovingAverageSlope",
    "OPENAI_CHART_EVIDENCE_PROVIDER_ID",
    "ParticipationState",
    "PineChartEvidence",
    "PriceRelationship",
    "PriceStructureEvidence",
    "PriceStructureValue",
    "ReferenceLevelChartEvidence",
    "ReferenceLevelIdentity",
    "TernaryVisibleState",
    "VolumeChartEvidence",
    "VolumeTrend",
    "chart_evidence_provider_schema",
    "chart_evidence_response_from_dict",
    "chart_evidence_response_to_dict",
    "chart_revision",
    "response_to_observations",
]
