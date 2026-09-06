from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from kronos.application.intraday_review_v2 import (
    IntradayReviewV2CandidateSnapshot,
    IntradayReviewV2Snapshot,
)
from kronos.application.intraday_statistics import (
    CANDIDATE_COLUMNS,
    STAGE_COLUMNS,
    IntradayStatisticsError,
    project_intraday_statistics,
)
from kronos.intraday.operational_readiness import (
    WO_B_CONTRACT_VERSION,
    WO_B_PRODUCT_IDENTITY,
)
from kronos.intraday.probables_v2 import evaluate_probables_v2_run
from tests.unit.intraday.test_probables_v2 import (
    PROVENANCE,
    SOURCE_RUN,
    _opening_inputs,
    _run,
)


STAGES = (
    "DOMAIN_001_INSTRUMENT",
    "DOMAIN_008_SESSION",
    "PROBABLES",
    "ANALYTICAL_PROMOTION",
    "WO13_TRADE_PLAN",
    "WO14_RISK_OBSERVATION",
    "WO15_TIMING_HANDOFF",
    "WO16_SPONSOR_LIFECYCLE",
    "WO17_POSITION_MONITORING",
)


def _current():  # type: ignore[no-untyped-def]
    run = _run(_opening_inputs()[-1])
    result = run.results[0]
    candidate = IntradayReviewV2CandidateSnapshot(
        sponsor_label="RELIANCE",
        canonical_subject_identity=result.canonical_subject_identity,
        direction=result.direction.value,
        methodology_identity=result.methodology_identity,
        methodology_version=result.methodology_version,
        methodology_publication_identity=result.methodology_publication_identity,
        analysis_boundary=run.analysis_boundary,
        phase=result.phase.value,
        review_state="REVIEW_CYCLE_EXISTS",
        chart_state="CHART_READY",
        review_pack_state="READY",
        question_pack_state="CREATED",
        answer_state="NOT_IMPORTED",
        cycle_identity="INTRADAY-REVIEW-CYCLE-CURRENT",
        probable_result_identity=result.result_identity,
        nifty_applicability="APPLICABLE",
        mcx_commissioning_state=None,
        chart_revision_identity="INTRADAY-CHART-REVISION-CURRENT",
        chart_revision_ordinal=2,
        chart_payload_sha256="a" * 64,
        question_transport_identity="INTRADAY-QUESTION-TRANSPORT-CURRENT",
        question_filename="KRONOS_CURRENT_QUESTIONS.pdf",
        expected_answer_filename="KRONOS_CURRENT_ANSWERS.json",
    )
    review = IntradayReviewV2Snapshot(
        probables_run_identity=run.run_identity,
        current_pointer_identity="CURRENT-INTRADAY-REVIEW-POINTER",
        candidates=(candidate,),
    )
    items = []
    references = []
    for index, boundary in enumerate(STAGES):
        classification = (
            "AVAILABLE" if index < 2 else "TERMINAL" if index == 2 else "NOT_REACHED"
        )
        basis = (
            "CURRENT_VALID_SOURCE"
            if index < 2
            else "SOURCE_TERMINAL"
            if index == 2
            else "EXPECTED_DOWNSTREAM_ABSENCE"
        )
        reference_identity = f"WO-B-SOURCE-{boundary}" if index < 3 else None
        items.append({
            "source_boundary": boundary,
            "source_state": (
                "AVAILABLE" if index < 2 else "LONG_PROBABLE" if index == 2 else "NOT_REACHED"
            ),
            "source_reason": None,
            "classification": classification,
            "classification_basis": basis,
            "next_governed_stage": "ANALYTICAL_PROMOTION" if index >= 2 else None,
            "source_reference_identity": reference_identity,
        })
        if reference_identity is not None:
            references.append({
                "source_boundary": boundary,
                "artifact_identity": f"ARTIFACT-{boundary}",
                "schema": f"SCHEMA-{boundary} / 1.0.0",
                "policy": f"POLICY-{boundary} / 1.0.0",
                "observed_at": run.analysis_boundary.isoformat(),
                "current": True,
                "superseded": False,
            })
    readiness = {
        "product_identity": WO_B_PRODUCT_IDENTITY,
        "product_version": WO_B_CONTRACT_VERSION,
        "reviews": ({
            "review_snapshot_identity": "INTRADAY-WO-B-REVIEW-CURRENT",
            "candidate_identity": result.result_identity,
            "analysis_run_identity": run.run_identity,
            "canonical_subject_identity": result.canonical_subject_identity,
            "market_family": "NSE_EQUITY",
            "direction": result.direction.value,
            "active_contract_identity": None,
            "review_boundary": (run.analysis_boundary + timedelta(minutes=20)).isoformat(),
            "next_governed_stage": "ANALYTICAL_PROMOTION",
            "items": tuple(items),
            "source_references": tuple(references),
        },),
    }
    return run, review, readiness


