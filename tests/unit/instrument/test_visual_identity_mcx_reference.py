from datetime import datetime, timezone

import pytest

from kronos.instrument.visual_identity import (
    VISUAL_IDENTITY_REFERENCE_ANALYTICAL_SUBJECTS,
    VisualIdentityResolutionError,
    VisualIdentitySourceContext,
    parse_visual_identity_publication,
)
from kronos.instrument.visual_identity_persistence import (
    DEFAULT_VISUAL_IDENTITY_ROOT,
    load_visual_identity_resolver,
)


def test_mcx_reference_successor_has_exact_five_continuous_visible_identities() -> None:
    resolver = load_visual_identity_resolver(publication_version="1.2.0")
    expected = {
        "COMEX:GC1!": "REFERENCE-SUBJECT-COMEX-GOLD",
        "COMEX:SI1!": "REFERENCE-SUBJECT-COMEX-SILVER",
        "COMEX:HG1!": "REFERENCE-SUBJECT-COMEX-COPPER",
        "NYMEX:CL1!": "REFERENCE-SUBJECT-NYMEX-CRUDE-OIL",
        "NYMEX:NG1!": "REFERENCE-SUBJECT-NYMEX-NATURAL-GAS",
    }
    boundary = datetime(2026, 8, 30, 12, tzinfo=timezone.utc)
    resolved = {
        visible: resolver.resolve(
            observed_visible_subject_identity=visible,
            source_context=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
            governed_observation_boundary=boundary,
        ).canonical_subject_identity
        for visible in expected
    }
    assert resolved == expected
    assert set(resolved.values()) == set(VISUAL_IDENTITY_REFERENCE_ANALYTICAL_SUBJECTS)


def test_mcx_reference_successor_is_exact_and_old_publications_still_load() -> None:
    current = load_visual_identity_resolver(publication_version="1.2.0")
    with pytest.raises(VisualIdentityResolutionError):
        current.resolve(
            observed_visible_subject_identity="COMEX:GOLD",
            source_context=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
            governed_observation_boundary=datetime(2026, 8, 30, 12, tzinfo=timezone.utc),
        )
    assert load_visual_identity_resolver(publication_version="1.0.0").publication.publication_version == "1.0.0"
    assert load_visual_identity_resolver(publication_version="1.1.0").publication.publication_version == "1.1.0"


def test_mcx_reference_successor_tamper_fails_integrity() -> None:
    payload = (DEFAULT_VISUAL_IDENTITY_ROOT / "KRONOS-GOVERNED-VISUAL-IDENTITY-RELATIONSHIP-PUBLICATION-V1" / "1.2.0.json").read_bytes()
    tampered = payload.replace(b"COMEX:GC1!", b"COMEX:GC2!", 1)
    with pytest.raises(VisualIdentityResolutionError):
        parse_visual_identity_publication(
            tampered,
            canonical_subject_identities=VISUAL_IDENTITY_REFERENCE_ANALYTICAL_SUBJECTS,
        )
