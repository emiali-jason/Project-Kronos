from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import struct
import zlib

import pytest
from pypdf import PdfReader

from kronos.application.intraday_review import IntradayReviewApplication
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.review import (
    CHART_TIMEFRAMES,
    QUESTIONS,
    FutureAnswerPackBinding,
    FutureVisualAnswerIdentity,
    ObservationStatus,
    ReviewError,
    ReviewFailure,
    ReviewState,
    artifact_bytes,
)
from kronos.intraday.review_pdf import IntradayReviewPdfTransport, render_question_pack_pdf
from kronos.intraday.review_persistence import MAX_CHART_BYTES, IntradayReviewStore, validate_chart_payload
from kronos.instrument.visual_identity import (
    VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1,
    VisualIdentityRelationshipStatus,
    VisualIdentityResolver,
    VisualIdentitySourceContext,
    create_visual_identity_publication,
    create_visual_identity_relationship,
)
from tests.unit.intraday.test_historical_semantic import BOUNDARY
from tests.unit.intraday.test_probables import _member, _run


def _png(red: int) -> bytes:
    raw = bytes((0, red, 20, 30))
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def _application(
    tmp_path: Path,
    current: list,
    visual_identity_resolver: VisualIdentityResolver | None = None,
):  # type: ignore[no-untyped-def]
    subjects = tuple(
        result.canonical_subject_identity for result in current[0].results
    )
    relationships = tuple(
        create_visual_identity_relationship(
            canonical_subject_identity=subject,
            observed_visible_subject_identity=subject,
            source_context=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
            effective_from=BOUNDARY - timedelta(days=1),
            effective_through=BOUNDARY + timedelta(days=1),
            status=VisualIdentityRelationshipStatus.ACTIVE,
            source_identity="TEST-TRADINGVIEW-VISUAL-CHART",
            provenance=("TEST", subject),
            supersedes=None,
        )
        for subject in subjects
    )
    resolver = visual_identity_resolver or VisualIdentityResolver(
        create_visual_identity_publication(
            canonical_subject_identities=subjects,
            publication_identity=VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1,
            publication_version="1.0.0",
            effective_from=BOUNDARY - timedelta(days=1),
            effective_through=BOUNDARY + timedelta(days=1),
            source_identities=("TEST-ADR-0018",),
            provenance=("TEST", "DOMAIN-001"),
            relationships=relationships,
            supersedes=None,
            schema_identity=VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1,
        )
    )
    return IntradayReviewApplication(
        current_probables=lambda: current[0],
        store=IntradayReviewStore((tmp_path / "evidence").resolve()),
        transport=IntradayReviewPdfTransport(
            question_outbox=(tmp_path / "questions").resolve(),
            answer_inbox=(tmp_path / "answers").resolve(),
        ),
        visual_identity_resolver=resolver,
        clock=lambda: BOUNDARY + timedelta(seconds=30),
    )


def test_question_set_is_exact_typed_and_non_trading() -> None:
    assert tuple(item.question_id for item in QUESTIONS) == tuple(f"Q{index}" for index in range(1, 11))
    assert QUESTIONS[0].wording == (
        "On the visible completed 1D chart, does the broader price structure visually support, oppose, or neither clearly support nor oppose the proposed Intraday direction?"
    )
    assert QUESTIONS[6].timeframe_scope == ("15M", "5M")
    assert QUESTIONS[7].timeframe_scope == ("15M", "5M")
    assert QUESTIONS[8].timeframe_scope == ("15M", "5M")
    assert QUESTIONS[9].allowed_answers == ("NONE", "MATERIAL_OBSERVATION")
    assert "why_not_covered_elsewhere must be null" in QUESTIONS[9].conditional_instruction
    assert tuple(ObservationStatus) == (
        ObservationStatus.OBSERVED,
        ObservationStatus.PARTIAL,
        ObservationStatus.NOT_VISIBLE,
        ObservationStatus.NOT_APPLICABLE,
        ObservationStatus.UNAVAILABLE,
        ObservationStatus.INVALID,
    )
    encoded = str(QUESTIONS).upper()
    assert "ENTER_NOW" not in encoded and "PAPER/LIVE" not in encoded
    identity = FutureVisualAnswerIdentity("WIPRO", "TCS")
    assert identity.expected_canonical_subject_identity != identity.observed_visible_subject_identity
    binding = FutureAnswerPackBinding(
        probables_run_identity="INTRADAY-PROBABLES-RUN-A",
        expected_canonical_subject_identity="WIPRO",
        observed_visible_subject_identity="TCS",
        review_cycle_identity="INTRADAY-REVIEW-CYCLE-A",
        chart_revision_identity="INTRADAY-CHART-REVISION-A",
        review_pack_identity="INTRADAY-REVIEW-PACK-A",
    )
    assert binding.expected_canonical_subject_identity == "WIPRO"
    assert binding.observed_visible_subject_identity == "TCS"


