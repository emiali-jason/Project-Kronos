from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path

import pytest

from kronos.application.intraday_native_visual_reconciliation import (
    IntradayNativeVisualReconciliationApplication,
    ReconciliationMemberState,
)
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.native_visual_reconciliation import (
    AnalyticalPromotionState,
    AnalyticalReadinessState,
    ReconciliationError,
    ReconciliationFailure,
    RemainingConditionClass,
    RemainingConditionIdentity,
    ReviewOutcomeState,
    reconciliation_artifact_bytes,
)
from kronos.intraday.native_visual_reconciliation_persistence import (
    IntradayNativeVisualReconciliationStore,
)
from kronos.intraday.probables import ProbableState
from kronos.intraday.review import ReviewFailure
from kronos.intraday.review_answer import AnswerImportState, answer_pack_filename
from tests.unit.intraday.test_historical_semantic import BOUNDARY
from tests.unit.intraday.test_probables import _member, _run, _unavailable
from tests.unit.intraday.test_review import _application, _png
from tests.unit.intraday.test_review_answer import (
    _batch_document,
    _batch_filename,
    _document,
    _write,
)


def _reconciliation(
    root: Path,
    current: list,
    review,
) -> IntradayNativeVisualReconciliationApplication:  # type: ignore[no-untyped-def]
    return IntradayNativeVisualReconciliationApplication(
        current_probables=lambda: current[0],
        review_store=review.store,
        store=IntradayNativeVisualReconciliationStore(
            (root / "reconciliation").resolve()
        ),
    )


def _complete_current_cycle(
    review,
    reconciliation: IntradayNativeVisualReconciliationApplication,
    probable,
    *,
    chart_red: int,
    answers: dict[str, str] | None = None,
    statuses: dict[str, str] | None = None,
):  # type: ignore[no-untyped-def]
    cycle = review.start_review(probable.result_identity)
    chart = review.upload_chart(
        cycle.cycle_identity,
        media_type="image/png",
        payload=_png(chart_red),
    )
    pack, _ = review.create_question_pack(cycle.cycle_identity)
    document = _document(pack)
    by_question = {item["question_id"]: item for item in document["answers"]}
    for question, answer in (answers or {}).items():
        by_question[question]["answer"] = answer
        if question == "Q10" and answer == "MATERIAL_OBSERVATION":
            by_question[question]["why_not_covered_elsewhere"] = (
                "Not represented by Q1-Q9."
            )
    for question, status in (statuses or {}).items():
        item = by_question[question]
        item["observation_status"] = status
        if status == "PARTIAL":
            item.update(
                visible_timeframes=[item["visible_timeframes"][0]],
                status_detail="The governed panel is only partially visible.",
            )
        else:
            item.update(
                answer=None,
                visible_timeframes=[],
                visible_basis=None,
                status_detail="Governed visual evidence unavailable.",
            )
    if statuses:
        document["global_observation_status"] = "PARTIAL"
    imported = review.upload_answer(
        cycle.cycle_identity,
        media_type="application/json",
        payload=json.dumps(document).encode(),
    )
    assert imported.state is AnswerImportState.IMPORTED
    result = reconciliation.reconcile(cycle.cycle_identity)
    assert result.state is ReconciliationMemberState.RECONCILED
    return (
        cycle,
        chart,
        pack,
        imported,
        reconciliation.store.load_run(result.reconciliation_run_identity or ""),
    )


