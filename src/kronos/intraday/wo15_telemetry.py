"""WO-15C immutable extension and research telemetry.

The module measures completed-5M facts around an already-decided WO-15B result.
It cannot qualify, fail, expire, block, or otherwise alter Entry Timing.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, is_dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from hashlib import sha256
import json
from typing import Mapping, Sequence

from kronos.intraday.historical_semantic import (
    GovernedHistoricalCandlePayload,
    SemanticDirection,
)
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo15 import (
    WO15_POLICY_CHECKSUM,
    WO15_POLICY_IDENTITY,
    WO15_POLICY_VERSION,
    Wo15FiveMinuteEvidence,
    Wo15QualificationPath,
    Wo15SessionBinding,
    Wo15TimingState,
    Wo15Wo13Handoff,
)
from kronos.intraday.wo15_timing import Wo15TimingEvaluationResult


WO15_TELEMETRY_IDENTITY = "KRONOS-INTRADAY-WO15-RESEARCH-TELEMETRY-V1"
WO15_TELEMETRY_VERSION = "1.0.0"
WO15_TELEMETRY_AUTHORITY = "ADVISORY_RESEARCH_TELEMETRY_ONLY"
WO15_ATR14_IDENTITY = "KRONOS-INTRADAY-WO15-COMPLETED-5M-WILDER-ATR14-V1"
WO15_ATR14_METHOD = "WILDER_RMA"
WO15_ATR14_PERIOD = 14
WO15_EXTENSION_SEVERITY = "UNCLASSIFIED"


class Wo15TelemetryError(ValueError):
    """Sanitized telemetry contract or lineage failure."""


class Wo15TelemetryAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class Wo15AtrUnavailableReason(StrEnum):
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    HISTORY_INCOMPLETE = "HISTORY_INCOMPLETE"
    NON_POSITIVE_ATR = "NON_POSITIVE_ATR"


class Wo15ResearchRole(StrEnum):
    VOLUME_5M = "VOLUME_5M"
    RSI14_5M = "RSI14_5M"
    SMA_RAILWAY_5M = "SMA_RAILWAY_5M"
    LEVEL_CONTEXT = "CPR_PDH_PDL_PIVOT_CONTEXT"
    SESSION_PHASE = "SESSION_PHASE"
    WO14_AUDIT_CONTEXT = "WO14_AUDIT_CONTEXT"
    FUTURE_OUTCOME = "FUTURE_OUTCOME"
    REFERENCE_MARKET_CONTEXT = "REFERENCE_MARKET_CONTEXT"


class Wo15ResearchLocality(StrEnum):
    LOCAL_ANALYTICAL_SUBJECT = "LOCAL_ANALYTICAL_SUBJECT"
    SEPARATE_REFERENCE_CONTEXT = "SEPARATE_REFERENCE_CONTEXT"


@dataclass(frozen=True, slots=True)
class Wo15TelemetryCandle:
    """Completed candle plus WO-15 product-local identity and sequence binding."""

    candle_binding_identity: str
    candle_binding_integrity: str
    source_candle_identity: str
    source_candle_integrity: str
    evidence_identity: str
    evidence_integrity: str
    canonical_subject_identity: str
    market_family: IntradayMarketFamily
    instrument_identity: str
    actual_contract_identity: str | None
    roll_lineage_identity: str | None
    session_identity: str
    candle_start: datetime
    candle_end: datetime
    observation_boundary: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    sequence_index: int
    schema_version: str = WO15_TELEMETRY_VERSION

    def __post_init__(self) -> None:
        for name in ("open", "high", "low", "close"):
            object.__setattr__(self, name, _decimal(getattr(self, name)))
        values = _without(self, "candle_binding_identity", "candle_binding_integrity")
        mcx = self.market_family is IntradayMarketFamily.MCX
        if (
            not _texts((
                self.source_candle_identity,
                self.source_candle_integrity,
                self.evidence_identity,
                self.evidence_integrity,
                self.canonical_subject_identity,
                self.instrument_identity,
                self.session_identity,
            ))
            or type(self.market_family) is not IntradayMarketFamily
            or mcx != (self.actual_contract_identity is not None)
            or mcx != (self.roll_lineage_identity is not None)
            or not all(_aware(item) for item in (
                self.candle_start, self.candle_end, self.observation_boundary
            ))
            or self.candle_end - self.candle_start != timedelta(minutes=5)
            or self.candle_end > self.observation_boundary
            or self.high < max(self.open, self.low, self.close)
            or self.low > min(self.open, self.high, self.close)
            or type(self.volume) is not int
            or self.volume < 0
            or type(self.sequence_index) is not int
            or self.sequence_index < 0
            or self.schema_version != WO15_TELEMETRY_VERSION
            or self.candle_binding_identity
            != _identity("INTRADAY-WO15-TELEMETRY-CANDLE-", values)
            or self.candle_binding_integrity
            != _identity("INTEGRITY-INTRADAY-WO15-TELEMETRY-CANDLE-", values)
        ):
            raise Wo15TelemetryError("WO15_TELEMETRY_CANDLE_INVALID")


@dataclass(frozen=True, slots=True)
class Wo15Atr14Observation:
    atr_identity: str
    atr_integrity: str
    availability: Wo15TelemetryAvailability
    value: Decimal | None
    unavailable_reason: Wo15AtrUnavailableReason | None
    canonical_subject_identity: str
    instrument_identity: str
    actual_contract_identity: str | None
    roll_lineage_identity: str | None
    session_identity: str
    observation_boundary: datetime
    source_candle_identities: tuple[str, ...]
    source_candle_integrities: tuple[str, ...]
    schema_identity: str = WO15_ATR14_IDENTITY
    schema_version: str = WO15_TELEMETRY_VERSION
    method: str = WO15_ATR14_METHOD
    period: int = WO15_ATR14_PERIOD
    authority: str = "NON_DIRECTIONAL_NORMALIZER_ONLY"

    def __post_init__(self) -> None:
        if self.value is not None:
            object.__setattr__(self, "value", _decimal(self.value))
        values = _without(self, "atr_identity", "atr_integrity")
        available = self.availability is Wo15TelemetryAvailability.AVAILABLE
        if (
            type(self.availability) is not Wo15TelemetryAvailability
            or available != (self.value is not None)
            or available == (self.unavailable_reason is not None)
            or (self.value is not None and self.value <= 0)
            or not _texts((
                self.canonical_subject_identity,
                self.instrument_identity,
                self.session_identity,
            ))
            or not _aware(self.observation_boundary)
            or len(self.source_candle_identities) != len(self.source_candle_integrities)
            or not _texts(self.source_candle_identities)
            or not _texts(self.source_candle_integrities)
            or self.schema_identity != WO15_ATR14_IDENTITY
            or self.schema_version != WO15_TELEMETRY_VERSION
            or self.method != WO15_ATR14_METHOD
            or self.period != WO15_ATR14_PERIOD
            or self.authority != "NON_DIRECTIONAL_NORMALIZER_ONLY"
            or self.atr_identity != _identity("INTRADAY-WO15-ATR14-", values)
            or self.atr_integrity != _identity("INTEGRITY-INTRADAY-WO15-ATR14-", values)
        ):
            raise Wo15TelemetryError("WO15_ATR14_INVALID")


@dataclass(frozen=True, slots=True)
class Wo15ResearchReference:
    reference_identity: str
    reference_integrity: str
    role: Wo15ResearchRole
    locality: Wo15ResearchLocality
    availability: Wo15TelemetryAvailability
    canonical_subject_identity: str
    instrument_identity: str | None
    actual_contract_identity: str | None
    roll_lineage_identity: str | None
    observation_boundary: datetime
    facts: tuple[tuple[str, str], ...]
    source_identities: tuple[str, ...]
    source_integrities: tuple[str, ...]
    authority: str = "RESEARCH_CONTEXT_ONLY"
    schema_version: str = WO15_TELEMETRY_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "reference_identity", "reference_integrity")
        available = self.availability is Wo15TelemetryAvailability.AVAILABLE
        reference = self.locality is Wo15ResearchLocality.SEPARATE_REFERENCE_CONTEXT
        if (
            type(self.role) is not Wo15ResearchRole
            or type(self.locality) is not Wo15ResearchLocality
            or type(self.availability) is not Wo15TelemetryAvailability
            or not _texts((self.canonical_subject_identity,))
            or not _aware(self.observation_boundary)
            or len(self.source_identities) != len(self.source_integrities)
            or available != bool(self.source_identities)
            or available != bool(self.source_integrities)
            or any(not _texts(item) for item in self.facts)
            or len({item[0] for item in self.facts}) != len(self.facts)
            or (not available and bool(self.facts))
            or reference != (self.role is Wo15ResearchRole.REFERENCE_MARKET_CONTEXT)
            or (not reference and not _texts((self.instrument_identity,)))
            or self.authority != "RESEARCH_CONTEXT_ONLY"
            or self.schema_version != WO15_TELEMETRY_VERSION
            or self.reference_identity != _identity("INTRADAY-WO15-RESEARCH-REFERENCE-", values)
            or self.reference_integrity
            != _identity("INTEGRITY-INTRADAY-WO15-RESEARCH-REFERENCE-", values)
        ):
            raise Wo15TelemetryError("WO15_RESEARCH_REFERENCE_INVALID")


@dataclass(frozen=True, slots=True)
class Wo15LatencyTelemetry:
    plan_to_first_evaluation: timedelta | None
    plan_to_first_interaction: timedelta | None
    first_interaction_to_qualification: timedelta | None
    first_evaluation_to_qualification: timedelta | None
    bars_plan_to_first_evaluation: int | None
    bars_first_evaluation_to_interaction: int | None
    bars_interaction_to_qualification: int | None
    bars_first_evaluation_to_qualification: int | None

    def __post_init__(self) -> None:
        for value in (
            self.plan_to_first_evaluation,
            self.plan_to_first_interaction,
            self.first_interaction_to_qualification,
            self.first_evaluation_to_qualification,
        ):
            if value is not None and (type(value) is not timedelta or value < timedelta(0)):
                raise Wo15TelemetryError("WO15_TELEMETRY_LATENCY_INVALID")
        for value in (
            self.bars_plan_to_first_evaluation,
            self.bars_first_evaluation_to_interaction,
            self.bars_interaction_to_qualification,
            self.bars_first_evaluation_to_qualification,
        ):
            if value is not None and (type(value) is not int or value < 0):
                raise Wo15TelemetryError("WO15_TELEMETRY_LATENCY_INVALID")


@dataclass(frozen=True, slots=True)
class Wo15ResearchTelemetry:
    telemetry_identity: str
    telemetry_integrity: str
    wo13_trade_plan_identity: str
    wo13_trade_plan_integrity: str
    timing_cycle_id: str
    timing_result_identity: str
    timing_result_integrity: str
    timing_observation_identity: str
    timing_observation_integrity: str
    canonical_subject_identity: str
    market_family: IntradayMarketFamily
    instrument_identity: str
    actual_contract_identity: str | None
    roll_lineage_identity: str | None
    session_identity: str
    calendar_identity: str
    calendar_version: str
    observation_boundary: datetime
    measurement_evidence_identity: str
    measurement_evidence_integrity: str
    direction: SemanticDirection
    qualification_path: Wo15QualificationPath
    timing_state_observed: Wo15TimingState
    entry_reference: Decimal
    completed_five_minute_close: Decimal
    directional_extension: Decimal
    absolute_extension: Decimal
    atr14: Wo15Atr14Observation
    normalized_directional_extension: Decimal | None
    normalized_extension_availability: Wo15TelemetryAvailability
    extension_severity: str
    maximum_favourable_extension: Decimal | None
    maximum_adverse_distance: Decimal | None
    maximum_extension_before_qualification: Decimal | None
    excursion_availability: Wo15TelemetryAvailability
    retest_occurred: bool
    latency: Wo15LatencyTelemetry
    research_references: tuple[Wo15ResearchReference, ...]
    source_evidence_identities: tuple[str, ...]
    source_evidence_integrities: tuple[str, ...]
    policy_identity: str = WO15_POLICY_IDENTITY
    policy_version: str = WO15_POLICY_VERSION
    policy_checksum: str = WO15_POLICY_CHECKSUM
    schema_identity: str = WO15_TELEMETRY_IDENTITY
    schema_version: str = WO15_TELEMETRY_VERSION
    authority: str = WO15_TELEMETRY_AUTHORITY
    timing_decision_authority: bool = False
    geometry_authority: bool = False
    risk_authority: bool = False
    sponsor_decision_authority: bool = False
    execution_authority: bool = False
    broker_authority: bool = False

    def __post_init__(self) -> None:
        for name in (
            "entry_reference", "completed_five_minute_close",
            "directional_extension", "absolute_extension",
            "normalized_directional_extension", "maximum_favourable_extension",
            "maximum_adverse_distance", "maximum_extension_before_qualification",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _decimal(value))
        values = _without(self, "telemetry_identity", "telemetry_integrity")
        normalized = self.normalized_extension_availability is Wo15TelemetryAvailability.AVAILABLE
        excursions = self.excursion_availability is Wo15TelemetryAvailability.AVAILABLE
        mcx = self.market_family is IntradayMarketFamily.MCX
        expected_directional = (
            self.completed_five_minute_close - self.entry_reference
            if self.direction is SemanticDirection.LONG
            else self.entry_reference - self.completed_five_minute_close
        )
        expected_normalized = (
            expected_directional / self.atr14.value
            if self.atr14.value is not None
            else None
        )
        if (
            not _texts((
                self.wo13_trade_plan_identity, self.wo13_trade_plan_integrity,
                self.timing_cycle_id, self.timing_result_identity,
                self.timing_result_integrity, self.timing_observation_identity,
                self.timing_observation_integrity, self.canonical_subject_identity,
                self.instrument_identity, self.session_identity, self.calendar_identity,
                self.calendar_version, self.measurement_evidence_identity,
                self.measurement_evidence_integrity,
            ))
            or type(self.market_family) is not IntradayMarketFamily
            or mcx != (self.actual_contract_identity is not None)
            or mcx != (self.roll_lineage_identity is not None)
            or not _aware(self.observation_boundary)
            or self.direction not in {SemanticDirection.LONG, SemanticDirection.SHORT}
            or type(self.qualification_path) is not Wo15QualificationPath
            or type(self.timing_state_observed) is not Wo15TimingState
            or self.directional_extension != expected_directional
            or self.absolute_extension != abs(
                self.completed_five_minute_close - self.entry_reference
            )
            or normalized != (self.normalized_directional_extension is not None)
            or normalized != (self.atr14.availability is Wo15TelemetryAvailability.AVAILABLE)
            or self.normalized_directional_extension != expected_normalized
            or self.atr14.canonical_subject_identity != self.canonical_subject_identity
            or self.atr14.instrument_identity != self.instrument_identity
            or self.atr14.actual_contract_identity != self.actual_contract_identity
            or self.atr14.roll_lineage_identity != self.roll_lineage_identity
            or self.atr14.session_identity != self.session_identity
            or self.atr14.observation_boundary != self.observation_boundary
            or excursions != all(item is not None for item in (
                self.maximum_favourable_extension,
                self.maximum_adverse_distance,
                self.maximum_extension_before_qualification,
            ))
            or self.extension_severity != WO15_EXTENSION_SEVERITY
            or type(self.retest_occurred) is not bool
            or type(self.latency) is not Wo15LatencyTelemetry
            or any(type(item) is not Wo15ResearchReference for item in self.research_references)
            or len(self.source_evidence_identities) != len(self.source_evidence_integrities)
            or not _texts(self.source_evidence_identities)
            or not _texts(self.source_evidence_integrities)
            or self.policy_identity != WO15_POLICY_IDENTITY
            or self.policy_version != WO15_POLICY_VERSION
            or self.policy_checksum != WO15_POLICY_CHECKSUM
            or self.schema_identity != WO15_TELEMETRY_IDENTITY
            or self.schema_version != WO15_TELEMETRY_VERSION
            or self.authority != WO15_TELEMETRY_AUTHORITY
            or any((
                self.timing_decision_authority, self.geometry_authority,
                self.risk_authority, self.sponsor_decision_authority,
                self.execution_authority, self.broker_authority,
            ))
            or self.telemetry_identity != _identity("INTRADAY-WO15-TELEMETRY-", values)
            or self.telemetry_integrity
            != _identity("INTEGRITY-INTRADAY-WO15-TELEMETRY-", values)
        ):
            raise Wo15TelemetryError("WO15_RESEARCH_TELEMETRY_INVALID")


def bind_wo15_telemetry_candle(
    *,
    source: GovernedHistoricalCandlePayload,
    evidence: Wo15FiveMinuteEvidence,
    admission: Wo15Wo13Handoff,
    session: Wo15SessionBinding,
    sequence_index: int,
) -> Wo15TelemetryCandle:
    """Bind a completed source candle to exact WO-15 product lineage."""

    try:
        source.__post_init__()
        evidence.__post_init__()
        admission.__post_init__()
        session.__post_init__()
    except (ValueError, TypeError) as error:
        raise Wo15TelemetryError("WO15_TELEMETRY_SOURCE_INVALID") from error
    pairs = (
        (source.candle_identity, evidence.source_candle_identity),
        (source.integrity_identity, evidence.source_candle_integrity),
        (source.canonical_subject_identity, admission.canonical_subject_identity),
        (source.market_session_identity, session.session_identity),
        (source.exchange, session.exchange),
        (evidence.evidence_identity, evidence.evidence_identity),
        (evidence.canonical_subject_identity, admission.canonical_subject_identity),
        (evidence.instrument_identity, admission.instrument_identity),
        (evidence.actual_contract_identity, admission.actual_contract_identity),
        (evidence.roll_lineage_identity, admission.roll_lineage_identity),
        (evidence.session_identity, session.session_identity),
        (evidence.candle_start, source.candle_start),
        (evidence.candle_end, source.candle_end),
    )
    if any(left != right for left, right in pairs) or evidence.timeframe != "5M":
        raise Wo15TelemetryError("WO15_TELEMETRY_LINEAGE_MISMATCH")
    values = {
        "source_candle_identity": source.candle_identity,
        "source_candle_integrity": source.integrity_identity,
        "evidence_identity": evidence.evidence_identity,
        "evidence_integrity": evidence.evidence_integrity,
        "canonical_subject_identity": admission.canonical_subject_identity,
        "market_family": admission.market_family,
        "instrument_identity": admission.instrument_identity,
        "actual_contract_identity": admission.actual_contract_identity,
        "roll_lineage_identity": admission.roll_lineage_identity,
        "session_identity": session.session_identity,
        "candle_start": source.candle_start,
        "candle_end": source.candle_end,
        "observation_boundary": evidence.observation_boundary,
        "open": source.open,
        "high": source.high,
        "low": source.low,
        "close": source.close,
        "volume": source.volume,
        "sequence_index": sequence_index,
        "schema_version": WO15_TELEMETRY_VERSION,
    }
    return Wo15TelemetryCandle(
        candle_binding_identity=_identity("INTRADAY-WO15-TELEMETRY-CANDLE-", values),
        candle_binding_integrity=_identity(
            "INTEGRITY-INTRADAY-WO15-TELEMETRY-CANDLE-", values
        ),
        **values,
    )


def create_wo15_research_reference(
    *,
    role: Wo15ResearchRole,
    locality: Wo15ResearchLocality,
    availability: Wo15TelemetryAvailability,
    canonical_subject_identity: str,
    observation_boundary: datetime,
    facts: tuple[tuple[str, str], ...] = (),
    source_identities: tuple[str, ...] = (),
    source_integrities: tuple[str, ...] = (),
    instrument_identity: str | None = None,
    actual_contract_identity: str | None = None,
    roll_lineage_identity: str | None = None,
) -> Wo15ResearchReference:
    values = {
        "role": role,
        "locality": locality,
        "availability": availability,
        "canonical_subject_identity": canonical_subject_identity,
        "instrument_identity": instrument_identity,
        "actual_contract_identity": actual_contract_identity,
        "roll_lineage_identity": roll_lineage_identity,
        "observation_boundary": observation_boundary,
        "facts": facts,
        "source_identities": source_identities,
        "source_integrities": source_integrities,
        "authority": "RESEARCH_CONTEXT_ONLY",
        "schema_version": WO15_TELEMETRY_VERSION,
    }
    return Wo15ResearchReference(
        reference_identity=_identity("INTRADAY-WO15-RESEARCH-REFERENCE-", values),
        reference_integrity=_identity(
            "INTEGRITY-INTRADAY-WO15-RESEARCH-REFERENCE-", values
        ),
        **values,
    )


def calculate_wo15_atr14(
    *,
    admission: Wo15Wo13Handoff,
    session: Wo15SessionBinding,
    history: Sequence[Wo15TelemetryCandle],
    observation_boundary: datetime,
) -> Wo15Atr14Observation:
    candles = tuple(history)
    _validate_history(admission, session, candles, observation_boundary)
    reason: Wo15AtrUnavailableReason | None = None
    value: Decimal | None = None
    if len(candles) < WO15_ATR14_PERIOD + 1:
        reason = Wo15AtrUnavailableReason.INSUFFICIENT_HISTORY
    elif any(
        current.candle_start != previous.candle_end
        or current.sequence_index != previous.sequence_index + 1
        for previous, current in zip(candles, candles[1:])
    ):
        reason = Wo15AtrUnavailableReason.HISTORY_INCOMPLETE
    else:
        true_ranges = tuple(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
            for previous, current in zip(candles, candles[1:])
        )
        value = sum(true_ranges[:WO15_ATR14_PERIOD], Decimal(0)) / Decimal(
            WO15_ATR14_PERIOD
        )
        for true_range in true_ranges[WO15_ATR14_PERIOD:]:
            value = (
                value * Decimal(WO15_ATR14_PERIOD - 1) + true_range
            ) / Decimal(WO15_ATR14_PERIOD)
        if not value.is_finite() or value <= 0:
            value = None
            reason = Wo15AtrUnavailableReason.NON_POSITIVE_ATR
    availability = (
        Wo15TelemetryAvailability.AVAILABLE
        if value is not None
        else Wo15TelemetryAvailability.UNAVAILABLE
    )
    values = {
        "availability": availability,
        "value": value,
        "unavailable_reason": reason,
        "canonical_subject_identity": admission.canonical_subject_identity,
        "instrument_identity": admission.instrument_identity,
        "actual_contract_identity": admission.actual_contract_identity,
        "roll_lineage_identity": admission.roll_lineage_identity,
        "session_identity": session.session_identity,
        "observation_boundary": observation_boundary,
        "source_candle_identities": tuple(item.source_candle_identity for item in candles),
        "source_candle_integrities": tuple(item.source_candle_integrity for item in candles),
        "schema_identity": WO15_ATR14_IDENTITY,
        "schema_version": WO15_TELEMETRY_VERSION,
        "method": WO15_ATR14_METHOD,
        "period": WO15_ATR14_PERIOD,
        "authority": "NON_DIRECTIONAL_NORMALIZER_ONLY",
    }
    return Wo15Atr14Observation(
        atr_identity=_identity("INTRADAY-WO15-ATR14-", values),
        atr_integrity=_identity("INTEGRITY-INTRADAY-WO15-ATR14-", values),
        **values,
    )


def build_wo15_research_telemetry(
    *,
    admission: Wo15Wo13Handoff,
    session: Wo15SessionBinding,
    timing_result: Wo15TimingEvaluationResult,
    measurement: Wo15TelemetryCandle,
    atr_history: Sequence[Wo15TelemetryCandle],
    cycle_history: Sequence[Wo15TelemetryCandle],
    research_references: Sequence[Wo15ResearchReference] = (),
) -> Wo15ResearchTelemetry:
    """Measure research facts without changing the supplied WO-15B result."""

    before = (timing_result.result_identity, timing_result.result_integrity,
              timing_result.current_state, timing_result.qualification_path)
    cycle_evaluation = timing_result.cycle_evaluation
    history = timing_result.local_history
    if cycle_evaluation is None or history is None or timing_result.timing_cycle_id is None:
        raise Wo15TelemetryError("WO15_TELEMETRY_CYCLE_REQUIRED")
    cycle = cycle_evaluation.cycle
    observation = cycle_evaluation.observation
    mandatory_pairs = (
        (timing_result.wo13_trade_plan_identity, admission.wo13_trade_plan_identity),
        (cycle.wo13_trade_plan_identity, admission.wo13_trade_plan_identity),
        (cycle.wo13_trade_plan_integrity, admission.wo13_trade_plan_integrity),
        (timing_result.timing_cycle_id, cycle.timing_cycle_id),
        (measurement.evidence_identity, timing_result.evidence_identity),
        (measurement.evidence_integrity, timing_result.evidence_integrity),
        (measurement.candle_end, timing_result.observation_boundary),
        (measurement.canonical_subject_identity, admission.canonical_subject_identity),
        (measurement.instrument_identity, admission.instrument_identity),
        (measurement.actual_contract_identity, admission.actual_contract_identity),
        (measurement.roll_lineage_identity, admission.roll_lineage_identity),
        (measurement.session_identity, session.session_identity),
        (cycle.session_identity, session.session_identity),
        (cycle.calendar_identity, session.calendar_identity),
        (cycle.calendar_version, session.calendar_version),
        (cycle.direction, admission.direction),
        (cycle.setup_family, admission.setup_family),
        (cycle.entry_reference, admission.entry_reference),
    )
    if any(left != right for left, right in mandatory_pairs):
        raise Wo15TelemetryError("WO15_TELEMETRY_LINEAGE_MISMATCH")
    atr_candles = tuple(atr_history)
    candles = tuple(cycle_history)
    _validate_history(admission, session, atr_candles, measurement.candle_end)
    _validate_history(admission, session, candles, measurement.candle_end)
    if candles[0].candle_end != cycle.cycle_creation_boundary:
        raise Wo15TelemetryError("WO15_TELEMETRY_CYCLE_HISTORY_MISMATCH")
    if any(
        item.source_candle_identity != measurement.source_candle_identity
        or item.source_candle_integrity != measurement.source_candle_integrity
        or item.evidence_identity != measurement.evidence_identity
        or item.evidence_integrity != measurement.evidence_integrity
        for item in (atr_candles[-1], candles[-1])
    ):
        raise Wo15TelemetryError("WO15_TELEMETRY_MEASUREMENT_NOT_LATEST")
    references = tuple(research_references)
    for reference in references:
        _validate_reference(reference, admission, measurement.candle_end)

    entry = admission.entry_reference
    close = measurement.close
    directional = (
        close - entry
        if admission.direction is SemanticDirection.LONG
        else entry - close
    )
    atr = calculate_wo15_atr14(
        admission=admission,
        session=session,
        history=atr_candles,
        observation_boundary=measurement.candle_end,
    )
    normalized = directional / atr.value if atr.value is not None else None
    normalized_availability = (
        Wo15TelemetryAvailability.AVAILABLE
        if normalized is not None
        else Wo15TelemetryAvailability.UNAVAILABLE
    )
    directional_history = tuple(
        item.close - entry
        if admission.direction is SemanticDirection.LONG
        else entry - item.close
        for item in candles
    )
    excursion_availability = (
        Wo15TelemetryAvailability.AVAILABLE
        if directional_history
        else Wo15TelemetryAvailability.UNAVAILABLE
    )
    favourable = max((max(Decimal(0), item) for item in directional_history), default=None)
    adverse = max((max(Decimal(0), -item) for item in directional_history), default=None)
    qualification_boundary = history.first_qualification_boundary
    before_qualification = tuple(
        value
        for candle, value in zip(candles, directional_history)
        if qualification_boundary is None or candle.candle_end <= qualification_boundary
    )
    maximum_before = max(before_qualification, default=None)
    latency = _latency(admission, timing_result, candles)
    source_ids = (
        admission.wo13_trade_plan_identity,
        timing_result.result_identity,
        observation.observation_identity,
        *(item.candle_binding_identity for item in atr_candles),
        *(item.candle_binding_identity for item in candles),
        *(item.reference_identity for item in references),
    )
    source_integrities = (
        admission.wo13_trade_plan_integrity,
        timing_result.result_integrity,
        observation.observation_integrity,
        *(item.candle_binding_integrity for item in atr_candles),
        *(item.candle_binding_integrity for item in candles),
        *(item.reference_integrity for item in references),
    )
    values = {
        "wo13_trade_plan_identity": admission.wo13_trade_plan_identity,
        "wo13_trade_plan_integrity": admission.wo13_trade_plan_integrity,
        "timing_cycle_id": timing_result.timing_cycle_id,
        "timing_result_identity": timing_result.result_identity,
        "timing_result_integrity": timing_result.result_integrity,
        "timing_observation_identity": observation.observation_identity,
        "timing_observation_integrity": observation.observation_integrity,
        "canonical_subject_identity": admission.canonical_subject_identity,
        "market_family": admission.market_family,
        "instrument_identity": admission.instrument_identity,
        "actual_contract_identity": admission.actual_contract_identity,
        "roll_lineage_identity": admission.roll_lineage_identity,
        "session_identity": session.session_identity,
        "calendar_identity": session.calendar_identity,
        "calendar_version": session.calendar_version,
        "observation_boundary": measurement.candle_end,
        "measurement_evidence_identity": measurement.evidence_identity,
        "measurement_evidence_integrity": measurement.evidence_integrity,
        "direction": admission.direction,
        "qualification_path": timing_result.qualification_path,
        "timing_state_observed": timing_result.current_state,
        "entry_reference": entry,
        "completed_five_minute_close": close,
        "directional_extension": directional,
        "absolute_extension": abs(close - entry),
        "atr14": atr,
        "normalized_directional_extension": normalized,
        "normalized_extension_availability": normalized_availability,
        "extension_severity": WO15_EXTENSION_SEVERITY,
        "maximum_favourable_extension": favourable,
        "maximum_adverse_distance": adverse,
        "maximum_extension_before_qualification": maximum_before,
        "excursion_availability": excursion_availability,
        "retest_occurred": history.retest_boundary is not None,
        "latency": latency,
        "research_references": references,
        "source_evidence_identities": source_ids,
        "source_evidence_integrities": source_integrities,
        "policy_identity": WO15_POLICY_IDENTITY,
        "policy_version": WO15_POLICY_VERSION,
        "policy_checksum": WO15_POLICY_CHECKSUM,
        "schema_identity": WO15_TELEMETRY_IDENTITY,
        "schema_version": WO15_TELEMETRY_VERSION,
        "authority": WO15_TELEMETRY_AUTHORITY,
        "timing_decision_authority": False,
        "geometry_authority": False,
        "risk_authority": False,
        "sponsor_decision_authority": False,
        "execution_authority": False,
        "broker_authority": False,
    }
    telemetry = Wo15ResearchTelemetry(
        telemetry_identity=_identity("INTRADAY-WO15-TELEMETRY-", values),
        telemetry_integrity=_identity("INTEGRITY-INTRADAY-WO15-TELEMETRY-", values),
        **values,
    )
    after = (timing_result.result_identity, timing_result.result_integrity,
             timing_result.current_state, timing_result.qualification_path)
    if before != after:
        raise Wo15TelemetryError("WO15_TIMING_RESULT_MUTATED")
    return telemetry


def _validate_history(
    admission: Wo15Wo13Handoff,
    session: Wo15SessionBinding,
    candles: tuple[Wo15TelemetryCandle, ...],
    observation_boundary: datetime,
) -> None:
    if not candles or not _aware(observation_boundary):
        raise Wo15TelemetryError("WO15_TELEMETRY_HISTORY_INVALID")
    for item in candles:
        try:
            item.__post_init__()
        except (ValueError, TypeError) as error:
            raise Wo15TelemetryError("WO15_TELEMETRY_HISTORY_INVALID") from error
        if (
            item.canonical_subject_identity != admission.canonical_subject_identity
            or item.market_family is not admission.market_family
            or item.instrument_identity != admission.instrument_identity
            or item.actual_contract_identity != admission.actual_contract_identity
            or item.roll_lineage_identity != admission.roll_lineage_identity
            or item.session_identity != session.session_identity
            or item.candle_end > observation_boundary
        ):
            raise Wo15TelemetryError("WO15_TELEMETRY_LINEAGE_MISMATCH")
    if any(
        current.candle_end <= previous.candle_end
        or current.sequence_index <= previous.sequence_index
        for previous, current in zip(candles, candles[1:])
    ) or candles[-1].candle_end != observation_boundary:
        raise Wo15TelemetryError("WO15_TELEMETRY_HISTORY_INVALID")


def _validate_reference(
    reference: Wo15ResearchReference,
    admission: Wo15Wo13Handoff,
    observation_boundary: datetime,
) -> None:
    try:
        reference.__post_init__()
    except (ValueError, TypeError) as error:
        raise Wo15TelemetryError("WO15_RESEARCH_REFERENCE_INVALID") from error
    if reference.observation_boundary > observation_boundary:
        raise Wo15TelemetryError("WO15_RESEARCH_REFERENCE_FUTURE")
    if reference.locality is Wo15ResearchLocality.LOCAL_ANALYTICAL_SUBJECT and (
        reference.canonical_subject_identity != admission.canonical_subject_identity
        or reference.instrument_identity != admission.instrument_identity
        or reference.actual_contract_identity != admission.actual_contract_identity
        or reference.roll_lineage_identity != admission.roll_lineage_identity
    ):
        raise Wo15TelemetryError("WO15_RESEARCH_REFERENCE_LINEAGE_MISMATCH")


def _latency(
    admission: Wo15Wo13Handoff,
    timing_result: Wo15TimingEvaluationResult,
    candles: tuple[Wo15TelemetryCandle, ...],
) -> Wo15LatencyTelemetry:
    history = timing_result.local_history
    if history is None or not candles:
        return Wo15LatencyTelemetry(*(None for _ in range(8)))
    first = candles[0]
    by_boundary = {item.candle_end: item.sequence_index for item in candles}
    interaction_at = history.first_entry_interaction_at
    qualification_at = history.first_qualification_at
    interaction_boundary = history.first_entry_interaction_boundary
    qualification_boundary = history.first_qualification_boundary
    first_index = first.sequence_index
    interaction_index = by_boundary.get(interaction_boundary)
    qualification_index = by_boundary.get(qualification_boundary)
    return Wo15LatencyTelemetry(
        plan_to_first_evaluation=first.candle_end - admission.analysis_boundary,
        plan_to_first_interaction=(
            interaction_at - admission.analysis_boundary
            if interaction_at is not None else None
        ),
        first_interaction_to_qualification=(
            qualification_at - interaction_at
            if interaction_at is not None and qualification_at is not None else None
        ),
        first_evaluation_to_qualification=(
            qualification_at - first.candle_end
            if qualification_at is not None else None
        ),
        bars_plan_to_first_evaluation=first_index,
        bars_first_evaluation_to_interaction=(
            interaction_index - first_index if interaction_index is not None else None
        ),
        bars_interaction_to_qualification=(
            qualification_index - interaction_index
            if qualification_index is not None and interaction_index is not None else None
        ),
        bars_first_evaluation_to_qualification=(
            qualification_index - first_index if qualification_index is not None else None
        ),
    )


def _without(value: object, *names: str) -> dict[str, object]:
    return {
        field.name: getattr(value, field.name)
        for field in fields(value)  # type: ignore[arg-type]
        if field.name not in names
    }


def _identity(prefix: str, values: Mapping[str, object]) -> str:
    payload = json.dumps(
        _normalise(values), ensure_ascii=True, separators=(",", ":"), sort_keys=True
    )
    return f"{prefix}{sha256(payload.encode('utf-8')).hexdigest()}"


def _normalise(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _normalise(item) for key, item in value.items()}
    if is_dataclass(value):
        return _normalise(asdict(value))
    if isinstance(value, (tuple, list)):
        return [_normalise(item) for item in value]
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, timedelta):
        return str(value.total_seconds())
    return value


def _decimal(value: Decimal) -> Decimal:
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as error:
        raise Wo15TelemetryError("WO15_TELEMETRY_DECIMAL_INVALID") from error
    if not result.is_finite():
        raise Wo15TelemetryError("WO15_TELEMETRY_DECIMAL_INVALID")
    return result


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None


def _texts(values: Sequence[object]) -> bool:
    return all(isinstance(value, str) and bool(value) for value in values)


__all__ = [
    "WO15_ATR14_IDENTITY", "WO15_ATR14_METHOD", "WO15_ATR14_PERIOD",
    "WO15_EXTENSION_SEVERITY", "WO15_TELEMETRY_AUTHORITY",
    "WO15_TELEMETRY_IDENTITY", "WO15_TELEMETRY_VERSION",
    "Wo15Atr14Observation", "Wo15AtrUnavailableReason", "Wo15LatencyTelemetry",
    "Wo15ResearchLocality", "Wo15ResearchReference", "Wo15ResearchRole",
    "Wo15ResearchTelemetry", "Wo15TelemetryAvailability", "Wo15TelemetryCandle",
    "Wo15TelemetryError", "bind_wo15_telemetry_candle",
    "build_wo15_research_telemetry", "calculate_wo15_atr14",
    "create_wo15_research_reference",
]
