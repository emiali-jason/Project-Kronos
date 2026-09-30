"""Retained Provider identity is factual evidence, not MCX entry authority."""

from dataclasses import replace
from datetime import date, timedelta

import pytest

from kronos.application.swing_mcx_evidence import (
    listed_v1_mcx_offers, read_retained_mcx_master_match,
)
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.instrument_master_persistence import ProviderInstrumentSnapshotStore
from kronos.swing.v1.mcx_contract_profile import McxFamily
from tests.unit.provider.test_instrument_master_snapshot import NOW, _snapshot, _source


def test_exact_retained_provider_master_match_remains_non_actionable(tmp_path):
    snapshot = _snapshot()
    store = ProviderInstrumentSnapshotStore(tmp_path / "provider-master")
    store.retain(snapshot)
    record = next(item for item in snapshot.records
                  if item.trading_symbol == "GOLDM26AUGFUT")
    normalized = InstrumentRecord(
        record.provider, record.exchange, record.segment,
        record.trading_symbol, record.name, record.instrument_type,
        record.expiry, record.tick_size, record.lot_size,
    )
    path = store.path_for(provider="KITE", dataset_identity=snapshot.dataset_identity,
                          snapshot_identity=snapshot.snapshot_identity)
    before = path.read_bytes()
    matched = read_retained_mcx_master_match(
        store, snapshot_identity=snapshot.snapshot_identity,
        record_identity=record.provider_record_identity,
        family=McxFamily.GOLDM, normalized_contract=normalized,
        observed_at=NOW + timedelta(days=1),
    )
    assert matched.record_identity == record.provider_record_identity
    assert matched.normalized_contract == normalized
    assert matched.provider_instrument_token == record.provider_instrument_token
    assert matched.record_integrity_identity == record.record_integrity_identity
    assert matched.acquisition_effective_at == snapshot.acquisition_effective_at
    assert matched.source_boundary == snapshot.source_boundary
    assert matched.provider_validity_assertion == snapshot.provider_validity_assertion
    assert matched.permits_new_entry is False
    assert path.read_bytes() == before
    with pytest.raises(ValueError, match="CONTRACT_MISMATCH"):
        read_retained_mcx_master_match(
            store, snapshot_identity=snapshot.snapshot_identity,
            record_identity=record.provider_record_identity,
            family=McxFamily.GOLDM,
            normalized_contract=replace(normalized, lot_size=1),
            observed_at=NOW + timedelta(days=1),
        )
    with pytest.raises(ValueError, match="MASTER_UNAVAILABLE"):
        read_retained_mcx_master_match(
            store, snapshot_identity=snapshot.snapshot_identity,
            record_identity=record.provider_record_identity,
            family=McxFamily.GOLDM, normalized_contract=normalized,
            observed_at=NOW - timedelta(seconds=1),
        )


def test_all_five_v1_offers_retain_two_listed_contracts_and_snapshot_time(tmp_path):
    rows = []
    for index, family in enumerate(McxFamily):
        for month, expiry in (("OCT", date(2026, 10, 28)),
                              ("NOV", date(2026, 11, 27))):
            rows.append(_source(1000 + index * 2 + (month == "NOV"),
                f"{family.value}26{month}FUT", exchange="MCX",
                segment="MCX-FUT", name=family.value,
                instrument_type="FUT", expiry=expiry, lot=1, tick="0.05"))
    snapshot = _snapshot(tuple(rows))
    store = ProviderInstrumentSnapshotStore(tmp_path / "master")
    store.retain(snapshot)
    path = store.path_for(provider="KITE",
                          dataset_identity=snapshot.dataset_identity,
                          snapshot_identity=snapshot.snapshot_identity)
    before = path.read_bytes()
    offers = listed_v1_mcx_offers(
        store, snapshot_identity=snapshot.snapshot_identity,
        run_identity="SWING-RUN-0123456789ABCDEF0123456789ABCDEF",
        observed_at=NOW + timedelta(days=1))
    assert set(offers) == set(McxFamily)
    for family, offer in offers.items():
        assert offer.near.instrument.trading_symbol == f"{family.value}26OCTFUT"
        assert offer.next_eligible.instrument.trading_symbol == f"{family.value}26NOVFUT"
        assert offer.near.snapshot_acquired_at == snapshot.acquired_at
        assert offer.next_eligible.snapshot_acquired_at == snapshot.acquired_at
        assert offer.near.master_valid_until is None
        assert offer.near.effective_specification_sha256 is None
    assert path.read_bytes() == before
