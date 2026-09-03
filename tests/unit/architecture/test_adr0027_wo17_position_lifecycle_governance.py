from __future__ import annotations

from hashlib import sha256
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ARCHITECTURE = ROOT / "docs" / "architecture"
ADR = ARCHITECTURE / "adr" / (
    "ADR-0027-INTRADAY-WO17-POSITION-EVIDENCE-AND-ACTIVE-LIFECYCLE-"
    "MONITORING.md"
)
PRODUCT = ARCHITECTURE / "products" / "intraday" / (
    "KRONOS-INTRADAY-WO-17-POSITION-EVIDENCE-AND-ACTIVE-LIFECYCLE-"
    "MONITORING-V1.md"
)
INTERFACE = ARCHITECTURE / "interfaces" / (
    "KRONOS-INTRADAY-WO17-POSITION-EVIDENCE-AND-ACTIVE-LIFECYCLE-"
    "MONITORING-V1.md"
)
POLICY = ARCHITECTURE / "products" / "intraday" / (
    "KRONOS-INTRADAY-WO17-POSITION-EVIDENCE-AND-ACTIVE-LIFECYCLE-"
    "MONITORING-POLICY-V1.json"
)
LIVING = ARCHITECTURE / "products" / "intraday" / (
    "KRONOS-INTRADAY-ENGINEERING-METHODOLOGY-ARCHITECTURE-RECORD-V0.1.md"
)
POLICY_SHA256 = "4fafb49ef2ffb95c60d53e4061f3658237134c82995db9bd128be99637d38a1a"


def _policy() -> dict[str, object]:
    return json.loads(POLICY.read_text(encoding="utf-8"))


def test_identity_version_authority_and_engineering_hold_are_exact() -> None:
    for path in (ADR, PRODUCT, INTERFACE):
        text = path.read_text(encoding="utf-8")
        assert (
            "KRONOS-INTRADAY-WO17-POSITION-EVIDENCE-AND-ACTIVE-"
            "LIFECYCLE-MONITORING-V1"
        ) in text
        assert "1.0.0" in text
        assert (
            "FACTUAL_POSITION_EVIDENCE_AND_READ_ONLY_LIFECYCLE_MONITORING_ONLY"
        ) in text
    assert "WO-17 production source engineering not authorized" in ADR.read_text(
        encoding="utf-8"
    )


def test_policy_is_canonical_json_and_checksum_is_published() -> None:
    raw = POLICY.read_bytes()
    policy = _policy()
    canonical = (json.dumps(policy, sort_keys=True, indent=2) + "\n").encode("utf-8")
    assert raw == canonical
    assert sha256(raw).hexdigest() == POLICY_SHA256
    assert policy["policy_identity"] == (
        "KRONOS-INTRADAY-WO17-POSITION-EVIDENCE-AND-ACTIVE-LIFECYCLE-"
        "MONITORING-POLICY-V1"
    )
    assert policy["policy_version"] == "1.0.0"
    assert policy["authority"] == (
        "FACTUAL_POSITION_EVIDENCE_AND_READ_ONLY_LIFECYCLE_MONITORING_ONLY"
    )
    assert POLICY_SHA256 in ADR.read_text(encoding="utf-8")
    assert POLICY_SHA256 in PRODUCT.read_text(encoding="utf-8")


def test_exact_upstream_binding_ignore_exclusion_and_wo14_non_veto() -> None:
    upstream = _policy()["upstream"]
    assert upstream["allowed_sponsor_choices"] == ["PAPER", "LIVE"]
    assert upstream["admission_disposition"] == "PENDING_POSITION_EVIDENCE"
    assert upstream["ignore"] == "EXCLUDED"
    assert upstream["recalculation"] == "PROHIBITED"
    assert upstream["wo14_authority"] == "ADVISORY_NON_VETO"
    assert upstream["bindings"] == [
        "WO13_TRADE_PLAN",
        "WO14_RISK_OBSERVATION",
        "WO15_TIMING_HANDOFF",
        "WO16_SPONSOR_DECISION",
        "WO16_LIFECYCLE_ADMISSION",
        "DOMAIN_008_SESSION",
        "CANONICAL_SUBJECT_INSTRUMENT_CONTRACT_ROLL_LINEAGE",
    ]


