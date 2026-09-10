"""WO-07C presentation helper; governed templates and stores retain authority."""
from io import BytesIO
import json
from xml.sax.saxutils import escape
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Image, Spacer, PageBreak, KeepTogether, Preformatted
from kronos.intraday.visual_contract_v2 import BOUNDARY


def chart_dimensions(width, height):
    scale = min(265 * mm / width, 130 * mm / height)
    return width * scale, height * scale


def render_visual_review(entries, *, expected_filename, answer_template, paired=False, paired_flags=None):
    """entries: exact machine orientation, immutable chart bytes, frozen questions."""
    output = BytesIO()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("Binding", parent=styles["BodyText"], fontSize=7, leading=9, wordWrap="CJK"))
    styles.add(ParagraphStyle("JSON", fontName="Courier", fontSize=7, leading=9))
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
        if paired if paired_flags is None else paired_flags[index]:
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
    story.extend((PageBreak(), paragraph("Chart Analyst Answer Protocol", "Heading1")))
    families = (paired,) if paired_flags is None else tuple(dict.fromkeys(paired_flags))
    for family in families:
        if paired_flags is not None:
            story.append(paragraph("MCX candidate protocol" if family else "NSE candidate protocol", "Heading2"))
        for rule in answer_protocol(paired=family):
            story.extend((paragraph(rule), Spacer(1, 2*mm)))
    if paired_flags is not None:
        story.append(paragraph("BATCH: preserve the ordered member bindings and each nested answer schema. Return ONE file. global_observation_status is per member: agree with NSE candidate status; for MCX use OBSERVED when all R/M/X are OBSERVED, PARTIAL when assessed and unavailable scopes coexist without INVALID, or the uniform unavailable status. INVALID cannot be hidden. No member may be omitted, added, duplicated or reordered."))
    story.extend((PageBreak(), paragraph("Exact bound Answer template", "Heading1"),
        paragraph("Return one UTF-8 JSON file named exactly " + expected_filename +
                  ". This PDF is the only Question input artifact. The template below is part of this PDF. "
                  "Replace observation placeholders only; preserve every envelope key, identity, question order and candidate population. "
                  "Use JSON null, not the string null; no markdown fences, comments, extra keys or prose outside JSON.", "Binding"),
        paragraph("BEGIN EXACT ANSWER JSON", "Binding")))
    # One complete JSON line per flowable keeps long identities intact when
    # copying/extracting text; no arbitrary chunk split can corrupt a token.
    template = json.dumps(json.loads(answer_template), indent=2, ensure_ascii=True)
    for line in template.splitlines():
        story.append(Preformatted(line, styles["JSON"]))
    story.append(paragraph("END EXACT ANSWER JSON", "Binding"))
    document.build(story)
    return output.getvalue()


