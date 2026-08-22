"""Immutable DOMAIN-006 Instrument Master snapshot acquisition and sealing."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, fields
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json
from typing import Protocol

from kronos.provider.contracts.instrument_master import (
    KITE_INSTRUMENT_MASTER_DATASET,
    KITE_INSTRUMENT_MASTER_OPERATION,
    PROVIDER_INSTRUMENT_SNAPSHOT_SCHEMA,
    PROVIDER_INSTRUMENT_SNAPSHOT_VERSION,
    ProviderInstrumentDiagnosticPhase,
    ProviderInstrumentFieldFamily,
    ProviderInstrumentMasterError,
    ProviderInstrumentMasterFailure,
    ProviderInstrumentMasterSourceRecord,
    ProviderInstrumentValidationRule,
    ProviderInstrumentValueClassification,
    create_provider_instrument_master_source_record,
    provider_instrument_schema_error,
)


class ProviderAcquisitionOutcome(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    EMPTY = "EMPTY"
    MISSING = "MISSING"
    UNSUPPORTED = "UNSUPPORTED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True, repr=False)
class ProviderInstrumentRecord:
    """One immutable, snapshot-bounded Provider factual record."""

    provider_record_identity: str
    record_integrity_identity: str
    snapshot_identity: str
    snapshot_ordinal: int
    provider: str
    provider_instrument_token: int
    exchange_token: int | None
    trading_symbol: str
    name: str
    last_price: Decimal | None
    expiry: date | None
    strike: Decimal | None
    tick_size: Decimal
    lot_size: int
    instrument_type: str
    segment: str
    exchange: str

    def __post_init__(self) -> None:
        try:
            source = _source_from_record(self)
        except ProviderInstrumentMasterError:
            raise
        except (TypeError, ValueError) as error:
            raise provider_instrument_schema_error(
                phase=ProviderInstrumentDiagnosticPhase.SNAPSHOT_VALIDATION,
                rule=ProviderInstrumentValidationRule.RECORD_IDENTITY_INVALID,
                field_family=ProviderInstrumentFieldFamily.RECORD_IDENTITY,
                value_classification=ProviderInstrumentValueClassification.INVALID,
                input_ordinal=(
                    self.snapshot_ordinal
                    if type(self.snapshot_ordinal) is int
                    and self.snapshot_ordinal > 0
                    else None
                ),
            ) from None
        fields = _record_identity_fields(
            snapshot_identity=self.snapshot_identity,
            snapshot_ordinal=self.snapshot_ordinal,
            facts=_source_record_document(source),
        )
        if (
            not _text(self.snapshot_identity)
            or type(self.snapshot_ordinal) is not int
            or self.snapshot_ordinal <= 0
            or self.provider_record_identity
            != _identity("PROVIDER-INSTRUMENT-RECORD", fields)
            or self.record_integrity_identity
            != _identity(
                "PROVIDER-INSTRUMENT-RECORD-INTEGRITY",
                {**fields, "provider_record_identity": self.provider_record_identity},
            )
        ):
            raise provider_instrument_schema_error(
                phase=ProviderInstrumentDiagnosticPhase.SNAPSHOT_VALIDATION,
                rule=ProviderInstrumentValidationRule.RECORD_IDENTITY_INVALID,
                field_family=ProviderInstrumentFieldFamily.RECORD_IDENTITY,
                value_classification=ProviderInstrumentValueClassification.INVALID,
                input_ordinal=(
                    self.snapshot_ordinal
                    if type(self.snapshot_ordinal) is int
                    and self.snapshot_ordinal > 0
                    else None
                ),
                failure=ProviderInstrumentMasterFailure.SNAPSHOT_INTEGRITY_INVALID,
            )

    def __repr__(self) -> str:
        return (
            "<ProviderInstrumentRecord "
            f"identity={self.provider_record_identity} token-redacted>"
        )


@dataclass(frozen=True, slots=True, repr=False)
class ProviderInstrumentSnapshot:
    """Closed immutable Provider snapshot with explicit factual provenance."""

    snapshot_identity: str
    snapshot_version: str
    provider: str
    dataset_identity: str
    operation_identity: str
    source_boundary: datetime
    request_started_at: datetime
    response_received_at: datetime
    acquired_at: datetime
    acquisition_effective_at: datetime
    authenticated_context_identity: str
    authorized_operation_identity: str
    component_identities: tuple[str, ...]
    acquisition_outcome: ProviderAcquisitionOutcome
    requested_scope: str
    record_count: int
    exchange_counts: tuple[tuple[str, int], ...]
    segment_counts: tuple[tuple[str, int], ...]
    instrument_type_counts: tuple[tuple[str, int], ...]
    records: tuple[ProviderInstrumentRecord, ...]
    provenance: tuple[str, ...]
    supersedes: str | None
    provider_validity_assertion: str | None
    integrity_identity: str
    schema_identity: str = PROVIDER_INSTRUMENT_SNAPSHOT_SCHEMA

    def __post_init__(self) -> None:
        if type(self.records) is not tuple or any(
            type(item) is not ProviderInstrumentRecord for item in self.records
        ):
            raise provider_instrument_schema_error(
                phase=ProviderInstrumentDiagnosticPhase.SNAPSHOT_VALIDATION,
                rule=ProviderInstrumentValidationRule.RECORD_SET_INVALID,
                field_family=ProviderInstrumentFieldFamily.RECORD,
                value_classification=ProviderInstrumentValueClassification.INVALID,
            )
        record_ids = tuple(item.provider_record_identity for item in self.records)
        ordinals = tuple(item.snapshot_ordinal for item in self.records)
        if len(record_ids) != len(set(record_ids)):
            raise provider_instrument_schema_error(
                phase=ProviderInstrumentDiagnosticPhase.SNAPSHOT_VALIDATION,
                rule=ProviderInstrumentValidationRule.DUPLICATE_RECORD_IDENTITY,
                field_family=ProviderInstrumentFieldFamily.RECORD_IDENTITY,
                value_classification=ProviderInstrumentValueClassification.DUPLICATE,
                failure=(
                    ProviderInstrumentMasterFailure.DUPLICATE_PROVIDER_RECORD_IDENTITY
                ),
            )
        expected_exchange_counts = _counts(item.exchange for item in self.records)
        expected_segment_counts = _counts(item.segment for item in self.records)
        expected_type_counts = _counts(item.instrument_type for item in self.records)
        identity_fields = _snapshot_identity_fields(self)
        if (
            self.schema_identity != PROVIDER_INSTRUMENT_SNAPSHOT_SCHEMA
            or self.snapshot_version != PROVIDER_INSTRUMENT_SNAPSHOT_VERSION
            or not _text(self.provider)
            or not _text(self.dataset_identity)
            or not _text(self.operation_identity)
            or not all(
                _aware(item)
                for item in (
                    self.source_boundary,
                    self.request_started_at,
                    self.response_received_at,
                    self.acquired_at,
                    self.acquisition_effective_at,
                )
            )
            or not (
                self.request_started_at
                <= self.response_received_at
                <= self.acquired_at
            )
            or not _text(self.authenticated_context_identity)
            or not _text(self.authorized_operation_identity)
            or not _texts(self.component_identities)
            or len(set(self.component_identities)) != len(self.component_identities)
            or type(self.acquisition_outcome) is not ProviderAcquisitionOutcome
            or not _text(self.requested_scope)
            or self.record_count != len(self.records)
            or self.record_count <= 0
            or ordinals != tuple(range(1, len(self.records) + 1))
            or any(item.snapshot_identity != self.snapshot_identity for item in self.records)
            or self.exchange_counts != expected_exchange_counts
            or self.segment_counts != expected_segment_counts
            or self.instrument_type_counts != expected_type_counts
            or not _texts(self.provenance)
            or (self.supersedes is not None and not _text(self.supersedes))
            or (
                self.provider_validity_assertion is not None
                and not _text(self.provider_validity_assertion)
            )
        ):
            raise provider_instrument_schema_error(
                phase=ProviderInstrumentDiagnosticPhase.SNAPSHOT_VALIDATION,
                rule=ProviderInstrumentValidationRule.SNAPSHOT_METADATA_INVALID,
                field_family=ProviderInstrumentFieldFamily.SNAPSHOT_METADATA,
                value_classification=ProviderInstrumentValueClassification.INVALID,
            )
        if self.snapshot_identity != _identity(
            "PROVIDER-INSTRUMENT-SNAPSHOT", identity_fields
        ):
            raise provider_instrument_schema_error(
                phase=ProviderInstrumentDiagnosticPhase.SNAPSHOT_VALIDATION,
                rule=ProviderInstrumentValidationRule.SNAPSHOT_IDENTITY_INVALID,
                field_family=ProviderInstrumentFieldFamily.INTEGRITY,
                value_classification=ProviderInstrumentValueClassification.INVALID,
                failure=ProviderInstrumentMasterFailure.SNAPSHOT_INTEGRITY_INVALID,
            )
        expected_integrity = _identity(
            "PROVIDER-INSTRUMENT-SNAPSHOT-INTEGRITY",
            _snapshot_integrity_fields(self),
        )
        if self.integrity_identity != expected_integrity:
            raise provider_instrument_schema_error(
                phase=ProviderInstrumentDiagnosticPhase.SNAPSHOT_VALIDATION,
                rule=ProviderInstrumentValidationRule.INTEGRITY_INVALID,
                field_family=ProviderInstrumentFieldFamily.INTEGRITY,
                value_classification=ProviderInstrumentValueClassification.INVALID,
                failure=ProviderInstrumentMasterFailure.SNAPSHOT_INTEGRITY_INVALID,
            )

    @property
    def component_request_count(self) -> int:
        return len(self.component_identities)

    def __repr__(self) -> str:
        return (
            "<ProviderInstrumentSnapshot "
            f"identity={self.snapshot_identity} records={self.record_count} "
            "tokens-redacted>"
        )


class _SharedProviderRuntime(Protocol):
    @property
    def provider_identity(self) -> str: ...

    @property
    def lifecycle_state(self) -> object: ...

    @property
    def authenticated_context_identity(self) -> str: ...

    def acquire_provider_instrument_master_records(
        self,
        *,
        operation_identity: str,
    ) -> tuple[ProviderInstrumentMasterSourceRecord, ...]: ...


class ProviderInstrumentMasterAcquisitionService:
    """Use the sole active shared context for one explicit consolidated read."""

    __slots__ = ("_clock", "_runtime")

    def __init__(
        self,
        runtime: _SharedProviderRuntime,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        if not callable(clock) or not callable(
            getattr(runtime, "acquire_provider_instrument_master_records", None)
        ):
            raise ValueError("PROVIDER_INSTRUMENT_MASTER_DEPENDENCY_INVALID")
        self._runtime = runtime
        self._clock = clock

    def acquire(
        self,
        *,
        source_boundary: datetime,
        authorized_operation_identity: str,
        provenance: tuple[str, ...],
        supersedes: str | None = None,
        provider_validity_assertion: str | None = None,
    ) -> ProviderInstrumentSnapshot:
        if (
            not _aware(source_boundary)
            or authorized_operation_identity != KITE_INSTRUMENT_MASTER_OPERATION
            or not _texts(provenance)
        ):
            raise ProviderInstrumentMasterError(
                ProviderInstrumentMasterFailure.OPERATION_UNAUTHORIZED
            )
        lifecycle = getattr(self._runtime.lifecycle_state, "value", "")
        if lifecycle != "ACTIVE":
            raise ProviderInstrumentMasterError(
                ProviderInstrumentMasterFailure.CONTEXT_UNAVAILABLE
            )
        if self._runtime.provider_identity != "KITE":
            raise ProviderInstrumentMasterError(
                ProviderInstrumentMasterFailure.OPERATION_UNAUTHORIZED
            )
        request_started_at = self._now()
        try:
            records = self._runtime.acquire_provider_instrument_master_records(
                operation_identity=authorized_operation_identity
            )
        except ProviderInstrumentMasterError:
            raise
        except Exception as error:
            failure_value = getattr(getattr(error, "failure", None), "value", "")
            failure = (
                ProviderInstrumentMasterFailure.OPERATION_UNAUTHORIZED
                if failure_value == "OPERATION_NOT_AUTHORIZED"
                else ProviderInstrumentMasterFailure.CONTEXT_UNAVAILABLE
                if failure_value
                in {
                    "CONTEXT_UNAVAILABLE",
                    "LEASE_RELEASED",
                    "CONTEXT_EXPIRED",
                    "CONTEXT_INVALIDATED",
                    "CONTEXT_ENDING",
                    "CONTEXT_DISPOSED",
                }
                else ProviderInstrumentMasterFailure.PROVIDER_ACQUISITION_FAILED
            )
            raise ProviderInstrumentMasterError(failure) from None
        response_received_at = self._now()
        if (
            type(records) is not tuple
            or not records
            or any(type(item) is not ProviderInstrumentMasterSourceRecord for item in records)
        ):
            raise ProviderInstrumentMasterError(
                ProviderInstrumentMasterFailure.PROVIDER_DATASET_UNAVAILABLE
            )
        acquired_at = self._now()
        component_identity = _identity(
            "PROVIDER-INSTRUMENT-ACQUISITION-COMPONENT",
            {
                "provider": self._runtime.provider_identity,
                "dataset_identity": KITE_INSTRUMENT_MASTER_DATASET,
                "operation_identity": authorized_operation_identity,
                "request_started_at": request_started_at.isoformat(),
                "response_received_at": response_received_at.isoformat(),
                "record_count": len(records),
            },
        )
        return create_provider_instrument_snapshot(
            records=records,
            provider=self._runtime.provider_identity,
            dataset_identity=KITE_INSTRUMENT_MASTER_DATASET,
            operation_identity=authorized_operation_identity,
            source_boundary=source_boundary,
            request_started_at=request_started_at,
            response_received_at=response_received_at,
            acquired_at=acquired_at,
            acquisition_effective_at=source_boundary,
            authenticated_context_identity=self._runtime.authenticated_context_identity,
            authorized_operation_identity=authorized_operation_identity,
            component_identities=(component_identity,),
            acquisition_outcome=ProviderAcquisitionOutcome.COMPLETE,
            provenance=provenance,
            supersedes=supersedes,
            provider_validity_assertion=provider_validity_assertion,
        )

    def _now(self) -> datetime:
        value = self._clock()
        if not _aware(value):
            raise ValueError("PROVIDER_INSTRUMENT_MASTER_CLOCK_INVALID")
        return value


def create_provider_instrument_snapshot(
    *,
    records: tuple[ProviderInstrumentMasterSourceRecord, ...],
    provider: str,
    dataset_identity: str,
    operation_identity: str,
    source_boundary: datetime,
    request_started_at: datetime,
    response_received_at: datetime,
    acquired_at: datetime,
    acquisition_effective_at: datetime,
    authenticated_context_identity: str,
    authorized_operation_identity: str,
    component_identities: tuple[str, ...],
    acquisition_outcome: ProviderAcquisitionOutcome,
    provenance: tuple[str, ...],
    supersedes: str | None = None,
    provider_validity_assertion: str | None = None,
) -> ProviderInstrumentSnapshot:
    if type(records) is not tuple or not records or any(
        type(item) is not ProviderInstrumentMasterSourceRecord for item in records
    ):
        raise provider_instrument_schema_error(
            phase=ProviderInstrumentDiagnosticPhase.SNAPSHOT_CONSTRUCTION,
            rule=ProviderInstrumentValidationRule.RECORD_SET_INVALID,
            field_family=ProviderInstrumentFieldFamily.RECORD,
            value_classification=ProviderInstrumentValueClassification.INVALID,
        )
    if any(item.provider != provider for item in records):
        raise provider_instrument_schema_error(
            phase=ProviderInstrumentDiagnosticPhase.SNAPSHOT_CONSTRUCTION,
            rule=ProviderInstrumentValidationRule.RECORD_PROVIDER_CONFLICT,
            field_family=ProviderInstrumentFieldFamily.PROVIDER,
            value_classification=ProviderInstrumentValueClassification.CONFLICTING,
        )
    _validate_snapshot_construction_metadata(
        provider=provider,
        dataset_identity=dataset_identity,
        operation_identity=operation_identity,
        source_boundary=source_boundary,
        request_started_at=request_started_at,
        response_received_at=response_received_at,
        acquired_at=acquired_at,
        acquisition_effective_at=acquisition_effective_at,
        authenticated_context_identity=authenticated_context_identity,
        authorized_operation_identity=authorized_operation_identity,
        component_identities=component_identities,
        acquisition_outcome=acquisition_outcome,
        provenance=provenance,
        supersedes=supersedes,
        provider_validity_assertion=provider_validity_assertion,
    )
    ordered = tuple(sorted(records, key=_source_record_sort_key))
    header = {
        "schema_identity": PROVIDER_INSTRUMENT_SNAPSHOT_SCHEMA,
        "snapshot_version": PROVIDER_INSTRUMENT_SNAPSHOT_VERSION,
        "provider": provider,
        "dataset_identity": dataset_identity,
        "operation_identity": operation_identity,
        "source_boundary": source_boundary.isoformat(),
        "request_started_at": request_started_at.isoformat(),
        "response_received_at": response_received_at.isoformat(),
        "acquired_at": acquired_at.isoformat(),
        "acquisition_effective_at": acquisition_effective_at.isoformat(),
        "authenticated_context_identity": authenticated_context_identity,
        "authorized_operation_identity": authorized_operation_identity,
        "component_identities": list(component_identities),
        "acquisition_outcome": acquisition_outcome.value,
        "requested_scope": "COMPLETE_RETURNED_AUTHORIZED_INSTRUMENT_MASTER_DATASET",
        "record_count": len(ordered),
        "provenance": list(provenance),
        "supersedes": supersedes,
        "provider_validity_assertion": provider_validity_assertion,
        "record_facts": [_source_record_document(item) for item in ordered],
    }
    snapshot_identity = _identity("PROVIDER-INSTRUMENT-SNAPSHOT", header)
    sealed_records = tuple(
        _seal_record(snapshot_identity, ordinal, item)
        for ordinal, item in enumerate(ordered, start=1)
    )
    snapshot_values: dict[str, object] = {
        "snapshot_identity": snapshot_identity,
        "snapshot_version": PROVIDER_INSTRUMENT_SNAPSHOT_VERSION,
        "provider": provider,
        "dataset_identity": dataset_identity,
        "operation_identity": operation_identity,
        "source_boundary": source_boundary,
        "request_started_at": request_started_at,
        "response_received_at": response_received_at,
        "acquired_at": acquired_at,
        "acquisition_effective_at": acquisition_effective_at,
        "authenticated_context_identity": authenticated_context_identity,
        "authorized_operation_identity": authorized_operation_identity,
        "component_identities": component_identities,
        "acquisition_outcome": acquisition_outcome,
        "requested_scope": "COMPLETE_RETURNED_AUTHORIZED_INSTRUMENT_MASTER_DATASET",
        "record_count": len(sealed_records),
        "exchange_counts": _counts(item.exchange for item in sealed_records),
        "segment_counts": _counts(item.segment for item in sealed_records),
        "instrument_type_counts": _counts(item.instrument_type for item in sealed_records),
        "records": sealed_records,
        "provenance": provenance,
        "supersedes": supersedes,
        "provider_validity_assertion": provider_validity_assertion,
        "schema_identity": PROVIDER_INSTRUMENT_SNAPSHOT_SCHEMA,
    }
    integrity = _identity(
        "PROVIDER-INSTRUMENT-SNAPSHOT-INTEGRITY",
        _snapshot_integrity_document(snapshot_values),
    )
    return ProviderInstrumentSnapshot(**snapshot_values, integrity_identity=integrity)  # type: ignore[arg-type]


def provider_instrument_snapshot_document(
    snapshot: ProviderInstrumentSnapshot,
) -> dict[str, object]:
    if type(snapshot) is not ProviderInstrumentSnapshot:
        raise ProviderInstrumentMasterError(
            ProviderInstrumentMasterFailure.SNAPSHOT_SCHEMA_INVALID
        )
    return {
        "schema_identity": snapshot.schema_identity,
        "snapshot_identity": snapshot.snapshot_identity,
        "snapshot_version": snapshot.snapshot_version,
        "provider": snapshot.provider,
        "dataset_identity": snapshot.dataset_identity,
        "operation_identity": snapshot.operation_identity,
        "source_boundary": snapshot.source_boundary.isoformat(),
        "request_started_at": snapshot.request_started_at.isoformat(),
        "response_received_at": snapshot.response_received_at.isoformat(),
        "acquired_at": snapshot.acquired_at.isoformat(),
        "acquisition_effective_at": snapshot.acquisition_effective_at.isoformat(),
        "authenticated_context_identity": snapshot.authenticated_context_identity,
        "authorized_operation_identity": snapshot.authorized_operation_identity,
        "component_identities": list(snapshot.component_identities),
        "acquisition_outcome": snapshot.acquisition_outcome.value,
        "requested_scope": snapshot.requested_scope,
        "record_count": snapshot.record_count,
        "exchange_counts": [list(item) for item in snapshot.exchange_counts],
        "segment_counts": [list(item) for item in snapshot.segment_counts],
        "instrument_type_counts": [list(item) for item in snapshot.instrument_type_counts],
        "records": [_provider_record_document(item) for item in snapshot.records],
        "provenance": list(snapshot.provenance),
        "supersedes": snapshot.supersedes,
        "provider_validity_assertion": snapshot.provider_validity_assertion,
        "integrity_identity": snapshot.integrity_identity,
    }


def encode_provider_instrument_snapshot(snapshot: ProviderInstrumentSnapshot) -> bytes:
    return json.dumps(
        provider_instrument_snapshot_document(snapshot),
        ensure_ascii=True,
        indent=2,
        sort_keys=True,
    ).encode("utf-8")


def parse_provider_instrument_snapshot(encoded: bytes) -> ProviderInstrumentSnapshot:
    try:
        document = json.loads(encoded)
        if type(document) is not dict or set(document) != _SNAPSHOT_KEYS:
            raise ValueError
        records = tuple(_parse_provider_record(item) for item in document["records"])
        snapshot = ProviderInstrumentSnapshot(
            schema_identity=document["schema_identity"],
            snapshot_identity=document["snapshot_identity"],
            snapshot_version=document["snapshot_version"],
            provider=document["provider"],
            dataset_identity=document["dataset_identity"],
            operation_identity=document["operation_identity"],
            source_boundary=datetime.fromisoformat(document["source_boundary"]),
            request_started_at=datetime.fromisoformat(document["request_started_at"]),
            response_received_at=datetime.fromisoformat(document["response_received_at"]),
            acquired_at=datetime.fromisoformat(document["acquired_at"]),
            acquisition_effective_at=datetime.fromisoformat(
                document["acquisition_effective_at"]
            ),
            authenticated_context_identity=document["authenticated_context_identity"],
            authorized_operation_identity=document["authorized_operation_identity"],
            component_identities=tuple(document["component_identities"]),
            acquisition_outcome=ProviderAcquisitionOutcome(
                document["acquisition_outcome"]
            ),
            requested_scope=document["requested_scope"],
            record_count=document["record_count"],
            exchange_counts=_parse_counts(document["exchange_counts"]),
            segment_counts=_parse_counts(document["segment_counts"]),
            instrument_type_counts=_parse_counts(document["instrument_type_counts"]),
            records=records,
            provenance=tuple(document["provenance"]),
            supersedes=document["supersedes"],
            provider_validity_assertion=document["provider_validity_assertion"],
            integrity_identity=document["integrity_identity"],
        )
    except ProviderInstrumentMasterError:
        raise
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ProviderInstrumentMasterError(
            ProviderInstrumentMasterFailure.SNAPSHOT_SCHEMA_INVALID
        ) from error
    if encode_provider_instrument_snapshot(snapshot) != encoded:
        raise ProviderInstrumentMasterError(
            ProviderInstrumentMasterFailure.SNAPSHOT_INTEGRITY_INVALID
        )
    return snapshot


def _seal_record(
    snapshot_identity: str,
    ordinal: int,
    source: ProviderInstrumentMasterSourceRecord,
) -> ProviderInstrumentRecord:
    facts = _source_record_document(source)
    identity_fields = _record_identity_fields(
        snapshot_identity=snapshot_identity,
        snapshot_ordinal=ordinal,
        facts=facts,
    )
    provider_record_identity = _identity(
        "PROVIDER-INSTRUMENT-RECORD", identity_fields
    )
    record_integrity = _identity(
        "PROVIDER-INSTRUMENT-RECORD-INTEGRITY",
        {**identity_fields, "provider_record_identity": provider_record_identity},
    )
    return ProviderInstrumentRecord(
        provider_record_identity=provider_record_identity,
        record_integrity_identity=record_integrity,
        snapshot_identity=snapshot_identity,
        snapshot_ordinal=ordinal,
        **{field.name: getattr(source, field.name) for field in fields(source)},
    )


def _snapshot_identity_fields(snapshot: ProviderInstrumentSnapshot) -> dict[str, object]:
    return {
        "schema_identity": snapshot.schema_identity,
        "snapshot_version": snapshot.snapshot_version,
        "provider": snapshot.provider,
        "dataset_identity": snapshot.dataset_identity,
        "operation_identity": snapshot.operation_identity,
        "source_boundary": snapshot.source_boundary.isoformat(),
        "request_started_at": snapshot.request_started_at.isoformat(),
        "response_received_at": snapshot.response_received_at.isoformat(),
        "acquired_at": snapshot.acquired_at.isoformat(),
        "acquisition_effective_at": snapshot.acquisition_effective_at.isoformat(),
        "authenticated_context_identity": snapshot.authenticated_context_identity,
        "authorized_operation_identity": snapshot.authorized_operation_identity,
        "component_identities": list(snapshot.component_identities),
        "acquisition_outcome": snapshot.acquisition_outcome.value,
        "requested_scope": snapshot.requested_scope,
        "record_count": snapshot.record_count,
        "provenance": list(snapshot.provenance),
        "supersedes": snapshot.supersedes,
        "provider_validity_assertion": snapshot.provider_validity_assertion,
        "record_facts": [
            _source_record_document(_source_from_record(item))
            for item in snapshot.records
        ],
    }


def _snapshot_integrity_fields(snapshot: ProviderInstrumentSnapshot) -> dict[str, object]:
    return provider_instrument_snapshot_document_without_integrity(snapshot)


def _snapshot_integrity_document(values: dict[str, object]) -> dict[str, object]:
    records = values["records"]
    assert type(records) is tuple
    return {
        "schema_identity": values["schema_identity"],
        "snapshot_version": values["snapshot_version"],
        "provider": values["provider"],
        "dataset_identity": values["dataset_identity"],
        "operation_identity": values["operation_identity"],
        "source_boundary": values["source_boundary"].isoformat(),  # type: ignore[union-attr]
        "request_started_at": values["request_started_at"].isoformat(),  # type: ignore[union-attr]
        "response_received_at": values["response_received_at"].isoformat(),  # type: ignore[union-attr]
        "acquired_at": values["acquired_at"].isoformat(),  # type: ignore[union-attr]
        "acquisition_effective_at": values["acquisition_effective_at"].isoformat(),  # type: ignore[union-attr]
        "authenticated_context_identity": values["authenticated_context_identity"],
        "authorized_operation_identity": values["authorized_operation_identity"],
        "component_identities": list(values["component_identities"]),  # type: ignore[arg-type]
        "acquisition_outcome": values["acquisition_outcome"].value,  # type: ignore[union-attr]
        "requested_scope": values["requested_scope"],
        "record_count": values["record_count"],
        "provenance": list(values["provenance"]),  # type: ignore[arg-type]
        "supersedes": values["supersedes"],
        "provider_validity_assertion": values["provider_validity_assertion"],
        "record_facts": [
            _source_record_document(_source_from_record(item)) for item in records
        ],
        "snapshot_identity": values["snapshot_identity"],
        "exchange_counts": [list(item) for item in values["exchange_counts"]],  # type: ignore[union-attr]
        "segment_counts": [list(item) for item in values["segment_counts"]],  # type: ignore[union-attr]
        "instrument_type_counts": [
            list(item) for item in values["instrument_type_counts"]  # type: ignore[union-attr]
        ],
        "records": [_provider_record_document(item) for item in records],
    }


def provider_instrument_snapshot_document_without_integrity(
    snapshot: ProviderInstrumentSnapshot,
) -> dict[str, object]:
    return {
        **_snapshot_identity_fields(snapshot),
        "snapshot_identity": snapshot.snapshot_identity,
        "exchange_counts": [list(item) for item in snapshot.exchange_counts],
        "segment_counts": [list(item) for item in snapshot.segment_counts],
        "instrument_type_counts": [list(item) for item in snapshot.instrument_type_counts],
        "records": [_provider_record_document(item) for item in snapshot.records],
    }


def _provider_record_document(record: ProviderInstrumentRecord) -> dict[str, object]:
    return {
        "provider_record_identity": record.provider_record_identity,
        "record_integrity_identity": record.record_integrity_identity,
        "snapshot_identity": record.snapshot_identity,
        "snapshot_ordinal": record.snapshot_ordinal,
        **_source_record_document(_source_from_record(record)),
    }


def _source_record_document(
    record: ProviderInstrumentMasterSourceRecord,
) -> dict[str, object]:
    return {
        "provider": record.provider,
        "provider_instrument_token": record.provider_instrument_token,
        "exchange_token": record.exchange_token,
        "trading_symbol": record.trading_symbol,
        "name": record.name,
        "last_price": _decimal_text(record.last_price),
        "expiry": None if record.expiry is None else record.expiry.isoformat(),
        "strike": _decimal_text(record.strike),
        "tick_size": _decimal_text(record.tick_size),
        "lot_size": record.lot_size,
        "instrument_type": record.instrument_type,
        "segment": record.segment,
        "exchange": record.exchange,
    }


def _parse_provider_record(document: object) -> ProviderInstrumentRecord:
    if type(document) is not dict or set(document) != _RECORD_KEYS:
        raise ValueError
    return ProviderInstrumentRecord(
        provider_record_identity=document["provider_record_identity"],
        record_integrity_identity=document["record_integrity_identity"],
        snapshot_identity=document["snapshot_identity"],
        snapshot_ordinal=document["snapshot_ordinal"],
        provider=document["provider"],
        provider_instrument_token=document["provider_instrument_token"],
        exchange_token=document["exchange_token"],
        trading_symbol=document["trading_symbol"],
        name=document["name"],
        last_price=_optional_decimal(document["last_price"]),
        expiry=(
            None
            if document["expiry"] is None
            else date.fromisoformat(document["expiry"])
        ),
        strike=_optional_decimal(document["strike"]),
        tick_size=Decimal(document["tick_size"]),
        lot_size=document["lot_size"],
        instrument_type=document["instrument_type"],
        segment=document["segment"],
        exchange=document["exchange"],
    )


def _source_from_record(
    record: ProviderInstrumentRecord,
) -> ProviderInstrumentMasterSourceRecord:
    ordinal = (
        record.snapshot_ordinal
        if type(record.snapshot_ordinal) is int and record.snapshot_ordinal > 0
        else None
    )
    return create_provider_instrument_master_source_record(
        provider=record.provider,
        provider_instrument_token=record.provider_instrument_token,
        exchange_token=record.exchange_token,
        trading_symbol=record.trading_symbol,
        name=record.name,
        last_price=record.last_price,
        expiry=record.expiry,
        strike=record.strike,
        tick_size=record.tick_size,
        lot_size=record.lot_size,
        instrument_type=record.instrument_type,
        segment=record.segment,
        exchange=record.exchange,
        missing_fields=frozenset(),
        phase=ProviderInstrumentDiagnosticPhase.SNAPSHOT_VALIDATION,
        input_ordinal=ordinal,
    )


def _validate_snapshot_construction_metadata(
    *,
    provider: object,
    dataset_identity: object,
    operation_identity: object,
    source_boundary: object,
    request_started_at: object,
    response_received_at: object,
    acquired_at: object,
    acquisition_effective_at: object,
    authenticated_context_identity: object,
    authorized_operation_identity: object,
    component_identities: object,
    acquisition_outcome: object,
    provenance: object,
    supersedes: object,
    provider_validity_assertion: object,
) -> None:
    valid_times = all(_aware(item) for item in (
        source_boundary,
        request_started_at,
        response_received_at,
        acquired_at,
        acquisition_effective_at,
    ))
    ordered_times = (
        valid_times
        and request_started_at <= response_received_at <= acquired_at  # type: ignore[operator]
    )
    if not (
        _text(provider)
        and _text(dataset_identity)
        and _text(operation_identity)
        and valid_times
        and ordered_times
        and _text(authenticated_context_identity)
        and _text(authorized_operation_identity)
        and _texts(component_identities)
        and len(set(component_identities)) == len(component_identities)  # type: ignore[arg-type]
        and type(acquisition_outcome) is ProviderAcquisitionOutcome
        and _texts(provenance)
        and (supersedes is None or _text(supersedes))
        and (
            provider_validity_assertion is None
            or _text(provider_validity_assertion)
        )
    ):
        raise provider_instrument_schema_error(
            phase=ProviderInstrumentDiagnosticPhase.SNAPSHOT_CONSTRUCTION,
            rule=ProviderInstrumentValidationRule.SNAPSHOT_METADATA_INVALID,
            field_family=ProviderInstrumentFieldFamily.SNAPSHOT_METADATA,
            value_classification=ProviderInstrumentValueClassification.INVALID,
        )


def _record_identity_fields(
    *,
    snapshot_identity: str,
    snapshot_ordinal: int,
    facts: dict[str, object],
) -> dict[str, object]:
    return {
        "snapshot_identity": snapshot_identity,
        "snapshot_ordinal": snapshot_ordinal,
        "facts": facts,
    }


def _source_record_sort_key(record: ProviderInstrumentMasterSourceRecord) -> str:
    return json.dumps(
        _source_record_document(record),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _counts(values: object) -> tuple[tuple[str, int], ...]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return tuple(sorted(counts.items()))


def _parse_counts(value: object) -> tuple[tuple[str, int], ...]:
    if not isinstance(value, list):
        raise ValueError
    parsed = tuple((item[0], item[1]) for item in value)
    if any(
        not isinstance(item, list)
        or len(item) != 2
        or not _text(item[0])
        or type(item[1]) is not int
        or item[1] <= 0
        for item in value
    ):
        raise ValueError
    return parsed


def _identity(prefix: str, fields: dict[str, object]) -> str:
    digest = sha256(
        json.dumps(
            fields,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return f"{prefix}-{digest}"


def _decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def _optional_decimal(value: object) -> Decimal | None:
    return None if value is None else Decimal(value)


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _texts(value: object) -> bool:
    return (
        type(value) is tuple
        and bool(value)
        and all(_text(item) for item in value)
    )


_RECORD_KEYS = {
    "provider_record_identity",
    "record_integrity_identity",
    "snapshot_identity",
    "snapshot_ordinal",
    "provider",
    "provider_instrument_token",
    "exchange_token",
    "trading_symbol",
    "name",
    "last_price",
    "expiry",
    "strike",
    "tick_size",
    "lot_size",
    "instrument_type",
    "segment",
    "exchange",
}

_SNAPSHOT_KEYS = {
    "schema_identity",
    "snapshot_identity",
    "snapshot_version",
    "provider",
    "dataset_identity",
    "operation_identity",
    "source_boundary",
    "request_started_at",
    "response_received_at",
    "acquired_at",
    "acquisition_effective_at",
    "authenticated_context_identity",
    "authorized_operation_identity",
    "component_identities",
    "acquisition_outcome",
    "requested_scope",
    "record_count",
    "exchange_counts",
    "segment_counts",
    "instrument_type_counts",
    "records",
    "provenance",
    "supersedes",
    "provider_validity_assertion",
    "integrity_identity",
}


__all__ = [
    "ProviderAcquisitionOutcome",
    "ProviderInstrumentMasterAcquisitionService",
    "ProviderInstrumentRecord",
    "ProviderInstrumentSnapshot",
    "create_provider_instrument_snapshot",
    "encode_provider_instrument_snapshot",
    "parse_provider_instrument_snapshot",
    "provider_instrument_snapshot_document",
]
