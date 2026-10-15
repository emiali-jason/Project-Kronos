"""TE-04A: one Theta-local definition for schemas, templates and instructions.

These are external Analyst evidence contracts, never an assessment methodology.
No runtime, persistence, Provider or Swing analytical dependency is introduced.
"""
from copy import deepcopy
from datetime import date
import re

from kronos.theta.contracts import ANSWER_SCHEMA, QUESTION_SCHEMA, SUBJECTS, stamp
from kronos.theta.contracts import ThetaError

V3 = "3.0.0"
COMBINED_SCHEMA = "KRONOS-THETA-COMBINED-ANSWER-V1"
COMBINED_VERSION = "1.0.0"
BATCH_SCHEMA = "KRONOS-THETA-TRANSPORT-V1"
BATCH_VERSION = "2.0.0"
MAX_CHILD_BYTES = 2 * 1024 * 1024
MAX_COMBINED_BYTES = 5 * MAX_CHILD_BYTES + 64 * 1024
MAX_DEPTH = 64
MAX_NODES = 250000
TEXT_LIMIT = 16000
RESEARCH_SECTIONS = (
    "chart_assessment", "reference_mcx_assessment", "bullish_evidence",
    "bearish_evidence", "macro_fundamental_research", "commodity_research",
    "reconciliation", "counterevidence", "uncertainty",
)
RELATIONSHIPS = (
    "SUPPORT", "OPPOSITION", "ALIGNMENT", "DIVERGENCE", "RECONCILIATION",
    "UNRESOLVED_CONTRADICTION",
)
CLASSIFICATIONS = ("FACT", "RESEARCH_RESULT", "HYPOTHESIS")


class V3Error(ThetaError):
    """Controlled code only: never echo external fields, values or private data."""


def check(condition, code="SCHEMA"):
    if not condition:
        raise V3Error("THETA_V3_" + code)


def obj(properties):
    return {"type": "object", "properties": properties, "required": list(properties),
            "additionalProperties": False}


def string(maximum=TEXT_LIMIT, **constraints):
    # Absolute end in both ECMA-262 JSON Schema and Python (not $ before LF).
    constraints["pattern"] = "^(?:" + constraints.get("pattern", r"[\s\S]*\S[\s\S]*") + r")(?![\s\S])"
    return {"type": "string", "minLength": 1, "maxLength": maximum, **constraints}


def nullable(schema):
    return {"anyOf": [schema, {"type": "null"}]}


def array(items, maximum, minimum=0, *, unique=False):
    return {"type": "array", "items": items, "minItems": minimum,
            "maxItems": maximum, **({"uniqueItems": True} if unique else {})}


