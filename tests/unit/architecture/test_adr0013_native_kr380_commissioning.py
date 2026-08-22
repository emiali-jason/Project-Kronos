from __future__ import annotations

import re
from pathlib import Path

from kronos.swing.v1.native_entry_timing import (
    KR380_CONTRACT_ID,
    KR380_CONTRACT_VERSION,
    NO_BROKER_AUTHORITY,
    PORTFOLIO_STATE_CONTRACT_ID,
    RISK_PERMISSION_CONTRACT_ID,
    RISK_POLICY_ID,
    RISK_POLICY_VERSION,
)


ROOT = Path(__file__).resolve().parents[3]
ARCHITECTURE = ROOT / "docs" / "architecture"
ADR = (
    ARCHITECTURE
    / "adr"
    / "ADR-0013-NATIVE-SWING-DOMAIN-007-RISK-PERMISSION-AND-KR-380-V2-PRODUCTION-COMMISSIONING.md"
)


def test_adr0013_commissions_only_the_bounded_native_path() -> None:
    text = ADR.read_text(encoding="utf-8")

    for required in (
        "FAIL-CLOSED OBJECTIVE-MODEL RISK PERMISSION",
        "KRONOS-SWING-PORTFOLIO-STATE-V1",
        "Step-31 remains the sole owner",
        "SharedSwingMonitoringHub",
        "KRONOS-KR-380-ENTRY-OUTCOME-V2",
        "Historical KR-380 V1",
        "BROKER",
        "Autonomous Trading:** NOT AUTHORIZED",
    ):
        assert required.casefold() in text.casefold()
    assert "future separately\napproved DOMAIN-007 V2" in text


def test_runtime_contract_identities_match_adr0013() -> None:
    assert RISK_PERMISSION_CONTRACT_ID == "KRONOS-SWING-V1-RISK-APPROVAL-V1"
    assert RISK_POLICY_ID == "KRONOS-SWING-DOMAIN-007-RISK-PERMISSION-V1"
    assert RISK_POLICY_VERSION == "1"
    assert PORTFOLIO_STATE_CONTRACT_ID == "KRONOS-SWING-PORTFOLIO-STATE-V1"
    assert KR380_CONTRACT_ID == "KRONOS-KR-380-ENTRY-OUTCOME-V2"
    assert KR380_CONTRACT_VERSION == "2"
    assert NO_BROKER_AUTHORITY == "NONE"


def test_adr0013_architecture_links_resolve() -> None:
    markdown_link = re.compile(r"\[[^]]+\]\(([^)]+)\)")
    for target in markdown_link.findall(ADR.read_text(encoding="utf-8")):
        if "://" in target or target.startswith("#"):
            continue
        resolved = (ADR.parent / target.split("#", 1)[0]).resolve()
        assert resolved.exists(), target


def test_historical_step32_isolation_is_explicitly_conformed() -> None:
    baseline = (
        ARCHITECTURE / "adr" / "ADR-SWING-STEP-32-PLATFORM-AMENDMENTS.md"
    ).read_text(encoding="utf-8")
    contracts = (
        ARCHITECTURE / "interfaces" / "SWING-V1-STEP-32-VERSIONED-CONTRACTS.md"
    ).read_text(encoding="utf-8")

    assert "SHADOW / VALIDATION ONLY except" in baseline
    assert "ADR-0013" in baseline
    assert "historical, immutable, read-only/restorable" in contracts
    assert "ADR-0013 commissions the exact Native" in contracts
