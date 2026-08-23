from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path

import pytest

from kronos.instrument.semantic_v2 import (
    CANONICAL_INSTRUMENT_CATALOGUE_V2,
    AnalyticalSubjectV2,
    CanonicalClassification,
    CanonicalSemanticKind,
    DerivativeContractV2,
    DirectListedInstrumentV2,
    InstrumentSemanticResolverV2,
    ProviderInstrumentSubmissionV2,
    V2ResolutionError,
    V2ResolutionFailure,
    create_active_derivative_binding,
    create_analytical_subject,
    create_semantic_publication_v2,
    encode_semantic_publication_v2,
    parse_semantic_publication_v2,
)
from kronos.instrument.semantic_v2_persistence import (
    DEFAULT_INSTRUMENT_SEMANTIC_V2_ROOT,
    InstrumentSemanticV2Store,
)
from kronos.intraday.universe import load_intraday_universe_publication


P3_VERSION = "1.0.0"
P4_VERSION = "1.1.0"
P3_HASH = "7c9ca75ab08067e7369653ba8d6d9ecd92f654e51f5c276ef3a254ce240f15c8"
P4_INTEGRITY = "V2-PUBLICATION-09918d28261dcf1ebdf5389ac12d94a57b1bff81da26517a6c00ca67cbb95803"
UNIVERSE_HASH = "ebc070df99e53a7baf108f550a5d3c0a50fa1f3fb41564b813205e41580c89bd"
V1_HASHES = {
    "1.0.0": "b5a7ce48af7a123cb513bf5acacaea11e878d0ada3f8c5de99895f3fd29d4cdc",
    "1.0.1": "0bdd56b153a8007da676c744aed4f114d48e51da11f824093022edc90e4b8ef4",
}
SUBJECT_IDS = {
    "MCX-SUBJECT-GOLDM",
    "MCX-SUBJECT-SILVERM",
    "MCX-SUBJECT-COPPER",
    "MCX-SUBJECT-NATGAS",
    "MCX-SUBJECT-CRUDE",
}
EXPECTED_CONTRACTS = {
    "GOLDM": (
        ("GOLDM26SEPFUT", date(2026, 9, 4), Decimal("1.0")),
        ("GOLDM26OCTFUT", date(2026, 10, 5), Decimal("1.0")),
        ("GOLDM26NOVFUT", date(2026, 11, 5), Decimal("1.0")),
        ("GOLDM26DECFUT", date(2026, 12, 4), Decimal("1.0")),
        ("GOLDM27JANFUT", date(2027, 1, 5), Decimal("1.0")),
        ("GOLDM27FEBFUT", date(2027, 2, 5), Decimal("1.0")),
    ),
    "SILVERM": (
        ("SILVERM26AUGFUT", date(2026, 8, 31), Decimal("1.0")),
        ("SILVERM26NOVFUT", date(2026, 11, 30), Decimal("1.0")),
        ("SILVERM27FEBFUT", date(2027, 2, 26), Decimal("1.0")),
        ("SILVERM27APRFUT", date(2027, 4, 30), Decimal("1.0")),
        ("SILVERM27JUNFUT", date(2027, 6, 30), Decimal("1.0")),
    ),
    "COPPER": (
        ("COPPER26AUGFUT", date(2026, 8, 31), Decimal("0.05")),
        ("COPPER26SEPFUT", date(2026, 9, 30), Decimal("0.05")),
        ("COPPER26OCTFUT", date(2026, 10, 30), Decimal("0.05")),
        ("COPPER26NOVFUT", date(2026, 11, 30), Decimal("0.05")),
        ("COPPER26DECFUT", date(2026, 12, 31), Decimal("0.05")),
    ),
}


def _load(version: str):
    return InstrumentSemanticV2Store(DEFAULT_INSTRUMENT_SEMANTIC_V2_ROOT).load(
        publication_identity=CANONICAL_INSTRUMENT_CATALOGUE_V2,
        publication_version=version,
    )


def _contracts(publication):
    return tuple(item for item in publication.semantic_objects if type(item) is DerivativeContractV2)


def _mcx_subjects(publication):
    return tuple(
        item
        for item in publication.semantic_objects
        if type(item) is AnalyticalSubjectV2
        and item.classification is CanonicalClassification.MCX_COMMODITY
    )


def _rebuild(publication, **changes):
    values = {
        name: getattr(publication, name)
        for name in publication.__dataclass_fields__
        if name != "integrity_identity"
    }
    values.update(changes)
    return create_semantic_publication_v2(**values)


