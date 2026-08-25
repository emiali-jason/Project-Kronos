from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ARCHITECTURE = ROOT / "docs" / "architecture"
ADR = (
    ARCHITECTURE
    / "adr"
    / "ADR-0016-SWING-PAPER-OBSERVATION-TRACK-AUTHORITY.md"
)
TRACK = (
    ARCHITECTURE
    / "interfaces"
    / "KRONOS-SWING-PAPER-OBSERVATION-TRACK-V1.md"
)
PROJECTION = (
    ARCHITECTURE
    / "interfaces"
    / "KRONOS-SWING-SPONSOR-OBSERVATION-PROJECTION-V2.md"
)
LEDGER = (
    ARCHITECTURE
    / "interfaces"
    / "KRONOS-SWING-OBSERVATION-RESEARCH-LEDGER-V2.md"
)


def test_adr0016_freezes_three_truth_families_and_non_position_authority() -> None:
    text = ADR.read_text(encoding="utf-8")

    for required in (
        "PAPER Observation Decision",
        "Paper Observation Track",
        "PAPER Sponsor Position",
        "No record in one family implies a record in another",
        "Broker Authority:** NONE",
        "Autonomous Trading:** NOT AUTHORIZED",
    ):
        assert required in text

    assert "Non-position observation" in text
    assert "Risk permission" in text
    assert "Sponsor Position" in text
    assert "cannot create or emulate a KR-380 state, KR-390 model" in text


def test_domain007_remains_hard_while_blocked_paper_may_be_observed() -> None:
    adr = ADR.read_text(encoding="utf-8")
    risk_architecture = (
        ARCHITECTURE / "platform" / "domains" / "risk" / "ARCHITECTURE.md"
    ).read_text(encoding="utf-8")
    risk_contracts = (
        ARCHITECTURE / "platform" / "domains" / "risk" / "CONTRACTS.md"
    ).read_text(encoding="utf-8")

    assert "DOMAIN-007 remains the hard permission gate" in adr
    assert "A Paper Observation Track receives no Risk approval, override, or\nbypass" in adr
    assert "Position Activation    BLOCKED" in adr
    assert "Paper Observation Track AVAILABLE / ACTIVE" in adr
    assert "does not weaken this boundary" in risk_architecture
    assert "Track receives no permission,\noverride, or bypass" in risk_contracts


def test_activated_paper_uses_position_relationship_without_duplicate_track() -> None:
    adr = ADR.read_text(encoding="utf-8")
    ledger = LEDGER.read_text(encoding="utf-8")

    assert "NOT_APPLICABLE_POSITION_ACTIVATED" in adr
    assert "One Sponsor PAPER decision remains one primary research-ledger row" in adr
    assert "cannot also create a Paper Track relationship" in ledger
    assert "A track never creates a second Sponsor-decision row" in ledger


def test_track_preserves_all_severities_and_exact_geometry() -> None:
    text = ADR.read_text(encoding="utf-8")

    for required in (
        "GREEN, AMBER, and RED",
        "OBSERVATION_ENTRY_REFERENCE",
        "Stop, Target, invalidation",
        "No favourable target or valid R:R is manufactured",
        "Entry                      3211.4",
        "Stop                       2892.1",
        "Target                     3023.7",
        "R:R                        INVALID",
    ):
        assert required in text


def test_track_outcomes_completion_and_ambiguity_are_bounded() -> None:
    text = TRACK.read_text(encoding="utf-8")

    for state in (
        "ENTRY_NOT_OBSERVED",
        "ENTRY_OBSERVED",
        "STOP_LEVEL_TOUCHED",
        "TARGET_LEVEL_TOUCHED",
        "BOTH_ORDERING_UNRESOLVED",
        "EXPIRED",
        "OUTCOME_NOT_ESTABLISHED",
    ):
        assert state in text
    assert "unfinished candles cannot establish a\nfinal outcome" in text
    assert "without guessing" in ADR.read_text(encoding="utf-8")
    assert "EXPIRY POLICY UNRESOLVED" in text


def test_monitoring_recovery_and_supersession_fail_closed() -> None:
    text = TRACK.read_text(encoding="utf-8")

    for required in (
        "SharedSwingMonitoringHub",
        "dedicated Paper Track\nconsumer",
        "MONITORING_INTERRUPTED",
        "bounded historical reconciliation",
        "Restart restores persisted state idempotently",
        "Later analysis-run supersession does not rewrite or terminate",
    ):
        assert required in text


def test_live_objective_position_broker_and_accounting_are_isolated() -> None:
    adr = ADR.read_text(encoding="utf-8")
    track = TRACK.read_text(encoding="utf-8")

    for required in (
        "LIVE authority is unchanged",
        "no LIVE Observation Track",
        "Broker authority remains `NONE`",
        "monetary P&L and actual R are `UNAVAILABLE`",
    ):
        assert required in adr
    for forbidden_authority in (
        "cannot create KR-380, KR-390, Sponsor Position",
        "order, fill, or broker evidence",
    ):
        assert forbidden_authority in track


def test_contract_versions_history_and_future_work_are_explicit() -> None:
    adr = ADR.read_text(encoding="utf-8")

    assert "KRONOS-SWING-PAPER-OBSERVATION-TRACK-V1" in TRACK.read_text(encoding="utf-8")
    assert "KRONOS-SWING-SPONSOR-OBSERVATION-PROJECTION-V2" in PROJECTION.read_text(encoding="utf-8")
    assert "KRONOS-SWING-OBSERVATION-RESEARCH-LEDGER-V2" in LEDGER.read_text(encoding="utf-8")
    assert "No automatic\nbackfill" in adr
    assert "PAPER-OBS-01" in adr
    assert "PAPER-OBS-LEDGER-01" in adr
    assert "JOURNAL-UX-01" in adr
    assert "STEP31-RESEARCH-01 remains future-only and is not authorized to begin" in adr
    assert "No current runtime behavior changes" in adr


def test_adr0016_is_indexed_and_all_changed_architecture_links_resolve() -> None:
    index_paths = (
        ARCHITECTURE / "README.md",
        ARCHITECTURE / "KNOWLEDGE_BASE.md",
        ARCHITECTURE / "adr" / "README.md",
        ARCHITECTURE / "interfaces" / "README.md",
        ARCHITECTURE / "platform" / "ARCHITECTURE_INDEX.md",
        ARCHITECTURE / "products" / "swing" / "README.md",
    )
    for path in index_paths:
        assert "ADR-0016" in path.read_text(encoding="utf-8")

    markdown_link = re.compile(r"\[[^]]+\]\(([^)]+)\)")
    changed_docs = (
        ADR,
        TRACK,
        PROJECTION,
        LEDGER,
        *index_paths,
        ARCHITECTURE / "ENGINE_OWNERSHIP.md",
        ARCHITECTURE / "DATA_FLOW.md",
        ARCHITECTURE / "platform" / "domains" / "risk" / "ARCHITECTURE.md",
        ARCHITECTURE / "platform" / "domains" / "risk" / "CONTRACTS.md",
        ARCHITECTURE / "products" / "swing" / "SWING-V1-STEP-32-PRODUCT-ADRS.md",
        ARCHITECTURE / "products" / "swing" / "SWING-V1-STEP-33-OUTCOME-AND-JOURNAL-INTEGRATION.md",
    )
    for path in changed_docs:
        for target in markdown_link.findall(path.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("#"):
                continue
            resolved = (path.parent / target.split("#", 1)[0]).resolve()
            assert resolved.exists(), f"{path}: missing {target}"
