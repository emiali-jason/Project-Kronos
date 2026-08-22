"""Governed Intraday Native universe publication and runtime resolution.

This module owns analytical membership only.  It deliberately contains no
execution eligibility, trading state, risk decision, or broker identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import json
from pathlib import Path
import re

from kronos.instrument.runtime import (
    ExecutionContextAvailability,
    InstrumentFreshness,
    ProviderBindingStatus,
    RuntimeInstrument,
    RuntimeInstrumentRegistry,
)


INTRADAY_NATIVE_UNIVERSE_SCHEMA = "KRONOS-INTRADAY-NATIVE-UNIVERSE-V1"
INTRADAY_NATIVE_UNIVERSE_IDENTITY = "KRONOS-INTRADAY-NATIVE-UNIVERSE-V1"
INTRADAY_PRODUCT_IDENTITY = "INTRADAY"
INTRADAY_NATIVE_UNIVERSE_VERSION = "1.0.0"
EXPECTED_NATIVE_MEMBER_COUNT = 98
DEFAULT_INTRADAY_NATIVE_UNIVERSE_PATH = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "intraday"
    / INTRADAY_NATIVE_UNIVERSE_IDENTITY
    / f"{INTRADAY_NATIVE_UNIVERSE_VERSION}.json"
)

_LABEL = re.compile(r"[A-Z0-9_&-]+\Z")


class IntradayMarketFamily(StrEnum):
    NSE_EQUITY = "NSE_EQUITY"
    NSE_INDEX = "NSE_INDEX"
    MCX = "MCX"


class IntradayUniverseRole(StrEnum):
    NATIVE = "NATIVE"


class IntradayMembershipStatus(StrEnum):
    GOVERNED_TARGET = "GOVERNED_TARGET"


class CanonicalResolutionState(StrEnum):
    CANONICAL_READY = "CANONICAL_READY"
    CANONICAL_BINDING_UNAVAILABLE = "CANONICAL_BINDING_UNAVAILABLE"
    CANONICAL_STALE = "CANONICAL_STALE"
    RUNTIME_INSTRUMENT_UNAVAILABLE = "RUNTIME_INSTRUMENT_UNAVAILABLE"
    PROVIDER_BINDING_UNAVAILABLE = "PROVIDER_BINDING_UNAVAILABLE"


class IntradayUniverseFailure(StrEnum):
    PUBLICATION_UNAVAILABLE = "PUBLICATION_UNAVAILABLE"
    PUBLICATION_INVALID = "PUBLICATION_INVALID"
    INTEGRITY_MISMATCH = "INTEGRITY_MISMATCH"
    PUBLICATION_STALE = "PUBLICATION_STALE"
    VERSION_CONFLICT = "VERSION_CONFLICT"


class IntradayUniverseError(RuntimeError):
    def __init__(self, failure: IntradayUniverseFailure) -> None:
        self.failure = failure
        super().__init__(failure.value)


@dataclass(frozen=True, slots=True)
class IntradayUniverseMember:
    sponsor_label: str
    canonical_instrument_id: str | None
    market_family: IntradayMarketFamily
    role: IntradayUniverseRole
    membership_status: IntradayMembershipStatus
    valid_from: datetime
    valid_through: datetime
    source_identity: str
    provenance: tuple[str, ...]
    membership_identity: str

    def __post_init__(self) -> None:
        fields = _member_fields(self)
        if (
            type(self.sponsor_label) is not str
            or _LABEL.fullmatch(self.sponsor_label) is None
            or (
                self.canonical_instrument_id is not None
                and (
                    type(self.canonical_instrument_id) is not str
                    or not self.canonical_instrument_id
                )
            )
            or type(self.market_family) is not IntradayMarketFamily
            or self.role is not IntradayUniverseRole.NATIVE
            or self.membership_status is not IntradayMembershipStatus.GOVERNED_TARGET
            or not _aware(self.valid_from)
            or not _aware(self.valid_through)
            or self.valid_through < self.valid_from
            or not _text(self.source_identity)
            or not _texts(self.provenance)
            or self.membership_identity != _identity("INTRADAY-NATIVE-MEMBER", fields)
        ):
            raise IntradayUniverseError(IntradayUniverseFailure.PUBLICATION_INVALID)


@dataclass(frozen=True, slots=True)
class IntradayUniversePublication:
    publication_identity: str
    publication_version: str
    product_identity: str
    valid_from: datetime
    valid_through: datetime
    source_boundary: datetime
    supersedes: str | None
    source_identities: tuple[str, ...]
    provenance: tuple[str, ...]
    members: tuple[IntradayUniverseMember, ...]
    integrity_identity: str
    schema_identity: str = INTRADAY_NATIVE_UNIVERSE_SCHEMA

    def __post_init__(self) -> None:
        labels = tuple(item.sponsor_label for item in self.members)
        canonicals = tuple(
            item.canonical_instrument_id
            for item in self.members
            if item.canonical_instrument_id is not None
        )
        if (
            self.schema_identity != INTRADAY_NATIVE_UNIVERSE_SCHEMA
            or self.publication_identity != INTRADAY_NATIVE_UNIVERSE_IDENTITY
            or not _version(self.publication_version)
            or self.product_identity != INTRADAY_PRODUCT_IDENTITY
            or not _aware(self.valid_from)
            or not _aware(self.valid_through)
            or not _aware(self.source_boundary)
            or self.valid_through < self.valid_from
            or self.source_boundary > self.valid_from
            or (self.supersedes is not None and not _text(self.supersedes))
            or not _texts(self.source_identities)
            or not _texts(self.provenance)
            or len(self.members) != EXPECTED_NATIVE_MEMBER_COUNT
            or any(type(item) is not IntradayUniverseMember for item in self.members)
            or len(set(labels)) != len(labels)
            or len(set(canonicals)) != len(canonicals)
            or not self.integrity_identity.startswith("INTRADAY-NATIVE-UNIVERSE-")
        ):
            raise IntradayUniverseError(IntradayUniverseFailure.PUBLICATION_INVALID)

    def require_current(self, observed_at: datetime) -> None:
        if not _aware(observed_at) or not self.valid_from <= observed_at <= self.valid_through:
            raise IntradayUniverseError(IntradayUniverseFailure.PUBLICATION_STALE)

    def contains(self, sponsor_label: str) -> bool:
        return any(item.sponsor_label == sponsor_label for item in self.members)


@dataclass(frozen=True, slots=True)
class IntradayUniverseMemberResolution:
    membership_identity: str
    sponsor_label: str
    canonical_instrument_id: str | None
    canonical_resolution_state: CanonicalResolutionState
    runtime_instrument: RuntimeInstrument | None
    runtime_instrument_available: bool
    provider_binding_available: bool
    runtime_consumable: bool
    market_family: IntradayMarketFamily
    unavailable_reason: str | None

    def __post_init__(self) -> None:
        if (
            not _text(self.membership_identity)
            or not _text(self.sponsor_label)
            or type(self.canonical_resolution_state) is not CanonicalResolutionState
            or (
                self.runtime_instrument is not None
                and type(self.runtime_instrument) is not RuntimeInstrument
            )
            or self.runtime_instrument_available != (self.runtime_instrument is not None)
            or type(self.provider_binding_available) is not bool
            or type(self.runtime_consumable) is not bool
            or type(self.market_family) is not IntradayMarketFamily
            or (self.runtime_consumable and self.unavailable_reason is not None)
            or (not self.runtime_consumable and not _text(self.unavailable_reason))
        ):
            raise ValueError("INTRADAY_UNIVERSE_RESOLUTION_INVALID")


@dataclass(frozen=True, slots=True)
class IntradayUniverseResolution:
    publication_identity: str
    publication_version: str
    observed_at: datetime
    members: tuple[IntradayUniverseMemberResolution, ...]

    def __post_init__(self) -> None:
        identities = tuple(item.membership_identity for item in self.members)
        if (
            self.publication_identity != INTRADAY_NATIVE_UNIVERSE_IDENTITY
            or not _version(self.publication_version)
            or not _aware(self.observed_at)
            or len(self.members) != EXPECTED_NATIVE_MEMBER_COUNT
            or any(type(item) is not IntradayUniverseMemberResolution for item in self.members)
            or len(set(identities)) != len(identities)
        ):
            raise ValueError("INTRADAY_UNIVERSE_RESOLUTION_INVALID")

    def lookup(self, sponsor_label: str) -> IntradayUniverseMemberResolution:
        for item in self.members:
            if item.sponsor_label == sponsor_label:
                return item
        raise ValueError("INTRADAY_NATIVE_MEMBER_UNAVAILABLE")


def resolve_intraday_universe(
    *,
    publication: IntradayUniversePublication,
    runtime_registry: RuntimeInstrumentRegistry,
    observed_at: datetime,
) -> IntradayUniverseResolution:
    """Resolve only governed members; registry-only identities cannot enter."""

    if (
        type(publication) is not IntradayUniversePublication
        or type(runtime_registry) is not RuntimeInstrumentRegistry
    ):
        raise ValueError("INTRADAY_UNIVERSE_RESOLUTION_INPUT_INVALID")
    publication.require_current(observed_at)
    return IntradayUniverseResolution(
        publication_identity=publication.publication_identity,
        publication_version=publication.publication_version,
        observed_at=observed_at,
        members=tuple(
            _resolve_member(member, runtime_registry) for member in publication.members
        ),
    )


def seal_intraday_universe_document(document: dict[str, object]) -> bytes:
    core = _source_document(document)
    members: list[dict[str, object]] = []
    for raw in core["members"]:
        assert type(raw) is dict
        item = dict(raw)
        item["membership_identity"] = _identity("INTRADAY-NATIVE-MEMBER", item)
        members.append(item)
    sealed = {**core, "members": members}
    sealed["integrity_identity"] = _identity("INTRADAY-NATIVE-UNIVERSE", sealed)
    return _encode(sealed)


def parse_intraday_universe_publication(encoded: bytes) -> IntradayUniversePublication:
    try:
        document = json.loads(encoded)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as error:
        raise IntradayUniverseError(IntradayUniverseFailure.PUBLICATION_INVALID) from error
    if type(document) is not dict or type(document.get("integrity_identity")) is not str:
        raise IntradayUniverseError(IntradayUniverseFailure.PUBLICATION_INVALID)
    supplied = document["integrity_identity"]
    core = {key: value for key, value in document.items() if key != "integrity_identity"}
    if supplied != _identity("INTRADAY-NATIVE-UNIVERSE", core):
        raise IntradayUniverseError(IntradayUniverseFailure.INTEGRITY_MISMATCH)
    try:
        members = tuple(_parse_member(item) for item in core["members"])
        return IntradayUniversePublication(
            schema_identity=core["schema_identity"],
            publication_identity=core["publication_identity"],
            publication_version=core["publication_version"],
            product_identity=core["product_identity"],
            valid_from=_datetime(core["valid_from"]),
            valid_through=_datetime(core["valid_through"]),
            source_boundary=_datetime(core["source_boundary"]),
            supersedes=core["supersedes"],
            source_identities=_strings(core["source_identities"]),
            provenance=_strings(core["provenance"]),
            members=members,
            integrity_identity=supplied,
        )
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, IntradayUniverseError):
            raise
        raise IntradayUniverseError(IntradayUniverseFailure.PUBLICATION_INVALID) from error


def load_intraday_universe_publication(
    path: Path = DEFAULT_INTRADAY_NATIVE_UNIVERSE_PATH,
) -> IntradayUniversePublication:
    path = Path(path)
    if not path.is_absolute():
        raise IntradayUniverseError(IntradayUniverseFailure.PUBLICATION_INVALID)
    try:
        encoded = path.read_bytes()
    except OSError as error:
        raise IntradayUniverseError(IntradayUniverseFailure.PUBLICATION_UNAVAILABLE) from error
    return parse_intraday_universe_publication(encoded)


def _resolve_member(
    member: IntradayUniverseMember,
    registry: RuntimeInstrumentRegistry,
) -> IntradayUniverseMemberResolution:
    canonical_id = member.canonical_instrument_id
    if canonical_id is None:
        return _unavailable(member, CanonicalResolutionState.CANONICAL_BINDING_UNAVAILABLE)
    try:
        runtime = registry.lookup(canonical_id)
    except ValueError:
        return _unavailable(member, CanonicalResolutionState.RUNTIME_INSTRUMENT_UNAVAILABLE)
    provider_available = runtime.binding_status is ProviderBindingStatus.BOUND
    consumable = runtime.execution_context is ExecutionContextAvailability.COMPLETE
    if runtime.canonical_freshness is InstrumentFreshness.STALE:
        state = CanonicalResolutionState.CANONICAL_STALE
    elif not provider_available:
        state = CanonicalResolutionState.PROVIDER_BINDING_UNAVAILABLE
    else:
        state = CanonicalResolutionState.CANONICAL_READY
    return IntradayUniverseMemberResolution(
        membership_identity=member.membership_identity,
        sponsor_label=member.sponsor_label,
        canonical_instrument_id=canonical_id,
        canonical_resolution_state=state,
        runtime_instrument=runtime,
        runtime_instrument_available=True,
        provider_binding_available=provider_available,
        runtime_consumable=consumable,
        market_family=member.market_family,
        unavailable_reason=None if consumable else state.value,
    )


def _unavailable(
    member: IntradayUniverseMember,
    state: CanonicalResolutionState,
) -> IntradayUniverseMemberResolution:
    return IntradayUniverseMemberResolution(
        membership_identity=member.membership_identity,
        sponsor_label=member.sponsor_label,
        canonical_instrument_id=member.canonical_instrument_id,
        canonical_resolution_state=state,
        runtime_instrument=None,
        runtime_instrument_available=False,
        provider_binding_available=False,
        runtime_consumable=False,
        market_family=member.market_family,
        unavailable_reason=state.value,
    )


def _source_document(document: dict[str, object]) -> dict[str, object]:
    required = {
        "schema_identity", "publication_identity", "publication_version",
        "product_identity", "valid_from", "valid_through", "source_boundary",
        "supersedes", "source_identities", "provenance", "members",
    }
    if (
        type(document) is not dict
        or set(document) != required
        or document["schema_identity"] != INTRADAY_NATIVE_UNIVERSE_SCHEMA
        or document["publication_identity"] != INTRADAY_NATIVE_UNIVERSE_IDENTITY
        or document["product_identity"] != INTRADAY_PRODUCT_IDENTITY
        or type(document["members"]) is not list
    ):
        raise IntradayUniverseError(IntradayUniverseFailure.PUBLICATION_INVALID)
    return dict(document)


def _parse_member(value: object) -> IntradayUniverseMember:
    required = {
        "sponsor_label", "canonical_instrument_id", "market_family", "role",
        "membership_status", "valid_from", "valid_through", "source_identity",
        "provenance", "membership_identity",
    }
    if type(value) is not dict or set(value) != required:
        raise IntradayUniverseError(IntradayUniverseFailure.PUBLICATION_INVALID)
    return IntradayUniverseMember(
        sponsor_label=value["sponsor_label"],
        canonical_instrument_id=value["canonical_instrument_id"],
        market_family=IntradayMarketFamily(value["market_family"]),
        role=IntradayUniverseRole(value["role"]),
        membership_status=IntradayMembershipStatus(value["membership_status"]),
        valid_from=_datetime(value["valid_from"]),
        valid_through=_datetime(value["valid_through"]),
        source_identity=value["source_identity"],
        provenance=_strings(value["provenance"]),
        membership_identity=value["membership_identity"],
    )


def _member_fields(value: IntradayUniverseMember) -> dict[str, object]:
    return {
        "sponsor_label": value.sponsor_label,
        "canonical_instrument_id": value.canonical_instrument_id,
        "market_family": value.market_family.value,
        "role": value.role.value,
        "membership_status": value.membership_status.value,
        "valid_from": value.valid_from.isoformat(),
        "valid_through": value.valid_through.isoformat(),
        "source_identity": value.source_identity,
        "provenance": list(value.provenance),
    }


def _identity(prefix: str, payload: object) -> str:
    return f"{prefix}-{sha256(_canonical(payload)).hexdigest()}"


def _canonical(payload: object) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _encode(payload: object) -> bytes:
    return (json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode()


def _datetime(value: object) -> datetime:
    if type(value) is not str:
        raise ValueError
    return datetime.fromisoformat(value)


def _strings(value: object) -> tuple[str, ...]:
    if type(value) is not list or not value:
        raise ValueError
    values = tuple(value)
    if not _texts(values):
        raise ValueError
    return values


def _text(value: object) -> bool:
    return type(value) is str and bool(value.strip())


def _texts(values: object) -> bool:
    return type(values) is tuple and bool(values) and all(_text(value) for value in values)


def _aware(value: object) -> bool:
    return type(value) is datetime and value.tzinfo is not None and value.utcoffset() is not None


def _version(value: object) -> bool:
    if type(value) is not str:
        return False
    parts = value.split(".")
    return len(parts) == 3 and all(part.isdigit() for part in parts)


__all__ = [
    "CanonicalResolutionState",
    "DEFAULT_INTRADAY_NATIVE_UNIVERSE_PATH",
    "EXPECTED_NATIVE_MEMBER_COUNT",
    "INTRADAY_NATIVE_UNIVERSE_IDENTITY",
    "INTRADAY_NATIVE_UNIVERSE_SCHEMA",
    "INTRADAY_NATIVE_UNIVERSE_VERSION",
    "IntradayMarketFamily",
    "IntradayMembershipStatus",
    "IntradayUniverseError",
    "IntradayUniverseFailure",
    "IntradayUniverseMember",
    "IntradayUniverseMemberResolution",
    "IntradayUniversePublication",
    "IntradayUniverseResolution",
    "IntradayUniverseRole",
    "load_intraday_universe_publication",
    "parse_intraday_universe_publication",
    "resolve_intraday_universe",
    "seal_intraday_universe_document",
]
