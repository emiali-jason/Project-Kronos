"""Intraday-owned Opening NIFTY relative-context contracts.

The arithmetic copies the proven Swing pattern, while canonical identity,
session alignment, evidence roles, and consequences remain Intraday-owned.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json
from typing import Mapping, Sequence

from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.historical_semantic import GovernedHistoricalCandlePayload


NIFTY_CANONICAL_IDENTITY = "NSE-INDEX-NIFTY"
NIFTY_RELATIVE_CONTEXT_FACT_IDENTITY = (
    "KRONOS-INTRADAY-NIFTY-RELATIVE-CONTEXT-FACT-V1"
)
NIFTY_RELATIVE_CONTEXT_EVIDENCE_IDENTITY = (
    "KRONOS-INTRADAY-NIFTY-RELATIVE-CONTEXT-EVIDENCE-V1"
)
NIFTY_RELATIVE_CONTEXT_VERSION = "1.0.0"
NIFTY_RELATIVE_CONTEXT_POLICY = (
    "KRONOS-INTRADAY-NIFTY-RELATIVE-CONTEXT-POLICY-V1"
)


class NiftyRelativeContextError(ValueError):
    """Sanitized boundary or integrity failure."""


class NiftyApplicability(StrEnum):
    APPLICABLE = "APPLICABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class NiftyRelativeState(StrEnum):
    OUTPERFORMING = "OUTPERFORMING"
    UNDERPERFORMING = "UNDERPERFORMING"
    EQUAL = "EQUAL"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class NiftyRelationship(StrEnum):
    SUPPORTING = "SUPPORTING"
    CONFLICTING = "CONFLICTING"
    INFORMATIONAL = "INFORMATIONAL"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class NiftyFailure(StrEnum):
    BENCHMARK_FACT_UNAVAILABLE = "BENCHMARK_FACT_UNAVAILABLE"
    BENCHMARK_IDENTITY_INVALID = "BENCHMARK_IDENTITY_INVALID"
    BOUNDARY_MISMATCH = "BOUNDARY_MISMATCH"
    SOURCE_INTEGRITY_INVALID = "SOURCE_INTEGRITY_INVALID"
    SUBJECT_FACT_UNAVAILABLE = "SUBJECT_FACT_UNAVAILABLE"
    BENCHMARK_SELF_COMPARISON_NOT_APPLICABLE = (
        "BENCHMARK_SELF_COMPARISON_NOT_APPLICABLE"
    )
    NOT_APPLICABLE_MARKET = "NOT_APPLICABLE_MARKET"


class RelativeProgressionState(StrEnum):
    IMPROVING = "IMPROVING"
    DETERIORATING = "DETERIORATING"
    FLAT = "FLAT"
    MIXED = "MIXED"


@dataclass(frozen=True, slots=True)
class NiftyRelativeContextFact:
    fact_identity: str
    canonical_subject_identity: str
    benchmark_identity: str
    analysis_boundary: datetime
    applicability: NiftyApplicability
    state: NiftyRelativeState
    reason: NiftyFailure | None
    timeframe: IntradayTimeframe | None
    interval_start: datetime | None
    interval_end: datetime | None
    subject_market_session_identity: str | None
    benchmark_market_session_identity: str | None
    subject_candle_identity: str | None
    benchmark_candle_identity: str | None
    subject_session_open: Decimal | None
    benchmark_session_open: Decimal | None
    subject_close: Decimal | None
    benchmark_close: Decimal | None
    subject_return_pct: Decimal | None
    benchmark_return_pct: Decimal | None
    relative_return_pct: Decimal | None
    source_provenance: tuple[str, ...]
    integrity_identity: str
    policy_identity: str = NIFTY_RELATIVE_CONTEXT_POLICY
    policy_version: str = NIFTY_RELATIVE_CONTEXT_VERSION
    schema_identity: str = NIFTY_RELATIVE_CONTEXT_FACT_IDENTITY
    schema_version: str = NIFTY_RELATIVE_CONTEXT_VERSION

    def __post_init__(self) -> None:
        values = asdict(self)
        values.pop("fact_identity")
        values.pop("integrity_identity")
        numerical = (
            self.subject_session_open,
            self.benchmark_session_open,
            self.subject_close,
            self.benchmark_close,
            self.subject_return_pct,
            self.benchmark_return_pct,
            self.relative_return_pct,
        )
        identities = (
            self.subject_market_session_identity,
            self.benchmark_market_session_identity,
            self.subject_candle_identity,
            self.benchmark_candle_identity,
        )
        boundaries = (self.interval_start, self.interval_end)
        available = self.state in {
            NiftyRelativeState.OUTPERFORMING,
            NiftyRelativeState.UNDERPERFORMING,
            NiftyRelativeState.EQUAL,
        }
        if (
            not self.fact_identity.startswith("INTRADAY-NIFTY-RELATIVE-FACT-")
            or not _texts((self.canonical_subject_identity, self.benchmark_identity))
            or self.benchmark_identity != NIFTY_CANONICAL_IDENTITY
            or not _aware(self.analysis_boundary)
            or type(self.applicability) is not NiftyApplicability
            or type(self.state) is not NiftyRelativeState
            or self.reason is not None and type(self.reason) is not NiftyFailure
            or any(item is not None and type(item) is not Decimal for item in numerical)
            or any(item is not None and not _text(item) for item in identities)
            or any(item is not None and not _aware(item) for item in boundaries)
            or not _texts(self.source_provenance)
            or self.policy_identity != NIFTY_RELATIVE_CONTEXT_POLICY
            or self.policy_version != NIFTY_RELATIVE_CONTEXT_VERSION
            or self.schema_identity != NIFTY_RELATIVE_CONTEXT_FACT_IDENTITY
            or self.schema_version != NIFTY_RELATIVE_CONTEXT_VERSION
            or (
                available
                and (
                    self.applicability is not NiftyApplicability.APPLICABLE
                    or self.reason is not None
                    or self.timeframe is not IntradayTimeframe.FIFTEEN_MINUTES
                    or any(item is None for item in (*boundaries, *identities, *numerical))
                    or self.interval_end > self.analysis_boundary
                    or self.subject_session_open <= 0
                    or self.benchmark_session_open <= 0
                    or (
                        self.state is NiftyRelativeState.OUTPERFORMING
                        and self.relative_return_pct <= 0
                    )
                    or (
                        self.state is NiftyRelativeState.UNDERPERFORMING
                        and self.relative_return_pct >= 0
                    )
                    or (
                        self.state is NiftyRelativeState.EQUAL
                        and self.relative_return_pct != 0
                    )
                )
            )
            or (
                not available
                and (
                    self.reason is None
                    or self.timeframe is not None
                    or any(item is not None for item in (*boundaries, *identities, *numerical))
                )
            )
            or (
                self.applicability is NiftyApplicability.NOT_APPLICABLE
                and self.state is not NiftyRelativeState.NOT_APPLICABLE
            )
            or (
                self.state is NiftyRelativeState.UNAVAILABLE
                and self.applicability is not NiftyApplicability.APPLICABLE
            )
            or self.fact_identity
            != _identity("INTRADAY-NIFTY-RELATIVE-FACT-", values)
            or self.integrity_identity
            != _identity("INTEGRITY-INTRADAY-NIFTY-RELATIVE-FACT-", values)
        ):
            raise NiftyRelativeContextError("NIFTY_RELATIVE_CONTEXT_FACT_INVALID")


@dataclass(frozen=True, slots=True)
class NiftyRelativeContextEvidence:
    evidence_identity: str
    fact: NiftyRelativeContextFact
    opening_direction: str
    relationship: NiftyRelationship
    authority: str
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = NIFTY_RELATIVE_CONTEXT_EVIDENCE_IDENTITY
    schema_version: str = NIFTY_RELATIVE_CONTEXT_VERSION

    def __post_init__(self) -> None:
        values = asdict(self)
        values.pop("evidence_identity")
        values.pop("integrity_identity")
        if (
            not self.evidence_identity.startswith("INTRADAY-NIFTY-RELATIVE-EVIDENCE-")
            or type(self.fact) is not NiftyRelativeContextFact
            or self.opening_direction not in {"LONG", "SHORT", "NON_DIRECTIONAL"}
            or type(self.relationship) is not NiftyRelationship
            or self.relationship != _relationship(self.fact.state, self.opening_direction)
            or self.authority != "SUPPORTING_CONTEXT_ONLY"
            or not _texts(self.provenance)
            or self.schema_identity != NIFTY_RELATIVE_CONTEXT_EVIDENCE_IDENTITY
            or self.schema_version != NIFTY_RELATIVE_CONTEXT_VERSION
            or self.evidence_identity
            != _identity("INTRADAY-NIFTY-RELATIVE-EVIDENCE-", values)
            or self.integrity_identity
            != _identity("INTEGRITY-INTRADAY-NIFTY-RELATIVE-EVIDENCE-", values)
        ):
            raise NiftyRelativeContextError(
                "NIFTY_RELATIVE_CONTEXT_EVIDENCE_INVALID"
            )


def build_nifty_relative_context(
    *,
    canonical_subject_identity: str,
    subject_exchange: str,
    opening_direction: str,
    analysis_boundary: datetime,
    subject_candle: GovernedHistoricalCandlePayload | None,
    benchmark_candle: GovernedHistoricalCandlePayload | None,
    subject_session_open: Decimal | None,
    benchmark_session_open: Decimal | None,
    provenance: tuple[str, ...],
) -> NiftyRelativeContextEvidence:
    """Build exact Opening relative context or a typed fail-closed state."""

    if (
        not _texts((canonical_subject_identity, subject_exchange))
        or opening_direction not in {"LONG", "SHORT", "NON_DIRECTIONAL"}
        or not _aware(analysis_boundary)
        or not _texts(provenance)
    ):
        raise NiftyRelativeContextError("NIFTY_RELATIVE_CONTEXT_INPUT_INVALID")
    if subject_exchange == "MCX":
        fact = _unavailable(
            canonical_subject_identity,
            analysis_boundary,
            NiftyApplicability.NOT_APPLICABLE,
            NiftyRelativeState.NOT_APPLICABLE,
            NiftyFailure.NOT_APPLICABLE_MARKET,
            provenance,
        )
    elif canonical_subject_identity == NIFTY_CANONICAL_IDENTITY:
        fact = _unavailable(
            canonical_subject_identity,
            analysis_boundary,
            NiftyApplicability.NOT_APPLICABLE,
            NiftyRelativeState.NOT_APPLICABLE,
            NiftyFailure.BENCHMARK_SELF_COMPARISON_NOT_APPLICABLE,
            provenance,
        )
    elif subject_exchange != "NSE":
        fact = _unavailable(
            canonical_subject_identity,
            analysis_boundary,
            NiftyApplicability.NOT_APPLICABLE,
            NiftyRelativeState.NOT_APPLICABLE,
            NiftyFailure.NOT_APPLICABLE_MARKET,
            provenance,
        )
    elif subject_candle is None:
        fact = _unavailable(
            canonical_subject_identity,
            analysis_boundary,
            NiftyApplicability.APPLICABLE,
            NiftyRelativeState.UNAVAILABLE,
            NiftyFailure.SUBJECT_FACT_UNAVAILABLE,
            provenance,
        )
    elif benchmark_candle is None:
        fact = _unavailable(
            canonical_subject_identity,
            analysis_boundary,
            NiftyApplicability.APPLICABLE,
            NiftyRelativeState.UNAVAILABLE,
            NiftyFailure.BENCHMARK_FACT_UNAVAILABLE,
            provenance,
        )
    elif benchmark_candle.canonical_subject_identity != NIFTY_CANONICAL_IDENTITY:
        fact = _unavailable(
            canonical_subject_identity,
            analysis_boundary,
            NiftyApplicability.APPLICABLE,
            NiftyRelativeState.UNAVAILABLE,
            NiftyFailure.BENCHMARK_IDENTITY_INVALID,
            provenance,
        )
    elif not _aligned(subject_candle, benchmark_candle, analysis_boundary):
        fact = _unavailable(
            canonical_subject_identity,
            analysis_boundary,
            NiftyApplicability.APPLICABLE,
            NiftyRelativeState.UNAVAILABLE,
            NiftyFailure.BOUNDARY_MISMATCH,
            provenance,
        )
    elif (
        type(subject_session_open) is not Decimal
        or type(benchmark_session_open) is not Decimal
        or subject_session_open <= 0
        or benchmark_session_open <= 0
    ):
        fact = _unavailable(
            canonical_subject_identity,
            analysis_boundary,
            NiftyApplicability.APPLICABLE,
            NiftyRelativeState.UNAVAILABLE,
            NiftyFailure.SOURCE_INTEGRITY_INVALID,
            provenance,
        )
    else:
        subject_return = ((subject_candle.close / subject_session_open) - Decimal(1)) * Decimal(100)
        benchmark_return = ((benchmark_candle.close / benchmark_session_open) - Decimal(1)) * Decimal(100)
        relative_return = subject_return - benchmark_return
        state = (
            NiftyRelativeState.OUTPERFORMING
            if relative_return > 0
            else NiftyRelativeState.UNDERPERFORMING
            if relative_return < 0
            else NiftyRelativeState.EQUAL
        )
        values = {
            "canonical_subject_identity": canonical_subject_identity,
            "benchmark_identity": NIFTY_CANONICAL_IDENTITY,
            "analysis_boundary": analysis_boundary,
            "applicability": NiftyApplicability.APPLICABLE,
            "state": state,
            "reason": None,
            "timeframe": IntradayTimeframe.FIFTEEN_MINUTES,
            "interval_start": subject_candle.candle_start,
            "interval_end": subject_candle.candle_end,
            "subject_market_session_identity": subject_candle.market_session_identity,
            "benchmark_market_session_identity": benchmark_candle.market_session_identity,
            "subject_candle_identity": subject_candle.candle_identity,
            "benchmark_candle_identity": benchmark_candle.candle_identity,
            "subject_session_open": subject_session_open,
            "benchmark_session_open": benchmark_session_open,
            "subject_close": subject_candle.close,
            "benchmark_close": benchmark_candle.close,
            "subject_return_pct": subject_return,
            "benchmark_return_pct": benchmark_return,
            "relative_return_pct": relative_return,
            "source_provenance": provenance,
            "policy_identity": NIFTY_RELATIVE_CONTEXT_POLICY,
            "policy_version": NIFTY_RELATIVE_CONTEXT_VERSION,
            "schema_identity": NIFTY_RELATIVE_CONTEXT_FACT_IDENTITY,
            "schema_version": NIFTY_RELATIVE_CONTEXT_VERSION,
        }
        fact = NiftyRelativeContextFact(
            fact_identity=_identity("INTRADAY-NIFTY-RELATIVE-FACT-", values),
            integrity_identity=_identity(
                "INTEGRITY-INTRADAY-NIFTY-RELATIVE-FACT-", values
            ),
            **values,
        )
    values = {
        "fact": fact,
        "opening_direction": opening_direction,
        "relationship": _relationship(fact.state, opening_direction),
        "authority": "SUPPORTING_CONTEXT_ONLY",
        "provenance": provenance,
        "schema_identity": NIFTY_RELATIVE_CONTEXT_EVIDENCE_IDENTITY,
        "schema_version": NIFTY_RELATIVE_CONTEXT_VERSION,
    }
    return NiftyRelativeContextEvidence(
        evidence_identity=_identity("INTRADAY-NIFTY-RELATIVE-EVIDENCE-", values),
        integrity_identity=_identity(
            "INTEGRITY-INTRADAY-NIFTY-RELATIVE-EVIDENCE-", values
        ),
        **values,
    )


def classify_relative_progression(
    relative_returns: Sequence[Decimal],
) -> RelativeProgressionState:
    values = tuple(relative_returns)
    if len(values) != 3 or any(type(item) is not Decimal for item in values):
        raise NiftyRelativeContextError("NIFTY_RELATIVE_PROGRESSION_INVALID")
    if values[0] < values[1] < values[2]:
        return RelativeProgressionState.IMPROVING
    if values[0] > values[1] > values[2]:
        return RelativeProgressionState.DETERIORATING
    if values[0] == values[1] == values[2]:
        return RelativeProgressionState.FLAT
    return RelativeProgressionState.MIXED


def _unavailable(
    subject: str,
    boundary: datetime,
    applicability: NiftyApplicability,
    state: NiftyRelativeState,
    reason: NiftyFailure,
    provenance: tuple[str, ...],
) -> NiftyRelativeContextFact:
    values = {
        "canonical_subject_identity": subject,
        "benchmark_identity": NIFTY_CANONICAL_IDENTITY,
        "analysis_boundary": boundary,
        "applicability": applicability,
        "state": state,
        "reason": reason,
        "timeframe": None,
        "interval_start": None,
        "interval_end": None,
        "subject_market_session_identity": None,
        "benchmark_market_session_identity": None,
        "subject_candle_identity": None,
        "benchmark_candle_identity": None,
        "subject_session_open": None,
        "benchmark_session_open": None,
        "subject_close": None,
        "benchmark_close": None,
        "subject_return_pct": None,
        "benchmark_return_pct": None,
        "relative_return_pct": None,
        "source_provenance": provenance,
        "policy_identity": NIFTY_RELATIVE_CONTEXT_POLICY,
        "policy_version": NIFTY_RELATIVE_CONTEXT_VERSION,
        "schema_identity": NIFTY_RELATIVE_CONTEXT_FACT_IDENTITY,
        "schema_version": NIFTY_RELATIVE_CONTEXT_VERSION,
    }
    return NiftyRelativeContextFact(
        fact_identity=_identity("INTRADAY-NIFTY-RELATIVE-FACT-", values),
        integrity_identity=_identity(
            "INTEGRITY-INTRADAY-NIFTY-RELATIVE-FACT-", values
        ),
        **values,
    )


def _aligned(
    subject: GovernedHistoricalCandlePayload,
    benchmark: GovernedHistoricalCandlePayload,
    boundary: datetime,
) -> bool:
    return (
        type(subject) is GovernedHistoricalCandlePayload
        and type(benchmark) is GovernedHistoricalCandlePayload
        and subject.canonical_subject_identity != NIFTY_CANONICAL_IDENTITY
        and subject.exchange == benchmark.exchange == "NSE"
        and subject.market_identity == benchmark.market_identity
        and subject.timeframe is benchmark.timeframe is IntradayTimeframe.FIFTEEN_MINUTES
        and subject.candle_start == benchmark.candle_start
        and subject.candle_end == benchmark.candle_end
        and subject.available_at == benchmark.available_at == subject.candle_end
        and subject.observation_boundary == benchmark.observation_boundary == boundary
        and subject.completion_state == benchmark.completion_state == "COMPLETE"
    )


def _relationship(
    state: NiftyRelativeState,
    direction: str,
) -> NiftyRelationship:
    if state is NiftyRelativeState.UNAVAILABLE:
        return NiftyRelationship.UNAVAILABLE
    if state is NiftyRelativeState.NOT_APPLICABLE:
        return NiftyRelationship.NOT_APPLICABLE
    if state is NiftyRelativeState.EQUAL or direction == "NON_DIRECTIONAL":
        return NiftyRelationship.INFORMATIONAL
    supporting = (
        state is NiftyRelativeState.OUTPERFORMING and direction == "LONG"
    ) or (
        state is NiftyRelativeState.UNDERPERFORMING and direction == "SHORT"
    )
    return NiftyRelationship.SUPPORTING if supporting else NiftyRelationship.CONFLICTING


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(_encode(value)).hexdigest().upper()


def _encode(value: object) -> bytes:
    return json.dumps(
        _normalize(value), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _normalize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {name: _normalize(item) for name, item in asdict(value).items()}
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(name): _normalize(item) for name, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    return value


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


def _texts(values: Sequence[object]) -> bool:
    retained = tuple(values)
    return bool(retained) and all(_text(item) for item in retained)


__all__ = [
    "NIFTY_CANONICAL_IDENTITY",
    "NIFTY_RELATIVE_CONTEXT_EVIDENCE_IDENTITY",
    "NIFTY_RELATIVE_CONTEXT_FACT_IDENTITY",
    "NIFTY_RELATIVE_CONTEXT_POLICY",
    "NIFTY_RELATIVE_CONTEXT_VERSION",
    "NiftyApplicability",
    "NiftyFailure",
    "NiftyRelationship",
    "NiftyRelativeContextError",
    "NiftyRelativeContextEvidence",
    "NiftyRelativeContextFact",
    "NiftyRelativeState",
    "RelativeProgressionState",
    "build_nifty_relative_context",
    "classify_relative_progression",
]
