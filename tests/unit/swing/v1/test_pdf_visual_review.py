from dataclasses import replace
from datetime import UTC, datetime, timedelta
from io import BytesIO
import json
from pathlib import Path

from PIL import Image, ImageDraw
from pypdf import PdfReader
import pytest
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from kronos.application.swing_native_review import NativeReviewWorkflow
from kronos.configuration.pdf_visual_review import PdfVisualReviewConfiguration
from kronos.swing.v1.evidence_store import LocalTradingViewEvidenceStore
from kronos.swing.v1.native_review import NativeReviewEvidenceStore
from kronos.swing.v1.native_discovery import (
    NativeAnchor,
    NativeDiscoveryStatus,
    discover_native_mtf,
)
from kronos.swing.v1.pdf_visual_review import (
    BEGIN_GOVERNED_ANSWER_DATA,
    END_GOVERNED_ANSWER_DATA,
    GOVERNED_ANSWER_SCHEMA,
    PDF_ANSWER_PROVIDER_IDENTITY,
    PDF_VISUAL_REVIEW_TRANSPORT_ID,
    PDF_VISUAL_REVIEW_TRANSPORT_VERSION,
    CANDIDATE_CHART_MAX_HEIGHT,
    CANDIDATE_CHART_MAX_WIDTH,
    VALID_OBSERVATION_EXAMPLE,
    AnswerImportState,
    PdfReviewRecordStore,
    PdfReviewTransportError,
    PdfVisualReviewTransport,
    _fit_image,
    _render_question_pdf,
    _validate_answer_payload,
)
from kronos.swing.v1.visual_evidence_v2 import (
    FROZEN_VISUAL_QUESTION_SET_V2,
    VISUAL_QUESTION_SET_V2_ID,
    VISUAL_QUESTION_SET_V2_VERSION,
    VisualEvidenceV2Observation,
    VisualEvidenceSubjectKind,
    VisualLevelAvailability,
    VisualObservationStatus,
    VisualQuestionV2,
    VisualTimeframe,
    build_visual_evidence_v2_request,
    visual_evidence_v2_response_to_dict,
)
from tests.unit.swing.v1.test_native_review import _evidence_run
from tests.unit.swing.v1.test_native_review_mcx_reference import _run_with_probables
from tests.unit.swing.v1.test_visual_evidence_v2 import _response


NOW = datetime(2026, 8, 16, 15, 35, 30, tzinfo=UTC)


