from __future__ import annotations

from dataclasses import fields
from datetime import UTC, date, datetime
from decimal import Decimal
import json
from pathlib import Path

import pytest

from kronos.instrument.catalogue import load_canonical_instrument_catalogue
from kronos.instrument.semantic_v2 import (
    ACTIVE_DERIVATIVE_CONTRACT_BINDING_V1,
    CANONICAL_INSTRUMENT_CATALOGUE_V2,
    PROVIDER_CLASSIFICATION_MAPPING_V1,
    PROVIDER_MAPPING_DIRECTIVE_V2,
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
    create_classification_mapping,
    create_derivative_contract,
    create_direct_listed_instrument,
    create_effective_geometry,
    create_provider_mapping_directive_v2,
    create_semantic_publication_v2,
    encode_semantic_publication_v2,
    parse_semantic_publication_v2,
)
from kronos.instrument.semantic_v2_persistence import InstrumentSemanticV2Store
from kronos.intraday.universe import (
    EXPECTED_NATIVE_MEMBER_COUNT,
    load_intraday_universe_publication,
)


START = datetime(2026, 1, 1, tzinfo=UTC)
END = datetime(2027, 12, 31, tzinfo=UTC)
NOW = datetime(2026, 8, 22, tzinfo=UTC)
PROVENANCE = ("ADR-0014", "KRONOS-PLATFORM-WO-P2")


def _geometry(canonical_id: str, tick: str, lot: int = 1):
    return create_effective_geometry(
        geometry_identity=f"GEOMETRY-{canonical_id}",
        geometry_version="1.0.0",
        canonical_object_id=canonical_id,
        tick_size=Decimal(tick),
        lot_size=lot,
        effective_from=START,
        effective_through=END,
        source_identity="SYNTHETIC-GOVERNED-GEOMETRY",
        provenance=PROVENANCE,
    )


def _objects():
    reliance_geometry = _geometry("NSE-EQ-RELIANCE", "0.05")
    gold_sep_geometry = _geometry("MCX-FUT-GOLDM-2026-09-04", "1")
    gold_oct_geometry = _geometry("MCX-FUT-GOLDM-2026-10-05", "1")
    reliance = create_direct_listed_instrument(
        canonical_id="NSE-EQ-RELIANCE",
        canonical_symbol="RELIANCE",
        exchange="NSE",
        classification=CanonicalClassification.NSE_CASH_EQUITY,
        valid_from=START,
        valid_through=END,
        source_identity="SYNTHETIC-RELIANCE-V2",
        provenance=PROVENANCE,
        geometry=(reliance_geometry,),
    )
    nifty = create_analytical_subject(
        canonical_id="NSE-INDEX-NIFTY",
        canonical_symbol="NIFTY",
        exchange="NSE",
        classification=CanonicalClassification.NSE_INDEX,
        valid_from=START,
        valid_through=END,
        source_identity="SYNTHETIC-NIFTY",
        provenance=PROVENANCE,
    )
    banknifty = create_analytical_subject(
        canonical_id="NSE-INDEX-BANKNIFTY",
        canonical_symbol="BANKNIFTY",
        exchange="NSE",
        classification=CanonicalClassification.NSE_INDEX,
        valid_from=START,
        valid_through=END,
        source_identity="SYNTHETIC-BANKNIFTY",
        provenance=PROVENANCE,
    )
    goldm = create_analytical_subject(
        canonical_id="MCX-SUBJECT-GOLDM",
        canonical_symbol="GOLDM",
        exchange="MCX",
        classification=CanonicalClassification.MCX_COMMODITY,
        valid_from=START,
        valid_through=END,
        source_identity="SYNTHETIC-GOLDM",
        provenance=PROVENANCE,
    )
    natgas = create_analytical_subject(
        canonical_id="MCX-SUBJECT-NATGAS",
        canonical_symbol="NATGAS",
        exchange="MCX",
        classification=CanonicalClassification.MCX_COMMODITY,
        valid_from=START,
        valid_through=END,
        source_identity="SYNTHETIC-NATGAS",
        provenance=PROVENANCE,
    )
    crude = create_analytical_subject(
        canonical_id="MCX-SUBJECT-CRUDE",
        canonical_symbol="CRUDE",
        exchange="MCX",
        classification=CanonicalClassification.MCX_COMMODITY,
        valid_from=START,
        valid_through=END,
        source_identity="SYNTHETIC-CRUDE",
        provenance=PROVENANCE,
    )
    gold_sep = create_derivative_contract(
        canonical_id="MCX-FUT-GOLDM-2026-09-04",
        canonical_symbol="GOLDM26SEPFUT",
        exchange="MCX",
        classification=CanonicalClassification.MCX_FUTURE,
        parent_subject_id=goldm.canonical_id,
        expiry=date(2026, 9, 4),
        valid_from=START,
        valid_through=END,
        source_identity="SYNTHETIC-GOLDM-SEP",
        provenance=PROVENANCE,
        geometry=(gold_sep_geometry,),
    )
    gold_oct = create_derivative_contract(
        canonical_id="MCX-FUT-GOLDM-2026-10-05",
        canonical_symbol="GOLDM26OCTFUT",
        exchange="MCX",
        classification=CanonicalClassification.MCX_FUTURE,
        parent_subject_id=goldm.canonical_id,
        expiry=date(2026, 10, 5),
        valid_from=START,
        valid_through=END,
        source_identity="SYNTHETIC-GOLDM-OCT",
        provenance=PROVENANCE,
        geometry=(gold_oct_geometry,),
    )
    return reliance, nifty, banknifty, goldm, natgas, crude, gold_sep, gold_oct


