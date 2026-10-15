"""TE-02 independent Astra-Ultra mandate and deterministic offline transport."""

from io import BytesIO
import json
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from reportlab.lib.pagesizes import A4, A3, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (BaseDocTemplate, Frame, Image, KeepTogether,
                               NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer)

from kronos.theta.contracts import answer_template, digest, encode


COMMON = (
    ("Research depth before response speed", "ASTRA-ULTRA is the independent research/forecast Analyst. Research depth and evidentiary quality take precedence over response speed. There is no Intraday response-time constraint. Take the time required to investigate deeply, open and compare sources, verify important claims, challenge the initial conclusion and revise analytical judgment where warranted. Do not manufacture research volume; depth means relevant, verified, decision-useful evidence. KRONOS does not forecast or call Astra automatically."),
    ("Primary analytical question", "Given the supplied chart evidence and all relevant information legitimately available by the fixed information-set cutoff T0, within what price range do you expect the specified underlying MCX futures contract's authoritative option-expiry settlement outcome to fall, and what percentage confidence do you assign to terminal containment? Analyse E1 and E2 independently; do not construct E2 by merely widening E1."),
    ("Exact target and independence", "Analyse only the exact governed E1/E2 identities supplied here. Never substitute spot, continuous futures, COMEX/NYMEX, an option premium, a generic commodity price, another expiry or guessed nearest futures. International markets are reference evidence, not forecast targets. Do not optimize for Imran's intended option trade or produce convenient ranges for option selling. If identity, mapping, units or required evidence is missing/contradictory, DO NOT GUESS: report NOT_EVALUABLE and the gap to Sponsor outside the accepted machine Answer flow; never fill a missing forecast with invented numbers."),
    ("Chart assessment T1-T8", "T1: What visible higher-timeframe and multi-timeframe structure matters? T2: What support, resistance and structural boundaries are materially visible? T3: What visible trend, momentum, volatility, price behavior and volume/context indicate? T4: Do 1D, 4H and 1H agree or disagree? T5: How does the international reference compare with MCX? T6: What visible evidence supports higher prices? T7: What supports lower prices? T8: What is unclear, conflicting or unobservable? Distinguish OBSERVED CHART EVIDENCE from ANALYTICAL JUDGMENT. Do not invent indicators, candles, levels, labels or chart times. The supplied image is one exact original composite: reference 1D/4H/1H on top, MCX 1D/4H/1H below. Sponsor role attestation is not independently verified pixel identity."),
    ("Independent global research", "Charts alone are insufficient. Perform extensive independent internet research that is commodity-specific, not a generic macro-news summary. Investigate material global trends, supply/demand, inventories, production, consumption, USD, USD/INR, rates, real yields, inflation, central banks, growth, China, geopolitics, sanctions, tariffs/trade policy, weather, seasonality and commodity-specific developments. Distinguish transient headlines from developments relevant to each exact horizon; explain MCX/India transmission rather than mechanically copying international price movement."),
    ("Shared Global Macro context", "The exact shared composite contains DXY / US Dollar Index, US 10Y, US 30Y, USD/INR, Nasdaq-100, USD/CNH, CSI 300 and Dow Jones. It supports the commissioned commodity only where economically/materially relevant. It is not a sixth forecast subject; do not produce Macro E1/E2 forecasts or force every panel into every commodity."),
    ("Events through E1 and E2", "Identify important events known at T0 occurring before each expiry: central-bank meetings, inflation, employment, China data, OPEC+, inventory publications, industry reports, supply decisions, geopolitical deadlines and weather/seasonal transitions where material. A future scheduled event may be known at T0; its unknowable outcome is not a fact. Reflect event risk in uncertainty for each horizon."),
    ("Bull, bear, base and reconciliation", "For each horizon consider BULL: what could drive terminal price materially higher? BEAR: materially lower? BASE: what is best supported by complete evidence? Actively seek evidence AGAINST the initial conclusion. Does fundamental/global research CONFIRM, QUALIFY or CONTRADICT the chart? Explain conflicts, dominant evidence, weighting and why; reflect disagreement honestly in range/confidence."),
    ("Range and confidence quality", "Return terminal [LOWER, UPPER] with LOWER < UPPER and correct governed contract price units. Balance coverage with usefulness/sharpness; do not optimize for the widest interval or reverse-engineer around desired sold strikes. CONFIDENCE is 0-100% assessed probability of authoritative terminal settlement containment. It is NOT profitability, OTM probability, no-touch probability, expected return or probability price never leaves the range. Do not inflate confidence merely by widening. Explain effects of evidence quality/agreement, chart/fundamental clarity, horizon, volatility, event risk, counterevidence, source quality and uncertainty. Report material intraperiod path risk separately; never redefine the terminal interval as a no-touch range."),
    ("Source discipline and fixed information set", "Prioritize exchanges, government/statistical agencies, central banks, recognized commodity/energy agencies, official producer/company disclosures, reputable financial news and established market/research sources. Cite material sources actually opened/used. T0 / INFORMATION_SET_CUTOFF is frozen at Question commissioning. You may retrieve and analyse sources after T0 without a response-speed deadline, but evidence first published or legitimately available after T0 must be excluded. Never use hindsight, later updates or future event outcomes. Record published_at (null only when unknown), supported available_at, and truthful accessed_at separately. available_at must be supported in evidence text and at/before T0, not inferred from an unknown publication date. Known published_at must also be at/before T0. Actual retrieval may be later and must be no later than analyzed_at. Source timestamps are Analyst assertions, not KRONOS verification of source truth."),
    ("Required response and exact machine template", "Populate the EXACT answer-template.json, one UTF-8 JSON object without fences, extra keys or renamed/removed fields. Preserve Question identity/hash, commodity, chart SHA, and every exact E1/E2 target field verbatim; do not normalize or silently repair contract identifiers. Numeric LOWER, UPPER and confidence_pct are decimal strings. Replace required null placeholders; published_at alone may remain null. information_cutoff is prefilled and immutable; analyzed_at is the truthful later completion time. Use chart_analysis for structure/regime, levels, momentum/volatility, timeframe agreement, reference-vs-MCX and chart risks; global_research for commodity/macro/MCX transmission/events; supporting_evidence and opposing_evidence for bull/bear; uncertainty for unresolved and path risks; reasoning for base case, reconciliation and independent range/confidence rationale. Each horizon has its own narrative and material sources. In text distinguish FACT, ANALYTICAL_JUDGMENT, UNCERTAINTY and FORECAST where useful; retain governed classification enums FACT, RESEARCH_RESULT or HYPOTHESIS (judgments/forecasts/uncertainties are HYPOTHESIS unless directly supported otherwise). The blank template is not an acceptable completed Answer."),
    ("Cross-commodity consistency and analytical boundary", "Each canonical commodity Question and Answer remains independent. If Sponsor supplies all five packs, after independent analysis check unexplained contradictions involving USD, rates, inflation, China, growth, sentiment and energy/inflation relationships. Do not force one macro narrative or copy another commodity's forecast; legitimate commodity-specific forces may differ. Return each Answer to its own canonical Question/template. Do not recommend CE/PE strikes, lots, entry, exit, stop, hedge, roll, adjustment, margin or option premium. No broker or trading instruction; no Sponsor-facing Greeks. Research is analytical only."),
    ("Final Astra validation", "Before return verify correct Question, cycle, commodity, E1/E2, exact underlying MCX futures and settlement reference; LOWER < UPPER, units, confidence 0-100%, horizons not reversed and independently analysed; genuine material sources available at/before T0, current research actually performed and counterevidence considered; visible chart observations only, reference/MCX distinguished, Macro used only where relevant, conflicts disclosed and uncertainty honest; no option strategy, strike, trading or broker instruction."),
)