def _projection():  # type: ignore[no-untyped-def]
    run, review, readiness = _current()
    return project_intraday_statistics(
        run, review, readiness, generated_at=run.analysis_boundary + timedelta(hours=1)
    )


def _candidate_values(projection):  # type: ignore[no-untyped-def]
    return dict(zip(CANDIDATE_COLUMNS, projection.candidates[0].values, strict=True))


def test_exact_current_lineage_projects_only_governed_counts_and_rows() -> None:
    projection = _projection()
    metrics = {item.metric: item.value for item in projection.metrics}

    assert metrics == {
        "Starting Population": 1,
        "Evaluable Population": 1,
        "Unavailable Population": 0,
        "Admitted Probables": 1,
        "LONG": 1,
        "SHORT": 0,
        "Not Admitted": 0,
        "Conflicting": 0,
        "Review Cycles": 1,
        "Charts Ready": 1,
        "Review Packs Ready": 1,
        "Question Packs Created": 1,
        "Question Packs Transport Ready": 0,
        "Answers Imported": 0,
        "Answers Not Imported": 1,
        "Visual Evidence Ready": 0,
        "Visual Evidence Absent": 1,
        "WO-B AVAILABLE": 2,
        "WO-B TERMINAL": 1,
        "WO-B NOT_REACHED": 6,
        "WO-B WAITING": 0,
        "WO-B BLOCKED": 0,
        "WO-B UNAVAILABLE": 0,
    }
    assert len(projection.candidates) == 1
    assert len(projection.stages) == 9
    assert [row.values[7] for row in projection.stages] == list(STAGES)
    values = _candidate_values(projection)
    assert values["Probables Run Identity"] == projection.probables_run_identity
    assert values["Review Cycle Identity"] == "INTRADAY-REVIEW-CYCLE-CURRENT"
    assert values["Active Contract Identity"] == "NOT_APPLICABLE"
    assert not set(CANDIDATE_COLUMNS) & {
        "P&L", "Realised R", "Win Rate", "Expectancy", "Holding Duration"
    }


def test_absent_review_and_readiness_remain_unavailable_without_wo10_dependency() -> None:
    run, _, _ = _current()
    projection = project_intraday_statistics(
        run,
        IntradayReviewV2Snapshot(None, None, ()),
        {"product_identity": WO_B_PRODUCT_IDENTITY, "reviews": ()},
        generated_at=run.analysis_boundary,
    )
    values = _candidate_values(projection)
    metrics = {item.metric: (item.value, item.state) for item in projection.metrics}

    assert values["Review State"] == "UNAVAILABLE"
    assert values["Chart State"] == "UNAVAILABLE"
    assert values["Answer State"] == "UNAVAILABLE"
    assert all(row.values[8] == "UNAVAILABLE" for row in projection.stages)
    assert metrics["Review Cycles"] == ("UNAVAILABLE", "UNAVAILABLE")
    assert metrics["WO-B AVAILABLE"] == ("NOT_REACHED", "NOT_REACHED")


def test_foreign_review_and_historical_wo_b_are_rejected() -> None:
    run, review, readiness = _current()
    with pytest.raises(
        IntradayStatisticsError,
        match="^INTRADAY_STATISTICS_HISTORICAL_REVIEW_REJECTED$",
    ):
        project_intraday_statistics(
            run,
            replace(review, probables_run_identity="HISTORICAL-PROBABLES-RUN"),
            readiness,
            generated_at=run.analysis_boundary,
        )

    foreign = dict(readiness)
    foreign_review = dict(readiness["reviews"][0])
    foreign_review["analysis_run_identity"] = "HISTORICAL-PROBABLES-RUN"
    foreign["reviews"] = (foreign_review,)
    with pytest.raises(
        IntradayStatisticsError,
        match="^INTRADAY_STATISTICS_WO_B_LINEAGE_INVALID$",
    ):
        project_intraday_statistics(
            run, review, foreign, generated_at=run.analysis_boundary
        )


