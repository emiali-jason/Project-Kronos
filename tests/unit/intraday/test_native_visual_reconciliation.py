from __future__ import annotations

import json
from pathlib import Path

import pytest

from kronos.application.intraday_native_visual_reconciliation import (
    IntradayNativeVisualReconciliationApplication,
    ReconciliationMemberState,
)
from kronos.intraday.native_visual_reconciliation import (
    AnalyticalPromotionState,
    AnalyticalReadinessState,
    RemainingConditionClass,
    RemainingConditionIdentity,
    ReconciliationError,
    ReconciliationFailure,
    ReviewOutcomeState,
    create_v1_reconciliation_policy,
    reconcile_native_visual_evidence,
    reconciliation_artifact_bytes,
)
from kronos.intraday.native_visual_reconciliation_persistence import (
    IntradayNativeVisualReconciliationStore,
)
from kronos.intraday.historical_semantic import SemanticDirection
from tests.unit.intraday.test_probables import _member, _run
from tests.unit.intraday.test_review import _application, _png
from tests.unit.intraday.test_review_answer import _document


def _prepared(tmp_path: Path, *, subject: str = "WIPRO", answers: dict[str, str] | None = None,
              statuses: dict[str, str] | None = None):  # type: ignore[no-untyped-def]
    run = _run((_member(subject),))
    current = [run]
    review = _application(tmp_path, current)
    cycle = review.start_review(run.results[0].result_identity)
    review.upload_chart(cycle.cycle_identity, media_type="image/png", payload=_png(12))
    pack, _ = review.create_question_pack(cycle.cycle_identity)
    document = _document(pack)
    by_question = {item["question_id"]: item for item in document["answers"]}
    for question, answer in (answers or {}).items():
        by_question[question]["answer"] = answer
        if question == "Q10" and answer == "MATERIAL_OBSERVATION":
            by_question[question]["why_not_covered_elsewhere"] = "Not represented by Q1-Q9."
    for question, status in (statuses or {}).items():
        item = by_question[question]
        item["observation_status"] = status
        if status == "PARTIAL":
            item["status_detail"] = "The governed panel is only partially visible."
        if status in {"NOT_VISIBLE", "NOT_APPLICABLE", "UNAVAILABLE"}:
            item.update(answer=None, visible_timeframes=[], visible_basis=None, status_detail="Governed visual evidence unavailable.")
    if any(item["observation_status"] != "OBSERVED" for item in document["answers"]):
        document["global_observation_status"] = "PARTIAL"
    imported = review.upload_answer(
        cycle.cycle_identity,
        media_type="application/json",
        payload=json.dumps(document).encode(),
    )
    assert imported.visual_evidence_identity is not None
    reconciliation = IntradayNativeVisualReconciliationApplication(
        current_probables=lambda: current[0],
        review_store=review.store,
        store=IntradayNativeVisualReconciliationStore((tmp_path / "reconciliation").resolve()),
    )
    return current, review, reconciliation, cycle, pack


def test_frozen_policy_identity_checksum_and_no_score_or_trading_authority() -> None:
    first = create_v1_reconciliation_policy()
    second = create_v1_reconciliation_policy()
    assert first == second
    assert first.policy_identity == "KRONOS-INTRADAY-NATIVE-VISUAL-RECONCILIATION-POLICY-V1"
    assert first.policy_version == "1.0.0"
    assert first.policy_family == "POLICY_B_CORE_STRUCTURE"
    encoded = reconciliation_artifact_bytes(first).decode().lower()
    for prohibited in ("score", "weight", "rank", "quota", "majority"):
        assert prohibited not in encoded
    assert "broker" not in encoded and "entry" in encoded  # authority exclusion is explicit


def test_supportive_core_is_ready_promoted_and_direction_is_inherited(tmp_path: Path) -> None:
    _, _, app, cycle, _ = _prepared(tmp_path)
    result = app.reconcile(cycle.cycle_identity)
    assert result.state is ReconciliationMemberState.RECONCILED
    run = app.store.load_run(result.reconciliation_run_identity)
    assert run.review_state.state is ReviewOutcomeState.REVIEW_COMPLETE
    assert run.readiness.state is AnalyticalReadinessState.ANALYTICALLY_READY
    assert run.promotion.state is AnalyticalPromotionState.PROMOTED
    assert run.inherited_direction == "LONG"
    assert not run.remaining_conditions
    assert not any((run.promotion.entry_authority, run.promotion.trade_construction_authority,
                    run.promotion.risk_authority, run.promotion.broker_authority))


