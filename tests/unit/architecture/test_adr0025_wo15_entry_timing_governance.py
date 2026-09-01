from __future__ import annotations

from hashlib import sha256
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ARCHITECTURE = ROOT / "docs" / "architecture"
ADR = ARCHITECTURE / "adr" / (
    "ADR-0025-INTRADAY-WO15-KR380-COMPLETED-5M-ENTRY-TIMING-BOUNDARY.md"
)
PRODUCT = ARCHITECTURE / "products" / "intraday" / (
    "KRONOS-INTRADAY-WO-15-KR380-ENTRY-TIMING-V1.md"
)
POLICY = ARCHITECTURE / "products" / "intraday" / (
    "KRONOS-INTRADAY-WO15-ENTRY-TIMING-POLICY-V1.json"
)
POLICY_SHA256 = "d36386a98e2f1b78e5b70d0c27079c056951fd76a5b70ec2e9fa1bc1615a3f26"


def _policy() -> dict[str, object]:
    return json.loads(POLICY.read_text(encoding="utf-8"))


def test_adr0025_identity_authority_and_four_part_boundary_are_exact() -> None:
    text = ADR.read_text(encoding="utf-8")
    for expected in (
        "ADR-0025",
        "KRONOS-INTRADAY-WO15-KR380-ENTRY-TIMING-BOUNDARY-V1",
        "COMPLETED_5M_ENTRY_TIMING_QUALIFICATION_ONLY",
        "**WO-15A:**",
        "**WO-15B:**",
        "**WO-15C:**",
        "**WO-15D:**",
        "WO-15 production source engineering not authorized",
    ):
        assert expected in text


def test_policy_payload_and_checksum_are_canonical() -> None:
    raw = POLICY.read_bytes()
    assert sha256(raw).hexdigest() == POLICY_SHA256
    policy = _policy()
    assert policy["policy_identity"] == (
        "KRONOS-INTRADAY-WO15-ENTRY-TIMING-POLICY-V1"
    )
    assert policy["policy_version"] == "1.0.0"
    assert policy["authority"] == "COMPLETED_5M_ENTRY_TIMING_QUALIFICATION_ONLY"
    assert POLICY_SHA256 in ADR.read_text(encoding="utf-8")
    assert POLICY_SHA256 in PRODUCT.read_text(encoding="utf-8")


def test_wo13_geometry_is_immutable_and_wo14_is_non_veto_context() -> None:
    policy = _policy()
    assert policy["wo13_input"]["contract_identity"] == (
        "KRONOS-INTRADAY-WO13-TRADE-PLAN-V1"
    )
    assert policy["wo13_input"]["geometry_mutation"] == "PROHIBITED"
    assert policy["risk_relationship"] == {
        "prerequisite": False,
        "risk_alert_timing_veto": False,
        "risk_observed_timing_veto": False,
        "risk_unavailable_timing_veto": False,
    }
    text = ADR.read_text(encoding="utf-8")
    assert "does not require\n`RISK_APPROVED`, `RISK_PERMISSION` or `RISK_REJECTED`" in text
    assert "ADR-0011/ADR-0013 Swing Risk-permission" in text


def test_completed_5m_authority_states_and_precedence_are_exact() -> None:
    policy = _policy()
    assert policy["canonical_evidence"] == {
        "authoritative": "COMPLETED_GOVERNED_5M_CANDLES_ONLY",
        "incomplete_candle_authority": "NONE",
        "live_ltp_authority": "DISPLAY_CONTEXT_ONLY",
        "wick_only_authority": "NONE",
    }
    assert policy["states"] == [
        "TIMING_NOT_EVALUATED",
        "TIMING_WAITING",
        "TIMING_QUALIFIED",
        "TIMING_FAILED",
        "TIMING_EXPIRED",
        "TIMING_UNAVAILABLE",
    ]
    assert policy["state_precedence"] == [
        "TIMING_UNAVAILABLE",
        "TIMING_EXPIRED",
        "TIMING_FAILED",
        "TIMING_QUALIFIED",
        "TIMING_WAITING",
    ]


