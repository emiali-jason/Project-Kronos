"""DOMAIN-001 runtime Instrument registry and consumption publisher."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json


INSTRUMENT_RUNTIME_SCHEMA = "KRONOS-INSTRUMENT-RUNTIME-V1"


class InstrumentFreshness(StrEnum):
    CURRENT = "CURRENT"
    STALE = "STALE"


class ProviderBindingStatus(StrEnum):
    BOUND = "BOUND"
    UNAVAILABLE = "UNAVAILABLE"
    STALE = "STALE"


class ExecutionContextAvailability(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"


@dataclass(frozen=True, slots=True)
class CanonicalInstrument:
    canonical_instrument_id: str
    exchange: str
    segment: str
    instrument_type: str
    canonical_tick_size: Decimal | None
    canonical_lot_size: int | None
    canonical_price_precision: int | None
    canonical_source_identity: str
    source_boundary: datetime
    valid_through: datetime
    integrity_identity: str
    schema_identity: str = INSTRUMENT_RUNTIME_SCHEMA

    def __post_init__(self) -> None:
        tick = _optional_decimal(self.canonical_tick_size)
        precision = price_precision_for_tick(tick)
        expected = canonical_instrument_integrity(
            canonical_instrument_id=self.canonical_instrument_id,
            exchange=self.exchange,
            segment=self.segment,
            instrument_type=self.instrument_type,
            canonical_tick_size=tick,
            canonical_lot_size=self.canonical_lot_size,
            canonical_source_identity=self.canonical_source_identity,
            source_boundary=self.source_boundary,
            valid_through=self.valid_through,
        )
        if (
            any(
                not _text(value)
                for value in (
                    self.canonical_instrument_id,
                    self.exchange,
                    self.segment,
                    self.instrument_type,
                    self.canonical_source_identity,
                )
            )
            or (tick is not None and tick <= 0)
            or (
                self.canonical_lot_size is not None
                and (
                    type(self.canonical_lot_size) is not int
                    or self.canonical_lot_size <= 0
                )
            )
            or self.canonical_price_precision != precision
            or not _aware(self.source_boundary)
            or not _aware(self.valid_through)
            or self.valid_through < self.source_boundary
            or self.integrity_identity != expected
            or self.schema_identity != INSTRUMENT_RUNTIME_SCHEMA
        ):
            raise ValueError("CANONICAL_INSTRUMENT_INVALID")
        object.__setattr__(self, "canonical_tick_size", tick)


def create_canonical_instrument(
    *,
    canonical_instrument_id: str,
    exchange: str,
    segment: str,
    instrument_type: str,
    canonical_tick_size: Decimal | None,
    canonical_lot_size: int | None,
    canonical_source_identity: str,
    source_boundary: datetime,
    valid_through: datetime,
) -> CanonicalInstrument:
    tick = _optional_decimal(canonical_tick_size)
    fields = {
        "canonical_instrument_id": canonical_instrument_id,
        "exchange": exchange,
        "segment": segment,
        "instrument_type": instrument_type,
        "canonical_tick_size": tick,
        "canonical_lot_size": canonical_lot_size,
        "canonical_source_identity": canonical_source_identity,
        "source_boundary": source_boundary,
        "valid_through": valid_through,
    }
    return CanonicalInstrument(
        **fields,
        canonical_price_precision=price_precision_for_tick(tick),
        integrity_identity=canonical_instrument_integrity(**fields),
    )


@dataclass(frozen=True, slots=True)
class ProviderInstrumentAssertion:
    provider: str
    provider_symbol: str
    provider_instrument_token: int
    exchange: str
    segment: str
    instrument_type: str
    asserted_tick_size: Decimal | None
    asserted_lot_size: int | None
    binding_source_identity: str
    source_boundary: datetime
    valid_through: datetime
    assertion_identity: str

    def __post_init__(self) -> None:
        tick = _optional_decimal(self.asserted_tick_size)
        fields = _provider_fields(self, tick)
        if (
            any(
                not _text(value)
                for value in (
                    self.provider,
                    self.provider_symbol,
                    self.exchange,
                    self.segment,
                    self.instrument_type,
                    self.binding_source_identity,
                )
            )
            or type(self.provider_instrument_token) is not int
            or self.provider_instrument_token <= 0
            or (tick is not None and tick <= 0)
            or (
                self.asserted_lot_size is not None
                and (
                    type(self.asserted_lot_size) is not int
                    or self.asserted_lot_size <= 0
                )
            )
            or not _aware(self.source_boundary)
            or not _aware(self.valid_through)
            or self.valid_through < self.source_boundary
            or self.assertion_identity != provider_assertion_identity(**fields)
        ):
            raise ValueError("PROVIDER_INSTRUMENT_ASSERTION_INVALID")
        object.__setattr__(self, "asserted_tick_size", tick)


def create_provider_assertion(
    *,
    provider: str,
    provider_symbol: str,
    provider_instrument_token: int,
    exchange: str,
    segment: str,
    instrument_type: str,
    asserted_tick_size: Decimal | None,
    asserted_lot_size: int | None,
    binding_source_identity: str,
    source_boundary: datetime,
    valid_through: datetime,
) -> ProviderInstrumentAssertion:
    fields = {
        "provider": provider,
        "provider_symbol": provider_symbol,
        "provider_instrument_token": provider_instrument_token,
        "exchange": exchange,
        "segment": segment,
        "instrument_type": instrument_type,
        "asserted_tick_size": _optional_decimal(asserted_tick_size),
        "asserted_lot_size": asserted_lot_size,
        "binding_source_identity": binding_source_identity,
        "source_boundary": source_boundary,
        "valid_through": valid_through,
    }
    return ProviderInstrumentAssertion(
        **fields,
        assertion_identity=provider_assertion_identity(**fields),
    )


@dataclass(frozen=True, slots=True)
class ProviderBindingDirective:
    canonical_instrument_id: str
    provider: str
    provider_symbol: str
    directive_source_identity: str
    integrity_identity: str

    def __post_init__(self) -> None:
        expected = provider_binding_directive_integrity(
            canonical_instrument_id=self.canonical_instrument_id,
            provider=self.provider,
            provider_symbol=self.provider_symbol,
            directive_source_identity=self.directive_source_identity,
        )
        if (
            any(
                not _text(value)
                for value in (
                    self.canonical_instrument_id,
                    self.provider,
                    self.provider_symbol,
                    self.directive_source_identity,
                )
            )
            or self.integrity_identity != expected
        ):
            raise ValueError("PROVIDER_BINDING_DIRECTIVE_INVALID")


def create_provider_binding_directive(
    *,
    canonical_instrument_id: str,
    provider: str,
    provider_symbol: str,
    directive_source_identity: str,
) -> ProviderBindingDirective:
    fields = {
        "canonical_instrument_id": canonical_instrument_id,
        "provider": provider,
        "provider_symbol": provider_symbol,
        "directive_source_identity": directive_source_identity,
    }
    return ProviderBindingDirective(
        **fields,
        integrity_identity=provider_binding_directive_integrity(**fields),
    )


@dataclass(frozen=True, slots=True)
class ProviderInstrumentBinding:
    provider: str
    provider_symbol: str
    provider_instrument_token: int
    assertion_identity: str
    binding_source_identity: str
    source_boundary: datetime
    valid_through: datetime
    binding_identity: str

    def __post_init__(self) -> None:
        if (
            any(
                not _text(value)
                for value in (
                    self.provider,
                    self.provider_symbol,
                    self.assertion_identity,
                    self.binding_source_identity,
                    self.binding_identity,
                )
            )
            or type(self.provider_instrument_token) is not int
            or self.provider_instrument_token <= 0
            or not self.assertion_identity.startswith(
                "PROVIDER-INSTRUMENT-ASSERTION-"
            )
            or not self.binding_identity.startswith("PROVIDER-BINDING-")
            or not _aware(self.source_boundary)
            or not _aware(self.valid_through)
            or self.valid_through < self.source_boundary
        ):
            raise ValueError("PROVIDER_INSTRUMENT_BINDING_INVALID")


@dataclass(frozen=True, slots=True)
class RuntimeInstrument:
    canonical: CanonicalInstrument
    canonical_freshness: InstrumentFreshness
    binding_status: ProviderBindingStatus
    provider_binding: ProviderInstrumentBinding | None
    execution_context: ExecutionContextAvailability
    publication_identity: str

    def __post_init__(self) -> None:
        bound = self.binding_status is ProviderBindingStatus.BOUND
        has_binding = self.binding_status in {
            ProviderBindingStatus.BOUND,
            ProviderBindingStatus.STALE,
        }
        complete = self.execution_context is ExecutionContextAvailability.COMPLETE
        expected = runtime_instrument_identity(
            self.canonical,
            self.canonical_freshness,
            self.binding_status,
            self.provider_binding,
            self.execution_context,
        )
        if (
            type(self.canonical) is not CanonicalInstrument
            or type(self.canonical_freshness) is not InstrumentFreshness
            or type(self.binding_status) is not ProviderBindingStatus
            or (has_binding != (self.provider_binding is not None))
            or type(self.execution_context) is not ExecutionContextAvailability
            or (
                complete
                != (
                    bound
                    and self.canonical_freshness is InstrumentFreshness.CURRENT
                    and self.canonical.canonical_tick_size is not None
                    and self.canonical.canonical_lot_size is not None
                    and self.canonical.canonical_price_precision is not None
                )
            )
            or self.publication_identity != expected
        ):
            raise ValueError("RUNTIME_INSTRUMENT_INVALID")


class RuntimeInstrumentRegistry:
    """Immutable product-neutral publication of governed canonical instruments."""

    def __init__(self, instruments: tuple[RuntimeInstrument, ...]) -> None:
        if not instruments or any(type(item) is not RuntimeInstrument for item in instruments):
            raise ValueError("RUNTIME_INSTRUMENT_REGISTRY_INVALID")
        identities = tuple(item.canonical.canonical_instrument_id for item in instruments)
        if len(set(identities)) != len(identities):
            raise ValueError("RUNTIME_INSTRUMENT_DUPLICATE")
        self._instruments = tuple(sorted(instruments, key=lambda item: item.canonical.canonical_instrument_id))
        self._by_identity = {
            item.canonical.canonical_instrument_id: item for item in self._instruments
        }

    @property
    def instruments(self) -> tuple[RuntimeInstrument, ...]:
        return self._instruments

    def lookup(self, canonical_instrument_id: str) -> RuntimeInstrument:
        try:
            return self._by_identity[canonical_instrument_id]
        except (KeyError, TypeError) as error:
            raise ValueError("RUNTIME_INSTRUMENT_UNAVAILABLE") from error

    def require_consumable(self, canonical_instrument_id: str) -> RuntimeInstrument:
        result = self.lookup(canonical_instrument_id)
        if result.execution_context is not ExecutionContextAvailability.COMPLETE:
            raise ValueError("RUNTIME_INSTRUMENT_INCOMPLETE")
        return result


def publish_runtime_instruments(
    *,
    canonical_instruments: tuple[CanonicalInstrument, ...],
    provider_assertions: tuple[ProviderInstrumentAssertion, ...],
    binding_directives: tuple[ProviderBindingDirective, ...],
    observed_at: datetime,
) -> RuntimeInstrumentRegistry:
    if (
        not canonical_instruments
        or any(type(item) is not CanonicalInstrument for item in canonical_instruments)
        or any(type(item) is not ProviderInstrumentAssertion for item in provider_assertions)
        or any(type(item) is not ProviderBindingDirective for item in binding_directives)
        or not _aware(observed_at)
    ):
        raise ValueError("RUNTIME_INSTRUMENT_PUBLICATION_INVALID")
    _reject_duplicates(canonical_instruments, provider_assertions, binding_directives)
    assertions = {(item.provider, item.provider_symbol): item for item in provider_assertions}
    directives = {item.canonical_instrument_id: item for item in binding_directives}
    published = tuple(
        _publish_one(item, assertions, directives.get(item.canonical_instrument_id), observed_at)
        for item in canonical_instruments
    )
    return RuntimeInstrumentRegistry(published)


def _publish_one(
    canonical: CanonicalInstrument,
    assertions: dict[tuple[str, str], ProviderInstrumentAssertion],
    directive: ProviderBindingDirective | None,
    observed_at: datetime,
) -> RuntimeInstrument:
    canonical_freshness = (
        InstrumentFreshness.CURRENT
        if canonical.source_boundary <= observed_at <= canonical.valid_through
        else InstrumentFreshness.STALE
    )
    assertion = None if directive is None else assertions.get((directive.provider, directive.provider_symbol))
    valid = (
        assertion is not None
        and _assertion_matches(canonical, assertion)
        and max(assertion.source_boundary, canonical.source_boundary)
        <= min(assertion.valid_through, canonical.valid_through)
    )
    binding: ProviderInstrumentBinding | None = None
    if valid and assertion is not None:
        binding_status = (
            ProviderBindingStatus.BOUND
            if (
                max(assertion.source_boundary, canonical.source_boundary)
                <= observed_at
                <= min(assertion.valid_through, canonical.valid_through)
            )
            else ProviderBindingStatus.STALE
        )
        binding_id = _binding_identity(canonical, assertion, directive)
        binding = ProviderInstrumentBinding(
            provider=assertion.provider,
            provider_symbol=assertion.provider_symbol,
            provider_instrument_token=assertion.provider_instrument_token,
            assertion_identity=assertion.assertion_identity,
            binding_source_identity=directive.directive_source_identity,
            source_boundary=max(assertion.source_boundary, canonical.source_boundary),
            valid_through=min(assertion.valid_through, canonical.valid_through),
            binding_identity=binding_id,
        )
    else:
        binding_status = ProviderBindingStatus.UNAVAILABLE
    execution = (
        ExecutionContextAvailability.COMPLETE
        if (
            binding_status is ProviderBindingStatus.BOUND
            and canonical_freshness is InstrumentFreshness.CURRENT
            and canonical.canonical_tick_size is not None
            and canonical.canonical_lot_size is not None
            and canonical.canonical_price_precision is not None
        )
        else ExecutionContextAvailability.INCOMPLETE
    )
    publication_id = runtime_instrument_identity(
        canonical,
        canonical_freshness,
        binding_status,
        binding,
        execution,
    )
    return RuntimeInstrument(
        canonical,
        canonical_freshness,
        binding_status,
        binding,
        execution,
        publication_id,
    )


def _assertion_matches(canonical: CanonicalInstrument, assertion: ProviderInstrumentAssertion) -> bool:
    return (
        assertion.exchange == canonical.exchange
        and assertion.segment == canonical.segment
        and assertion.instrument_type == canonical.instrument_type
        and assertion.asserted_tick_size == canonical.canonical_tick_size
        and assertion.asserted_lot_size == canonical.canonical_lot_size
    )


def _reject_duplicates(
    canonicals: tuple[CanonicalInstrument, ...],
    assertions: tuple[ProviderInstrumentAssertion, ...],
    directives: tuple[ProviderBindingDirective, ...],
) -> None:
    canonical_ids = [item.canonical_instrument_id for item in canonicals]
    assertion_keys = [(item.provider, item.provider_symbol) for item in assertions]
    directive_ids = [item.canonical_instrument_id for item in directives]
    directive_keys = [(item.provider, item.provider_symbol) for item in directives]
    token_keys = [(item.provider, item.provider_instrument_token) for item in assertions]
    if len(set(canonical_ids)) != len(canonical_ids):
        raise ValueError("CANONICAL_INSTRUMENT_DUPLICATE")
    if len(set(assertion_keys)) != len(assertion_keys):
        raise ValueError("PROVIDER_ASSERTION_DUPLICATE")
    if len(set(directive_ids)) != len(directive_ids) or len(set(directive_keys)) != len(directive_keys):
        raise ValueError("PROVIDER_BINDING_CONFLICT")
    if len(set(token_keys)) != len(token_keys):
        raise ValueError("PROVIDER_TOKEN_CONFLICT")
    if any(item.canonical_instrument_id not in set(canonical_ids) for item in directives):
        raise ValueError("PROVIDER_BINDING_UNKNOWN_CANONICAL_INSTRUMENT")


def price_precision_for_tick(tick_size: Decimal | None) -> int | None:
    tick = _optional_decimal(tick_size)
    if tick is None:
        return None
    if tick <= 0:
        raise ValueError("CANONICAL_TICK_SIZE_INVALID")
    normalized = tick.normalize()
    return max(0, -normalized.as_tuple().exponent)


def canonical_instrument_integrity(**fields: object) -> str:
    return f"CANONICAL-INSTRUMENT-{_digest(_serializable(fields))}"


def provider_assertion_identity(**fields: object) -> str:
    return f"PROVIDER-INSTRUMENT-ASSERTION-{_digest(_serializable(fields))}"


def provider_binding_directive_integrity(**fields: object) -> str:
    return f"PROVIDER-BINDING-DIRECTIVE-{_digest(_serializable(fields))}"


def runtime_instrument_identity(
    canonical: CanonicalInstrument,
    freshness: InstrumentFreshness,
    status: ProviderBindingStatus,
    binding: ProviderInstrumentBinding | None,
    execution: ExecutionContextAvailability,
) -> str:
    payload = {
        "canonical_integrity": canonical.integrity_identity,
        "canonical_freshness": freshness.value,
        "binding_status": status.value,
        "binding_identity": binding.binding_identity if binding is not None else None,
        "execution_context": execution.value,
    }
    return f"RUNTIME-INSTRUMENT-{_digest(payload)}"


def _binding_identity(
    canonical: CanonicalInstrument,
    assertion: ProviderInstrumentAssertion,
    directive: ProviderBindingDirective,
) -> str:
    return f"PROVIDER-BINDING-{_digest({'canonical': canonical.integrity_identity, 'assertion': assertion.assertion_identity, 'directive': directive.integrity_identity})}"


def _provider_fields(item: ProviderInstrumentAssertion, tick: Decimal | None) -> dict[str, object]:
    return {
        "provider": item.provider,
        "provider_symbol": item.provider_symbol,
        "provider_instrument_token": item.provider_instrument_token,
        "exchange": item.exchange,
        "segment": item.segment,
        "instrument_type": item.instrument_type,
        "asserted_tick_size": tick,
        "asserted_lot_size": item.asserted_lot_size,
        "binding_source_identity": item.binding_source_identity,
        "source_boundary": item.source_boundary,
        "valid_through": item.valid_through,
    }


def _serializable(value: object) -> object:
    if isinstance(value, dict):
        return {key: _serializable(item) for key, item in value.items()}
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _digest(payload: object) -> str:
    canonical = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return sha256(canonical.encode("utf-8")).hexdigest()


def _optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("CANONICAL_TICK_SIZE_INVALID")
    try:
        result = Decimal(str(value))
    except Exception as error:
        raise ValueError("CANONICAL_TICK_SIZE_INVALID") from error
    if not result.is_finite():
        raise ValueError("CANONICAL_TICK_SIZE_INVALID")
    return result


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


__all__ = [
    "CanonicalInstrument",
    "ExecutionContextAvailability",
    "INSTRUMENT_RUNTIME_SCHEMA",
    "InstrumentFreshness",
    "ProviderBindingDirective",
    "ProviderBindingStatus",
    "ProviderInstrumentAssertion",
    "ProviderInstrumentBinding",
    "RuntimeInstrument",
    "RuntimeInstrumentRegistry",
    "create_canonical_instrument",
    "create_provider_assertion",
    "create_provider_binding_directive",
    "price_precision_for_tick",
    "publish_runtime_instruments",
]
