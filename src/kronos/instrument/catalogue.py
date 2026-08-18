"""Sealed DOMAIN-001 canonical Instrument catalogue publication."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from hashlib import sha256
import json
from pathlib import Path

from kronos.instrument.runtime import (
    CanonicalInstrument,
    ProviderBindingDirective,
    ProviderInstrumentAssertion,
    RuntimeInstrumentRegistry,
    create_canonical_instrument,
    create_provider_binding_directive,
    price_precision_for_tick,
    publish_runtime_instruments,
)


CANONICAL_INSTRUMENT_CATALOGUE_SCHEMA = (
    "KRONOS-CANONICAL-INSTRUMENT-CATALOGUE-V1"
)
CANONICAL_INSTRUMENT_CATALOGUE_IDENTITY = (
    "KRONOS-CANONICAL-INSTRUMENT-CATALOGUE-V1"
)
DEFAULT_CANONICAL_INSTRUMENT_CATALOGUE_PATH = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "instruments"
    / CANONICAL_INSTRUMENT_CATALOGUE_IDENTITY
    / "1.0.0.json"
)


class CanonicalInstrumentAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class CanonicalCatalogueFailure(StrEnum):
    PUBLICATION_UNAVAILABLE = "PUBLICATION_UNAVAILABLE"
    PUBLICATION_INVALID = "PUBLICATION_INVALID"
    INTEGRITY_MISMATCH = "INTEGRITY_MISMATCH"
    PUBLICATION_STALE = "PUBLICATION_STALE"


class CanonicalCatalogueError(RuntimeError):
    def __init__(self, failure: CanonicalCatalogueFailure) -> None:
        self.failure = failure
        super().__init__(failure.value)


@dataclass(frozen=True, slots=True)
class CanonicalCatalogueInstrument:
    canonical_instrument_id: str
    canonical_symbol: str
    canonical_name: str
    exchange: str
    segment: str
    instrument_type: str
    tick_size: Decimal | None
    lot_size: int | None
    price_precision: int | None
    availability: CanonicalInstrumentAvailability
    valid_from: datetime
    valid_through: datetime
    source_identities: tuple[str, ...]
    provenance: tuple[str, ...]
    integrity_identity: str

    def __post_init__(self) -> None:
        tick = _tick_or_none(self.tick_size)
        lot = self.lot_size if type(self.lot_size) is int and self.lot_size > 0 else None
        fields = _instrument_fields(self, tick=tick, lot=lot)
        if (
            any(
                not _text(value)
                for value in (
                    self.canonical_instrument_id,
                    self.canonical_symbol,
                    self.canonical_name,
                    self.exchange,
                    self.segment,
                    self.instrument_type,
                )
            )
            or type(self.availability) is not CanonicalInstrumentAvailability
            or self.price_precision != price_precision_for_tick(tick)
            or not _aware(self.valid_from)
            or not _aware(self.valid_through)
            or self.valid_through < self.valid_from
            or not _texts(self.source_identities)
            or not _texts(self.provenance)
            or self.integrity_identity != _identity("CANONICAL-RECORD", fields)
        ):
            raise CanonicalCatalogueError(CanonicalCatalogueFailure.PUBLICATION_INVALID)
        object.__setattr__(self, "tick_size", tick)
        object.__setattr__(self, "lot_size", lot)

    def runtime_canonical(
        self,
        *,
        publication_source_identity: str,
    ) -> CanonicalInstrument:
        available = self.availability is CanonicalInstrumentAvailability.AVAILABLE
        return create_canonical_instrument(
            canonical_instrument_id=self.canonical_instrument_id,
            exchange=self.exchange,
            segment=self.segment,
            instrument_type=self.instrument_type,
            canonical_tick_size=self.tick_size if available else None,
            canonical_lot_size=self.lot_size if available else None,
            canonical_source_identity=publication_source_identity,
            source_boundary=self.valid_from,
            valid_through=self.valid_through,
        )


@dataclass(frozen=True, slots=True)
class GovernedProviderBindingDirective:
    canonical_instrument_id: str
    provider_identity: str
    expected_provider_symbol: str
    directive_version: str
    valid_from: datetime
    valid_through: datetime
    source_identity: str
    source_boundary: datetime
    provenance: tuple[str, ...]
    integrity_identity: str

    def __post_init__(self) -> None:
        fields = _directive_fields(self)
        if (
            any(
                not _text(value)
                for value in (
                    self.canonical_instrument_id,
                    self.provider_identity,
                    self.expected_provider_symbol,
                    self.directive_version,
                    self.source_identity,
                )
            )
            or not _aware(self.valid_from)
            or not _aware(self.valid_through)
            or not _aware(self.source_boundary)
            or self.valid_through < self.valid_from
            or not _texts(self.provenance)
            or self.integrity_identity != _identity("PROVIDER-BINDING-DIRECTIVE", fields)
        ):
            raise CanonicalCatalogueError(CanonicalCatalogueFailure.PUBLICATION_INVALID)

    def active_at(self, observed_at: datetime) -> bool:
        return _aware(observed_at) and self.valid_from <= observed_at <= self.valid_through

    def runtime_directive(self) -> ProviderBindingDirective:
        return create_provider_binding_directive(
            canonical_instrument_id=self.canonical_instrument_id,
            provider=self.provider_identity,
            provider_symbol=self.expected_provider_symbol,
            directive_source_identity=(
                f"{self.source_identity}:{self.directive_version}:"
                f"{self.integrity_identity}"
            ),
        )


@dataclass(frozen=True, slots=True)
class CanonicalInstrumentCatalogue:
    publication_identity: str
    publication_version: str
    valid_from: datetime
    valid_through: datetime
    source_boundary: datetime
    supersedes: str | None
    source_identities: tuple[str, ...]
    provenance: tuple[str, ...]
    instruments: tuple[CanonicalCatalogueInstrument, ...]
    binding_directives: tuple[GovernedProviderBindingDirective, ...]
    integrity_identity: str
    schema_identity: str = CANONICAL_INSTRUMENT_CATALOGUE_SCHEMA

    def __post_init__(self) -> None:
        instrument_ids = tuple(item.canonical_instrument_id for item in self.instruments)
        directive_ids = tuple(item.canonical_instrument_id for item in self.binding_directives)
        directive_keys = tuple(
            (item.provider_identity, item.expected_provider_symbol)
            for item in self.binding_directives
        )
        if (
            self.schema_identity != CANONICAL_INSTRUMENT_CATALOGUE_SCHEMA
            or self.publication_identity != CANONICAL_INSTRUMENT_CATALOGUE_IDENTITY
            or not _text(self.publication_version)
            or not _aware(self.valid_from)
            or not _aware(self.valid_through)
            or not _aware(self.source_boundary)
            or self.valid_through < self.valid_from
            or (self.supersedes is not None and not _text(self.supersedes))
            or not _texts(self.source_identities)
            or not _texts(self.provenance)
            or not self.instruments
            or any(type(item) is not CanonicalCatalogueInstrument for item in self.instruments)
            or any(
                type(item) is not GovernedProviderBindingDirective
                for item in self.binding_directives
            )
            or len(set(instrument_ids)) != len(instrument_ids)
            or len(set(directive_ids)) != len(directive_ids)
            or len(set(directive_keys)) != len(directive_keys)
            or any(identity not in set(instrument_ids) for identity in directive_ids)
            or not self.integrity_identity.startswith("CATALOGUE-PUBLICATION-")
        ):
            raise CanonicalCatalogueError(CanonicalCatalogueFailure.PUBLICATION_INVALID)

    @property
    def publication_source_identity(self) -> str:
        return (
            f"{self.publication_identity}:{self.publication_version}:"
            f"{self.integrity_identity}"
        )

    def require_current(self, observed_at: datetime) -> None:
        if not _aware(observed_at) or not self.valid_from <= observed_at <= self.valid_through:
            raise CanonicalCatalogueError(CanonicalCatalogueFailure.PUBLICATION_STALE)

    def runtime_registry(
        self,
        *,
        provider_assertions: tuple[ProviderInstrumentAssertion, ...],
        observed_at: datetime,
    ) -> RuntimeInstrumentRegistry:
        self.require_current(observed_at)
        if any(type(item) is not ProviderInstrumentAssertion for item in provider_assertions):
            raise CanonicalCatalogueError(CanonicalCatalogueFailure.PUBLICATION_INVALID)
        canonicals = tuple(
            item.runtime_canonical(
                publication_source_identity=self.publication_source_identity,
            )
            for item in self.instruments
        )
        directives = tuple(
            item.runtime_directive()
            for item in self.binding_directives
            if item.active_at(observed_at)
        )
        return publish_runtime_instruments(
            canonical_instruments=canonicals,
            provider_assertions=provider_assertions,
            binding_directives=directives,
            observed_at=observed_at,
        )


def seal_canonical_catalogue_document(document: dict[str, object]) -> bytes:
    """Deterministically seal a reviewable catalogue source document."""

    core = _source_document(document)
    instruments = []
    for raw in core["instruments"]:
        assert type(raw) is dict
        item = dict(raw)
        tick = _tick_or_none(item.get("tick_size"))
        item["tick_size"] = None if tick is None else format(tick, "f")
        lot = item.get("lot_size")
        item["lot_size"] = lot if type(lot) is int and lot > 0 else None
        item["integrity_identity"] = _identity("CANONICAL-RECORD", item)
        instruments.append(item)
    directives = []
    for raw in core["binding_directives"]:
        assert type(raw) is dict
        item = dict(raw)
        item["integrity_identity"] = _identity("PROVIDER-BINDING-DIRECTIVE", item)
        directives.append(item)
    sealed = {**core, "instruments": instruments, "binding_directives": directives}
    sealed["integrity_identity"] = _identity("CATALOGUE-PUBLICATION", sealed)
    return _encode(sealed)


def parse_canonical_catalogue_publication(encoded: bytes) -> CanonicalInstrumentCatalogue:
    try:
        document = json.loads(encoded)
    except (json.JSONDecodeError, TypeError, UnicodeDecodeError) as error:
        raise CanonicalCatalogueError(CanonicalCatalogueFailure.PUBLICATION_INVALID) from error
    if type(document) is not dict or type(document.get("integrity_identity")) is not str:
        raise CanonicalCatalogueError(CanonicalCatalogueFailure.PUBLICATION_INVALID)
    supplied_integrity = document["integrity_identity"]
    core = {key: value for key, value in document.items() if key != "integrity_identity"}
    if supplied_integrity != _identity("CATALOGUE-PUBLICATION", core):
        raise CanonicalCatalogueError(CanonicalCatalogueFailure.INTEGRITY_MISMATCH)
    try:
        instruments = tuple(_parse_instrument(item) for item in core["instruments"])
        directives = tuple(_parse_directive(item) for item in core["binding_directives"])
        return CanonicalInstrumentCatalogue(
            schema_identity=core["schema_identity"],
            publication_identity=core["publication_identity"],
            publication_version=core["publication_version"],
            valid_from=_datetime(core["valid_from"]),
            valid_through=_datetime(core["valid_through"]),
            source_boundary=_datetime(core["source_boundary"]),
            supersedes=core["supersedes"],
            source_identities=_strings(core["source_identities"]),
            provenance=_strings(core["provenance"]),
            instruments=instruments,
            binding_directives=directives,
            integrity_identity=supplied_integrity,
        )
    except (KeyError, TypeError, ValueError, InvalidOperation) as error:
        if isinstance(error, CanonicalCatalogueError):
            raise
        raise CanonicalCatalogueError(CanonicalCatalogueFailure.PUBLICATION_INVALID) from error


def load_canonical_instrument_catalogue(
    path: Path = DEFAULT_CANONICAL_INSTRUMENT_CATALOGUE_PATH,
) -> CanonicalInstrumentCatalogue:
    path = Path(path)
    if not path.is_absolute():
        raise CanonicalCatalogueError(CanonicalCatalogueFailure.PUBLICATION_INVALID)
    try:
        encoded = path.read_bytes()
    except OSError as error:
        raise CanonicalCatalogueError(CanonicalCatalogueFailure.PUBLICATION_UNAVAILABLE) from error
    return parse_canonical_catalogue_publication(encoded)


def _source_document(document: dict[str, object]) -> dict[str, object]:
    required = {
        "schema_identity",
        "publication_identity",
        "publication_version",
        "valid_from",
        "valid_through",
        "source_boundary",
        "supersedes",
        "source_identities",
        "provenance",
        "instruments",
        "binding_directives",
    }
    if type(document) is not dict or set(document) != required:
        raise CanonicalCatalogueError(CanonicalCatalogueFailure.PUBLICATION_INVALID)
    if (
        document["schema_identity"] != CANONICAL_INSTRUMENT_CATALOGUE_SCHEMA
        or document["publication_identity"] != CANONICAL_INSTRUMENT_CATALOGUE_IDENTITY
        or type(document["instruments"]) is not list
        or not document["instruments"]
        or type(document["binding_directives"]) is not list
    ):
        raise CanonicalCatalogueError(CanonicalCatalogueFailure.PUBLICATION_INVALID)
    return dict(document)


def _parse_instrument(value: object) -> CanonicalCatalogueInstrument:
    if type(value) is not dict:
        raise CanonicalCatalogueError(CanonicalCatalogueFailure.PUBLICATION_INVALID)
    tick = _tick_or_none(value["tick_size"])
    lot = value["lot_size"] if type(value["lot_size"]) is int and value["lot_size"] > 0 else None
    return CanonicalCatalogueInstrument(
        canonical_instrument_id=value["canonical_instrument_id"],
        canonical_symbol=value["canonical_symbol"],
        canonical_name=value["canonical_name"],
        exchange=value["exchange"],
        segment=value["segment"],
        instrument_type=value["instrument_type"],
        tick_size=tick,
        lot_size=lot,
        price_precision=price_precision_for_tick(tick),
        availability=CanonicalInstrumentAvailability(value["availability"]),
        valid_from=_datetime(value["valid_from"]),
        valid_through=_datetime(value["valid_through"]),
        source_identities=_strings(value["source_identities"]),
        provenance=_strings(value["provenance"]),
        integrity_identity=value["integrity_identity"],
    )


def _parse_directive(value: object) -> GovernedProviderBindingDirective:
    if type(value) is not dict:
        raise CanonicalCatalogueError(CanonicalCatalogueFailure.PUBLICATION_INVALID)
    return GovernedProviderBindingDirective(
        canonical_instrument_id=value["canonical_instrument_id"],
        provider_identity=value["provider_identity"],
        expected_provider_symbol=value["expected_provider_symbol"],
        directive_version=value["directive_version"],
        valid_from=_datetime(value["valid_from"]),
        valid_through=_datetime(value["valid_through"]),
        source_identity=value["source_identity"],
        source_boundary=_datetime(value["source_boundary"]),
        provenance=_strings(value["provenance"]),
        integrity_identity=value["integrity_identity"],
    )


def _instrument_fields(
    value: CanonicalCatalogueInstrument,
    *,
    tick: Decimal | None,
    lot: int | None,
) -> dict[str, object]:
    return {
        "canonical_instrument_id": value.canonical_instrument_id,
        "canonical_symbol": value.canonical_symbol,
        "canonical_name": value.canonical_name,
        "exchange": value.exchange,
        "segment": value.segment,
        "instrument_type": value.instrument_type,
        "tick_size": None if tick is None else format(tick, "f"),
        "lot_size": lot,
        "availability": value.availability.value,
        "valid_from": value.valid_from.isoformat(),
        "valid_through": value.valid_through.isoformat(),
        "source_identities": list(value.source_identities),
        "provenance": list(value.provenance),
    }


def _directive_fields(value: GovernedProviderBindingDirective) -> dict[str, object]:
    return {
        "canonical_instrument_id": value.canonical_instrument_id,
        "provider_identity": value.provider_identity,
        "expected_provider_symbol": value.expected_provider_symbol,
        "directive_version": value.directive_version,
        "valid_from": value.valid_from.isoformat(),
        "valid_through": value.valid_through.isoformat(),
        "source_identity": value.source_identity,
        "source_boundary": value.source_boundary.isoformat(),
        "provenance": list(value.provenance),
    }


def _tick_or_none(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        tick = value if type(value) is Decimal else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return tick if tick.is_finite() and tick > 0 else None


def _datetime(value: object) -> datetime:
    if type(value) is not str:
        raise ValueError("CANONICAL_CATALOGUE_DATETIME_INVALID")
    parsed = datetime.fromisoformat(value)
    if not _aware(parsed):
        raise ValueError("CANONICAL_CATALOGUE_DATETIME_INVALID")
    return parsed


def _strings(value: object) -> tuple[str, ...]:
    if type(value) is not list or not value or any(not _text(item) for item in value):
        raise ValueError("CANONICAL_CATALOGUE_STRINGS_INVALID")
    return tuple(value)


def _texts(value: object) -> bool:
    return type(value) is tuple and bool(value) and all(_text(item) for item in value)


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _identity(prefix: str, document: object) -> str:
    return f"{prefix}-{sha256(_encode(document)).hexdigest()}"


def _encode(document: object) -> bytes:
    return json.dumps(
        document,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


__all__ = [
    "CANONICAL_INSTRUMENT_CATALOGUE_IDENTITY",
    "CANONICAL_INSTRUMENT_CATALOGUE_SCHEMA",
    "CanonicalCatalogueError",
    "CanonicalCatalogueFailure",
    "CanonicalCatalogueInstrument",
    "CanonicalInstrumentAvailability",
    "CanonicalInstrumentCatalogue",
    "DEFAULT_CANONICAL_INSTRUMENT_CATALOGUE_PATH",
    "GovernedProviderBindingDirective",
    "load_canonical_instrument_catalogue",
    "parse_canonical_catalogue_publication",
    "seal_canonical_catalogue_document",
]