def test_strict_close_progression_and_pullback_grammar_are_frozen() -> None:
    policy = _policy()
    pullback = policy["setup_grammar"]["INTRADAY_PULLBACK_CONTINUATION"]
    assert pullback["long"] == "CLOSE_GT_ENTRY_AND_LONG_ALIGNED_PROGRESSION"
    assert pullback["short"] == "CLOSE_LT_ENTRY_AND_SHORT_ALIGNED_PROGRESSION"
    assert pullback["qualifying_closes"] == 1
    assert pullback["mandatory_retest"] is False
    assert pullback["failure"] == (
        "AUTHORITATIVE_OPPOSING_GOVERNED_5M_STRUCTURAL_PROGRESSION"
    )
    assert policy["progression_adapter"]["new_price_algorithm"] == "PROHIBITED"
    product = PRODUCT.read_text(encoding="utf-8")
    assert "Equality: not qualified" in product
    assert "No Entry buffer exists" in product


def test_breakout_direct_retest_resumption_and_failure_are_exact() -> None:
    breakout = _policy()["setup_grammar"]["INTRADAY_RANGE_BREAKOUT"]
    expected = {
        "direct_long": "CLOSE_GT_ORIGINAL_RANGE_HIGH_AND_LONG_ALIGNED_PROGRESSION",
        "direct_short": "CLOSE_LT_ORIGINAL_RANGE_LOW_AND_SHORT_ALIGNED_PROGRESSION",
        "long_retest": "LOW_LTE_ENTRY_AND_CLOSE_GTE_ENTRY",
        "short_retest": "HIGH_GTE_ENTRY_AND_CLOSE_LTE_ENTRY",
        "long_resumption": (
            "SUBSEQUENT_CLOSE_GT_RETEST_HIGH_AND_LONG_ALIGNED_PROGRESSION"
        ),
        "short_resumption": (
            "SUBSEQUENT_CLOSE_LT_RETEST_LOW_AND_SHORT_ALIGNED_PROGRESSION"
        ),
        "failure_long": "AFTER_ACTIVE_INTERACTION_CLOSE_LT_ORIGINAL_RANGE_HIGH",
        "failure_short": "AFTER_ACTIVE_INTERACTION_CLOSE_GT_ORIGINAL_RANGE_LOW",
    }
    for key, value in expected.items():
        assert breakout[key] == value
    assert breakout["mandatory_retest"] is False
    assert breakout["retest_tolerance"] == "NONE"
    assert "Timing failure is not thesis invalidation" in PRODUCT.read_text(
        encoding="utf-8"
    )


def test_cycle_creation_reset_multi_cycle_and_statefulness_are_frozen() -> None:
    policy = _policy()
    cycle = policy["cycle"]
    assert cycle["active_non_terminal_per_wo13_plan"] == 1
    assert cycle["creation"] == (
        "FIRST_VALID_COMPLETED_5M_EVALUATION_BOUNDARY_STRICTLY_AFTER_WO13_EFFECTIVE_BOUNDARY"
    )
    assert cycle["creation_and_first_evaluation"] == "ATOMIC"
    assert cycle["failed_cycle_rewrite"] == "PROHIBITED"
    assert cycle["reset_cooldown"] == "NONE"
    assert cycle["reset_maximum_attempts"] == "NONE"
    assert cycle["reset_common_requirements"] == [
        "PRIOR_CYCLE_TERMINALLY_FAILED",
        "BOUNDARY_STRICTLY_LATER_THAN_FAILURE",
        "SAME_CURRENT_NON_SUPERSEDED_WO13_PLAN",
        "SESSION_VALID",
        "INSTRUMENT_CONTRACT_ROLL_UNCHANGED",
        "DIRECTION_UNCHANGED",
        "SETUP_FAMILY_UNCHANGED",
        "PRIOR_FAILURE_PREDICATE_NO_LONGER_SATISFIED",
        "PROGRESSION_ALIGNED_OR_NON_DIRECTIONAL_FORMING",
        "PROGRESSION_NOT_CONTRADICTORY",
    ]
    assert policy["statefulness"]["qualified_is_historical_truth"] is True
    assert policy["statefulness"]["qualified_to_waiting_stateless_flicker"] == (
        "PROHIBITED"
    )


def test_expiry_is_bounded_and_has_no_arbitrary_ttl() -> None:
    expiry = _policy()["expiry"]
    assert expiry["causes"] == [
        "SESSION_END",
        "WO13_PLAN_SUPERSEDED",
        "UPSTREAM_CYCLE_SUPERSEDED",
        "INSTRUMENT_CONTRACT_SUPERSEDED",
        "DOMAIN_008_MARKET_SESSION_INVALID_OR_CLOSED",
    ]
    assert expiry["arbitrary_bar_expiry"] == "NONE"
    assert expiry["arbitrary_time_expiry"] == "NONE"
    assert expiry["overnight_cycle_carry"] == "PROHIBITED"


