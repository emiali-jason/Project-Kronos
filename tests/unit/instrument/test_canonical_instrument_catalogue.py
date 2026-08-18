from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from kronos.instrument.catalogue import (
    CANONICAL_INSTRUMENT_CATALOGUE_IDENTITY,
    DEFAULT_CANONICAL_INSTRUMENT_CATALOGUE_PATH,
    CanonicalCatalogueError,
    CanonicalCatalogueFailure,
    load_canonical_instrument_catalogue,
    parse_canonical_catalogue_publication,
    seal_canonical_catalogue_document,
)
from kronos.instrument.runtime import (
    ExecutionContextAvailability,
    ProviderBindingStatus,
    create_provider_assertion,
)


IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 8, 18, 19, 0, tzinfo=IST)
VALID_THROUGH = datetime(2026, 12, 31, 23, 59, 59, tzinfo=IST)


def _source(
    *,
    version: str = "1.0.0",
    supersedes: str | None = None,
    tick: object = "0.05",
    lot: object = 1,
) -> dict[str, object]:
    return {
        "schema_identity": CANONICAL_INSTRUMENT_CATALOGUE_IDENTITY,
        "publication_identity": CANONICAL_INSTRUMENT_CATALOGUE_IDENTITY,
        "publication_version": version,
        "valid_from": "2026-08-18T00:00:00+05:30",
        "valid_through": VALID_THROUGH.isoformat(),
        "source_boundary": "2026-08-18T00:00:00+05:30",
        "supersedes": supersedes,
        "source_identities": ["ADP-001I-V1.0", "DOMAIN-006-ASSERTION-V1"],
        "provenance": ["identity_owner=DOMAIN-001"],
        "instruments": [
            {
                "canonical_instrument_id": "RELIANCE",
                "canonical_symbol": "RELIANCE",
                "canonical_name": "Reliance Industries Limited",
                "exchange": "NSE",
                "segment": "NSE",
                "instrument_type": "EQ",
                "tick_size": tick,
                "lot_size": lot,
                "availability": "AVAILABLE",
                "valid_from": "2026-08-18T00:00:00+05:30",
                "valid_through": VALID_THROUGH.isoformat(),
                "source_identities": ["ADP-001I:RELIANCE"],
                "provenance": ["provider_presence_not_identity=true"],
            }
        ],
        "binding_directives": [
            {
                "canonical_instrument_id": "RELIANCE",
                "provider_identity": "KITE",
                "expected_provider_symbol": "RELIANCE",
                "directive_version": version,
                "valid_from": "2026-08-18T00:00:00+05:30",
                "valid_through": VALID_THROUGH.isoformat(),
                "source_identity": "DOMAIN-001-BINDINGS-V1",
                "source_boundary": "2026-08-18T00:00:00+05:30",
                "provenance": ["mapping_owner=DOMAIN-001"],
            }
        ],
    }


def _publication(**changes: object):  # type: ignore[no-untyped-def]
    source = _source()
    source.update(changes)
    return parse_canonical_catalogue_publication(
        seal_canonical_catalogue_document(source)
    )


def _assertion(
    *,
    symbol: str = "RELIANCE",
    token: int = 738561,
    segment: str = "NSE",
    instrument_type: str = "EQ",
    tick: Decimal = Decimal("0.1"),
    lot: int = 1,
):  # type: ignore[no-untyped-def]
    return create_provider_assertion(
        provider="KITE",
        provider_symbol=symbol,
        provider_instrument_token=token,
        exchange="NSE",
        segment=segment,
        instrument_type=instrument_type,
        asserted_tick_size=tick,
        asserted_lot_size=lot,
        binding_source_identity="KITE-INSTRUMENT-MASTER-20260818",
        source_boundary=NOW,
        valid_through=VALID_THROUGH,
    )


def test_production_catalogue_is_exact_reviewed_immutable_publication() -> None:
    catalogue = load_canonical_instrument_catalogue()

    assert catalogue.publication_identity == CANONICAL_INSTRUMENT_CATALOGUE_IDENTITY
    assert catalogue.publication_version == "1.0.1"
    assert catalogue.supersedes == "1.0.0"
    assert tuple(item.canonical_instrument_id for item in catalogue.instruments) == (
        "RELIANCE",
    )
    record = catalogue.instruments[0]
    assert record.canonical_name == "Reliance Industries Limited"
    assert (record.exchange, record.segment, record.instrument_type) == ("NSE", "NSE", "EQ")
    assert (record.tick_size, record.lot_size, record.price_precision) == (
        Decimal("0.1"),
        1,
        1,
    )
    with pytest.raises(FrozenInstanceError):
        record.canonical_symbol = "CHANGED"  # type: ignore[misc]


