"""Deterministic post-extraction integrity checks for Chart Analyst V2.

The provider schema deliberately keeps visible Pine transcription fields as
bounded strings because one screenshot may contain two comparison columns.
This module validates those strings after extraction without interpreting or
remapping their analytical meaning.  It also rejects required bounded prose
that is mechanically incomplete at the schema boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re


_TIMEFRAMES = ("1W", "1D", "4H", "1H")
_PINE_FIELDS = (
    "trend",
    "quality",
    "acceptance",
    "momentum",
    "opportunity",
    "confidence",
    "decision",
    "need",
    "status",
)
_UNAVAILABLE_TOKENS = frozenset({
    "-",
    "--",
    "—",
    "N/A",
    "NA",
    "NONE",
    "NOT_PRESENT",
    "UNAVAILABLE",
    "UNDETERMINABLE",
    "UNREADABLE",
})
_PINE_VOCABULARIES = {
    "trend": frozenset({"BULLISH", "BEARISH", "NEUTRAL", "CONFLICTED"}),
    "quality": frozenset({"EXCELLENT", "HEALTHY", "WEAK", "EXTENDED", "NEUTRAL"}),
    "acceptance": frozenset({
        "STRONG ACCEPTANCE", "ACCEPTANCE", "ACCEPTED", "TESTING", "REJECTED", "NEUTRAL",
    }),
    "momentum": frozenset({"BUILDING", "STRONG", "NORMAL", "WEAKENING", "EXHAUSTED"}),
    "opportunity": frozenset({"GOOD", "LIMITED"}),
    "confidence": frozenset({
        "EXCEPTIONAL", "HIGH CONFIDENCE", "DEVELOPING", "LOW CONFIDENCE", "AVOID",
    }),
    "decision": frozenset({
        "AVOID", "WAIT", "WATCH LONG", "WATCH SHORT", "BUY READY", "SELL READY",
        "BUY NOW", "SELL NOW", "NO SETUP", "BLOCKED",
    }),
    "need": frozenset({
        "WAIT FOR PULLBACK",
        "HIGHER TF CONFIRMATION",
        "BREAKOUT FROM COMPRESSION",
        "SETUP READINESS",
        "MARKET DATA",
        "COMEX DAILY DATA",
        "COMEX DAILY TREND ALIGNMENT",
        "COMEX 4H DATA",
        "WAIT FOR COMEX 4H BREAKOUT",
        "COMEX 4H PRICE ACCEPTANCE",
        "COMEX 1H DATA",
        "COMEX 1H MOMENTUM",
        "SWITCH TO MCX 1H CHART",
        "MCX 1H PRICE ACCEPTANCE",
        "MCX 1H CONFIDENCE BUILDING",
        "MCX 1H BREAKOUT",
        "MCX 1H MOMENTUM",
        "MCX 1H CONFIRMATION",
        "OPPORTUNITY BUILDING",
        "REVIEW GATE CLEARS",
        "PRICE ACCEPTANCE",
        "CONFIDENCE BUILDING",
        "DIRECTIONAL ALIGNMENT",
        "TREND ALIGNED",
        "ACCEPTANCE CONFIRMED",
        # Frozen observed workstation abbreviations retained as transcription,
        # not interpreted as analytical states.
        "ENTRY COMPLETES",
        "UP READINESS",
        "CONFIRMATION",
    }),
    "status": frozenset({"DATA OK", "DATA WAIT", "DATA DEGRADED", "WAITING"}),
}
_PRODUCT_DECISION_VOCABULARIES = {
    "MCX": _PINE_VOCABULARIES["decision"],
    "NSE": _PINE_VOCABULARIES["decision"] - {"BUY NOW", "SELL NOW"},
}
_COMPOSITE = re.compile(
    r"^(?P<left_label>PROD|ANALYTICAL)\s*[:=]\s*(?P<left>.+?)\s*"
    r"(?:;|\|)\s*(?P<right_label>V2|NOT PROD)\s*[:=]\s*(?P<right>.+)$",
    re.IGNORECASE,
)
_CONFIDENCE_SCORE = re.compile(
    r"^(?:100|[0-9]{1,2})\s*-\s*"
    r"(?:EXCEPTIONAL|HIGH CONFIDENCE|DEVELOPING|LOW CONFIDENCE|AVOID)$"
)
_REQUIRED_TEXT_PATHS = (
    ("multi_timeframe", "key_timeframe_contradiction"),
    ("pine_vs_chart", "contradiction_reason"),
    ("thesis_behaviour", "thesis_behaviour_reason"),
    ("next_observable_event", "what_needs_to_happen_next"),
    ("overall_observation", "most_material_positive_evidence"),
    ("overall_observation", "most_material_negative_evidence"),
)
_COMPLETE_TEXT_SENTINELS = frozenset({"UNDETERMINABLE", "UNREADABLE", "NOT_PRESENT"})
_DANGLING_WORDS = frozenset({
    "A", "AN", "AND", "AS", "AT", "BECAUSE", "BEFORE", "BUT", "BY", "FOR", "FROM",
    "IF", "IN", "NEAR", "OF", "ON", "OR", "OVER", "POST", "THAN", "THAT", "THE",
    "THROUGH", "TO", "UNDER", "WHEN", "WHERE", "WHICH", "WHILE", "WITH", "WITHOUT",
})


class ChartAnalystV2IntegrityFailureCode(StrEnum):
    INVALID_TRANSCRIPTION = "INVALID_TRANSCRIPTION"
    INVALID_INCOMPLETE_TEXT = "INVALID_INCOMPLETE_TEXT"


@dataclass(frozen=True, slots=True)
class ChartAnalystV2IntegrityCheck:
    field_path: str
    raw_value: str
    normalized_value: tuple[str, ...]
    validation_result: str
    failure_code: ChartAnalystV2IntegrityFailureCode | None = None
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        if (
            not self.field_path
            or type(self.raw_value) is not str
            or type(self.normalized_value) is not tuple
            or not self.normalized_value
            or self.validation_result not in {"ACCEPTED", "REJECTED"}
            or (self.validation_result == "ACCEPTED" and (
                self.failure_code is not None or self.failure_reason is not None
            ))
            or (self.validation_result == "REJECTED" and (
                type(self.failure_code) is not ChartAnalystV2IntegrityFailureCode
                or not self.failure_reason
            ))
        ):
            raise ValueError("CHART_ANALYST_V2_INTEGRITY_CHECK_INVALID")


@dataclass(frozen=True, slots=True)
class ChartAnalystV2IntegrityReport:
    checks: tuple[ChartAnalystV2IntegrityCheck, ...]

    def __post_init__(self) -> None:
        if not self.checks or any(
            type(check) is not ChartAnalystV2IntegrityCheck for check in self.checks
        ):
            raise ValueError("CHART_ANALYST_V2_INTEGRITY_REPORT_INVALID")

    @property
    def accepted(self) -> bool:
        return all(check.validation_result == "ACCEPTED" for check in self.checks)

    @property
    def failures(self) -> tuple[ChartAnalystV2IntegrityCheck, ...]:
        return tuple(
            check for check in self.checks if check.validation_result == "REJECTED"
        )


class ChartAnalystV2OutputIntegrityError(ValueError):
    """Schema-valid model output failed deterministic acceptance checks."""

    def __init__(self, report: ChartAnalystV2IntegrityReport) -> None:
        if type(report) is not ChartAnalystV2IntegrityReport or report.accepted:
            raise ValueError("CHART_ANALYST_V2_INTEGRITY_ERROR_INVALID")
        self.report = report
        super().__init__("CHART_ANALYST_V2_OUTPUT_INTEGRITY_INVALID")


def validate_chart_analyst_v2_output_integrity(
    analysis: dict[str, object],
) -> ChartAnalystV2IntegrityReport:
    """Validate schema-shaped V2 output without altering its raw values."""

    if type(analysis) is not dict:
        raise TypeError("CHART_ANALYST_V2_OUTPUT_INTEGRITY_INPUT_INVALID")
    checks: list[ChartAnalystV2IntegrityCheck] = []
    try:
        product = analysis["product"]
        if product not in _PRODUCT_DECISION_VOCABULARIES:
            raise TypeError
        timeframes = analysis["timeframes"]
        if type(timeframes) is not dict:
            raise TypeError
        for timeframe in _TIMEFRAMES:
            timeframe_value = timeframes[timeframe]
            if type(timeframe_value) is not dict:
                raise TypeError
            workstation = timeframe_value["pine_workstation"]
            if type(workstation) is not dict:
                raise TypeError
            for field in _PINE_FIELDS:
                raw_value = workstation[field]
                if type(raw_value) is not str:
                    raise TypeError
                checks.append(_pine_check(timeframe, field, raw_value, product))
        for path in _REQUIRED_TEXT_PATHS:
            container = analysis[path[0]]
            if type(container) is not dict or type(container[path[1]]) is not str:
                raise TypeError
            checks.append(_required_text_check(path, container[path[1]]))
    except (KeyError, TypeError):
        raise TypeError("CHART_ANALYST_V2_OUTPUT_INTEGRITY_INPUT_INVALID") from None
    return ChartAnalystV2IntegrityReport(tuple(checks))


def chart_analyst_v2_integrity_report_to_dict(
    report: ChartAnalystV2IntegrityReport,
) -> dict[str, object]:
    if type(report) is not ChartAnalystV2IntegrityReport:
        raise TypeError("CHART_ANALYST_V2_INTEGRITY_REPORT_INVALID")
    return {
        "validation_result": "ACCEPTED" if report.accepted else "REJECTED",
        "checks": [
            {
                "field_path": check.field_path,
                "raw_value": check.raw_value,
                "normalized_value": list(check.normalized_value),
                "validation_result": check.validation_result,
                "failure_code": (
                    check.failure_code.value if check.failure_code is not None else None
                ),
                "failure_reason": check.failure_reason,
            }
            for check in report.checks
        ],
    }


def _pine_check(
    timeframe: str,
    field: str,
    raw_value: str,
    product: object,
) -> ChartAnalystV2IntegrityCheck:
    values = _pine_values(raw_value)
    path = f"timeframes.{timeframe}.pine_workstation.{field}"
    if values is None:
        return _rejected(
            path,
            raw_value,
            (raw_value.strip(),),
            ChartAnalystV2IntegrityFailureCode.INVALID_TRANSCRIPTION,
            "PINE_FIELD_COMPOSITE_INVALID",
        )
    invalid = tuple(
        value for value in values
        if not _pine_value_permitted(field, value, str(product))
    )
    if not invalid:
        return ChartAnalystV2IntegrityCheck(path, raw_value, values, "ACCEPTED")
    displacement = any(
        _belongs_to_other_pine_field(field, value) for value in invalid
    )
    return _rejected(
        path,
        raw_value,
        values,
        ChartAnalystV2IntegrityFailureCode.INVALID_TRANSCRIPTION,
        (
            "PINE_FIELD_SEMANTIC_DISPLACEMENT"
            if displacement
            else "PINE_FIELD_VALUE_OUTSIDE_VOCABULARY"
        ),
    )


def _pine_values(raw_value: str) -> tuple[str, ...] | None:
    stripped = raw_value.strip()
    if not stripped:
        return None
    composite = _COMPOSITE.fullmatch(stripped)
    if composite is not None:
        values = (composite.group("left").strip(), composite.group("right").strip())
        return values if all(values) else None
    if re.match(r"^(?:PROD|ANALYTICAL|V2|NOT PROD)\s*[:=]", stripped, re.IGNORECASE):
        return None
    return (stripped,)


def _pine_value_permitted(field: str, value: str, product: str) -> bool:
    normalized = value.strip().upper()
    if normalized in _UNAVAILABLE_TOKENS:
        return True
    if field == "confidence" and _CONFIDENCE_SCORE.fullmatch(normalized) is not None:
        return True
    if field == "decision":
        return normalized in _PRODUCT_DECISION_VOCABULARIES[product]
    return normalized in _PINE_VOCABULARIES[field]


def _belongs_to_other_pine_field(field: str, value: str) -> bool:
    normalized = value.strip().upper()
    if normalized in _UNAVAILABLE_TOKENS:
        return False
    return any(
        other != field and normalized in vocabulary
        for other, vocabulary in _PINE_VOCABULARIES.items()
    )


def _required_text_check(
    path: tuple[str, str],
    raw_value: str,
) -> ChartAnalystV2IntegrityCheck:
    field_path = ".".join(path)
    normalized = raw_value.strip()
    accepted = ChartAnalystV2IntegrityCheck(
        field_path,
        raw_value,
        (normalized,),
        "ACCEPTED",
    )
    if normalized.upper() in _COMPLETE_TEXT_SENTINELS:
        return accepted
    reason = _incomplete_text_reason(normalized)
    if reason is None:
        return accepted
    return _rejected(
        field_path,
        raw_value,
        (normalized,),
        ChartAnalystV2IntegrityFailureCode.INVALID_INCOMPLETE_TEXT,
        reason,
    )


def _incomplete_text_reason(value: str) -> str | None:
    if "\ufffd" in value:
        return "TEXT_CONTAINS_REPLACEMENT_CHARACTER"
    if value.endswith(("...", "…", "-", "–", "—", "/", "\\", ",", ";", ":")):
        return "TEXT_ENDS_WITH_INCOMPLETE_MARKER"
    final_word = re.search(r"([A-Za-z]+)$", value)
    if final_word is not None and final_word.group(1).upper() in _DANGLING_WORDS:
        return "TEXT_ENDS_WITH_DANGLING_WORD"
    if len(value) >= 256 and not value.endswith((".", "?", "!", ")", "]", '"', "'")):
        return "TEXT_REACHED_BOUNDARY_WITHOUT_TERMINATOR"
    return None


def _rejected(
    field_path: str,
    raw_value: str,
    normalized_value: tuple[str, ...],
    failure_code: ChartAnalystV2IntegrityFailureCode,
    failure_reason: str,
) -> ChartAnalystV2IntegrityCheck:
    return ChartAnalystV2IntegrityCheck(
        field_path,
        raw_value,
        normalized_value,
        "REJECTED",
        failure_code,
        failure_reason,
    )


__all__ = [
    "ChartAnalystV2IntegrityCheck",
    "ChartAnalystV2IntegrityFailureCode",
    "ChartAnalystV2IntegrityReport",
    "ChartAnalystV2OutputIntegrityError",
    "chart_analyst_v2_integrity_report_to_dict",
    "validate_chart_analyst_v2_output_integrity",
]