def test_review_flow_is_immutable_idempotent_and_provider_independent(tmp_path: Path) -> None:
    run = _run((
        _member("WIPRO", hourly=SemanticDirection.SHORT, fifteen=SemanticDirection.SHORT),
        _member("LICI"),
        _member("RELIANCE", narrow=False),
        _member("GOLDM", narrow=None),
    ))
    current = [run]
    application = _application(tmp_path, current)
    candidates = application.snapshot().candidates
    assert tuple(item.canonical_subject_identity for item in candidates) == ("LICI", "WIPRO")
    wipro = next(item for item in candidates if item.canonical_subject_identity == "WIPRO")
    lici = next(item for item in candidates if item.canonical_subject_identity == "LICI")

    cycle = application.start_review(wipro.probable_result_identity)
    assert cycle.initial_review_state is ReviewState.CHART_REQUIRED
    assert application.start_review(wipro.probable_result_identity) == cycle
    with pytest.raises(ReviewError, match=ReviewFailure.CHART_REQUIRED.value):
        application.create_question_pack(cycle.cycle_identity)

    first = application.upload_chart(cycle.cycle_identity, media_type="image/png", payload=_png(10))
    replay = application.upload_chart(cycle.cycle_identity, media_type="image/png", payload=_png(10))
    second = application.upload_chart(cycle.cycle_identity, media_type="image/png", payload=_png(11))
    assert replay == first
    assert second.revision_ordinal == 2 and first.revision_ordinal == 1
    assert first.chart_revision_identity != second.chart_revision_identity

    pack, path = application.create_question_pack(cycle.cycle_identity)
    repeated, repeated_path = application.create_question_pack(cycle.cycle_identity)
    assert pack == repeated and path == repeated_path
    assert path.exists() and (tmp_path / "answers").is_dir()
    assert pack.chart_revision_identity == second.chart_revision_identity
    assert pack.review_cycle_identity == cycle.cycle_identity
    assert pack.probables_run_identity == run.run_identity
    assert pack.questions == QUESTIONS
    restored = _application(tmp_path, current).snapshot()
    wipro_restored = next(item for item in restored.candidates if item.canonical_subject_identity == "WIPRO")
    lici_restored = next(item for item in restored.candidates if item.canonical_subject_identity == "LICI")
    assert wipro_restored.review_state == ReviewState.QUESTION_PACK_CREATED.value
    assert wipro_restored.chart_revision_ordinal == 2
    assert wipro_restored.review_pack_identity == pack.review_pack_identity
    assert lici_restored.cycle_identity is None
    assert restored.provider_operations == restored.discovery_operations == restored.probables_operations == 0


def test_direct_first_chart_establishes_one_exact_cycle_idempotently(tmp_path: Path) -> None:
    run = _run((_member("WIPRO"), _member("LICI")))
    current = [run]
    application = _application(tmp_path, current)
    wipro = next(item for item in run.results if item.canonical_subject_identity == "WIPRO")

    first = application.upload_chart_for_result(
        wipro.result_identity, media_type="image/png", payload=_png(35)
    )
    replay = application.upload_chart_for_result(
        wipro.result_identity, media_type="image/png", payload=_png(35)
    )

    assert replay == first and first.revision_ordinal == 1
    snapshot = application.snapshot()
    wipro_snapshot = next(
        item for item in snapshot.candidates if item.canonical_subject_identity == "WIPRO"
    )
    lici_snapshot = next(
        item for item in snapshot.candidates if item.canonical_subject_identity == "LICI"
    )
    assert wipro_snapshot.review_state == ReviewState.CHART_READY.value
    assert wipro_snapshot.chart_revision_identity == first.chart_revision_identity
    assert lici_snapshot.cycle_identity is None
    assert len(application.store.load_current().cycles) == 1  # type: ignore[union-attr]


