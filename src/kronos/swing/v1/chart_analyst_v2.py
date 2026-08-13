"""Frozen provider-neutral contract for the bounded Swing V1 Chart Analyst V2.

The analyst observes one normal four-pane TradingView screenshot.  It returns
evidence only; KRONOS retains ownership of reconciliation, Readiness, trade
construction, ranking, and execution authority.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import json
import math
import re
from typing import Protocol, runtime_checkable

from kronos.swing.v1.models import V1Direction
from kronos.swing.run_identity import (
    LEGACY_UNBOUND_SWING_RUN_ID,
    is_swing_run_binding,
)
from kronos.swing.v1.chart_analyst_v2_integrity import (
    ChartAnalystV2OutputIntegrityError,
    validate_chart_analyst_v2_output_integrity,
)


CHART_ANALYST_V2_QUESTION_SET_ID = "KRONOS-SWING-V1-CHART-ANALYST-V2"
CHART_ANALYST_V2_QUESTION_SET_VERSION = "2.0"
CHART_ANALYST_V2_SCHEMA_ID = "KRONOS-SWING-V1-CHART-ANALYST-V2"
OPENAI_CHART_ANALYST_V2_PROVIDER_ID = "OPENAI_CHART_ANALYST_V2_PROVIDER"
CHART_ANALYST_V2_TIMEFRAMES = ("1W", "1D", "4H", "1H")
CHART_ANALYST_V2_EVIDENCE_FAMILIES = (
    "IDENTITY_READABILITY",
    "PINE_WORKSTATION",
    "MARKET_STRUCTURE",
    "IMPULSE",
    "PULLBACK",
    "CONTINUATION_PATTERN",
    "POST_IMPULSE_BEHAVIOUR",
    "POST_IMPULSE_PROGRESS",
    "CANDLESTICK_EVIDENCE",
    "BREAKOUT_BREAKDOWN_RETEST",
    "SMA20_SMA50_SMA200",
    "VOLUME_PARTICIPATION",
    "SUPPORT_RESISTANCE_BARRIERS",
    "MATURITY_EXTENSION_CHASE_RISK",
    "WEAKENING_FAILURE_EVIDENCE",
    "RESUMPTION_EVIDENCE",
    "MULTI_TIMEFRAME_ALIGNMENT",
    "PINE_VS_CHART_CONTRADICTION",
    "THESIS_BEHAVIOUR_RELATIONSHIP",
    "NEXT_OBSERVABLE_EVENT",
)


class ChartAnalystProduct(StrEnum):
    NSE = "NSE"
    MCX = "MCX"


class ChartAnalystV2FailureCode(StrEnum):
    DISABLED = "CHART_ANALYST_V2_DISABLED"
    UNAVAILABLE = "CHART_ANALYST_V2_UNAVAILABLE"
    TIMEOUT = "CHART_ANALYST_V2_TIMEOUT"
    REFUSAL = "CHART_ANALYST_V2_REFUSAL"
    INCOMPLETE = "CHART_ANALYST_V2_RESPONSE_INCOMPLETE"
    INVALID_SCHEMA = "CHART_ANALYST_V2_SCHEMA_INVALID"
    IDENTITY_MISMATCH = "CHART_ANALYST_V2_IDENTITY_MISMATCH"


class ChartAnalystV2Error(RuntimeError):
    def __init__(self, code: ChartAnalystV2FailureCode) -> None:
        if type(code) is not ChartAnalystV2FailureCode:
            raise TypeError("CHART_ANALYST_V2_FAILURE_INVALID")
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class ChartAnalystV2Thesis:
    direction: V1Direction
    setup: str

    def __post_init__(self) -> None:
        if (
            self.direction not in {V1Direction.LONG, V1Direction.SHORT}
            or not _bounded_text(self.setup, 128)
        ):
            raise ValueError("CHART_ANALYST_V2_THESIS_INVALID")


@dataclass(frozen=True, slots=True)
class ChartAnalystV2Request:
    run_identity: str
    instrument: str
    product: ChartAnalystProduct
    observation_boundary: datetime
    request_timestamp: datetime
    image_sha256: str
    content_type: str
    original_image: bytes
    thesis: ChartAnalystV2Thesis
    question_set_id: str = CHART_ANALYST_V2_QUESTION_SET_ID
    question_set_version: str = CHART_ANALYST_V2_QUESTION_SET_VERSION
    swing_analysis_run_identity: str = LEGACY_UNBOUND_SWING_RUN_ID

    def __post_init__(self) -> None:
        if (
            not _bounded_text(self.run_identity, 512)
            or not is_swing_run_binding(self.swing_analysis_run_identity)
            or not _bounded_text(self.instrument, 128)
            or type(self.product) is not ChartAnalystProduct
            or not _aware(self.observation_boundary)
            or not _aware(self.request_timestamp)
            or re.fullmatch(r"[0-9a-f]{64}", self.image_sha256) is None
            or self.content_type not in {"image/png", "image/jpeg", "image/webp"}
            or type(self.original_image) is not bytes
            or not self.original_image
            or sha256(self.original_image).hexdigest() != self.image_sha256
            or type(self.thesis) is not ChartAnalystV2Thesis
            or self.question_set_id != CHART_ANALYST_V2_QUESTION_SET_ID
            or self.question_set_version != CHART_ANALYST_V2_QUESTION_SET_VERSION
        ):
            raise ValueError("CHART_ANALYST_V2_REQUEST_INVALID")


@dataclass(frozen=True, slots=True)
class ChartAnalystV2Response:
    provider_identity: str
    model_identity: str
    request_timestamp: datetime
    run_identity: str
    analysis: dict[str, object]
    cache_hit: bool = False
    swing_analysis_run_identity: str = LEGACY_UNBOUND_SWING_RUN_ID

    def __post_init__(self) -> None:
        if (
            not _bounded_text(self.provider_identity, 128)
            or not is_swing_run_binding(self.swing_analysis_run_identity)
            or not _bounded_text(self.model_identity, 128)
            or not _aware(self.request_timestamp)
            or not _bounded_text(self.run_identity, 512)
            or type(self.analysis) is not dict
            or type(self.cache_hit) is not bool
        ):
            raise ValueError("CHART_ANALYST_V2_RESPONSE_INVALID")
        try:
            _validate_schema_value(self.analysis, chart_analyst_v2_provider_schema())
        except (TypeError, ValueError) as error:
            raise ValueError("CHART_ANALYST_V2_RESPONSE_INVALID") from error
        integrity = validate_chart_analyst_v2_output_integrity(self.analysis)
        if not integrity.accepted:
            raise ChartAnalystV2OutputIntegrityError(integrity)
        object.__setattr__(self, "analysis", deepcopy(self.analysis))

    @property
    def instrument(self) -> str:
        return str(self.analysis["instrument"])

    @property
    def product(self) -> ChartAnalystProduct:
        return ChartAnalystProduct(self.analysis["product"])

    @property
    def image_sha256(self) -> str:
        return str(self.analysis["image_sha256"])

    def validate_binding(self, request: ChartAnalystV2Request) -> None:
        if type(request) is not ChartAnalystV2Request:
            raise ChartAnalystV2Error(ChartAnalystV2FailureCode.IDENTITY_MISMATCH)
        if (
            self.run_identity != request.run_identity
            or self.swing_analysis_run_identity
            != request.swing_analysis_run_identity
            or self.instrument != request.instrument
            or self.product is not request.product
            or self.image_sha256 != request.image_sha256
            or self.analysis["question_set_id"] != request.question_set_id
            or self.analysis["question_set_version"] != request.question_set_version
        ):
            raise ChartAnalystV2Error(ChartAnalystV2FailureCode.IDENTITY_MISMATCH)


@runtime_checkable
class ChartAnalystV2Provider(Protocol):
    @property
    def provider_identity(self) -> str: ...

    def analyze(self, request: ChartAnalystV2Request) -> ChartAnalystV2Response: ...


def chart_analyst_v2_response_to_dict(
    response: ChartAnalystV2Response,
) -> dict[str, object]:
    if type(response) is not ChartAnalystV2Response:
        raise ValueError("CHART_ANALYST_V2_RESPONSE_INVALID")
    return {
        "schema_identity": CHART_ANALYST_V2_SCHEMA_ID,
        "provider_identity": response.provider_identity,
        "model_identity": response.model_identity,
        "request_timestamp": response.request_timestamp.isoformat(),
        "run_identity": response.run_identity,
        "swing_analysis_run_identity": response.swing_analysis_run_identity,
        "cache_hit": response.cache_hit,
        "analysis": deepcopy(response.analysis),
    }


def chart_analyst_v2_response_from_dict(
    value: object,
) -> ChartAnalystV2Response:
    if type(value) is not dict or set(value) not in ({
        "schema_identity",
        "provider_identity",
        "model_identity",
        "request_timestamp",
        "run_identity",
        "cache_hit",
        "analysis",
    }, {
        "schema_identity",
        "provider_identity",
        "model_identity",
        "request_timestamp",
        "run_identity",
        "swing_analysis_run_identity",
        "cache_hit",
        "analysis",
    }) or value.get("schema_identity") != CHART_ANALYST_V2_SCHEMA_ID:
        raise ValueError("CHART_ANALYST_V2_RESPONSE_INVALID")
    try:
        return ChartAnalystV2Response(
            provider_identity=value["provider_identity"],
            model_identity=value["model_identity"],
            request_timestamp=datetime.fromisoformat(value["request_timestamp"]),
            run_identity=value["run_identity"],
            swing_analysis_run_identity=value.get(
                "swing_analysis_run_identity",
                LEGACY_UNBOUND_SWING_RUN_ID,
            ),
            cache_hit=value["cache_hit"],
            analysis=value["analysis"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("CHART_ANALYST_V2_RESPONSE_INVALID") from error


def chart_analyst_v2_provider_schema() -> dict[str, object]:
    """Return the strict JSON schema sent to the provider."""

    ternary = _enum("YES", "NO", "UNDETERMINABLE")
    readability = _enum("GOOD", "PARTIAL", "POOR")
    visible_text = {"type": "string", "minLength": 1, "maxLength": 128}
    pine = _object({
        key: visible_text
        for key in (
            "trend", "quality", "acceptance", "momentum", "opportunity",
            "confidence", "decision", "need", "status",
        )
    })
    market_structure = _object({
        "structure": _enum("BULLISH", "BEARISH", "MIXED", "RANGE", "UNDETERMINABLE"),
        "higher_highs_visible": ternary,
        "higher_lows_visible": ternary,
        "lower_highs_visible": ternary,
        "lower_lows_visible": ternary,
        "structure_condition": _enum(
            "STRENGTHENING", "PRESERVED", "DETERIORATING", "REVERSING",
            "UNDETERMINABLE",
        ),
        "recent_swing_high": _number_or_null(),
        "recent_swing_low": _number_or_null(),
    })
    impulse = _object({
        "clear_impulse_present": ternary,
        "impulse_direction": _enum("BULLISH", "BEARISH", "NONE", "UNDETERMINABLE"),
        "impulse_quality": _enum("STRONG", "MODERATE", "WEAK", "UNDETERMINABLE"),
    })
    pullback = _object({
        "pullback_present": ternary,
        "pullback_quality": _enum(
            "ORDERLY", "DESTRUCTIVE", "MIXED", "NONE", "UNDETERMINABLE"
        ),
        "pullback_depth": _enum("SHALLOW", "MODERATE", "DEEP", "UNDETERMINABLE"),
        "impulse_structure_retained": ternary,
    })
    continuation = _object({
        "continuation_pattern": _enum(
            "ORDERLY_PULLBACK", "FLAG_LIKE_PAUSE", "PENNANT_LIKE_PAUSE",
            "CONSOLIDATION_AFTER_IMPULSE", "BREAKOUT_CONTINUATION",
            "BREAKDOWN_CONTINUATION", "NONE", "UNDETERMINABLE",
        ),
        "continuation_status": _enum(
            "DEVELOPING", "CONFIRMED", "FAILED", "NONE", "UNDETERMINABLE"
        ),
        "continuation_direction": _enum("BULLISH", "BEARISH", "NONE", "UNDETERMINABLE"),
    })
    candle = _object({
        "material_candle_evidence": _enum(
            "STRONG_BULLISH_CLOSE", "STRONG_BEARISH_CLOSE", "BULLISH_REJECTION",
            "BEARISH_REJECTION", "LONG_LOWER_WICK", "LONG_UPPER_WICK",
            "ENGULFING_BULLISH", "ENGULFING_BEARISH", "INSIDE_BAR_COMPRESSION",
            "INDECISION", "FAILED_CONTINUATION_CANDLE", "NONE_MATERIAL",
            "UNDETERMINABLE",
        ),
        "candle_acceptance": _enum(
            "ACCEPTED", "REJECTED", "TESTING", "MIXED", "UNDETERMINABLE"
        ),
    })
    break_retest = _object({
        "break_state": _enum("NONE", "DEVELOPING", "CONFIRMED", "FAILED", "UNDETERMINABLE"),
        "break_direction": _enum("BULLISH", "BEARISH", "NONE", "UNDETERMINABLE"),
        "close_beyond_structure": ternary,
        "returned_inside_range": _enum("YES", "NO", "NOT_APPLICABLE", "UNDETERMINABLE"),
        "retest_state": _enum("NONE", "DEVELOPING", "HELD", "FAILED", "UNDETERMINABLE"),
    })
    moving_average = _object({
        "price_relation": _enum("ABOVE", "BELOW", "INTERACTING", "UNDETERMINABLE"),
        "slope": _enum("RISING", "FALLING", "FLAT", "UNDETERMINABLE"),
        "role": _enum("SUPPORT", "RESISTANCE", "NEUTRAL", "UNDETERMINABLE"),
    })
    moving_averages = _object({key: moving_average for key in ("SMA20", "SMA50", "SMA200")})
    volume = _object({
        "volume_context": _enum("SUPPORTIVE", "WEAK", "MIXED", "UNDETERMINABLE"),
        "volume_with_impulse": _enum(
            "EXPANDING", "CONTRACTING", "NEUTRAL", "NOT_APPLICABLE", "UNDETERMINABLE"
        ),
        "volume_during_pullback": _enum(
            "CONTRACTING", "EXPANDING", "NEUTRAL", "NOT_APPLICABLE", "UNDETERMINABLE"
        ),
        "volume_on_break": _enum("SUPPORTIVE", "WEAK", "NOT_APPLICABLE", "UNDETERMINABLE"),
        "participation_deteriorating": ternary,
    })
    barrier = _object({
        "nearest_visible_support": _level(),
        "nearest_visible_resistance": _level(),
        "major_swing_barrier_present": ternary,
        "ma_or_reference_barrier_present": ternary,
        "barrier_direction": _enum(
            "ABOVE_PRICE", "BELOW_PRICE", "BOTH", "NONE", "UNDETERMINABLE"
        ),
        "visible_room_for_continuation": _enum("GOOD", "LIMITED", "BLOCKED", "UNDETERMINABLE"),
    })
    timeframe = _object({
        "readability": readability,
        "pine_workstation": pine,
        "market_structure": market_structure,
        "impulse": impulse,
        "pullback": pullback,
        "continuation_pattern": continuation,
        "post_impulse_behaviour": _enum(
            "IMMEDIATE_CONTINUATION", "TIGHT_CONSOLIDATION", "SIDEWAYS_DIGESTION",
            "SHALLOW_PULLBACK", "ORDERLY_PULLBACK", "DEEP_PULLBACK",
            "DESTRUCTIVE_PULLBACK", "FAILED_IMPULSE", "NONE", "UNDETERMINABLE",
        ),
        "post_impulse_progress": _enum(
            "CONTINUING", "PAUSED", "STALLING", "REVERSING", "FAILED", "UNDETERMINABLE"
        ),
        "candlestick_evidence": candle,
        "breakout_breakdown_retest": break_retest,
        "moving_averages": moving_averages,
        "volume_participation": volume,
        "support_resistance_barriers": barrier,
        "maturity_extension_chase_risk": _object({
            "move_maturity": _enum(
                "EARLY", "DEVELOPING", "MATURE", "EXTENDED", "EXHAUSTION_RISK",
                "UNDETERMINABLE",
            ),
            "chase_risk": _enum("LOW", "MODERATE", "HIGH", "UNDETERMINABLE"),
        }),
        "weakening_failure_evidence": _enum(
            "NONE", "LOSS_OF_PROGRESS", "REPEATED_REJECTION", "VOLUME_DETERIORATION",
            "STRUCTURAL_DAMAGE", "FAILED_BREAK", "MULTIPLE", "UNDETERMINABLE",
        ),
        "resumption_evidence": _enum(
            "STRONG", "DEVELOPING", "EARLY", "NONE", "FAILED", "UNDETERMINABLE"
        ),
    })
    short_text = {"type": "string", "minLength": 1, "maxLength": 256}
    return _object({
        "instrument": {"type": "string", "minLength": 1, "maxLength": 128},
        "product": _enum(*(item.value for item in ChartAnalystProduct)),
        "image_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "question_set_id": {"type": "string", "const": CHART_ANALYST_V2_QUESTION_SET_ID},
        "question_set_version": {
            "type": "string", "const": CHART_ANALYST_V2_QUESTION_SET_VERSION,
        },
        "expected_timeframes_present": _object({key: ternary for key in CHART_ANALYST_V2_TIMEFRAMES}),
        "overall_image_readability": readability,
        "timeframes": _object({key: timeframe for key in CHART_ANALYST_V2_TIMEFRAMES}),
        "multi_timeframe": _object({
            "timeframe_alignment": _enum(
                "ALIGNED_BULLISH", "ALIGNED_BEARISH", "PARTIALLY_ALIGNED",
                "CONFLICTING", "UNDETERMINABLE",
            ),
            "dominant_higher_timeframe_direction": _enum(
                "BULLISH", "BEARISH", "MIXED", "UNDETERMINABLE"
            ),
            "lower_timeframe_state": _enum(
                "CONFIRMING", "DEVELOPING", "CONFLICTING", "UNDETERMINABLE"
            ),
            "key_timeframe_contradiction": short_text,
        }),
        "pine_vs_chart": _object({
            "pine_vs_visible_chart": _enum("AGREE", "PARTIAL", "CONTRADICT", "UNDETERMINABLE"),
            "contradiction_reason": short_text,
        }),
        "thesis_behaviour": _object({
            "relationship": _enum(
                "SUPPORTS_THESIS", "SUPPORTS_BUT_STALLED", "NEUTRAL_TO_THESIS",
                "WEAKENS_THESIS", "CONTRADICTS_THESIS", "UNDETERMINABLE",
            ),
            "thesis_behaviour_reason": short_text,
        }),
        "next_observable_event": _object({"what_needs_to_happen_next": short_text}),
        "overall_observation": _object({
            "setup_visually_exists": ternary,
            "setup_direction": _enum("BULLISH", "BEARISH", "NONE", "UNDETERMINABLE"),
            "setup_phase": _enum(
                "DEVELOPING", "MATURE", "EXTENDED", "WEAKENING", "FAILED", "NONE",
                "UNDETERMINABLE",
            ),
            "most_material_positive_evidence": short_text,
            "most_material_negative_evidence": short_text,
            "overall_determinability": readability,
        }),
    })


def canonical_chart_analyst_v2_json(value: dict[str, object]) -> str:
    _validate_schema_value(value, chart_analyst_v2_provider_schema())
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _object(properties: dict[str, object]) -> dict[str, object]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _enum(*values: str) -> dict[str, object]:
    return {"type": "string", "enum": list(values)}


def _number_or_null() -> dict[str, object]:
    return {"anyOf": [{"type": "number"}, {"type": "null"}]}


def _level() -> dict[str, object]:
    return {
        "anyOf": [
            {"type": "number"},
            _enum("NONE", "UNDETERMINABLE"),
        ]
    }


def _validate_schema_value(value: object, schema: object) -> None:
    if type(schema) is not dict:
        raise TypeError("CHART_ANALYST_V2_SCHEMA_INVALID")
    alternatives = schema.get("anyOf")
    if type(alternatives) is list:
        valid = 0
        for candidate in alternatives:
            try:
                _validate_schema_value(value, candidate)
            except (TypeError, ValueError):
                continue
            valid += 1
        if valid != 1:
            raise ValueError("CHART_ANALYST_V2_SCHEMA_VALUE_INVALID")
        return
    expected = schema.get("type")
    if expected == "object":
        if type(value) is not dict:
            raise TypeError("CHART_ANALYST_V2_SCHEMA_VALUE_INVALID")
        properties = schema.get("properties")
        required = schema.get("required")
        if type(properties) is not dict or type(required) is not list:
            raise TypeError("CHART_ANALYST_V2_SCHEMA_INVALID")
        if set(value) != set(required) or set(value) != set(properties):
            raise ValueError("CHART_ANALYST_V2_SCHEMA_VALUE_INVALID")
        for key, child_schema in properties.items():
            _validate_schema_value(value[key], child_schema)
        return
    if expected == "string":
        if type(value) is not str:
            raise TypeError("CHART_ANALYST_V2_SCHEMA_VALUE_INVALID")
        if "const" in schema and value != schema["const"]:
            raise ValueError("CHART_ANALYST_V2_SCHEMA_VALUE_INVALID")
        if "enum" in schema and value not in schema["enum"]:
            raise ValueError("CHART_ANALYST_V2_SCHEMA_VALUE_INVALID")
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", 10_000):
            raise ValueError("CHART_ANALYST_V2_SCHEMA_VALUE_INVALID")
        if "pattern" in schema and re.fullmatch(str(schema["pattern"]), value) is None:
            raise ValueError("CHART_ANALYST_V2_SCHEMA_VALUE_INVALID")
        return
    if expected == "number":
        if type(value) not in {int, float} or not math.isfinite(float(value)):
            raise TypeError("CHART_ANALYST_V2_SCHEMA_VALUE_INVALID")
        return
    if expected == "null":
        if value is not None:
            raise TypeError("CHART_ANALYST_V2_SCHEMA_VALUE_INVALID")
        return
    raise TypeError("CHART_ANALYST_V2_SCHEMA_INVALID")


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _bounded_text(value: object, maximum: int) -> bool:
    return type(value) is str and bool(value.strip()) and len(value) <= maximum


__all__ = [
    "CHART_ANALYST_V2_EVIDENCE_FAMILIES",
    "CHART_ANALYST_V2_QUESTION_SET_ID",
    "CHART_ANALYST_V2_QUESTION_SET_VERSION",
    "CHART_ANALYST_V2_SCHEMA_ID",
    "CHART_ANALYST_V2_TIMEFRAMES",
    "OPENAI_CHART_ANALYST_V2_PROVIDER_ID",
    "ChartAnalystProduct",
    "ChartAnalystV2Error",
    "ChartAnalystV2FailureCode",
    "ChartAnalystV2Provider",
    "ChartAnalystV2Request",
    "ChartAnalystV2Response",
    "ChartAnalystV2Thesis",
    "canonical_chart_analyst_v2_json",
    "chart_analyst_v2_provider_schema",
    "chart_analyst_v2_response_from_dict",
    "chart_analyst_v2_response_to_dict",
]