def answer_protocol(*, paired):
    """Explain the published validator without creating a second validator."""
    common = (
        "Every question has exactly seven fields: question_id, observation_status, answer, visible_timeframes, visible_basis, status_detail, why_not_covered_elsewhere. Use the exact allowed answer vocabulary printed for that question.",
        "OBSERVED requires every governed required timeframe/evidence scope listed for that question to be genuinely assessed. answer must be an allowed value; visible_basis must be truthful nonempty text; visible_timeframes must equal the complete listed scope in its governed order.",
        "PARTIAL is required when only part of that scope can genuinely be assessed. Supply an allowed answer, truthful nonempty visible_basis and truthful nonempty status_detail explaining what is missing or limited. visible_timeframes lists only genuinely assessed qualified panels, in the governed question order, without duplicates. Never append a timeframe merely to satisfy validation. PARTIAL may also describe a genuine limitation within panels that are all listed.",
        "NOT_VISIBLE, UNAVAILABLE and INVALID require answer=null, visible_timeframes=[], visible_basis=null and truthful nonempty status_detail. NOT_APPLICABLE also requires answer=null, visible_timeframes=[] and visible_basis=null; status_detail may be null. Do not report unavailable evidence as neutral or use INVALID placeholders as a completed Answer. Invalid evidence is rejected by import.",
        "All non-null text fields must be nonempty, trimmed text of at most 2000 characters. Explain only qualified completed evidence; omit forming, future, stale, cropped or unobservable panels from visible_timeframes. Expected identity is orientation, never a substitute for independently observed visible identity.",
    )
    if paired:
        family = (
            "MCX envelope: reference_answers contains R1-R5, native_answers M1-M5, cross_market_answers X1-X4, and escape_hatch_answer X5. There is no candidate/global status key in the published MCX envelope: do not add one. Preserve each question-level status truthfully.",
            "R questions assess REFERENCE panels only; M questions NATIVE panels only; X questions compare BOTH roles at each listed timeframe. Governed order is 1D, 4H, 15M, 5M, restricted to the printed question scope. R5 requires 4H/15M/5M; M5 requires 15M/5M; every X1-X5 requires all four timeframes on both sides for OBSERVED. A timeframe in a cross-market answer must be genuinely assessed on both sides, not the union of unrelated panels. Otherwise use PARTIAL with a nonempty limitation or the appropriate unavailable status.",
            "Native MCX is primary and independently machine-corresponded. NYMEX/COMEX is SUPPORTING_VISUAL_CONTEXT_ONLY; independent reference correspondence remains NOT_INDEPENDENTLY_ESTABLISHED, never VALID/VERIFIED. R/X visual observations do not create Promotion or trading authority, reference constituent membership, measured latency or causality. Do not put these explanatory authority labels into new JSON keys.",
            "X5: NONE means no additional material condition after assessing the required scope; it still requires OBSERVED full scope or truthful PARTIAL scope/status_detail and visible_basis. why_not_covered_elsewhere must be null for NONE. MATERIAL_OBSERVATION requires truthful nonempty why_not_covered_elsewhere explaining why R1-R5/M1-M5/X1-X4 do not cover it; do not duplicate them. Unobservable scope is not NONE.",
        )
    else:
        family = (
            "NSE governed order is 1D, 1H, 15M, 5M, restricted to each question's listed scope. Q6/Q8/Q9 require 15M and 5M; Q7/Q10 require all four timeframes for OBSERVED. Q7 with only 15M/5M is not OBSERVED: use truthful PARTIAL, status_detail and consistent candidate status, or report unavailable evidence. Genuine assessment of all four qualified panels may be OBSERVED. Do not add the missing panels without assessment.",
            "Each NSE candidate global_observation_status must be OBSERVED only when every Q1-Q10 status is OBSERVED. It must be PARTIAL when at least one question is OBSERVED or PARTIAL, not all are OBSERVED, and none is INVALID. Any other global status requires every question to have exactly that same status. An INVALID question cannot be hidden under global PARTIAL. Do not add a batch-global status key; candidates remain independent.",
            "Q10: NONE means no additional material condition after assessing the required scope; it still requires OBSERVED full scope or truthful PARTIAL scope/status_detail and visible_basis. why_not_covered_elsewhere must be null for NONE. MATERIAL_OBSERVATION requires truthful nonempty why_not_covered_elsewhere explaining why Q1-Q9 do not cover it; do not duplicate them. Unobservable scope is not NONE.",
        )
    from kronos.intraday.analyst_chart_observation import PROTOCOL
    return common + family + tuple(rule.replace("1D/1H/4H/15M/5M", "1D/4H/15M/5M" if paired else "1D/1H/15M/5M") for rule in PROTOCOL) + (
        "why_not_covered_elsewhere must be null on every question except Q10/X5 with answer MATERIAL_OBSERVATION. Neither NONE nor MATERIAL_OBSERVATION relaxes scope, status or visible_basis requirements. No vote, score, trade recommendation or new analytical consequence is requested.",
    )
