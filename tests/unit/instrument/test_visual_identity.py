from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path

import pytest

from kronos.instrument.visual_identity import (
    VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1,
    VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1_SUCCESSOR_VERSION,
    GovernedVisualIdentityRelationship,
    VisualIdentityRelationshipStatus,
    VisualIdentityResolutionError,
    VisualIdentityResolutionFailure,
    VisualIdentityResolver,
    VisualIdentitySourceContext,
    create_visual_identity_publication,
    create_visual_identity_relationship,
    encode_visual_identity_publication,
    parse_visual_identity_publication,
)
from kronos.instrument.visual_identity_persistence import VisualIdentityRelationshipStore
from kronos.instrument.visual_identity_persistence import (
    load_default_visual_identity_resolver,
    load_visual_identity_resolver,
)


BOUNDARY = datetime(2026, 8, 27, 10, 59, 49, 164000, tzinfo=UTC)
END = datetime.max.replace(tzinfo=UTC)
CANONICAL = ("NSE-EQ-RBLBANK", "NSE-INDEX-BANKNIFTY", "NSE-EQ-OTHER")


def _relationship(
    canonical: str = "NSE-EQ-RBLBANK",
    observed: str = "RBL Bank Ltd",
    *,
    start: datetime = BOUNDARY,
    end: datetime = END,
    source: VisualIdentitySourceContext = VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
) -> GovernedVisualIdentityRelationship:
    return create_visual_identity_relationship(
        canonical_subject_identity=canonical,
        observed_visible_subject_identity=observed,
        source_context=source,
        effective_from=start,
        effective_through=end,
        status=VisualIdentityRelationshipStatus.ACTIVE,
        source_identity="TRADINGVIEW_VISUAL_CHART",
        provenance=("ADR-0018", "GOVERNED-CHART-ARTIFACT"),
        supersedes=None,
    )


def _publication(
    relationships: tuple[GovernedVisualIdentityRelationship, ...] | None = None,
):  # type: ignore[no-untyped-def]
    return create_visual_identity_publication(
        canonical_subject_identities=CANONICAL,
        publication_identity=VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1,
        publication_version="1.0.0",
        effective_from=BOUNDARY,
        effective_through=END,
        source_identities=("ADR-0018", "KRONOS-CANONICAL-INSTRUMENT-CATALOGUE-V2:1.2.0"),
        provenance=("ADR-0018", "DOMAIN-001"),
        relationships=relationships or (
            _relationship(),
            _relationship("NSE-INDEX-BANKNIFTY", "Nifty Bank Index"),
        ),
        supersedes=None,
        schema_identity=VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1,
    )


def test_exact_rblbank_and_banknifty_relationships_resolve() -> None:
    resolver = VisualIdentityResolver(_publication())
    rblbank = resolver.resolve(
        observed_visible_subject_identity="RBL Bank Ltd",
        source_context=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
        governed_observation_boundary=BOUNDARY,
    )
    banknifty = resolver.resolve(
        observed_visible_subject_identity="Nifty Bank Index",
        source_context=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
        governed_observation_boundary=BOUNDARY + timedelta(seconds=1),
    )
    assert rblbank.canonical_subject_identity == "NSE-EQ-RBLBANK"
    assert banknifty.canonical_subject_identity == "NSE-INDEX-BANKNIFTY"
    assert rblbank.observed_visible_subject_identity == "RBL Bank Ltd"
    assert rblbank.relationship_identity.startswith("VISUAL-IDENTITY-RELATIONSHIP-")
    assert rblbank.publication_integrity_identity == resolver.publication.integrity_identity


@pytest.mark.parametrize(
    "observed",
    ("rbl bank ltd", "RBL Bank", "RBLBANK", "NSE-EQ-RBLBANK", "RBL Bank Ltd "),
)
def test_near_matches_ticker_provider_and_whitespace_guess_fail_closed(observed: str) -> None:
    resolver = VisualIdentityResolver(_publication())
    with pytest.raises(
        VisualIdentityResolutionError,
        match=VisualIdentityResolutionFailure.RELATIONSHIP_UNAVAILABLE.value,
    ):
        resolver.resolve(
            observed_visible_subject_identity=observed,
            source_context=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
            governed_observation_boundary=BOUNDARY,
        )


def test_source_context_mismatch_fails_closed() -> None:
    with pytest.raises(VisualIdentityResolutionError, match="UNAVAILABLE"):
        VisualIdentityResolver(_publication()).resolve(
            observed_visible_subject_identity="RBL Bank Ltd",
            source_context="OTHER_VISUAL_SOURCE",  # type: ignore[arg-type]
            governed_observation_boundary=BOUNDARY,
        )


