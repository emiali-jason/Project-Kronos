"""DOMAIN-001 V2 semantic contracts and fail-closed runtime resolution.

The module is deliberately additive.  V1 catalogue and runtime contracts retain
their historical meaning while V2 represents persistent analytical subjects,
expiry-specific contracts, exact Provider classification, and effective facts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from hashlib import sha256
import json
from typing import TypeAlias


CANONICAL_INSTRUMENT_CATALOGUE_V2 = "KRONOS-CANONICAL-INSTRUMENT-CATALOGUE-V2"
CANONICAL_INSTRUMENT_CATALOGUE_V2_VERSION = "1.0.0"
PROVIDER_CLASSIFICATION_MAPPING_V1 = "PROVIDER_INSTRUMENT_CLASSIFICATION_MAPPING_V1"
PROVIDER_CLASSIFICATION_MAPPING_V1_VERSION = "1.0.0"
PROVIDER_MAPPING_DIRECTIVE_V2 = "PROVIDER_MAPPING_DIRECTIVE_V2"
PROVIDER_MAPPING_DIRECTIVE_V2_VERSION = "1.0.0"
ACTIVE_DERIVATIVE_CONTRACT_BINDING_V1 = "ACTIVE_DERIVATIVE_CONTRACT_BINDING_V1"
ACTIVE_DERIVATIVE_CONTRACT_BINDING_V1_VERSION = "1.0.0"


class CanonicalSemanticKind(StrEnum):
    DIRECT_LISTED_INSTRUMENT = "DIRECT_LISTED_INSTRUMENT"
    ANALYTICAL_SUBJECT = "ANALYTICAL_SUBJECT"
    DERIVATIVE_CONTRACT = "DERIVATIVE_CONTRACT"


class CanonicalClassification(StrEnum):
    NSE_CASH_EQUITY = "NSE_CASH_EQUITY"
    NSE_INDEX = "NSE_INDEX"
    EXCHANGE_INDEX = "EXCHANGE_INDEX"
    MCX_COMMODITY = "MCX_COMMODITY"
    MCX_FUTURE = "MCX_FUTURE"


class V2ResolutionFailure(StrEnum):
    CANONICAL_SUBJECT_UNAVAILABLE = "CANONICAL_SUBJECT_UNAVAILABLE"
    CLASSIFICATION_MAPPING_UNAVAILABLE = "CLASSIFICATION_MAPPING_UNAVAILABLE"
    CANONICAL_CLASSIFICATION_CONFLICT = "CANONICAL_CLASSIFICATION_CONFLICT"
    PROVIDER_ASSERTION_UNAVAILABLE = "PROVIDER_ASSERTION_UNAVAILABLE"
    PROVIDER_BINDING_UNAVAILABLE = "PROVIDER_BINDING_UNAVAILABLE"
    ACTIVE_CONTRACT_BINDING_UNAVAILABLE = "ACTIVE_CONTRACT_BINDING_UNAVAILABLE"
    CANONICAL_GEOMETRY_MISMATCH = "CANONICAL_GEOMETRY_MISMATCH"
    SOURCE_STALE = "SOURCE_STALE"
    PUBLICATION_STALE = "PUBLICATION_STALE"
    INTEGRITY_INVALID = "INTEGRITY_INVALID"


class V2ResolutionError(RuntimeError):
    def __init__(self, failure: V2ResolutionFailure) -> None:
        self.failure = failure
        super().__init__(failure.value)


@dataclass(frozen=True, slots=True)
class EffectiveExecutionGeometry:
    geometry_identity: str
    geometry_version: str
    canonical_object_id: str
    tick_size: Decimal
    lot_size: int
    price_precision: int
    effective_from: datetime
    effective_through: datetime
    source_identity: str
    provenance: tuple[str, ...]
    integrity_identity: str

    def __post_init__(self) -> None:
        tick = _positive_decimal(self.tick_size)
        fields = _geometry_fields(self, tick)
        if (
            not _text(self.geometry_identity)
            or not _version(self.geometry_version)
            or not _text(self.canonical_object_id)
            or type(self.lot_size) is not int
            or self.lot_size <= 0
            or type(self.price_precision) is not int
            or self.price_precision != _precision(tick)
            or not _interval(self.effective_from, self.effective_through)
            or not _text(self.source_identity)
            or not _texts(self.provenance)
            or self.integrity_identity != _identity("V2-GEOMETRY", fields)
        ):
            raise V2ResolutionError(V2ResolutionFailure.INTEGRITY_INVALID)
        object.__setattr__(self, "tick_size", tick)

    def active_at(self, observed_at: datetime) -> bool:
        return _active(self.effective_from, self.effective_through, observed_at)


def create_effective_geometry(
    *,
    geometry_identity: str,
    geometry_version: str,
    canonical_object_id: str,
    tick_size: Decimal,
    lot_size: int,
    effective_from: datetime,
    effective_through: datetime,
    source_identity: str,
    provenance: tuple[str, ...],
) -> EffectiveExecutionGeometry:
    tick = _positive_decimal(tick_size)
    values = {
        "geometry_identity": geometry_identity,
        "geometry_version": geometry_version,
        "canonical_object_id": canonical_object_id,
        "tick_size": tick,
        "lot_size": lot_size,
        "price_precision": _precision(tick),
        "effective_from": effective_from,
        "effective_through": effective_through,
        "source_identity": source_identity,
        "provenance": provenance,
    }
    return EffectiveExecutionGeometry(
        **values,
        integrity_identity=_identity("V2-GEOMETRY", values),
    )


@dataclass(frozen=True, slots=True)
class DirectListedInstrumentV2:
    canonical_id: str
    canonical_symbol: str
    exchange: str
    classification: CanonicalClassification
    valid_from: datetime
    valid_through: datetime
    source_identity: str
    provenance: tuple[str, ...]
    geometry: tuple[EffectiveExecutionGeometry, ...]
    integrity_identity: str
    semantic_kind: CanonicalSemanticKind = CanonicalSemanticKind.DIRECT_LISTED_INSTRUMENT

    def __post_init__(self) -> None:
        if (
            self.semantic_kind is not CanonicalSemanticKind.DIRECT_LISTED_INSTRUMENT
            or self.classification is not CanonicalClassification.NSE_CASH_EQUITY
            or not _base_semantic_valid(self)
            or not self.geometry
            or any(item.canonical_object_id != self.canonical_id for item in self.geometry)
            or _overlaps(self.geometry)
            or self.integrity_identity != _identity("V2-DIRECT", _semantic_fields(self))
        ):
            raise V2ResolutionError(V2ResolutionFailure.INTEGRITY_INVALID)


@dataclass(frozen=True, slots=True)
class AnalyticalSubjectV2:
    canonical_id: str
    canonical_symbol: str
    exchange: str
    classification: CanonicalClassification
    valid_from: datetime
    valid_through: datetime
    source_identity: str
    provenance: tuple[str, ...]
    integrity_identity: str
    semantic_kind: CanonicalSemanticKind = CanonicalSemanticKind.ANALYTICAL_SUBJECT

    def __post_init__(self) -> None:
        if (
            self.semantic_kind is not CanonicalSemanticKind.ANALYTICAL_SUBJECT
            or self.classification not in {
                CanonicalClassification.NSE_INDEX,
                CanonicalClassification.EXCHANGE_INDEX,
                CanonicalClassification.MCX_COMMODITY,
            }
            or not _base_semantic_valid(self)
            or self.integrity_identity != _identity("V2-SUBJECT", _semantic_fields(self))
        ):
            raise V2ResolutionError(V2ResolutionFailure.INTEGRITY_INVALID)


@dataclass(frozen=True, slots=True)
class DerivativeContractV2:
    canonical_id: str
    canonical_symbol: str
    exchange: str
    classification: CanonicalClassification
    parent_subject_id: str
    expiry: date
    valid_from: datetime
    valid_through: datetime
    source_identity: str
    provenance: tuple[str, ...]
    geometry: tuple[EffectiveExecutionGeometry, ...]
    integrity_identity: str
    semantic_kind: CanonicalSemanticKind = CanonicalSemanticKind.DERIVATIVE_CONTRACT

    def __post_init__(self) -> None:
        if (
            self.semantic_kind is not CanonicalSemanticKind.DERIVATIVE_CONTRACT
            or self.classification is not CanonicalClassification.MCX_FUTURE
            or not _base_semantic_valid(self)
            or not _text(self.parent_subject_id)
            or self.parent_subject_id == self.canonical_id
            or type(self.expiry) is not date
            or not self.geometry
            or any(item.canonical_object_id != self.canonical_id for item in self.geometry)
            or _overlaps(self.geometry)
            or self.integrity_identity != _identity("V2-CONTRACT", _semantic_fields(self))
        ):
            raise V2ResolutionError(V2ResolutionFailure.INTEGRITY_INVALID)


CanonicalSemanticObject: TypeAlias = (
    DirectListedInstrumentV2 | AnalyticalSubjectV2 | DerivativeContractV2
)


def create_direct_listed_instrument(**fields: object) -> DirectListedInstrumentV2:
    values = dict(fields)
    values.setdefault("semantic_kind", CanonicalSemanticKind.DIRECT_LISTED_INSTRUMENT)
    return _create_semantic(DirectListedInstrumentV2, "V2-DIRECT", values)  # type: ignore[return-value]


def create_analytical_subject(**fields: object) -> AnalyticalSubjectV2:
    values = dict(fields)
    values.setdefault("semantic_kind", CanonicalSemanticKind.ANALYTICAL_SUBJECT)
    return _create_semantic(AnalyticalSubjectV2, "V2-SUBJECT", values)  # type: ignore[return-value]


def create_derivative_contract(**fields: object) -> DerivativeContractV2:
    values = dict(fields)
    values.setdefault("semantic_kind", CanonicalSemanticKind.DERIVATIVE_CONTRACT)
    return _create_semantic(DerivativeContractV2, "V2-CONTRACT", values)  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class ProviderClassificationMapping:
    mapping_identity: str
    mapping_version: str
    provider: str
    exchange: str
    segment: str
    provider_instrument_type: str
    canonical_classification: CanonicalClassification
    governed_subject_ids: tuple[str, ...]
    effective_from: datetime
    effective_through: datetime
    source_identity: str
    provenance: tuple[str, ...]
    supersedes: str | None
    integrity_identity: str
    contract_identity: str = PROVIDER_CLASSIFICATION_MAPPING_V1

    def __post_init__(self) -> None:
        fields = _mapping_fields(self)
        index_scope = self.canonical_classification in {
            CanonicalClassification.NSE_INDEX,
            CanonicalClassification.EXCHANGE_INDEX,
        }
        if (
            self.contract_identity != PROVIDER_CLASSIFICATION_MAPPING_V1
            or not _text(self.mapping_identity)
            or not _version(self.mapping_version)
            or any(
                not _text(item)
                for item in (
                    self.provider,
                    self.exchange,
                    self.segment,
                    self.provider_instrument_type,
                    self.source_identity,
                )
            )
            or type(self.canonical_classification) is not CanonicalClassification
            or index_scope != bool(self.governed_subject_ids)
            or (self.governed_subject_ids and not _unique_texts(self.governed_subject_ids))
            or not _interval(self.effective_from, self.effective_through)
            or not _texts(self.provenance)
            or (self.supersedes is not None and not _text(self.supersedes))
            or self.integrity_identity != _identity("V2-CLASSIFICATION-MAPPING", fields)
        ):
            raise V2ResolutionError(V2ResolutionFailure.INTEGRITY_INVALID)

    @property
    def provider_key(self) -> tuple[str, str, str, str]:
        return (
            self.provider,
            self.exchange,
            self.segment,
            self.provider_instrument_type,
        )

    def active_at(self, observed_at: datetime) -> bool:
        return _active(self.effective_from, self.effective_through, observed_at)


def create_classification_mapping(**fields: object) -> ProviderClassificationMapping:
    values = dict(fields)
    values.setdefault("contract_identity", PROVIDER_CLASSIFICATION_MAPPING_V1)
    return ProviderClassificationMapping(
        **values,  # type: ignore[arg-type]
        integrity_identity=_identity("V2-CLASSIFICATION-MAPPING", values),
    )


@dataclass(frozen=True, slots=True)
class ProviderMappingDirectiveV2:
    directive_identity: str
    directive_version: str
    canonical_object_id: str
    provider: str
    provider_record_identity: str
    provider_symbol: str
    classification_mapping_identity: str
    effective_from: datetime
    effective_through: datetime
    source_identity: str
    provenance: tuple[str, ...]
    supersedes: str | None
    integrity_identity: str
    contract_identity: str = PROVIDER_MAPPING_DIRECTIVE_V2

    def __post_init__(self) -> None:
        fields = _directive_fields(self)
        if (
            self.contract_identity != PROVIDER_MAPPING_DIRECTIVE_V2
            or any(
                not _text(item)
                for item in (
                    self.directive_identity,
                    self.canonical_object_id,
                    self.provider,
                    self.provider_record_identity,
                    self.provider_symbol,
                    self.classification_mapping_identity,
                    self.source_identity,
                )
            )
            or not _version(self.directive_version)
            or not self.provider_record_identity.startswith("PROVIDER-INSTRUMENT-RECORD-")
            or not _interval(self.effective_from, self.effective_through)
            or not _texts(self.provenance)
            or (self.supersedes is not None and not _text(self.supersedes))
            or self.integrity_identity != _identity("V2-PROVIDER-DIRECTIVE", fields)
        ):
            raise V2ResolutionError(V2ResolutionFailure.INTEGRITY_INVALID)

    def active_at(self, observed_at: datetime) -> bool:
        return _active(self.effective_from, self.effective_through, observed_at)


def create_provider_mapping_directive_v2(**fields: object) -> ProviderMappingDirectiveV2:
    values = dict(fields)
    values.setdefault("contract_identity", PROVIDER_MAPPING_DIRECTIVE_V2)
    return ProviderMappingDirectiveV2(
        **values,  # type: ignore[arg-type]
        integrity_identity=_identity("V2-PROVIDER-DIRECTIVE", values),
    )


@dataclass(frozen=True, slots=True)
class ActiveDerivativeContractBinding:
    binding_identity: str
    binding_version: str
    subject_id: str
    derivative_contract_id: str
    effective_from: datetime
    effective_through: datetime
    contract_expiry: date
    provider_reference_identity: str
    source_identity: str
    provenance: tuple[str, ...]
    supersedes: str | None
    integrity_identity: str
    contract_identity: str = ACTIVE_DERIVATIVE_CONTRACT_BINDING_V1

    def __post_init__(self) -> None:
        fields = _active_binding_fields(self)
        if (
            self.contract_identity != ACTIVE_DERIVATIVE_CONTRACT_BINDING_V1
            or any(
                not _text(item)
                for item in (
                    self.binding_identity,
                    self.subject_id,
                    self.derivative_contract_id,
                    self.provider_reference_identity,
                    self.source_identity,
                )
            )
            or self.subject_id == self.derivative_contract_id
            or not _version(self.binding_version)
            or not _interval(self.effective_from, self.effective_through)
            or type(self.contract_expiry) is not date
            or not _texts(self.provenance)
            or (self.supersedes is not None and not _text(self.supersedes))
            or self.integrity_identity != _identity("V2-ACTIVE-BINDING", fields)
        ):
            raise V2ResolutionError(V2ResolutionFailure.INTEGRITY_INVALID)

    def active_at(self, observed_at: datetime) -> bool:
        return _active(self.effective_from, self.effective_through, observed_at)


def create_active_derivative_binding(**fields: object) -> ActiveDerivativeContractBinding:
    values = dict(fields)
    values.setdefault("contract_identity", ACTIVE_DERIVATIVE_CONTRACT_BINDING_V1)
    return ActiveDerivativeContractBinding(
        **values,  # type: ignore[arg-type]
        integrity_identity=_identity("V2-ACTIVE-BINDING", values),
    )


@dataclass(frozen=True, slots=True)
class ProviderInstrumentSubmissionV2:
    """Token-free eligible EAIC-002 factual input for V2 resolution."""

    provider_record_identity: str
    provider: str
    provider_symbol: str
    exchange: str
    segment: str
    provider_instrument_type: str
    tick_size: Decimal | None
    lot_size: int | None
    source_boundary: datetime
    valid_through: datetime
    provenance: tuple[str, ...]

    def __post_init__(self) -> None:
        tick = _optional_positive_decimal(self.tick_size)
        if (
            not self.provider_record_identity.startswith("PROVIDER-INSTRUMENT-RECORD-")
            or any(
                not _text(item)
                for item in (
                    self.provider,
                    self.provider_symbol,
                    self.exchange,
                    self.segment,
                    self.provider_instrument_type,
                )
            )
            or (self.lot_size is not None and (type(self.lot_size) is not int or self.lot_size <= 0))
            or not _interval(self.source_boundary, self.valid_through)
            or not _texts(self.provenance)
        ):
            raise V2ResolutionError(V2ResolutionFailure.INTEGRITY_INVALID)
        object.__setattr__(self, "tick_size", tick)

    def active_at(self, observed_at: datetime) -> bool:
        return _active(self.source_boundary, self.valid_through, observed_at)


@dataclass(frozen=True, slots=True)
class InstrumentSemanticPublicationV2:
    publication_identity: str
    publication_version: str
    effective_from: datetime
    effective_through: datetime
    supersedes: str | None
    source_identities: tuple[str, ...]
    provenance: tuple[str, ...]
    semantic_objects: tuple[CanonicalSemanticObject, ...]
    classification_mappings: tuple[ProviderClassificationMapping, ...]
    provider_directives: tuple[ProviderMappingDirectiveV2, ...]
    active_bindings: tuple[ActiveDerivativeContractBinding, ...]
    integrity_identity: str
    schema_identity: str = CANONICAL_INSTRUMENT_CATALOGUE_V2

    def __post_init__(self) -> None:
        core = _publication_fields(self)
        object_ids = tuple(item.canonical_id for item in self.semantic_objects)
        mapping_ids = tuple(item.mapping_identity for item in self.classification_mappings)
        directive_ids = tuple(item.directive_identity for item in self.provider_directives)
        binding_ids = tuple(item.binding_identity for item in self.active_bindings)
        subjects = {
            item.canonical_id
            for item in self.semantic_objects
            if type(item) is AnalyticalSubjectV2
        }
        contracts = {
            item.canonical_id: item
            for item in self.semantic_objects
            if type(item) is DerivativeContractV2
        }
        if (
            self.schema_identity != CANONICAL_INSTRUMENT_CATALOGUE_V2
            or self.publication_identity != CANONICAL_INSTRUMENT_CATALOGUE_V2
            or not _version(self.publication_version)
            or not _interval(self.effective_from, self.effective_through)
            or (self.supersedes is not None and not _text(self.supersedes))
            or not _texts(self.source_identities)
            or not _texts(self.provenance)
            or not self.semantic_objects
            or any(type(item) not in {DirectListedInstrumentV2, AnalyticalSubjectV2, DerivativeContractV2} for item in self.semantic_objects)
            or not _unique(object_ids)
            or not _unique(mapping_ids)
            or not _unique(directive_ids)
            or not _unique(binding_ids)
            or any(item.parent_subject_id not in subjects for item in contracts.values())
            or any(item.canonical_object_id not in set(object_ids) for item in self.provider_directives)
            or any(
                item.subject_id not in subjects
                or item.derivative_contract_id not in contracts
                or contracts[item.derivative_contract_id].parent_subject_id != item.subject_id
                or contracts[item.derivative_contract_id].expiry != item.contract_expiry
                for item in self.active_bindings
            )
            or _binding_overlaps(self.active_bindings)
            or self.integrity_identity != _identity("V2-PUBLICATION", core)
        ):
            raise V2ResolutionError(V2ResolutionFailure.INTEGRITY_INVALID)

    def require_current(self, observed_at: datetime) -> None:
        if not _active(self.effective_from, self.effective_through, observed_at):
            raise V2ResolutionError(V2ResolutionFailure.PUBLICATION_STALE)

    def classification_mapping(
        self,
        *,
        mapping_identity: str,
        mapping_version: str,
    ) -> ProviderClassificationMapping:
        matches = tuple(
            item
            for item in self.classification_mappings
            if item.mapping_identity == mapping_identity
            and item.mapping_version == mapping_version
        )
        if len(matches) != 1:
            raise V2ResolutionError(V2ResolutionFailure.CLASSIFICATION_MAPPING_UNAVAILABLE)
        return matches[0]

    def provider_directive(
        self,
        *,
        directive_identity: str,
        directive_version: str,
    ) -> ProviderMappingDirectiveV2:
        matches = tuple(
            item
            for item in self.provider_directives
            if item.directive_identity == directive_identity
            and item.directive_version == directive_version
        )
        if len(matches) != 1:
            raise V2ResolutionError(V2ResolutionFailure.PROVIDER_BINDING_UNAVAILABLE)
        return matches[0]

    def active_binding(
        self,
        *,
        binding_identity: str,
        binding_version: str,
    ) -> ActiveDerivativeContractBinding:
        matches = tuple(
            item
            for item in self.active_bindings
            if item.binding_identity == binding_identity
            and item.binding_version == binding_version
        )
        if len(matches) != 1:
            raise V2ResolutionError(V2ResolutionFailure.ACTIVE_CONTRACT_BINDING_UNAVAILABLE)
        return matches[0]


def create_semantic_publication_v2(**fields: object) -> InstrumentSemanticPublicationV2:
    values = dict(fields)
    values.setdefault("schema_identity", CANONICAL_INSTRUMENT_CATALOGUE_V2)
    values.setdefault("publication_identity", CANONICAL_INSTRUMENT_CATALOGUE_V2)
    return InstrumentSemanticPublicationV2(
        **values,  # type: ignore[arg-type]
        integrity_identity=_identity("V2-PUBLICATION", values),
    )


@dataclass(frozen=True, slots=True)
class RuntimeListedInstrumentV2:
    canonical: DirectListedInstrumentV2
    provider_directive: ProviderMappingDirectiveV2
    provider_submission: ProviderInstrumentSubmissionV2
    geometry: EffectiveExecutionGeometry
    runtime_identity: str


@dataclass(frozen=True, slots=True)
class RuntimeAnalyticalSubjectV2:
    canonical: AnalyticalSubjectV2
    provider_directive: ProviderMappingDirectiveV2 | None
    provider_submission: ProviderInstrumentSubmissionV2 | None
    active_contract_id: str | None
    runtime_identity: str


@dataclass(frozen=True, slots=True)
class RuntimeDerivativeContractV2:
    subject: AnalyticalSubjectV2
    contract: DerivativeContractV2
    active_binding: ActiveDerivativeContractBinding
    provider_directive: ProviderMappingDirectiveV2
    provider_submission: ProviderInstrumentSubmissionV2
    geometry: EffectiveExecutionGeometry
    runtime_identity: str


class InstrumentSemanticResolverV2:
    """Resolve exact governed V2 relationships without selection heuristics."""

    def __init__(
        self,
        publication: InstrumentSemanticPublicationV2,
        submissions: tuple[ProviderInstrumentSubmissionV2, ...],
    ) -> None:
        if type(publication) is not InstrumentSemanticPublicationV2 or any(
            type(item) is not ProviderInstrumentSubmissionV2 for item in submissions
        ):
            raise V2ResolutionError(V2ResolutionFailure.INTEGRITY_INVALID)
        record_ids = tuple(item.provider_record_identity for item in submissions)
        if not _unique(record_ids):
            raise V2ResolutionError(V2ResolutionFailure.PROVIDER_ASSERTION_UNAVAILABLE)
        self._publication = publication
        self._objects = {item.canonical_id: item for item in publication.semantic_objects}
        self._submissions = {item.provider_record_identity: item for item in submissions}

    def resolve_listed(self, canonical_id: str, observed_at: datetime) -> RuntimeListedInstrumentV2:
        self._publication.require_current(observed_at)
        item = self._objects.get(canonical_id)
        if type(item) is not DirectListedInstrumentV2:
            raise V2ResolutionError(V2ResolutionFailure.CANONICAL_SUBJECT_UNAVAILABLE)
        directive, submission = self._provider_pair(item.canonical_id, observed_at)
        classification = self._classification(
            submission,
            item.canonical_id,
            directive.classification_mapping_identity,
            observed_at,
        )
        if classification is not item.classification:
            raise V2ResolutionError(V2ResolutionFailure.CANONICAL_CLASSIFICATION_CONFLICT)
        geometry = _active_geometry(item.geometry, observed_at)
        _require_geometry(geometry, submission)
        return RuntimeListedInstrumentV2(
            item,
            directive,
            submission,
            geometry,
            _identity("V2-RUNTIME-LISTED", {
                "canonical": item.integrity_identity,
                "directive": directive.integrity_identity,
                "submission": submission.provider_record_identity,
                "geometry": geometry.integrity_identity,
                "observed_at": observed_at,
            }),
        )

    def resolve_subject(self, canonical_id: str, observed_at: datetime) -> RuntimeAnalyticalSubjectV2:
        self._publication.require_current(observed_at)
        item = self._objects.get(canonical_id)
        if type(item) is not AnalyticalSubjectV2:
            raise V2ResolutionError(V2ResolutionFailure.CANONICAL_SUBJECT_UNAVAILABLE)
        if item.classification is CanonicalClassification.MCX_COMMODITY:
            bindings = tuple(
                binding
                for binding in self._publication.active_bindings
                if binding.subject_id == item.canonical_id
                and binding.active_at(observed_at)
            )
            if len(bindings) > 1:
                raise V2ResolutionError(V2ResolutionFailure.INTEGRITY_INVALID)
            return RuntimeAnalyticalSubjectV2(
                item,
                None,
                None,
                bindings[0].derivative_contract_id if bindings else None,
                _identity("V2-RUNTIME-SUBJECT", {
                    "canonical": item.integrity_identity,
                    "active_binding": bindings[0].integrity_identity if bindings else None,
                    "observed_at": observed_at,
                }),
            )
        directive, submission = self._provider_pair(item.canonical_id, observed_at)
        classification = self._classification(
            submission,
            item.canonical_id,
            directive.classification_mapping_identity,
            observed_at,
        )
        if classification is not item.classification:
            raise V2ResolutionError(V2ResolutionFailure.CANONICAL_CLASSIFICATION_CONFLICT)
        return RuntimeAnalyticalSubjectV2(
            item,
            directive,
            submission,
            None,
            _identity("V2-RUNTIME-SUBJECT", {
                "canonical": item.integrity_identity,
                "directive": directive.integrity_identity,
                "submission": submission.provider_record_identity,
                "observed_at": observed_at,
            }),
        )

    def resolve_active_contract(self, subject_id: str, observed_at: datetime) -> RuntimeDerivativeContractV2:
        self._publication.require_current(observed_at)
        subject = self._objects.get(subject_id)
        if type(subject) is not AnalyticalSubjectV2:
            raise V2ResolutionError(V2ResolutionFailure.CANONICAL_SUBJECT_UNAVAILABLE)
        binding = self._active_binding(subject_id, observed_at)
        contract = self._objects.get(binding.derivative_contract_id)
        if type(contract) is not DerivativeContractV2 or contract.parent_subject_id != subject_id:
            raise V2ResolutionError(V2ResolutionFailure.INTEGRITY_INVALID)
        directive, submission = self._provider_pair(contract.canonical_id, observed_at)
        classification = self._classification(
            submission,
            contract.canonical_id,
            directive.classification_mapping_identity,
            observed_at,
        )
        if classification is not contract.classification:
            raise V2ResolutionError(V2ResolutionFailure.CANONICAL_CLASSIFICATION_CONFLICT)
        if binding.provider_reference_identity not in {
            directive.directive_identity,
            directive.provider_record_identity,
        }:
            raise V2ResolutionError(V2ResolutionFailure.PROVIDER_BINDING_UNAVAILABLE)
        geometry = _active_geometry(contract.geometry, observed_at)
        _require_geometry(geometry, submission)
        return RuntimeDerivativeContractV2(
            subject,
            contract,
            binding,
            directive,
            submission,
            geometry,
            _identity("V2-RUNTIME-CONTRACT", {
                "subject": subject.integrity_identity,
                "contract": contract.integrity_identity,
                "binding": binding.integrity_identity,
                "directive": directive.integrity_identity,
                "submission": submission.provider_record_identity,
                "geometry": geometry.integrity_identity,
                "observed_at": observed_at,
            }),
        )

    def _classification(
        self,
        submission: ProviderInstrumentSubmissionV2,
        canonical_id: str,
        mapping_identity: str,
        observed_at: datetime,
    ) -> CanonicalClassification:
        key = (
            submission.provider,
            submission.exchange,
            submission.segment,
            submission.provider_instrument_type,
        )
        key_matches = tuple(
            item
            for item in self._publication.classification_mappings
            if item.provider_key == key
            and item.active_at(observed_at)
            and (
                not item.governed_subject_ids
                or canonical_id in item.governed_subject_ids
            )
        )
        if not key_matches:
            raise V2ResolutionError(V2ResolutionFailure.CLASSIFICATION_MAPPING_UNAVAILABLE)
        if len(key_matches) != 1:
            raise V2ResolutionError(V2ResolutionFailure.CANONICAL_CLASSIFICATION_CONFLICT)
        selected = key_matches[0]
        if selected.mapping_identity != mapping_identity:
            raise V2ResolutionError(V2ResolutionFailure.CLASSIFICATION_MAPPING_UNAVAILABLE)
        return selected.canonical_classification

    def _provider_pair(
        self,
        canonical_id: str,
        observed_at: datetime,
    ) -> tuple[ProviderMappingDirectiveV2, ProviderInstrumentSubmissionV2]:
        directives = tuple(
            item
            for item in self._publication.provider_directives
            if item.canonical_object_id == canonical_id and item.active_at(observed_at)
        )
        if len(directives) != 1:
            raise V2ResolutionError(V2ResolutionFailure.PROVIDER_BINDING_UNAVAILABLE)
        directive = directives[0]
        submission = self._submissions.get(directive.provider_record_identity)
        if submission is None:
            raise V2ResolutionError(V2ResolutionFailure.PROVIDER_ASSERTION_UNAVAILABLE)
        if not submission.active_at(observed_at):
            raise V2ResolutionError(V2ResolutionFailure.SOURCE_STALE)
        if (
            directive.provider != submission.provider
            or directive.provider_symbol != submission.provider_symbol
        ):
            raise V2ResolutionError(V2ResolutionFailure.PROVIDER_BINDING_UNAVAILABLE)
        return directive, submission

    def _active_binding(
        self,
        subject_id: str,
        observed_at: datetime,
    ) -> ActiveDerivativeContractBinding:
        matches = tuple(
            item
            for item in self._publication.active_bindings
            if item.subject_id == subject_id and item.active_at(observed_at)
        )
        if len(matches) != 1:
            raise V2ResolutionError(V2ResolutionFailure.ACTIVE_CONTRACT_BINDING_UNAVAILABLE)
        return matches[0]


def encode_semantic_publication_v2(publication: InstrumentSemanticPublicationV2) -> bytes:
    if type(publication) is not InstrumentSemanticPublicationV2:
        raise V2ResolutionError(V2ResolutionFailure.INTEGRITY_INVALID)
    return (json.dumps(
        _serializable(_publication_document(publication)),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ) + "\n").encode("ascii")


def parse_semantic_publication_v2(encoded: bytes) -> InstrumentSemanticPublicationV2:
    try:
        raw = json.loads(encoded)
        if type(raw) is not dict:
            raise TypeError
        objects = tuple(_parse_semantic(item) for item in raw["semantic_objects"])
        mappings = tuple(_parse_mapping(item) for item in raw["classification_mappings"])
        directives = tuple(_parse_directive(item) for item in raw["provider_directives"])
        bindings = tuple(_parse_binding(item) for item in raw["active_bindings"])
        publication = InstrumentSemanticPublicationV2(
            schema_identity=raw["schema_identity"],
            publication_identity=raw["publication_identity"],
            publication_version=raw["publication_version"],
            effective_from=_datetime(raw["effective_from"]),
            effective_through=_datetime(raw["effective_through"]),
            supersedes=raw["supersedes"],
            source_identities=tuple(raw["source_identities"]),
            provenance=tuple(raw["provenance"]),
            semantic_objects=objects,
            classification_mappings=mappings,
            provider_directives=directives,
            active_bindings=bindings,
            integrity_identity=raw["integrity_identity"],
        )
        if encode_semantic_publication_v2(publication) != encoded:
            raise V2ResolutionError(V2ResolutionFailure.INTEGRITY_INVALID)
        return publication
    except V2ResolutionError:
        raise
    except (
        InvalidOperation,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        UnicodeDecodeError,
    ) as error:
        raise V2ResolutionError(V2ResolutionFailure.INTEGRITY_INVALID) from error


def _create_semantic(kind: type[CanonicalSemanticObject], prefix: str, fields: dict[str, object]) -> CanonicalSemanticObject:
    values = dict(fields)
    return kind(**values, integrity_identity=_identity(prefix, values))  # type: ignore[arg-type]


def _base_semantic_valid(item: CanonicalSemanticObject) -> bool:
    return (
        all(_text(value) for value in (item.canonical_id, item.canonical_symbol, item.exchange, item.source_identity))
        and type(item.classification) is CanonicalClassification
        and _interval(item.valid_from, item.valid_through)
        and _texts(item.provenance)
    )


def _semantic_fields(item: CanonicalSemanticObject) -> dict[str, object]:
    fields = {
        name: getattr(item, name)
        for name in item.__dataclass_fields__
        if name != "integrity_identity"
    }
    return fields


def _geometry_fields(item: EffectiveExecutionGeometry, tick: Decimal) -> dict[str, object]:
    return {
        "geometry_identity": item.geometry_identity,
        "geometry_version": item.geometry_version,
        "canonical_object_id": item.canonical_object_id,
        "tick_size": tick,
        "lot_size": item.lot_size,
        "price_precision": item.price_precision,
        "effective_from": item.effective_from,
        "effective_through": item.effective_through,
        "source_identity": item.source_identity,
        "provenance": item.provenance,
    }


def _mapping_fields(item: ProviderClassificationMapping) -> dict[str, object]:
    return {name: getattr(item, name) for name in item.__dataclass_fields__ if name != "integrity_identity"}


def _directive_fields(item: ProviderMappingDirectiveV2) -> dict[str, object]:
    return {name: getattr(item, name) for name in item.__dataclass_fields__ if name != "integrity_identity"}


def _active_binding_fields(item: ActiveDerivativeContractBinding) -> dict[str, object]:
    return {name: getattr(item, name) for name in item.__dataclass_fields__ if name != "integrity_identity"}


def _publication_fields(item: InstrumentSemanticPublicationV2) -> dict[str, object]:
    return {name: getattr(item, name) for name in item.__dataclass_fields__ if name != "integrity_identity"}


def _publication_document(item: InstrumentSemanticPublicationV2) -> dict[str, object]:
    return _publication_fields(item) | {"integrity_identity": item.integrity_identity}


def _parse_semantic(raw: object) -> CanonicalSemanticObject:
    if type(raw) is not dict:
        raise V2ResolutionError(V2ResolutionFailure.INTEGRITY_INVALID)
    values = dict(raw)
    values["classification"] = CanonicalClassification(values["classification"])
    values["semantic_kind"] = CanonicalSemanticKind(values["semantic_kind"])
    values["valid_from"] = _datetime(values["valid_from"])
    values["valid_through"] = _datetime(values["valid_through"])
    values["provenance"] = tuple(values["provenance"])
    kind = values["semantic_kind"]
    if kind is CanonicalSemanticKind.DIRECT_LISTED_INSTRUMENT:
        values["geometry"] = tuple(_parse_geometry(item) for item in values["geometry"])
        return DirectListedInstrumentV2(**values)
    if kind is CanonicalSemanticKind.ANALYTICAL_SUBJECT:
        return AnalyticalSubjectV2(**values)
    values["geometry"] = tuple(_parse_geometry(item) for item in values["geometry"])
    values["expiry"] = date.fromisoformat(values["expiry"])
    return DerivativeContractV2(**values)


def _parse_geometry(raw: object) -> EffectiveExecutionGeometry:
    if type(raw) is not dict:
        raise V2ResolutionError(V2ResolutionFailure.INTEGRITY_INVALID)
    values = dict(raw)
    values["tick_size"] = Decimal(values["tick_size"])
    values["effective_from"] = _datetime(values["effective_from"])
    values["effective_through"] = _datetime(values["effective_through"])
    values["provenance"] = tuple(values["provenance"])
    return EffectiveExecutionGeometry(**values)


def _parse_mapping(raw: object) -> ProviderClassificationMapping:
    values = _parsed_common(raw)
    values["canonical_classification"] = CanonicalClassification(values["canonical_classification"])
    values["governed_subject_ids"] = tuple(values["governed_subject_ids"])
    return ProviderClassificationMapping(**values)


def _parse_directive(raw: object) -> ProviderMappingDirectiveV2:
    return ProviderMappingDirectiveV2(**_parsed_common(raw))


def _parse_binding(raw: object) -> ActiveDerivativeContractBinding:
    values = _parsed_common(raw)
    values["contract_expiry"] = date.fromisoformat(values["contract_expiry"])
    return ActiveDerivativeContractBinding(**values)


def _parsed_common(raw: object) -> dict[str, object]:
    if type(raw) is not dict:
        raise V2ResolutionError(V2ResolutionFailure.INTEGRITY_INVALID)
    values = dict(raw)
    values["effective_from"] = _datetime(values["effective_from"])
    values["effective_through"] = _datetime(values["effective_through"])
    values["provenance"] = tuple(values["provenance"])
    return values


def _active_geometry(
    segments: tuple[EffectiveExecutionGeometry, ...],
    observed_at: datetime,
) -> EffectiveExecutionGeometry:
    matches = tuple(item for item in segments if item.active_at(observed_at))
    if len(matches) != 1:
        raise V2ResolutionError(V2ResolutionFailure.CANONICAL_GEOMETRY_MISMATCH)
    return matches[0]


def _require_geometry(
    canonical: EffectiveExecutionGeometry,
    provider: ProviderInstrumentSubmissionV2,
) -> None:
    if canonical.tick_size != provider.tick_size or canonical.lot_size != provider.lot_size:
        raise V2ResolutionError(V2ResolutionFailure.CANONICAL_GEOMETRY_MISMATCH)


def _overlaps(items: tuple[EffectiveExecutionGeometry, ...]) -> bool:
    ordered = sorted(items, key=lambda item: item.effective_from)
    return any(left.effective_through >= right.effective_from for left, right in zip(ordered, ordered[1:]))


def _binding_overlaps(items: tuple[ActiveDerivativeContractBinding, ...]) -> bool:
    by_subject: dict[str, list[ActiveDerivativeContractBinding]] = {}
    for item in items:
        by_subject.setdefault(item.subject_id, []).append(item)
    return any(
        left.effective_through >= right.effective_from
        for values in by_subject.values()
        for left, right in zip(sorted(values, key=lambda item: item.effective_from), sorted(values, key=lambda item: item.effective_from)[1:])
    )


def _positive_decimal(value: object) -> Decimal:
    try:
        result = value if type(value) is Decimal else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise V2ResolutionError(V2ResolutionFailure.INTEGRITY_INVALID) from error
    if not result.is_finite() or result <= 0:
        raise V2ResolutionError(V2ResolutionFailure.INTEGRITY_INVALID)
    return result


def _optional_positive_decimal(value: object) -> Decimal | None:
    return None if value is None else _positive_decimal(value)


def _precision(tick: Decimal) -> int:
    return max(0, -tick.normalize().as_tuple().exponent)


def _identity(prefix: str, fields: object) -> str:
    encoded = json.dumps(_serializable(fields), ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return f"{prefix}-{sha256(encoded.encode('ascii')).hexdigest()}"


def _serializable(value: object) -> object:
    if isinstance(value, dict):
        return {key: _serializable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_serializable(item) for item in value]
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "__dataclass_fields__"):
        return {
            name: _serializable(getattr(value, name))
            for name in value.__dataclass_fields__
        }
    return value


def _datetime(value: object) -> datetime:
    if type(value) is not str:
        raise ValueError
    result = datetime.fromisoformat(value)
    if not _aware(result):
        raise ValueError
    return result


def _active(start: datetime, end: datetime, observed_at: datetime) -> bool:
    return _aware(observed_at) and start <= observed_at <= end


def _interval(start: object, end: object) -> bool:
    return _aware(start) and _aware(end) and start <= end


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


def _texts(values: object) -> bool:
    return type(values) is tuple and bool(values) and all(_text(item) for item in values)


def _unique_texts(values: tuple[str, ...]) -> bool:
    return _texts(values) and _unique(values)


def _unique(values: tuple[object, ...]) -> bool:
    return len(set(values)) == len(values)


def _version(value: object) -> bool:
    if type(value) is not str:
        return False
    parts = value.split(".")
    return len(parts) == 3 and all(part.isascii() and part.isdigit() for part in parts)


__all__ = [
    "ACTIVE_DERIVATIVE_CONTRACT_BINDING_V1",
    "CANONICAL_INSTRUMENT_CATALOGUE_V2",
    "PROVIDER_CLASSIFICATION_MAPPING_V1",
    "PROVIDER_MAPPING_DIRECTIVE_V2",
    "ActiveDerivativeContractBinding",
    "AnalyticalSubjectV2",
    "CanonicalClassification",
    "CanonicalSemanticKind",
    "DerivativeContractV2",
    "DirectListedInstrumentV2",
    "EffectiveExecutionGeometry",
    "InstrumentSemanticPublicationV2",
    "InstrumentSemanticResolverV2",
    "ProviderClassificationMapping",
    "ProviderInstrumentSubmissionV2",
    "ProviderMappingDirectiveV2",
    "RuntimeAnalyticalSubjectV2",
    "RuntimeDerivativeContractV2",
    "RuntimeListedInstrumentV2",
    "V2ResolutionError",
    "V2ResolutionFailure",
    "create_active_derivative_binding",
    "create_analytical_subject",
    "create_classification_mapping",
    "create_derivative_contract",
    "create_direct_listed_instrument",
    "create_effective_geometry",
    "create_provider_mapping_directive_v2",
    "create_semantic_publication_v2",
    "encode_semantic_publication_v2",
    "parse_semantic_publication_v2",
]