def _mapping(
    identity: str,
    exchange: str,
    segment: str,
    provider_type: str,
    classification: CanonicalClassification,
    subjects: tuple[str, ...] = (),
    *,
    start: datetime = START,
    end: datetime = END,
):
    return create_classification_mapping(
        mapping_identity=identity,
        mapping_version="1.0.0",
        provider="KITE",
        exchange=exchange,
        segment=segment,
        provider_instrument_type=provider_type,
        canonical_classification=classification,
        governed_subject_ids=subjects,
        effective_from=start,
        effective_through=end,
        source_identity="SYNTHETIC-CLASSIFICATION-AUTHORITY",
        provenance=PROVENANCE,
        supersedes=None,
    )


def _directive(canonical_id: str, symbol: str, record: str, mapping: str):
    return create_provider_mapping_directive_v2(
        directive_identity=f"DIRECTIVE-{canonical_id}",
        directive_version="1.0.0",
        canonical_object_id=canonical_id,
        provider="KITE",
        provider_record_identity=record,
        provider_symbol=symbol,
        classification_mapping_identity=mapping,
        effective_from=START,
        effective_through=END,
        source_identity="SYNTHETIC-EAIC-002",
        provenance=PROVENANCE,
        supersedes=None,
    )


def _submission(
    record: str,
    symbol: str,
    exchange: str,
    segment: str,
    provider_type: str,
    tick: str | None,
    lot: int | None,
):
    return ProviderInstrumentSubmissionV2(
        provider_record_identity=record,
        provider="KITE",
        provider_symbol=symbol,
        exchange=exchange,
        segment=segment,
        provider_instrument_type=provider_type,
        tick_size=None if tick is None else Decimal(tick),
        lot_size=lot,
        source_boundary=START,
        valid_through=END,
        provenance=("EAIC-002", "SYNTHETIC-PROVIDER-FACT"),
    )


