from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ARCHITECTURE = ROOT / "docs" / "architecture"
ADR = (
    ARCHITECTURE
    / "adr"
    / "ADR-0021-INTRADAY-WO12-FOUR-CRITERION-PROMOTION-AND-WO15-EXTENSION-OWNERSHIP.md"
)
PRODUCT = (
    ARCHITECTURE
    / "products"
    / "intraday"
    / "KRONOS-INTRADAY-WO-12-KR370-ANALYTICAL-PROMOTION-V2.md"
)


def test_adr0021_freezes_exact_four_k_and_wo15_extension_ownership() -> None:
    text = ADR.read_text(encoding="utf-8")
    for criterion in (
        "K1_15M_DIRECTIONAL_PROGRESSION",
        "K2_15M_CPR_ACCEPTANCE",
        "K3_15M_IMMEDIATE_PATH_CLEARANCE",
        "K4_15M_SETUP_QUALITY",
    ):
        assert criterion in text
    assert "There is no Intraday WO-12 V2 K5 or K6" in text
    assert "WO-15 / KR-380 owns any future extension/chase consequence" in text
    assert "Swing retains its separate five-criterion" in text


def test_v2_mapping_and_authority_boundaries_are_explicit() -> None:
    text = PRODUCT.read_text(encoding="utf-8")
    for row in (
        "| 4 | `BUY_NOW` | `SELL_NOW` |",
        "| 3 | `BUY_READY` | `SELL_READY` |",
        "| 2 | `POTENTIAL_BUY_SETUP` | `POTENTIAL_SELL_SETUP` |",
        "| 0–1 | `NO_SETUP` | `NO_SETUP` |",
    ):
        assert row in text
    assert "Unavailable K1–K4 fails closed" in text
    assert "5M has no WO-12 authority" in text
    assert "WO-12 emits no Entry, Stop, Target" in text


def test_history_is_preserved_and_successor_is_indexed() -> None:
    adr0019 = ARCHITECTURE / "adr" / "ADR-0019-INTRADAY-WO10-WO11-PRE-KR370-SEMANTIC-BOUNDARY.md"
    adr0020 = ARCHITECTURE / "adr" / "ADR-0020-INTRADAY-WO11-WO12-KR370-ANALYTICAL-PROMOTION-BOUNDARY.md"
    v1 = ARCHITECTURE / "products" / "intraday" / "KRONOS-INTRADAY-WO-12-KR370-ANALYTICAL-PROMOTION-V1.md"
    assert adr0019.exists() and adr0020.exists() and v1.exists()
    for index in (
        ARCHITECTURE / "adr" / "README.md",
        ARCHITECTURE / "KNOWLEDGE_BASE.md",
        ARCHITECTURE / "products" / "intraday" / "README.md",
    ):
        text = index.read_text(encoding="utf-8")
        assert "ADR-0021" in text or index.name == "README.md" and "Analytical Promotion V2" in text


def test_changed_architecture_links_resolve() -> None:
    markdown_link = re.compile(r"\[[^]]+\]\(([^)]+)\)")
    changed = (
        ADR,
        PRODUCT,
        ARCHITECTURE / "adr" / "README.md",
        ARCHITECTURE / "KNOWLEDGE_BASE.md",
        ARCHITECTURE / "products" / "intraday" / "README.md",
        ARCHITECTURE / "products" / "intraday" / "KRONOS-INTRADAY-V1-PROGRAMME-ROADMAP.md",
        ARCHITECTURE / "products" / "intraday" / "KRONOS-INTRADAY-ENGINEERING-METHODOLOGY-ARCHITECTURE-RECORD-V0.1.md",
    )
    for path in changed:
        for target in markdown_link.findall(path.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("#"):
                continue
            resolved = (path.parent / target.split("#", 1)[0]).resolve()
            assert resolved.exists(), f"{path}: missing {target}"
