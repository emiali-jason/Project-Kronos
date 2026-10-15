"""Portable, exact-chart Question PDF and deterministic offline ZIP transport."""

from io import BytesIO
import json
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer

from kronos.theta.contracts import answer_template, digest, encode


def render_question(question: dict, charts: dict[str, bytes]) -> bytes:
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, leftMargin=42, rightMargin=42,
                           topMargin=42, bottomMargin=42, invariant=1,
                           title="KRONOS Theta Earners - External Analyst Question Pack")
    styles = getSampleStyleSheet()
    body = ParagraphStyle("ThetaBody", parent=styles["BodyText"], fontSize=9,
                          leading=13, spaceAfter=8, splitLongWords=True)
    heading = styles["Heading2"]
    target_style = ParagraphStyle("ThetaTarget", parent=body, fontSize=8.5,
                                  leading=11, spaceAfter=2)
    story = []

    def paragraph(value, style=body):
        return Paragraph(escape(str(value)).replace("\n", "<br/>"), style)

    story += [paragraph("KRONOS THETA EARNERS", styles["Title"]),
              paragraph("External Chart Analyst Question Pack", heading),
              paragraph(question["question_id"]),
              paragraph("Created: " + question["created_at"]),
              paragraph("Required Answer filename: " + question["question_id"] + "_ANSWERS.json")]
    for instruction in question["instructions"]:
        story.append(paragraph(instruction))
    story += [paragraph("Approved applicable methodology", heading),
              paragraph(question["methodology_reference"]),
              paragraph(question["methodology_instructions"]),
              paragraph("Machine contract", heading),
              paragraph("The ZIP contains question.json and answer-template.json. The exact template is mandatory; numeric values are decimal strings. Every analysis statement has classification FACT, RESEARCH_RESULT or HYPOTHESIS. External research cannot grant OPERATIONAL_AUTHORITY. Hashes provide byte integrity, not proof of Analyst authorship or research truth.")]
    for chart in question["charts"]:
        story += [PageBreak(), paragraph(chart["subject"], styles["Title"]),
                  paragraph("Sponsor-declared chart label: " + chart["label"]),
                  paragraph("Chart information cutoff: " + chart["information_cutoff"]),
                  paragraph("Exact original image SHA-256: " + chart["sha256"])]
        image = Image(BytesIO(charts[chart["sha256"]]))
        scale = min(511 / image.imageWidth, 310 / image.imageHeight, 1)
        image.drawWidth, image.drawHeight = image.imageWidth * scale, image.imageHeight * scale
        story += [Spacer(1, 8), image, Spacer(1, 10)]
        for target in question["targets"]:
            if target["subject"] == chart["subject"]:
                block = [paragraph(target["horizon"] + " - exact forecast target", heading)]
                block.extend(paragraph(f"{key}: {value}", target_style)
                             for key, value in target.items())
                story.append(KeepTogether(block))

    def footer(canvas, _):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.drawString(42, 22, "KRONOS Theta V1 | External evidence only | No trading authority")
        canvas.drawRightString(A4[0] - 42, 22, str(doc.page))
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()


def render_transport(question: dict, charts: dict[str, bytes]) -> tuple[bytes, bytes]:
    pdf = render_question(question, charts)
    files = {"questions.pdf": pdf, "question.json": encode(question),
             "answer-template.json": json.dumps(answer_template(question), indent=2,
                                                  ensure_ascii=False).encode()}
    for chart in question["charts"]:
        suffix = ".png" if chart["media_type"] == "image/png" else ".jpg"
        files["charts/" + chart["subject"] + "-" + chart["sha256"] + suffix] = charts[chart["sha256"]]
    files["manifest.json"] = encode({name: digest(payload) for name, payload in files.items()})
    result = BytesIO()
    with ZipFile(result, "w") as archive:
        for name, payload in sorted(files.items()):
            info = ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, payload)
    return pdf, result.getvalue()
