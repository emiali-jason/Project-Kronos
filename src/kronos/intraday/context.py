"""Slice 1E factual previous-session, Classic Pivot, and CPR context."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from hashlib import sha256
import json
from typing import Protocol
from zoneinfo import ZoneInfo

from kronos.intraday.candles import ReconciliationResult, reconcile_provider_candles
from kronos.intraday.contracts import (
    DataAvailability,
    IntradayInstrumentReference,
    IntradayRun,
    IntradayTimeframe,
    ObservationBoundary,
    SourceProvenance,
)
from kronos.market.schedule import MarketDaySchedule, MarketWindow, TradingDayStatus
from kronos.provider.contracts.market_data import HistoricalCandle


SLICE_1E_SCHEMA = "KRONOS-INTRADAY-V1-SLICE-1E-CONTEXT-V1"
PREVIOUS_SESSION_FACTS_V1 = "PREVIOUS_SESSION_FACTS_V1"
CLASSIC_PIVOT_POINTS_V1 = "CLASSIC_PIVOT_POINTS_V1"
CPR_V1 = "CPR_V1"
CPR_RELATIONSHIP_POLICY_V1 = "KR-280-CPR-RELATIONSHIP-V1"


class ReferenceRelationship(StrEnum):
    ABOVE = "ABOVE"
    BELOW = "BELOW"
    AT = "AT"


class CprRelationship(StrEnum):
    UNCHANGED = "UNCHANGED"
    INSIDE = "INSIDE"
    OUTSIDE = "OUTSIDE"
    OVERLAPPING_HIGHER = "OVERLAPPING_HIGHER"
    OVERLAPPING_LOWER = "OVERLAPPING_LOWER"


class PreviousTradingScheduleSource(Protocol):
    def previous_trading_schedule(
        self, exchange: str, before_date: date
    ) -> MarketDaySchedule | None: ...


@dataclass(frozen=True, slots=True)
class PreviousSessionFacts:
    evidence_identity: str
    availability: DataAvailability
    current_trading_date: date
    previous_schedule: MarketDaySchedule | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    provenance: SourceProvenance
    observation_boundary: ObservationBoundary
    evidence_family: str = PREVIOUS_SESSION_FACTS_V1

    @property
    def pdh(self) -> Decimal | None:
        return self.high

    @property
    def pdl(self) -> Decimal | None:
        return self.low

    def __post_init__(self) -> None:
        values = (self.high, self.low, self.close)
        available = self.availability is DataAvailability.AVAILABLE
        if (
            type(self.current_trading_date) is not date
            or type(self.availability) is not DataAvailability
            or (self.previous_schedule is not None and type(self.previous_schedule) is not MarketDaySchedule)
            or type(self.provenance) is not SourceProvenance
            or type(self.observation_boundary) is not ObservationBoundary
            or available != all(value is not None for value in values)
            or (available and self.previous_schedule is None)
            or (available and self.previous_schedule.trading_date >= self.current_trading_date)
            or (available and self.high < max(self.low, self.close))
            or any(value is not None and _decimal(value) < 0 for value in values)
            or self.evidence_family != PREVIOUS_SESSION_FACTS_V1
        ):
            raise ValueError("INTRADAY_PREVIOUS_SESSION_FACTS_INVALID")
        normalized = tuple(None if value is None else _decimal(value) for value in values)
        object.__setattr__(self, "high", normalized[0])
        object.__setattr__(self, "low", normalized[1])
        object.__setattr__(self, "close", normalized[2])
        if self.evidence_identity != _identity("PREVIOUS-SESSION-", _previous_payload(self)):
            raise ValueError("INTRADAY_PREVIOUS_SESSION_FACTS_INVALID")


@dataclass(frozen=True, slots=True)
class ClassicPivotEvidence:
    evidence_identity: str
    availability: DataAvailability
    p: Decimal | None
    r1: Decimal | None
    r2: Decimal | None
    r3: Decimal | None
    r4: Decimal | None
    s1: Decimal | None
    s2: Decimal | None
    s3: Decimal | None
    s4: Decimal | None
    evidence_family: str = CLASSIC_PIVOT_POINTS_V1

    def __post_init__(self) -> None:
        values = self.values
        available = self.availability is DataAvailability.AVAILABLE
        if (
            type(self.availability) is not DataAvailability
            or available != all(value is not None for value in values)
            or any(value is not None and not value.is_finite() for value in values)
            or self.evidence_family != CLASSIC_PIVOT_POINTS_V1
            or self.evidence_identity != _identity("CLASSIC-PIVOT-", _pivot_payload(self))
        ):
            raise ValueError("INTRADAY_CLASSIC_PIVOT_EVIDENCE_INVALID")

    @property
    def values(self) -> tuple[Decimal | None, ...]:
        return (self.p, self.r1, self.r2, self.r3, self.r4, self.s1, self.s2, self.s3, self.s4)


@dataclass(frozen=True, slots=True)
class CprEvidence:
    evidence_identity: str
    availability: DataAvailability
    pivot: Decimal | None
    bc: Decimal | None
    tc: Decimal | None
    lower: Decimal | None
    upper: Decimal | None
    width: Decimal | None
    relationship_to_prior: CprRelationship | None
    relationship_policy: str = CPR_RELATIONSHIP_POLICY_V1
    evidence_family: str = CPR_V1

    def __post_init__(self) -> None:
        values = (self.pivot, self.bc, self.tc, self.lower, self.upper, self.width)
        available = self.availability is DataAvailability.AVAILABLE
        if (
            type(self.availability) is not DataAvailability
            or available != all(value is not None for value in values)
            or any(value is not None and not value.is_finite() for value in values)
            or (available and (self.lower > self.upper or self.width != self.upper - self.lower))
            or (self.relationship_to_prior is not None and type(self.relationship_to_prior) is not CprRelationship)
            or self.relationship_policy != CPR_RELATIONSHIP_POLICY_V1
            or self.evidence_family != CPR_V1
            or self.evidence_identity != _identity("CPR-", _cpr_payload(self))
        ):
            raise ValueError("INTRADAY_CPR_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class PriceReferenceFact:
    reference_identity: str
    reference_value: Decimal
    relationship: ReferenceRelationship

    def __post_init__(self) -> None:
        value = _decimal(self.reference_value)
        if (
            not self.reference_identity
            or type(self.relationship) is not ReferenceRelationship
        ):
            raise ValueError("INTRADAY_PRICE_REFERENCE_FACT_INVALID")
        object.__setattr__(self, "reference_value", value)


@dataclass(frozen=True, slots=True)
class Slice1EContext:
    evidence_id: str
    run: IntradayRun
    instrument: IntradayInstrumentReference
    previous_session: PreviousSessionFacts
    classic_pivots: ClassicPivotEvidence
    cpr: CprEvidence
    current_price: Decimal | None
    price_relationships: tuple[PriceReferenceFact, ...]
    integrity_identity: str
    schema_identity: str = SLICE_1E_SCHEMA

    def __post_init__(self) -> None:
        price = None if self.current_price is None else _decimal(self.current_price)
        payload = slice1e_payload(self)
        if (
            type(self.run) is not IntradayRun
            or type(self.instrument) is not IntradayInstrumentReference
            or type(self.previous_session) is not PreviousSessionFacts
            or type(self.classic_pivots) is not ClassicPivotEvidence
            or type(self.cpr) is not CprEvidence
            or any(type(item) is not PriceReferenceFact for item in self.price_relationships)
            or (price is None and bool(self.price_relationships))
            or self.run.observation_boundary != self.previous_session.observation_boundary
            or self.schema_identity != SLICE_1E_SCHEMA
            or self.evidence_id != _identity("INTRADAY-SLICE-1E-", payload)
            or self.integrity_identity != _identity("SHA256-", payload)
        ):
            raise ValueError("INTRADAY_SLICE_1E_CONTEXT_INVALID")
        object.__setattr__(self, "current_price", price)


def build_slice1e_context(
    *,
    run: IntradayRun,
    instrument: IntradayInstrumentReference,
    current_trading_date: date,
    calendar: PreviousTradingScheduleSource,
    previous_session_candles: Sequence[HistoricalCandle],
    provenance: SourceProvenance,
    current_price: Decimal | None = None,
    prior_cpr: CprEvidence | None = None,
) -> Slice1EContext:
    """Build shadow context from the preceding governed completed session only."""

    if (
        type(run) is not IntradayRun
        or type(instrument) is not IntradayInstrumentReference
        or type(current_trading_date) is not date
        or isinstance(previous_session_candles, (str, bytes))
        or not isinstance(previous_session_candles, Sequence)
        or type(provenance) is not SourceProvenance
        or (prior_cpr is not None and type(prior_cpr) is not CprEvidence)
    ):
        raise ValueError("INTRADAY_SLICE_1E_REQUEST_INVALID")
    schedule = calendar.previous_trading_schedule(instrument.exchange, current_trading_date)
    availability = DataAvailability.UNAVAILABLE
    high = low = close = None
    if schedule is not None:
        reconciliation = reconcile_provider_candles(
            instrument=instrument,
            timeframe=IntradayTimeframe.DAILY,
            schedule=schedule,
            provider_candles=previous_session_candles,
            observed_at=run.observation_boundary.observed_at,
            provenance=provenance,
        )
        availability = reconciliation.availability
        if (
            reconciliation.result is ReconciliationResult.COMPLETE
            and len(reconciliation.structural_candles) == 1
        ):
            candle = reconciliation.structural_candles[0]
            high, low, close = candle.high, candle.low, candle.close
        elif reconciliation.result is ReconciliationResult.COMPLETE:
            availability = DataAvailability.INCOMPLETE
    previous = _make_previous(
        availability=availability,
        current_trading_date=current_trading_date,
        schedule=schedule,
        high=high,
        low=low,
        close=close,
        provenance=provenance,
        boundary=run.observation_boundary,
    )
    pivots = classic_pivots(previous)
    cpr = cpr_evidence(previous, prior_cpr=prior_cpr)
    price = None if current_price is None else _decimal(current_price)
    if price is not None and price < 0:
        raise ValueError("INTRADAY_SLICE_1E_REQUEST_INVALID")
    relationships = _price_relationships(price, previous, pivots, cpr)
    provisional = object.__new__(Slice1EContext)
    for name, value in {
        "run": run,
        "instrument": instrument,
        "previous_session": previous,
        "classic_pivots": pivots,
        "cpr": cpr,
        "current_price": price,
        "price_relationships": relationships,
        "schema_identity": SLICE_1E_SCHEMA,
    }.items():
        object.__setattr__(provisional, name, value)
    payload = slice1e_payload(provisional)
    return Slice1EContext(
        evidence_id=_identity("INTRADAY-SLICE-1E-", payload),
        run=run,
        instrument=instrument,
        previous_session=previous,
        classic_pivots=pivots,
        cpr=cpr,
        current_price=price,
        price_relationships=relationships,
        integrity_identity=_identity("SHA256-", payload),
    )


def classic_pivots(previous: PreviousSessionFacts) -> ClassicPivotEvidence:
    if previous.availability is not DataAvailability.AVAILABLE:
        return _make_pivots(DataAvailability.UNAVAILABLE, (None,) * 9)
    high, low, close = previous.high, previous.low, previous.close
    pivot = (high + low + close) / Decimal(3)
    span = high - low
    values = (
        pivot,
        Decimal(2) * pivot - low,
        pivot + span,
        pivot + Decimal(2) * span,
        pivot + Decimal(3) * span,
        Decimal(2) * pivot - high,
        pivot - span,
        pivot - Decimal(2) * span,
        pivot - Decimal(3) * span,
    )
    return _make_pivots(DataAvailability.AVAILABLE, values)


def cpr_evidence(
    previous: PreviousSessionFacts, *, prior_cpr: CprEvidence | None = None
) -> CprEvidence:
    if previous.availability is not DataAvailability.AVAILABLE:
        return _make_cpr(DataAvailability.UNAVAILABLE, (None,) * 6, None)
    high, low, close = previous.high, previous.low, previous.close
    pivot = (high + low + close) / Decimal(3)
    bc = (high + low) / Decimal(2)
    tc = Decimal(2) * pivot - bc
    lower, upper = min(bc, tc), max(bc, tc)
    values = (pivot, bc, tc, lower, upper, upper - lower)
    relationship = None
    if prior_cpr is not None and prior_cpr.availability is DataAvailability.AVAILABLE:
        relationship = _cpr_relationship(values, prior_cpr)
    return _make_cpr(DataAvailability.AVAILABLE, values, relationship)


def slice1e_payload(value: Slice1EContext) -> dict[str, object]:
    return {
        "schema_identity": value.schema_identity,
        "run_id": value.run.run_id,
        "instrument": value.instrument.canonical_instrument_id,
        "mapping_identity": value.instrument.mapping_identity,
        "current_trading_date": value.previous_session.current_trading_date.isoformat(),
        "previous_session": _previous_payload(value.previous_session),
        "classic_pivots": _pivot_payload(value.classic_pivots),
        "cpr": _cpr_payload(value.cpr),
        "current_price": _string(value.current_price),
        "price_relationships": [
            {
                "reference_identity": item.reference_identity,
                "reference_value": str(item.reference_value),
                "relationship": item.relationship.value,
            }
            for item in value.price_relationships
        ],
        "observation_boundary": value.run.observation_boundary.observed_at.isoformat(),
        "provenance": {
            "provider": value.previous_session.provenance.provider,
            "source_identity": value.previous_session.provenance.source_identity,
            "retrieved_at": value.previous_session.provenance.retrieved_at.isoformat(),
            "source_version": value.previous_session.provenance.source_version,
        },
    }


def slice1e_document(value: Slice1EContext) -> dict[str, object]:
    """Return the complete canonical restart document for factual context."""

    schedule = value.previous_session.previous_schedule
    instrument = value.instrument
    provenance = value.previous_session.provenance
    return {
        "schema_identity": value.schema_identity,
        "evidence_id": value.evidence_id,
        "integrity_identity": value.integrity_identity,
        "run": {
            "run_id": value.run.run_id,
            "created_at": value.run.created_at.isoformat(),
            "observation_boundary": value.run.observation_boundary.observed_at.isoformat(),
            "schema_identity": value.run.schema_identity,
        },
        "instrument": {
            "canonical_instrument_id": instrument.canonical_instrument_id,
            "exchange": instrument.exchange,
            "segment": instrument.segment,
            "instrument_type": instrument.instrument_type,
            "provider": instrument.provider,
            "provider_symbol": instrument.provider_symbol,
            "provider_instrument_token": instrument.provider_instrument_token,
            "tick_size": str(instrument.tick_size),
            "lot_size": instrument.lot_size,
            "price_precision": instrument.price_precision,
            "mapping_identity": instrument.mapping_identity,
        },
        "previous_schedule": None if schedule is None else {
            "exchange": schedule.exchange,
            "trading_date": schedule.trading_date.isoformat(),
            "session_id": schedule.session_id,
            "timezone": schedule.timezone,
            "status": schedule.status.value,
            "windows": [
                {"opens_at": item.opens_at.isoformat(), "closes_at": item.closes_at.isoformat()}
                for item in schedule.windows
            ],
            "source_identity": schedule.source_identity,
            "source_version": schedule.source_version,
            "special_session": schedule.special_session,
            "schema_identity": schedule.schema_identity,
        },
        "provenance": {
            "provider": provenance.provider,
            "source_identity": provenance.source_identity,
            "retrieved_at": provenance.retrieved_at.isoformat(),
            "source_version": provenance.source_version,
        },
        "previous_session_evidence_identity": value.previous_session.evidence_identity,
        "classic_pivot_evidence_identity": value.classic_pivots.evidence_identity,
        "cpr_evidence_identity": value.cpr.evidence_identity,
        "evidence": slice1e_payload(value),
    }


def slice1e_from_document(document: dict[str, object]) -> Slice1EContext:
    if not isinstance(document, dict) or set(document) != {
        "schema_identity", "evidence_id", "integrity_identity", "run", "instrument",
        "previous_schedule", "provenance", "previous_session_evidence_identity",
        "classic_pivot_evidence_identity", "cpr_evidence_identity", "evidence",
    }:
        raise ValueError("INTRADAY_SLICE_1E_DOCUMENT_INVALID")
    run_data = document["run"]
    instrument_data = document["instrument"]
    provenance_data = document["provenance"]
    evidence = document["evidence"]
    if not all(isinstance(item, dict) for item in (run_data, instrument_data, provenance_data, evidence)):
        raise ValueError("INTRADAY_SLICE_1E_DOCUMENT_INVALID")
    run = IntradayRun(
        run_id=run_data["run_id"],
        created_at=datetime.fromisoformat(run_data["created_at"]),
        observation_boundary=ObservationBoundary(datetime.fromisoformat(run_data["observation_boundary"])),
        schema_identity=run_data["schema_identity"],
    )
    instrument = IntradayInstrumentReference(
        canonical_instrument_id=instrument_data["canonical_instrument_id"],
        exchange=instrument_data["exchange"], segment=instrument_data["segment"],
        instrument_type=instrument_data["instrument_type"], provider=instrument_data["provider"],
        provider_symbol=instrument_data["provider_symbol"],
        provider_instrument_token=instrument_data["provider_instrument_token"],
        tick_size=Decimal(instrument_data["tick_size"]), lot_size=instrument_data["lot_size"],
        price_precision=instrument_data["price_precision"],
        mapping_identity=instrument_data["mapping_identity"],
    )
    schedule_data = document["previous_schedule"]
    schedule = None
    if schedule_data is not None:
        if not isinstance(schedule_data, dict):
            raise ValueError("INTRADAY_SLICE_1E_DOCUMENT_INVALID")
        zone = ZoneInfo(schedule_data["timezone"])
        schedule = MarketDaySchedule(
            exchange=schedule_data["exchange"],
            trading_date=date.fromisoformat(schedule_data["trading_date"]),
            session_id=schedule_data["session_id"], timezone=schedule_data["timezone"],
            status=TradingDayStatus(schedule_data["status"]),
            windows=tuple(
                MarketWindow(
                    datetime.fromisoformat(item["opens_at"]).astimezone(zone),
                    datetime.fromisoformat(item["closes_at"]).astimezone(zone),
                )
                for item in schedule_data["windows"]
            ),
            source_identity=schedule_data["source_identity"],
            source_version=schedule_data["source_version"],
            special_session=schedule_data["special_session"],
            schema_identity=schedule_data["schema_identity"],
        )
    provenance = SourceProvenance(
        provider=provenance_data["provider"], source_identity=provenance_data["source_identity"],
        retrieved_at=datetime.fromisoformat(provenance_data["retrieved_at"]),
        source_version=provenance_data["source_version"],
    )
    previous_data = evidence["previous_session"]
    pivot_data = evidence["classic_pivots"]
    cpr_data = evidence["cpr"]
    if not all(isinstance(item, dict) for item in (previous_data, pivot_data, cpr_data)):
        raise ValueError("INTRADAY_SLICE_1E_DOCUMENT_INVALID")
    previous = _make_previous(
        availability=DataAvailability(previous_data["availability"]),
        current_trading_date=date.fromisoformat(evidence["current_trading_date"]),
        schedule=schedule,
        high=_optional_decimal(previous_data["high"]),
        low=_optional_decimal(previous_data["low"]),
        close=_optional_decimal(previous_data["close"]),
        provenance=provenance,
        boundary=run.observation_boundary,
    )
    pivot_values = tuple(
        _optional_decimal(pivot_data[name])
        for name in ("p", "r1", "r2", "r3", "r4", "s1", "s2", "s3", "s4")
    )
    pivots = _make_pivots(DataAvailability(pivot_data["availability"]), pivot_values)
    cpr_values = tuple(
        _optional_decimal(cpr_data[name])
        for name in ("pivot", "bc", "tc", "lower", "upper", "width")
    )
    relationship = cpr_data["relationship_to_prior"]
    cpr = _make_cpr(
        DataAvailability(cpr_data["availability"]), cpr_values,
        None if relationship is None else CprRelationship(relationship),
    )
    relationships = tuple(
        PriceReferenceFact(
            item["reference_identity"], Decimal(item["reference_value"]),
            ReferenceRelationship(item["relationship"]),
        )
        for item in evidence["price_relationships"]
    )
    result = Slice1EContext(
        evidence_id=document["evidence_id"], run=run, instrument=instrument,
        previous_session=previous, classic_pivots=pivots, cpr=cpr,
        current_price=_optional_decimal(evidence["current_price"]),
        price_relationships=relationships, integrity_identity=document["integrity_identity"],
        schema_identity=document["schema_identity"],
    )
    if (
        previous.evidence_identity != document["previous_session_evidence_identity"]
        or pivots.evidence_identity != document["classic_pivot_evidence_identity"]
        or cpr.evidence_identity != document["cpr_evidence_identity"]
        or slice1e_document(result) != document
    ):
        raise ValueError("INTRADAY_SLICE_1E_DOCUMENT_INTEGRITY_MISMATCH")
    return result


def _make_previous(**values: object) -> PreviousSessionFacts:
    provisional = object.__new__(PreviousSessionFacts)
    names = {
        "availability": values["availability"],
        "current_trading_date": values["current_trading_date"],
        "previous_schedule": values["schedule"],
        "high": values["high"],
        "low": values["low"],
        "close": values["close"],
        "provenance": values["provenance"],
        "observation_boundary": values["boundary"],
        "evidence_family": PREVIOUS_SESSION_FACTS_V1,
    }
    for name, value in names.items():
        object.__setattr__(provisional, name, value)
    return PreviousSessionFacts(
        evidence_identity=_identity("PREVIOUS-SESSION-", _previous_payload(provisional)),
        **names,
    )


def _make_pivots(
    availability: DataAvailability, values: tuple[Decimal | None, ...]
) -> ClassicPivotEvidence:
    names = ("p", "r1", "r2", "r3", "r4", "s1", "s2", "s3", "s4")
    fields = dict(zip(names, values, strict=True))
    provisional = object.__new__(ClassicPivotEvidence)
    object.__setattr__(provisional, "availability", availability)
    object.__setattr__(provisional, "evidence_family", CLASSIC_PIVOT_POINTS_V1)
    for name, value in fields.items():
        object.__setattr__(provisional, name, value)
    return ClassicPivotEvidence(
        evidence_identity=_identity("CLASSIC-PIVOT-", _pivot_payload(provisional)),
        availability=availability,
        **fields,
    )


def _make_cpr(
    availability: DataAvailability,
    values: tuple[Decimal | None, ...],
    relationship: CprRelationship | None,
) -> CprEvidence:
    names = ("pivot", "bc", "tc", "lower", "upper", "width")
    fields = dict(zip(names, values, strict=True))
    provisional = object.__new__(CprEvidence)
    for name, value in {
        "availability": availability,
        **fields,
        "relationship_to_prior": relationship,
        "relationship_policy": CPR_RELATIONSHIP_POLICY_V1,
        "evidence_family": CPR_V1,
    }.items():
        object.__setattr__(provisional, name, value)
    return CprEvidence(
        evidence_identity=_identity("CPR-", _cpr_payload(provisional)),
        availability=availability,
        relationship_to_prior=relationship,
        **fields,
    )


def _price_relationships(
    price: Decimal | None,
    previous: PreviousSessionFacts,
    pivots: ClassicPivotEvidence,
    cpr: CprEvidence,
) -> tuple[PriceReferenceFact, ...]:
    if price is None or pivots.availability is not DataAvailability.AVAILABLE:
        return ()
    references = (
        ("PDH", previous.pdh), ("PDL", previous.pdl),
        ("P", pivots.p), ("R1", pivots.r1), ("R2", pivots.r2),
        ("R3", pivots.r3), ("R4", pivots.r4), ("S1", pivots.s1),
        ("S2", pivots.s2), ("S3", pivots.s3), ("S4", pivots.s4),
        ("CPR_UPPER", cpr.upper), ("CPR_LOWER", cpr.lower),
    )
    return tuple(
        PriceReferenceFact(name, value, _relative(price, value))
        for name, value in references
    )


def _relative(value: Decimal, reference: Decimal) -> ReferenceRelationship:
    if value > reference:
        return ReferenceRelationship.ABOVE
    if value < reference:
        return ReferenceRelationship.BELOW
    return ReferenceRelationship.AT


def _cpr_relationship(
    current: tuple[Decimal, ...], prior: CprEvidence
) -> CprRelationship:
    pivot, _, _, lower, upper, _ = current
    tolerance = pivot * Decimal("0.0001")
    if abs(pivot - prior.pivot) <= tolerance:
        return CprRelationship.UNCHANGED
    if upper <= prior.upper and lower >= prior.lower:
        return CprRelationship.INSIDE
    if upper >= prior.upper and lower <= prior.lower:
        return CprRelationship.OUTSIDE
    if pivot > prior.pivot:
        return CprRelationship.OVERLAPPING_HIGHER
    return CprRelationship.OVERLAPPING_LOWER


def _previous_payload(value: PreviousSessionFacts) -> dict[str, object]:
    schedule = value.previous_schedule
    return {
        "evidence_family": value.evidence_family,
        "availability": value.availability.value,
        "current_trading_date": value.current_trading_date.isoformat(),
        "previous_trading_date": None if schedule is None else schedule.trading_date.isoformat(),
        "previous_session_id": None if schedule is None else schedule.session_id,
        "previous_schedule_source": None if schedule is None else schedule.source_identity,
        "high": _string(value.high), "low": _string(value.low), "close": _string(value.close),
        "pdh": _string(value.pdh), "pdl": _string(value.pdl),
    }


def _pivot_payload(value: ClassicPivotEvidence) -> dict[str, object]:
    return {
        "evidence_family": value.evidence_family,
        "availability": value.availability.value,
        **{
            name: _string(getattr(value, name))
            for name in ("p", "r1", "r2", "r3", "r4", "s1", "s2", "s3", "s4")
        },
    }


def _cpr_payload(value: CprEvidence) -> dict[str, object]:
    return {
        "evidence_family": value.evidence_family,
        "relationship_policy": value.relationship_policy,
        "availability": value.availability.value,
        **{
            name: _string(getattr(value, name))
            for name in ("pivot", "bc", "tc", "lower", "upper", "width")
        },
        "relationship_to_prior": (
            None if value.relationship_to_prior is None else value.relationship_to_prior.value
        ),
    }


def _identity(prefix: str, payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return f"{prefix}{sha256(canonical.encode('utf-8')).hexdigest()}"


def _decimal(value: Decimal) -> Decimal:
    try:
        converted = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("INTRADAY_CONTEXT_DECIMAL_INVALID") from error
    if not converted.is_finite():
        raise ValueError("INTRADAY_CONTEXT_DECIMAL_INVALID")
    return converted


def _string(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _optional_decimal(value: object) -> Decimal | None:
    return None if value is None else Decimal(value)


__all__ = [
    "CLASSIC_PIVOT_POINTS_V1", "CPR_V1", "PREVIOUS_SESSION_FACTS_V1",
    "CprEvidence", "CprRelationship", "ClassicPivotEvidence", "PreviousSessionFacts",
    "PriceReferenceFact", "ReferenceRelationship", "Slice1EContext",
    "build_slice1e_context", "classic_pivots", "cpr_evidence", "slice1e_document",
    "slice1e_from_document", "slice1e_payload",
]
