from __future__ import annotations

from dataclasses import fields, replace
from datetime import date, datetime, timedelta
from decimal import Decimal
import json
from zoneinfo import ZoneInfo

import pytest

from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.validation import (
    ANSWER_QUESTIONS,
    ComparisonResult,
    DiscrepancyFamily,
    FactualValueKind,
    MachineEvidence,
    MachineEvidenceState,
    MachineFact,
    QuestionAnswerState,
    SLICE3V_COMPARISON_POLICY,
    SLICE3V_QUESTION_SET,
    SLICE3V_VALIDATION_RECORD_SCHEMA,
    SLICE3V_VISUAL_ANSWER_SCHEMA,
    Slice3VContractError,
    ValidationFailureState,
    ValidationEvidenceFamily,
    ValidationQuestion,
    VisualAnswerPayload,
    VisualObservation,
    VisualPrecision,
    VisualQuestionAnswer,
    accept_visual_answer,
    compare_machine_to_visual,
    validation_statistics,
    visual_answer_payload,
    visual_answer_payload_from_dict,
)
from kronos.intraday.validation_persistence import LocalSlice3VValidationStore


IST = ZoneInfo("Asia/Kolkata")
TRADING_DATE = date(2026, 8, 17)
BOUNDARY = datetime(2026, 8, 17, 15, 15, tzinfo=IST)
FROZEN_AT = datetime(2026, 8, 18, 8, 0, tzinfo=IST)
OBSERVED_AT = datetime(2026, 8, 18, 8, 30, tzinfo=IST)
COMPARED_AT = datetime(2026, 8, 18, 9, 0, tzinfo=IST)


def _machine(
    *,
    state: MachineEvidenceState = MachineEvidenceState.FROZEN,
) -> MachineEvidence:
    return MachineEvidence(
        evidence_identity="INTRADAY-EVIDENCE-RELIANCE-1D-20260817",
        run_identity="INTRADAY-RUN-02490E741DA64343AAB2916271E98299",
        canonical_instrument_id="NSE:RELIANCE:EQ",
        expected_visible_symbol="RELIANCE",
        exchange="NSE",
        trading_date=TRADING_DATE,
        timeframe=IntradayTimeframe.FIFTEEN_MINUTES,
        observation_boundary=BOUNDARY,
        frozen_at=FROZEN_AT,
        facts=(
            MachineFact(
                ValidationQuestion.COMPLETED_CANDLE,
                "close",
                FactualValueKind.NUMERIC,
                Decimal("1316.0"),
                DiscrepancyFamily.CANDLE_VALUE_DISCREPANCY,
            ),
            MachineFact(
                ValidationQuestion.STRUCTURAL_EVENTS,
                "headline_relationship",
                FactualValueKind.RELATION,
                "CLOSE_ABOVE_BOUNDARY",
                DiscrepancyFamily.STRUCTURAL_EVENT_DISCREPANCY,
            ),
            MachineFact(
                ValidationQuestion.CURRENT_INCOMPLETE_CANDLE,
                "excluded_from_structural_authority",
                FactualValueKind.BOOLEAN,
                True,
                DiscrepancyFamily.COMPLETED_VS_INCOMPLETE_DISCREPANCY,
            ),
        ),
        state=state,
    )


def _observation(
    question: ValidationQuestion,
    fact_key: str,
    precision: VisualPrecision,
    kind: FactualValueKind | None = None,
    value=None,
    *,
    note: str | None = None,
) -> VisualObservation:
    return VisualObservation(
        question=question,
        fact_key=fact_key,
        precision=precision,
        value_kind=kind,
        value=value,
        factual_note=note,
    )