COMMODITY = {
    "GOLDM": ("COMEX Gold + MCX Gold Mini", "International Gold structure; US rates and real yields; USD; central-bank Gold activity; ETF/investment flows; physical and India/China demand; geopolitical safe-haven demand; positioning/inventories; scheduled risk events; USD/INR transmission to MCX."),
    "SILVERM": ("COMEX Silver + MCX Silver Mini", "International Silver; Gold/Silver relationship without assuming Silver simply follows Gold; USD/rates; industrial demand including solar/PV and electronics; mines/supply; inventories; China/global manufacturing; investment demand; positioning; USD/INR transmission to MCX."),
    "COPPER": ("COMEX Copper + MCX Copper", "Perform especially deep Copper research: COMEX/LME/global Copper; China demand, property, infrastructure, manufacturing/PMI; global growth; inventories/exchange stocks and physical tightness; mine disruptions and producer-country developments; concentrate availability and treatment/refining conditions; smelter activity and production guidance; energy-transition/grid demand; tariffs/trade policy; USD; reliable spreads/term evidence; USD/INR. Do not mechanically copy COMEX movement into MCX."),
    "CRUDEOIL": ("NYMEX Light Crude + MCX Crude Oil", "International benchmark structure; OPEC+ policy/compliance; production; inventories; demand forecasts; refinery activity and product demand; geopolitical supply risk; sanctions/shipping disruption; US production; China demand/global growth; seasonality; futures term structure; scheduled OPEC+/policy events; USD and USD/INR transmission to MCX."),
    "NATURALGAS": ("NYMEX Natural Gas + MCX Natural Gas", "Weather and temperature regime; storage/injections/withdrawals; production; LNG feedgas/exports; pipelines, outages and maintenance; power burn and industrial demand; seasonal transition; international LNG where relevant; futures curve/term structure; USD/INR transmission to MCX. Reflect genuine Natural Gas uncertainty."),
}