@pytest.mark.parametrize(
    ("question", "answer", "review", "condition", "classification"),
    (
        ("Q2", "OPPOSING", ReviewOutcomeState.REVIEW_COMPLETE, RemainingConditionIdentity.CORE_VISUAL_1H_NOT_SUPPORTIVE, RemainingConditionClass.BLOCKING),
        ("Q4", "OPPOSING", ReviewOutcomeState.REVIEW_COMPLETE, RemainingConditionIdentity.CORE_VISUAL_15M_NOT_SUPPORTIVE, RemainingConditionClass.BLOCKING),
        ("Q2", "MIXED", ReviewOutcomeState.REVIEW_REQUIRED, RemainingConditionIdentity.CORE_VISUAL_DIRECTION_AMBIGUOUS, RemainingConditionClass.REVIEW_REQUIRED),
        ("Q3", "MATERIAL_OVERLAP", ReviewOutcomeState.REVIEW_COMPLETE, RemainingConditionIdentity.ONE_HOUR_MATERIAL_OVERLAP, RemainingConditionClass.ADVERSE_NON_BLOCKING),
        ("Q5", "STALLING_OR_FAILED_CONTINUATION", ReviewOutcomeState.REVIEW_COMPLETE, RemainingConditionIdentity.FIFTEEN_MINUTE_CONTINUATION_STALLED, RemainingConditionClass.ADVERSE_NON_BLOCKING),
        ("Q5", "OPPOSING_STRUCTURE_VISIBLE", ReviewOutcomeState.REVIEW_REQUIRED, RemainingConditionIdentity.FIFTEEN_MINUTE_OPPOSING_STRUCTURE, RemainingConditionClass.REVIEW_REQUIRED),
        ("Q9", "REJECTION_AGAINST_DIRECTION", ReviewOutcomeState.REVIEW_REQUIRED, RemainingConditionIdentity.LOCAL_REJECTION_AGAINST_DIRECTION, RemainingConditionClass.REVIEW_REQUIRED),
        ("Q10", "MATERIAL_OBSERVATION", ReviewOutcomeState.REVIEW_REQUIRED, RemainingConditionIdentity.MATERIAL_VISUAL_OBSERVATION_REQUIRES_REVIEW, RemainingConditionClass.REVIEW_REQUIRED),
    ),
)
def test_exact_consequence_matrix(
    tmp_path: Path, question: str, answer: str, review: ReviewOutcomeState,
    condition: RemainingConditionIdentity, classification: RemainingConditionClass,
) -> None:
    _, _, app, cycle, _ = _prepared(tmp_path, answers={question: answer})
    result = app.reconcile(cycle.cycle_identity)
    run = app.store.load_run(result.reconciliation_run_identity)
    assert run.review_state.state is review
    selected = next(item for item in run.remaining_conditions if item.condition_identity is condition)
    assert selected.classification is classification and selected.source_question_id == question
    ready = review is ReviewOutcomeState.REVIEW_COMPLETE and question in {"Q3", "Q5"}
    assert (run.readiness.state is AnalyticalReadinessState.ANALYTICALLY_READY) is ready
    assert (run.promotion.state is AnalyticalPromotionState.PROMOTED) is ready


@pytest.mark.parametrize("question", ("Q2", "Q4"))
@pytest.mark.parametrize("status", ("PARTIAL", "NOT_VISIBLE", "UNAVAILABLE", "NOT_APPLICABLE"))
def test_core_incomplete_status_fails_closed(tmp_path: Path, question: str, status: str) -> None:
    _, _, app, cycle, _ = _prepared(tmp_path, statuses={question: status})
    result = app.reconcile(cycle.cycle_identity)
    run = app.store.load_run(result.reconciliation_run_identity)
    assert run.review_state.state is ReviewOutcomeState.REVIEW_INCOMPLETE
    assert run.readiness.state is AnalyticalReadinessState.NOT_READY
    assert run.promotion.state is AnalyticalPromotionState.NOT_PROMOTED
    assert any(item.condition_identity is RemainingConditionIdentity.CORE_VISUAL_EVIDENCE_INCOMPLETE for item in run.remaining_conditions)


def test_noncore_unavailability_is_informational_and_does_not_block(tmp_path: Path) -> None:
    _, _, app, cycle, _ = _prepared(tmp_path, statuses={"Q1": "UNAVAILABLE", "Q7": "NOT_VISIBLE"})
    result = app.reconcile(cycle.cycle_identity)
    run = app.store.load_run(result.reconciliation_run_identity)
    assert run.review_state.state is ReviewOutcomeState.REVIEW_COMPLETE
    assert run.readiness.state is AnalyticalReadinessState.ANALYTICALLY_READY
    assert all(item.classification is RemainingConditionClass.INFORMATIONAL for item in run.remaining_conditions)