def _payload(
    *observations: VisualObservation,
    symbol: str = "RELIANCE",
    exchange: str = "NSE",
    timeframe: IntradayTimeframe = IntradayTimeframe.FIFTEEN_MINUTES,
    boundary: datetime = BOUNDARY,
    trading_date: date = TRADING_DATE,
    observed_at: datetime = OBSERVED_AT,
) -> VisualAnswerPayload:
    grouped: dict[ValidationQuestion, list[VisualObservation]] = {}
    for observation in observations:
        grouped.setdefault(observation.question, []).append(observation)
    answers = []
    for question in ANSWER_QUESTIONS:
        supplied = tuple(grouped.get(question, ()))
        if supplied:
            answers.append(
                VisualQuestionAnswer(
                    question=question,
                    state=QuestionAnswerState.OBSERVED,
                    observations=supplied,
                )
            )
        elif question is ValidationQuestion.ADDITIONAL_FACTUAL_DISCREPANCY:
            answers.append(
                VisualQuestionAnswer(
                    question=question,
                    state=QuestionAnswerState.NO_ADDITIONAL_DISCREPANCY,
                )
            )
        else:
            answers.append(
                VisualQuestionAnswer(
                    question=question,
                    state=QuestionAnswerState.NOT_OBSERVABLE,
                    unavailability_reason="Not exposed with reliable chart precision.",
                )
            )
    return VisualAnswerPayload(
        visible_symbol=symbol,
        exchange=exchange,
        trading_date=trading_date,
        timeframe=timeframe,
        observation_boundary=boundary,
        chart_observed_at=observed_at,
        chart_available=True,
        answers=tuple(answers),
    )


def _answer(*observations: VisualObservation, **kwargs):
    return accept_visual_answer(_payload(*observations, **kwargs))


def _compare(*observations: VisualObservation, machine=None, **kwargs):
    source = _machine() if machine is None else machine
    return compare_machine_to_visual(
        source,
        _answer(*observations, **kwargs),
        compared_at=COMPARED_AT,
    )


def _result(record, fact_key: str):
    return next(item.result for item in record.comparison_results if item.fact_key == fact_key)


def test_exact_machine_number_matches_only_exact_visual_number() -> None:
    record = _compare(
        _observation(
            ValidationQuestion.COMPLETED_CANDLE,
            "close",
            VisualPrecision.EXACT,
            FactualValueKind.NUMERIC,
            Decimal("1316.0"),
        )
    )

    assert _result(record, "close") is ComparisonResult.MATCH
    assert record.question_set_identity == SLICE3V_QUESTION_SET
    assert record.visual_answer_schema_identity == SLICE3V_VISUAL_ANSWER_SCHEMA
    assert record.comparison_policy_identity == SLICE3V_COMPARISON_POLICY
    assert record.schema_identity == SLICE3V_VALIDATION_RECORD_SCHEMA


def test_relational_match_is_valid_but_approximate_number_has_no_tolerance() -> None:
    record = _compare(
        _observation(
            ValidationQuestion.COMPLETED_CANDLE,
            "close",
            VisualPrecision.APPROXIMATE,
            FactualValueKind.NUMERIC,
            Decimal("1316"),
        ),
        _observation(
            ValidationQuestion.STRUCTURAL_EVENTS,
            "headline_relationship",
            VisualPrecision.RELATIONAL_ONLY,
            FactualValueKind.RELATION,
            "CLOSE_ABOVE_BOUNDARY",
        ),
    )

    assert _result(record, "close") is ComparisonResult.NOT_VISUALLY_VERIFIABLE
    assert _result(record, "headline_relationship") is ComparisonResult.MATCH


def test_exact_value_mismatch_creates_bounded_factual_discrepancy() -> None:
    record = _compare(
        _observation(
            ValidationQuestion.COMPLETED_CANDLE,
            "close",
            VisualPrecision.EXACT,
            FactualValueKind.NUMERIC,
            Decimal("1315.9"),
        )
    )

    assert _result(record, "close") is ComparisonResult.MISMATCH
    discrepancy = next(item for item in record.discrepancies if item.fact_key == "close")
    assert discrepancy.family is DiscrepancyFamily.CANDLE_VALUE_DISCREPANCY
    assert "trade" not in discrepancy.factual_explanation.lower()


def test_not_observable_is_preserved_without_weakening_machine_truth() -> None:
    record = _compare()

    assert all(
        item.result is ComparisonResult.NOT_VISUALLY_VERIFIABLE
        for item in record.comparison_results
    )
    assert record.discrepancies == ()


def test_wrong_chart_identity_fails_closed_as_identity_mismatch() -> None:
    record = _compare(symbol="NOT-RELIANCE")

    assert record.comparison_results[0].result is ComparisonResult.IDENTITY_MISMATCH
    assert record.discrepancies[0].family is (
        DiscrepancyFamily.SOURCE_CHART_IDENTITY_DISCREPANCY
    )


def test_wrong_timeframe_is_not_reinterpreted_as_factual_match() -> None:
    record = _compare(timeframe=IntradayTimeframe.FIVE_MINUTES)

    assert record.comparison_results[0].result is ComparisonResult.TIMEFRAME_MISMATCH


