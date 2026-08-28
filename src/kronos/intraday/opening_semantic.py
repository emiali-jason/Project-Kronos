"""Frozen Opening semantic facts for Intraday Probables V2."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json
from typing import Mapping, Sequence

from kronos.intraday.completed_evidence import (
    EvidenceSessionRole,
    IntradayAnalysisPhase,
    PhaseAwareCompletedEvidenceSelection,
)
from kronos.intraday.historical_semantic import (
    GovernedHistoricalCandlePayload,
    SemanticDirection,
)
from kronos.intraday.nifty_relative_context import (
    NiftyApplicability,
    NiftyRelationship,
    NiftyRelativeContextEvidence,
)
from kronos.intraday.qualification import NarrowCprFact


OPENING_SEMANTIC_FACT_IDENTITY = "KRONOS-INTRADAY-OPENING-SEMANTIC-FACT-V1"
OPENING_SEMANTIC_EVIDENCE_IDENTITY = (
    "KRONOS-INTRADAY-OPENING-SEMANTIC-EVIDENCE-V1"
)
OPENING_SEMANTIC_VERSION = "1.0.0"
OPENING_SEMANTIC_POLICY = "KRONOS-INTRADAY-OPENING-SEMANTIC-POLICY-V1"


class OpeningSemanticError(ValueError):
    """Sanitized invalid or conflicting Opening evidence."""


class OpeningRelationship(StrEnum):
    SUPPORTING = "SUPPORTING"
    CONFLICTING = "CONFLICTING"
    INFORMATIONAL = "INFORMATIONAL"


@dataclass(frozen=True, slots=True)
class OpeningSemanticFact:
    fact_identity: str
    canonical_subject_identity: str
    analysis_boundary: datetime
    phase: IntradayAnalysisPhase
    completed_evidence_selection_identity: str
    opening_direction: SemanticDirection
    opening_candle_identity: str
    opening_candle_boundary: tuple[datetime, datetime]
    opening_ohlcv: tuple[Decimal, Decimal, Decimal, Decimal, int]
    opening_5m_candle_identities: tuple[str, str, str]
    opening_5m_boundaries: tuple[
        tuple[datetime, datetime],
        tuple[datetime, datetime],
        tuple[datetime, datetime],
    ]
    five_minute_progression: SemanticDirection
    prior_one_hour_candle_identities: tuple[str, str]
    prior_one_hour_boundaries: tuple[
        tuple[datetime, datetime],
        tuple[datetime, datetime],
    ]
    prior_one_hour_session_identity: str
    prior_one_hour_direction: SemanticDirection
    prior_one_hour_relationship: OpeningRelationship
    five_minute_relationship: OpeningRelationship
    narrow_cpr_fact_identity: str
    narrow_cpr_qualified: bool
    reference_fact_identities: tuple[tuple[str, str], ...]
    participation_state: str
    nifty_relative_evidence_identity: str
    nifty_applicability: NiftyApplicability
    nifty_relationship: NiftyRelationship
    source_provenance: tuple[str, ...]
    integrity_identity: str
    policy_identity: str = OPENING_SEMANTIC_POLICY
    policy_version: str = OPENING_SEMANTIC_VERSION
    schema_identity: str = OPENING_SEMANTIC_FACT_IDENTITY
    schema_version: str = OPENING_SEMANTIC_VERSION

    def __post_init__(self) -> None:
        values = asdict(self)
        values.pop("fact_identity")
        values.pop("integrity_identity")
        if (
            not self.fact_identity.startswith("INTRADAY-OPENING-SEMANTIC-FACT-")
            or not _texts((
                self.canonical_subject_identity,
                self.completed_evidence_selection_identity,
                self.opening_candle_identity,
                self.narrow_cpr_fact_identity,
                self.participation_state,
                self.nifty_relative_evidence_identity,
            ))
            or not _aware(self.analysis_boundary)
            or self.phase is not IntradayAnalysisPhase.OPENING
            or type(self.opening_direction) is not SemanticDirection
            or self.opening_direction not in {
                SemanticDirection.LONG,
                SemanticDirection.SHORT,
                SemanticDirection.NON_DIRECTIONAL,
            }
            or len(self.opening_candle_boundary) != 2
            or not all(_aware(item) for item in self.opening_candle_boundary)
            or self.opening_candle_boundary[0] >= self.opening_candle_boundary[1]
            or len(self.opening_ohlcv) != 5
            or any(type(item) is not Decimal for item in self.opening_ohlcv[:4])
            or type(self.opening_ohlcv[4]) is not int
            or not _texts(self.opening_5m_candle_identities)
            or len(self.opening_5m_candle_identities) != 3
            or len(set(self.opening_5m_candle_identities)) != 3
            or len(self.opening_5m_boundaries) != 3
            or any(
                len(boundary) != 2
                or not all(_aware(item) for item in boundary)
                or boundary[0] >= boundary[1]
                for boundary in self.opening_5m_boundaries
            )
            or type(self.five_minute_progression) is not SemanticDirection
            or self.five_minute_progression not in {
                SemanticDirection.LONG,
                SemanticDirection.SHORT,
                SemanticDirection.NON_DIRECTIONAL,
                SemanticDirection.CONFLICTING,
            }
            or not _texts(self.prior_one_hour_candle_identities)
            or len(self.prior_one_hour_candle_identities) != 2
            or len(self.prior_one_hour_boundaries) != 2
            or any(
                len(boundary) != 2
                or not all(_aware(item) for item in boundary)
                or boundary[0] >= boundary[1]
                for boundary in self.prior_one_hour_boundaries
            )
            or not _text(self.prior_one_hour_session_identity)
            or type(self.prior_one_hour_direction) is not SemanticDirection
            or self.prior_one_hour_direction not in {
                SemanticDirection.LONG,
                SemanticDirection.SHORT,
                SemanticDirection.NON_DIRECTIONAL,
            }
            or type(self.prior_one_hour_relationship) is not OpeningRelationship
            or type(self.five_minute_relationship) is not OpeningRelationship
            or type(self.narrow_cpr_qualified) is not bool
            or tuple(sorted(self.reference_fact_identities))
            != self.reference_fact_identities
            or len({name for name, _ in self.reference_fact_identities})
            != len(self.reference_fact_identities)
            or any(not _texts(item) for item in self.reference_fact_identities)
            or type(self.nifty_applicability) is not NiftyApplicability
            or type(self.nifty_relationship) is not NiftyRelationship
            or not _texts(self.source_provenance)
            or self.policy_identity != OPENING_SEMANTIC_POLICY
            or self.policy_version != OPENING_SEMANTIC_VERSION
            or self.schema_identity != OPENING_SEMANTIC_FACT_IDENTITY
            or self.schema_version != OPENING_SEMANTIC_VERSION
            or self.fact_identity
            != _identity("INTRADAY-OPENING-SEMANTIC-FACT-", values)
            or self.integrity_identity
            != _identity("INTEGRITY-INTRADAY-OPENING-SEMANTIC-FACT-", values)
        ):
            raise OpeningSemanticError("OPENING_SEMANTIC_FACT_INVALID")


@dataclass(frozen=True, slots=True)
class OpeningSemanticEvidence:
    evidence_identity: str
    fact: OpeningSemanticFact
    combined_relationship: OpeningRelationship
    normal_fifteen_minute_structure_state: str
    available_at: datetime
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = OPENING_SEMANTIC_EVIDENCE_IDENTITY
    schema_version: str = OPENING_SEMANTIC_VERSION

    def __post_init__(self) -> None:
        values = asdict(self)
        values.pop("evidence_identity")
        values.pop("integrity_identity")
        if (
            not self.evidence_identity.startswith("INTRADAY-OPENING-SEMANTIC-EVIDENCE-")
            or type(self.fact) is not OpeningSemanticFact
            or type(self.combined_relationship) is not OpeningRelationship
            or self.combined_relationship != combine_opening_relationships(
                self.fact.prior_one_hour_relationship,
                self.fact.five_minute_relationship,
                _nifty_opening_relationship(self.fact.nifty_relationship),
            )
            or self.normal_fifteen_minute_structure_state != "DEFERRED_IN_OPENING"
            or not _aware(self.available_at)
            or self.available_at > self.fact.analysis_boundary
            or not _texts(self.provenance)
            or self.schema_identity != OPENING_SEMANTIC_EVIDENCE_IDENTITY
            or self.schema_version != OPENING_SEMANTIC_VERSION
            or self.evidence_identity
            != _identity("INTRADAY-OPENING-SEMANTIC-EVIDENCE-", values)
            or self.integrity_identity
            != _identity("INTEGRITY-INTRADAY-OPENING-SEMANTIC-EVIDENCE-", values)
        ):
            raise OpeningSemanticError("OPENING_SEMANTIC_EVIDENCE_INVALID")


def build_opening_semantic_evidence(
    *,
    selection: PhaseAwareCompletedEvidenceSelection,
    narrow_cpr_fact: NarrowCprFact,
    nifty_relative_evidence: NiftyRelativeContextEvidence,
    reference_fact_identities: tuple[tuple[str, str], ...] = (),
    participation_state: str = "UNAVAILABLE",
    provenance: tuple[str, ...],
) -> OpeningSemanticEvidence:
    """Derive the exact frozen Opening facts without creating admission authority."""

    if (
        type(selection) is not PhaseAwareCompletedEvidenceSelection
        or selection.phase is not IntradayAnalysisPhase.OPENING
        or type(narrow_cpr_fact) is not NarrowCprFact
        or narrow_cpr_fact.canonical_subject_identity
        != selection.canonical_subject_identity
        or narrow_cpr_fact.observation_boundary > selection.analysis_boundary
        or type(nifty_relative_evidence) is not NiftyRelativeContextEvidence
        or nifty_relative_evidence.fact.canonical_subject_identity
        != selection.canonical_subject_identity
        or nifty_relative_evidence.fact.analysis_boundary
        != selection.analysis_boundary
        or not _text(participation_state)
        or not _texts(provenance)
    ):
        raise OpeningSemanticError("OPENING_SEMANTIC_INPUT_INVALID")
    opening = selection.candles(
        timeframe=_fifteen(), role=EvidenceSessionRole.CURRENT_SESSION_15M
    )
    five = selection.candles(
        timeframe=_five(), role=EvidenceSessionRole.CURRENT_SESSION_5M
    )
    prior = selection.candles(
        timeframe=_hour(), role=EvidenceSessionRole.PRIOR_SESSION_1H_CONTEXT
    )
    if len(opening) != 1 or len(five) != 3 or len(prior) != 2:
        raise OpeningSemanticError("OPENING_SEMANTIC_SELECTION_INVALID")
    direction = _open_direction(opening[0])
    progression = _five_minute_progression(five)
    prior_direction = _movement_direction(prior[0], prior[1])
    prior_relationship = _direction_relationship(direction, prior_direction)
    five_relationship = _direction_relationship(direction, progression)
    values = {
        "canonical_subject_identity": selection.canonical_subject_identity,
        "analysis_boundary": selection.analysis_boundary,
        "phase": IntradayAnalysisPhase.OPENING,
        "completed_evidence_selection_identity": selection.selection_identity,
        "opening_direction": direction,
        "opening_candle_identity": opening[0].candle_identity,
        "opening_candle_boundary": (
            opening[0].candle_start,
            opening[0].candle_end,
        ),
        "opening_ohlcv": (
            opening[0].open,
            opening[0].high,
            opening[0].low,
            opening[0].close,
            opening[0].volume,
        ),
        "opening_5m_candle_identities": tuple(item.candle_identity for item in five),
        "opening_5m_boundaries": tuple(
            (item.candle_start, item.candle_end) for item in five
        ),
        "five_minute_progression": progression,
        "prior_one_hour_candle_identities": tuple(item.candle_identity for item in prior),
        "prior_one_hour_boundaries": tuple(
            (item.candle_start, item.candle_end) for item in prior
        ),
        "prior_one_hour_session_identity": prior[0].market_session_identity,
        "prior_one_hour_direction": prior_direction,
        "prior_one_hour_relationship": prior_relationship,
        "five_minute_relationship": five_relationship,
        "narrow_cpr_fact_identity": narrow_cpr_fact.fact_identity,
        "narrow_cpr_qualified": narrow_cpr_fact.narrow_cpr_kgs_v0,
        "reference_fact_identities": tuple(sorted(reference_fact_identities)),
        "participation_state": participation_state,
        "nifty_relative_evidence_identity": nifty_relative_evidence.evidence_identity,
        "nifty_applicability": nifty_relative_evidence.fact.applicability,
        "nifty_relationship": nifty_relative_evidence.relationship,
        "source_provenance": provenance,
        "policy_identity": OPENING_SEMANTIC_POLICY,
        "policy_version": OPENING_SEMANTIC_VERSION,
        "schema_identity": OPENING_SEMANTIC_FACT_IDENTITY,
        "schema_version": OPENING_SEMANTIC_VERSION,
    }
    fact = OpeningSemanticFact(
        fact_identity=_identity("INTRADAY-OPENING-SEMANTIC-FACT-", values),
        integrity_identity=_identity(
            "INTEGRITY-INTRADAY-OPENING-SEMANTIC-FACT-", values
        ),
        **values,
    )
    evidence_values = {
        "fact": fact,
        "combined_relationship": combine_opening_relationships(
            prior_relationship,
            five_relationship,
            _nifty_opening_relationship(nifty_relative_evidence.relationship),
        ),
        "normal_fifteen_minute_structure_state": "DEFERRED_IN_OPENING",
        "available_at": max(item.candle_end for item in (*opening, *five, *prior)),
        "provenance": provenance,
        "schema_identity": OPENING_SEMANTIC_EVIDENCE_IDENTITY,
        "schema_version": OPENING_SEMANTIC_VERSION,
    }
    return OpeningSemanticEvidence(
        evidence_identity=_identity(
            "INTRADAY-OPENING-SEMANTIC-EVIDENCE-", evidence_values
        ),
        integrity_identity=_identity(
            "INTEGRITY-INTRADAY-OPENING-SEMANTIC-EVIDENCE-", evidence_values
        ),
        **evidence_values,
    )


def combine_opening_relationships(
    *values: OpeningRelationship,
) -> OpeningRelationship:
    if not values or any(type(item) is not OpeningRelationship for item in values):
        raise OpeningSemanticError("OPENING_RELATIONSHIP_INPUT_INVALID")
    if OpeningRelationship.CONFLICTING in values:
        return OpeningRelationship.CONFLICTING
    if OpeningRelationship.SUPPORTING in values:
        return OpeningRelationship.SUPPORTING
    return OpeningRelationship.INFORMATIONAL


def _open_direction(value: GovernedHistoricalCandlePayload) -> SemanticDirection:
    if value.close > value.open:
        return SemanticDirection.LONG
    if value.close < value.open:
        return SemanticDirection.SHORT
    return SemanticDirection.NON_DIRECTIONAL


def _movement_direction(
    previous: GovernedHistoricalCandlePayload,
    current: GovernedHistoricalCandlePayload,
) -> SemanticDirection:
    above = current.high > previous.high and current.low > previous.low and current.close > previous.close
    below = current.high < previous.high and current.low < previous.low and current.close < previous.close
    if above:
        return SemanticDirection.LONG
    if below:
        return SemanticDirection.SHORT
    return SemanticDirection.NON_DIRECTIONAL


def _five_minute_progression(
    candles: tuple[GovernedHistoricalCandlePayload, ...],
) -> SemanticDirection:
    transitions = tuple(
        _movement_direction(previous, current)
        for previous, current in zip(candles, candles[1:])
    )
    if transitions == (SemanticDirection.LONG, SemanticDirection.LONG):
        return SemanticDirection.LONG
    if transitions == (SemanticDirection.SHORT, SemanticDirection.SHORT):
        return SemanticDirection.SHORT
    if set(transitions) == {SemanticDirection.LONG, SemanticDirection.SHORT}:
        return SemanticDirection.CONFLICTING
    return SemanticDirection.NON_DIRECTIONAL


def _direction_relationship(
    opening: SemanticDirection,
    context: SemanticDirection,
) -> OpeningRelationship:
    if opening not in {SemanticDirection.LONG, SemanticDirection.SHORT}:
        return OpeningRelationship.INFORMATIONAL
    if context is opening:
        return OpeningRelationship.SUPPORTING
    if context in {SemanticDirection.LONG, SemanticDirection.SHORT, SemanticDirection.CONFLICTING}:
        return OpeningRelationship.CONFLICTING
    return OpeningRelationship.INFORMATIONAL


def _nifty_opening_relationship(value: NiftyRelationship) -> OpeningRelationship:
    if value is NiftyRelationship.SUPPORTING:
        return OpeningRelationship.SUPPORTING
    if value is NiftyRelationship.CONFLICTING:
        return OpeningRelationship.CONFLICTING
    return OpeningRelationship.INFORMATIONAL


def _hour():  # type: ignore[no-untyped-def]
    from kronos.intraday.contracts import IntradayTimeframe
    return IntradayTimeframe.ONE_HOUR


def _fifteen():  # type: ignore[no-untyped-def]
    from kronos.intraday.contracts import IntradayTimeframe
    return IntradayTimeframe.FIFTEEN_MINUTES


def _five():  # type: ignore[no-untyped-def]
    from kronos.intraday.contracts import IntradayTimeframe
    return IntradayTimeframe.FIVE_MINUTES


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
    "OPENING_SEMANTIC_EVIDENCE_IDENTITY",
    "OPENING_SEMANTIC_FACT_IDENTITY",
    "OPENING_SEMANTIC_POLICY",
    "OPENING_SEMANTIC_VERSION",
    "OpeningRelationship",
    "OpeningSemanticError",
    "OpeningSemanticEvidence",
    "OpeningSemanticFact",
    "build_opening_semantic_evidence",
    "combine_opening_relationships",
]
