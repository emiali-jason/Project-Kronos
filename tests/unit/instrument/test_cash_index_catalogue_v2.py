from __future__ import annotations

from dataclasses import fields
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path

import pytest

from kronos.instrument.catalogue import load_canonical_instrument_catalogue
from kronos.instrument.semantic_v2 import (
    CANONICAL_INSTRUMENT_CATALOGUE_V2,
    AnalyticalSubjectV2,
    CanonicalClassification,
    CanonicalSemanticKind,
    DirectListedInstrumentV2,
    InstrumentSemanticResolverV2,
    ProviderInstrumentSubmissionV2,
    V2ResolutionError,
    V2ResolutionFailure,
    create_analytical_subject,
    create_classification_mapping,
    create_direct_listed_instrument,
    create_effective_geometry,
    create_provider_mapping_directive_v2,
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
P3_PATH = (
    DEFAULT_INSTRUMENT_SEMANTIC_V2_ROOT
    / CANONICAL_INSTRUMENT_CATALOGUE_V2
    / f"{P3_VERSION}.json"
)
P1_SNAPSHOT = "PROVIDER-INSTRUMENT-SNAPSHOT-e4eb2e41dddd87ee6dff55628822b55b8a2695170f21ac63ced62e96d214637c"
P1_SNAPSHOT_INTEGRITY = "PROVIDER-INSTRUMENT-SNAPSHOT-INTEGRITY-4b0604d0ee95f783465079ca7257772f352bb5db951e47323dd137139d0a276a"
P1_MANIFEST = "INTRADAY-PROVIDER-COMMISSIONING-b8d026b1ef8c90059eae05583762f3fa8aaae1ce9ed5c02255a4f078cccc1323"
P3_INTEGRITY = "V2-PUBLICATION-e06a3ae92e8a46473ca3a87230f154cefe41335787181c1555545ab774f0c745"
V1_HASHES = {
    "1.0.0": "b5a7ce48af7a123cb513bf5acacaea11e878d0ada3f8c5de99895f3fd29d4cdc",
    "1.0.1": "0bdd56b153a8007da676c744aed4f114d48e51da11f824093022edc90e4b8ef4",
}
UNIVERSE_HASH = "ebc070df99e53a7baf108f550a5d3c0a50fa1f3fb41564b813205e41580c89bd"


def _publication():
    return InstrumentSemanticV2Store(DEFAULT_INSTRUMENT_SEMANTIC_V2_ROOT).load(
        publication_identity=CANONICAL_INSTRUMENT_CATALOGUE_V2,
        publication_version=P3_VERSION,
    )


def _submissions(publication):
    objects = {item.canonical_id: item for item in publication.semantic_objects}
    return tuple(
        ProviderInstrumentSubmissionV2(
            provider_record_identity=directive.provider_record_identity,
            provider=directive.provider,
            provider_symbol=directive.provider_symbol,
            exchange=("NSE"),
            segment=(
                "NSE"
                if type(objects[directive.canonical_object_id]) is DirectListedInstrumentV2
                else "INDICES"
            ),
            provider_instrument_type="EQ",
            tick_size=(
                objects[directive.canonical_object_id].geometry[0].tick_size
                if type(objects[directive.canonical_object_id]) is DirectListedInstrumentV2
                else None
            ),
            lot_size=(
                objects[directive.canonical_object_id].geometry[0].lot_size
                if type(objects[directive.canonical_object_id]) is DirectListedInstrumentV2
                else None
            ),
            source_boundary=publication.effective_from,
            valid_through=publication.effective_through,
            provenance=(P1_SNAPSHOT, "EAIC-002"),
        )
        for directive in publication.provider_directives
    )


def test_p3_production_publication_counts_identity_and_source_evidence():
    publication = _publication()
    cash = tuple(item for item in publication.semantic_objects if type(item) is DirectListedInstrumentV2)
    indexes = tuple(item for item in publication.semantic_objects if type(item) is AnalyticalSubjectV2)

    assert publication.publication_identity == CANONICAL_INSTRUMENT_CATALOGUE_V2
    assert publication.publication_version == P3_VERSION
    assert publication.supersedes is None
    assert publication.integrity_identity == P3_INTEGRITY
    assert len(cash) == 91
    assert len(indexes) == 2
    assert len(publication.semantic_objects) == 93
    assert P1_SNAPSHOT in publication.source_identities
    assert P1_SNAPSHOT_INTEGRITY in publication.source_identities
    assert P1_MANIFEST in publication.source_identities
    assert len(publication.provider_directives) == 93
    assert publication.active_bindings == ()


def test_p3_cash_records_are_direct_exact_and_effective_dated():
    publication = _publication()
    cash = tuple(item for item in publication.semantic_objects if type(item) is DirectListedInstrumentV2)
    directive_by_id = {item.canonical_object_id: item for item in publication.provider_directives}

    assert all(item.semantic_kind is CanonicalSemanticKind.DIRECT_LISTED_INSTRUMENT for item in cash)
    assert all(item.classification is CanonicalClassification.NSE_CASH_EQUITY for item in cash)
    assert all(item.exchange == "NSE" for item in cash)
    assert all(len(item.geometry) == 1 for item in cash)
    assert all(item.geometry[0].effective_from == publication.effective_from for item in cash)
    assert all(item.geometry[0].effective_through == publication.effective_through for item in cash)
    assert all(item.geometry[0].tick_size > 0 and item.geometry[0].lot_size == 1 for item in cash)
    assert all(directive_by_id[item.canonical_id].provider_symbol == item.canonical_symbol for item in cash)
    assert all(item.canonical_id in directive_by_id for item in cash)
    assert {item.classification_mapping_identity for item in directive_by_id.values()} == {
        "P3-KITE-NSE-CASH-EQUITY-MAPPING",
        "P3-KITE-NSE-INDEX-MAPPING",
    }


def test_nifty_and_banknifty_are_non_executable_analytical_subjects():
    publication = _publication()
    indexes = {
        item.canonical_symbol: item
        for item in publication.semantic_objects
        if type(item) is AnalyticalSubjectV2
    }
    directives = {item.canonical_object_id: item for item in publication.provider_directives}

    assert set(indexes) == {"NIFTY", "BANKNIFTY"}
    assert indexes["NIFTY"].canonical_id == "NSE-INDEX-NIFTY"
    assert indexes["BANKNIFTY"].canonical_id == "NSE-INDEX-BANKNIFTY"
    assert all(item.classification is CanonicalClassification.NSE_INDEX for item in indexes.values())
    assert all(not hasattr(item, "geometry") for item in indexes.values())
    assert directives["NSE-INDEX-NIFTY"].provider_symbol == "NIFTY 50"
    assert directives["NSE-INDEX-BANKNIFTY"].provider_symbol == "NIFTY BANK"
    assert publication.active_bindings == ()


def test_production_classification_mappings_are_only_the_exact_two_required():
    mappings = {item.mapping_identity: item for item in _publication().classification_mappings}
    assert set(mappings) == {
        "P3-KITE-NSE-CASH-EQUITY-MAPPING",
        "P3-KITE-NSE-INDEX-MAPPING",
    }
    assert mappings["P3-KITE-NSE-CASH-EQUITY-MAPPING"].provider_key == (
        "KITE", "NSE", "NSE", "EQ"
    )
    assert mappings["P3-KITE-NSE-CASH-EQUITY-MAPPING"].governed_subject_ids == ()
    assert mappings["P3-KITE-NSE-INDEX-MAPPING"].provider_key == (
        "KITE", "NSE", "INDICES", "EQ"
    )
    assert mappings["P3-KITE-NSE-INDEX-MAPPING"].governed_subject_ids == (
        "NSE-INDEX-NIFTY",
        "NSE-INDEX-BANKNIFTY",
    )


def test_all_93_exact_provider_submissions_resolve_and_geometry_mismatch_fails_closed():
    publication = _publication()
    submissions = _submissions(publication)
    resolver = InstrumentSemanticResolverV2(publication, submissions)
    observed_at = publication.effective_from

    cash = tuple(item for item in publication.semantic_objects if type(item) is DirectListedInstrumentV2)
    indexes = tuple(item for item in publication.semantic_objects if type(item) is AnalyticalSubjectV2)
    assert len(tuple(resolver.resolve_listed(item.canonical_id, observed_at) for item in cash)) == 91
    assert len(tuple(resolver.resolve_subject(item.canonical_id, observed_at) for item in indexes)) == 2

    reliance = next(item for item in submissions if item.provider_symbol == "RELIANCE")
    wrong = ProviderInstrumentSubmissionV2(
        provider_record_identity=reliance.provider_record_identity,
        provider=reliance.provider,
        provider_symbol=reliance.provider_symbol,
        exchange=reliance.exchange,
        segment=reliance.segment,
        provider_instrument_type=reliance.provider_instrument_type,
        tick_size=Decimal("0.05"),
        lot_size=reliance.lot_size,
        source_boundary=reliance.source_boundary,
        valid_through=reliance.valid_through,
        provenance=reliance.provenance,
    )
    replaced = tuple(wrong if item.provider_record_identity == wrong.provider_record_identity else item for item in submissions)
    with pytest.raises(V2ResolutionError) as error:
        InstrumentSemanticResolverV2(publication, replaced).resolve_listed("RELIANCE", observed_at)
    assert error.value.failure is V2ResolutionFailure.CANONICAL_GEOMETRY_MISMATCH


def test_missing_or_fuzzy_provider_evidence_fails_closed():
    publication = _publication()
    submissions = _submissions(publication)
    observed_at = publication.effective_from
    without_reliance = tuple(item for item in submissions if item.provider_symbol != "RELIANCE")
    with pytest.raises(V2ResolutionError) as error:
        InstrumentSemanticResolverV2(publication, without_reliance).resolve_listed("RELIANCE", observed_at)
    assert error.value.failure is V2ResolutionFailure.PROVIDER_ASSERTION_UNAVAILABLE

    reliance = next(item for item in submissions if item.provider_symbol == "RELIANCE")
    fuzzy = ProviderInstrumentSubmissionV2(
        provider_record_identity=reliance.provider_record_identity,
        provider="KITE",
        provider_symbol="RELIANCE-EQ",
        exchange="NSE",
        segment="NSE",
        provider_instrument_type="EQ",
        tick_size=reliance.tick_size,
        lot_size=reliance.lot_size,
        source_boundary=reliance.source_boundary,
        valid_through=reliance.valid_through,
        provenance=reliance.provenance,
    )
    replaced = tuple(fuzzy if item.provider_record_identity == fuzzy.provider_record_identity else item for item in submissions)
    with pytest.raises(V2ResolutionError) as error:
        InstrumentSemanticResolverV2(publication, replaced).resolve_listed("RELIANCE", observed_at)
    assert error.value.failure is V2ResolutionFailure.PROVIDER_BINDING_UNAVAILABLE


def _successor(publication):
    start = publication.effective_from
    end = publication.effective_through
    geometry = create_effective_geometry(
        geometry_identity="SYNTHETIC-GEOMETRY-FUTURECASH",
        geometry_version="1.0.0",
        canonical_object_id="NSE-EQ-FUTURECASH",
        tick_size=Decimal("0.05"),
        lot_size=1,
        effective_from=start,
        effective_through=end,
        source_identity="SYNTHETIC-GOVERNED-SECURITY-EVIDENCE",
        provenance=("P3-EXTENSIBILITY-PROOF",),
    )
    cash = create_direct_listed_instrument(
        canonical_id="NSE-EQ-FUTURECASH",
        canonical_symbol="FUTURECASH",
        exchange="NSE",
        classification=CanonicalClassification.NSE_CASH_EQUITY,
        valid_from=start,
        valid_through=end,
        source_identity="SYNTHETIC-GOVERNED-SECURITY-EVIDENCE",
        provenance=("P3-EXTENSIBILITY-PROOF",),
        geometry=(geometry,),
    )
    nse_index = create_analytical_subject(
        canonical_id="NSE-INDEX-FUTUREINDEX",
        canonical_symbol="FUTUREINDEX",
        exchange="NSE",
        classification=CanonicalClassification.NSE_INDEX,
        valid_from=start,
        valid_through=end,
        source_identity="SYNTHETIC-GOVERNED-NSE-INDEX-EVIDENCE",
        provenance=("P3-EXTENSIBILITY-PROOF",),
    )
    non_nse_index = create_analytical_subject(
        canonical_id="BSE-INDEX-FUTUREINDEX",
        canonical_symbol="FUTUREBSEINDEX",
        exchange="BSE",
        classification=CanonicalClassification.EXCHANGE_INDEX,
        valid_from=start,
        valid_through=end,
        source_identity="SYNTHETIC-GOVERNED-NON-NSE-INDEX-EVIDENCE",
        provenance=("P3-EXTENSIBILITY-PROOF",),
    )
    directive = create_provider_mapping_directive_v2(
        directive_identity="SYNTHETIC-DIRECTIVE-FUTURECASH",
        directive_version="1.0.0",
        canonical_object_id=cash.canonical_id,
        provider="KITE",
        provider_record_identity="PROVIDER-INSTRUMENT-RECORD-SYNTHETIC-FUTURECASH",
        provider_symbol=cash.canonical_symbol,
        classification_mapping_identity="P3-KITE-NSE-CASH-EQUITY-MAPPING",
        effective_from=start,
        effective_through=end,
        source_identity="SYNTHETIC-PROVIDER-EVIDENCE",
        provenance=("P3-EXTENSIBILITY-PROOF",),
        supersedes=None,
    )
    return create_semantic_publication_v2(
        publication_version="1.1.0",
        effective_from=start,
        effective_through=end,
        supersedes=publication.integrity_identity,
        source_identities=publication.source_identities + ("SYNTHETIC-P3-SUCCESSOR",),
        provenance=publication.provenance + ("P3-EXTENSIBILITY-PROOF",),
        semantic_objects=publication.semantic_objects + (cash, nse_index, non_nse_index),
        classification_mappings=publication.classification_mappings,
        provider_directives=publication.provider_directives + (directive,),
        active_bindings=publication.active_bindings,
    )


def test_successor_can_add_cash_nse_index_and_non_nse_index_without_schema_redesign(tmp_path):
    publication = _publication()
    predecessor = encode_semantic_publication_v2(publication)
    successor = _successor(publication)

    assert successor.schema_identity == publication.schema_identity
    assert tuple(field.name for field in fields(type(successor))) == tuple(
        field.name for field in fields(type(publication))
    )
    assert len(successor.semantic_objects) == 96
    assert successor.semantic_objects[:93] == publication.semantic_objects
    assert successor.semantic_objects[-1].exchange == "BSE"
    assert successor.semantic_objects[-1].classification is CanonicalClassification.EXCHANGE_INDEX
    assert encode_semantic_publication_v2(publication) == predecessor

    store = InstrumentSemanticV2Store(tmp_path.resolve())
    store.retain(publication)
    store.retain(successor)
    assert store.load(publication_identity=CANONICAL_INSTRUMENT_CATALOGUE_V2, publication_version="1.0.0") == publication
    assert store.load(publication_identity=CANONICAL_INSTRUMENT_CATALOGUE_V2, publication_version="1.1.0") == successor


def test_provider_presence_cannot_create_canonical_record_or_execution_eligibility():
    publication = _publication()
    submissions = _submissions(publication) + (
        ProviderInstrumentSubmissionV2(
            provider_record_identity="PROVIDER-INSTRUMENT-RECORD-KITE-ONLY",
            provider="KITE",
            provider_symbol="KITEONLY",
            exchange="NSE",
            segment="NSE",
            provider_instrument_type="EQ",
            tick_size=Decimal("0.05"),
            lot_size=1,
            source_boundary=publication.effective_from,
            valid_through=publication.effective_through,
            provenance=("SYNTHETIC-PROVIDER-PRESENCE",),
        ),
    )
    resolver = InstrumentSemanticResolverV2(publication, submissions)
    with pytest.raises(V2ResolutionError) as error:
        resolver.resolve_listed("NSE-EQ-KITEONLY", publication.effective_from)
    assert error.value.failure is V2ResolutionFailure.CANONICAL_SUBJECT_UNAVAILABLE
    assert publication.active_bindings == ()
    assert not any("execution" in item.canonical_id.lower() for item in publication.semantic_objects)


def test_reliance_v1_replay_is_immutable_and_v2_compatible():
    root = P3_PATH.parents[1] / "KRONOS-CANONICAL-INSTRUMENT-CATALOGUE-V1"
    for version, expected_hash in V1_HASHES.items():
        path = root / f"{version}.json"
        assert sha256(path.read_bytes()).hexdigest() == expected_hash
        assert load_canonical_instrument_catalogue(path.resolve()).publication_version == version

    v2 = next(item for item in _publication().semantic_objects if item.canonical_id == "RELIANCE")
    v1 = load_canonical_instrument_catalogue((root / "1.0.1.json").resolve()).instruments[0]
    assert v2.canonical_id == v1.canonical_instrument_id
    assert v2.canonical_symbol == v1.canonical_symbol
    assert v2.exchange == v1.exchange
    assert v2.geometry[0].tick_size == v1.tick_size == Decimal("0.1")
    assert v2.geometry[0].lot_size == v1.lot_size == 1


def test_intraday_universe_is_unchanged_and_canonical_coverage_is_separate():
    universe_path = Path(__file__).resolve().parents[3] / "data/intraday/KRONOS-INTRADAY-NATIVE-UNIVERSE-V1/1.0.0.json"
    assert sha256(universe_path.read_bytes()).hexdigest() == UNIVERSE_HASH
    universe = load_intraday_universe_publication(universe_path.resolve())
    assert len(universe.members) == 98
    assert sum(item.canonical_instrument_id is not None for item in universe.members) == 1
    assert len(_publication().semantic_objects) == 93


def test_no_bulk_provider_canonicalization_no_mcx_and_no_token_exposure():
    encoded = P3_PATH.read_bytes()
    document = json.loads(encoded)
    text = encoded.decode("ascii").lower()

    assert len(document["semantic_objects"]) == 93
    assert len(document["provider_directives"]) == 93
    assert all(item["exchange"] != "MCX" for item in document["semantic_objects"])
    assert not any(item["canonical_symbol"] in {"GOLDM", "SILVERM", "COPPER", "NATGAS", "CRUDE", "GOLD", "SILVER"} for item in document["semantic_objects"])
    assert "provider_instrument_token" not in text
    assert "instrument_token" not in text
    assert "access_token" not in text
    assert "authenticated_context" not in text
    assert "117015" not in text


def test_integrity_tamper_and_conflicting_duplicate_fail_closed(tmp_path):
    encoded = P3_PATH.read_bytes()
    parse_semantic_publication_v2(encoded)
    tampered = encoded.replace(b'"canonical_symbol":"ADANIENT"', b'"canonical_symbol":"TAMPERED"')
    with pytest.raises(V2ResolutionError) as error:
        parse_semantic_publication_v2(tampered)
    assert error.value.failure is V2ResolutionFailure.INTEGRITY_INVALID

    publication = _publication()
    store = InstrumentSemanticV2Store(tmp_path.resolve())
    first = store.retain(publication)
    assert store.retain(publication) == first
    first.write_bytes(b"conflict\n")
    with pytest.raises(V2ResolutionError) as error:
        store.retain(publication)
    assert error.value.failure is V2ResolutionFailure.INTEGRITY_INVALID


def test_current_counts_are_not_semantic_capacity_constants():
    semantic_source = (Path(__file__).resolve().parents[3] / "src/kronos/instrument/semantic_v2.py").read_text()
    persistence_source = (Path(__file__).resolve().parents[3] / "src/kronos/instrument/semantic_v2_persistence.py").read_text()
    combined = semantic_source + persistence_source
    assert "EXPECTED_EQUITY_COUNT" not in combined
    assert "MAX_EQUITIES" not in combined
    assert "maximum_index_count" not in combined
    assert "allowed_indices" not in combined
    assert "allowed_symbols" not in combined
    assert "91" not in combined
    assert "117015" not in combined
