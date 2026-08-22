"""DOMAIN-006 factual contracts for the Provider Instrument Master dataset."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from hashlib import sha256
import json
from typing import Protocol

from kronos.provider.contracts.instrument import InstrumentRecord


PROVIDER_INSTRUMENT_SNAPSHOT_SCHEMA = "KRONOS-PROVIDER-INSTRUMENT-SNAPSHOT-V1"
PROVIDER_INSTRUMENT_SNAPSHOT_VERSION = "1.0.0"
KITE_INSTRUMENT_MASTER_DATASET = "KITE-INSTRUMENT-MASTER"
KITE_INSTRUMENT_MASTER_OPERATION = "KITE-CONSOLIDATED-INSTRUMENT-MASTER-V1"


class ProviderInstrumentMasterFailure(StrEnum):
    """Sanitized fail-closed failures for the bounded P1 path."""

    CONTEXT_UNAVAILABLE = "CONTEXT_UNAVAILABLE"
    OPERATION_UNAUTHORIZED = "OPERATION_UNAUTHORIZED"
    PROVIDER_DATASET_UNAVAILABLE = "PROVIDER_DATASET_UNAVAILABLE"
    PROVIDER_ACQUISITION_FAILED = "PROVIDER_ACQUISITION_FAILED"
    SNAPSHOT_SCHEMA_INVALID = "SNAPSHOT_SCHEMA_INVALID"
    DUPLICATE_PROVIDER_RECORD_IDENTITY = "DUPLICATE_PROVIDER_RECORD_IDENTITY"
    SNAPSHOT_INTEGRITY_INVALID = "SNAPSHOT_INTEGRITY_INVALID"
    SNAPSHOT_CONFLICT = "SNAPSHOT_CONFLICT"
    PERSISTENCE_FAILED = "PERSISTENCE_FAILED"
    SOURCE_STALE = "SOURCE_STALE"


class ProviderInstrumentDiagnosticPhase(StrEnum):
    """Safe phase identity for one schema rejection."""

    PROVIDER_NORMALIZATION = "PROVIDER_NORMALIZATION"
    SNAPSHOT_CONSTRUCTION = "SNAPSHOT_CONSTRUCTION"
    SNAPSHOT_VALIDATION = "SNAPSHOT_VALIDATION"


class ProviderInstrumentValidationRule(StrEnum):
    """Stable rule identities containing no rejected Provider value."""

    RECORD_MAPPING_REQUIRED = "RECORD_MAPPING_REQUIRED"
    PROVIDER_REQUIRED = "PROVIDER_REQUIRED"
    PROVIDER_RECORD_IDENTITY_INVALID = "PROVIDER_RECORD_IDENTITY_INVALID"
    SYMBOL_REQUIRED = "SYMBOL_REQUIRED"
    NAME_INVALID = "NAME_INVALID"
    INSTRUMENT_TYPE_INVALID = "INSTRUMENT_TYPE_INVALID"
    SEGMENT_REQUIRED = "SEGMENT_REQUIRED"
    EXCHANGE_REQUIRED = "EXCHANGE_REQUIRED"
    LAST_PRICE_INVALID = "LAST_PRICE_INVALID"
    STRIKE_INVALID = "STRIKE_INVALID"
    TICK_REQUIRED = "TICK_REQUIRED"
    TICK_INVALID = "TICK_INVALID"
    LOT_REQUIRED = "LOT_REQUIRED"
    LOT_INVALID = "LOT_INVALID"
    EXPIRY_SHAPE_INVALID = "EXPIRY_SHAPE_INVALID"
    RECORD_SET_INVALID = "RECORD_SET_INVALID"
    RECORD_PROVIDER_CONFLICT = "RECORD_PROVIDER_CONFLICT"
    RECORD_IDENTITY_INVALID = "RECORD_IDENTITY_INVALID"
    DUPLICATE_RECORD_IDENTITY = "DUPLICATE_RECORD_IDENTITY"
    SNAPSHOT_METADATA_INVALID = "SNAPSHOT_METADATA_INVALID"
    SNAPSHOT_IDENTITY_INVALID = "SNAPSHOT_IDENTITY_INVALID"
    INTEGRITY_INVALID = "INTEGRITY_INVALID"


class ProviderInstrumentFieldFamily(StrEnum):
    """Bounded field families safe for operational projection."""

    RECORD = "RECORD"
    PROVIDER = "PROVIDER"
    PROVIDER_RECORD_IDENTITY = "PROVIDER_RECORD_IDENTITY"
    INSTRUMENT_TOKEN = "INSTRUMENT_TOKEN"
    EXCHANGE_TOKEN = "EXCHANGE_TOKEN"
    SYMBOL = "SYMBOL"
    NAME = "NAME"
    INSTRUMENT_TYPE = "INSTRUMENT_TYPE"
    SEGMENT = "SEGMENT"
    EXCHANGE = "EXCHANGE"
    LAST_PRICE = "LAST_PRICE"
    TICK_SIZE = "TICK_SIZE"
    LOT_SIZE = "LOT_SIZE"
    EXPIRY = "EXPIRY"
    STRIKE = "STRIKE"
    RECORD_IDENTITY = "RECORD_IDENTITY"
    SNAPSHOT_METADATA = "SNAPSHOT_METADATA"
    INTEGRITY = "INTEGRITY"
    OTHER = "OTHER"


class ProviderInstrumentValueClassification(StrEnum):
    """Safe value-shape classifications that never retain the value."""

    MISSING = "MISSING"
    NULL = "NULL"
    EMPTY = "EMPTY"
    MALFORMED = "MALFORMED"
    NEGATIVE = "NEGATIVE"
    NON_FINITE = "NON_FINITE"
    DUPLICATE = "DUPLICATE"
    CONFLICTING = "CONFLICTING"
    INVALID = "INVALID"


@dataclass(frozen=True, slots=True, repr=False)
class ProviderInstrumentSchemaDiagnostic:
    """Token-free diagnostic for one fail-fast schema rejection."""

    phase: ProviderInstrumentDiagnosticPhase
    rule: ProviderInstrumentValidationRule
    field_family: ProviderInstrumentFieldFamily
    value_classification: ProviderInstrumentValueClassification
    input_ordinal: int | None
    record_locator: str | None
    affected_count: int = 1

    def __post_init__(self) -> None:
        if (
            type(self.phase) is not ProviderInstrumentDiagnosticPhase
            or type(self.rule) is not ProviderInstrumentValidationRule
            or type(self.field_family) is not ProviderInstrumentFieldFamily
            or type(self.value_classification)
            is not ProviderInstrumentValueClassification
            or (
                self.input_ordinal is not None
                and (
                    type(self.input_ordinal) is not int
                    or self.input_ordinal <= 0
                )
            )
            or type(self.affected_count) is not int
            or self.affected_count != 1
        ):
            raise ValueError("PROVIDER_SCHEMA_DIAGNOSTIC_INVALID")
        expected_locator = _diagnostic_locator(
            self.phase,
            self.rule,
            self.field_family,
            self.value_classification,
            self.input_ordinal,
        )
        if self.record_locator != expected_locator:
            raise ValueError("PROVIDER_SCHEMA_DIAGNOSTIC_INVALID")

    def __repr__(self) -> str:
        return (
            "<ProviderInstrumentSchemaDiagnostic "
            f"phase={self.phase.value} rule={self.rule.value} redacted>"
        )


class ProviderInstrumentMasterError(RuntimeError):
    """Failure retaining no raw Provider response or authentication material."""

    def __init__(
        self,
        failure: ProviderInstrumentMasterFailure,
        diagnostic: ProviderInstrumentSchemaDiagnostic | None = None,
    ) -> None:
        if (
            type(failure) is not ProviderInstrumentMasterFailure
            or (
                diagnostic is not None
                and type(diagnostic) is not ProviderInstrumentSchemaDiagnostic
            )
        ):
            raise ValueError("PROVIDER_INSTRUMENT_MASTER_ERROR_INVALID")
        self.failure = failure
        self.diagnostic = diagnostic
        super().__init__(failure.value)

    def __repr__(self) -> str:
        return (
            "<ProviderInstrumentMasterError "
            f"failure={self.failure.value} diagnostic=redacted>"
        )


@dataclass(frozen=True, slots=True, repr=False)
class ProviderInstrumentMasterSourceRecord:
    """One safely normalized Provider-owned record before snapshot sealing."""

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
        last_price, strike, tick_size = _validate_source_values(
            provider=self.provider,
            provider_instrument_token=self.provider_instrument_token,
            exchange_token=self.exchange_token,
            trading_symbol=self.trading_symbol,
            name=self.name,
            last_price=self.last_price,
            expiry=self.expiry,
            strike=self.strike,
            tick_size=self.tick_size,
            lot_size=self.lot_size,
            instrument_type=self.instrument_type,
            segment=self.segment,
            exchange=self.exchange,
            missing_fields=frozenset(),
            phase=ProviderInstrumentDiagnosticPhase.SNAPSHOT_CONSTRUCTION,
            input_ordinal=None,
        )
        object.__setattr__(self, "last_price", last_price)
        object.__setattr__(self, "strike", strike)
        object.__setattr__(self, "tick_size", tick_size)

    def sanitized_instrument_record(self) -> InstrumentRecord:
        """Return the existing token-free read-only Instrument representation."""

        return InstrumentRecord(
            provider=self.provider,
            exchange=self.exchange,
            segment=self.segment,
            trading_symbol=self.trading_symbol,
            name=self.name,
            instrument_type=self.instrument_type,
            expiry=self.expiry,
            tick_size=self.tick_size,
            lot_size=self.lot_size,
        )

    def __repr__(self) -> str:
        return "<ProviderInstrumentMasterSourceRecord token-redacted>"


def create_provider_instrument_master_source_record(
    *,
    provider: object,
    provider_instrument_token: object,
    exchange_token: object,
    trading_symbol: object,
    name: object,
    last_price: object,
    expiry: object,
    strike: object,
    tick_size: object,
    lot_size: object,
    instrument_type: object,
    segment: object,
    exchange: object,
    missing_fields: frozenset[str],
    phase: ProviderInstrumentDiagnosticPhase,
    input_ordinal: int | None,
) -> ProviderInstrumentMasterSourceRecord:
    """Validate raw field shapes with safe phase/ordinal context."""

    last, normalized_strike, tick = _validate_source_values(
        provider=provider,
        provider_instrument_token=provider_instrument_token,
        exchange_token=exchange_token,
        trading_symbol=trading_symbol,
        name=name,
        last_price=last_price,
        expiry=expiry,
        strike=strike,
        tick_size=tick_size,
        lot_size=lot_size,
        instrument_type=instrument_type,
        segment=segment,
        exchange=exchange,
        missing_fields=missing_fields,
        phase=phase,
        input_ordinal=input_ordinal,
    )
    return ProviderInstrumentMasterSourceRecord(
        provider=provider,  # type: ignore[arg-type]
        provider_instrument_token=provider_instrument_token,  # type: ignore[arg-type]
        exchange_token=exchange_token,  # type: ignore[arg-type]
        trading_symbol=trading_symbol,  # type: ignore[arg-type]
        name=name,  # type: ignore[arg-type]
        last_price=last,
        expiry=expiry,  # type: ignore[arg-type]
        strike=normalized_strike,
        tick_size=tick,  # type: ignore[arg-type]
        lot_size=lot_size,  # type: ignore[arg-type]
        instrument_type=instrument_type,  # type: ignore[arg-type]
        segment=segment,  # type: ignore[arg-type]
        exchange=exchange,  # type: ignore[arg-type]
    )


def provider_instrument_schema_error(
    *,
    phase: ProviderInstrumentDiagnosticPhase,
    rule: ProviderInstrumentValidationRule,
    field_family: ProviderInstrumentFieldFamily,
    value_classification: ProviderInstrumentValueClassification,
    input_ordinal: int | None = None,
    failure: ProviderInstrumentMasterFailure = (
        ProviderInstrumentMasterFailure.SNAPSHOT_SCHEMA_INVALID
    ),
) -> ProviderInstrumentMasterError:
    """Create one typed error without retaining the rejected value."""

    return ProviderInstrumentMasterError(
        failure,
        ProviderInstrumentSchemaDiagnostic(
            phase=phase,
            rule=rule,
            field_family=field_family,
            value_classification=value_classification,
            input_ordinal=input_ordinal,
            record_locator=_diagnostic_locator(
                phase,
                rule,
                field_family,
                value_classification,
                input_ordinal,
            ),
        ),
    )


class ProviderInstrumentMasterCapability(Protocol):
    """DOMAIN-006-private consolidated Instrument Master operation."""

    @property
    def active(self) -> bool: ...

    def instrument_master_records(
        self,
    ) -> tuple[ProviderInstrumentMasterSourceRecord, ...]: ...


def _validate_source_values(
    *,
    provider: object,
    provider_instrument_token: object,
    exchange_token: object,
    trading_symbol: object,
    name: object,
    last_price: object,
    expiry: object,
    strike: object,
    tick_size: object,
    lot_size: object,
    instrument_type: object,
    segment: object,
    exchange: object,
    missing_fields: frozenset[str],
    phase: ProviderInstrumentDiagnosticPhase,
    input_ordinal: int | None,
) -> tuple[Decimal | None, Decimal | None, Decimal]:
    if (
        type(missing_fields) is not frozenset
        or type(phase) is not ProviderInstrumentDiagnosticPhase
    ):
        raise ValueError("PROVIDER_SOURCE_VALIDATION_CONTEXT_INVALID")

    def reject(
        rule: ProviderInstrumentValidationRule,
        field: ProviderInstrumentFieldFamily,
        classification: ProviderInstrumentValueClassification,
    ) -> None:
        raise provider_instrument_schema_error(
            phase=phase,
            rule=rule,
            field_family=field,
            value_classification=classification,
            input_ordinal=input_ordinal,
        )

    _required_text(
        provider,
        "provider",
        missing_fields,
        ProviderInstrumentValidationRule.PROVIDER_REQUIRED,
        ProviderInstrumentFieldFamily.PROVIDER,
        reject,
    )
    if "provider_instrument_token" in missing_fields:
        reject(
            ProviderInstrumentValidationRule.PROVIDER_RECORD_IDENTITY_INVALID,
            ProviderInstrumentFieldFamily.INSTRUMENT_TOKEN,
            ProviderInstrumentValueClassification.MISSING,
        )
    if provider_instrument_token is None:
        reject(
            ProviderInstrumentValidationRule.PROVIDER_RECORD_IDENTITY_INVALID,
            ProviderInstrumentFieldFamily.INSTRUMENT_TOKEN,
            ProviderInstrumentValueClassification.NULL,
        )
    if type(provider_instrument_token) is not int:
        reject(
            ProviderInstrumentValidationRule.PROVIDER_RECORD_IDENTITY_INVALID,
            ProviderInstrumentFieldFamily.INSTRUMENT_TOKEN,
            ProviderInstrumentValueClassification.MALFORMED,
        )
    if provider_instrument_token <= 0:
        reject(
            ProviderInstrumentValidationRule.PROVIDER_RECORD_IDENTITY_INVALID,
            ProviderInstrumentFieldFamily.INSTRUMENT_TOKEN,
            ProviderInstrumentValueClassification.NEGATIVE
            if provider_instrument_token < 0
            else ProviderInstrumentValueClassification.INVALID,
        )
    if exchange_token is not None and type(exchange_token) is not int:
        reject(
            ProviderInstrumentValidationRule.PROVIDER_RECORD_IDENTITY_INVALID,
            ProviderInstrumentFieldFamily.EXCHANGE_TOKEN,
            ProviderInstrumentValueClassification.MALFORMED,
        )
    if type(exchange_token) is int and exchange_token < 0:
        reject(
            ProviderInstrumentValidationRule.PROVIDER_RECORD_IDENTITY_INVALID,
            ProviderInstrumentFieldFamily.EXCHANGE_TOKEN,
            ProviderInstrumentValueClassification.NEGATIVE,
        )
    _required_text(
        trading_symbol,
        "trading_symbol",
        missing_fields,
        ProviderInstrumentValidationRule.SYMBOL_REQUIRED,
        ProviderInstrumentFieldFamily.SYMBOL,
        reject,
    )
    _optional_text_value(
        name,
        "name",
        missing_fields,
        ProviderInstrumentValidationRule.NAME_INVALID,
        ProviderInstrumentFieldFamily.NAME,
        reject,
    )
    _optional_text_value(
        instrument_type,
        "instrument_type",
        missing_fields,
        ProviderInstrumentValidationRule.INSTRUMENT_TYPE_INVALID,
        ProviderInstrumentFieldFamily.INSTRUMENT_TYPE,
        reject,
    )
    _required_text(
        segment,
        "segment",
        missing_fields,
        ProviderInstrumentValidationRule.SEGMENT_REQUIRED,
        ProviderInstrumentFieldFamily.SEGMENT,
        reject,
    )
    _required_text(
        exchange,
        "exchange",
        missing_fields,
        ProviderInstrumentValidationRule.EXCHANGE_REQUIRED,
        ProviderInstrumentFieldFamily.EXCHANGE,
        reject,
    )
    normalized_last, last_failure = _decimal_shape(last_price)
    if last_failure is not None:
        reject(
            ProviderInstrumentValidationRule.LAST_PRICE_INVALID,
            ProviderInstrumentFieldFamily.LAST_PRICE,
            last_failure,
        )
    if normalized_last is not None and normalized_last < 0:
        reject(
            ProviderInstrumentValidationRule.LAST_PRICE_INVALID,
            ProviderInstrumentFieldFamily.LAST_PRICE,
            ProviderInstrumentValueClassification.NEGATIVE,
        )
    normalized_strike, strike_failure = _decimal_shape(strike)
    if strike_failure is not None:
        reject(
            ProviderInstrumentValidationRule.STRIKE_INVALID,
            ProviderInstrumentFieldFamily.STRIKE,
            strike_failure,
        )
    if normalized_strike is not None and normalized_strike < 0:
        reject(
            ProviderInstrumentValidationRule.STRIKE_INVALID,
            ProviderInstrumentFieldFamily.STRIKE,
            ProviderInstrumentValueClassification.NEGATIVE,
        )
    if "tick_size" in missing_fields:
        reject(
            ProviderInstrumentValidationRule.TICK_REQUIRED,
            ProviderInstrumentFieldFamily.TICK_SIZE,
            ProviderInstrumentValueClassification.MISSING,
        )
    if tick_size is None:
        reject(
            ProviderInstrumentValidationRule.TICK_REQUIRED,
            ProviderInstrumentFieldFamily.TICK_SIZE,
            ProviderInstrumentValueClassification.NULL,
        )
    normalized_tick, tick_failure = _decimal_shape(tick_size)
    if tick_failure is not None:
        reject(
            ProviderInstrumentValidationRule.TICK_INVALID,
            ProviderInstrumentFieldFamily.TICK_SIZE,
            tick_failure,
        )
    assert normalized_tick is not None
    if normalized_tick < 0:
        reject(
            ProviderInstrumentValidationRule.TICK_INVALID,
            ProviderInstrumentFieldFamily.TICK_SIZE,
            ProviderInstrumentValueClassification.NEGATIVE,
        )
    if "lot_size" in missing_fields:
        reject(
            ProviderInstrumentValidationRule.LOT_REQUIRED,
            ProviderInstrumentFieldFamily.LOT_SIZE,
            ProviderInstrumentValueClassification.MISSING,
        )
    if lot_size is None:
        reject(
            ProviderInstrumentValidationRule.LOT_REQUIRED,
            ProviderInstrumentFieldFamily.LOT_SIZE,
            ProviderInstrumentValueClassification.NULL,
        )
    if type(lot_size) is not int:
        reject(
            ProviderInstrumentValidationRule.LOT_INVALID,
            ProviderInstrumentFieldFamily.LOT_SIZE,
            ProviderInstrumentValueClassification.MALFORMED,
        )
    if lot_size < 0:
        reject(
            ProviderInstrumentValidationRule.LOT_INVALID,
            ProviderInstrumentFieldFamily.LOT_SIZE,
            ProviderInstrumentValueClassification.NEGATIVE,
        )
    if expiry is not None and type(expiry) is not date:
        reject(
            ProviderInstrumentValidationRule.EXPIRY_SHAPE_INVALID,
            ProviderInstrumentFieldFamily.EXPIRY,
            ProviderInstrumentValueClassification.MALFORMED,
        )
    return normalized_last, normalized_strike, normalized_tick


def _required_text(
    value: object,
    field_name: str,
    missing_fields: frozenset[str],
    rule: ProviderInstrumentValidationRule,
    field: ProviderInstrumentFieldFamily,
    reject: Callable[
        [
            ProviderInstrumentValidationRule,
            ProviderInstrumentFieldFamily,
            ProviderInstrumentValueClassification,
        ],
        None,
    ],
) -> None:
    if field_name in missing_fields:
        reject(rule, field, ProviderInstrumentValueClassification.MISSING)
    if value is None:
        reject(rule, field, ProviderInstrumentValueClassification.NULL)
    if not isinstance(value, str):
        reject(rule, field, ProviderInstrumentValueClassification.MALFORMED)
    if value == "":
        reject(rule, field, ProviderInstrumentValueClassification.EMPTY)
    if value != value.strip():
        reject(rule, field, ProviderInstrumentValueClassification.MALFORMED)


def _optional_text_value(
    value: object,
    field_name: str,
    missing_fields: frozenset[str],
    rule: ProviderInstrumentValidationRule,
    field: ProviderInstrumentFieldFamily,
    reject: Callable[
        [
            ProviderInstrumentValidationRule,
            ProviderInstrumentFieldFamily,
            ProviderInstrumentValueClassification,
        ],
        None,
    ],
) -> None:
    if field_name in missing_fields:
        reject(rule, field, ProviderInstrumentValueClassification.MISSING)
    if value is None:
        reject(rule, field, ProviderInstrumentValueClassification.NULL)
    if not isinstance(value, str) or value != value.strip():
        reject(rule, field, ProviderInstrumentValueClassification.MALFORMED)


def _decimal_shape(
    value: object,
) -> tuple[Decimal | None, ProviderInstrumentValueClassification | None]:
    if value is None:
        return None, None
    try:
        result = value if type(value) is Decimal else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None, ProviderInstrumentValueClassification.MALFORMED
    if not result.is_finite():
        return None, ProviderInstrumentValueClassification.NON_FINITE
    return result, None


def _diagnostic_locator(
    phase: ProviderInstrumentDiagnosticPhase,
    rule: ProviderInstrumentValidationRule,
    field: ProviderInstrumentFieldFamily,
    classification: ProviderInstrumentValueClassification,
    ordinal: int | None,
) -> str | None:
    if ordinal is None:
        return None
    digest = sha256(
        json.dumps(
            {
                "schema": PROVIDER_INSTRUMENT_SNAPSHOT_SCHEMA,
                "version": PROVIDER_INSTRUMENT_SNAPSHOT_VERSION,
                "phase": phase.value,
                "rule": rule.value,
                "field": field.value,
                "classification": classification.value,
                "ordinal": ordinal,
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return f"PROVIDER-SCHEMA-LOCATOR-{digest}"


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _optional_text(value: object) -> bool:
    return isinstance(value, str) and value == value.strip()


__all__ = [
    "KITE_INSTRUMENT_MASTER_DATASET",
    "KITE_INSTRUMENT_MASTER_OPERATION",
    "PROVIDER_INSTRUMENT_SNAPSHOT_SCHEMA",
    "PROVIDER_INSTRUMENT_SNAPSHOT_VERSION",
    "ProviderInstrumentMasterCapability",
    "ProviderInstrumentMasterError",
    "ProviderInstrumentMasterFailure",
    "ProviderInstrumentMasterSourceRecord",
    "ProviderInstrumentDiagnosticPhase",
    "ProviderInstrumentFieldFamily",
    "ProviderInstrumentSchemaDiagnostic",
    "ProviderInstrumentValidationRule",
    "ProviderInstrumentValueClassification",
    "create_provider_instrument_master_source_record",
    "provider_instrument_schema_error",
]
