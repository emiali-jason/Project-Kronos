"""Token-free P1 commissioning audit over a governed Provider snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json

from kronos.intraday.universe import (
    EXPECTED_NATIVE_MEMBER_COUNT,
    INTRADAY_NATIVE_UNIVERSE_IDENTITY,
    IntradayMarketFamily,
    IntradayUniversePublication,
)
from kronos.provider.instrument_master import (
    ProviderInstrumentRecord,
    ProviderInstrumentSnapshot,
)


INTRADAY_PROVIDER_COMMISSIONING_SCHEMA = (
    "KRONOS-INTRADAY-PROVIDER-COMMISSIONING-MANIFEST-V1"
)
INTRADAY_PROVIDER_COMMISSIONING_VERSION = "1.0.0"


class CommissioningResolutionStatus(StrEnum):
    UNIQUE_PROVIDER_RECORD = "UNIQUE_PROVIDER_RECORD"
    MULTIPLE_PROVIDER_RECORDS = "MULTIPLE_PROVIDER_RECORDS"
    NO_PROVIDER_RECORD = "NO_PROVIDER_RECORD"
    PROVIDER_INDEX_RECORD_CANDIDATE = "PROVIDER_INDEX_RECORD_CANDIDATE"
    PERSISTENT_SUBJECT_REQUIRES_DOMAIN_001_INTERPRETATION = (
        "PERSISTENT_SUBJECT_REQUIRES_DOMAIN_001_INTERPRETATION"
    )
    MULTIPLE_PROVIDER_CONTRACT_RECORDS = "MULTIPLE_PROVIDER_CONTRACT_RECORDS"


@dataclass(frozen=True, slots=True)
class CommissioningProviderRecordReference:
    """A token-free reference to one immutable Provider factual record."""

    provider_record_identity: str
    provider_symbol: str
    exchange: str
    segment: str
    provider_instrument_type: str
    expiry: date | None
    strike: Decimal | None
    tick_size: Decimal
    lot_size: int

    def __post_init__(self) -> None:
        if (
            not all(_text(item) for item in (
                self.provider_record_identity,
                self.provider_symbol,
                self.exchange,
                self.segment,
            ))
            or not isinstance(self.provider_instrument_type, str)
            or type(self.lot_size) is not int
            or self.lot_size < 0
        ):
            raise ValueError("COMMISSIONING_PROVIDER_REFERENCE_INVALID")


@dataclass(frozen=True, slots=True)
class IntradayProviderCommissioningMember:
    sponsor_label: str
    universe_membership_identity: str
    market_family: IntradayMarketFamily
    candidate_records: tuple[CommissioningProviderRecordReference, ...]
    status: CommissioningResolutionStatus
    domain_001_interpretation_required: bool
    canonical_identity_established: bool = False
    execution_eligibility_established: bool = False
    active_contract_selected: bool = False

    def __post_init__(self) -> None:
        record_ids = tuple(item.provider_record_identity for item in self.candidate_records)
        if (
            not _text(self.sponsor_label)
            or not _text(self.universe_membership_identity)
            or type(self.market_family) is not IntradayMarketFamily
            or any(type(item) is not CommissioningProviderRecordReference for item in self.candidate_records)
            or len(record_ids) != len(set(record_ids))
            or type(self.status) is not CommissioningResolutionStatus
            or type(self.domain_001_interpretation_required) is not bool
            or self.canonical_identity_established
            or self.execution_eligibility_established
            or self.active_contract_selected
            or (self.status is CommissioningResolutionStatus.NO_PROVIDER_RECORD) != (not self.candidate_records)
        ):
            raise ValueError("INTRADAY_COMMISSIONING_MEMBER_INVALID")


@dataclass(frozen=True, slots=True)
class IntradayProviderCommissioningManifest:
    manifest_identity: str
    manifest_version: str
    provider_snapshot_identity: str
    provider_snapshot_integrity_identity: str
    intraday_universe_identity: str
    intraday_universe_version: str
    intraday_universe_integrity_identity: str
    members: tuple[IntradayProviderCommissioningMember, ...]
    integrity_identity: str
    canonical_identity_authority: bool = False
    execution_eligibility_authority: bool = False
    active_contract_selection_authority: bool = False
    schema_identity: str = INTRADAY_PROVIDER_COMMISSIONING_SCHEMA

    def __post_init__(self) -> None:
        labels = tuple(item.sponsor_label for item in self.members)
        expected = _manifest_document(self, include_integrity=False)
        if (
            self.schema_identity != INTRADAY_PROVIDER_COMMISSIONING_SCHEMA
            or self.manifest_version != INTRADAY_PROVIDER_COMMISSIONING_VERSION
            or self.intraday_universe_identity != INTRADAY_NATIVE_UNIVERSE_IDENTITY
            or len(self.members) != EXPECTED_NATIVE_MEMBER_COUNT
            or len(labels) != len(set(labels))
            or any(type(item) is not IntradayProviderCommissioningMember for item in self.members)
            or self.canonical_identity_authority
            or self.execution_eligibility_authority
            or self.active_contract_selection_authority
            or self.manifest_identity != _identity("INTRADAY-PROVIDER-COMMISSIONING", _manifest_identity_fields(self))
            or self.integrity_identity != _identity("INTRADAY-PROVIDER-COMMISSIONING-INTEGRITY", expected)
        ):
            raise ValueError("INTRADAY_PROVIDER_COMMISSIONING_MANIFEST_INVALID")


def create_intraday_provider_commissioning_manifest(
    *,
    snapshot: ProviderInstrumentSnapshot,
    universe: IntradayUniversePublication,
) -> IntradayProviderCommissioningManifest:
    if (
        type(snapshot) is not ProviderInstrumentSnapshot
        or type(universe) is not IntradayUniversePublication
    ):
        raise ValueError("INTRADAY_PROVIDER_COMMISSIONING_INPUT_INVALID")
    members = tuple(
        _commission_member(member, snapshot.records) for member in universe.members
    )
    identity_values = {
        "schema_identity": INTRADAY_PROVIDER_COMMISSIONING_SCHEMA,
        "manifest_version": INTRADAY_PROVIDER_COMMISSIONING_VERSION,
        "provider_snapshot_identity": snapshot.snapshot_identity,
        "provider_snapshot_integrity_identity": snapshot.integrity_identity,
        "intraday_universe_identity": universe.publication_identity,
        "intraday_universe_version": universe.publication_version,
        "intraday_universe_integrity_identity": universe.integrity_identity,
        "members": [_member_document(item) for item in members],
        "canonical_identity_authority": False,
        "execution_eligibility_authority": False,
        "active_contract_selection_authority": False,
    }
    manifest_identity = _identity("INTRADAY-PROVIDER-COMMISSIONING", identity_values)
    integrity_values = {**identity_values, "manifest_identity": manifest_identity}
    return IntradayProviderCommissioningManifest(
        manifest_identity=manifest_identity,
        manifest_version=INTRADAY_PROVIDER_COMMISSIONING_VERSION,
        provider_snapshot_identity=snapshot.snapshot_identity,
        provider_snapshot_integrity_identity=snapshot.integrity_identity,
        intraday_universe_identity=universe.publication_identity,
        intraday_universe_version=universe.publication_version,
        intraday_universe_integrity_identity=universe.integrity_identity,
        members=members,
        integrity_identity=_identity(
            "INTRADAY-PROVIDER-COMMISSIONING-INTEGRITY", integrity_values
        ),
    )


def _commission_member(member: object, records: tuple[ProviderInstrumentRecord, ...]) -> IntradayProviderCommissioningMember:
    label = member.sponsor_label  # type: ignore[attr-defined]
    family = member.market_family  # type: ignore[attr-defined]
    candidates = tuple(item for item in records if _candidate(item, label, family))
    references = tuple(_reference(item) for item in candidates)
    if not references:
        status = CommissioningResolutionStatus.NO_PROVIDER_RECORD
    elif family is IntradayMarketFamily.NSE_INDEX:
        status = CommissioningResolutionStatus.PROVIDER_INDEX_RECORD_CANDIDATE
    elif family is IntradayMarketFamily.MCX and len(references) > 1:
        status = CommissioningResolutionStatus.MULTIPLE_PROVIDER_CONTRACT_RECORDS
    elif family is IntradayMarketFamily.MCX:
        status = CommissioningResolutionStatus.PERSISTENT_SUBJECT_REQUIRES_DOMAIN_001_INTERPRETATION
    elif len(references) == 1:
        status = CommissioningResolutionStatus.UNIQUE_PROVIDER_RECORD
    else:
        status = CommissioningResolutionStatus.MULTIPLE_PROVIDER_RECORDS
    return IntradayProviderCommissioningMember(
        sponsor_label=label,
        universe_membership_identity=member.membership_identity,  # type: ignore[attr-defined]
        market_family=family,
        candidate_records=references,
        status=status,
        domain_001_interpretation_required=family is not IntradayMarketFamily.NSE_EQUITY,
    )


def _candidate(record: ProviderInstrumentRecord, label: str, family: IntradayMarketFamily) -> bool:
    if family is IntradayMarketFamily.NSE_EQUITY:
        symbol = "BAJAJ-AUTO" if label == "BAJAJ_AUTO" else label
        return (
            record.exchange == "NSE"
            and record.segment == "NSE"
            and record.instrument_type == "EQ"
            and record.trading_symbol == symbol
        )
    if family is IntradayMarketFamily.NSE_INDEX:
        symbol = {"NIFTY": "NIFTY 50", "BANKNIFTY": "NIFTY BANK"}[label]
        return (
            record.exchange == "NSE"
            and record.segment == "INDICES"
            and record.trading_symbol == symbol
        )
    return (
        record.exchange == "MCX"
        and record.segment == "MCX-FUT"
        and record.instrument_type == "FUT"
        and record.name == label
    )


def _reference(record: ProviderInstrumentRecord) -> CommissioningProviderRecordReference:
    return CommissioningProviderRecordReference(
        provider_record_identity=record.provider_record_identity,
        provider_symbol=record.trading_symbol,
        exchange=record.exchange,
        segment=record.segment,
        provider_instrument_type=record.instrument_type,
        expiry=record.expiry,
        strike=record.strike,
        tick_size=record.tick_size,
        lot_size=record.lot_size,
    )


def _manifest_identity_fields(manifest: IntradayProviderCommissioningManifest) -> dict[str, object]:
    return {
        "schema_identity": manifest.schema_identity,
        "manifest_version": manifest.manifest_version,
        "provider_snapshot_identity": manifest.provider_snapshot_identity,
        "provider_snapshot_integrity_identity": manifest.provider_snapshot_integrity_identity,
        "intraday_universe_identity": manifest.intraday_universe_identity,
        "intraday_universe_version": manifest.intraday_universe_version,
        "intraday_universe_integrity_identity": manifest.intraday_universe_integrity_identity,
        "members": [_member_document(item) for item in manifest.members],
        "canonical_identity_authority": manifest.canonical_identity_authority,
        "execution_eligibility_authority": manifest.execution_eligibility_authority,
        "active_contract_selection_authority": manifest.active_contract_selection_authority,
    }


def _manifest_document(manifest: IntradayProviderCommissioningManifest, *, include_integrity: bool) -> dict[str, object]:
    document = {
        **_manifest_identity_fields(manifest),
        "manifest_identity": manifest.manifest_identity,
    }
    if include_integrity:
        document["integrity_identity"] = manifest.integrity_identity
    return document


def _member_document(member: IntradayProviderCommissioningMember) -> dict[str, object]:
    return {
        "sponsor_label": member.sponsor_label,
        "universe_membership_identity": member.universe_membership_identity,
        "market_family": member.market_family.value,
        "candidate_records": [_reference_document(item) for item in member.candidate_records],
        "status": member.status.value,
        "domain_001_interpretation_required": member.domain_001_interpretation_required,
        "canonical_identity_established": member.canonical_identity_established,
        "execution_eligibility_established": member.execution_eligibility_established,
        "active_contract_selected": member.active_contract_selected,
    }


def _reference_document(reference: CommissioningProviderRecordReference) -> dict[str, object]:
    return {
        "provider_record_identity": reference.provider_record_identity,
        "provider_symbol": reference.provider_symbol,
        "exchange": reference.exchange,
        "segment": reference.segment,
        "provider_instrument_type": reference.provider_instrument_type,
        "expiry": None if reference.expiry is None else reference.expiry.isoformat(),
        "strike": None if reference.strike is None else format(reference.strike, "f"),
        "tick_size": format(reference.tick_size, "f"),
        "lot_size": reference.lot_size,
    }


def _identity(prefix: str, document: dict[str, object]) -> str:
    digest = sha256(json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return f"{prefix}-{digest}"


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


__all__ = [
    "CommissioningProviderRecordReference",
    "CommissioningResolutionStatus",
    "INTRADAY_PROVIDER_COMMISSIONING_SCHEMA",
    "INTRADAY_PROVIDER_COMMISSIONING_VERSION",
    "IntradayProviderCommissioningManifest",
    "IntradayProviderCommissioningMember",
    "create_intraday_provider_commissioning_manifest",
]
