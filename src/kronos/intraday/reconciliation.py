"""Factual Intraday product/canonical/Provider/runtime reconciliation.

This product-owned module reads governed Platform publications.  It neither
selects derivative contracts nor establishes trading or execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import json
from typing import Iterable

from kronos.instrument.semantic_v2 import (
    AnalyticalSubjectV2,
    CanonicalSemanticKind,
    DerivativeContractV2,
    DirectListedInstrumentV2,
    InstrumentSemanticPublicationV2,
    InstrumentSemanticResolverV2,
    ProviderInstrumentSubmissionV2,
)
from kronos.intraday.universe import (
    IntradayMarketFamily,
    IntradayUniverseMember,
    IntradayUniversePublication,
)


RECONCILIATION_SCHEMA = "KRONOS-INTRADAY-CANONICAL-RUNTIME-RECONCILIATION-V1"
RECONCILIATION_IDENTITY = RECONCILIATION_SCHEMA
RECONCILIATION_VERSION = "1.0.0"


class Availability(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_ESTABLISHED = "NOT_ESTABLISHED"


class ReconciliationState(StrEnum):
    FULLY_RECONCILED_FOR_CURRENT_FACTUAL_PATH = (
        "FULLY_RECONCILED_FOR_CURRENT_FACTUAL_PATH"
    )
    ACTIVE_CONTRACT_BINDING_UNAVAILABLE = "ACTIVE_CONTRACT_BINDING_UNAVAILABLE"
    PROVIDER_CONTRACT_UNAVAILABLE = "PROVIDER_CONTRACT_UNAVAILABLE"


class ReconciliationReason(StrEnum):
    PRODUCT_MEMBERSHIP_AVAILABLE = "PRODUCT_MEMBERSHIP_AVAILABLE"
    CANONICAL_IDENTITY_AVAILABLE = "CANONICAL_IDENTITY_AVAILABLE"
    CANONICAL_SEMANTICS_AVAILABLE = "CANONICAL_SEMANTICS_AVAILABLE"
    PROVIDER_MAPPING_AVAILABLE = "PROVIDER_MAPPING_AVAILABLE"
    PROVIDER_FACT_AVAILABLE = "PROVIDER_FACT_AVAILABLE"
    EFFECTIVE_GEOMETRY_AVAILABLE = "EFFECTIVE_GEOMETRY_AVAILABLE"
    DERIVATIVE_CONTRACTS_AVAILABLE = "DERIVATIVE_CONTRACTS_AVAILABLE"
    ACTIVE_BINDING_MISSING = "ACTIVE_BINDING_MISSING"
    PROVIDER_CONTRACT_UNAVAILABLE = "PROVIDER_CONTRACT_UNAVAILABLE"
    RUNTIME_ANALYTICAL_AVAILABLE = "RUNTIME_ANALYTICAL_AVAILABLE"
    RUNTIME_CONTRACT_UNAVAILABLE = "RUNTIME_CONTRACT_UNAVAILABLE"
    MACHINE_FACT_CONSUMABLE = "MACHINE_FACT_CONSUMABLE"
    MACHINE_FACT_PREREQUISITE_UNAVAILABLE = (
        "MACHINE_FACT_PREREQUISITE_UNAVAILABLE"
    )
    EXECUTION_ELIGIBILITY_NOT_ESTABLISHED = (
        "EXECUTION_ELIGIBILITY_NOT_ESTABLISHED"
    )


class ReconciliationFailure(StrEnum):
    INPUT_INVALID = "INPUT_INVALID"
    INTEGRITY_MISMATCH = "INTEGRITY_MISMATCH"
    VERSION_CONFLICT = "VERSION_CONFLICT"
    PUBLICATION_UNAVAILABLE = "PUBLICATION_UNAVAILABLE"
    STALE_UNIVERSE = "STALE_UNIVERSE"
    STALE_CATALOGUE = "STALE_CATALOGUE"
    STALE_PROVIDER_SNAPSHOT = "STALE_PROVIDER_SNAPSHOT"


class ReconciliationError(RuntimeError):
    def __init__(self, failure: ReconciliationFailure) -> None:
        self.failure = failure
        super().__init__(failure.value)


@dataclass(frozen=True, slots=True)
class AvailabilityDimensions:
    product_membership: Availability
    canonical_identity: Availability
    canonical_semantics: Availability
    provider_mapping: Availability
    provider_fact: Availability
    effective_geometry: Availability
    derivative_contract_set: Availability
    active_derivative_binding: Availability
    runtime_analytical_availability: Availability
    runtime_contract_availability: Availability
    machine_fact_consumability: Availability
    execution_eligibility: Availability

    def __post_init__(self) -> None:
        if any(
            type(getattr(self, name)) is not Availability
            for name in AvailabilityDimensions.__dataclass_fields__
        ):
            raise ReconciliationError(ReconciliationFailure.INPUT_INVALID)


@dataclass(frozen=True, slots=True)
class ReconciliationMember:
    sponsor_label: str
    universe_member_identity: str
    market_family: IntradayMarketFamily
    canonical_identity: str
    semantic_type: CanonicalSemanticKind
    exchange: str
    provider_symbol: str | None
    provider_directive_identities: tuple[str, ...]
    provider_record_identities: tuple[str, ...]
    derivative_contract_identities: tuple[str, ...]
    dimensions: AvailabilityDimensions
    state: ReconciliationState
    reasons: tuple[ReconciliationReason, ...]
    reconciliation_member_identity: str

    def __post_init__(self) -> None:
        payload = reconciliation_member_payload(self, include_identity=False)
        if (
            not _text(self.sponsor_label)
            or not _text(self.universe_member_identity)
            or type(self.market_family) is not IntradayMarketFamily
            or not _text(self.canonical_identity)
            or type(self.semantic_type) is not CanonicalSemanticKind
            or not _text(self.exchange)
            or (self.provider_symbol is not None and not _text(self.provider_symbol))
            or not _unique_texts(self.provider_directive_identities)
            or not _unique_texts(self.provider_record_identities)
            or not _unique_texts(self.derivative_contract_identities)
            or type(self.dimensions) is not AvailabilityDimensions
            or type(self.state) is not ReconciliationState
            or not self.reasons
            or any(type(item) is not ReconciliationReason for item in self.reasons)
            or len(set(self.reasons)) != len(self.reasons)
            or self.reconciliation_member_identity
            != _identity("INTRADAY-RECONCILIATION-MEMBER", payload)
        ):
            raise ReconciliationError(ReconciliationFailure.INPUT_INVALID)


@dataclass(frozen=True, slots=True)
class ReconciliationPublication:
    publication_identity: str
    publication_version: str
    universe_identity: str
    universe_version: str
    universe_integrity_identity: str
    catalogue_identity: str
    catalogue_version: str
    catalogue_integrity_identity: str
    provider_snapshot_identity: str
    provider_snapshot_integrity_identity: str
    commissioning_manifest_identity: str
    effective_boundary: datetime
    provider_evidence_boundary: datetime
    supersedes: str | None
    source_identities: tuple[str, ...]
    provenance: tuple[str, ...]
    members: tuple[ReconciliationMember, ...]
    aggregate_counts: tuple[tuple[str, int], ...]
    integrity_identity: str
    schema_identity: str = RECONCILIATION_SCHEMA

    def __post_init__(self) -> None:
        member_ids = tuple(item.reconciliation_member_identity for item in self.members)
        labels = tuple(item.sponsor_label for item in self.members)
        counts = dict(self.aggregate_counts)
        core = reconciliation_publication_payload(self, include_integrity=False)
        if (
            self.schema_identity != RECONCILIATION_SCHEMA
            or self.publication_identity != RECONCILIATION_IDENTITY
            or not _version(self.publication_version)
            or any(
                not _text(value)
                for value in (
                    self.universe_identity,
                    self.universe_version,
                    self.universe_integrity_identity,
                    self.catalogue_identity,
                    self.catalogue_version,
                    self.catalogue_integrity_identity,
                    self.provider_snapshot_identity,
                    self.provider_snapshot_integrity_identity,
                    self.commissioning_manifest_identity,
                )
            )
            or not _aware(self.effective_boundary)
            or not _aware(self.provider_evidence_boundary)
            or (self.supersedes is not None and not _text(self.supersedes))
            or not _unique_texts(self.source_identities)
            or not _unique_texts(self.provenance)
            or not self.members
            or any(type(item) is not ReconciliationMember for item in self.members)
            or len(set(member_ids)) != len(member_ids)
            or len(set(labels)) != len(labels)
            or not self.aggregate_counts
            or tuple(sorted(counts.items())) != self.aggregate_counts
            or any(not _text(key) or type(value) is not int or value < 0 for key, value in counts.items())
            or counts != aggregate_reconciliation_counts(self.members)
            or self.integrity_identity != _identity("INTRADAY-RECONCILIATION", core)
        ):
            raise ReconciliationError(ReconciliationFailure.INTEGRITY_MISMATCH)

    def lookup(self, sponsor_label: str) -> ReconciliationMember:
        matches = tuple(item for item in self.members if item.sponsor_label == sponsor_label)
        if len(matches) != 1:
            raise ReconciliationError(ReconciliationFailure.INPUT_INVALID)
        return matches[0]

    def require_evidence(
        self,
        *,
        universe_identity: str,
        universe_version: str,
        catalogue_identity: str,
        catalogue_version: str,
        provider_snapshot_identity: str,
    ) -> None:
        if (universe_identity, universe_version) != (
            self.universe_identity,
            self.universe_version,
        ):
            raise ReconciliationError(ReconciliationFailure.STALE_UNIVERSE)
        if (catalogue_identity, catalogue_version) != (
            self.catalogue_identity,
            self.catalogue_version,
        ):
            raise ReconciliationError(ReconciliationFailure.STALE_CATALOGUE)
        if provider_snapshot_identity != self.provider_snapshot_identity:
            raise ReconciliationError(ReconciliationFailure.STALE_PROVIDER_SNAPSHOT)


def reconcile_intraday_publications(
    *,
    universe: IntradayUniversePublication,
    catalogue: InstrumentSemanticPublicationV2,
    provider_snapshot_identity: str,
    provider_snapshot_integrity_identity: str,
    commissioning_manifest_identity: str,
    provider_evidence_boundary: datetime,
    publication_version: str = RECONCILIATION_VERSION,
    supersedes: str | None = None,
) -> ReconciliationPublication:
    """Reconcile exact governed identities without aliasing or contract selection."""

    if (
        type(universe) is not IntradayUniversePublication
        or type(catalogue) is not InstrumentSemanticPublicationV2
        or not _text(provider_snapshot_identity)
        or not _text(provider_snapshot_integrity_identity)
        or not _text(commissioning_manifest_identity)
        or not _aware(provider_evidence_boundary)
    ):
        raise ReconciliationError(ReconciliationFailure.INPUT_INVALID)
    observed_at = catalogue.effective_from
    universe.require_current(observed_at)
    catalogue.require_current(observed_at)
    objects = {item.canonical_id: item for item in catalogue.semantic_objects}
    directives_by_object = _group_directives(catalogue)
    submissions = _provider_submissions(catalogue, observed_at)
    resolver = InstrumentSemanticResolverV2(catalogue, submissions)
    reconciled = tuple(
        _reconcile_member(
            member=member,
            objects=objects,
            directives_by_object=directives_by_object,
            resolver=resolver,
            observed_at=observed_at,
        )
        for member in universe.members
    )
    return create_reconciliation_publication(
        publication_version=publication_version,
        universe_identity=universe.publication_identity,
        universe_version=universe.publication_version,
        universe_integrity_identity=universe.integrity_identity,
        catalogue_identity=catalogue.publication_identity,
        catalogue_version=catalogue.publication_version,
        catalogue_integrity_identity=catalogue.integrity_identity,
        provider_snapshot_identity=provider_snapshot_identity,
        provider_snapshot_integrity_identity=provider_snapshot_integrity_identity,
        commissioning_manifest_identity=commissioning_manifest_identity,
        effective_boundary=observed_at,
        provider_evidence_boundary=provider_evidence_boundary,
        supersedes=supersedes,
        source_identities=(
            universe.integrity_identity,
            catalogue.integrity_identity,
            provider_snapshot_identity,
            provider_snapshot_integrity_identity,
            commissioning_manifest_identity,
        ),
        provenance=(
            "ADR-0014",
            "KRONOS-PLATFORM-WO-P5",
            "Published immutable P1/P3/P4 evidence only",
            "No active-contract selection or execution authority",
        ),
        members=reconciled,
    )


def create_reconciliation_publication(
    *,
    publication_version: str,
    universe_identity: str,
    universe_version: str,
    universe_integrity_identity: str,
    catalogue_identity: str,
    catalogue_version: str,
    catalogue_integrity_identity: str,
    provider_snapshot_identity: str,
    provider_snapshot_integrity_identity: str,
    commissioning_manifest_identity: str,
    effective_boundary: datetime,
    provider_evidence_boundary: datetime,
    supersedes: str | None,
    source_identities: tuple[str, ...],
    provenance: tuple[str, ...],
    members: tuple[ReconciliationMember, ...],
) -> ReconciliationPublication:
    """Seal any governed successor membership without a fixed capacity."""

    values = {
        "publication_identity": RECONCILIATION_IDENTITY,
        "publication_version": publication_version,
        "universe_identity": universe_identity,
        "universe_version": universe_version,
        "universe_integrity_identity": universe_integrity_identity,
        "catalogue_identity": catalogue_identity,
        "catalogue_version": catalogue_version,
        "catalogue_integrity_identity": catalogue_integrity_identity,
        "provider_snapshot_identity": provider_snapshot_identity,
        "provider_snapshot_integrity_identity": provider_snapshot_integrity_identity,
        "commissioning_manifest_identity": commissioning_manifest_identity,
        "effective_boundary": effective_boundary,
        "provider_evidence_boundary": provider_evidence_boundary,
        "supersedes": supersedes,
        "source_identities": source_identities,
        "provenance": provenance,
        "members": members,
        "aggregate_counts": tuple(sorted(aggregate_reconciliation_counts(members).items())),
        "schema_identity": RECONCILIATION_SCHEMA,
    }
    return ReconciliationPublication(
        **values,
        integrity_identity=_identity(
            "INTRADAY-RECONCILIATION",
            reconciliation_publication_payload_from_values(values),
        ),
    )


def create_reconciliation_member(**fields: object) -> ReconciliationMember:
    values = dict(fields)
    payload = {
        "sponsor_label": values["sponsor_label"],
        "universe_member_identity": values["universe_member_identity"],
        "market_family": values["market_family"].value,
        "canonical_identity": values["canonical_identity"],
        "semantic_type": values["semantic_type"].value,
        "exchange": values["exchange"],
        "provider_symbol": values["provider_symbol"],
        "provider_directive_identities": list(values["provider_directive_identities"]),
        "provider_record_identities": list(values["provider_record_identities"]),
        "derivative_contract_identities": list(values["derivative_contract_identities"]),
        "dimensions": {
            name: getattr(values["dimensions"], name).value
            for name in AvailabilityDimensions.__dataclass_fields__
        },
        "state": values["state"].value,
        "reasons": [item.value for item in values["reasons"]],
    }
    return ReconciliationMember(
        **values,  # type: ignore[arg-type]
        reconciliation_member_identity=_identity(
            "INTRADAY-RECONCILIATION-MEMBER", payload
        ),
    )


def _reconcile_member(
    *,
    member: IntradayUniverseMember,
    objects: dict[str, object],
    directives_by_object: dict[str, tuple[object, ...]],
    resolver: InstrumentSemanticResolverV2,
    observed_at: datetime,
) -> ReconciliationMember:
    canonical = _canonical_for_member(member, objects)
    if canonical is None:
        raise ReconciliationError(ReconciliationFailure.INPUT_INVALID)
    directives = directives_by_object.get(canonical.canonical_id, ())
    provider_symbol = directives[0].provider_symbol if len(directives) == 1 else None
    contracts = tuple(
        item
        for item in objects.values()
        if type(item) is DerivativeContractV2
        and item.parent_subject_id == canonical.canonical_id
    )
    contract_directives = tuple(
        directive
        for contract in contracts
        for directive in directives_by_object.get(contract.canonical_id, ())
    )
    is_mcx = member.market_family is IntradayMarketFamily.MCX
    provider_available = (
        bool(contracts) and len(contract_directives) == len(contracts)
        if is_mcx
        else len(directives) == 1
    )
    if type(canonical) is DirectListedInstrumentV2:
        resolver.resolve_listed(canonical.canonical_id, observed_at)
    else:
        resolver.resolve_subject(canonical.canonical_id, observed_at)
    if not is_mcx:
        dimensions = AvailabilityDimensions(
            Availability.AVAILABLE,
            Availability.AVAILABLE,
            Availability.AVAILABLE,
            Availability.AVAILABLE,
            Availability.AVAILABLE,
            (
                Availability.AVAILABLE
                if type(canonical) is DirectListedInstrumentV2
                else Availability.NOT_APPLICABLE
            ),
            Availability.NOT_APPLICABLE,
            Availability.NOT_APPLICABLE,
            Availability.AVAILABLE,
            Availability.NOT_APPLICABLE,
            Availability.AVAILABLE,
            Availability.NOT_ESTABLISHED,
        )
        state = ReconciliationState.FULLY_RECONCILED_FOR_CURRENT_FACTUAL_PATH
        reasons = (
            ReconciliationReason.PRODUCT_MEMBERSHIP_AVAILABLE,
            ReconciliationReason.CANONICAL_IDENTITY_AVAILABLE,
            ReconciliationReason.CANONICAL_SEMANTICS_AVAILABLE,
            ReconciliationReason.PROVIDER_MAPPING_AVAILABLE,
            ReconciliationReason.PROVIDER_FACT_AVAILABLE,
            *(
                (ReconciliationReason.EFFECTIVE_GEOMETRY_AVAILABLE,)
                if type(canonical) is DirectListedInstrumentV2
                else ()
            ),
            ReconciliationReason.RUNTIME_ANALYTICAL_AVAILABLE,
            ReconciliationReason.MACHINE_FACT_CONSUMABLE,
            ReconciliationReason.EXECUTION_ELIGIBILITY_NOT_ESTABLISHED,
        )
    else:
        dimensions = AvailabilityDimensions(
            Availability.AVAILABLE,
            Availability.AVAILABLE,
            Availability.AVAILABLE,
            Availability.AVAILABLE if provider_available else Availability.UNAVAILABLE,
            Availability.AVAILABLE if provider_available else Availability.UNAVAILABLE,
            Availability.NOT_APPLICABLE,
            Availability.AVAILABLE if contracts else Availability.UNAVAILABLE,
            Availability.UNAVAILABLE,
            Availability.AVAILABLE,
            Availability.UNAVAILABLE,
            Availability.UNAVAILABLE,
            Availability.NOT_ESTABLISHED,
        )
        state = (
            ReconciliationState.ACTIVE_CONTRACT_BINDING_UNAVAILABLE
            if contracts
            else ReconciliationState.PROVIDER_CONTRACT_UNAVAILABLE
        )
        reasons = (
            ReconciliationReason.PRODUCT_MEMBERSHIP_AVAILABLE,
            ReconciliationReason.CANONICAL_IDENTITY_AVAILABLE,
            ReconciliationReason.CANONICAL_SEMANTICS_AVAILABLE,
            *(
                (
                    ReconciliationReason.PROVIDER_MAPPING_AVAILABLE,
                    ReconciliationReason.PROVIDER_FACT_AVAILABLE,
                    ReconciliationReason.DERIVATIVE_CONTRACTS_AVAILABLE,
                )
                if provider_available
                else (ReconciliationReason.PROVIDER_CONTRACT_UNAVAILABLE,)
            ),
            ReconciliationReason.ACTIVE_BINDING_MISSING,
            ReconciliationReason.RUNTIME_ANALYTICAL_AVAILABLE,
            ReconciliationReason.RUNTIME_CONTRACT_UNAVAILABLE,
            ReconciliationReason.MACHINE_FACT_PREREQUISITE_UNAVAILABLE,
            ReconciliationReason.EXECUTION_ELIGIBILITY_NOT_ESTABLISHED,
        )
    return create_reconciliation_member(
        sponsor_label=member.sponsor_label,
        universe_member_identity=member.membership_identity,
        market_family=member.market_family,
        canonical_identity=canonical.canonical_id,
        semantic_type=canonical.semantic_kind,
        exchange=canonical.exchange,
        provider_symbol=provider_symbol,
        provider_directive_identities=tuple(
            item.directive_identity for item in (directives or contract_directives)
        ),
        provider_record_identities=tuple(
            item.provider_record_identity for item in (directives or contract_directives)
        ),
        derivative_contract_identities=tuple(
            sorted(item.canonical_id for item in contracts)
        ),
        dimensions=dimensions,
        state=state,
        reasons=reasons,
    )


def _canonical_for_member(
    member: IntradayUniverseMember, objects: dict[str, object]
) -> DirectListedInstrumentV2 | AnalyticalSubjectV2 | None:
    # Current universe labels are preserved exactly.  The governed source/member
    # identity is used for cash/index; exact canonical_symbol is used for MCX.
    source_matches = tuple(
        item
        for item in objects.values()
        if type(item) in {DirectListedInstrumentV2, AnalyticalSubjectV2}
        and item.source_identity == member.membership_identity
    )
    if len(source_matches) == 1:
        return source_matches[0]
    mcx_matches = tuple(
        item
        for item in objects.values()
        if type(item) is AnalyticalSubjectV2
        and item.exchange == "MCX"
        and item.canonical_symbol == member.sponsor_label
    )
    return mcx_matches[0] if len(mcx_matches) == 1 else None


def _group_directives(catalogue: InstrumentSemanticPublicationV2) -> dict[str, tuple[object, ...]]:
    result: dict[str, tuple[object, ...]] = {}
    for canonical_id in {item.canonical_object_id for item in catalogue.provider_directives}:
        result[canonical_id] = tuple(
            item
            for item in catalogue.provider_directives
            if item.canonical_object_id == canonical_id
        )
    return result


def _provider_submissions(
    catalogue: InstrumentSemanticPublicationV2, observed_at: datetime
) -> tuple[ProviderInstrumentSubmissionV2, ...]:
    objects = {item.canonical_id: item for item in catalogue.semantic_objects}
    mappings = {item.mapping_identity: item for item in catalogue.classification_mappings}
    values = []
    for directive in catalogue.provider_directives:
        canonical = objects[directive.canonical_object_id]
        if type(canonical) not in {DirectListedInstrumentV2, AnalyticalSubjectV2}:
            continue
        mapping = mappings[directive.classification_mapping_identity]
        geometry = canonical.geometry[0] if type(canonical) is DirectListedInstrumentV2 else None
        values.append(
            ProviderInstrumentSubmissionV2(
                provider_record_identity=directive.provider_record_identity,
                provider=directive.provider,
                provider_symbol=directive.provider_symbol,
                exchange=mapping.exchange,
                segment=mapping.segment,
                provider_instrument_type=mapping.provider_instrument_type,
                tick_size=geometry.tick_size if geometry else None,
                lot_size=geometry.lot_size if geometry else None,
                source_boundary=directive.effective_from,
                valid_through=directive.effective_through,
                provenance=(directive.source_identity, directive.integrity_identity),
            )
        )
    return tuple(values)


def aggregate_reconciliation_counts(
    members: Iterable[ReconciliationMember],
) -> dict[str, int]:
    items = tuple(members)
    counts: dict[str, int] = {"members.total": len(items)}
    for family in IntradayMarketFamily:
        counts[f"family.{family.value}"] = sum(item.market_family is family for item in items)
    for semantic in CanonicalSemanticKind:
        counts[f"semantic.{semantic.value}"] = sum(item.semantic_type is semantic for item in items)
    for name in AvailabilityDimensions.__dataclass_fields__:
        for availability in Availability:
            counts[f"dimension.{name}.{availability.value}"] = sum(
                getattr(item.dimensions, name) is availability for item in items
            )
    for state in ReconciliationState:
        counts[f"state.{state.value}"] = sum(item.state is state for item in items)
    counts["derivative_contracts.total"] = sum(
        len(item.derivative_contract_identities) for item in items
    )
    return counts


def reconciliation_member_payload(
    value: ReconciliationMember, *, include_identity: bool = True
) -> dict[str, object]:
    payload: dict[str, object] = {
        "sponsor_label": value.sponsor_label,
        "universe_member_identity": value.universe_member_identity,
        "market_family": value.market_family.value,
        "canonical_identity": value.canonical_identity,
        "semantic_type": value.semantic_type.value,
        "exchange": value.exchange,
        "provider_symbol": value.provider_symbol,
        "provider_directive_identities": list(value.provider_directive_identities),
        "provider_record_identities": list(value.provider_record_identities),
        "derivative_contract_identities": list(value.derivative_contract_identities),
        "dimensions": {
            name: getattr(value.dimensions, name).value
            for name in AvailabilityDimensions.__dataclass_fields__
        },
        "state": value.state.value,
        "reasons": [item.value for item in value.reasons],
    }
    if include_identity:
        payload["reconciliation_member_identity"] = value.reconciliation_member_identity
    return payload


def reconciliation_publication_payload(
    value: ReconciliationPublication, *, include_integrity: bool = True
) -> dict[str, object]:
    payload = reconciliation_publication_payload_from_values(
        {
            name: getattr(value, name)
            for name in ReconciliationPublication.__dataclass_fields__
            if name != "integrity_identity"
        }
    )
    if include_integrity:
        payload["integrity_identity"] = value.integrity_identity
    return payload


def reconciliation_publication_payload_from_values(values: dict[str, object]) -> dict[str, object]:
    return {
        "schema_identity": values["schema_identity"],
        "publication_identity": values["publication_identity"],
        "publication_version": values["publication_version"],
        "universe_identity": values["universe_identity"],
        "universe_version": values["universe_version"],
        "universe_integrity_identity": values["universe_integrity_identity"],
        "catalogue_identity": values["catalogue_identity"],
        "catalogue_version": values["catalogue_version"],
        "catalogue_integrity_identity": values["catalogue_integrity_identity"],
        "provider_snapshot_identity": values["provider_snapshot_identity"],
        "provider_snapshot_integrity_identity": values["provider_snapshot_integrity_identity"],
        "commissioning_manifest_identity": values["commissioning_manifest_identity"],
        "effective_boundary": values["effective_boundary"].isoformat(),
        "provider_evidence_boundary": values["provider_evidence_boundary"].isoformat(),
        "supersedes": values["supersedes"],
        "source_identities": list(values["source_identities"]),
        "provenance": list(values["provenance"]),
        "members": [reconciliation_member_payload(item) for item in values["members"]],
        "aggregate_counts": {key: count for key, count in values["aggregate_counts"]},
    }


def parse_reconciliation_publication(encoded: bytes) -> ReconciliationPublication:
    try:
        document = json.loads(encoded)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ReconciliationError(ReconciliationFailure.INTEGRITY_MISMATCH) from error
    try:
        members = tuple(_parse_member(item) for item in document["members"])
        counts = tuple(sorted((key, value) for key, value in document["aggregate_counts"].items()))
        value = ReconciliationPublication(
            publication_identity=document["publication_identity"],
            publication_version=document["publication_version"],
            universe_identity=document["universe_identity"],
            universe_version=document["universe_version"],
            universe_integrity_identity=document["universe_integrity_identity"],
            catalogue_identity=document["catalogue_identity"],
            catalogue_version=document["catalogue_version"],
            catalogue_integrity_identity=document["catalogue_integrity_identity"],
            provider_snapshot_identity=document["provider_snapshot_identity"],
            provider_snapshot_integrity_identity=document["provider_snapshot_integrity_identity"],
            commissioning_manifest_identity=document["commissioning_manifest_identity"],
            effective_boundary=datetime.fromisoformat(document["effective_boundary"]),
            provider_evidence_boundary=datetime.fromisoformat(document["provider_evidence_boundary"]),
            supersedes=document["supersedes"],
            source_identities=tuple(document["source_identities"]),
            provenance=tuple(document["provenance"]),
            members=members,
            aggregate_counts=counts,
            integrity_identity=document["integrity_identity"],
            schema_identity=document["schema_identity"],
        )
    except (KeyError, TypeError, ValueError, ReconciliationError) as error:
        raise ReconciliationError(ReconciliationFailure.INTEGRITY_MISMATCH) from error
    if reconciliation_publication_bytes(value) != encoded:
        raise ReconciliationError(ReconciliationFailure.INTEGRITY_MISMATCH)
    return value


def _parse_member(document: dict[str, object]) -> ReconciliationMember:
    dimensions = AvailabilityDimensions(
        **{name: Availability(document["dimensions"][name]) for name in AvailabilityDimensions.__dataclass_fields__}
    )
    return ReconciliationMember(
        sponsor_label=document["sponsor_label"],
        universe_member_identity=document["universe_member_identity"],
        market_family=IntradayMarketFamily(document["market_family"]),
        canonical_identity=document["canonical_identity"],
        semantic_type=CanonicalSemanticKind(document["semantic_type"]),
        exchange=document["exchange"],
        provider_symbol=document["provider_symbol"],
        provider_directive_identities=tuple(document["provider_directive_identities"]),
        provider_record_identities=tuple(document["provider_record_identities"]),
        derivative_contract_identities=tuple(document["derivative_contract_identities"]),
        dimensions=dimensions,
        state=ReconciliationState(document["state"]),
        reasons=tuple(ReconciliationReason(item) for item in document["reasons"]),
        reconciliation_member_identity=document["reconciliation_member_identity"],
    )


def reconciliation_publication_bytes(value: ReconciliationPublication) -> bytes:
    return _encode(reconciliation_publication_payload(value))


def _identity(prefix: str, value: object) -> str:
    return f"{prefix}-{sha256(_encode(value)).hexdigest()}"


def _encode(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


def _version(value: object) -> bool:
    return _text(value) and len(value.split(".")) == 3 and all(part.isdigit() for part in value.split("."))


def _unique_texts(values: object) -> bool:
    return isinstance(values, tuple) and all(_text(item) for item in values) and len(set(values)) == len(values)


__all__ = [
    "Availability",
    "AvailabilityDimensions",
    "RECONCILIATION_IDENTITY",
    "RECONCILIATION_SCHEMA",
    "RECONCILIATION_VERSION",
    "ReconciliationError",
    "ReconciliationFailure",
    "ReconciliationMember",
    "ReconciliationPublication",
    "ReconciliationReason",
    "ReconciliationState",
    "aggregate_reconciliation_counts",
    "create_reconciliation_member",
    "create_reconciliation_publication",
    "parse_reconciliation_publication",
    "reconcile_intraday_publications",
    "reconciliation_publication_bytes",
]