def _fixture(*, active_binding: bool = True, mappings=()):
    objects = _objects()
    reliance, nifty, banknifty, goldm, _, _, gold_sep, _ = objects
    base_mappings = (
        _mapping("MAP-KITE-NSE-CASH", "NSE", "NSE", "EQ", CanonicalClassification.NSE_CASH_EQUITY),
        _mapping(
            "MAP-KITE-NSE-INDEX",
            "NSE",
            "INDICES",
            "EQ",
            CanonicalClassification.NSE_INDEX,
            (nifty.canonical_id, banknifty.canonical_id),
        ),
        _mapping("MAP-KITE-MCX-FUT", "MCX", "MCX-FUT", "FUT", CanonicalClassification.MCX_FUTURE),
    )
    directives = (
        _directive(reliance.canonical_id, "RELIANCE", "PROVIDER-INSTRUMENT-RECORD-RELIANCE", "MAP-KITE-NSE-CASH"),
        _directive(nifty.canonical_id, "NIFTY 50", "PROVIDER-INSTRUMENT-RECORD-NIFTY", "MAP-KITE-NSE-INDEX"),
        _directive(banknifty.canonical_id, "NIFTY BANK", "PROVIDER-INSTRUMENT-RECORD-BANKNIFTY", "MAP-KITE-NSE-INDEX"),
        _directive(gold_sep.canonical_id, "GOLDM26SEPFUT", "PROVIDER-INSTRUMENT-RECORD-GOLDM-SEP", "MAP-KITE-MCX-FUT"),
    )
    binding = create_active_derivative_binding(
        binding_identity="ACTIVE-GOLDM-SEP",
        binding_version="1.0.0",
        subject_id=goldm.canonical_id,
        derivative_contract_id=gold_sep.canonical_id,
        effective_from=START,
        effective_through=datetime(2026, 9, 3, tzinfo=UTC),
        contract_expiry=gold_sep.expiry,
        provider_reference_identity=f"DIRECTIVE-{gold_sep.canonical_id}",
        source_identity="SYNTHETIC-SELECTION-AUTHORITY",
        provenance=PROVENANCE,
        supersedes=None,
    )
    publication = create_semantic_publication_v2(
        publication_version="1.0.0",
        effective_from=START,
        effective_through=END,
        supersedes=None,
        source_identities=("ADR-0014", "WO-P2-SYNTHETIC"),
        provenance=PROVENANCE,
        semantic_objects=objects,
        classification_mappings=base_mappings + tuple(mappings),
        provider_directives=directives,
        active_bindings=(binding,) if active_binding else (),
    )
    submissions = (
        _submission("PROVIDER-INSTRUMENT-RECORD-RELIANCE", "RELIANCE", "NSE", "NSE", "EQ", "0.05", 1),
        _submission("PROVIDER-INSTRUMENT-RECORD-NIFTY", "NIFTY 50", "NSE", "INDICES", "EQ", None, None),
        _submission("PROVIDER-INSTRUMENT-RECORD-BANKNIFTY", "NIFTY BANK", "NSE", "INDICES", "EQ", None, None),
        _submission("PROVIDER-INSTRUMENT-RECORD-GOLDM-SEP", "GOLDM26SEPFUT", "MCX", "MCX-FUT", "FUT", "1", 1),
    )
    return publication, submissions


def _failure(call, expected: V2ResolutionFailure) -> None:
    with pytest.raises(V2ResolutionError) as captured:
        call()
    assert captured.value.failure is expected


def _rebuild(publication, **changes):
    values = {
        name: getattr(publication, name)
        for name in publication.__dataclass_fields__
        if name != "integrity_identity"
    }
    values.update(changes)
    return create_semantic_publication_v2(**values)


def test_v1_catalogue_history_and_reliance_meaning_remain_replayable() -> None:
    root = Path(__file__).resolve().parents[3]
    catalogue_root = root / "data/instruments/KRONOS-CANONICAL-INSTRUMENT-CATALOGUE-V1"
    old = load_canonical_instrument_catalogue((catalogue_root / "1.0.0.json").resolve())
    current = load_canonical_instrument_catalogue((catalogue_root / "1.0.1.json").resolve())
    assert (old.publication_version, current.publication_version) == ("1.0.0", "1.0.1")
    assert old.instruments[0].canonical_instrument_id == current.instruments[0].canonical_instrument_id
    assert old.instruments[0].canonical_symbol == "RELIANCE"


def test_v2_semantic_kinds_and_parent_relationship_are_explicit() -> None:
    publication, _ = _fixture()
    reliance, nifty, _, goldm, _, _, gold_sep, gold_oct = publication.semantic_objects
    assert type(reliance) is DirectListedInstrumentV2
    assert reliance.semantic_kind is CanonicalSemanticKind.DIRECT_LISTED_INSTRUMENT
    assert type(nifty) is AnalyticalSubjectV2
    assert nifty.semantic_kind is CanonicalSemanticKind.ANALYTICAL_SUBJECT
    assert type(gold_sep) is DerivativeContractV2
    assert gold_sep.parent_subject_id == goldm.canonical_id
    assert gold_sep.canonical_id != goldm.canonical_id != gold_oct.canonical_id


