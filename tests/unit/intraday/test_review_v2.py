from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
import json
from pathlib import Path

import pytest

from kronos.application.intraday_review_v2 import IntradayReviewV2Application
from kronos.instrument.visual_identity import (
    VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1,
    VisualIdentityRelationshipStatus,
    VisualIdentityResolver,
    VisualIdentitySourceContext,
    create_visual_identity_publication,
    create_visual_identity_relationship,
)
from kronos.intraday.completed_evidence import IntradayAnalysisPhase
from kronos.intraday.mcx_commissioning import McxCommissioningState
from kronos.intraday.probables import ProbableState
from kronos.intraday.probables_v2 import create_probables_v2_methodology
from kronos.intraday.probables_v2_persistence import ProbablesV2Store
from kronos.intraday.review import QUESTIONS, ReviewError, ReviewFailure
from kronos.intraday.review_answer import (
    ANSWER_PACK_IDENTITY,
    ANSWER_CONTRACT_VERSION,
    parse_answer_pack,
)
from kronos.intraday.review_v2 import (
    REVIEW_CYCLE_V2_IDENTITY,
    REVIEW_V2_CONTRACT_VERSION,
    artifact_bytes_v2,
    artifact_from_bytes_v2,
    bind_imported_visual_evidence_v2,
    create_chart_revision_v2,
    create_question_batch_v2,
    create_question_pack_v2,
)
from kronos.intraday.review_v2_persistence import IntradayReviewV2Store
from .test_probables_v2 import (
    _later_mapping,
    _opening_inputs,
    _run,
)
from .test_review import _png


def _application(tmp_path: Path, mapping):  # type: ignore[no-untyped-def]
    run = _run(mapping)
    probables = ProbablesV2Store((tmp_path / "probables-v2").resolve())
    probables.retain_complete(run=run, mappings=(mapping,))
    review = IntradayReviewV2Store((tmp_path / "review-v2").resolve())
    return run, IntradayReviewV2Application(
        probables_store=probables,
        review_store=review,
    )


def _answer(pack):  # type: ignore[no-untyped-def]
    document = {
        "schema_identity": ANSWER_PACK_IDENTITY,
        "schema_version": ANSWER_CONTRACT_VERSION,
        "question_set_identity": pack.question_set_identity,
        "question_set_version": pack.question_set_version,
        "review_pack_identity": pack.review_pack_identity,
        "review_cycle_identity": pack.review_cycle_identity,
        "review_request_identity": pack.review_request_identity,
        "chart_revision_identity": pack.chart_revision_identity,
        "expected_canonical_subject_identity": pack.expected_canonical_subject_identity,
        "observed_visible_subject_identity": "Reliance Industries Ltd",
        "proposed_direction": pack.proposed_direction,
        "global_observation_status": "OBSERVED",
        "answers": [{
            "question_id": question.question_id,
            "observation_status": "OBSERVED",
            "answer": question.allowed_answers[0],
            "visible_timeframes": list(question.timeframe_scope),
            "visible_basis": "Visible completed chart evidence.",
            "status_detail": None,
            "why_not_covered_elsewhere": None,
        } for question in QUESTIONS],
    }
    return parse_answer_pack(json.dumps(document).encode())


def _resolver(boundary: datetime) -> VisualIdentityResolver:
    relationship = create_visual_identity_relationship(
        canonical_subject_identity="NSE-EQ-RELIANCE",
        observed_visible_subject_identity="Reliance Industries Ltd",
        source_context=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
        effective_from=boundary - timedelta(days=1),
        effective_through=boundary + timedelta(days=1),
        status=VisualIdentityRelationshipStatus.ACTIVE,
        source_identity="TEST-TRADINGVIEW",
        provenance=("TEST", "ADR-0018"),
        supersedes=None,
    )
    return VisualIdentityResolver(create_visual_identity_publication(
        canonical_subject_identities=("NSE-EQ-RELIANCE",),
        publication_identity=VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1,
        publication_version="1.0.0",
        effective_from=boundary - timedelta(days=1),
        effective_through=boundary + timedelta(days=1),
        source_identities=("TEST-ADR-0018",),
        provenance=("TEST", "DOMAIN-001"),
        relationships=(relationship,),
        supersedes=None,
        schema_identity=VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1,
    ))


@pytest.mark.parametrize("legacy", (True, False))
def test_exact_v2_methodology_lineage_creates_and_restores_separate_cycle(
    tmp_path: Path, legacy: bool,
) -> None:
    methodology = create_probables_v2_methodology(legacy=legacy)
    *_, mapping = _opening_inputs(methodology=methodology)
    run, application = _application(tmp_path, mapping)

    cycles = application.create_eligible_cycles(run)
    assert len(cycles) == 1
    cycle = cycles[0]
    assert cycle.schema_identity == REVIEW_CYCLE_V2_IDENTITY
    assert cycle.schema_version == REVIEW_V2_CONTRACT_VERSION
    assert cycle.methodology_version == methodology.methodology_version
    assert cycle.methodology_publication_identity == methodology.publication_identity
    assert cycle.methodology_checksum == methodology.payload_checksum
    assert cycle.phase is IntradayAnalysisPhase.OPENING
    assert cycle.completed_evidence_selection_identity == mapping.completed_evidence.selection_identity
    assert cycle.completed_evidence_integrity_identity == mapping.completed_evidence.integrity_identity
    assert cycle.semantic_evidence_identity == mapping.semantic_evidence.evidence_identity
    assert cycle.semantic_evidence_integrity_identity == mapping.semantic_evidence.integrity_identity
    assert cycle.nifty_evidence_identity == mapping.nifty_relative.evidence_identity
    assert application.create_eligible_cycles(run) == cycles

    restored = IntradayReviewV2Store(application.review_store.root)
    assert restored.load_current().probables_run_identity == run.run_identity  # type: ignore[union-attr]
    assert restored.load_cycle(cycle.cycle_identity) == cycle
    assert artifact_from_bytes_v2(artifact_bytes_v2(cycle)) == cycle


