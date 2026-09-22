"""Dormant KR-370 Swing V2 analytical promotion engine.

WO-09B: a closed, additive successor. No route or downstream owner imports it.
The V1 classifier and persistence remain untouched. Currentness is established
by the caller's governed source owner at explicit evaluation and rechecked on
current reads; this module creates no new authoritative current pointer.
"""

from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import stat
from threading import RLock
from typing import Callable

from kronos.swing.run_identity import is_swing_analysis_run_id
from kronos.swing.universe import SWING_PHASE1_UNIVERSE, SwingUniverseAssetClass
from kronos.swing.v1.analytical_promotion import (
    Kr370CriterionIdentity, Kr370CriterionResult, Kr370Watchability,
    _binding_failure, _hard_gate, _k1, _k2, _k3, _k4, _k5,
    _k2_condition, _native_requirement_sha256,
)
from kronos.swing.v1.extension import CompletedOneHourExtensionFact, extension_integrity_sha256
from kronos.swing.v1.extension import EXTENSION_POLICY_IDENTITY, EXTENSION_POLICY_VERSION
from kronos.swing.v1.mcx_native_visual_contract import (
    COMPARISON_EVIDENCE, MCX_REFERENCE_MAPPINGS, NATIVE_EVIDENCE_V2,
    NATIVE_TIMEFRAMES, REFERENCE_EVIDENCE_V2, SUCCESSOR_VERSION,
    NATIVE_QUESTIONS_V2, REFERENCE_QUESTIONS_V2,
    NATIVE_ANSWER_V2, REFERENCE_ANSWER_V2,
    parse_mcx_json,
)
from kronos.swing.v1.mtf_facts import FactualTimeframe, SameRunMtfFactSnapshot
from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.native_discovery import NativeProductPath
from kronos.swing.v1.native_review import NativeReviewRequirement
from kronos.swing.v1.path_clearance import (
    OneHourPathClearanceFact, path_clearance_integrity_sha256,
    PATH_CLEARANCE_POLICY_IDENTITY, PATH_CLEARANCE_POLICY_VERSION,
)
from kronos.swing.v1.reference_facts import SwingReferenceChartTimeframe, machine_fact_integrity_sha256
from kronos.swing.v1.review_evidence_store import ReviewAcceptanceCommit
from kronos.swing.v1.relative_context import (
    DirectionalRelativeContext, RELATIVE_CONTEXT_BENCHMARK,
    RELATIVE_CONTEXT_SCHEMA, RelativeContextRecord, RelativeContextRun,
    RelativeContextReason,
    directional_relative_context, relative_context_record_sha256,
    relative_context_run_sha256,
)
from kronos.swing.v1.review_evidence_binding import (
    NseReviewRequestMapping, ReviewAcceptanceReceipt, canonical, strict_json,
    RECEIPT_SCHEMA, RECEIPT_SCHEMA_V2,
)
from kronos.swing.v1.review_evidence_store import ReviewEvidenceStore
from kronos.swing.v1.visual_evidence_v3 import (
    VisualEvidenceV3Response, visual_evidence_v3_response_from_dict,
    VISUAL_QUESTION_SET_V3_ID, VISUAL_EVIDENCE_V3_SCHEMA,
    VISUAL_EVIDENCE_V3_SUCCESSOR_SCHEMA,
)
from kronos.validation.kr370 import Kr370CriterionState


CONTRACT = "KRONOS-KR-370-SWING-ANALYTICAL-PROMOTION-V2"
VERSION = "2"
POLICY = "KR-370-SWING-WO09-PROMOTION-POLICY-V2"
SCHEMA = "KRONOS-SWING-KR370-ANALYTICAL-PROMOTION-RECORD-V2"
DEFAULT_ROOT = (Path.home() / "Library" / "Application Support" / "KRONOS" /
                "evidence" / "swing-v1" / "kr370-analytical-promotion-v2")

ROOT_FIELDS = frozenset({
    "schema", "contract_identity", "contract_version", "policy_identity",
    "policy_version", "owner_identity", "state_family_identity", "product",
    "authority", "record_identity", "input_sha256", "source", "criteria",
    "evaluation_disposition", "reason_codes", "satisfied_count",
    "missing_count", "promotion_state", "sole_missing_criterion",
    "confirmation", "confirmation_pending", "promotion_condition",
    "watchability", "freshness", "created_at", "authority_flags",
    "integrity_sha256",
})
SOURCE_FIELDS = frozenset({
    "native_run_identity", "committed_run_manifest_identity", "market",
    "asset_class", "canonical_instrument", "direction",
    "native_opportunity_identity", "native_assessment_sha256",
    "native_requirement_sha256", "analysis_boundary",
    "observation_boundaries", "machine_snapshot_identity",
    "machine_fact_bindings", "e01_fact_integrity_sha256",
    "e03_fact_integrity_sha256", "acceptance",
})
ACCEPTANCE_FIELDS = frozenset({
    "commit_identity", "receipt_identity", "receipt_schema", "receipt_version",
    "receipt_integrity_sha256", "request_publication_identity",
    "review_cycle_identity", "review_pack_identity", "review_pack_sha256",
    "request_bindings", "answer_identity", "answer_pdf_sha256",
    "visual_contracts", "visual_bindings",
})
REQUEST_FIELDS = frozenset({"role", "request_identity", "request_sha256",
                            "review_pack_identity", "review_pack_sha256"})
CONTRACT_FIELDS = frozenset({"role", "question_contract_identity",
    "question_contract_version", "answer_contract_identity", "answer_contract_version",
    "structured_evidence_schema", "structured_evidence_version"})
VISUAL_FIELDS = frozenset({"role", "timeframe", "subject_identity", "reference_market",
    "reference_symbol", "chart_revision_identity", "chart_sha256",
    "structured_evidence_schema", "structured_evidence_version",
    "structured_evidence_sha256", "evidence_integrity_sha256"})
CRITERION_FIELDS = frozenset({"identity", "state", "reason_code", "evidence_sha256"})
CONFIRMATION_FIELDS = frozenset({"kind", "state", "reason_codes", "nse_binding", "mcx_binding"})
BINDING_FIELDS = frozenset({"validation_state", "observed_payload_sha256", "payload"})
NSE_FIELDS = frozenset({"schema", "policy_identity", "policy_version",
    "context_run_integrity_sha256", "context_record_integrity_sha256",
    "run_identity", "canonical_instrument", "benchmark_identity", "horizons"})
NSE_HORIZON_FIELDS = frozenset({"timeframe", "common_start_boundary",
    "latest_common_completed_boundary", "stock_source_identity", "benchmark_source_identity",
    "stock_provenance", "benchmark_provenance", "relative_state", "directional_context",
    "reason_codes"})
MCX_FIELDS = frozenset({"registered_mapping", "native_candidate_reference",
    "pair_binding_sha256", "native_request_identity", "native_request_sha256",
    "reference_request_identity", "reference_request_sha256", "comparison_schema",
    "comparison_version", "comparison_artifact_sha256", "comparison_integrity_sha256",
    "m1", "m2", "m3"})
MCX_MAPPING_FIELDS = frozenset({"native_family", "reference_name", "reference_market",
                                "reference_symbol"})
MCX_M1_FIELDS = frozenset({"question_id", "observation_status", "mapping_state", "coverage_state"})
MCX_M2_FIELDS = frozenset({"question_id", "observation_status", "by_timeframe"})
MCX_M2_ROW_FIELDS = frozenset({"timeframe", "relationship"})
MCX_M3_FIELDS = frozenset({"question_id", "observation_status",
    "relationship_to_native_direction", "affected_timeframes", "limitations"})
CONDITION_FIELDS = frozenset({"criterion_identity", "timeframe", "comparator", "price",
                              "summary", "source_evidence_ids", "observation_boundary"})
FLAGS = frozenset({"geometry", "risk", "sponsor_decision", "entry_timing", "position",
                   "fill", "execution", "broker", "alert", "kr390_current_input",
                   "kr400_current_alert_source"})

class Disposition(StrEnum):
    EVALUATED = "EVALUATED"
    NOT_EVALUABLE = "NOT_EVALUABLE"
    HARD_GATED = "HARD_GATED"

class Promotion(StrEnum):
    NO_FOCUS = "NO_FOCUS"
    NEAR_READY = "NEAR_READY"
    BUY_READY = "BUY_READY"
    SELL_READY = "SELL_READY"
    BUY_NOW = "BUY_NOW"
    SELL_NOW = "SELL_NOW"

class ConfirmationState(StrEnum):
    ESTABLISHED = "ESTABLISHED"
    WITHHELD = "WITHHELD"
    NOT_REQUIRED_BY_ASSET_CLASS = "NOT_REQUIRED_BY_ASSET_CLASS"