@pytest.mark.parametrize(
    ("direction", "hourly", "fifteen"),
    (
        ("LONG", SemanticDirection.LONG, SemanticDirection.LONG),
        ("SHORT", SemanticDirection.SHORT, SemanticDirection.SHORT),
    ),
)
def test_wo11_clean_long_and_short_traverse_exact_production_contracts(
    tmp_path: Path,
    direction: str,
    hourly: SemanticDirection,
    fifteen: SemanticDirection,
) -> None:
    run = _run((_member("WIPRO", hourly=hourly, fifteen=fifteen),))
    probable = run.results[0]
    current = [run]
    review = _application(tmp_path, current)
    reconciliation = _reconciliation(tmp_path, current, review)

    cycle, chart, pack, imported, result = _complete_current_cycle(
        review,
        reconciliation,
        probable,
        chart_red=10 if direction == "LONG" else 20,
    )
    pointer = review.store.load_visual_evidence_pointer(pack.review_pack_identity)
    assert pointer is not None
    visual = review.store.load_visual_evidence(pointer.visual_evidence_identity)

    assert probable.state is (
        ProbableState.LONG_PROBABLE
        if direction == "LONG"
        else ProbableState.SHORT_PROBABLE
    )
    assert cycle.probables_run_identity == run.run_identity
    assert cycle.probable_result_identity == probable.result_identity
    assert chart.cycle_identity == cycle.cycle_identity
    assert chart.probable_result_identity == probable.result_identity
    assert pack.probables_run_identity == run.run_identity
    assert pack.probable_result_identity == probable.result_identity
    assert pack.review_cycle_identity == cycle.cycle_identity
    assert pack.chart_revision_identity == chart.chart_revision_identity
    assert visual.answer_pack_identity == imported.answer_pack_identity
    assert visual.review_pack_identity == pack.review_pack_identity
    assert result.probables_run_identity == run.run_identity
    assert result.probable_result_identity == probable.result_identity
    assert result.review_cycle_identity == cycle.cycle_identity
    assert result.review_pack_identity == pack.review_pack_identity
    assert result.chart_revision_identity == chart.chart_revision_identity
    assert result.answer_pack_identity == visual.answer_pack_identity
    assert result.visual_evidence_identity == visual.visual_evidence_identity
    assert result.canonical_subject_identity == "WIPRO"
    assert result.inherited_direction == direction
    assert result.review_state.state is ReviewOutcomeState.REVIEW_COMPLETE
    assert result.readiness.state is AnalyticalReadinessState.ANALYTICALLY_READY
    assert result.promotion.state is AnalyticalPromotionState.PROMOTED
    assert not any(
        (
            result.promotion.entry_authority,
            result.promotion.trade_construction_authority,
            result.promotion.risk_authority,
            result.promotion.broker_authority,
        )
    )


@pytest.mark.parametrize(
    ("question", "answer", "review_state", "condition"),
    (
        (
            "Q2",
            "UNCLEAR",
            ReviewOutcomeState.REVIEW_REQUIRED,
            RemainingConditionIdentity.CORE_VISUAL_DIRECTION_AMBIGUOUS,
        ),
        (
            "Q4",
            "MIXED",
            ReviewOutcomeState.REVIEW_REQUIRED,
            RemainingConditionIdentity.CORE_VISUAL_DIRECTION_AMBIGUOUS,
        ),
        (
            "Q4",
            "UNCLEAR",
            ReviewOutcomeState.REVIEW_REQUIRED,
            RemainingConditionIdentity.CORE_VISUAL_DIRECTION_AMBIGUOUS,
        ),
        (
            "Q5",
            "BOTH",
            ReviewOutcomeState.REVIEW_REQUIRED,
            RemainingConditionIdentity.FIFTEEN_MINUTE_OPPOSING_STRUCTURE,
        ),
    ),
)
def test_wo11_extended_review_required_matrix(
    tmp_path: Path,
    question: str,
    answer: str,
    review_state: ReviewOutcomeState,
    condition: RemainingConditionIdentity,
) -> None:
    run = _run((_member("WIPRO"),))
    current = [run]
    review = _application(tmp_path, current)
    reconciliation = _reconciliation(tmp_path, current, review)
    *_, result = _complete_current_cycle(
        review,
        reconciliation,
        run.results[0],
        chart_red=31,
        answers={question: answer},
    )
    assert result.review_state.state is review_state
    assert result.readiness.state is AnalyticalReadinessState.NOT_READY
    assert result.promotion.state is AnalyticalPromotionState.NOT_PROMOTED
    selected = next(
        item for item in result.remaining_conditions if item.condition_identity is condition
    )
    assert selected.classification is RemainingConditionClass.REVIEW_REQUIRED
    assert result.inherited_direction == "LONG"