def test_later_phase_is_bound_not_recomputed(tmp_path: Path) -> None:
    boundary = datetime.fromisoformat("2026-08-28T12:00:00+05:30")
    mapping = _later_mapping(8, 2, boundary=boundary)
    run, application = _application(tmp_path, mapping)
    cycle = application.create_eligible_cycles(run)[0]
    assert cycle.phase is IntradayAnalysisPhase.CURRENT_SESSION_ESTABLISHED
    assert cycle.nifty_evidence_identity is None


@pytest.mark.parametrize("family", ("GOLDM", "SILVERM", "COPPER", "CRUDE"))
def test_only_commissioned_mcx_probables_create_review(
    tmp_path: Path, family: str,
) -> None:
    *_, mapping = _opening_inputs(
        subject=f"MCX-SUBJECT-{family}", subject_exchange="MCX"
    )
    run, application = _application(tmp_path, mapping)
    cycle = application.create_eligible_cycles(run)[0]
    assert cycle.mcx_commissioning is not None
    assert cycle.mcx_commissioning.state is McxCommissioningState.COMMISSIONED
    assert cycle.nifty_applicability.value == "NOT_APPLICABLE"  # type: ignore[union-attr]


def test_held_unavailable_and_not_admitted_members_do_not_create_review(
    tmp_path: Path,
) -> None:
    *_, held_mapping = _opening_inputs(
        subject="MCX-SUBJECT-NATGAS", subject_exchange="MCX"
    )
    held_run, held = _application(tmp_path / "held", held_mapping)
    assert held_run.results[0].state is ProbableState.UNAVAILABLE
    assert held.create_eligible_cycles(held_run) == ()

    *_, blocked_mapping = _opening_inputs(narrow_qualified=False)
    blocked_run, blocked = _application(tmp_path / "blocked", blocked_mapping)
    assert blocked_run.results[0].state is ProbableState.NOT_ADMITTED
    assert blocked.create_eligible_cycles(blocked_run) == ()


def test_exact_persisted_run_result_and_evidence_are_required(tmp_path: Path) -> None:
    *_, mapping = _opening_inputs()
    run, application = _application(tmp_path, mapping)
    missing = IntradayReviewV2Application(
        probables_store=ProbablesV2Store((tmp_path / "empty-probables").resolve()),
        review_store=IntradayReviewV2Store((tmp_path / "empty-review").resolve()),
    )
    with pytest.raises(ReviewError, match=ReviewFailure.ARTIFACT_UNAVAILABLE.value):
        missing.create_eligible_cycles(run)

    result_path = (
        tmp_path / "probables-v2" / "probables-v2" / "results"
        / f"{run.results[0].result_identity}.json"
    )
    result_path.write_bytes(result_path.read_bytes().replace(b'"LONG_PROBABLE"', b'"NOT_ADMITTED"'))
    with pytest.raises(ReviewError):
        application.create_eligible_cycles(run)


def test_successor_chart_pack_and_answer_preserve_exact_cycle_and_visual_identity(
    tmp_path: Path,
) -> None:
    *_, mapping = _opening_inputs()
    run, application = _application(tmp_path, mapping)
    cycle = application.create_eligible_cycles(run)[0]
    handoff = application.review_store.load_handoff(cycle.handoff_identity)
    payload = _png(42)
    chart = create_chart_revision_v2(
        cycle, revision_ordinal=1, payload=payload, media_type="image/png",
        received_at=run.analysis_boundary + timedelta(seconds=1),
    )
    application.review_store.retain_chart(chart, payload)
    assert application.review_store.load_chart_bytes(chart) == payload
    pack = create_question_pack_v2(handoff, cycle, chart)
    answer = _answer(pack)
    evidence = bind_imported_visual_evidence_v2(
        pack, answer,
        imported_at=run.analysis_boundary + timedelta(seconds=2),
        visual_identity_resolver=_resolver(run.analysis_boundary),
    )
    assert evidence.observed_visible_subject_identity == "Reliance Industries Ltd"
    assert evidence.resolved_canonical_subject_identity == "NSE-EQ-RELIANCE"
    assert evidence.methodology_checksum == cycle.methodology_checksum
    assert evidence.phase is cycle.phase

    batch = create_question_batch_v2((pack,))
    application.review_store.retain_batch(batch)
    assert application.review_store.load_batch(batch.batch_identity) == batch

    with pytest.raises(ReviewError, match=ReviewFailure.INTEGRITY_INVALID.value):
        replace(cycle, direction="SHORT")


def test_unknown_methodology_phase_and_integrity_tampering_fail_closed(
    tmp_path: Path,
) -> None:
    *_, mapping = _opening_inputs()
    run, application = _application(tmp_path, mapping)
    cycle = application.create_eligible_cycles(run)[0]
    for changes in (
        {"methodology_checksum": "0" * 64},
        {"phase": IntradayAnalysisPhase.STRUCTURE},
        {"completed_evidence_selection_identity": "WRONG"},
        {"semantic_evidence_identity": "WRONG"},
        {"probables_run_identity": "WRONG"},
        {"integrity_identity": "INTEGRITY-TAMPERED"},
    ):
        with pytest.raises(ReviewError, match=ReviewFailure.INTEGRITY_INVALID.value):
            replace(cycle, **changes)
