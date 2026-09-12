"""Prospective WO-11 contracts. Historical wo11.py retains its own authority.

Sponsor/EA consolidated WO-11 order: one-lot model truth, never broker fills.
"""
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json

from kronos.intraday.wo10_futures_contract import encoded, digest, PROGRAMME
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.monitoring import ProviderMarketTick

POLICY = "KRONOS-INTRADAY-WO11-POSITION-OBSERVATION-LIFECYCLE-POLICY"
VERSION = "1.0.0"
PRICING = "WO11_WEBSOCKET_LAST_PRICE_MODEL_V1"
LATENESS = "WO11_WEBSOCKET_OBSERVATION_LATENESS_V1"
POST_ENTRY_INVALIDATION = "NOT_COMMISSIONED_V1"
FUTURE_INVALIDATION_CAPABILITY = "POST_ENTRY_ANALYTICAL_INVALIDATION_V2"
TRADING_EXIT_REASONS = frozenset({"STOP_LOSS", "TARGET", "SPONSOR_EXIT"})
TERMINAL_STATUSES = frozenset({
    "CLOSED", "SESSION_ENDED", "CONTRACT_ENDED", "CANCELLED_BEFORE_ENTRY",
    "OBSERVATION_STOPPED_BEFORE_ENTRY", "UPSTREAM_SUPERSEDED",
    "OUTCOME_AMBIGUOUS", "OUTCOME_UNAVAILABLE", "EXPIRED_BEFORE_ENTRY",
})
LATENESS_RULES = {"maximum_microseconds": 5_000_000, "inclusive": True,
                  "negative": "INVALID", "fallback": "NONE", "ordering_authority": "NONE"}
LATENESS_CHECKSUM = digest(LATENESS_RULES)
RULES = {
    "truth_classes": ["PAPER_POSITION", "PAPER_OBSERVATION"], "lots": 1,
    "live": "LIVE_POSITION_NOT_COMMISSIONED_V1", "pricing": PRICING,
    "latency_policy": LATENESS, "latency_checksum": LATENESS_CHECKSUM,
    "timing": "COMPLETED_5M_ALIGNED_PULLBACK_CANONICAL_STRICT_CLOSE",
    "entry": "FIRST_SUBSEQUENT_ELIGIBLE_FUTURE_LTP_INCLUSIVE_CROSSING",
    "nse_entry_cutoff": "15:00 Asia/Kolkata", "mcx_entry_cutoff": "23:00 Asia/Kolkata",
    "quantity_context": "WO10_SELECTED_LOTS_UPSTREAM_ONLY",
    "cardinality": "ONE_TRUTH_PER_OPPORTUNITY_AND_SEMANTIC_EXPRESSION",
    "manual_price": False, "rest_price": False, "broker_authority": False,
    "same_time_conflict": "UNORDERED_WITHOUT_GOVERNED_SEQUENCE",
    "gap": "IMMUTABLE_NO_BACKFILL_FRESH_BASELINE", "overnight": False,
    "natgas": "HELD", "reference_authority": "SUPPORTING_ONLY",
    "stop_target": "DIRECTIONAL_INCLUSIVE_ELIGIBLE_LTP_ACTUAL_PRICE",
    "trading_exit_reasons": ["STOP_LOSS", "TARGET", "SPONSOR_EXIT"],
    "exit_status_separation": "TRADING_EXIT_REASON_SEPARATE_FROM_TERMINAL_DATA_STATUS",
    "invalidation": "ORIGINAL_WO10_THESIS_DEFINITION_CONTEXT_ONLY",
    "post_entry_analytical_invalidation": POST_ENTRY_INVALIDATION,
    "future_invalidation_capability": FUTURE_INVALIDATION_CAPABILITY,
    "manual_close": "SPONSOR_REQUEST_THEN_FIRST_SUBSEQUENT_ELIGIBLE_WS_PRICE",
    "terminal": "FINAL_DOMAIN008_OR_EARLIER_CONTRACT_BOUNDARY_NO_CACHED_MARK",
    "terminal_without_price": "CLOSED_OUTCOME_UNAVAILABLE",
    "mfe": "MAX_ZERO_DIRECTION_SIGN_TIMES_PRICE_MINUS_MODEL_ENTRY",
    "mae": "MAX_ZERO_NEGATIVE_DIRECTION_SIGN_TIMES_PRICE_MINUS_MODEL_ENTRY",
    "coverage": "ELIGIBLE_SAMPLES_AND_IMMUTABLE_GAPS_NO_FULL_PATH_INFERENCE",
    "model_r": "DIRECTIONAL_RESULT_OVER_POSITIVE_INITIAL_MODEL_ENTRY_STOP_DISTANCE",
    "money": "ONE_LOT_EXACT_GOVERNED_ECONOMICS_GROSS_ONLY",
    "restart": "INERT_RESTORE_VALID_AUTHORIZATION_EXISTING_CAPABILITY_FRESH_BASELINE",
    "upstream_context": "WO09_WO10_EXACT_OPPORTUNITY_NATIVE_PLAN_RISK_LINEAGE",
    "downstream": "WO12_IMMUTABLE_HANDOFF_NO_DENOMINATOR_INFLATION",
    "notifications": "SOURCE_EVENTS_ONLY_NO_DELIVERY",
}
CHECKSUM = digest(RULES)
SCHEMAS = frozenset((
    "WO11_AUTHORIZATION_V1", "WO11_ACTION_V1", "WO11_TRACK_V1",
    "WO11_MONITORING_V1", "WO11_MARKET_OBSERVATION_V1", "WO11_TIMING_V1",
    "WO11_ENTRY_V1", "WO11_EVENT_V1", "WO11_CLOSE_REQUEST_V1",
    "WO11_EXIT_V1", "WO11_METRICS_V1", "WO11_CLOSURE_V1",
    "WO11_POINTER_V1", "WO11_WO12_HANDOFF_V1", "WO11_GAP_V1",
    "WO11_INTAKE_V1", "WO11_FUTURE_LIVE_SCHEMA_V1", "WO11_CONTRACT_BOUNDARY_V1", "WO11_AUTHORITY_CHECK_V1",
))


