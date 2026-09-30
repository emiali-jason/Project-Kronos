"""Isolated proof preparation never confers production MCX entry authority."""

from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from kronos.application.swing_mcx_evidence import McxRetainedMasterMatch
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.swing.v1.mcx_contract_profile import McxFamily, mcx_unit_profile
from kronos.swing.v1.mcx_production_proof import (
    McxCutoffObservation, McxObservationOrigin,
    McxProviderConversionObservation, inspect_mcx_specification_pdf,
    prepare_mcx_production_proof,
)
from kronos.swing.v1.mcx_quantity import McxQuantityProofOrigin, McxTypedQuantity


IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 9, 29, 12, 0, tzinfo=IST)
EXPIRY = date(2026, 10, 20)
HASH = "a" * 64


def _facts(family: McxFamily, tmp_path: Path):
    profile = mcx_unit_profile(family)
    symbol = f"{family.value}26OCTFUT"
    instrument = InstrumentRecord(
        "KITE", "MCX", "MCX-FUT", symbol, family.value, "FUT",
        EXPIRY, profile.tick_in_quotation_units, 1,
    )
    master = McxRetainedMasterMatch(
        "ISOLATED-SNAPSHOT", "ISOLATED-RECORD", HASH, NOW - timedelta(days=1),
        instrument, 123456, "ISOLATED-INTEGRITY",
        NOW - timedelta(days=1), NOW - timedelta(days=1), None,
    )
    pdf = tmp_path / f"{family.value}.pdf"
    pdf.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n")
    pdf_hash = sha256(pdf.read_bytes()).hexdigest()
    specification = inspect_mcx_specification_pdf(
        pdf, family=family, source_url=profile.exchange_specification_url,
        expected_sha256=pdf_hash,
        effective_from=date(2026, 8, 1), effective_through=None,
        physical_quantity_per_lot=profile.trading_quantity,
        physical_unit=profile.trading_unit,
        quotation_base_quantity=profile.quotation_quantity,
        quotation_unit=profile.quotation_unit,
        tick_size=profile.tick_in_quotation_units,
        settlement=profile.settlement,
        origin=McxObservationOrigin.ISOLATED_FIXTURE,
    )
    quantity = McxTypedQuantity(
        2, profile.trading_quantity, profile.trading_unit,
        profile.quotation_quantity, profile.quotation_unit,
        profile.quotation_multiplier_per_lot, 2, "LOTS", HASH,
        McxQuantityProofOrigin.ISOLATED_FIXTURE,
    )
    conversion = McxProviderConversionObservation(
        master.snapshot_identity, master.record_identity,
        master.provider_instrument_token, symbol, "LOTS", 1, HASH,
        McxObservationOrigin.ISOLATED_FIXTURE,
    )
    cutoff = McxCutoffObservation(
        symbol, EXPIRY, datetime(2026, 10, 20, 17, tzinfo=IST),
        datetime(2026, 10, 20, 15, tzinfo=IST),
        datetime(2026, 10, 20, 14, tzinfo=IST),
        datetime(2026, 10, 20, 16, tzinfo=IST),
        datetime(2026, 10, 20, 13, tzinfo=IST)
        if profile.settlement.value == "PHYSICAL" else None,
        HASH, HASH, McxObservationOrigin.ISOLATED_FIXTURE,
    )
    return master, specification, quantity, conversion, cutoff


@pytest.mark.parametrize("family", tuple(McxFamily))
def test_five_families_are_exactly_typed_but_fixture_cannot_issue_authority(
    family, tmp_path,
):
    master, specification, quantity, conversion, cutoff = _facts(family, tmp_path)
    inspected = prepare_mcx_production_proof(
        family=family, master=master, observed_at=NOW,
        specification=specification, quantity=quantity,
        conversion=conversion, cutoff=cutoff,
    )
    assert inspected.provider_instrument_token == master.provider_instrument_token
    assert inspected.trading_symbol == master.normalized_contract.trading_symbol
    assert inspected.expiry == EXPIRY
    assert specification.quotation_multiplier_per_lot == quantity.rupees_per_price_point_per_lot
    assert specification.rupees_per_tick_per_lot == (
        profile := mcx_unit_profile(family)
    ).rupees_per_tick_per_lot
    assert quantity.notional(Decimal("100")) == Decimal("200") * profile.quotation_multiplier_per_lot
    assert inspected.permits_new_entry is False
    assert "MCX_CURRENT_MASTER_VALIDITY_UNPROVEN" in inspected.missing_authority
    assert "MCX_EFFECTIVE_SPECIFICATION_APPROVAL_UNAVAILABLE" in inspected.missing_authority
    assert "MCX_EXACT_PROVIDER_QUANTITY_CONVERSION_UNAPPROVED" in inspected.missing_authority
    assert "MCX_CUTOFF_AUTHORITY_UNAPPROVED" in inspected.missing_authority