def test_contract_identities_and_versions_are_governed() -> None:
    publication, _ = _fixture()
    assert publication.schema_identity == CANONICAL_INSTRUMENT_CATALOGUE_V2
    assert publication.classification_mappings[0].contract_identity == PROVIDER_CLASSIFICATION_MAPPING_V1
    assert publication.provider_directives[0].contract_identity == PROVIDER_MAPPING_DIRECTIVE_V2
    assert publication.active_bindings[0].contract_identity == ACTIVE_DERIVATIVE_CONTRACT_BINDING_V1
    assert {item.mapping_version for item in publication.classification_mappings} == {"1.0.0"}


def test_mapping_directive_and_binding_require_explicit_identity_version_lookup() -> None:
    publication, _ = _fixture()
    assert publication.classification_mapping(
        mapping_identity="MAP-KITE-NSE-CASH",
        mapping_version="1.0.0",
    ).canonical_classification is CanonicalClassification.NSE_CASH_EQUITY
    assert publication.provider_directive(
        directive_identity="DIRECTIVE-NSE-EQ-RELIANCE",
        directive_version="1.0.0",
    ).provider_symbol == "RELIANCE"
    assert publication.active_binding(
        binding_identity="ACTIVE-GOLDM-SEP",
        binding_version="1.0.0",
    ).derivative_contract_id == "MCX-FUT-GOLDM-2026-09-04"
    _failure(
        lambda: publication.classification_mapping(
            mapping_identity="MAP-KITE-NSE-CASH",
            mapping_version="9.9.9",
        ),
        V2ResolutionFailure.CLASSIFICATION_MAPPING_UNAVAILABLE,
    )


def test_exact_mappings_resolve_reliance_nifty_and_banknifty() -> None:
    publication, submissions = _fixture()
    resolver = InstrumentSemanticResolverV2(publication, submissions)
    listed = resolver.resolve_listed("NSE-EQ-RELIANCE", NOW)
    nifty = resolver.resolve_subject("NSE-INDEX-NIFTY", NOW)
    bank = resolver.resolve_subject("NSE-INDEX-BANKNIFTY", NOW)
    assert listed.canonical.classification is CanonicalClassification.NSE_CASH_EQUITY
    assert nifty.provider_submission is not None and nifty.provider_submission.provider_symbol == "NIFTY 50"
    assert bank.provider_submission is not None and bank.provider_submission.provider_symbol == "NIFTY BANK"


def test_unknown_or_case_guessed_mapping_fails_closed() -> None:
    publication, submissions = _fixture()
    wrong = _submission("PROVIDER-INSTRUMENT-RECORD-RELIANCE", "RELIANCE", "nse", "NSE", "EQ", "0.05", 1)
    resolver = InstrumentSemanticResolverV2(publication, (wrong,) + submissions[1:])
    _failure(
        lambda: resolver.resolve_listed("NSE-EQ-RELIANCE", NOW),
        V2ResolutionFailure.CLASSIFICATION_MAPPING_UNAVAILABLE,
    )


def test_conflicting_governed_mapping_fails_closed() -> None:
    conflict = _mapping(
        "MAP-CONFLICT",
        "NSE",
        "NSE",
        "EQ",
        CanonicalClassification.MCX_FUTURE,
    )
    publication, submissions = _fixture(mappings=(conflict,))
    resolver = InstrumentSemanticResolverV2(publication, submissions)
    _failure(
        lambda: resolver.resolve_listed("NSE-EQ-RELIANCE", NOW),
        V2ResolutionFailure.CANONICAL_CLASSIFICATION_CONFLICT,
    )


def test_mapping_is_effective_dated_and_exact_identity_selected() -> None:
    publication, submissions = _fixture()
    resolver = InstrumentSemanticResolverV2(publication, submissions)
    _failure(
        lambda: resolver.resolve_listed("NSE-EQ-RELIANCE", datetime(2028, 1, 1, tzinfo=UTC)),
        V2ResolutionFailure.PUBLICATION_STALE,
    )
    assert resolver.resolve_listed("NSE-EQ-RELIANCE", NOW).provider_directive.classification_mapping_identity == "MAP-KITE-NSE-CASH"


