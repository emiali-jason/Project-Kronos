"""Governed Slice 3V factual/visual validation contracts with no trading authority."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from hashlib import sha256
import json
import re

from kronos.intraday.contracts import IntradayTimeframe
from kronos.instrument.visual_identity import (
    VisualIdentityResolver, VisualIdentityResolution, VisualIdentityResolutionError,
    VisualIdentitySourceContext,
)
from kronos.intraday.contracts import (
    CandleBoundary, CandleCompletion, GovernedCandle, ObservationBoundary, SourceProvenance,
)
from kronos.intraday.candles import expected_candle_boundaries
from kronos.market.calendar import MarketCalendarPublisher
from kronos.market.schedule import (
    MarketSchedule, MarketDaySchedule, MarketWindow, MarketSessionWindow,
    TradingDayStatus, MarketAvailability, ScheduleFreshness, ScheduleIntegrity,
)


SLICE3V_QUESTION_SET = "KRONOS-INTRADAY-SLICE-3V-QUESTION-SET-V1"
SLICE3V_VISUAL_ANSWER_SCHEMA = "KRONOS-INTRADAY-SLICE-3V-VISUAL-ANSWER-V1"
SLICE3V_COMPARISON_POLICY = "KRONOS-INTRADAY-SLICE-3V-COMPARISON-POLICY-V1"
SLICE3V_VALIDATION_RECORD_SCHEMA = (
    "KRONOS-INTRADAY-SLICE-3V-VALIDATION-RECORD-V1"
)

_KEY = re.compile(r"[a-z][a-z0-9_.:-]{0,95}\Z")


class ValidationQuestion(StrEnum):
    CHART_IDENTITY = "CHART_IDENTITY"
    TIMEFRAME_CONTEXT = "TIMEFRAME_CONTEXT"
    COMPLETED_CANDLE = "COMPLETED_CANDLE"
    PREVIOUS_SESSION = "PREVIOUS_SESSION"
    CLASSIC_PIVOTS = "CLASSIC_PIVOTS"
    CPR = "CPR"
    STRUCTURAL_BARRIERS = "STRUCTURAL_BARRIERS"
    STRUCTURAL_EVENTS = "STRUCTURAL_EVENTS"
    VOLUME_PARTICIPATION = "VOLUME_PARTICIPATION"
    CURRENT_INCOMPLETE_CANDLE = "CURRENT_INCOMPLETE_CANDLE"
    SESSION_BOUNDARY = "SESSION_BOUNDARY"
    ADDITIONAL_FACTUAL_DISCREPANCY = "ADDITIONAL_FACTUAL_DISCREPANCY"


QUESTION_SET = tuple(ValidationQuestion)
ANSWER_QUESTIONS = QUESTION_SET[2:]


class VisualPrecision(StrEnum):
    EXACT = "EXACT"
    APPROXIMATE = "APPROXIMATE"
    RELATIONAL_ONLY = "RELATIONAL_ONLY"
    NOT_OBSERVABLE = "NOT_OBSERVABLE"


class FactualValueKind(StrEnum):
    NUMERIC = "NUMERIC"
    RELATION = "RELATION"
    TEXT = "TEXT"
    BOOLEAN = "BOOLEAN"


class QuestionAnswerState(StrEnum):
    OBSERVED = "OBSERVED"
    NOT_OBSERVABLE = "NOT_OBSERVABLE"
    NO_ADDITIONAL_DISCREPANCY = "NO_ADDITIONAL_DISCREPANCY"


class ComparisonResult(StrEnum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    NOT_VISUALLY_VERIFIABLE = "NOT_VISUALLY_VERIFIABLE"
    CHART_EVIDENCE_UNAVAILABLE = "CHART_EVIDENCE_UNAVAILABLE"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    TIMEFRAME_MISMATCH = "TIMEFRAME_MISMATCH"
    OBSERVATION_BOUNDARY_MISMATCH = "OBSERVATION_BOUNDARY_MISMATCH"


class DiscrepancyFamily(StrEnum):
    CANDLE_VALUE_DISCREPANCY = "CANDLE_VALUE_DISCREPANCY"
    LEVEL_VALUE_DISCREPANCY = "LEVEL_VALUE_DISCREPANCY"
    LEVEL_PLACEMENT_DISCREPANCY = "LEVEL_PLACEMENT_DISCREPANCY"
    STRUCTURAL_EVENT_DISCREPANCY = "STRUCTURAL_EVENT_DISCREPANCY"
    VOLUME_DISCREPANCY = "VOLUME_DISCREPANCY"
    SESSION_BOUNDARY_DISCREPANCY = "SESSION_BOUNDARY_DISCREPANCY"
    COMPLETED_VS_INCOMPLETE_DISCREPANCY = (
        "COMPLETED_VS_INCOMPLETE_DISCREPANCY"
    )
    SOURCE_CHART_IDENTITY_DISCREPANCY = "SOURCE_CHART_IDENTITY_DISCREPANCY"
    OTHER_GOVERNED_FACTUAL_DISCREPANCY = (
        "OTHER_GOVERNED_FACTUAL_DISCREPANCY"
    )


class ValidationFailureState(StrEnum):
    MISSING_CHART = "MISSING_CHART"
    WRONG_INSTRUMENT = "WRONG_INSTRUMENT"
    WRONG_TIMEFRAME = "WRONG_TIMEFRAME"
    WRONG_TRADING_CONTEXT = "WRONG_TRADING_CONTEXT"
    VISUAL_ANSWER_SCHEMA_FAILURE = "VISUAL_ANSWER_SCHEMA_FAILURE"
    PARTIAL_ANSWER = "PARTIAL_ANSWER"
    STALE_ANSWER = "STALE_ANSWER"
    DUPLICATE_CONFLICTING_ANSWER = "DUPLICATE_CONFLICTING_ANSWER"
    MACHINE_EVIDENCE_UNAVAILABLE = "MACHINE_EVIDENCE_UNAVAILABLE"
    MACHINE_EVIDENCE_SUPERSEDED = "MACHINE_EVIDENCE_SUPERSEDED"
    COMPARISON_FAILURE = "COMPARISON_FAILURE"


class MachineEvidenceState(StrEnum):
    FROZEN = "FROZEN"
    SUPERSEDED = "SUPERSEDED"


class ValidationEvidenceFamily(StrEnum):
    NATIVE_CHART = "NATIVE_CHART"
    MCX_REFERENCE_MARKET_RELATIONSHIP = "MCX_REFERENCE_MARKET_RELATIONSHIP_V0"


class Slice3VContractError(ValueError):
    """Sanitized, bounded Slice 3V contract failure."""

    def __init__(self, state: ValidationFailureState, code: str) -> None:
        self.state = state
        super().__init__(code)


FactValue = Decimal | str | bool


@dataclass(frozen=True, slots=True)
class MachineFact:
    question: ValidationQuestion
    fact_key: str
    value_kind: FactualValueKind
    value: FactValue
    discrepancy_family: DiscrepancyFamily

    def __post_init__(self) -> None:
        if (
            type(self.question) is not ValidationQuestion
            or self.question in {
                ValidationQuestion.CHART_IDENTITY,
                ValidationQuestion.TIMEFRAME_CONTEXT,
                ValidationQuestion.ADDITIONAL_FACTUAL_DISCREPANCY,
            }
            or not _key(self.fact_key)
            or type(self.value_kind) is not FactualValueKind
            or type(self.discrepancy_family) is not DiscrepancyFamily
        ):
            raise ValueError("SLICE3V_MACHINE_FACT_INVALID")
        object.__setattr__(self, "value", _normalize_value(self.value_kind, self.value))


@dataclass(frozen=True, slots=True)
class MachineEvidence:
    evidence_identity: str
    run_identity: str
    canonical_instrument_id: str
    expected_visible_symbol: str
    exchange: str
    trading_date: date
    timeframe: IntradayTimeframe
    observation_boundary: datetime
    frozen_at: datetime
    facts: tuple[MachineFact, ...]
    state: MachineEvidenceState = MachineEvidenceState.FROZEN
    evidence_family: ValidationEvidenceFamily = ValidationEvidenceFamily.NATIVE_CHART

    def __post_init__(self) -> None:
        fact_keys = tuple((item.question, item.fact_key) for item in self.facts)
        if (
            not _text(self.evidence_identity, 192)
            or not _text(self.run_identity, 192)
            or not _text(self.canonical_instrument_id, 192)
            or not _text(self.expected_visible_symbol, 96)
            or not _text(self.exchange, 32)
            or type(self.trading_date) is not date
            or type(self.timeframe) is not IntradayTimeframe
            or not _aware(self.observation_boundary)
            or not _aware(self.frozen_at)
            or not self.facts
            or any(type(item) is not MachineFact for item in self.facts)
            or len(set(fact_keys)) != len(fact_keys)
            or type(self.state) is not MachineEvidenceState
            or type(self.evidence_family) is not ValidationEvidenceFamily
        ):
            raise ValueError("SLICE3V_MACHINE_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class VisualObservation:
    question: ValidationQuestion
    fact_key: str
    precision: VisualPrecision
    value_kind: FactualValueKind | None = None
    value: FactValue | None = None
    factual_note: str | None = None

    def __post_init__(self) -> None:
        if (
            type(self.question) is not ValidationQuestion
            or self.question not in ANSWER_QUESTIONS
            or not _key(self.fact_key)
            or type(self.precision) is not VisualPrecision
            or (self.factual_note is not None and not _text(self.factual_note, 280))
        ):
            raise Slice3VContractError(
                ValidationFailureState.VISUAL_ANSWER_SCHEMA_FAILURE,
                "SLICE3V_VISUAL_OBSERVATION_INVALID",
            )
        if self.precision is VisualPrecision.NOT_OBSERVABLE:
            if self.value_kind is not None or self.value is not None:
                raise Slice3VContractError(
                    ValidationFailureState.VISUAL_ANSWER_SCHEMA_FAILURE,
                    "SLICE3V_NOT_OBSERVABLE_VALUE_PROHIBITED",
                )
            return
        if type(self.value_kind) is not FactualValueKind or self.value is None:
            raise Slice3VContractError(
                ValidationFailureState.VISUAL_ANSWER_SCHEMA_FAILURE,
                "SLICE3V_VISUAL_VALUE_REQUIRED",
            )
        if (
            self.precision is VisualPrecision.APPROXIMATE
            and self.value_kind is not FactualValueKind.NUMERIC
        ) or (
            self.precision is VisualPrecision.RELATIONAL_ONLY
            and self.value_kind is not FactualValueKind.RELATION
        ):
            raise Slice3VContractError(
                ValidationFailureState.VISUAL_ANSWER_SCHEMA_FAILURE,
                "SLICE3V_VISUAL_PRECISION_KIND_INVALID",
            )
        object.__setattr__(self, "value", _normalize_value(self.value_kind, self.value))
        if (
            self.question is ValidationQuestion.ADDITIONAL_FACTUAL_DISCREPANCY
            and self.factual_note is None
        ):
            raise Slice3VContractError(
                ValidationFailureState.VISUAL_ANSWER_SCHEMA_FAILURE,
                "SLICE3V_ADDITIONAL_DISCREPANCY_EXPLANATION_REQUIRED",
            )


@dataclass(frozen=True, slots=True)
class VisualQuestionAnswer:
    question: ValidationQuestion
    state: QuestionAnswerState
    observations: tuple[VisualObservation, ...] = ()
    unavailability_reason: str | None = None

    def __post_init__(self) -> None:
        keys = tuple(item.fact_key for item in self.observations)
        if (
            type(self.question) is not ValidationQuestion
            or self.question not in ANSWER_QUESTIONS
            or type(self.state) is not QuestionAnswerState
            or any(type(item) is not VisualObservation for item in self.observations)
            or any(item.question is not self.question for item in self.observations)
            or len(set(keys)) != len(keys)
        ):
            raise Slice3VContractError(
                ValidationFailureState.VISUAL_ANSWER_SCHEMA_FAILURE,
                "SLICE3V_VISUAL_QUESTION_ANSWER_INVALID",
            )
        if self.state is QuestionAnswerState.OBSERVED:
            if not self.observations or self.unavailability_reason is not None:
                raise Slice3VContractError(
                    ValidationFailureState.VISUAL_ANSWER_SCHEMA_FAILURE,
                    "SLICE3V_OBSERVED_ANSWER_INVALID",
                )
        elif self.state is QuestionAnswerState.NOT_OBSERVABLE:
            if self.observations or not _text(self.unavailability_reason, 160):
                raise Slice3VContractError(
                    ValidationFailureState.VISUAL_ANSWER_SCHEMA_FAILURE,
                    "SLICE3V_NOT_OBSERVABLE_ANSWER_INVALID",
                )
        elif (
            self.question is not ValidationQuestion.ADDITIONAL_FACTUAL_DISCREPANCY
            or self.observations
            or self.unavailability_reason is not None
        ):
            raise Slice3VContractError(
                ValidationFailureState.VISUAL_ANSWER_SCHEMA_FAILURE,
                "SLICE3V_NO_ADDITIONAL_DISCREPANCY_INVALID",
            )


@dataclass(frozen=True, slots=True)
class VisualAnswerPayload:
    visible_symbol: str
    exchange: str
    trading_date: date
    timeframe: IntradayTimeframe
    observation_boundary: datetime
    chart_observed_at: datetime
    chart_available: bool
    answers: tuple[VisualQuestionAnswer, ...]
    schema_identity: str = SLICE3V_VISUAL_ANSWER_SCHEMA
    question_set_identity: str = SLICE3V_QUESTION_SET

    def __post_init__(self) -> None:
        questions = tuple(item.question for item in self.answers)
        if (
            not _text(self.visible_symbol, 96)
            or not _text(self.exchange, 32)
            or type(self.trading_date) is not date
            or type(self.timeframe) is not IntradayTimeframe
            or not _aware(self.observation_boundary)
            or not _aware(self.chart_observed_at)
            or type(self.chart_available) is not bool
            or any(type(item) is not VisualQuestionAnswer for item in self.answers)
            or self.schema_identity != SLICE3V_VISUAL_ANSWER_SCHEMA
            or self.question_set_identity != SLICE3V_QUESTION_SET
        ):
            raise Slice3VContractError(
                ValidationFailureState.VISUAL_ANSWER_SCHEMA_FAILURE,
                "SLICE3V_VISUAL_ANSWER_SCHEMA_INVALID",
            )
        if self.chart_available:
            if questions != ANSWER_QUESTIONS:
                raise Slice3VContractError(
                    ValidationFailureState.PARTIAL_ANSWER,
                    "SLICE3V_VISUAL_ANSWER_PARTIAL_OR_UNORDERED",
                )
        elif self.answers:
            raise Slice3VContractError(
                ValidationFailureState.VISUAL_ANSWER_SCHEMA_FAILURE,
                "SLICE3V_UNAVAILABLE_CHART_ANSWERS_PROHIBITED",
            )


@dataclass(frozen=True, slots=True)
class VisualAnswer:
    visual_evidence_identity: str
    integrity_identity: str
    payload: VisualAnswerPayload

    def __post_init__(self) -> None:
        payload = visual_answer_payload(self.payload)
        if (
            type(self.payload) is not VisualAnswerPayload
            or self.visual_evidence_identity
            != _identity("SLICE3V-VISUAL-EVIDENCE-", payload)
            or self.integrity_identity != _identity("SHA256-", payload)
        ):
            raise Slice3VContractError(
                ValidationFailureState.VISUAL_ANSWER_SCHEMA_FAILURE,
                "SLICE3V_VISUAL_ANSWER_INTEGRITY_INVALID",
            )


@dataclass(frozen=True, slots=True)
class ComparisonItem:
    question: ValidationQuestion
    fact_key: str
    result: ComparisonResult
    machine_value_kind: FactualValueKind | None
    machine_value: FactValue | None
    visual_precision: VisualPrecision | None
    visual_value_kind: FactualValueKind | None
    visual_value: FactValue | None

    def __post_init__(self) -> None:
        if (
            type(self.question) is not ValidationQuestion
            or not _key(self.fact_key)
            or type(self.result) is not ComparisonResult
            or (
                self.machine_value_kind is not None
                and type(self.machine_value_kind) is not FactualValueKind
            )
            or (
                self.visual_precision is not None
                and type(self.visual_precision) is not VisualPrecision
            )
            or (
                self.visual_value_kind is not None
                and type(self.visual_value_kind) is not FactualValueKind
            )
        ):
            raise ValueError("SLICE3V_COMPARISON_ITEM_INVALID")


@dataclass(frozen=True, slots=True)
class DiscrepancyRecord:
    question: ValidationQuestion
    fact_key: str
    family: DiscrepancyFamily
    factual_explanation: str

    def __post_init__(self) -> None:
        if (
            type(self.question) is not ValidationQuestion
            or not _key(self.fact_key)
            or type(self.family) is not DiscrepancyFamily
            or not _text(self.factual_explanation, 280)
        ):
            raise ValueError("SLICE3V_DISCREPANCY_INVALID")


@dataclass(frozen=True, slots=True)
class ValidationRecord:
    validation_record_identity: str
    validation_run_identity: str
    canonical_instrument_id: str
    trading_date: date
    observation_boundary: datetime
    timeframe: IntradayTimeframe
    machine_evidence_identity: str
    visual_evidence_identity: str
    evidence_family: ValidationEvidenceFamily
    compared_at: datetime
    comparison_results: tuple[ComparisonItem, ...]
    discrepancies: tuple[DiscrepancyRecord, ...]
    integrity_identity: str
    question_set_identity: str = SLICE3V_QUESTION_SET
    visual_answer_schema_identity: str = SLICE3V_VISUAL_ANSWER_SCHEMA
    comparison_policy_identity: str = SLICE3V_COMPARISON_POLICY
    schema_identity: str = SLICE3V_VALIDATION_RECORD_SCHEMA

    def __post_init__(self) -> None:
        run_payload = _validation_run_payload(self)
        payload = validation_record_payload(self)
        if (
            not _text(self.canonical_instrument_id, 192)
            or type(self.trading_date) is not date
            or not _aware(self.observation_boundary)
            or type(self.timeframe) is not IntradayTimeframe
            or not _text(self.machine_evidence_identity, 192)
            or not _text(self.visual_evidence_identity, 192)
            or type(self.evidence_family) is not ValidationEvidenceFamily
            or not _aware(self.compared_at)
            or not self.comparison_results
            or any(type(item) is not ComparisonItem for item in self.comparison_results)
            or any(type(item) is not DiscrepancyRecord for item in self.discrepancies)
            or self.question_set_identity != SLICE3V_QUESTION_SET
            or self.visual_answer_schema_identity != SLICE3V_VISUAL_ANSWER_SCHEMA
            or self.comparison_policy_identity != SLICE3V_COMPARISON_POLICY
            or self.schema_identity != SLICE3V_VALIDATION_RECORD_SCHEMA
            or self.validation_run_identity
            != _identity("SLICE3V-VALIDATION-RUN-", run_payload)
            or self.validation_record_identity
            != _identity("SLICE3V-VALIDATION-RECORD-", payload)
            or self.integrity_identity != _identity("SHA256-", payload)
        ):
            raise ValueError("SLICE3V_VALIDATION_RECORD_INVALID")


@dataclass(frozen=True, slots=True)
class ValidationStatistics:
    observations_compared: int
    result_counts: tuple[tuple[ComparisonResult, int], ...]
    result_percentages: tuple[tuple[ComparisonResult, Decimal], ...]
    discrepancy_counts: tuple[tuple[DiscrepancyFamily, int], ...]
    timeframe_counts: tuple[tuple[IntradayTimeframe, int], ...]
    instrument_counts: tuple[tuple[str, int], ...]


def accept_visual_answer(payload: VisualAnswerPayload) -> VisualAnswer:
    if type(payload) is not VisualAnswerPayload:
        raise Slice3VContractError(
            ValidationFailureState.VISUAL_ANSWER_SCHEMA_FAILURE,
            "SLICE3V_VISUAL_ANSWER_SCHEMA_INVALID",
        )
    document = visual_answer_payload(payload)
    return VisualAnswer(
        visual_evidence_identity=_identity("SLICE3V-VISUAL-EVIDENCE-", document),
        integrity_identity=_identity("SHA256-", document),
        payload=payload,
    )


def compare_machine_to_visual(
    machine: MachineEvidence | None,
    visual: VisualAnswer,
    *,
    compared_at: datetime,
) -> ValidationRecord:
    if machine is None:
        raise Slice3VContractError(
            ValidationFailureState.MACHINE_EVIDENCE_UNAVAILABLE,
            "SLICE3V_MACHINE_EVIDENCE_UNAVAILABLE",
        )
    if type(machine) is not MachineEvidence or type(visual) is not VisualAnswer:
        raise Slice3VContractError(
            ValidationFailureState.COMPARISON_FAILURE,
            "SLICE3V_COMPARISON_INPUT_INVALID",
        )
    if machine.state is MachineEvidenceState.SUPERSEDED:
        raise Slice3VContractError(
            ValidationFailureState.MACHINE_EVIDENCE_SUPERSEDED,
            "SLICE3V_MACHINE_EVIDENCE_SUPERSEDED",
        )
    if machine.evidence_family is not ValidationEvidenceFamily.NATIVE_CHART:
        raise Slice3VContractError(
            ValidationFailureState.COMPARISON_FAILURE,
            "SLICE3V_REFERENCE_RELATIONSHIP_COMPARISON_NOT_IMPLEMENTED",
        )
    if not _aware(compared_at) or compared_at < machine.frozen_at:
        raise Slice3VContractError(
            ValidationFailureState.COMPARISON_FAILURE,
            "SLICE3V_COMPARISON_BEFORE_MACHINE_FREEZE",
        )
    answer = visual.payload
    if answer.chart_observed_at < machine.frozen_at:
        raise Slice3VContractError(
            ValidationFailureState.STALE_ANSWER,
            "SLICE3V_VISUAL_ANSWER_STALE",
        )
    if not answer.chart_available:
        return _record(
            machine,
            visual,
            compared_at,
            (
                ComparisonItem(
                    ValidationQuestion.CHART_IDENTITY,
                    "chart_availability",
                    ComparisonResult.CHART_EVIDENCE_UNAVAILABLE,
                    None,
                    None,
                    None,
                    None,
                    None,
                ),
            ),
            (),
        )
    if (
        answer.visible_symbol != machine.expected_visible_symbol
        or answer.exchange != machine.exchange
    ):
        return _preflight_mismatch(
            machine,
            visual,
            compared_at,
            ValidationQuestion.CHART_IDENTITY,
            "chart_identity",
            ComparisonResult.IDENTITY_MISMATCH,
            DiscrepancyFamily.SOURCE_CHART_IDENTITY_DISCREPANCY,
            "Visible symbol or exchange differs from the governed machine binding.",
        )
    if answer.trading_date != machine.trading_date:
        raise Slice3VContractError(
            ValidationFailureState.WRONG_TRADING_CONTEXT,
            "SLICE3V_WRONG_TRADING_DATE",
        )
    if answer.timeframe is not machine.timeframe:
        return _preflight_mismatch(
            machine,
            visual,
            compared_at,
            ValidationQuestion.TIMEFRAME_CONTEXT,
            "timeframe",
            ComparisonResult.TIMEFRAME_MISMATCH,
            DiscrepancyFamily.SOURCE_CHART_IDENTITY_DISCREPANCY,
            "Visible timeframe differs from the governed machine binding.",
        )
    if answer.observation_boundary != machine.observation_boundary:
        return _preflight_mismatch(
            machine,
            visual,
            compared_at,
            ValidationQuestion.TIMEFRAME_CONTEXT,
            "observation_boundary",
            ComparisonResult.OBSERVATION_BOUNDARY_MISMATCH,
            DiscrepancyFamily.SESSION_BOUNDARY_DISCREPANCY,
            "Visible observation boundary differs from the frozen machine boundary.",
        )

    answers = {item.question: item for item in answer.answers}
    results: list[ComparisonItem] = []
    discrepancies: list[DiscrepancyRecord] = []
    for fact in machine.facts:
        question_answer = answers[fact.question]
        observations = {item.fact_key: item for item in question_answer.observations}
        visual_observation = observations.get(fact.fact_key)
        item = _compare_fact(fact, question_answer, visual_observation)
        results.append(item)
        if item.result is ComparisonResult.MISMATCH:
            discrepancies.append(
                DiscrepancyRecord(
                    question=fact.question,
                    fact_key=fact.fact_key,
                    family=fact.discrepancy_family,
                    factual_explanation=(
                        "Visual observation differs from the exact frozen machine fact."
                    ),
                )
            )

    additional = answers[ValidationQuestion.ADDITIONAL_FACTUAL_DISCREPANCY]
    if additional.state is QuestionAnswerState.OBSERVED:
        for observation in additional.observations:
            results.append(
                ComparisonItem(
                    question=observation.question,
                    fact_key=observation.fact_key,
                    result=ComparisonResult.MISMATCH,
                    machine_value_kind=None,
                    machine_value=None,
                    visual_precision=observation.precision,
                    visual_value_kind=observation.value_kind,
                    visual_value=observation.value,
                )
            )
            discrepancies.append(
                DiscrepancyRecord(
                    question=observation.question,
                    fact_key=observation.fact_key,
                    family=DiscrepancyFamily.OTHER_GOVERNED_FACTUAL_DISCREPANCY,
                    factual_explanation=observation.factual_note or "Factual discrepancy.",
                )
            )
    return _record(machine, visual, compared_at, tuple(results), tuple(discrepancies))


def validation_statistics(records: tuple[ValidationRecord, ...]) -> ValidationStatistics:
    if any(type(item) is not ValidationRecord for item in records):
        raise ValueError("SLICE3V_VALIDATION_STATISTICS_INPUT_INVALID")
    result_counts = {item: 0 for item in ComparisonResult}
    discrepancy_counts = {item: 0 for item in DiscrepancyFamily}
    timeframe_counts = {item: 0 for item in IntradayTimeframe}
    instrument_counts: dict[str, int] = {}
    total = 0
    for record in records:
        timeframe_counts[record.timeframe] += len(record.comparison_results)
        instrument_counts[record.canonical_instrument_id] = (
            instrument_counts.get(record.canonical_instrument_id, 0)
            + len(record.comparison_results)
        )
        for item in record.comparison_results:
            result_counts[item.result] += 1
            total += 1
        for item in record.discrepancies:
            discrepancy_counts[item.family] += 1
    percentages = tuple(
        (result, Decimal(0) if total == 0 else Decimal(count * 100) / Decimal(total))
        for result, count in result_counts.items()
    )
    return ValidationStatistics(
        observations_compared=total,
        result_counts=tuple(result_counts.items()),
        result_percentages=percentages,
        discrepancy_counts=tuple(discrepancy_counts.items()),
        timeframe_counts=tuple(timeframe_counts.items()),
        instrument_counts=tuple(sorted(instrument_counts.items())),
    )


def visual_answer_payload(value: VisualAnswerPayload) -> dict[str, object]:
    return {
        "schema_identity": value.schema_identity,
        "question_set_identity": value.question_set_identity,
        "visible_symbol": value.visible_symbol,
        "exchange": value.exchange,
        "trading_date": value.trading_date.isoformat(),
        "timeframe": value.timeframe.value,
        "observation_boundary": value.observation_boundary.isoformat(),
        "chart_observed_at": value.chart_observed_at.isoformat(),
        "chart_available": value.chart_available,
        "answers": [
            {
                "question": answer.question.value,
                "state": answer.state.value,
                "unavailability_reason": answer.unavailability_reason,
                "observations": [
                    {
                        "question": item.question.value,
                        "fact_key": item.fact_key,
                        "precision": item.precision.value,
                        "value_kind": (
                            item.value_kind.value if item.value_kind is not None else None
                        ),
                        "value": _json_value(item.value),
                        "factual_note": item.factual_note,
                    }
                    for item in answer.observations
                ],
            }
            for answer in value.answers
        ],
    }


def visual_answer_payload_from_dict(document: dict[str, object]) -> VisualAnswerPayload:
    expected = {
        "schema_identity",
        "question_set_identity",
        "visible_symbol",
        "exchange",
        "trading_date",
        "timeframe",
        "observation_boundary",
        "chart_observed_at",
        "chart_available",
        "answers",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise Slice3VContractError(
            ValidationFailureState.VISUAL_ANSWER_SCHEMA_FAILURE,
            "SLICE3V_VISUAL_ANSWER_SCHEMA_INVALID",
        )
    try:
        answers = tuple(_question_answer_from_dict(item) for item in document["answers"])
        return VisualAnswerPayload(
            visible_symbol=document["visible_symbol"],
            exchange=document["exchange"],
            trading_date=date.fromisoformat(document["trading_date"]),
            timeframe=IntradayTimeframe(document["timeframe"]),
            observation_boundary=datetime.fromisoformat(document["observation_boundary"]),
            chart_observed_at=datetime.fromisoformat(document["chart_observed_at"]),
            chart_available=document["chart_available"],
            answers=answers,
            schema_identity=document["schema_identity"],
            question_set_identity=document["question_set_identity"],
        )
    except Slice3VContractError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise Slice3VContractError(
            ValidationFailureState.VISUAL_ANSWER_SCHEMA_FAILURE,
            "SLICE3V_VISUAL_ANSWER_SCHEMA_INVALID",
        ) from error


def validation_record_payload(value: ValidationRecord) -> dict[str, object]:
    return {
        **_validation_run_payload(value),
        "compared_at": value.compared_at.isoformat(),
        "comparison_results": [_comparison_item_dict(item) for item in value.comparison_results],
        "discrepancies": [_discrepancy_dict(item) for item in value.discrepancies],
        "schema_identity": value.schema_identity,
    }


def _compare_fact(
    machine: MachineFact,
    answer: VisualQuestionAnswer,
    visual: VisualObservation | None,
) -> ComparisonItem:
    if answer.state is QuestionAnswerState.NOT_OBSERVABLE or visual is None:
        return _comparison_item(
            machine, ComparisonResult.NOT_VISUALLY_VERIFIABLE, visual
        )
    if visual.precision in {
        VisualPrecision.APPROXIMATE,
        VisualPrecision.NOT_OBSERVABLE,
    }:
        return _comparison_item(
            machine, ComparisonResult.NOT_VISUALLY_VERIFIABLE, visual
        )
    if visual.value_kind is not machine.value_kind:
        return _comparison_item(machine, ComparisonResult.MISMATCH, visual)
    if visual.precision is VisualPrecision.RELATIONAL_ONLY:
        result = (
            ComparisonResult.MATCH
            if machine.value_kind is FactualValueKind.RELATION
            and visual.value == machine.value
            else ComparisonResult.MISMATCH
        )
    else:
        result = (
            ComparisonResult.MATCH
            if visual.value == machine.value
            else ComparisonResult.MISMATCH
        )
    return _comparison_item(machine, result, visual)


def _comparison_item(
    machine: MachineFact,
    result: ComparisonResult,
    visual: VisualObservation | None,
) -> ComparisonItem:
    return ComparisonItem(
        question=machine.question,
        fact_key=machine.fact_key,
        result=result,
        machine_value_kind=machine.value_kind,
        machine_value=machine.value,
        visual_precision=visual.precision if visual is not None else None,
        visual_value_kind=visual.value_kind if visual is not None else None,
        visual_value=visual.value if visual is not None else None,
    )


def _preflight_mismatch(
    machine: MachineEvidence,
    visual: VisualAnswer,
    compared_at: datetime,
    question: ValidationQuestion,
    fact_key: str,
    result: ComparisonResult,
    family: DiscrepancyFamily,
    explanation: str,
) -> ValidationRecord:
    return _record(
        machine,
        visual,
        compared_at,
        (ComparisonItem(question, fact_key, result, None, None, None, None, None),),
        (DiscrepancyRecord(question, fact_key, family, explanation),),
    )


def _record(
    machine: MachineEvidence,
    visual: VisualAnswer,
    compared_at: datetime,
    results: tuple[ComparisonItem, ...],
    discrepancies: tuple[DiscrepancyRecord, ...],
) -> ValidationRecord:
    base = {
        "canonical_instrument_id": machine.canonical_instrument_id,
        "trading_date": machine.trading_date.isoformat(),
        "observation_boundary": machine.observation_boundary.isoformat(),
        "timeframe": machine.timeframe.value,
        "machine_evidence_identity": machine.evidence_identity,
        "visual_evidence_identity": visual.visual_evidence_identity,
        "evidence_family": machine.evidence_family.value,
        "question_set_identity": SLICE3V_QUESTION_SET,
        "visual_answer_schema_identity": SLICE3V_VISUAL_ANSWER_SCHEMA,
        "comparison_policy_identity": SLICE3V_COMPARISON_POLICY,
    }
    validation_run_identity = _identity("SLICE3V-VALIDATION-RUN-", base)
    shell = _ValidationRecordShell(
        validation_run_identity=validation_run_identity,
        canonical_instrument_id=machine.canonical_instrument_id,
        trading_date=machine.trading_date,
        observation_boundary=machine.observation_boundary,
        timeframe=machine.timeframe,
        machine_evidence_identity=machine.evidence_identity,
        visual_evidence_identity=visual.visual_evidence_identity,
        evidence_family=machine.evidence_family,
        compared_at=compared_at,
        comparison_results=results,
        discrepancies=discrepancies,
    )
    payload = validation_record_payload(shell)  # type: ignore[arg-type]
    return ValidationRecord(
        validation_record_identity=_identity("SLICE3V-VALIDATION-RECORD-", payload),
        integrity_identity=_identity("SHA256-", payload),
        **shell.__dict__,
    )


@dataclass(frozen=True)
class _ValidationRecordShell:
    validation_run_identity: str
    canonical_instrument_id: str
    trading_date: date
    observation_boundary: datetime
    timeframe: IntradayTimeframe
    machine_evidence_identity: str
    visual_evidence_identity: str
    evidence_family: ValidationEvidenceFamily
    compared_at: datetime
    comparison_results: tuple[ComparisonItem, ...]
    discrepancies: tuple[DiscrepancyRecord, ...]
    question_set_identity: str = SLICE3V_QUESTION_SET
    visual_answer_schema_identity: str = SLICE3V_VISUAL_ANSWER_SCHEMA
    comparison_policy_identity: str = SLICE3V_COMPARISON_POLICY
    schema_identity: str = SLICE3V_VALIDATION_RECORD_SCHEMA


def _validation_run_payload(value: ValidationRecord | _ValidationRecordShell) -> dict[str, object]:
    return {
        "canonical_instrument_id": value.canonical_instrument_id,
        "trading_date": value.trading_date.isoformat(),
        "observation_boundary": value.observation_boundary.isoformat(),
        "timeframe": value.timeframe.value,
        "machine_evidence_identity": value.machine_evidence_identity,
        "visual_evidence_identity": value.visual_evidence_identity,
        "evidence_family": value.evidence_family.value,
        "question_set_identity": value.question_set_identity,
        "visual_answer_schema_identity": value.visual_answer_schema_identity,
        "comparison_policy_identity": value.comparison_policy_identity,
    }


def _question_answer_from_dict(value: object) -> VisualQuestionAnswer:
    if not isinstance(value, dict) or set(value) != {
        "question", "state", "unavailability_reason", "observations"
    }:
        raise ValueError
    question = ValidationQuestion(value["question"])
    return VisualQuestionAnswer(
        question=question,
        state=QuestionAnswerState(value["state"]),
        observations=tuple(_visual_observation_from_dict(item) for item in value["observations"]),
        unavailability_reason=value["unavailability_reason"],
    )


def _visual_observation_from_dict(value: object) -> VisualObservation:
    if not isinstance(value, dict) or set(value) != {
        "question", "fact_key", "precision", "value_kind", "value", "factual_note"
    }:
        raise ValueError
    kind = None if value["value_kind"] is None else FactualValueKind(value["value_kind"])
    parsed = _value_from_json(kind, value["value"])
    return VisualObservation(
        question=ValidationQuestion(value["question"]),
        fact_key=value["fact_key"],
        precision=VisualPrecision(value["precision"]),
        value_kind=kind,
        value=parsed,
        factual_note=value["factual_note"],
    )


def _comparison_item_dict(item: ComparisonItem) -> dict[str, object]:
    return {
        "question": item.question.value,
        "fact_key": item.fact_key,
        "result": item.result.value,
        "machine_value_kind": (
            item.machine_value_kind.value if item.machine_value_kind is not None else None
        ),
        "machine_value": _json_value(item.machine_value),
        "visual_precision": (
            item.visual_precision.value if item.visual_precision is not None else None
        ),
        "visual_value_kind": (
            item.visual_value_kind.value if item.visual_value_kind is not None else None
        ),
        "visual_value": _json_value(item.visual_value),
    }


def _discrepancy_dict(item: DiscrepancyRecord) -> dict[str, object]:
    return {
        "question": item.question.value,
        "fact_key": item.fact_key,
        "family": item.family.value,
        "factual_explanation": item.factual_explanation,
    }


def _normalize_value(kind: FactualValueKind, value: object) -> FactValue:
    if kind is FactualValueKind.NUMERIC:
        if isinstance(value, bool):
            raise ValueError("SLICE3V_NUMERIC_VALUE_INVALID")
        try:
            result = Decimal(str(value))
        except (InvalidOperation, ValueError) as error:
            raise ValueError("SLICE3V_NUMERIC_VALUE_INVALID") from error
        if not result.is_finite():
            raise ValueError("SLICE3V_NUMERIC_VALUE_INVALID")
        return result
    if kind is FactualValueKind.BOOLEAN:
        if type(value) is not bool:
            raise ValueError("SLICE3V_BOOLEAN_VALUE_INVALID")
        return value
    if not _text(value, 192):
        raise ValueError("SLICE3V_TEXT_VALUE_INVALID")
    return value


def _value_from_json(kind: FactualValueKind | None, value: object) -> FactValue | None:
    if kind is None:
        if value is not None:
            raise ValueError
        return None
    return _normalize_value(kind, value)


def _json_value(value: FactValue | None) -> str | bool | None:
    return str(value) if isinstance(value, Decimal) else value


def _identity(prefix: str, payload: object) -> str:
    canonical = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return f"{prefix}{sha256(canonical.encode('utf-8')).hexdigest()}"


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _text(value: object, maximum: int) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and len(value) <= maximum
    )


def _key(value: object) -> bool:
    return isinstance(value, str) and _KEY.fullmatch(value) is not None


__all__ = [
    "ANSWER_QUESTIONS",
    "ComparisonItem",
    "ComparisonResult",
    "DiscrepancyFamily",
    "DiscrepancyRecord",
    "FactualValueKind",
    "MachineEvidence",
    "MachineEvidenceState",
    "MachineFact",
    "QUESTION_SET",
    "QuestionAnswerState",
    "SLICE3V_COMPARISON_POLICY",
    "SLICE3V_QUESTION_SET",
    "SLICE3V_VALIDATION_RECORD_SCHEMA",
    "SLICE3V_VISUAL_ANSWER_SCHEMA",
    "Slice3VContractError",
    "ValidationEvidenceFamily",
    "ValidationFailureState",
    "ValidationQuestion",
    "ValidationRecord",
    "ValidationStatistics",
    "VisualAnswer",
    "VisualAnswerPayload",
    "VisualObservation",
    "VisualPrecision",
    "VisualQuestionAnswer",
    "accept_visual_answer",
    "compare_machine_to_visual",
    "validation_record_payload",
    "validation_statistics",
    "visual_answer_payload",
    "visual_answer_payload_from_dict",
]


# WO-02B: additive V2 contracts. V1 serialization and interpretation stay frozen.

PANEL_VALIDATION_CONTRACT = "KRONOS-INTRADAY-SLICE-3V-PANEL-VALIDATION-V2"
PANEL_VALIDATION_VERSION = "2.0.0"


class ValidationState(StrEnum):
    VALIDATED = "VALIDATED"
    PARTIALLY_VALIDATED = "PARTIALLY_VALIDATED"
    NOT_VALIDATED = "NOT_VALIDATED"
    UNVERIFIABLE = "UNVERIFIABLE"


class RequiredFactCoverage(StrEnum):
    COMPLETE = "COMPLETE_REQUIRED_FACT_COVERAGE"
    PARTIAL = "PARTIAL_REQUIRED_FACT_COVERAGE"
    NONE = "NO_REQUIRED_FACT_COVERAGE"


class FactObservability(StrEnum):
    EXACT = "EXACT"
    APPROXIMATE = "APPROXIMATE"
    RELATIONAL = "RELATIONAL"
    NOT_VISIBLE = "NOT_VISIBLE"
    UNVERIFIABLE = "UNVERIFIABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class FactDisposition(StrEnum):
    OBSERVED = "OBSERVED"
    NOT_VISIBLE = "NOT_VISIBLE"
    UNVERIFIABLE = "UNVERIFIABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    MISSING = "MISSING"


# Independent of the supplied machine/visual subset. Applicability is machine-owned.
PANEL_REQUIRED_FACTS = (
    *((f"candle.{k}", ValidationQuestion.COMPLETED_CANDLE) for k in ("open", "high", "low", "close")),
    *((f"previous.{k}", ValidationQuestion.PREVIOUS_SESSION) for k in ("high", "low", "close", "pdh", "pdl")),
    *((f"pivot.{k}", ValidationQuestion.CLASSIC_PIVOTS) for k in ("p", "r1", "r2", "r3", "r4", "s1", "s2", "s3", "s4")),
    *((f"cpr.{k}", ValidationQuestion.CPR) for k in ("pivot", "lower", "upper", "width")),
    *((f"structure.{k}", ValidationQuestion.STRUCTURAL_EVENTS) for k in
      ("local_high", "local_low", "range", "break", "retest", "return_through", "boundary_interaction")),
    ("volume.participation", ValidationQuestion.VOLUME_PARTICIPATION),
)
_PANEL_FACT_KEYS = tuple(k for k, _ in PANEL_REQUIRED_FACTS)
_PANEL_QUESTIONS = dict(PANEL_REQUIRED_FACTS)


@dataclass(frozen=True, slots=True)
class PanelSource:
    context_key: str
    machine_source_identity: str
    candle: GovernedCandle

    def __post_init__(self) -> None:
        if not _key(self.context_key) or not _text(self.machine_source_identity, 256) or type(self.candle) is not GovernedCandle:
            raise ValueError("SLICE3V_PANEL_SOURCE_INVALID")


@dataclass(frozen=True, slots=True)
class RequiredPanelFact:
    fact_key: str
    context_key: str
    applicable: bool = True
    applicability_provenance: str | None = None
    relational_permitted: bool = False

    def __post_init__(self) -> None:
        if (
            self.fact_key not in _PANEL_FACT_KEYS or not _key(self.context_key)
            or type(self.applicable) is not bool or type(self.relational_permitted) is not bool
            or (not self.applicable and not _text(self.applicability_provenance, 256))
        ):
            raise ValueError("SLICE3V_REQUIRED_FACT_INVALID")


@dataclass(frozen=True, slots=True)
class PanelValidationRequest:
    machine: MachineEvidence
    chart_revision_identity: str
    chart_payload_sha256: str
    chart_received_at: datetime
    panel_context_key: str
    sources: tuple[PanelSource, ...]
    required_facts: tuple[RequiredPanelFact, ...]
    provenance: tuple[str, ...]
    contract_identity: str = PANEL_VALIDATION_CONTRACT
    contract_version: str = PANEL_VALIDATION_VERSION

    def __post_init__(self) -> None:
        source_keys = tuple(s.context_key for s in self.sources)
        if (
            type(self.machine) is not MachineEvidence
            or self.machine.state is not MachineEvidenceState.FROZEN
            or self.machine.frozen_at < self.machine.observation_boundary
            or self.machine.exchange != "NSE"
            or self.machine.evidence_family is not ValidationEvidenceFamily.NATIVE_CHART
            or not _text(self.chart_revision_identity, 256)
            or not _panel_digest(self.chart_payload_sha256)
            or not _aware(self.chart_received_at)
            or type(self.sources) is not tuple or not self.sources
            or any(type(s) is not PanelSource for s in self.sources)
            or len(set(source_keys)) != len(source_keys)
            or self.panel_context_key not in source_keys
            or any(s.candle.canonical_instrument_id != self.machine.canonical_instrument_id
                   or s.candle.observation_boundary.observed_at > self.machine.frozen_at
                   or s.candle.provenance.retrieved_at > self.machine.frozen_at for s in self.sources)
            or type(self.required_facts) is not tuple
            or tuple(f.fact_key for f in self.required_facts) != _PANEL_FACT_KEYS
            or any(type(f) is not RequiredPanelFact or f.context_key not in source_keys for f in self.required_facts)
            or not self.provenance or type(self.provenance) is not tuple
            or any(not _text(p, 256) for p in self.provenance)
            or self.contract_identity != PANEL_VALIDATION_CONTRACT
            or self.contract_version != PANEL_VALIDATION_VERSION
        ):
            raise ValueError("SLICE3V_PANEL_REQUEST_INVALID")
        panel = next(s.candle for s in self.sources if s.context_key == self.panel_context_key)
        if panel.boundary.timeframe is not self.machine.timeframe or any(
            f.fact_key.startswith("candle.") and f.context_key != self.panel_context_key for f in self.required_facts
        ):
            raise ValueError("SLICE3V_PANEL_TIMEFRAME_INVALID")
        if any(f.fact_key not in _PANEL_QUESTIONS or f.question is not _PANEL_QUESTIONS[f.fact_key] for f in self.machine.facts):
            raise ValueError("SLICE3V_PANEL_MACHINE_FACT_INVALID")


@dataclass(frozen=True, slots=True)
class ObservedPanelTime:
    context_key: str
    trading_date: date | None = None
    session: str | None = None
    timezone: str | None = None
    timeframe: IntradayTimeframe | None = None
    candle_start: datetime | None = None
    candle_end: datetime | None = None
    completion: CandleCompletion | None = None

    def __post_init__(self) -> None:
        if (
            not _key(self.context_key)
            or (self.trading_date is not None and type(self.trading_date) is not date)
            or (self.timeframe is not None and type(self.timeframe) is not IntradayTimeframe)
            or (self.completion is not None and type(self.completion) is not CandleCompletion)
            or any(x is not None and not _aware(x) for x in (self.candle_start, self.candle_end))
            or any(x is not None and not _text(x, 256) for x in (self.session, self.timezone))
        ):
            raise ValueError("SLICE3V_OBSERVED_TIME_INVALID")


@dataclass(frozen=True, slots=True)
class PanelFactObservation:
    fact_key: str
    observability: FactObservability
    value_kind: FactualValueKind | None = None
    value: FactValue | None = None

    def __post_init__(self) -> None:
        if self.fact_key not in _PANEL_FACT_KEYS or type(self.observability) is not FactObservability:
            raise ValueError("SLICE3V_PANEL_OBSERVATION_INVALID")
        if self.observability in (FactObservability.NOT_VISIBLE, FactObservability.UNVERIFIABLE, FactObservability.NOT_APPLICABLE):
            if self.value is not None or self.value_kind is not None:
                raise ValueError("SLICE3V_UNOBSERVABLE_VALUE_PROHIBITED")
        else:
            if self.value_kind is FactualValueKind.RELATION and self.observability is not FactObservability.RELATIONAL:
                raise ValueError("SLICE3V_RELATIONAL_PRECISION_REQUIRED")
            precision = {
                FactObservability.EXACT: VisualPrecision.EXACT,
                FactObservability.APPROXIMATE: VisualPrecision.APPROXIMATE,
                FactObservability.RELATIONAL: VisualPrecision.RELATIONAL_ONLY,
            }[self.observability]
            observation = VisualObservation(_PANEL_QUESTIONS[self.fact_key], self.fact_key, precision, self.value_kind, self.value)
            object.__setattr__(self, "value", observation.value)


@dataclass(frozen=True, slots=True)
class PanelVisualObservation:
    """Observer-only facts: no canonical ID, machine values, run ID or conclusions."""
    observed_subject: str
    exchange: str
    timeframe: IntradayTimeframe
    chart_captured_at: datetime | None
    answered_at: datetime
    temporal_contexts: tuple[ObservedPanelTime, ...]
    facts: tuple[PanelFactObservation, ...]
    contract_identity: str = PANEL_VALIDATION_CONTRACT
    contract_version: str = PANEL_VALIDATION_VERSION

    def __post_init__(self) -> None:
        if (
            (not isinstance(self.observed_subject, str) or not self.observed_subject or len(self.observed_subject) > 192) or not _text(self.exchange, 32)
            or type(self.timeframe) is not IntradayTimeframe
            or not _aware(self.answered_at)
            or (self.chart_captured_at is not None and not _aware(self.chart_captured_at))
            or type(self.temporal_contexts) is not tuple or type(self.facts) is not tuple
            or any(type(t) is not ObservedPanelTime for t in self.temporal_contexts)
            or any(type(f) is not PanelFactObservation for f in self.facts)
            or len({t.context_key for t in self.temporal_contexts}) != len(self.temporal_contexts)
            or len({f.fact_key for f in self.facts}) != len(self.facts)
            or self.contract_identity != PANEL_VALIDATION_CONTRACT
            or self.contract_version != PANEL_VALIDATION_VERSION
        ):
            raise ValueError("SLICE3V_PANEL_VISUAL_SCHEMA_INVALID")


@dataclass(frozen=True, slots=True)
class PanelFactResult:
    fact_key: str
    context_key: str
    expected: bool
    disposition: FactDisposition
    result: ValidationState
    reason: str

    def __post_init__(self) -> None:
        if (self.fact_key not in _PANEL_FACT_KEYS or not _key(self.context_key)
            or self.expected is not True or type(self.disposition) is not FactDisposition
            or type(self.result) is not ValidationState or not _text(self.reason, 256)):
            raise ValueError("SLICE3V_PANEL_FACT_RESULT_INVALID")


@dataclass(frozen=True, slots=True)
class PanelTemporalResult:
    context_key: str
    schedule: MarketSchedule | None
    result: ValidationState
    reason: str


@dataclass(frozen=True, slots=True)
class PanelValidationRecord:
    request: PanelValidationRequest
    visual: PanelVisualObservation
    actual_chart_sha256: str
    bound_chart_revision_identity: str
    visual_identity: VisualIdentityResolution | None
    visual_identity_failure: str | None
    temporal_results: tuple[PanelTemporalResult, ...]
    fact_results: tuple[PanelFactResult, ...]
    file_identity: ValidationState
    visual_identity_state: ValidationState
    temporal_correspondence: ValidationState
    factual_correspondence: ValidationState
    answer_import: ValidationState
    visual_reliability: ValidationState
    coverage: RequiredFactCoverage
    overall: ValidationState
    compared_at: datetime
    imported_at: datetime | None
    visual_observation_identity: str
    validation_record_identity: str
    integrity_identity: str

    def __post_init__(self) -> None:
        payload = _panel_record_payload(self)
        if (
            self.validation_record_identity != _identity("SLICE3V-PANEL-RECORD-", payload)
            or self.integrity_identity != _identity("SHA256-", payload)
            or self.visual_observation_identity != _identity("SLICE3V-PANEL-OBSERVATION-", _panel_encode(self.visual))
            or tuple(r.fact_key for r in self.fact_results) != _PANEL_FACT_KEYS
            or self.imported_at is not None
            or self.answer_import is not ValidationState.NOT_VALIDATED
            or self.visual_reliability is not ValidationState.NOT_VALIDATED
        ):
            raise ValueError("SLICE3V_PANEL_RECORD_INTEGRITY_INVALID")


def _panel_digest(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _panel_temporal(
    source: PanelSource, observed: ObservedPanelTime | None, schedule: MarketSchedule | None,
    request: PanelValidationRequest, visual: PanelVisualObservation,
) -> PanelTemporalResult:
    def result(state: ValidationState, reason: str) -> PanelTemporalResult:
        return PanelTemporalResult(source.context_key, schedule, state, reason)

    boundary = source.candle.boundary
    if schedule is None:
        return result(ValidationState.UNVERIFIABLE, "SESSION_AUTHORITY_UNAVAILABLE")
    day = MarketDaySchedule(
        exchange=schedule.exchange, trading_date=schedule.trading_date,
        session_id=schedule.session_identity, timezone=schedule.timezone,
        status=TradingDayStatus.TRADING,
        windows=tuple(MarketWindow(w.window_open, w.window_close) for w in schedule.windows),
        source_identity=schedule.source_identity, source_version=schedule.calendar_version,
    )
    if boundary not in expected_candle_boundaries(day, boundary.timeframe):
        return result(ValidationState.NOT_VALIDATED, "SOURCE_CANDLE_SESSION_MISMATCH")
    if source.candle.completion is not CandleCompletion.COMPLETE or boundary.end > request.machine.observation_boundary:
        return result(ValidationState.UNVERIFIABLE, "COMPLETED_CANDLE_NOT_PROVEN")
    if observed is None or any(getattr(observed, f) is None for f in (
        "trading_date", "session", "timezone", "timeframe", "candle_start", "candle_end", "completion",
    )) or visual.chart_captured_at is None:
        return result(ValidationState.UNVERIFIABLE, "TEMPORAL_EVIDENCE_MISSING")
    if observed.completion is not CandleCompletion.COMPLETE:
        return result(ValidationState.UNVERIFIABLE, "OBSERVED_CANDLE_INCOMPLETE")
    for label, actual, expected in (
        ("TRADING_DATE", observed.trading_date, boundary.trading_date),
        ("SESSION", observed.session, schedule.session_type),
        ("TIMEZONE", observed.timezone, schedule.timezone),
        ("TIMEFRAME", observed.timeframe, boundary.timeframe),
        ("CANDLE_START", observed.candle_start, boundary.start),
        ("CANDLE_END", observed.candle_end, boundary.end),
    ):
        if actual != expected:
            return result(ValidationState.NOT_VALIDATED, label + "_MISMATCH")
    if not (
        boundary.end <= visual.chart_captured_at <= request.chart_received_at
        and max(request.machine.frozen_at, request.chart_received_at) <= visual.answered_at
    ):
        return result(ValidationState.UNVERIFIABLE, "CAPTURE_OR_ANSWER_CHRONOLOGY_UNPROVEN")
    return result(ValidationState.VALIDATED, "EXACT_COMPLETED_SOURCE_CONTEXT")


def _panel_rollup(states: tuple[ValidationState, ...]) -> ValidationState:
    if not states:
        return ValidationState.NOT_VALIDATED
    if all(s is ValidationState.VALIDATED for s in states):
        return ValidationState.VALIDATED
    if ValidationState.NOT_VALIDATED in states:
        return ValidationState.NOT_VALIDATED
    if ValidationState.VALIDATED in states or ValidationState.PARTIALLY_VALIDATED in states:
        return ValidationState.PARTIALLY_VALIDATED
    return ValidationState.UNVERIFIABLE


def validate_panel(
    request: PanelValidationRequest, visual: PanelVisualObservation, *,
    chart_payload: bytes, bound_chart_revision_identity: str,
    identity_resolver: VisualIdentityResolver, calendar: MarketCalendarPublisher,
    compared_at: datetime,
) -> PanelValidationRecord:
    """Read-only V2 comparison. No imports, currentization, capture or authority writes."""
    if type(request) is not PanelValidationRequest or type(visual) is not PanelVisualObservation:
        raise ValueError("SLICE3V_PANEL_INPUT_INVALID")
    if (
        type(chart_payload) is not bytes or not _aware(compared_at)
        or compared_at < max(request.machine.frozen_at, visual.answered_at, request.chart_received_at)
        or visual.answered_at < request.machine.frozen_at
    ):
        raise ValueError("SLICE3V_PANEL_CHRONOLOGY_INVALID")
    if any(t.context_key not in {s.context_key for s in request.sources} for t in visual.temporal_contexts):
        raise ValueError("SLICE3V_UNEXPECTED_TEMPORAL_CONTEXT")
    digest = sha256(chart_payload).hexdigest()
    file_state = (ValidationState.VALIDATED if digest == request.chart_payload_sha256
                  and bound_chart_revision_identity == request.chart_revision_identity else ValidationState.NOT_VALIDATED)
    resolution = None
    failure = None
    try:
        resolution = identity_resolver.resolve(
            observed_visible_subject_identity=visual.observed_subject,
            source_context=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
            governed_observation_boundary=request.machine.observation_boundary,
        )
    except VisualIdentityResolutionError as error:
        failure = error.failure.value
    identity_state = ValidationState.VALIDATED if (
        resolution is not None
        and resolution.canonical_subject_identity == request.machine.canonical_instrument_id
        and visual.exchange == request.machine.exchange and visual.timeframe is request.machine.timeframe
    ) else ValidationState.NOT_VALIDATED
    if identity_state is ValidationState.NOT_VALIDATED and failure is None:
        failure = "PANEL_IDENTITY_MISMATCH"

    contexts = {t.context_key: t for t in visual.temporal_contexts}
    temporal = []
    for source in request.sources:
        schedule = None
        try:
            profile = calendar.instrument_session_profile(
                request.machine.exchange, source.candle.boundary.trading_date,
                canonical_instrument_id=request.machine.canonical_instrument_id,
                observed_at=request.machine.observation_boundary,
            )
            if profile is not None:
                schedule = next((s for s in (profile.continuous_trading, profile.closing_auction_session)
                                 if s is not None and s.session_identity == source.candle.boundary.session_id), None)
        except ValueError:
            pass  # Explicit unavailable result; never invent a replacement session.
        temporal.append(_panel_temporal(source, contexts.get(source.context_key), schedule, request, visual))
    times = {t.context_key: t for t in temporal}
    observations = {f.fact_key: f for f in visual.facts}
    machine_facts = {f.fact_key: f for f in request.machine.facts}
    rows = []
    try:
        previous_date = max(d for d in calendar.publication("NSE").trading_dates if d < request.machine.trading_date)
    except (ValueError, KeyError):
        previous_date = None
    for required in request.required_facts:
        obs = observations.get(required.fact_key)
        fact = machine_facts.get(required.fact_key)
        source = next(s.candle for s in request.sources if s.context_key == required.context_key)
        source_field = required.fact_key.split(".")[1]
        if required.fact_key.startswith("previous."):
            source_field = {"pdh": "high", "pdl": "low"}.get(source_field, source_field)
        source_mismatch = (fact is not None and required.fact_key.startswith(("candle.", "previous."))
                           and (fact.value_kind is not FactualValueKind.NUMERIC or fact.value != getattr(source, source_field)))
        disposition = FactDisposition.MISSING if obs is None else (
            FactDisposition.OBSERVED if obs.observability in (
                FactObservability.EXACT, FactObservability.APPROXIMATE, FactObservability.RELATIONAL
            ) else FactDisposition(obs.observability.value)
        )
        state, reason = ValidationState.UNVERIFIABLE, "VISUAL_FACT_MISSING"
        if not required.applicable:
            state = ValidationState.NOT_VALIDATED
            reason = "NOT_APPLICABLE"
            if obs is not None and obs.observability is not FactObservability.NOT_APPLICABLE:
                reason = "APPLICABILITY_CONFLICT"
        elif file_state is not ValidationState.VALIDATED or identity_state is not ValidationState.VALIDATED:
            state, reason = ValidationState.NOT_VALIDATED, "PANEL_IDENTITY_NOT_VALIDATED"
        elif times[required.context_key].result is not ValidationState.VALIDATED:
            state, reason = times[required.context_key].result, times[required.context_key].reason
        elif obs is not None and obs.observability is FactObservability.NOT_APPLICABLE:
            state, reason = ValidationState.NOT_VALIDATED, "APPLICABILITY_CONFLICT"
        elif fact is None:
            reason = "MACHINE_FACT_UNAVAILABLE"
        elif required.fact_key.startswith(("previous.", "pivot.", "cpr.")) and (
            source.boundary.timeframe is not IntradayTimeframe.DAILY or source.boundary.trading_date != previous_date
        ):
            state, reason = ValidationState.NOT_VALIDATED, "PREVIOUS_SESSION_SOURCE_MISMATCH"
        elif source_mismatch:
            state, reason = ValidationState.NOT_VALIDATED, "MACHINE_SOURCE_FACT_MISMATCH"
        elif obs is not None and disposition is FactDisposition.OBSERVED:
            if obs.observability is FactObservability.RELATIONAL and not required.relational_permitted:
                state, reason = ValidationState.NOT_VALIDATED, "RELATIONAL_COMPARISON_NOT_PERMITTED"
            else:
                precision = {
                    FactObservability.EXACT: VisualPrecision.EXACT,
                    FactObservability.APPROXIMATE: VisualPrecision.APPROXIMATE,
                    FactObservability.RELATIONAL: VisualPrecision.RELATIONAL_ONLY,
                }[obs.observability]
                observed = VisualObservation(fact.question, fact.fact_key, precision, obs.value_kind, obs.value)
                comparison = _compare_fact(fact, VisualQuestionAnswer(fact.question, QuestionAnswerState.OBSERVED, (observed,)), observed)
                state = {ComparisonResult.MATCH: ValidationState.VALIDATED,
                         ComparisonResult.MISMATCH: ValidationState.NOT_VALIDATED,
                         ComparisonResult.NOT_VISUALLY_VERIFIABLE: ValidationState.UNVERIFIABLE}[comparison.result]
                reason = comparison.result.value
        elif obs is not None:
            reason = obs.observability.value
        rows.append(PanelFactResult(required.fact_key, required.context_key, True, disposition, state, reason))
    accounted = sum((r.disposition is FactDisposition.OBSERVED and r.fact_key in machine_facts)
                    or (r.disposition is FactDisposition.NOT_APPLICABLE and r.reason == "NOT_APPLICABLE") for r in rows)
    coverage = RequiredFactCoverage.COMPLETE if accounted == len(rows) else (
        RequiredFactCoverage.PARTIAL if accounted else RequiredFactCoverage.NONE)
    applicable_states = tuple(r.result for r, f in zip(rows, request.required_facts)
                              if f.applicable or r.reason == "APPLICABILITY_CONFLICT")
    factual = _panel_rollup(applicable_states)
    temporal_state = _panel_rollup(tuple(t.result for t in temporal))
    overall = factual
    if temporal_state is ValidationState.NOT_VALIDATED:
        overall = ValidationState.NOT_VALIDATED
    elif factual is ValidationState.VALIDATED and temporal_state is not ValidationState.VALIDATED:
        overall = temporal_state
    if factual is ValidationState.NOT_VALIDATED or identity_state is ValidationState.NOT_VALIDATED or file_state is ValidationState.NOT_VALIDATED:
        overall = ValidationState.NOT_VALIDATED
    values = dict(
        request=request, visual=visual, actual_chart_sha256=digest,
        bound_chart_revision_identity=bound_chart_revision_identity,
        visual_identity=resolution, visual_identity_failure=failure,
        temporal_results=tuple(temporal), fact_results=tuple(rows),
        file_identity=file_state, visual_identity_state=identity_state,
        temporal_correspondence=temporal_state, factual_correspondence=factual,
        answer_import=ValidationState.NOT_VALIDATED, visual_reliability=ValidationState.NOT_VALIDATED,
        coverage=coverage, overall=overall, compared_at=compared_at, imported_at=None,
        visual_observation_identity=_identity("SLICE3V-PANEL-OBSERVATION-", _panel_encode(visual)),
    )
    payload = {k: _panel_encode(v) for k, v in values.items()}
    return PanelValidationRecord(
        **values,
        validation_record_identity=_identity("SLICE3V-PANEL-RECORD-", payload),
        integrity_identity=_identity("SHA256-", payload),
    )


def _panel_encode(value: object) -> object:
    """Closed tagged codec preserves Decimal precision and immutable tuple types."""
    if is_dataclass(value):
        return {"type": type(value).__name__, "fields": {f.name: _panel_encode(getattr(value, f.name)) for f in fields(value)}}
    if isinstance(value, StrEnum):
        return {"enum": type(value).__name__, "value": value.value}
    if type(value) in (datetime, date, Decimal):
        return {"scalar": type(value).__name__, "value": str(value)}
    if type(value) is tuple:
        return [_panel_encode(v) for v in value]
    if value is None or type(value) in (str, int, bool):
        return value
    raise ValueError("SLICE3V_PANEL_ENCODING_INVALID")


def _panel_decode(value: object) -> object:
    if type(value) is list:
        return tuple(_panel_decode(v) for v in value)
    if value is None or type(value) in (str, int, bool):
        return value
    if type(value) is not dict:
        raise ValueError("SLICE3V_PANEL_DOCUMENT_INVALID")
    if set(value) == {"scalar", "value"}:
        return {"datetime": datetime.fromisoformat, "date": date.fromisoformat, "Decimal": Decimal}[value["scalar"]](value["value"])
    if set(value) == {"enum", "value"}:
        enums = (IntradayTimeframe, CandleCompletion, ValidationQuestion, FactualValueKind,
                 DiscrepancyFamily, MachineEvidenceState, ValidationEvidenceFamily,
                 VisualIdentitySourceContext, MarketAvailability, ScheduleFreshness, ScheduleIntegrity,
                 ValidationState, RequiredFactCoverage, FactObservability, FactDisposition)
        cls = next(c for c in enums if c.__name__ == value["enum"])
        return cls(value["value"])
    if set(value) == {"type", "fields"}:
        classes = (PanelSource, RequiredPanelFact, PanelValidationRequest, ObservedPanelTime,
                   PanelFactObservation, PanelVisualObservation, PanelFactResult, PanelTemporalResult,
                   PanelValidationRecord, MachineEvidence, MachineFact, GovernedCandle, CandleBoundary,
                   SourceProvenance, ObservationBoundary, VisualIdentityResolution, MarketSchedule,
                   MarketSessionWindow)
        cls = next(c for c in classes if c.__name__ == value["type"])
        if type(value["fields"]) is not dict or set(value["fields"]) != {f.name for f in fields(cls)}:
            raise ValueError("SLICE3V_PANEL_DOCUMENT_INVALID")
        return cls(**{k: _panel_decode(v) for k, v in value["fields"].items()})
    raise ValueError("SLICE3V_PANEL_DOCUMENT_INVALID")


def _panel_record_payload(value: PanelValidationRecord) -> dict[str, object]:
    return {f.name: _panel_encode(getattr(value, f.name)) for f in fields(value)
            if f.name not in ("validation_record_identity", "integrity_identity")}


def panel_validation_document(value: PanelValidationRecord) -> dict[str, object]:
    if type(value) is not PanelValidationRecord:
        raise ValueError("SLICE3V_PANEL_RECORD_INVALID")
    return _panel_encode(value)


def panel_validation_from_document(document: object) -> PanelValidationRecord:
    try:
        value = _panel_decode(document)
        if type(value) is not PanelValidationRecord or panel_validation_document(value) != document:
            raise ValueError
        return value
    except (ValueError, TypeError, KeyError, StopIteration, AttributeError, InvalidOperation) as error:
        raise ValueError("SLICE3V_PANEL_DOCUMENT_INVALID") from error


__all__ += [
    "PANEL_VALIDATION_CONTRACT", "PANEL_VALIDATION_VERSION", "PANEL_REQUIRED_FACTS",
    "ValidationState", "RequiredFactCoverage", "FactObservability", "FactDisposition",
    "PanelSource", "RequiredPanelFact", "PanelValidationRequest", "ObservedPanelTime",
    "PanelFactObservation", "PanelVisualObservation", "PanelFactResult", "PanelTemporalResult",
    "PanelValidationRecord", "validate_panel", "panel_validation_document", "panel_validation_from_document",
]