def test_direct_chart_reuses_existing_cycle_and_rejects_invalid_candidate_or_chart(
    tmp_path: Path,
) -> None:
    run = _run((_member("WIPRO"), _member("LICI")))
    current = [run]
    application = _application(tmp_path, current)
    wipro = next(item for item in run.results if item.canonical_subject_identity == "WIPRO")
    cycle = application.start_review(wipro.result_identity)

    chart = application.upload_chart_for_result(
        wipro.result_identity, media_type="image/png", payload=_png(36)
    )
    assert chart.cycle_identity == cycle.cycle_identity
    assert len(application.store.load_current().cycles) == 1  # type: ignore[union-attr]

    with pytest.raises(ReviewError, match=ReviewFailure.NOT_CURRENT.value):
        application.upload_chart_for_result(
            "INTRADAY-PROBABLE-RESULT-WRONG", media_type="image/png", payload=_png(37)
        )
    before = application.store.load_current()
    with pytest.raises(ReviewError, match=ReviewFailure.CHART_INVALID.value):
        application.upload_chart_for_result(
            next(item for item in run.results if item.canonical_subject_identity == "LICI").result_identity,
            media_type="image/png",
            payload=b"invalid",
        )
    assert application.store.load_current() == before


def test_direct_chart_binds_new_run_and_direction_flip_without_old_cycle_reuse(
    tmp_path: Path,
) -> None:
    run_a = _run((
        _member("WIPRO", hourly=SemanticDirection.SHORT, fifteen=SemanticDirection.SHORT),
    ))
    current = [run_a]
    application = _application(tmp_path, current)
    chart_a = application.upload_chart_for_result(
        run_a.results[0].result_identity, media_type="image/png", payload=_png(38)
    )
    cycle_a = application.snapshot().candidates[0].cycle_identity

    boundary_b = BOUNDARY + timedelta(minutes=5)
    run_b = _run((_member("WIPRO", boundary=boundary_b),), boundary=boundary_b)
    current[0] = run_b
    chart_b = application.upload_chart_for_result(
        run_b.results[0].result_identity, media_type="image/png", payload=_png(39)
    )
    cycle_b = application.snapshot().candidates[0].cycle_identity

    assert cycle_a is not None and cycle_b is not None and cycle_a != cycle_b
    assert chart_a.cycle_identity == cycle_a and chart_b.cycle_identity == cycle_b
    assert application.store.load_cycle(cycle_a).direction == "SHORT"
    assert application.store.load_cycle(cycle_b).direction == "LONG"


def test_same_instrument_multiple_cycles_and_direction_flip_restore_exactly(tmp_path: Path) -> None:
    run_a = _run((_member("WIPRO", hourly=SemanticDirection.SHORT, fifteen=SemanticDirection.SHORT),))
    current = [run_a]
    application = _application(tmp_path, current)
    cycle_a = application.start_review(run_a.results[0].result_identity)
    chart_a = application.upload_chart(cycle_a.cycle_identity, media_type="image/png", payload=_png(1))
    pack_a, _ = application.create_question_pack(cycle_a.cycle_identity)

    boundary_b = BOUNDARY + timedelta(minutes=5)
    run_b = _run((_member("WIPRO", boundary=boundary_b),), boundary=boundary_b)
    current[0] = run_b
    snapshot = application.snapshot()
    assert snapshot.candidates[0].cycle_identity is None
    with pytest.raises(ReviewError, match=ReviewFailure.CYCLE_UNAVAILABLE.value):
        application.upload_chart(cycle_a.cycle_identity, media_type="image/png", payload=_png(2))
    cycle_b = application.start_review(run_b.results[0].result_identity)
    chart_b = application.upload_chart(cycle_b.cycle_identity, media_type="image/png", payload=_png(1))
    pack_b, _ = application.create_question_pack(cycle_b.cycle_identity)

    assert cycle_a.cycle_identity != cycle_b.cycle_identity
    assert chart_a.revision_ordinal == chart_b.revision_ordinal == 1
    assert chart_a.chart_revision_identity != chart_b.chart_revision_identity
    assert pack_a.review_pack_identity != pack_b.review_pack_identity
    restored = _application(tmp_path, current).snapshot().candidates[0]
    assert restored.cycle_identity == cycle_b.cycle_identity
    assert restored.review_pack_identity == pack_b.review_pack_identity
    store = IntradayReviewStore((tmp_path / "evidence").resolve())
    assert store.load_cycle(cycle_a.cycle_identity) == cycle_a
    assert store.load_pack(pack_a.review_pack_identity) == pack_a


