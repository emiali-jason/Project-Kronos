from __future__ import annotations

from hashlib import sha256
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ARCHITECTURE = ROOT / "docs" / "architecture"
ADR = ARCHITECTURE / "adr" / (
    "ADR-0026-INTRADAY-WO16-SPONSOR-DECISION-AND-SESSION-BOUNDED-"
    "LIFECYCLE-ADMISSION.md"
)
PRODUCT = ARCHITECTURE / "products" / "intraday" / (
    "KRONOS-INTRADAY-WO-16-SPONSOR-DECISION-AND-LIFECYCLE-ADMISSION-V1.md"
)
INTERFACE = ARCHITECTURE / "interfaces" / (
    "KRONOS-INTRADAY-WO16-SPONSOR-DECISION-AND-LIFECYCLE-ADMISSION-V1.md"
)
POLICY = ARCHITECTURE / "products" / "intraday" / (
    "KRONOS-INTRADAY-WO16-SPONSOR-DECISION-LIFECYCLE-ADMISSION-POLICY-V1.json"
)
POLICY_SHA256 = "f9ab891659500abad755cdd272527bfd6e406422042b825b209620d934a3ce9c"


def _policy() -> dict[str, object]:
    return json.loads(POLICY.read_text(encoding="utf-8"))


def test_adr0026_identity_status_authority_and_engineering_hold_are_exact() -> None:
    text = ADR.read_text(encoding="utf-8")
    for expected in (
        "ADR-0026",
        "KRONOS-INTRADAY-WO16-SPONSOR-DECISION-SESSION-BOUNDED-"
        "LIFECYCLE-ADMISSION-V1",
        "APPROVED — PUBLICATION PENDING",
        "EXPLICIT_SPONSOR_DECISION_AND_FACTUAL_LIFECYCLE_ADMISSION_ONLY",
        "WO-16 production source engineering not authorized",
        "Runtime / Provider / Position / Broker Authority:** NONE",
    ):
        assert expected in text


def test_policy_payload_checksum_identity_and_contract_family_are_exact() -> None:
    assert sha256(POLICY.read_bytes()).hexdigest() == POLICY_SHA256
    policy = _policy()
    assert policy["policy_identity"] == (
        "KRONOS-INTRADAY-WO16-SPONSOR-DECISION-LIFECYCLE-ADMISSION-"
        "POLICY-V1"
    )
    assert policy["policy_version"] == "1.0.0"
    assert policy["authority"] == (
        "EXPLICIT_SPONSOR_DECISION_AND_FACTUAL_LIFECYCLE_ADMISSION_ONLY"
    )
    assert policy["identity"] == {
        "admission_contract": "KRONOS-INTRADAY-WO16-LIFECYCLE-ADMISSION-V1",
        "current_pointer_contract": "KRONOS-INTRADAY-CURRENT-WO16-DECISION-V1",
        "decision_contract": "KRONOS-INTRADAY-WO16-SPONSOR-DECISION-V1",
        "invalid_operation_contract": "KRONOS-INTRADAY-WO16-INVALID-OPERATION-V1",
        "snapshot_contract": "KRONOS-INTRADAY-WO16-SPONSOR-DECISION-SNAPSHOT-V1",
    }
    assert POLICY_SHA256 in ADR.read_text(encoding="utf-8")
    assert POLICY_SHA256 in PRODUCT.read_text(encoding="utf-8")


def test_exact_current_wo13_wo14_wo15_and_session_admission_is_frozen() -> None:
    eligibility = _policy()["eligibility"]
    assert eligibility["wo13"] == {
        "current_non_superseded": True,
        "geometry_state": "GEOMETRY_COMPLETE",
        "integrity_required": True,
    }
    assert eligibility["wo15"] == {
        "current_non_superseded": True,
        "integrity_required": True,
        "timing_state": "TIMING_QUALIFIED",
    }
    assert eligibility["domain_008"] == {
        "required": True,
        "session_end": False,
        "state": "OPEN",
    }
    assert eligibility["canonical_lineage"] == "EXACT_MATCH_REQUIRED"
    assert eligibility["mcx_contract_roll_lineage"] == (
        "EXACT_MATCH_WHEN_APPLICABLE"
    )
    assert eligibility["older_qualified_handoff_selection"] == "PROHIBITED"


