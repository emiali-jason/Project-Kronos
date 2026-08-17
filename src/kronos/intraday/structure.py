"""Threshold-free Intraday Slice 2 structural fact foundation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from hashlib import sha256
import json
import re

from kronos.intraday.candles import CandleReconciliation, ReconciliationResult
from kronos.intraday.context import Slice1EContext
from kronos.intraday.contracts import (
    CandleCompletion,
    DataAvailability,
    GovernedCandle,
    IntradayInstrumentReference,
    IntradayRun,
    IntradayTimeframe,
    ObservationBoundary,
    SourceProvenance,
)


STRUCTURAL_FACT_SCHEMA = "KRONOS-INTRADAY-V1-STRUCTURAL-FACTS-V1"
STRUCTURAL_FACT_POLICY = "INTRADAY_STRUCTURAL_FACTS_V1"
LOCAL_RELATION_POLICY = "IMMEDIATE_NEIGHBOUR_RELATION_V1"
EXPLICIT_RANGE_POLICY = "EXPLICIT_RANGE_MEASUREMENT_V1"
EXPLICIT_MOVE_POLICY = "EXPLICIT_DIRECTIONAL_MOVE_MEASUREMENT_V1"
EXACT_BARRIER_POLICY = "EXACT_COMPLETED_CANDLE_BARRIER_RELATION_V1"


class FactualDirection(StrEnum):
    UP = "UP"
    DOWN = "DOWN"
    NONE = "NONE"


class StructuralFactType(StrEnum):
    HIGHER_HIGH = "HIGHER_HIGH"
    LOWER_HIGH = "LOWER_HIGH"
    EQUAL_HIGH = "EQUAL_HIGH"
    HIGHER_LOW = "HIGHER_LOW"
    LOWER_LOW = "LOWER_LOW"
    EQUAL_LOW = "EQUAL_LOW"
    HIGHER_CLOSE = "HIGHER_CLOSE"
    LOWER_CLOSE = "LOWER_CLOSE"
    EQUAL_CLOSE = "EQUAL_CLOSE"
    CANDIDATE_LOCAL_HIGH = "CANDIDATE_LOCAL_HIGH"
    CANDIDATE_LOCAL_LOW = "CANDIDATE_LOCAL_LOW"
    RANGE_SUMMARY = "RANGE_SUMMARY"
    BOUNDARY_BREAK_ABOVE = "BOUNDARY_BREAK_ABOVE"
    BOUNDARY_BREAK_BELOW = "BOUNDARY_BREAK_BELOW"
    RETURN_INSIDE = "RETURN_INSIDE"
    CLOSE_BACK_THROUGH = "CLOSE_BACK_THROUGH"
    RETEST_FROM_ABOVE = "RETEST_FROM_ABOVE"
    RETEST_FROM_BELOW = "RETEST_FROM_BELOW"
    CLOSE_ABOVE_BOUNDARY = "CLOSE_ABOVE_BOUNDARY"
    CLOSE_BELOW_BOUNDARY = "CLOSE_BELOW_BOUNDARY"
    CLOSE_AT_BOUNDARY = "CLOSE_AT_BOUNDARY"
    EXACT_BOUNDARY_TOUCH = "EXACT_BOUNDARY_TOUCH"
    DIRECTIONAL_MOVE_MEASUREMENT = "DIRECTIONAL_MOVE_MEASUREMENT"
    RETRACEMENT_MEASUREMENT = "RETRACEMENT_MEASUREMENT"


@dataclass(frozen=True, slots=True)
class StructuralValue:
    name: str
    value: Decimal

    def __post_init__(self) -> None:
        value = _decimal(self.value)
        if not _key(self.name):
            raise ValueError("INTRADAY_STRUCTURAL_VALUE_INVALID")
        object.__setattr__(self, "value", value)


@dataclass(frozen=True, slots=True)
class StructuralAttribute:
    name: str
    value: str

    def __post_init__(self) -> None:
        if not _key(self.name) or not isinstance(self.value, str) or not self.value:
            raise ValueError("INTRADAY_STRUCTURAL_ATTRIBUTE_INVALID")


@dataclass(frozen=True, slots=True)
class StructuralBarrier:
    barrier_id: str
    barrier_family: str
    reference_name: str
    price: Decimal | None
    origin_trading_date: date
    origin_timeframe: IntradayTimeframe
    origin_session_id: str | None
    source_identity: str
    provenance: SourceProvenance
    availability: DataAvailability

    def __post_init__(self) -> None:
        price = None if self.price is None else _decimal(self.price)
        available = self.availability is DataAvailability.AVAILABLE
        payload = _barrier_payload(self, include_identity=False)
        if (
            not _name(self.barrier_family)
            or not _name(self.reference_name)
            or type(self.origin_trading_date) is not date
            or type(self.origin_timeframe) is not IntradayTimeframe
            or (self.origin_session_id is not None and not self.origin_session_id)
            or not isinstance(self.source_identity, str)
            or not self.source_identity
            or type(self.provenance) is not SourceProvenance
            or type(self.availability) is not DataAvailability
            or available != (price is not None)
            or self.barrier_id != _identity("STRUCTURAL-BARRIER-", payload)
        ):
            raise ValueError("INTRADAY_STRUCTURAL_BARRIER_INVALID")
        object.__setattr__(self, "price", price)


@dataclass(frozen=True, slots=True)
class ExplicitRangeDefinition:
    range_id: str
    high: Decimal
    low: Decimal
    start_boundary: datetime
    end_boundary: datetime

    def __post_init__(self) -> None:
        high, low = _decimal(self.high), _decimal(self.low)
        if (
            not _name(self.range_id)
            or high < low
            or not _aware(self.start_boundary)
            or not _aware(self.end_boundary)
            or self.start_boundary >= self.end_boundary
        ):
            raise ValueError("INTRADAY_EXPLICIT_RANGE_INVALID")
        object.__setattr__(self, "high", high)
        object.__setattr__(self, "low", low)


@dataclass(frozen=True, slots=True)
class ExplicitMoveDefinition:
    move_id: str
    direction: FactualDirection
    start_candle_id: str
    end_candle_id: str
    retracement_end_candle_id: str | None = None

    def __post_init__(self) -> None:
        if (
            not _name(self.move_id)
            or self.direction not in (FactualDirection.UP, FactualDirection.DOWN)
            or not self.start_candle_id
            or not self.end_candle_id
            or self.start_candle_id == self.end_candle_id
            or (
                self.retracement_end_candle_id is not None
                and not self.retracement_end_candle_id
            )
        ):
            raise ValueError("INTRADAY_EXPLICIT_MOVE_INVALID")


@dataclass(frozen=True, slots=True)
class StructuralFact:
    fact_id: str
    run_id: str
    canonical_instrument_id: str
    mapping_identity: str
    trading_date: date
    timeframe: IntradayTimeframe
    observation_boundary: ObservationBoundary
    fact_type: StructuralFactType
    direction: FactualDirection
    values: tuple[StructuralValue, ...]
    attributes: tuple[StructuralAttribute, ...]
    source_candle_ids: tuple[str, ...]
    source_reference_ids: tuple[str, ...]
    start_boundary: datetime | None
    end_boundary: datetime | None
    confirmation_boundary: datetime | None
    availability: DataAvailability
    provenance: SourceProvenance
    policy_version: str
    integrity_identity: str
    schema_identity: str = STRUCTURAL_FACT_SCHEMA

    def __post_init__(self) -> None:
        payload = structural_fact_payload(self)
        if (
            not self.run_id
            or not self.canonical_instrument_id
            or not self.mapping_identity
            or type(self.trading_date) is not date
            or type(self.timeframe) is not IntradayTimeframe
            or type(self.observation_boundary) is not ObservationBoundary
            or type(self.fact_type) is not StructuralFactType
            or type(self.direction) is not FactualDirection
            or any(type(item) is not StructuralValue for item in self.values)
            or any(type(item) is not StructuralAttribute for item in self.attributes)
            or len(set(item.name for item in self.values)) != len(self.values)
            or len(set(item.name for item in self.attributes)) != len(self.attributes)
            or any(not item for item in (*self.source_candle_ids, *self.source_reference_ids))
            or any(value is not None and not _aware(value) for value in (
                self.start_boundary, self.end_boundary, self.confirmation_boundary
            ))
            or type(self.availability) is not DataAvailability
            or type(self.provenance) is not SourceProvenance
            or not _name(self.policy_version)
            or self.schema_identity != STRUCTURAL_FACT_SCHEMA
            or self.fact_id != _identity("STRUCTURAL-FACT-", payload)
            or self.integrity_identity != _identity("SHA256-", payload)
        ):
            raise ValueError("INTRADAY_STRUCTURAL_FACT_INVALID")


@dataclass(frozen=True, slots=True)
class StructuralEvidence:
    evidence_id: str
    run: IntradayRun
    instrument: IntradayInstrumentReference
    trading_date: date
    timeframe: IntradayTimeframe
    observation_boundary: ObservationBoundary
    governed_candle_ids: tuple[str, ...]
    barriers: tuple[StructuralBarrier, ...]
    facts: tuple[StructuralFact, ...]
    availability: DataAvailability
    provenance: SourceProvenance
    integrity_identity: str
    schema_identity: str = STRUCTURAL_FACT_SCHEMA

    def __post_init__(self) -> None:
        payload = structural_evidence_payload(self)
        if (
            type(self.run) is not IntradayRun
            or type(self.instrument) is not IntradayInstrumentReference
            or type(self.trading_date) is not date
            or type(self.timeframe) is not IntradayTimeframe
            or self.observation_boundary != self.run.observation_boundary
            or any(type(item) is not StructuralBarrier for item in self.barriers)
            or any(type(item) is not StructuralFact for item in self.facts)
            or len(set(self.governed_candle_ids)) != len(self.governed_candle_ids)
            or any(item.run_id != self.run.run_id for item in self.facts)
            or any(item.mapping_identity != self.instrument.mapping_identity for item in self.facts)
            or any(item.timeframe is not self.timeframe for item in self.facts)
            or any(item.trading_date != self.trading_date for item in self.facts)
            or any(item.observation_boundary != self.observation_boundary for item in self.facts)
            or any(item.provenance != self.provenance for item in self.facts)
            or any(
                candle_id not in self.governed_candle_ids
                for item in self.facts for candle_id in item.source_candle_ids
            )
            or any(
                reference_id not in {barrier.barrier_id for barrier in self.barriers}
                for item in self.facts for reference_id in item.source_reference_ids
            )
            or type(self.availability) is not DataAvailability
            or type(self.provenance) is not SourceProvenance
            or self.schema_identity != STRUCTURAL_FACT_SCHEMA
            or self.evidence_id != _identity("STRUCTURAL-EVIDENCE-", payload)
            or self.integrity_identity != _identity("SHA256-", payload)
        ):
            raise ValueError("INTRADAY_STRUCTURAL_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class StructuralProjection:
    canonical_instrument_id: str
    mapping_identity: str
    evidence_by_timeframe: tuple[tuple[IntradayTimeframe, tuple[StructuralEvidence, ...]], ...]
    slice1e_context: Slice1EContext | None

    def __post_init__(self) -> None:
        if (
            not self.canonical_instrument_id
            or not self.mapping_identity
            or any(
                type(timeframe) is not IntradayTimeframe
                or any(type(item) is not StructuralEvidence for item in evidence)
                for timeframe, evidence in self.evidence_by_timeframe
            )
            or any(
                item.instrument.mapping_identity != self.mapping_identity
                for _, evidence in self.evidence_by_timeframe for item in evidence
            )
            or (
                self.slice1e_context is not None
                and self.slice1e_context.instrument.mapping_identity != self.mapping_identity
            )
        ):
            raise ValueError("INTRADAY_STRUCTURAL_PROJECTION_INVALID")


def barriers_from_slice1e(context: Slice1EContext) -> tuple[StructuralBarrier, ...]:
    """Adapt Slice 1E references without assigning support/resistance meaning."""

    if type(context) is not Slice1EContext:
        raise ValueError("INTRADAY_STRUCTURAL_BARRIER_REQUEST_INVALID")
    previous = context.previous_session
    origin = (
        previous.current_trading_date
        if previous.previous_schedule is None
        else previous.previous_schedule.trading_date
    )
    origin_session_id = (
        None if previous.previous_schedule is None else previous.previous_schedule.session_id
    )
    definitions = [
        ("PREVIOUS_SESSION", "PDH", previous.pdh, previous.evidence_identity),
        ("PREVIOUS_SESSION", "PDL", previous.pdl, previous.evidence_identity),
        *(
            (context.classic_pivots.evidence_family, name.upper(), getattr(context.classic_pivots, name), context.classic_pivots.evidence_identity)
            for name in ("p", "r1", "r2", "r3", "r4", "s1", "s2", "s3", "s4")
        ),
        (context.cpr.evidence_family, "CPR_UPPER", context.cpr.upper, context.cpr.evidence_identity),
        (context.cpr.evidence_family, "CPR_LOWER", context.cpr.lower, context.cpr.evidence_identity),
        (context.cpr.evidence_family, "CPR_PIVOT", context.cpr.pivot, context.cpr.evidence_identity),
    ]
    return tuple(
        _barrier(
            family=family, name=name, price=price, origin=origin,
            origin_session_id=origin_session_id,
            source_identity=source, provenance=previous.provenance,
            availability=(DataAvailability.AVAILABLE if price is not None else DataAvailability.UNAVAILABLE),
        )
        for family, name, price, source in definitions
    )


def build_structural_evidence(
    *,
    run: IntradayRun,
    reconciliation: CandleReconciliation,
    barriers: Sequence[StructuralBarrier] = (),
    ranges: Sequence[ExplicitRangeDefinition] = (),
    moves: Sequence[ExplicitMoveDefinition] = (),
) -> StructuralEvidence:
    """Derive only exact facts from a reconciled completed-candle authority set."""

    if (
        type(run) is not IntradayRun
        or type(reconciliation) is not CandleReconciliation
        or any(type(item) is not StructuralBarrier for item in barriers)
        or any(type(item) is not ExplicitRangeDefinition for item in ranges)
        or any(type(item) is not ExplicitMoveDefinition for item in moves)
        or run.observation_boundary != reconciliation.observation_boundary
    ):
        raise ValueError("INTRADAY_STRUCTURAL_EVIDENCE_REQUEST_INVALID")
    candles = tuple(sorted(
        (
            item for item in reconciliation.structural_candles
            if item.completion is CandleCompletion.COMPLETE
        ),
        key=lambda item: item.boundary.start,
    ))
    availability = (
        DataAvailability.AVAILABLE
        if reconciliation.result is ReconciliationResult.COMPLETE
        else reconciliation.availability
    )
    facts: list[StructuralFact] = []
    if availability is DataAvailability.AVAILABLE:
        facts.extend(_pair_relationships(run, reconciliation, candles))
        facts.extend(_local_pivots(run, reconciliation, candles))
        for barrier in barriers:
            facts.extend(_barrier_facts(run, reconciliation, candles, barrier))
        for definition in ranges:
            facts.extend(_range_facts(run, reconciliation, candles, definition))
        for definition in moves:
            facts.extend(_move_facts(run, reconciliation, candles, definition))
    provisional = object.__new__(StructuralEvidence)
    values = {
        "run": run, "instrument": reconciliation.instrument,
        "trading_date": reconciliation.schedule.trading_date,
        "timeframe": reconciliation.timeframe,
        "observation_boundary": reconciliation.observation_boundary,
        "governed_candle_ids": tuple(item.candle_id for item in candles),
        "barriers": tuple(barriers), "facts": tuple(facts),
        "availability": availability, "provenance": reconciliation.provenance,
        "schema_identity": STRUCTURAL_FACT_SCHEMA,
    }
    for name, value in values.items():
        object.__setattr__(provisional, name, value)
    payload = structural_evidence_payload(provisional)
    return StructuralEvidence(
        evidence_id=_identity("STRUCTURAL-EVIDENCE-", payload),
        integrity_identity=_identity("SHA256-", payload),
        **values,
    )


def project_structural_evidence(
    evidence: Sequence[StructuralEvidence], *, slice1e_context: Slice1EContext | None = None
) -> StructuralProjection:
    if not evidence or any(type(item) is not StructuralEvidence for item in evidence):
        raise ValueError("INTRADAY_STRUCTURAL_PROJECTION_REQUEST_INVALID")
    first = evidence[0]
    if any(item.instrument.mapping_identity != first.instrument.mapping_identity for item in evidence):
        raise ValueError("INTRADAY_STRUCTURAL_PROJECTION_REQUEST_INVALID")
    grouped = tuple(
        (
            timeframe,
            tuple(sorted(
                (item for item in evidence if item.timeframe is timeframe),
                key=lambda item: (item.trading_date, item.observation_boundary.observed_at),
            )),
        )
        for timeframe in IntradayTimeframe
        if any(item.timeframe is timeframe for item in evidence)
    )
    return StructuralProjection(
        canonical_instrument_id=first.instrument.canonical_instrument_id,
        mapping_identity=first.instrument.mapping_identity,
        evidence_by_timeframe=grouped,
        slice1e_context=slice1e_context,
    )


def _pair_relationships(
    run: IntradayRun, reconciliation: CandleReconciliation,
    candles: tuple[GovernedCandle, ...],
) -> list[StructuralFact]:
    result: list[StructuralFact] = []
    for previous, current in zip(candles, candles[1:]):
        for field, higher, lower, equal in (
            ("high", StructuralFactType.HIGHER_HIGH, StructuralFactType.LOWER_HIGH, StructuralFactType.EQUAL_HIGH),
            ("low", StructuralFactType.HIGHER_LOW, StructuralFactType.LOWER_LOW, StructuralFactType.EQUAL_LOW),
            ("close", StructuralFactType.HIGHER_CLOSE, StructuralFactType.LOWER_CLOSE, StructuralFactType.EQUAL_CLOSE),
        ):
            prior_value, current_value = getattr(previous, field), getattr(current, field)
            fact_type = higher if current_value > prior_value else lower if current_value < prior_value else equal
            direction = (
                FactualDirection.UP if current_value > prior_value
                else FactualDirection.DOWN if current_value < prior_value
                else FactualDirection.NONE
            )
            result.append(_fact(
                run, reconciliation, fact_type=fact_type, direction=direction,
                values=(("previous_value", prior_value), ("current_value", current_value)),
                source_candles=(previous, current), policy=LOCAL_RELATION_POLICY,
                start=previous.boundary.start, end=current.boundary.end,
                confirmation=current.boundary.end,
            ))
    return result


def _local_pivots(
    run: IntradayRun, reconciliation: CandleReconciliation,
    candles: tuple[GovernedCandle, ...],
) -> list[StructuralFact]:
    result: list[StructuralFact] = []
    for left, pivot, right in zip(candles, candles[1:], candles[2:]):
        common = dict(
            run=run, reconciliation=reconciliation,
            source_candles=(left, pivot, right), policy=LOCAL_RELATION_POLICY,
            start=left.boundary.start, end=right.boundary.end,
            confirmation=right.boundary.end,
            attributes=(("pivot_candle_id", pivot.candle_id),),
        )
        if pivot.high > left.high and pivot.high > right.high:
            result.append(_fact(
                fact_type=StructuralFactType.CANDIDATE_LOCAL_HIGH,
                direction=FactualDirection.NONE,
                values=(("pivot_price", pivot.high),), **common,
            ))
        if pivot.low < left.low and pivot.low < right.low:
            result.append(_fact(
                fact_type=StructuralFactType.CANDIDATE_LOCAL_LOW,
                direction=FactualDirection.NONE,
                values=(("pivot_price", pivot.low),), **common,
            ))
    return result


def _range_facts(
    run: IntradayRun, reconciliation: CandleReconciliation,
    candles: tuple[GovernedCandle, ...], definition: ExplicitRangeDefinition,
) -> list[StructuralFact]:
    included = tuple(
        item for item in candles
        if item.boundary.start >= definition.start_boundary
        and item.boundary.end <= definition.end_boundary
    )
    if not included:
        return [_fact(
            run, reconciliation, fact_type=StructuralFactType.RANGE_SUMMARY,
            direction=FactualDirection.NONE,
            values=(("range_high", definition.high), ("range_low", definition.low),
                    ("range_width", definition.high - definition.low)),
            source_candles=(), policy=EXPLICIT_RANGE_POLICY,
            start=definition.start_boundary, end=definition.end_boundary,
            attributes=(("range_id", definition.range_id),),
            availability=DataAvailability.UNAVAILABLE,
        )]
    inside = sum(definition.low <= item.close <= definition.high for item in included)
    latest = candles[-1]
    latest_relation = _range_position(latest.close, definition)
    result = [_fact(
        run, reconciliation, fact_type=StructuralFactType.RANGE_SUMMARY,
        direction=FactualDirection.NONE,
        values=(
            ("range_high", definition.high), ("range_low", definition.low),
            ("range_width", definition.high - definition.low),
            ("highest_high", max(item.high for item in included)),
            ("lowest_low", min(item.low for item in included)),
            ("included_candle_count", Decimal(len(included))),
            ("included_close_inside_count", Decimal(inside)),
            ("included_close_outside_count", Decimal(len(included) - inside)),
            ("current_completed_close", latest.close),
        ),
        source_candles=included, policy=EXPLICIT_RANGE_POLICY,
        start=definition.start_boundary, end=definition.end_boundary,
        confirmation=included[-1].boundary.end,
        attributes=(("range_id", definition.range_id), ("current_close_relation", latest_relation)),
    )]
    evaluation = tuple(item for item in candles if item.boundary.end > definition.end_boundary)
    previous = included[-1]
    outside: str | None = None
    for candle in evaluation:
        current = _range_position(candle.close, definition)
        if current == "ABOVE" and _range_position(previous.close, definition) != "ABOVE":
            result.append(_range_event(run, reconciliation, definition, StructuralFactType.BOUNDARY_BREAK_ABOVE, previous, candle, FactualDirection.UP))
            outside = "ABOVE"
        elif current == "BELOW" and _range_position(previous.close, definition) != "BELOW":
            result.append(_range_event(run, reconciliation, definition, StructuralFactType.BOUNDARY_BREAK_BELOW, previous, candle, FactualDirection.DOWN))
            outside = "BELOW"
        elif current == "INSIDE" and outside is not None:
            result.append(_range_event(run, reconciliation, definition, StructuralFactType.RETURN_INSIDE, previous, candle, FactualDirection.NONE))
            outside = None
        previous = candle
    return result


def _barrier_facts(
    run: IntradayRun, reconciliation: CandleReconciliation,
    candles: tuple[GovernedCandle, ...], barrier: StructuralBarrier,
) -> list[StructuralFact]:
    if barrier.availability is not DataAvailability.AVAILABLE:
        return []
    result: list[StructuralFact] = []
    previous: GovernedCandle | None = None
    active_break: str | None = None
    for candle in candles:
        position = _level_position(candle.close, barrier.price)
        fact_type = {
            "ABOVE": StructuralFactType.CLOSE_ABOVE_BOUNDARY,
            "BELOW": StructuralFactType.CLOSE_BELOW_BOUNDARY,
            "AT": StructuralFactType.CLOSE_AT_BOUNDARY,
        }[position]
        result.append(_fact(
            run, reconciliation, fact_type=fact_type,
            direction=(FactualDirection.UP if position == "ABOVE" else FactualDirection.DOWN if position == "BELOW" else FactualDirection.NONE),
            values=(("boundary_price", barrier.price), ("completed_close", candle.close)),
            source_candles=(candle,), source_references=(barrier.barrier_id,),
            policy=EXACT_BARRIER_POLICY, start=candle.boundary.start,
            end=candle.boundary.end, confirmation=candle.boundary.end,
            attributes=(("reference_name", barrier.reference_name), ("barrier_family", barrier.barrier_family)),
        ))
        touching = tuple(
            field.upper()
            for field in ("open", "high", "low", "close")
            if getattr(candle, field) == barrier.price
        )
        if touching:
            result.append(_fact(
                run, reconciliation,
                fact_type=StructuralFactType.EXACT_BOUNDARY_TOUCH,
                direction=FactualDirection.NONE,
                values=(("boundary_price", barrier.price),),
                source_candles=(candle,), source_references=(barrier.barrier_id,),
                policy=EXACT_BARRIER_POLICY, start=candle.boundary.start,
                end=candle.boundary.end, confirmation=candle.boundary.end,
                attributes=(
                    ("reference_name", barrier.reference_name),
                    ("barrier_family", barrier.barrier_family),
                    ("matching_fields", ",".join(touching)),
                ),
            ))
        if previous is not None:
            prior = _level_position(previous.close, barrier.price)
            if position == "ABOVE" and prior != "ABOVE":
                result.append(_barrier_event(run, reconciliation, barrier, StructuralFactType.BOUNDARY_BREAK_ABOVE, previous, candle, FactualDirection.UP))
                active_break = "ABOVE"
            elif position == "BELOW" and prior != "BELOW":
                result.append(_barrier_event(run, reconciliation, barrier, StructuralFactType.BOUNDARY_BREAK_BELOW, previous, candle, FactualDirection.DOWN))
                active_break = "BELOW"
            elif active_break == "ABOVE" and candle.low <= barrier.price and candle.close > barrier.price:
                result.append(_barrier_event(run, reconciliation, barrier, StructuralFactType.RETEST_FROM_ABOVE, previous, candle, FactualDirection.NONE))
            elif active_break == "BELOW" and candle.high >= barrier.price and candle.close < barrier.price:
                result.append(_barrier_event(run, reconciliation, barrier, StructuralFactType.RETEST_FROM_BELOW, previous, candle, FactualDirection.NONE))
            if (prior == "ABOVE" and position == "BELOW") or (prior == "BELOW" and position == "ABOVE"):
                result.append(_barrier_event(run, reconciliation, barrier, StructuralFactType.CLOSE_BACK_THROUGH, previous, candle, FactualDirection.DOWN if position == "BELOW" else FactualDirection.UP))
        previous = candle
    return result


def _move_facts(
    run: IntradayRun, reconciliation: CandleReconciliation,
    candles: tuple[GovernedCandle, ...], definition: ExplicitMoveDefinition,
) -> list[StructuralFact]:
    indexes = {item.candle_id: index for index, item in enumerate(candles)}
    if definition.start_candle_id not in indexes or definition.end_candle_id not in indexes:
        return [_unavailable_move_fact(
            run, reconciliation, definition,
            tuple(item for item in candles if item.candle_id in {
                definition.start_candle_id, definition.end_candle_id
            }),
            "SOURCE_CANDLE_UNAVAILABLE",
        )]
    start_index, end_index = indexes[definition.start_candle_id], indexes[definition.end_candle_id]
    if start_index >= end_index:
        return [_unavailable_move_fact(
            run, reconciliation, definition,
            (candles[start_index], candles[end_index]), "BOUNDARY_ORDER_INVALID",
        )]
    move_candles = candles[start_index:end_index + 1]
    start, end = move_candles[0], move_candles[-1]
    magnitude = (
        end.high - start.low
        if definition.direction is FactualDirection.UP
        else start.high - end.low
    )
    if magnitude <= 0:
        return [_unavailable_move_fact(
            run, reconciliation, definition, move_candles,
            "DIRECTIONAL_MAGNITUDE_NOT_ESTABLISHED",
        )]
    result = [_fact(
        run, reconciliation,
        fact_type=StructuralFactType.DIRECTIONAL_MOVE_MEASUREMENT,
        direction=definition.direction,
        values=(
            ("move_start_low", start.low), ("move_start_high", start.high),
            ("move_end_low", end.low), ("move_end_high", end.high),
            ("move_magnitude", magnitude), ("candle_count", Decimal(len(move_candles))),
            ("local_high", max(item.high for item in move_candles)),
            ("local_low", min(item.low for item in move_candles)),
        ),
        source_candles=move_candles, policy=EXPLICIT_MOVE_POLICY,
        start=start.boundary.start, end=end.boundary.end,
        confirmation=end.boundary.end, attributes=(("move_id", definition.move_id),),
    )]
    retracement_id = definition.retracement_end_candle_id
    if retracement_id is None:
        return result
    if retracement_id not in indexes or indexes[retracement_id] <= end_index:
        result.append(_fact(
            run, reconciliation,
            fact_type=StructuralFactType.RETRACEMENT_MEASUREMENT,
            direction=(FactualDirection.DOWN if definition.direction is FactualDirection.UP else FactualDirection.UP),
            values=(), source_candles=move_candles, policy=EXPLICIT_MOVE_POLICY,
            start=start.boundary.start, end=end.boundary.end,
            attributes=(("move_id", definition.move_id), ("unavailability_reason", "RETRACEMENT_BOUNDARY_UNAVAILABLE")),
            availability=DataAvailability.UNAVAILABLE,
        ))
        return result
    retracement = candles[end_index + 1:indexes[retracement_id] + 1]
    retracement_high = max(item.high for item in retracement)
    retracement_low = min(item.low for item in retracement)
    retracement_magnitude = (
        end.high - retracement_low
        if definition.direction is FactualDirection.UP
        else retracement_high - end.low
    )
    result.append(_fact(
        run, reconciliation,
        fact_type=StructuralFactType.RETRACEMENT_MEASUREMENT,
        direction=(FactualDirection.DOWN if definition.direction is FactualDirection.UP else FactualDirection.UP),
        values=(
            ("move_magnitude", magnitude),
            ("retracement_high", retracement_high), ("retracement_low", retracement_low),
            ("retracement_magnitude", retracement_magnitude),
            ("retracement_percentage", retracement_magnitude / magnitude * Decimal(100)),
            ("retracement_candle_count", Decimal(len(retracement))),
        ),
        source_candles=(*move_candles, *retracement), policy=EXPLICIT_MOVE_POLICY,
        start=start.boundary.start, end=retracement[-1].boundary.end,
        confirmation=retracement[-1].boundary.end,
        attributes=(("move_id", definition.move_id),),
    ))
    return result


def _unavailable_move_fact(
    run: IntradayRun,
    reconciliation: CandleReconciliation,
    definition: ExplicitMoveDefinition,
    source_candles: tuple[GovernedCandle, ...],
    reason: str,
) -> StructuralFact:
    return _fact(
        run, reconciliation,
        fact_type=StructuralFactType.DIRECTIONAL_MOVE_MEASUREMENT,
        direction=definition.direction, values=(), source_candles=source_candles,
        policy=EXPLICIT_MOVE_POLICY,
        start=(source_candles[0].boundary.start if source_candles else None),
        end=(source_candles[-1].boundary.end if source_candles else None),
        attributes=(("move_id", definition.move_id), ("unavailability_reason", reason)),
        availability=DataAvailability.UNAVAILABLE,
    )


def _range_event(
    run: IntradayRun, reconciliation: CandleReconciliation,
    definition: ExplicitRangeDefinition, fact_type: StructuralFactType,
    previous: GovernedCandle, current: GovernedCandle, direction: FactualDirection,
) -> StructuralFact:
    return _fact(
        run, reconciliation, fact_type=fact_type, direction=direction,
        values=(("range_high", definition.high), ("range_low", definition.low),
                ("previous_close", previous.close), ("completed_close", current.close)),
        source_candles=(previous, current), policy=EXPLICIT_RANGE_POLICY,
        start=previous.boundary.start, end=current.boundary.end,
        confirmation=current.boundary.end, attributes=(("range_id", definition.range_id),),
    )


def _barrier_event(
    run: IntradayRun, reconciliation: CandleReconciliation,
    barrier: StructuralBarrier, fact_type: StructuralFactType,
    previous: GovernedCandle, current: GovernedCandle, direction: FactualDirection,
) -> StructuralFact:
    return _fact(
        run, reconciliation, fact_type=fact_type, direction=direction,
        values=(("boundary_price", barrier.price), ("previous_close", previous.close),
                ("completed_close", current.close)),
        source_candles=(previous, current), source_references=(barrier.barrier_id,),
        policy=EXACT_BARRIER_POLICY, start=previous.boundary.start,
        end=current.boundary.end, confirmation=current.boundary.end,
        attributes=(("reference_name", barrier.reference_name), ("barrier_family", barrier.barrier_family)),
    )


def _fact(
    run: IntradayRun,
    reconciliation: CandleReconciliation,
    *,
    fact_type: StructuralFactType,
    direction: FactualDirection,
    values: tuple[tuple[str, Decimal], ...],
    source_candles: tuple[GovernedCandle, ...],
    policy: str,
    attributes: tuple[tuple[str, str], ...] = (),
    source_references: tuple[str, ...] = (),
    start: datetime | None = None,
    end: datetime | None = None,
    confirmation: datetime | None = None,
    availability: DataAvailability = DataAvailability.AVAILABLE,
) -> StructuralFact:
    fields = {
        "run_id": run.run_id,
        "canonical_instrument_id": reconciliation.instrument.canonical_instrument_id,
        "mapping_identity": reconciliation.instrument.mapping_identity,
        "trading_date": reconciliation.schedule.trading_date,
        "timeframe": reconciliation.timeframe,
        "observation_boundary": reconciliation.observation_boundary,
        "fact_type": fact_type, "direction": direction,
        "values": tuple(StructuralValue(*item) for item in values),
        "attributes": tuple(StructuralAttribute(*item) for item in attributes),
        "source_candle_ids": tuple(item.candle_id for item in source_candles),
        "source_reference_ids": source_references,
        "start_boundary": start, "end_boundary": end,
        "confirmation_boundary": confirmation,
        "availability": availability, "provenance": reconciliation.provenance,
        "policy_version": policy, "schema_identity": STRUCTURAL_FACT_SCHEMA,
    }
    provisional = object.__new__(StructuralFact)
    for name, value in fields.items():
        object.__setattr__(provisional, name, value)
    payload = structural_fact_payload(provisional)
    return StructuralFact(
        fact_id=_identity("STRUCTURAL-FACT-", payload),
        integrity_identity=_identity("SHA256-", payload), **fields,
    )


def _barrier(
    *, family: str, name: str, price: Decimal | None, origin: date,
    origin_session_id: str | None,
    source_identity: str, provenance: SourceProvenance,
    availability: DataAvailability,
) -> StructuralBarrier:
    fields = {
        "barrier_family": family, "reference_name": name, "price": price,
        "origin_trading_date": origin, "origin_timeframe": IntradayTimeframe.DAILY,
        "origin_session_id": origin_session_id,
        "source_identity": source_identity, "provenance": provenance,
        "availability": availability,
    }
    provisional = object.__new__(StructuralBarrier)
    for key, value in fields.items():
        object.__setattr__(provisional, key, value)
    return StructuralBarrier(
        barrier_id=_identity("STRUCTURAL-BARRIER-", _barrier_payload(provisional, include_identity=False)),
        **fields,
    )


def structural_fact_payload(value: StructuralFact) -> dict[str, object]:
    return {
        "schema_identity": value.schema_identity,
        "run_id": value.run_id,
        "canonical_instrument_id": value.canonical_instrument_id,
        "mapping_identity": value.mapping_identity,
        "trading_date": value.trading_date.isoformat(),
        "timeframe": value.timeframe.value,
        "observation_boundary": value.observation_boundary.observed_at.isoformat(),
        "fact_type": value.fact_type.value, "direction": value.direction.value,
        "values": [{"name": item.name, "value": str(item.value)} for item in value.values],
        "attributes": [{"name": item.name, "value": item.value} for item in value.attributes],
        "source_candle_ids": list(value.source_candle_ids),
        "source_reference_ids": list(value.source_reference_ids),
        "start_boundary": _datetime(value.start_boundary),
        "end_boundary": _datetime(value.end_boundary),
        "confirmation_boundary": _datetime(value.confirmation_boundary),
        "availability": value.availability.value,
        "provenance": _provenance_payload(value.provenance),
        "policy_version": value.policy_version,
    }


def structural_evidence_payload(value: StructuralEvidence) -> dict[str, object]:
    return {
        "schema_identity": value.schema_identity,
        "run_id": value.run.run_id,
        "mapping_identity": value.instrument.mapping_identity,
        "trading_date": value.trading_date.isoformat(),
        "timeframe": value.timeframe.value,
        "observation_boundary": value.observation_boundary.observed_at.isoformat(),
        "governed_candle_ids": list(value.governed_candle_ids),
        "barriers": [_barrier_payload(item, include_identity=True) for item in value.barriers],
        "facts": [{"fact_id": item.fact_id, "integrity_identity": item.integrity_identity,
                   "fact": structural_fact_payload(item)} for item in value.facts],
        "availability": value.availability.value,
        "provenance": _provenance_payload(value.provenance),
    }


def _barrier_payload(value: StructuralBarrier, *, include_identity: bool) -> dict[str, object]:
    payload = {
        "barrier_family": value.barrier_family, "reference_name": value.reference_name,
        "price": None if value.price is None else str(value.price),
        "origin_trading_date": value.origin_trading_date.isoformat(),
        "origin_timeframe": value.origin_timeframe.value,
        "origin_session_id": value.origin_session_id,
        "source_identity": value.source_identity,
        "provenance": _provenance_payload(value.provenance),
        "availability": value.availability.value,
    }
    return {"barrier_id": value.barrier_id, **payload} if include_identity else payload


def _provenance_payload(value: SourceProvenance) -> dict[str, object]:
    return {
        "provider": value.provider, "source_identity": value.source_identity,
        "retrieved_at": value.retrieved_at.isoformat(), "source_version": value.source_version,
    }


def _range_position(value: Decimal, definition: ExplicitRangeDefinition) -> str:
    return "ABOVE" if value > definition.high else "BELOW" if value < definition.low else "INSIDE"


def _level_position(value: Decimal, level: Decimal) -> str:
    return "ABOVE" if value > level else "BELOW" if value < level else "AT"


def _identity(prefix: str, payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return f"{prefix}{sha256(canonical.encode('utf-8')).hexdigest()}"


def _decimal(value: Decimal) -> Decimal:
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("INTRADAY_STRUCTURAL_DECIMAL_INVALID") from error
    if not result.is_finite():
        raise ValueError("INTRADAY_STRUCTURAL_DECIMAL_INVALID")
    return result


def _name(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.upper()


def _key(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9_]*", value) is not None


def _aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def _datetime(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


__all__ = [
    "EXACT_BARRIER_POLICY", "EXPLICIT_MOVE_POLICY", "EXPLICIT_RANGE_POLICY",
    "LOCAL_RELATION_POLICY", "STRUCTURAL_FACT_POLICY", "STRUCTURAL_FACT_SCHEMA",
    "ExplicitMoveDefinition", "ExplicitRangeDefinition", "FactualDirection",
    "StructuralAttribute", "StructuralBarrier", "StructuralEvidence", "StructuralFact",
    "StructuralFactType", "StructuralProjection", "StructuralValue",
    "barriers_from_slice1e", "build_structural_evidence", "project_structural_evidence",
    "structural_evidence_payload", "structural_fact_payload",
]