GATE_REASONS = frozenset({
    "NATIVE_THESIS_INVALIDATED_OR_STRUCTURAL_FAILURE", "NSE_WEEKLY_OPPOSING",
    "NSE_WEEKLY_UNAVAILABLE_MANDATORY", "NATIVE_MANDATORY_VISUAL_EVIDENCE_INVALID",
    "NATIVE_1H_MESSY_CHOPPY", "AFFIRMATIVE_GOVERNED_DIRECTIONAL_CONFLICT",
})
K_REASON = frozenset({
    "NATIVE_1H_DIRECTIONALLY_PROGRESSING", "NATIVE_1H_STALLING", "NATIVE_1H_NEUTRAL",
    "NATIVE_1H_DETERIORATING", "NATIVE_1H_STRUCTURAL_FAILURE",
    "NATIVE_1H_PROGRESSION_UNAVAILABLE", "COMPLETED_1H_CLOSE_ACCEPTED_BEYOND_CPR",
    "COMPLETED_1H_CLOSE_NOT_ACCEPTED_BEYOND_CPR", "GOVERNED_1H_CPR_UNAVAILABLE",
    "E01_PATH_CLEAR", "E01_IMMEDIATE_PATH_BLOCKED", "E01_UNAVAILABLE",
    "CLEAN_DIRECTIONAL", "HEALTHY_CONSOLIDATION", "HEALTHY_COMPRESSION",
    "ORDERLY_PULLBACK", "MESSY_CHOPPY", "CONFLICTING",
    "NATIVE_1H_SETUP_QUALITY_UNAVAILABLE", "NATIVE_1H_SETUP_QUALITY_INVALID",
    "E03_NOT_MATERIALLY_EXTENDED", "E03_MATERIALLY_EXTENDED", "E03_UNAVAILABLE",
})
CRITERION_REASON_STATES = (
    {"NATIVE_1H_DIRECTIONALLY_PROGRESSING": "SATISFIED",
     "NATIVE_1H_STALLING": "UNSATISFIED", "NATIVE_1H_NEUTRAL": "UNSATISFIED",
     "NATIVE_1H_DETERIORATING": "UNSATISFIED",
     "NATIVE_1H_STRUCTURAL_FAILURE": "UNSATISFIED",
     "NATIVE_1H_PROGRESSION_UNAVAILABLE": "UNAVAILABLE"},
    {"COMPLETED_1H_CLOSE_ACCEPTED_BEYOND_CPR": "SATISFIED",
     "COMPLETED_1H_CLOSE_NOT_ACCEPTED_BEYOND_CPR": "UNSATISFIED",
     "GOVERNED_1H_CPR_UNAVAILABLE": "UNAVAILABLE"},
    {"E01_PATH_CLEAR": "SATISFIED", "E01_IMMEDIATE_PATH_BLOCKED": "UNSATISFIED",
     "E01_UNAVAILABLE": "UNAVAILABLE"},
    {"CLEAN_DIRECTIONAL": "SATISFIED", "HEALTHY_CONSOLIDATION": "SATISFIED",
     "HEALTHY_COMPRESSION": "SATISFIED", "ORDERLY_PULLBACK": "SATISFIED",
     "MESSY_CHOPPY": "UNSATISFIED", "CONFLICTING": "UNSATISFIED",
     "NATIVE_1H_SETUP_QUALITY_UNAVAILABLE": "UNAVAILABLE",
     "NATIVE_1H_SETUP_QUALITY_INVALID": "UNAVAILABLE"},
    {"E03_NOT_MATERIALLY_EXTENDED": "SATISFIED",
     "E03_MATERIALLY_EXTENDED": "UNSATISFIED", "E03_UNAVAILABLE": "UNAVAILABLE"},
)
NSE_REASONS = frozenset({"NSE_BOTH_HORIZONS_SUPPORTIVE", "NOT_REQUIRED_BY_ASSET_CLASS",
    "NSE_CONTEXT_MISSING", "NSE_CONTEXT_INVALID", "NSE_CONTEXT_STALE",
    "NSE_CONTEXT_BINDING_MISMATCH", "NSE_1D_NEUTRAL", "NSE_4H_NEUTRAL",
    "NSE_1D_CONTRADICTORY", "NSE_4H_CONTRADICTORY", "NSE_1D_UNAVAILABLE",
    "NSE_4H_UNAVAILABLE", "NSE_CONTEXT_NOT_APPLICABLE"})
LIMITATIONS = ("DIFFERENT_SESSIONS", "INCOMPLETE_BAR", "EXPIRY_OR_ROLL",
    "CONTINUOUS_BACK_ADJUSTMENT_UNKNOWN", "CONTRACT_IDENTITY_UNCLEAR",
    "CURRENCY_OR_BASIS_DIFFERENCE", "MISSING_EVIDENCE", "OTHER_VISIBLE_LIMITATION")
WITHHOLDING_LIMITATIONS = frozenset(LIMITATIONS) - {
    "DIFFERENT_SESSIONS", "CURRENCY_OR_BASIS_DIFFERENCE"}
MCX_REASONS = frozenset({"MCX_REFERENCE_CONFIRMED", "MCX_REFERENCE_MISSING",
    "MCX_REFERENCE_INVALID", "MCX_REFERENCE_STALE", "MCX_REFERENCE_BINDING_MISMATCH",
    "MCX_MAPPING_NOT_MATCHED", "MCX_COVERAGE_NOT_SUFFICIENT", "MCX_1D_NOT_AGREES",
    "MCX_4H_NOT_AGREES", "MCX_1H_CONFLICTS", "MCX_1H_NOT_COMPARABLE",
    "MCX_M3_CHALLENGES", "MCX_M3_MIXED", "MCX_M3_NOT_ESTABLISHED",
    "MCX_COMPARISON_UNAVAILABLE", *("MCX_LIMITATION_" + x for x in WITHHOLDING_LIMITATIONS)})
SOURCE_FAILURES = frozenset({"V2_SCHEMA_INVALID", "V2_VERSION_UNSUPPORTED",
    "V2_VERSION_MIXED", "V2_INTEGRITY_INVALID", "V2_SOURCE_MISSING",
    "V2_SOURCE_INVALID", "V2_SOURCE_BINDING_MISMATCH", "V2_SOURCE_STALE",
    "V2_PUBLICATION_CHANGED", "V2_IMMUTABLE_CONFLICT", "V2_OUTPUT_AMBIGUOUS",
    "V2_STORAGE_UNAVAILABLE"})

SCHEMA_SEAL = {
    "contract": CONTRACT, "contract_version": VERSION, "policy": POLICY,
    "policy_version": VERSION, "schema": SCHEMA,
    "root_fields": sorted(ROOT_FIELDS), "source_fields": sorted(SOURCE_FIELDS),
    "acceptance_fields": sorted(ACCEPTANCE_FIELDS), "request_fields": sorted(REQUEST_FIELDS),
    "visual_contract_fields": sorted(CONTRACT_FIELDS),
    "visual_fields": sorted(VISUAL_FIELDS), "criterion_fields": sorted(CRITERION_FIELDS),
    "confirmation_fields": sorted(CONFIRMATION_FIELDS), "nse_fields": sorted(NSE_FIELDS),
    "nse_horizon_fields": sorted(NSE_HORIZON_FIELDS), "mcx_fields": sorted(MCX_FIELDS),
    "confirmation_binding_fields": sorted(BINDING_FIELDS),
    "mcx_mapping_fields": sorted(MCX_MAPPING_FIELDS),
    "mcx_m1_fields": sorted(MCX_M1_FIELDS), "mcx_m2_fields": sorted(MCX_M2_FIELDS),
    "mcx_m2_row_fields": sorted(MCX_M2_ROW_FIELDS),
    "mcx_m3_fields": sorted(MCX_M3_FIELDS), "condition_fields": sorted(CONDITION_FIELDS),
    "authority_flags": sorted(FLAGS), "gate_reasons": sorted(GATE_REASONS),
    "criterion_reasons": sorted(K_REASON), "nse_reasons": sorted(NSE_REASONS),
    "criterion_reason_states": CRITERION_REASON_STATES,
    "mcx_reasons": sorted(MCX_REASONS), "source_failures": sorted(SOURCE_FAILURES),
    "dispositions": [x.value for x in Disposition],
    "promotions": [x.value for x in Promotion],
    "confirmation_states": [x.value for x in ConfirmationState],
    "persistence": "swing-v1/kr370-analytical-promotion-v2/<run>/<input_sha256>.json",
    "current_pointer": "existing WO-05 publication and WO-07 acceptance/consumer owners only",
}
SCHEMA_SEAL_SHA256 = sha256(canonical(SCHEMA_SEAL)).hexdigest()


def _require(condition: bool, code: str = "V2_SCHEMA_INVALID") -> None:
    if not condition:
        raise ValueError(code)


def _closed(value: object, fields: frozenset[str]) -> dict:
    _require(type(value) is dict and set(value) == fields)
    return value