def test_provider_token_cannot_enter_v2_identity_contracts() -> None:
    contract_types = (
        ProviderInstrumentSubmissionV2,
        type(_fixture()[0].provider_directives[0]),
        type(_fixture()[0].classification_mappings[0]),
    )
    for contract_type in contract_types:
        names = {item.name for item in fields(contract_type)}
        assert "provider_instrument_token" not in names
        assert "exchange_token" not in names


def test_provider_record_identity_is_safe_mapping_reference() -> None:
    publication, submissions = _fixture()
    result = InstrumentSemanticResolverV2(publication, submissions).resolve_listed("NSE-EQ-RELIANCE", NOW)
    assert result.provider_directive.provider_record_identity == "PROVIDER-INSTRUMENT-RECORD-RELIANCE"


def test_provider_symbol_mismatch_fails_as_binding_unavailable() -> None:
    publication, submissions = _fixture()
    wrong = _submission(
        "PROVIDER-INSTRUMENT-RECORD-RELIANCE",
        "RELIANCE-WRONG",
        "NSE",
        "NSE",
        "EQ",
        "0.05",
        1,
    )
    resolver = InstrumentSemanticResolverV2(publication, (wrong,) + submissions[1:])
    _failure(
        lambda: resolver.resolve_listed("NSE-EQ-RELIANCE", NOW),
        V2ResolutionFailure.PROVIDER_BINDING_UNAVAILABLE,
    )


def test_effective_geometry_and_precision_are_exact() -> None:
    publication, submissions = _fixture()
    result = InstrumentSemanticResolverV2(publication, submissions).resolve_listed("NSE-EQ-RELIANCE", NOW)
    assert (result.geometry.tick_size, result.geometry.lot_size, result.geometry.price_precision) == (Decimal("0.05"), 1, 2)


def test_geometry_mismatch_fails_closed() -> None:
    publication, submissions = _fixture()
    wrong = _submission("PROVIDER-INSTRUMENT-RECORD-RELIANCE", "RELIANCE", "NSE", "NSE", "EQ", "0.10", 1)
    resolver = InstrumentSemanticResolverV2(publication, (wrong,) + submissions[1:])
    _failure(
        lambda: resolver.resolve_listed("NSE-EQ-RELIANCE", NOW),
        V2ResolutionFailure.CANONICAL_GEOMETRY_MISMATCH,
    )


def test_goldm_active_binding_resolves_exact_contract_without_selection() -> None:
    publication, submissions = _fixture()
    resolver = InstrumentSemanticResolverV2(publication, submissions)
    runtime = resolver.resolve_active_contract("MCX-SUBJECT-GOLDM", NOW)
    assert runtime.subject.canonical_id == "MCX-SUBJECT-GOLDM"
    assert runtime.contract.canonical_id == "MCX-FUT-GOLDM-2026-09-04"
    assert runtime.contract.parent_subject_id == runtime.subject.canonical_id


def test_multiple_contracts_without_binding_do_not_auto_select() -> None:
    publication, submissions = _fixture(active_binding=False)
    resolver = InstrumentSemanticResolverV2(publication, submissions)
    subject = resolver.resolve_subject("MCX-SUBJECT-GOLDM", NOW)
    assert subject.active_contract_id is None
    assert sum(type(item) is DerivativeContractV2 for item in publication.semantic_objects) == 2
    _failure(
        lambda: resolver.resolve_active_contract("MCX-SUBJECT-GOLDM", NOW),
        V2ResolutionFailure.ACTIVE_CONTRACT_BINDING_UNAVAILABLE,
    )


def test_unknown_canonical_subject_fails_without_fallback_identity() -> None:
    publication, submissions = _fixture()
    resolver = InstrumentSemanticResolverV2(publication, submissions)
    _failure(
        lambda: resolver.resolve_subject("MCX-SUBJECT-UNKNOWN", NOW),
        V2ResolutionFailure.CANONICAL_SUBJECT_UNAVAILABLE,
    )


