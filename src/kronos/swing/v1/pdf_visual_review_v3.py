"""Controlled PDF Question Pack presentation for Swing Visual V3.

This module is additive and is not selected by the historical V2 Browser
workflow.  It provides the governed V3 authority presentation for future V3
cycles without altering Sponsor-facing workflow in this work order.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import re

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer

from kronos.swing.v1.visual_evidence_v3 import (
    VISUAL_EVIDENCE_V3_AUTHORITY,
    VISUAL_QUESTION_SEMANTICS_V3,
    VISUAL_QUESTION_SET_V3_ID,
    VISUAL_QUESTION_SET_V3_VERSION,
    VisualEvidenceV3Request,
)


VISUAL_V3_REVIEW_PACK_SCHEMA = "KRONOS-SWING-V1-VISUAL-V3-REVIEW-PACK"


@dataclass(frozen=True, slots=True)
class VisualV3ReviewPackRecord:
    review_pack_id: str
    native_run_identity: str
    canonical_instrument: str
    native_assessment_sha256: str
    created_at: datetime
    question_path: str
    question_pdf_sha256: str
    chart_revisions: tuple[tuple[str, str], ...]
    machine_fact_bindings: tuple[tuple[str, str], ...]
    question_set_identity: str = VISUAL_QUESTION_SET_V3_ID
    question_set_version: str = VISUAL_QUESTION_SET_V3_VERSION
    schema: str = VISUAL_V3_REVIEW_PACK_SCHEMA
    analyst_authority: str = VISUAL_EVIDENCE_V3_AUTHORITY

    def __post_init__(self) -> None:
        if (
            not self.review_pack_id.startswith("KRONOS-V3-REVIEW-")
            or not self.native_run_identity
            or not self.canonical_instrument
            or not _digest(self.native_assessment_sha256)
            or not _aware(self.created_at)
            or not Path(self.question_path).is_absolute()
            or not _digest(self.question_pdf_sha256)
            or len(self.chart_revisions) != 4
            or len(self.machine_fact_bindings) != 4
            or any(len(item) != 2 or not _digest(item[1]) for item in self.chart_revisions)
            or any(len(item) != 2 or not _digest(item[1]) for item in self.machine_fact_bindings)
            or self.question_set_identity != VISUAL_QUESTION_SET_V3_ID
            or self.question_set_version != VISUAL_QUESTION_SET_V3_VERSION
            or self.schema != VISUAL_V3_REVIEW_PACK_SCHEMA
            or self.analyst_authority != VISUAL_EVIDENCE_V3_AUTHORITY
        ):
            raise ValueError("VISUAL_V3_REVIEW_PACK_RECORD_INVALID")


def write_visual_v3_question_pack(
    requests: tuple[VisualEvidenceV3Request, ...],
    destination: Path,
    *,
    review_pack_id: str,
    created_at: datetime,
) -> VisualV3ReviewPackRecord:
    """Write one governed V3 Question Pack without machine numerical values."""

    if type(requests) is not tuple or len(requests) != 4:
        raise ValueError("VISUAL_V3_REVIEW_PACK_REQUESTS_INVALID")
    first = requests[0]
    if (
        tuple(item.timeframe for item in requests)
        != tuple(type(first.timeframe))
        or any(
            item.requirement != first.requirement
            or item.question_set_identity != VISUAL_QUESTION_SET_V3_ID
            or item.question_set_version != VISUAL_QUESTION_SET_V3_VERSION
            for item in requests
        )
    ):
        raise ValueError("VISUAL_V3_REVIEW_PACK_REQUESTS_INVALID")
    destination = Path(destination).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    buffer = BytesIO()
    styles = getSampleStyleSheet()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title="KRONOS Swing Visual V3 Question Pack",
    )
    story = [
        Paragraph("KRONOS SWING — VISUAL V3 QUESTION PACK", styles["Title"]),
        Spacer(1, 4 * mm),
        Paragraph(
            "Authority: INDEPENDENT VISUAL EVIDENCE ONLY. KRONOS independently "
            "maintains deterministic machine facts. Answer only from the supplied "
            "chart; do not transcribe or infer machine CP, BC, TC, or governed "
            "reference numerical values.",
            styles["BodyText"],
        ),
        Spacer(1, 3 * mm),
        Paragraph(
            f"Instrument: {first.requirement.canonical_instrument} | "
            f"Question set: {VISUAL_QUESTION_SET_V3_ID} {VISUAL_QUESTION_SET_V3_VERSION}",
            styles["BodyText"],
        ),
    ]
    for index, request in enumerate(requests):
        story.extend((
            Spacer(1, 5 * mm),
            Paragraph(f"TIMEFRAME {request.timeframe.value}", styles["Heading2"]),
            Image(BytesIO(request.original_image), width=174 * mm, height=98 * mm),
            Spacer(1, 3 * mm),
        ))
        for number, (question, routing) in enumerate(request.routing, start=1):
            story.append(Paragraph(
                f"Q{number} [{routing.value}] {VISUAL_QUESTION_SEMANTICS_V3[question]}",
                styles["BodyText"],
            ))
        if index != len(requests) - 1:
            story.append(PageBreak())
    document.build(story)
    payload = buffer.getvalue()
    destination.write_bytes(payload)
    return VisualV3ReviewPackRecord(
        review_pack_id=review_pack_id,
        native_run_identity=first.requirement.native_run_identity,
        canonical_instrument=first.requirement.canonical_instrument,
        native_assessment_sha256=first.requirement.thesis.native_assessment_sha256,
        created_at=created_at,
        question_path=str(destination),
        question_pdf_sha256=sha256(payload).hexdigest(),
        chart_revisions=tuple(
            (item.timeframe.value, item.chart_revision_sha256) for item in requests
        ),
        machine_fact_bindings=tuple(
            (item.timeframe.value, item.machine_fact.integrity_sha256)
            for item in requests
        ),
    )


def _digest(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


__all__ = [
    "VISUAL_V3_REVIEW_PACK_SCHEMA",
    "VisualV3ReviewPackRecord",
    "write_visual_v3_question_pack",
]
