"""Bounded individual Review transport and exact governed Answer inbox tests."""

from __future__ import annotations

from datetime import timedelta
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
from kronos.intraday.probables_v2 import (
    PROBABLES_V2_METHODOLOGY_VERSION,
    create_probables_v2_methodology,
    evaluate_probables_v2_run,
)
from kronos.intraday.probables_v2_persistence import ProbablesV2Store
from kronos.intraday.review import QUESTIONS, ReviewError, ReviewFailure
from kronos.intraday.visual_contract_v2 import NSE_QUESTIONS
from kronos.intraday.review_v2_persistence import IntradayReviewV2Store
from kronos.intraday.review_v2_transport import IntradayReviewV2Transport
from tests.unit.intraday.test_probables_v2 import (
    PROVENANCE,
    SOURCE_RUN,
    _opening_inputs,
)
from tests.unit.intraday.test_review import _png
from tests.unit.intraday.test_review_v2 import _retain_later_current_run


SUBJECTS = (
    "BDL", "CRUDE", "EICHERMOT", "MAXHEALTH", "NTPC",
    "SRF", "TATAPOWER", "TITAN", "TMPV",
)


def _fixture(tmp_path: Path, subjects=SUBJECTS, *, correspondence=True):  # type: ignore[no-untyped-def]
    mappings = tuple(
        _opening_inputs(subject=f"NSE-EQ-{subject}")[-1] for subject in subjects
    )
    first = mappings[0]
    run = evaluate_probables_v2_run(
        source_discovery_run_identity=SOURCE_RUN,
        universe_identity="KRONOS-INTRADAY-NATIVE-UNIVERSE-V1",
        universe_version="1.0.0",
        reconciliation_identity="KRONOS-INTRADAY-RECONCILIATION-V1",
        reconciliation_version="1.0.0",
        market_session_identity=first.market_session_identity,
        analysis_boundary=first.analysis_boundary,
        member_evidence=mappings,
        unavailable_members=(),
        provenance=PROVENANCE,
        methodology=(
            create_probables_v2_methodology(legacy=True)
            if first.methodology_version == PROBABLES_V2_METHODOLOGY_VERSION
            else None
        ),
    )
    probables = ProbablesV2Store((tmp_path / "probables-v2").resolve())
    probables.retain_complete(run=run, mappings=mappings)
    review = IntradayReviewV2Store((tmp_path / "review-v2").resolve())
    canonical = tuple(f"NSE-EQ-{subject}" for subject in subjects)
    relationships = tuple(
        create_visual_identity_relationship(
            canonical_subject_identity=subject,
            observed_visible_subject_identity=subject,
            source_context=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
            effective_from=run.analysis_boundary - timedelta(days=1),
            effective_through=run.analysis_boundary + timedelta(days=1),
            status=VisualIdentityRelationshipStatus.ACTIVE,
            source_identity="TEST-TRADINGVIEW",
            provenance=("TEST", subject),
            supersedes=None,
        )
        for subject in canonical
    )
    resolver = VisualIdentityResolver(create_visual_identity_publication(
        canonical_subject_identities=canonical,
        publication_identity=VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1,
        publication_version="1.0.0",
        effective_from=run.analysis_boundary - timedelta(days=1),
        effective_through=run.analysis_boundary + timedelta(days=1),
        source_identities=("TEST-ADR-0018",),
        provenance=("TEST", "DOMAIN-001"),
        relationships=relationships,
        supersedes=None,
        schema_identity=VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1,
    ))
    transport = IntradayReviewV2Transport(
        question_outbox=(tmp_path / "questions").resolve(),
        answer_inbox=(tmp_path / "answers").resolve(),
    )
    app = IntradayReviewV2Application(
        probables_store=probables,
        review_store=review,
        transport=transport,
        visual_identity_resolver=resolver,
        clock=lambda: run.analysis_boundary + timedelta(minutes=1),
    )
    app.create_eligible_cycles(run)
    from tests.unit.intraday.chart_input_fixtures import configure_fixture_calendar
    configure_fixture_calendar(app)
    if correspondence:
        from tests.unit.intraday.chart_input_fixtures import observe_fixture_uploads
        observe_fixture_uploads(app)
    return run, app


