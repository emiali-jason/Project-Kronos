from __future__ import annotations

import json
import re
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ARCHITECTURE_ROOT = REPOSITORY_ROOT / "docs" / "architecture"
REGISTRY_PATH = (
    ARCHITECTURE_ROOT
    / "interfaces"
    / "KR-370-KR-380-STATE-FAMILY-CONTRACTS.json"
)
CONTRACT_PATH = (
    ARCHITECTURE_ROOT
    / "interfaces"
    / "KR-370-KR-380-STATE-FAMILY-CONTRACTS.md"
)
ADR_PATH = (
    ARCHITECTURE_ROOT
    / "adr"
    / "ADR-0011-KR-370-ANALYTICAL-PROMOTION-AND-KR-380-ENTRY-OUTCOME-SEMANTICS.md"
)


def _registry() -> dict[str, object]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def _family(identity: str) -> dict[str, object]:
    families = _registry()["state_families"]
    assert isinstance(families, dict)
    family = families[identity]
    assert isinstance(family, dict)
    return family


def test_kr370_analytical_promotion_has_no_downstream_authority() -> None:
    assert _registry()["governing_decision_identity"] == "KR-370-ADR-01"
    family = _family("KR370_ANALYTICAL_PROMOTION_V1")

    assert family["owner_identity"] == "KR-370"
    assert family["state_family_identity"] == "KR370_ANALYTICAL_PROMOTION"
    assert family["states"] == [
        "BUY_NOW",
        "SELL_NOW",
        "BUY_READY",
        "SELL_READY",
        "POTENTIAL_BUY_SETUP",
        "POTENTIAL_SELL_SETUP",
        "NO_SETUP",
    ]
    for authority in (
        "execution_authority",
        "risk_authority",
        "sponsor_decision_authority",
        "position_authority",
        "fill_authority",
        "broker_authority",
        "kr390_current_input",
        "kr400_current_alert_source",
    ):
        assert family[authority] is False


def test_current_kr380_entry_outcome_uses_unambiguous_trigger_names() -> None:
    family = _family("KR380_ENTRY_OUTCOME_V2")

    assert family["owner_identity"] == "KR-380"
    assert family["state_family_identity"] == "KR380_ENTRY_OUTCOME"
    assert family["states"] == [
        "NO_TRIGGER",
        "FORMING",
        "LONG_ENTRY_TRIGGERED",
        "SHORT_ENTRY_TRIGGERED",
        "EXTENDED",
        "FAILED",
    ]
    assert "BUY_NOW" not in family["states"]
    assert "SELL_NOW" not in family["states"]


def test_historical_kr380_entry_outcome_remains_readable_only() -> None:
    family = _family("KR380_ENTRY_OUTCOME_V1")

    assert family["status"] == "HISTORICAL_READ_ONLY"
    assert family["states"] == [
        "NO_TRIGGER",
        "FORMING",
        "BUY_NOW",
        "SELL_NOW",
        "EXTENDED",
        "FAILED",
    ]
    assert family["current_production_permitted"] is False
    assert family["historical_restoration_permitted"] is True
    assert family["new_downstream_effect_permitted"] is False


def test_kr390_and_kr400_accept_only_current_kr380_trigger_states() -> None:
    promotion = _family("KR370_ANALYTICAL_PROMOTION_V1")
    entry = _family("KR380_ENTRY_OUTCOME_V2")

    assert promotion["kr390_current_input"] is False
    assert promotion["kr400_current_alert_source"] is False
    assert entry["kr390_current_trigger_states"] == [
        "LONG_ENTRY_TRIGGERED",
        "SHORT_ENTRY_TRIGGERED",
    ]
    assert entry["kr400_current_event_identities"] == [
        "KR380_LONG_ENTRY_TRIGGERED",
        "KR380_SHORT_ENTRY_TRIGGERED",
    ]


def test_contract_preserves_step31_risk_sponsor_and_broker_boundaries() -> None:
    contract = CONTRACT_PATH.read_text(encoding="utf-8")

    assert "Step 31" in contract
    assert "sole owner of Entry, Stop, Target, invalidation, and" in contract
    assert "DOMAIN-007 Risk permission" in contract
    assert "No state in either family records `LIVE`, `PAPER`, or `IGNORE`" in contract
    assert "places/modifies/cancels an order" in contract


def test_adr_requires_full_downstream_gates_and_no_runtime_authority() -> None:
    adr = ADR_PATH.read_text(encoding="utf-8")

    assert "KR-370 analytical `BUY NOW` / `SELL NOW` never bypasses Step 31, Risk, or" in adr
    assert "does not:\n\n- implement the KR-370 five-criterion classifier" in adr
    assert "change Intraday product behavior" in adr
    assert "Broker execution\n  -> no new authority" in adr


def test_current_canonical_ownership_documents_do_not_assign_now_literals_to_kr380() -> None:
    paths = (
        ARCHITECTURE_ROOT / "platform" / "PLATFORM-000-CONSTITUTION.md",
        ARCHITECTURE_ROOT / "ENGINE_OWNERSHIP.md",
        ARCHITECTURE_ROOT / "DATA_FLOW.md",
        ARCHITECTURE_ROOT
        / "principles"
        / "PP-007-Execution-Semantics-Across-Markets.md",
        ARCHITECTURE_ROOT / "platform" / "PLATFORM_BUSINESS_PIPELINE.md",
        ARCHITECTURE_ROOT / "platform" / "DOMAIN_OWNERSHIP_MATRIX.md",
    )
    forbidden = re.compile(
        r"KR-380 (?:retains|owns|produces).{0,80}BUY NOW / SELL NOW",
        flags=re.IGNORECASE,
    )

    for path in paths:
        assert forbidden.search(path.read_text(encoding="utf-8")) is None, path


def test_new_architecture_links_resolve() -> None:
    markdown_link = re.compile(r"\[[^]]+\]\(([^)]+)\)")

    for path in (ADR_PATH, CONTRACT_PATH):
        for target in markdown_link.findall(path.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("#"):
                continue
            resolved = (path.parent / target.split("#", 1)[0]).resolve()
            assert resolved.exists(), f"{path}: missing {target}"
