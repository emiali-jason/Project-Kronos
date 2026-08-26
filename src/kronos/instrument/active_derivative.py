"""ADR-0017 governed active derivative selection and immutable binding facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json
from zoneinfo import ZoneInfo

from kronos.instrument.semantic_v2 import (
    ACTIVE_DERIVATIVE_CONTRACT_BINDING_V1_VERSION,
    AnalyticalSubjectV2,
    CanonicalClassification,
    DerivativeContractV2,
    InstrumentSemanticPublicationV2,
    ProviderMappingDirectiveV2,
    ActiveDerivativeContractBinding,
    create_active_derivative_binding,
    create_derivative_contract,
    create_effective_geometry,
    create_provider_mapping_directive_v2,
    create_semantic_publication_v2,
)
from kronos.market.calendar import (
    MarketCalendarPublisher,
    McxContractFamilySessionProfile,
    McxContractSessionUnavailable,
)
from kronos.provider.instrument_master import (
    ProviderAcquisitionOutcome,
    ProviderInstrumentRecord,
    ProviderInstrumentSnapshot,
)


ACTIVE_DERIVATIVE_SELECTION_RULE_IDENTITY = (
    "KRONOS-GOVERNED-ACTIVE-DERIVATIVE-CONTRACT-SELECTION-V1"
)
ACTIVE_DERIVATIVE_SELECTION_RULE_VERSION = "1.0.0"
ACTIVE_DERIVATIVE_BINDING_ARTIFACT_IDENTITY = (
    "KRONOS-GOVERNED-ACTIVE-DERIVATIVE-BINDING-V1"
)
ACTIVE_DERIVATIVE_BINDING_ARTIFACT_VERSION = "1.0.0"
ACTIVE_DERIVATIVE_CATALOGUE_VERSION = "1.2.0"

ACTIVE_DERIVATIVE_FAMILY_MAPPINGS = (
    ("GOLDM", "MCX-SUBJECT-GOLDM", "GOLDM"),
    ("SILVERM", "MCX-SUBJECT-SILVERM", "SILVERM"),
    ("COPPER", "MCX-SUBJECT-COPPER", "COPPER"),
    ("NATGAS", "MCX-SUBJECT-NATGAS", "NATURALGAS"),
    ("CRUDE", "MCX-SUBJECT-CRUDE", "CRUDEOIL"),
)


class ActiveDerivativeSelectionFailure(StrEnum):
    INPUT_INVALID = "ACTIVE_DERIVATIVE_SELECTION_INPUT_INVALID"
    FAMILY_MAPPING_UNAVAILABLE = "ACTIVE_DERIVATIVE_FAMILY_MAPPING_UNAVAILABLE"
    PROVIDER_SNAPSHOT_UNAVAILABLE = "PROVIDER_INSTRUMENT_SNAPSHOT_UNAVAILABLE"
    PROVIDER_SNAPSHOT_STALE = "PROVIDER_INSTRUMENT_SNAPSHOT_STALE"
    PROVIDER_CONTRACT_UNAVAILABLE = "PROVIDER_CONTRACT_UNAVAILABLE"
    CANONICAL_CONTRACT_UNAVAILABLE = "CANONICAL_DERIVATIVE_CONTRACT_UNAVAILABLE"
    DOMAIN008_SESSION_UNAVAILABLE = "MCX_CONTRACT_SESSION_UNAVAILABLE"
    ACTIVE_BINDING_UNAVAILABLE = "ACTIVE_DERIVATIVE_BINDING_UNAVAILABLE"
    ACTIVE_BINDING_AMBIGUOUS = "ACTIVE_DERIVATIVE_BINDING_AMBIGUOUS"
    INTEGRITY_INVALID = "ACTIVE_DERIVATIVE_BINDING_INTEGRITY_INVALID"


class ActiveDerivativeSelectionError(RuntimeError):
    def __init__(self, failure: ActiveDerivativeSelectionFailure) -> None:
        if type(failure) is not ActiveDerivativeSelectionFailure:
            raise ValueError("ACTIVE_DERIVATIVE_SELECTION_ERROR_INVALID")
        self.failure = failure
        super().__init__(failure.value)


@dataclass(frozen=True, slots=True)
class ActiveDerivativeCandidateAccounting:
    family_record_count: int
    eligible_candidate_count: int
    expired_candidate_count: int
    rejected_candidate_count: int
    minimum_expiry_candidate_count: int

    def __post_init__(self) -> None:
        if any(
            type(value) is not int or value < 0
            for value in (
                self.family_record_count,
                self.eligible_candidate_count,
                self.expired_candidate_count,
                self.rejected_candidate_count,
                self.minimum_expiry_candidate_count,
            )
        ) or self.family_record_count != (
            self.eligible_candidate_count
            + self.expired_candidate_count
            + self.rejected_candidate_count
        ):
            raise ActiveDerivativeSelectionError(
                ActiveDerivativeSelectionFailure.INTEGRITY_INVALID
            )


@dataclass(frozen=True, slots=True, repr=False)
class ActiveDerivativeBindingArtifact:
    analytical_subject: str
    canonical_subject_id: str
    provider_contract_family: str
    provider_symbol: str
    provider_record_identity: str
    exchange: str
    segment: str
    provider_instrument_type: str
    tick_size: Decimal
    lot_size: int
    contract_expiry: date
    observation_boundary: datetime
    expiry_eligibility_boundary: datetime
    domain008_session_identity: str
    domain008_contract_identity: str
    domain008_contract_version: str
    domain008_publication_identity: str
    domain008_publication_version: str
    domain008_publication_sha256: str
    selection_rule_identity: str
    selection_rule_version: str
    provider_snapshot_identity: str
    provider_snapshot_integrity_identity: str
    provider_mapping_directive_identity: str
    catalogue_identity: str
    catalogue_version: str
    catalogue_integrity_identity: str
    active_binding: ActiveDerivativeContractBinding
    provenance: tuple[str, ...]
    integrity_identity: str
    artifact_identity: str = ACTIVE_DERIVATIVE_BINDING_ARTIFACT_IDENTITY
    artifact_version: str = ACTIVE_DERIVATIVE_BINDING_ARTIFACT_VERSION

    def __post_init__(self) -> None:
        fields = active_derivative_binding_payload(self, include_integrity=False)
        if (
            self.artifact_identity != ACTIVE_DERIVATIVE_BINDING_ARTIFACT_IDENTITY
            or self.artifact_version != ACTIVE_DERIVATIVE_BINDING_ARTIFACT_VERSION
            or self.selection_rule_identity != ACTIVE_DERIVATIVE_SELECTION_RULE_IDENTITY
            or self.selection_rule_version != ACTIVE_DERIVATIVE_SELECTION_RULE_VERSION
            or any(
                not _text(item)
                for item in (
                    self.analytical_subject,
                    self.canonical_subject_id,
                    self.provider_contract_family,
                    self.provider_symbol,
                    self.provider_record_identity,
                    self.exchange,
                    self.segment,
                    self.provider_instrument_type,
                    self.domain008_session_identity,
                    self.domain008_contract_identity,
                    self.domain008_contract_version,
                    self.domain008_publication_identity,
                    self.domain008_publication_version,
                    self.domain008_publication_sha256,
                    self.provider_snapshot_identity,
                    self.provider_snapshot_integrity_identity,
                    self.provider_mapping_directive_identity,
                    self.catalogue_identity,
                    self.catalogue_version,
                    self.catalogue_integrity_identity,
                )
            )
            or type(self.contract_expiry) is not date
            or type(self.tick_size) is not Decimal
            or self.tick_size <= 0
            or type(self.lot_size) is not int
            or self.lot_size <= 0
            or not _aware(self.observation_boundary)
            or not _aware(self.expiry_eligibility_boundary)
            or self.observation_boundary > self.expiry_eligibility_boundary
            or type(self.active_binding) is not ActiveDerivativeContractBinding
            or self.active_binding.subject_id != self.canonical_subject_id
            or self.active_binding.contract_expiry != self.contract_expiry
            or self.active_binding.provider_reference_identity
            != self.provider_mapping_directive_identity
            or not _texts(self.provenance)
            or self.integrity_identity
            != _identity("ACTIVE-DERIVATIVE-BINDING-ARTIFACT", fields)
        ):
            raise ActiveDerivativeSelectionError(
                ActiveDerivativeSelectionFailure.INTEGRITY_INVALID
            )

    @property
    def binding_identity(self) -> str:
        return self.active_binding.binding_identity

    def __repr__(self) -> str:
        return (
            "<ActiveDerivativeBindingArtifact "
            f"subject={self.analytical_subject} binding={self.binding_identity} "
            "provider-token-redacted>"
        )


@dataclass(frozen=True, slots=True)
class ActiveDerivativeSelectionOutcome:
    analytical_subject: str
    canonical_subject_id: str
    provider_contract_family: str
    accounting: ActiveDerivativeCandidateAccounting
    binding: ActiveDerivativeBindingArtifact | None
    failure: ActiveDerivativeSelectionFailure | None

    def __post_init__(self) -> None:
        if (
            not all(_text(item) for item in (
                self.analytical_subject,
                self.canonical_subject_id,
                self.provider_contract_family,
            ))
            or type(self.accounting) is not ActiveDerivativeCandidateAccounting
            or (self.binding is None) == (self.failure is None)
            or (
                self.binding is not None
                and (
                    self.binding.analytical_subject != self.analytical_subject
                    or self.binding.canonical_subject_id != self.canonical_subject_id
                    or self.binding.provider_contract_family
                    != self.provider_contract_family
                )
            )
        ):
            raise ActiveDerivativeSelectionError(
                ActiveDerivativeSelectionFailure.INTEGRITY_INVALID
            )


@dataclass(frozen=True, slots=True)
class ActiveDerivativeResolutionSet:
    observation_boundary: datetime
    provider_snapshot_identity: str
    provider_snapshot_integrity_identity: str
    outcomes: tuple[ActiveDerivativeSelectionOutcome, ...]

    def __post_init__(self) -> None:
        if (
            not _aware(self.observation_boundary)
            or not _text(self.provider_snapshot_identity)
            or not _text(self.provider_snapshot_integrity_identity)
            or tuple(item.analytical_subject for item in self.outcomes)
            != tuple(item[0] for item in ACTIVE_DERIVATIVE_FAMILY_MAPPINGS)
        ):
            raise ActiveDerivativeSelectionError(
                ActiveDerivativeSelectionFailure.INTEGRITY_INVALID
            )

    @property
    def successful_bindings(self) -> tuple[ActiveDerivativeBindingArtifact, ...]:
        return tuple(item.binding for item in self.outcomes if item.binding is not None)

    def for_subject(self, analytical_subject: str) -> ActiveDerivativeSelectionOutcome:
        matches = tuple(
            item for item in self.outcomes
            if item.analytical_subject == analytical_subject
            or item.canonical_subject_id == analytical_subject
        )
        if len(matches) != 1:
            raise ActiveDerivativeSelectionError(
                ActiveDerivativeSelectionFailure.FAMILY_MAPPING_UNAVAILABLE
            )
        return matches[0]


class GovernedActiveDerivativeResolver:
    """Select the unique minimum eligible expiry under ADR-0017."""

    def __init__(
        self,
        *,
        catalogue: InstrumentSemanticPublicationV2,
        provider_snapshot: ProviderInstrumentSnapshot,
        calendar_publisher: MarketCalendarPublisher,
    ) -> None:
        if (
            type(catalogue) is not InstrumentSemanticPublicationV2
            or type(provider_snapshot) is not ProviderInstrumentSnapshot
            or type(calendar_publisher) is not MarketCalendarPublisher
        ):
            raise ActiveDerivativeSelectionError(
                ActiveDerivativeSelectionFailure.INPUT_INVALID
            )
        self._catalogue = catalogue
        self._snapshot = provider_snapshot
        self._calendar = calendar_publisher

    def resolve_all(
        self,
        observation_boundary: datetime,
        *,
        previous_bindings: dict[str, ActiveDerivativeBindingArtifact] | None = None,
    ) -> ActiveDerivativeResolutionSet:
        if not _aware(observation_boundary):
            raise ActiveDerivativeSelectionError(
                ActiveDerivativeSelectionFailure.INPUT_INVALID
            )
        self._catalogue.require_current(observation_boundary)
        if self._snapshot.acquisition_outcome is not ProviderAcquisitionOutcome.COMPLETE:
            raise ActiveDerivativeSelectionError(
                ActiveDerivativeSelectionFailure.PROVIDER_SNAPSHOT_UNAVAILABLE
            )
        if self._snapshot.acquisition_effective_at != observation_boundary:
            raise ActiveDerivativeSelectionError(
                ActiveDerivativeSelectionFailure.PROVIDER_SNAPSHOT_STALE
            )
        prior = previous_bindings or {}
        outcomes = tuple(
            self._resolve_one(
                analytical_subject=label,
                canonical_subject_id=subject_id,
                provider_contract_family=family,
                observation_boundary=observation_boundary,
                previous_binding=prior.get(subject_id),
            )
            for label, subject_id, family in ACTIVE_DERIVATIVE_FAMILY_MAPPINGS
        )
        return ActiveDerivativeResolutionSet(
            observation_boundary=observation_boundary,
            provider_snapshot_identity=self._snapshot.snapshot_identity,
            provider_snapshot_integrity_identity=self._snapshot.integrity_identity,
            outcomes=outcomes,
        )

    def _resolve_one(
        self,
        *,
        analytical_subject: str,
        canonical_subject_id: str,
        provider_contract_family: str,
        observation_boundary: datetime,
        previous_binding: ActiveDerivativeBindingArtifact | None,
    ) -> ActiveDerivativeSelectionOutcome:
        records = tuple(
            item for item in self._snapshot.records
            if item.provider == "KITE"
            and item.exchange == "MCX"
            and item.segment == "MCX-FUT"
            and item.instrument_type == "FUT"
            and item.name == provider_contract_family
        )
        if not records:
            return _unavailable_outcome(
                analytical_subject,
                canonical_subject_id,
                provider_contract_family,
                ActiveDerivativeSelectionFailure.PROVIDER_CONTRACT_UNAVAILABLE,
            )
        eligible: list[tuple[
            ProviderInstrumentRecord,
            DerivativeContractV2,
            ProviderMappingDirectiveV2,
            McxContractFamilySessionProfile,
        ]] = []
        expired = 0
        rejected = 0
        session_unavailable = False
        canonical_unavailable = False
        local_date = observation_boundary.astimezone(
            ZoneInfo("Asia/Kolkata")
        ).date()
        for record in records:
            if record.expiry is None or record.expiry < local_date:
                expired += 1
                continue
            try:
                profile = self._calendar.mcx_contract_session_profile(
                    contract_family=provider_contract_family,
                    contract_expiry=record.expiry,
                    trading_date=local_date,
                    observed_at=observation_boundary,
                )
            except McxContractSessionUnavailable:
                session_unavailable = True
                rejected += 1
                continue
            if not profile.contract_eligible:
                expired += 1
                continue
            matches = tuple(
                item for item in self._catalogue.semantic_objects
                if type(item) is DerivativeContractV2
                and item.parent_subject_id == canonical_subject_id
                and item.expiry == record.expiry
                and item.canonical_symbol == record.trading_symbol
                and item.exchange == "MCX"
            )
            if len(matches) != 1:
                canonical_unavailable = True
                rejected += 1
                continue
            contract = matches[0]
            directives = tuple(
                item for item in self._catalogue.provider_directives
                if item.canonical_object_id == contract.canonical_id
                and item.provider == "KITE"
                and item.provider_symbol == record.trading_symbol
                and item.active_at(observation_boundary)
            )
            mappings = tuple(
                item for item in self._catalogue.classification_mappings
                if item.mapping_identity
                == (directives[0].classification_mapping_identity if len(directives) == 1 else "")
                and item.active_at(observation_boundary)
                and item.provider_key == ("KITE", "MCX", "MCX-FUT", "FUT")
                and item.canonical_classification is CanonicalClassification.MCX_FUTURE
            )
            geometry = tuple(
                item for item in contract.geometry if item.active_at(observation_boundary)
            )
            if (
                len(directives) != 1
                or len(mappings) != 1
                or len(geometry) != 1
                or geometry[0].tick_size != record.tick_size
                or geometry[0].lot_size != record.lot_size
            ):
                rejected += 1
                continue
            eligible.append((record, contract, directives[0], profile))
        if not eligible:
            failure = (
                ActiveDerivativeSelectionFailure.CANONICAL_CONTRACT_UNAVAILABLE
                if canonical_unavailable
                else ActiveDerivativeSelectionFailure.DOMAIN008_SESSION_UNAVAILABLE
                if session_unavailable
                else ActiveDerivativeSelectionFailure.ACTIVE_BINDING_UNAVAILABLE
            )
            return ActiveDerivativeSelectionOutcome(
                analytical_subject=analytical_subject,
                canonical_subject_id=canonical_subject_id,
                provider_contract_family=provider_contract_family,
                accounting=ActiveDerivativeCandidateAccounting(
                    family_record_count=len(records),
                    eligible_candidate_count=0,
                    expired_candidate_count=expired,
                    rejected_candidate_count=rejected,
                    minimum_expiry_candidate_count=0,
                ),
                binding=None,
                failure=failure,
            )
        minimum_expiry = min(item[0].expiry for item in eligible)
        selected = tuple(item for item in eligible if item[0].expiry == minimum_expiry)
        accounting = ActiveDerivativeCandidateAccounting(
            family_record_count=len(records),
            eligible_candidate_count=len(eligible),
            expired_candidate_count=expired,
            rejected_candidate_count=rejected,
            minimum_expiry_candidate_count=len(selected),
        )
        if len(selected) != 1:
            return ActiveDerivativeSelectionOutcome(
                analytical_subject=analytical_subject,
                canonical_subject_id=canonical_subject_id,
                provider_contract_family=provider_contract_family,
                accounting=accounting,
                binding=None,
                failure=ActiveDerivativeSelectionFailure.ACTIVE_BINDING_AMBIGUOUS,
            )
        record, contract, directive, profile = selected[0]
        artifact = _create_binding_artifact(
            analytical_subject=analytical_subject,
            canonical_subject_id=canonical_subject_id,
            provider_contract_family=provider_contract_family,
            record=record,
            contract=contract,
            directive=directive,
            profile=profile,
            observation_boundary=observation_boundary,
            catalogue=self._catalogue,
            snapshot=self._snapshot,
            previous_binding=previous_binding,
        )
        return ActiveDerivativeSelectionOutcome(
            analytical_subject=analytical_subject,
            canonical_subject_id=canonical_subject_id,
            provider_contract_family=provider_contract_family,
            accounting=accounting,
            binding=artifact,
            failure=None,
        )


def create_mcx_contract_catalogue_successor(
    *,
    predecessor: InstrumentSemanticPublicationV2,
    provider_snapshot: ProviderInstrumentSnapshot,
) -> InstrumentSemanticPublicationV2:
    """Publish missing exact Provider-backed contracts without selecting one."""

    if (
        type(predecessor) is not InstrumentSemanticPublicationV2
        or type(provider_snapshot) is not ProviderInstrumentSnapshot
    ):
        raise ActiveDerivativeSelectionError(
            ActiveDerivativeSelectionFailure.INPUT_INVALID
        )
    subjects = {
        item.canonical_id: item
        for item in predecessor.semantic_objects
        if type(item) is AnalyticalSubjectV2
    }
    existing = {
        (item.parent_subject_id, item.canonical_symbol, item.expiry)
        for item in predecessor.semantic_objects
        if type(item) is DerivativeContractV2
    }
    additions: list[DerivativeContractV2] = []
    directives: list[ProviderMappingDirectiveV2] = []
    for label, subject_id, family in ACTIVE_DERIVATIVE_FAMILY_MAPPINGS:
        subject = subjects.get(subject_id)
        if (
            subject is None
            or subject.canonical_symbol != label
            or subject.classification is not CanonicalClassification.MCX_COMMODITY
        ):
            raise ActiveDerivativeSelectionError(
                ActiveDerivativeSelectionFailure.FAMILY_MAPPING_UNAVAILABLE
            )
        records = tuple(sorted(
            (
                item for item in provider_snapshot.records
                if item.provider == "KITE"
                and item.exchange == "MCX"
                and item.segment == "MCX-FUT"
                and item.instrument_type == "FUT"
                and item.name == family
                and item.expiry is not None
            ),
            key=lambda item: (item.expiry, item.trading_symbol),
        ))
        if not records:
            raise ActiveDerivativeSelectionError(
                ActiveDerivativeSelectionFailure.PROVIDER_CONTRACT_UNAVAILABLE
            )
        identities = tuple((item.trading_symbol, item.expiry) for item in records)
        if len(identities) != len(set(identities)):
            raise ActiveDerivativeSelectionError(
                ActiveDerivativeSelectionFailure.ACTIVE_BINDING_AMBIGUOUS
            )
        for record in records:
            key = (subject_id, record.trading_symbol, record.expiry)
            if key in existing:
                continue
            assert record.expiry is not None
            canonical_id = f"MCX-FUT-{label}-{record.expiry.isoformat()}"
            valid_through = datetime.combine(
                record.expiry,
                time(23, 59, 59),
                ZoneInfo("Asia/Kolkata"),
            )
            provenance = (
                "ADR-0017",
                "KRONOS-INTRADAY-WO-06MCX-R",
                provider_snapshot.snapshot_identity,
                record.provider_record_identity,
                "Provider facts remain DOMAIN-006-owned",
                "No execution eligibility",
            )
            geometry = create_effective_geometry(
                geometry_identity=f"MCXR-GEOMETRY-{canonical_id}",
                geometry_version="1.0.0",
                canonical_object_id=canonical_id,
                tick_size=record.tick_size,
                lot_size=record.lot_size,
                effective_from=predecessor.effective_from,
                effective_through=valid_through,
                source_identity=provider_snapshot.snapshot_identity,
                provenance=provenance,
            )
            contract = create_derivative_contract(
                canonical_id=canonical_id,
                canonical_symbol=record.trading_symbol,
                exchange="MCX",
                classification=CanonicalClassification.MCX_FUTURE,
                parent_subject_id=subject_id,
                expiry=record.expiry,
                valid_from=predecessor.effective_from,
                valid_through=valid_through,
                source_identity=provider_snapshot.snapshot_identity,
                provenance=provenance,
                geometry=(geometry,),
            )
            directive = create_provider_mapping_directive_v2(
                directive_identity=f"MCXR-KITE-DIRECTIVE-{canonical_id}",
                directive_version="1.0.0",
                canonical_object_id=canonical_id,
                provider="KITE",
                provider_record_identity=record.provider_record_identity,
                provider_symbol=record.trading_symbol,
                classification_mapping_identity="P4-KITE-MCX-FUTURE-MAPPING",
                effective_from=predecessor.effective_from,
                effective_through=valid_through,
                source_identity=provider_snapshot.snapshot_identity,
                provenance=provenance,
                supersedes=None,
            )
            additions.append(contract)
            directives.append(directive)
            existing.add(key)
    return create_semantic_publication_v2(
        publication_version=ACTIVE_DERIVATIVE_CATALOGUE_VERSION,
        effective_from=predecessor.effective_from,
        effective_through=predecessor.effective_through,
        supersedes=predecessor.integrity_identity,
        source_identities=predecessor.source_identities + ("ADR-0017",),
        provenance=predecessor.provenance + (
            "ADR-0017",
            "KRONOS-INTRADAY-WO-06MCX-R",
            "Exact five-family mapping; no active selection in publication",
        ),
        semantic_objects=predecessor.semantic_objects + tuple(additions),
        classification_mappings=predecessor.classification_mappings,
        provider_directives=predecessor.provider_directives + tuple(directives),
        active_bindings=(),
    )


def active_derivative_binding_payload(
    value: ActiveDerivativeBindingArtifact,
    *,
    include_integrity: bool = True,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "artifact_identity": value.artifact_identity,
        "artifact_version": value.artifact_version,
        "analytical_subject": value.analytical_subject,
        "canonical_subject_id": value.canonical_subject_id,
        "provider_contract_family": value.provider_contract_family,
        "provider_symbol": value.provider_symbol,
        "provider_record_identity": value.provider_record_identity,
        "exchange": value.exchange,
        "segment": value.segment,
        "provider_instrument_type": value.provider_instrument_type,
        "tick_size": value.tick_size,
        "lot_size": value.lot_size,
        "contract_expiry": value.contract_expiry,
        "observation_boundary": value.observation_boundary,
        "expiry_eligibility_boundary": value.expiry_eligibility_boundary,
        "domain008_session_identity": value.domain008_session_identity,
        "domain008_contract_identity": value.domain008_contract_identity,
        "domain008_contract_version": value.domain008_contract_version,
        "domain008_publication_identity": value.domain008_publication_identity,
        "domain008_publication_version": value.domain008_publication_version,
        "domain008_publication_sha256": value.domain008_publication_sha256,
        "selection_rule_identity": value.selection_rule_identity,
        "selection_rule_version": value.selection_rule_version,
        "provider_snapshot_identity": value.provider_snapshot_identity,
        "provider_snapshot_integrity_identity": value.provider_snapshot_integrity_identity,
        "provider_mapping_directive_identity": value.provider_mapping_directive_identity,
        "catalogue_identity": value.catalogue_identity,
        "catalogue_version": value.catalogue_version,
        "catalogue_integrity_identity": value.catalogue_integrity_identity,
        "active_binding": _binding_payload(value.active_binding),
        "provenance": value.provenance,
    }
    if include_integrity:
        payload["integrity_identity"] = value.integrity_identity
    return payload


def active_derivative_binding_bytes(value: ActiveDerivativeBindingArtifact) -> bytes:
    if type(value) is not ActiveDerivativeBindingArtifact:
        raise ActiveDerivativeSelectionError(
            ActiveDerivativeSelectionFailure.INTEGRITY_INVALID
        )
    return _encode(active_derivative_binding_payload(value))


def parse_active_derivative_binding(encoded: bytes) -> ActiveDerivativeBindingArtifact:
    try:
        raw = json.loads(encoded)
        binding_raw = raw["active_binding"]
        binding = ActiveDerivativeContractBinding(
            binding_identity=binding_raw["binding_identity"],
            binding_version=binding_raw["binding_version"],
            subject_id=binding_raw["subject_id"],
            derivative_contract_id=binding_raw["derivative_contract_id"],
            effective_from=datetime.fromisoformat(binding_raw["effective_from"]),
            effective_through=datetime.fromisoformat(binding_raw["effective_through"]),
            contract_expiry=date.fromisoformat(binding_raw["contract_expiry"]),
            provider_reference_identity=binding_raw["provider_reference_identity"],
            source_identity=binding_raw["source_identity"],
            provenance=tuple(binding_raw["provenance"]),
            supersedes=binding_raw["supersedes"],
            integrity_identity=binding_raw["integrity_identity"],
            contract_identity=binding_raw["contract_identity"],
        )
        value = ActiveDerivativeBindingArtifact(
            artifact_identity=raw["artifact_identity"],
            artifact_version=raw["artifact_version"],
            analytical_subject=raw["analytical_subject"],
            canonical_subject_id=raw["canonical_subject_id"],
            provider_contract_family=raw["provider_contract_family"],
            provider_symbol=raw["provider_symbol"],
            provider_record_identity=raw["provider_record_identity"],
            exchange=raw["exchange"],
            segment=raw["segment"],
            provider_instrument_type=raw["provider_instrument_type"],
            tick_size=Decimal(raw["tick_size"]),
            lot_size=raw["lot_size"],
            contract_expiry=date.fromisoformat(raw["contract_expiry"]),
            observation_boundary=datetime.fromisoformat(raw["observation_boundary"]),
            expiry_eligibility_boundary=datetime.fromisoformat(
                raw["expiry_eligibility_boundary"]
            ),
            domain008_session_identity=raw["domain008_session_identity"],
            domain008_contract_identity=raw["domain008_contract_identity"],
            domain008_contract_version=raw["domain008_contract_version"],
            domain008_publication_identity=raw["domain008_publication_identity"],
            domain008_publication_version=raw["domain008_publication_version"],
            domain008_publication_sha256=raw["domain008_publication_sha256"],
            selection_rule_identity=raw["selection_rule_identity"],
            selection_rule_version=raw["selection_rule_version"],
            provider_snapshot_identity=raw["provider_snapshot_identity"],
            provider_snapshot_integrity_identity=raw[
                "provider_snapshot_integrity_identity"
            ],
            provider_mapping_directive_identity=raw[
                "provider_mapping_directive_identity"
            ],
            catalogue_identity=raw["catalogue_identity"],
            catalogue_version=raw["catalogue_version"],
            catalogue_integrity_identity=raw["catalogue_integrity_identity"],
            active_binding=binding,
            provenance=tuple(raw["provenance"]),
            integrity_identity=raw["integrity_identity"],
        )
    except Exception as error:
        if isinstance(error, ActiveDerivativeSelectionError):
            raise
        raise ActiveDerivativeSelectionError(
            ActiveDerivativeSelectionFailure.INTEGRITY_INVALID
        ) from error
    if active_derivative_binding_bytes(value) != encoded:
        raise ActiveDerivativeSelectionError(
            ActiveDerivativeSelectionFailure.INTEGRITY_INVALID
        )
    return value


def _create_binding_artifact(
    *,
    analytical_subject: str,
    canonical_subject_id: str,
    provider_contract_family: str,
    record: ProviderInstrumentRecord,
    contract: DerivativeContractV2,
    directive: ProviderMappingDirectiveV2,
    profile: McxContractFamilySessionProfile,
    observation_boundary: datetime,
    catalogue: InstrumentSemanticPublicationV2,
    snapshot: ProviderInstrumentSnapshot,
    previous_binding: ActiveDerivativeBindingArtifact | None,
) -> ActiveDerivativeBindingArtifact:
    if profile.continuous_trading is None or not profile.contract_eligible:
        raise ActiveDerivativeSelectionError(
            ActiveDerivativeSelectionFailure.DOMAIN008_SESSION_UNAVAILABLE
        )
    identity_values = {
        "subject": canonical_subject_id,
        "contract": contract.canonical_id,
        "expiry": contract.expiry,
        "provider_record": record.provider_record_identity,
        "provider_symbol": record.trading_symbol,
        "observation_boundary": observation_boundary,
        "eligibility_boundary": profile.expiry_eligibility_boundary,
        "selection_rule": ACTIVE_DERIVATIVE_SELECTION_RULE_IDENTITY,
        "selection_version": ACTIVE_DERIVATIVE_SELECTION_RULE_VERSION,
        "domain008": _profile_identity(profile),
        "catalogue": catalogue.integrity_identity,
        "provider_snapshot": snapshot.integrity_identity,
    }
    binding = create_active_derivative_binding(
        binding_identity=_identity("ACTIVE-DERIVATIVE-BINDING", identity_values),
        binding_version=ACTIVE_DERIVATIVE_CONTRACT_BINDING_V1_VERSION,
        subject_id=canonical_subject_id,
        derivative_contract_id=contract.canonical_id,
        effective_from=observation_boundary,
        effective_through=profile.expiry_eligibility_boundary,
        contract_expiry=contract.expiry,
        provider_reference_identity=directive.directive_identity,
        source_identity=snapshot.snapshot_identity,
        provenance=(
            "ADR-0017",
            ACTIVE_DERIVATIVE_SELECTION_RULE_IDENTITY,
            _profile_identity(profile),
            catalogue.integrity_identity,
            record.provider_record_identity,
        ),
        supersedes=(
            None
            if previous_binding is None
            or previous_binding.binding_identity
            == _identity("ACTIVE-DERIVATIVE-BINDING", identity_values)
            else previous_binding.binding_identity
        ),
    )
    publication = profile.publication_identity
    values = {
        "artifact_identity": ACTIVE_DERIVATIVE_BINDING_ARTIFACT_IDENTITY,
        "artifact_version": ACTIVE_DERIVATIVE_BINDING_ARTIFACT_VERSION,
        "analytical_subject": analytical_subject,
        "canonical_subject_id": canonical_subject_id,
        "provider_contract_family": provider_contract_family,
        "provider_symbol": record.trading_symbol,
        "provider_record_identity": record.provider_record_identity,
        "exchange": record.exchange,
        "segment": record.segment,
        "provider_instrument_type": record.instrument_type,
        "tick_size": record.tick_size,
        "lot_size": record.lot_size,
        "contract_expiry": contract.expiry,
        "observation_boundary": observation_boundary,
        "expiry_eligibility_boundary": profile.expiry_eligibility_boundary,
        "domain008_session_identity": profile.continuous_trading.session_identity,
        "domain008_contract_identity": profile.contract_identity,
        "domain008_contract_version": profile.contract_version,
        "domain008_publication_identity": publication,
        "domain008_publication_version": profile.publication_version,
        "domain008_publication_sha256": profile.publication_sha256,
        "selection_rule_identity": ACTIVE_DERIVATIVE_SELECTION_RULE_IDENTITY,
        "selection_rule_version": ACTIVE_DERIVATIVE_SELECTION_RULE_VERSION,
        "provider_snapshot_identity": snapshot.snapshot_identity,
        "provider_snapshot_integrity_identity": snapshot.integrity_identity,
        "provider_mapping_directive_identity": directive.directive_identity,
        "catalogue_identity": catalogue.publication_identity,
        "catalogue_version": catalogue.publication_version,
        "catalogue_integrity_identity": catalogue.integrity_identity,
        "active_binding": binding,
        "provenance": (
            "ADR-0017",
            "KRONOS-INTRADAY-WO-06MCX-R",
            "Active derivative binding is not execution eligibility",
        ),
    }
    provisional = ActiveDerivativeBindingArtifact(
        **values,
        integrity_identity=_identity(
            "ACTIVE-DERIVATIVE-BINDING-ARTIFACT",
            _artifact_payload_from_values(values),
        ),
    )
    return provisional


def _artifact_payload_from_values(values: dict[str, object]) -> dict[str, object]:
    artifact = values["active_binding"]
    assert type(artifact) is ActiveDerivativeContractBinding
    return {
        **values,
        "active_binding": _binding_payload(artifact),
    }


def _binding_payload(value: ActiveDerivativeContractBinding) -> dict[str, object]:
    return {
        "contract_identity": value.contract_identity,
        "binding_identity": value.binding_identity,
        "binding_version": value.binding_version,
        "subject_id": value.subject_id,
        "derivative_contract_id": value.derivative_contract_id,
        "effective_from": value.effective_from,
        "effective_through": value.effective_through,
        "contract_expiry": value.contract_expiry,
        "provider_reference_identity": value.provider_reference_identity,
        "source_identity": value.source_identity,
        "provenance": value.provenance,
        "supersedes": value.supersedes,
        "integrity_identity": value.integrity_identity,
    }


def _profile_identity(value: McxContractFamilySessionProfile) -> str:
    return _identity("MCX-CONTRACT-SESSION-PROFILE", {
        "requested_family": value.requested_contract_family,
        "contract_family": value.contract_family,
        "trading_date": value.trading_date,
        "contract_expiry": value.contract_expiry,
        "classification": value.classification.value,
        "session": (
            None
            if value.continuous_trading is None
            else value.continuous_trading.session_identity
        ),
        "eligibility_boundary": value.expiry_eligibility_boundary,
        "eligible": value.contract_eligible,
        "publication": value.publication_identity,
        "publication_version": value.publication_version,
        "publication_sha256": value.publication_sha256,
        "contract_identity": value.contract_identity,
        "contract_version": value.contract_version,
    })


def _unavailable_outcome(
    analytical_subject: str,
    canonical_subject_id: str,
    provider_contract_family: str,
    failure: ActiveDerivativeSelectionFailure,
) -> ActiveDerivativeSelectionOutcome:
    return ActiveDerivativeSelectionOutcome(
        analytical_subject=analytical_subject,
        canonical_subject_id=canonical_subject_id,
        provider_contract_family=provider_contract_family,
        accounting=ActiveDerivativeCandidateAccounting(0, 0, 0, 0, 0),
        binding=None,
        failure=failure,
    )


def _identity(prefix: str, value: object) -> str:
    return f"{prefix}-{sha256(_encode(value).rstrip()).hexdigest()}"


def _encode(value: object) -> bytes:
    return (json.dumps(
        value,
        default=lambda item: item.isoformat()
        if isinstance(item, (date, datetime))
        else list(item)
        if isinstance(item, tuple)
        else str(item),
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n").encode("ascii")


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


def _texts(values: object) -> bool:
    return type(values) is tuple and bool(values) and all(_text(item) for item in values)


__all__ = [
    "ACTIVE_DERIVATIVE_BINDING_ARTIFACT_IDENTITY",
    "ACTIVE_DERIVATIVE_BINDING_ARTIFACT_VERSION",
    "ACTIVE_DERIVATIVE_CATALOGUE_VERSION",
    "ACTIVE_DERIVATIVE_FAMILY_MAPPINGS",
    "ACTIVE_DERIVATIVE_SELECTION_RULE_IDENTITY",
    "ACTIVE_DERIVATIVE_SELECTION_RULE_VERSION",
    "ActiveDerivativeBindingArtifact",
    "ActiveDerivativeCandidateAccounting",
    "ActiveDerivativeResolutionSet",
    "ActiveDerivativeSelectionError",
    "ActiveDerivativeSelectionFailure",
    "ActiveDerivativeSelectionOutcome",
    "GovernedActiveDerivativeResolver",
    "active_derivative_binding_bytes",
    "active_derivative_binding_payload",
    "create_mcx_contract_catalogue_successor",
    "parse_active_derivative_binding",
]