def _contract_submissions(publication):
    contracts = {item.canonical_id: item for item in _contracts(publication)}
    return tuple(
        ProviderInstrumentSubmissionV2(
            provider_record_identity=item.provider_record_identity,
            provider=item.provider,
            provider_symbol=item.provider_symbol,
            exchange="MCX",
            segment="MCX-FUT",
            provider_instrument_type="FUT",
            tick_size=contracts[item.canonical_object_id].geometry[0].tick_size,
            lot_size=contracts[item.canonical_object_id].geometry[0].lot_size,
            source_boundary=publication.effective_from,
            valid_through=item.effective_through,
            provenance=("P1-PROVIDER-EVIDENCE", "EAIC-002"),
        )
        for item in publication.provider_directives
        if item.canonical_object_id in contracts
    )


def _binding(publication, *, subject="MCX-SUBJECT-GOLDM", contract=None, start=None, end=None, expiry=None):
    selected = contract or next(
        item for item in _contracts(publication) if item.parent_subject_id == subject
    )
    binding_start = start or publication.effective_from
    binding_end = end or min(selected.valid_through, binding_start + timedelta(days=2))
    return create_active_derivative_binding(
        binding_identity="SYNTHETIC-GOVERNED-ACTIVE-BINDING",
        binding_version="1.0.0",
        subject_id=subject,
        derivative_contract_id=(selected.canonical_id if type(selected) is DerivativeContractV2 else selected),
        effective_from=binding_start,
        effective_through=binding_end,
        contract_expiry=expiry or selected.expiry,
        provider_reference_identity=f"P4-KITE-DIRECTIVE-{selected.canonical_id}",
        source_identity="SYNTHETIC-GOVERNED-SELECTION-AUTHORITY",
        provenance=("P4-ACTIVE-BINDING-MACHINERY-PROOF",),
        supersedes=None,
    )


def test_p4_successor_preserves_p3_and_reports_separate_counts():
    p3 = _load(P3_VERSION)
    p4 = _load(P4_VERSION)
    direct = tuple(item for item in p4.semantic_objects if type(item) is DirectListedInstrumentV2)
    indexes = tuple(
        item
        for item in p4.semantic_objects
        if type(item) is AnalyticalSubjectV2
        and item.classification is CanonicalClassification.NSE_INDEX
    )

    assert p4.publication_identity == CANONICAL_INSTRUMENT_CATALOGUE_V2
    assert p4.publication_version == P4_VERSION
    assert p4.supersedes == p3.integrity_identity
    assert p4.integrity_identity == P4_INTEGRITY
    assert p4.semantic_objects[: len(p3.semantic_objects)] == p3.semantic_objects
    assert (len(direct), len(indexes), len(_mcx_subjects(p4)), len(_contracts(p4))) == (91, 2, 5, 16)
    assert len(direct) + len(indexes) + len(_mcx_subjects(p4)) == 98
    assert len(p4.semantic_objects) == 114
    assert len(p4.provider_directives) == 109
    assert p4.active_bindings == ()


def test_five_persistent_subjects_are_expiry_free_and_distinct_from_contracts():
    publication = _load(P4_VERSION)
    subjects = _mcx_subjects(publication)
    contracts = _contracts(publication)

    assert {item.canonical_id for item in subjects} == SUBJECT_IDS
    assert all(item.semantic_kind is CanonicalSemanticKind.ANALYTICAL_SUBJECT for item in subjects)
    assert all(item.exchange == "MCX" for item in subjects)
    assert all(not any(char.isdigit() for char in item.canonical_id) for item in subjects)
    assert all(contract.semantic_kind is CanonicalSemanticKind.DERIVATIVE_CONTRACT for contract in contracts)
    assert all(contract.canonical_id != contract.parent_subject_id for contract in contracts)
    assert all(contract.parent_subject_id in SUBJECT_IDS for contract in contracts)


