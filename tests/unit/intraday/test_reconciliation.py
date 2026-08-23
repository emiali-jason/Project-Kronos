from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from kronos.instrument.semantic_v2 import CanonicalSemanticKind
from kronos.instrument.semantic_v2_persistence import InstrumentSemanticV2Store
from kronos.intraday.reconciliation import (
    Availability,
    AvailabilityDimensions,
    RECONCILIATION_IDENTITY,
    ReconciliationError,
    ReconciliationFailure,
    ReconciliationReason,
    ReconciliationState,
    create_reconciliation_member,
    create_reconciliation_publication,
    reconcile_intraday_publications,
    reconciliation_publication_bytes,
)
from kronos.intraday.reconciliation_persistence import IntradayReconciliationStore
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.universe_persistence import IntradayUniversePublicationStore


ROOT = Path(__file__).resolve().parents[3]
UNIVERSE_VERSION = "1.0.0"
CATALOGUE_IDENTITY = "KRONOS-CANONICAL-INSTRUMENT-CATALOGUE-V2"
CATALOGUE_VERSION = "1.1.0"
SNAPSHOT = "PROVIDER-INSTRUMENT-SNAPSHOT-e4eb2e41dddd87ee6dff55628822b55b8a2695170f21ac63ced62e96d214637c"
SNAPSHOT_INTEGRITY = "PROVIDER-INSTRUMENT-SNAPSHOT-INTEGRITY-4b0604d0ee95f783465079ca7257772f352bb5db951e47323dd137139d0a276a"
MANIFEST = "INTRADAY-PROVIDER-COMMISSIONING-b8d026b1ef8c90059eae05583762f3fa8aaae1ce9ed5c02255a4f078cccc1323"
PROVIDER_BOUNDARY = datetime.fromisoformat("2026-08-22T16:22:54.301682+00:00")


@pytest.fixture(scope="module")
def publication():
    universe = IntradayUniversePublicationStore(ROOT / "data" / "intraday").load(
        publication_version=UNIVERSE_VERSION
    )
    catalogue = InstrumentSemanticV2Store(ROOT / "data" / "instruments").load(
        publication_identity=CATALOGUE_IDENTITY,
        publication_version=CATALOGUE_VERSION,
    )
    return reconcile_intraday_publications(
        universe=universe,
        catalogue=catalogue,
        provider_snapshot_identity=SNAPSHOT,
        provider_snapshot_integrity_identity=SNAPSHOT_INTEGRITY,
        commissioning_manifest_identity=MANIFEST,
        provider_evidence_boundary=PROVIDER_BOUNDARY,
    )


def test_exact_governed_publications_and_member_counts(publication) -> None:
    counts = dict(publication.aggregate_counts)
    assert (publication.universe_identity, publication.universe_version) == (
        "KRONOS-INTRADAY-NATIVE-UNIVERSE-V1",
        "1.0.0",
    )
    assert (publication.catalogue_identity, publication.catalogue_version) == (
        CATALOGUE_IDENTITY,
        CATALOGUE_VERSION,
    )
    assert publication.provider_snapshot_identity == SNAPSHOT
    assert publication.commissioning_manifest_identity == MANIFEST
    assert len(publication.members) == counts["members.total"] == 98
    assert counts["family.NSE_EQUITY"] == 91
    assert counts["family.NSE_INDEX"] == 2
    assert counts["family.MCX"] == 5
    assert counts["semantic.DIRECT_LISTED_INSTRUMENT"] == 91
    assert counts["semantic.ANALYTICAL_SUBJECT"] == 7


def test_all_cash_members_have_exact_canonical_provider_runtime_geometry(publication) -> None:
    cash = tuple(item for item in publication.members if item.market_family is IntradayMarketFamily.NSE_EQUITY)
    assert len(cash) == 91
    assert all(item.semantic_type is CanonicalSemanticKind.DIRECT_LISTED_INSTRUMENT for item in cash)
    assert publication.lookup("RELIANCE").canonical_identity == "RELIANCE"
    assert all(len(item.provider_directive_identities) == 1 for item in cash)
    assert all(len(item.provider_record_identities) == 1 for item in cash)
    assert all(item.dimensions.effective_geometry is Availability.AVAILABLE for item in cash)
    assert all(item.dimensions.runtime_analytical_availability is Availability.AVAILABLE for item in cash)
    assert all(item.dimensions.machine_fact_consumability is Availability.AVAILABLE for item in cash)