ID = string(100, pattern=r"[A-Za-z][A-Za-z0-9_.:-]{0,99}")
HASH = string(64, pattern=r"[0-9a-f]{64}")
TIME = string(64, format="date-time", pattern=r"[0-9]{4}-[0-9]{2}-[0-9]{2}T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](?:\.[0-9]{1,6})?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])")
DAY = string(10, format="date")
DECIMAL = string(128, pattern=r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?")
CLASS = string(32, enum=list(CLASSIFICATIONS))
HORIZONS = array(string(2, enum=["E1", "E2"]), 2, 1, unique=True)
REFS = array(ID, 200, unique=True)
DESCRIPTOR = obj({"identity": ID, "version": string(32, pattern=r"[0-9]+\.[0-9]+\.[0-9]+"),
                  "sha256": HASH})
CHART = obj({"subject": string(32, enum=[*SUBJECTS, "GLOBAL_MACRO"]),
             "cycle_id": ID, "chart_id": ID, "revision_id": ID, "sha256": HASH})
TARGET = obj({
    "subject": string(32, enum=list(SUBJECTS)), "canonical_subject": ID,
    "horizon": string(2, enum=["E1", "E2"]), "option_expiry": DAY,
    "expires_at": TIME, "underlying_future": ID, "futures_expiry": DAY,
    "settlement_reference": ID, "authority_reference": ID,
    "exchange_evidence_reference": ID,
    "target": string(64, const="OPTION_EXPIRY_UNDERLYING_SETTLEMENT_REFERENCE"),
    "price_unit": string(128),
})
TYPED_REF = obj({"kind": string(16, enum=["EVIDENCE", "OBSERVATION", "FORECAST"]),
                 "identity": ID})
TYPED_REFS = array(TYPED_REF, 200, unique=True)
STATEMENT = obj({"classification": CLASS, "text": string(),
                 "evidence_ids": REFS, "source_ids": REFS})
SECTION = {"anyOf": [
    obj({"availability": string(32, const="AVAILABLE"), "classification": CLASS,
         "text": string(), "reason": {"type": "null"},
         "evidence_ids": array(ID, 200, 1, unique=True)}),
    obj({"availability": string(32, enum=["UNAVAILABLE", "NOT_APPLICABLE"]),
         "classification": {"type": "null"}, "text": {"type": "null"},
         "reason": string(), "evidence_ids": REFS}),
]}
CHART_OBSERVATION = obj({
    "observation_id": ID, "chart_reference": CHART, "panel_locator": string(1024),
    "role": string(16, enum=["REFERENCE", "MCX", "MACRO"]),
    "displayed_instrument": nullable(string(1024)), "timeframe": nullable(string(128)),
    "availability": string(32, enum=["AVAILABLE", "UNAVAILABLE", "NOT_APPLICABLE"]),
    "observation_text": nullable(string()), "classification": nullable(CLASS),
    "visible_as_of": nullable(TIME),
    "completion": string(32, enum=["COMPLETED", "FORMING", "UNKNOWN", "NOT_APPLICABLE"]),
    "unavailable_reason": nullable(string()), "horizons": HORIZONS,
})
EVIDENCE = obj({"evidence_id": ID, "statement": string(), "classification": CLASS,
                "source_ids": REFS, "observation_ids": REFS, "horizons": HORIZONS,
                "assumption_ids": REFS})
RELATION = obj({"relation_id": ID, "references": array(TYPED_REF, 200, 2, unique=True),
                "relationship_type": string(32, enum=list(RELATIONSHIPS)),
                "horizons": HORIZONS, "explanation": string(),
                "unresolved_limitation": nullable(string()), "limitation_ids": REFS})
CONTEXT = obj({"identity": ID, "statement": string(),
               "scope": string(16, enum=["COMMODITY", "HORIZON"]),
               "horizons": HORIZONS, "supporting_evidence_ids": REFS,
               "affected_references": TYPED_REFS, "unresolved_consequence": nullable(string())})
WINDOW = obj({"start": TIME, "end": TIME})
EVENT = obj({"event_id": ID, "description": string(),
             "availability": string(32, enum=["AVAILABLE", "UNAVAILABLE", "NOT_APPLICABLE"]),
             "scheduled_window": nullable(WINDOW), "schedule_source_id": nullable(ID),
             "schedule_known_at": nullable(TIME), "horizons": HORIZONS,
             "evidence_ids": REFS, "possible_impact": nullable(string()),
             "limitations": string()})
SOURCE = obj({
    "source_id": ID, "publisher": string(1024), "title": string(),
    "source_kind": string(32, enum=["PRIMARY", "SECONDARY", "ANALYSIS", "OTHER", "UNKNOWN"]),
    "url": nullable(string()), "reference": nullable(ID),
    "published_at": nullable(TIME), "available_at": TIME, "accessed_at": TIME,
    "availability_evidence": string(), "observation_period": nullable(string(1024)),
    "lineage": obj({"status": string(16, enum=["KNOWN", "UNKNOWN"]),
                    "original_information_id": nullable(ID), "derivative_source_ids": REFS}),
    "archive_version_locator": nullable(string()), "relevance": string(),
    "linked_evidence_ids": REFS,
})
RESEARCH = obj({
    **{name: deepcopy(SECTION) for name in RESEARCH_SECTIONS},
    "chart_observations": array(CHART_OBSERVATION, 96, 1),
    "evidence_items": array(EVIDENCE, 200, 1), "relationships": array(RELATION, 200),
    "scheduled_events": array(EVENT, 100), "assumptions": array(CONTEXT, 100),
    "limitations": array(CONTEXT, 100), "sources": array(SOURCE, 200, 1),
})
FORECAST = obj({"target": TARGET, "lower": DECIMAL, "upper": DECIMAL,
                "confidence_pct": DECIMAL,
                **{name: deepcopy(STATEMENT) for name in
                   ("rationale", "counterevidence", "uncertainty", "path_risk", "confidence_justification")},
                "material_evidence_ids": array(ID, 200, 1, unique=True),
                "material_source_ids": REFS, "assumption_ids": REFS, "limitation_ids": REFS})
BINDING = obj({"subject": string(32, enum=list(SUBJECTS)), "canonical_subject": ID,
               "cycle_id": ID, "commodity_chart": CHART, "macro_chart": CHART,
               "methodology": DESCRIPTOR, "target_authority": DESCRIPTOR})
QUESTION = obj({"schema_identity": string(64, const=QUESTION_SCHEMA),
                "schema_version": string(16, const=V3),
                "question_id": string(68, pattern=r"TEQ-[0-9a-f]{64}"),
                "created_at": TIME, "information_cutoff": TIME,
                "authority_valid_through": TIME, "binding": BINDING,
                "targets": obj({h: deepcopy(TARGET) for h in ("E1", "E2")}),
                "methodology_instructions": string(),
                "synthetic": {"type": "boolean"}})
QUESTION_REF = obj({"question_id": string(68, pattern=r"TEQ-[0-9a-f]{64}"),
                    "question_sha256": HASH})
BATCH = obj({"schema_identity": string(64, const=BATCH_SCHEMA),
             "schema_version": string(16, const=BATCH_VERSION),
             "batch_id": string(68, pattern=r"TEB-[0-9a-f]{64}"), "cycle_id": ID,
             "subjects": {"const": list(SUBJECTS)},
             "questions": obj({s: deepcopy(QUESTION_REF) for s in SUBJECTS}),
             "macro_chart": CHART, "synthetic": {"type": "boolean"},
             "complete": {"const": True}})
ANSWER = obj({"schema_identity": string(64, const=ANSWER_SCHEMA),
              "schema_version": string(16, const=V3), "answer_id": ID,
              "question_id": string(68, pattern=r"TEQ-[0-9a-f]{64}"),
              "question_sha256": HASH, "binding": BINDING,
              "information_cutoff": TIME, "analyzed_at": TIME,
              "analyst": obj({"identity": string(1024), "model": string(1024),
                              "provenance": string(1024)}),
              "research": RESEARCH,
              "forecasts": obj({h: deepcopy(FORECAST) for h in ("E1", "E2")})})

# The same rule identifiers are used by semantic validation and producer guidance.
RULES = {
    "BINDING": "Copy all KRONOS-prefilled identities, bindings, T0 and exact E1/E2 targets verbatim. No repair, normalization, nearest-future selection or common-T0 invention.",
    "RANGE": "Each horizon requires independent finite decimal-string LOWER < UPPER and confidence_pct in 0–100. Preserve trailing zeroes; no scientific notation, float, replacement confidence or NOT_EVALUABLE forecast branch.",
    "CHRONOLOGY": "Known source publication and supported availability must be at/before this child's T0. available_at <= accessed_at <= analyzed_at <= KRONOS receipt. Research/retrieval may finish after T0; later first-available information and later event outcomes are excluded.",
    "REFERENCE": "All local references must resolve in this commodity's source/observation/evidence/assumption/limitation graph or its exact Question. No cross-commodity evidence borrowing. Horizon-specific references must include that horizon. Entity IDs are unique across this child's families; E1/E2 are reserved forecast references. Source linked_evidence_ids exactly mirror claims citing that source. Known reference URLs are public HTTP(S), without embedded credentials, credential query fields, localhost or private IP addresses.",
    "AVAILABILITY": "Use AVAILABLE, UNAVAILABLE or NOT_APPLICABLE for structured evidence. Unavailable/not-applicable records require a truthful reason and must not contain fabricated available values. Numeric forecasts remain required; report unresolved numeric forecasting outside this Answer path.",
    "LINEAGE": "UNKNOWN source lineage has null original_information_id and no invented derivative links. KNOWN lineage has an original_information_id. Derivative references resolve to local sources, with no cycles; different URLs do not establish independence.",
    "PROVIDER_NEUTRAL": "Forecast independently. Internal Kite/Provider state, tokens, sessions, broker/accounts, positions, intended CE/PE strikes, Sponsor direction/preferences, P&L, margin and contemplated option expressions are outside the information set. Do not optimize for a Sponsor trade. No strategy, trading or broker instructions.",
    "EVIDENCE_ONLY": "Classifications and relationship types are Astra assertions, not verified KRONOS facts or TE-05 verdicts. No quality scores, STRONG/WEAK, criterion pass/fail, promotion or option-suitability verdict. Retain genuine research, counterevidence, uncertainty and independently reasoned E1/E2.",
}


def validate_shape(value, schema):
    """Validate only the explicitly emitted JSON-Schema subset; no coercion."""
    if "anyOf" in schema:
        for alternative in schema["anyOf"]:
            try:
                validate_shape(value, alternative)
                return
            except V3Error:
                pass
        raise V3Error("THETA_V3_SCHEMA")
    if "const" in schema:
        check(type(value) is type(schema["const"]) and value == schema["const"])
    kind = schema.get("type")
    if kind == "object":
        check(type(value) is dict and set(value) == set(schema["properties"]))
        for key, child in schema["properties"].items():
            validate_shape(value[key], child)
    elif kind == "array":
        check(type(value) is list and schema["minItems"] <= len(value) <= schema["maxItems"])
        if schema.get("uniqueItems"):
            from kronos.theta.contracts import encode
            check(len({encode(v) for v in value}) == len(value), "REFERENCE")
        for member in value:
            validate_shape(member, schema["items"])
    elif kind == "string":
        check(type(value) is str and bool(value.strip())
              and schema["minLength"] <= len(value) <= schema["maxLength"])
        check("enum" not in schema or value in schema["enum"])
        check("pattern" not in schema or re.fullmatch(schema["pattern"], value) is not None)
        try:
            value.encode("utf-8")
            if schema.get("format") == "date-time":
                stamp(value)
            elif schema.get("format") == "date":
                check(date.fromisoformat(value).isoformat() == value)
        except (ValueError, UnicodeError):
            raise V3Error("THETA_V3_SCHEMA") from None
    elif kind == "null":
        check(value is None)
    elif kind == "boolean":
        check(type(value) is bool)
    elif kind is not None:
        raise V3Error("THETA_V3_CONTRACT_DEFINITION")


def schema_document(definition):
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", **deepcopy(definition)}


def blank(schema):
    """Placeholders intentionally fail completed-Answer validation."""
    if "const" in schema:
        return deepcopy(schema["const"])
    if "anyOf" in schema:
        return blank(schema["anyOf"][0])
    if schema.get("type") == "object":
        return {k: blank(s) for k, s in schema["properties"].items()}
    if schema.get("type") == "array":
        return [blank(schema["items"]) for _ in range(schema["minItems"])]
    return None


def producer_instructions():
    bounds = (f"One UTF-8 JSON object, no fences/extra keys/duplicate keys. Exactly five subject slots: {', '.join(SUBJECTS)}; Macro is supporting evidence, not a sixth Answer. "
              f"Blank null placeholders are NOT a completed Answer. Do not truncate: each child <= {MAX_CHILD_BYTES} bytes; whole file <= {MAX_COMBINED_BYTES} bytes; depth <= {MAX_DEPTH}; nodes <= {MAX_NODES}. "
              f"Narrative strings <= {TEXT_LIMIT} characters. Sources/evidence/relationships <= 200 each, observations <= 96, events/assumptions/limitations <= 100 each. Every reference array <= 200; use the accompanying schema for every exact field/bound.")
    vocabulary = ("Relationship vocabulary (assertions only): " + ", ".join(RELATIONSHIPS) + ". "
                  "UNRESOLVED_CONTRADICTION requires unresolved_limitation text. Timestamps use YYYY-MM-DDTHH:MM:SS with Z or explicit HH:MM UTC offset and at most six fractional digits; no leap-second or silently truncated precision. "
                  "The standalone JSON Schema covers structure; these generated semantic rules and the bound Question govern chronology, reference resolution and decimal comparisons.")
    return "\n\n".join([bounds, vocabulary, *[f"{k}: {v}" for k, v in RULES.items()]])
