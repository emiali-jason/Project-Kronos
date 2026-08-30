"""Deterministic PDF/JSON transport for one paired MCX Review Pack."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
from io import BytesIO
import json
from typing import Mapping

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer

from kronos.intraday.review import ReviewError, ReviewFailure
from kronos.intraday.review_mcx_paired import (
    MCX_PAIRED_QUESTIONS,
    McxPairedChartBundle,
    McxPairedReviewPack,
)
from kronos.intraday.review_mcx_paired_answer import answer_template


MCX_PAIRED_TRANSPORT_IDENTITY = "KRONOS-INTRADAY-MCX-PAIRED-REVIEW-TRANSPORT-V1"
MCX_PAIRED_TRANSPORT_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class McxPairedReviewTransport:
    transport_identity: str
    review_pack_identity: str
    paired_bundle_identity: str
    question_filename: str
    expected_answer_filename: str
    generated_at: datetime
    question_pdf_sha256: str
    answer_template_sha256: str
    integrity_identity: str
    schema_identity: str = MCX_PAIRED_TRANSPORT_IDENTITY
    schema_version: str = MCX_PAIRED_TRANSPORT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "transport_identity", "integrity_identity")
        stem = f"KRONOS_INTRADAY_MCX_PAIRED_REVIEW_{self.review_pack_identity[-12:]}"
        if (
            self.question_filename != f"{stem}_QUESTIONS.pdf"
            or self.expected_answer_filename != f"{stem}_ANSWERS.json"
            or not _aware(self.generated_at)
            or self.schema_identity != MCX_PAIRED_TRANSPORT_IDENTITY
            or self.schema_version != MCX_PAIRED_TRANSPORT_VERSION
            or self.transport_identity != _identity("INTRADAY-MCX-PAIRED-TRANSPORT-", values)
            or self.integrity_identity != _identity("INTEGRITY-INTRADAY-MCX-PAIRED-TRANSPORT-", values)
        ):
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)


def create_paired_transport(
    *, pack: McxPairedReviewPack, bundle: McxPairedChartBundle,
    native_chart_payload: bytes, reference_chart_payload: bytes,
    generated_at: datetime,
) -> tuple[McxPairedReviewTransport, bytes, bytes]:
    if (
        pack.paired_bundle_identity != bundle.bundle_identity
        or sha256(native_chart_payload).hexdigest() != bundle.native_chart_payload_sha256
        or sha256(reference_chart_payload).hexdigest() != bundle.reference_chart_payload_sha256
        or not _aware(generated_at)
    ):
        raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
    answer = answer_template(pack, bundle)
    pdf = _render_pdf(pack, bundle, native_chart_payload, reference_chart_payload)
    stem = f"KRONOS_INTRADAY_MCX_PAIRED_REVIEW_{pack.review_pack_identity[-12:]}"
    values = {
        "review_pack_identity": pack.review_pack_identity,
        "paired_bundle_identity": bundle.bundle_identity,
        "question_filename": f"{stem}_QUESTIONS.pdf",
        "expected_answer_filename": f"{stem}_ANSWERS.json",
        "generated_at": generated_at,
        "question_pdf_sha256": sha256(pdf).hexdigest(),
        "answer_template_sha256": sha256(answer).hexdigest(),
        "schema_identity": MCX_PAIRED_TRANSPORT_IDENTITY,
        "schema_version": MCX_PAIRED_TRANSPORT_VERSION,
    }
    transport = McxPairedReviewTransport(
        transport_identity=_identity("INTRADAY-MCX-PAIRED-TRANSPORT-", values),
        integrity_identity=_identity("INTEGRITY-INTRADAY-MCX-PAIRED-TRANSPORT-", values),
        **values,
    )
    return transport, pdf, answer


def transport_from_bytes(payload: bytes) -> McxPairedReviewTransport:
    try:
        raw = json.loads(payload.decode("utf-8"))
        if type(raw) is not dict:
            raise ValueError
        raw["generated_at"] = datetime.fromisoformat(raw["generated_at"])
        value = McxPairedReviewTransport(**raw)
        from kronos.intraday.review_mcx_paired import artifact_bytes
        if artifact_bytes(value) != payload:
            raise ValueError
        return value
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise ReviewError(ReviewFailure.INTEGRITY_INVALID) from error


def _render_pdf(pack: McxPairedReviewPack, bundle: McxPairedChartBundle, native: bytes, reference: bytes) -> bytes:
    output = BytesIO()
    document = SimpleDocTemplate(output, pagesize=A4, leftMargin=15*mm, rightMargin=15*mm,
                                 topMargin=14*mm, bottomMargin=14*mm,
                                 title="KRONOS MCX Paired Review", author="KRONOS", invariant=1)
    styles = getSampleStyleSheet()
    story: list[object] = [
        Paragraph("KRONOS INTRADAY · MCX PAIRED REVIEW", styles["Title"]),
        Paragraph(f"Native: {pack.canonical_mcx_subject_identity} · {pack.direction}", styles["Heading2"]),
        Paragraph(f"Reference: {bundle.reference_relationship.reference_name} · {bundle.reference_relationship.governed_visible_identity} · {bundle.reference_relationship.series_kind.value}", styles["BodyText"]),
        Paragraph("Visual timeframes: 1D / 4H / 15M / 5M. Visual 4H is higher-order visual context and is not Native machine 1H.", styles["BodyText"]),
        Spacer(1, 4*mm), Image(BytesIO(native), width=175*mm, height=105*mm),
        PageBreak(), Paragraph("INTERNATIONAL REFERENCE", styles["Heading1"]),
        Image(BytesIO(reference), width=175*mm, height=105*mm),
        PageBreak(), Paragraph("INDEPENDENT OBSERVATION QUESTIONS", styles["Heading1"]),
    ]
    for question in MCX_PAIRED_QUESTIONS:
        story.append(Paragraph(f"{question.question_id} · {question.side} · {question.timeframe} · {question.observation}<br/>Allowed: {', '.join(question.allowed_answers)}", styles["BodyText"]))
        story.append(Spacer(1, 2*mm))
    story.append(Paragraph("No global MCX synthesis, promotion, trading, Risk or execution answer is requested.", styles["BodyText"]))
    document.build(story)
    return output.getvalue()


def _without(value: object, *names: str) -> dict[str, object]:
    return {name: item for name, item in asdict(value).items() if name not in names}


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(_canonical(_normalize(value))).hexdigest().upper()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _normalize(value: object) -> object:
    if hasattr(value, "__dataclass_fields__"): return _normalize(asdict(value))
    if isinstance(value, datetime): return value.isoformat()
    if isinstance(value, Mapping): return {str(k): _normalize(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)): return [_normalize(item) for item in value]
    return value


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


__all__ = ["MCX_PAIRED_TRANSPORT_IDENTITY", "MCX_PAIRED_TRANSPORT_VERSION", "McxPairedReviewTransport", "create_paired_transport", "transport_from_bytes"]
