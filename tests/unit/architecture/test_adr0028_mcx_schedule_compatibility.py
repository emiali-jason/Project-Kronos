from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ARCHITECTURE = ROOT / "docs" / "architecture"
ADR = ARCHITECTURE / "adr" / (
    "ADR-0028-DOMAIN-008-MCX-CROSS-SCHEDULE-COMPATIBILITY.md"
)
MARKET = ARCHITECTURE / "platform" / "domains" / "market"


def test_adr0028_identity_contract_and_domain_ownership_are_exact() -> None:
    text = ADR.read_text(encoding="utf-8")
    assert "ADR-0028" in text
    assert "KRONOS-DOMAIN-008-MCX-CROSS-SCHEDULE-COMPATIBILITY-V1" in text
    assert "KRONOS-MARKET-SCHEDULE-COMPATIBILITY-V1 / 1.0.0" in text
    assert (
        "KRONOS-DOMAIN-008-MCX-FAMILY-SCHEDULE-DERIVATION-POLICY-V1 / 1.0.0"
        in text
    )
    assert "DOMAIN-008 alone owns schedule compatibility" in text


def test_directional_lineage_and_fail_closed_boundaries_are_frozen() -> None:
    text = ADR.read_text(encoding="utf-8")
    for phrase in (
        "directional statement",
        "Clock equality has no compatibility authority",
        "Wildcard compatibility",
        "arbitrary mixed schedules",
        "A superseded artifact is",
        "not applicable",
        "not contract-roll continuity",
    ):
        assert phrase in text


def test_negative_authority_and_historical_immutability_are_explicit() -> None:
    text = ADR.read_text(encoding="utf-8")
    for phrase in (
        "Historical",
        "completed-evidence artifacts remain immutable",
        "remain immutable",
        "no analytical",
        "trading or broker authority",
        "NATGAS commissioning hold is unchanged",
    ):
        assert phrase in text


def test_architecture_indexes_and_domain_records_reference_adr0028() -> None:
    paths = (
        ARCHITECTURE / "adr" / "README.md",
        ARCHITECTURE / "KNOWLEDGE_BASE.md",
        ARCHITECTURE / "platform" / "ARCHITECTURE_INDEX.md",
        MARKET / "ARCHITECTURE.md",
        MARKET / "ENGINEERING.md",
    )
    for path in paths:
        assert "ADR-0028" in path.read_text(encoding="utf-8")