def test_idempotency_persistence_restart_and_explicit_current_pointer(tmp_path: Path) -> None:
    current, review, app, cycle, _ = _prepared(tmp_path)
    first = app.reconcile(cycle.cycle_identity)
    second = app.reconcile(cycle.cycle_identity)
    assert second.state is ReconciliationMemberState.ALREADY_RECONCILED
    assert first.reconciliation_run_identity == second.reconciliation_run_identity
    first_bytes = (app.store.root / "runs" / f"{first.reconciliation_run_identity}.json").read_bytes()
    restored = IntradayNativeVisualReconciliationApplication(
        current_probables=lambda: current[0],
        review_store=review.store,
        store=IntradayNativeVisualReconciliationStore(app.store.root),
    )
    snapshot = restored.snapshot()
    assert snapshot.candidates[0].reconciliation_run_identity == first.reconciliation_run_identity
    assert snapshot.provider_calls == snapshot.discovery_operations == snapshot.probables_operations == snapshot.chart_analyst_calls == 0
    assert (app.store.root / "runs" / f"{first.reconciliation_run_identity}.json").read_bytes() == first_bytes


def test_tamper_missing_and_candidate_isolated_batch_fail_closed(tmp_path: Path) -> None:
    current, review, app, cycle, _ = _prepared(tmp_path)
    result = app.reconcile(cycle.cycle_identity)
    retained = app.store.load_run(result.reconciliation_run_identity)
    path = app.store.root / "runs" / f"{result.reconciliation_run_identity}.json"
    path.write_bytes(path.read_bytes().replace(b"ANALYTICALLY_READY", b"ANALYTICALLY_FAKE", 1))
    with pytest.raises(ReconciliationError, match=ReconciliationFailure.PERSISTENCE_CONFLICT.value):
        app.store.retain_run(retained)
    with pytest.raises(Exception, match="INTRADAY_RECONCILIATION_INTEGRITY_INVALID"):
        app.snapshot()

    other_root = tmp_path / "batch"
    run = _run((_member("WIPRO"), _member("LICI")))
    current[0] = run
    review2 = _application(other_root, current)
    wipro = next(item for item in run.results if item.canonical_subject_identity == "WIPRO")
    cycle2 = review2.start_review(wipro.result_identity)
    review2.upload_chart(cycle2.cycle_identity, media_type="image/png", payload=_png(1))
    pack2, _ = review2.create_question_pack(cycle2.cycle_identity)
    review2.upload_answer(cycle2.cycle_identity, media_type="application/json", payload=json.dumps(_document(pack2)).encode())
    app2 = IntradayNativeVisualReconciliationApplication(
        current_probables=lambda: current[0], review_store=review2.store,
        store=IntradayNativeVisualReconciliationStore((other_root / "reconciliation").resolve()),
    )
    batch = app2.reconcile_all_ready()
    assert tuple(item.canonical_subject_identity for item in batch.members) == ("LICI", "WIPRO")
    assert batch.count(ReconciliationMemberState.RECONCILED) == 1
    assert batch.count(ReconciliationMemberState.SKIPPED_VISUAL_EVIDENCE_REQUIRED) == 1


def test_wrong_native_run_and_wrong_visual_cycle_are_rejected(tmp_path: Path) -> None:
    current, review, _, cycle, pack = _prepared(tmp_path / "first")
    pointer = review.store.load_visual_evidence_pointer(pack.review_pack_identity)
    assert pointer is not None
    evidence = review.store.load_visual_evidence(pointer.visual_evidence_identity)
    other_run = _run((_member("LICI"),))
    with pytest.raises(ReconciliationError, match=ReconciliationFailure.EVIDENCE_INVALID.value):
        reconcile_native_visual_evidence(
            policy=create_v1_reconciliation_policy(), probables_run=other_run,
            probable=other_run.results[0], cycle=cycle, question_pack=pack,
            visual_evidence=evidence,
        )

    _, other_review, _, _, other_pack = _prepared(tmp_path / "second", subject="LICI")
    other_pointer = other_review.store.load_visual_evidence_pointer(other_pack.review_pack_identity)
    assert other_pointer is not None
    other_evidence = other_review.store.load_visual_evidence(other_pointer.visual_evidence_identity)
    with pytest.raises(ReconciliationError, match=ReconciliationFailure.EVIDENCE_INVALID.value):
        reconcile_native_visual_evidence(
            policy=create_v1_reconciliation_policy(), probables_run=current[0],
            probable=current[0].results[0], cycle=cycle, question_pack=pack,
            visual_evidence=other_evidence,
        )