def instructions(subject):
    return [f"{title}: {text}" for title, text in COMMON] + [
        "Commodity-specific investigation: " + COMMODITY[subject][1]]


def pack_name(question, kind):
    subject = question["subjects"][0]
    stem = ("SYNTHETIC_" if question["synthetic"] else "") + "THETA_" + question["cycle_id"][4:20] + "_" + subject + "_" + question["question_id"][4:]
    return stem + {"pdf": "_QUESTION.pdf", "zip": "_QUESTION.zip", "template": "_ANSWER_TEMPLATE.json"}[kind]


def archive(files):
    files = dict(files)
    files["manifest.json"] = encode({name: digest(value) for name, value in sorted(files.items())})
    output = BytesIO()
    with ZipFile(output, "w") as result:
        for name, value in sorted(files.items()):
            info = ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            result.writestr(info, value)
    return output.getvalue()


def render_question(question, charts, *, presentation=None):
    # TE-04C supplies a V3 presentation projection only; legacy defaults and
    # canonical V1/V2 evidence remain unchanged. Never use this view as identity.
    output = BytesIO()
    chart_size = landscape(A3)
    doc = BaseDocTemplate(output, pagesize=A4, leftMargin=42, rightMargin=42,
                          topMargin=42, bottomMargin=42, invariant=1,
                          title="KRONOS Theta - " + question["subjects"][0] + " - Astra-Ultra Question")
    styles = getSampleStyleSheet()
    body = ParagraphStyle("ThetaTE02Body", parent=styles["BodyText"], fontSize=10,
                          leading=14, spaceAfter=9, splitLongWords=True)
    small = ParagraphStyle("ThetaTE02Technical", parent=body, fontSize=8,
                           leading=10, spaceAfter=4)
    heading = ParagraphStyle("ThetaTE02Heading", parent=styles["Heading2"],
                             keepWithNext=True)

    def paragraph(value, style=body):
        if presentation is not None:
            value = str(value).replace("\u2013", "-").replace("\u2014", "-").replace("\u2011", "-")
        return Paragraph(escape(str(value)).replace("\n", "<br/>"), style)

    def footer(canvas, current):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        label = "SYNTHETIC - NOT FOR GENUINE FORECASTING" if question["synthetic"] else "External analytical evidence - no trading authority"
        canvas.drawString(30, 18, "KRONOS THETA | " + label)
        canvas.drawRightString(canvas._pagesize[0] - 30, 18, str(current.page))
        canvas.restoreState()

    doc.addPageTemplates([
        PageTemplate(id="text", frames=Frame(42,42,A4[0]-84,A4[1]-84), onPage=footer, pagesize=A4),
        PageTemplate(id="chart", frames=Frame(30,36,chart_size[0]-60,chart_size[1]-72), onPage=footer, pagesize=chart_size),
    ])
    subject = question["subjects"][0]
    story = [paragraph("KRONOS / THETA EARNERS", styles["Title"]),
             paragraph(subject + " | ASTRA-ULTRA QUESTION", heading)]
    if question["synthetic"]:
        story.append(paragraph("SYNTHETIC - NOT FOR GENUINE FORECASTING", heading))
    story += [paragraph("Independent commodity research. Manually submit this PDF, the exact original images and the Answer template to Astra-Ultra."),
              paragraph("Information-set cutoff T0: " + question["information_cutoff"]),
              paragraph("This cutoff is frozen. Research, retrieval and analysis may occur later; later first-available evidence must not drive this forecast."),
              paragraph("Reference relationship: " + COMMODITY[subject][0])]
    for target in question["targets"]:
        block = [paragraph(target["horizon"] + " | exact terminal target", heading)]
        for label, field in (("Option expiry", "option_expiry"), ("Expiry endpoint", "expires_at"),
                             ("Underlying MCX future", "underlying_future"), ("Futures expiry", "futures_expiry"),
                             ("Settlement reference", "settlement_reference")):
            block.append(paragraph(label + ": " + target[field]))
        if presentation is not None:
            block.append(paragraph("Price unit: " + target["price_unit"]))
        story.append(KeepTogether(block))
    story.append(paragraph("Use the exact contract's governed price units; if unavailable, report NOT_EVALUABLE rather than assume units."))
    for label, chart in ((subject + " exact commodity composite", question["charts"][0]),
                         ("Shared Global Macro - supporting evidence only", question["macro_chart"])):
        story += [NextPageTemplate("chart"), PageBreak(), paragraph(label, heading),
                  paragraph("Exact original; no crop, OCR, annotation, splitting or analytical modification. " + chart["label"], small)]
        image = Image(BytesIO(charts[chart["sha256"]]))
        scale = min((chart_size[0]-84)/image.imageWidth, (chart_size[1]-180)/image.imageHeight)
        image.drawWidth, image.drawHeight = image.imageWidth*scale, image.imageHeight*scale
        story += [Spacer(1,8), image, Spacer(1,8), paragraph("Original SHA-256: " + chart["sha256"], small),
                  paragraph("Chart declaration cutoff: " + chart["information_cutoff"] + " (receipt/declaration, not independently verified visible chart time).", small)]
    story += [NextPageTemplate("text"), PageBreak(), paragraph(subject + " | Research mandate", styles["Title"])]
    for title, text in (COMMON if presentation is None else presentation["mandate"]):
        if title == "Events through E1 and E2":
            story += [paragraph(subject + " specific investigation", heading), paragraph(COMMODITY[subject][1])]
        if title:
            story.append(paragraph(title, heading))
        story.append(KeepTogether([paragraph(text)]) if not title else paragraph(text))
    story += [paragraph("Applicable governed methodology", heading),
              paragraph(question["methodology_instructions"]),
              paragraph("Compact technical binding", heading)]
    if presentation is None:
        technical = {key: question[key] for key in ("question_id", "cycle_id", "methodology_reference", "information_cutoff", "answer_schema_identity", "answer_schema_version")}
        technical["expected_answer_filename"] = question["question_id"] + "_ANSWERS.json"
    else:
        technical = presentation["technical"]
    for key,value in technical.items():
        story.append(paragraph(key + ": " + str(value), small))
    story.append(paragraph("Question and Answer files preserve exact identities. Full cycle, commodity/Macro revisions, target authority references and checksums are in the accompanying canonical JSON. The eventual Answer destination is KRONOS REVIEW PACK / Theta Earners / CHATGPT ANSWERS; Answer UX changes are outside TE-02.", small))
    doc.build(story)
    return output.getvalue()


