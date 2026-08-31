from __future__ import annotations

from hashlib import sha256
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ARCHITECTURE = ROOT / "docs" / "architecture"
ADR = (
    ARCHITECTURE
    / "adr"
    / "ADR-0022-INTRADAY-WO12-WO13-STEP31-TRADE-CONSTRUCTION-BOUNDARY.md"
)
PRODUCT = (
    ARCHITECTURE
    / "products"
    / "intraday"
    / "KRONOS-INTRADAY-WO-13-STEP31-TRADE-CONSTRUCTION-V1.md"
)
POLICY = (
    ARCHITECTURE
    / "products"
    / "intraday"
    / "KRONOS-INTRADAY-WO13-STEP31-TRADE-CONSTRUCTION-POLICY-V1.json"
)
POLICY_SHA256 = "c5ea70a5af50af251088785a58a39da4e824b5cc6058c11c98e880fce0fb0e6b"


def test_adr0022_authorizes_only_exact_wo12_now_to_wo13_core() -> None:
    text = ADR.read_text(encoding="utf-8")
    assert "`BUY_NOW` or\n`SELL_NOW`" in text
    assert "Every other KR-370 classification is ineligible" in text
    assert "15M is the sole primary geometry frame" in text
    assert "5M has no WO-13 geometry authority" in text
    assert "Runtime, Browser and real WO-13 operation remain\nseparately gated" in text
    assert "Risk / Entry Timing / Sponsor / Broker Authority:** NONE" in text


def test_exact_setup_family_geometry_and_rr_authority_are_frozen() -> None:
    text = PRODUCT.read_text(encoding="utf-8")
    for identity in (
        "INTRADAY_PULLBACK_CONTINUATION",
        "INTRADAY_RANGE_BREAKOUT",
        "KRONOS-INTRADAY-WO13-STEP31-HANDOFF-V1",
        "KRONOS-INTRADAY-WO13-TRADE-PLAN-V1",
        "GEOMETRY_COMPLETE",
        "GEOMETRY_PARTIAL",
        "GEOMETRY_UNAVAILABLE",
    ):
        assert identity in text
    assert "No minimum R:R gate is authorized" in text
    assert "Target count is exactly one" in text
    assert "NATGAS remains operationally held" in text


def test_canonical_policy_payload_and_checksum_are_exact() -> None:
    raw = POLICY.read_bytes()
    assert sha256(raw).hexdigest() == POLICY_SHA256
    payload = json.loads(raw)
    assert payload["policy_version"] == "1.0.0"
    assert payload["geometry_frame"] == "15M"
    assert payload["setup_families"] == [
        "INTRADAY_PULLBACK_CONTINUATION",
        "INTRADAY_RANGE_BREAKOUT",
    ]
    assert payload["model_rr"]["gate"] == "NONE"
    assert payload["target_count"] == 1
    assert POLICY_SHA256 in ADR.read_text(encoding="utf-8")
    assert POLICY_SHA256 in PRODUCT.read_text(encoding="utf-8")


def test_wo13_governance_is_indexed_and_swing_remains_separate() -> None:
    for path in (
        ARCHITECTURE / "adr" / "README.md",
        ARCHITECTURE / "KNOWLEDGE_BASE.md",
        ARCHITECTURE / "products" / "intraday" / "README.md",
        ARCHITECTURE
        / "products"
        / "intraday"
        / "KRONOS-INTRADAY-CONTRACT-STATE-OWNERSHIP-REGISTRY.md",
        ARCHITECTURE
        / "products"
        / "intraday"
        / "KRONOS-INTRADAY-V1-PROGRAMME-ROADMAP.md",
    ):
        assert "WO-13" in path.read_text(encoding="utf-8")
    product_text = PRODUCT.read_text(encoding="utf-8")
    assert "Swing Step-31 contracts, policy, code, persistence and records are unchanged" in product_text
    assert "does not copy Swing Daily methodology" in product_text


def test_changed_architecture_links_resolve() -> None:
    markdown_link = re.compile(r"\[[^]]+\]\(([^)]+)\)")
    changed = (
        ADR,
        PRODUCT,
        ARCHITECTURE / "adr" / "README.md",
        ARCHITECTURE / "KNOWLEDGE_BASE.md",
        ARCHITECTURE / "products" / "intraday" / "README.md",
        ARCHITECTURE
        / "products"
        / "intraday"
        / "KRONOS-INTRADAY-V1-PROGRAMME-ROADMAP.md",
        ARCHITECTURE
        / "products"
        / "intraday"
        / "KRONOS-INTRADAY-ENGINEERING-METHODOLOGY-ARCHITECTURE-RECORD-V0.1.md",
    )
    for path in changed:
        for target in markdown_link.findall(path.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("#"):
                continue
            resolved = (path.parent / target.split("#", 1)[0]).resolve()
            assert resolved.exists(), f"{path}: missing {target}"