def test_batch_failure_is_candidate_isolated(tmp_path: Path) -> None:
    run = _run((_member("WIPRO"), _member("LICI")))
    current = [run]
    review = _application(tmp_path, current)
    packs = {}
    for index, probable in enumerate(run.results, start=1):
        cycle = review.start_review(probable.result_identity)
        review.upload_chart(cycle.cycle_identity, media_type="image/png", payload=_png(index))
        pack, _ = review.create_question_pack(cycle.cycle_identity)
        review.upload_answer(
            cycle.cycle_identity, media_type="application/json",
            payload=json.dumps(_document(pack)).encode(),
        )
        packs[probable.canonical_subject_identity] = pack
    bad_pointer = review.store.load_visual_evidence_pointer(packs["LICI"].review_pack_identity)
    assert bad_pointer is not None
    bad_path = review.store.root / "visual-evidence" / f"{bad_pointer.visual_evidence_identity}.json"
    bad_path.write_bytes(b"tampered")
    app = IntradayNativeVisualReconciliationApplication(
        current_probables=lambda: current[0], review_store=review.store,
        store=IntradayNativeVisualReconciliationStore((tmp_path / "reconciliation").resolve()),
    )
    batch = app.reconcile_all_ready()
    assert batch.count(ReconciliationMemberState.FAILED) == 1
    assert batch.count(ReconciliationMemberState.RECONCILED) == 1
    successful = next(item for item in batch.members if item.state is ReconciliationMemberState.RECONCILED)
    assert successful.canonical_subject_identity == "WIPRO"


def test_new_chart_answer_creates_new_run_and_preserves_prior_history(tmp_path: Path) -> None:
    _, review, app, cycle, _ = _prepared(tmp_path)
    first = app.reconcile(cycle.cycle_identity)
    first_path = app.store.root / "runs" / f"{first.reconciliation_run_identity}.json"
    first_bytes = first_path.read_bytes()

    review.upload_chart(cycle.cycle_identity, media_type="image/png", payload=_png(22))
    pack, _ = review.create_question_pack(cycle.cycle_identity)
    document = _document(pack)
    document["answers"][2]["answer"] = "MATERIAL_OVERLAP"
    review.upload_answer(
        cycle.cycle_identity, media_type="application/json", payload=json.dumps(document).encode()
    )
    assert app.snapshot().candidates[0].reconciliation_run_identity is None
    second = app.reconcile(cycle.cycle_identity)
    assert second.reconciliation_run_identity != first.reconciliation_run_identity
    assert first_path.read_bytes() == first_bytes
    assert app.store.load_run(first.reconciliation_run_identity).review_state.state is ReviewOutcomeState.REVIEW_COMPLETE


def test_new_probables_direction_cycle_cannot_reuse_historical_result(tmp_path: Path) -> None:
    current, review, app, cycle, _ = _prepared(tmp_path)
    first = app.reconcile(cycle.cycle_identity)
    run_b = _run((_member(
        "WIPRO", hourly=SemanticDirection.SHORT, fifteen=SemanticDirection.SHORT
    ),))
    current[0] = run_b
    assert app.snapshot().candidates[0].reconciliation_run_identity is None
    assert app.snapshot().candidates[0].inherited_direction == "SHORT"
    assert app.store.load_run(first.reconciliation_run_identity).inherited_direction == "LONG"
    cycle_b = review.start_review(run_b.results[0].result_identity)
    assert cycle_b.cycle_identity != cycle.cycle_identity


def test_missing_visual_artifact_policy_tamper_and_pointer_tamper_fail_closed(tmp_path: Path) -> None:
    _, review, app, cycle, _ = _prepared(tmp_path)
    result = app.reconcile(cycle.cycle_identity)
    visual_identity = app.store.load_run(result.reconciliation_run_identity).visual_evidence_identity
    visual_path = review.store.root / "visual-evidence" / f"{visual_identity}.json"
    visual_path.unlink()
    with pytest.raises(Exception):
        app.snapshot()

    other = tmp_path / "other"
    _, _, app2, cycle2, _ = _prepared(other)
    app2.reconcile(cycle2.cycle_identity)
    policy_path = next((app2.store.root / "policies").glob("*.json"))
    policy_path.write_bytes(policy_path.read_bytes().replace(b"POLICY_B_CORE_STRUCTURE", b"POLICY_X_CORE_STRUCTURE", 1))
    policy_identity = create_v1_reconciliation_policy().publication_identity
    with pytest.raises(Exception, match="INTRADAY_RECONCILIATION_INTEGRITY_INVALID"):
        app2.store.load_policy(policy_identity)

    pointer_path = app2.store.root / "current" / "CURRENT-RECONCILIATION-POINTER.json"
    pointer_path.write_bytes(pointer_path.read_bytes().replace(b"WIPRO", b"TAMPER", 1))
    with pytest.raises(Exception, match="INTRADAY_RECONCILIATION_INTEGRITY_INVALID"):
        app2.snapshot()