def test_superseding_publication_preserves_immutable_1_0_0_and_other_facts() -> None:
    old_path = DEFAULT_CANONICAL_INSTRUMENT_CATALOGUE_PATH.with_name("1.0.0.json")
    old_bytes = old_path.read_bytes()
    old = load_canonical_instrument_catalogue(old_path)
    current = load_canonical_instrument_catalogue()

    assert sha256(old_bytes).hexdigest() == (
        "b5a7ce48af7a123cb513bf5acacaea11e878d0ada3f8c5de99895f3fd29d4cdc"
    )
    assert old.publication_version == "1.0.0"
    assert old.supersedes is None
    assert current.publication_version == "1.0.1"
    assert current.supersedes == "1.0.0"
    assert old.integrity_identity != current.integrity_identity
    old_record = old.instruments[0]
    current_record = current.instruments[0]
    assert (old_record.tick_size, old_record.price_precision) == (Decimal("0.05"), 2)
    assert (current_record.tick_size, current_record.price_precision) == (Decimal("0.1"), 1)
    assert (
        old_record.canonical_instrument_id,
        old_record.canonical_symbol,
        old_record.canonical_name,
        old_record.exchange,
        old_record.segment,
        old_record.instrument_type,
        old_record.lot_size,
        old_record.availability,
        old_record.valid_through,
    ) == (
        current_record.canonical_instrument_id,
        current_record.canonical_symbol,
        current_record.canonical_name,
        current_record.exchange,
        current_record.segment,
        current_record.instrument_type,
        current_record.lot_size,
        current_record.availability,
        current_record.valid_through,
    )
    assert old.binding_directives == current.binding_directives
    assert tuple(item.canonical_instrument_id for item in old.instruments) == tuple(
        item.canonical_instrument_id for item in current.instruments
    ) == ("RELIANCE",)


def test_sealing_is_deterministic_and_source_document_remains_reviewable() -> None:
    first = seal_canonical_catalogue_document(_source())
    second = seal_canonical_catalogue_document(_source())
    assert first == second
    document = json.loads(first)
    assert document["instruments"][0]["canonical_instrument_id"] == "RELIANCE"
    assert document["binding_directives"][0]["expected_provider_symbol"] == "RELIANCE"
    assert document["integrity_identity"].startswith("CATALOGUE-PUBLICATION-")


@pytest.mark.parametrize(
    ("tick", "precision"),
    [("1", 0), ("0.5", 1), ("0.05", 2), ("0.0025", 4)],
)
def test_price_precision_is_exact_decimal_minimum(tick: str, precision: int) -> None:
    publication = parse_canonical_catalogue_publication(
        seal_canonical_catalogue_document(_source(tick=tick))
    )
    assert publication.instruments[0].price_precision == precision


@pytest.mark.parametrize("tick", [None, 0, "-0.05", "not-a-decimal"])
def test_invalid_or_missing_tick_is_unavailable_and_execution_incomplete(tick: object) -> None:
    publication = parse_canonical_catalogue_publication(
        seal_canonical_catalogue_document(_source(tick=tick))
    )
    record = publication.instruments[0]
    runtime = publication.runtime_registry(
        provider_assertions=(),
        observed_at=NOW,
    ).lookup("RELIANCE")
    assert record.tick_size is None
    assert record.price_precision is None
    assert runtime.execution_context is ExecutionContextAvailability.INCOMPLETE


def test_provider_assertion_binds_through_domain_001_runtime_path() -> None:
    registry = load_canonical_instrument_catalogue().runtime_registry(
        provider_assertions=(_assertion(),),
        observed_at=NOW,
    )
    runtime = registry.require_consumable("RELIANCE")
    assert runtime.binding_status is ProviderBindingStatus.BOUND
    assert runtime.provider_binding is not None
    assert runtime.provider_binding.provider_symbol == "RELIANCE"
    assert runtime.provider_binding.provider_instrument_token == 738561
    assert "738561" not in runtime.canonical.integrity_identity


def test_unknown_kite_only_instrument_never_creates_canonical_membership() -> None:
    unknown = _assertion(symbol="KITEONLY", token=999001)
    registry = load_canonical_instrument_catalogue().runtime_registry(
        provider_assertions=(_assertion(), unknown),
        observed_at=NOW,
    )
    assert tuple(item.canonical.canonical_instrument_id for item in registry.instruments) == (
        "RELIANCE",
    )
    with pytest.raises(ValueError, match="RUNTIME_INSTRUMENT_UNAVAILABLE"):
        registry.lookup("KITEONLY")


def test_canonical_exists_when_provider_assertion_is_missing() -> None:
    runtime = load_canonical_instrument_catalogue().runtime_registry(
        provider_assertions=(),
        observed_at=NOW,
    ).lookup("RELIANCE")
    assert runtime.canonical.canonical_instrument_id == "RELIANCE"
    assert runtime.binding_status is ProviderBindingStatus.UNAVAILABLE
    assert runtime.execution_context is ExecutionContextAvailability.INCOMPLETE