def test_wo14_is_required_context_and_never_permission_veto_or_quantity() -> None:
    risk = _policy()["eligibility"]["wo14"]
    assert risk == {
        "allowed_states": ["RISK_OBSERVED", "RISK_ALERT", "RISK_UNAVAILABLE"],
        "final_quantity_authority": False,
        "required": True,
        "trade_permission_authority": False,
        "trade_veto_authority": False,
    }
    text = ADR.read_text(encoding="utf-8")
    assert (
        "`RISK_APPROVED` and\n`RISK_REJECTED` are not Intraday WO-16 "
        "prerequisites or states"
    ) in text


def test_decision_vocabulary_authorship_and_separate_admission_are_exact() -> None:
    policy = _policy()
    assert policy["decision"] == {
        "choices": ["PAPER", "LIVE", "IGNORE"],
        "free_text_note": "NOT_SUPPORTED_V1",
        "person_identity": "NOT_RECORDED_V1",
        "reason_vocabulary": "NONE_V1",
        "source": "LOCAL_SPONSOR_BROWSER_ACTION",
    }
    assert policy["admission"] == {
        "IGNORE": "NOT_APPLICABLE_IGNORE",
        "LIVE": "PENDING_POSITION_EVIDENCE",
        "PAPER": "PENDING_POSITION_EVIDENCE",
        "position_created": False,
    }
    interface = INTERFACE.read_text(encoding="utf-8")
    assert "Decision receipt and lifecycle admission are separate" in ADR.read_text(
        encoding="utf-8"
    )
    assert "There is no person-identity field, free-text note or Swing reason" in interface


def test_paper_and_live_truth_never_invents_position_fill_or_economics() -> None:
    policy = _policy()
    unavailable = {
        "actual_fill_price": "UNAVAILABLE",
        "actual_fill_timestamp": "UNAVAILABLE",
        "broker_execution_state": "UNAVAILABLE",
        "broker_order_identity": "UNAVAILABLE",
        "fees": "UNAVAILABLE",
        "monetary_pnl": "UNAVAILABLE",
        "quantity": "UNAVAILABLE",
        "realised_r": "UNAVAILABLE",
    }
    assert policy["truth"]["PAPER"] == unavailable
    assert policy["truth"]["LIVE"] == unavailable
    for prohibited in (
        "SPONSOR_POSITION_CREATION",
        "PAPER_SIMULATED_FILL",
        "LIVE_FILL_INFERENCE",
        "QUANTITY_INFERENCE",
        "PNL_OR_REALISED_R_CREATION",
        "BROKER_ORDER_MUTATION",
    ):
        assert prohibited in policy["prohibited"]


def test_session_replay_supersession_and_current_cardinality_are_exact() -> None:
    policy = _policy()
    assert policy["replay"] == {
        "conflicting_bytes": "FAIL_CLOSED",
        "exact_same_request_bytes": "RETURN_RETAINED_RESULT",
        "final_decisions_per_timing_handoff": 1,
        "mode_revision_same_handoff": "PROHIBITED",
    }
    assert policy["session"] == {
        "closed_or_ended_operation": "REJECT_BEFORE_DECISION",
        "existing_records": "IMMUTABLE_HISTORICAL",
        "forced_exit_authority": "NONE",
        "overnight_carry_authority": "NONE",
        "session_or_lineage_not_current": "CURRENT_PROJECTION_INELIGIBLE",
    }
    assert policy["persistence"]["current_cardinality"] == (
        "ONE_PER_CANONICAL_SUBJECT"
    )
    assert policy["supersession"]["prior_record_mutation"] == "PROHIBITED"
    assert policy["supersession"]["ignore_scope"] == "EXACT_BOUND_LINEAGE_ONLY"