@pytest.mark.parametrize(
    ("label", "canonical", "provider_symbol"),
    (("NIFTY", "NSE-INDEX-NIFTY", "NIFTY 50"), ("BANKNIFTY", "NSE-INDEX-BANKNIFTY", "NIFTY BANK")),
)
def test_index_analytical_paths_are_provider_backed_but_non_executable(
    publication, label, canonical, provider_symbol
) -> None:
    item = publication.lookup(label)
    assert item.canonical_identity == canonical
    assert item.provider_symbol == provider_symbol
    assert item.semantic_type is CanonicalSemanticKind.ANALYTICAL_SUBJECT
    assert item.dimensions.provider_mapping is Availability.AVAILABLE
    assert item.dimensions.provider_fact is Availability.AVAILABLE
    assert item.dimensions.effective_geometry is Availability.NOT_APPLICABLE
    assert item.dimensions.derivative_contract_set is Availability.NOT_APPLICABLE
    assert item.dimensions.runtime_contract_availability is Availability.NOT_APPLICABLE
    assert item.dimensions.machine_fact_consumability is Availability.AVAILABLE
    assert item.dimensions.execution_eligibility is Availability.NOT_ESTABLISHED


@pytest.mark.parametrize(
    ("label", "canonical", "contracts"),
    (("GOLDM", "MCX-SUBJECT-GOLDM", 6), ("SILVERM", "MCX-SUBJECT-SILVERM", 5), ("COPPER", "MCX-SUBJECT-COPPER", 5)),
)
def test_provider_supported_mcx_subjects_stop_at_missing_active_binding(
    publication, label, canonical, contracts
) -> None:
    item = publication.lookup(label)
    assert item.canonical_identity == canonical
    assert len(item.derivative_contract_identities) == contracts
    assert item.dimensions.derivative_contract_set is Availability.AVAILABLE
    assert item.dimensions.active_derivative_binding is Availability.UNAVAILABLE
    assert item.dimensions.runtime_analytical_availability is Availability.AVAILABLE
    assert item.dimensions.runtime_contract_availability is Availability.UNAVAILABLE
    assert item.dimensions.machine_fact_consumability is Availability.UNAVAILABLE
    assert item.state is ReconciliationState.ACTIVE_CONTRACT_BINDING_UNAVAILABLE
    assert ReconciliationReason.ACTIVE_BINDING_MISSING in item.reasons


@pytest.mark.parametrize(("label", "canonical"), (("NATGAS", "MCX-SUBJECT-NATGAS"), ("CRUDE", "MCX-SUBJECT-CRUDE")))
def test_provider_absent_mcx_members_remain_canonical_members(publication, label, canonical) -> None:
    item = publication.lookup(label)
    assert item.canonical_identity == canonical
    assert item.dimensions.product_membership is Availability.AVAILABLE
    assert item.dimensions.canonical_identity is Availability.AVAILABLE
    assert item.dimensions.provider_mapping is Availability.UNAVAILABLE
    assert item.dimensions.provider_fact is Availability.UNAVAILABLE
    assert item.dimensions.derivative_contract_set is Availability.UNAVAILABLE
    assert item.dimensions.runtime_analytical_availability is Availability.AVAILABLE
    assert item.dimensions.runtime_contract_availability is Availability.UNAVAILABLE
    assert item.state is ReconciliationState.PROVIDER_CONTRACT_UNAVAILABLE
    assert item.provider_symbol is None
    assert item.provider_record_identities == ()


def test_availability_dimensions_preserve_required_non_equivalences(publication) -> None:
    natgas = publication.lookup("NATGAS")
    goldm = publication.lookup("GOLDM")
    nifty = publication.lookup("NIFTY")
    assert natgas.dimensions.product_membership is Availability.AVAILABLE
    assert natgas.dimensions.provider_fact is Availability.UNAVAILABLE
    assert goldm.dimensions.provider_fact is Availability.AVAILABLE
    assert goldm.dimensions.runtime_contract_availability is Availability.UNAVAILABLE
    assert nifty.dimensions.runtime_analytical_availability is Availability.AVAILABLE
    assert nifty.dimensions.execution_eligibility is Availability.NOT_ESTABLISHED


