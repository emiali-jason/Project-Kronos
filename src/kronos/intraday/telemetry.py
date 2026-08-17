"""Slice 3 shadow participation and extension telemetry with no trading authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from hashlib import sha256
import json

from kronos.intraday.candles import CandleReconciliation, ReconciliationResult
from kronos.intraday.contracts import (
    DataAvailability,
    IntradayInstrumentReference,
    IntradayRun,
    IntradayTimeframe,
    ObservationBoundary,
    SourceProvenance,
)


SHADOW_TELEMETRY_SCHEMA = "KRONOS-INTRADAY-V1-SHADOW-TELEMETRY-V1"
SHADOW_TELEMETRY_POLICY = "INTRADAY_SHADOW_TELEMETRY_V1"


class TelemetryType(StrEnum):
    VOLUME_OBSERVATION = "VOLUME_OBSERVATION"
    RECENT_VOLUME_COMPARISON = "RECENT_VOLUME_COMPARISON"
    SESSION_VOLUME_COMPARISON = "SESSION_VOLUME_COMPARISON"
    REFERENCE_DISTANCE = "REFERENCE_DISTANCE"
    STRUCTURAL_REWARD_RISK_MEASUREMENT = "STRUCTURAL_REWARD_RISK_MEASUREMENT"


class FactualComparison(StrEnum):
    EXPANSION = "EXPANSION"
    CONTRACTION = "CONTRACTION"
    UNCHANGED = "UNCHANGED"
    NOT_AVAILABLE = "NOT_AVAILABLE"


@dataclass(frozen=True, slots=True)
class TelemetryValue:
    name: str
    value: Decimal

    def __post_init__(self) -> None:
        value = _decimal(self.value)
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("INTRADAY_TELEMETRY_VALUE_INVALID")
        object.__setattr__(self, "value", value)


@dataclass(frozen=True, slots=True)
class TelemetryAttribute:
    name: str
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name or not isinstance(self.value, str) or not self.value:
            raise ValueError("INTRADAY_TELEMETRY_ATTRIBUTE_INVALID")


@dataclass(frozen=True, slots=True)
class ExplicitTelemetryReferences:
    selected_reference: Decimal | None = None
    selected_reference_identity: str | None = None
    breakout_boundary: Decimal | None = None
    breakout_boundary_identity: str | None = None
    impulse_origin: Decimal | None = None
    impulse_origin_identity: str | None = None
    pullback_reference: Decimal | None = None
    pullback_reference_identity: str | None = None
    next_barrier: Decimal | None = None
    next_barrier_identity: str | None = None
    structural_reward_reference: Decimal | None = None
    structural_reward_reference_identity: str | None = None
    structural_risk_reference: Decimal | None = None
    structural_risk_reference_identity: str | None = None

    def __post_init__(self) -> None:
        for price_name, identity_name in (
            ("selected_reference", "selected_reference_identity"),
            ("breakout_boundary", "breakout_boundary_identity"),
            ("impulse_origin", "impulse_origin_identity"),
            ("pullback_reference", "pullback_reference_identity"),
            ("next_barrier", "next_barrier_identity"),
            ("structural_reward_reference", "structural_reward_reference_identity"),
            ("structural_risk_reference", "structural_risk_reference_identity"),
        ):
            price, identity = getattr(self, price_name), getattr(self, identity_name)
            if (price is None) != (identity is None):
                raise ValueError("INTRADAY_TELEMETRY_REFERENCE_INVALID")
            if price is not None:
                object.__setattr__(self, price_name, _decimal(price))
                if not isinstance(identity, str) or not identity:
                    raise ValueError("INTRADAY_TELEMETRY_REFERENCE_INVALID")


@dataclass(frozen=True, slots=True)
class TelemetryMeasure:
    telemetry_id: str
    telemetry_type: TelemetryType
    timeframe: IntradayTimeframe
    values: tuple[TelemetryValue, ...]
    attributes: tuple[TelemetryAttribute, ...]
    comparison: FactualComparison
    source_candle_ids: tuple[str, ...]
    source_reference_ids: tuple[str, ...]
    availability: DataAvailability
    policy_version: str
    integrity_identity: str

    def __post_init__(self) -> None:
        payload = telemetry_measure_payload(self)
        if (
            type(self.telemetry_type) is not TelemetryType
            or type(self.timeframe) is not IntradayTimeframe
            or any(type(item) is not TelemetryValue for item in self.values)
            or any(type(item) is not TelemetryAttribute for item in self.attributes)
            or len(set(item.name for item in self.values)) != len(self.values)
            or len(set(item.name for item in self.attributes)) != len(self.attributes)
            or type(self.comparison) is not FactualComparison
            or any(not item for item in (*self.source_candle_ids, *self.source_reference_ids))
            or type(self.availability) is not DataAvailability
            or self.policy_version != SHADOW_TELEMETRY_POLICY
            or self.telemetry_id != _identity("SHADOW-TELEMETRY-MEASURE-", payload)
            or self.integrity_identity != _identity("SHA256-", payload)
        ):
            raise ValueError("INTRADAY_TELEMETRY_MEASURE_INVALID")


@dataclass(frozen=True, slots=True)
class ShadowTelemetryEvidence:
    evidence_id: str
    run: IntradayRun
    instrument: IntradayInstrumentReference
    trading_date: date
    timeframe: IntradayTimeframe
    observation_boundary: ObservationBoundary
    governed_candle_ids: tuple[str, ...]
    measures: tuple[TelemetryMeasure, ...]
    availability: DataAvailability
    provenance: SourceProvenance
    integrity_identity: str
    schema_identity: str = SHADOW_TELEMETRY_SCHEMA

    def __post_init__(self) -> None:
        payload = shadow_telemetry_payload(self)
        if (
            type(self.run) is not IntradayRun
            or type(self.instrument) is not IntradayInstrumentReference
            or type(self.trading_date) is not date
            or type(self.timeframe) is not IntradayTimeframe
            or self.observation_boundary != self.run.observation_boundary
            or any(type(item) is not TelemetryMeasure for item in self.measures)
            or any(item.timeframe is not self.timeframe for item in self.measures)
            or any(
                candle_id not in self.governed_candle_ids
                for item in self.measures for candle_id in item.source_candle_ids
            )
            or type(self.availability) is not DataAvailability
            or type(self.provenance) is not SourceProvenance
            or self.schema_identity != SHADOW_TELEMETRY_SCHEMA
            or self.evidence_id != _identity("SHADOW-TELEMETRY-EVIDENCE-", payload)
            or self.integrity_identity != _identity("SHA256-", payload)
        ):
            raise ValueError("INTRADAY_SHADOW_TELEMETRY_INVALID")


def build_shadow_telemetry(
    *,
    run: IntradayRun,
    reconciliation: CandleReconciliation,
    references: ExplicitTelemetryReferences | None = None,
) -> ShadowTelemetryEvidence:
    if (
        type(run) is not IntradayRun
        or type(reconciliation) is not CandleReconciliation
        or run.observation_boundary != reconciliation.observation_boundary
        or (references is not None and type(references) is not ExplicitTelemetryReferences)
    ):
        raise ValueError("INTRADAY_SHADOW_TELEMETRY_REQUEST_INVALID")
    refs = references or ExplicitTelemetryReferences()
    candles = tuple(reconciliation.structural_candles)
    available = reconciliation.result is ReconciliationResult.COMPLETE and bool(candles)
    measures: list[TelemetryMeasure] = []
    if available:
        current = candles[-1]
        measures.append(_measure(
            TelemetryType.VOLUME_OBSERVATION, reconciliation.timeframe,
            (("current_volume", Decimal(current.volume)),),
            source_candles=(current.candle_id,),
        ))
        previous_five = candles[-6:-1] if len(candles) >= 6 else ()
        measures.append(_volume_comparison(
            TelemetryType.RECENT_VOLUME_COMPARISON,
            reconciliation.timeframe, current, previous_five,
        ))
        measures.append(_volume_comparison(
            TelemetryType.SESSION_VOLUME_COMPARISON,
            reconciliation.timeframe, current, candles[:-1],
        ))
        for name, price, identity in (
            ("SELECTED_REFERENCE", refs.selected_reference, refs.selected_reference_identity),
            ("BREAKOUT_BOUNDARY", refs.breakout_boundary, refs.breakout_boundary_identity),
            ("IMPULSE_ORIGIN", refs.impulse_origin, refs.impulse_origin_identity),
            ("PULLBACK_REFERENCE", refs.pullback_reference, refs.pullback_reference_identity),
            ("NEXT_BARRIER", refs.next_barrier, refs.next_barrier_identity),
        ):
            measures.append(_distance(
                reconciliation.timeframe, current.close, current.candle_id,
                name, price, identity,
            ))
        measures.append(_reward_risk(
            reconciliation.timeframe, current.close, current.candle_id, refs,
        ))
    availability = (
        DataAvailability.AVAILABLE if available else
        reconciliation.availability if reconciliation.result is not ReconciliationResult.COMPLETE
        else DataAvailability.UNAVAILABLE
    )
    fields = {
        "run": run, "instrument": reconciliation.instrument,
        "trading_date": reconciliation.schedule.trading_date,
        "timeframe": reconciliation.timeframe,
        "observation_boundary": reconciliation.observation_boundary,
        "governed_candle_ids": tuple(item.candle_id for item in candles),
        "measures": tuple(measures), "availability": availability,
        "provenance": reconciliation.provenance,
        "schema_identity": SHADOW_TELEMETRY_SCHEMA,
    }
    provisional = object.__new__(ShadowTelemetryEvidence)
    for name, value in fields.items():
        object.__setattr__(provisional, name, value)
    payload = shadow_telemetry_payload(provisional)
    return ShadowTelemetryEvidence(
        evidence_id=_identity("SHADOW-TELEMETRY-EVIDENCE-", payload),
        integrity_identity=_identity("SHA256-", payload), **fields,
    )


def _volume_comparison(
    telemetry_type: TelemetryType,
    timeframe: IntradayTimeframe,
    current,
    previous: tuple,
) -> TelemetryMeasure:
    if not previous:
        return _measure(
            telemetry_type, timeframe, (), source_candles=(current.candle_id,),
            availability=DataAvailability.UNAVAILABLE,
        )
    mean = sum((Decimal(item.volume) for item in previous), Decimal(0)) / Decimal(len(previous))
    ratio = None if mean == 0 else Decimal(current.volume) / mean
    comparison = (
        FactualComparison.EXPANSION if Decimal(current.volume) > mean
        else FactualComparison.CONTRACTION if Decimal(current.volume) < mean
        else FactualComparison.UNCHANGED
    )
    values = [
        ("current_volume", Decimal(current.volume)),
        ("comparison_mean", mean),
        ("comparison_candle_count", Decimal(len(previous))),
        *(
            (f"comparison_volume_{index:03d}", Decimal(item.volume))
            for index, item in enumerate(previous, start=1)
        ),
    ]
    if ratio is not None:
        values.append(("volume_ratio", ratio))
    return _measure(
        telemetry_type, timeframe, tuple(values), comparison=comparison,
        source_candles=(*tuple(item.candle_id for item in previous), current.candle_id),
    )


def _distance(
    timeframe: IntradayTimeframe,
    current: Decimal,
    candle_id: str,
    name: str,
    reference: Decimal | None,
    reference_id: str | None,
) -> TelemetryMeasure:
    if reference is None or reference_id is None:
        return _measure(
            TelemetryType.REFERENCE_DISTANCE, timeframe, (),
            comparison=FactualComparison.NOT_AVAILABLE,
            source_candles=(candle_id,), availability=DataAvailability.UNAVAILABLE,
            attributes=(("reference_role", name),),
        )
    signed = current - reference
    return _measure(
        TelemetryType.REFERENCE_DISTANCE, timeframe,
        (("current_price", current), ("reference_price", reference),
         ("signed_distance", signed), ("absolute_distance", abs(signed))),
        source_candles=(candle_id,), source_references=(reference_id,),
        attributes=(("reference_role", name),),
    )


def _reward_risk(
    timeframe: IntradayTimeframe,
    current: Decimal,
    candle_id: str,
    refs: ExplicitTelemetryReferences,
) -> TelemetryMeasure:
    reward, risk = refs.structural_reward_reference, refs.structural_risk_reference
    reward_id, risk_id = (
        refs.structural_reward_reference_identity,
        refs.structural_risk_reference_identity,
    )
    if reward is None or risk is None or reward_id is None or risk_id is None:
        return _measure(
            TelemetryType.STRUCTURAL_REWARD_RISK_MEASUREMENT, timeframe, (),
            comparison=FactualComparison.NOT_AVAILABLE,
            source_candles=(candle_id,), availability=DataAvailability.UNAVAILABLE,
        )
    reward_distance, risk_distance = abs(reward - current), abs(current - risk)
    values = [
        ("current_price", current), ("structural_reward_reference", reward),
        ("structural_risk_reference", risk), ("structural_reward", reward_distance),
        ("structural_risk", risk_distance),
    ]
    if risk_distance != 0:
        values.append(("structural_reward_risk_ratio", reward_distance / risk_distance))
    return _measure(
        TelemetryType.STRUCTURAL_REWARD_RISK_MEASUREMENT, timeframe,
        tuple(values), source_candles=(candle_id,),
        source_references=(reward_id, risk_id),
    )


def _measure(
    telemetry_type: TelemetryType,
    timeframe: IntradayTimeframe,
    values: tuple[tuple[str, Decimal], ...],
    *,
    comparison: FactualComparison = FactualComparison.NOT_AVAILABLE,
    source_candles: tuple[str, ...] = (),
    source_references: tuple[str, ...] = (),
    attributes: tuple[tuple[str, str], ...] = (),
    availability: DataAvailability = DataAvailability.AVAILABLE,
) -> TelemetryMeasure:
    fields = {
        "telemetry_type": telemetry_type, "timeframe": timeframe,
        "values": tuple(TelemetryValue(name, value) for name, value in values),
        "attributes": tuple(TelemetryAttribute(name, value) for name, value in attributes),
        "comparison": comparison,
        "source_candle_ids": source_candles,
        "source_reference_ids": source_references,
        "availability": availability, "policy_version": SHADOW_TELEMETRY_POLICY,
    }
    provisional = object.__new__(TelemetryMeasure)
    for name, value in fields.items():
        object.__setattr__(provisional, name, value)
    payload = telemetry_measure_payload(provisional)
    return TelemetryMeasure(
        telemetry_id=_identity("SHADOW-TELEMETRY-MEASURE-", payload),
        integrity_identity=_identity("SHA256-", payload), **fields,
    )


def telemetry_measure_payload(value: TelemetryMeasure) -> dict[str, object]:
    return {
        "telemetry_type": value.telemetry_type.value,
        "timeframe": value.timeframe.value,
        "values": [{"name": item.name, "value": str(item.value)} for item in value.values],
        "attributes": [{"name": item.name, "value": item.value} for item in value.attributes],
        "comparison": value.comparison.value,
        "source_candle_ids": list(value.source_candle_ids),
        "source_reference_ids": list(value.source_reference_ids),
        "availability": value.availability.value,
        "policy_version": value.policy_version,
    }


def shadow_telemetry_payload(value: ShadowTelemetryEvidence) -> dict[str, object]:
    return {
        "schema_identity": value.schema_identity,
        "run_id": value.run.run_id,
        "mapping_identity": value.instrument.mapping_identity,
        "trading_date": value.trading_date.isoformat(),
        "timeframe": value.timeframe.value,
        "observation_boundary": value.observation_boundary.observed_at.isoformat(),
        "governed_candle_ids": list(value.governed_candle_ids),
        "measures": [
            {"telemetry_id": item.telemetry_id, "integrity_identity": item.integrity_identity,
             "measure": telemetry_measure_payload(item)}
            for item in value.measures
        ],
        "availability": value.availability.value,
        "provenance": {
            "provider": value.provenance.provider,
            "source_identity": value.provenance.source_identity,
            "retrieved_at": value.provenance.retrieved_at.isoformat(),
            "source_version": value.provenance.source_version,
        },
    }


def _identity(prefix: str, payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return f"{prefix}{sha256(canonical.encode('utf-8')).hexdigest()}"


def _decimal(value: Decimal) -> Decimal:
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("INTRADAY_TELEMETRY_DECIMAL_INVALID") from error
    if not result.is_finite():
        raise ValueError("INTRADAY_TELEMETRY_DECIMAL_INVALID")
    return result


__all__ = [
    "SHADOW_TELEMETRY_POLICY", "SHADOW_TELEMETRY_SCHEMA",
    "ExplicitTelemetryReferences", "FactualComparison", "ShadowTelemetryEvidence",
    "TelemetryAttribute", "TelemetryMeasure", "TelemetryType", "TelemetryValue", "build_shadow_telemetry",
    "shadow_telemetry_payload", "telemetry_measure_payload",
]
