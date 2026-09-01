from pathlib import Path

from kronos.swing.v1.native_trade_construction import (
    TRADE_CONSTRUCTION_POLICY_ID,
    TRADE_CONSTRUCTION_POLICY_VERSION,
    TRADE_PLAN_CONTRACT_ID,
)
from kronos.swing.v1.step31_observation import STEP31_OBSERVATION_CONTRACT_ID


ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / "docs" / "architecture" / "adr" / (
    "ADR-0024-SWING-STEP31-FORWARD-TARGET-ELIGIBILITY-GOVERNANCE.md"
)


def test_adr0024_governs_strict_forward_target_and_no_fallback() -> None:
    text = ADR.read_text(encoding="utf-8")
    for required in (
        "SWING-V1-TRADE-CONSTRUCTION-V1",
        "TARGET_NOT_FORWARD_OF_ENTRY",
        "LONG rounded target must be strictly above rounded Entry",
        "SHORT rounded target must be strictly below rounded Entry",
        "No fallback search may occur",
        "broker authority",
    ):
        assert required in text


def test_successor_runtime_contracts_are_explicitly_versioned() -> None:
    assert TRADE_CONSTRUCTION_POLICY_ID == "SWING-V1-TRADE-CONSTRUCTION-V1"
    assert TRADE_CONSTRUCTION_POLICY_VERSION == "1.0"
    assert TRADE_PLAN_CONTRACT_ID == "KRONOS-SWING-V1-TRADE-PLAN-RECORD-V1"
    assert STEP31_OBSERVATION_CONTRACT_ID == "KRONOS-SWING-STEP31-OBSERVATION-EVIDENCE-V2"