@pytest.mark.parametrize("subject", ["GOLDM", "SILVERM", "COPPER"])
def test_exact_p1_contracts_geometry_parents_and_directives(subject):
    publication = _load(P4_VERSION)
    contracts = tuple(item for item in _contracts(publication) if item.parent_subject_id == f"MCX-SUBJECT-{subject}")
    directives = {item.canonical_object_id: item for item in publication.provider_directives}
    actual = tuple((item.canonical_symbol, item.expiry, item.geometry[0].tick_size) for item in contracts)

    assert actual == EXPECTED_CONTRACTS[subject]
    assert all(item.geometry[0].lot_size == 1 for item in contracts)
    assert all(item.geometry[0].canonical_object_id == item.canonical_id for item in contracts)
    assert all(item.geometry[0].effective_from == item.valid_from for item in contracts)
    assert all(item.canonical_id == f"MCX-FUT-{subject}-{item.expiry.isoformat()}" for item in contracts)
    assert all(directives[item.canonical_id].provider_symbol == item.canonical_symbol for item in contracts)
    assert all(directives[item.canonical_id].classification_mapping_identity == "P4-KITE-MCX-FUTURE-MAPPING" for item in contracts)


@pytest.mark.parametrize("subject", ["NATGAS", "CRUDE"])
def test_provider_absent_subjects_remain_canonical_but_contract_runtime_unavailable(subject):
    publication = _load(P4_VERSION)
    resolver = InstrumentSemanticResolverV2(publication, _contract_submissions(publication))
    canonical_id = f"MCX-SUBJECT-{subject}"

    result = resolver.resolve_subject(canonical_id, publication.effective_from)
    assert result.canonical.canonical_id == canonical_id
    assert result.provider_directive is None
    assert result.provider_submission is None
    assert result.active_contract_id is None
    assert not any(item.parent_subject_id == canonical_id for item in _contracts(publication))
    assert not any(item.canonical_object_id == canonical_id for item in publication.provider_directives)
    with pytest.raises(V2ResolutionError) as error:
        resolver.resolve_active_contract(canonical_id, publication.effective_from)
    assert error.value.failure is V2ResolutionFailure.ACTIVE_CONTRACT_BINDING_UNAVAILABLE


def test_exact_mcx_classification_mapping_does_not_target_persistent_subjects():
    publication = _load(P4_VERSION)
    mapping = publication.classification_mapping(
        mapping_identity="P4-KITE-MCX-FUTURE-MAPPING",
        mapping_version="1.0.0",
    )
    assert mapping.provider_key == ("KITE", "MCX", "MCX-FUT", "FUT")
    assert mapping.canonical_classification is CanonicalClassification.MCX_FUTURE
    assert mapping.governed_subject_ids == ()
    assert all(
        item.classification_mapping_identity != mapping.mapping_identity
        for item in publication.provider_directives
        if item.canonical_object_id in SUBJECT_IDS
    )


def test_multiple_contracts_without_binding_never_auto_select():
    publication = _load(P4_VERSION)
    resolver = InstrumentSemanticResolverV2(publication, _contract_submissions(publication))
    for subject in ("GOLDM", "SILVERM", "COPPER"):
        canonical_id = f"MCX-SUBJECT-{subject}"
        assert resolver.resolve_subject(canonical_id, publication.effective_from).active_contract_id is None
        with pytest.raises(V2ResolutionError) as error:
            resolver.resolve_active_contract(canonical_id, publication.effective_from)
        assert error.value.failure is V2ResolutionFailure.ACTIVE_CONTRACT_BINDING_UNAVAILABLE


def test_exact_synthetic_binding_resolves_only_supplied_contract_and_geometry_mismatch_fails():
    publication = _load(P4_VERSION)
    selected = next(item for item in _contracts(publication) if item.canonical_symbol == "GOLDM26OCTFUT")
    binding = _binding(publication, contract=selected)
    bound = _rebuild(publication, active_bindings=(binding,))
    submissions = _contract_submissions(publication)
    runtime = InstrumentSemanticResolverV2(bound, submissions).resolve_active_contract(
        "MCX-SUBJECT-GOLDM", publication.effective_from
    )
    assert runtime.contract.canonical_id == selected.canonical_id
    assert runtime.contract.expiry == selected.expiry

    original = next(item for item in submissions if item.provider_symbol == selected.canonical_symbol)
    wrong = ProviderInstrumentSubmissionV2(
        provider_record_identity=original.provider_record_identity,
        provider=original.provider,
        provider_symbol=original.provider_symbol,
        exchange=original.exchange,
        segment=original.segment,
        provider_instrument_type=original.provider_instrument_type,
        tick_size=Decimal("0.05"),
        lot_size=original.lot_size,
        source_boundary=original.source_boundary,
        valid_through=original.valid_through,
        provenance=original.provenance,
    )
    mismatched = tuple(wrong if item.provider_record_identity == wrong.provider_record_identity else item for item in submissions)
    with pytest.raises(V2ResolutionError) as error:
        InstrumentSemanticResolverV2(bound, mismatched).resolve_active_contract(
            "MCX-SUBJECT-GOLDM", publication.effective_from
        )
    assert error.value.failure is V2ResolutionFailure.CANONICAL_GEOMETRY_MISMATCH