@pytest.mark.parametrize(
    ("question", "answer"),
    (
        ("Q6", "STALLING"),
        ("Q6", "OPPOSING"),
        ("Q6", "CHOPPY"),
        ("Q6", "MIXED"),
        ("Q6", "UNCLEAR"),
        ("Q7", "PRESENT"),
        ("Q8", "VISIBLY_EXTENDED"),
    ),
)
def test_wo11_supporting_and_informational_answers_never_block(
    tmp_path: Path,
    question: str,
    answer: str,
) -> None:
    run = _run((_member("WIPRO"),))
    current = [run]
    review = _application(tmp_path, current)
    reconciliation = _reconciliation(tmp_path, current, review)
    *_, result = _complete_current_cycle(
        review,
        reconciliation,
        run.results[0],
        chart_red=32,
        answers={question: answer},
    )
    assert result.review_state.state is ReviewOutcomeState.REVIEW_COMPLETE
    assert result.readiness.state is AnalyticalReadinessState.ANALYTICALLY_READY
    assert result.promotion.state is AnalyticalPromotionState.PROMOTED
    assert not any(
        item.classification
        in {RemainingConditionClass.BLOCKING, RemainingConditionClass.REVIEW_REQUIRED}
        for item in result.remaining_conditions
    )


@pytest.mark.parametrize("status", ("PARTIAL", "NOT_VISIBLE", "UNAVAILABLE"))
def test_wo11_secondary_incomplete_is_preserved_but_nonblocking(
    tmp_path: Path,
    status: str,
) -> None:
    run = _run((_member("WIPRO"),))
    current = [run]
    review = _application(tmp_path, current)
    reconciliation = _reconciliation(tmp_path, current, review)
    *_, result = _complete_current_cycle(
        review,
        reconciliation,
        run.results[0],
        chart_red=33,
        statuses={"Q3": status},
    )
    condition = next(
        item
        for item in result.remaining_conditions
        if item.condition_identity
        is RemainingConditionIdentity.SECONDARY_VISUAL_EVIDENCE_INCOMPLETE
    )
    assert condition.classification is RemainingConditionClass.INFORMATIONAL
    assert result.review_state.state is ReviewOutcomeState.REVIEW_COMPLETE
    assert result.readiness.state is AnalyticalReadinessState.ANALYTICALLY_READY
    assert result.promotion.state is AnalyticalPromotionState.PROMOTED


def test_wo11_invalid_visual_evidence_stops_before_trusted_import(
    tmp_path: Path,
) -> None:
    run = _run((_member("WIPRO"),))
    current = [run]
    review = _application(tmp_path, current)
    reconciliation = _reconciliation(tmp_path, current, review)
    cycle = review.start_review(run.results[0].result_identity)
    review.upload_chart(cycle.cycle_identity, media_type="image/png", payload=_png(34))
    pack, _ = review.create_question_pack(cycle.cycle_identity)
    document = _document(pack)
    document["global_observation_status"] = "INVALID"
    for answer in document["answers"]:
        answer.update(
            observation_status="INVALID",
            answer=None,
            visible_timeframes=[],
            visible_basis=None,
            status_detail="The supplied visual evidence is invalid.",
            why_not_covered_elsewhere=None,
        )
    imported = review.upload_answer(
        cycle.cycle_identity,
        media_type="application/json",
        payload=json.dumps(document).encode(),
    )
    assert imported.state is AnswerImportState.INVALID
    assert review.store.load_visual_evidence_pointer(pack.review_pack_identity) is None
    result = reconciliation.reconcile(cycle.cycle_identity)
    assert result.state is ReconciliationMemberState.SKIPPED_VISUAL_EVIDENCE_REQUIRED
    assert reconciliation.snapshot().candidates[0].promotion_state == "NOT_PROMOTED"


