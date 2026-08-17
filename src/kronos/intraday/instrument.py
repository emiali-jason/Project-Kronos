"""Thin Intraday consumer adapter over governed Instrument/provider outputs."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from kronos.instrument.runtime import (
    ExecutionContextAvailability,
    ProviderBindingStatus,
    RuntimeInstrument,
)
from kronos.intraday.contracts import (
    IntradayInstrumentReference,
    instrument_mapping_identity,
)
from kronos.provider.contracts.instrument import InstrumentRecord


@dataclass(frozen=True, slots=True)
class InstrumentExecutionMetadata:
    """Instrument-owned execution mapping supplied to the product boundary."""

    provider_instrument_token: int
    tick_size: Decimal
    lot_size: int
    price_precision: int

    def __post_init__(self) -> None:
        tick = Decimal(str(self.tick_size))
        if (
            type(self.provider_instrument_token) is not int
            or self.provider_instrument_token <= 0
            or not tick.is_finite()
            or tick <= 0
            or type(self.lot_size) is not int
            or self.lot_size <= 0
            or type(self.price_precision) is not int
            or self.price_precision < 0
            or -tick.as_tuple().exponent > self.price_precision
        ):
            raise ValueError("INSTRUMENT_EXECUTION_METADATA_INVALID")
        object.__setattr__(self, "tick_size", tick)


def adapt_instrument_reference(
    *,
    canonical_instrument_id: str,
    provider_record: InstrumentRecord,
    execution_metadata: InstrumentExecutionMetadata,
) -> IntradayInstrumentReference:
    """Bind existing outputs without interpreting or repairing Provider data."""

    if (
        type(provider_record) is not InstrumentRecord
        or type(execution_metadata) is not InstrumentExecutionMetadata
    ):
        raise ValueError("INTRADAY_INSTRUMENT_MAPPING_UNAVAILABLE")
    fields = {
        "canonical_instrument_id": canonical_instrument_id,
        "exchange": provider_record.exchange,
        "segment": provider_record.segment,
        "instrument_type": provider_record.instrument_type,
        "provider": provider_record.provider,
        "provider_symbol": provider_record.trading_symbol,
        "provider_instrument_token": execution_metadata.provider_instrument_token,
        "tick_size": execution_metadata.tick_size,
        "lot_size": execution_metadata.lot_size,
        "price_precision": execution_metadata.price_precision,
    }
    return IntradayInstrumentReference(
        **fields,
        mapping_identity=instrument_mapping_identity(**fields),
    )


def adapt_runtime_instrument(
    published: RuntimeInstrument,
) -> IntradayInstrumentReference:
    """Consume a complete DOMAIN-001 publication without acquiring ownership."""

    if (
        type(published) is not RuntimeInstrument
        or published.binding_status is not ProviderBindingStatus.BOUND
        or published.execution_context is not ExecutionContextAvailability.COMPLETE
        or published.provider_binding is None
        or published.canonical.canonical_tick_size is None
        or published.canonical.canonical_lot_size is None
        or published.canonical.canonical_price_precision is None
    ):
        raise ValueError("INTRADAY_INSTRUMENT_MAPPING_UNAVAILABLE")
    canonical = published.canonical
    binding = published.provider_binding
    return adapt_instrument_reference(
        canonical_instrument_id=canonical.canonical_instrument_id,
        provider_record=InstrumentRecord(
            provider=binding.provider,
            exchange=canonical.exchange,
            segment=canonical.segment,
            trading_symbol=binding.provider_symbol,
            name=canonical.canonical_instrument_id,
            instrument_type=canonical.instrument_type,
            expiry=None,
        ),
        execution_metadata=InstrumentExecutionMetadata(
            provider_instrument_token=binding.provider_instrument_token,
            tick_size=canonical.canonical_tick_size,
            lot_size=canonical.canonical_lot_size,
            price_precision=canonical.canonical_price_precision,
        ),
    )


class IntradayInstrumentRegistry:
    """Immutable fail-closed view of mappings supplied to Intraday."""

    def __init__(self, references: Iterable[IntradayInstrumentReference]) -> None:
        items = tuple(references)
        if not items or any(type(item) is not IntradayInstrumentReference for item in items):
            raise ValueError("INTRADAY_INSTRUMENT_REGISTRY_INVALID")
        by_canonical: dict[str, IntradayInstrumentReference] = {}
        by_provider: dict[tuple[str, int], IntradayInstrumentReference] = {}
        for item in items:
            existing = by_canonical.get(item.canonical_instrument_id)
            provider_key = (item.provider, item.provider_instrument_token)
            provider_existing = by_provider.get(provider_key)
            if (existing is not None and existing != item) or (
                provider_existing is not None and provider_existing != item
            ):
                raise ValueError("INTRADAY_INSTRUMENT_MAPPING_CONFLICT")
            by_canonical[item.canonical_instrument_id] = item
            by_provider[provider_key] = item
        self._references = tuple(by_canonical[key] for key in sorted(by_canonical))
        self._by_canonical = by_canonical

    @property
    def references(self) -> tuple[IntradayInstrumentReference, ...]:
        return self._references

    def resolve(self, canonical_instrument_id: str) -> IntradayInstrumentReference:
        try:
            return self._by_canonical[canonical_instrument_id]
        except (KeyError, TypeError) as error:
            raise ValueError("INTRADAY_INSTRUMENT_MAPPING_UNAVAILABLE") from error


__all__ = [
    "InstrumentExecutionMetadata",
    "IntradayInstrumentRegistry",
    "adapt_instrument_reference",
    "adapt_runtime_instrument",
]