def test_duplicate_stage_fails_closed() -> None:
    run, review, readiness = _current()
    duplicate = dict(readiness)
    review_document = dict(readiness["reviews"][0])
    review_document["items"] += (review_document["items"][0],)
    duplicate["reviews"] = (review_document,)
    with pytest.raises(
        IntradayStatisticsError,
        match="^INTRADAY_STATISTICS_DUPLICATE_STAGE$",
    ):
        project_intraday_statistics(
            run, review, duplicate, generated_at=run.analysis_boundary
        )


def test_missing_wo_b_boundary_is_exported_and_counted_as_unavailable() -> None:
    run, review, readiness = _current()
    partial = dict(readiness)
    review_document = dict(readiness["reviews"][0])
    review_document["items"] = review_document["items"][:-1]
    partial["reviews"] = (review_document,)
    projection = project_intraday_statistics(
        run, review, partial, generated_at=run.analysis_boundary
    )
    missing = dict(zip(STAGE_COLUMNS, projection.stages[-1].values, strict=True))
    metrics = {item.metric: item.value for item in projection.metrics}
    assert missing["Source Boundary"] == "WO17_POSITION_MONITORING"
    assert missing["Classification"] == "UNAVAILABLE"
    assert missing["Source Reason"] == "UNAVAILABLE"
    assert metrics["WO-B UNAVAILABLE"] == 1


def test_no_current_probables_fails_bounded() -> None:
    with pytest.raises(
        IntradayStatisticsError,
        match="^INTRADAY_STATISTICS_CURRENT_PROBABLES_UNAVAILABLE$",
    ):
        project_intraday_statistics(
            None,
            IntradayReviewV2Snapshot(None, None, ()),
            {"reviews": ()},
            generated_at=_opening_inputs()[0].analysis_boundary,
        )


def test_stage_headers_and_values_preserve_explicit_unavailable_semantics() -> None:
    projection = _projection()
    rows = [dict(zip(STAGE_COLUMNS, row.values, strict=True)) for row in projection.stages]
    downstream = rows[3]
    assert downstream["Classification"] == "NOT_REACHED"
    assert downstream["Source Artifact Identity"] == "UNAVAILABLE"
    assert downstream["Observed At"] == "UNAVAILABLE"
    assert downstream["Current At Review Boundary"] == "UNAVAILABLE"


def test_nine_current_candidates_produce_exactly_81_stable_stage_rows() -> None:
    mappings = tuple(
        _opening_inputs(subject=f"NSE-EQ-TEST{index}")[-1]
        for index in range(9)
    )
    run = evaluate_probables_v2_run(
        source_discovery_run_identity=SOURCE_RUN,
        universe_identity="KRONOS-INTRADAY-NATIVE-UNIVERSE-V1",
        universe_version="1.0.0",
        reconciliation_identity="KRONOS-INTRADAY-RECONCILIATION-V1",
        reconciliation_version="1.0.0",
        market_session_identity=mappings[0].market_session_identity,
        analysis_boundary=mappings[0].analysis_boundary,
        member_evidence=mappings,
        unavailable_members=(),
        provenance=PROVENANCE,
    )
    projection = project_intraday_statistics(
        run,
        IntradayReviewV2Snapshot(None, None, ()),
        {"product_identity": WO_B_PRODUCT_IDENTITY, "reviews": ()},
        generated_at=run.analysis_boundary,
    )
    assert len(projection.candidates) == 9
    assert len(projection.stages) == 81
    assert [row.values[0] for row in projection.candidates] == [
        f"TEST{index}" for index in range(9)
    ]
    assert all(
        [row.values[7] for row in projection.stages[index:index + 9]]
        == list(STAGES)
        for index in range(0, 81, 9)
    )


@pytest.mark.parametrize(
    ("changes", "column", "expected"),
    (
        ({"chart_state": "CHART_REQUIRED", "chart_revision_identity": None}, "Chart State", "CHART_REQUIRED"),
        ({"question_pack_state": "ABSENT", "question_transport_identity": None}, "Question Pack State", "ABSENT"),
        ({"answer_state": "NOT_IMPORTED", "answer_pack_identity": None}, "Answer State", "NOT_IMPORTED"),
        ({"visual_evidence_state": "ABSENT", "visual_evidence_identity": None}, "Visual Evidence State", "ABSENT"),
    ),
)
def test_partial_review_states_are_preserved_without_fabrication(
    changes, column, expected
) -> None:  # type: ignore[no-untyped-def]
    run, review, readiness = _current()
    candidate = replace(review.candidates[0], **changes)
    projection = project_intraday_statistics(
        run,
        replace(review, candidates=(candidate,)),
        readiness,
        generated_at=run.analysis_boundary,
    )
    assert _candidate_values(projection)[column] == expected
