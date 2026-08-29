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
    parse_batch_answer_transport,
)
from kronos.intraday.review_v2 import (
    REVIEW_CYCLE_V2_IDENTITY,
    REVIEW_V2_CONTRACT_VERSION,
    artifact_bytes_v2,
    artifact_from_bytes_v2,
    bind_imported_visual_evidence_v2,
    create_chart_intake_request_v2,
    create_chart_revision_v2,
    create_question_batch_v2,
    create_question_pack_v2,
)
from kronos.intraday.review_v2_persistence import IntradayReviewV2Store
from kronos.intraday.review_v2_transport import (
    REVIEW_BATCH_TRANSPORT_V2_IDENTITY,
    IntradayReviewV2Transport,
)
from kronos.intraday.review_persistence import MAX_CHART_BYTES
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


def _completed_batch_payload(path: Path, observed: str) -> bytes:
    document = json.loads(path.read_bytes())
    candidate = document["candidates"][0]
    candidate["observed_visible_subject_identity"] = observed
    candidate["global_observation_status"] = "OBSERVED"
    for question, answer in zip(QUESTIONS, candidate["answers"], strict=True):
        answer.update(
            observation_status="OBSERVED",
            answer=question.allowed_answers[0],
            visible_timeframes=list(question.timeframe_scope),
            visible_basis="Visible completed chart evidence.",
            status_detail=None,
            why_not_covered_elsewhere=None,
        )
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode()


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


def test_v2_chart_intake_is_exact_cycle_bound_idempotent_and_restart_safe(
    tmp_path: Path,
) -> None:
    *_, mapping = _opening_inputs()
    run, application = _application(tmp_path, mapping)
    cycle = application.create_eligible_cycles(run)[0]
    original_cycle = artifact_bytes_v2(cycle)

    first = application.upload_chart(
        cycle.cycle_identity, media_type="image/png", payload=_png(51)
    )
    same = application.upload_chart(
        cycle.cycle_identity, media_type="image/png", payload=_png(51)
    )
    replacement = application.upload_chart(
        cycle.cycle_identity, media_type="image/png", payload=_png(52)
    )

    assert same == first
    assert first.revision_ordinal == 1
    assert replacement.revision_ordinal == 2
    assert first.chart_revision_identity != replacement.chart_revision_identity
    assert application.review_store.load_chart_bytes(first) == _png(51)
    assert application.review_store.load_chart_bytes(replacement) == _png(52)
    assert artifact_bytes_v2(application.review_store.load_cycle(cycle.cycle_identity)) == original_cycle
    current = application.review_store.load_current_chart(cycle.cycle_identity)
    assert current is not None
    assert current.chart_revision_identity == replacement.chart_revision_identity
    assert current.expected_canonical_subject_identity == cycle.canonical_subject_identity
    assert current.direction == cycle.direction
    assert current.methodology_publication_identity == cycle.methodology_publication_identity
    assert current.methodology_checksum == cycle.methodology_checksum
    assert current.phase is cycle.phase
    assert current.analysis_boundary == cycle.analysis_boundary

    restored = IntradayReviewV2Application(
        probables_store=application.probables_store,
        review_store=IntradayReviewV2Store(application.review_store.root),
    )
    candidate = restored.snapshot().candidates[0]
    assert candidate.chart_state == "CHART_READY"
    assert candidate.chart_revision_identity == replacement.chart_revision_identity
    assert candidate.chart_revision_ordinal == 2


def test_v2_chart_intake_rejects_invalid_image_and_forged_lineage(
    tmp_path: Path,
) -> None:
    *_, mapping = _opening_inputs()
    run, application = _application(tmp_path, mapping)
    cycle = application.create_eligible_cycles(run)[0]

    for media_type, payload in (
        ("image/png", b""),
        ("text/plain", _png(1)),
        ("image/png", b"not-a-png"),
        ("image/png", b"\x89PNG\r\n\x1a\n" + b"0" * MAX_CHART_BYTES),
    ):
        with pytest.raises(ReviewError, match=ReviewFailure.CHART_INVALID.value):
            application.upload_chart(
                cycle.cycle_identity, media_type=media_type, payload=payload
            )
    with pytest.raises(ReviewError, match=ReviewFailure.NOT_CURRENT.value):
        application.upload_chart(
            "INTRADAY-REVIEW-V2-CYCLE-WRONG",
            media_type="image/png",
            payload=_png(2),
        )

    request = create_chart_intake_request_v2(
        cycle,
        payload=_png(3),
        media_type="image/png",
        requested_at=run.analysis_boundary + timedelta(seconds=1),
    )
    for change in (
        {"expected_canonical_subject_identity": "NSE-EQ-WRONG"},
        {"direction": "SHORT"},
        {"methodology_checksum": "0" * 64},
        {"review_cycle_identity": "INTRADAY-REVIEW-V2-CYCLE-WRONG"},
    ):
        with pytest.raises(ReviewError, match=ReviewFailure.CHART_INVALID.value):
            replace(request, **change)


