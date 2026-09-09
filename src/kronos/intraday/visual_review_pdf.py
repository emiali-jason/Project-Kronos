"""WO-07C presentation helper; governed templates and stores retain authority."""
from io import BytesIO
from xml.sax.saxutils import escape
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Image, Spacer, PageBreak, KeepTogether
from kronos.intraday.visual_contract_v2 import BOUNDARY


def chart_dimensions(width, height):
    scale = min(265 * mm / width, 130 * mm / height)
    return width * scale, height * scale


def render_visual_review(entries, *, expected_filename, paired=False):
    """entries: exact machine orientation, immutable chart bytes, frozen questions."""
    output = BytesIO()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("Binding", parent=styles["BodyText"], fontSize=7, leading=9, wordWrap="CJK"))
    styles["BodyText"].fontSize = 10
    styles["BodyText"].leading = 13
    document = SimpleDocTemplate(output, pagesize=landscape(A4), leftMargin=14*mm,
        rightMargin=14*mm, topMargin=12*mm, bottomMargin=12*mm,
        title="KRONOS Intraday Visual Review V2", author="KRONOS", invariant=1)
    story = []
    def paragraph(text, style="BodyText"):
        return Paragraph(escape(str(text)), styles[style])
    for index, (orientation, payloads, questions) in enumerate(entries):
        if index:
            story.append(PageBreak())
        story.append(paragraph(orientation[0], "Title"))
        for text in orientation[1:]:
            story.append(paragraph(text, "Binding"))
        story.append(paragraph("Expected Answer: " + expected_filename, "Binding"))
        if paired:
            story.append(paragraph("TOP = INTERNATIONAL BENCHMARK / REFERENCE   |   BOTTOM = NATIVE MCX CONTRACT"))
        for number, payload in enumerate(payloads):
            if number:
                story.append(PageBreak())
            chart = Image(BytesIO(payload))
            chart.drawWidth, chart.drawHeight = chart_dimensions(chart.imageWidth, chart.imageHeight)
            story.extend((Spacer(1, 3*mm), chart))
        story.extend((PageBreak(), paragraph("Independent visual observations", "Heading1"), paragraph(BOUNDARY)))
        for question in questions:
            items = [paragraph(question.question_id + " · " + question.wording, "Heading3"),
                paragraph("Timeframes: " + " / ".join(question.timeframe_scope)),
                paragraph("Allowed: " + " / ".join(question.allowed_answers))]
            if question.conditional_instruction:
                items.append(paragraph(question.conditional_instruction))
            story.append(KeepTogether(items + [Spacer(1, 2*mm)]))
        story.append(paragraph("Complete the accompanying prepopulated JSON template. Preserve all machine binding fields; supply observed identities independently. No trade recommendation or aggregate score is requested."))
    document.build(story)
    return output.getvalue()