def _completed(path: Path) -> bytes:
    document = json.loads(path.read_bytes())
    for candidate in document["candidates"]:
        candidate.pop("chart_observation_header", None)  # Retained pre-header observer fixture.
        candidate["observed_visible_subject_identity"] = candidate[
            "expected_canonical_subject_identity"
        ]
        candidate["global_observation_status"] = "OBSERVED"
        for question, answer in zip((NSE_QUESTIONS if candidate["question_set_version"] == "2.0.0" else QUESTIONS), candidate["answers"], strict=True):
            answer.update(
                observation_status="OBSERVED",
                answer=("NOT_OBSERVABLE" if candidate["question_set_version"] == "2.0.0" and question.question_id in {"Q6", "Q9"} else question.allowed_answers[0]),
                visible_timeframes=list(question.timeframe_scope),
                visible_basis="Visible completed chart evidence.",
                status_detail=None,
                why_not_covered_elsewhere=None,
            )
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode()


def _cycles(app: IntradayReviewV2Application):  # type: ignore[no-untyped-def]
    return {item.sponsor_label: item for item in app.snapshot().candidates}


def test_nine_candidate_subset_creates_only_two_individual_transports(tmp_path: Path) -> None:
    _, app = _fixture(tmp_path)
    cycles = _cycles(app)
    for label, marker in (("BDL", 1), ("CRUDE", 2)):
        app.upload_chart(
            cycles[label].cycle_identity, media_type="image/png", payload=_png(marker)
        )
    before_crude = app.review_store.root.joinpath("question-packs")
    bdl = app.create_individual_question_transport(cycles["BDL"].cycle_identity)
    assert bdl.batch.candidate_identities == ("NSE-EQ-BDL",)
    assert len(tuple(before_crude.glob("*"))) == 1
    assert _cycles(app)["CRUDE"].question_pack_state == "ABSENT"
    repeated = app.create_individual_question_transport(cycles["BDL"].cycle_identity)
    assert repeated == bdl
    crude = app.create_individual_question_transport(cycles["CRUDE"].cycle_identity)
    assert crude.batch.candidate_identities == ("NSE-EQ-CRUDE",)
    assert len(tuple(before_crude.glob("*"))) == 2
    assert bdl.question_path.read_bytes() == repeated.question_path.read_bytes()
    snapshot = _cycles(app)
    assert snapshot["BDL"].question_pack_state == "TRANSPORT_READY"
    assert snapshot["CRUDE"].question_pack_state == "TRANSPORT_READY"
    assert all(snapshot[name].question_pack_state == "ABSENT" for name in SUBJECTS[2:])
    with pytest.raises(ReviewError, match=ReviewFailure.CHART_REQUIRED.value):
        app.create_combined_question_transport()


def test_individual_transport_binds_revision_and_replacement_makes_old_stale(
    tmp_path: Path,
) -> None:
    _, app = _fixture(tmp_path, ("BDL",))
    cycle = _cycles(app)["BDL"].cycle_identity
    first_chart = app.upload_chart(cycle, media_type="image/png", payload=_png(11))
    first = app.create_individual_question_transport(cycle)
    assert first.packs[0].chart_revision_identity == first_chart.chart_revision_identity
    second_chart = app.upload_chart(cycle, media_type="image/png", payload=_png(12))
    stale = app.snapshot().candidates[0]
    assert stale.chart_revision_identity == second_chart.chart_revision_identity
    assert stale.question_pack_state == "ABSENT"
    second = app.create_individual_question_transport(cycle)
    assert second.packs[0].chart_revision_identity == second_chart.chart_revision_identity
    assert second.batch.batch_identity != first.batch.batch_identity
    assert first.question_path.read_bytes().startswith(b"%PDF")
    later = _retain_later_current_run(app)
    app.create_eligible_cycles(later)
    with pytest.raises(ReviewError, match=ReviewFailure.NOT_CURRENT.value):
        app.create_individual_question_transport(cycle)