def aware(value):
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def instant(value):
    result = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not aware(result):
        raise ValueError("WO11_AWARE_TIMESTAMP_REQUIRED")
    return result.astimezone(timezone.utc)


def price(value):
    if isinstance(value, bool):
        raise ValueError("WO11_PRICE_INVALID")
    result = Decimal(str(value))
    if not result.is_finite() or result <= 0:
        raise ValueError("WO11_PRICE_INVALID")
    return result


@dataclass(frozen=True, slots=True)
class LifecycleRecord:
    schema: str
    payload_json: str
    identity: str
    integrity: str
    programme_identity: str = PROGRAMME
    policy_identity: str = POLICY
    policy_version: str = VERSION
    policy_checksum: str = CHECKSUM

    def __post_init__(self):
        value = json.loads(self.payload_json)
        if (self.schema not in SCHEMAS or type(value) is not dict
                or value.get("post_entry_analytical_invalidation") != POST_ENTRY_INVALIDATION
                or encoded(value).decode() != self.payload_json
                or self.programme_identity != PROGRAMME
                or (self.policy_identity, self.policy_version, self.policy_checksum) != (POLICY, VERSION, CHECKSUM)):
            raise ValueError("WO11_RECORD_CONTRACT_INVALID")
        if self.schema == "WO11_EXIT_V1" and value.get("reason") not in TRADING_EXIT_REASONS:
            raise ValueError("WO11_EXIT_REASON_INVALID")
        if self.schema in {"WO11_TRACK_V1", "WO11_CLOSURE_V1", "WO11_WO12_HANDOFF_V1"}:
            exit_reason = value.get("exit_reason")
            terminal_status = value.get("terminal_status")
            if ("exit_reason" not in value or "terminal_status" not in value
                    or exit_reason not in TRADING_EXIT_REASONS | {None}
                    or terminal_status not in TERMINAL_STATUSES | {None}):
                raise ValueError("WO11_EXIT_TERMINAL_CONTRACT_INVALID")
            exit_value = value.get("exit")
            if exit_reason is not None and (terminal_status != "CLOSED"
                    or type(exit_value) is not dict or exit_value.get("reason") != exit_reason):
                raise ValueError("WO11_EXIT_TERMINAL_CONTRACT_INVALID")
            if exit_reason is None and exit_value is not None:
                raise ValueError("WO11_EXIT_TERMINAL_CONTRACT_INVALID")
        material = {k: v for k, v in asdict(self).items() if k not in {"identity", "integrity"}}
        expected = digest(material)
        if self.integrity != expected or self.identity != self.schema + "-" + expected:
            raise ValueError("WO11_RECORD_INTEGRITY_INVALID")

    @property
    def data(self):
        return json.loads(self.payload_json)