@pytest.mark.parametrize(
    "assertion",
    [
        _assertion(segment="INDICES"),
        _assertion(instrument_type="FUT"),
        _assertion(tick=Decimal("0.01")),
        _assertion(lot=2),
    ],
)
def test_mismatched_assertion_fails_binding_closed(assertion) -> None:  # type: ignore[no-untyped-def]
    runtime = load_canonical_instrument_catalogue().runtime_registry(
        provider_assertions=(assertion,),
        observed_at=NOW,
    ).lookup("RELIANCE")
    assert runtime.binding_status is ProviderBindingStatus.UNAVAILABLE
    assert runtime.execution_context is ExecutionContextAvailability.INCOMPLETE


def test_provider_symbol_change_without_new_directive_fails_closed() -> None:
    runtime = load_canonical_instrument_catalogue().runtime_registry(
        provider_assertions=(_assertion(symbol="RELIANCE-NEW"),),
        observed_at=NOW,
    ).lookup("RELIANCE")
    assert runtime.binding_status is ProviderBindingStatus.UNAVAILABLE


@pytest.mark.parametrize("area", ["publication", "instrument", "directive"])
def test_any_tamper_is_rejected(area: str) -> None:
    document = json.loads(seal_canonical_catalogue_document(_source()))
    if area == "publication":
        document["publication_version"] = "tampered"
    elif area == "instrument":
        document["instruments"][0]["tick_size"] = "99"
    else:
        document["binding_directives"][0]["expected_provider_symbol"] = "OTHER"
    if area != "publication":
        core = {key: value for key, value in document.items() if key != "integrity_identity"}
        encoded_core = json.dumps(
            core,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        document["integrity_identity"] = (
            f"CATALOGUE-PUBLICATION-{sha256(encoded_core).hexdigest()}"
        )
    with pytest.raises(CanonicalCatalogueError) as captured:
        parse_canonical_catalogue_publication(json.dumps(document).encode())
    expected = (
        CanonicalCatalogueFailure.INTEGRITY_MISMATCH
        if area == "publication"
        else CanonicalCatalogueFailure.PUBLICATION_INVALID
    )
    assert captured.value.failure is expected


def test_stale_publication_is_unavailable() -> None:
    with pytest.raises(CanonicalCatalogueError) as captured:
        load_canonical_instrument_catalogue().runtime_registry(
            provider_assertions=(),
            observed_at=VALID_THROUGH + timedelta(seconds=1),
        )
    assert captured.value.failure is CanonicalCatalogueFailure.PUBLICATION_STALE


def test_duplicate_canonical_and_conflicting_directives_are_rejected() -> None:
    duplicate_record = _source()
    duplicate_record["instruments"] = duplicate_record["instruments"] * 2  # type: ignore[operator]
    with pytest.raises(CanonicalCatalogueError) as record_error:
        parse_canonical_catalogue_publication(
            seal_canonical_catalogue_document(duplicate_record)
        )
    assert record_error.value.failure is CanonicalCatalogueFailure.PUBLICATION_INVALID

    duplicate_directive = _source()
    duplicate_directive["binding_directives"] = duplicate_directive["binding_directives"] * 2  # type: ignore[operator]
    with pytest.raises(CanonicalCatalogueError) as directive_error:
        parse_canonical_catalogue_publication(
            seal_canonical_catalogue_document(duplicate_directive)
        )
    assert directive_error.value.failure is CanonicalCatalogueFailure.PUBLICATION_INVALID


def test_catalogue_version_is_new_publication_not_mutation() -> None:
    first_bytes = seal_canonical_catalogue_document(_source())
    first = parse_canonical_catalogue_publication(first_bytes)
    second = parse_canonical_catalogue_publication(
        seal_canonical_catalogue_document(
            _source(version="2.0.0", supersedes=first.integrity_identity)
        )
    )
    assert first.publication_version == "1.0.0"
    assert second.publication_version == "2.0.0"
    assert second.supersedes == first.integrity_identity
    assert second.integrity_identity != first.integrity_identity
    assert seal_canonical_catalogue_document(_source()) == first_bytes


def test_product_membership_and_provider_expansion_do_not_change_catalogue() -> None:
    before = load_canonical_instrument_catalogue()
    expanded_provider_assertions = tuple(
        _assertion(symbol=symbol, token=token)
        for symbol, token in (("RELIANCE", 738561), ("GOLDM26AUGFUT", 900001))
    )
    registry = before.runtime_registry(
        provider_assertions=expanded_provider_assertions,
        observed_at=NOW,
    )
    after = load_canonical_instrument_catalogue()
    assert before == after
    assert tuple(item.canonical.canonical_instrument_id for item in registry.instruments) == (
        "RELIANCE",
    )
    assert not any("swing" in item.lower() or "intraday" in item.lower() for item in before.provenance)


def test_missing_file_is_sanitized(tmp_path: Path) -> None:
    with pytest.raises(CanonicalCatalogueError) as captured:
        load_canonical_instrument_catalogue(tmp_path / "missing.json")
    assert captured.value.failure is CanonicalCatalogueFailure.PUBLICATION_UNAVAILABLE
