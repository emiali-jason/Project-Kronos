"""Prospective WO-12 local research publication contracts.

This module owns research authority only.  It does not acquire market facts,
create upstream lifecycle authority, or confer trading authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json


PROGRAMME_IDENTITY = "KRONOS-INTRADAY-PROSPECTIVE-PROGRAMME-V2"
POLICY_IDENTITY = "KRONOS-INTRADAY-WO12-LOCAL-RESEARCH-PUBLICATION-POLICY"
POLICY_VERSION = "1.0.0"
WORKBOOK_SCHEMA = "KRONOS-INTRADAY-RESEARCH-WORKBOOK-V1"
WORKBOOK_VERSION = "1.0.0"
LOCAL_PUBLICATION_ROOT = "/Users/imranali/Documents/Project-KRONOS/Statistics/Intraday"
SHEETS = ("Opportunities", "Tracks", "Events", "Analysis", "Data_Quality", "Metadata")
MONTH_STATES = frozenset({"OPEN_MONTH", "FINALIZED_MONTH", "CORRECTION_PENDING", "REPUBLISHED_MONTH"})
DAY_STATES = frozenset({"OPEN", "PUBLISHED", "FINALIZED"})

POLICY_RULES = {
    "authority": "RESEARCH_ONLY_NO_TRADING_AUTHORITY",
    "publication": "ATOMIC_LOCAL_MONTHLY_XLSX",
    "sheets": list(SHEETS),
    "opportunity_origin": "EARLIEST_RETAINED_ADMITTED_PROBABLES_EVENT",
    "same_session_successor": "GOVERNED_RESET_AFTER_PRIOR_TERMINAL_ONLY",
    "sponsor_id": "CANONICAL_SYMBOL-YYYYMMDD-HHMMSS_ASIA_KOLKATA",
    "truth_classes": ["PAPER_POSITION", "PAPER_OBSERVATION"],
    "paper_lots": 1,
    "raw_market_data": "EXCLUDED",
    "workbook_controls": "TABLES_AND_AUDITED_FORMULAS_ONLY",
    "overwrite": "ATOMIC_REPLACE_AFTER_STAGED_VALIDATION",
    "transport": "LOCAL_FILESYSTEM_ONLY",
    "google_drive": "NOT_COMMISSIONED",
    "automatic_schedule": "NONE_V1",
}


def normalize(value):
    if is_dataclass(value):
        return normalize(asdict(value))
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("WO12_AWARE_TIMESTAMP_REQUIRED")
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("WO12_FINITE_DECIMAL_REQUIRED")
        return format(value, "f")
    if hasattr(value, "value"):
        return normalize(value.value)
    if isinstance(value, dict):
        return {str(key): normalize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [normalize(item) for item in value]
    return value


def encoded(value) -> bytes:
    return json.dumps(normalize(value), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value) -> str:
    return sha256(encoded(value)).hexdigest()


POLICY_CHECKSUM = digest(POLICY_RULES)


SCHEMAS = frozenset({
    "WO12_OPPORTUNITY_ORIGIN_V1",
    "WO12_OPPORTUNITY_RESET_V1",
    "WO12_DAILY_PACKAGE_V1",
    "WO12_RESEARCH_UPDATE_V1",
    "WO12_LOCAL_PUBLICATION_RECEIPT_V1",
    "WO12_LOCAL_PUBLICATION_FAILURE_V1",
})


@dataclass(frozen=True, slots=True)
class ResearchRecord:
    schema: str
    payload_json: str
    identity: str
    integrity: str
    programme_identity: str = PROGRAMME_IDENTITY
    policy_identity: str = POLICY_IDENTITY
    policy_version: str = POLICY_VERSION
    policy_checksum: str = POLICY_CHECKSUM

    def __post_init__(self) -> None:
        try:
            payload = json.loads(self.payload_json)
        except (TypeError, json.JSONDecodeError) as error:
            raise ValueError("WO12_RECORD_INVALID") from error
        material = {key: value for key, value in asdict(self).items() if key not in {"identity", "integrity"}}
        expected = digest(material)
        if (
            self.schema not in SCHEMAS
            or type(payload) is not dict
            or encoded(payload).decode() != self.payload_json
            or self.programme_identity != PROGRAMME_IDENTITY
            or (self.policy_identity, self.policy_version, self.policy_checksum)
            != (POLICY_IDENTITY, POLICY_VERSION, POLICY_CHECKSUM)
            or self.integrity != expected
            or self.identity != self.schema + "-" + expected
        ):
            raise ValueError("WO12_RECORD_INVALID")

    @property
    def data(self) -> dict[str, object]:
        return json.loads(self.payload_json)


def record(schema: str, **payload: object) -> ResearchRecord:
    material = {
        "schema": schema,
        "payload_json": encoded(payload).decode(),
        "programme_identity": PROGRAMME_IDENTITY,
        "policy_identity": POLICY_IDENTITY,
        "policy_version": POLICY_VERSION,
        "policy_checksum": POLICY_CHECKSUM,
    }
    integrity = digest(material)
    return ResearchRecord(identity=schema + "-" + integrity, integrity=integrity, **material)


def require(value: ResearchRecord, schema: str) -> dict[str, object]:
    if type(value) is not ResearchRecord or value.schema != schema:
        raise ValueError("WO12_EXACT_RECORD_REQUIRED")
    value.__post_init__()
    return value.data


def opportunity_id(canonical_subject_identity: str, origin_at: datetime) -> str:
    """Return the permanent Sponsor-readable ID from governed origin time."""
    from zoneinfo import ZoneInfo

    if not isinstance(canonical_subject_identity, str) or not canonical_subject_identity.strip():
        raise ValueError("WO12_CANONICAL_SUBJECT_REQUIRED")
    if origin_at.tzinfo is None or origin_at.utcoffset() is None:
        raise ValueError("WO12_AWARE_TIMESTAMP_REQUIRED")
    symbol = canonical_subject_identity.rsplit("-", 1)[-1]
    if not symbol or any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_&" for character in symbol):
        raise ValueError("WO12_SPONSOR_SYMBOL_INVALID")
    return f"{symbol}-{origin_at.astimezone(ZoneInfo('Asia/Kolkata')).strftime('%Y%m%d-%H%M%S')}"


def opportunity_origin(*, canonical_subject_identity: str, market_family: str,
                       session_identity: str, origin_at: datetime,
                       probable_result_identity: str, probables_run_identity: str,
                       reset_identity: str | None = None) -> ResearchRecord:
    sponsor_id = opportunity_id(canonical_subject_identity, origin_at)
    machine_material = {
        "programme_identity": PROGRAMME_IDENTITY,
        "product": "INTRADAY",
        "canonical_subject_identity": canonical_subject_identity,
        "market_session_identity": session_identity,
        "origin_at": origin_at,
        "opportunity_id": sponsor_id,
        "policy_identity": POLICY_IDENTITY,
        "policy_version": POLICY_VERSION,
        "policy_checksum": POLICY_CHECKSUM,
        "reset_identity": reset_identity,
    }
    return record(
        "WO12_OPPORTUNITY_ORIGIN_V1",
        opportunity_id=sponsor_id,
        opportunity_identity="INTRADAY-WO12-OPPORTUNITY-" + digest(machine_material),
        canonical_subject_identity=canonical_subject_identity,
        market_family=market_family,
        market_session_identity=session_identity,
        origin_at=origin_at,
        probable_result_identity=probable_result_identity,
        probables_run_identity=probables_run_identity,
        reset_identity=reset_identity,
        origin_authority="EARLIEST_RETAINED_ADMITTED_PROBABLES_EVENT",
    )


__all__ = [
    "DAY_STATES", "LOCAL_PUBLICATION_ROOT", "MONTH_STATES", "POLICY_CHECKSUM",
    "POLICY_IDENTITY", "POLICY_VERSION", "ResearchRecord", "SHEETS",
    "WORKBOOK_SCHEMA", "WORKBOOK_VERSION", "digest", "encoded",
    "opportunity_id", "opportunity_origin", "record", "require",
]
