"""WO-06 Part-1 qualification research contracts and Narrow CPR V0 facts.

This module owns deterministic research artifacts only.  It does not admit a
Probable, rank a subject, create a trade, or establish execution eligibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json
from statistics import median
from typing import Iterable, Mapping


QUALIFICATION_CONTRACT_IDENTITY = (
    "KRONOS-INTRADAY-NATIVE-DISCOVERY-QUALIFICATION-V0"
)
QUALIFICATION_CONTRACT_VERSION = "0.1.0"
QUALIFICATION_HYPOTHESIS_IDENTITY = (
    "KRONOS-INTRADAY-QUALIFICATION-HYPOTHESIS-V0"
)
QUALIFICATION_CORPUS_IDENTITY = "KRONOS-INTRADAY-QUALIFICATION-CORPUS-V0"
QUALIFICATION_OBSERVATION_IDENTITY = (
    "KRONOS-INTRADAY-QUALIFICATION-OBSERVATION-V0"
)
POPULATION_DIAGNOSTICS_IDENTITY = (
    "KRONOS-INTRADAY-QUALIFICATION-POPULATION-DIAGNOSTICS-V0"
)
QUALIFICATION_REPORT_IDENTITY = "KRONOS-INTRADAY-QUALIFICATION-REPORT-V0"
FACTUAL_OUTCOME_CONTRACT_IDENTITY = (
    "KRONOS-INTRADAY-QUALIFICATION-FACTUAL-OUTCOME-V0"
)
NARROW_CPR_FACT_IDENTITY = "KRONOS-INTRADAY-NARROW-CPR-KGS-V0"
PART1_CONTRACT_VERSION = "0.1.0"
NARROW_CPR_CALCULATION_IDENTITY = "NARROW_CPR_KGS_V0"


class QualificationFailure(StrEnum):
    INPUT_INVALID = "QUALIFICATION_INPUT_INVALID"
    INTEGRITY_INVALID = "QUALIFICATION_INTEGRITY_INVALID"
    INCOMPLETE_CANDLE = "INCOMPLETE_DAILY_CANDLE_NOT_AUTHORIZED"
    LOOK_AHEAD = "QUALIFICATION_LOOK_AHEAD_REJECTED"
    EVIDENCE_AUTHORITY = "QUALIFICATION_EVIDENCE_AUTHORITY_INVALID"
    OUTCOME_DEFINITION_PENDING = "OUTCOME_DEFINITION_PENDING"
    PERSISTENCE_CONFLICT = "QUALIFICATION_PERSISTENCE_CONFLICT"
    ARTIFACT_UNAVAILABLE = "QUALIFICATION_ARTIFACT_UNAVAILABLE"


class QualificationError(RuntimeError):
    """Sanitized qualification failure."""

    def __init__(self, failure: QualificationFailure) -> None:
        self.failure = failure
        super().__init__(failure.value)


class QualificationEvidenceSource(StrEnum):
    REAL_GOVERNED_MARKET_EVIDENCE = "REAL_GOVERNED_MARKET_EVIDENCE"
    SYNTHETIC_TEST_FIXTURE = "SYNTHETIC_TEST_FIXTURE"


class QualificationEvidenceSufficiency(StrEnum):
    EVIDENCE_UNAVAILABLE = "EVIDENCE_UNAVAILABLE"
    EVIDENCE_INSUFFICIENT = "EVIDENCE_INSUFFICIENT"
    EVIDENCE_ACCUMULATING = "EVIDENCE_ACCUMULATING"
    EVIDENCE_READY_FOR_REVIEW = "EVIDENCE_READY_FOR_REVIEW"


class QualificationHypothesisStatus(StrEnum):
    UNCOMMISSIONED = "UNCOMMISSIONED"
    QUALIFYING = "QUALIFYING"
    SUPPORTED = "SUPPORTED"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    REJECTED = "REJECTED"
    APPROVED_FOR_METHODOLOGY = "APPROVED_FOR_METHODOLOGY"


class QualificationObservationResult(StrEnum):
    HYPOTHESIS_TRUE = "HYPOTHESIS_TRUE"
    HYPOTHESIS_FALSE = "HYPOTHESIS_FALSE"
    UNAVAILABLE = "UNAVAILABLE"
    FACTUAL_FAILURE = "FACTUAL_FAILURE"


class OutcomeDefinitionStatus(StrEnum):
    OUTCOME_DEFINITION_PENDING = "OUTCOME_DEFINITION_PENDING"
    DEFINITION_APPROVED = "DEFINITION_APPROVED"


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    evidence_identity: str
    available_at: datetime
    source: QualificationEvidenceSource
    provenance: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not _text(self.evidence_identity)
            or not _aware(self.available_at)
            or type(self.source) is not QualificationEvidenceSource
            or not _texts(self.provenance)
        ):
            raise QualificationError(QualificationFailure.INPUT_INVALID)


@dataclass(frozen=True, slots=True)
class PreviousCompletedDailyCandle:
    canonical_subject_identity: str
    previous_session_identity: str
    observation_session_identity: str
    source_daily_candle_identity: str
    completed_at: datetime
    observation_boundary: datetime
    high: Decimal
    low: Decimal
    close: Decimal
    completed: bool
    source_integrity_identity: str
    provenance: tuple[str, ...]

    def __post_init__(self) -> None:
        values = (self.high, self.low, self.close)
        if (
            not _text(self.canonical_subject_identity)
            or not _text(self.previous_session_identity)
            or not _text(self.observation_session_identity)
            or self.previous_session_identity == self.observation_session_identity
            or not _text(self.source_daily_candle_identity)
            or not _aware(self.completed_at)
            or not _aware(self.observation_boundary)
            or self.completed_at > self.observation_boundary
            or any(type(value) is not Decimal or not value.is_finite() for value in values)
            or self.close <= 0
            or self.high < self.low
            or self.high < self.close
            or self.low > self.close
            or type(self.completed) is not bool
            or not _text(self.source_integrity_identity)
            or not self.source_integrity_identity.startswith("INTEGRITY-")
            or not _texts(self.provenance)
        ):
            raise QualificationError(QualificationFailure.INPUT_INVALID)
        if not self.completed:
            raise QualificationError(QualificationFailure.INCOMPLETE_CANDLE)


@dataclass(frozen=True, slots=True)
class NarrowCprFact:
    fact_identity: str
    canonical_subject_identity: str
    previous_session_identity: str
    observation_session_identity: str
    source_daily_candle_identity: str
    observation_boundary: datetime
    previous_daily_high: Decimal
    previous_daily_low: Decimal
    previous_daily_close: Decimal
    pivot: Decimal
    bc_raw: Decimal
    tc_raw: Decimal
    cpr_bottom: Decimal
    cpr_top: Decimal
    cpr_half_width: Decimal
    cpr_half_width_pct: Decimal
    cpr_total_width: Decimal
    cpr_total_width_pct: Decimal
    narrow_cpr_kgs_v0: bool
    source_integrity_identity: str
    provenance: tuple[str, ...]
    schema_identity: str = NARROW_CPR_FACT_IDENTITY
    schema_version: str = PART1_CONTRACT_VERSION
    integrity_identity: str = ""

    def __post_init__(self) -> None:
        if (
            not self.fact_identity.startswith("INTRADAY-NARROW-CPR-FACT-")
            or not _text(self.canonical_subject_identity)
            or not _text(self.previous_session_identity)
            or not _text(self.observation_session_identity)
            or not _text(self.source_daily_candle_identity)
            or not _aware(self.observation_boundary)
            or any(
                type(value) is not Decimal or not value.is_finite()
                for value in (
                    self.previous_daily_high,
                    self.previous_daily_low,
                    self.previous_daily_close,
                    self.pivot,
                    self.bc_raw,
                    self.tc_raw,
                    self.cpr_bottom,
                    self.cpr_top,
                    self.cpr_half_width,
                    self.cpr_half_width_pct,
                    self.cpr_total_width,
                    self.cpr_total_width_pct,
                )
            )
            or type(self.narrow_cpr_kgs_v0) is not bool
            or not _text(self.source_integrity_identity)
            or not _texts(self.provenance)
            or self.schema_identity != NARROW_CPR_FACT_IDENTITY
            or self.schema_version != PART1_CONTRACT_VERSION
            or not self.integrity_identity.startswith("INTEGRITY-NARROW-CPR-")
        ):
            raise QualificationError(QualificationFailure.INTEGRITY_INVALID)
        payload = _narrow_cpr_payload(self)
        if self.fact_identity != _identity("INTRADAY-NARROW-CPR-FACT-", payload):
            raise QualificationError(QualificationFailure.INTEGRITY_INVALID)
        if self.integrity_identity != _identity("INTEGRITY-NARROW-CPR-", payload):
            raise QualificationError(QualificationFailure.INTEGRITY_INVALID)


def create_narrow_cpr_fact(candle: PreviousCompletedDailyCandle) -> NarrowCprFact:
    if type(candle) is not PreviousCompletedDailyCandle:
        raise QualificationError(QualificationFailure.INPUT_INVALID)
    three = Decimal(3)
    two = Decimal(2)
    hundred = Decimal(100)
    pivot = (candle.high + candle.low + candle.close) / three
    bc_raw = (candle.high + candle.low) / two
    tc_raw = (two * pivot) - bc_raw
    bottom = min(bc_raw, tc_raw)
    top = max(bc_raw, tc_raw)
    half_width = abs(pivot - bc_raw)
    half_pct = half_width / candle.close * hundred
    total_width = top - bottom
    total_pct = total_width / candle.close * hundred
    payload = {
        "canonical_subject_identity": candle.canonical_subject_identity,
        "previous_session_identity": candle.previous_session_identity,
        "observation_session_identity": candle.observation_session_identity,
        "source_daily_candle_identity": candle.source_daily_candle_identity,
        "observation_boundary": candle.observation_boundary,
        "previous_daily_high": candle.high,
        "previous_daily_low": candle.low,
        "previous_daily_close": candle.close,
        "pivot": pivot,
        "bc_raw": bc_raw,
        "tc_raw": tc_raw,
        "cpr_bottom": bottom,
        "cpr_top": top,
        "cpr_half_width": half_width,
        "cpr_half_width_pct": half_pct,
        "cpr_total_width": total_width,
        "cpr_total_width_pct": total_pct,
        "narrow_cpr_kgs_v0": half_width < Decimal("0.001") * candle.close,
        "source_integrity_identity": candle.source_integrity_identity,
        "provenance": candle.provenance,
        "schema_identity": NARROW_CPR_FACT_IDENTITY,
        "schema_version": PART1_CONTRACT_VERSION,
    }
    return NarrowCprFact(
        fact_identity=_identity("INTRADAY-NARROW-CPR-FACT-", payload),
        integrity_identity=_identity("INTEGRITY-NARROW-CPR-", payload),
        **payload,
    )


@dataclass(frozen=True, slots=True)
class QualificationHypothesis:
    hypothesis_identity: str
    hypothesis_version: str
    name: str
    family: str
    required_evidence_families: tuple[str, ...]
    calculation_identity: str | None
    status: QualificationHypothesisStatus
    evidence_sufficiency: QualificationEvidenceSufficiency
    qualification_corpus_identity: str | None
    population_diagnostics_identity: str | None
    outcome_diagnostics_identity: str | None
    effective_from: datetime
    effective_through: datetime
    provenance: tuple[str, ...]
    real_evidence_count: int
    integrity_identity: str
    schema_identity: str = QUALIFICATION_HYPOTHESIS_IDENTITY
    schema_version: str = PART1_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            not self.hypothesis_identity.startswith("INTRADAY-QUALIFICATION-HYPOTHESIS-")
            or not _text(self.hypothesis_version)
            or not _text(self.name)
            or not _text(self.family)
            or not _texts(self.required_evidence_families)
            or self.calculation_identity is not None and not _text(self.calculation_identity)
            or type(self.status) is not QualificationHypothesisStatus
            or type(self.evidence_sufficiency) is not QualificationEvidenceSufficiency
            or not _aware(self.effective_from)
            or not _aware(self.effective_through)
            or self.effective_from > self.effective_through
            or not _texts(self.provenance)
            or type(self.real_evidence_count) is not int
            or self.real_evidence_count < 0
            or self.schema_identity != QUALIFICATION_HYPOTHESIS_IDENTITY
            or self.schema_version != PART1_CONTRACT_VERSION
            or not self.integrity_identity.startswith("INTEGRITY-QUALIFICATION-HYPOTHESIS-")
            or (
                self.status is QualificationHypothesisStatus.APPROVED_FOR_METHODOLOGY
                and (
                    self.real_evidence_count == 0
                    or self.evidence_sufficiency
                    is not QualificationEvidenceSufficiency.EVIDENCE_READY_FOR_REVIEW
                )
            )
        ):
            raise QualificationError(QualificationFailure.INPUT_INVALID)
        payload = _hypothesis_payload(self)
        if self.hypothesis_identity != _identity(
            "INTRADAY-QUALIFICATION-HYPOTHESIS-", payload
        ) or self.integrity_identity != _identity(
            "INTEGRITY-QUALIFICATION-HYPOTHESIS-", payload
        ):
            raise QualificationError(QualificationFailure.INTEGRITY_INVALID)


def create_qualification_hypothesis(
    *,
    hypothesis_version: str,
    name: str,
    family: str,
    required_evidence_families: tuple[str, ...],
    calculation_identity: str | None,
    status: QualificationHypothesisStatus,
    evidence_sufficiency: QualificationEvidenceSufficiency,
    effective_from: datetime,
    effective_through: datetime,
    provenance: tuple[str, ...],
    real_evidence_count: int = 0,
    qualification_corpus_identity: str | None = None,
    population_diagnostics_identity: str | None = None,
    outcome_diagnostics_identity: str | None = None,
) -> QualificationHypothesis:
    if any(callable(value) for value in required_evidence_families):
        raise QualificationError(QualificationFailure.INPUT_INVALID)
    payload = {
        "hypothesis_version": hypothesis_version,
        "name": name,
        "family": family,
        "required_evidence_families": required_evidence_families,
        "calculation_identity": calculation_identity,
        "status": status,
        "evidence_sufficiency": evidence_sufficiency,
        "qualification_corpus_identity": qualification_corpus_identity,
        "population_diagnostics_identity": population_diagnostics_identity,
        "outcome_diagnostics_identity": outcome_diagnostics_identity,
        "effective_from": effective_from,
        "effective_through": effective_through,
        "provenance": provenance,
        "real_evidence_count": real_evidence_count,
        "schema_identity": QUALIFICATION_HYPOTHESIS_IDENTITY,
        "schema_version": PART1_CONTRACT_VERSION,
    }
    return QualificationHypothesis(
        hypothesis_identity=_identity("INTRADAY-QUALIFICATION-HYPOTHESIS-", payload),
        integrity_identity=_identity("INTEGRITY-QUALIFICATION-HYPOTHESIS-", payload),
        **payload,
    )


def create_narrow_cpr_hypothesis(
    *, effective_from: datetime, effective_through: datetime
) -> QualificationHypothesis:
    return create_qualification_hypothesis(
        hypothesis_version="0.1.0",
        name="Previous-session Narrow CPR qualification hypothesis",
        family="CPR_COMPRESSION",
        required_evidence_families=("PREVIOUS_COMPLETED_1D_CANDLE",),
        calculation_identity=NARROW_CPR_CALCULATION_IDENTITY,
        status=QualificationHypothesisStatus.QUALIFYING,
        evidence_sufficiency=QualificationEvidenceSufficiency.EVIDENCE_UNAVAILABLE,
        effective_from=effective_from,
        effective_through=effective_through,
        provenance=("WO-06-PART-1-SPONSOR-SPECIFIED-NARROW-CPR",),
    )


@dataclass(frozen=True, slots=True)
class FactualOutcomeDefinition:
    definition_identity: str
    definition_version: str
    family: str
    measure_names: tuple[str, ...]
    status: OutcomeDefinitionStatus
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = FACTUAL_OUTCOME_CONTRACT_IDENTITY
    schema_version: str = PART1_CONTRACT_VERSION

    def __post_init__(self) -> None:
        banned = {"entry_fill", "broker_quantity", "pnl", "realised_r", "stop_hit", "target_hit", "trade_win_loss"}
        if (
            not self.definition_identity.startswith("INTRADAY-FACTUAL-OUTCOME-DEFINITION-")
            or not _text(self.definition_version)
            or not _text(self.family)
            or not _texts(self.measure_names)
            or any(item.lower() in banned for item in self.measure_names)
            or type(self.status) is not OutcomeDefinitionStatus
            or not _texts(self.provenance)
            or self.schema_identity != FACTUAL_OUTCOME_CONTRACT_IDENTITY
            or self.schema_version != PART1_CONTRACT_VERSION
        ):
            raise QualificationError(QualificationFailure.INPUT_INVALID)
        payload = _outcome_definition_payload(self)
        if self.definition_identity != _identity(
            "INTRADAY-FACTUAL-OUTCOME-DEFINITION-", payload
        ) or self.integrity_identity != _identity(
            "INTEGRITY-FACTUAL-OUTCOME-DEFINITION-", payload
        ):
            raise QualificationError(QualificationFailure.INTEGRITY_INVALID)


def create_factual_outcome_definition(
    *,
    definition_version: str,
    family: str,
    measure_names: tuple[str, ...],
    status: OutcomeDefinitionStatus,
    provenance: tuple[str, ...],
) -> FactualOutcomeDefinition:
    payload = {
        "definition_version": definition_version,
        "family": family,
        "measure_names": measure_names,
        "status": status,
        "provenance": provenance,
        "schema_identity": FACTUAL_OUTCOME_CONTRACT_IDENTITY,
        "schema_version": PART1_CONTRACT_VERSION,
    }
    return FactualOutcomeDefinition(
        definition_identity=_identity("INTRADAY-FACTUAL-OUTCOME-DEFINITION-", payload),
        integrity_identity=_identity("INTEGRITY-FACTUAL-OUTCOME-DEFINITION-", payload),
        **payload,
    )


@dataclass(frozen=True, slots=True)
class FactualOutcomeRecord:
    outcome_identity: str
    definition_identity: str
    canonical_subject_identity: str
    source_observation_identity: str
    observation_boundary: datetime
    measured_at: datetime
    measures: tuple[tuple[str, Decimal], ...]
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = FACTUAL_OUTCOME_CONTRACT_IDENTITY
    schema_version: str = PART1_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            not self.outcome_identity.startswith("INTRADAY-FACTUAL-OUTCOME-")
            or not _text(self.definition_identity)
            or not _text(self.canonical_subject_identity)
            or not _text(self.source_observation_identity)
            or not _aware(self.observation_boundary)
            or not _aware(self.measured_at)
            or self.measured_at <= self.observation_boundary
            or not self.measures
            or any(
                not _text(name) or type(value) is not Decimal or not value.is_finite()
                for name, value in self.measures
            )
            or not _texts(self.provenance)
            or self.schema_identity != FACTUAL_OUTCOME_CONTRACT_IDENTITY
            or self.schema_version != PART1_CONTRACT_VERSION
        ):
            raise QualificationError(QualificationFailure.INPUT_INVALID)
        payload = _outcome_payload(self)
        if self.outcome_identity != _identity("INTRADAY-FACTUAL-OUTCOME-", payload) or self.integrity_identity != _identity(
            "INTEGRITY-FACTUAL-OUTCOME-", payload
        ):
            raise QualificationError(QualificationFailure.INTEGRITY_INVALID)


def create_factual_outcome_record(
    *,
    definition: FactualOutcomeDefinition,
    canonical_subject_identity: str,
    source_observation_identity: str,
    observation_boundary: datetime,
    measured_at: datetime,
    measures: tuple[tuple[str, Decimal], ...],
    provenance: tuple[str, ...],
) -> FactualOutcomeRecord:
    if (
        type(definition) is not FactualOutcomeDefinition
        or definition.status is not OutcomeDefinitionStatus.DEFINITION_APPROVED
        or tuple(name for name, _ in measures) != definition.measure_names
    ):
        raise QualificationError(QualificationFailure.OUTCOME_DEFINITION_PENDING)
    payload = {
        "definition_identity": definition.definition_identity,
        "canonical_subject_identity": canonical_subject_identity,
        "source_observation_identity": source_observation_identity,
        "observation_boundary": observation_boundary,
        "measured_at": measured_at,
        "measures": measures,
        "provenance": provenance,
        "schema_identity": FACTUAL_OUTCOME_CONTRACT_IDENTITY,
        "schema_version": PART1_CONTRACT_VERSION,
    }
    return FactualOutcomeRecord(
        outcome_identity=_identity("INTRADAY-FACTUAL-OUTCOME-", payload),
        integrity_identity=_identity("INTEGRITY-FACTUAL-OUTCOME-", payload),
        **payload,
    )


@dataclass(frozen=True, slots=True)
class QualificationObservation:
    observation_identity: str
    canonical_subject_identity: str
    market_session_identity: str
    observation_boundary: datetime
    hypothesis_identity: str
    hypothesis_version: str
    evidence: tuple[EvidenceReference, ...]
    result: QualificationObservationResult
    result_fact_identity: str | None
    subsequent_outcome_identity: str | None
    evidence_source: QualificationEvidenceSource
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = QUALIFICATION_OBSERVATION_IDENTITY
    schema_version: str = PART1_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            not self.observation_identity.startswith("INTRADAY-QUALIFICATION-OBSERVATION-")
            or not _text(self.canonical_subject_identity)
            or not _text(self.market_session_identity)
            or not _aware(self.observation_boundary)
            or not _text(self.hypothesis_identity)
            or not _text(self.hypothesis_version)
            or not self.evidence
            or any(type(item) is not EvidenceReference for item in self.evidence)
            or any(item.available_at > self.observation_boundary for item in self.evidence)
            or any(item.source is not self.evidence_source for item in self.evidence)
            or type(self.result) is not QualificationObservationResult
            or self.result_fact_identity is not None and not _text(self.result_fact_identity)
            or self.subsequent_outcome_identity is not None and not _text(self.subsequent_outcome_identity)
            or type(self.evidence_source) is not QualificationEvidenceSource
            or not _texts(self.provenance)
            or self.schema_identity != QUALIFICATION_OBSERVATION_IDENTITY
            or self.schema_version != PART1_CONTRACT_VERSION
        ):
            failure = (
                QualificationFailure.LOOK_AHEAD
                if self.evidence and any(item.available_at > self.observation_boundary for item in self.evidence)
                else QualificationFailure.INPUT_INVALID
            )
            raise QualificationError(failure)
        payload = _observation_payload(self)
        if self.observation_identity != _identity(
            "INTRADAY-QUALIFICATION-OBSERVATION-", payload
        ) or self.integrity_identity != _identity(
            "INTEGRITY-QUALIFICATION-OBSERVATION-", payload
        ):
            raise QualificationError(QualificationFailure.INTEGRITY_INVALID)


def create_qualification_observation(
    *,
    canonical_subject_identity: str,
    market_session_identity: str,
    observation_boundary: datetime,
    hypothesis: QualificationHypothesis,
    evidence: tuple[EvidenceReference, ...],
    result: QualificationObservationResult,
    result_fact_identity: str | None,
    evidence_source: QualificationEvidenceSource,
    provenance: tuple[str, ...],
    subsequent_outcome_identity: str | None = None,
) -> QualificationObservation:
    payload = {
        "canonical_subject_identity": canonical_subject_identity,
        "market_session_identity": market_session_identity,
        "observation_boundary": observation_boundary,
        "hypothesis_identity": hypothesis.hypothesis_identity,
        "hypothesis_version": hypothesis.hypothesis_version,
        "evidence": evidence,
        "result": result,
        "result_fact_identity": result_fact_identity,
        "subsequent_outcome_identity": subsequent_outcome_identity,
        "evidence_source": evidence_source,
        "provenance": provenance,
        "schema_identity": QUALIFICATION_OBSERVATION_IDENTITY,
        "schema_version": PART1_CONTRACT_VERSION,
    }
    return QualificationObservation(
        observation_identity=_identity("INTRADAY-QUALIFICATION-OBSERVATION-", payload),
        integrity_identity=_identity("INTEGRITY-QUALIFICATION-OBSERVATION-", payload),
        **payload,
    )


@dataclass(frozen=True, slots=True)
class PopulationDiagnostics:
    diagnostics_identity: str
    market_session_identity: str
    hypothesis_identity: str
    factual_universe_count: int
    hypothesis_match_count: int
    hypothesis_non_match_count: int
    unavailable_count: int
    factual_failure_count: int
    retention_percentage: Decimal
    stage_survivor_counts: tuple[tuple[str, int], ...]
    final_probables_count: int | None
    long_count: int | None
    short_count: int | None
    neutral_other_count: int | None
    zero_match_session: bool
    over_ten_session: bool
    over_fifteen_session: bool
    twenty_or_more_session: bool
    integrity_identity: str
    schema_identity: str = POPULATION_DIAGNOSTICS_IDENTITY
    schema_version: str = PART1_CONTRACT_VERSION

    def __post_init__(self) -> None:
        counts = (
            self.factual_universe_count,
            self.hypothesis_match_count,
            self.hypothesis_non_match_count,
            self.unavailable_count,
            self.factual_failure_count,
        )
        optional = (
            self.final_probables_count,
            self.long_count,
            self.short_count,
            self.neutral_other_count,
        )
        if (
            not self.diagnostics_identity.startswith("INTRADAY-QUALIFICATION-POPULATION-")
            or not _text(self.market_session_identity)
            or not _text(self.hypothesis_identity)
            or any(type(value) is not int or value < 0 for value in counts)
            or sum(counts[1:]) != self.factual_universe_count
            or type(self.retention_percentage) is not Decimal
            or not self.retention_percentage.is_finite()
            or any(not _text(name) or type(value) is not int or value < 0 for name, value in self.stage_survivor_counts)
            or any(value is not None and (type(value) is not int or value < 0) for value in optional)
            or any(type(value) is not bool for value in (
                self.zero_match_session,
                self.over_ten_session,
                self.over_fifteen_session,
                self.twenty_or_more_session,
            ))
            or self.zero_match_session != (self.hypothesis_match_count == 0)
            or self.over_ten_session != (self.hypothesis_match_count > 10)
            or self.over_fifteen_session != (self.hypothesis_match_count > 15)
            or self.twenty_or_more_session != (self.hypothesis_match_count >= 20)
            or self.schema_identity != POPULATION_DIAGNOSTICS_IDENTITY
            or self.schema_version != PART1_CONTRACT_VERSION
        ):
            raise QualificationError(QualificationFailure.INPUT_INVALID)
        payload = _population_payload(self)
        if self.diagnostics_identity != _identity(
            "INTRADAY-QUALIFICATION-POPULATION-", payload
        ) or self.integrity_identity != _identity(
            "INTEGRITY-QUALIFICATION-POPULATION-", payload
        ):
            raise QualificationError(QualificationFailure.INTEGRITY_INVALID)


def create_population_diagnostics(
    *,
    market_session_identity: str,
    hypothesis_identity: str,
    observations: Iterable[QualificationObservation],
    stage_survivor_counts: tuple[tuple[str, int], ...] = (),
) -> PopulationDiagnostics:
    retained = tuple(observations)
    if any(type(item) is not QualificationObservation for item in retained):
        raise QualificationError(QualificationFailure.INPUT_INVALID)
    result_counts = {
        result: sum(item.result is result for item in retained)
        for result in QualificationObservationResult
    }
    total = len(retained)
    matches = result_counts[QualificationObservationResult.HYPOTHESIS_TRUE]
    retention = Decimal(0) if total == 0 else Decimal(matches) / Decimal(total) * Decimal(100)
    payload = {
        "market_session_identity": market_session_identity,
        "hypothesis_identity": hypothesis_identity,
        "factual_universe_count": total,
        "hypothesis_match_count": matches,
        "hypothesis_non_match_count": result_counts[QualificationObservationResult.HYPOTHESIS_FALSE],
        "unavailable_count": result_counts[QualificationObservationResult.UNAVAILABLE],
        "factual_failure_count": result_counts[QualificationObservationResult.FACTUAL_FAILURE],
        "retention_percentage": retention,
        "stage_survivor_counts": stage_survivor_counts,
        "final_probables_count": None,
        "long_count": None,
        "short_count": None,
        "neutral_other_count": None,
        "zero_match_session": matches == 0,
        "over_ten_session": matches > 10,
        "over_fifteen_session": matches > 15,
        "twenty_or_more_session": matches >= 20,
        "schema_identity": POPULATION_DIAGNOSTICS_IDENTITY,
        "schema_version": PART1_CONTRACT_VERSION,
    }
    return PopulationDiagnostics(
        diagnostics_identity=_identity("INTRADAY-QUALIFICATION-POPULATION-", payload),
        integrity_identity=_identity("INTEGRITY-QUALIFICATION-POPULATION-", payload),
        **payload,
    )


@dataclass(frozen=True, slots=True)
class QualificationCorpusSession:
    session_record_identity: str
    market_session_identity: str
    observation_boundary: datetime
    universe_publication_identity: str
    reconciliation_publication_identity: str
    discovery_run_identity: str | None
    factual_evidence_identities: tuple[str, ...]
    hypothesis_identities: tuple[str, ...]
    outcome_evidence_window_identity: str | None
    population_diagnostics_identity: str
    provenance: tuple[str, ...]
    integrity_identity: str

    def __post_init__(self) -> None:
        if (
            not self.session_record_identity.startswith("INTRADAY-QUALIFICATION-CORPUS-SESSION-")
            or not _text(self.market_session_identity)
            or not _aware(self.observation_boundary)
            or not _text(self.universe_publication_identity)
            or not _text(self.reconciliation_publication_identity)
            or self.discovery_run_identity is not None and not _text(self.discovery_run_identity)
            or not _texts(self.factual_evidence_identities)
            or not _texts(self.hypothesis_identities)
            or self.outcome_evidence_window_identity is not None and not _text(self.outcome_evidence_window_identity)
            or not _text(self.population_diagnostics_identity)
            or not _texts(self.provenance)
        ):
            raise QualificationError(QualificationFailure.INPUT_INVALID)
        payload = _corpus_session_payload(self)
        if self.session_record_identity != _identity(
            "INTRADAY-QUALIFICATION-CORPUS-SESSION-", payload
        ) or self.integrity_identity != _identity(
            "INTEGRITY-QUALIFICATION-CORPUS-SESSION-", payload
        ):
            raise QualificationError(QualificationFailure.INTEGRITY_INVALID)


def create_qualification_corpus_session(
    *,
    market_session_identity: str,
    observation_boundary: datetime,
    universe_publication_identity: str,
    reconciliation_publication_identity: str,
    discovery_run_identity: str | None,
    factual_evidence_identities: tuple[str, ...],
    hypothesis_identities: tuple[str, ...],
    outcome_evidence_window_identity: str | None,
    population_diagnostics_identity: str,
    provenance: tuple[str, ...],
) -> QualificationCorpusSession:
    payload = {
        "market_session_identity": market_session_identity,
        "observation_boundary": observation_boundary,
        "universe_publication_identity": universe_publication_identity,
        "reconciliation_publication_identity": reconciliation_publication_identity,
        "discovery_run_identity": discovery_run_identity,
        "factual_evidence_identities": factual_evidence_identities,
        "hypothesis_identities": hypothesis_identities,
        "outcome_evidence_window_identity": outcome_evidence_window_identity,
        "population_diagnostics_identity": population_diagnostics_identity,
        "provenance": provenance,
    }
    return QualificationCorpusSession(
        session_record_identity=_identity(
            "INTRADAY-QUALIFICATION-CORPUS-SESSION-", payload
        ),
        integrity_identity=_identity(
            "INTEGRITY-QUALIFICATION-CORPUS-SESSION-", payload
        ),
        **payload,
    )


@dataclass(frozen=True, slots=True)
class QualificationCorpus:
    corpus_identity: str
    corpus_version: str
    sessions: tuple[QualificationCorpusSession, ...]
    observations: tuple[QualificationObservation, ...]
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = QUALIFICATION_CORPUS_IDENTITY
    schema_version: str = PART1_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            not self.corpus_identity.startswith("INTRADAY-QUALIFICATION-CORPUS-")
            or not _text(self.corpus_version)
            or not self.sessions
            or any(type(item) is not QualificationCorpusSession for item in self.sessions)
            or not self.observations
            or any(type(item) is not QualificationObservation for item in self.observations)
            or not _texts(self.provenance)
            or self.schema_identity != QUALIFICATION_CORPUS_IDENTITY
            or self.schema_version != PART1_CONTRACT_VERSION
        ):
            raise QualificationError(QualificationFailure.INPUT_INVALID)
        session_ids = {item.market_session_identity for item in self.sessions}
        if any(item.market_session_identity not in session_ids for item in self.observations):
            raise QualificationError(QualificationFailure.INPUT_INVALID)
        payload = _corpus_payload(self)
        if self.corpus_identity != _identity("INTRADAY-QUALIFICATION-CORPUS-", payload) or self.integrity_identity != _identity(
            "INTEGRITY-QUALIFICATION-CORPUS-", payload
        ):
            raise QualificationError(QualificationFailure.INTEGRITY_INVALID)


def create_qualification_corpus(
    *, corpus_version: str,
    sessions: tuple[QualificationCorpusSession, ...],
    observations: tuple[QualificationObservation, ...],
    provenance: tuple[str, ...],
) -> QualificationCorpus:
    payload = {
        "corpus_version": corpus_version,
        "sessions": sessions,
        "observations": observations,
        "provenance": provenance,
        "schema_identity": QUALIFICATION_CORPUS_IDENTITY,
        "schema_version": PART1_CONTRACT_VERSION,
    }
    return QualificationCorpus(
        corpus_identity=_identity("INTRADAY-QUALIFICATION-CORPUS-", payload),
        integrity_identity=_identity("INTEGRITY-QUALIFICATION-CORPUS-", payload),
        **payload,
    )


@dataclass(frozen=True, slots=True)
class QualificationReport:
    report_identity: str
    report_version: str
    corpus_identity: str
    corpus_version: str
    hypothesis_identities: tuple[str, ...]
    session_count: int
    observation_count: int
    real_evidence_count: int
    synthetic_fixture_count: int
    evidence_sufficiency: QualificationEvidenceSufficiency
    mean_match_population: Decimal
    median_match_population: Decimal
    minimum_match_population: int
    maximum_match_population: int
    match_population_distribution: tuple[tuple[int, int], ...]
    stage_survivor_totals: tuple[tuple[str, int], ...]
    zero_match_session_count: int
    over_ten_session_count: int
    over_fifteen_session_count: int
    twenty_or_more_session_count: int
    hypothesis_true_count: int
    hypothesis_false_count: int
    match_percentage: Decimal
    outcome_available: bool
    unresolved_methodology_questions: tuple[str, ...]
    conclusion: str
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = QUALIFICATION_REPORT_IDENTITY
    schema_version: str = PART1_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            not self.report_identity.startswith("INTRADAY-QUALIFICATION-REPORT-")
            or not _text(self.report_version)
            or not _text(self.corpus_identity)
            or not _text(self.corpus_version)
            or not _texts(self.hypothesis_identities)
            or any(type(value) is not int or value < 0 for value in (
                self.session_count,
                self.observation_count,
                self.real_evidence_count,
                self.synthetic_fixture_count,
                self.minimum_match_population,
                self.maximum_match_population,
                self.zero_match_session_count,
                self.over_ten_session_count,
                self.over_fifteen_session_count,
                self.twenty_or_more_session_count,
                self.hypothesis_true_count,
                self.hypothesis_false_count,
            ))
            or self.real_evidence_count + self.synthetic_fixture_count != self.observation_count
            or type(self.evidence_sufficiency) is not QualificationEvidenceSufficiency
            or any(type(value) is not Decimal or not value.is_finite() for value in (
                self.mean_match_population,
                self.median_match_population,
                self.match_percentage,
            ))
            or type(self.outcome_available) is not bool
            or any(
                not _text(name) or type(value) is not int or value < 0
                for name, value in self.stage_survivor_totals
            )
            or not _texts(self.unresolved_methodology_questions)
            or not _text(self.conclusion)
            or not _texts(self.provenance)
            or self.real_evidence_count == 0 and self.conclusion != "MARKET_USEFULNESS_NOT_ESTABLISHED"
            or self.schema_identity != QUALIFICATION_REPORT_IDENTITY
            or self.schema_version != PART1_CONTRACT_VERSION
        ):
            raise QualificationError(QualificationFailure.INPUT_INVALID)
        payload = _report_payload(self)
        if self.report_identity != _identity("INTRADAY-QUALIFICATION-REPORT-", payload) or self.integrity_identity != _identity(
            "INTEGRITY-QUALIFICATION-REPORT-", payload
        ):
            raise QualificationError(QualificationFailure.INTEGRITY_INVALID)


def create_qualification_report(
    *,
    report_version: str,
    corpus: QualificationCorpus,
    hypotheses: tuple[QualificationHypothesis, ...],
    diagnostics: tuple[PopulationDiagnostics, ...],
    evidence_sufficiency: QualificationEvidenceSufficiency,
    unresolved_methodology_questions: tuple[str, ...],
    provenance: tuple[str, ...],
) -> QualificationReport:
    if (
        type(corpus) is not QualificationCorpus
        or not hypotheses
        or not diagnostics
        or any(type(item) is not QualificationHypothesis for item in hypotheses)
        or any(type(item) is not PopulationDiagnostics for item in diagnostics)
    ):
        raise QualificationError(QualificationFailure.INPUT_INVALID)
    populations = tuple(item.hypothesis_match_count for item in diagnostics)
    distribution = tuple(
        (value, populations.count(value)) for value in sorted(set(populations))
    )
    stage_names = sorted({name for item in diagnostics for name, _ in item.stage_survivor_counts})
    stage_totals = tuple(
        (
            name,
            sum(dict(item.stage_survivor_counts).get(name, 0) for item in diagnostics),
        )
        for name in stage_names
    )
    real = sum(
        item.evidence_source is QualificationEvidenceSource.REAL_GOVERNED_MARKET_EVIDENCE
        for item in corpus.observations
    )
    synthetic = len(corpus.observations) - real
    if (
        real == 0
        and evidence_sufficiency
        is QualificationEvidenceSufficiency.EVIDENCE_READY_FOR_REVIEW
    ):
        raise QualificationError(QualificationFailure.EVIDENCE_AUTHORITY)
    true_count = sum(item.result is QualificationObservationResult.HYPOTHESIS_TRUE for item in corpus.observations)
    false_count = sum(item.result is QualificationObservationResult.HYPOTHESIS_FALSE for item in corpus.observations)
    comparable = true_count + false_count
    match_pct = Decimal(0) if comparable == 0 else Decimal(true_count) / Decimal(comparable) * Decimal(100)
    payload = {
        "report_version": report_version,
        "corpus_identity": corpus.corpus_identity,
        "corpus_version": corpus.corpus_version,
        "hypothesis_identities": tuple(item.hypothesis_identity for item in hypotheses),
        "session_count": len(corpus.sessions),
        "observation_count": len(corpus.observations),
        "real_evidence_count": real,
        "synthetic_fixture_count": synthetic,
        "evidence_sufficiency": evidence_sufficiency,
        "mean_match_population": Decimal(sum(populations)) / Decimal(len(populations)),
        "median_match_population": Decimal(median(populations)),
        "minimum_match_population": min(populations),
        "maximum_match_population": max(populations),
        "match_population_distribution": distribution,
        "stage_survivor_totals": stage_totals,
        "zero_match_session_count": sum(item.zero_match_session for item in diagnostics),
        "over_ten_session_count": sum(item.over_ten_session for item in diagnostics),
        "over_fifteen_session_count": sum(item.over_fifteen_session for item in diagnostics),
        "twenty_or_more_session_count": sum(item.twenty_or_more_session for item in diagnostics),
        "hypothesis_true_count": true_count,
        "hypothesis_false_count": false_count,
        "match_percentage": match_pct,
        "outcome_available": any(item.subsequent_outcome_identity is not None for item in corpus.observations),
        "unresolved_methodology_questions": unresolved_methodology_questions,
        "conclusion": "MARKET_USEFULNESS_NOT_ESTABLISHED" if real == 0 else "EVIDENCE_PENDING_GOVERNED_REVIEW",
        "provenance": provenance,
        "schema_identity": QUALIFICATION_REPORT_IDENTITY,
        "schema_version": PART1_CONTRACT_VERSION,
    }
    return QualificationReport(
        report_identity=_identity("INTRADAY-QUALIFICATION-REPORT-", payload),
        integrity_identity=_identity("INTEGRITY-QUALIFICATION-REPORT-", payload),
        **payload,
    )


def qualification_artifact_document(value: object) -> dict[str, object]:
    artifact_type = type(value).__name__
    payload_functions = {
        "NarrowCprFact": _narrow_cpr_payload,
        "QualificationHypothesis": _hypothesis_payload,
        "FactualOutcomeDefinition": _outcome_definition_payload,
        "FactualOutcomeRecord": _outcome_payload,
        "QualificationObservation": _observation_payload,
        "PopulationDiagnostics": _population_payload,
        "QualificationCorpus": _corpus_payload,
        "QualificationReport": _report_payload,
    }
    function = payload_functions.get(artifact_type)
    if function is None:
        raise QualificationError(QualificationFailure.INPUT_INVALID)
    return {
        "artifact_type": artifact_type,
        "artifact": _normalize(function(value, include_identities=True)),
    }


def qualification_artifact_bytes(value: object) -> bytes:
    return _encode(qualification_artifact_document(value))


def qualification_artifact_from_document(document: Mapping[str, object]) -> object:
    if set(document) != {"artifact_type", "artifact"} or type(document["artifact"]) is not dict:
        raise QualificationError(QualificationFailure.INTEGRITY_INVALID)
    kind = document["artifact_type"]
    data = document["artifact"]
    try:
        if kind == "NarrowCprFact":
            value = NarrowCprFact(**_decode_fields(data, _NARROW_DECIMALS, _NARROW_DATES, {"provenance"}))
        elif kind == "QualificationHypothesis":
            decoded = _decode_fields(data, set(), {"effective_from", "effective_through"}, {"required_evidence_families", "provenance"})
            decoded["status"] = QualificationHypothesisStatus(decoded["status"])
            decoded["evidence_sufficiency"] = QualificationEvidenceSufficiency(decoded["evidence_sufficiency"])
            value = QualificationHypothesis(**decoded)
        elif kind == "FactualOutcomeDefinition":
            decoded = _decode_fields(data, set(), set(), {"measure_names", "provenance"})
            decoded["status"] = OutcomeDefinitionStatus(decoded["status"])
            value = FactualOutcomeDefinition(**decoded)
        elif kind == "FactualOutcomeRecord":
            decoded = _decode_fields(data, set(), {"observation_boundary", "measured_at"}, {"measures", "provenance"})
            decoded["measures"] = tuple((name, Decimal(value)) for name, value in decoded["measures"])
            value = FactualOutcomeRecord(**decoded)
        elif kind == "QualificationObservation":
            decoded = _decode_fields(data, set(), {"observation_boundary"}, {"evidence", "provenance"})
            decoded["result"] = QualificationObservationResult(decoded["result"])
            decoded["evidence_source"] = QualificationEvidenceSource(decoded["evidence_source"])
            decoded["evidence"] = tuple(_evidence_from_document(item) for item in decoded["evidence"])
            value = QualificationObservation(**decoded)
        elif kind == "PopulationDiagnostics":
            decoded = _decode_fields(data, {"retention_percentage"}, set(), {"stage_survivor_counts"})
            decoded["stage_survivor_counts"] = tuple(tuple(item) for item in decoded["stage_survivor_counts"])
            value = PopulationDiagnostics(**decoded)
        elif kind == "QualificationCorpus":
            decoded = _decode_fields(data, set(), set(), {"sessions", "observations", "provenance"})
            decoded["sessions"] = tuple(_session_from_document(item) for item in decoded["sessions"])
            decoded["observations"] = tuple(_observation_from_payload(item) for item in decoded["observations"])
            value = QualificationCorpus(**decoded)
        elif kind == "QualificationReport":
            decoded = _decode_fields(data, {"mean_match_population", "median_match_population", "match_percentage"}, set(), {"hypothesis_identities", "match_population_distribution", "stage_survivor_totals", "unresolved_methodology_questions", "provenance"})
            decoded["evidence_sufficiency"] = QualificationEvidenceSufficiency(decoded["evidence_sufficiency"])
            decoded["match_population_distribution"] = tuple(tuple(item) for item in decoded["match_population_distribution"])
            decoded["stage_survivor_totals"] = tuple(tuple(item) for item in decoded["stage_survivor_totals"])
            value = QualificationReport(**decoded)
        else:
            raise QualificationError(QualificationFailure.INTEGRITY_INVALID)
    except (KeyError, TypeError, ValueError, QualificationError) as error:
        if isinstance(error, QualificationError):
            raise
        raise QualificationError(QualificationFailure.INTEGRITY_INVALID) from error
    if qualification_artifact_document(value) != document:
        raise QualificationError(QualificationFailure.INTEGRITY_INVALID)
    return value


def qualification_artifact_from_bytes(encoded: bytes) -> object:
    try:
        document = json.loads(encoded)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise QualificationError(QualificationFailure.INTEGRITY_INVALID) from error
    if type(document) is not dict or _encode(document) != encoded:
        raise QualificationError(QualificationFailure.INTEGRITY_INVALID)
    return qualification_artifact_from_document(document)


_NARROW_DECIMALS = {
    "previous_daily_high", "previous_daily_low", "previous_daily_close", "pivot",
    "bc_raw", "tc_raw", "cpr_bottom", "cpr_top", "cpr_half_width",
    "cpr_half_width_pct", "cpr_total_width", "cpr_total_width_pct",
}
_NARROW_DATES = {"observation_boundary"}


def _narrow_cpr_payload(value: NarrowCprFact, include_identities: bool = False) -> dict[str, object]:
    payload = {name: getattr(value, name) for name in (
        "canonical_subject_identity", "previous_session_identity", "observation_session_identity",
        "source_daily_candle_identity", "observation_boundary", "previous_daily_high",
        "previous_daily_low", "previous_daily_close", "pivot", "bc_raw", "tc_raw",
        "cpr_bottom", "cpr_top", "cpr_half_width", "cpr_half_width_pct",
        "cpr_total_width", "cpr_total_width_pct", "narrow_cpr_kgs_v0",
        "source_integrity_identity", "provenance", "schema_identity", "schema_version",
    )}
    return _with_identities(payload, value, include_identities, "fact_identity", "integrity_identity")


def _hypothesis_payload(value: QualificationHypothesis, include_identities: bool = False) -> dict[str, object]:
    payload = {name: getattr(value, name) for name in (
        "hypothesis_version", "name", "family", "required_evidence_families",
        "calculation_identity", "status", "evidence_sufficiency",
        "qualification_corpus_identity", "population_diagnostics_identity",
        "outcome_diagnostics_identity", "effective_from", "effective_through",
        "provenance", "real_evidence_count", "schema_identity", "schema_version",
    )}
    return _with_identities(payload, value, include_identities, "hypothesis_identity", "integrity_identity")


def _outcome_definition_payload(value: FactualOutcomeDefinition, include_identities: bool = False) -> dict[str, object]:
    payload = {name: getattr(value, name) for name in (
        "definition_version", "family", "measure_names", "status", "provenance",
        "schema_identity", "schema_version",
    )}
    return _with_identities(payload, value, include_identities, "definition_identity", "integrity_identity")


def _outcome_payload(value: FactualOutcomeRecord, include_identities: bool = False) -> dict[str, object]:
    payload = {name: getattr(value, name) for name in (
        "definition_identity", "canonical_subject_identity", "source_observation_identity",
        "observation_boundary", "measured_at", "measures", "provenance",
        "schema_identity", "schema_version",
    )}
    return _with_identities(payload, value, include_identities, "outcome_identity", "integrity_identity")


def _observation_payload(value: QualificationObservation, include_identities: bool = False) -> dict[str, object]:
    payload = {name: getattr(value, name) for name in (
        "canonical_subject_identity", "market_session_identity", "observation_boundary",
        "hypothesis_identity", "hypothesis_version", "evidence", "result",
        "result_fact_identity", "subsequent_outcome_identity", "evidence_source",
        "provenance", "schema_identity", "schema_version",
    )}
    return _with_identities(payload, value, include_identities, "observation_identity", "integrity_identity")


def _population_payload(value: PopulationDiagnostics, include_identities: bool = False) -> dict[str, object]:
    payload = {name: getattr(value, name) for name in (
        "market_session_identity", "hypothesis_identity", "factual_universe_count",
        "hypothesis_match_count", "hypothesis_non_match_count", "unavailable_count",
        "factual_failure_count", "retention_percentage", "stage_survivor_counts",
        "final_probables_count", "long_count", "short_count", "neutral_other_count",
        "zero_match_session", "over_ten_session", "over_fifteen_session",
        "twenty_or_more_session", "schema_identity", "schema_version",
    )}
    return _with_identities(payload, value, include_identities, "diagnostics_identity", "integrity_identity")


def _corpus_payload(value: QualificationCorpus, include_identities: bool = False) -> dict[str, object]:
    payload = {name: getattr(value, name) for name in (
        "corpus_version", "sessions", "observations", "provenance", "schema_identity", "schema_version",
    )}
    return _with_identities(payload, value, include_identities, "corpus_identity", "integrity_identity")


def _report_payload(value: QualificationReport, include_identities: bool = False) -> dict[str, object]:
    payload = {name: getattr(value, name) for name in (
        "report_version", "corpus_identity", "corpus_version", "hypothesis_identities",
        "session_count", "observation_count", "real_evidence_count", "synthetic_fixture_count",
        "evidence_sufficiency", "mean_match_population", "median_match_population",
        "minimum_match_population", "maximum_match_population", "match_population_distribution",
        "stage_survivor_totals",
        "zero_match_session_count", "over_ten_session_count", "over_fifteen_session_count",
        "twenty_or_more_session_count", "hypothesis_true_count", "hypothesis_false_count",
        "match_percentage", "outcome_available", "unresolved_methodology_questions",
        "conclusion", "provenance", "schema_identity", "schema_version",
    )}
    return _with_identities(payload, value, include_identities, "report_identity", "integrity_identity")


def _with_identities(payload: dict[str, object], value: object, include: bool, *names: str) -> dict[str, object]:
    if include:
        for name in names:
            payload[name] = getattr(value, name)
    return payload


def _session_document(value: QualificationCorpusSession) -> dict[str, object]:
    return _normalize({name: getattr(value, name) for name in (
        "session_record_identity", "market_session_identity", "observation_boundary", "universe_publication_identity",
        "reconciliation_publication_identity", "discovery_run_identity", "factual_evidence_identities",
        "hypothesis_identities", "outcome_evidence_window_identity", "population_diagnostics_identity",
        "provenance", "integrity_identity",
    )})


def _corpus_session_payload(value: QualificationCorpusSession) -> dict[str, object]:
    return {name: getattr(value, name) for name in (
        "market_session_identity", "observation_boundary", "universe_publication_identity",
        "reconciliation_publication_identity", "discovery_run_identity", "factual_evidence_identities",
        "hypothesis_identities", "outcome_evidence_window_identity", "population_diagnostics_identity",
        "provenance",
    )}


def _session_from_document(value: Mapping[str, object]) -> QualificationCorpusSession:
    decoded = dict(value)
    decoded["observation_boundary"] = datetime.fromisoformat(decoded["observation_boundary"])
    for name in ("factual_evidence_identities", "hypothesis_identities", "provenance"):
        decoded[name] = tuple(decoded[name])
    return QualificationCorpusSession(**decoded)


def _evidence_document(value: EvidenceReference) -> dict[str, object]:
    return _normalize({
        "evidence_identity": value.evidence_identity,
        "available_at": value.available_at,
        "source": value.source,
        "provenance": value.provenance,
    })


def _evidence_from_document(value: Mapping[str, object]) -> EvidenceReference:
    return EvidenceReference(
        evidence_identity=value["evidence_identity"],
        available_at=datetime.fromisoformat(value["available_at"]),
        source=QualificationEvidenceSource(value["source"]),
        provenance=tuple(value["provenance"]),
    )


def _observation_from_payload(value: Mapping[str, object]) -> QualificationObservation:
    decoded = dict(value)
    decoded["observation_boundary"] = datetime.fromisoformat(decoded["observation_boundary"])
    decoded["evidence"] = tuple(_evidence_from_document(item) for item in decoded["evidence"])
    decoded["result"] = QualificationObservationResult(decoded["result"])
    decoded["evidence_source"] = QualificationEvidenceSource(decoded["evidence_source"])
    decoded["provenance"] = tuple(decoded["provenance"])
    return QualificationObservation(**decoded)


def _decode_fields(data: Mapping[str, object], decimal_names: set[str], date_names: set[str], tuple_names: set[str]) -> dict[str, object]:
    decoded = dict(data)
    for name in decimal_names:
        decoded[name] = Decimal(decoded[name])
    for name in date_names:
        decoded[name] = datetime.fromisoformat(decoded[name])
    for name in tuple_names:
        decoded[name] = tuple(decoded[name])
    return decoded


def _normalize(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, EvidenceReference):
        return _evidence_document(value)
    if isinstance(value, QualificationCorpusSession):
        return _session_document(value)
    if isinstance(value, QualificationObservation):
        return _normalize(_observation_payload(value, include_identities=True))
    if isinstance(value, tuple):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    return value


def _encode(value: object) -> bytes:
    return json.dumps(_normalize(value), sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(_encode(value)).hexdigest()


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


def _texts(value: object) -> bool:
    return type(value) is tuple and bool(value) and all(_text(item) for item in value)


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


__all__ = [
    "FACTUAL_OUTCOME_CONTRACT_IDENTITY",
    "NARROW_CPR_CALCULATION_IDENTITY",
    "NARROW_CPR_FACT_IDENTITY",
    "PART1_CONTRACT_VERSION",
    "POPULATION_DIAGNOSTICS_IDENTITY",
    "QUALIFICATION_CONTRACT_IDENTITY",
    "QUALIFICATION_CONTRACT_VERSION",
    "QUALIFICATION_CORPUS_IDENTITY",
    "QUALIFICATION_HYPOTHESIS_IDENTITY",
    "QUALIFICATION_OBSERVATION_IDENTITY",
    "QUALIFICATION_REPORT_IDENTITY",
    "EvidenceReference",
    "FactualOutcomeDefinition",
    "FactualOutcomeRecord",
    "NarrowCprFact",
    "OutcomeDefinitionStatus",
    "PopulationDiagnostics",
    "PreviousCompletedDailyCandle",
    "QualificationCorpus",
    "QualificationCorpusSession",
    "QualificationError",
    "QualificationEvidenceSource",
    "QualificationEvidenceSufficiency",
    "QualificationFailure",
    "QualificationHypothesis",
    "QualificationHypothesisStatus",
    "QualificationObservation",
    "QualificationObservationResult",
    "QualificationReport",
    "create_factual_outcome_definition",
    "create_factual_outcome_record",
    "create_narrow_cpr_fact",
    "create_narrow_cpr_hypothesis",
    "create_population_diagnostics",
    "create_qualification_corpus",
    "create_qualification_corpus_session",
    "create_qualification_hypothesis",
    "create_qualification_observation",
    "create_qualification_report",
    "qualification_artifact_bytes",
    "qualification_artifact_document",
    "qualification_artifact_from_bytes",
    "qualification_artifact_from_document",
]