def test_incorrect_units_and_conflicting_contract_identity_reject(tmp_path):
    master, spec, quantity, conversion, cutoff = _facts(McxFamily.COPPER, tmp_path)
    # An effective series can differ from the illustrative table; its bytes
    # and approval remain a separate authority gate, and quantity must match.
    changed_series = prepare_mcx_production_proof(
        family=McxFamily.COPPER, master=master, observed_at=NOW,
        specification=replace(spec, physical_quantity_per_lot=Decimal("1")),
    )
    assert not changed_series.permits_new_entry
    assert "MCX_EFFECTIVE_SPECIFICATION_APPROVAL_UNAVAILABLE" in changed_series.missing_authority
    with pytest.raises(ValueError, match="QUANTITY_SPECIFICATION_MISMATCH"):
        prepare_mcx_production_proof(
            family=McxFamily.COPPER, master=master, observed_at=NOW,
            specification=spec,
            quantity=replace(quantity, physical_quantity_per_lot=Decimal("1"),
                             rupees_per_price_point_per_lot=Decimal("1")),
            conversion=conversion, cutoff=cutoff,
        )
    with pytest.raises(ValueError, match="PROVIDER_CONVERSION_CONTRACT_MISMATCH"):
        prepare_mcx_production_proof(
            family=McxFamily.COPPER, master=master, observed_at=NOW,
            specification=spec, quantity=quantity,
            conversion=replace(conversion, provider_instrument_token=999),
            cutoff=cutoff,
        )
    with pytest.raises(ValueError, match="CUTOFF_CONTRACT_MISMATCH"):
        prepare_mcx_production_proof(
            family=McxFamily.COPPER, master=master, observed_at=NOW,
            specification=spec, quantity=quantity,
            conversion=conversion, cutoff=replace(cutoff, expiry=date(2026, 11, 20)),
        )


def test_stale_and_missing_facts_withhold_authority(tmp_path):
    master, spec, quantity, conversion, cutoff = _facts(McxFamily.GOLDM, tmp_path)
    with pytest.raises(ValueError, match="PRODUCTION_PROOF_INPUT_INVALID"):
        prepare_mcx_production_proof(
            family=McxFamily.GOLDM, master=replace(master, acquired_at=NOW + timedelta(seconds=1)),
            observed_at=NOW,
        )
    with pytest.raises(ValueError, match="SPECIFICATION_CONTRACT_MISMATCH"):
        prepare_mcx_production_proof(
            family=McxFamily.GOLDM, master=master, observed_at=NOW,
            specification=replace(spec, effective_through=date(2026, 9, 30)),
        )
    inspection = prepare_mcx_production_proof(
        family=McxFamily.GOLDM, master=master, observed_at=NOW,
    )
    assert inspection.permits_new_entry is False
    assert "MCX_EFFECTIVE_SPECIFICATION_BYTES_UNAVAILABLE" in inspection.missing_authority
    assert "MCX_EXACT_PROVIDER_QUANTITY_CONVERSION_UNAVAILABLE" in inspection.missing_authority
    assert "MCX_EXCHANGE_CUTOFF_UNAVAILABLE" in inspection.missing_authority
    assert "MCX_BROKER_CUTOFF_UNAVAILABLE" in inspection.missing_authority


def test_cutoff_boundaries_block_new_entry_without_removing_exit_obligation(tmp_path):
    _, spec, _, _, cutoff = _facts(McxFamily.COPPER, tmp_path)
    assert cutoff.entry_reasons(NOW, spec.settlement) == ()
    assert "MCX_DELIVERY_TENDER_ACTIVE" in cutoff.entry_reasons(
        cutoff.delivery_or_tender_start, spec.settlement,
    )
    assert "MCX_BROKER_ENTRY_CLOSED" in cutoff.entry_reasons(
        cutoff.broker_entry_until, spec.settlement,
    )
    assert "MCX_EXCHANGE_SESSION_CLOSED" in cutoff.entry_reasons(
        cutoff.exchange_session_close, spec.settlement,
    )
    assert "MCX_MANDATORY_EXIT_REACHED" in cutoff.entry_reasons(
        cutoff.mandatory_exit_at, spec.settlement,
    )
    with pytest.raises(ValueError, match="CUTOFF_OBSERVATION_INVALID"):
        replace(cutoff, last_entry_at=cutoff.mandatory_exit_at + timedelta(seconds=1))
    assert cutoff.mandatory_exit_at != cutoff.last_entry_at


def test_pdf_bytes_and_missing_conversion_fail_closed(tmp_path):
    master, spec, quantity, conversion, cutoff = _facts(McxFamily.SILVERM, tmp_path)
    pdf = tmp_path / "SILVERM.pdf"
    pdf.write_bytes(pdf.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="SPECIFICATION_BYTES_MISMATCH"):
        inspect_mcx_specification_pdf(
            pdf, family=McxFamily.SILVERM, source_url=spec.source_url,
            expected_sha256=spec.document_sha256,
            effective_from=spec.effective_from, effective_through=None,
            physical_quantity_per_lot=spec.physical_quantity_per_lot,
            physical_unit=spec.physical_unit,
            quotation_base_quantity=spec.quotation_base_quantity,
            quotation_unit=spec.quotation_unit, tick_size=spec.tick_size,
            settlement=spec.settlement,
            origin=McxObservationOrigin.ISOLATED_FIXTURE,
        )
    with pytest.raises(ValueError, match="PROVIDER_CONVERSION_CONTRACT_MISMATCH"):
        prepare_mcx_production_proof(
            family=McxFamily.SILVERM, master=master, observed_at=NOW,
            specification=spec, quantity=quantity,
            conversion=replace(conversion, provider_quantity_per_lot=5),
            cutoff=cutoff,
        )


def test_later_effective_series_needs_its_own_official_bytes(tmp_path):
    _, spec, _, _, _ = _facts(McxFamily.SILVERM, tmp_path)
    later_url = (
        "https://www.mcxindia.com/docs/default-source/products/"
        "contract-specification/synthetic-test-only.pdf"
    )
    later = replace(spec, source_url=later_url, effective_from=date(2027, 2, 1))
    assert later.source_url == later_url
    assert later.origin is McxObservationOrigin.ISOLATED_FIXTURE
    with pytest.raises(ValueError, match="SPECIFICATION_OBSERVATION_INVALID"):
        replace(later, source_url="https://example.com/specification.pdf")
