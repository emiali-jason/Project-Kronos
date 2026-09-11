"""ADR-0039: prospective Futures-only immutable contracts, not execution authority."""
from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from hashlib import sha256
import json

PROGRAMME = "KRONOS-INTRADAY-PROSPECTIVE-PROGRAMME-V2"
VERSION = "1.0.0"
POLICY = "KRONOS-INTRADAY-WO10-FUTURES-ONLY-POLICY"
# Logical boundary, not a fabricated runtime activation timestamp.
LEGACY_BOUNDARY = "ADR-0039:EXPLICIT_PROSPECTIVE_WO10_OPERATION"
BOUNDARY = "ADR-0042:EXPLICIT_PROSPECTIVE_WO10_ADVISORY_OPERATION"
POLICY_VERSION = "1.1.0"
LEGACY_POLICY_RULES = {
    "scope": "FUTURES_ONLY", "readiness": "EXACT_CURRENT_FIVE_OF_FIVE_NOW",
    "now_ttl_seconds": 300, "plan_ttl_seconds": 300, "quote_ttl_seconds": 30,
    "selection_ttl_seconds": 30, "cross_leg_skew_seconds": 5,
    "expiry": {"NSE": "STRICTLY_AFTER_TRADING_DATE", "MCX": "EXISTING_EXACT_ACTIVE_AUTHORITY"}, "automatic_retries": 0,
    "quote_requests": 1, "request_timeout_seconds": 7,
    "sizing": "RISK_ONLY", "broker_margin_authority": False,
    "options": "NOT_COMMISSIONED_V1", "natgas": "HELD",
    "long_rounding": ["UP", "DOWN", "DOWN"],
    "short_rounding": ["DOWN", "UP", "UP"],
    "minimum_rr": None, "oi_baseline": "SESSION_FIRST_OBSERVED_OI_BASELINE_V1",
    "selection": ["SELECTED_FUTURE", "NONE"], "broker_authority": False,
}


def normalize(value):
    if is_dataclass(value):
        return normalize(asdict(value))
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("WO10_AWARE_TIMESTAMP_REQUIRED")
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("WO10_FINITE_DECIMAL_REQUIRED")
        return format(value, "f")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: normalize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [normalize(item) for item in value]
    return value


def encoded(value):
    return json.dumps(normalize(value), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return sha256(encoded(value)).hexdigest()


LEGACY_CHECKSUM = digest(LEGACY_POLICY_RULES)
POLICY_RULES = dict(LEGACY_POLICY_RULES, sizing="ADVISORY_REFERENCE_ONLY",
    risk_unavailable="ADVISORY_NOT_VETO", quantity="POSITIVE_WHOLE_LOTS_NO_RISK_CAP")
CHECKSUM = digest(POLICY_RULES)
SCHEMAS = frozenset("""WO10_FROM_WO09_CONSTRUCTION_ADAPTER_V1
WO10_CANONICAL_TRADE_PLAN_V1 WO10_FUTURES_MARKET_SNAPSHOT_V1
WO10_FUTURE_EXPRESSION_V1 WO10_RISK_FACT_V1 WO10_RISK_PERMISSION_V1
WO10_SPONSOR_COMPARISON_V1 WO10_SPONSOR_SELECTION_V1
WO10_SELECTED_TRADE_HANDOFF_V1 WO10_ACQUISITION_OPERATION_V1
WO10_FUTURE_CONTRACT_V1 WO10_CURRENT_POINTER_V1 WO10_OPPORTUNITY_V1
WO10_RISK_CONFIGURATION_V1 WO10_RISK_REFERENCE_V1 WO10_RISK_ADVISORY_V1 WO10_CONSTRUCTION_REQUEST_V1 WO10_CONSTRUCTION_OPERATION_V1 WO10_CONSTRUCTION_UNAVAILABLE_V1 SESSION_FIRST_OBSERVED_OI_BASELINE_V1""".split())


@dataclass(frozen=True, slots=True)
class Record:
    """Canonical immutable payload; callers receive detached decoded projections."""
    schema: str
    payload_json: str
    identity: str
    integrity: str
    programme_identity: str = PROGRAMME
    programme_version: str = VERSION
    policy_identity: str = POLICY
    policy_version: str = POLICY_VERSION
    policy_checksum: str = CHECKSUM
    effective_authority_boundary: str = BOUNDARY

    def __post_init__(self):
        data = json.loads(self.payload_json)
        if (self.schema not in SCHEMAS or not isinstance(data, dict)
                or encoded(data).decode() != self.payload_json
                or self.programme_identity != PROGRAMME or self.programme_version != VERSION
                or self.policy_identity != POLICY
                or (self.policy_version, self.policy_checksum, self.effective_authority_boundary) not in {
                    (POLICY_VERSION, CHECKSUM, BOUNDARY), (VERSION, LEGACY_CHECKSUM, LEGACY_BOUNDARY)}):
            raise ValueError("WO10_RECORD_CONTRACT_INVALID")
        expected = digest(self.material())
        if self.integrity != expected or self.identity != self.schema + "-" + expected:
            raise ValueError("WO10_RECORD_INTEGRITY_INVALID")

    @property
    def data(self):
        return json.loads(self.payload_json)

    def material(self):
        return {k: v for k, v in asdict(self).items() if k not in {"identity", "integrity"}}


def record(schema, **data):
    if schema in {"WO10_RISK_PERMISSION_V1", "WO10_RISK_CONFIGURATION_V1"}:
        raise ValueError("WO10_HISTORICAL_SCHEMA_NOT_COMMISSIONED")
    material = dict(schema=schema, payload_json=encoded(data).decode(),
                    programme_identity=PROGRAMME, programme_version=VERSION,
                    policy_identity=POLICY, policy_version=POLICY_VERSION,
                    policy_checksum=CHECKSUM, effective_authority_boundary=BOUNDARY)
    integrity = digest(material)
    return Record(identity=schema + "-" + integrity, integrity=integrity, **material)


def require(value, schema):
    if type(value) is not Record or value.schema != schema:
        raise ValueError("WO10_RECORD_TYPE_INVALID")
    value.__post_init__()
    if value.policy_version != POLICY_VERSION or value.policy_checksum != CHECKSUM:
        raise ValueError("WO10_HISTORICAL_AUTHORITY_NOT_CURRENT")
    return value.data


def number(value, *, positive=False):
    if isinstance(value, bool) or value is None:
        raise ValueError("WO10_NUMBER_INVALID")
    result = Decimal(str(value))
    if not result.is_finite() or (positive and result <= 0):
        raise ValueError("WO10_NUMBER_INVALID")
    return result


def moment(value):
    result = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(result, datetime) or result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("WO10_AWARE_TIMESTAMP_REQUIRED")
    return result.astimezone(timezone.utc)


def fresh(value, now, seconds):
    return 0 <= (moment(now) - moment(value)).total_seconds() <= seconds
