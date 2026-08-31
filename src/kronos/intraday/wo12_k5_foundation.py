"""WO-12 K5 factual and research-only qualification foundations.

This module does not decide whether an ATR-normalized extension is material.
It only binds an exact governed structural origin, calculates completed-15M
Wilder ATR, and labels forward structure at fixed research horizons.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json
from typing import Sequence

from kronos.intraday.contracts import DataAvailability, IntradayTimeframe
from kronos.intraday.historical_semantic import (
    GovernedHistoricalCandlePayload,
    SemanticAvailability,
    SemanticDirection,
    SemanticFactFamily,
    SemanticQualificationFact,
)
from kronos.intraday.mcx_history import RetainedMcxContractCandle
from kronos.intraday.structure import (
    EXPLICIT_MOVE_POLICY,
    EXPLICIT_RANGE_POLICY,
    FactualDirection,
    StructuralEvidence,
    StructuralFact,
    StructuralFactType,
)
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo12 import Wo12Handoff
from kronos.intraday.wo12_facts import (
    WO12_EXTENSION_CALCULATION_IDENTITY,
    Wo12ExtensionMeasurement,
    create_wo12_extension_measurement,
)


WO12_K5_FOUNDATION_VERSION = "1.0.0"
WO12_STRUCTURAL_ORIGIN_IDENTITY = "KRONOS-INTRADAY-WO12-15M-STRUCTURAL-ORIGIN-V1"
WO12_ATR_IDENTITY = "KRONOS-INTRADAY-15M-WILDER-RMA-ATR-14-V1"
WO12_FORWARD_OUTCOME_IDENTITY = "KRONOS-INTRADAY-WO12-15M-FORWARD-STRUCTURE-OUTCOME-V1"
WO12_K5_RESEARCH_AUTHORITY = "RESEARCH_ONLY_NO_PRODUCTION_ANALYTICAL_AUTHORITY"
WO12_K5_THRESHOLD_AUTHORITY = "POLICY_UNRESOLVED"
WO12_ATR_PERIOD = 14
WO12_FORWARD_HORIZONS = (4, 8, 12)
WO12_HELD_MCX_SUBJECTS = frozenset(("MCX-SUBJECT-NATGAS",))
WO12_PULLBACK_ORIGIN_METHOD = "EXPLICIT_GOVERNED_15M_DIRECTIONAL_MOVE_ORIGIN_V1"
WO12_BREAKOUT_ORIGIN_METHOD = "EXPLICIT_GOVERNED_15M_RANGE_BOUNDARY_ORIGIN_V1"


class Wo12K5FoundationError(ValueError):
    """Sanitized factual-foundation validation failure."""


class Wo12SetupFamily(StrEnum):
    PULLBACK_CONTINUATION = "INTRADAY_PULLBACK_CONTINUATION"
    RANGE_BREAKOUT = "INTRADAY_RANGE_BREAKOUT"


class Wo12ForwardOutcome(StrEnum):
    CONTINUED = "CONTINUED"
    FAILED = "FAILED"
    INDETERMINATE = "INDETERMINATE"


@dataclass(frozen=True, slots=True)
class Wo12StructuralOriginFact:
    fact_identity: str
    fact_integrity: str
    canonical_subject_identity: str
    market_family: IntradayMarketFamily
    setup_family: Wo12SetupFamily
    inherited_direction: SemanticDirection
    timeframe: IntradayTimeframe
    analysis_boundary: datetime
    availability: SemanticAvailability
    origin_value: Decimal | None
    origin_boundary: datetime | None
    origin_type: str
    calculation_identity: str
    governing_structure_identity: str | None
    source_fact_identities: tuple[str, ...]
    source_fact_integrities: tuple[str, ...]
    provenance: tuple[str, ...]
    reason: str
    threshold_authority: str = WO12_K5_THRESHOLD_AUTHORITY
    schema_identity: str = WO12_STRUCTURAL_ORIGIN_IDENTITY
    schema_version: str = WO12_K5_FOUNDATION_VERSION

    def __post_init__(self) -> None:
        value = self.origin_value
        if value is not None:
            value = _decimal(value)
        available = self.availability is SemanticAvailability.AVAILABLE
        values = _without(self, "fact_identity", "fact_integrity")
        if (
            not _text(self.canonical_subject_identity)
            or type(self.market_family) is not IntradayMarketFamily
            or type(self.setup_family) is not Wo12SetupFamily
            or self.inherited_direction not in (SemanticDirection.LONG, SemanticDirection.SHORT)
            or self.timeframe is not IntradayTimeframe.FIFTEEN_MINUTES
            or not _aware(self.analysis_boundary)
            or type(self.availability) is not SemanticAvailability
            or available != all(item is not None for item in (
                value, self.origin_boundary, self.governing_structure_identity,
            ))
            or self.origin_boundary is not None and (
                not _aware(self.origin_boundary) or self.origin_boundary > self.analysis_boundary
            )
            or len(self.source_fact_identities) != len(self.source_fact_integrities)
            or available and not self.source_fact_identities
            or any(not _text(item) for item in (*self.source_fact_identities, *self.source_fact_integrities))
            or not _texts((self.origin_type, self.calculation_identity, self.reason))
            or not _texts(self.provenance)
            or self.threshold_authority != WO12_K5_THRESHOLD_AUTHORITY
            or self.schema_identity != WO12_STRUCTURAL_ORIGIN_IDENTITY
            or self.schema_version != WO12_K5_FOUNDATION_VERSION
            or self.fact_identity != _identity("INTRADAY-WO12-STRUCTURAL-ORIGIN-", values)
            or self.fact_integrity != _identity("INTEGRITY-INTRADAY-WO12-STRUCTURAL-ORIGIN-", values)
        ):
            raise Wo12K5FoundationError("WO12_STRUCTURAL_ORIGIN_FACT_INVALID")
        object.__setattr__(self, "origin_value", value)


@dataclass(frozen=True, slots=True)
class Wo12AtrFact:
    fact_identity: str
    fact_integrity: str
    canonical_subject_identity: str
    market_family: IntradayMarketFamily
    market_session_identity: str
    analysis_boundary: datetime
    availability: SemanticAvailability
    atr_value: Decimal | None
    period: int
    completed_candle_count: int
    last_completed_candle_identity: str | None
    canonical_contract_identity: str | None
    source_candle_identities: tuple[str, ...]
    source_candle_integrities: tuple[str, ...]
    provenance: tuple[str, ...]
    reason: str
    calculation_identity: str = WO12_ATR_IDENTITY
    schema_identity: str = WO12_ATR_IDENTITY
    schema_version: str = WO12_K5_FOUNDATION_VERSION

    def __post_init__(self) -> None:
        value = self.atr_value
        if value is not None:
            value = _decimal(value)
        available = self.availability is SemanticAvailability.AVAILABLE
        values = _without(self, "fact_identity", "fact_integrity")
        if (
            not _texts((self.canonical_subject_identity, self.market_session_identity, self.reason))
            or type(self.market_family) is not IntradayMarketFamily
            or not _aware(self.analysis_boundary)
            or type(self.availability) is not SemanticAvailability
            or available != (value is not None and self.last_completed_candle_identity is not None)
            or available and value <= 0
            or self.period != WO12_ATR_PERIOD
            or type(self.completed_candle_count) is not int
            or self.completed_candle_count != len(self.source_candle_identities)
            or len(self.source_candle_identities) != len(self.source_candle_integrities)
            or any(not _text(item) for item in (*self.source_candle_identities, *self.source_candle_integrities))
            or not _texts(self.provenance)
            or self.last_completed_candle_identity is not None and not _text(self.last_completed_candle_identity)
            or self.canonical_contract_identity is not None and not _text(self.canonical_contract_identity)
            or self.calculation_identity != WO12_ATR_IDENTITY
            or self.schema_identity != WO12_ATR_IDENTITY
            or self.schema_version != WO12_K5_FOUNDATION_VERSION
            or self.fact_identity != _identity("INTRADAY-WO12-15M-ATR-", values)
            or self.fact_integrity != _identity("INTEGRITY-INTRADAY-WO12-15M-ATR-", values)
        ):
            raise Wo12K5FoundationError("WO12_ATR_FACT_INVALID")
        object.__setattr__(self, "atr_value", value)


@dataclass(frozen=True, slots=True)
class Wo12ForwardOutcomeFact:
    fact_identity: str
    fact_integrity: str
    canonical_subject_identity: str
    market_family: IntradayMarketFamily
    inherited_direction: SemanticDirection
    original_analysis_boundary: datetime
    horizon_completed_15m_bars: int
    terminal_boundary: datetime | None
    availability: SemanticAvailability
    outcome: Wo12ForwardOutcome
    market_session_identity: str
    canonical_contract_identity: str | None
    source_candle_identities: tuple[str, ...]
    source_candle_integrities: tuple[str, ...]
    terminal_structure_fact_identity: str | None
    terminal_structure_fact_integrity: str | None
    provenance: tuple[str, ...]
    reason: str
    authority: str = WO12_K5_RESEARCH_AUTHORITY
    schema_identity: str = WO12_FORWARD_OUTCOME_IDENTITY
    schema_version: str = WO12_K5_FOUNDATION_VERSION

    def __post_init__(self) -> None:
        available = self.availability is SemanticAvailability.AVAILABLE
        values = _without(self, "fact_identity", "fact_integrity")
        if (
            not _texts((self.canonical_subject_identity, self.market_session_identity, self.reason))
            or type(self.market_family) is not IntradayMarketFamily
            or self.inherited_direction not in (SemanticDirection.LONG, SemanticDirection.SHORT)
            or not _aware(self.original_analysis_boundary)
            or self.horizon_completed_15m_bars not in WO12_FORWARD_HORIZONS
            or type(self.availability) is not SemanticAvailability
            or type(self.outcome) is not Wo12ForwardOutcome
            or available != all(item is not None for item in (
                self.terminal_boundary,
                self.terminal_structure_fact_identity,
                self.terminal_structure_fact_integrity,
            ))
            or self.terminal_boundary is not None and (
                not _aware(self.terminal_boundary)
                or self.terminal_boundary <= self.original_analysis_boundary
            )
            or len(self.source_candle_identities) != len(self.source_candle_integrities)
            or available and len(self.source_candle_identities) != self.horizon_completed_15m_bars
            or any(not _text(item) for item in (*self.source_candle_identities, *self.source_candle_integrities))
            or not _texts(self.provenance)
            or self.canonical_contract_identity is not None and not _text(self.canonical_contract_identity)
            or self.authority != WO12_K5_RESEARCH_AUTHORITY
            or self.schema_identity != WO12_FORWARD_OUTCOME_IDENTITY
            or self.schema_version != WO12_K5_FOUNDATION_VERSION
            or self.fact_identity != _identity("INTRADAY-WO12-FORWARD-OUTCOME-", values)
            or self.fact_integrity != _identity("INTEGRITY-INTRADAY-WO12-FORWARD-OUTCOME-", values)
        ):
            raise Wo12K5FoundationError("WO12_FORWARD_OUTCOME_FACT_INVALID")


@dataclass(frozen=True, slots=True)
class _Completed15mCandle:
    identity: str
    integrity: str
    subject: str
    session: str
    contract: str | None
    start: datetime
    end: datetime
    high: Decimal
    low: Decimal
    close: Decimal


def derive_wo12_structural_origin(
    *,
    canonical_subject_identity: str,
    market_family: IntradayMarketFamily,
    setup_family: Wo12SetupFamily,
    inherited_direction: SemanticDirection,
    analysis_boundary: datetime,
    evidence: StructuralEvidence | None,
) -> Wo12StructuralOriginFact:
    """Bind one exact governed 15M origin or fail closed."""

    if (
        not _text(canonical_subject_identity)
        or type(market_family) is not IntradayMarketFamily
        or type(setup_family) is not Wo12SetupFamily
        or inherited_direction not in (SemanticDirection.LONG, SemanticDirection.SHORT)
        or not _aware(analysis_boundary)
        or evidence is not None and type(evidence) is not StructuralEvidence
    ):
        raise Wo12K5FoundationError("WO12_STRUCTURAL_ORIGIN_REQUEST_INVALID")
    if evidence is None:
        return _origin_unavailable(
            canonical_subject_identity, market_family, setup_family,
            inherited_direction, analysis_boundary, "GOVERNED_15M_STRUCTURE_UNAVAILABLE",
        )
    if (
        evidence.instrument.canonical_instrument_id != canonical_subject_identity
        or evidence.timeframe is not IntradayTimeframe.FIFTEEN_MINUTES
        or evidence.observation_boundary.observed_at != analysis_boundary
        or evidence.availability is not DataAvailability.AVAILABLE
    ):
        return _origin_unavailable(
            canonical_subject_identity, market_family, setup_family,
            inherited_direction, analysis_boundary, "GOVERNED_15M_STRUCTURE_BINDING_MISMATCH",
        )
    if setup_family is Wo12SetupFamily.PULLBACK_CONTINUATION:
        fact_type = StructuralFactType.DIRECTIONAL_MOVE_MEASUREMENT
        direction = FactualDirection.UP if inherited_direction is SemanticDirection.LONG else FactualDirection.DOWN
        candidates = tuple(
            item for item in evidence.facts
            if item.fact_type is fact_type
            and item.policy_version == EXPLICIT_MOVE_POLICY
            and item.direction is direction
            and _usable(item, analysis_boundary)
        )
        if len(candidates) != 1:
            return _origin_unavailable(
                canonical_subject_identity, market_family, setup_family,
                inherited_direction, analysis_boundary,
                "EXPLICIT_DIRECTIONAL_MOVE_AMBIGUOUS" if candidates else "EXPLICIT_DIRECTIONAL_MOVE_UNAVAILABLE",
            )
        selected = candidates[0]
        value_name = "move_start_low" if inherited_direction is SemanticDirection.LONG else "move_start_high"
        origin = _structural_value(selected, value_name)
        governing = _structural_attribute(selected, "move_id")
    else:
        direction = FactualDirection.UP if inherited_direction is SemanticDirection.LONG else FactualDirection.DOWN
        break_type = (
            StructuralFactType.BOUNDARY_BREAK_ABOVE
            if inherited_direction is SemanticDirection.LONG
            else StructuralFactType.BOUNDARY_BREAK_BELOW
        )
        summaries = tuple(
            item for item in evidence.facts
            if item.fact_type is StructuralFactType.RANGE_SUMMARY
            and item.policy_version == EXPLICIT_RANGE_POLICY
            and _usable(item, analysis_boundary)
        )
        breaks = tuple(
            item for item in evidence.facts
            if item.fact_type is break_type
            and item.policy_version == EXPLICIT_RANGE_POLICY
            and item.direction is direction
            and _usable(item, analysis_boundary)
        )
        matching_range_ids = tuple(sorted({
            range_id
            for summary in summaries
            if (range_id := _structural_attribute(summary, "range_id")) is not None
            and any(_structural_attribute(event, "range_id") == range_id for event in breaks)
        }))
        if len(matching_range_ids) != 1:
            return _origin_unavailable(
                canonical_subject_identity, market_family, setup_family,
                inherited_direction, analysis_boundary,
                "EXPLICIT_RANGE_BREAK_AMBIGUOUS"
                if matching_range_ids
                else "EXPLICIT_RANGE_BREAK_UNAVAILABLE",
            )
        range_id = matching_range_ids[0]
        matching_summaries = tuple(
            item for item in summaries
            if _structural_attribute(item, "range_id") == range_id
        )
        matching_breaks = tuple(
            item for item in breaks
            if _structural_attribute(item, "range_id") == range_id
        )
        if len(matching_summaries) != 1:
            return _origin_unavailable(
                canonical_subject_identity, market_family, setup_family,
                inherited_direction, analysis_boundary, "EXPLICIT_RANGE_BREAK_AMBIGUOUS",
            )
        selected = matching_summaries[0]
        value_name = "range_high" if inherited_direction is SemanticDirection.LONG else "range_low"
        origin = _structural_value(selected, value_name)
        governing = _structural_attribute(selected, "range_id")
        candidates = (selected, *matching_breaks)
    if origin is None or governing is None or selected.start_boundary is None:
        return _origin_unavailable(
            canonical_subject_identity, market_family, setup_family,
            inherited_direction, analysis_boundary, "GOVERNED_STRUCTURAL_ORIGIN_INCOMPLETE",
        )
    source = candidates
    return _origin_fact(
        canonical_subject_identity=canonical_subject_identity,
        market_family=market_family,
        setup_family=setup_family,
        inherited_direction=inherited_direction,
        timeframe=IntradayTimeframe.FIFTEEN_MINUTES,
        analysis_boundary=analysis_boundary,
        availability=SemanticAvailability.AVAILABLE,
        origin_value=origin,
        origin_boundary=selected.start_boundary,
        origin_type=(
            "DIRECTIONAL_IMPULSE_LEG_START"
            if setup_family is Wo12SetupFamily.PULLBACK_CONTINUATION
            else "RANGE_DIRECTIONAL_BOUNDARY"
        ),
        calculation_identity=(
            WO12_PULLBACK_ORIGIN_METHOD
            if setup_family is Wo12SetupFamily.PULLBACK_CONTINUATION
            else WO12_BREAKOUT_ORIGIN_METHOD
        ),
        governing_structure_identity=governing,
        source_fact_identities=tuple(item.fact_id for item in source),
        source_fact_integrities=tuple(item.integrity_identity for item in source),
        provenance=(
            evidence.provenance.source_identity,
            evidence.integrity_identity,
            "COMPLETED_GOVERNED_15M_STRUCTURE_ONLY",
        ),
        reason="EXACT_GOVERNED_15M_STRUCTURAL_ORIGIN_BOUND",
    )


def calculate_wo12_wilder_atr(
    *,
    canonical_subject_identity: str,
    market_family: IntradayMarketFamily,
    market_session_identity: str,
    analysis_boundary: datetime,
    candles: Sequence[GovernedHistoricalCandlePayload | RetainedMcxContractCandle],
) -> Wo12AtrFact:
    """Calculate ATR-14 using only exact completed 15M candles at the boundary."""

    if (
        not _texts((canonical_subject_identity, market_session_identity))
        or type(market_family) is not IntradayMarketFamily
        or not _aware(analysis_boundary)
    ):
        raise Wo12K5FoundationError("WO12_ATR_REQUEST_INVALID")
    if canonical_subject_identity in WO12_HELD_MCX_SUBJECTS:
        return _atr_unavailable(
            canonical_subject_identity, market_family, market_session_identity,
            analysis_boundary, (), "HELD_MCX_SUBJECT",
        )
    normalized = tuple(sorted(
        (
            item for value in candles
            if (item := _completed_candle(value, analysis_boundary)) is not None
            and item.subject == canonical_subject_identity
        ),
        key=lambda item: (item.end, item.identity),
    ))
    if not normalized:
        return _atr_unavailable(
            canonical_subject_identity, market_family, market_session_identity,
            analysis_boundary, (), "COMPLETED_15M_CANDLES_UNAVAILABLE",
        )
    if normalized[-1].session != market_session_identity:
        return _atr_unavailable(
            canonical_subject_identity, market_family, market_session_identity,
            analysis_boundary, normalized, "ANALYSIS_SESSION_CANDLE_UNAVAILABLE",
        )
    if len({item.identity for item in normalized}) != len(normalized):
        return _atr_unavailable(
            canonical_subject_identity, market_family, market_session_identity,
            analysis_boundary, normalized, "COMPLETED_15M_CANDLE_DUPLICATE",
        )
    contracts = {item.contract for item in normalized if item.contract is not None}
    if len(contracts) > 1:
        return _atr_unavailable(
            canonical_subject_identity, market_family, market_session_identity,
            analysis_boundary, normalized, "MCX_CONTRACT_ROLL_CROSSING",
        )
    if len(normalized) < WO12_ATR_PERIOD:
        return _atr_unavailable(
            canonical_subject_identity, market_family, market_session_identity,
            analysis_boundary, normalized, "ATR_14_WARMUP_INCOMPLETE",
        )
    true_ranges: list[Decimal] = []
    previous_close: Decimal | None = None
    for candle in normalized:
        true_range = candle.high - candle.low
        if previous_close is not None:
            true_range = max(
                true_range,
                abs(candle.high - previous_close),
                abs(candle.low - previous_close),
            )
        true_ranges.append(true_range)
        previous_close = candle.close
    atr = sum(true_ranges[:WO12_ATR_PERIOD], Decimal(0)) / Decimal(WO12_ATR_PERIOD)
    for true_range in true_ranges[WO12_ATR_PERIOD:]:
        atr = (atr * Decimal(WO12_ATR_PERIOD - 1) + true_range) / Decimal(WO12_ATR_PERIOD)
    if atr <= 0:
        return _atr_unavailable(
            canonical_subject_identity, market_family, market_session_identity,
            analysis_boundary, normalized, "ATR_14_NON_POSITIVE",
        )
    values = {
        "canonical_subject_identity": canonical_subject_identity,
        "market_family": market_family,
        "market_session_identity": market_session_identity,
        "analysis_boundary": analysis_boundary,
        "availability": SemanticAvailability.AVAILABLE,
        "atr_value": atr,
        "period": WO12_ATR_PERIOD,
        "completed_candle_count": len(normalized),
        "last_completed_candle_identity": normalized[-1].identity,
        "canonical_contract_identity": next(iter(contracts), None),
        "source_candle_identities": tuple(item.identity for item in normalized),
        "source_candle_integrities": tuple(item.integrity for item in normalized),
        "provenance": (
            "RETAINED_GOVERNED_COMPLETED_15M_CANDLES",
            "WILDER_RMA_TRUE_RANGE",
        ),
        "reason": "COMPLETED_15M_WILDER_RMA_ATR_14_AVAILABLE",
        "calculation_identity": WO12_ATR_IDENTITY,
        "schema_identity": WO12_ATR_IDENTITY,
        "schema_version": WO12_K5_FOUNDATION_VERSION,
    }
    return Wo12AtrFact(
        fact_identity=_identity("INTRADAY-WO12-15M-ATR-", values),
        fact_integrity=_identity("INTEGRITY-INTRADAY-WO12-15M-ATR-", values),
        **values,
    )


def reconstruct_wo12_forward_outcomes(
    *,
    canonical_subject_identity: str,
    market_family: IntradayMarketFamily,
    inherited_direction: SemanticDirection,
    original_analysis_boundary: datetime,
    market_session_identity: str,
    future_candles: Sequence[GovernedHistoricalCandlePayload | RetainedMcxContractCandle],
    future_structure_facts: Sequence[SemanticQualificationFact],
) -> tuple[Wo12ForwardOutcomeFact, ...]:
    """Reconstruct fixed-horizon outcomes without return thresholds or look-ahead."""

    if (
        not _texts((canonical_subject_identity, market_session_identity))
        or type(market_family) is not IntradayMarketFamily
        or inherited_direction not in (SemanticDirection.LONG, SemanticDirection.SHORT)
        or not _aware(original_analysis_boundary)
    ):
        raise Wo12K5FoundationError("WO12_FORWARD_OUTCOME_REQUEST_INVALID")
    if canonical_subject_identity in WO12_HELD_MCX_SUBJECTS:
        return tuple(
            _outcome_unavailable(
                canonical_subject_identity, market_family, inherited_direction,
                original_analysis_boundary, horizon, market_session_identity,
                (), "HELD_MCX_SUBJECT",
            )
            for horizon in WO12_FORWARD_HORIZONS
        )
    normalized = tuple(sorted(
        (
            item for value in future_candles
            if (item := _completed_candle(value, datetime.max.replace(tzinfo=original_analysis_boundary.tzinfo))) is not None
            and item.subject == canonical_subject_identity
            and item.session == market_session_identity
            and item.end > original_analysis_boundary
        ),
        key=lambda item: (item.end, item.identity),
    ))
    outcomes: list[Wo12ForwardOutcomeFact] = []
    for horizon in WO12_FORWARD_HORIZONS:
        selected = normalized[:horizon]
        if len(selected) != horizon:
            outcomes.append(_outcome_unavailable(
                canonical_subject_identity, market_family, inherited_direction,
                original_analysis_boundary, horizon, market_session_identity,
                selected, "FORWARD_COMPLETED_15M_HORIZON_INCOMPLETE",
            ))
            continue
        if selected[0].start != original_analysis_boundary or any(
            right.start != left.end for left, right in zip(selected, selected[1:], strict=False)
        ):
            outcomes.append(_outcome_unavailable(
                canonical_subject_identity, market_family, inherited_direction,
                original_analysis_boundary, horizon, market_session_identity,
                selected, "FORWARD_15M_CONTINUITY_GAP",
            ))
            continue
        contracts = {item.contract for item in selected if item.contract is not None}
        if len(contracts) > 1:
            outcomes.append(_outcome_unavailable(
                canonical_subject_identity, market_family, inherited_direction,
                original_analysis_boundary, horizon, market_session_identity,
                selected, "MCX_CONTRACT_ROLL_CROSSING",
            ))
            continue
        terminal = selected[-1].end
        facts = tuple(
            fact for fact in future_structure_facts
            if type(fact) is SemanticQualificationFact
            and fact.family is SemanticFactFamily.FIFTEEN_MINUTE_STRUCTURE
            and fact.canonical_subject_identity == canonical_subject_identity
            and fact.market_session_identity == market_session_identity
            and fact.timeframe is IntradayTimeframe.FIFTEEN_MINUTES
            and fact.observation_boundary == terminal
            and fact.available_at <= terminal
            and fact.availability is SemanticAvailability.AVAILABLE
        )
        if len(facts) != 1:
            outcomes.append(_outcome_unavailable(
                canonical_subject_identity, market_family, inherited_direction,
                original_analysis_boundary, horizon, market_session_identity,
                selected,
                "TERMINAL_15M_STRUCTURE_AMBIGUOUS" if facts else "TERMINAL_15M_STRUCTURE_UNAVAILABLE",
            ))
            continue
        fact = facts[0]
        outcome = (
            Wo12ForwardOutcome.CONTINUED
            if fact.direction is inherited_direction
            else Wo12ForwardOutcome.FAILED
            if fact.direction in (SemanticDirection.LONG, SemanticDirection.SHORT)
            else Wo12ForwardOutcome.INDETERMINATE
        )
        values = {
            "canonical_subject_identity": canonical_subject_identity,
            "market_family": market_family,
            "inherited_direction": inherited_direction,
            "original_analysis_boundary": original_analysis_boundary,
            "horizon_completed_15m_bars": horizon,
            "terminal_boundary": terminal,
            "availability": SemanticAvailability.AVAILABLE,
            "outcome": outcome,
            "market_session_identity": market_session_identity,
            "canonical_contract_identity": next(iter(contracts), None),
            "source_candle_identities": tuple(item.identity for item in selected),
            "source_candle_integrities": tuple(item.integrity for item in selected),
            "terminal_structure_fact_identity": fact.fact_identity,
            "terminal_structure_fact_integrity": fact.integrity_identity,
            "provenance": (
                WO12_K5_RESEARCH_AUTHORITY,
                "FUTURE_COMPLETED_GOVERNED_15M_ONLY",
                fact.policy_identity,
            ),
            "reason": "GOVERNED_TERMINAL_15M_STRUCTURE_CLASSIFIED",
            "authority": WO12_K5_RESEARCH_AUTHORITY,
            "schema_identity": WO12_FORWARD_OUTCOME_IDENTITY,
            "schema_version": WO12_K5_FOUNDATION_VERSION,
        }
        outcomes.append(Wo12ForwardOutcomeFact(
            fact_identity=_identity("INTRADAY-WO12-FORWARD-OUTCOME-", values),
            fact_integrity=_identity("INTEGRITY-INTRADAY-WO12-FORWARD-OUTCOME-", values),
            **values,
        ))
    return tuple(outcomes)


def create_k5_measurement_from_foundation(
    *,
    handoff: Wo12Handoff,
    origin: Wo12StructuralOriginFact,
    atr: Wo12AtrFact,
    completed_close: Decimal,
) -> Wo12ExtensionMeasurement | None:
    """Reuse the frozen K5 formula while leaving its threshold unresolved."""

    if (
        type(handoff) is not Wo12Handoff
        or type(origin) is not Wo12StructuralOriginFact
        or type(atr) is not Wo12AtrFact
        or origin.canonical_subject_identity != handoff.canonical_subject_identity
        or atr.canonical_subject_identity != handoff.canonical_subject_identity
        or origin.market_family is not handoff.market_family
        or atr.market_family is not handoff.market_family
        or origin.inherited_direction is not handoff.inherited_direction
        or origin.analysis_boundary != handoff.analysis_boundary
        or atr.analysis_boundary != handoff.analysis_boundary
    ):
        raise Wo12K5FoundationError("WO12_K5_FOUNDATION_BINDING_INVALID")
    if (
        origin.availability is not SemanticAvailability.AVAILABLE
        or atr.availability is not SemanticAvailability.AVAILABLE
        or origin.origin_value is None
        or atr.atr_value is None
    ):
        return None
    return create_wo12_extension_measurement(
        handoff=handoff,
        structural_origin_identity=origin.fact_identity,
        structural_origin_value=origin.origin_value,
        completed_close=completed_close,
        atr_value=atr.atr_value,
        atr_period=atr.period,
        atr_calculation_identity=WO12_EXTENSION_CALCULATION_IDENTITY,
        source_evidence_identities=(origin.fact_identity, atr.fact_identity),
        source_evidence_integrities=(origin.fact_integrity, atr.fact_integrity),
    )


def _origin_unavailable(
    subject: str,
    market_family: IntradayMarketFamily,
    setup_family: Wo12SetupFamily,
    direction: SemanticDirection,
    boundary: datetime,
    reason: str,
) -> Wo12StructuralOriginFact:
    return _origin_fact(
        canonical_subject_identity=subject,
        market_family=market_family,
        setup_family=setup_family,
        inherited_direction=direction,
        timeframe=IntradayTimeframe.FIFTEEN_MINUTES,
        analysis_boundary=boundary,
        availability=SemanticAvailability.UNAVAILABLE,
        origin_value=None,
        origin_boundary=None,
        origin_type=(
            "DIRECTIONAL_IMPULSE_LEG_START"
            if setup_family is Wo12SetupFamily.PULLBACK_CONTINUATION
            else "RANGE_DIRECTIONAL_BOUNDARY"
        ),
        calculation_identity=(
            WO12_PULLBACK_ORIGIN_METHOD
            if setup_family is Wo12SetupFamily.PULLBACK_CONTINUATION
            else WO12_BREAKOUT_ORIGIN_METHOD
        ),
        governing_structure_identity=None,
        source_fact_identities=(),
        source_fact_integrities=(),
        provenance=("GOVERNED_15M_STRUCTURE_REQUIRED",),
        reason=reason,
    )


def _origin_fact(**values: object) -> Wo12StructuralOriginFact:
    values = {
        **values,
        "threshold_authority": WO12_K5_THRESHOLD_AUTHORITY,
        "schema_identity": WO12_STRUCTURAL_ORIGIN_IDENTITY,
        "schema_version": WO12_K5_FOUNDATION_VERSION,
    }
    return Wo12StructuralOriginFact(
        fact_identity=_identity("INTRADAY-WO12-STRUCTURAL-ORIGIN-", values),
        fact_integrity=_identity("INTEGRITY-INTRADAY-WO12-STRUCTURAL-ORIGIN-", values),
        **values,
    )


def _atr_unavailable(
    subject: str,
    family: IntradayMarketFamily,
    session: str,
    boundary: datetime,
    candles: Sequence[_Completed15mCandle],
    reason: str,
) -> Wo12AtrFact:
    contracts = {item.contract for item in candles if item.contract is not None}
    values = {
        "canonical_subject_identity": subject,
        "market_family": family,
        "market_session_identity": session,
        "analysis_boundary": boundary,
        "availability": SemanticAvailability.UNAVAILABLE,
        "atr_value": None,
        "period": WO12_ATR_PERIOD,
        "completed_candle_count": len(candles),
        "last_completed_candle_identity": None,
        "canonical_contract_identity": next(iter(contracts)) if len(contracts) == 1 else None,
        "source_candle_identities": tuple(item.identity for item in candles),
        "source_candle_integrities": tuple(item.integrity for item in candles),
        "provenance": (
            "RETAINED_GOVERNED_COMPLETED_15M_CANDLES",
            "WILDER_RMA_TRUE_RANGE",
        ),
        "reason": reason,
        "calculation_identity": WO12_ATR_IDENTITY,
        "schema_identity": WO12_ATR_IDENTITY,
        "schema_version": WO12_K5_FOUNDATION_VERSION,
    }
    return Wo12AtrFact(
        fact_identity=_identity("INTRADAY-WO12-15M-ATR-", values),
        fact_integrity=_identity("INTEGRITY-INTRADAY-WO12-15M-ATR-", values),
        **values,
    )


def _outcome_unavailable(
    subject: str,
    family: IntradayMarketFamily,
    direction: SemanticDirection,
    boundary: datetime,
    horizon: int,
    session: str,
    candles: Sequence[_Completed15mCandle],
    reason: str,
) -> Wo12ForwardOutcomeFact:
    contracts = {item.contract for item in candles if item.contract is not None}
    values = {
        "canonical_subject_identity": subject,
        "market_family": family,
        "inherited_direction": direction,
        "original_analysis_boundary": boundary,
        "horizon_completed_15m_bars": horizon,
        "terminal_boundary": None,
        "availability": SemanticAvailability.UNAVAILABLE,
        "outcome": Wo12ForwardOutcome.INDETERMINATE,
        "market_session_identity": session,
        "canonical_contract_identity": next(iter(contracts)) if len(contracts) == 1 else None,
        "source_candle_identities": tuple(item.identity for item in candles),
        "source_candle_integrities": tuple(item.integrity for item in candles),
        "terminal_structure_fact_identity": None,
        "terminal_structure_fact_integrity": None,
        "provenance": (
            WO12_K5_RESEARCH_AUTHORITY,
            "FUTURE_COMPLETED_GOVERNED_15M_REQUIRED",
        ),
        "reason": reason,
        "authority": WO12_K5_RESEARCH_AUTHORITY,
        "schema_identity": WO12_FORWARD_OUTCOME_IDENTITY,
        "schema_version": WO12_K5_FOUNDATION_VERSION,
    }
    return Wo12ForwardOutcomeFact(
        fact_identity=_identity("INTRADAY-WO12-FORWARD-OUTCOME-", values),
        fact_integrity=_identity("INTEGRITY-INTRADAY-WO12-FORWARD-OUTCOME-", values),
        **values,
    )


def _completed_candle(
    value: object,
    boundary: datetime,
) -> _Completed15mCandle | None:
    if type(value) is GovernedHistoricalCandlePayload:
        if (
            value.timeframe is not IntradayTimeframe.FIFTEEN_MINUTES
            or value.completion_state != "COMPLETE"
            or value.available_at != value.candle_end
            or value.candle_end > boundary
        ):
            return None
        return _Completed15mCandle(
            identity=value.candle_identity,
            integrity=value.integrity_identity,
            subject=value.canonical_subject_identity,
            session=value.market_session_identity,
            contract=None,
            start=value.candle_start,
            end=value.candle_end,
            high=value.high,
            low=value.low,
            close=value.close,
        )
    if type(value) is RetainedMcxContractCandle:
        if value.timeframe is not IntradayTimeframe.FIFTEEN_MINUTES or value.candle_end > boundary:
            return None
        return _Completed15mCandle(
            identity=value.candle_identity,
            integrity=value.integrity_identity,
            subject=value.canonical_subject_identity,
            session=value.domain008_session_identity,
            contract=value.canonical_contract_identity,
            start=value.candle_start,
            end=value.candle_end,
            high=value.high,
            low=value.low,
            close=value.close,
        )
    return None


def _usable(fact: StructuralFact, boundary: datetime) -> bool:
    return (
        fact.availability is DataAvailability.AVAILABLE
        and fact.confirmation_boundary is not None
        and fact.confirmation_boundary <= boundary
    )


def _structural_value(fact: StructuralFact, name: str) -> Decimal | None:
    return next((item.value for item in fact.values if item.name == name), None)


def _structural_attribute(fact: StructuralFact, name: str) -> str | None:
    return next((item.value for item in fact.attributes if item.name == name), None)


def _without(value: object, *names: str) -> dict[str, object]:
    data = asdict(value) if is_dataclass(value) else dict(value)
    for name in names:
        data.pop(name, None)
    return data


def _identity(prefix: str, value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")
    return f"{prefix}{sha256(payload).hexdigest().upper()}"


def _json_default(value: object) -> object:
    if isinstance(value, (datetime, Decimal, StrEnum)):
        return str(value)
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(type(value).__name__)


def _decimal(value: object) -> Decimal:
    result = value if type(value) is Decimal else Decimal(str(value))
    if not result.is_finite():
        raise Wo12K5FoundationError("WO12_K5_DECIMAL_INVALID")
    return result


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _texts(values: Sequence[object]) -> bool:
    return all(_text(value) for value in values)