def test_v2_combined_transport_is_exact_bound_idempotent_and_reloadable(
    tmp_path: Path,
) -> None:
    *_, mapping = _opening_inputs()
    run, original = _application(tmp_path, mapping)
    application = IntradayReviewV2Application(
        probables_store=original.probables_store,
        review_store=original.review_store,
        transport=IntradayReviewV2Transport(
            question_outbox=(tmp_path / "questions").resolve(),
            answer_inbox=(tmp_path / "answers").resolve(),
        ),
    )
    cycle = application.create_eligible_cycles(run)[0]
    chart = application.upload_chart(
        cycle.cycle_identity, media_type="image/png", payload=_png(71)
    )

    first = application.create_combined_question_transport()
    repeated = application.create_combined_question_transport()

    assert repeated == first
    assert first.transport.schema_identity == REVIEW_BATCH_TRANSPORT_V2_IDENTITY
    assert first.batch.review_cycle_identities == (cycle.cycle_identity,)
    assert first.packs[0].chart_revision_identity == chart.chart_revision_identity
    assert first.packs[0].review_cycle_identity == cycle.cycle_identity
    assert first.question_path.read_bytes().startswith(b"%PDF")
    parsed = parse_batch_answer_transport(first.answer_template_path.read_bytes())
    assert parsed.review_batch_identity == first.batch.batch_identity
    assert parsed.probables_run_identity == run.run_identity
    assert len(parsed.candidate_documents) == 1
    candidate = parsed.candidate_documents[0]
    assert candidate["review_pack_identity"] == first.packs[0].review_pack_identity
    assert candidate["review_cycle_identity"] == cycle.cycle_identity
    assert candidate["chart_revision_identity"] == chart.chart_revision_identity
    assert candidate["observed_visible_subject_identity"] is None
    parsed_candidate = parse_answer_pack(json.dumps(candidate).encode())
    assert parsed_candidate.review_pack_identity == first.packs[0].review_pack_identity
    assert parsed_candidate.review_cycle_identity == cycle.cycle_identity
    assert parsed_candidate.chart_revision_identity == chart.chart_revision_identity

    restored = IntradayReviewV2Store(application.review_store.root)
    assert restored.load_pack(first.packs[0].review_pack_identity) == first.packs[0]
    assert restored.load_batch(first.batch.batch_identity) == first.batch
    assert restored.load_transport(first.transport.transport_identity) == first.transport
    assert restored.load_transport_question_pdf(first.transport) == first.question_path.read_bytes()
    assert restored.load_transport_answer_template(first.transport) == first.answer_template_path.read_bytes()
    snapshot = application.snapshot()
    assert snapshot.candidates[0].review_pack_state == "READY"
    assert snapshot.candidates[0].question_pack_state == "TRANSPORT_READY"
    assert snapshot.question_transport_identity == first.transport.transport_identity