def test_before_boundary_is_stale_at_and_after_resolve() -> None:
    resolver = VisualIdentityResolver(_publication())
    with pytest.raises(
        VisualIdentityResolutionError,
        match=VisualIdentityResolutionFailure.PUBLICATION_STALE.value,
    ):
        resolver.resolve(
            observed_visible_subject_identity="RBL Bank Ltd",
            source_context=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
            governed_observation_boundary=BOUNDARY - timedelta(microseconds=1),
        )
    for observed_at in (BOUNDARY, BOUNDARY + timedelta(days=1)):
        assert VisualIdentityResolver(_publication()).resolve(
            observed_visible_subject_identity="RBL Bank Ltd",
            source_context=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
            governed_observation_boundary=observed_at,
        ).canonical_subject_identity == "NSE-EQ-RBLBANK"


def test_inactive_missing_and_ambiguous_relationships_fail_closed() -> None:
    inactive = create_visual_identity_relationship(
        canonical_subject_identity="NSE-EQ-RBLBANK",
        observed_visible_subject_identity="RBL Bank Ltd",
        source_context=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
        effective_from=BOUNDARY,
        effective_through=END,
        status=VisualIdentityRelationshipStatus.INACTIVE,
        source_identity="TRADINGVIEW_VISUAL_CHART",
        provenance=("ADR-0018", "GOVERNED-CHART-ARTIFACT"),
        supersedes=None,
    )
    with pytest.raises(VisualIdentityResolutionError, match="UNAVAILABLE"):
        VisualIdentityResolver(_publication((inactive,))).resolve(
            observed_visible_subject_identity="RBL Bank Ltd",
            source_context=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
            governed_observation_boundary=BOUNDARY,
        )

    duplicate_meaning = create_visual_identity_relationship(
        canonical_subject_identity="NSE-EQ-RBLBANK",
        observed_visible_subject_identity="RBL Bank Ltd",
        source_context=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
        effective_from=BOUNDARY,
        effective_through=END,
        status=VisualIdentityRelationshipStatus.ACTIVE,
        source_identity="TRADINGVIEW_VISUAL_CHART",
        provenance=("ADR-0018", "SECOND-INDEPENDENT-EVIDENCE"),
        supersedes=None,
    )
    resolver = VisualIdentityResolver(_publication((_relationship(), duplicate_meaning)))
    with pytest.raises(VisualIdentityResolutionError, match="AMBIGUOUS"):
        resolver.resolve(
            observed_visible_subject_identity="RBL Bank Ltd",
            source_context=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
            governed_observation_boundary=BOUNDARY,
        )


def test_conflicting_overlap_duplicate_identity_and_dangling_subject_reject() -> None:
    conflict = _relationship("NSE-EQ-OTHER", "RBL Bank Ltd")
    with pytest.raises(VisualIdentityResolutionError, match="INTEGRITY_INVALID"):
        _publication((_relationship(), conflict))
    with pytest.raises(VisualIdentityResolutionError, match="INTEGRITY_INVALID"):
        _publication((_relationship(), _relationship()))
    with pytest.raises(VisualIdentityResolutionError, match="INTEGRITY_INVALID"):
        create_visual_identity_publication(
            canonical_subject_identities=CANONICAL,
            publication_identity=VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1,
            publication_version="1.0.0",
            effective_from=BOUNDARY,
            effective_through=END,
            source_identities=("ADR-0018",),
            provenance=("ADR-0018",),
            relationships=(_relationship("NSE-EQ-NOT-CANONICAL"),),
            supersedes=None,
            schema_identity=VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1,
        )


def test_invalid_interval_and_tampered_relationship_and_publication_reject() -> None:
    with pytest.raises(VisualIdentityResolutionError, match="INTEGRITY_INVALID"):
        _relationship(start=BOUNDARY + timedelta(seconds=1), end=BOUNDARY)

    encoded = encode_visual_identity_publication(_publication())
    tampered_relationship = encoded.replace(b"RBL Bank Ltd", b"RBL Bank LTD")
    with pytest.raises(VisualIdentityResolutionError, match="INTEGRITY_INVALID"):
        parse_visual_identity_publication(
            tampered_relationship,
            canonical_subject_identities=CANONICAL,
        )
    document = json.loads(encoded)
    document["provenance"][1] = "TAMPERED"
    with pytest.raises(VisualIdentityResolutionError, match="INTEGRITY_INVALID"):
        parse_visual_identity_publication(
            json.dumps(document).encode(),
            canonical_subject_identities=CANONICAL,
        )