def test_exact_individual_inbox_missing_import_idempotency_and_tamper(
    tmp_path: Path,
) -> None:
    _, app = _fixture(tmp_path, ("BDL",))
    cycle = _cycles(app)["BDL"].cycle_identity
    app.upload_chart(cycle, media_type="image/png", payload=_png(21))
    result = app.create_individual_question_transport(cycle)
    assert result.answer_template_path.parent == app.review_store.root / "answer-templates"
    assert not (app._transport.answer_inbox / result.transport.expected_answer_filename).exists()  # noqa: SLF001
    missing = app.import_expected_answer(cycle)
    assert missing.not_found_count == 1 and missing.members[0].state == "NOT_FOUND"
    (app._transport.answer_inbox / "unrelated.json").write_text("{}")  # noqa: SLF001
    assert app.import_expected_answer(cycle).not_found_count == 1
    expected = app._transport.answer_inbox / result.transport.expected_answer_filename  # noqa: SLF001
    payload = _completed(result.answer_template_path)
    expected.write_bytes(payload)
    imported = app.import_expected_answer(cycle)
    assert imported.imported_count == 1 and imported.rejected_count == 0
    replay = app.import_expected_answer(cycle)
    assert replay.already_imported_count == 1 and replay.imported_count == 0
    document = json.loads(payload)
    document["candidates"][0]["review_cycle_identity"] = "WRONG"
    expected.write_text(json.dumps(document))
    rejected = app.import_expected_answer(cycle)
    assert rejected.rejected_count == 1 and rejected.members[0].state == "REJECTED"


def test_partial_all_import_considers_only_exact_current_individual_transports(
    tmp_path: Path,
) -> None:
    _, app = _fixture(tmp_path)
    cycles = _cycles(app)
    transports = {}
    for label, marker in (("BDL", 31), ("CRUDE", 32)):
        app.upload_chart(
            cycles[label].cycle_identity, media_type="image/png", payload=_png(marker)
        )
        transports[label] = app.create_individual_question_transport(
            cycles[label].cycle_identity
        )
    bdl = transports["BDL"]
    (app._transport.answer_inbox / bdl.transport.expected_answer_filename).write_bytes(  # noqa: SLF001
        _completed(bdl.answer_template_path)
    )
    result = app.import_all_expected_answers()
    assert (
        result.current_review_count,
        result.expected_count,
        result.found_count,
        result.imported_count,
        result.not_found_count,
        result.rejected_count,
    ) == (9, 2, 1, 1, 1, 0)
    assert {item.state for item in result.members} == {"IMPORTED", "NOT_FOUND"}


def test_exact_combined_answer_has_precedence_over_individual_files(
    tmp_path: Path,
) -> None:
    _, app = _fixture(tmp_path, ("BDL", "CRUDE"))
    cycles = _cycles(app)
    individual = []
    for label, marker in (("BDL", 41), ("CRUDE", 42)):
        app.upload_chart(
            cycles[label].cycle_identity, media_type="image/png", payload=_png(marker)
        )
        individual.append(app.create_individual_question_transport(
            cycles[label].cycle_identity
        ))
    combined = app.create_combined_question_transport()
    for item in individual:
        (app._transport.answer_inbox / item.transport.expected_answer_filename).write_bytes(  # noqa: SLF001
            _completed(item.answer_template_path)
        )
    (app._transport.answer_inbox / combined.transport.expected_answer_filename).write_bytes(  # noqa: SLF001
        _completed(combined.answer_template_path)
    )
    result = app.import_all_expected_answers()
    assert result.mode == "COMBINED"
    assert result.current_review_count == result.expected_count == 2
    assert result.found_count == result.imported_count == 2
    assert result.not_found_count == result.rejected_count == 0