def test_wrong_observation_boundary_is_explicit() -> None:
    record = _compare(boundary=BOUNDARY - timedelta(minutes=15))

    assert record.comparison_results[0].result is (
        ComparisonResult.OBSERVATION_BOUNDARY_MISMATCH
    )
    assert record.discrepancies[0].family is (
        DiscrepancyFamily.SESSION_BOUNDARY_DISCREPANCY
    )


def test_wrong_trading_date_is_sanitized_context_failure() -> None:
    with pytest.raises(Slice3VContractError) as captured:
        _compare(trading_date=date(2026, 8, 18))

    assert captured.value.state is ValidationFailureState.WRONG_TRADING_CONTEXT
    assert str(captured.value) == "SLICE3V_WRONG_TRADING_DATE"


def test_completed_vs_incomplete_separation_is_a_bounded_mismatch() -> None:
    record = _compare(
        _observation(
            ValidationQuestion.CURRENT_INCOMPLETE_CANDLE,
            "excluded_from_structural_authority",
            VisualPrecision.EXACT,
            FactualValueKind.BOOLEAN,
            False,
        )
    )

    assert _result(record, "excluded_from_structural_authority") is (
        ComparisonResult.MISMATCH
    )
    assert next(
        item.family
        for item in record.discrepancies
        if item.fact_key == "excluded_from_structural_authority"
    ) is DiscrepancyFamily.COMPLETED_VS_INCOMPLETE_DISCREPANCY


def test_partial_answer_is_rejected() -> None:
    complete = _payload()

    with pytest.raises(Slice3VContractError) as captured:
        replace(complete, answers=complete.answers[:-1])

    assert captured.value.state is ValidationFailureState.PARTIAL_ANSWER


def test_wrong_visual_schema_and_question_set_versions_are_rejected() -> None:
    document = visual_answer_payload(_payload())
    document["schema_identity"] = "UNAPPROVED-V2"

    with pytest.raises(Slice3VContractError) as captured:
        visual_answer_payload_from_dict(document)

    assert captured.value.state is ValidationFailureState.VISUAL_ANSWER_SCHEMA_FAILURE


def test_stale_answer_created_before_machine_freeze_is_rejected() -> None:
    visual = _answer(observed_at=FROZEN_AT - timedelta(seconds=1))

    with pytest.raises(Slice3VContractError) as captured:
        compare_machine_to_visual(_machine(), visual, compared_at=COMPARED_AT)

    assert captured.value.state is ValidationFailureState.STALE_ANSWER


def test_missing_chart_is_recorded_without_synthetic_answers() -> None:
    unavailable = accept_visual_answer(
        VisualAnswerPayload(
            visible_symbol="RELIANCE",
            exchange="NSE",
            trading_date=TRADING_DATE,
            timeframe=IntradayTimeframe.FIFTEEN_MINUTES,
            observation_boundary=BOUNDARY,
            chart_observed_at=OBSERVED_AT,
            chart_available=False,
            answers=(),
        )
    )
    record = compare_machine_to_visual(_machine(), unavailable, compared_at=COMPARED_AT)

    assert record.comparison_results[0].result is (
        ComparisonResult.CHART_EVIDENCE_UNAVAILABLE
    )


def test_machine_unavailable_and_superseded_fail_closed() -> None:
    visual = _answer()
    with pytest.raises(Slice3VContractError) as missing:
        compare_machine_to_visual(None, visual, compared_at=COMPARED_AT)
    with pytest.raises(Slice3VContractError) as superseded:
        compare_machine_to_visual(
            _machine(state=MachineEvidenceState.SUPERSEDED),
            visual,
            compared_at=COMPARED_AT,
        )

    assert missing.value.state is ValidationFailureState.MACHINE_EVIDENCE_UNAVAILABLE
    assert superseded.value.state is ValidationFailureState.MACHINE_EVIDENCE_SUPERSEDED


def test_visual_contract_contains_only_visual_fields_and_no_machine_hashes() -> None:
    payload = _payload()
    field_names = {item.name for item in fields(VisualAnswerPayload)}
    document = visual_answer_payload(payload)
    encoded = json.dumps(document, sort_keys=True).lower()

    assert field_names == {
        "visible_symbol",
        "exchange",
        "trading_date",
        "timeframe",
        "observation_boundary",
        "chart_observed_at",
        "chart_available",
        "answers",
        "schema_identity",
        "question_set_identity",
    }
    assert not {
        "machine_evidence_identity",
        "machine_run_identity",
        "canonical_instrument_id",
        "mapping_identity",
        "provider_instrument_token",
        "internal_provenance",
    } & set(document)
    assert "machine_evidence" not in encoded
    assert "access_token" not in encoded
    assert "provider_instrument_token" not in encoded


