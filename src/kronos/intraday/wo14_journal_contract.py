"""Compact, immutable WO-14 Intraday Trading Journal presentation contract.

This namespace is intentionally separate from the historical WO-14 risk
observation contract.  Journal records are projections of retained WO-10 and
WO-11 authority; they never become lifecycle, monitoring, or research facts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json


POLICY_IDENTITY = "KRONOS-INTRADAY-WO14-TRADING-JOURNAL-POLICY"
POLICY_VERSION = "1.0.0"
TRUTH_CLASSES = frozenset({"PAPER_POSITION", "PAPER_OBSERVATION", "NONE", "DO_NOTHING"})
MONITORING_STATES = frozenset({"LIVE", "INTERRUPTED", "IDLE", "NOT_REQUIRED", "UNAVAILABLE"})
TRADING_EXIT_REASONS = frozenset({"STOP_LOSS", "TARGET", "SPONSOR_EXIT"})
RULES = {
    "authority": "COMPACT_PRESENTATION_PROJECTION_ONLY",
    "identity_source": "RETAINED_WO12_OPPORTUNITY_ORIGIN_V1",
    "truth_classes": sorted(TRUTH_CLASSES),
    "live": "LIVE_POSITION_NOT_COMMISSIONED_V1",
    "suppression": "PRESENTATION_ONLY_NO_SOURCE_OR_LIFECYCLE_EFFECT",
    "monitoring": "CONSUME_WO11_OWNER_STATE_CREATE_NOTHING",
    "exit_reasons": sorted(TRADING_EXIT_REASONS),
    "research": "NO_METRIC_RECALCULATION_NO_DENOMINATOR_EFFECT",
}


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


POLICY_CHECKSUM = sha256(_json(RULES).encode()).hexdigest()


def _aware(value: str) -> datetime:
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("WO14_JOURNAL_AWARE_TIMESTAMP_REQUIRED")
    return result.astimezone(timezone.utc)


def stable_identity(*parts: object) -> str:
    return "WO14-JOURNAL-" + sha256(_json(parts).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class JournalRevision:
    journal_identity: str
    revision_identity: str
    payload_json: str
    policy_identity: str = POLICY_IDENTITY
    policy_version: str = POLICY_VERSION
    policy_checksum: str = POLICY_CHECKSUM

    @property
    def data(self) -> dict[str, object]:
        value = json.loads(self.payload_json)
        if not isinstance(value, dict):
            raise ValueError("WO14_JOURNAL_PAYLOAD_INVALID")
        return value

    def __post_init__(self) -> None:
        data = self.data
        required = {
            "opportunity_id", "opportunity_identity", "subject", "direction",
            "session_identity", "decision", "decision_identity", "decision_at",
            "truth_class", "track_identity", "status", "terminal", "source_identities",
            "monitoring", "model_lots", "entry", "exit", "exit_reason",
            "terminal_status", "metrics", "trade_plan_identity", "future",
            "underlying_geometry", "future_geometry", "planned_rr",
            "selected_lots_context", "setup_family", "market_family", "origin_at",
            "readiness_identity", "highest_readiness", "decision_reason", "holding_time",
            "trading_date",
        }
        if set(data) != required:
            raise ValueError("WO14_JOURNAL_EXACT_FIELDS_REQUIRED")
        if data["truth_class"] not in TRUTH_CLASSES:
            raise ValueError("WO14_JOURNAL_TRUTH_CLASS_INVALID")
        if data["monitoring"] not in MONITORING_STATES:
            raise ValueError("WO14_JOURNAL_MONITORING_STATE_INVALID")
        if data["exit_reason"] is not None and data["exit_reason"] not in TRADING_EXIT_REASONS:
            raise ValueError("WO14_JOURNAL_EXIT_REASON_INVALID")
        if data["truth_class"] in {"PAPER_POSITION", "PAPER_OBSERVATION"}:
            if data["model_lots"] != 1 or not data["track_identity"]:
                raise ValueError("WO14_JOURNAL_TRACK_AUTHORITY_INVALID")
        elif any(data[key] is not None for key in ("track_identity", "model_lots", "entry", "exit", "exit_reason")):
            raise ValueError("WO14_JOURNAL_NO_TRACK_FACTS_INVALID")
        if not isinstance(data["opportunity_id"], str) or not data["opportunity_id"]:
            raise ValueError("WO14_JOURNAL_OPPORTUNITY_ID_REQUIRED")
        if not isinstance(data["opportunity_identity"], str) or not data["opportunity_identity"]:
            raise ValueError("WO14_JOURNAL_OPPORTUNITY_IDENTITY_REQUIRED")
        _aware(str(data["decision_at"]))
        expected = stable_identity("INTRADAY", data["opportunity_identity"], data["decision_identity"],
                                   data["track_identity"], data["truth_class"], data["decision"])
        if self.journal_identity != expected:
            raise ValueError("WO14_JOURNAL_IDENTITY_MISMATCH")
        if self.revision_identity != "WO14-JOURNAL-REVISION-" + sha256(self.payload_json.encode()).hexdigest():
            raise ValueError("WO14_JOURNAL_REVISION_IDENTITY_MISMATCH")
        if (self.policy_identity, self.policy_version, self.policy_checksum) != (
                POLICY_IDENTITY, POLICY_VERSION, POLICY_CHECKSUM):
            raise ValueError("WO14_JOURNAL_POLICY_MISMATCH")


def revision(**data: object) -> JournalRevision:
    data = {"origin_at": None, "readiness_identity": None, "highest_readiness": None,
            "decision_reason": None, "holding_time": None, "trading_date": None, **data}
    payload = _json(data)
    identity = stable_identity("INTRADAY", data["opportunity_identity"], data["decision_identity"],
                               data["track_identity"], data["truth_class"], data["decision"])
    return JournalRevision(identity, "WO14-JOURNAL-REVISION-" + sha256(payload.encode()).hexdigest(), payload)


@dataclass(frozen=True, slots=True)
class JournalSnapshot:
    records: tuple[JournalRevision, ...]
    suppressed: tuple[str, ...]
    monitoring: tuple[tuple[str, str], ...] = ()


__all__ = [
    "JournalRevision", "JournalSnapshot", "MONITORING_STATES", "POLICY_CHECKSUM",
    "POLICY_IDENTITY", "POLICY_VERSION", "TRADING_EXIT_REASONS", "TRUTH_CLASSES",
    "revision", "stable_identity",
]
