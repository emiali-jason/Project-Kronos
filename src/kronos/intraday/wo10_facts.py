"""Family-neutral completed-candle facts for the WO-10 successor family.

The module measures evidence only.  It deliberately has no WO-10 classifier,
direction consequence, Entry, Trade Construction, Risk, or broker authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json
from typing import Mapping, Sequence, TypeAlias

from kronos.intraday.context import ReferenceRelationship, Slice1EContext
from kronos.intraday.contracts import DataAvailability, IntradayTimeframe
from kronos.intraday.historical_semantic import GovernedHistoricalCandlePayload
from kronos.intraday.structure import StructuralEvidence, StructuralFact, StructuralFactType
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo10 import Wo10ContractError, market_family_for_subject


WO10_RSI_FACT_IDENTITY = "KRONOS-INTRADAY-WO10-RSI-FACT-V1"
WO10_RSI_CALCULATION_IDENTITY = "KRONOS-TRADINGVIEW-WILDER-RMA-RSI-14-V1"
WO10_SMA_FACTS_IDENTITY = "KRONOS-INTRADAY-WO10-SMA-FACTS-V1"
WO10_SMA_CALCULATION_IDENTITY = "KRONOS-SIMPLE-MOVING-AVERAGE-20-50-200-V1"
WO10_LOCATION_FACTS_IDENTITY = "KRONOS-INTRADAY-WO10-STRUCTURAL-LOCATION-V1"
WO10_VOLUME_FACT_IDENTITY = "KRONOS-INTRADAY-WO10-VOLUME-FACT-V1"
WO10_SAME_TIME_VOLUME_IDENTITY = (
    "KRONOS-INTRADAY-WO10-SAME-TIME-SESSION-VOLUME-V1"
)
WO10_EVENT_VOLUME_IDENTITY = "KRONOS-INTRADAY-WO10-EVENT-VOLUME-BINDING-V1"
WO10_FACT_VERSION = "1.0.0"
WO10_RSI_PERIOD = 14
WO10_SMA_PERIODS = (20, 50, 200)
WO10_SMA_SLOPE_COMPARISON_BARS = 5
WO10_VOLUME_LOOKBACK = 20
WO10_VOLUME_LOOKBACK_IDENTITY = (
    "KRONOS-COMPLETED-VOLUME-ROLLING-BASELINE-20-V1"
)


class Wo10RsiCondition(StrEnum):
    OVERBOUGHT = "OVERBOUGHT"
    OVERSOLD = "OVERSOLD"
    MIDRANGE = "MIDRANGE"
    UNAVAILABLE = "UNAVAILABLE"


class Wo10PriceRelationship(StrEnum):
    ABOVE = "ABOVE"
    BELOW = "BELOW"
    AT = "AT"
    UNAVAILABLE = "UNAVAILABLE"


class Wo10SmaSlope(StrEnum):
    RISING = "RISING"
    FALLING = "FALLING"
    FLAT_EXACT = "FLAT_EXACT"
    UNAVAILABLE = "UNAVAILABLE"


class Wo10SmaStack(StrEnum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    MIXED = "MIXED"
    UNAVAILABLE = "UNAVAILABLE"


class Wo10ExactChange(StrEnum):
    CONVERGING = "CONVERGING"
    DIVERGING = "DIVERGING"
    UNCHANGED = "UNCHANGED"
    UNAVAILABLE = "UNAVAILABLE"


class Wo10RecentSeparation(StrEnum):
    ALL_ABOVE = "ALL_ABOVE"
    ALL_BELOW = "ALL_BELOW"
    MIXED_OR_AT = "MIXED_OR_AT"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class Wo10CandleSeries:
    """Exact completed-candle selection and contract lineage for one calculation."""

    series_identity: str
    integrity_identity: str
    canonical_subject_identity: str
    market_family: IntradayMarketFamily
    timeframe: IntradayTimeframe
    observation_boundary: datetime
    mapping_identity: str
    actual_contract_identity: str | None
    roll_lineage_identity: str | None
    candles: tuple[GovernedHistoricalCandlePayload, ...]
    schema_identity: str = "KRONOS-INTRADAY-WO10-CANDLE-SERIES-V1"
    schema_version: str = WO10_FACT_VERSION

    def __post_init__(self) -> None:
        data = _without(self, "series_identity", "integrity_identity")
        candle_key = tuple((item.candle_start, item.candle_end) for item in self.candles)
        sessions = tuple(item.market_session_identity for item in self.candles)
        mcx = self.market_family is IntradayMarketFamily.MCX
        if (
            not self.candles
            or any(type(item) is not GovernedHistoricalCandlePayload for item in self.candles)
            or type(self.market_family) is not IntradayMarketFamily
            or market_family_for_subject(self.canonical_subject_identity) is not self.market_family
            or type(self.timeframe) is not IntradayTimeframe
            or not _aware(self.observation_boundary)
            or not _text(self.mapping_identity)
            or any(item.canonical_subject_identity != self.canonical_subject_identity for item in self.candles)
            or any(item.timeframe is not self.timeframe for item in self.candles)
            or any(item.observation_boundary != self.observation_boundary for item in self.candles)
            or candle_key != tuple(sorted(candle_key))
            or len({item.candle_identity for item in self.candles}) != len(self.candles)
            or (mcx and (not _text(self.actual_contract_identity) or not _text(self.roll_lineage_identity)))
            or (not mcx and (self.actual_contract_identity is not None or self.roll_lineage_identity is not None))
            or (mcx and len({item.provider_source_identity for item in self.candles}) != 1)
            or not all(_text(item) for item in sessions)
            or self.schema_version != WO10_FACT_VERSION
            or self.series_identity != _identity("INTRADAY-WO10-CANDLE-SERIES-", data)
            or self.integrity_identity != _identity("INTEGRITY-INTRADAY-WO10-CANDLE-SERIES-", data)
        ):
            raise Wo10ContractError("WO10_CANDLE_SERIES_INVALID")

    @property
    def source_candle_identities(self) -> tuple[str, ...]:
        return tuple(item.candle_identity for item in self.candles)

    @property
    def source_candle_integrities(self) -> tuple[str, ...]:
        return tuple(item.integrity_identity for item in self.candles)

    @property
    def market_session_identities(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item.market_session_identity for item in self.candles))


def create_wo10_candle_series(
    *,
    canonical_subject_identity: str,
    market_family: IntradayMarketFamily,
    timeframe: IntradayTimeframe,
    observation_boundary: datetime,
    mapping_identity: str,
    candles: Sequence[GovernedHistoricalCandlePayload],
    actual_contract_identity: str | None = None,
    roll_lineage_identity: str | None = None,
) -> Wo10CandleSeries:
    ordered = tuple(sorted(candles, key=lambda item: (item.candle_start, item.candle_end)))
    values = {
        "canonical_subject_identity": canonical_subject_identity,
        "market_family": market_family,
        "timeframe": timeframe,
        "observation_boundary": observation_boundary,
        "mapping_identity": mapping_identity,
        "actual_contract_identity": actual_contract_identity,
        "roll_lineage_identity": roll_lineage_identity,
        "candles": ordered,
        "schema_identity": "KRONOS-INTRADAY-WO10-CANDLE-SERIES-V1",
        "schema_version": WO10_FACT_VERSION,
    }
    return Wo10CandleSeries(
        series_identity=_identity("INTRADAY-WO10-CANDLE-SERIES-", values),
        integrity_identity=_identity("INTEGRITY-INTRADAY-WO10-CANDLE-SERIES-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo10RsiFact:
    evidence_identity: str
    integrity_identity: str
    series_identity: str
    canonical_subject_identity: str
    market_family: IntradayMarketFamily
    timeframe: IntradayTimeframe
    observation_boundary: datetime
    market_session_identities: tuple[str, ...]
    source_candle_identities: tuple[str, ...]
    source_candle_integrities: tuple[str, ...]
    availability: DataAvailability
    value: Decimal | None
    condition: Wo10RsiCondition
    period: int = WO10_RSI_PERIOD
    calculation_identity: str = WO10_RSI_CALCULATION_IDENTITY
    schema_identity: str = WO10_RSI_FACT_IDENTITY
    schema_version: str = WO10_FACT_VERSION

    def __post_init__(self) -> None:
        data = _without(self, "evidence_identity", "integrity_identity")
        available = self.availability is DataAvailability.AVAILABLE
        if (
            type(self.market_family) is not IntradayMarketFamily
            or self.timeframe not in {
                IntradayTimeframe.ONE_HOUR,
                IntradayTimeframe.FIFTEEN_MINUTES,
                IntradayTimeframe.FIVE_MINUTES,
            }
            or not _aware(self.observation_boundary)
            or not self.market_session_identities
            or len(self.source_candle_identities) != len(self.source_candle_integrities)
            or available != (self.value is not None)
            or available != (self.condition is not Wo10RsiCondition.UNAVAILABLE)
            or (available and (self.value < 0 or self.value > 100))
            or self.period != WO10_RSI_PERIOD
            or self.calculation_identity != WO10_RSI_CALCULATION_IDENTITY
            or self.schema_identity != WO10_RSI_FACT_IDENTITY
            or self.schema_version != WO10_FACT_VERSION
            or self.evidence_identity != _identity("INTRADAY-WO10-RSI-", data)
            or self.integrity_identity != _identity("INTEGRITY-INTRADAY-WO10-RSI-", data)
        ):
            raise Wo10ContractError("WO10_RSI_FACT_INVALID")


def classify_wo10_rsi(
    timeframe: IntradayTimeframe, value: Decimal
) -> Wo10RsiCondition:
    value = _decimal(value)
    thresholds = {
        IntradayTimeframe.ONE_HOUR: (Decimal(70), Decimal(30)),
        IntradayTimeframe.FIFTEEN_MINUTES: (Decimal(70), Decimal(30)),
        IntradayTimeframe.FIVE_MINUTES: (Decimal(80), Decimal(20)),
    }
    if timeframe not in thresholds or value < 0 or value > 100:
        raise Wo10ContractError("WO10_RSI_CLASSIFICATION_INPUT_INVALID")
    overbought, oversold = thresholds[timeframe]
    if value >= overbought:
        return Wo10RsiCondition.OVERBOUGHT
    if value <= oversold:
        return Wo10RsiCondition.OVERSOLD
    return Wo10RsiCondition.MIDRANGE


def build_wo10_rsi_fact(series: Wo10CandleSeries) -> Wo10RsiFact:
    if type(series) is not Wo10CandleSeries or series.timeframe is IntradayTimeframe.DAILY:
        raise Wo10ContractError("WO10_RSI_REQUEST_INVALID")
    selected = series.candles
    value = _wilder_rsi(tuple(item.close for item in selected), WO10_RSI_PERIOD)
    availability = DataAvailability.AVAILABLE if value is not None else DataAvailability.UNAVAILABLE
    values = {
        "series_identity": series.series_identity,
        "canonical_subject_identity": series.canonical_subject_identity,
        "market_family": series.market_family,
        "timeframe": series.timeframe,
        "observation_boundary": series.observation_boundary,
        "market_session_identities": series.market_session_identities,
        "source_candle_identities": series.source_candle_identities,
        "source_candle_integrities": series.source_candle_integrities,
        "availability": availability,
        "value": value,
        "condition": (
            classify_wo10_rsi(series.timeframe, value)
            if value is not None else Wo10RsiCondition.UNAVAILABLE
        ),
        "period": WO10_RSI_PERIOD,
        "calculation_identity": WO10_RSI_CALCULATION_IDENTITY,
        "schema_identity": WO10_RSI_FACT_IDENTITY,
        "schema_version": WO10_FACT_VERSION,
    }
    return Wo10RsiFact(
        evidence_identity=_identity("INTRADAY-WO10-RSI-", values),
        integrity_identity=_identity("INTEGRITY-INTRADAY-WO10-RSI-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo10SmaFact:
    period: int
    value_availability: DataAvailability
    value: Decimal | None
    prior_comparison_value: Decimal | None
    numerical_slope: Decimal | None
    slope: Wo10SmaSlope
    price_relationship: Wo10PriceRelationship
    interaction: str
    source_candle_identities: tuple[str, ...]

    def __post_init__(self) -> None:
        available = self.value_availability is DataAvailability.AVAILABLE
        if (
            self.period not in WO10_SMA_PERIODS
            or available != (self.value is not None)
            or (self.numerical_slope is None) != (self.prior_comparison_value is None)
            or (self.numerical_slope is None) != (self.slope is Wo10SmaSlope.UNAVAILABLE)
            or available != (self.price_relationship is not Wo10PriceRelationship.UNAVAILABLE)
            or self.interaction not in {"RANGE_TOUCH", "NO_RANGE_TOUCH", "UNAVAILABLE"}
            or not self.source_candle_identities
        ):
            raise Wo10ContractError("WO10_SMA_FACT_INVALID")


@dataclass(frozen=True, slots=True)
class Wo10SmaPairChange:
    pair_identity: str
    current_distance: Decimal | None
    prior_distance: Decimal | None
    exact_change: Wo10ExactChange

    def __post_init__(self) -> None:
        available = self.exact_change is not Wo10ExactChange.UNAVAILABLE
        if (
            self.pair_identity not in {"SMA20_SMA50", "SMA20_SMA200", "SMA50_SMA200"}
            or available != (self.current_distance is not None and self.prior_distance is not None)
        ):
            raise Wo10ContractError("WO10_SMA_PAIR_CHANGE_INVALID")


@dataclass(frozen=True, slots=True)
class Wo10SmaFacts:
    evidence_identity: str
    integrity_identity: str
    series_identity: str
    canonical_subject_identity: str
    market_family: IntradayMarketFamily
    timeframe: IntradayTimeframe
    observation_boundary: datetime
    market_session_identities: tuple[str, ...]
    source_candle_identities: tuple[str, ...]
    source_candle_integrities: tuple[str, ...]
    averages: tuple[Wo10SmaFact, ...]
    stack: Wo10SmaStack
    crisscross20_count: int | None
    recent_separation: Wo10RecentSeparation
    pair_changes: tuple[Wo10SmaPairChange, ...]
    policy_unresolved: tuple[str, ...]
    calculation_identity: str = WO10_SMA_CALCULATION_IDENTITY
    schema_identity: str = WO10_SMA_FACTS_IDENTITY
    schema_version: str = WO10_FACT_VERSION

    def __post_init__(self) -> None:
        data = _without(self, "evidence_identity", "integrity_identity")
        if (
            type(self.market_family) is not IntradayMarketFamily
            or type(self.timeframe) is not IntradayTimeframe
            or not _aware(self.observation_boundary)
            or tuple(item.period for item in self.averages) != WO10_SMA_PERIODS
            or any(type(item) is not Wo10SmaFact for item in self.averages)
            or type(self.stack) is not Wo10SmaStack
            or (self.crisscross20_count is not None and self.crisscross20_count < 0)
            or type(self.recent_separation) is not Wo10RecentSeparation
            or tuple(item.pair_identity for item in self.pair_changes)
            != ("SMA20_SMA50", "SMA20_SMA200", "SMA50_SMA200")
            or self.policy_unresolved != (
                "MATERIAL_CRISSCROSS_THRESHOLD",
                "MATERIAL_SEPARATION_THRESHOLD",
            )
            or self.calculation_identity != WO10_SMA_CALCULATION_IDENTITY
            or self.evidence_identity != _identity("INTRADAY-WO10-SMA-FACTS-", data)
            or self.integrity_identity != _identity("INTEGRITY-INTRADAY-WO10-SMA-FACTS-", data)
        ):
            raise Wo10ContractError("WO10_SMA_FACTS_INVALID")


def build_wo10_sma_facts(series: Wo10CandleSeries) -> Wo10SmaFacts:
    if type(series) is not Wo10CandleSeries:
        raise Wo10ContractError("WO10_SMA_REQUEST_INVALID")
    closes = tuple(item.close for item in series.candles)
    current = series.candles[-1]
    averages: list[Wo10SmaFact] = []
    by_period: dict[int, tuple[Decimal | None, Decimal | None]] = {}
    for period in WO10_SMA_PERIODS:
        value = _sma(closes, period)
        prior = _sma(closes[:-WO10_SMA_SLOPE_COMPARISON_BARS], period)
        by_period[period] = (value, prior)
        numerical = None if value is None or prior is None else value - prior
        slope = (
            Wo10SmaSlope.UNAVAILABLE if numerical is None
            else Wo10SmaSlope.RISING if numerical > 0
            else Wo10SmaSlope.FALLING if numerical < 0
            else Wo10SmaSlope.FLAT_EXACT
        )
        relationship = (
            Wo10PriceRelationship.UNAVAILABLE if value is None
            else _price_relationship(current.close, value)
        )
        interaction = (
            "UNAVAILABLE" if value is None
            else "RANGE_TOUCH" if current.low <= value <= current.high
            else "NO_RANGE_TOUCH"
        )
        source = tuple(item.candle_identity for item in series.candles[-period:])
        if not source:
            source = (series.candles[-1].candle_identity,)
        averages.append(Wo10SmaFact(
            period=period,
            value_availability=(DataAvailability.AVAILABLE if value is not None else DataAvailability.UNAVAILABLE),
            value=value,
            prior_comparison_value=prior,
            numerical_slope=numerical,
            slope=slope,
            price_relationship=relationship,
            interaction=interaction,
            source_candle_identities=source,
        ))
    values = tuple(by_period[period][0] for period in WO10_SMA_PERIODS)
    stack = (
        Wo10SmaStack.UNAVAILABLE if any(item is None for item in values)
        else Wo10SmaStack.BULLISH if values[0] > values[1] > values[2]
        else Wo10SmaStack.BEARISH if values[0] < values[1] < values[2]
        else Wo10SmaStack.MIXED
    )
    crisscross, separation = _sma20_price_organization(series.candles)
    pair_changes = tuple(
        _sma_pair_change(first, second, by_period)
        for first, second in ((20, 50), (20, 200), (50, 200))
    )
    fields = {
        "series_identity": series.series_identity,
        "canonical_subject_identity": series.canonical_subject_identity,
        "market_family": series.market_family,
        "timeframe": series.timeframe,
        "observation_boundary": series.observation_boundary,
        "market_session_identities": series.market_session_identities,
        "source_candle_identities": series.source_candle_identities,
        "source_candle_integrities": series.source_candle_integrities,
        "averages": tuple(averages),
        "stack": stack,
        "crisscross20_count": crisscross,
        "recent_separation": separation,
        "pair_changes": pair_changes,
        "policy_unresolved": (
            "MATERIAL_CRISSCROSS_THRESHOLD",
            "MATERIAL_SEPARATION_THRESHOLD",
        ),
        "calculation_identity": WO10_SMA_CALCULATION_IDENTITY,
        "schema_identity": WO10_SMA_FACTS_IDENTITY,
        "schema_version": WO10_FACT_VERSION,
    }
    return Wo10SmaFacts(
        evidence_identity=_identity("INTRADAY-WO10-SMA-FACTS-", fields),
        integrity_identity=_identity("INTEGRITY-INTRADAY-WO10-SMA-FACTS-", fields),
        **fields,
    )


@dataclass(frozen=True, slots=True)
class Wo10LevelFact:
    reference_name: str
    reference_value: Decimal | None
    relationship: Wo10PriceRelationship
    source_identity: str

    def __post_init__(self) -> None:
        if (
            not _text(self.reference_name)
            or not _text(self.source_identity)
            or (
                self.reference_value is None
                and self.relationship is not Wo10PriceRelationship.UNAVAILABLE
            )
        ):
            raise Wo10ContractError("WO10_LEVEL_FACT_INVALID")


@dataclass(frozen=True, slots=True)
class Wo10StructuralLocationFacts:
    evidence_identity: str
    integrity_identity: str
    canonical_subject_identity: str
    market_family: IntradayMarketFamily
    observation_boundary: datetime
    market_session_identity: str
    mapping_identity: str
    actual_contract_identity: str | None
    roll_lineage_identity: str | None
    context_evidence_identity: str
    context_integrity_identity: str
    levels: tuple[Wo10LevelFact, ...]
    structural_evidence_identities: tuple[str, ...]
    structural_evidence_integrities: tuple[str, ...]
    implemented_interactions: tuple[str, ...]
    policy_unresolved: tuple[str, ...]
    schema_identity: str = WO10_LOCATION_FACTS_IDENTITY
    schema_version: str = WO10_FACT_VERSION

    def __post_init__(self) -> None:
        data = _without(self, "evidence_identity", "integrity_identity")
        mcx = self.market_family is IntradayMarketFamily.MCX
        if (
            market_family_for_subject(self.canonical_subject_identity) is not self.market_family
            or not _aware(self.observation_boundary)
            or not all(_text(item) for item in (
                self.market_session_identity,
                self.mapping_identity,
                self.context_evidence_identity,
                self.context_integrity_identity,
            ))
            or (mcx and (not _text(self.actual_contract_identity) or not _text(self.roll_lineage_identity)))
            or (not mcx and (self.actual_contract_identity is not None or self.roll_lineage_identity is not None))
            or any(type(item) is not Wo10LevelFact for item in self.levels)
            or len(self.structural_evidence_identities) != len(self.structural_evidence_integrities)
            or self.policy_unresolved != (
                "APPROACH_TOLERANCE",
                "FAILURE_QUALIFICATION",
                "HOLD_QUALIFICATION",
                "REJECTION_QUALIFICATION",
            )
            or self.evidence_identity != _identity("INTRADAY-WO10-LOCATION-", data)
            or self.integrity_identity != _identity("INTEGRITY-INTRADAY-WO10-LOCATION-", data)
        ):
            raise Wo10ContractError("WO10_STRUCTURAL_LOCATION_INVALID")


def build_wo10_structural_location_facts(
    *,
    context: Slice1EContext,
    structural_evidence: Sequence[StructuralEvidence] = (),
    actual_contract_identity: str | None = None,
    roll_lineage_identity: str | None = None,
) -> Wo10StructuralLocationFacts:
    if type(context) is not Slice1EContext:
        raise Wo10ContractError("WO10_STRUCTURAL_LOCATION_REQUEST_INVALID")
    evidence = tuple(structural_evidence)
    if any(
        type(item) is not StructuralEvidence
        or item.instrument.mapping_identity != context.instrument.mapping_identity
        or item.instrument.canonical_instrument_id != context.instrument.canonical_instrument_id
        or item.observation_boundary != context.run.observation_boundary
        or item.timeframe not in {IntradayTimeframe.ONE_HOUR, IntradayTimeframe.FIFTEEN_MINUTES}
        for item in evidence
    ):
        raise Wo10ContractError("WO10_STRUCTURAL_LOCATION_LINEAGE_MISMATCH")
    previous = context.previous_session
    pivot = context.classic_pivots
    cpr = context.cpr
    definitions = (
        ("PDH", previous.pdh, previous.evidence_identity),
        ("PDL", previous.pdl, previous.evidence_identity),
        ("PREVIOUS_CLOSE", previous.close, previous.evidence_identity),
        ("P", pivot.p, pivot.evidence_identity),
        ("R1", pivot.r1, pivot.evidence_identity),
        ("R2", pivot.r2, pivot.evidence_identity),
        ("R3", pivot.r3, pivot.evidence_identity),
        ("R4", pivot.r4, pivot.evidence_identity),
        ("S1", pivot.s1, pivot.evidence_identity),
        ("S2", pivot.s2, pivot.evidence_identity),
        ("S3", pivot.s3, pivot.evidence_identity),
        ("S4", pivot.s4, pivot.evidence_identity),
        ("CPR_PIVOT", cpr.pivot, cpr.evidence_identity),
        ("CPR_LOWER", cpr.lower, cpr.evidence_identity),
        ("CPR_UPPER", cpr.upper, cpr.evidence_identity),
        ("CPR_WIDTH", cpr.width, cpr.evidence_identity),
    )
    levels = tuple(Wo10LevelFact(
        reference_name=name,
        reference_value=value,
        relationship=(
            Wo10PriceRelationship.UNAVAILABLE
            if value is None or context.current_price is None or name == "CPR_WIDTH"
            else _price_relationship(context.current_price, value)
        ),
        source_identity=source,
    ) for name, value, source in definitions)
    implemented = tuple(sorted({
        fact.fact_type.value
        for item in evidence for fact in item.facts
        if fact.fact_type in {
            StructuralFactType.BOUNDARY_BREAK_ABOVE,
            StructuralFactType.BOUNDARY_BREAK_BELOW,
            StructuralFactType.CLOSE_ABOVE_BOUNDARY,
            StructuralFactType.CLOSE_AT_BOUNDARY,
            StructuralFactType.CLOSE_BACK_THROUGH,
            StructuralFactType.CLOSE_BELOW_BOUNDARY,
            StructuralFactType.EXACT_BOUNDARY_TOUCH,
            StructuralFactType.RETEST_FROM_ABOVE,
            StructuralFactType.RETEST_FROM_BELOW,
        }
    }))
    schedule = previous.previous_schedule
    session_identity = (
        schedule.session_id if schedule is not None
        else f"UNAVAILABLE-PREVIOUS-SESSION-{previous.current_trading_date.isoformat()}"
    )
    family = market_family_for_subject(context.instrument.canonical_instrument_id)
    values = {
        "canonical_subject_identity": context.instrument.canonical_instrument_id,
        "market_family": family,
        "observation_boundary": context.run.observation_boundary.observed_at,
        "market_session_identity": session_identity,
        "mapping_identity": context.instrument.mapping_identity,
        "actual_contract_identity": actual_contract_identity,
        "roll_lineage_identity": roll_lineage_identity,
        "context_evidence_identity": context.evidence_id,
        "context_integrity_identity": context.integrity_identity,
        "levels": levels,
        "structural_evidence_identities": tuple(item.evidence_id for item in evidence),
        "structural_evidence_integrities": tuple(item.integrity_identity for item in evidence),
        "implemented_interactions": implemented,
        "policy_unresolved": (
            "APPROACH_TOLERANCE",
            "FAILURE_QUALIFICATION",
            "HOLD_QUALIFICATION",
            "REJECTION_QUALIFICATION",
        ),
        "schema_identity": WO10_LOCATION_FACTS_IDENTITY,
        "schema_version": WO10_FACT_VERSION,
    }
    return Wo10StructuralLocationFacts(
        evidence_identity=_identity("INTRADAY-WO10-LOCATION-", values),
        integrity_identity=_identity("INTEGRITY-INTRADAY-WO10-LOCATION-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo10VolumeFact:
    evidence_identity: str
    integrity_identity: str
    series_identity: str
    canonical_subject_identity: str
    market_family: IntradayMarketFamily
    timeframe: IntradayTimeframe
    observation_boundary: datetime
    market_session_identities: tuple[str, ...]
    source_candle_identities: tuple[str, ...]
    source_candle_integrities: tuple[str, ...]
    availability: DataAvailability
    current_volume: Decimal | None
    rolling_median_volume: Decimal | None
    rolling_mean_volume: Decimal | None
    volume_ratio_to_median: Decimal | None
    volume_ratio_to_mean: Decimal | None
    volume_percentile: Decimal | None
    comparison_count: int
    lookback_identity: str = WO10_VOLUME_LOOKBACK_IDENTITY
    lookback_count: int = WO10_VOLUME_LOOKBACK
    consequence: str = "POLICY_UNRESOLVED_NO_THRESHOLD"
    schema_identity: str = WO10_VOLUME_FACT_IDENTITY
    schema_version: str = WO10_FACT_VERSION

    def __post_init__(self) -> None:
        data = _without(self, "evidence_identity", "integrity_identity")
        available = self.availability is DataAvailability.AVAILABLE
        measures = (
            self.current_volume,
            self.rolling_median_volume,
            self.rolling_mean_volume,
            self.volume_ratio_to_median,
            self.volume_ratio_to_mean,
            self.volume_percentile,
        )
        if (
            type(self.market_family) is not IntradayMarketFamily
            or not _aware(self.observation_boundary)
            or available != all(item is not None for item in measures)
            or (available and not (Decimal(0) <= self.volume_percentile <= Decimal(1)))
            or self.comparison_count not in {0, WO10_VOLUME_LOOKBACK}
            or self.lookback_identity != WO10_VOLUME_LOOKBACK_IDENTITY
            or self.lookback_count != WO10_VOLUME_LOOKBACK
            or self.consequence != "POLICY_UNRESOLVED_NO_THRESHOLD"
            or self.evidence_identity != _identity("INTRADAY-WO10-VOLUME-", data)
            or self.integrity_identity != _identity("INTEGRITY-INTRADAY-WO10-VOLUME-", data)
        ):
            raise Wo10ContractError("WO10_VOLUME_FACT_INVALID")


def build_wo10_volume_fact(series: Wo10CandleSeries) -> Wo10VolumeFact:
    if type(series) is not Wo10CandleSeries:
        raise Wo10ContractError("WO10_VOLUME_REQUEST_INVALID")
    volumes = tuple(Decimal(item.volume) for item in series.candles)
    available = len(volumes) >= WO10_VOLUME_LOOKBACK + 1
    baseline = volumes[-(WO10_VOLUME_LOOKBACK + 1):-1] if available else ()
    available = available and bool(baseline) and all(item > 0 for item in baseline)
    current = volumes[-1] if available else None
    median = _median(baseline) if available else None
    mean = sum(baseline, Decimal(0)) / Decimal(len(baseline)) if available else None
    values = {
        "series_identity": series.series_identity,
        "canonical_subject_identity": series.canonical_subject_identity,
        "market_family": series.market_family,
        "timeframe": series.timeframe,
        "observation_boundary": series.observation_boundary,
        "market_session_identities": series.market_session_identities,
        "source_candle_identities": series.source_candle_identities,
        "source_candle_integrities": series.source_candle_integrities,
        "availability": DataAvailability.AVAILABLE if available else DataAvailability.UNAVAILABLE,
        "current_volume": current,
        "rolling_median_volume": median,
        "rolling_mean_volume": mean,
        "volume_ratio_to_median": (current / median if available and median != 0 else None),
        "volume_ratio_to_mean": (current / mean if available and mean != 0 else None),
        "volume_percentile": (
            Decimal(sum(item <= current for item in baseline)) / Decimal(len(baseline))
            if available else None
        ),
        "comparison_count": len(baseline) if available else 0,
        "lookback_identity": WO10_VOLUME_LOOKBACK_IDENTITY,
        "lookback_count": WO10_VOLUME_LOOKBACK,
        "consequence": "POLICY_UNRESOLVED_NO_THRESHOLD",
        "schema_identity": WO10_VOLUME_FACT_IDENTITY,
        "schema_version": WO10_FACT_VERSION,
    }
    return Wo10VolumeFact(
        evidence_identity=_identity("INTRADAY-WO10-VOLUME-", values),
        integrity_identity=_identity("INTEGRITY-INTRADAY-WO10-VOLUME-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo10SessionPositionedCandle:
    candle: GovernedHistoricalCandlePayload
    calendar_identity: str
    session_position_identity: str

    def __post_init__(self) -> None:
        if (
            type(self.candle) is not GovernedHistoricalCandlePayload
            or not _text(self.calendar_identity)
            or not _text(self.session_position_identity)
        ):
            raise Wo10ContractError("WO10_SESSION_POSITIONED_CANDLE_INVALID")


@dataclass(frozen=True, slots=True)
class Wo10SameTimeVolumeFact:
    evidence_identity: str
    integrity_identity: str
    canonical_subject_identity: str
    market_family: IntradayMarketFamily
    timeframe: IntradayTimeframe
    observation_boundary: datetime
    current_session_identity: str
    calendar_identity: str
    session_position_identity: str
    historical_session_set_identity: str
    historical_session_identities: tuple[str, ...]
    source_candle_identities: tuple[str, ...]
    source_candle_integrities: tuple[str, ...]
    current_volume: Decimal
    same_time_session_median: Decimal
    same_time_session_ratio: Decimal | None
    same_time_session_percentile: Decimal
    comparison_count: int
    lookback_identity: str
    consequence: str = "POLICY_UNRESOLVED_NO_THRESHOLD"
    schema_identity: str = WO10_SAME_TIME_VOLUME_IDENTITY
    schema_version: str = WO10_FACT_VERSION

    def __post_init__(self) -> None:
        data = _without(self, "evidence_identity", "integrity_identity")
        if (
            self.timeframe not in {IntradayTimeframe.FIFTEEN_MINUTES, IntradayTimeframe.FIVE_MINUTES}
            or not _aware(self.observation_boundary)
            or not all(_text(item) for item in (
                self.current_session_identity,
                self.calendar_identity,
                self.session_position_identity,
                self.historical_session_set_identity,
                self.lookback_identity,
            ))
            or not self.historical_session_identities
            or self.current_session_identity in self.historical_session_identities
            or len(set(self.historical_session_identities)) != len(self.historical_session_identities)
            or self.comparison_count != len(self.historical_session_identities)
            or not (Decimal(0) <= self.same_time_session_percentile <= Decimal(1))
            or self.consequence != "POLICY_UNRESOLVED_NO_THRESHOLD"
            or self.evidence_identity != _identity("INTRADAY-WO10-SAME-TIME-VOLUME-", data)
            or self.integrity_identity != _identity("INTEGRITY-INTRADAY-WO10-SAME-TIME-VOLUME-", data)
        ):
            raise Wo10ContractError("WO10_SAME_TIME_VOLUME_INVALID")


def build_wo10_same_time_volume_fact(
    *,
    current: Wo10SessionPositionedCandle,
    historical: Sequence[Wo10SessionPositionedCandle],
    market_family: IntradayMarketFamily,
    historical_session_set_identity: str,
    lookback_identity: str,
) -> Wo10SameTimeVolumeFact:
    retained = tuple(historical)
    if (
        type(current) is not Wo10SessionPositionedCandle
        or not retained
        or any(type(item) is not Wo10SessionPositionedCandle for item in retained)
        or current.candle.timeframe not in {IntradayTimeframe.FIFTEEN_MINUTES, IntradayTimeframe.FIVE_MINUTES}
        or market_family_for_subject(current.candle.canonical_subject_identity) is not market_family
        or any(
            item.candle.canonical_subject_identity != current.candle.canonical_subject_identity
            or item.candle.timeframe is not current.candle.timeframe
            or item.candle.observation_boundary != current.candle.observation_boundary
            or item.calendar_identity != current.calendar_identity
            or item.session_position_identity != current.session_position_identity
            or item.candle.market_session_identity == current.candle.market_session_identity
            for item in retained
        )
        or len({item.candle.market_session_identity for item in retained}) != len(retained)
        or not _text(historical_session_set_identity)
        or not _text(lookback_identity)
    ):
        raise Wo10ContractError("WO10_SAME_TIME_VOLUME_REQUEST_INVALID")
    baseline = tuple(Decimal(item.candle.volume) for item in retained)
    current_volume = Decimal(current.candle.volume)
    median = _median(baseline)
    candles = (current, *retained)
    values = {
        "canonical_subject_identity": current.candle.canonical_subject_identity,
        "market_family": market_family,
        "timeframe": current.candle.timeframe,
        "observation_boundary": current.candle.observation_boundary,
        "current_session_identity": current.candle.market_session_identity,
        "calendar_identity": current.calendar_identity,
        "session_position_identity": current.session_position_identity,
        "historical_session_set_identity": historical_session_set_identity,
        "historical_session_identities": tuple(item.candle.market_session_identity for item in retained),
        "source_candle_identities": tuple(item.candle.candle_identity for item in candles),
        "source_candle_integrities": tuple(item.candle.integrity_identity for item in candles),
        "current_volume": current_volume,
        "same_time_session_median": median,
        "same_time_session_ratio": None if median == 0 else current_volume / median,
        "same_time_session_percentile": Decimal(sum(item <= current_volume for item in baseline)) / Decimal(len(baseline)),
        "comparison_count": len(baseline),
        "lookback_identity": lookback_identity,
        "consequence": "POLICY_UNRESOLVED_NO_THRESHOLD",
        "schema_identity": WO10_SAME_TIME_VOLUME_IDENTITY,
        "schema_version": WO10_FACT_VERSION,
    }
    return Wo10SameTimeVolumeFact(
        evidence_identity=_identity("INTRADAY-WO10-SAME-TIME-VOLUME-", values),
        integrity_identity=_identity("INTEGRITY-INTRADAY-WO10-SAME-TIME-VOLUME-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo10EventVolumeBinding:
    evidence_identity: str
    integrity_identity: str
    volume_evidence_identity: str
    volume_evidence_integrity: str
    structural_event_identity: str
    structural_event_integrity: str
    structural_event_type: StructuralFactType
    volume_source_candle_identities: tuple[str, ...]
    event_source_candle_identities: tuple[str, ...]
    consequence: str = "FACTUAL_BINDING_ONLY"
    schema_identity: str = WO10_EVENT_VOLUME_IDENTITY
    schema_version: str = WO10_FACT_VERSION

    def __post_init__(self) -> None:
        data = _without(self, "evidence_identity", "integrity_identity")
        if (
            type(self.structural_event_type) is not StructuralFactType
            or not self.volume_source_candle_identities
            or not self.event_source_candle_identities
            or self.consequence != "FACTUAL_BINDING_ONLY"
            or self.evidence_identity != _identity("INTRADAY-WO10-EVENT-VOLUME-", data)
            or self.integrity_identity != _identity("INTEGRITY-INTRADAY-WO10-EVENT-VOLUME-", data)
        ):
            raise Wo10ContractError("WO10_EVENT_VOLUME_BINDING_INVALID")


def bind_wo10_event_volume(
    volume: Wo10VolumeFact,
    structural_event: StructuralFact,
) -> Wo10EventVolumeBinding:
    if (
        type(volume) is not Wo10VolumeFact
        or type(structural_event) is not StructuralFact
        or volume.canonical_subject_identity != structural_event.canonical_instrument_id
        or volume.timeframe is not structural_event.timeframe
        or volume.observation_boundary != structural_event.observation_boundary.observed_at
    ):
        raise Wo10ContractError("WO10_EVENT_VOLUME_BINDING_REQUEST_INVALID")
    values = {
        "volume_evidence_identity": volume.evidence_identity,
        "volume_evidence_integrity": volume.integrity_identity,
        "structural_event_identity": structural_event.fact_id,
        "structural_event_integrity": structural_event.integrity_identity,
        "structural_event_type": structural_event.fact_type,
        "volume_source_candle_identities": volume.source_candle_identities,
        "event_source_candle_identities": structural_event.source_candle_ids,
        "consequence": "FACTUAL_BINDING_ONLY",
        "schema_identity": WO10_EVENT_VOLUME_IDENTITY,
        "schema_version": WO10_FACT_VERSION,
    }
    return Wo10EventVolumeBinding(
        evidence_identity=_identity("INTRADAY-WO10-EVENT-VOLUME-", values),
        integrity_identity=_identity("INTEGRITY-INTRADAY-WO10-EVENT-VOLUME-", values),
        **values,
    )


Wo10FactArtifact: TypeAlias = (
    Wo10RsiFact
    | Wo10SmaFacts
    | Wo10StructuralLocationFacts
    | Wo10VolumeFact
    | Wo10SameTimeVolumeFact
    | Wo10EventVolumeBinding
)


def _wilder_rsi(closes: tuple[Decimal, ...], period: int) -> Decimal | None:
    if len(closes) < period + 1:
        return None
    changes = tuple(current - prior for prior, current in zip(closes, closes[1:]))
    gains = tuple(max(item, Decimal(0)) for item in changes)
    losses = tuple(max(-item, Decimal(0)) for item in changes)
    average_gain = sum(gains[:period], Decimal(0)) / Decimal(period)
    average_loss = sum(losses[:period], Decimal(0)) / Decimal(period)
    for gain, loss in zip(gains[period:], losses[period:]):
        average_gain = (average_gain * Decimal(period - 1) + gain) / Decimal(period)
        average_loss = (average_loss * Decimal(period - 1) + loss) / Decimal(period)
    if average_gain == 0 and average_loss == 0:
        return Decimal(50)
    if average_loss == 0:
        return Decimal(100)
    if average_gain == 0:
        return Decimal(0)
    relative_strength = average_gain / average_loss
    return Decimal(100) - Decimal(100) / (Decimal(1) + relative_strength)


def _sma(values: tuple[Decimal, ...], period: int) -> Decimal | None:
    return sum(values[-period:], Decimal(0)) / Decimal(period) if len(values) >= period else None


def _sma20_price_organization(
    candles: tuple[GovernedHistoricalCandlePayload, ...],
) -> tuple[int | None, Wo10RecentSeparation]:
    if len(candles) < 20:
        return None, Wo10RecentSeparation.UNAVAILABLE
    closes = tuple(item.close for item in candles)
    sides: list[Decimal] = []
    crosses = 0
    for index in range(19, len(candles)):
        average = sum(closes[index - 19:index + 1], Decimal(0)) / Decimal(20)
        side = closes[index] - average
        if sides and side * sides[-1] < 0:
            crosses += 1
        sides.append(side)
    recent = tuple(sides[-5:])
    separation = (
        Wo10RecentSeparation.ALL_ABOVE if len(recent) == 5 and all(item > 0 for item in recent)
        else Wo10RecentSeparation.ALL_BELOW if len(recent) == 5 and all(item < 0 for item in recent)
        else Wo10RecentSeparation.MIXED_OR_AT
    )
    return crosses, separation


def _sma_pair_change(
    first: int,
    second: int,
    values: Mapping[int, tuple[Decimal | None, Decimal | None]],
) -> Wo10SmaPairChange:
    current_first, prior_first = values[first]
    current_second, prior_second = values[second]
    if None in {current_first, prior_first, current_second, prior_second}:
        return Wo10SmaPairChange(
            f"SMA{first}_SMA{second}", None, None, Wo10ExactChange.UNAVAILABLE
        )
    current_distance = abs(current_first - current_second)
    prior_distance = abs(prior_first - prior_second)
    change = (
        Wo10ExactChange.CONVERGING if current_distance < prior_distance
        else Wo10ExactChange.DIVERGING if current_distance > prior_distance
        else Wo10ExactChange.UNCHANGED
    )
    return Wo10SmaPairChange(
        f"SMA{first}_SMA{second}", current_distance, prior_distance, change
    )


def _price_relationship(value: Decimal, reference: Decimal) -> Wo10PriceRelationship:
    relationship = (
        ReferenceRelationship.ABOVE if value > reference
        else ReferenceRelationship.BELOW if value < reference
        else ReferenceRelationship.AT
    )
    return Wo10PriceRelationship(relationship.value)


def _median(values: tuple[Decimal, ...]) -> Decimal:
    ordered = tuple(sorted(values))
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal(2)


def _without(value: object, *names: str) -> dict[str, object]:
    return {name: item for name, item in asdict(value).items() if name not in names}


def _identity(prefix: str, value: object) -> str:
    encoded = json.dumps(
        _normalize(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return prefix + sha256(encoded).hexdigest().upper()


def _normalize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _normalize(asdict(value))
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(name): _normalize(item) for name, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    return value


def _decimal(value: object) -> Decimal:
    if isinstance(value, bool):
        raise Wo10ContractError("WO10_DECIMAL_INVALID")
    try:
        result = Decimal(str(value))
    except Exception as error:
        raise Wo10ContractError("WO10_DECIMAL_INVALID") from error
    if not result.is_finite():
        raise Wo10ContractError("WO10_DECIMAL_INVALID")
    return result


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


__all__ = [
    "WO10_EVENT_VOLUME_IDENTITY",
    "WO10_FACT_VERSION",
    "WO10_LOCATION_FACTS_IDENTITY",
    "WO10_RSI_CALCULATION_IDENTITY",
    "WO10_RSI_FACT_IDENTITY",
    "WO10_RSI_PERIOD",
    "WO10_SAME_TIME_VOLUME_IDENTITY",
    "WO10_SMA_CALCULATION_IDENTITY",
    "WO10_SMA_FACTS_IDENTITY",
    "WO10_SMA_PERIODS",
    "WO10_SMA_SLOPE_COMPARISON_BARS",
    "WO10_VOLUME_FACT_IDENTITY",
    "WO10_VOLUME_LOOKBACK",
    "WO10_VOLUME_LOOKBACK_IDENTITY",
    "Wo10CandleSeries",
    "Wo10EventVolumeBinding",
    "Wo10ExactChange",
    "Wo10FactArtifact",
    "Wo10LevelFact",
    "Wo10PriceRelationship",
    "Wo10RecentSeparation",
    "Wo10RsiCondition",
    "Wo10RsiFact",
    "Wo10SameTimeVolumeFact",
    "Wo10SessionPositionedCandle",
    "Wo10SmaFact",
    "Wo10SmaFacts",
    "Wo10SmaPairChange",
    "Wo10SmaSlope",
    "Wo10SmaStack",
    "Wo10StructuralLocationFacts",
    "Wo10VolumeFact",
    "bind_wo10_event_volume",
    "build_wo10_rsi_fact",
    "build_wo10_same_time_volume_fact",
    "build_wo10_sma_facts",
    "build_wo10_structural_location_facts",
    "build_wo10_volume_fact",
    "classify_wo10_rsi",
    "create_wo10_candle_series",
]