def test_duplicate_is_idempotent_but_conflicting_answer_is_rejected(tmp_path) -> None:
    store = LocalSlice3VValidationStore(tmp_path / "slice3v")
    first = _answer()
    conflicting = _answer(
        _observation(
            ValidationQuestion.COMPLETED_CANDLE,
            "close",
            VisualPrecision.EXACT,
            FactualValueKind.NUMERIC,
            Decimal("1316.0"),
        )
    )
    store.retain_visual_answer(first)
    store.retain_visual_answer(first)

    with pytest.raises(Slice3VContractError) as captured:
        store.retain_visual_answer(conflicting)

    assert captured.value.state is ValidationFailureState.DUPLICATE_CONFLICTING_ANSWER


def test_restart_reload_and_deterministic_identity_integrity(tmp_path) -> None:
    machine = _machine()
    visual = _answer(
        _observation(
            ValidationQuestion.COMPLETED_CANDLE,
            "close",
            VisualPrecision.EXACT,
            FactualValueKind.NUMERIC,
            Decimal("1316.0"),
        )
    )
    first = compare_machine_to_visual(machine, visual, compared_at=COMPARED_AT)
    second = compare_machine_to_visual(machine, visual, compared_at=COMPARED_AT)
    store = LocalSlice3VValidationStore(tmp_path / "slice3v")
    store.retain_visual_answer(visual)
    store.retain_validation_record(first)

    restarted = LocalSlice3VValidationStore(store.root)
    assert restarted.load_visual_answer(
        visual_evidence_identity=visual.visual_evidence_identity
    ) == visual
    assert restarted.load_validation_record(
        validation_record_identity=first.validation_record_identity
    ) == first
    assert first == second
    assert first.validation_record_identity == second.validation_record_identity
    assert first.integrity_identity == second.integrity_identity


def test_validation_statistics_are_engineering_counts_without_threshold() -> None:
    matching = _compare(
        _observation(
            ValidationQuestion.COMPLETED_CANDLE,
            "close",
            VisualPrecision.EXACT,
            FactualValueKind.NUMERIC,
            Decimal("1316.0"),
        )
    )
    mismatching = _compare(
        _observation(
            ValidationQuestion.COMPLETED_CANDLE,
            "close",
            VisualPrecision.EXACT,
            FactualValueKind.NUMERIC,
            Decimal("1310"),
        )
    )
    statistics = validation_statistics((matching, mismatching))
    counts = dict(statistics.result_counts)

    assert statistics.observations_compared == 6
    assert counts[ComparisonResult.MATCH] == 1
    assert counts[ComparisonResult.MISMATCH] == 1
    assert counts[ComparisonResult.NOT_VISUALLY_VERIFIABLE] == 4
    assert not hasattr(statistics, "production_ready")
    assert not hasattr(statistics, "acceptance_threshold")


def test_mcx_relationship_family_is_a_seam_not_native_comparison() -> None:
    machine = replace(
        _machine(),
        evidence_family=ValidationEvidenceFamily.MCX_REFERENCE_MARKET_RELATIONSHIP,
    )

    with pytest.raises(Slice3VContractError) as captured:
        compare_machine_to_visual(machine, _answer(), compared_at=COMPARED_AT)

    assert captured.value.state is ValidationFailureState.COMPARISON_FAILURE
    assert str(captured.value) == (
        "SLICE3V_REFERENCE_RELATIONSHIP_COMPARISON_NOT_IMPLEMENTED"
    )


def test_contract_has_no_trading_risk_or_promotion_fields() -> None:
    forbidden = {
        "discovery",
        "probable",
        "readiness",
        "entry",
        "stop",
        "target",
        "risk",
        "paper_eligibility",
        "live_eligibility",
        "buy_now",
        "sell_now",
    }
    contract_names = {
        item.name
        for contract in (MachineEvidence, VisualAnswerPayload)
        for item in fields(contract)
    }

    assert contract_names.isdisjoint(forbidden)
