"""Governed Slice 3V factual/visual validation contracts with no trading authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from hashlib import sha256
import json
import re

from kronos.intraday.contracts import IntradayTimeframe


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
