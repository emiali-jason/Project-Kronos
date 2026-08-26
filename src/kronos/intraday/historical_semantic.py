"""WO-06S immutable completed-candle payload and semantic research facts.

The contracts in this module retain Provider-neutral facts only.  They do not
admit a Probable, rank a subject, create a trade, or establish Risk or broker
authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json
from typing import Iterable, Mapping, Sequence

from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.historical_qualification import HistoricalPreviousSessionFacts
from kronos.intraday.structure import LOCAL_RELATION_POLICY, StructuralFactType


HISTORICAL_CANDLE_PAYLOAD_IDENTITY = (
    "KRONOS-INTRADAY-GOVERNED-HISTORICAL-CANDLE-PAYLOAD-V1"
)
SEMANTIC_QUALIFICATION_FACT_IDENTITY = (
    "KRONOS-INTRADAY-SEMANTIC-QUALIFICATION-FACT-V1"
)
SEMANTIC_QUALIFICATION_EVIDENCE_IDENTITY = (
    "KRONOS-INTRADAY-SEMANTIC-QUALIFICATION-EVIDENCE-V1"
)
WO06S_CONTRACT_VERSION = "1.0.0"
WO06S_PROVENANCE = "KRONOS-WO-06S-SEMANTIC-EVIDENCE-001"


class SemanticEvidenceError(ValueError):
    """Sanitized invalid or conflicting semantic evidence."""


class SemanticAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class SemanticDirection(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    NON_DIRECTIONAL = "NON_DIRECTIONAL"
    CONFLICTING = "CONFLICTING"
    UNAVAILABLE = "UNAVAILABLE"


class SemanticFactFamily(StrEnum):
    DAILY_CONTEXT = "1D_CONTEXT"
    HOURLY_REGIME = "1H_REGIME"
    FIFTEEN_MINUTE_STRUCTURE = "15M_STRUCTURE"
    DIRECTIONAL_COHERENCE = "DIRECTIONAL_COHERENCE"
    VOLUME_PARTICIPATION = "VOLUME_PARTICIPATION"
    FIVE_MINUTE_PROGRESSION = "5M_PROGRESSION"
    PDH_PDL_RELATIONSHIP = "PDH_PDL_RELATIONSHIP"
    CPR_LOCATION = "CPR_LOCATION"
    CLASSIC_PIVOT_RELATIONSHIPS = "CLASSIC_PIVOT_RELATIONSHIPS"


@dataclass(frozen=True, slots=True)
class GovernedHistoricalCandlePayload:
    candle_identity: str
    canonical_subject_identity: str
    exchange: str
    market_identity: str
    market_session_identity: str
    timeframe: IntradayTimeframe
    candle_start: datetime
    candle_end: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    completion_state: str
    available_at: datetime
    observation_boundary: datetime
    provider_source_identity: str
    source_operation_identity: str
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = HISTORICAL_CANDLE_PAYLOAD_IDENTITY
    schema_version: str = WO06S_CONTRACT_VERSION

    def __post_init__(self) -> None:
        prices = (self.open, self.high, self.low, self.close)
        if (
            not self.candle_identity.startswith("INTRADAY-GOVERNED-HISTORICAL-CANDLE-")
            or not _texts((
                self.canonical_subject_identity,
                self.exchange,
                self.market_identity,
                self.market_session_identity,
                self.provider_source_identity,
                self.source_operation_identity,
            ))
            or type(self.timeframe) is not IntradayTimeframe
            or not _aware(self.candle_start)
            or not _aware(self.candle_end)
            or not _aware(self.available_at)
            or not _aware(self.observation_boundary)
            or self.candle_start >= self.candle_end
            or self.available_at != self.candle_end
            or self.candle_end > self.observation_boundary
            or any(type(item) is not Decimal or not item.is_finite() or item < 0 for item in prices)
            or self.high < max(self.open, self.low, self.close)
            or self.low > min(self.open, self.high, self.close)
            or type(self.volume) is not int
            or self.volume < 0
            or self.completion_state != "COMPLETE"
            or not _texts(self.provenance)
            or self.schema_identity != HISTORICAL_CANDLE_PAYLOAD_IDENTITY
            or self.schema_version != WO06S_CONTRACT_VERSION
        ):
            raise SemanticEvidenceError("SEMANTIC_CANDLE_PAYLOAD_INVALID")
        _verify(
            self,
            "candle_identity",
            "INTRADAY-GOVERNED-HISTORICAL-CANDLE-",
            "INTEGRITY-GOVERNED-HISTORICAL-CANDLE-",
        )


def create_governed_historical_candle_payload(
    *,
    canonical_subject_identity: str,
    exchange: str,
    market_identity: str,
    market_session_identity: str,
    timeframe: IntradayTimeframe,
    candle_start: datetime,
    candle_end: datetime,
    open: Decimal,
    high: Decimal,
    low: Decimal,
    close: Decimal,
    volume: int,
    observation_boundary: datetime,
    provider_source_identity: str,
    source_operation_identity: str,
    provenance: tuple[str, ...],
) -> GovernedHistoricalCandlePayload:
    values = {
        "canonical_subject_identity": canonical_subject_identity,
        "exchange": exchange,
        "market_identity": market_identity,
        "market_session_identity": market_session_identity,
        "timeframe": timeframe,
        "candle_start": candle_start,
        "candle_end": candle_end,
        "open": open,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "completion_state": "COMPLETE",
        "available_at": candle_end,
        "observation_boundary": observation_boundary,
        "provider_source_identity": provider_source_identity,
        "source_operation_identity": source_operation_identity,
        "provenance": provenance,
        "schema_identity": HISTORICAL_CANDLE_PAYLOAD_IDENTITY,
        "schema_version": WO06S_CONTRACT_VERSION,
    }
    return GovernedHistoricalCandlePayload(
        candle_identity=_identity("INTRADAY-GOVERNED-HISTORICAL-CANDLE-", values),
        integrity_identity=_identity("INTEGRITY-GOVERNED-HISTORICAL-CANDLE-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class SemanticQualificationFact:
    fact_identity: str
    family: SemanticFactFamily
    canonical_subject_identity: str
    market_session_identity: str
    timeframe: IntradayTimeframe | None
    availability: SemanticAvailability
    direction: SemanticDirection
    attributes: tuple[tuple[str, str], ...]
    values: tuple[tuple[str, Decimal], ...]
    source_evidence_identities: tuple[str, ...]
    available_at: datetime
    observation_boundary: datetime
    policy_identity: str
    source_operation_identity: str
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = SEMANTIC_QUALIFICATION_FACT_IDENTITY
    schema_version: str = WO06S_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            not self.fact_identity.startswith("INTRADAY-SEMANTIC-FACT-")
            or type(self.family) is not SemanticFactFamily
            or not _texts((self.canonical_subject_identity, self.market_session_identity))
            or self.timeframe is not None and type(self.timeframe) is not IntradayTimeframe
            or type(self.availability) is not SemanticAvailability
            or type(self.direction) is not SemanticDirection
            or any(not _text(name) or not _text(value) for name, value in self.attributes)
            or len({name for name, _ in self.attributes}) != len(self.attributes)
            or any(not _text(name) or type(value) is not Decimal or not value.is_finite() for name, value in self.values)
            or len({name for name, _ in self.values}) != len(self.values)
            or not _texts(self.source_evidence_identities)
            or not _aware(self.available_at)
            or not _aware(self.observation_boundary)
            or self.available_at > self.observation_boundary
            or not _texts((self.policy_identity, self.source_operation_identity))
            or not _texts(self.provenance)
            or self.schema_identity != SEMANTIC_QUALIFICATION_FACT_IDENTITY
            or self.schema_version != WO06S_CONTRACT_VERSION
            or (
                self.availability is SemanticAvailability.UNAVAILABLE
                and self.direction is not SemanticDirection.UNAVAILABLE
            )
        ):
            raise SemanticEvidenceError("SEMANTIC_FACT_INVALID")
        _verify(
            self,
            "fact_identity",
            "INTRADAY-SEMANTIC-FACT-",
            "INTEGRITY-SEMANTIC-FACT-",
        )


def create_semantic_qualification_fact(
    *,
    family: SemanticFactFamily,
    canonical_subject_identity: str,
    market_session_identity: str,
    timeframe: IntradayTimeframe | None,
    availability: SemanticAvailability,
    direction: SemanticDirection,
    attributes: tuple[tuple[str, str], ...],
    values: tuple[tuple[str, Decimal], ...],
    source_evidence_identities: tuple[str, ...],
    available_at: datetime,
    observation_boundary: datetime,
    policy_identity: str,
    source_operation_identity: str,
    provenance: tuple[str, ...],
) -> SemanticQualificationFact:
    data = {
        "family": family,
        "canonical_subject_identity": canonical_subject_identity,
        "market_session_identity": market_session_identity,
        "timeframe": timeframe,
        "availability": availability,
        "direction": direction,
        "attributes": attributes,
        "values": values,
        "source_evidence_identities": source_evidence_identities,
        "available_at": available_at,
        "observation_boundary": observation_boundary,
        "policy_identity": policy_identity,
        "source_operation_identity": source_operation_identity,
        "provenance": provenance,
        "schema_identity": SEMANTIC_QUALIFICATION_FACT_IDENTITY,
        "schema_version": WO06S_CONTRACT_VERSION,
    }
    return SemanticQualificationFact(
        fact_identity=_identity("INTRADAY-SEMANTIC-FACT-", data),
        integrity_identity=_identity("INTEGRITY-SEMANTIC-FACT-", data),
        **data,
    )


@dataclass(frozen=True, slots=True)
class SemanticQualificationEvidence:
    evidence_identity: str
    canonical_subject_identity: str
    market_session_identity: str
    observation_boundary: datetime
    source_bundle_identity: str
    source_operation_identity: str
    candle_payload_identities: tuple[str, ...]
    facts: tuple[SemanticQualificationFact, ...]
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = SEMANTIC_QUALIFICATION_EVIDENCE_IDENTITY
    schema_version: str = WO06S_CONTRACT_VERSION

    def __post_init__(self) -> None:
        expected = set(SemanticFactFamily)
        if (
            not self.evidence_identity.startswith("INTRADAY-SEMANTIC-EVIDENCE-")
            or not _texts((
                self.canonical_subject_identity,
                self.market_session_identity,
                self.source_bundle_identity,
                self.source_operation_identity,
            ))
            or not _aware(self.observation_boundary)
            or not _texts(self.candle_payload_identities)
            or len(set(self.candle_payload_identities)) != len(self.candle_payload_identities)
            or not self.facts
            or any(type(item) is not SemanticQualificationFact for item in self.facts)
            or {item.family for item in self.facts} != expected
            or len(self.facts) != len(expected)
            or any(item.canonical_subject_identity != self.canonical_subject_identity for item in self.facts)
            or any(item.market_session_identity != self.market_session_identity for item in self.facts)
            or any(item.source_operation_identity != self.source_operation_identity for item in self.facts)
            or any(item.fact_identity in self.candle_payload_identities for item in self.facts)
            or not _texts(self.provenance)
            or self.schema_identity != SEMANTIC_QUALIFICATION_EVIDENCE_IDENTITY
            or self.schema_version != WO06S_CONTRACT_VERSION
        ):
            raise SemanticEvidenceError("SEMANTIC_EVIDENCE_INVALID")
        _verify(
            self,
            "evidence_identity",
            "INTRADAY-SEMANTIC-EVIDENCE-",
            "INTEGRITY-SEMANTIC-EVIDENCE-",
        )


def derive_semantic_qualification_evidence(
    *,
    candle_payloads: Sequence[GovernedHistoricalCandlePayload],
    previous_session_facts: HistoricalPreviousSessionFacts,
    source_bundle_identity: str,
    source_operation_identity: str,
    provenance: tuple[str, ...],
) -> SemanticQualificationEvidence:
    candles = tuple(candle_payloads)
    if (
        not candles
        or any(type(item) is not GovernedHistoricalCandlePayload for item in candles)
        or type(previous_session_facts) is not HistoricalPreviousSessionFacts
        or not _texts((source_bundle_identity, source_operation_identity))
        or not _texts(provenance)
    ):
        raise SemanticEvidenceError("SEMANTIC_DERIVATION_INPUT_INVALID")
    subject = candles[0].canonical_subject_identity
    session = candles[0].market_session_identity
    boundary = candles[0].observation_boundary
    if any(
        item.canonical_subject_identity != subject
        or item.market_session_identity != session
        or item.observation_boundary != boundary
        or item.source_operation_identity != source_operation_identity
        for item in candles
    ):
        raise SemanticEvidenceError("SEMANTIC_DERIVATION_INPUT_INVALID")
    by_timeframe = {
        timeframe: tuple(sorted(
            (item for item in candles if item.timeframe is timeframe),
            key=lambda item: item.candle_start,
        ))
        for timeframe in IntradayTimeframe
    }
    daily = by_timeframe[IntradayTimeframe.DAILY]
    hourly = by_timeframe[IntradayTimeframe.ONE_HOUR]
    fifteen = by_timeframe[IntradayTimeframe.FIFTEEN_MINUTES]
    five = by_timeframe[IntradayTimeframe.FIVE_MINUTES]
    if len(daily) != 1 or len(hourly) < 2 or len(fifteen) < 2 or len(five) < 2:
        raise SemanticEvidenceError("SEMANTIC_COMPLETED_CANDLES_INSUFFICIENT")

    facts = [
        _daily_context(daily[0], previous_session_facts, source_operation_identity, provenance),
        _movement_fact(SemanticFactFamily.HOURLY_REGIME, hourly[-2:], source_operation_identity, provenance),
        _movement_fact(SemanticFactFamily.FIFTEEN_MINUTE_STRUCTURE, fifteen[-2:], source_operation_identity, provenance),
        _participation_fact(five[-2:], source_operation_identity, provenance),
        _movement_fact(SemanticFactFamily.FIVE_MINUTE_PROGRESSION, five[-2:], source_operation_identity, provenance),
    ]
    facts.insert(3, _coherence_fact(facts[1], facts[2], source_operation_identity, provenance))
    facts.extend(_auxiliary_facts(
        current=five[-1],
        previous=previous_session_facts,
        source_operation_identity=source_operation_identity,
        provenance=provenance,
    ))
    data = {
        "canonical_subject_identity": subject,
        "market_session_identity": session,
        "observation_boundary": boundary,
        "source_bundle_identity": source_bundle_identity,
        "source_operation_identity": source_operation_identity,
        "candle_payload_identities": tuple(item.candle_identity for item in candles),
        "facts": tuple(facts),
        "provenance": provenance,
        "schema_identity": SEMANTIC_QUALIFICATION_EVIDENCE_IDENTITY,
        "schema_version": WO06S_CONTRACT_VERSION,
    }
    return SemanticQualificationEvidence(
        evidence_identity=_identity("INTRADAY-SEMANTIC-EVIDENCE-", data),
        integrity_identity=_identity("INTEGRITY-SEMANTIC-EVIDENCE-", data),
        **data,
    )


def semantic_artifact_document(value: object) -> dict[str, object]:
    identity = _artifact_identity(value)
    core = {
        "artifact_type": type(value).__name__,
        "artifact_identity": identity,
        "artifact": _normalize(value),
    }
    return {**core, "document_integrity": _identity("INTEGRITY-SEMANTIC-DOCUMENT-", core)}


def semantic_artifact_bytes(value: object) -> bytes:
    return _encode(semantic_artifact_document(value)) + b"\n"


def semantic_artifact_from_bytes(encoded: bytes) -> object:
    try:
        document = json.loads(encoded)
    except (TypeError, ValueError) as error:
        raise SemanticEvidenceError("SEMANTIC_DOCUMENT_INVALID") from error
    verify_semantic_artifact_document(document)
    artifact = document["artifact"]
    if document["artifact_type"] == "GovernedHistoricalCandlePayload":
        return _candle_from_data(artifact)
    if document["artifact_type"] == "SemanticQualificationEvidence":
        return _evidence_from_data(artifact)
    raise SemanticEvidenceError("SEMANTIC_DOCUMENT_INVALID")


def verify_semantic_artifact_document(document: Mapping[str, object]) -> None:
    core = {key: document.get(key) for key in ("artifact_type", "artifact_identity", "artifact")}
    if document.get("document_integrity") != _identity("INTEGRITY-SEMANTIC-DOCUMENT-", core):
        raise SemanticEvidenceError("SEMANTIC_DOCUMENT_INTEGRITY_INVALID")


def _daily_context(
    current: GovernedHistoricalCandlePayload,
    previous: HistoricalPreviousSessionFacts,
    operation: str,
    provenance: tuple[str, ...],
) -> SemanticQualificationFact:
    direction = (
        SemanticDirection.LONG if current.close > previous.close
        else SemanticDirection.SHORT if current.close < previous.close
        else SemanticDirection.NON_DIRECTIONAL
    )
    return create_semantic_qualification_fact(
        family=SemanticFactFamily.DAILY_CONTEXT,
        canonical_subject_identity=current.canonical_subject_identity,
        market_session_identity=current.market_session_identity,
        timeframe=IntradayTimeframe.DAILY,
        availability=SemanticAvailability.AVAILABLE,
        direction=direction,
        attributes=(("close_relationship", _relationship(current.close, previous.close)),),
        values=(("current_close", current.close), ("previous_close", previous.close)),
        source_evidence_identities=(current.candle_identity, previous.facts_identity),
        available_at=current.available_at,
        observation_boundary=current.observation_boundary,
        policy_identity="CURRENT_COMPLETED_DAILY_CLOSE_VS_PREVIOUS_CLOSE_V1",
        source_operation_identity=operation,
        provenance=provenance,
    )


def _movement_fact(
    family: SemanticFactFamily,
    pair: Sequence[GovernedHistoricalCandlePayload],
    operation: str,
    provenance: tuple[str, ...],
) -> SemanticQualificationFact:
    previous, current = tuple(pair)
    relationships = tuple(
        (name, _structural_relationship(name, getattr(current, name), getattr(previous, name)))
        for name in ("high", "low", "close")
    )
    simple = tuple(_relationship(getattr(current, name), getattr(previous, name)) for name in ("high", "low", "close"))
    direction = (
        SemanticDirection.LONG if simple == ("ABOVE", "ABOVE", "ABOVE")
        else SemanticDirection.SHORT if simple == ("BELOW", "BELOW", "BELOW")
        else SemanticDirection.NON_DIRECTIONAL
    )
    return create_semantic_qualification_fact(
        family=family,
        canonical_subject_identity=current.canonical_subject_identity,
        market_session_identity=current.market_session_identity,
        timeframe=current.timeframe,
        availability=SemanticAvailability.AVAILABLE,
        direction=direction,
        attributes=relationships,
        values=tuple(
            (f"previous_{name}", getattr(previous, name)) for name in ("high", "low", "close")
        ) + tuple((f"current_{name}", getattr(current, name)) for name in ("high", "low", "close")),
        source_evidence_identities=(previous.candle_identity, current.candle_identity),
        available_at=current.available_at,
        observation_boundary=current.observation_boundary,
        policy_identity=LOCAL_RELATION_POLICY,
        source_operation_identity=operation,
        provenance=provenance,
    )


def _coherence_fact(
    hourly: SemanticQualificationFact,
    fifteen: SemanticQualificationFact,
    operation: str,
    provenance: tuple[str, ...],
) -> SemanticQualificationFact:
    direction = (
        hourly.direction
        if hourly.direction in (SemanticDirection.LONG, SemanticDirection.SHORT)
        and hourly.direction is fifteen.direction
        else SemanticDirection.CONFLICTING
        if {hourly.direction, fifteen.direction} == {SemanticDirection.LONG, SemanticDirection.SHORT}
        else SemanticDirection.NON_DIRECTIONAL
    )
    return create_semantic_qualification_fact(
        family=SemanticFactFamily.DIRECTIONAL_COHERENCE,
        canonical_subject_identity=hourly.canonical_subject_identity,
        market_session_identity=hourly.market_session_identity,
        timeframe=None,
        availability=SemanticAvailability.AVAILABLE,
        direction=direction,
        attributes=(("hourly_direction", hourly.direction.value), ("fifteen_minute_direction", fifteen.direction.value)),
        values=(),
        source_evidence_identities=(hourly.fact_identity, fifteen.fact_identity),
        available_at=max(hourly.available_at, fifteen.available_at),
        observation_boundary=hourly.observation_boundary,
        policy_identity="EXACT_1H_15M_DIRECTIONAL_COHERENCE_V1",
        source_operation_identity=operation,
        provenance=provenance,
    )


def _participation_fact(
    pair: Sequence[GovernedHistoricalCandlePayload],
    operation: str,
    provenance: tuple[str, ...],
) -> SemanticQualificationFact:
    previous, current = tuple(pair)
    return create_semantic_qualification_fact(
        family=SemanticFactFamily.VOLUME_PARTICIPATION,
        canonical_subject_identity=current.canonical_subject_identity,
        market_session_identity=current.market_session_identity,
        timeframe=IntradayTimeframe.FIVE_MINUTES,
        availability=SemanticAvailability.AVAILABLE,
        direction=SemanticDirection.NON_DIRECTIONAL,
        attributes=(("current_vs_previous_completed_volume", _relationship(Decimal(current.volume), Decimal(previous.volume))),),
        values=(("previous_volume", Decimal(previous.volume)), ("current_volume", Decimal(current.volume))),
        source_evidence_identities=(previous.candle_identity, current.candle_identity),
        available_at=current.available_at,
        observation_boundary=current.observation_boundary,
        policy_identity="IMMEDIATE_PREVIOUS_COMPLETED_VOLUME_COMPARISON_V1",
        source_operation_identity=operation,
        provenance=provenance,
    )


def _auxiliary_facts(
    *,
    current: GovernedHistoricalCandlePayload,
    previous: HistoricalPreviousSessionFacts,
    source_operation_identity: str,
    provenance: tuple[str, ...],
) -> tuple[SemanticQualificationFact, ...]:
    high, low, close = previous.high, previous.low, previous.close
    pivot = (high + low + close) / Decimal(3)
    span = high - low
    pivots = (
        ("P", pivot),
        ("R1", Decimal(2) * pivot - low),
        ("R2", pivot + span),
        ("R3", pivot + Decimal(2) * span),
        ("R4", pivot + Decimal(3) * span),
        ("S1", Decimal(2) * pivot - high),
        ("S2", pivot - span),
        ("S3", pivot - Decimal(2) * span),
        ("S4", pivot - Decimal(3) * span),
    )
    bc = (high + low) / Decimal(2)
    tc = Decimal(2) * pivot - bc
    cpr = (("CPR_PIVOT", pivot), ("CPR_LOWER", min(bc, tc)), ("CPR_UPPER", max(bc, tc)))
    common = {
        "canonical_subject_identity": current.canonical_subject_identity,
        "market_session_identity": current.market_session_identity,
        "timeframe": IntradayTimeframe.FIVE_MINUTES,
        "availability": SemanticAvailability.AVAILABLE,
        "direction": SemanticDirection.NON_DIRECTIONAL,
        "available_at": current.available_at,
        "observation_boundary": current.observation_boundary,
        "source_operation_identity": source_operation_identity,
        "provenance": provenance,
    }
    return (
        create_semantic_qualification_fact(
            family=SemanticFactFamily.PDH_PDL_RELATIONSHIP,
            attributes=(("PDH", _relationship(current.close, high)), ("PDL", _relationship(current.close, low))),
            values=(("current_close", current.close), ("PDH", high), ("PDL", low)),
            source_evidence_identities=(current.candle_identity, previous.facts_identity),
            policy_identity="EXACT_COMPLETED_CLOSE_TO_PDH_PDL_V1",
            **common,
        ),
        create_semantic_qualification_fact(
            family=SemanticFactFamily.CPR_LOCATION,
            attributes=tuple((name, _relationship(current.close, value)) for name, value in cpr),
            values=(("current_close", current.close), *cpr),
            source_evidence_identities=(current.candle_identity, previous.facts_identity),
            policy_identity="EXACT_COMPLETED_CLOSE_TO_CPR_V1",
            **common,
        ),
        create_semantic_qualification_fact(
            family=SemanticFactFamily.CLASSIC_PIVOT_RELATIONSHIPS,
            attributes=tuple((name, _relationship(current.close, value)) for name, value in pivots),
            values=(("current_close", current.close), *pivots),
            source_evidence_identities=(current.candle_identity, previous.facts_identity),
            policy_identity="EXACT_COMPLETED_CLOSE_TO_CLASSIC_PIVOTS_V1",
            **common,
        ),
    )


def _structural_relationship(name: str, current: Decimal, previous: Decimal) -> str:
    types = {
        "high": (StructuralFactType.HIGHER_HIGH, StructuralFactType.LOWER_HIGH, StructuralFactType.EQUAL_HIGH),
        "low": (StructuralFactType.HIGHER_LOW, StructuralFactType.LOWER_LOW, StructuralFactType.EQUAL_LOW),
        "close": (StructuralFactType.HIGHER_CLOSE, StructuralFactType.LOWER_CLOSE, StructuralFactType.EQUAL_CLOSE),
    }[name]
    return (types[0] if current > previous else types[1] if current < previous else types[2]).value


def _relationship(current: Decimal, reference: Decimal) -> str:
    return "ABOVE" if current > reference else "BELOW" if current < reference else "AT"


def _artifact_identity(value: object) -> str:
    if type(value) is GovernedHistoricalCandlePayload:
        return value.candle_identity
    if type(value) is SemanticQualificationEvidence:
        return value.evidence_identity
    raise SemanticEvidenceError("SEMANTIC_ARTIFACT_INVALID")


def _candle_from_data(data: Mapping[str, object]) -> GovernedHistoricalCandlePayload:
    values = dict(data)
    values["timeframe"] = IntradayTimeframe(values["timeframe"])
    for name in ("candle_start", "candle_end", "available_at", "observation_boundary"):
        values[name] = datetime.fromisoformat(str(values[name]))
    for name in ("open", "high", "low", "close"):
        values[name] = Decimal(str(values[name]))
    values["provenance"] = tuple(values["provenance"])
    return GovernedHistoricalCandlePayload(**values)


def _fact_from_data(data: Mapping[str, object]) -> SemanticQualificationFact:
    values = dict(data)
    values["family"] = SemanticFactFamily(values["family"])
    values["timeframe"] = None if values["timeframe"] is None else IntradayTimeframe(values["timeframe"])
    values["availability"] = SemanticAvailability(values["availability"])
    values["direction"] = SemanticDirection(values["direction"])
    values["attributes"] = tuple(tuple(item) for item in values["attributes"])
    values["values"] = tuple((name, Decimal(str(value))) for name, value in values["values"])
    values["source_evidence_identities"] = tuple(values["source_evidence_identities"])
    values["available_at"] = datetime.fromisoformat(str(values["available_at"]))
    values["observation_boundary"] = datetime.fromisoformat(str(values["observation_boundary"]))
    values["provenance"] = tuple(values["provenance"])
    return SemanticQualificationFact(**values)


def _evidence_from_data(data: Mapping[str, object]) -> SemanticQualificationEvidence:
    values = dict(data)
    values["observation_boundary"] = datetime.fromisoformat(str(values["observation_boundary"]))
    values["candle_payload_identities"] = tuple(values["candle_payload_identities"])
    values["facts"] = tuple(_fact_from_data(item) for item in values["facts"])
    values["provenance"] = tuple(values["provenance"])
    return SemanticQualificationEvidence(**values)


def _verify(value: object, identity_name: str, identity_prefix: str, integrity_prefix: str) -> None:
    payload = asdict(value)
    payload.pop(identity_name)
    payload.pop("integrity_identity")
    if getattr(value, identity_name) != _identity(identity_prefix, payload):
        raise SemanticEvidenceError("SEMANTIC_IDENTITY_INVALID")
    if value.integrity_identity != _identity(integrity_prefix, payload):
        raise SemanticEvidenceError("SEMANTIC_INTEGRITY_INVALID")


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(_encode(value)).hexdigest().upper()


def _encode(value: object) -> bytes:
    return json.dumps(_normalize(value), sort_keys=True, separators=(",", ":")).encode("utf-8")


def _normalize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {name: _normalize(item) for name, item in asdict(value).items()}
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(name): _normalize(item) for name, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    return value


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


def _texts(values: Iterable[object]) -> bool:
    retained = tuple(values)
    return bool(retained) and all(_text(item) for item in retained)


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


__all__ = [
    "HISTORICAL_CANDLE_PAYLOAD_IDENTITY",
    "SEMANTIC_QUALIFICATION_EVIDENCE_IDENTITY",
    "SEMANTIC_QUALIFICATION_FACT_IDENTITY",
    "WO06S_CONTRACT_VERSION",
    "WO06S_PROVENANCE",
    "GovernedHistoricalCandlePayload",
    "SemanticAvailability",
    "SemanticDirection",
    "SemanticEvidenceError",
    "SemanticFactFamily",
    "SemanticQualificationEvidence",
    "SemanticQualificationFact",
    "create_governed_historical_candle_payload",
    "create_semantic_qualification_fact",
    "derive_semantic_qualification_evidence",
    "semantic_artifact_bytes",
    "semantic_artifact_document",
    "semantic_artifact_from_bytes",
    "verify_semantic_artifact_document",
]