def test_extension_atr_and_other_telemetry_are_research_only() -> None:
    policy = _policy()
    extension = policy["extension"]
    assert extension["long_directional_formula"] == (
        "COMPLETED_5M_CLOSE_MINUS_ENTRY_REFERENCE"
    )
    assert extension["short_directional_formula"] == (
        "ENTRY_REFERENCE_MINUS_COMPLETED_5M_CLOSE"
    )
    assert extension["absolute_formula"] == (
        "ABS(COMPLETED_5M_CLOSE_MINUS_ENTRY_REFERENCE)"
    )
    assert extension["normalized_formula"] == (
        "DIRECTIONAL_EXTENSION_DIVIDED_BY_ATR14_5M"
    )
    assert extension["atr"]["timeframe"] == "COMPLETED_GOVERNED_5M"
    assert extension["atr"]["calculation"] == "WILDER_RMA"
    assert extension["atr"]["period"] == 14
    assert extension["authority"] == "ADVISORY_RESEARCH_ONLY"
    assert extension["severity"] == "UNCLASSIFIED"
    assert extension["timing_veto"] == extension["trade_veto"] == "NONE"
    for fact in (
        "VOLUME_RATIO_PERCENTILE",
        "RSI14",
        "SMA_RAILWAY_STATE",
        "CPR_PDH_PDL_PIVOT_CONTEXT",
    ):
        assert fact in policy["research_only"]


def test_timing_handoff_is_versioned_append_only_and_non_executing() -> None:
    handoff = _policy()["handoff"]
    assert handoff["contract_identity"] == (
        "KRONOS-INTRADAY-WO15-TIMING-HANDOFF-V1"
    )
    assert handoff["contract_version"] == "1.0.0"
    assert handoff["creation_states"] == [
        "TIMING_QUALIFIED",
        "TIMING_FAILED",
        "TIMING_EXPIRED",
        "TIMING_UNAVAILABLE",
    ]
    assert handoff["authority"] == "TIMING_EVIDENCE_ONLY"
    assert handoff["timing_evidence_authority"] is True
    assert handoff["mandatory_contents"] == [
        "HANDOFF_IDENTITY",
        "HANDOFF_CONTRACT_IDENTITY_VERSION",
        "WO13_TRADE_PLAN_IDENTITY_INTEGRITY",
        "TIMING_CYCLE_IDENTITY",
        "TIMING_OBSERVATION_IDENTITY",
        "TIMING_TRANSITION_IDENTITY",
        "PRIOR_CURRENT_STATE_AND_CAUSE",
        "DIRECTION_SETUP_ENTRY_REFERENCE",
        "QUALIFICATION_PATH",
        "QUALIFYING_FAILING_5M_EVIDENCE_AND_BOUNDARY",
        "TIMING_LIFECYCLE_TIMESTAMPS",
        "EXTENSION_AND_APPROVED_RESEARCH_REFERENCES",
        "SESSION_CALENDAR_IDENTITY_VERSION",
        "CANONICAL_INSTRUMENT_CONTRACT_ROLL_IDENTITY",
        "WO15_POLICY_IDENTITY_VERSION",
        "OPTIONAL_WO14_RISK_REFERENCE",
        "CREATION_TIMESTAMP_PROVENANCE_INTEGRITY",
        "SUPERSESSION_LINEAGE",
    ]
    for key in (
        "sponsor_decision_authority",
        "paper_authority",
        "live_authority",
        "ignore_authority",
        "position_authority",
        "broker_authority",
    ):
        assert handoff[key] == "NONE"
    product = PRODUCT.read_text(encoding="utf-8")
    assert "A later FAILED/EXPIRED handoff references rather than mutates" in product
    assert "latest current non-superseded handoff" in product


def test_family_authority_and_natgas_hold_are_exact() -> None:
    families = _policy()["market_family_authority"]
    assert families["EQUITY"] == "STOCK_LOCAL_COMPLETED_5M"
    assert families["INDEX"] == "UNDERLYING_INDEX_COMPLETED_5M"
    assert families["MCX"] == "EXACT_ACTIVE_FUTURES_CONTRACT_COMPLETED_5M"
    assert families["option_premium_substitution"] == "PROHIBITED"
    assert families["reference_market_substitution"] == "PROHIBITED"
    assert families["NATGAS"] == "STRUCTURALLY_SUPPORTED_OPERATIONALLY_HELD"


