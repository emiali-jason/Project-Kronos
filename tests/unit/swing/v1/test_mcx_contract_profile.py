from dataclasses import replace
from decimal import Decimal
from datetime import date

import pytest

from kronos.provider.contracts.instrument import InstrumentRecord

from kronos.swing.v1.mcx_contract_profile import (
    McxEntryFactState,
    McxFamily,
    McxSettlement,
    mcx_contract_name_matches,
    mcx_lineage_matches_completed_facts,
    mcx_unit_profile,
)
from kronos.swing.v1.mcx_quantity import (
    McxQuantityProofOrigin, McxTypedQuantity, quantity_from_dict,
)
from kronos.swing.v1.mtf_facts import (
    FactualTimeframe,
    MtfFactEvidenceStore,
)
from tests.unit.application.test_swing_mtf_facts import RUN_ID, _build


@pytest.mark.parametrize(
    "family,quote_multiplier,tick_value,entry,stop,notional,stop_risk,settlement",
    (
        (McxFamily.GOLDM, "10", "10", "75000", "74900", "750000", "1000", McxSettlement.PHYSICAL),
        (McxFamily.SILVERM, "5", "5", "100000", "99000", "500000", "5000", McxSettlement.PHYSICAL),
        (McxFamily.COPPER, "2500", "125", "900", "890", "2250000", "25000", McxSettlement.PHYSICAL),
        (McxFamily.CRUDEOIL, "100", "100", "6000", "5900", "600000", "10000", McxSettlement.CASH),
        (McxFamily.NATURALGAS, "1250", "125", "300", "290", "375000", "12500", McxSettlement.CASH),
    ),
)
def test_effective_2026_unit_geometry_is_quote_normalized_and_non_authorizing(
    family, quote_multiplier, tick_value, entry, stop, notional, stop_risk, settlement,
) -> None:
    profile = mcx_unit_profile(family)
    assert profile.quotation_multiplier_per_lot == Decimal(quote_multiplier)
    assert profile.rupees_per_tick_per_lot == Decimal(tick_value)
    assert profile.settlement is settlement
    assert profile.verified_specification_sha256 is None
    assert profile.provider_order_quantity_semantics is None
    assert profile.approved_entry_blackout_identity is None
    assert not profile.permits_new_entry
    assert profile.illustrative_price_exposure(
        entry=Decimal(entry), stop=Decimal(stop), lots=1,
    ) == (Decimal(notional), Decimal(stop_risk))
    assert profile.exchange_specification_url.startswith("https://www.mcxindia.com/")
    with pytest.raises(ValueError, match="MCX_PRICE_EXPOSURE_INPUT_INVALID"):
        profile.illustrative_price_exposure(
            entry=Decimal(entry), stop=Decimal(stop), lots=0,
        )


@pytest.mark.parametrize("family,entry,stop,notional,stop_risk", (
    (McxFamily.GOLDM, "75000", "74900", "750000", "1000"),
    (McxFamily.SILVERM, "100000", "99000", "500000", "5000"),
    (McxFamily.COPPER, "900", "890", "2250000", "25000"),
    (McxFamily.CRUDEOIL, "6000", "5900", "600000", "10000"),
    (McxFamily.NATURALGAS, "300", "290", "375000", "12500"),
))
def test_typed_quantity_separates_physical_quote_and_provider_order(
    family, entry, stop, notional, stop_risk,
) -> None:
    profile = mcx_unit_profile(family)
    quantity = McxTypedQuantity(
        lots=1, physical_quantity_per_lot=profile.trading_quantity,
        physical_unit=profile.trading_unit,
        quotation_base_quantity=profile.quotation_quantity,
        quotation_unit=profile.quotation_unit,
        rupees_per_price_point_per_lot=profile.quotation_multiplier_per_lot,
        provider_order_quantity=1, provider_order_unit="LOTS",
        provider_conversion_identity="ISOLATED-CONVERSION-" + family.value,
        proof_origin=McxQuantityProofOrigin.ISOLATED_FIXTURE,
    )
    assert quantity.physical_quantity == profile.trading_quantity
    assert quantity.price_to_rupee_multiplier == profile.quotation_multiplier_per_lot
    assert quantity.notional(Decimal(entry)) == Decimal(notional)
    assert quantity.stop_risk(Decimal(entry), Decimal(stop)) == Decimal(stop_risk)
    assert quantity.provider_order_quantity == 1
    assert quantity_from_dict({
        name: str(getattr(quantity, name)) if isinstance(getattr(quantity, name), Decimal)
        else getattr(quantity, name)
        for name in quantity.__dataclass_fields__
    }) == quantity
    if family is McxFamily.GOLDM:
        assert quantity.physical_quantity == Decimal("100")
        assert quantity.quotation_base_quantity == Decimal("10")
        assert quantity.price_to_rupee_multiplier == Decimal("10")
        assert quantity.provider_order_quantity == 1
    with pytest.raises(ValueError, match="MCX_TYPED_QUANTITY_INVALID"):
        replace(quantity, provider_conversion_identity="")
    with pytest.raises(ValueError, match="MCX_TYPED_QUANTITY_INVALID"):
        replace(quantity, provider_order_quantity=2)
    with pytest.raises(ValueError, match="MCX_TYPED_QUANTITY_INVALID"):
        replace(quantity, provider_order_unit="BASE_UNITS")


