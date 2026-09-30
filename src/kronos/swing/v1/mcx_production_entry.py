"""Exact-contract MCX evidence proof candidate, without Step-31 commissioning.

The caller owns the current-pointer read and the WO-05 -> WO-07 commit guard.
This module neither acquires Provider data nor turns a fixture or a retained
historical master into entry authority.  It checks the same source bytes and
current read set at proposal and immediately before a prospective commit.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from contextlib import AbstractContextManager
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from kronos.application.swing_mcx_evidence import McxRetainedMasterMatch
from kronos.swing.v1.mcx_contract_profile import (
    McxFamily, McxRequestBoundCandleLineage, _digest as _lineage_digest,
)
from kronos.swing.v1.mcx_contract_selection import (
    McxSponsorContractSelection, require_mcx_choice_matches_handoff,
    _instrument_value,
)
from kronos.swing.v1.mcx_production_proof import (
    McxCutoffObservation, McxProviderConversionObservation,
    McxSpecificationObservation, inspect_mcx_specification_pdf,
    prepare_mcx_production_proof,
)
from kronos.swing.v1.mcx_quantity import McxTypedQuantity
from kronos.swing.v1.mcx_step31_prepared_handoff import McxStep31PreparedHandoff


_MAX_EVIDENCE_BYTES = 16 * 1024 * 1024
_MAX_MASTER_BYTES = 128 * 1024 * 1024
_IST = ZoneInfo("Asia/Kolkata")


class McxProductionEvidenceRejected(ValueError):
    """Missing, changed or mismatched prospective production facts."""


def _aware(value: object) -> bool:
    return type(value) is datetime and value.tzinfo is not None and value.utcoffset() is not None


def _canonical(value: object) -> bytes:
    def primitive(item: object) -> object:
        if isinstance(item, Decimal):
            return str(item)
        if isinstance(item, (date, datetime)):
            return item.isoformat()
        if isinstance(item, dict):
            return {key: primitive(part) for key, part in item.items()}
        if isinstance(item, (tuple, list)):
            return [primitive(part) for part in item]
        if hasattr(item, "value") and isinstance(item.value, str):
            return item.value
        return item
    return json.dumps(primitive(value), sort_keys=True, separators=(",", ":")).encode()


def _source_hash(path: Path, expected: str, *, limit: int = _MAX_EVIDENCE_BYTES) -> str:
    if (not isinstance(path, Path) or not path.is_absolute() or path.is_symlink()
            or any(parent.is_symlink() for parent in path.parents)
            or type(expected) is not str or len(expected) != 64):
        raise McxProductionEvidenceRejected("MCX_PROOF_SOURCE_INVALID")
    try:
        size = path.stat().st_size
        if not path.is_file() or size <= 0 or size > limit:
            raise McxProductionEvidenceRejected("MCX_PROOF_SOURCE_UNAVAILABLE")
        digest = sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if path.stat().st_size != size or digest.hexdigest() != expected:
            raise McxProductionEvidenceRejected("MCX_PROOF_SOURCE_CHANGED")
        return digest.hexdigest()
    except OSError as error:
        raise McxProductionEvidenceRejected("MCX_PROOF_SOURCE_UNAVAILABLE") from error


@dataclass(frozen=True, slots=True)
class McxProductionReadSet:
    """Owner-selected current objects and original bounded source files."""

    selection: McxSponsorContractSelection
    handoff: McxStep31PreparedHandoff
    lineage: McxRequestBoundCandleLineage
    master: McxRetainedMasterMatch
    master_file: Path
    specification: McxSpecificationObservation
    specification_file: Path
    quantity: McxTypedQuantity
    conversion: McxProviderConversionObservation
    conversion_file: Path
    cutoff: McxCutoffObservation
    exchange_cutoff_file: Path
    broker_cutoff_file: Path


@dataclass(frozen=True, slots=True)
class McxExactContractProof:
    """Immutable factual join; absent policy and commissioning never permit entry."""

    family: McxFamily
    run_identity: str
    selected_contract: str
    selected_expiry: str
    selection_sha256: str
    handoff_sha256: str
    review_receipt_identity: str
    review_receipt_sha256: str
    v2_identity: str
    v2_sha256: str
    master_snapshot_identity: str
    master_record_identity: str
    master_token: int
    master_file_sha256: str
    specification_sha256: str
    conversion_sha256: str
    exchange_cutoff_sha256: str
    broker_cutoff_sha256: str
    completed_daily_sha256: str
    completed_four_hour_sha256: str
    completed_one_hour_sha256: str
    completed_series_sha256: str
    completed_daily_boundary: datetime
    completed_four_hour_boundary: datetime
    completed_one_hour_boundary: datetime
    lots: int
    physical_quantity: Decimal
    physical_unit: str
    provider_order_quantity: int
    provider_order_unit: str
    price_to_rupee_multiplier: Decimal
    gross_notional: Decimal
    rupees_per_tick: Decimal
    gross_stop_risk: Decimal
    fees: None
    margin: None
    missing_authority: tuple[str, ...]
    read_set_sha256: str

    @property
    def permits_new_entry(self) -> bool:
        return False


def _bind(read: McxProductionReadSet, *, observed_at: datetime,
          entry: Decimal, stop: Decimal) -> McxExactContractProof:
    if (type(read) is not McxProductionReadSet or not _aware(observed_at)
            or any(type(price) is not Decimal or not price.is_finite() or price <= 0
                   for price in (entry, stop))):
        raise McxProductionEvidenceRejected("MCX_PROOF_INPUT_INVALID")
    selection, handoff, master = read.selection, read.handoff, read.master
    lineage = read.lineage
    spec, quantity, conversion, cutoff = (
        read.specification, read.quantity, read.conversion, read.cutoff)
    if (type(selection) is not McxSponsorContractSelection
            or type(handoff) is not McxStep31PreparedHandoff
            or type(master) is not McxRetainedMasterMatch
            or type(lineage) is not McxRequestBoundCandleLineage
            or type(spec) is not McxSpecificationObservation
            or type(quantity) is not McxTypedQuantity
            or type(conversion) is not McxProviderConversionObservation
            or type(cutoff) is not McxCutoffObservation):
        raise McxProductionEvidenceRejected("MCX_PROOF_INPUT_INVALID")
    try:
        require_mcx_choice_matches_handoff(selection, handoff)
    except ValueError as error:
        raise McxProductionEvidenceRejected("MCX_PROOF_SELECTION_CHANGED") from error
    contract = master.normalized_contract
    if (selection.recorded_at > handoff.prepared_at
            or handoff.prepared_at > observed_at
            or master.acquired_at > selection.recorded_at
            or selection.instrument_sha256 != sha256(_canonical(
                _instrument_value(contract))).hexdigest()
            or (contract.trading_symbol, contract.expiry.isoformat())
               != (selection.trading_symbol, selection.expiry)
            or (contract.provider, contract.exchange, contract.segment,
                contract.instrument_type) != ("KITE", "MCX", "MCX-FUT", "FUT")
            or master.provider_instrument_token != conversion.provider_instrument_token):
        raise McxProductionEvidenceRejected("MCX_PROOF_MASTER_SELECTION_MISMATCH")
    if (lineage.run_identity != selection.run_identity
            or lineage.family is not selection.family
            or lineage.trading_symbol != contract.trading_symbol
            or lineage.expiry != selection.expiry
            or lineage.normalized_instrument_sha256 != _lineage_digest(asdict(contract))
            or handoff.bound.request_bound_lineage_sha256 != _lineage_digest(asdict(lineage))
            or handoff.bound.completed_one_hour_sha256 != lineage.completed_1h_sha256):
        raise McxProductionEvidenceRejected("MCX_PROOF_CANDLE_CONTRACT_MISMATCH")
    if (entry / spec.tick_size != (entry / spec.tick_size).to_integral_value()
            or stop / spec.tick_size != (stop / spec.tick_size).to_integral_value()
            or entry == stop):
        raise McxProductionEvidenceRejected("MCX_PROOF_PRICE_TICK_INVALID")
    try:
        inspect_mcx_specification_pdf(
            read.specification_file, family=spec.family,
            source_url=spec.source_url, expected_sha256=spec.document_sha256,
            effective_from=spec.effective_from,
            effective_through=spec.effective_through,
            physical_quantity_per_lot=spec.physical_quantity_per_lot,
            physical_unit=spec.physical_unit,
            quotation_base_quantity=spec.quotation_base_quantity,
            quotation_unit=spec.quotation_unit, tick_size=spec.tick_size,
            settlement=spec.settlement, origin=spec.origin,
        )
        checked = prepare_mcx_production_proof(
            family=selection.family, master=master, observed_at=observed_at,
            specification=spec, quantity=quantity, conversion=conversion,
            cutoff=cutoff,
        )
    except ValueError as error:
        raise McxProductionEvidenceRejected("MCX_PROOF_FACT_MISMATCH") from error
    _source_hash(read.master_file, master.snapshot_file_sha256,
                 limit=_MAX_MASTER_BYTES)
    for path, expected in (
        (read.conversion_file, conversion.evidence_sha256),
        (read.exchange_cutoff_file, cutoff.exchange_source_sha256),
        (read.broker_cutoff_file, cutoff.broker_source_sha256),
    ):
        _source_hash(path, expected)
    if (checked.trading_symbol != handoff.bound.derivative_symbol
            or checked.expiry.isoformat() != handoff.bound.derivative_expiry
            or checked.provider_instrument_token != master.provider_instrument_token
            or cutoff.exchange_session_close is None
            or cutoff.exchange_session_close.astimezone(_IST).date() != contract.expiry
            or spec.family is not handoff.bound.family):
        raise McxProductionEvidenceRejected("MCX_PROOF_HANDOFF_MISMATCH")
    reasons = tuple(dict.fromkeys((*checked.missing_authority,
        "MCX_NUMERIC_RISK_POLICY_UNAPPROVED",
        "MCX_COMPLETED_1H_KR380_ISSUER_UNCOMMISSIONED",
        "MCX_STEP31_NOT_COMMISSIONED")))
    identity = sha256(_canonical({
        "selection": selection.integrity_sha256,
        "handoff": handoff.integrity_sha256,
        "lineage": asdict(lineage),
        "master": asdict(master),
        "specification": asdict(spec),
        "quantity": asdict(quantity),
        "conversion": asdict(conversion),
        "cutoff": asdict(cutoff),
        "entry": entry, "stop": stop,
    })).hexdigest()
    return McxExactContractProof(
        family=selection.family, run_identity=selection.run_identity,
        selected_contract=selection.trading_symbol,
        selected_expiry=selection.expiry,
        selection_sha256=selection.integrity_sha256,
        handoff_sha256=handoff.integrity_sha256,
        review_receipt_identity=handoff.bound.receipt_identity,
        review_receipt_sha256=handoff.bound.receipt_integrity_sha256,
        v2_identity=handoff.bound.promotion_identity,
        v2_sha256=handoff.bound.promotion_integrity_sha256,
        master_snapshot_identity=master.snapshot_identity,
        master_record_identity=master.record_identity,
        master_token=master.provider_instrument_token,
        master_file_sha256=master.snapshot_file_sha256,
        specification_sha256=spec.document_sha256,
        conversion_sha256=conversion.evidence_sha256,
        exchange_cutoff_sha256=cutoff.exchange_source_sha256,
        broker_cutoff_sha256=cutoff.broker_source_sha256,
        completed_daily_sha256=lineage.completed_1d_sha256,
        completed_four_hour_sha256=lineage.completed_4h_sha256,
        completed_one_hour_sha256=handoff.bound.completed_one_hour_sha256,
        completed_series_sha256=lineage.completed_series_sha256,
        completed_daily_boundary=lineage.completed_1d_boundary,
        completed_four_hour_boundary=lineage.completed_4h_boundary,
        completed_one_hour_boundary=handoff.bound.completed_one_hour_boundary,
        lots=quantity.lots, physical_quantity=quantity.physical_quantity,
        physical_unit=quantity.physical_unit,
        provider_order_quantity=quantity.provider_order_quantity,
        provider_order_unit=quantity.provider_order_unit,
        price_to_rupee_multiplier=quantity.price_to_rupee_multiplier,
        gross_notional=quantity.notional(entry),
        rupees_per_tick=spec.rupees_per_tick_per_lot * quantity.lots,
        gross_stop_risk=quantity.stop_risk(entry, stop),
        fees=None, margin=None, missing_authority=reasons,
        read_set_sha256=identity,
    )


def issue_mcx_exact_contract_proof(
    current: Callable[[], McxProductionReadSet], *, observed_at: datetime,
    entry: Decimal, stop: Decimal,
) -> McxExactContractProof:
    """Read twice to fence a changed pointer or source before returning proof."""
    if not callable(current):
        raise McxProductionEvidenceRejected("MCX_PROOF_INPUT_INVALID")
    first = _bind(current(), observed_at=observed_at, entry=entry, stop=stop)
    second = _bind(current(), observed_at=observed_at, entry=entry, stop=stop)
    if first != second:
        raise McxProductionEvidenceRejected("MCX_PROOF_READ_SET_CHANGED")
    return first


def require_mcx_proof_current_at_commit(
    proof: McxExactContractProof,
    current: Callable[[], McxProductionReadSet], *, observed_at: datetime,
    entry: Decimal, stop: Decimal,
    commit_guard: Callable[[], AbstractContextManager[object]],
) -> None:
    """Owner WO-05 -> WO-07 guard encloses the last read and decision."""
    if type(proof) is not McxExactContractProof or not callable(commit_guard):
        raise McxProductionEvidenceRejected("MCX_PROOF_INPUT_INVALID")
    with commit_guard():
        actual = issue_mcx_exact_contract_proof(
            current, observed_at=observed_at, entry=entry, stop=stop)
        if proof != actual:
            raise McxProductionEvidenceRejected("MCX_PROOF_STALE_AT_COMMIT")
        if actual.missing_authority:
            raise McxProductionEvidenceRejected("MCX_STEP31_NOT_COMMISSIONED")


__all__ = ["McxExactContractProof", "McxProductionEvidenceRejected",
           "McxProductionReadSet", "issue_mcx_exact_contract_proof",
           "require_mcx_proof_current_at_commit"]