def test_product_local_persistence_and_restore_are_side_effect_free() -> None:
    persistence = _policy()["persistence"]
    assert persistence["evidence_root"] == "INTRADAY_PRODUCT_LOCAL_WO16"
    assert persistence["append_only_families"] == [
        "SNAPSHOTS",
        "DECISIONS",
        "ADMISSIONS",
        "OPERATIONS",
        "INVALID",
        "SUPERSESSIONS",
    ]
    assert persistence["current_pointer"] == "ATOMIC_ALIAS_TO_IMMUTABLE_GRAPH"
    assert persistence["latest_failure"] == "SEPARATE_ATOMIC_ALIAS"
    assert persistence["later_failure_replaces_current"] is False
    assert persistence["restore_recalculation"] is False
    assert persistence["restore_side_effects"] == "NONE"


def test_browser_security_and_future_authority_are_bounded() -> None:
    policy = _policy()
    assert policy["browser"] == {
        "actual_facts_missing_value": "UNAVAILABLE",
        "broker_copy": "NO_BROKER_ORDER_WAS_PLACED",
        "current_history_latest_failure_separate": True,
        "get_side_effects": "NONE",
        "ownership": "INTRADAY_PRODUCT_ROUTES_AND_VIEWS",
    }
    security = policy["security"]
    assert security["content_type"] == "APPLICATION_JSON_ONLY"
    assert security["fields"] == "EXACT_REQUIRED_AND_EXTRA_REJECTED"
    assert security["query"] == "PROHIBITED"
    assert security["host"] == "EXACT_LOOPBACK_HOST_VALIDATION"
    assert security["origin"] == "EXACT_SAME_ORIGIN_VALIDATION"
    assert security["sponsor_work_admission"] == "REQUIRED"
    assert security["concurrency"] == "NONBLOCKING_BOUNDED_BUSY"
    assert security["sanitized_failures"] is True
    assert set(policy["future_authority"].values()) == {
        "SEPARATE_GOVERNANCE_REQUIRED"
    }


def test_governance_indexes_ownership_and_deferred_boundaries_are_current() -> None:
    indexed = (
        ARCHITECTURE / "README.md",
        ARCHITECTURE / "KNOWLEDGE_BASE.md",
        ARCHITECTURE / "adr" / "README.md",
        ARCHITECTURE / "interfaces" / "README.md",
        ARCHITECTURE / "platform" / "ARCHITECTURE_INDEX.md",
        ARCHITECTURE / "products" / "intraday" / "README.md",
        ARCHITECTURE / "products" / "intraday" / "RESPONSIBILITIES.md",
        ARCHITECTURE / "products" / "intraday" / "INTERFACES.md",
        ARCHITECTURE / "products" / "intraday"
        / "KRONOS-INTRADAY-CONTRACT-STATE-OWNERSHIP-REGISTRY.md",
        ARCHITECTURE / "products" / "intraday"
        / "KRONOS-INTRADAY-DEFERRED-DECISION-REGISTER.md",
        ARCHITECTURE / "products" / "intraday"
        / "KRONOS-INTRADAY-V1-PROGRAMME-ROADMAP.md",
    )
    for path in indexed:
        assert "WO-16" in path.read_text(encoding="utf-8"), path
    deferred = indexed[-2].read_text(encoding="utf-8")
    for expected in (
        "Intraday PAPER simulation and position model",
        "Intraday LIVE actual-position attestation",
        "Intraday position monitoring and closure",
        "Intraday monetary P&L and realised R",
    ):
        assert expected in deferred


def test_changed_architecture_links_resolve() -> None:
    markdown_link = re.compile(r"\[[^]]+\]\(([^)]+)\)")
    changed = (
        ADR,
        PRODUCT,
        INTERFACE,
        ARCHITECTURE / "README.md",
        ARCHITECTURE / "KNOWLEDGE_BASE.md",
        ARCHITECTURE / "adr" / "README.md",
        ARCHITECTURE / "interfaces" / "README.md",
        ARCHITECTURE / "platform" / "ARCHITECTURE_INDEX.md",
        ARCHITECTURE / "products" / "intraday" / "README.md",
        ARCHITECTURE / "products" / "intraday"
        / "KRONOS-INTRADAY-V1-PROGRAMME-ROADMAP.md",
    )
    for path in changed:
        for target in markdown_link.findall(path.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("#"):
                continue
            resolved = (path.parent / target.split("#", 1)[0]).resolve()
            assert resolved.exists(), f"{path}: missing {target}"