def render_transport(question, charts):
    pdf = render_question(question, charts)
    template = json.dumps(answer_template(question), indent=2, ensure_ascii=False).encode()
    files = {"questions.pdf":pdf, "question.json":encode(question), "answer-template.json":template,
             "README.txt": ("Manually submit to ASTRA-ULTRA. " + ("SYNTHETIC - NOT FOR GENUINE FORECASTING. " if question["synthetic"] else "") +
                            "Use the exact Answer template. Original charts are authoritative evidence bytes; manifest.json checks every file. Expected Answer: " + question["question_id"] + "_ANSWERS.json\n").encode()}
    for chart in [*question["charts"], question["macro_chart"]]:
        suffix = ".png" if chart["media_type"] == "image/png" else ".jpg"
        files["charts/" + chart["subject"] + "-" + chart["sha256"] + suffix] = charts[chart["sha256"]]
    return pdf, archive(files), template


def combined_transport(batch, packs, macro):
    files = {"transport.json":encode(batch), "README.txt": (
        "SYNTHETIC - NOT FOR GENUINE FORECASTING.\n" if batch["synthetic"] else "") .encode() +
        b"Transport convenience only: each individual canonical Question/template remains authoritative. Common exact Macro evidence is stored once under shared/. Match SHA-256 in each question.json. Never merge or rename individual Answer identities. Partial status is explicit in transport.json.\n"}
    for subject, (question,pdf,template,commodity) in packs.items():
        prefix = "individual/" + subject + "/"
        files[prefix+"questions.pdf"] = pdf
        files[prefix+"question.json"] = encode(question)
        files[prefix+"answer-template.json"] = template
        chart = question["charts"][0]
        files[prefix+"charts/"+subject+(".png" if chart["media_type"]=="image/png" else ".jpg")] = commodity
    chart, payload = macro
    files["shared/GLOBAL_MACRO-"+chart["sha256"]+(".png" if chart["media_type"]=="image/png" else ".jpg")] = payload
    return archive(files)