def test_execution_is_not_established_for_every_member(publication) -> None:
    assert all(item.dimensions.execution_eligibility is Availability.NOT_ESTABLISHED for item in publication.members)
    assert dict(publication.aggregate_counts)["dimension.execution_eligibility.NOT_ESTABLISHED"] == 98


def test_exact_dimensional_and_overall_aggregate_counts(publication) -> None:
    counts = dict(publication.aggregate_counts)
    assert counts["dimension.canonical_identity.AVAILABLE"] == 98
    assert counts["dimension.provider_mapping.AVAILABLE"] == 96
    assert counts["dimension.provider_mapping.UNAVAILABLE"] == 2
    assert counts["dimension.runtime_analytical_availability.AVAILABLE"] == 98
    assert counts["dimension.runtime_contract_availability.UNAVAILABLE"] == 5
    assert counts["dimension.machine_fact_consumability.AVAILABLE"] == 93
    assert counts["dimension.machine_fact_consumability.UNAVAILABLE"] == 5
    assert counts["derivative_contracts.total"] == 16
    assert counts["state.FULLY_RECONCILED_FOR_CURRENT_FACTUAL_PATH"] == 93
    assert counts["state.ACTIVE_CONTRACT_BINDING_UNAVAILABLE"] == 3
    assert counts["state.PROVIDER_CONTRACT_UNAVAILABLE"] == 2


def test_member_and_publication_integrities_are_deterministic(publication) -> None:
    rebuilt = publication
    assert reconciliation_publication_bytes(rebuilt) == reconciliation_publication_bytes(publication)
    assert len({item.reconciliation_member_identity for item in publication.members}) == 98
    assert publication.integrity_identity.startswith("INTRADAY-RECONCILIATION-")


def test_immutable_explicit_version_persistence_restart_and_conflict(publication, tmp_path) -> None:
    store = IntradayReconciliationStore(tmp_path.resolve())
    first = store.retain(publication)
    assert store.retain(publication) == first
    reloaded = IntradayReconciliationStore(tmp_path.resolve()).load(
        publication_identity=RECONCILIATION_IDENTITY,
        publication_version="1.0.0",
    )
    assert reloaded == publication
    conflicting = _successor_with_extra_members(
        publication, ("FUTUREEQ",), publication_version="1.0.0"
    )
    with pytest.raises(ReconciliationError, match="VERSION_CONFLICT"):
        store.retain(conflicting)
    with pytest.raises(ReconciliationError, match="PUBLICATION_UNAVAILABLE"):
        store.load(publication_identity=RECONCILIATION_IDENTITY, publication_version="9.9.9")


def test_tamper_is_rejected(publication, tmp_path) -> None:
    store = IntradayReconciliationStore(tmp_path.resolve())
    path = store.retain(publication)
    encoded = path.read_bytes().replace(b'"sponsor_label":"ADANIENT"', b'"sponsor_label":"ALTERED"')
    path.write_bytes(encoded)
    with pytest.raises(ReconciliationError, match="INTEGRITY_MISMATCH"):
        store.load(publication_identity=RECONCILIATION_IDENTITY, publication_version="1.0.0")


@pytest.mark.parametrize(
    ("field", "failure"),
    (("universe_version", ReconciliationFailure.STALE_UNIVERSE), ("catalogue_version", ReconciliationFailure.STALE_CATALOGUE), ("provider_snapshot_identity", ReconciliationFailure.STALE_PROVIDER_SNAPSHOT)),
)
def test_stale_evidence_is_rejected(publication, field, failure) -> None:
    values = {
        "universe_identity": publication.universe_identity,
        "universe_version": publication.universe_version,
        "catalogue_identity": publication.catalogue_identity,
        "catalogue_version": publication.catalogue_version,
        "provider_snapshot_identity": publication.provider_snapshot_identity,
    }
    values[field] = "successor"
    with pytest.raises(ReconciliationError) as raised:
        publication.require_evidence(**values)
    assert raised.value.failure is failure