def _digest(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _identity(value: object) -> bool:
    return type(value) is str and bool(value.strip()) and len(value) <= 512


def _timestamp(value: object) -> bool:
    if type(value) is not str or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z", value):
        return False
    try:
        return datetime.fromisoformat(value).tzinfo is not None
    except ValueError:
        return False


def _time(value: datetime) -> str:
    _require(type(value) is datetime and value.tzinfo is not None and value.utcoffset() is not None)
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _enum(value: object, choices: object) -> bool:
    return type(value) is str and value in choices


def _ordered_codes(value: object, choices: frozenset[str], *, nonempty: bool = False) -> bool:
    return (type(value) is list and (not nonempty or bool(value)) and
            value == sorted(set(value)) and all(_enum(item, choices) for item in value))


def _validate_source(value: object) -> dict:
    source = _closed(value, SOURCE_FIELDS)
    _require(is_swing_analysis_run_id(source["native_run_identity"]))
    _require(_digest(source["committed_run_manifest_identity"]))
    _require(source["market"] in {"NSE", "MCX"} and source["asset_class"] in
             ({"NSE_EQUITY", "NSE_INDEX"} if source["market"] == "NSE" else {"MCX_COMMODITY"}))
    _require(_identity(source["canonical_instrument"]) and source["direction"] in {"LONG", "SHORT"})
    _require(_identity(source["native_opportunity_identity"]))
    _require(_digest(source["native_assessment_sha256"]) and _digest(source["native_requirement_sha256"]))
    _require(_timestamp(source["analysis_boundary"]) and _identity(source["machine_snapshot_identity"]))
    for key in ("e01_fact_integrity_sha256", "e03_fact_integrity_sha256"):
        _require(source[key] is None or _digest(source[key]))
    for name, field in (("observation_boundaries", "boundary"),
                        ("machine_fact_bindings", "integrity_sha256")):
        items = source[name]
        _require(type(items) is list and bool(items) and len(items) == 4)
        _require([x.get("timeframe") for x in items if type(x) is dict] == ["1W", "1D", "4H", "1H"])
        for item in items:
            _closed(item, frozenset({"timeframe", field}))
            _require(_timestamp(item[field]) if field == "boundary" else _digest(item[field]))
    acceptance = _closed(source["acceptance"], ACCEPTANCE_FIELDS)
    for key in ("commit_identity", "receipt_identity", "receipt_schema", "receipt_version",
                "request_publication_identity", "review_cycle_identity", "review_pack_identity", "answer_identity"):
        _require(_identity(acceptance[key]))
    for key in ("receipt_integrity_sha256", "review_pack_sha256", "answer_pdf_sha256"):
        _require(_digest(acceptance[key]))
    _require((acceptance["receipt_schema"], acceptance["receipt_version"]) in
             ({(RECEIPT_SCHEMA, "1.0"), (RECEIPT_SCHEMA_V2, "2.0")}
              if source["market"] == "NSE" else {(RECEIPT_SCHEMA_V2, "2.0")}),
             "V2_VERSION_MIXED")
    roles = ["NATIVE_NSE"] if source["market"] == "NSE" else ["NATIVE_MCX", "SUPPORTING_REFERENCE"]
    requests = acceptance["request_bindings"]
    _require(type(requests) is list and len(requests) == len(roles))
    for item, role in zip(requests, roles, strict=True):
        _closed(item, REQUEST_FIELDS)
        _require(item["role"] == role and _identity(item["request_identity"]) and
                 _identity(item["review_pack_identity"]) and _digest(item["request_sha256"]) and
                 _digest(item["review_pack_sha256"]))
    contracts = acceptance["visual_contracts"]
    _require(type(contracts) is list and len(contracts) == len(roles))
    for item, role in zip(contracts, roles, strict=True):
        _closed(item, CONTRACT_FIELDS)
        _require(item["role"] == role and all(_identity(v) for v in item.values()))
        if role == "NATIVE_NSE":
            version = item["question_contract_version"]
            _require(version in {"3.1", "3.2"} and
                     item["question_contract_identity"] == VISUAL_QUESTION_SET_V3_ID and
                     item["structured_evidence_schema"] ==
                       (VISUAL_EVIDENCE_V3_SCHEMA if version == "3.1" else
                        VISUAL_EVIDENCE_V3_SUCCESSOR_SCHEMA) and
                     item["structured_evidence_version"] == version and
                     item["answer_contract_version"] == acceptance["receipt_version"],
                     "V2_VERSION_MIXED")
        else:
            _require((item["question_contract_identity"],
                      item["answer_contract_identity"], item["structured_evidence_schema"]) ==
                     ((NATIVE_QUESTIONS_V2, NATIVE_ANSWER_V2, NATIVE_EVIDENCE_V2)
                      if role == "NATIVE_MCX" else
                      (REFERENCE_QUESTIONS_V2, REFERENCE_ANSWER_V2, REFERENCE_EVIDENCE_V2)) and
                     item["question_contract_version"] == SUCCESSOR_VERSION and
                     item["answer_contract_version"] == SUCCESSOR_VERSION and
                     item["structured_evidence_version"] == SUCCESSOR_VERSION,
                     "V2_VERSION_MIXED")
    visuals = acceptance["visual_bindings"]
    expected = [(role, tf) for role in roles for tf in
                (["1W", "1D", "4H", "1H"] if role == "NATIVE_NSE" else ["1D", "4H", "1H"])]
    _require(type(visuals) is list and len(visuals) == len(expected))
    for item, (role, tf) in zip(visuals, expected, strict=True):
        _closed(item, VISUAL_FIELDS)
        _require(item["role"] == role and item["timeframe"] == tf)
        _require((item["reference_market"] is None and item["reference_symbol"] is None)
                 if role != "SUPPORTING_REFERENCE" else
                 (_identity(item["reference_market"]) and _identity(item["reference_symbol"])))
        _require(all(_identity(item[key]) for key in ("subject_identity", "chart_revision_identity",
            "structured_evidence_schema", "structured_evidence_version")))
        _require(all(_digest(item[key]) for key in ("chart_sha256", "structured_evidence_sha256",
            "evidence_integrity_sha256")))
        contract = contracts[roles.index(role)]
        _require(item["structured_evidence_schema"] == contract["structured_evidence_schema"] and
                 item["structured_evidence_version"] == contract["structured_evidence_version"],
                 "V2_VERSION_MIXED")
        if role == "SUPPORTING_REFERENCE":
            mapping = MCX_REFERENCE_MAPPINGS.get(source["canonical_instrument"])
            _require(mapping is not None and (item["reference_market"], item["reference_symbol"]) ==
                     (mapping[1], mapping[2]), "V2_SOURCE_BINDING_MISMATCH")
    return source


def _validate_nse(binding: dict, source: dict) -> tuple[str, list[str]]:
    payload = _closed(binding["payload"], NSE_FIELDS)
    _require(payload["schema"] == RELATIVE_CONTEXT_SCHEMA and
             payload["policy_identity"] == "SWING-PHASE1-V1-RELATIVE-CONTEXT-POLICY" and
             payload["policy_version"] == "1")
    _require(_digest(payload["context_run_integrity_sha256"]) and
             _digest(payload["context_record_integrity_sha256"]))
    _require(payload["run_identity"] == source["native_run_identity"] and
             payload["canonical_instrument"] == source["canonical_instrument"] and
             payload["benchmark_identity"] == RELATIVE_CONTEXT_BENCHMARK)
    horizons = payload["horizons"]
    _require(type(horizons) is list and len(horizons) == 2)
    reasons = []
    for item, tf in zip(horizons, ("1D", "4H"), strict=True):
        _closed(item, NSE_HORIZON_FIELDS)
        _require(item["timeframe"] == tf and item["relative_state"] in
                 {"OUTPERFORMING", "UNDERPERFORMING", "EQUAL", "UNAVAILABLE", "NOT_APPLICABLE"})
        directional = ({"OUTPERFORMING": "SUPPORTIVE_CONTEXT", "UNDERPERFORMING": "CONTRADICTORY_CONTEXT"}
                       if source["direction"] == "LONG" else
                       {"UNDERPERFORMING": "SUPPORTIVE_CONTEXT", "OUTPERFORMING": "CONTRADICTORY_CONTEXT"})
        directional.update(EQUAL="NEUTRAL_CONTEXT", UNAVAILABLE="UNAVAILABLE", NOT_APPLICABLE="NOT_APPLICABLE")
        _require(item["directional_context"] == directional[item["relative_state"]])
        available = item["relative_state"] in {"OUTPERFORMING", "UNDERPERFORMING", "EQUAL"}
        for key in ("common_start_boundary", "latest_common_completed_boundary"):
            _require(_timestamp(item[key]) if available else item[key] is None)
        for key in ("stock_source_identity", "benchmark_source_identity"):
            _require(_identity(item[key]) if available else item[key] is None)
        for key in ("stock_provenance", "benchmark_provenance"):
            _require(type(item[key]) is list and
                     (bool(item[key]) and all(_identity(x) for x in item[key]) if available else item[key] == []))
        _require(type(item["reason_codes"]) is list and
                 (item["reason_codes"] == [] if available else bool(item["reason_codes"])))
        _require(all(_enum(x, {r.value for r in RelativeContextReason}) for x in item["reason_codes"]))
        if item["directional_context"] != "SUPPORTIVE_CONTEXT":
            kind = {"NEUTRAL_CONTEXT": "NEUTRAL", "CONTRADICTORY_CONTEXT": "CONTRADICTORY",
                    "UNAVAILABLE": "UNAVAILABLE", "NOT_APPLICABLE": "UNAVAILABLE"}[item["directional_context"]]
            reasons.append(f"NSE_{tf}_{kind}" if kind != "UNAVAILABLE" or
                           item["directional_context"] != "NOT_APPLICABLE" else "NSE_CONTEXT_NOT_APPLICABLE")
    return (ConfirmationState.ESTABLISHED.value if not reasons else ConfirmationState.WITHHELD.value,
            ["NSE_BOTH_HORIZONS_SUPPORTIVE"] if not reasons else sorted(set(reasons)))


def _validate_mcx(binding: dict, source: dict) -> tuple[str, list[str]]:
    p = _closed(binding["payload"], MCX_FIELDS)
    mapping = _closed(p["registered_mapping"], MCX_MAPPING_FIELDS)
    expected = MCX_REFERENCE_MAPPINGS.get(source["canonical_instrument"])
    _require(expected is not None and mapping == dict(native_family=source["canonical_instrument"],
              reference_name=expected[0], reference_market=expected[1], reference_symbol=expected[2]))
    _require(p["native_candidate_reference"] == source["native_requirement_sha256"])
    _require(p["comparison_schema"] == COMPARISON_EVIDENCE and p["comparison_version"] == "1.0")
    for key in ("pair_binding_sha256", "native_request_sha256", "reference_request_sha256",
                "comparison_artifact_sha256", "comparison_integrity_sha256"):
        _require(_digest(p[key]))
    for key in ("native_request_identity", "reference_request_identity"):
        _require(_identity(p[key]))
    reqs = source["acceptance"]["request_bindings"]
    _require((p["native_request_identity"], p["native_request_sha256"]) ==
             (reqs[0]["request_identity"], reqs[0]["request_sha256"]) and
             (p["reference_request_identity"], p["reference_request_sha256"]) ==
             (reqs[1]["request_identity"], reqs[1]["request_sha256"]))
    m1, m2, m3 = (_closed(p[k], f) for k, f in (("m1", MCX_M1_FIELDS),
        ("m2", MCX_M2_FIELDS), ("m3", MCX_M3_FIELDS)))
    _require((m1["question_id"], m2["question_id"], m3["question_id"]) ==
             ("M1_COMPARISON_VALIDITY", "M2_STRUCTURAL_AGREEMENT", "M3_DIVERGENCE_LIMITATIONS"))
    statuses = (m1["observation_status"], m2["observation_status"], m3["observation_status"])
    _require(all(x in {"OBSERVED", "PARTIAL", "UNAVAILABLE"} for x in statuses))
    _require(m1["mapping_state"] in {"MATCHED", "UNDETERMINED"} and
             m1["coverage_state"] in {"SUFFICIENT", "PARTIAL", "INSUFFICIENT"})
    rows = m2["by_timeframe"]
    _require(type(rows) is list and len(rows) == 3)
    for row, tf in zip(rows, NATIVE_TIMEFRAMES, strict=True):
        _closed(row, MCX_M2_ROW_FIELDS)
        _require(row["timeframe"] == tf and row["relationship"] in
                 {"AGREES", "PARTLY_AGREES", "CONFLICTS", "NOT_COMPARABLE"})
    _require(m3["relationship_to_native_direction"] in
             {"SUPPORTS", "CHALLENGES", "MIXED", "NO_MATERIAL_DIVERGENCE", "NOT_ESTABLISHED"})
    for name, order in (("affected_timeframes", NATIVE_TIMEFRAMES), ("limitations", LIMITATIONS)):
        _require(type(m3[name]) is list and m3[name] == [x for x in order if x in m3[name]])
    reasons = []
    if "UNAVAILABLE" in statuses:
        reasons.append("MCX_COMPARISON_UNAVAILABLE")
    if m1["mapping_state"] != "MATCHED": reasons.append("MCX_MAPPING_NOT_MATCHED")
    if m1["coverage_state"] != "SUFFICIENT": reasons.append("MCX_COVERAGE_NOT_SUFFICIENT")
    for row in rows[:2]:
        if row["relationship"] != "AGREES": reasons.append(f"MCX_{row['timeframe']}_NOT_AGREES")
    if rows[2]["relationship"] in {"CONFLICTS", "NOT_COMPARABLE"}:
        reasons.append("MCX_1H_" + rows[2]["relationship"])
    m3v = m3["relationship_to_native_direction"]
    if m3v not in {"SUPPORTS", "NO_MATERIAL_DIVERGENCE"}:
        reasons.append("MCX_M3_" + m3v)
    reasons.extend("MCX_LIMITATION_" + x for x in m3["limitations"] if x in WITHHOLDING_LIMITATIONS)
    return (ConfirmationState.ESTABLISHED.value if not reasons else ConfirmationState.WITHHELD.value,
            ["MCX_REFERENCE_CONFIRMED"] if not reasons else sorted(set(reasons)))


def _validate_confirmation(value: object, source: dict) -> dict:
    conf = _closed(value, CONFIRMATION_FIELDS)
    asset = source["asset_class"]
    kind = {"NSE_EQUITY": "NSE_NIFTY", "NSE_INDEX": "ASSET_CLASS_EXEMPT",
            "MCX_COMMODITY": "MCX_GLOBAL_REFERENCE"}[asset]
    _require(conf["kind"] == kind)
    if asset == "NSE_INDEX":
        _require(conf["nse_binding"] is None and conf["mcx_binding"] is None and
                 conf["state"] == ConfirmationState.NOT_REQUIRED_BY_ASSET_CLASS.value and
                 conf["reason_codes"] == ["NOT_REQUIRED_BY_ASSET_CLASS"])
        return conf
    key = "nse_binding" if asset == "NSE_EQUITY" else "mcx_binding"
    other = "mcx_binding" if key == "nse_binding" else "nse_binding"
    _require(conf[other] is None)
    binding = _closed(conf[key], BINDING_FIELDS)
    _require(binding["validation_state"] in {"VALID", "MISSING", "INVALID", "STALE", "MISMATCHED"})
    _require(binding["observed_payload_sha256"] is None or _digest(binding["observed_payload_sha256"]))
    if binding["validation_state"] != "VALID":
        _require(binding["payload"] is None)
        reason = ({"MISSING": "NSE_CONTEXT_MISSING", "INVALID": "NSE_CONTEXT_INVALID",
                   "STALE": "NSE_CONTEXT_STALE", "MISMATCHED": "NSE_CONTEXT_BINDING_MISMATCH"}
                  if key == "nse_binding" else
                  {"MISSING": "MCX_REFERENCE_MISSING", "INVALID": "MCX_REFERENCE_INVALID",
                   "STALE": "MCX_REFERENCE_STALE", "MISMATCHED": "MCX_REFERENCE_BINDING_MISMATCH"})[binding["validation_state"]]
        expected_state, expected_reasons = ConfirmationState.WITHHELD.value, [reason]
    else:
        _require(_digest(binding["observed_payload_sha256"]))
        expected_state, expected_reasons = (_validate_nse(binding, source) if key == "nse_binding"
                                            else _validate_mcx(binding, source))
    _require(conf["state"] == expected_state and conf["reason_codes"] == expected_reasons)
    return conf


def _state(direction: str, satisfied: int, confirmation: str) -> str:
    if satisfied <= 2: return Promotion.NO_FOCUS.value
    if satisfied == 3: return Promotion.NEAR_READY.value
    prefix = "BUY" if direction == "LONG" else "SELL"
    if satisfied == 4: return prefix + "_READY"
    return prefix + ("_NOW" if confirmation in
                     {ConfirmationState.ESTABLISHED.value,
                      ConfirmationState.NOT_REQUIRED_BY_ASSET_CLASS.value} else "_READY")


def _validate_record(value: object) -> dict:
    v = _closed(value, ROOT_FIELDS)
    _require((v["schema"], v["contract_identity"], v["contract_version"],
              v["policy_identity"], v["policy_version"], v["owner_identity"],
              v["state_family_identity"], v["product"], v["authority"], v["freshness"]) ==
             (SCHEMA, CONTRACT, VERSION, POLICY, VERSION, "KR-370", "KR370_ANALYTICAL_PROMOTION",
              "SWING", "ANALYTICAL_PROMOTION_ONLY", "EXACT_CURRENT_SAME_RUN"),
             "V2_VERSION_MIXED")
    source = _validate_source(v["source"])
    confirmation = _validate_confirmation(v["confirmation"], source)
    _require(type(v["criteria"]) is list and len(v["criteria"]) == 5)
    states = []
    for criterion, identity, reason_states in zip(v["criteria"], Kr370CriterionIdentity,
                                                   CRITERION_REASON_STATES, strict=True):
        _closed(criterion, CRITERION_FIELDS)
        _require(criterion["identity"] == identity.value and criterion["state"] in
                 {"SATISFIED", "UNSATISFIED", "UNAVAILABLE"})
        _require(_enum(criterion["reason_code"], K_REASON))
        _require(reason_states.get(criterion["reason_code"]) == criterion["state"])
        _require(type(criterion["evidence_sha256"]) is list and
                 criterion["evidence_sha256"] == sorted(set(criterion["evidence_sha256"])) and
                 all(_digest(x) for x in criterion["evidence_sha256"]))
        _require(criterion["evidence_sha256"] or criterion["state"] == "UNAVAILABLE")
        states.append(criterion["state"])
    disposition = v["evaluation_disposition"]
    _require(disposition in {x.value for x in Disposition})
    hard = disposition == Disposition.HARD_GATED.value
    intrinsic_gate = _intrinsic_gate(v["criteria"])
    unavailable = "UNAVAILABLE" in states
    expected_reasons = (["CRITERION_UNAVAILABLE"] if disposition == "NOT_EVALUABLE" else [])
    _require(_ordered_codes(v["reason_codes"], GATE_REASONS | {"CRITERION_UNAVAILABLE"},
                            nonempty=disposition != "EVALUATED"))
    if hard:
        _require(bool(set(v["reason_codes"]) & GATE_REASONS))
        _require(("CRITERION_UNAVAILABLE" in v["reason_codes"]) == unavailable)
        if v["criteria"][0]["reason_code"] == "NATIVE_1H_STRUCTURAL_FAILURE":
            _require("NATIVE_THESIS_INVALIDATED_OR_STRUCTURAL_FAILURE" in v["reason_codes"])
    elif disposition == "NOT_EVALUABLE":
        _require(unavailable and intrinsic_gate is None and v["reason_codes"] == expected_reasons)
    else:
        _require(not unavailable and intrinsic_gate is None and v["reason_codes"] == [])
    count = states.count("SATISFIED")
    if disposition != "EVALUATED":
        _require(v["satisfied_count"] is None and v["missing_count"] is None and
                 v["promotion_state"] is None and v["sole_missing_criterion"] is None and
                 v["promotion_condition"] is None and v["watchability"] == "NOT_APPLICABLE" and
                 v["confirmation_pending"] is False)
    else:
        _require(type(v["satisfied_count"]) is int and v["satisfied_count"] == count and
                 type(v["missing_count"]) is int and v["missing_count"] == 5 - count)
        _require(v["promotion_state"] == _state(source["direction"], count, confirmation["state"]))
        missing = next((x["identity"] for x in v["criteria"] if x["state"] == "UNSATISFIED"), None)
        _require(v["sole_missing_criterion"] == (missing if count == 4 else None))
        _require(v["confirmation_pending"] is (count == 5 and
                 confirmation["state"] == ConfirmationState.WITHHELD.value))
        condition = v["promotion_condition"]
        if condition is not None:
            _closed(condition, CONDITION_FIELDS)
            _require(count == 4 and missing == Kr370CriterionIdentity.K2_CPR_ACCEPTANCE.value and
                     condition["criterion_identity"] == missing and condition["timeframe"] == "1H" and
                     condition["comparator"] == ("BAR_CLOSE_ABOVE" if source["direction"] == "LONG"
                                                  else "BAR_CLOSE_BELOW") and
                     type(condition["price"]) is float and math.isfinite(condition["price"]) and
                     condition["price"] >= 0 and _identity(condition["summary"]) and
                     type(condition["source_evidence_ids"]) is list and bool(condition["source_evidence_ids"]) and
                     all(_identity(x) for x in condition["source_evidence_ids"]) and
                     _timestamp(condition["observation_boundary"]))
        _require(v["watchability"] == ("NOT_APPLICABLE" if count < 4 or v["promotion_state"] in
                {"BUY_NOW", "SELL_NOW"} else "WATCH_AVAILABLE" if condition is not None else
                "NO_AUTOMATED_ALERT_AVAILABLE"))
    flags = _closed(v["authority_flags"], FLAGS)
    _require(all(x is False for x in flags.values()))
    _require(_timestamp(v["created_at"]) and _digest(v["input_sha256"]) and
             _digest(v["integrity_sha256"]))
    input_material = {k: v[k] for k in ("schema", "contract_identity", "contract_version",
        "policy_identity", "policy_version")}
    input_material.update(source=source, confirmation_binding={
        "kind": confirmation["kind"], "nse_binding": confirmation["nse_binding"],
        "mcx_binding": confirmation["mcx_binding"]})
    _require(v["input_sha256"] == sha256(canonical(input_material)).hexdigest(), "V2_INTEGRITY_INVALID")
    unsigned = {k: x for k, x in v.items() if k not in {"record_identity", "integrity_sha256"}}
    _require(v["integrity_sha256"] == sha256(canonical(unsigned)).hexdigest() and
             v["record_identity"] == f"{CONTRACT}:{VERSION}:{v['integrity_sha256']}",
             "V2_INTEGRITY_INVALID")
    return v


@dataclass(frozen=True, slots=True)
class V2PromotionRecord:
    payload: bytes

    def __post_init__(self) -> None:
        _require(type(self.payload) is bytes)
        try:
            value = strict_json(self.payload)
            _validate_record(value)
            _require(canonical(value) == self.payload, "V2_INTEGRITY_INVALID")
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            if isinstance(error, ValueError) and str(error) in SOURCE_FAILURES:
                raise
            raise ValueError("V2_SCHEMA_INVALID") from error

    @property
    def value(self) -> dict:
        return strict_json(self.payload)

    @property
    def identity(self) -> str:
        return self.value["record_identity"]


def classify(criteria: tuple[Kr370CriterionResult, ...], direction: V1Direction,
             confirmation: dict, hard_gate_reason: str | None = None,
             condition: dict | None = None) -> tuple[str, list[str], int | None,
                                                     int | None, str | None, str | None, bool, str]:
    _require(type(criteria) is tuple and tuple(x.identity for x in criteria) ==
             tuple(Kr370CriterionIdentity))
    _require(direction in {V1Direction.LONG, V1Direction.SHORT})
    _require(hard_gate_reason is None or hard_gate_reason in GATE_REASONS)
    serialized = [dict(reason_code=_criterion_reason(x), state=x.state.value)
                  for x in criteria]
    _require(all(mapping.get(item["reason_code"]) == item["state"] for mapping, item in
                 zip(CRITERION_REASON_STATES, serialized, strict=True)))
    intrinsic_gate = _intrinsic_gate(serialized)
    if hard_gate_reason is None:
        hard_gate_reason = intrinsic_gate
    elif serialized[0]["reason_code"] == "NATIVE_1H_STRUCTURAL_FAILURE":
        _require(hard_gate_reason == "NATIVE_THESIS_INVALIDATED_OR_STRUCTURAL_FAILURE")
    unavailable = any(x.state is Kr370CriterionState.UNAVAILABLE for x in criteria)
    if hard_gate_reason is not None:
        reasons = sorted({hard_gate_reason, *( ["CRITERION_UNAVAILABLE"] if unavailable else [] )})
        return "HARD_GATED", reasons, None, None, None, None, False, "NOT_APPLICABLE"
    if unavailable:
        return "NOT_EVALUABLE", ["CRITERION_UNAVAILABLE"], None, None, None, None, False, "NOT_APPLICABLE"
    count = sum(x.state is Kr370CriterionState.SATISFIED for x in criteria)
    state = _state(direction.value, count, confirmation["state"])
    missing = next((x.identity.value for x in criteria if x.state is Kr370CriterionState.UNSATISFIED), None)
    sole = missing if count == 4 else None
    _require(condition is None or sole == Kr370CriterionIdentity.K2_CPR_ACCEPTANCE.value)
    watch = ("NOT_APPLICABLE" if count < 4 or state in {"BUY_NOW", "SELL_NOW"} else
             "WATCH_AVAILABLE" if condition is not None else "NO_AUTOMATED_ALERT_AVAILABLE")
    return "EVALUATED", [], count, 5 - count, state, sole, bool(count == 5 and
           confirmation["state"] == "WITHHELD"), watch


def _intrinsic_gate(criteria: list[dict]) -> str | None:
    reasons = [item["reason_code"] for item in criteria]
    if reasons[0] == "NATIVE_1H_STRUCTURAL_FAILURE":
        return "NATIVE_THESIS_INVALIDATED_OR_STRUCTURAL_FAILURE"
    if reasons[3] == "NATIVE_1H_SETUP_QUALITY_INVALID":
        return "NATIVE_MANDATORY_VISUAL_EVIDENCE_INVALID"
    if reasons[3] == "MESSY_CHOPPY":
        return "NATIVE_1H_MESSY_CHOPPY"
    if reasons[3] == "CONFLICTING":
        return "AFFIRMATIVE_GOVERNED_DIRECTIONAL_CONFLICT"
    return None


def create_record(*, source: dict, criteria: tuple[Kr370CriterionResult, ...],
                  confirmation: dict, created_at: datetime, hard_gate_reason: str | None = None,
                  promotion_condition: dict | None = None) -> V2PromotionRecord:
    source, confirmation = deepcopy(source), deepcopy(confirmation)
    _validate_source(source)
    _validate_confirmation(confirmation, source)
    disp, reasons, count, missing, state, sole, pending, watch = classify(
        criteria, V1Direction(source["direction"]), confirmation, hard_gate_reason,
        promotion_condition)
    if disp != "EVALUATED": promotion_condition = None
    value = dict(schema=SCHEMA, contract_identity=CONTRACT, contract_version=VERSION,
        policy_identity=POLICY, policy_version=VERSION, owner_identity="KR-370",
        state_family_identity="KR370_ANALYTICAL_PROMOTION", product="SWING",
        authority="ANALYTICAL_PROMOTION_ONLY", source=source,
        criteria=[dict(identity=x.identity.value, state=x.state.value,
            reason_code=_criterion_reason(x), evidence_sha256=sorted(set(x.evidence_identities)))
            for x in criteria], evaluation_disposition=disp, reason_codes=reasons,
        satisfied_count=count, missing_count=missing, promotion_state=state,
        sole_missing_criterion=sole, confirmation=confirmation, confirmation_pending=pending,
        promotion_condition=promotion_condition, watchability=watch,
        freshness="EXACT_CURRENT_SAME_RUN", created_at=_time(created_at),
        authority_flags={k: False for k in FLAGS})
    input_material = {k: value[k] for k in ("schema", "contract_identity", "contract_version",
        "policy_identity", "policy_version")}
    input_material.update(source=source, confirmation_binding={
        "kind": confirmation["kind"], "nse_binding": confirmation["nse_binding"],
        "mcx_binding": confirmation["mcx_binding"]})
    value["input_sha256"] = sha256(canonical(input_material)).hexdigest()
    value["integrity_sha256"] = sha256(canonical(value)).hexdigest()
    value["record_identity"] = f"{CONTRACT}:{VERSION}:{value['integrity_sha256']}"
    return V2PromotionRecord(canonical(value))


def _criterion_reason(x: Kr370CriterionResult) -> str:
    reason = x.reason
    if reason in K_REASON:
        return reason
    # V1 owner diagnostics can contain an exact source-specific unavailable
    # code; V2 stores the closed reason and binds that source by digest.
    if x.identity is Kr370CriterionIdentity.K3_PATH_CLEARANCE and x.state is Kr370CriterionState.UNAVAILABLE:
        return "E01_UNAVAILABLE"
    if x.identity is Kr370CriterionIdentity.K5_NON_EXTENSION and x.state is Kr370CriterionState.UNAVAILABLE:
        return "E03_UNAVAILABLE"
    if x.identity is Kr370CriterionIdentity.K4_SETUP_QUALITY:
        return ("NATIVE_1H_SETUP_QUALITY_INVALID" if "INVALID" in reason else
                "NATIVE_1H_SETUP_QUALITY_UNAVAILABLE")
    _require(False, "V2_SOURCE_INVALID")
    raise AssertionError


def _source_from_owners(requirement: NativeReviewRequirement, facts: SameRunMtfFactSnapshot,
                        receipt: ReviewAcceptanceReceipt, commit: ReviewAcceptanceCommit,
                        store: ReviewEvidenceStore, manifest: str,
                        nse_request: NseReviewRequestMapping | None) -> dict:
    """Capture accepted authority, preserving artifact and semantic digests separately."""
    _require(type(requirement) is NativeReviewRequirement and
             type(facts) is SameRunMtfFactSnapshot and
             type(receipt) is ReviewAcceptanceReceipt and
             type(commit) is ReviewAcceptanceCommit and
             type(store) is ReviewEvidenceStore, "V2_SOURCE_INVALID")
    _require(requirement.requirement_sha256 == _native_requirement_sha256(requirement),
             "V2_SOURCE_INVALID")
    _require(facts.run_identity == requirement.native_run_identity and
             receipt in commit.receipts, "V2_SOURCE_BINDING_MISMATCH")
    stored = store.resolve_committed_receipt(commit.identity, receipt.receipt_id, current=True)
    _require(stored._payload == receipt._payload, "V2_SOURCE_STALE")
    # The owner validates every artifact byte and typed artifact relationship.
    store._verify_complete_receipt(receipt)
    b, body = receipt.binding.value, receipt.body
    instrument = facts.instrument(requirement.canonical_instrument)
    market = requirement.thesis.product_path.name
    _require(market in {"NSE", "MCX"} and b["market"] == market and
             b["analytical_run_identity"] == requirement.native_run_identity and
             b["committed_run_manifest_identity"] == manifest and
             b["candidate_identity"] == requirement.requirement_sha256 and
             b["canonical_instrument"] == requirement.canonical_instrument and
             b["native_assessment_sha256"] == requirement.thesis.native_assessment_sha256,
             "V2_SOURCE_BINDING_MISMATCH")
    member = next((x for x in SWING_PHASE1_UNIVERSE if x.canonical_identity ==
                   requirement.canonical_instrument), None)
    _require(member is not None and member.asset_class.value in
             ({"NSE_EQUITY", "NSE_INDEX"} if market == "NSE" else {"MCX_COMMODITY"}),
             "V2_SOURCE_BINDING_MISMATCH")
    machine = instrument.reference_facts
    _require(len(machine) == 4 and all(item.integrity_sha256 ==
             machine_fact_integrity_sha256(item) for item in machine), "V2_SOURCE_INVALID")
    charts = {(x["role"], x["timeframe_or_panel_identity"]): x for x in body["chart_revisions"]}
    evidence = {(x["role"], x["timeframe_or_family_identity"]): x for x in body["structured_evidence"]}
    roles = ["NATIVE_NSE"] if market == "NSE" else ["NATIVE_MCX", "SUPPORTING_REFERENCE"]
    request_bindings = []
    if market == "NSE":
        _require(type(nse_request) is NseReviewRequestMapping, "V2_SOURCE_INVALID")
        mapping = nse_request.value
        _require((mapping["request_identity"], mapping["native_run_identity"],
                  mapping["committed_run_manifest_identity"], mapping["review_pack_identity"],
                  mapping["review_pack_sha256"]) ==
                 (b["request_identity"], requirement.native_run_identity, manifest,
                  b["review_pack_identity"], b["review_pack_sha256"]),
                 "V2_SOURCE_BINDING_MISMATCH")
        selected = [x for x in mapping["subjects"] if x["canonical_instrument"] ==
                    requirement.canonical_instrument]
        _require(len(selected) == 1 and selected[0]["native_assessment_sha256"] ==
                 requirement.thesis.native_assessment_sha256,
                 "V2_SOURCE_BINDING_MISMATCH")
        _require(all(x["chart_revision_sha256"] ==
                 charts[("NATIVE_NSE", x["timeframe"])]["sha256"] for x in selected[0]["responses"]),
                 "V2_SOURCE_BINDING_MISMATCH")
        request_bindings.append(dict(role="NATIVE_NSE", request_identity=b["request_identity"],
            request_sha256=mapping["request_sha256"],
            review_pack_identity=b["review_pack_identity"], review_pack_sha256=b["review_pack_sha256"]))
    else:
        _require(nse_request is None, "V2_SOURCE_INVALID")
        compare = body["comparison_evidence"]
        _require(compare is not None, "V2_SOURCE_INVALID")
        for role, prefix in zip(roles, ("native", "reference"), strict=True):
            request_bindings.append(dict(role=role,
                request_identity=compare[prefix + "_request_identity"],
                request_sha256=compare[prefix + "_request_sha256"],
                review_pack_identity=b["review_pack_identity"], review_pack_sha256=b["review_pack_sha256"]))
    visual_bindings = []
    for role in roles:
        for tf in (["1W", "1D", "4H", "1H"] if role == "NATIVE_NSE" else ["1D", "4H", "1H"]):
            chart, item = charts[(role, tf)], evidence[(role, tf)]
            raw = store._read(item["retained_relative_path"])
            decoded = strict_json(raw)
            _require(sha256(raw).hexdigest() == item["sha256"], "V2_SOURCE_INVALID")
            if role == "NATIVE_NSE":
                _require(decoded.pop("answer_pdf_sha256", None) == body["answer"]["pdf_sha256"],
                         "V2_SOURCE_INVALID")
                semantic = visual_evidence_v3_response_from_dict(decoded).evidence_sha256
            else:
                semantic = decoded["integrity_sha256"]
            visual_bindings.append(dict(role=role, timeframe=tf, subject_identity=chart["subject_identity"],
                reference_market=chart["reference_market"], reference_symbol=chart["reference_symbol"],
                chart_revision_identity=chart["revision_identity"], chart_sha256=chart["sha256"],
                structured_evidence_schema=item["schema"], structured_evidence_version=item["version"],
                structured_evidence_sha256=item["sha256"], evidence_integrity_sha256=semantic))
    acceptance = dict(commit_identity=commit.identity, receipt_identity=receipt.receipt_id,
        receipt_schema=receipt.value["schema"], receipt_version=receipt.value["version"],
        receipt_integrity_sha256=receipt.value["integrity_sha256"],
        request_publication_identity=commit.value["request_publication_identity"],
        review_cycle_identity=b["review_cycle_identity"], review_pack_identity=b["review_pack_identity"],
        review_pack_sha256=b["review_pack_sha256"], request_bindings=request_bindings,
        answer_identity=body["answer"]["answer_identity"],
        answer_pdf_sha256=body["answer"]["pdf_sha256"],
        visual_contracts=[dict(x) for role in roles for x in body["contracts"] if x["role"] == role],
        visual_bindings=visual_bindings)
    source = dict(native_run_identity=requirement.native_run_identity,
        committed_run_manifest_identity=manifest, market=market, asset_class=member.asset_class.value,
        canonical_instrument=requirement.canonical_instrument, direction=requirement.thesis.direction.value,
        native_opportunity_identity=requirement.thesis.opportunity_identity.value,
        native_assessment_sha256=requirement.thesis.native_assessment_sha256,
        native_requirement_sha256=requirement.requirement_sha256,
        analysis_boundary=_time(max(x.analysis_boundary for x in machine)),
        observation_boundaries=[dict(timeframe=x.timeframe.value, boundary=_time(x.observation_boundary))
            for x in instrument.timeframes], machine_snapshot_identity=facts.provider_source_identity,
        machine_fact_bindings=[dict(timeframe=x.chart_timeframe.value,
            integrity_sha256=x.integrity_sha256) for x in machine],
        e01_fact_integrity_sha256=None, e03_fact_integrity_sha256=None, acceptance=acceptance)
    return _validate_source(source)


def _nse_confirmation(source: dict, run: RelativeContextRun | None) -> dict:
    if source["asset_class"] == "NSE_INDEX":
        return dict(kind="ASSET_CLASS_EXEMPT", state="NOT_REQUIRED_BY_ASSET_CLASS",
                    reason_codes=["NOT_REQUIRED_BY_ASSET_CLASS"], nse_binding=None, mcx_binding=None)
    if run is None:
        binding = dict(validation_state="MISSING", observed_payload_sha256=None, payload=None)
    else:
        _require(type(run) is RelativeContextRun and
                 run.integrity_sha256 == relative_context_run_sha256(run), "V2_SOURCE_INVALID")
        record = run.record(source["canonical_instrument"])
        _require(type(record) is RelativeContextRecord and
                 record.integrity_sha256 == relative_context_record_sha256(record), "V2_SOURCE_INVALID")
        if (run.run_identity != source["native_run_identity"] or
                record.run_identity != source["native_run_identity"]):
            binding = dict(validation_state="STALE", observed_payload_sha256=record.integrity_sha256,
                           payload=None)
        else:
            horizons = []
            for tf in (FactualTimeframe.DAILY, FactualTimeframe.FOUR_HOUR):
                item = record.horizon(tf)
                available = item.relative_state.value in {"OUTPERFORMING", "UNDERPERFORMING", "EQUAL"}
                horizons.append(dict(timeframe=tf.value,
                    common_start_boundary=_time(item.stock_start_boundary) if available else None,
                    latest_common_completed_boundary=_time(item.stock_end_boundary) if available else None,
                    stock_source_identity=item.stock_source_identity,
                    benchmark_source_identity=item.benchmark_source_identity,
                    stock_provenance=list(item.stock_provenance),
                    benchmark_provenance=list(item.benchmark_provenance),
                    relative_state=item.relative_state.value,
                    directional_context=directional_relative_context(item.relative_state,
                        source["direction"]).value, reason_codes=[x.value for x in item.reason_codes]))
                if available:
                    _require(item.stock_start_boundary == item.benchmark_start_boundary and
                             item.stock_end_boundary == item.benchmark_end_boundary,
                             "V2_SOURCE_BINDING_MISMATCH")
            payload = dict(schema=record.schema, policy_identity=record.policy_identity,
                policy_version=record.policy_version, context_run_integrity_sha256=run.integrity_sha256,
                context_record_integrity_sha256=record.integrity_sha256,
                run_identity=record.run_identity, canonical_instrument=record.canonical_instrument,
                benchmark_identity=record.benchmark_identity, horizons=horizons)
            binding = dict(validation_state="VALID", observed_payload_sha256=record.integrity_sha256,
                           payload=payload)
    conf = dict(kind="NSE_NIFTY", state="WITHHELD", reason_codes=[], nse_binding=binding,
                mcx_binding=None)
    if binding["validation_state"] == "VALID":
        conf["state"], conf["reason_codes"] = _validate_nse(binding, source)
    else:
        conf["reason_codes"] = ["NSE_CONTEXT_" + binding["validation_state"]]
    return _validate_confirmation(conf, source)


def _mcx_confirmation(source: dict, receipt: ReviewAcceptanceReceipt,
                      store: ReviewEvidenceStore) -> dict:
    ref = receipt.body["comparison_evidence"]
    if ref is None:
        binding = dict(validation_state="MISSING", observed_payload_sha256=None, payload=None)
    else:
        raw = store._read(ref["retained_relative_path"])
        _require(sha256(raw).hexdigest() == ref["sha256"], "V2_SOURCE_INVALID")
        comparison = parse_mcx_json(raw)
        _require(comparison["integrity_sha256"] == sha256(canonical({k:v for k,v in
                 comparison.items() if k != "integrity_sha256"})).hexdigest(), "V2_SOURCE_INVALID")
        mapping = MCX_REFERENCE_MAPPINGS[source["canonical_instrument"]]
        obs = comparison["observations"]
        p = dict(registered_mapping=dict(native_family=source["canonical_instrument"],
                 reference_name=mapping[0], reference_market=mapping[1], reference_symbol=mapping[2]),
            native_candidate_reference=comparison["native_candidate_reference"],
            pair_binding_sha256=comparison["pair_binding_sha256"],
            native_request_identity=ref["native_request_identity"],
            native_request_sha256=ref["native_request_sha256"],
            reference_request_identity=ref["reference_request_identity"],
            reference_request_sha256=ref["reference_request_sha256"],
            comparison_schema=comparison["schema"], comparison_version=comparison["version"],
            comparison_artifact_sha256=ref["sha256"],
            comparison_integrity_sha256=comparison["integrity_sha256"],
            m1={k:obs[0]["result"][k] if k in {"mapping_state", "coverage_state"} else
                obs[0][k] for k in MCX_M1_FIELDS},
            m2=dict(question_id=obs[1]["question_id"], observation_status=obs[1]["observation_status"],
                by_timeframe=[dict(timeframe=x["timeframe"], relationship=x["relationship"])
                              for x in obs[1]["result"]["by_timeframe"]]),
            m3={k:obs[2]["result"][k] if k in {"relationship_to_native_direction",
                "affected_timeframes", "limitations"} else obs[2][k] for k in MCX_M3_FIELDS})
        binding = dict(validation_state="VALID", observed_payload_sha256=ref["sha256"], payload=p)
    conf = dict(kind="MCX_GLOBAL_REFERENCE", state="WITHHELD", reason_codes=[],
                nse_binding=None, mcx_binding=binding)
    if binding["validation_state"] == "VALID":
        conf["state"], conf["reason_codes"] = _validate_mcx(binding, source)
    else:
        conf["reason_codes"] = ["MCX_REFERENCE_MISSING"]
    return _validate_confirmation(conf, source)


def _derive_criteria(requirement: NativeReviewRequirement, facts: SameRunMtfFactSnapshot,
                     visual: tuple[VisualEvidenceV3Response, ...] | None,
                     path_clearance: OneHourPathClearanceFact,
                     extension: CompletedOneHourExtensionFact,
                     receipt: ReviewAcceptanceReceipt, store: ReviewEvidenceStore,
                     source: dict) -> tuple[tuple[Kr370CriterionResult, ...], str | None, dict | None]:
    _require(type(path_clearance) is OneHourPathClearanceFact and
             type(extension) is CompletedOneHourExtensionFact, "V2_SOURCE_INVALID")
    _require(path_clearance.integrity_sha256 == path_clearance_integrity_sha256(path_clearance) and
             extension.integrity_sha256 == extension_integrity_sha256(extension), "V2_SOURCE_INVALID")
    source["e01_fact_integrity_sha256"] = path_clearance.integrity_sha256
    source["e03_fact_integrity_sha256"] = extension.integrity_sha256
    instrument = facts.instrument(requirement.canonical_instrument)
    hour = instrument.fact(FactualTimeframe.ONE_HOUR)
    atr = instrument.one_hour_atr
    expected_analysis = atr.analysis_boundary if atr is not None else hour.observation_boundary
    thesis = {x.timeframe: x for x in requirement.thesis.timeframe_facts}
    _require(facts.run_identity == requirement.native_run_identity and
        all((thesis[x.timeframe].observation_boundary, thesis[x.timeframe].source_timestamp,
             thesis[x.timeframe].close) ==
            (x.observation_boundary, x.source_timestamp, x.close) for x in instrument.timeframes),
        "V2_SOURCE_BINDING_MISMATCH")
    _require(path_clearance.policy_identity == PATH_CLEARANCE_POLICY_IDENTITY and
        path_clearance.policy_version == PATH_CLEARANCE_POLICY_VERSION and
        path_clearance.run_identity == requirement.native_run_identity and
        path_clearance.canonical_instrument == requirement.canonical_instrument and
        path_clearance.direction is requirement.thesis.direction and
        path_clearance.observation_boundary == hour.observation_boundary and
        path_clearance.analysis_boundary == expected_analysis and
        path_clearance.source_market_data_boundary == hour.source_market_data_boundary and
        path_clearance.completed_price == hour.close and
        (atr is None or path_clearance.atr_fact_integrity_sha256 == atr.integrity_sha256),
        "V2_SOURCE_BINDING_MISMATCH")
    _require(extension.policy_identity == EXTENSION_POLICY_IDENTITY and
        extension.policy_version == EXTENSION_POLICY_VERSION and
        extension.run_identity == requirement.native_run_identity and
        extension.native_assessment_sha256 == requirement.thesis.native_assessment_sha256 and
        extension.canonical_instrument == requirement.canonical_instrument and
        extension.direction is requirement.thesis.direction and
        extension.observation_boundary == hour.observation_boundary and
        extension.source_market_data_boundary == hour.source_market_data_boundary and
        extension.completed_close == hour.close and
        extension.calendar_identity == hour.calendar_identity and
        extension.calendar_version == hour.calendar_version and
        extension.session_identity == hour.session_identity and
        extension.source_provider_identity == hour.source_provider_identity and
        (atr is None or extension.atr_fact_integrity_sha256 == atr.integrity_sha256),
        "V2_SOURCE_BINDING_MISMATCH")
    if source["market"] == "NSE":
        _require(type(visual) is tuple and all(type(x) is VisualEvidenceV3Response for x in visual),
                 "V2_SOURCE_INVALID")
        _require(_binding_failure(requirement, facts, visual, path_clearance, extension) is None,
                 "V2_SOURCE_BINDING_MISMATCH")
        _require([(x.timeframe.value, x.evidence_sha256) for x in visual] ==
                 [(x["timeframe"], x["evidence_integrity_sha256"]) for x in
                  source["acceptance"]["visual_bindings"]], "V2_SOURCE_BINDING_MISMATCH")
        k4, quality_gate = _k4(visual)
    else:
        _require(visual is None, "V2_SOURCE_INVALID")
        for tf in NATIVE_TIMEFRAMES:
            item = next(x for x in receipt.body["structured_evidence"] if
                        x["role"] == "NATIVE_MCX" and x["timeframe_or_family_identity"] == tf)
            native = parse_mcx_json(store._read(item["retained_relative_path"]))
            bind = native["binding"]
            fact = instrument.reference_fact(SwingReferenceChartTimeframe(tf))
            _require(native["schema"] == NATIVE_EVIDENCE_V2 and
                     native["version"] == SUCCESSOR_VERSION and
                     bind["native_candidate_reference"] == requirement.requirement_sha256 and
                     bind["native_assessment_sha256"] == requirement.thesis.native_assessment_sha256 and
                     bind["native_run_identity"] == requirement.native_run_identity and
                     bind["committed_run_manifest_identity"] == source["committed_run_manifest_identity"] and
                     bind["timeframe"] == tf and
                     bind["native_machine_fact_binding"] == fact.integrity_sha256,
                     "V2_SOURCE_BINDING_MISMATCH")
        # MCX V2 native 1H Q5 uses the same governed quality enum as NSE K4.
        item = next(x for x in source["acceptance"]["visual_bindings"] if
                    x["role"] == "NATIVE_MCX" and x["timeframe"] == "1H")
        receipt_item = next(x for x in receipt.body["structured_evidence"] if
                            x["role"] == "NATIVE_MCX" and x["timeframe_or_family_identity"] == "1H")
        evidence = parse_mcx_json(store._read(receipt_item["retained_relative_path"]))
        _require(evidence["schema"] == NATIVE_EVIDENCE_V2 and evidence["version"] == SUCCESSOR_VERSION and
                 evidence["integrity_sha256"] == item["evidence_integrity_sha256"] and
                 evidence["binding"]["native_candidate_reference"] == requirement.requirement_sha256 and
                 evidence["binding"]["native_assessment_sha256"] ==
                    requirement.thesis.native_assessment_sha256, "V2_SOURCE_BINDING_MISMATCH")
        quality = evidence["response"]["observations"][4]
        _require(quality["question_id"] == "PRICE_ACTION_QUALITY", "V2_SOURCE_INVALID")
        quality_state = quality["result"]["setup_quality"]
        if quality["observation_status"] != "OBSERVED" or quality_state == "NOT_OBSERVABLE":
            state, reason, quality_gate = Kr370CriterionState.UNAVAILABLE, "NATIVE_1H_SETUP_QUALITY_UNAVAILABLE", None
        elif quality_state in {"MESSY_CHOPPY", "CONFLICTING"}:
            state, reason = Kr370CriterionState.UNSATISFIED, quality_state
            quality_gate = "NATIVE_1H_MESSY_CHOPPY" if quality_state == "MESSY_CHOPPY" else \
                           "AFFIRMATIVE_GOVERNED_DIRECTIONAL_CONFLICT"
        else:
            _require(quality_state in {"CLEAN_DIRECTIONAL", "HEALTHY_CONSOLIDATION",
                     "HEALTHY_COMPRESSION", "ORDERLY_PULLBACK"}, "V2_SOURCE_INVALID")
            state, reason, quality_gate = Kr370CriterionState.SATISFIED, quality_state, None
        k4 = Kr370CriterionResult(Kr370CriterionIdentity.K4_SETUP_QUALITY, state,
                                  reason, (item["evidence_integrity_sha256"],))
    k1, structural_gate = _k1(requirement)
    k2 = _k2(requirement, facts.instrument(requirement.canonical_instrument))
    criteria = (k1, k2, _k3(path_clearance), k4, _k5(extension))
    gate = _hard_gate(requirement, structural_gate, quality_gate)
    gate = {"MISSING_OR_INVALID_MANDATORY_V3_1_EVIDENCE": "NATIVE_MANDATORY_VISUAL_EVIDENCE_INVALID",
            "V3_1_1H_MESSY_CHOPPY": "NATIVE_1H_MESSY_CHOPPY"}.get(gate, gate)
    condition = None
    if (gate is None and not any(x.state is Kr370CriterionState.UNAVAILABLE for x in criteria) and
        sum(x.state is Kr370CriterionState.SATISFIED for x in criteria) == 4 and
        k2.state is Kr370CriterionState.UNSATISFIED):
        c = _k2_condition(requirement, facts, criteria)
        condition = dict(criterion_identity=c.criterion_identity.value, timeframe=c.timeframe.value,
            comparator=c.comparator, price=c.price, summary=c.summary,
            source_evidence_ids=list(c.source_evidence_ids), observation_boundary=_time(c.observation_boundary))
    return criteria, gate, condition


def evaluate_governed(*, requirement: NativeReviewRequirement, facts: SameRunMtfFactSnapshot,
                      path_clearance: OneHourPathClearanceFact,
                      extension: CompletedOneHourExtensionFact,
                      store: ReviewEvidenceStore, commit_identity: str, receipt_identity: str,
                      current_manifest: Callable[[], str], created_at: datetime,
                      visual: tuple[VisualEvidenceV3Response, ...] | None = None,
                      relative_context: RelativeContextRun | None = None,
                      nse_request: NseReviewRequestMapping | None = None) -> V2PromotionRecord:
    """Explicit source-owned evaluation; never called by GET or runtime startup."""
    _require(type(store) is ReviewEvidenceStore and callable(current_manifest), "V2_SOURCE_INVALID")
    manifest = current_manifest()
    _require(_digest(manifest), "V2_SOURCE_INVALID")
    receipt = store.resolve_committed_receipt(commit_identity, receipt_identity, current=True)
    commit = store.load_acceptance(commit_identity)
    source = _source_from_owners(requirement, facts, receipt, commit, store, manifest, nse_request)
    criteria, gate, condition = _derive_criteria(requirement, facts, visual, path_clearance,
                                                  extension, receipt, store, source)
    confirmation = (_nse_confirmation(source, relative_context) if source["market"] == "NSE"
                    else _mcx_confirmation(source, receipt, store))
    record = create_record(source=source, criteria=criteria, confirmation=confirmation,
                           created_at=created_at, hard_gate_reason=gate,
                           promotion_condition=condition)
    _require(current_manifest() == manifest, "V2_PUBLICATION_CHANGED")
    _require(store.resolve_committed_receipt(commit_identity, receipt_identity, current=True)._payload ==
             receipt._payload, "V2_SOURCE_STALE")
    return record


class LocalV2PromotionStore:
    """Immutable exact-input V2 files; no current alias or GET write."""

    def __init__(self, root: Path = DEFAULT_ROOT) -> None:
        root = Path(root).expanduser()
        _require(root.is_absolute(), "V2_STORAGE_UNAVAILABLE")
        self.root = root
        self._lock = RLock()

    def _path(self, source: dict, input_sha256: str) -> Path:
        _require(is_swing_analysis_run_id(source["native_run_identity"]) and _digest(input_sha256))
        directory = self.root / source["native_run_identity"]
        path = directory / f"{input_sha256}.json"
        _require(not self.root.is_symlink() and not directory.is_symlink() and
                 not path.is_symlink(), "V2_STORAGE_UNAVAILABLE")
        return path

    @staticmethod
    def _read(path: Path) -> bytes:
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(descriptor, "rb") as stream:
                _require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "V2_STORAGE_UNAVAILABLE")
                return stream.read()
        except FileNotFoundError:
            raise
        except OSError as error:
            raise ValueError("V2_STORAGE_UNAVAILABLE") from error

    def retain(self, record: V2PromotionRecord, *, current: Callable[[dict], bool]) -> Path:
        _require(type(record) is V2PromotionRecord and callable(current))
        value = record.value
        _require(current(value["source"]) is True, "V2_SOURCE_STALE")
        path = self._path(value["source"], value["input_sha256"])
        with self._lock:
            if path.exists():
                _require(self._read(path) == record.payload, "V2_IMMUTABLE_CONFLICT")
                _require(current(value["source"]) is True, "V2_SOURCE_STALE")
                return path
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            temp = path.with_name(path.name + ".tmp-" + os.urandom(8).hex())
            try:
                with temp.open("xb") as stream:
                    os.fchmod(stream.fileno(), 0o600)
                    stream.write(record.payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                _require(current(value["source"]) is True, "V2_PUBLICATION_CHANGED")
                # Exclusive hardlink admission prevents overwriting a concurrent
                # first writer; exact retry compares the complete retained bytes.
                try:
                    os.link(temp, path)
                except FileExistsError:
                    _require(not path.is_symlink() and self._read(path) == record.payload,
                             "V2_IMMUTABLE_CONFLICT")
                fd = os.open(path.parent, os.O_RDONLY)
                try: os.fsync(fd)
                finally: os.close(fd)
            finally:
                temp.unlink(missing_ok=True)
        _require(current(value["source"]) is True, "V2_PUBLICATION_CHANGED")
        return path

    def load_exact(self, source: dict, input_sha256: str, *,
                   current: Callable[[dict], bool]) -> V2PromotionRecord | None:
        _require(callable(current))
        _validate_source(source)
        _require(_digest(input_sha256))
        _require(current(source) is True, "V2_SOURCE_STALE")
        path = self._path(source, input_sha256)
        try:
            payload = self._read(path)
        except FileNotFoundError:
            return None
        record = V2PromotionRecord(payload)
        _require(record.value["source"] == source and record.value["input_sha256"] == input_sha256,
                 "V2_SOURCE_BINDING_MISMATCH")
        _require(current(source) is True, "V2_PUBLICATION_CHANGED")
        return record


__all__ = ["CONTRACT", "VERSION", "POLICY", "SCHEMA", "SCHEMA_SEAL_SHA256",
           "Disposition", "Promotion", "ConfirmationState", "V2PromotionRecord",
           "LocalV2PromotionStore", "classify", "create_record", "evaluate_governed"]