def test_invalid_chart_path_safety_tamper_and_missing_pointer_fail_closed(tmp_path: Path) -> None:
    run = _run((_member("WIPRO"),))
    current = [run]
    application = _application(tmp_path, current)
    cycle = application.start_review(run.results[0].result_identity)
    for media_type, payload in (
        ("application/x-sh", b"#!/bin/sh"),
        ("image/png", b""),
        ("image/png", b"not-an-image"),
    ):
        with pytest.raises(ReviewError, match=ReviewFailure.CHART_INVALID.value):
            application.upload_chart(cycle.cycle_identity, media_type=media_type, payload=payload)
    with pytest.raises(ReviewError, match=ReviewFailure.CHART_INVALID.value):
        validate_chart_payload("image/png", b"x" * (MAX_CHART_BYTES + 1))
    store = IntradayReviewStore((tmp_path / "evidence").resolve())
    with pytest.raises(ReviewError):
        store.load_cycle("../cycle")
    chart = application.upload_chart(cycle.cycle_identity, media_type="image/png", payload=_png(80))
    chart_manifest = store.root / "chart-revisions" / f"{chart.chart_revision_identity}.json"
    chart_manifest.unlink()
    with pytest.raises(ReviewError, match=ReviewFailure.ARTIFACT_UNAVAILABLE.value):
        _application(tmp_path, current).snapshot()
    pointer = store.root / "current" / "CURRENT-REVIEW-POINTER.json"
    pointer.write_bytes(pointer.read_bytes().replace(b"WIPRO", b"TAMPER"))
    with pytest.raises(ReviewError, match=ReviewFailure.INTEGRITY_INVALID.value):
        _application(tmp_path, current).snapshot()


def test_same_identity_different_bytes_is_a_persistence_conflict(tmp_path: Path) -> None:
    run = _run((_member("WIPRO"),))
    current = [run]
    application = _application(tmp_path, current)
    cycle = application.start_review(run.results[0].result_identity)
    store = IntradayReviewStore((tmp_path / "evidence").resolve())
    cycle_path = store.root / "cycles" / f"{cycle.cycle_identity}.json"
    cycle_path.write_bytes(b"conflicting-content")
    with pytest.raises(ReviewError, match=ReviewFailure.PERSISTENCE_CONFLICT.value):
        store.retain_cycle(cycle)


def test_pdf_is_deterministic_readable_and_canonical_json_remains_authority(tmp_path: Path) -> None:
    run = _run((_member("WIPRO"),))
    current = [run]
    application = _application(tmp_path, current)
    cycle = application.start_review(run.results[0].result_identity)
    application.upload_chart(cycle.cycle_identity, media_type="image/png", payload=_png(50))
    pack, path = application.create_question_pack(cycle.cycle_identity)
    payload = path.read_bytes()
    assert payload == render_question_pack_pdf(pack, _png(50))
    text = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    assert "KRONOS INTRADAY V1" in text
    assert "WIPRO" in text and "LONG" in text
    assert all(question.question_id in text for question in QUESTIONS)
    assert "VISUAL EVIDENCE ONLY" in text
    assert "ENTER NOW" in text
    assert artifact_bytes(pack).startswith(b'{"artifact_type":"ReviewQuestionPack"')
    assert pack.review_pack_identity.encode() not in payload or pack.review_pack_identity in text
    assert CHART_TIMEFRAMES == ("1D", "1H", "15M", "5M")