@pytest.mark.parametrize(
    ("direction_a", "direction_b"),
    (
        (SemanticDirection.SHORT, SemanticDirection.SHORT),
        (SemanticDirection.SHORT, SemanticDirection.LONG),
    ),
)
def test_wo11_same_subject_multiple_complete_cycles_restore_only_current(
    tmp_path: Path,
    direction_a: SemanticDirection,
    direction_b: SemanticDirection,
) -> None:
    run_a = _run(
        (_member("WIPRO", hourly=direction_a, fifteen=direction_a),)
    )
    current = [run_a]
    review = _application(tmp_path, current)
    reconciliation = _reconciliation(tmp_path, current, review)
    cycle_a, _, pack_a, _, result_a = _complete_current_cycle(
        review,
        reconciliation,
        run_a.results[0],
        chart_red=40,
    )
    bytes_a = reconciliation_artifact_bytes(result_a)

    boundary_b = BOUNDARY + timedelta(minutes=5)
    run_b = _run(
        (
            _member(
                "WIPRO",
                boundary=boundary_b,
                hourly=direction_b,
                fifteen=direction_b,
            ),
        ),
        boundary=boundary_b,
    )
    current[0] = run_b
    cycle_b, _, pack_b, _, result_b = _complete_current_cycle(
        review,
        reconciliation,
        run_b.results[0],
        chart_red=40,
    )
    pointer = reconciliation.store.load_current()
    assert pointer is not None and pointer.probables_run_identity == run_b.run_identity
    assert cycle_a.cycle_identity != cycle_b.cycle_identity
    assert pack_a.review_pack_identity != pack_b.review_pack_identity
    assert result_a.run_identity != result_b.run_identity
    assert result_a.inherited_direction == direction_a.value
    assert result_b.inherited_direction == direction_b.value

    restored = _reconciliation(tmp_path, current, _application(tmp_path, current))
    snapshot = restored.snapshot()
    assert snapshot.current_probables_run_identity == run_b.run_identity
    assert snapshot.candidates[0].review_cycle_identity == cycle_b.cycle_identity
    assert snapshot.candidates[0].reconciliation_run_identity == result_b.run_identity
    assert snapshot.candidates[0].inherited_direction == direction_b.value
    assert reconciliation_artifact_bytes(
        restored.store.load_run(result_a.run_identity)
    ) == bytes_a


def test_wo11_probable_disappearance_never_resurrects_historical_promotion(
    tmp_path: Path,
) -> None:
    run_a = _run((_member("WIPRO"),))
    current = [run_a]
    review = _application(tmp_path, current)
    reconciliation = _reconciliation(tmp_path, current, review)
    *_, result_a = _complete_current_cycle(
        review,
        reconciliation,
        run_a.results[0],
        chart_red=50,
    )
    assert result_a.promotion.state is AnalyticalPromotionState.PROMOTED

    boundary_b = BOUNDARY + timedelta(minutes=5)
    run_b = _run(
        (_member("WIPRO", boundary=boundary_b, narrow=False),),
        boundary=boundary_b,
    )
    current[0] = run_b
    assert run_b.results[0].state is ProbableState.NOT_ADMITTED
    assert review.snapshot().candidates == ()
    assert reconciliation.snapshot().candidates == ()
    restored = _reconciliation(tmp_path, current, _application(tmp_path, current))
    assert restored.snapshot().candidates == ()
    assert restored.store.load_run(result_a.run_identity).promotion.state is (
        AnalyticalPromotionState.PROMOTED
    )