def test_exact_inbox_rejects_traversal_symlink_and_nonregular_files(
    tmp_path: Path,
) -> None:
    transport = IntradayReviewV2Transport(
        question_outbox=(tmp_path / "questions").resolve(),
        answer_inbox=(tmp_path / "answers").resolve(),
    )
    transport.answer_inbox.mkdir()
    with pytest.raises(ReviewError, match=ReviewFailure.INPUT_INVALID.value):
        transport.read_expected_answer("../outside.json")
    expected = "KRONOS_INTRADAY_REVIEW_V2_20260905_120000_IST_ABCDEF12_ANSWERS.json"
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    (transport.answer_inbox / expected).symlink_to(outside)
    with pytest.raises(ReviewError, match=ReviewFailure.INTEGRITY_INVALID.value):
        transport.read_expected_answer(expected)
    (transport.answer_inbox / expected).unlink()
    (transport.answer_inbox / expected).mkdir()
    with pytest.raises(ReviewError, match=ReviewFailure.INTEGRITY_INVALID.value):
        transport.read_expected_answer(expected)


@pytest.fixture(params=(
    'KRONOS_INTRADAY_REVIEW_V2_20260906_120000_IST_ABCDEF12_ANSWERS.json',
    'KRONOS_INTRADAY_MCX_PAIRED_REVIEW_ABCDEF123456_ANSWERS.json',
), ids=('ordinary', 'paired'))
def secured_inbox(tmp_path, request):
    root = tmp_path.resolve() / 'configured' / 'parent' / 'answers'
    root.mkdir(parents=True)
    transport = IntradayReviewV2Transport(question_outbox=tmp_path.resolve() / 'questions', answer_inbox=root)
    return transport, request.param


@pytest.mark.parametrize('invalid', ('../escape.json', 'child/answer.json', '/outside/answer.json',
    'answer.json', 'KRONOS_INTRADAY_REVIEW_V2_20260906_120000_IST_ABCDEF12_ANSWERS.JSON'))
def test_inbox_lexical_filename_rejections(secured_inbox, invalid):
    transport, _ = secured_inbox
    with pytest.raises(ReviewError, match=ReviewFailure.INPUT_INVALID.value):
        transport.read_expected_answer(invalid)


def test_inbox_exact_file_ignores_sibling_and_unrelated_json(secured_inbox):
    transport, filename = secured_inbox
    sibling = transport.answer_inbox.parent / 'sibling'
    sibling.mkdir()
    (sibling / filename).write_bytes(b'{"outside":true}')
    (transport.answer_inbox / 'unrelated.json').write_bytes(b'{}')
    assert transport.read_expected_answer(filename) is None
    with pytest.raises(ReviewError): transport.read_expected_answer(str(sibling / filename))
    with pytest.raises(ReviewError): transport.read_expected_answer('../sibling/' + filename)
    payload = b'{"exact":true}'
    (transport.answer_inbox / filename).write_bytes(payload)
    assert transport.read_expected_answer(filename) == payload


@pytest.mark.parametrize('position', ('target_outside', 'target_inside', 'child', 'root', 'ancestor', 'nested_ancestors'))
def test_inbox_rejects_every_symlink_position(secured_inbox, position, tmp_path):
    transport, filename = secured_inbox
    inbox = transport.answer_inbox
    outside = tmp_path.resolve() / 'outside'
    outside.mkdir()
    (outside / filename).write_bytes(b'{"outside":true}')
    if position.startswith('target'):
        destination = outside / filename
        if position == 'target_inside':
            destination = inbox / 'other.json'; destination.write_bytes(b'{}')
        (inbox / filename).symlink_to(destination)
    elif position == 'child':
        (inbox / 'child').symlink_to(outside, target_is_directory=True)
        filename = 'child/' + filename
    elif position == 'root':
        inbox.rmdir(); inbox.symlink_to(outside, target_is_directory=True)
    else:
        moved = tmp_path.resolve() / 'moved-parent'
        inbox.parent.rename(moved)
        (moved / 'answers' / filename).write_bytes(b'{"escaped":true}')
        destination = moved
        if position == 'nested_ancestors':
            destination = tmp_path.resolve() / 'second-link'
            destination.symlink_to(moved, target_is_directory=True)
        inbox.parent.symlink_to(destination, target_is_directory=True)
    with pytest.raises(ReviewError): transport.read_expected_answer(filename)