def _png(instrument: str = "SAMPLE") -> bytes:
    stream = BytesIO()
    image = Image.new("RGB", (1600, 900), "#071724")
    draw = ImageDraw.Draw(image)
    draw.text((28, 18), f"{instrument}  |  KRONOS COMPOSITE", fill="#f4f7fa")
    for index, timeframe in enumerate(("1W", "1D", "4H", "1H")):
        left = 20 + (index % 2) * 790
        top = 55 + (index // 2) * 420
        right, bottom = left + 770, top + 400
        draw.rectangle((left, top, right, bottom), outline="#2d6078", width=2)
        draw.text((left + 12, top + 10), f"{instrument} {timeframe}", fill="#18c3ef")
        for offset in range(1, 6):
            y = top + offset * 60
            draw.line((left + 10, y, right - 10, y), fill="#17394a")
        for candle in range(22):
            x = left + 28 + candle * 31
            midpoint = bottom - 65 - ((candle * 17 + index * 13) % 220)
            colour = "#3bd58f" if candle % 3 else "#ef6674"
            draw.line((x, midpoint - 24, x, midpoint + 26), fill=colour, width=2)
            draw.rectangle((x - 6, midpoint - 12, x + 6, midpoint + 13), fill=colour)
        draw.text((left + 12, bottom - 58), "CPR 127.50 | PDH 130.00 | PDL 124.00", fill="#f0ce6a")
        draw.text((left + 12, bottom - 35), "PINE: TREND / ACCEPTANCE / MOMENTUM", fill="#c7d3dc")
    image.save(stream, format="PNG")
    return stream.getvalue()


def _workflow(tmp_path: Path, *, candidate_count: int = 1):  # type: ignore[no-untyped-def]
    facts, run, probable = _evidence_run()
    if candidate_count > 1:
        replacements = []
        for index, source in enumerate(run.assessments[:candidate_count], 1):
            replacements.append(replace(
                source,
                direction=probable.direction,
                weekly_state=probable.weekly_state,
                daily_state=probable.daily_state,
                four_hour_state=probable.four_hour_state,
                one_hour_state=probable.one_hour_state,
                status=probable.status,
                context_kind=probable.context_kind,
                opportunity_identity=probable.opportunity_identity,
                operative_anchor=NativeAnchor(
                    probable.operative_anchor.anchor_type,
                    probable.operative_anchor.price,
                    probable.operative_anchor.source_boundary,
                ),
                reason_codes=("PDF_REVIEW_TEST_PROBABLE",),
                result_sha256=f"{index:064x}",
            ))
        run = replace(
            run,
            assessments=(*replacements, *run.assessments[candidate_count:]),
            result_sha256="c" * 64,
        )
    configuration = PdfVisualReviewConfiguration(
        tmp_path / "KRONOS QUESTIONS", tmp_path / "CHATGPT ANSWERS"
    )
    transport = PdfVisualReviewTransport(
        configuration,
        PdfReviewRecordStore(tmp_path / "records"),
        clock=lambda: NOW,
    )
    workflow = NativeReviewWorkflow(
        NativeReviewEvidenceStore(tmp_path / "native"),
        chart_store=LocalTradingViewEvidenceStore(tmp_path / "charts", clock=lambda: NOW),
        pdf_transport=transport,
        clock=lambda: NOW,
    )
    workflow.prepare(run, facts)
    for requirement in workflow.snapshot().requirements:
        workflow.upload_chart(
            instrument=requirement.canonical_instrument,
            content_type="image/png",
            original_bytes=_png(requirement.canonical_instrument),
        )
    return workflow, transport


def _mcx_workflow(tmp_path: Path):  # type: ignore[no-untyped-def]
    facts, run = _run_with_probables("GOLDM")
    configuration = PdfVisualReviewConfiguration(
        tmp_path / "KRONOS QUESTIONS", tmp_path / "CHATGPT ANSWERS"
    )
    transport = PdfVisualReviewTransport(
        configuration,
        PdfReviewRecordStore(tmp_path / "records"),
        clock=lambda: NOW,
    )
    workflow = NativeReviewWorkflow(
        NativeReviewEvidenceStore(tmp_path / "native"),
        chart_store=LocalTradingViewEvidenceStore(
            tmp_path / "charts", clock=lambda: NOW
        ),
        pdf_transport=transport,
        clock=lambda: NOW,
    )
    workflow.prepare(run, facts)
    workflow.upload_chart(
        instrument="GOLDM",
        content_type="image/png",
        original_bytes=_png("GOLDM + COMEX:GC1!"),
    )
    return workflow, transport


def _new_run_with_probables(facts, indexes: tuple[int, ...]):  # type: ignore[no-untyped-def]
    run_identity = "SWING-RUN-" + "D" * 32
    current_facts = replace(
        facts,
        run_identity=run_identity,
        observed_at=facts.observed_at + timedelta(minutes=1),
        instruments=tuple(
            replace(item, reference_facts=()) for item in facts.instruments
        ),
    )
    base = discover_native_mtf(current_facts)
    template = _evidence_run()[2]
    assessments = []
    for index, source in enumerate(base.assessments):
        if index not in indexes:
            assessments.append(source)
            continue
        boundary = current_facts.instrument(source.canonical_instrument).fact(
            next(
                item.timeframe
                for item in current_facts.instrument(source.canonical_instrument).timeframes
                if item.timeframe.value == "4H"
            )
        ).observation_boundary
        assessments.append(replace(
            source,
            direction=template.direction,
            weekly_state=template.weekly_state,
            daily_state=template.daily_state,
            four_hour_state=template.four_hour_state,
            one_hour_state=template.one_hour_state,
            status=NativeDiscoveryStatus.PROBABLE,
            context_kind=template.context_kind,
            opportunity_identity=template.opportunity_identity,
            operative_anchor=NativeAnchor(
                template.operative_anchor.anchor_type,
                template.operative_anchor.price,
                boundary,
            ),
            reason_codes=("PDF_REVIEW_REFRESH_PROBABLE",),
            result_sha256=f"{index + 100:064x}",
        ))
    return current_facts, replace(
        base,
        assessments=tuple(assessments),
        result_sha256="d" * 64,
    )


def _payload(workflow: NativeReviewWorkflow, record):  # type: ignore[no-untyped-def]
    snapshot = workflow.snapshot()
    requirement = snapshot.requirements[0]
    package = next(
        item for item in snapshot.chart_packages
        if item.binding.subject_kind == "NATIVE"
    )
    revision = package.active_revisions[0]
    original = workflow.active_chart(
        instrument=requirement.canonical_instrument, sha256=revision.sha256
    )[1]
    candidate = record.candidates[0]

    def serialized_responses(subject_kind, identity, timeframes):  # type: ignore[no-untyped-def]
        responses = []
        for timeframe_value in timeframes:
            timeframe = VisualTimeframe(timeframe_value)
            fact = next(
                item for item in requirement.thesis.timeframe_facts
                if item.timeframe.value == timeframe.value
            )
            request = build_visual_evidence_v2_request(
                requirement,
                timeframe=timeframe,
                observation_boundary=fact.observation_boundary,
                chart_identity=identity,
                content_type=revision.content_type,
                original_image=original,
                request_timestamp=NOW,
                subject_kind=subject_kind,
            )
            response = replace(
                _response(request),
                provider_identity=PDF_ANSWER_PROVIDER_IDENTITY,
                model_identity="SPONSOR_CHART_ANALYST",
                source_provenance=(
                    PDF_VISUAL_REVIEW_TRANSPORT_ID,
                    record.review_pack_id,
                ),
            )
            serialized = visual_evidence_v2_response_to_dict(response)
            for field in (
                "provider_identity",
                "native_assessment_sha256",
                "source_provenance",
                "schema",
                "authority",
            ):
                serialized.pop(field)
            for observation in serialized["observations"]:
                observation.pop("provenance")
            responses.append(serialized)
        return responses

    responses = serialized_responses(
        VisualEvidenceSubjectKind.NATIVE,
        package.binding.chart_subject_identity,
        candidate.expected_timeframes,
    )
    reference_responses = (
        []
        if candidate.reference_symbol is None
        else serialized_responses(
            VisualEvidenceSubjectKind.REFERENCE,
            candidate.reference_symbol,
            candidate.reference_expected_timeframes,
        )
    )
    return {
        "schema": GOVERNED_ANSWER_SCHEMA,
        "manifest": {
            "review_pack_id": record.review_pack_id,
            "native_run_identity": record.native_run_identity,
            "question_set_identity": VISUAL_QUESTION_SET_V2_ID,
            "question_set_version": VISUAL_QUESTION_SET_V2_VERSION,
            "transport_policy_identity": PDF_VISUAL_REVIEW_TRANSPORT_ID,
            "transport_policy_version": PDF_VISUAL_REVIEW_TRANSPORT_VERSION,
            "candidate_population": [{
                "canonical_instrument": candidate.canonical_instrument,
                "chart_revision_sha256": candidate.chart_revision_sha256,
            }],
        },
        "candidates": [{
            "canonical_instrument": candidate.canonical_instrument,
            "observed_chart_instrument": candidate.canonical_instrument,
            "chart_revision_sha256": candidate.chart_revision_sha256,
            "responses": responses,
            **(
                {
                    "observed_reference_chart_instrument": (
                        candidate.reference_symbol
                    ),
                    "reference_responses": reference_responses,
                }
                if candidate.reference_symbol is not None else {}
            ),
        }],
    }


def _answer_pdf(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(path), pagesize=A4)
    y = A4[1] - 30
    pdf.setFont("Courier", 4)
    lines = [BEGIN_GOVERNED_ANSWER_DATA, *json.dumps(
        payload, indent=1, sort_keys=True, separators=(",", ": ")
    ).splitlines(), END_GOVERNED_ANSWER_DATA]
    for line in lines:
        if y < 25:
            pdf.showPage()
            pdf.setFont("Courier", 4)
            y = A4[1] - 30
        pdf.drawString(18, y, line)
        y -= 5
    pdf.save()


def _pdf_pages(path: str | Path) -> tuple[str, ...]:
    return tuple(page.extract_text() or "" for page in PdfReader(str(path)).pages)


def test_question_pack_is_immutable_self_contained_and_sha_bound(tmp_path: Path) -> None:
    workflow, _ = _workflow(tmp_path)
    record = workflow.generate_review_pack()

    assert record.question_filename == "KRONOS_REVIEW_20260816_210530_IST_QUESTIONS.pdf"
    assert record.expected_answer_filename == "KRONOS_REVIEW_20260816_210530_IST_ANSWERS.pdf"
    assert record.candidates[0].expected_timeframes == ("1W", "1D", "4H", "1H")
    assert Path(record.question_path).is_file()
    text = " ".join("\n".join(_pdf_pages(record.question_path)).split())
    for required in (
        "KRONOS SWING CHART ANALYST", "Independently report OBSERVED_CHART_INSTRUMENT",
        "FROZEN VISUAL QUESTION SET V2", "Q3 reports only material visual S/R",
        "Q10 is a strict escape hatch", BEGIN_GOVERNED_ANSWER_DATA,
        "LEVEL_UNAVAILABLE", "NOT_APPLICABLE", "ambiguity_reason",
        record.review_pack_id, record.expected_answer_filename,
        "Do not reproduce or invent KRONOS internal provenance hashes",
    ):
        assert required in text
    assert "native_assessment_sha256" not in text
    assert "source_provenance" not in text
    assert '"provenance"' not in text
    with pytest.raises(PdfReviewTransportError, match="FILENAME_EXISTS"):
        # A fresh transport at the identical frozen clock cannot overwrite the pack.
        workflow._review_pack = None  # type: ignore[attr-defined]
        workflow.generate_review_pack()


def test_goldm_one_composite_binds_native_and_reference_and_pack_prints_both(
    tmp_path: Path,
) -> None:
    workflow, _ = _mcx_workflow(tmp_path)
    packages = workflow.snapshot().chart_packages
    native = next(item for item in packages if item.binding.subject_kind == "NATIVE")
    reference = next(
        item for item in packages if item.binding.subject_kind == "REFERENCE"
    )
    assert len(native.active_revisions) == len(reference.active_revisions) == 1
    native_revision = native.active_revisions[0]
    reference_revision = reference.active_revisions[0]
    assert native_revision.sha256 == reference_revision.sha256
    assert native_revision.relative_path == reference_revision.relative_path

    record = workflow.generate_review_pack()
    pages = _pdf_pages(record.question_path)
    assert len(pages) == 6
    assert "ANCHOR:" in pages[2]
    candidate = record.candidates[0]
    assert candidate.expected_timeframes == ("1H",)
    assert candidate.reference_subject_identity == "COMEX Gold"
    assert candidate.reference_market == "COMEX"
    assert candidate.reference_symbol == "COMEX:GC1!"
    assert candidate.reference_expected_timeframes == ("1D", "4H", "1H")
    text = " ".join("\n".join(pages).split())
    assert "NATIVE SUBJECT: MCX GOLDM (1H)" in text
    assert "REFERENCE SUBJECT: COMEX Gold / COMEX:GC1! (1D / 4H / 1H)" in text
    assert "ONE SHARED REVISION" in text
    assert '"subject_kind": "REFERENCE_EVIDENCE_SUBJECT"' in text


def test_goldm_answer_imports_separate_reference_observations_as_typed_result(
    tmp_path: Path,
) -> None:
    workflow, transport = _mcx_workflow(tmp_path)
    record = workflow.generate_review_pack()
    answer = transport.configuration.answer_directory / record.expected_answer_filename
    _answer_pdf(answer, _payload(workflow, record))

    imported, readiness = workflow.upload_review_answer()

    assert imported.consumed
    assert len(readiness) == 1
    snapshot = workflow.snapshot()
    assert len(tuple(
        item for item in snapshot.visual_v2_results
        if item.subject_kind is VisualEvidenceSubjectKind.NATIVE
    )) == 1
    assert len(tuple(
        item for item in snapshot.visual_v2_results
        if item.subject_kind is VisualEvidenceSubjectKind.REFERENCE
    )) == 3
    result = snapshot.reference_results[0]
    assert result.status.value == "RECEIVED"
    assert result.binding_status == "SAME_RUN_REFERENCE_BOUND"
    assert result.reason == (
        "REFERENCE_VISUAL_EVIDENCE_RECEIVED_RECONCILIATION_PENDING"
    )


def test_corrected_answer_cycle_preserves_old_evidence_and_restores_current_goldm_reference(
    tmp_path: Path,
) -> None:
    workflow, transport = _mcx_workflow(tmp_path)
    first = workflow.generate_review_pack()
    first_answer = transport.configuration.answer_directory / first.expected_answer_filename
    _answer_pdf(first_answer, _payload(workflow, first))
    workflow.upload_review_answer()
    first_hashes = {
        item.evidence_sha256 for item in workflow.snapshot().visual_v2_results
    }

    transport._clock = lambda: NOW + timedelta(seconds=1)  # type: ignore[attr-defined]
    second = workflow.generate_review_pack()
    second_answer = transport.configuration.answer_directory / second.expected_answer_filename
    _answer_pdf(second_answer, _payload(workflow, second))
    imported, _ = workflow.upload_review_answer()

    assert imported.state is AnswerImportState.REVIEW_EVIDENCE_IMPORTED
    assert second.review_pack_id != first.review_pack_id
    current = workflow.snapshot()
    assert current.reference_results[0].status.value == "RECEIVED"
    assert current.reference_results[0].binding_status == "SAME_RUN_REFERENCE_BOUND"
    assert all(
        second.review_pack_id in item.source_provenance
        for item in current.visual_v2_results
    )
    assert first_hashes.isdisjoint(
        {item.evidence_sha256 for item in current.visual_v2_results}
    )

    facts, run = _run_with_probables("GOLDM")
    restored = NativeReviewWorkflow(
        NativeReviewEvidenceStore(tmp_path / "native"),
        chart_store=LocalTradingViewEvidenceStore(
            tmp_path / "charts", clock=lambda: NOW
        ),
        pdf_transport=transport,
        clock=lambda: NOW,
    ).restore(run, facts)
    assert restored.refresh_status == "CURRENT REVIEW RESTORED"
    assert restored.reference_results == current.reference_results
    assert restored.visual_v2_results == current.visual_v2_results
    assert restored.readiness_records == current.readiness_records
    assert all(
        second.review_pack_id in item.source_provenance
        for item in restored.visual_v2_results
    )


@pytest.mark.parametrize("mismatch", ("identity", "revision", "run", "masquerade"))
def test_goldm_reference_answer_binding_fails_closed(
    tmp_path: Path, mismatch: str,
) -> None:
    workflow, _ = _mcx_workflow(tmp_path)
    record = workflow.generate_review_pack()
    payload = _payload(workflow, record)
    candidate = payload["candidates"][0]
    responses = candidate["reference_responses"]
    if mismatch == "identity":
        candidate["observed_reference_chart_instrument"] = "COMEX:SI1!"
    elif mismatch == "revision":
        responses[0]["chart_revision_sha256"] = "f" * 64
    elif mismatch == "run":
        responses[0]["native_run_identity"] = "SWING-RUN-" + "F" * 32
    else:
        responses[0]["subject_kind"] = "NATIVE_ANALYTICAL_SUBJECT"
        responses[0]["subject_identity"] = "GOLDM"
        responses[0]["reference_market"] = None
        responses[0]["reference_symbol"] = None
    with pytest.raises(
        PdfReviewTransportError,
        match="REFERENCE_(IDENTITY|BINDING|ANSWER)",
    ):
        _validate_answer_payload(record, payload)


def test_seven_candidates_are_packaged_canonically_a_to_z(tmp_path: Path) -> None:
    workflow, _ = _workflow(tmp_path, candidate_count=7)
    original = tuple(item.canonical_instrument for item in workflow.snapshot().requirements)
    record = workflow.generate_review_pack()
    ordered = tuple(item.canonical_instrument for item in record.candidates)

    assert ordered == tuple(sorted(original))
    assert set(ordered) == set(original)
    text = "\n".join(page.extract_text() or "" for page in PdfReader(record.question_path).pages)
    positions = [text.index(instrument, text.index("COMPOSITE TRADINGVIEW CHART") if False else 0) for instrument in ordered]
    assert positions == sorted(positions)


def test_seven_candidate_pack_is_eleven_pages_with_one_candidate_per_page(tmp_path: Path) -> None:
    workflow, _ = _workflow(tmp_path, candidate_count=7)
    expected = tuple(item.canonical_instrument for item in workflow.snapshot().requirements)
    record = workflow.generate_review_pack()
    pages = _pdf_pages(record.question_path)

    assert len(pages) == 11
    assert "GOVERNED REVIEW INSTRUCTIONS" in pages[0]
    assert "FROZEN VISUAL QUESTION SET V2" in pages[1]
    assert "CANONICAL GOVERNED ANSWER CONTRACT" in pages[9]
    assert "ANSWER FILE AND FINAL OPERATING INSTRUCTIONS" in pages[10]
    for page, instrument in zip(pages[2:9], sorted(expected), strict=True):
        assert f"EXPECTED {instrument}" in page
        assert sum(f"EXPECTED {candidate}" in page for candidate in expected) == 1


def test_candidate_chart_is_materially_larger_and_facts_are_compact(tmp_path: Path) -> None:
    current = _fit_image(_png(), CANDIDATE_CHART_MAX_WIDTH, CANDIDATE_CHART_MAX_HEIGHT)
    previous = _fit_image(_png(), 180 * mm, 150 * mm)
    assert current.drawWidth * current.drawHeight > previous.drawWidth * previous.drawHeight * 1.30

    workflow, _ = _workflow(tmp_path)
    record = workflow.generate_review_pack()
    candidate_page = _pdf_pages(record.question_path)[2]
    assert all(value in candidate_page for value in (
        "TF", "OHLC / VOLUME", "SMA20", "SMA50", "SMA200", "KEY STRUCTURE", "ANCHOR",
    ))
    assert "provider_identity" not in candidate_page
    assert "calendar_identity" not in candidate_page
    assert "session_identity" not in candidate_page
    assert "observation_boundary" not in candidate_page
    assert "131.60750000000002" not in candidate_page


def test_ampersand_symbol_renders_exactly(tmp_path: Path) -> None:
    workflow, _ = _workflow(tmp_path)
    snapshot = workflow.snapshot()
    requirement = snapshot.requirements[0]
    package = snapshot.chart_packages[0]
    revision = package.active_revisions[0]
    image = _png("M&M")
    digest = __import__("hashlib").sha256(image).hexdigest()
    thesis = replace(requirement.thesis, canonical_instrument="M&M")
    requirement = replace(requirement, thesis=thesis)
    binding = replace(
        package.binding, canonical_instrument="M&M", chart_subject_identity="M&M",
    )
    revision = replace(
        revision, canonical_instrument="M&M", sha256=digest, byte_count=len(image),
    )
    package = replace(
        package, binding=binding, revisions=(revision,), active_revisions=(revision,),
    )
    path = tmp_path / "ampersand.pdf"
    manifest = {
        "review_pack_id": "KRONOS-REVIEW-AMPERSAND",
        "native_run_identity": requirement.native_run_identity,
        "question_set_identity": VISUAL_QUESTION_SET_V2_ID,
        "question_set_version": VISUAL_QUESTION_SET_V2_VERSION,
        "transport_policy_identity": PDF_VISUAL_REVIEW_TRANSPORT_ID,
        "transport_policy_version": PDF_VISUAL_REVIEW_TRANSPORT_VERSION,
        "creation_timestamp": NOW.isoformat(),
        "observation_boundary": NOW.isoformat(),
        "candidate_count": 1,
        "expected_answer_filename": "KRONOS_REVIEW_AMPERSAND_ANSWERS.pdf",
        "candidates": [{
            "canonical_instrument": "M&M",
            "native_direction": thesis.direction.value,
            "native_opportunity_identity": thesis.opportunity_identity.value,
            "native_assessment_sha256": thesis.native_assessment_sha256,
            "chart_identity": "M&M",
            "chart_revision_sha256": digest,
            "expected_timeframes": ["1W", "1D", "4H", "1H"],
        }],
    }
    _render_question_pdf(path, manifest, ((requirement, package, revision, image),))
    text = "\n".join(_pdf_pages(path))
    assert "M&M" in text
    assert "M&M;" not in text


def test_pack_prints_exact_coverage_q10_numeric_and_bias_contract(tmp_path: Path) -> None:
    workflow, _ = _workflow(tmp_path)
    record = workflow.generate_review_pack()
    text = "\n".join(_pdf_pages(record.question_path))
    assert (
        "Every timeframe response MUST contain Q1 through Q10 exactly once and in order."
        in text
    )
    assert "Where routing is not applicable, return the governed NOT_APPLICABLE representation" in text
    assert "Q10 observation = NONE requires why_not_covered_elsewhere = null" in text
    assert '"observation":"NONE","why_not_covered_elsewhere":"No additional fact met the escape hatch."}' in text
    assert '"observation":"NONE","why_not_covered_elsewhere":null}' in text
    assert "POINT: price = 127.50, zone_low = null, zone_high = null" in text
    assert "ZONE: price = null, zone_low = 127.00, zone_high = 128.00" in text
    assert "LEVEL_UNAVAILABLE: all three numeric fields = null" in text
    assert (
        "a confident finding that no additional material S/R exists is "
        "OBSERVED / NONE / NOT_APPLICABLE"
        in text.replace("\n", " ")
    )
    assert "Use NOT_VISIBLE only when the chart does not permit reliable determination." in text
    assert '"observation_status":"OBSERVED","observation":"NONE"' in text
    assert (
        "The supplied Native direction and opportunity are context only. Do not seek confirming evidence. "
        "Report supportive, contradictory, neutral, incomplete, ambiguous, and adverse visible facts with "
        "equal priority. Do not force visual evidence to agree with the Native thesis."
        in text.replace("\n", " ")
    )


def test_printed_observation_example_and_numeric_forms_match_frozen_domain() -> None:
    def construct(value: dict[str, object]) -> VisualEvidenceV2Observation:
        return VisualEvidenceV2Observation(
            question_id=VisualQuestionV2(value["question_id"]),
            timeframe=VisualTimeframe(value["timeframe"]),
            observation_status=VisualObservationStatus(value["observation_status"]),
            observation=value["observation"],
            level_availability=VisualLevelAvailability(value["level_availability"]),
            price=value["price"], zone_low=value["zone_low"], zone_high=value["zone_high"],
            visible_basis=value["visible_basis"],
            source_chart_identity=value["source_chart_identity"],
            source_chart_revision=value["source_chart_revision"],
            confidence_in_extraction=value["confidence_in_extraction"],
            ambiguity_reason=value["ambiguity_reason"],
            provenance=tuple(value.get(
                "provenance", (PDF_VISUAL_REVIEW_TRANSPORT_ID,)
            )),
            why_not_covered_elsewhere=value["why_not_covered_elsewhere"],
        )

    assert construct(VALID_OBSERVATION_EXAMPLE).observation == "NONE"
    base = dict(VALID_OBSERVATION_EXAMPLE)
    base.update(
        question_id="VISUAL_OBSTACLE_EVIDENCE", observation="VISIBLE LEVEL",
        level_availability="AVAILABLE", why_not_covered_elsewhere=None,
    )
    assert construct({**base, "price": 127.50}).price == 127.50
    assert construct({**base, "zone_low": 127.00, "zone_high": 128.00}).zone_high == 128.00
    unavailable = {**base, "observation_status": "NOT_VISIBLE", "observation": "LEVEL_UNAVAILABLE",
                   "level_availability": "LEVEL_UNAVAILABLE", "price": None,
                   "zone_low": None, "zone_high": None}
    assert construct(unavailable).level_availability is VisualLevelAvailability.LEVEL_UNAVAILABLE
    with pytest.raises(ValueError, match="VISUAL_V2_OBSERVATION_INVALID"):
        construct({**base, "price": 127.50, "zone_low": 127.00, "zone_high": 128.00})


def test_validator_requires_every_frozen_question_once_and_in_order(tmp_path: Path) -> None:
    workflow, _ = _workflow(tmp_path)
    record = workflow.generate_review_pack()
    payload = _payload(workflow, record)
    response = payload["candidates"][0]["responses"][0]
    question_ids = tuple(item["question_id"] for item in response["observations"])
    assert question_ids == tuple(item.value for item in FROZEN_VISUAL_QUESTION_SET_V2)
    for observations in (response["observations"][:-1], tuple(reversed(response["observations"]))):
        mutated = dict(response)
        mutated["observations"] = observations
        with pytest.raises(ValueError, match="VISUAL_V2_RESPONSE_INVALID"):
            from kronos.swing.v1.visual_evidence_v2 import visual_evidence_v2_response_from_dict
            visual_evidence_v2_response_from_dict(mutated)


def test_complete_machine_manifest_remains_persisted(tmp_path: Path) -> None:
    workflow, _ = _workflow(tmp_path)
    record = workflow.generate_review_pack()
    persisted = tuple((tmp_path / "records" / "review-packs").glob("*.json"))
    assert len(persisted) == 1
    payload = json.loads(persisted[0].read_text())
    serialized = json.dumps(payload, sort_keys=True)
    assert record.review_pack_id in serialized
    assert record.native_run_identity in serialized
    assert record.question_set_identity in serialized
    assert record.transport_policy_identity in serialized
    assert record.candidates[0].chart_revision_sha256 in serialized


def test_new_chart_revision_supersedes_pack_without_mutating_it(tmp_path: Path) -> None:
    workflow, _ = _workflow(tmp_path)
    record = workflow.generate_review_pack()
    instrument = workflow.snapshot().requirements[0].canonical_instrument
    original_bytes = Path(record.question_path).read_bytes()

    workflow.upload_chart(
        instrument=instrument,
        content_type="image/png",
        original_bytes=_png(instrument + "-NEW"),
    )

    assert workflow.snapshot().review_pack_superseded is True
    assert Path(record.question_path).read_bytes() == original_bytes
    assert workflow._pdf_transport.record_store.load_review_packs() == (record,)  # type: ignore[union-attr]


def test_individual_pack_contains_only_selected_candidate(tmp_path: Path) -> None:
    workflow, _ = _workflow(tmp_path, candidate_count=3)
    selected = workflow.snapshot().requirements[1].canonical_instrument

    record = workflow.generate_review_pack(selected)

    assert tuple(item.canonical_instrument for item in record.candidates) == (selected,)
    assert workflow.snapshot().review_pack_scope == "INDIVIDUAL"
    assert workflow.snapshot().review_pack_skipped == ()


def test_all_pack_includes_chart_complete_candidates_and_reports_skipped(
    tmp_path: Path,
) -> None:
    workflow, _ = _workflow(tmp_path, candidate_count=3)
    missing = workflow.snapshot().requirements[-1].canonical_instrument
    workflow.remove_chart(instrument=missing)

    record = workflow.generate_review_pack()

    assert tuple(item.canonical_instrument for item in record.candidates) == tuple(
        sorted(
            item.canonical_instrument
            for item in workflow.snapshot().requirements
            if item.canonical_instrument != missing
        )
    )
    assert workflow.snapshot().review_pack_scope == "ALL_ELIGIBLE"
    assert workflow.snapshot().review_pack_skipped == ((missing, "CHART REQUIRED"),)


def test_rejected_pack_can_be_regenerated_and_old_artifacts_remain_immutable(
    tmp_path: Path,
) -> None:
    workflow, transport = _workflow(tmp_path)
    times = iter((
        NOW,
        NOW + timedelta(milliseconds=500),
        NOW + timedelta(seconds=1),
    ))
    transport._clock = lambda: next(times)  # type: ignore[attr-defined]
    first = workflow.generate_review_pack()
    payload = _payload(workflow, first)
    payload["candidates"][0]["observed_chart_instrument"] = "WRONG"
    _answer_pdf(
        transport.configuration.answer_directory / first.expected_answer_filename,
        payload,
    )
    with pytest.raises(PdfReviewTransportError, match="CHART_IDENTITY_MISMATCH"):
        workflow.upload_review_answer()
    first_bytes = Path(first.question_path).read_bytes()

    second = workflow.generate_review_pack()

    assert first.review_pack_id != second.review_pack_id
    assert first.question_filename != second.question_filename
    assert Path(first.question_path).read_bytes() == first_bytes
    assert len(transport.record_store.load_review_packs()) == 2
    assert transport.record_store.load_current()[0] == second  # type: ignore[index]
    assert workflow.snapshot().review_pack_record == second


def test_current_pack_selection_survives_restart_without_mtime_guessing(
    tmp_path: Path,
) -> None:
    workflow, transport = _workflow(tmp_path)
    selected = workflow.snapshot().requirements[-1].canonical_instrument
    record = workflow.generate_review_pack(selected)
    facts, run, _ = _evidence_run()

    restored = NativeReviewWorkflow(
        NativeReviewEvidenceStore(tmp_path / "native"),
        chart_store=LocalTradingViewEvidenceStore(tmp_path / "charts", clock=lambda: NOW),
        pdf_transport=transport,
        clock=lambda: NOW,
    ).restore(run, facts)

    assert restored.review_pack_record == record
    assert restored.review_pack_scope == "INDIVIDUAL"
    assert restored.review_pack_superseded is False


def test_refresh_same_population_is_non_mutating_and_creates_no_pack(
    tmp_path: Path,
) -> None:
    workflow, transport = _workflow(tmp_path)
    facts, run, _ = _evidence_run()
    before = workflow.snapshot()

    after = workflow.refresh(run, facts)

    assert after.requirements == before.requirements
    assert after.chart_packages == before.chart_packages
    assert after.refresh_status == "CURRENT REVIEW UNCHANGED"
    assert transport.record_store.load_review_packs() == ()


def test_refresh_new_run_rebuilds_current_population_and_supersedes_old_pack(
    tmp_path: Path,
) -> None:
    workflow, transport = _workflow(tmp_path, candidate_count=2)
    old_record = workflow.generate_review_pack()
    old_candidates = {
        item.canonical_instrument for item in workflow.snapshot().requirements
    }
    facts, _, _ = _evidence_run()
    current_facts, current_run = _new_run_with_probables(facts, (1, 2))

    refreshed = workflow.refresh(current_run, current_facts)

    current_candidates = tuple(
        item.canonical_instrument for item in refreshed.requirements
    )
    assert set(current_candidates) != old_candidates
    assert refreshed.native_run_identity == current_run.run_identity
    assert refreshed.review_pack_record == old_record
    assert refreshed.review_pack_superseded is True
    assert len(transport.record_store.load_review_packs()) == 1
    assert all(package.missing_required_timeframes for package in refreshed.chart_packages)
    with pytest.raises(PdfReviewTransportError, match="REVIEW_PACK_SUPERSEDED"):
        workflow.upload_review_answer()


def test_valid_answer_imports_v2_layer2_readiness_and_is_idempotent(tmp_path: Path) -> None:
    workflow, _ = _workflow(tmp_path)
    record = workflow.generate_review_pack()
    payload = _payload(workflow, record)
    answer = Path(record.question_path).parent.parent / "CHATGPT ANSWERS" / record.expected_answer_filename
    _answer_pdf(answer, payload)

    imported, readiness = workflow.upload_review_answer()
    assert imported.state is AnswerImportState.REVIEW_EVIDENCE_IMPORTED
    assert len(workflow.snapshot().visual_v2_results) == 4
    assert len(workflow.snapshot().layer2_records) == 1
    assert len(readiness) == 1
    counts = (
        len(workflow.snapshot().visual_v2_results),
        len(workflow.snapshot().layer2_records),
        len(workflow.snapshot().readiness_records),
    )
    repeated, _ = workflow.upload_review_answer()
    assert repeated.evidence_import_identity == imported.evidence_import_identity
    assert counts == (
        len(workflow.snapshot().visual_v2_results),
        len(workflow.snapshot().layer2_records),
        len(workflow.snapshot().readiness_records),
    )


def test_kronos_injects_native_sha_and_generated_provenance(tmp_path: Path) -> None:
    workflow, _ = _workflow(tmp_path)
    record = workflow.generate_review_pack()
    payload = _payload(workflow, record)
    for response in payload["candidates"][0]["responses"]:
        response["provider_identity"] = "UNTRUSTED_OVERRIDE"
        response["source_provenance"] = ["UNTRUSTED_OVERRIDE"]
        for observation in response["observations"]:
            observation["provenance"] = ["UNTRUSTED_OVERRIDE"]

    validated = _validate_answer_payload(record, payload)

    assert all(
        response.provider_identity == PDF_ANSWER_PROVIDER_IDENTITY
        and
        response.native_assessment_sha256
        == record.candidates[0].native_assessment_sha256
        and response.source_provenance
        == (PDF_VISUAL_REVIEW_TRANSPORT_ID, record.review_pack_id)
        and all(
            observation.provenance
            == (PDF_VISUAL_REVIEW_TRANSPORT_ID, record.review_pack_id)
            for observation in response.observations
        )
        for response in validated[0].responses
    )


def test_answer_cannot_override_authoritative_native_sha(tmp_path: Path) -> None:
    workflow, _ = _workflow(tmp_path)
    record = workflow.generate_review_pack()
    payload = _payload(workflow, record)
    for response in payload["candidates"][0]["responses"]:
        response["native_assessment_sha256"] = "f" * 64

    validated = _validate_answer_payload(record, payload)

    assert all(
        response.native_assessment_sha256
        == record.candidates[0].native_assessment_sha256
        for response in validated[0].responses
    )


def test_invalid_review_pack_native_binding_fails_closed(tmp_path: Path) -> None:
    workflow, _ = _workflow(tmp_path)
    record = workflow.generate_review_pack()
    payload = _payload(workflow, record)
    object.__setattr__(record.candidates[0], "native_assessment_sha256", "invalid")

    with pytest.raises(
        PdfReviewTransportError, match="NATIVE_ASSESSMENT_BINDING_INVALID"
    ):
        _validate_answer_payload(record, payload)


def test_rejected_answer_artifact_can_receive_new_attempt_and_then_import(
    tmp_path: Path,
) -> None:
    workflow, transport = _workflow(tmp_path)
    record = workflow.generate_review_pack()
    payload = _payload(workflow, record)
    answer = transport.configuration.answer_directory / record.expected_answer_filename
    _answer_pdf(answer, payload)
    times = iter((NOW, NOW + timedelta(seconds=1)))
    transport._clock = lambda: next(times)  # type: ignore[attr-defined]

    first = transport.record_rejection(
        record, answer, "PREVIOUS_VALIDATOR_REJECTED"
    )
    imported, _ = workflow.upload_review_answer()

    attempts = transport.record_store.load_answer_imports(record.review_pack_id)
    artifacts = transport.record_store.load_answer_artifacts(record.review_pack_id)
    assert attempts == (first, imported)
    assert len(artifacts) == 1
    assert artifacts[0].answer_pdf_sha256 == first.answer_pdf_sha256
    assert imported.state is AnswerImportState.REVIEW_EVIDENCE_IMPORTED

    repeated, _ = workflow.upload_review_answer()
    assert repeated == imported
    assert transport.record_store.load_answer_imports(record.review_pack_id) == attempts


def test_documented_identity_contract_passes_without_response_observed_duplicate(
    tmp_path: Path,
) -> None:
    workflow, _ = _workflow(tmp_path)
    record = workflow.generate_review_pack()
    payload = _payload(workflow, record)
    expected = record.candidates[0].canonical_instrument
    candidate = payload["candidates"][0]

    assert candidate["observed_chart_instrument"] == expected
    assert all(
        "observed_chart_instrument" not in response
        and response["chart_identity"] == expected
        and all(
            observation["source_chart_identity"] == expected
            for observation in response["observations"]
        )
        for response in candidate["responses"]
    )
    assert len(_validate_answer_payload(record, payload)) == 1


@pytest.mark.parametrize(
    ("mutation", "reason"),
    (
        ("instrument", "CHART_IDENTITY_MISMATCH"),
        ("unreadable", "CHART_IDENTITY_MISMATCH"),
        ("response_chart", "CHART_IDENTITY_MISMATCH"),
        ("source_chart", "CHART_IDENTITY_MISMATCH"),
        ("revision", "CHART_REVISION_MISMATCH"),
        ("review_pack", "REVIEW_PACK_ID_MISMATCH"),
        ("run", "NATIVE_RUN_MISMATCH"),
        ("timeframe", "ANSWER_INCOMPLETE"),
    ),
)
def test_answer_acceptance_gates_fail_closed(tmp_path: Path, mutation: str, reason: str) -> None:
    workflow, _ = _workflow(tmp_path)
    record = workflow.generate_review_pack()
    payload = _payload(workflow, record)
    candidate = payload["candidates"][0]
    if mutation == "instrument":
        candidate["observed_chart_instrument"] = "CDSL"
    elif mutation == "unreadable":
        candidate["observed_chart_instrument"] = "UNREADABLE"
    elif mutation == "response_chart":
        candidate["responses"][0]["chart_identity"] = "SBIN"
    elif mutation == "source_chart":
        candidate["responses"][0]["observations"][0][
            "source_chart_identity"
        ] = "SBIN"
    elif mutation == "revision":
        candidate["chart_revision_sha256"] = "f" * 64
    elif mutation == "review_pack":
        payload["manifest"]["review_pack_id"] = "KRONOS-REVIEW-WRONG"
    elif mutation == "run":
        payload["manifest"]["native_run_identity"] = "SWING-RUN-OLD"
    elif mutation == "timeframe":
        candidate["responses"].pop()
    with pytest.raises(PdfReviewTransportError, match=reason):
        _validate_answer_payload(record, payload)
    assert workflow.snapshot().visual_v2_results == ()
    assert workflow.snapshot().layer2_records == ()
    assert workflow.snapshot().readiness_records == ()


def test_exact_m_and_m_identity_passes_without_response_level_observed_field(
    tmp_path: Path,
) -> None:
    workflow, _ = _workflow(tmp_path)
    original_record = workflow.generate_review_pack()
    payload = _payload(workflow, original_record)
    original_candidate = original_record.candidates[0]
    candidate_record = replace(
        original_candidate,
        canonical_instrument="M&M",
        chart_identity="M&M",
    )
    record = replace(original_record, candidates=(candidate_record,))
    payload["manifest"]["candidate_population"][0]["canonical_instrument"] = "M&M"
    candidate = payload["candidates"][0]
    candidate["canonical_instrument"] = "M&M"
    candidate["observed_chart_instrument"] = "M&M"
    for response in candidate["responses"]:
        assert "observed_chart_instrument" not in response
        response["native_canonical_instrument"] = "M&M"
        response["subject_identity"] = "M&M"
        response["chart_identity"] = "M&M"
        for observation in response["observations"]:
            observation["source_chart_identity"] = "M&M"

    assert len(_validate_answer_payload(record, payload)) == 1

    candidate["observed_chart_instrument"] = "M&M;"
    with pytest.raises(PdfReviewTransportError, match="CHART_IDENTITY_MISMATCH"):
        _validate_answer_payload(record, payload)


def test_answer_pdf_wrong_filename_and_symlink_fail_closed(tmp_path: Path) -> None:
    workflow, transport = _workflow(tmp_path)
    record = workflow.generate_review_pack()
    payload = _payload(workflow, record)
    wrong = transport.configuration.answer_directory / "KRONOS_REVIEW_20260816_000000_IST_ANSWERS.pdf"
    _answer_pdf(wrong, payload)
    with pytest.raises(PdfReviewTransportError, match="ANSWER_FILENAME_MISMATCH"):
        transport.find_and_validate_answer(record)
    wrong.unlink()
    external = tmp_path / "external.pdf"
    _answer_pdf(external, payload)
    expected = transport.configuration.answer_directory / record.expected_answer_filename
    expected.symlink_to(external)
    with pytest.raises(PdfReviewTransportError, match="ANSWER_FILE_UNSAFE"):
        transport.find_and_validate_answer(record)


def test_rejected_identity_is_persisted_and_restart_restores_pack(tmp_path: Path) -> None:
    workflow, transport = _workflow(tmp_path)
    record = workflow.generate_review_pack()
    payload = _payload(workflow, record)
    payload["candidates"][0]["observed_chart_instrument"] = "CDSL"
    answer = transport.configuration.answer_directory / record.expected_answer_filename
    _answer_pdf(answer, payload)

    with pytest.raises(PdfReviewTransportError, match="CHART_IDENTITY_MISMATCH"):
        workflow.upload_review_answer()
    snapshot = workflow.snapshot()
    assert snapshot.answer_import_records[-1].state is AnswerImportState.ANSWER_PACK_REJECTED
    assert snapshot.visual_v2_results == ()
    facts, run, _ = _evidence_run()
    restored = NativeReviewWorkflow(
        NativeReviewEvidenceStore(tmp_path / "native"),
        chart_store=LocalTradingViewEvidenceStore(tmp_path / "charts", clock=lambda: NOW),
        pdf_transport=transport,
        clock=lambda: NOW,
    ).restore(run, facts)
    assert restored.review_pack_record == record
    assert restored.answer_import_records[-1].state is AnswerImportState.ANSWER_PACK_REJECTED