def test_expired_binding_is_unavailable_and_wrong_parent_unknown_or_expiry_mismatch_fail_closed():
    publication = _load(P4_VERSION)
    selected = next(item for item in _contracts(publication) if item.canonical_symbol == "GOLDM26SEPFUT")
    start = publication.effective_from
    binding = _binding(publication, contract=selected, start=start, end=start + timedelta(hours=1))
    bound = _rebuild(publication, active_bindings=(binding,))
    resolver = InstrumentSemanticResolverV2(bound, _contract_submissions(publication))
    with pytest.raises(V2ResolutionError) as error:
        resolver.resolve_active_contract("MCX-SUBJECT-GOLDM", start + timedelta(hours=2))
    assert error.value.failure is V2ResolutionFailure.ACTIVE_CONTRACT_BINDING_UNAVAILABLE

    wrong_parent = _binding(publication, subject="MCX-SUBJECT-SILVERM", contract=selected)
    with pytest.raises(V2ResolutionError) as error:
        _rebuild(publication, active_bindings=(wrong_parent,))
    assert error.value.failure is V2ResolutionFailure.INTEGRITY_INVALID

    unknown = _binding(publication, contract=selected)
    unknown = create_active_derivative_binding(
        binding_identity="SYNTHETIC-UNKNOWN-CONTRACT-BINDING",
        binding_version="1.0.0",
        subject_id="MCX-SUBJECT-GOLDM",
        derivative_contract_id="MCX-FUT-GOLDM-UNKNOWN",
        effective_from=start,
        effective_through=start + timedelta(hours=1),
        contract_expiry=selected.expiry,
        provider_reference_identity="SYNTHETIC-UNKNOWN-PROVIDER-REFERENCE",
        source_identity="SYNTHETIC-GOVERNED-SELECTION-AUTHORITY",
        provenance=("P4-ACTIVE-BINDING-MACHINERY-PROOF",),
        supersedes=None,
    )
    with pytest.raises(V2ResolutionError) as error:
        _rebuild(publication, active_bindings=(unknown,))
    assert error.value.failure is V2ResolutionFailure.INTEGRITY_INVALID

    expiry_mismatch = _binding(publication, contract=selected, expiry=date(2026, 9, 5))
    with pytest.raises(V2ResolutionError) as error:
        _rebuild(publication, active_bindings=(expiry_mismatch,))
    assert error.value.failure is V2ResolutionFailure.INTEGRITY_INVALID


def test_future_gold_and_silver_are_distinct_extensible_subjects_without_production_records(tmp_path):
    publication = _load(P4_VERSION)
    additions = tuple(
        create_analytical_subject(
            canonical_id=f"MCX-SUBJECT-{symbol}",
            canonical_symbol=symbol,
            exchange="MCX",
            classification=CanonicalClassification.MCX_COMMODITY,
            valid_from=publication.effective_from,
            valid_through=publication.effective_through,
            source_identity=f"SYNTHETIC-GOVERNED-{symbol}-AUTHORITY",
            provenance=("P4-EXTENSIBILITY-PROOF",),
        )
        for symbol in ("GOLD", "SILVER")
    )
    successor = _rebuild(
        publication,
        publication_version="1.2.0",
        supersedes=publication.integrity_identity,
        source_identities=publication.source_identities + ("SYNTHETIC-P4-SUCCESSOR",),
        semantic_objects=publication.semantic_objects + additions,
    )
    assert additions[0].canonical_id != "MCX-SUBJECT-GOLDM"
    assert additions[1].canonical_id != "MCX-SUBJECT-SILVERM"
    assert not any(item.canonical_symbol in {"GOLD", "SILVER"} for item in publication.semantic_objects)
    store = InstrumentSemanticV2Store(tmp_path.resolve())
    store.retain(publication)
    store.retain(successor)
    assert store.load(publication_identity=CANONICAL_INSTRUMENT_CATALOGUE_V2, publication_version=P4_VERSION) == publication
    assert store.load(publication_identity=CANONICAL_INSTRUMENT_CATALOGUE_V2, publication_version="1.2.0") == successor