def test_v2_combined_answer_validates_imports_and_restores_exact_evidence(
    tmp_path: Path,
) -> None:
    *_, mapping = _opening_inputs()
    run, original = _application(tmp_path, mapping)
    application = IntradayReviewV2Application(
        probables_store=original.probables_store,
        review_store=original.review_store,
        transport=IntradayReviewV2Transport(
            question_outbox=(tmp_path / "questions").resolve(),
            answer_inbox=(tmp_path / "answers").resolve(),
        ),
        visual_identity_resolver=_resolver(run.analysis_boundary),
    )
    cycle = application.create_eligible_cycles(run)[0]
    application.upload_chart(
        cycle.cycle_identity, media_type="image/png", payload=_png(91)
    )
    transport = application.create_combined_question_transport()
    payload = _completed_batch_payload(
        transport.answer_template_path, "Reliance Industries Ltd"
    )

    validation = application.validate_combined_answer(payload)
    assert validation.candidate_count == validation.exact_match_count == 1
    assert (
        validation.identity_mismatch_count,
        validation.schema_invalid_count,
        validation.conflict_count,
        validation.duplicate_count,
        validation.missing_count,
        validation.extra_count,
    ) == (0, 0, 0, 0, 0, 0)
    result = application.import_combined_answer(payload)
    assert result.state == "IMPORTED" and result.imported_count == 1
    assert result.review_batch_identity == transport.batch.batch_identity
    member = result.members[0]
    assert member.canonical_subject_identity == "NSE-EQ-RELIANCE"
    assert member.observed_visible_subject_identity == "Reliance Industries Ltd"
    assert member.resolved_canonical_subject_identity == "NSE-EQ-RELIANCE"

    restored = IntradayReviewV2Application(
        probables_store=application.probables_store,
        review_store=IntradayReviewV2Store(application.review_store.root),
    )
    candidate = restored.snapshot().candidates[0]
    assert candidate.answer_state == "IMPORTED"
    assert candidate.visual_identity_state == "MATCH"
    assert candidate.visual_evidence_state == "READY"
    assert candidate.visual_evidence_identity == member.visual_evidence_identity
    evidence = restored.review_store.load_visual_evidence_for_pack(
        transport.packs[0].review_pack_identity
    )
    assert evidence is not None
    assert evidence.visual_evidence_identity == member.visual_evidence_identity


def test_v2_combined_answer_duplicate_wrong_identity_and_wrong_mapping_fail_closed(
    tmp_path: Path,
) -> None:
    *_, mapping = _opening_inputs()
    run, original = _application(tmp_path, mapping)
    application = IntradayReviewV2Application(
        probables_store=original.probables_store,
        review_store=original.review_store,
        transport=IntradayReviewV2Transport(
            question_outbox=(tmp_path / "questions").resolve(),
            answer_inbox=(tmp_path / "answers").resolve(),
        ),
        visual_identity_resolver=_resolver(run.analysis_boundary),
    )
    cycle = application.create_eligible_cycles(run)[0]
    application.upload_chart(
        cycle.cycle_identity, media_type="image/png", payload=_png(92)
    )
    transport = application.create_combined_question_transport()
    payload = _completed_batch_payload(
        transport.answer_template_path, "Reliance Industries Ltd"
    )
    duplicate = json.loads(payload)
    duplicate["candidates"].append(dict(duplicate["candidates"][0]))
    with pytest.raises(ReviewError, match=ReviewFailure.ANSWER_IDENTITY_MISMATCH.value):
        application.validate_combined_answer(json.dumps(duplicate).encode())

    wrong = json.loads(payload)
    wrong["candidates"][0]["chart_revision_identity"] = "WRONG"
    with pytest.raises(ReviewError, match=ReviewFailure.ANSWER_IDENTITY_MISMATCH.value):
        application.validate_combined_answer(json.dumps(wrong).encode())

    relationship = create_visual_identity_relationship(
        canonical_subject_identity="NSE-EQ-OTHER",
        observed_visible_subject_identity="Reliance Industries Ltd",
        source_context=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
        effective_from=run.analysis_boundary - timedelta(days=1),
        effective_through=run.analysis_boundary + timedelta(days=1),
        status=VisualIdentityRelationshipStatus.ACTIVE,
        source_identity="TEST-TRADINGVIEW",
        provenance=("TEST", "ADR-0018"),
        supersedes=None,
    )
    wrong_mapping = VisualIdentityResolver(create_visual_identity_publication(
        canonical_subject_identities=("NSE-EQ-RELIANCE", "NSE-EQ-OTHER"),
        publication_identity=VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1,
        publication_version="1.1.0",
        effective_from=run.analysis_boundary - timedelta(days=1),
        effective_through=run.analysis_boundary + timedelta(days=1),
        source_identities=("TEST-ADR-0018",),
        provenance=("TEST", "DOMAIN-001"),
        relationships=(relationship,),
        supersedes=None,
        schema_identity=VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1,
    ))
    mismatched_application = IntradayReviewV2Application(
        probables_store=application.probables_store,
        review_store=application.review_store,
        transport=application._transport,  # noqa: SLF001
        visual_identity_resolver=wrong_mapping,
    )
    with pytest.raises(ReviewError, match=ReviewFailure.ANSWER_IDENTITY_MISMATCH.value):
        mismatched_application.validate_combined_answer(payload)
