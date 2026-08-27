"""Deterministic Sponsor PDF transport for Intraday Review Question Packs."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re
from typing import Sequence
from uuid import uuid4
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from kronos.intraday.review import CHART_TIMEFRAMES, ReviewError, ReviewFailure, ReviewQuestionPack
from kronos.intraday.review_batch import ReviewBatchPdf
from kronos.intraday.review_transport import ReviewBatchTransport
from kronos.intraday.review_answer import (
    ANSWER_CONTRACT_VERSION,
    ANSWER_PACK_IDENTITY,
    answer_pack_filename,
    batch_answer_pack_filename,
    batch_answer_pack_template,
)


DEFAULT_QUESTION_OUTBOX = Path(
    "/Users/imranali/Documents/Project-KRONOS/KRONOS REVIEW PACK/Intraday/KRONOS QUESTIONS"
)
DEFAULT_ANSWER_INBOX = Path(
    "/Users/imranali/Documents/Project-KRONOS/KRONOS REVIEW PACK/Intraday/CHATGPT ANSWERS"
)
_IST = ZoneInfo("Asia/Kolkata")


class IntradayReviewPdfTransport:
    """Export presentation only; canonical Question Pack JSON remains authority."""

    def __init__(
        self,
        *,
        question_outbox: Path = DEFAULT_QUESTION_OUTBOX,
        answer_inbox: Path = DEFAULT_ANSWER_INBOX,
    ) -> None:
        if not _safe_absolute_directory(question_outbox) or not _safe_absolute_directory(answer_inbox):
            raise ValueError("INTRADAY_REVIEW_TRANSPORT_PATH_INVALID")
        self.question_outbox = question_outbox
        self.answer_inbox = answer_inbox

    def export(self, pack: ReviewQuestionPack, chart_payload: bytes) -> Path:
        if type(pack) is not ReviewQuestionPack or type(chart_payload) is not bytes or not chart_payload:
            raise ReviewError(ReviewFailure.INPUT_INVALID)
        self.question_outbox.mkdir(parents=True, exist_ok=True)
        self.answer_inbox.mkdir(parents=True, exist_ok=True)
        target = self.question_outbox / question_pack_filename(pack)
        payload = render_question_pack_pdf(pack, chart_payload)
        return _retain_pdf(target, payload)

    def export_batch(
        self,
        batch: ReviewBatchPdf,
        transport: ReviewBatchTransport,
        entries: Sequence[tuple[ReviewQuestionPack, bytes]],
    ) -> Path:
        retained = tuple(entries)
        if (
            type(batch) is not ReviewBatchPdf
            or type(transport) is not ReviewBatchTransport
            or transport.review_batch_identity != batch.batch_identity
            or transport.probables_run_identity != batch.probables_run_identity
            or transport.candidate_count != len(batch.members)
            or not retained
            or any(type(pack) is not ReviewQuestionPack or type(chart) is not bytes or not chart for pack, chart in retained)
            or tuple(pack.review_pack_identity for pack, _ in retained)
            != tuple(member.review_pack_identity for member in batch.members)
            or any(
                pack.expected_canonical_subject_identity != member.canonical_subject_identity
                or pack.proposed_direction != member.direction
                or pack.review_cycle_identity != member.review_cycle_identity
                or pack.chart_revision_identity != member.chart_revision_identity
                for member, (pack, _) in zip(batch.members, retained, strict=True)
            )
        ):
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        self.question_outbox.mkdir(parents=True, exist_ok=True)
        self.answer_inbox.mkdir(parents=True, exist_ok=True)
        target = self.question_outbox / review_batch_filename(transport)
        return _retain_pdf(target, render_review_batch_pdf(batch, transport, retained))


def _retain_pdf(target: Path, payload: bytes) -> Path:
    if target.exists():
        try:
            current = target.read_bytes()
        except OSError as error:
            raise ReviewError(ReviewFailure.ARTIFACT_UNAVAILABLE) from error
        if current != payload:
            raise ReviewError(ReviewFailure.PERSISTENCE_CONFLICT)
        return target
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_bytes(payload)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def question_pack_filename(pack: ReviewQuestionPack) -> str:
    instrument = re.sub(r"[^A-Z0-9_-]", "-", pack.expected_canonical_subject_identity.upper())
    cycle_suffix = pack.review_cycle_identity.rsplit("-", 1)[-1][:12]
    revision_suffix = pack.chart_revision_identity.rsplit("-", 1)[-1][:12]
    return f"{instrument}_INTRADAY_REVIEW_{cycle_suffix}_CHART-{revision_suffix}_QV1.pdf"


def review_batch_filename(transport: ReviewBatchTransport) -> str:
    if type(transport) is not ReviewBatchTransport:
        raise ReviewError(ReviewFailure.INPUT_INVALID)
    return transport.question_filename


def render_question_pack_pdf(pack: ReviewQuestionPack, chart_payload: bytes) -> bytes:
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title="KRONOS Intraday V1 Visual Review Question Pack",
        author="KRONOS",
        invariant=1,
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "KronosTitle", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=18, leading=22, textColor=colors.HexColor("#0a7b55"), alignment=TA_CENTER,
    )
    heading = ParagraphStyle(
        "KronosHeading", parent=styles["Heading2"], fontName="Helvetica-Bold",
        fontSize=11, leading=14, textColor=colors.HexColor("#075f46"), spaceBefore=6, spaceAfter=5,
    )
    body = ParagraphStyle("KronosBody", parent=styles["BodyText"], fontSize=8.5, leading=11)
    small = ParagraphStyle("KronosSmall", parent=body, fontSize=7.5, leading=9.5, textColor=colors.HexColor("#3f4c49"))
    table_value = ParagraphStyle("KronosTableValue", parent=body, fontSize=6.5, leading=8)
    warning = ParagraphStyle("KronosWarning", parent=body, fontName="Helvetica-Bold", textColor=colors.HexColor("#7a3500"))
    story = [
        Paragraph("KRONOS INTRADAY V1", title),
        Paragraph("GOVERNED VISUAL REVIEW QUESTION PACK", heading),
        Spacer(1, 3 * mm),
        Table(
            [
                ["Expected canonical instrument", Paragraph(escape(pack.expected_canonical_subject_identity), table_value)],
                ["Proposed direction", Paragraph(escape(pack.proposed_direction), table_value)],
                ["Review Pack", Paragraph(escape(pack.review_pack_identity), table_value)],
                ["Review Cycle / Request", Paragraph(escape(pack.review_cycle_identity), table_value)],
                ["Chart Revision", Paragraph(escape(pack.chart_revision_identity), table_value)],
                ["Question Set", Paragraph(escape(f"{pack.question_set_identity} / {pack.question_set_version}"), table_value)],
                ["Visible panels required", Paragraph(" | ".join(CHART_TIMEFRAMES), table_value)],
            ],
            colWidths=(48 * mm, 126 * mm),
            style=TableStyle([
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e8f4ef")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#a9bbb4")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("LEADING", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]),
        ),
        Spacer(1, 4 * mm),
        Paragraph("Sponsor-supplied composite", heading),
    ]
    chart = Image(BytesIO(chart_payload))
    max_width, max_height = 174 * mm, 105 * mm
    scale = min(max_width / chart.imageWidth, max_height / chart.imageHeight, 1)
    chart.drawWidth = chart.imageWidth * scale
    chart.drawHeight = chart.imageHeight * scale
    story.extend((chart, PageBreak(), Paragraph("Observation instructions", heading)))
    statuses = ", ".join(item.value for item in pack.observation_statuses)
    story.extend((
        Paragraph(f"Global observation status: {escape(statuses)}. UNCLEAR is substantive ambiguity where the chart is visible; UNCLEAR is not NOT_VISIBLE.", body),
        Spacer(1, 2 * mm),
        Paragraph(escape(pack.trust_boundary), warning),
        Spacer(1, 2 * mm),
        Paragraph(escape(pack.trading_authority_prohibition), warning),
        Spacer(1, 3 * mm),
        Paragraph("Expected identity is supplied by KRONOS. Report the independently observed visible chart identity without forcing it to equal the expected identity.", body),
        Spacer(1, 3 * mm),
        Paragraph("Chart Analyst Answer Pack transport", heading),
        Paragraph(
            "Return one UTF-8 JSON object for this candidate using schema "
            f"{escape(ANSWER_PACK_IDENTITY)} / {escape(ANSWER_CONTRACT_VERSION)}. "
            "Do not return prose, Markdown fences, machine hashes, Provider tokens, internal KRONOS provenance, trading fields or additional keys.",
            body,
        ),
        Paragraph(
            "Required filename: <b>" + escape(answer_pack_filename(pack)) + "</b>",
            small,
        ),
        Paragraph(
            "Top-level keys: schema_identity, schema_version, question_set_identity, question_set_version, review_pack_identity, review_cycle_identity, review_request_identity, chart_revision_identity, expected_canonical_subject_identity, observed_visible_subject_identity, proposed_direction, global_observation_status, answers.",
            small,
        ),
        Paragraph(
            "Each of the exact ordered Q1-Q10 answer objects requires: question_id, observation_status, answer, visible_timeframes, visible_basis, status_detail, why_not_covered_elsewhere. Use null where the contract requires absence. UNCLEAR is an allowed substantive answer, never a status.",
            small,
        ),
        Paragraph(
            "OBSERVED requires the full governed timeframe scope and a concise visible basis. PARTIAL requires the visible subset, basis and status detail. If chart identity is unreadable, observed_visible_subject_identity must be null; never force it to match expected identity.",
            warning,
        ),
        Spacer(1, 3 * mm),
    ))
    for question in pack.questions:
        values = " | ".join(question.allowed_answers)
        detail = [
            Paragraph(f"<b>{question.question_id}</b> - {escape(question.wording)}", body),
            Paragraph(f"Scope: {' + '.join(question.timeframe_scope)}", small),
            Paragraph(f"Allowed: {escape(values)}", small),
        ]
        if question.authority != "VISUAL_EVIDENCE_ONLY":
            detail.append(Paragraph(f"Authority: {escape(question.authority)}", small))
        if question.conditional_instruction is not None:
            detail.append(Paragraph(escape(question.conditional_instruction), small))
        detail.extend(Paragraph(escape(value), small) for value in question.constraints)
        story.append(KeepTogether(detail + [Spacer(1, 3 * mm)]))
    document.build(story, onFirstPage=_page, onLaterPages=_page)
    return output.getvalue()


def render_review_batch_pdf(
    batch: ReviewBatchPdf,
    transport: ReviewBatchTransport,
    entries: Sequence[tuple[ReviewQuestionPack, bytes]],
) -> bytes:
    retained = tuple(entries)
    if (
        type(batch) is not ReviewBatchPdf
        or type(transport) is not ReviewBatchTransport
        or transport.review_batch_identity != batch.batch_identity
        or transport.probables_run_identity != batch.probables_run_identity
        or transport.candidate_count != len(batch.members)
        or tuple(pack.review_pack_identity for pack, _ in retained)
        != tuple(member.review_pack_identity for member in batch.members)
    ):
        raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title="KRONOS Intraday V1 Visual Review Batch",
        author="KRONOS",
        invariant=1,
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "KronosBatchTitle", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=18, leading=22, textColor=colors.HexColor("#0a7b55"), alignment=TA_CENTER,
    )
    heading = ParagraphStyle(
        "KronosBatchHeading", parent=styles["Heading2"], fontName="Helvetica-Bold",
        fontSize=11, leading=14, textColor=colors.HexColor("#075f46"), spaceBefore=6, spaceAfter=5,
    )
    body = ParagraphStyle("KronosBatchBody", parent=styles["BodyText"], fontSize=8.5, leading=11)
    small = ParagraphStyle(
        "KronosBatchSmall", parent=body, fontSize=7.5, leading=9.5,
        textColor=colors.HexColor("#3f4c49"),
    )
    table_value = ParagraphStyle("KronosBatchTable", parent=body, fontSize=6.5, leading=8)
    warning = ParagraphStyle(
        "KronosBatchWarning", parent=body, fontName="Helvetica-Bold",
        textColor=colors.HexColor("#7a3500"),
    )
    story = [
        Paragraph("KRONOS INTRADAY V1", title),
        Paragraph("GOVERNED VISUAL REVIEW - BATCH TRANSPORT", heading),
        Spacer(1, 3 * mm),
        Table(
            [
                ["Batch identity", Paragraph(escape(batch.batch_identity), table_value)],
                ["Current Probables Run", Paragraph(escape(batch.probables_run_identity), table_value)],
                ["Generated at (IST)", Paragraph(escape(transport.generated_at.astimezone(_IST).isoformat()), table_value)],
                ["Included individual packs", str(len(batch.members))],
                ["Authority", "ONE TRANSPORT - CANDIDATE EVIDENCE REMAINS INDEPENDENT"],
            ],
            colWidths=(48 * mm, 126 * mm),
            style=_identity_table_style(),
        ),
        Spacer(1, 3 * mm),
        Paragraph(
            "This is the governed combined Review transport. Return exactly one combined JSON Answer Pack. Every candidate retains an independent Review Cycle, Chart Revision, Question Pack, validation result and persisted visual evidence identity.",
            warning,
        ),
        Paragraph(
            "REQUIRED ANSWER FILENAME: <b>"
            + escape(batch_answer_pack_filename(transport)) + "</b>",
            body,
        ),
        Paragraph(
            "Return exactly ONE UTF-8 JSON object containing every candidate Answer Pack. "
            "Do not return individual candidate files. Preserve this Question-batch filename stem exactly; "
            "do not create or change the generation timestamp.",
            warning,
        ),
    ]
    for index, (member, (pack, chart_payload)) in enumerate(zip(batch.members, retained, strict=True), start=1):
        story.extend((
            PageBreak(),
            Paragraph(f"CANDIDATE {index}", heading),
            Table(
                [
                    ["Expected canonical instrument", Paragraph(escape(member.canonical_subject_identity), table_value)],
                    ["Proposed direction", member.direction],
                    ["Review Pack", Paragraph(escape(member.review_pack_identity), table_value)],
                    ["Review Cycle", Paragraph(escape(member.review_cycle_identity), table_value)],
                    ["Review Request", Paragraph(escape(pack.review_request_identity), table_value)],
                    ["Chart Revision", Paragraph(escape(member.chart_revision_identity), table_value)],
                    ["Question Set", Paragraph(escape(f"{pack.question_set_identity} / {pack.question_set_version}"), table_value)],
                ],
                colWidths=(48 * mm, 126 * mm),
                style=_identity_table_style(),
            ),
            Spacer(1, 3 * mm),
            Paragraph("Sponsor-supplied composite", heading),
        ))
        chart = Image(BytesIO(chart_payload))
        scale = min((174 * mm) / chart.imageWidth, (80 * mm) / chart.imageHeight, 1)
        chart.drawWidth = chart.imageWidth * scale
        chart.drawHeight = chart.imageHeight * scale
        story.extend((chart, PageBreak(), Paragraph("Governed Q1-Q10", heading)))
        story.extend((
            Paragraph(escape(pack.trust_boundary), warning),
            Spacer(1, 2 * mm),
            Paragraph(escape(pack.trading_authority_prohibition), warning),
            Spacer(1, 3 * mm),
            Paragraph("Candidate member of the combined JSON Answer Pack", heading),
            Paragraph(
                "Return this candidate inside the single combined Answer Pack. Its candidate object uses schema "
                + escape(ANSWER_PACK_IDENTITY) + " / " + escape(ANSWER_CONTRACT_VERSION)
                + " with exact ordered Q1-Q10 and no additional or trading fields. Candidate association is by the exact identities shown above, never array order.",
                warning,
            ),
            Spacer(1, 3 * mm),
        ))
        for question in pack.questions:
            detail = [
                Paragraph(f"<b>{question.question_id}</b> - {escape(question.wording)}", body),
                Paragraph(f"Scope: {' + '.join(question.timeframe_scope)}", small),
                Paragraph(f"Allowed: {escape(' | '.join(question.allowed_answers))}", small),
            ]
            if question.authority != "VISUAL_EVIDENCE_ONLY":
                detail.append(Paragraph(f"Authority: {escape(question.authority)}", small))
            if question.conditional_instruction is not None:
                detail.append(Paragraph(escape(question.conditional_instruction), small))
            detail.extend(Paragraph(escape(value), small) for value in question.constraints)
            story.append(KeepTogether(detail + [Spacer(1, 3 * mm)]))
    template = batch_answer_pack_template(batch, tuple(pack for pack, _ in retained)).decode("utf-8").strip()
    story.extend((
        PageBreak(),
        Paragraph("EXACT COMBINED ANSWER CONTRACT", heading),
        Paragraph(
            "Return one UTF-8 JSON object only. Replace governed observation placeholders without changing identity fields, keys or candidate population. Do not use Markdown fences or prose.",
            warning,
        ),
        Paragraph(
            "Required filename: <b>" + escape(batch_answer_pack_filename(transport)) + "</b>. "
            "Do not return individual files and do not change the generation timestamp.",
            warning,
        ),
        Spacer(1, 2 * mm),
    ))
    for offset in range(0, len(template), 900):
        story.append(Paragraph(escape(template[offset:offset + 900]), small))
    document.build(story, onFirstPage=_batch_page, onLaterPages=_batch_page)
    return output.getvalue()


def _identity_table_style() -> TableStyle:
    return TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e8f4ef")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#a9bbb4")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("LEADING", (0, 0), (-1, -1), 9),
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
    canvas.drawString(16 * mm, 7 * mm, "KRONOS Intraday V1 - visual evidence only")
    canvas.drawRightString(194 * mm, 7 * mm, f"Page {document.page}")
    canvas.restoreState()


def _batch_page(canvas, document) -> None:  # type: ignore[no-untyped-def]
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#60706a"))
    canvas.drawString(16 * mm, 7 * mm, "KRONOS Intraday V1 - governed combined Review transport")
    canvas.drawRightString(194 * mm, 7 * mm, f"Page {document.page}")
    canvas.restoreState()


def _safe_absolute_directory(path: Path) -> bool:
    return (
        isinstance(path, Path)
        and path.is_absolute()
        and path != Path("/")
        and ".." not in path.parts
    )


__all__ = [
    "DEFAULT_ANSWER_INBOX",
    "DEFAULT_QUESTION_OUTBOX",
    "IntradayReviewPdfTransport",
    "question_pack_filename",
    "render_review_batch_pdf",
    "render_question_pack_pdf",
    "review_batch_filename",
]
