"""Frozen Pine-first evidence contract for KRONOS Swing V1.

This module defines producer-neutral data only.  It does not implement Pine
serialization, webhook transport, persistence, Readiness, or trade decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
import json
import math
import re
from typing import Mapping

from kronos.swing.v1.chart_evidence import (
    CHART_QUESTION_SET_V1_ID,
    ChartQuestionId,
)


PINE_EVIDENCE_CONTRACT_ID = "KRONOS-SWING-V1-PINE-EVIDENCE-V1"
PINE_EVIDENCE_CONTRACT_VERSION = "1.1"
PINE_EVIDENCE_INTERNAL_MAX_BYTES = 16_384
TRADINGVIEW_PINE_ALERT_MESSAGE_CEILING = 40_960


class PineProduct(StrEnum):
    MCX = "MCX"
    NSE = "NSE"


class PinePublisherRole(StrEnum):
    PRODUCTION = "PRODUCTION"
    CANDIDATE = "CANDIDATE"


class PineCompatibilityClass(StrEnum):
    IMPLEMENTATION_CHANGE_CONTRACT_COMPATIBLE = (
        "IMPLEMENTATION_CHANGE_CONTRACT_COMPATIBLE"
    )
    NEW_EVIDENCE_ADDITION = "NEW_EVIDENCE_ADDITION"
    EXISTING_EVIDENCE_SEMANTIC_CHANGE = "EXISTING_EVIDENCE_SEMANTIC_CHANGE"
    BREAKING_CONTRACT_CHANGE = "BREAKING_CONTRACT_CHANGE"


class ObservationBoundaryState(StrEnum):
    COMPLETED = "COMPLETED"
    DEVELOPING = "DEVELOPING"
    UNKNOWN = "UNKNOWN"


class PineEvidenceAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class PineEvidenceIntegrity(StrEnum):
    VALID = "VALID"
    DEGRADED = "DEGRADED"
    INCOMPLETE = "INCOMPLETE"
    INVALID = "INVALID"


class PineEvidenceDerivation(StrEnum):
    DIRECT = "DIRECT"
    EXPOSURE = "EXPOSURE"
    DERIVED = "DERIVED"


class PineEvidenceDomain(StrEnum):
    CHART_INSTRUMENT_IDENTITY = "CHART_INSTRUMENT_IDENTITY"
    CHART_TIMEFRAME_IDENTITY = "CHART_TIMEFRAME_IDENTITY"
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


PINE_OWNED_QUESTION_IDS = tuple(PineEvidenceDomain)
BROWSER_OWNED_QUESTION_IDS = (ChartQuestionId.CHART_TEMPLATE_IDENTITY,)
KRONOS_OWNED_QUESTION_IDS = (ChartQuestionId.CONTRADICTIONS,)


class PineProducerType(StrEnum):
    TRADINGVIEW_PINE = "TRADINGVIEW_PINE"


class InstrumentType(StrEnum):
    FUTURE = "FUTURE"
    EQUITY = "EQUITY"
    INDEX = "INDEX"


class ReferenceMarket(StrEnum):
    COMEX = "COMEX"
    NYMEX = "NYMEX"


class PineEvidenceValidationIssueCode(StrEnum):
    WRONG_PRODUCT = "WRONG_PRODUCT"
    WRONG_PINE_IDENTITY = "WRONG_PINE_IDENTITY"
    WRONG_PINE_VERSION = "WRONG_PINE_VERSION"
    WRONG_PINE_BUILD = "WRONG_PINE_BUILD"
    WRONG_SOURCE_HASH = "WRONG_SOURCE_HASH"
    MISSING_MANDATORY_FIELD = "MISSING_MANDATORY_FIELD"
    UNSUPPORTED_CONTRACT_VERSION = "UNSUPPORTED_CONTRACT_VERSION"
    INVALID_TIMEFRAME_REPRESENTATION = "INVALID_TIMEFRAME_REPRESENTATION"
    INVALID_BOUNDARY_REPRESENTATION = "INVALID_BOUNDARY_REPRESENTATION"
    INVALID_PRODUCT_SPECIFIC_FIELDS = "INVALID_PRODUCT_SPECIFIC_FIELDS"
    INVALID_EVIDENCE = "INVALID_EVIDENCE"
    INVALID_EVENT_ID = "INVALID_EVENT_ID"
    PAYLOAD_BUDGET_EXCEEDED = "PAYLOAD_BUDGET_EXCEEDED"
    WRONG_PUBLISHER_ROLE = "WRONG_PUBLISHER_ROLE"
    WRONG_EVIDENCE_CONTRACT = "WRONG_EVIDENCE_CONTRACT"
    WRONG_COMPATIBILITY_CLASS = "WRONG_COMPATIBILITY_CLASS"
    WRONG_PUBLISHER_REGISTRY = "WRONG_PUBLISHER_REGISTRY"


JsonScalar = str | int | float | bool


def _text(value: object) -> bool:
    return type(value) is str and bool(value.strip())


def _sha(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None


def _timeframe(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"(?:[1-9][0-9]{0,4}|[DWM])", value) is not None


def _scalar(value: object) -> bool:
    return (
        type(value) in {str, int, bool}
        or (type(value) is float and math.isfinite(value))
    )


@dataclass(frozen=True, slots=True)
class PineProducer:
    producer_type: PineProducerType
    publisher_role: PinePublisherRole
    pine_identity: str
    pine_version: str
    pine_build: str
    pine_source_sha256: str
    evidence_contract_id: str
    evidence_contract_version: str
    compatibility_class: PineCompatibilityClass
    publisher_registry_id: str

    def __post_init__(self) -> None:
        if (
            type(self.producer_type) is not PineProducerType
            or type(self.publisher_role) is not PinePublisherRole
            or not _text(self.pine_identity)
            or not _text(self.pine_version)
            or not _text(self.pine_build)
            or not _sha(self.pine_source_sha256)
            or self.evidence_contract_id != PINE_EVIDENCE_CONTRACT_ID
            or self.evidence_contract_version != PINE_EVIDENCE_CONTRACT_VERSION
            or type(self.compatibility_class) is not PineCompatibilityClass
            or not _text(self.publisher_registry_id)
        ):
            raise ValueError("PINE_EVIDENCE_PRODUCER_INVALID")


@dataclass(frozen=True, slots=True)
class PineInstrumentIdentity:
    canonical_instrument: str
    tradingview_symbol: str
    analysis_subject: str
    execution_subject: str
    exchange: str
    instrument_type: InstrumentType
    supported_instrument: bool

    def __post_init__(self) -> None:
        if (
            any(
                not _text(item)
                for item in (
                    self.canonical_instrument,
                    self.tradingview_symbol,
                    self.analysis_subject,
                    self.execution_subject,
                    self.exchange,
                )
            )
            or type(self.instrument_type) is not InstrumentType
            or type(self.supported_instrument) is not bool
        ):
            raise ValueError("PINE_EVIDENCE_INSTRUMENT_IDENTITY_INVALID")


@dataclass(frozen=True, slots=True)
class PineTimeframeIdentity:
    chart_timeframe: str
    strategic_timeframe: str
    trend_timeframe: str
    structure_timeframe: str
    execution_timeframe: str

    def __post_init__(self) -> None:
        if any(not _timeframe(item) for item in _field_values(self)):
            raise ValueError("PINE_EVIDENCE_TIMEFRAME_INVALID")


@dataclass(frozen=True, slots=True)
class PineObservationBoundary:
    state: ObservationBoundaryState
    chart_bar_open_ts: datetime
    chart_bar_close_ts: datetime
    evaluated_ts: datetime
    timeframe: str
    confirmed: bool
    source_period_identity: str

    def __post_init__(self) -> None:
        completed = self.state is ObservationBoundaryState.COMPLETED
        developing = self.state is ObservationBoundaryState.DEVELOPING
        if (
            type(self.state) is not ObservationBoundaryState
            or not all(
                _aware(item)
                for item in (
                    self.chart_bar_open_ts,
                    self.chart_bar_close_ts,
                    self.evaluated_ts,
                )
            )
            or self.chart_bar_open_ts >= self.chart_bar_close_ts
            or self.evaluated_ts < self.chart_bar_open_ts
            or not _timeframe(self.timeframe)
            or type(self.confirmed) is not bool
            or not _text(self.source_period_identity)
            or completed != self.confirmed
            or (completed and self.evaluated_ts < self.chart_bar_close_ts)
            or (developing and self.evaluated_ts >= self.chart_bar_close_ts)
            or (self.state is ObservationBoundaryState.UNKNOWN and self.confirmed)
        ):
            raise ValueError("PINE_EVIDENCE_BOUNDARY_INVALID")


@dataclass(frozen=True, slots=True)
class PineEnvelopeProvenance:
    publisher: str
    publisher_role: PinePublisherRole
    publisher_registry_id: str
    lineage_identity: str
    publication_identity: str
    calculation_basis: str

    def __post_init__(self) -> None:
        if (
            not _text(self.publisher)
            or type(self.publisher_role) is not PinePublisherRole
            or not _text(self.publisher_registry_id)
            or not _text(self.lineage_identity)
            or not _text(self.publication_identity)
            or not _text(self.calculation_basis)
        ):
            raise ValueError("PINE_EVIDENCE_ENVELOPE_PROVENANCE_INVALID")


@dataclass(frozen=True, slots=True)
class PineEvidenceProvenance:
    producer_identity: str
    source_period_identity: str
    calculation_identity: str

    def __post_init__(self) -> None:
        if any(not _text(item) for item in _field_values(self)):
            raise ValueError("PINE_EVIDENCE_PROVENANCE_INVALID")


@dataclass(frozen=True, slots=True)
class PineDomainEvidence:
    question_id: PineEvidenceDomain
    availability: PineEvidenceAvailability
    state: str
    value: JsonScalar | None
    values: tuple[JsonScalar, ...]
    source_engine: str
    source_fields: tuple[str, ...]
    derivation: PineEvidenceDerivation
    integrity: PineEvidenceIntegrity
    boundary_state: ObservationBoundaryState
    provenance: PineEvidenceProvenance

    def __post_init__(self) -> None:
        available = self.availability is PineEvidenceAvailability.AVAILABLE
        has_value = self.value is not None or bool(self.values)
        if (
            type(self.question_id) is not PineEvidenceDomain
            or type(self.availability) is not PineEvidenceAvailability
            or not _text(self.state)
            or (self.value is not None and not _scalar(self.value))
            or type(self.values) is not tuple
            or any(not _scalar(item) for item in self.values)
            or not _text(self.source_engine)
            or type(self.source_fields) is not tuple
            or any(not _text(item) for item in self.source_fields)
            or len(set(self.source_fields)) != len(self.source_fields)
            or type(self.derivation) is not PineEvidenceDerivation
            or type(self.integrity) is not PineEvidenceIntegrity
            or type(self.boundary_state) is not ObservationBoundaryState
            or type(self.provenance) is not PineEvidenceProvenance
            or available != has_value
            or (available and not self.source_fields)
        ):
            raise ValueError("PINE_DOMAIN_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class ProductTimeframeState:
    timeframe: str
    availability: PineEvidenceAvailability
    state: str
    boundary_state: ObservationBoundaryState

    def __post_init__(self) -> None:
        if (
            not _timeframe(self.timeframe)
            or type(self.availability) is not PineEvidenceAvailability
            or not _text(self.state)
            or type(self.boundary_state) is not ObservationBoundaryState
        ):
            raise ValueError("PINE_PRODUCT_TIMEFRAME_STATE_INVALID")


@dataclass(frozen=True, slots=True)
class ProductContextEvidence:
    availability: PineEvidenceAvailability
    state: str
    source_fields: tuple[str, ...]
    integrity: PineEvidenceIntegrity

    def __post_init__(self) -> None:
        if (
            type(self.availability) is not PineEvidenceAvailability
            or not _text(self.state)
            or type(self.source_fields) is not tuple
            or any(not _text(item) for item in self.source_fields)
            or type(self.integrity) is not PineEvidenceIntegrity
            or (
                self.availability is PineEvidenceAvailability.AVAILABLE
                and not self.source_fields
            )
        ):
            raise ValueError("PINE_PRODUCT_CONTEXT_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class McxPineEvidenceExtension:
    analytical_identity: str
    reference_symbol: str
    reference_market: ReferenceMarket
    reference_timeframe_states: tuple[ProductTimeframeState, ...]
    readiness_reference_context: ProductContextEvidence
    commodity_workstation_semantics: tuple[str, ...]
    now_trigger_evidence: ProductContextEvidence

    def __post_init__(self) -> None:
        if (
            not _text(self.analytical_identity)
            or not _text(self.reference_symbol)
            or type(self.reference_market) is not ReferenceMarket
            or type(self.reference_timeframe_states) is not tuple
            or not self.reference_timeframe_states
            or any(
                type(item) is not ProductTimeframeState
                for item in self.reference_timeframe_states
            )
            or type(self.readiness_reference_context) is not ProductContextEvidence
            or type(self.commodity_workstation_semantics) is not tuple
            or not self.commodity_workstation_semantics
            or any(not _text(item) for item in self.commodity_workstation_semantics)
            or type(self.now_trigger_evidence) is not ProductContextEvidence
        ):
            raise ValueError("MCX_PINE_EVIDENCE_EXTENSION_INVALID")


@dataclass(frozen=True, slots=True)
class NsePineEvidenceExtension:
    cash_analysis_symbol: str
    futures_to_underlying_provenance: str
    sector_index: str
    parent_index: str
    sector_context: ProductContextEvidence
    broad_market_context: ProductContextEvidence
    relative_alignment: ProductContextEvidence
    reference_completeness: PineEvidenceIntegrity
    readiness_context: ProductContextEvidence
    now: ProductContextEvidence

    def __post_init__(self) -> None:
        if (
            any(
                not _text(item)
                for item in (
                    self.cash_analysis_symbol,
                    self.futures_to_underlying_provenance,
                    self.sector_index,
                    self.parent_index,
                )
            )
            or any(
                type(item) is not ProductContextEvidence
                for item in (
                    self.sector_context,
                    self.broad_market_context,
                    self.relative_alignment,
                    self.readiness_context,
                    self.now,
                )
            )
            or type(self.reference_completeness) is not PineEvidenceIntegrity
            or self.now.availability is not PineEvidenceAvailability.NOT_APPLICABLE
            or self.now.state != "NOT_IN_NSE_V1"
        ):
            raise ValueError("NSE_PINE_EVIDENCE_EXTENSION_INVALID")


@dataclass(frozen=True, slots=True)
class PineEvidenceEnvelope:
    contract_id: str
    contract_version: str
    product: PineProduct
    event_id: str
    producer: PineProducer
    identity: PineInstrumentIdentity
    timeframe: PineTimeframeIdentity
    observation_boundary: PineObservationBoundary
    sequence_number: int
    integrity: PineEvidenceIntegrity
    provenance: PineEnvelopeProvenance
    evidence: tuple[PineDomainEvidence, ...]
    mcx: McxPineEvidenceExtension | None
    nse: NsePineEvidenceExtension | None

    def __post_init__(self) -> None:
        if (
            self.contract_id != PINE_EVIDENCE_CONTRACT_ID
            or self.contract_version != PINE_EVIDENCE_CONTRACT_VERSION
            or type(self.product) is not PineProduct
            or not _sha(self.event_id)
            or type(self.producer) is not PineProducer
            or type(self.identity) is not PineInstrumentIdentity
            or type(self.timeframe) is not PineTimeframeIdentity
            or type(self.observation_boundary) is not PineObservationBoundary
            or self.timeframe.chart_timeframe != self.observation_boundary.timeframe
            or type(self.sequence_number) is not int
            or self.sequence_number < 0
            or type(self.integrity) is not PineEvidenceIntegrity
            or type(self.provenance) is not PineEnvelopeProvenance
            or self.producer.publisher_role is not self.provenance.publisher_role
            or self.producer.publisher_registry_id
            != self.provenance.publisher_registry_id
            or self.producer.pine_identity != self.provenance.publisher
            or type(self.evidence) is not tuple
            or tuple(item.question_id for item in self.evidence)
            != PINE_OWNED_QUESTION_IDS
            or any(type(item) is not PineDomainEvidence for item in self.evidence)
            or any(
                item.boundary_state is not self.observation_boundary.state
                or item.provenance.source_period_identity
                != self.observation_boundary.source_period_identity
                for item in self.evidence
            )
            or not _product_fields_valid(self)
            or self.integrity is not aggregate_integrity(self)
        ):
            raise ValueError("PINE_EVIDENCE_ENVELOPE_INVALID")

    @property
    def stream_identity(self) -> str:
        material = (
            self.product.value,
            self.producer.publisher_role.value,
            self.producer.pine_identity,
            self.producer.pine_build,
            self.producer.pine_source_sha256,
            self.identity.canonical_instrument,
            self.timeframe.chart_timeframe,
        )
        return sha256("\x1f".join(material).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PineEvidenceValidationExpectations:
    product: PineProduct
    publisher_role: PinePublisherRole
    pine_identity: str
    pine_version: str
    pine_build: str
    pine_source_sha256: str
    evidence_contract_id: str
    evidence_contract_version: str
    compatibility_class: PineCompatibilityClass
    publisher_registry_id: str

    def __post_init__(self) -> None:
        if (
            type(self.product) is not PineProduct
            or type(self.publisher_role) is not PinePublisherRole
            or any(
                not _text(item)
                for item in (self.pine_identity, self.pine_version, self.pine_build)
            )
            or not _sha(self.pine_source_sha256)
            or self.evidence_contract_id != PINE_EVIDENCE_CONTRACT_ID
            or self.evidence_contract_version != PINE_EVIDENCE_CONTRACT_VERSION
            or type(self.compatibility_class) is not PineCompatibilityClass
            or not _text(self.publisher_registry_id)
        ):
            raise ValueError("PINE_EVIDENCE_VALIDATION_EXPECTATIONS_INVALID")


@dataclass(frozen=True, slots=True)
class PineEvidenceValidationResult:
    valid: bool
    integrity: PineEvidenceIntegrity
    issues: tuple[PineEvidenceValidationIssueCode, ...]
    canonical_size_bytes: int | None
    envelope: PineEvidenceEnvelope | None


@dataclass(frozen=True, slots=True)
class PineLayer2EvidenceHandoff:
    """Validated Pine facts ready for later provider ingress/reconciliation."""

    contract_id: str
    contract_version: str
    event_id: str
    product: PineProduct
    publisher_role: PinePublisherRole
    publisher_registry_id: str
    registry_entry_id: str
    canonical_instrument: str
    timeframe: str
    question_set_identity: str
    evidence: tuple[PineDomainEvidence, ...]
    browser_owned_questions: tuple[ChartQuestionId, ...]
    kronos_owned_questions: tuple[ChartQuestionId, ...]
    routine_openai_calls: int = 0

    def __post_init__(self) -> None:
        if (
            self.contract_id != PINE_EVIDENCE_CONTRACT_ID
            or self.contract_version != PINE_EVIDENCE_CONTRACT_VERSION
            or type(self.product) is not PineProduct
            or self.publisher_role is not PinePublisherRole.PRODUCTION
            or not _text(self.publisher_registry_id)
            or not _text(self.registry_entry_id)
            or not _sha(self.event_id)
            or not _text(self.canonical_instrument)
            or not _timeframe(self.timeframe)
            or self.question_set_identity != CHART_QUESTION_SET_V1_ID
            or type(self.evidence) is not tuple
            or tuple(item.question_id for item in self.evidence)
            != PINE_OWNED_QUESTION_IDS
            or self.browser_owned_questions != BROWSER_OWNED_QUESTION_IDS
            or self.kronos_owned_questions != KRONOS_OWNED_QUESTION_IDS
            or self.routine_openai_calls != 0
        ):
            raise ValueError("PINE_LAYER2_EVIDENCE_HANDOFF_INVALID")


@dataclass(frozen=True, slots=True)
class PineEvidenceRetentionKey:
    product: PineProduct
    publisher_role: PinePublisherRole
    pine_identity: str
    pine_build: str
    pine_source_sha256: str
    canonical_instrument: str
    timeframe: str
    observation_boundary_state: ObservationBoundaryState
    chart_bar_open_ts: datetime
    chart_bar_close_ts: datetime
    source_period_identity: str

    @classmethod
    def from_envelope(cls, envelope: PineEvidenceEnvelope) -> PineEvidenceRetentionKey:
        return cls(
            product=envelope.product,
            publisher_role=envelope.producer.publisher_role,
            pine_identity=envelope.producer.pine_identity,
            pine_build=envelope.producer.pine_build,
            pine_source_sha256=envelope.producer.pine_source_sha256,
            canonical_instrument=envelope.identity.canonical_instrument,
            timeframe=envelope.timeframe.chart_timeframe,
            observation_boundary_state=envelope.observation_boundary.state,
            chart_bar_open_ts=envelope.observation_boundary.chart_bar_open_ts,
            chart_bar_close_ts=envelope.observation_boundary.chart_bar_close_ts,
            source_period_identity=envelope.observation_boundary.source_period_identity,
        )

    @property
    def identity(self) -> str:
        return sha256(canonical_serialize(self)).hexdigest()


@dataclass(frozen=True, slots=True)
class ParallelPineEvidenceRetention:
    """Collision-safe in-memory model; no durable persistence is implemented."""

    envelopes: tuple[PineEvidenceEnvelope, ...]

    def __post_init__(self) -> None:
        if (
            type(self.envelopes) is not tuple
            or any(type(item) is not PineEvidenceEnvelope for item in self.envelopes)
        ):
            raise ValueError("PARALLEL_PINE_EVIDENCE_RETENTION_INVALID")
        keys = tuple(PineEvidenceRetentionKey.from_envelope(item) for item in self.envelopes)
        if len(set(keys)) != len(keys):
            raise ValueError("PARALLEL_PINE_EVIDENCE_RETENTION_COLLISION")

    def retain(self, envelope: PineEvidenceEnvelope) -> ParallelPineEvidenceRetention:
        if type(envelope) is not PineEvidenceEnvelope:
            raise TypeError("PINE_EVIDENCE_RETENTION_ENVELOPE_INVALID")
        return ParallelPineEvidenceRetention((*self.envelopes, envelope))


def _field_values(instance: object) -> tuple[object, ...]:
    return tuple(getattr(instance, item.name) for item in fields(instance))


def _integrity_rank(value: PineEvidenceIntegrity) -> int:
    return {
        PineEvidenceIntegrity.VALID: 0,
        PineEvidenceIntegrity.DEGRADED: 1,
        PineEvidenceIntegrity.INCOMPLETE: 2,
        PineEvidenceIntegrity.INVALID: 3,
    }[value]


def aggregate_integrity(envelope: PineEvidenceEnvelope) -> PineEvidenceIntegrity:
    values = [item.integrity for item in envelope.evidence]
    if envelope.mcx is not None:
        values.extend(
            (
                envelope.mcx.readiness_reference_context.integrity,
                envelope.mcx.now_trigger_evidence.integrity,
            )
        )
    if envelope.nse is not None:
        values.extend(
            (
                envelope.nse.sector_context.integrity,
                envelope.nse.broad_market_context.integrity,
                envelope.nse.relative_alignment.integrity,
                envelope.nse.reference_completeness,
                envelope.nse.readiness_context.integrity,
                envelope.nse.now.integrity,
            )
        )
    return max(values, key=_integrity_rank)


def _product_fields_valid(envelope: PineEvidenceEnvelope) -> bool:
    if envelope.product is PineProduct.MCX:
        return (
            type(envelope.mcx) is McxPineEvidenceExtension
            and envelope.nse is None
            and envelope.identity.exchange == "MCX"
            and envelope.identity.instrument_type is InstrumentType.FUTURE
            and envelope.identity.analysis_subject == envelope.mcx.analytical_identity
        )
    return (
        envelope.mcx is None
        and type(envelope.nse) is NsePineEvidenceExtension
        and envelope.identity.exchange == "NSE"
        and envelope.identity.instrument_type
        in {InstrumentType.EQUITY, InstrumentType.INDEX, InstrumentType.FUTURE}
        and envelope.identity.analysis_subject == envelope.nse.cash_analysis_symbol
    )


def _primitive(value: object) -> object:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        normalized = value.astimezone(timezone.utc)
        return normalized.isoformat(timespec="seconds").replace("+00:00", "Z")
    if is_dataclass(value):
        return {
            item.name: _primitive(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, tuple):
        return [_primitive(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _primitive(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_primitive(item) for item in value]
    return value


def canonical_serialize(value: object) -> bytes:
    """Serialize a contract value as stable UTF-8 canonical JSON."""

    return json.dumps(
        _primitive(value),
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _event_identity_material(
    *,
    product: PineProduct,
    producer: PineProducer,
    identity: PineInstrumentIdentity,
    timeframe: PineTimeframeIdentity,
    boundary: PineObservationBoundary,
    sequence_number: int,
    provenance: PineEnvelopeProvenance,
    evidence: tuple[PineDomainEvidence, ...],
    mcx: McxPineEvidenceExtension | None,
    nse: NsePineEvidenceExtension | None,
) -> dict[str, object]:
    payload_digest = sha256(
        canonical_serialize({"evidence": evidence, "mcx": mcx, "nse": nse})
    ).hexdigest()
    return {
        "identity": (
            PINE_EVIDENCE_CONTRACT_ID,
            PINE_EVIDENCE_CONTRACT_VERSION,
            product,
            producer.publisher_role,
            producer.pine_identity,
            producer.pine_version,
            producer.pine_build,
            producer.pine_source_sha256,
            producer.evidence_contract_id,
            producer.evidence_contract_version,
            producer.compatibility_class,
            producer.publisher_registry_id,
            identity.canonical_instrument,
            identity.tradingview_symbol,
            timeframe.chart_timeframe,
            boundary.state,
            boundary.chart_bar_open_ts,
            boundary.chart_bar_close_ts,
            boundary.evaluated_ts,
            boundary.timeframe,
            boundary.source_period_identity,
            sequence_number,
        ),
        "evidence_payload_sha256": payload_digest,
    }


def derive_event_id(envelope: PineEvidenceEnvelope) -> str:
    material = _event_identity_material(
        product=envelope.product,
        producer=envelope.producer,
        identity=envelope.identity,
        timeframe=envelope.timeframe,
        boundary=envelope.observation_boundary,
        sequence_number=envelope.sequence_number,
        provenance=envelope.provenance,
        evidence=envelope.evidence,
        mcx=envelope.mcx,
        nse=envelope.nse,
    )
    return sha256(canonical_serialize(material)).hexdigest()


def build_pine_evidence_envelope(
    *,
    product: PineProduct,
    producer: PineProducer,
    identity: PineInstrumentIdentity,
    timeframe: PineTimeframeIdentity,
    observation_boundary: PineObservationBoundary,
    sequence_number: int,
    integrity: PineEvidenceIntegrity,
    provenance: PineEnvelopeProvenance,
    evidence: tuple[PineDomainEvidence, ...],
    mcx: McxPineEvidenceExtension | None = None,
    nse: NsePineEvidenceExtension | None = None,
) -> PineEvidenceEnvelope:
    event_id = sha256(
        canonical_serialize(
            _event_identity_material(
                product=product,
                producer=producer,
                identity=identity,
                timeframe=timeframe,
                boundary=observation_boundary,
                sequence_number=sequence_number,
                provenance=provenance,
                evidence=evidence,
                mcx=mcx,
                nse=nse,
            )
        )
    ).hexdigest()
    return PineEvidenceEnvelope(
        contract_id=PINE_EVIDENCE_CONTRACT_ID,
        contract_version=PINE_EVIDENCE_CONTRACT_VERSION,
        product=product,
        event_id=event_id,
        producer=producer,
        identity=identity,
        timeframe=timeframe,
        observation_boundary=observation_boundary,
        sequence_number=sequence_number,
        integrity=integrity,
        provenance=provenance,
        evidence=evidence,
        mcx=mcx,
        nse=nse,
    )


def _parse_datetime(value: object) -> datetime:
    if not _text(value):
        raise ValueError("PINE_EVIDENCE_DATETIME_INVALID")
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if not _aware(parsed):
        raise ValueError("PINE_EVIDENCE_DATETIME_INVALID")
    return parsed


def _parse_context(payload: Mapping[str, object]) -> ProductContextEvidence:
    return ProductContextEvidence(
        availability=PineEvidenceAvailability(payload["availability"]),
        state=str(payload["state"]),
        source_fields=tuple(payload["source_fields"]),
        integrity=PineEvidenceIntegrity(payload["integrity"]),
    )


def pine_evidence_from_dict(payload: Mapping[str, object]) -> PineEvidenceEnvelope:
    producer = payload["producer"]
    identity = payload["identity"]
    timeframe = payload["timeframe"]
    boundary = payload["observation_boundary"]
    provenance = payload["provenance"]
    if not all(
        isinstance(item, Mapping)
        for item in (producer, identity, timeframe, boundary, provenance)
    ):
        raise ValueError("PINE_EVIDENCE_NESTED_OBJECT_INVALID")

    evidence_items: list[PineDomainEvidence] = []
    for item in payload["evidence"]:
        if not isinstance(item, Mapping) or not isinstance(item["provenance"], Mapping):
            raise ValueError("PINE_DOMAIN_EVIDENCE_INVALID")
        item_provenance = item["provenance"]
        evidence_items.append(
            PineDomainEvidence(
                question_id=PineEvidenceDomain(item["question_id"]),
                availability=PineEvidenceAvailability(item["availability"]),
                state=str(item["state"]),
                value=item["value"],
                values=tuple(item["values"]),
                source_engine=str(item["source_engine"]),
                source_fields=tuple(item["source_fields"]),
                derivation=PineEvidenceDerivation(item["derivation"]),
                integrity=PineEvidenceIntegrity(item["integrity"]),
                boundary_state=ObservationBoundaryState(item["boundary_state"]),
                provenance=PineEvidenceProvenance(
                    producer_identity=str(item_provenance["producer_identity"]),
                    source_period_identity=str(item_provenance["source_period_identity"]),
                    calculation_identity=str(item_provenance["calculation_identity"]),
                ),
            )
        )

    mcx_payload = payload.get("mcx")
    mcx = None
    if isinstance(mcx_payload, Mapping):
        mcx = McxPineEvidenceExtension(
            analytical_identity=str(mcx_payload["analytical_identity"]),
            reference_symbol=str(mcx_payload["reference_symbol"]),
            reference_market=ReferenceMarket(mcx_payload["reference_market"]),
            reference_timeframe_states=tuple(
                ProductTimeframeState(
                    timeframe=str(item["timeframe"]),
                    availability=PineEvidenceAvailability(item["availability"]),
                    state=str(item["state"]),
                    boundary_state=ObservationBoundaryState(item["boundary_state"]),
                )
                for item in mcx_payload["reference_timeframe_states"]
            ),
            readiness_reference_context=_parse_context(
                mcx_payload["readiness_reference_context"]
            ),
            commodity_workstation_semantics=tuple(
                mcx_payload["commodity_workstation_semantics"]
            ),
            now_trigger_evidence=_parse_context(mcx_payload["now_trigger_evidence"]),
        )

    nse_payload = payload.get("nse")
    nse = None
    if isinstance(nse_payload, Mapping):
        nse = NsePineEvidenceExtension(
            cash_analysis_symbol=str(nse_payload["cash_analysis_symbol"]),
            futures_to_underlying_provenance=str(
                nse_payload["futures_to_underlying_provenance"]
            ),
            sector_index=str(nse_payload["sector_index"]),
            parent_index=str(nse_payload["parent_index"]),
            sector_context=_parse_context(nse_payload["sector_context"]),
            broad_market_context=_parse_context(nse_payload["broad_market_context"]),
            relative_alignment=_parse_context(nse_payload["relative_alignment"]),
            reference_completeness=PineEvidenceIntegrity(
                nse_payload["reference_completeness"]
            ),
            readiness_context=_parse_context(nse_payload["readiness_context"]),
            now=_parse_context(nse_payload["now"]),
        )

    return PineEvidenceEnvelope(
        contract_id=str(payload["contract_id"]),
        contract_version=str(payload["contract_version"]),
        product=PineProduct(payload["product"]),
        event_id=str(payload["event_id"]),
        producer=PineProducer(
            producer_type=PineProducerType(producer["producer_type"]),
            publisher_role=PinePublisherRole(producer["publisher_role"]),
            pine_identity=str(producer["pine_identity"]),
            pine_version=str(producer["pine_version"]),
            pine_build=str(producer["pine_build"]),
            pine_source_sha256=str(producer["pine_source_sha256"]),
            evidence_contract_id=str(producer["evidence_contract_id"]),
            evidence_contract_version=str(producer["evidence_contract_version"]),
            compatibility_class=PineCompatibilityClass(
                producer["compatibility_class"]
            ),
            publisher_registry_id=str(producer["publisher_registry_id"]),
        ),
        identity=PineInstrumentIdentity(
            canonical_instrument=str(identity["canonical_instrument"]),
            tradingview_symbol=str(identity["tradingview_symbol"]),
            analysis_subject=str(identity["analysis_subject"]),
            execution_subject=str(identity["execution_subject"]),
            exchange=str(identity["exchange"]),
            instrument_type=InstrumentType(identity["instrument_type"]),
            supported_instrument=identity["supported_instrument"],
        ),
        timeframe=PineTimeframeIdentity(
            chart_timeframe=str(timeframe["chart_timeframe"]),
            strategic_timeframe=str(timeframe["strategic_timeframe"]),
            trend_timeframe=str(timeframe["trend_timeframe"]),
            structure_timeframe=str(timeframe["structure_timeframe"]),
            execution_timeframe=str(timeframe["execution_timeframe"]),
        ),
        observation_boundary=PineObservationBoundary(
            state=ObservationBoundaryState(boundary["state"]),
            chart_bar_open_ts=_parse_datetime(boundary["chart_bar_open_ts"]),
            chart_bar_close_ts=_parse_datetime(boundary["chart_bar_close_ts"]),
            evaluated_ts=_parse_datetime(boundary["evaluated_ts"]),
            timeframe=str(boundary["timeframe"]),
            confirmed=boundary["confirmed"],
            source_period_identity=str(boundary["source_period_identity"]),
        ),
        sequence_number=payload["sequence_number"],
        integrity=PineEvidenceIntegrity(payload["integrity"]),
        provenance=PineEnvelopeProvenance(
            publisher=str(provenance["publisher"]),
            publisher_role=PinePublisherRole(provenance["publisher_role"]),
            publisher_registry_id=str(provenance["publisher_registry_id"]),
            lineage_identity=str(provenance["lineage_identity"]),
            publication_identity=str(provenance["publication_identity"]),
            calculation_basis=str(provenance["calculation_basis"]),
        ),
        evidence=tuple(evidence_items),
        mcx=mcx,
        nse=nse,
    )


def validate_pine_evidence_payload(
    payload: Mapping[str, object],
    expectations: PineEvidenceValidationExpectations | None = None,
) -> PineEvidenceValidationResult:
    issues: list[PineEvidenceValidationIssueCode] = []
    mandatory = {item.name for item in fields(PineEvidenceEnvelope)}
    if not isinstance(payload, Mapping) or not mandatory.issubset(payload):
        return PineEvidenceValidationResult(
            valid=False,
            integrity=PineEvidenceIntegrity.INVALID,
            issues=(PineEvidenceValidationIssueCode.MISSING_MANDATORY_FIELD,),
            canonical_size_bytes=None,
            envelope=None,
        )
    if payload.get("contract_id") != PINE_EVIDENCE_CONTRACT_ID or payload.get(
        "contract_version"
    ) != PINE_EVIDENCE_CONTRACT_VERSION:
        issues.append(PineEvidenceValidationIssueCode.UNSUPPORTED_CONTRACT_VERSION)

    raw_timeframe = payload.get("timeframe")
    if not isinstance(raw_timeframe, Mapping) or any(
        not _timeframe(raw_timeframe.get(name))
        for name in (
            "chart_timeframe",
            "strategic_timeframe",
            "trend_timeframe",
            "structure_timeframe",
            "execution_timeframe",
        )
    ):
        issues.append(PineEvidenceValidationIssueCode.INVALID_TIMEFRAME_REPRESENTATION)

    raw_boundary = payload.get("observation_boundary")
    if not isinstance(raw_boundary, Mapping) or not {
        "state",
        "chart_bar_open_ts",
        "chart_bar_close_ts",
        "evaluated_ts",
        "timeframe",
        "confirmed",
        "source_period_identity",
    }.issubset(raw_boundary) or raw_boundary.get("state") not in {
        item.value for item in ObservationBoundaryState
    }:
        issues.append(PineEvidenceValidationIssueCode.INVALID_BOUNDARY_REPRESENTATION)

    product_value = payload.get("product")
    if product_value == PineProduct.MCX.value:
        identity = payload.get("identity")
        if (
            not isinstance(payload.get("mcx"), Mapping)
            or payload.get("nse") is not None
            or not isinstance(identity, Mapping)
            or identity.get("exchange") != "MCX"
            or identity.get("instrument_type") != InstrumentType.FUTURE.value
        ):
            issues.append(PineEvidenceValidationIssueCode.INVALID_PRODUCT_SPECIFIC_FIELDS)
    elif product_value == PineProduct.NSE.value:
        identity = payload.get("identity")
        if (
            payload.get("mcx") is not None
            or not isinstance(payload.get("nse"), Mapping)
            or not isinstance(identity, Mapping)
            or identity.get("exchange") != "NSE"
        ):
            issues.append(PineEvidenceValidationIssueCode.INVALID_PRODUCT_SPECIFIC_FIELDS)
    else:
        issues.append(PineEvidenceValidationIssueCode.WRONG_PRODUCT)

    envelope: PineEvidenceEnvelope | None = None
    try:
        envelope = pine_evidence_from_dict(payload)
    except KeyError:
        issues.append(PineEvidenceValidationIssueCode.MISSING_MANDATORY_FIELD)
    except (TypeError, ValueError):
        if PineEvidenceValidationIssueCode.INVALID_TIMEFRAME_REPRESENTATION not in issues:
            if PineEvidenceValidationIssueCode.INVALID_BOUNDARY_REPRESENTATION not in issues:
                issues.append(PineEvidenceValidationIssueCode.INVALID_EVIDENCE)

    size = len(canonical_serialize(payload))
    if size > PINE_EVIDENCE_INTERNAL_MAX_BYTES:
        issues.append(PineEvidenceValidationIssueCode.PAYLOAD_BUDGET_EXCEEDED)

    if envelope is not None:
        if derive_event_id(envelope) != envelope.event_id:
            issues.append(PineEvidenceValidationIssueCode.INVALID_EVENT_ID)
        if expectations is not None:
            if envelope.product is not expectations.product:
                issues.append(PineEvidenceValidationIssueCode.WRONG_PRODUCT)
            if envelope.producer.publisher_role is not expectations.publisher_role:
                issues.append(PineEvidenceValidationIssueCode.WRONG_PUBLISHER_ROLE)
            if envelope.producer.pine_identity != expectations.pine_identity:
                issues.append(PineEvidenceValidationIssueCode.WRONG_PINE_IDENTITY)
            if envelope.producer.pine_version != expectations.pine_version:
                issues.append(PineEvidenceValidationIssueCode.WRONG_PINE_VERSION)
            if envelope.producer.pine_build != expectations.pine_build:
                issues.append(PineEvidenceValidationIssueCode.WRONG_PINE_BUILD)
            if envelope.producer.pine_source_sha256 != expectations.pine_source_sha256:
                issues.append(PineEvidenceValidationIssueCode.WRONG_SOURCE_HASH)
            if (
                envelope.producer.evidence_contract_id
                != expectations.evidence_contract_id
                or envelope.producer.evidence_contract_version
                != expectations.evidence_contract_version
            ):
                issues.append(PineEvidenceValidationIssueCode.WRONG_EVIDENCE_CONTRACT)
            if (
                envelope.producer.compatibility_class
                is not expectations.compatibility_class
            ):
                issues.append(PineEvidenceValidationIssueCode.WRONG_COMPATIBILITY_CLASS)
            if (
                envelope.producer.publisher_registry_id
                != expectations.publisher_registry_id
            ):
                issues.append(PineEvidenceValidationIssueCode.WRONG_PUBLISHER_REGISTRY)
        if envelope.integrity is PineEvidenceIntegrity.INVALID:
            issues.append(PineEvidenceValidationIssueCode.INVALID_EVIDENCE)

    deduplicated = tuple(dict.fromkeys(issues))
    return PineEvidenceValidationResult(
        valid=not deduplicated,
        integrity=(
            envelope.integrity
            if envelope is not None and not deduplicated
            else PineEvidenceIntegrity.INVALID
        ),
        issues=deduplicated,
        canonical_size_bytes=size,
        envelope=envelope,
    )


def build_pine_layer2_handoff(
    envelope: PineEvidenceEnvelope,
    registry: object,
) -> PineLayer2EvidenceHandoff:
    from kronos.swing.v1.pine_registry import ApprovedPineRegistry

    result = validate_pine_evidence_payload(_primitive(envelope))
    if not result.valid:
        raise ValueError("PINE_LAYER2_HANDOFF_REQUIRES_VALID_ENVELOPE")
    if type(registry) is not ApprovedPineRegistry:
        raise TypeError("PINE_LAYER2_HANDOFF_REGISTRY_INVALID")
    registry_entry = registry.authoritative_entry(envelope)
    if registry_entry is None:
        raise ValueError("PINE_LAYER2_HANDOFF_AUTHORITY_DENIED")
    return PineLayer2EvidenceHandoff(
        contract_id=envelope.contract_id,
        contract_version=envelope.contract_version,
        event_id=envelope.event_id,
        product=envelope.product,
        publisher_role=envelope.producer.publisher_role,
        publisher_registry_id=envelope.producer.publisher_registry_id,
        registry_entry_id=registry_entry.registry_entry_id,
        canonical_instrument=envelope.identity.canonical_instrument,
        timeframe=envelope.timeframe.chart_timeframe,
        question_set_identity=CHART_QUESTION_SET_V1_ID,
        evidence=envelope.evidence,
        browser_owned_questions=BROWSER_OWNED_QUESTION_IDS,
        kronos_owned_questions=KRONOS_OWNED_QUESTION_IDS,
    )


def payload_budget_headroom(size_bytes: int) -> dict[str, int]:
    if type(size_bytes) is not int or size_bytes < 0:
        raise ValueError("PINE_EVIDENCE_PAYLOAD_SIZE_INVALID")
    return {
        "fixture_size_bytes": size_bytes,
        "internal_max_bytes": PINE_EVIDENCE_INTERNAL_MAX_BYTES,
        "internal_headroom_bytes": PINE_EVIDENCE_INTERNAL_MAX_BYTES - size_bytes,
        "tradingview_ceiling": TRADINGVIEW_PINE_ALERT_MESSAGE_CEILING,
        "tradingview_headroom": TRADINGVIEW_PINE_ALERT_MESSAGE_CEILING - size_bytes,
    }


__all__ = [
    "BROWSER_OWNED_QUESTION_IDS",
    "InstrumentType",
    "KRONOS_OWNED_QUESTION_IDS",
    "McxPineEvidenceExtension",
    "NsePineEvidenceExtension",
    "ObservationBoundaryState",
    "PINE_EVIDENCE_CONTRACT_ID",
    "PINE_EVIDENCE_CONTRACT_VERSION",
    "PINE_EVIDENCE_INTERNAL_MAX_BYTES",
    "PINE_OWNED_QUESTION_IDS",
    "ParallelPineEvidenceRetention",
    "PineDomainEvidence",
    "PineEnvelopeProvenance",
    "PineEvidenceAvailability",
    "PineCompatibilityClass",
    "PineEvidenceDerivation",
    "PineEvidenceDomain",
    "PineEvidenceEnvelope",
    "PineEvidenceIntegrity",
    "PineEvidenceRetentionKey",
    "PineEvidenceProvenance",
    "PineEvidenceValidationExpectations",
    "PineEvidenceValidationIssueCode",
    "PineEvidenceValidationResult",
    "PineInstrumentIdentity",
    "PineLayer2EvidenceHandoff",
    "PineObservationBoundary",
    "PineProducer",
    "PineProducerType",
    "PineProduct",
    "PinePublisherRole",
    "PineTimeframeIdentity",
    "ProductContextEvidence",
    "ProductTimeframeState",
    "ReferenceMarket",
    "TRADINGVIEW_PINE_ALERT_MESSAGE_CEILING",
    "aggregate_integrity",
    "build_pine_evidence_envelope",
    "build_pine_layer2_handoff",
    "canonical_serialize",
    "derive_event_id",
    "payload_budget_headroom",
    "pine_evidence_from_dict",
    "validate_pine_evidence_payload",
]