def test_paper_requires_two_ordered_continuous_crossing_observations() -> None:
    paper = _policy()["paper"]
    assert paper["armed_state"] == "PAPER_ARMED"
    assert paper["activation_state"] == "PAPER_ACTIVE"
    assert paper["entry_event"] == "PAPER_ENTRY_OBSERVED"
    assert paper["first_observation"] == "BASELINE_ONLY"
    assert paper["required_observation_count"] == 2
    assert paper["required_observation_relation"] == (
        "ORDERED_CONSECUTIVE_CONTINUOUS"
    )
    assert paper["long_crossing"] == {
        "current": "PRICE_GREATER_THAN_OR_EQUAL_TO_ENTRY_REFERENCE",
        "previous": "PRICE_LESS_THAN_ENTRY_REFERENCE",
    }
    assert paper["short_crossing"] == {
        "current": "PRICE_LESS_THAN_OR_EQUAL_TO_ENTRY_REFERENCE",
        "previous": "PRICE_GREATER_THAN_ENTRY_REFERENCE",
    }
    assert paper["starts_beyond_entry"] == "ENTRY_SEQUENCE_UNRESOLVED"
    assert _policy()["entry"]["gap_crossing_consequence"] == (
        "ENTRY_SEQUENCE_UNRESOLVED"
    )


def test_live_requires_exact_sponsor_attestation_and_never_broker_truth() -> None:
    live = _policy()["live"]
    assert live["armed_state"] == "LIVE_AWAITING_SPONSOR_ENTRY_EVIDENCE"
    assert live["entry_event"] == "LIVE_ENTRY_ATTESTED"
    assert live["activation_state"] == "LIVE_ACTIVE"
    assert live["actual_entry_required"] == [
        "WO16_DECISION_ADMISSION_IDENTITY",
        "EXACT_INSTRUMENT_OR_MCX_CONTRACT",
        "DIRECTION",
        "ACTUAL_ENTRY_PRICE",
        "ACTUAL_ENTRY_TIMESTAMP",
        "BOUNDED_MANUAL_ACTION_PROVENANCE",
        "EXACT_LINEAGE",
    ]
    assert live["broker_acknowledgement"] is False
    assert live["market_observation_auto_close"] is False
    assert live["closure"] == "SPONSOR_ATTESTED_ACTUAL_EXIT_EVIDENCE_ONLY"


def test_nse_mcx_cutoffs_are_inclusive_rejections_and_live_is_dual_timestamp() -> None:
    cutoffs = _policy()["cutoffs"]
    assert cutoffs["NSE"] == {
        "comparison": "STRICTLY_BEFORE",
        "cutoff_ist": "15:00:00",
        "entry_or_attestation_at_cutoff": "REJECT",
    }
    assert cutoffs["MCX"] == {
        "comparison": "STRICTLY_BEFORE",
        "cutoff_ist": "23:00:00",
        "entry_or_attestation_at_cutoff": "REJECT",
    }
    assert cutoffs["LIVE"]["both_timestamps_must_precede_cutoff"] is True
    assert cutoffs["LIVE"]["required_timestamps"] == [
        "ACTUAL_ENTRY_TIMESTAMP",
        "SPONSOR_ATTESTATION_OPERATION_TIMESTAMP",
    ]
    assert cutoffs["global_cutoff"] == "NONE"
    assert cutoffs["exceptional_sessions_owner"] == "DOMAIN_008"


def test_pre_entry_invalidation_and_expiry_create_no_position() -> None:
    entry = _policy()["entry"]
    assert entry["pre_entry_invalidation"] == "ENTRY_INVALIDATED_BEFORE_POSITION"
    assert entry["window_expiry"] == "ENTRY_WINDOW_EXPIRED"
    interface = INTERFACE.read_text(encoding="utf-8")
    assert "Both preserve history and create no position" in interface


def test_one_non_closed_position_per_subject_blocks_successor_activation() -> None:
    cardinality = _policy()["position_cardinality"]
    assert cardinality["maximum_non_closed_per_subject"] == 1
    assert cardinality["current_pointer_scope"] == "CANONICAL_SUBJECT"
    assert cardinality["prior_session_non_closed_remains_current"] is True
    assert cardinality["successor_activation_while_non_closed"] == (
        "REJECT_FAIL_CLOSED"
    )
    assert cardinality["successor_wo16_evidence_mutation"] == "PROHIBITED"
    assert cardinality["mcx_automatic_contract_migration"] == "PROHIBITED"
    assert cardinality["pointer_binding"] == [
        "EXACT_INSTRUMENT",
        "ACTUAL_MCX_CONTRACT_WHEN_APPLICABLE",
        "ROLL_LINEAGE",
        "ENTRY_SESSION",
        "LIFECYCLE",
    ]