@pytest.mark.parametrize("subject_id", ["MCX-SUBJECT-NATGAS", "MCX-SUBJECT-CRUDE"])
def test_persistent_subject_survives_unavailable_provider_path(subject_id: str) -> None:
    publication, submissions = _fixture()
    resolver = InstrumentSemanticResolverV2(publication, submissions)
    subject = resolver.resolve_subject(subject_id, NOW)
    assert subject.canonical.canonical_id == subject_id
    assert subject.provider_submission is None
    assert subject.active_contract_id is None
    _failure(
        lambda: resolver.resolve_active_contract(subject_id, NOW),
        V2ResolutionFailure.ACTIVE_CONTRACT_BINDING_UNAVAILABLE,
    )


def test_missing_provider_assertion_and_stale_source_fail_closed() -> None:
    publication, submissions = _fixture()
    resolver = InstrumentSemanticResolverV2(publication, submissions[1:])
    _failure(
        lambda: resolver.resolve_listed("NSE-EQ-RELIANCE", NOW),
        V2ResolutionFailure.PROVIDER_ASSERTION_UNAVAILABLE,
    )
    stale = ProviderInstrumentSubmissionV2(
        **{
            name: getattr(submissions[0], name)
            for name in submissions[0].__dataclass_fields__
            if name not in {"source_boundary", "valid_through"}
        },
        source_boundary=datetime(2025, 1, 1, tzinfo=UTC),
        valid_through=datetime(2025, 12, 31, tzinfo=UTC),
    )
    resolver = InstrumentSemanticResolverV2(publication, (stale,) + submissions[1:])
    _failure(
        lambda: resolver.resolve_listed("NSE-EQ-RELIANCE", NOW),
        V2ResolutionFailure.SOURCE_STALE,
    )


def test_deterministic_integrity_roundtrip_and_tamper_rejection() -> None:
    publication, _ = _fixture()
    first = encode_semantic_publication_v2(publication)
    second = encode_semantic_publication_v2(publication)
    assert first == second
    assert parse_semantic_publication_v2(first) == publication
    document = json.loads(first)
    document["semantic_objects"][0]["canonical_symbol"] = "TAMPERED"
    tampered = (json.dumps(document, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n").encode("ascii")
    _failure(
        lambda: parse_semantic_publication_v2(tampered),
        V2ResolutionFailure.INTEGRITY_INVALID,
    )


def test_explicit_identity_version_store_is_idempotent_and_restart_safe(tmp_path: Path) -> None:
    publication, _ = _fixture()
    store = InstrumentSemanticV2Store(tmp_path.resolve())
    retained = store.retain(publication)
    assert store.retain(publication) == retained
    restarted = InstrumentSemanticV2Store(tmp_path.resolve())
    assert restarted.load(
        publication_identity=CANONICAL_INSTRUMENT_CATALOGUE_V2,
        publication_version="1.0.0",
    ) == publication
    _failure(
        lambda: restarted.load(
            publication_identity=CANONICAL_INSTRUMENT_CATALOGUE_V2,
            publication_version="9.9.9",
        ),
        V2ResolutionFailure.CANONICAL_SUBJECT_UNAVAILABLE,
    )


def test_store_rejects_conflicting_duplicate_version(tmp_path: Path) -> None:
    publication, _ = _fixture()
    store = InstrumentSemanticV2Store(tmp_path.resolve())
    store.retain(publication)
    conflicting = _rebuild(
        publication,
        source_identities=("ADR-0014", "CONFLICTING-SAME-VERSION"),
    )
    _failure(
        lambda: store.retain(conflicting),
        V2ResolutionFailure.INTEGRITY_INVALID,
    )


def test_intraday_universe_membership_is_unchanged() -> None:
    universe = load_intraday_universe_publication()
    assert len(universe.members) == EXPECTED_NATIVE_MEMBER_COUNT == 98
    assert universe.publication_version == "1.0.0"


def test_no_selection_heuristic_vocabulary_exists_in_runtime_module() -> None:
    source = Path(__file__).resolve().parents[3] / "src/kronos/instrument/semantic_v2.py"
    text = source.read_text(encoding="utf-8").lower()
    for prohibited in ("nearest_expiry", "front_month", "highest_volume", "highest_oi", "most_liquid"):
        assert prohibited not in text