def test_predecessors_universe_and_provider_evidence_references_are_immutable():
    root = Path(__file__).resolve().parents[3]
    p3_path = root / "data/instruments/KRONOS-CANONICAL-INSTRUMENT-CATALOGUE-V2/1.0.0.json"
    assert sha256(p3_path.read_bytes()).hexdigest() == P3_HASH
    for version, expected in V1_HASHES.items():
        path = root / f"data/instruments/KRONOS-CANONICAL-INSTRUMENT-CATALOGUE-V1/{version}.json"
        assert sha256(path.read_bytes()).hexdigest() == expected
    universe_path = root / "data/intraday/KRONOS-INTRADAY-NATIVE-UNIVERSE-V1/1.0.0.json"
    assert sha256(universe_path.read_bytes()).hexdigest() == UNIVERSE_HASH
    assert len(load_intraday_universe_publication(universe_path.resolve()).members) == 98
    publication = _load(P4_VERSION)
    assert any(item.startswith("PROVIDER-INSTRUMENT-SNAPSHOT-e4eb2e41") for item in publication.source_identities)
    assert any(item.startswith("PROVIDER-INSTRUMENT-SNAPSHOT-INTEGRITY-4b0604d0") for item in publication.source_identities)


def test_no_capacity_selection_execution_reference_or_token_leakage():
    root = Path(__file__).resolve().parents[3]
    encoded = (root / "data/instruments/KRONOS-CANONICAL-INSTRUMENT-CATALOGUE-V2/1.1.0.json").read_bytes()
    text = encoded.decode("ascii").lower()
    document = json.loads(encoded)
    assert "allowed_mcx_subjects" not in text
    assert "max_mcx_subjects" not in text
    assert "nearest_expiry" not in text
    assert "front_month" not in text
    assert "volume_selection" not in text
    assert "oi_selection" not in text
    assert "liquidity_selection" not in text
    assert "provider_instrument_token" not in text
    assert "instrument_token" not in text
    assert "access_token" not in text
    assert "execution_eligibility" not in text
    assert not any(item["canonical_symbol"] in {"GOLD", "SILVER"} for item in document["semantic_objects"])
    assert document["active_bindings"] == []


def test_deterministic_integrity_tamper_conflict_and_exact_version_lookup(tmp_path):
    p3 = _load(P3_VERSION)
    p4 = _load(P4_VERSION)
    encoded = encode_semantic_publication_v2(p4)
    assert parse_semantic_publication_v2(encoded) == p4
    tampered = encoded.replace(b'"canonical_symbol":"GOLDM"', b'"canonical_symbol":"GOLXX"')
    with pytest.raises(V2ResolutionError) as error:
        parse_semantic_publication_v2(tampered)
    assert error.value.failure is V2ResolutionFailure.INTEGRITY_INVALID

    store = InstrumentSemanticV2Store(tmp_path.resolve())
    store.retain(p3)
    path = store.retain(p4)
    assert store.retain(p4) == path
    assert store.load(publication_identity=CANONICAL_INSTRUMENT_CATALOGUE_V2, publication_version=P3_VERSION) == p3
    assert store.load(publication_identity=CANONICAL_INSTRUMENT_CATALOGUE_V2, publication_version=P4_VERSION) == p4
    path.write_bytes(b"conflict\n")
    with pytest.raises(V2ResolutionError) as error:
        store.retain(p4)
    assert error.value.failure is V2ResolutionFailure.INTEGRITY_INVALID


def test_p2_failure_vocabulary_remains_complete():
    assert set(V2ResolutionFailure) == {
        V2ResolutionFailure.CANONICAL_SUBJECT_UNAVAILABLE,
        V2ResolutionFailure.CLASSIFICATION_MAPPING_UNAVAILABLE,
        V2ResolutionFailure.CANONICAL_CLASSIFICATION_CONFLICT,
        V2ResolutionFailure.PROVIDER_ASSERTION_UNAVAILABLE,
        V2ResolutionFailure.PROVIDER_BINDING_UNAVAILABLE,
        V2ResolutionFailure.ACTIVE_CONTRACT_BINDING_UNAVAILABLE,
        V2ResolutionFailure.CANONICAL_GEOMETRY_MISMATCH,
        V2ResolutionFailure.SOURCE_STALE,
        V2ResolutionFailure.PUBLICATION_STALE,
        V2ResolutionFailure.INTEGRITY_INVALID,
    }
