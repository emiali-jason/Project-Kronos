from dataclasses import replace
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader

from kronos.application.swing_visual_v3 import chart_inputs_from_requirement
from kronos.swing.v1.native_review import build_native_review_requirements
from kronos.swing.v1.pdf_visual_review_v3 import write_visual_v3_question_pack
from kronos.swing.v1.visual_evidence_v2 import VISUAL_QUESTION_SET_V2_ID
from kronos.swing.v1.visual_evidence_v3 import (
    VISUAL_QUESTION_SET_V3_ID,
    VisualTimeframe,
    build_visual_evidence_v3_request,
)
from tests.unit.swing.v1.test_native_review import _evidence_run


NOW = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)


def _image() -> bytes:
    value = BytesIO()
    Image.new("RGB", (1600, 900), "#071724").save(value, "PNG")
    return value.getvalue()


def _requests():  # type: ignore[no-untyped-def]
    facts, run, _ = _evidence_run()
    requirement = build_native_review_requirements(run, facts)[0]
    charts = chart_inputs_from_requirement(
        requirement,
        chart_identity=requirement.canonical_instrument,
        content_type="image/png",
        images=tuple(_image() for _ in VisualTimeframe),
    )
    return tuple(
        build_visual_evidence_v3_request(
            requirement,
            facts,
            timeframe=chart.timeframe,
            observation_boundary=chart.observation_boundary,
            chart_identity=chart.chart_identity,
            content_type=chart.content_type,
            original_image=chart.original_image,
            request_timestamp=NOW,
        )
        for chart in charts
    )


def test_v3_question_pack_is_versioned_visual_only_and_contains_no_machine_values(
    tmp_path: Path,
) -> None:
    requests = _requests()
    path = tmp_path / "V3_QUESTIONS.pdf"
    record = write_visual_v3_question_pack(
        requests,
        path,
        review_pack_id="KRONOS-V3-REVIEW-CONTROLLED",
        created_at=NOW,
    )
    text = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    compact_text = " ".join(text.split())

    assert record.question_set_identity == VISUAL_QUESTION_SET_V3_ID
    assert "INDEPENDENT VISUAL EVIDENCE ONLY" in compact_text
    assert "do not transcribe or infer machine CP, BC, TC" in compact_text
    assert "Observe CPR presence" in compact_text
    assert "do not create a numerical zone" in compact_text
    for request in requests:
        fact = request.machine_fact
        for value in (fact.cp, fact.bc, fact.tc, fact.reference_high, fact.reference_low):
            assert value is not None
            assert str(value) not in compact_text


def test_v3_question_pack_identity_cannot_be_reinterpreted_as_v2(tmp_path: Path) -> None:
    record = write_visual_v3_question_pack(
        _requests(),
        tmp_path / "V3_QUESTIONS.pdf",
        review_pack_id="KRONOS-V3-REVIEW-CONTROLLED",
        created_at=NOW,
    )
    with pytest.raises(ValueError, match="REVIEW_PACK_RECORD_INVALID"):
        replace(record, question_set_identity=VISUAL_QUESTION_SET_V2_ID)


def test_v3_pack_requires_exact_four_timeframes(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="REQUESTS_INVALID"):
        write_visual_v3_question_pack(
            _requests()[:-1],
            tmp_path / "V3_QUESTIONS.pdf",
            review_pack_id="KRONOS-V3-REVIEW-CONTROLLED",
            created_at=NOW,
        )