def test_monitoring_availability_interruption_and_recovery_are_separate() -> None:
    monitoring = _policy()["monitoring"]
    assert monitoring["provider_transport"] == (
        "SHARED_DOMAIN_006_READ_ONLY_KITE_WEBSOCKET"
    )
    assert monitoring["availability_separate_from_position_state"] is True
    assert monitoring["availability_states"] == [
        "NOT_APPLICABLE",
        "AVAILABLE",
        "INTERRUPTED",
        "RECOVERING",
        "SESSION_ENDED",
        "UNAVAILABLE",
    ]
    assert monitoring["state_preserved_on_interruption"] is True
    assert monitoring["fresh_baseline_after_recovery"] is True
    assert monitoring["missed_crossing_inference"] == "PROHIBITED"
    assert monitoring["order_updates_create_lifecycle_truth"] is False


def test_stop_target_order_ambiguity_and_session_end_fail_closed() -> None:
    lifecycle = _policy()["stop_target_invalidation"]
    assert lifecycle["levels"] == "EXACT_IMMUTABLE_WO13"
    assert lifecycle["long_stop"] == "PRICE_LESS_THAN_OR_EQUAL_TO_STOP"
    assert lifecycle["long_target"] == "PRICE_GREATER_THAN_OR_EQUAL_TO_TARGET"
    assert lifecycle["short_stop"] == "PRICE_GREATER_THAN_OR_EQUAL_TO_STOP"
    assert lifecycle["short_target"] == "PRICE_LESS_THAN_OR_EQUAL_TO_TARGET"
    assert lifecycle["same_observation_or_gap_both_crossed"] == (
        "LIFECYCLE_EVENT_ORDER_UNRESOLVED"
    )
    assert lifecycle["invalidation_after_entry"] == (
        "INVALIDATION_OBSERVED_NO_AUTOMATIC_CLOSE"
    )
    end = _policy()["session_end"]
    assert end["force_close"] is False
    assert end["assumed_exit"] is False
    assert end["automatic_later_session_reactivation"] is False
    assert end["position_and_history"] == "PRESERVE"


def test_quantity_pnl_r_broker_notification_delivery_and_journal_are_excluded() -> None:
    policy = _policy()
    for mode in ("paper", "live"):
        assert policy[mode]["quantity"] == "UNAVAILABLE"
        assert policy[mode]["monetary_pnl"] == "UNAVAILABLE"
        assert policy[mode]["realised_r"] == "UNAVAILABLE"
    prohibited = set(policy["prohibited"])
    assert {
        "WO14_PERMISSION_OR_VETO",
        "BROKER_ORDER_OR_EXECUTION",
        "QUANTITY_OR_SIZING",
        "MONETARY_PNL",
        "REALISED_R",
        "NOTIFICATION_DELIVERY",
        "JOURNAL_OR_ANALYTICS",
    } <= prohibited
    assert policy["notification"]["delivery_authority"] == "WO_18_ONLY"
    assert policy["notification"]["notifications_are_lifecycle_authority"] is False


def test_persistence_and_restart_cannot_manufacture_events() -> None:
    persistence = _policy()["persistence"]
    assert persistence["identities_owner"] == "KRONOS_INTRADAY"
    assert persistence["immutable_append_only"] is True
    assert persistence["canonical_serialization"] is True
    assert persistence["integrity"] == "SHA_256"
    assert persistence["conflicting_bytes"] == "REJECT"
    assert persistence["current_pointer"] == "ATOMIC_SUBJECT_SCOPED_ALIAS"
    assert persistence["latest_failure"] == "SEPARATE_ATOMIC_ALIAS"
    assert persistence["restart_event_manufacture"] == "PROHIBITED"
    assert persistence["restoration_recalculation"] is False


def test_cutoff_supersession_is_explicit_and_deferred_wording_is_removed() -> None:
    adr = ADR.read_text(encoding="utf-8")
    living = LIVING.read_text(encoding="utf-8")
    assert "explicitly supersedes older Intraday wording" in adr
    assert "Action at or after `15:00:00 IST` is rejected" in living
    assert "Action at or after `23:00:00 IST` is rejected" in living
    assert "Exact semantics at precisely `15:00:00`: **DEFERRED / UNRESOLVED**" not in living
    assert "exact NSE new-entry semantics at `15:00:00`;" not in living


def test_governance_indexes_and_ownership_records_are_current() -> None:
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
        LIVING,
    )
    for path in indexed:
        assert "WO-17" in path.read_text(encoding="utf-8"), path


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
        LIVING,
    )
    for path in changed:
        for target in markdown_link.findall(path.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("#"):
                continue
            resolved = (path.parent / target.split("#", 1)[0]).resolve()
            assert resolved.exists(), f"{path}: missing {target}"
