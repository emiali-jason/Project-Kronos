from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ARCHITECTURE = ROOT / "docs" / "architecture"
ADR = (
    ARCHITECTURE
    / "adr"
    / "ADR-0023-INTRADAY-DOMAIN-007-ADVISORY-RISK-OBSERVATION-BOUNDARY.md"
)
PRODUCT = (
    ARCHITECTURE
    / "products"
    / "intraday"
    / "KRONOS-INTRADAY-WO-14-DOMAIN-007-RISK-OBSERVATION-V1.md"
)
SWING_ADR = (
    ARCHITECTURE
    / "adr"
    / "ADR-0013-NATIVE-SWING-DOMAIN-007-RISK-PERMISSION-AND-KR-380-V2-PRODUCTION-COMMISSIONING.md"
)


def test_intraday_wo14_is_observation_only_and_never_permission() -> None:
    text = ADR.read_text(encoding="utf-8")
    assert "`RISK_OBSERVATION_ONLY`" in text
    assert "It does not own trade permission, trade rejection" in text
    assert "None of these states grants or denies progression to WO-15" in text
    assert "Sponsor owns PAPER, LIVE, IGNORE, actual participation and actual quantity" in text
    for prohibited in (
        "`TRADE_ALLOWED`",
        "`TRADE_BLOCKED`",
        "`RISK_APPROVED`",
        "`RISK_REJECTED`",
        "`MAX_PERMITTED_QUANTITY`",
        "`BROKER_ALLOWED`",
    ):
        assert prohibited in text


def test_successor_contract_state_and_alert_authority_are_exact() -> None:
    text = PRODUCT.read_text(encoding="utf-8")
    assert "`KRONOS-INTRADAY-DOMAIN-007-RISK-OBSERVATION-V1`" in text
    assert "**Version:** `1.0.0`" in text
    for state in ("RISK_OBSERVED", "RISK_ALERT", "RISK_UNAVAILABLE"):
        assert f"`{state}`" in text
    assert "Initial V1 uses severity `UNCLASSIFIED`" in text
    assert "`RISK_ALERT` is not an ordinary producible state" in text
    assert "Sponsor owns actual quantity" in text


def test_geometry_vehicle_and_wo15_boundaries_are_frozen() -> None:
    text = PRODUCT.read_text(encoding="utf-8")
    assert "Risk observes geometry. It never rewrites geometry." in text
    assert "Vehicle selection is outside WO-14" in text
    assert "`OPTION_POSITION_RISK = UNAVAILABLE`" in text
    assert "COMEX/NYMEX have no sizing authority" in text
    assert "ATR extension/chase, 5M progression, trigger and timing are WO-15-only" in text
    assert "cannot block timing evaluation" in text


def test_swing_permission_contract_is_preserved() -> None:
    swing = SWING_ADR.read_text(encoding="utf-8")
    assert "fail-closed objective-model Risk Permission gate" in swing
    for state in ("APPROVED", "CONSTRAINED", "REJECTED", "UNAVAILABLE"):
        assert f"`{state}`" in swing
    adr = ADR.read_text(encoding="utf-8")
    assert "ADR-0013, ADR-0015 and `KRONOS-SWING-DOMAIN-007-RISK-PERMISSION-V1` remain\nunchanged" in adr


def test_domain007_exposes_separate_non_translatable_product_contracts() -> None:
    contracts = (
        ARCHITECTURE / "platform" / "domains" / "risk" / "CONTRACTS.md"
    ).read_text(encoding="utf-8")
    assert "## KRONOS-SWING-DOMAIN-007-RISK-PERMISSION-V1" in contracts
    assert "## KRONOS-INTRADAY-DOMAIN-007-RISK-OBSERVATION-V1" in contracts
    assert "states must never be translated between the two families" in contracts
    ownership = (
        ARCHITECTURE / "platform" / "DOMAIN_OWNERSHIP_MATRIX.md"
    ).read_text(encoding="utf-8")
    assert "| Risk Observation and Loss-Exposure Semantics | Risk |" in ownership


def test_wo14_governance_is_indexed_and_source_remains_gated() -> None:
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
        assert "WO-14" in path.read_text(encoding="utf-8")
    product = PRODUCT.read_text(encoding="utf-8")
    assert "Source engineering is not\nstartable until the actual WO-13" in product
    assert "Runtime, Browser, real Risk observation, Provider access, WO-15 and broker work\nremain unauthorized" in product


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
    )
    for path in changed:
        for target in markdown_link.findall(path.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("#"):
                continue
            resolved = (path.parent / target.split("#", 1)[0]).resolve()
            assert resolved.exists(), f"{path}: missing {target}"