def test_publication_round_trip_immutable_retain_and_explicit_reload(tmp_path: Path) -> None:
    publication = _publication()
    encoded = encode_visual_identity_publication(publication)
    assert parse_visual_identity_publication(
        encoded, canonical_subject_identities=CANONICAL
    ) == publication
    store = VisualIdentityRelationshipStore(tmp_path.resolve())
    target = store.retain(publication, canonical_subject_identities=CANONICAL)
    assert store.retain(
        publication, canonical_subject_identities=CANONICAL
    ) == target
    restored = store.load(
        publication_identity=publication.publication_identity,
        publication_version=publication.publication_version,
        canonical_subject_identities=CANONICAL,
    )
    assert restored == publication
    conflicting_publication = create_visual_identity_publication(
        canonical_subject_identities=CANONICAL,
        publication_identity=VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1,
        publication_version="1.0.0",
        effective_from=BOUNDARY,
        effective_through=END,
        source_identities=("ADR-0018",),
        provenance=("ADR-0018", "DIFFERENT-PUBLICATION-CONTENT"),
        relationships=publication.relationships,
        supersedes=None,
        schema_identity=VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1,
    )
    with pytest.raises(VisualIdentityResolutionError, match="INTEGRITY_INVALID"):
        store.retain(
            conflicting_publication,
            canonical_subject_identities=CANONICAL,
        )
    target.write_bytes(target.read_bytes().replace(b"RBL Bank Ltd", b"RBL Bank LTD"))
    with pytest.raises(VisualIdentityResolutionError, match="INTEGRITY_INVALID"):
        store.load(
            publication_identity=publication.publication_identity,
            publication_version=publication.publication_version,
            canonical_subject_identities=CANONICAL,
        )


def test_repository_default_publication_loads_against_canonical_catalogue() -> None:
    resolver = load_default_visual_identity_resolver()
    assert resolver.resolve(
        observed_visible_subject_identity="RBL Bank Ltd",
        source_context=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
        governed_observation_boundary=BOUNDARY,
    ).canonical_subject_identity == "NSE-EQ-RBLBANK"
    assert resolver.resolve(
        observed_visible_subject_identity="Nifty Bank Index",
        source_context=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
        governed_observation_boundary=BOUNDARY,
    ).canonical_subject_identity == "NSE-INDEX-BANKNIFTY"


def test_successor_1_1_0_resolves_exact_v2_labels_and_preserves_1_0_0() -> None:
    historical = Path(
        "data/instruments/"
        "KRONOS-GOVERNED-VISUAL-IDENTITY-RELATIONSHIP-PUBLICATION-V1/1.0.0.json"
    ).read_bytes()
    assert sha256(historical).hexdigest() == (
        "da0412ade5eb2961fa0fd08857f551db64a67abef941cd4ba24e4023aed5c1e4"
    )
    historical_resolver = load_default_visual_identity_resolver()
    assert historical_resolver.publication.publication_version == "1.0.0"
    assert historical_resolver.resolve(
        observed_visible_subject_identity="RBL Bank Ltd",
        source_context=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
        governed_observation_boundary=BOUNDARY,
    ).canonical_subject_identity == "NSE-EQ-RBLBANK"

    successor = load_visual_identity_resolver(
        publication_version=(
            VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1_SUCCESSOR_VERSION
        )
    )
    assert successor.publication.publication_version == "1.1.0"
    assert {
        observed: successor.resolve(
            observed_visible_subject_identity=observed,
            source_context=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
            governed_observation_boundary=datetime.fromisoformat(
                "2026-08-28T17:18:48.326000+00:00"
            ),
        ).canonical_subject_identity
        for observed in (
            "Apollo Hospitals Enterprise Limited",
            "Bajaj Auto Limited",
            "Hero Motocorp Limited",
            "PB Fintech Limited",
        )
    } == {
        "Apollo Hospitals Enterprise Limited": "NSE-EQ-APOLLOHOSP",
        "Bajaj Auto Limited": "NSE-EQ-BAJAJ-AUTO",
        "Hero Motocorp Limited": "NSE-EQ-HEROMOTOCO",
        "PB Fintech Limited": "NSE-EQ-POLICYBZR",
    }


def test_unknown_successor_version_and_wrong_context_fail_closed() -> None:
    with pytest.raises(VisualIdentityResolutionError, match="INTEGRITY_INVALID"):
        create_visual_identity_publication(
            canonical_subject_identities=CANONICAL,
            publication_identity=VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1,
            publication_version="1.3.0",
            effective_from=BOUNDARY,
            effective_through=END,
            source_identities=("ADR-0018",),
            provenance=("ADR-0018",),
            relationships=(_relationship(),),
            supersedes=None,
            schema_identity=VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1,
        )
    successor = load_visual_identity_resolver(publication_version="1.1.0")
    with pytest.raises(VisualIdentityResolutionError, match="UNAVAILABLE"):
        successor.resolve(
            observed_visible_subject_identity="Apollo Hospitals Enterprise Limited",
            source_context="WRONG_SOURCE",  # type: ignore[arg-type]
            governed_observation_boundary=datetime.fromisoformat(
                "2026-08-28T17:18:48.326000+00:00"
            ),
        )