def test_wo11_new_chart_requires_new_answer_and_reconciliation(
    tmp_path: Path,
) -> None:
    run = _run((_member("WIPRO"),))
    current = [run]
    review = _application(tmp_path, current)
    reconciliation = _reconciliation(tmp_path, current, review)
    cycle, chart_a, pack_a, _, result_a = _complete_current_cycle(
        review,
        reconciliation,
        run.results[0],
        chart_red=60,
    )
    document_a = _document(pack_a)

    chart_b = review.upload_chart(
        cycle.cycle_identity,
        media_type="image/png",
        payload=_png(61),
    )
    pack_b, _ = review.create_question_pack(cycle.cycle_identity)
    assert chart_b.revision_ordinal == 2
    assert pack_b.review_pack_identity != pack_a.review_pack_identity
    assert reconciliation.snapshot().candidates[0].reconciliation_run_identity is None
    rejected = review.upload_answer(
        cycle.cycle_identity,
        media_type="application/json",
        payload=json.dumps(document_a).encode(),
    )
    assert rejected.state is AnswerImportState.IDENTITY_MISMATCH
    assert review.store.load_visual_evidence_pointer(pack_b.review_pack_identity) is None

    imported_b = review.upload_answer(
        cycle.cycle_identity,
        media_type="application/json",
        payload=json.dumps(_document(pack_b)).encode(),
    )
    assert imported_b.state is AnswerImportState.IMPORTED
    result_b = reconciliation.reconcile(cycle.cycle_identity)
    assert result_b.state is ReconciliationMemberState.RECONCILED
    assert result_b.reconciliation_run_identity != result_a.run_identity
    assert reconciliation.store.load_run(result_a.run_identity).run_identity == result_a.run_identity


def test_wo11_three_member_answer_and_reconciliation_partial_failures_are_isolated(
    tmp_path: Path,
) -> None:
    run = _run(tuple(_member(subject) for subject in ("WIPRO", "LICI", "RELIANCE")))
    current = [run]
    review = _application(tmp_path, current)
    packs = {}
    cycles = {}
    for index, probable in enumerate(run.results, start=1):
        cycle = review.start_review(probable.result_identity)
        review.upload_chart(cycle.cycle_identity, media_type="image/png", payload=_png(70 + index))
        pack, _ = review.create_question_pack(cycle.cycle_identity)
        packs[probable.canonical_subject_identity] = pack
        cycles[probable.canonical_subject_identity] = cycle

    review_batch, combined = _batch_document(review, packs)
    candidates = [_document(packs[subject]) for subject in ("WIPRO", "RELIANCE")]
    invalid = _document(packs["LICI"])
    invalid["observed_visible_subject_identity"] = "TCS"
    candidates.append(invalid)
    combined["candidates"] = candidates
    batch = review.import_all_answers(
        media_type="application/json", payload=json.dumps(combined).encode(),
        source_filename=_batch_filename(review, review_batch),
    )
    assert batch.count(AnswerImportState.IMPORTED) == 2
    assert batch.count(AnswerImportState.IDENTITY_MISMATCH) == 1
    assert review.snapshot().candidates[0].canonical_subject_identity == "LICI"

    valid_lici = _document(packs["LICI"])
    target = tmp_path / "answers" / answer_pack_filename(packs["LICI"])
    target.write_text(json.dumps(valid_lici), encoding="utf-8")
    assert review.import_answer(cycles["LICI"].cycle_identity).state is AnswerImportState.IMPORTED
    lici_pointer = review.store.load_visual_evidence_pointer(packs["LICI"].review_pack_identity)
    assert lici_pointer is not None
    lici_artifact = (
        review.store.root
        / "visual-evidence"
        / f"{lici_pointer.visual_evidence_identity}.json"
    )
    lici_artifact.write_bytes(b"tampered-controlled-fixture")

    reconciliation = _reconciliation(tmp_path, current, review)
    reconciliation_batch = reconciliation.reconcile_all_ready()
    assert reconciliation_batch.count(ReconciliationMemberState.RECONCILED) == 2
    assert reconciliation_batch.count(ReconciliationMemberState.FAILED) == 1
    assert {
        item.canonical_subject_identity
        for item in reconciliation_batch.members
        if item.state is ReconciliationMemberState.RECONCILED
    } == {"RELIANCE", "WIPRO"}