def test_trust_failure_is_unavailable_not_failed() -> None:
    policy = _policy()
    assert policy["trust_failure_consequence"] == "TIMING_UNAVAILABLE"
    for blocker in (
        "SUPERSEDED_WO13_PLAN",
        "DIRECTION_MISMATCH",
        "ACTIVE_CONTRACT_MISMATCH",
        "ROLL_LINEAGE_MISMATCH",
        "INCOMPLETE_CANDLE_AS_COMPLETED",
        "SESSION_CALENDAR_MISMATCH",
        "INTEGRITY_FAILURE",
    ):
        assert blocker in policy["trust_failures"]


def test_deferred_policy_has_no_invented_threshold_or_indicator_authority() -> None:
    policy = _policy()
    for deferred in (
        "EXTENSION_CHASE_THRESHOLD",
        "EXTENSION_SEVERITY_BANDS",
        "ATR_VETO_THRESHOLD",
        "VOLUME_CONFIRMATION_THRESHOLD",
        "RSI_TIMING_CONSEQUENCE",
        "RAILWAY_SMA_TIMING_CONSEQUENCE",
        "N_BAR_EXPIRY",
        "TIME_BASED_EXPIRY",
        "EXTENSION_ALERT_THRESHOLD",
        "NEW_INDICATOR_GATES",
    ):
        assert deferred in policy["unresolved_policy"]
    for prohibited in (
        "NEW_INDICATOR_STACK",
        "AI_TIMING_SCORE",
        "ATR_VETO",
        "RR_TIMING_GATE",
        "BROKER_ACTION",
    ):
        assert prohibited in policy["prohibited"]


def test_governance_indexes_ownership_roadmap_and_reuse_are_current() -> None:
    paths = (
        ARCHITECTURE / "adr" / "README.md",
        ARCHITECTURE / "KNOWLEDGE_BASE.md",
        ARCHITECTURE / "platform" / "ARCHITECTURE_INDEX.md",
        ARCHITECTURE / "products" / "intraday" / "README.md",
        ARCHITECTURE / "products" / "intraday" / "RESPONSIBILITIES.md",
        ARCHITECTURE / "products" / "intraday"
        / "KRONOS-INTRADAY-CONTRACT-STATE-OWNERSHIP-REGISTRY.md",
        ARCHITECTURE / "products" / "intraday"
        / "KRONOS-INTRADAY-DEFERRED-DECISION-REGISTER.md",
        ARCHITECTURE / "products" / "intraday"
        / "KRONOS-INTRADAY-V1-PROGRAMME-ROADMAP.md",
        ARCHITECTURE / "products" / "intraday"
        / "KRONOS-INTRADAY-ENGINEERING-METHODOLOGY-ARCHITECTURE-RECORD-V0.1.md",
    )
    for path in paths:
        assert "WO-15" in path.read_text(encoding="utf-8"), path
    adr = ADR.read_text(encoding="utf-8")
    assert "Reuse as principles" in adr
    assert "Reuse through Intraday adapters" in adr
    assert "Do not copy Swing timeframe grammar" in adr


def test_changed_architecture_links_resolve() -> None:
    markdown_link = re.compile(r"\[[^]]+\]\(([^)]+)\)")
    changed = (
        ADR,
        PRODUCT,
        ARCHITECTURE / "adr" / "README.md",
        ARCHITECTURE / "KNOWLEDGE_BASE.md",
        ARCHITECTURE / "platform" / "ARCHITECTURE_INDEX.md",
        ARCHITECTURE / "products" / "intraday" / "README.md",
        ARCHITECTURE / "products" / "intraday"
        / "KRONOS-INTRADAY-V1-PROGRAMME-ROADMAP.md",
        ARCHITECTURE / "products" / "intraday"
        / "KRONOS-INTRADAY-ENGINEERING-METHODOLOGY-ARCHITECTURE-RECORD-V0.1.md",
    )
    for path in changed:
        for target in markdown_link.findall(path.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("#"):
                continue
            resolved = (path.parent / target.split("#", 1)[0]).resolve()
            assert resolved.exists(), f"{path}: missing {target}"
