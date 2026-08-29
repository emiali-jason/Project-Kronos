"""Immutable combined Question transport for exact V2 Review lineage."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from typing import Mapping, Sequence
from uuid import uuid4
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from kronos.intraday.review import QUESTIONS, ReviewError, ReviewFailure
from kronos.intraday.review_answer import (
    ANSWER_CONTRACT_VERSION,
    ANSWER_PACK_IDENTITY,
    BATCH_ANSWER_PACK_IDENTITY,
)
from kronos.intraday.review_pdf import DEFAULT_ANSWER_INBOX, DEFAULT_QUESTION_OUTBOX
from kronos.intraday.review_v2 import ReviewQuestionBatchV2, ReviewQuestionPackV2


REVIEW_BATCH_TRANSPORT_V2_IDENTITY = "KRONOS-INTRADAY-REVIEW-BATCH-TRANSPORT-V2"
REVIEW_BATCH_TRANSPORT_V2_VERSION = "2.0.0"
REVIEW_V2_QUESTION_TRANSPORT_ROUTE = "/intraday/review/v2/question-transport"
_IST = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True, slots=True)
class ReviewBatchTransportV2:
    transport_identity: str
    review_batch_identity: str
    probables_run_identity: str
    review_pack_identities: tuple[str, ...]
    generated_at: datetime
    question_filename: str
    expected_answer_filename: str
    candidate_count: int
    question_pdf_sha256: str
    answer_template_sha256: str
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = REVIEW_BATCH_TRANSPORT_V2_IDENTITY
    schema_version: str = REVIEW_BATCH_TRANSPORT_V2_VERSION

    def __post_init__(self) -> None:
        core = _transport_core(self)
        values = _without(self, "transport_identity", "integrity_identity")
        if (
            not self.review_batch_identity.startswith("INTRADAY-REVIEW-BATCH-V2-")
            or not self.probables_run_identity.startswith("INTRADAY-PROBABLES-V2-RUN-")
            or not self.review_pack_identities
            or len(self.review_pack_identities) != self.candidate_count
            or not _aware(self.generated_at)
            or self.candidate_count < 1
            or self.question_filename != f"{_stem(self)}_QUESTIONS.pdf"
            or self.expected_answer_filename != f"{_stem(self)}_ANSWERS.json"
            or not _sha(self.question_pdf_sha256)
            or not _sha(self.answer_template_sha256)
            or not self.provenance
            or self.schema_identity != REVIEW_BATCH_TRANSPORT_V2_IDENTITY
            or self.schema_version != REVIEW_BATCH_TRANSPORT_V2_VERSION
            or self.transport_identity
            != _identity("INTRADAY-REVIEW-BATCH-TRANSPORT-V2-", core)
            or self.integrity_identity
            != _identity("INTEGRITY-REVIEW-BATCH-TRANSPORT-V2-", values)
        ):
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)


class IntradayReviewV2Transport:
    """Write one immutable V2 Question PDF and its exact Answer template."""

    def __init__(
        self,
        *,
        question_outbox: Path = DEFAULT_QUESTION_OUTBOX,
        answer_inbox: Path = DEFAULT_ANSWER_INBOX,
    ) -> None:
        if not _safe_directory(question_outbox) or not _safe_directory(answer_inbox):
            raise ValueError("INTRADAY_REVIEW_V2_TRANSPORT_PATH_INVALID")
        self.question_outbox = question_outbox
        self.answer_inbox = answer_inbox

    def export(
        self,
        batch: ReviewQuestionBatchV2,
        entries: Sequence[tuple[ReviewQuestionPackV2, bytes]],
    ) -> tuple[ReviewBatchTransportV2, Path, Path]:
        retained = _validate_entries(batch, entries)
        generated_at = batch.created_at
        core = _core_values(batch, generated_at)
        transport_identity = expected_transport_identity_v2(batch)
        stem = _stem_from(batch.batch_identity, generated_at)
        question_filename = f"{stem}_QUESTIONS.pdf"
        answer_filename = f"{stem}_ANSWERS.json"
        template = answer_template_v2(batch, tuple(pack for pack, _ in retained))
        pdf = render_review_batch_v2_pdf(
            batch,
            retained,
            transport_identity=transport_identity,
            expected_answer_filename=answer_filename,
        )
        values = {
            **core,
            "question_filename": question_filename,
            "expected_answer_filename": answer_filename,
            "question_pdf_sha256": sha256(pdf).hexdigest(),
            "answer_template_sha256": sha256(template).hexdigest(),
            "provenance": (
                "KRONOS-INTRADAY-V2-REVIEW-PHASE-B",
                batch.batch_identity,
            ),
        }
        transport = ReviewBatchTransportV2(
            transport_identity=transport_identity,
            integrity_identity=_identity(
                "INTEGRITY-REVIEW-BATCH-TRANSPORT-V2-", values
            ),
            **values,
        )
        self.question_outbox.mkdir(parents=True, exist_ok=True)
        self.answer_inbox.mkdir(parents=True, exist_ok=True)
        question_path = _retain(self.question_outbox / question_filename, pdf)
        answer_path = _retain(self.answer_inbox / answer_filename, template)
        return transport, question_path, answer_path


def answer_template_v2(
    batch: ReviewQuestionBatchV2,
    packs: tuple[ReviewQuestionPackV2, ...],
) -> bytes:
    ordered = _ordered_packs(batch, packs)
    document = {
        "schema_identity": BATCH_ANSWER_PACK_IDENTITY,
        "schema_version": ANSWER_CONTRACT_VERSION,
        "question_set_identity": ordered[0].question_set_identity,
        "question_set_version": ordered[0].question_set_version,
        "review_batch_identity": batch.batch_identity,
        "probables_run_identity": batch.probables_run_identity,
        "candidates": [_answer_candidate(pack) for pack in ordered],
    }
    return _canonical(document) + b"\n"


def expected_transport_identity_v2(batch: ReviewQuestionBatchV2) -> str:
    if type(batch) is not ReviewQuestionBatchV2:
        raise ReviewError(ReviewFailure.INPUT_INVALID)
    return _identity(
        "INTRADAY-REVIEW-BATCH-TRANSPORT-V2-",
        _core_values(batch, batch.created_at),
    )


def render_review_batch_v2_pdf(
    batch: ReviewQuestionBatchV2,
    entries: Sequence[tuple[ReviewQuestionPackV2, bytes]],
    *,
    transport_identity: str,
    expected_answer_filename: str,
) -> bytes:
    retained = _validate_entries(batch, entries)
    if not transport_identity.startswith("INTRADAY-REVIEW-BATCH-TRANSPORT-V2-"):
        raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
    output = BytesIO()
    document = SimpleDocTemplate(
        output, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
        topMargin=14 * mm, bottomMargin=14 * mm,
        title="KRONOS Intraday V2 Visual Review Batch", author="KRONOS",
        invariant=1,
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "V2Title", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=18, leading=22, textColor=colors.HexColor("#0a7b55"),
        alignment=TA_CENTER,
    )
    heading = ParagraphStyle(
        "V2Heading", parent=styles["Heading2"], fontName="Helvetica-Bold",
        fontSize=11, leading=14, textColor=colors.HexColor("#075f46"),
        spaceBefore=6, spaceAfter=5,
    )
    body = ParagraphStyle("V2Body", parent=styles["BodyText"], fontSize=8.5, leading=11)
    small = ParagraphStyle("V2Small", parent=body, fontSize=6.6, leading=8.2)
    warning = ParagraphStyle(
        "V2Warning", parent=body, fontName="Helvetica-Bold",
        textColor=colors.HexColor("#7a3500"),
    )
    story: list[object] = [
        Paragraph("KRONOS INTRADAY V2 REVIEW", title),
        Paragraph("GOVERNED COMBINED VISUAL QUESTION TRANSPORT", heading),
        Table([
            ["V2 Batch", Paragraph(escape(batch.batch_identity), small)],
            ["V2 Transport", Paragraph(escape(transport_identity), small)],
            ["Probables V2 Run", Paragraph(escape(batch.probables_run_identity), small)],
            ["Candidate count", str(len(batch.candidate_identities))],
            ["Required Answer", Paragraph(escape(expected_answer_filename), small)],
        ], colWidths=(45 * mm, 129 * mm), style=_table_style()),
        Spacer(1, 3 * mm),
        Paragraph(
            "Return exactly one UTF-8 combined JSON Answer Pack. Candidate evidence remains independent and is bound by exact V2 Review Pack, Review Cycle and Chart Revision identities—not by array order.",
            warning,
        ),
    ]
    for index, (pack, chart_payload) in enumerate(retained, start=1):
        story.extend((
            PageBreak(),
            Paragraph(f"CANDIDATE {index} · {escape(pack.expected_canonical_subject_identity)}", heading),
            Table([
                ["Expected canonical subject", Paragraph(escape(pack.expected_canonical_subject_identity), small)],
                ["Direction / phase", f"{pack.proposed_direction} / {pack.phase.value}"],
                ["Review Pack V2", Paragraph(escape(pack.review_pack_identity), small)],
                ["Review Cycle V2", Paragraph(escape(pack.review_cycle_identity), small)],
                ["Chart Revision V2", Paragraph(escape(pack.chart_revision_identity), small)],
                ["Methodology", Paragraph(escape(f"{pack.methodology_identity} / {pack.methodology_version}"), small)],
                ["Analysis boundary", escape(pack.analysis_boundary.isoformat())],
                ["Question Set", Paragraph(escape(f"{pack.question_set_identity} / {pack.question_set_version}"), small)],
            ], colWidths=(45 * mm, 129 * mm), style=_table_style()),
            Spacer(1, 3 * mm),
            Paragraph("Genuine Sponsor chart composite", heading),
        ))
        chart = Image(BytesIO(chart_payload))
        scale = min((174 * mm) / chart.imageWidth, (88 * mm) / chart.imageHeight, 1)
        chart.drawWidth = chart.imageWidth * scale
        chart.drawHeight = chart.imageHeight * scale
        story.extend((chart, PageBreak(), Paragraph("GOVERNED Q1–Q10", heading)))
        story.extend((
            Paragraph(escape(pack.trust_boundary), warning),
            Paragraph(escape(pack.trading_authority_prohibition), warning),
            Paragraph(
                "Expected canonical subject is KRONOS-owned. observed_visible_subject_identity is Chart Analyst observation authority and must not be copied from the expected identity without direct visual observation.",
                warning,
            ),
            Spacer(1, 2 * mm),
        ))
        for question in pack.questions:
            detail = [
                Paragraph(f"<b>{question.question_id}</b> — {escape(question.wording)}", body),
                Paragraph(f"Scope: {' + '.join(question.timeframe_scope)}", small),
                Paragraph(f"Allowed: {escape(' | '.join(question.allowed_answers))}", small),
            ]
            if question.conditional_instruction is not None:
                detail.append(Paragraph(escape(question.conditional_instruction), small))
            detail.extend(Paragraph(escape(value), small) for value in question.constraints)
            story.append(KeepTogether(detail + [Spacer(1, 2.5 * mm)]))
    template = answer_template_v2(batch, tuple(pack for pack, _ in retained)).decode().strip()
    story.extend((
        PageBreak(), Paragraph("EXACT COMBINED ANSWER CONTRACT", heading),
        Paragraph(
            f"Schema: {escape(BATCH_ANSWER_PACK_IDENTITY)} / {escape(ANSWER_CONTRACT_VERSION)}. Required filename: <b>{escape(expected_answer_filename)}</b>. Replace observation placeholders only; preserve every V2 identity, key, Q1–Q10 order and candidate population.",
            warning,
        ), Spacer(1, 2 * mm),
    ))
    for offset in range(0, len(template), 850):
        story.append(Paragraph(escape(template[offset:offset + 850]), small))
    document.build(story, onFirstPage=_page, onLaterPages=_page)
    return output.getvalue()


def transport_artifact_bytes_v2(value: ReviewBatchTransportV2) -> bytes:
    if type(value) is not ReviewBatchTransportV2:
        raise ReviewError(ReviewFailure.INPUT_INVALID)
    return _canonical({"artifact_type": "ReviewBatchTransportV2", "value": _normalize(value)})


def transport_from_bytes_v2(payload: bytes) -> ReviewBatchTransportV2:
    try:
        document = json.loads(payload.decode())
        if document["artifact_type"] != "ReviewBatchTransportV2":
            raise ValueError
        raw = dict(document["value"])
        raw["review_pack_identities"] = tuple(raw["review_pack_identities"])
        raw["generated_at"] = datetime.fromisoformat(raw["generated_at"])
        raw["provenance"] = tuple(raw["provenance"])
        return ReviewBatchTransportV2(**raw)
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError, ReviewError) as error:
        raise ReviewError(ReviewFailure.INTEGRITY_INVALID) from error


def _answer_candidate(pack: ReviewQuestionPackV2) -> dict[str, object]:
    return {
        "schema_identity": ANSWER_PACK_IDENTITY,
        "schema_version": ANSWER_CONTRACT_VERSION,
        "question_set_identity": pack.question_set_identity,
        "question_set_version": pack.question_set_version,
        "review_pack_identity": pack.review_pack_identity,
        "review_cycle_identity": pack.review_cycle_identity,
        "review_request_identity": pack.review_request_identity,
        "chart_revision_identity": pack.chart_revision_identity,
        "expected_canonical_subject_identity": pack.expected_canonical_subject_identity,
        "observed_visible_subject_identity": None,
        "proposed_direction": pack.proposed_direction,
        "global_observation_status": "INVALID",
        "answers": [{
            "question_id": question.question_id,
            "observation_status": "INVALID",
            "answer": None,
            "visible_timeframes": [],
            "visible_basis": None,
            "status_detail": "REPLACE WITH GOVERNED OBSERVATION",
            "why_not_covered_elsewhere": None,
        } for question in QUESTIONS],
    }


def _validate_entries(
    batch: ReviewQuestionBatchV2,
    entries: Sequence[tuple[ReviewQuestionPackV2, bytes]],
) -> tuple[tuple[ReviewQuestionPackV2, bytes], ...]:
    retained = tuple(entries)
    if (
        type(batch) is not ReviewQuestionBatchV2
        or not retained
        or any(type(pack) is not ReviewQuestionPackV2 or type(payload) is not bytes or not payload for pack, payload in retained)
    ):
        raise ReviewError(ReviewFailure.INPUT_INVALID)
    ordered = tuple(sorted(retained, key=lambda item: item[0].expected_canonical_subject_identity))
    if (
        tuple(pack.review_pack_identity for pack, _ in ordered) != batch.review_pack_identities
        or tuple(pack.review_cycle_identity for pack, _ in ordered) != batch.review_cycle_identities
        or tuple(pack.expected_canonical_subject_identity for pack, _ in ordered) != batch.candidate_identities
        or any(sha256(payload).hexdigest() != pack.chart_payload_sha256 for pack, payload in ordered)
    ):
        raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
    return ordered


def _ordered_packs(
    batch: ReviewQuestionBatchV2,
    packs: tuple[ReviewQuestionPackV2, ...],
) -> tuple[ReviewQuestionPackV2, ...]:
    ordered = tuple(sorted(packs, key=lambda item: item.expected_canonical_subject_identity))
    if (
        type(batch) is not ReviewQuestionBatchV2
        or not ordered
        or any(type(item) is not ReviewQuestionPackV2 for item in ordered)
        or tuple(item.review_pack_identity for item in ordered) != batch.review_pack_identities
    ):
        raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
    return ordered


def _core_values(batch: ReviewQuestionBatchV2, generated_at: datetime) -> dict[str, object]:
    return {
        "review_batch_identity": batch.batch_identity,
        "probables_run_identity": batch.probables_run_identity,
        "review_pack_identities": batch.review_pack_identities,
        "generated_at": generated_at,
        "candidate_count": len(batch.candidate_identities),
        "schema_identity": REVIEW_BATCH_TRANSPORT_V2_IDENTITY,
        "schema_version": REVIEW_BATCH_TRANSPORT_V2_VERSION,
    }


def _transport_core(value: ReviewBatchTransportV2) -> dict[str, object]:
    return {
        "review_batch_identity": value.review_batch_identity,
        "probables_run_identity": value.probables_run_identity,
        "review_pack_identities": value.review_pack_identities,
        "generated_at": value.generated_at,
        "candidate_count": value.candidate_count,
        "schema_identity": value.schema_identity,
        "schema_version": value.schema_version,
    }


def _stem(value: ReviewBatchTransportV2) -> str:
    return _stem_from(value.review_batch_identity, value.generated_at)


def _stem_from(batch_identity: str, generated_at: datetime) -> str:
    stamp = generated_at.astimezone(_IST).strftime("%Y%m%d_%H%M%S")
    suffix = batch_identity.rsplit("-", 1)[-1][:8]
    return f"KRONOS_INTRADAY_REVIEW_V2_{stamp}_IST_{suffix}"


def _retain(path: Path, payload: bytes) -> Path:
    if path.exists():
        if path.read_bytes() != payload:
            raise ReviewError(ReviewFailure.PERSISTENCE_CONFLICT)
        return path
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_bytes(payload)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def _table_style() -> TableStyle:
    return TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e8f4ef")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#a9bbb4")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ])


def _page(canvas, document) -> None:  # type: ignore[no-untyped-def]
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#60706a"))
    canvas.drawString(16 * mm, 7 * mm, "KRONOS Intraday V2 Review — visual evidence only")
    canvas.drawRightString(194 * mm, 7 * mm, f"Page {document.page}")
    canvas.restoreState()


def _safe_directory(path: Path) -> bool:
    return isinstance(path, Path) and path.is_absolute() and path != Path("/") and ".." not in path.parts


def _aware(value: datetime) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _sha(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _without(value: object, *names: str) -> dict[str, object]:
    return {name: item for name, item in asdict(value).items() if name not in names}


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(_canonical(value)).hexdigest().upper()


def _canonical(value: object) -> bytes:
    return json.dumps(_normalize(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _normalize(value: object) -> object:
    if hasattr(value, "__dataclass_fields__"):
        return _normalize(asdict(value))
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    return value


__all__ = [
    "REVIEW_BATCH_TRANSPORT_V2_IDENTITY",
    "REVIEW_BATCH_TRANSPORT_V2_VERSION",
    "REVIEW_V2_QUESTION_TRANSPORT_ROUTE",
    "IntradayReviewV2Transport",
    "ReviewBatchTransportV2",
    "answer_template_v2",
    "expected_transport_identity_v2",
    "render_review_batch_v2_pdf",
    "transport_artifact_bytes_v2",
    "transport_from_bytes_v2",
]
