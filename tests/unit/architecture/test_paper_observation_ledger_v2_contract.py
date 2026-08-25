from pathlib import Path

from kronos.swing.v1.observation_research_ledger import (
    OBSERVATION_RESEARCH_CONTRACT_ID,
)
from kronos.swing.v1.observation_research_ledger_v2 import (
    OBSERVATION_RESEARCH_V2_CONTRACT_ID,
    OBSERVATION_RESEARCH_V2_CONTRACT_VERSION,
    SPONSOR_OBSERVATION_PROJECTION_V2_CONTRACT_ID,
)


ROOT = Path(__file__).resolve().parents[3]
INTERFACES = ROOT / "docs" / "architecture" / "interfaces"


def test_v2_contracts_are_implemented_without_reinterpreting_v1() -> None:
    ledger = (
        INTERFACES / "KRONOS-SWING-OBSERVATION-RESEARCH-LEDGER-V2.md"
    ).read_text(encoding="utf-8")
    projection = (
        INTERFACES / "KRONOS-SWING-SPONSOR-OBSERVATION-PROJECTION-V2.md"
    ).read_text(encoding="utf-8")

    assert OBSERVATION_RESEARCH_V2_CONTRACT_ID in ledger
    assert OBSERVATION_RESEARCH_V2_CONTRACT_VERSION == "2"
    assert SPONSOR_OBSERVATION_PROJECTION_V2_CONTRACT_ID in projection
    assert "Approved implementation contract" in ledger
    assert "Approved implementation contract" in projection
    assert "No automatic backfill" in ledger
    assert "Historical V1 projections retain" in projection
    assert OBSERVATION_RESEARCH_CONTRACT_ID.endswith("-V1")


def test_v2_contracts_freeze_authority_and_future_handoffs() -> None:
    ledger = (
        INTERFACES / "KRONOS-SWING-OBSERVATION-RESEARCH-LEDGER-V2.md"
    ).read_text(encoding="utf-8")
    projection = (
        INTERFACES / "KRONOS-SWING-SPONSOR-OBSERVATION-PROJECTION-V2.md"
    ).read_text(encoding="utf-8")

    for required in (
        "A track never creates a second Sponsor-decision row",
        "must not derive win rate, P&L, actual R",
        "Current LTP and direction-aware distance",
        "DOMAIN-008's governed trading date",
        "SharedSwingMonitoringHub",
        "REST Provider authentication is not WebSocket authority",
    ):
        assert required in ledger
    for required in (
        "four truth families",
        "Current market price",
        "Notifications remain outside this contract",
        "cannot be mixed",
    ):
        assert required in projection