def test_wo11_equity_mcx_provider_failure_and_roll_lineage_are_isolated(
    tmp_path: Path,
) -> None:
    goldm_a = replace(
        _member("GOLDM"),
        source_member_identity="INTRADAY-DISCOVERY-RESULT:GOLDM:ACTIVE-BINDING-X",
        provenance=("SYNTHETIC-WO-11-QUALIFICATION", "ACTIVE-BINDING-X"),
    )
    run_a = _run(
        (_member("WIPRO"), goldm_a),
        (_unavailable("LICI"),),
    )
    current = [run_a]
    review = _application(tmp_path, current)
    reconciliation = _reconciliation(tmp_path, current, review)
    results_a = {}
    for index, probable in enumerate(
        (
            item
            for item in run_a.results
            if item.state in {ProbableState.LONG_PROBABLE, ProbableState.SHORT_PROBABLE}
        ),
        start=1,
    ):
        results_a[probable.canonical_subject_identity] = _complete_current_cycle(
            review,
            reconciliation,
            probable,
            chart_red=80 + index,
        )
    assert set(results_a) == {"GOLDM", "WIPRO"}
    assert next(item for item in run_a.results if item.canonical_subject_identity == "LICI").state is ProbableState.UNAVAILABLE
    goldm_pack_a = results_a["GOLDM"][2]
    assert goldm_pack_a.expected_canonical_subject_identity == "GOLDM"
    assert goldm_pack_a.discovery_member_identity.endswith("ACTIVE-BINDING-X")

    boundary_b = BOUNDARY + timedelta(minutes=5)
    goldm_b = replace(
        _member("GOLDM", boundary=boundary_b),
        source_member_identity="INTRADAY-DISCOVERY-RESULT:GOLDM:ACTIVE-BINDING-Y",
        provenance=("SYNTHETIC-WO-11-QUALIFICATION", "ACTIVE-BINDING-Y"),
    )
    run_b = _run((goldm_b,), boundary=boundary_b)
    current[0] = run_b
    cycle_b, _, pack_b, _, result_b = _complete_current_cycle(
        review,
        reconciliation,
        run_b.results[0],
        chart_red=90,
    )
    assert cycle_b.canonical_subject_identity == "GOLDM"
    assert pack_b.expected_canonical_subject_identity == "GOLDM"
    assert pack_b.discovery_member_identity.endswith("ACTIVE-BINDING-Y")
    assert pack_b.review_pack_identity != goldm_pack_a.review_pack_identity
    assert result_b.canonical_subject_identity == "GOLDM"
    assert results_a["GOLDM"][4].run_identity != result_b.run_identity


def test_wo11_missing_current_reconciliation_never_falls_back_to_history(
    tmp_path: Path,
) -> None:
    run_a = _run((_member("WIPRO"),))
    current = [run_a]
    review = _application(tmp_path, current)
    reconciliation = _reconciliation(tmp_path, current, review)
    *_, result_a = _complete_current_cycle(
        review,
        reconciliation,
        run_a.results[0],
        chart_red=100,
    )
    boundary_b = BOUNDARY + timedelta(minutes=5)
    run_b = _run((_member("WIPRO", boundary=boundary_b),), boundary=boundary_b)
    current[0] = run_b
    *_, result_b = _complete_current_cycle(
        review,
        reconciliation,
        run_b.results[0],
        chart_red=101,
    )
    missing = reconciliation.store.root / "runs" / f"{result_b.run_identity}.json"
    missing.unlink()
    restored = _reconciliation(tmp_path, current, _application(tmp_path, current))
    with pytest.raises(ReconciliationError, match=ReconciliationFailure.ARTIFACT_UNAVAILABLE.value):
        restored.snapshot()
    assert restored.store.load_run(result_a.run_identity).run_identity == result_a.run_identity