@pytest.mark.parametrize('size', (0, 1_000_001))
def test_inbox_bounded_size_remains_enforced(secured_inbox, size, monkeypatch):
    import kronos.intraday.review_v2_transport as module
    # Exercise the configured parser limit without relying on its numeric policy.
    monkeypatch.setattr(module, 'MAX_ANSWER_BYTES', 1_000_000)
    transport, filename = secured_inbox
    (transport.answer_inbox / filename).write_bytes(b'x' * size)
    with pytest.raises(ReviewError): transport.read_expected_answer(filename)


@pytest.mark.parametrize('moment', ('ancestor_before_component_open', 'ancestor_before_file_open',
                                   'target_before_file_open', 'target_after_read', 'content_after_read'))
def test_inbox_symlink_swaps_and_file_changes_fail_closed(secured_inbox, moment, monkeypatch, tmp_path):
    import os
    transport, filename = secured_inbox
    inbox = transport.answer_inbox
    target = inbox / filename
    target.write_bytes(b'{"trusted":true}')
    outside = tmp_path.resolve() / 'outside-race'
    (outside / 'answers').mkdir(parents=True)
    external_payload = b'{"external":true}'
    (outside / 'answers' / filename).write_bytes(external_payload)
    original_open, original_read = os.open, os.read
    fired, observed_reads = [], []
    def swap_ancestor():
        inbox.parent.rename(tmp_path.resolve() / 'retained-parent')
        inbox.parent.symlink_to(outside, target_is_directory=True)
    def swap_target():
        target.unlink(); target.symlink_to(outside / 'answers' / filename)
    def race_open(path, flags, *args, **kwargs):
        if not fired and kwargs.get('dir_fd') is not None:
            if moment == 'ancestor_before_component_open' and path == 'parent':
                fired.append(True); swap_ancestor()
            elif path == filename and moment in ('ancestor_before_file_open', 'target_before_file_open'):
                fired.append(True)
                swap_ancestor() if moment.startswith('ancestor') else swap_target()
        return original_open(path, flags, *args, **kwargs)
    def race_read(descriptor, size):
        payload = original_read(descriptor, size); observed_reads.append(payload)
        if not fired and moment in ('target_after_read', 'content_after_read'):
            fired.append(True)
            if moment == 'target_after_read': swap_target()
            else: target.write_bytes(b'{"changed":true}')
        return payload
    monkeypatch.setattr(os, 'open', race_open)
    monkeypatch.setattr(os, 'read', race_read)
    with pytest.raises(ReviewError): transport.read_expected_answer(filename)
    assert fired
    assert external_payload not in observed_reads


@pytest.mark.parametrize('mode', ('individual', 'all_individual', 'combined'))
def test_all_inbox_import_modes_reject_ancestor_escape(tmp_path, mode):
    _, app = _fixture(tmp_path.resolve() / 'evidence', ('BDL', 'SRF'))
    candidates = app.snapshot().candidates
    transports = []
    for marker, candidate in enumerate(candidates, 1):
        app.upload_chart(candidate.cycle_identity, media_type='image/png', payload=_png(marker))
        transports.append(app.create_individual_question_transport(candidate.cycle_identity))
    if mode == 'combined': transports = [app.create_combined_question_transport()]
    inbox = tmp_path.resolve() / 'configured' / 'parent' / 'answers'
    inbox.mkdir(parents=True)
    for result in transports:
        (inbox / result.transport.expected_answer_filename).write_bytes(_completed(result.answer_template_path))
    moved = tmp_path.resolve() / 'outside-parent'
    inbox.parent.rename(moved)
    inbox.parent.symlink_to(moved, target_is_directory=True)
    app._transport.answer_inbox = inbox
    result = (app.import_expected_answer(candidates[0].cycle_identity)
              if mode == 'individual' else app.import_all_expected_answers())
    assert result.imported_count == result.already_imported_count == 0
    assert result.rejected_count == (1 if mode == 'individual' else 2)
    assert all(item.state == 'REJECTED' for item in result.members)
    assert not tuple((app.review_store.root / 'visual-evidence').glob('*.json'))
