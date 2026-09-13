"""WO-13 compact attention contract; upstream records retain all decision authority."""
from datetime import datetime
from hashlib import sha256
import json
import re

POLICY_IDENTITY = "KRONOS-INTRADAY-WO13-NOTIFICATIONS"
POLICY_VERSION = "1.0.0"
TITLES = {
    "READY_FOUR": "4/5 READY", "READY_FIVE": "5/5 NOW",
    "TRADE_CANDIDATE": "TRADE CANDIDATE", "PAPER_ENTRY": "PAPER ENTRY",
    "OBSERVATION_ENTRY": "OBSERVATION ENTRY", "TARGET": "TARGET",
    "STOP_LOSS": "STOP LOSS", "SPONSOR_EXIT": "SPONSOR EXIT",
    "MONITORING_INTERRUPTED": "MONITORING INTERRUPTED", "ACTION_REQUIRED": "ACTION REQUIRED",
}
ACTION_REASONS = frozenset({"STRUCTURAL_CONSTRUCTION_AUTHORITY_NOT_ESTABLISHED",
                            "WO10_ACQUISITION_COMPOSITION_UNAVAILABLE"})
MONITORING_STATES = frozenset({"LIVE", "INTERRUPTED", "IDLE", "NOT_REQUIRED", "UNAVAILABLE"})
FIELDS = frozenset({"opportunity_id", "opportunity_identity", "subject", "direction", "market_family",
    "session_identity", "trading_date", "source_identity", "source_integrity", "event_identity",
    "event_at", "published_at", "family", "semantic_transition", "track_identity", "truth_class",
    "owner_identity", "gap_identity", "contract", "expiry", "entry", "stop", "target", "exit",
    "lots", "model_rr", "model_points", "one_lot_result", "executability", "risk_advisory",
    "pricing_identity", "readiness_count", "criteria", "reason", "action_identity",
    "policy_identity", "policy_version", "policy_checksum"})
POLICY = {"identity": POLICY_IDENTITY, "version": POLICY_VERSION, "families": TITLES,
          "action_reasons": sorted(ACTION_REASONS), "deduplication": "OPPORTUNITY_EVENT_TRACK_TRUTH_SEMANTICS",
          "ownership": "PRESENTATION_ONLY", "three_of_five": "NOT_COMMISSIONED",
          "monitoring": "EXACT_EXTERNAL_OWNER_ONLY", "reactivation": "SHARED_EXPLICIT_SOURCE_VALID_ONLY"}
POLICY_CHECKSUM = sha256(json.dumps(POLICY,sort_keys=True,separators=(",", ":")).encode()).hexdigest()


def aware(value):
    try:
        result = datetime.fromisoformat(value) if isinstance(value,str) else value
    except (TypeError, ValueError) as error:
        raise ValueError("WO13_EVENT_TIME_UNAVAILABLE") from error
    if not isinstance(result,datetime) or result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("WO13_EVENT_TIME_UNAVAILABLE")
    return result


def validate(details):
    """Compact allowlist only: no upstream payload, local path, or secret field."""
    required = {"opportunity_id", "opportunity_identity", "subject", "direction", "market_family",
                "session_identity", "source_identity", "source_integrity", "event_identity", "family",
                "event_at", "semantic_transition", "policy_identity", "policy_version", "policy_checksum"}
    if not isinstance(details,dict) or set(details)-FIELDS or not required <= set(details):
        raise ValueError("WO13_COMPACT_FIELDS_INVALID")
    if (details["family"] not in TITLES or details["direction"] not in {"LONG","SHORT"}
        or details["policy_identity"] != POLICY_IDENTITY or details["policy_version"] != POLICY_VERSION
        or details["policy_checksum"] != POLICY_CHECKSUM
        or not re.fullmatch(r"[A-Z0-9_&]+-\d{8}-\d{6}",details["opportunity_id"])):
        raise ValueError("WO13_POLICY_BINDING_INVALID")
    aware(details["event_at"])
    for key,value in details.items():
        if value is not None and (not isinstance(value,(str,int)) or isinstance(value,bool)):
            raise ValueError("WO13_COMPACT_VALUE_INVALID")
        if isinstance(value,str) and (len(value)>512 or any(x in value for x in ("/Users/","/private/","/tmp/","file://","Bearer ","<",">","\\"))):
            raise ValueError("WO13_NONPORTABLE_PAYLOAD")
    if details.get("truth_class") not in {None,"PAPER_POSITION","PAPER_OBSERVATION"}:
        raise ValueError("WO13_TRUTH_CLASS_INVALID")
    if details.get("truth_class") is not None and details.get("lots") != 1:
        raise ValueError("WO13_ONE_LOT_REQUIRED")
    if details["family"] == "ACTION_REQUIRED" and details.get("reason") not in ACTION_REASONS:
        raise ValueError("WO13_ACTION_NOT_ALLOWLISTED")


def semantic_identity(details):
    validate(details)
    material = ["INTRADAY", details["opportunity_identity"], details["family"],
                details["semantic_transition"], details.get("track_identity"), details.get("truth_class")]
    return "INTRADAY-WO13-" + sha256(json.dumps(material,separators=(",", ":")).encode()).hexdigest()


def telegram_text(details):
    validate(details)
    lines = ["KRONOS · INTRADAY", TITLES[details["family"]], details["subject"]+" · "+details["direction"],
             details["opportunity_id"]]
    for key in ("truth_class","lots","contract","expiry","entry","stop","target","exit","model_rr","model_points","one_lot_result","executability","risk_advisory"):
        if details.get(key) is not None:
            lines.append(key.replace("_"," ").upper()+": "+str(details[key]))
    if details.get("truth_class"):
        lines.append("MODEL ONLY · NO BROKER EXECUTION" if details["truth_class"]=="PAPER_POSITION" else "COUNTERFACTUAL MODEL · NO EXPOSURE")
    return "\n".join(lines)
