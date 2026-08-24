from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ARCHITECTURE = ROOT / "docs" / "architecture"
ADR = (
    ARCHITECTURE
    / "adr"
    / "ADR-0015-SWING-SPONSOR-OBSERVATION-PHASE-AUTHORITY-AND-STEP-31-EVIDENCE-GOVERNANCE.md"
)


def test_adr0015_preserves_owner_separation_and_no_broker_authority() -> None:
    text = ADR.read_text(encoding="utf-8")

    for required in (
        "KR-370 RECOMMENDS",
        "STEP-31 CALCULATES AND WARNS",
        "THE SPONSOR DECIDES",
        "KRONOS MONITORS AND RECORDS",
        "SWING-STEP31-OBSERVATION-PHASE-V1",
        "Broker Authority:** NONE",
        "Autonomous Trading:** NOT AUTHORIZED",
    ):
        assert required in text


def test_adr0015_classifies_geometry_warnings_separately_from_hard_blockers() -> None:
    text = ADR.read_text(encoding="utf-8")

    for warning in (
        "TARGET_BELOW_ENTRY",
        "NON_POSITIVE_REWARD",
        "RR_UNFAVOURABLE",
        "TARGET_UNAVAILABLE",
        "STOP_UNAVAILABLE",
        "ENTRY_UNAVAILABLE",
    ):
        assert warning in text
    for blocker in (
        "stale or foreign run",
        "identity, lineage, version, digest, integrity, freshness",
        "current DOMAIN-007 `REJECTED` or `UNAVAILABLE`",
        "non-`QUALIFIED` ECPC context",
    ):
        assert blocker in text
    assert (
        "They are not, by themselves,\n"
        "the Sponsor's participation decision"
    ) in text


def test_domain007_remains_hard_for_objective_and_position_activation() -> None:
    risk_architecture = (
        ARCHITECTURE / "platform" / "domains" / "risk" / "ARCHITECTURE.md"
    ).read_text(encoding="utf-8")
    contracts = (
        ARCHITECTURE / "platform" / "domains" / "risk" / "CONTRACTS.md"
    ).read_text(encoding="utf-8")

    assert "does not make DOMAIN-007 advisory" in risk_architecture
    assert "`REJECTED` and `UNAVAILABLE` remain genuine" in risk_architecture
    assert "no DOMAIN-007 state itself\nrecords `LIVE`, `PAPER`, or `IGNORE`" in risk_architecture
    assert "`REJECTED` and `UNAVAILABLE` remain hard fail-closed" in contracts


def test_observation_phase_keeps_decision_activation_and_objective_truth_distinct() -> None:
    adr = ADR.read_text(encoding="utf-8")
    product = (
        ARCHITECTURE
        / "products"
        / "swing"
        / "SWING-V1-STEP-32-PRODUCT-ADRS.md"
    ).read_text(encoding="utf-8")
    step33 = (
        ARCHITECTURE
        / "products"
        / "swing"
        / "SWING-V1-STEP-33-OUTCOME-AND-JOURNAL-INTEGRATION.md"
    ).read_text(encoding="utf-8")

    assert "LIVE, PAPER, and IGNORE decisions" in adr
    assert "IGNORE creates no Sponsor Position" in adr
    assert "A recorded PAPER or LIVE observation choice creates no Sponsor Position" in product
    assert "not sufficient by itself to retain every LIVE, PAPER, and IGNORE" in step33


def test_future_work_orders_are_bounded_and_runtime_is_not_started() -> None:
    text = ADR.read_text(encoding="utf-8")

    for work_order in (
        "STEP31-OBS-01 — Advisory Trade Construction",
        "SPONSOR-OBS-01 — LIVE / PAPER / IGNORE Evidence Capture",
        "JOURNAL-OBS-01 — Outcome & Research Ledger",
        "STEP31-RESEARCH-01 — Empirical Performance Review",
    ):
        assert work_order in text
    assert "The first three are authorized for later bounded work orders" in text
    assert "STEP31-RESEARCH-01 is not authorized to begin now" in text
    assert "No Python, Browser, Provider, Pine, Telegram, Risk-policy, or broker runtime is\nchanged" in text


def test_adr0015_is_indexed_and_all_changed_architecture_links_resolve() -> None:
    index_paths = (
        ARCHITECTURE / "adr" / "README.md",
        ARCHITECTURE / "KNOWLEDGE_BASE.md",
        ARCHITECTURE / "platform" / "ARCHITECTURE_INDEX.md",
    )
    for path in index_paths:
        assert "ADR-0015" in path.read_text(encoding="utf-8")

    markdown_link = re.compile(r"\[[^]]+\]\(([^)]+)\)")
    changed_docs = (
        ADR,
        ARCHITECTURE / "README.md",
        *index_paths,
        ARCHITECTURE / "ENGINE_OWNERSHIP.md",
        ARCHITECTURE / "DATA_FLOW.md",
        ARCHITECTURE / "platform" / "domains" / "risk" / "ARCHITECTURE.md",
        ARCHITECTURE / "platform" / "domains" / "risk" / "CONTRACTS.md",
        ARCHITECTURE / "interfaces" / "SWING-V1-STEP-32-VERSIONED-CONTRACTS.md",
        ARCHITECTURE / "products" / "swing" / "SWING-V1-STEP-32-PRODUCT-ADRS.md",
        ARCHITECTURE / "products" / "swing" / "SWING-V1-STEP-33-OUTCOME-AND-JOURNAL-INTEGRATION.md",
    )
    for path in changed_docs:
        for target in markdown_link.findall(path.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("#"):
                continue
            resolved = (path.parent / target.split("#", 1)[0]).resolve()
            assert resolved.exists(), f"{path}: missing {target}"
