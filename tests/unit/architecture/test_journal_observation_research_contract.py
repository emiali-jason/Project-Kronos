from pathlib import Path

from kronos.swing.v1.observation_research_ledger import (
    OBSERVATION_RESEARCH_AUTHORITY,
    OBSERVATION_RESEARCH_CONTRACT_ID,
)


ROOT = Path(__file__).resolve().parents[3]
CONTRACT = (
    ROOT / "docs" / "architecture" / "interfaces"
    / "KRONOS-SWING-OBSERVATION-RESEARCH-LEDGER-V1.md"
)


def test_observation_research_contract_is_approved_indexed_and_versioned() -> None:
    text = CONTRACT.read_text(encoding="utf-8")
    index = (CONTRACT.parent / "README.md").read_text(encoding="utf-8")
    assert "Approved implementation contract" in text
    assert "Version:** 1" in text
    assert "Observation Research Ledger V1" in index
    assert OBSERVATION_RESEARCH_CONTRACT_ID == (
        "KRONOS-SWING-OBSERVATION-RESEARCH-LEDGER-V1"
    )


def test_contract_preserves_population_outcome_and_authority_boundaries() -> None:
    text = CONTRACT.read_text(encoding="utf-8")
    for required in (
        "Every prospective `LIVE`, `PAPER`, and `IGNORE`",
        "Activated and blocked decisions remain in the same population",
        "append-only",
        "no historical backfill or migration",
        "not an input to Native Discovery, KR-370, Step-31, Risk, KR-380",
        "not position, execution, order, fill, or broker authority",
        "must not derive or display win rate, P&L",
    ):
        assert required in text
    assert "NO_ANALYTICAL_RISK_READINESS_POSITION_EXECUTION_OR_BROKER_AUTHORITY" in OBSERVATION_RESEARCH_AUTHORITY


def test_contract_preserves_mcx_temporal_context_and_equity_isolation() -> None:
    text = CONTRACT.read_text(encoding="utf-8")
    assert "MCX supporting-context linkage is retained only when it is present" in text
    assert "NSE equity whose ticker is `MCX` must not acquire" in text