def test_mcx_lineage_retains_exact_requested_future_for_all_five_families(tmp_path) -> None:
    snapshot, requests = _build(
        retain_completed_series=True, retain_mcx_lineage=True,
    )
    mcx = tuple(snapshot.instrument(family.value) for family in McxFamily)
    assert len(mcx) == 5
    for instrument in mcx:
        lineage = instrument.mcx_request_lineage
        assert lineage is not None
        assert lineage.run_identity == RUN_ID
        assert lineage.trading_symbol == f"{instrument.canonical_instrument}26AUGFUT"
        assert lineage.segment == "MCX-FUT"
        assert lineage.entry_fact_state is McxEntryFactState.MASTER_AND_SPECIFICATION_UNVERIFIED
        assert lineage.source_master_record_identity is None
        assert lineage.source_master_snapshot_identity is None
        assert lineage.effective_specification_sha256 is None
        assert lineage.daily_request_sha256 != lineage.hourly_request_sha256
        assert not lineage.permits_new_entry
        matching_requests = tuple(
            request for request in requests
            if request.instrument.trading_symbol == lineage.trading_symbol
        )
        assert {request.interval.value for request in matching_requests} == {"day", "60minute"}
        assert all(
            request.instrument.expiry.isoformat() == lineage.expiry
            for request in matching_requests
        )
        assert mcx_lineage_matches_completed_facts(
            lineage, run_identity=RUN_ID,
            canonical_instrument=instrument.canonical_instrument,
            current_instrument=next(
                request.instrument for request in matching_requests
            ),
            completed_facts=tuple(
                instrument.fact(timeframe) for timeframe in (
                    FactualTimeframe.DAILY, FactualTimeframe.FOUR_HOUR,
                    FactualTimeframe.ONE_HOUR,
                )
            ),
            completed_series=instrument.completed_series,
        )
    assert all(
        instrument.mcx_request_lineage is None
        for instrument in snapshot.instruments if instrument.exchange == "NSE"
    )
    store = MtfFactEvidenceStore(tmp_path / "facts")
    store.retain(snapshot)
    path = tmp_path / "facts" / "complete-runs" / f"{RUN_ID}.json"
    before = path.stat().st_mtime_ns
    assert store.load(RUN_ID) == snapshot
    assert store.load(RUN_ID) == snapshot
    assert path.stat().st_mtime_ns == before
    store.retain(snapshot)


def test_changed_run_fact_or_derived_anchor_cannot_reuse_mcx_lineage() -> None:
    snapshot, _ = _build(
        retain_completed_series=True, retain_mcx_lineage=True,
    )
    instrument = snapshot.instrument("COPPER")
    lineage = instrument.mcx_request_lineage
    assert lineage is not None
    source_instrument = InstrumentRecord(
        provider=lineage.provider,
        exchange=lineage.exchange,
        segment=lineage.segment,
        trading_symbol=lineage.trading_symbol,
        name=lineage.family.value,
        instrument_type=lineage.instrument_type,
        expiry=date.fromisoformat(lineage.expiry),
        tick_size=Decimal("0.05"),
        lot_size=1,
    )
    assert mcx_contract_name_matches(McxFamily.COPPER, source_instrument)
    assert not mcx_contract_name_matches(
        McxFamily.COPPER, replace(source_instrument, trading_symbol="GOLDM26AUGFUT")
    )
    assert not mcx_contract_name_matches(
        McxFamily.COPPER, replace(source_instrument, expiry=date(2026, 9, 30))
    )
    assert not mcx_contract_name_matches(
        McxFamily.COPPER, replace(source_instrument, segment="MCX-OPT")
    )
    facts = tuple(instrument.fact(timeframe) for timeframe in (
        FactualTimeframe.DAILY, FactualTimeframe.FOUR_HOUR,
        FactualTimeframe.ONE_HOUR,
    ))
    match = lambda run, subject, current_facts, series: mcx_lineage_matches_completed_facts(
        lineage,
        run_identity=run,
        canonical_instrument=subject,
        current_instrument=source_instrument,
        completed_facts=current_facts,
        completed_series=series,
    )
    assert match(RUN_ID, "COPPER", facts, instrument.completed_series)
    assert not mcx_lineage_matches_completed_facts(
        lineage, run_identity=RUN_ID, canonical_instrument="COPPER",
        current_instrument=replace(source_instrument, expiry=date(2026, 9, 30)),
        completed_facts=facts, completed_series=instrument.completed_series,
    )
    assert not match("SWING-RUN-FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF", "COPPER", facts, instrument.completed_series)
    assert not match(RUN_ID, "GOLDM", facts, instrument.completed_series)
    assert not match(
        RUN_ID, "COPPER", (replace(facts[0], volume=facts[0].volume + 1), *facts[1:]),
        instrument.completed_series,
    )
    first_four_hour = next(
        index for index, bar in enumerate(instrument.completed_series)
        if bar.timeframe is FactualTimeframe.FOUR_HOUR
    )
    changed_series = tuple(
        replace(bar, volume=bar.volume + 1) if index == first_four_hour else bar
        for index, bar in enumerate(instrument.completed_series)
    )
    assert not match(RUN_ID, "COPPER", facts, changed_series)


def test_legacy_snapshots_remain_byte_compatible_without_mcx_lineage(tmp_path) -> None:
    snapshot, _ = _build(
        retain_completed_series=True, retain_mcx_lineage=True,
    )
    legacy = replace(snapshot, instruments=tuple(
        replace(instrument, mcx_request_lineage=None)
        for instrument in snapshot.instruments
    ))
    store = MtfFactEvidenceStore(tmp_path / "legacy")
    path = store.retain(legacy)
    before = path.read_bytes()
    assert b"mcx_request_lineage" not in before
    assert store.load(RUN_ID) == legacy
    assert store.retain(legacy).read_bytes() == before