def test_successor_membership_is_not_capacity_bound(publication) -> None:
    labels = ("FUTUREEQ", "FINNIFTY", "SENSEX", "GOLD", "SILVER")
    successor = _successor_with_extra_members(publication, labels)
    assert len(successor.members) == 103
    assert all(successor.lookup(label).sponsor_label == label for label in labels)
    assert len(publication.members) == 98


def test_checked_in_publication_is_exact_reconstruction(publication) -> None:
    stored = IntradayReconciliationStore(ROOT / "data" / "intraday").load(
        publication_identity=RECONCILIATION_IDENTITY,
        publication_version="1.0.0",
    )
    assert stored == publication


def _successor_with_extra_members(publication, labels, publication_version="2.0.0"):
    family_by_label = {
        "FUTUREEQ": IntradayMarketFamily.NSE_EQUITY,
        "FINNIFTY": IntradayMarketFamily.NSE_INDEX,
        "SENSEX": IntradayMarketFamily.NSE_INDEX,
        "GOLD": IntradayMarketFamily.MCX,
        "SILVER": IntradayMarketFamily.MCX,
    }
    members = publication.members + tuple(
        create_reconciliation_member(
            sponsor_label=label,
            universe_member_identity=f"SYNTHETIC-MEMBER-{label}",
            market_family=family_by_label.get(label, IntradayMarketFamily.NSE_EQUITY),
            canonical_identity=f"SYNTHETIC-CANONICAL-{label}",
            semantic_type=(CanonicalSemanticKind.DIRECT_LISTED_INSTRUMENT if family_by_label.get(label, IntradayMarketFamily.NSE_EQUITY) is IntradayMarketFamily.NSE_EQUITY else CanonicalSemanticKind.ANALYTICAL_SUBJECT),
            exchange="NSE" if family_by_label.get(label) is not IntradayMarketFamily.MCX else "MCX",
            provider_symbol=None,
            provider_directive_identities=(),
            provider_record_identities=(),
            derivative_contract_identities=(),
            dimensions=AvailabilityDimensions(
                Availability.AVAILABLE,
                Availability.AVAILABLE,
                Availability.AVAILABLE,
                Availability.UNAVAILABLE,
                Availability.UNAVAILABLE,
                Availability.NOT_APPLICABLE,
                Availability.NOT_APPLICABLE,
                Availability.NOT_APPLICABLE,
                Availability.AVAILABLE,
                Availability.NOT_APPLICABLE,
                Availability.UNAVAILABLE,
                Availability.NOT_ESTABLISHED,
            ),
            state=ReconciliationState.PROVIDER_CONTRACT_UNAVAILABLE,
            reasons=(
                ReconciliationReason.PRODUCT_MEMBERSHIP_AVAILABLE,
                ReconciliationReason.CANONICAL_IDENTITY_AVAILABLE,
                ReconciliationReason.PROVIDER_CONTRACT_UNAVAILABLE,
                ReconciliationReason.EXECUTION_ELIGIBILITY_NOT_ESTABLISHED,
            ),
        )
        for label in labels
    )
    return create_reconciliation_publication(
        publication_version=publication_version,
        universe_identity=publication.universe_identity,
        universe_version="2.0.0",
        universe_integrity_identity="SYNTHETIC-SUCCESSOR-UNIVERSE",
        catalogue_identity=publication.catalogue_identity,
        catalogue_version=publication.catalogue_version,
        catalogue_integrity_identity=publication.catalogue_integrity_identity,
        provider_snapshot_identity=publication.provider_snapshot_identity,
        provider_snapshot_integrity_identity=publication.provider_snapshot_integrity_identity,
        commissioning_manifest_identity=publication.commissioning_manifest_identity,
        effective_boundary=publication.effective_boundary,
        provider_evidence_boundary=publication.provider_evidence_boundary,
        supersedes=publication.integrity_identity,
        source_identities=publication.source_identities + ("SYNTHETIC-SUCCESSOR-UNIVERSE",),
        provenance=publication.provenance,
        members=members,
    )