def record(schema, **data):
    data.setdefault("post_entry_analytical_invalidation", POST_ENTRY_INVALIDATION)
    values = dict(schema=schema, payload_json=encoded(data).decode(), programme_identity=PROGRAMME,
                  policy_identity=POLICY, policy_version=VERSION, policy_checksum=CHECKSUM)
    checksum = digest(values)
    return LifecycleRecord(identity=schema + "-" + checksum, integrity=checksum, **values)


def require(item, schema):
    if type(item) is not LifecycleRecord or item.schema != schema:
        raise ValueError("WO11_EXACT_RECORD_REQUIRED")
    item.__post_init__()
    return item.data


def websocket_observation(tick, *, authorization_identity, instrument, session_identity,
                          expected_session_identity, causal_at, decision_at):
    """Retain even a valid but ineligible Provider fact; never repair its bytes.

    Timestamp comparisons retain microsecond precision. Receipt time establishes
    latency only and is never sequence authority. Session comes from DOMAIN-008.
    """
    reason = None
    lateness_us = None
    if type(tick) is not ProviderMarketTick:
        raise ValueError("WO11_PROVIDER_MARKET_TICK_REQUIRED")
    try:
        tick.__post_init__()
    except (ValueError, TypeError):
        reason = "WEBSOCKET_OBSERVATION_INVALID"
    if aware(tick.observed_at) and aware(tick.received_at):
        delta = tick.received_at - tick.observed_at
        lateness_us = (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds
        if delta < timedelta(0):
            reason = "WEBSOCKET_OBSERVATION_INVALID"
        elif reason is None and delta > timedelta(seconds=5):
            reason = "WEBSOCKET_OBSERVATION_STALE"
    else:
        reason = "WEBSOCKET_TIMESTAMP_UNAVAILABLE"
    if reason is None:
        if type(instrument) is not InstrumentRecord or tick.instrument != instrument:
            reason = "WEBSOCKET_CONTRACT_MISMATCH"
        elif not session_identity or session_identity != expected_session_identity:
            reason = "WEBSOCKET_SESSION_MISMATCH"
        elif tick.received_at > instant(decision_at) or tick.observed_at > instant(decision_at):
            reason = "WEBSOCKET_FUTURE_OBSERVATION"
        elif tick.observed_at <= instant(causal_at):
            reason = "WEBSOCKET_CAUSAL_PREREQUISITE_NOT_SATISFIED"
        elif tick.recovered:
            reason = "WEBSOCKET_RECOVERED_OBSERVATION"
        elif not all((tick.previous_interval_available, tick.session_continuous, tick.ordering_deterministic)):
            reason = "WEBSOCKET_CONTINUITY_NOT_ESTABLISHED"
        elif tick.last_price <= 0:
            reason = "WEBSOCKET_PRICE_UNAVAILABLE"
    # Invalid timestamps are represented literally, not converted into valid facts.
    raw = asdict(tick)
    for key in ("observed_at", "received_at"):
        if not aware(raw[key]):
            raw[key] = None if raw[key] is None else str(raw[key])
    return record("WO11_MARKET_OBSERVATION_V1", authorization_identity=authorization_identity,
        fact=raw, fact_identity="WO11_SOURCE_FACT-" + digest(raw), session_identity=session_identity,
        pricing_identity=PRICING, pricing_version=VERSION, lateness_identity=LATENESS,
        lateness_version=VERSION, lateness_checksum=LATENESS_CHECKSUM,
        lateness_microseconds=lateness_us, eligible=reason is None,
        reason=reason or "ELIGIBLE", causal_at=instant(causal_at), decision_at=instant(decision_at))
