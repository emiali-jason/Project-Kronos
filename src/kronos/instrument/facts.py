"""DOMAIN-001 canonical execution facts derived from Provider submissions."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from hashlib import sha256
import re

from kronos.provider.contracts.instrument import InstrumentRecord


INSTRUMENT_EXECUTION_CONTEXT_CONTRACT_ID = "KRONOS-INSTRUMENT-EXECUTION-CONTEXT-V1"


class InstrumentContextStatus(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"


def canonical_price_precision(tick_size: object) -> int | None:
    """Return exact canonical decimal precision or UNAVAILABLE as ``None``."""

    try:
        value = tick_size if type(tick_size) is Decimal else Decimal(str(tick_size))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not value.is_finite() or value <= 0:
        return None
    canonical = value.normalize()
    exponent = canonical.as_tuple().exponent
    return max(0, -exponent)


@dataclass(frozen=True, slots=True)
class CanonicalInstrumentContext:
    """Canonical DOMAIN-001 facts; Provider-private identifiers are excluded."""

    identity: str
    canonical_instrument: str
    product: str
    provider: str
    provider_trading_symbol: str
    exchange: str
    segment: str
    instrument_type: str
    tick_size: Decimal | None
    lot_size: int | None
    price_precision: int | None
    status: InstrumentContextStatus
    provenance: tuple[str, ...]
    contract_identity: str = INSTRUMENT_EXECUTION_CONTEXT_CONTRACT_ID

    def __post_init__(self) -> None:
        complete = self.status is InstrumentContextStatus.COMPLETE
        tick_available = self.tick_size is None or (
            type(self.tick_size) is Decimal
            and self.tick_size.is_finite()
            and self.tick_size >= 0
        )
        lot_available = self.lot_size is None or (
            type(self.lot_size) is int and self.lot_size >= 0
        )
        complete_geometry = (
            type(self.tick_size) is Decimal
            and self.tick_size.is_finite()
            and self.tick_size > 0
            and type(self.lot_size) is int
            and self.lot_size > 0
            and type(self.price_precision) is int
            and self.price_precision >= 0
        )
        if (
            self.contract_identity != INSTRUMENT_EXECUTION_CONTEXT_CONTRACT_ID
            or not _identity(self.identity)
            or not self.canonical_instrument
            or not self.product
            or not self.provider
            or not self.provider_trading_symbol
            or not self.exchange
            or not self.segment
            or not self.instrument_type
            or type(self.status) is not InstrumentContextStatus
            or type(self.provenance) is not tuple
            or not self.provenance
            or not tick_available
            or not lot_available
            or complete != complete_geometry
            or (not complete and self.price_precision is not None)
        ):
            raise ValueError("INSTRUMENT_EXECUTION_CONTEXT_INVALID")


def publish_instrument_context(
    canonical_instrument: str,
    product: str,
    record: InstrumentRecord,
) -> CanonicalInstrumentContext:
    """Interpret one Provider fact submission under DOMAIN-001 ownership."""

    if (
        type(record) is not InstrumentRecord
        or not canonical_instrument
        or not product
    ):
        raise ValueError("INSTRUMENT_FACT_SUBMISSION_INVALID")
    precision = canonical_price_precision(record.tick_size)
    complete = (
        type(record.tick_size) is Decimal
        and record.tick_size > 0
        and type(record.lot_size) is int
        and record.lot_size > 0
        and precision is not None
    )
    digest = sha256("|".join((
        canonical_instrument,
        product,
        record.provider,
        record.exchange,
        record.segment,
        record.trading_symbol,
        record.instrument_type,
        str(record.tick_size),
        str(record.lot_size),
    )).encode()).hexdigest()
    return CanonicalInstrumentContext(
        identity=f"INSTRUMENT-CONTEXT-{digest}",
        canonical_instrument=canonical_instrument,
        product=product,
        provider=record.provider,
        provider_trading_symbol=record.trading_symbol,
        exchange=record.exchange,
        segment=record.segment,
        instrument_type=record.instrument_type,
        tick_size=record.tick_size,
        lot_size=record.lot_size,
        price_precision=precision if complete else None,
        status=(
            InstrumentContextStatus.COMPLETE
            if complete
            else InstrumentContextStatus.INCOMPLETE
        ),
        provenance=("DOMAIN-006:EAIC-002", f"KITE:{record.exchange}:{record.trading_symbol}"),
    )


def _identity(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[A-Za-z0-9_.:@|+/-]{1,512}", value) is not None


__all__ = [
    "CanonicalInstrumentContext",
    "INSTRUMENT_EXECUTION_CONTEXT_CONTRACT_ID",
    "InstrumentContextStatus",
    "canonical_price_precision",
    "publish_instrument_context",
]
