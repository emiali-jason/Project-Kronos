from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / "docs/architecture/adr/ADR-0029-INTRADAY-WO-B-OPERATIONAL-READINESS-REVIEW.md"
PRODUCT = (
    ROOT
    / "docs/architecture/products/intraday"
    / "KRONOS-INTRADAY-WO-B-OPERATIONAL-READINESS-REVIEW-V1.md"
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_adr0029_identity_status_scope_and_authority_are_frozen() -> None:
    text = _text(ADR)
    assert "ADR-0029" in text
    assert "KRONOS-INTRADAY-WO-B-OPERATIONAL-READINESS-REVIEW-V1" in text
    assert "APPROVED — PUBLICATION PENDING" in text
    assert "Intraday Product Composition / Presentation Boundary" in text
    assert "READ_ONLY_CROSS_DOMAIN_COMPOSITION" in text
    assert "Runtime / Provider / Analytical / Trading / Broker Authority:** NONE" in text


def test_adr_freezes_snapshot_pointer_failure_and_restoration_rules() -> None:
    text = _text(ADR)
    for phrase in (
        "immutable review snapshot",
        "candidate-scoped current pointer",
        "projection-only",
        "Latest bounded failure evidence",
        "Conflicting bytes",
        "Restoration",
        "inert",
        "fail closed",
    ):
        assert phrase.lower() in text.lower()


def test_review_classifications_and_multi_state_boundary_are_exact() -> None:
    text = _text(ADR) + _text(PRODUCT)
    for state in (
        "NOT_REACHED",
        "AVAILABLE",
        "WAITING",
        "BLOCKED",
        "UNAVAILABLE",
        "TERMINAL",
    ):
        assert f"`{state}`" in text
    assert "TIMING_QUALIFIED" in text
    assert "RISK_UNAVAILABLE" in text
    assert "no global `TRADE_READY` boolean" in text


def test_source_owners_and_negative_authorities_are_preserved() -> None:
    text = _text(PRODUCT)
    for owner in (
        "WO-13 retains Trade Construction",
        "WO-14/DOMAIN-007 retains advisory Risk",
        "WO-15/DOMAIN-004 retains Entry Timing",
        "WO-16 retains Sponsor Decision",
        "WO-17 retains position evidence",
        "DOMAIN-001 retains Instrument/active-contract identity",
        "DOMAIN-008 retains session/currentness truth",
        "DOMAIN-006 retains Provider factual acquisition",
    ):
        assert owner in text
    assert "broker authority are all `NONE`" in text


def test_swing_is_pattern_only_and_browser_runtime_are_deferred() -> None:
    text = _text(ADR) + _text(PRODUCT)
    normalized = " ".join(text.split())
    assert "REUSE_PATTERN_ONLY" in text
    assert "Swing analytical/Risk policy" in text
    assert "WO-B1 has no Browser or runtime scope" in text
    assert "WO-B2 live source adapters/composition" in text
    assert "WO-B3 Browser/runtime acceptance" in normalized


def test_indexes_reference_adr_and_product_record() -> None:
    paths = (
        ROOT / "docs/architecture/README.md",
        ROOT / "docs/architecture/KNOWLEDGE_BASE.md",
        ROOT / "docs/architecture/adr/README.md",
        ROOT / "docs/architecture/platform/ARCHITECTURE_INDEX.md",
        ROOT / "docs/architecture/products/intraday/README.md",
    )
    combined = "\n".join(_text(path) for path in paths)
    assert "ADR-0029-INTRADAY-WO-B-OPERATIONAL-READINESS-REVIEW.md" in combined
    assert "KRONOS-INTRADAY-WO-B-OPERATIONAL-READINESS-REVIEW-V1.md" in combined


def test_ownership_and_interface_indexes_preserve_composition_only() -> None:
    product_root = ROOT / "docs/architecture/products/intraday"
    combined = "\n".join(
        _text(product_root / name)
        for name in (
            "RESPONSIBILITIES.md",
            "INTERFACES.md",
            "KRONOS-INTRADAY-CONTRACT-STATE-OWNERSHIP-REGISTRY.md",
        )
    )
    assert "product composition/presentation boundary" in combined
    assert "WO-B review classification ≠ producer-domain state or trading readiness" in combined
    assert "WO-B1 executes none of those producers" in combined
