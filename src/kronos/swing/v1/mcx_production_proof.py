"""Read-only MCX production-proof preparation; no commissioning issuer.

The retained master is historical. Public specification URLs, illustrative unit
tables and isolated fixtures cannot create a current contract proof. This
module validates exact-contract relationships and reports the missing authority
without writing evidence or enabling Step-31.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
import re
from urllib.parse import urlsplit

from kronos.application.swing_mcx_evidence import McxRetainedMasterMatch
from kronos.swing.v1.mcx_contract_profile import (
    McxFamily, McxSettlement, mcx_contract_name_matches, mcx_unit_profile,
)
from kronos.swing.v1.mcx_quantity import McxTypedQuantity


_MAX_PDF_BYTES = 16 * 1024 * 1024


class McxObservationOrigin(StrEnum):
    ISOLATED_FIXTURE = "ISOLATED_FIXTURE"
    PUBLIC_UNAPPROVED = "PUBLIC_UNAPPROVED"
    RETAINED_UNVERIFIED = "RETAINED_UNVERIFIED"


def _aware(value: object) -> bool:
    return type(value) is datetime and value.tzinfo is not None and value.utcoffset() is not None


def _digest(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _official_specification_url(value: object) -> bool:
    if type(value) is not str:
        return False
    parsed = urlsplit(value)
    return (
        parsed.scheme == "https" and parsed.netloc == "www.mcxindia.com"
        and parsed.path.startswith("/docs/default-source/")
        and parsed.path.endswith(".pdf")
        and not parsed.query and not parsed.fragment
    )


@dataclass(frozen=True, slots=True)
class McxSpecificationObservation:
    family: McxFamily
    source_url: str
    document_sha256: str
    effective_from: date
    effective_through: date | None
    physical_quantity_per_lot: Decimal
    physical_unit: str
    quotation_base_quantity: Decimal
    quotation_unit: str
    tick_size: Decimal
    settlement: McxSettlement
    origin: McxObservationOrigin

    def __post_init__(self) -> None:
        if (
            type(self.family) is not McxFamily
            or not _official_specification_url(self.source_url)
            or not _digest(self.document_sha256)
            or type(self.effective_from) is not date
            or (self.effective_through is not None and (
                type(self.effective_through) is not date
                or self.effective_through < self.effective_from
            ))
            or any(type(v) is not Decimal or not v.is_finite() or v <= 0 for v in (
                self.physical_quantity_per_lot, self.quotation_base_quantity,
                self.tick_size,
            ))
            or not self.physical_unit or self.physical_unit != self.quotation_unit
            or type(self.settlement) is not McxSettlement
            or type(self.origin) is not McxObservationOrigin
        ):
            raise ValueError("MCX_SPECIFICATION_OBSERVATION_INVALID")

    @property
    def quotation_multiplier_per_lot(self) -> Decimal:
        return self.physical_quantity_per_lot / self.quotation_base_quantity

    @property
    def rupees_per_tick_per_lot(self) -> Decimal:
        return self.tick_size * self.quotation_multiplier_per_lot

    def applies_to(self, expiry: date) -> bool:
        return (
            type(expiry) is date
            and expiry >= self.effective_from
            and (self.effective_through is None or expiry <= self.effective_through)
        )


def inspect_mcx_specification_pdf(
    path: Path, *, family: McxFamily, source_url: str,
    expected_sha256: str,
    effective_from: date, effective_through: date | None,
    physical_quantity_per_lot: Decimal, physical_unit: str,
    quotation_base_quantity: Decimal, quotation_unit: str,
    tick_size: Decimal, settlement: McxSettlement,
    origin: McxObservationOrigin,
) -> McxSpecificationObservation:
    """Bind bytes to declared facts, without treating a URL as approval.

    The facts must be independently reviewed against these exact PDF bytes.
    This function deliberately has no APPROVED origin or authority output.
    """

    if not isinstance(path, Path) or not path.is_absolute() or path.is_symlink():
        raise ValueError("MCX_SPECIFICATION_PATH_INVALID")
    if any(parent.is_symlink() for parent in path.parents):
        raise ValueError("MCX_SPECIFICATION_PATH_INVALID")
    if not _digest(expected_sha256):
        raise ValueError("MCX_SPECIFICATION_HASH_INVALID")
    try:
        if not path.is_file() or path.stat().st_size > _MAX_PDF_BYTES:
            raise ValueError("MCX_SPECIFICATION_BYTES_UNAVAILABLE")
        raw = path.read_bytes()
    except OSError as error:
        raise ValueError("MCX_SPECIFICATION_BYTES_UNAVAILABLE") from error
    if (
        not raw.startswith(b"%PDF-")
        or b"%%EOF" not in raw[-1024:]
        or sha256(raw).hexdigest() != expected_sha256
    ):
        raise ValueError("MCX_SPECIFICATION_BYTES_MISMATCH")
    return McxSpecificationObservation(
        family, source_url,
        expected_sha256, effective_from, effective_through,
        physical_quantity_per_lot, physical_unit,
        quotation_base_quantity, quotation_unit, tick_size, settlement, origin,
    )


@dataclass(frozen=True, slots=True)
class McxProviderConversionObservation:
    snapshot_identity: str
    record_identity: str
    provider_instrument_token: int
    trading_symbol: str
    provider_order_unit: str
    provider_quantity_per_lot: int
    evidence_sha256: str
    origin: McxObservationOrigin

    def __post_init__(self) -> None:
        if (
            not self.snapshot_identity or not self.record_identity
            or type(self.provider_instrument_token) is not int
            or self.provider_instrument_token <= 0
            or not self.trading_symbol
            or self.provider_order_unit not in {"LOTS", "BASE_UNITS"}
            or type(self.provider_quantity_per_lot) is not int
            or self.provider_quantity_per_lot <= 0
            or not _digest(self.evidence_sha256)
            or type(self.origin) is not McxObservationOrigin
        ):
            raise ValueError("MCX_PROVIDER_CONVERSION_INVALID")


@dataclass(frozen=True, slots=True)
class McxCutoffObservation:
    trading_symbol: str
    expiry: date
    exchange_session_close: datetime | None
    last_entry_at: datetime | None
    broker_entry_until: datetime | None
    mandatory_exit_at: datetime | None
    delivery_or_tender_start: datetime | None
    exchange_source_sha256: str | None
    broker_source_sha256: str | None
    origin: McxObservationOrigin

    def __post_init__(self) -> None:
        values = (
            self.exchange_session_close, self.last_entry_at,
            self.broker_entry_until, self.mandatory_exit_at,
            self.delivery_or_tender_start,
        )
        if (
            not self.trading_symbol or type(self.expiry) is not date
            or any(v is not None and not _aware(v) for v in values)
            or any(v is not None and not _digest(v) for v in (
                self.exchange_source_sha256, self.broker_source_sha256,
            ))
            or type(self.origin) is not McxObservationOrigin
            or (self.exchange_session_close is not None and any(
                v is not None and v > self.exchange_session_close
                for v in (self.last_entry_at, self.broker_entry_until,
                          self.mandatory_exit_at)
            ))
            or (self.mandatory_exit_at is not None and any(
                v is not None and v > self.mandatory_exit_at
                for v in (self.last_entry_at, self.broker_entry_until)
            ))
        ):
            raise ValueError("MCX_CUTOFF_OBSERVATION_INVALID")

    def entry_reasons(self, observed_at: datetime, settlement: McxSettlement) -> tuple[str, ...]:
        if not _aware(observed_at) or type(settlement) is not McxSettlement:
            raise ValueError("MCX_CUTOFF_CHECK_INVALID")
        reasons = []
        for name, value in (
            ("EXCHANGE_SESSION", self.exchange_session_close),
            ("LAST_ENTRY", self.last_entry_at),
            ("BROKER_ENTRY", self.broker_entry_until),
        ):
            if value is None:
                reasons.append(f"MCX_{name}_UNVERIFIED")
            elif observed_at >= value:
                reasons.append(f"MCX_{name}_CLOSED")
        if settlement is McxSettlement.PHYSICAL:
            if self.delivery_or_tender_start is None:
                reasons.append("MCX_DELIVERY_TENDER_UNVERIFIED")
            elif observed_at >= self.delivery_or_tender_start:
                reasons.append("MCX_DELIVERY_TENDER_ACTIVE")
        if self.mandatory_exit_at is None:
            reasons.append("MCX_MANDATORY_EXIT_UNVERIFIED")
        elif observed_at >= self.mandatory_exit_at:
            reasons.append("MCX_MANDATORY_EXIT_REACHED")
        return tuple(reasons)


@dataclass(frozen=True, slots=True)
class McxProductionProofPreparation:
    family: McxFamily
    trading_symbol: str
    provider_instrument_token: int
    expiry: date
    snapshot_identity: str
    record_identity: str
    specification_sha256: str | None
    conversion_sha256: str | None
    exchange_cutoff_sha256: str | None
    broker_cutoff_sha256: str | None
    missing_authority: tuple[str, ...]

    @property
    def permits_new_entry(self) -> bool:
        # Slice 1 has no production issuer, approved specification registry,
        # current-master validity, or commissioned Step-31 integration.
        return False


def prepare_mcx_production_proof(
    *, family: McxFamily, master: McxRetainedMasterMatch,
    observed_at: datetime,
    specification: McxSpecificationObservation | None = None,
    quantity: McxTypedQuantity | None = None,
    conversion: McxProviderConversionObservation | None = None,
    cutoff: McxCutoffObservation | None = None,
) -> McxProductionProofPreparation:
    """Check a prospective contract's facts; never issue entry authority."""

    if (
        type(family) is not McxFamily
        or type(master) is not McxRetainedMasterMatch
        or not _aware(observed_at)
        or not mcx_contract_name_matches(family, master.normalized_contract)
        or master.normalized_contract.expiry is None
        or master.acquired_at > observed_at
    ):
        raise ValueError("MCX_PRODUCTION_PROOF_INPUT_INVALID")
    instrument = master.normalized_contract
    if specification is not None and (
        type(specification) is not McxSpecificationObservation
        or specification.family is not family
        or not specification.applies_to(instrument.expiry)
        or specification.tick_size != instrument.tick_size
    ):
        raise ValueError("MCX_SPECIFICATION_CONTRACT_MISMATCH")
    # The retained unit profile is illustrative.  A later effective contract
    # series must be checked against its own reviewed specification bytes and
    # exact Provider conversion, never rejected solely for differing from the
    # example profile (or accepted merely because it happens to match it).
    if quantity is not None and (
        type(quantity) is not McxTypedQuantity
        or specification is None
        or quantity.physical_quantity_per_lot != specification.physical_quantity_per_lot
        or quantity.physical_unit != specification.physical_unit
        or quantity.quotation_base_quantity != specification.quotation_base_quantity
        or quantity.quotation_unit != specification.quotation_unit
        or quantity.rupees_per_price_point_per_lot
           != specification.quotation_multiplier_per_lot
    ):
        raise ValueError("MCX_QUANTITY_SPECIFICATION_MISMATCH")
    if conversion is not None and (
        type(conversion) is not McxProviderConversionObservation
        or conversion.snapshot_identity != master.snapshot_identity
        or conversion.record_identity != master.record_identity
        or conversion.provider_instrument_token != master.provider_instrument_token
        or conversion.trading_symbol != instrument.trading_symbol
        or (quantity is not None and (
            quantity.provider_order_unit != conversion.provider_order_unit
            or quantity.provider_order_quantity
               != conversion.provider_quantity_per_lot * quantity.lots
            or quantity.provider_conversion_identity != conversion.evidence_sha256
        ))
    ):
        raise ValueError("MCX_PROVIDER_CONVERSION_CONTRACT_MISMATCH")
    if cutoff is not None and (
        type(cutoff) is not McxCutoffObservation
        or cutoff.trading_symbol != instrument.trading_symbol
        or cutoff.expiry != instrument.expiry
    ):
        raise ValueError("MCX_CUTOFF_CONTRACT_MISMATCH")
    missing = ["MCX_CURRENT_MASTER_VALIDITY_UNPROVEN"]
    if master.provider_validity_assertion is None:
        missing.append("MCX_PROVIDER_VALIDITY_ASSERTION_ABSENT")
    if specification is None:
        missing.append("MCX_EFFECTIVE_SPECIFICATION_BYTES_UNAVAILABLE")
    else:
        missing.append("MCX_EFFECTIVE_SPECIFICATION_APPROVAL_UNAVAILABLE")
    if quantity is None or conversion is None:
        missing.append("MCX_EXACT_PROVIDER_QUANTITY_CONVERSION_UNAVAILABLE")
    else:
        missing.append("MCX_EXACT_PROVIDER_QUANTITY_CONVERSION_UNAPPROVED")
    if cutoff is None:
        missing.extend(("MCX_EXCHANGE_CUTOFF_UNAVAILABLE", "MCX_BROKER_CUTOFF_UNAVAILABLE"))
    else:
        missing.extend(cutoff.entry_reasons(observed_at,
            specification.settlement if specification is not None else mcx_unit_profile(family).settlement))
        missing.append("MCX_CUTOFF_AUTHORITY_UNAPPROVED")
    return McxProductionProofPreparation(
        family, instrument.trading_symbol, master.provider_instrument_token,
        instrument.expiry, master.snapshot_identity, master.record_identity,
        None if specification is None else specification.document_sha256,
        None if conversion is None else conversion.evidence_sha256,
        None if cutoff is None else cutoff.exchange_source_sha256,
        None if cutoff is None else cutoff.broker_source_sha256,
        tuple(dict.fromkeys(missing)),
    )


__all__ = [
    "McxCutoffObservation", "McxObservationOrigin",
    "McxProductionProofPreparation", "McxProviderConversionObservation",
    "McxSpecificationObservation", "inspect_mcx_specification_pdf",
    "prepare_mcx_production_proof",
]
