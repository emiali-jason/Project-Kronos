"""Sponsor-authorized independent Analyst header; never derive pixels from expectations."""
from dataclasses import asdict, fields
from datetime import date, datetime
import json
from kronos.intraday.chart_input import (ObservedChartPanel, ChartInputObservation,
    NSE_PANELS, MCX_PANELS, CONTENT, FactObservability, CandleCompletion)
from kronos.intraday.review import ReviewError, ReviewFailure

SCHEMA = "KRONOS-CHART-ANALYST-CORRESPONDENCE"
VERSION = "1.1.0"
LEGACY_VERSION = "1.0.0"
FIELD = "chart_observation_header"
PANEL_FIELDS = {f.name for f in fields(ObservedChartPanel)}
LEGACY_PANEL_FIELDS = PANEL_FIELDS - {"temporal_context"}
HEADER_FIELDS = {"schema_identity", "schema_version", "review_pack_identity",
                 "review_cycle_identity", "chart_binding_identity", "panels"}
ROW_FIELDS = {"slot_role", "slot_timeframe", "panel_state", "right_edge", "observed"}
STATES = {"PRESENT", "ABSENT", "CROPPED", "LOADING", "UNREADABLE", "NOT_OBSERVABLE"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def template(pack, *, paired=False, version=VERSION):
    """Only envelope/slot expectations are populated; no observed fact is supplied."""
    return {"schema_identity": SCHEMA, "schema_version": version,
        "review_pack_identity": pack.review_pack_identity,
        "review_cycle_identity": pack.review_cycle_identity,
        "chart_binding_identity": pack.paired_bundle_identity if paired else pack.chart_revision_identity,
        "panels": [{"slot_role": role, "slot_timeframe": frame,
            "panel_state": "NOT_OBSERVABLE", "right_edge": "UNVERIFIABLE",
            "observed": {**{name: None for name in (PANEL_FIELDS if version == VERSION else LEGACY_PANEL_FIELDS)},
                "content": [[name, "UNVERIFIABLE"] for name in CONTENT],
                **({"temporal_context": {"context_sufficient": None, "visible_labels": [],
                    "later_evidence": "UNKNOWN", "forming_evidence": "UNKNOWN",
                    "forming_excluded": None, "excluded_forming_date": None,
                    "other_contradiction": "UNKNOWN", "basis": None, "exclusion_basis": None}}
                   if version == VERSION else {})}}
            for role, frame in (MCX_PANELS if paired else NSE_PANELS)]}


def parse(document, *, paired=False):
    """Canonical immutable string in Answer model; strict object in JSON transport."""
    try:
        if type(document) is not dict or set(document) != HEADER_FIELDS:
            raise ValueError
        if document["schema_identity"] != SCHEMA or document["schema_version"] not in {VERSION, LEGACY_VERSION}:
            raise ValueError
        if any(type(document[k]) is not str or not document[k] or len(document[k]) > 256
               for k in ("review_pack_identity", "review_cycle_identity", "chart_binding_identity")):
            raise ValueError
        rows = document["panels"]
        if type(rows) is not list or len(rows) != (8 if paired else 4):
            raise ValueError
        for row, slot in zip(rows, MCX_PANELS if paired else NSE_PANELS, strict=True):
            if type(row) is not dict or set(row) != ROW_FIELDS:
                raise ValueError
            if (row["slot_role"], row["slot_timeframe"]) != slot or row["panel_state"] not in STATES:
                raise ValueError
            FactObservability(row["right_edge"])
            panel(row["observed"], allow_missing=True, version=document["schema_version"])
        return canonical(document)
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID) from error


def panel(raw, *, allow_missing=False, version=VERSION):
    if type(raw) is not dict or set(raw) != (PANEL_FIELDS if version == VERSION else LEGACY_PANEL_FIELDS):
        raise ValueError
    data = dict(raw)
    if data.get("temporal_context") is not None:
        from kronos.intraday.visual_temporal import from_document
        data["temporal_context"] = from_document(data["temporal_context"])
    for name in ("candle_start", "candle_end", "captured_at", "latest_visible_end"):
        data[name] = datetime.fromisoformat(data[name]) if data[name] is not None else None
    data["trading_date"] = date.fromisoformat(data["trading_date"]) if data["trading_date"] is not None else None
    data["completion"] = CandleCompletion(data["completion"]) if data["completion"] is not None else None
    if type(data["content"]) is not list or any(type(x) is not list or len(x) != 2 for x in data["content"]):
        raise ValueError
    data["content"] = tuple((k, FactObservability(v)) for k, v in data["content"])
    # Validate nullable observations without turning missing role/timeframe into facts.
    missing = data["role"] is None or data["timeframe"] is None
    if missing and allow_missing:
        ObservedChartPanel(**{**data, "role": data["role"] or "NATIVE", "timeframe": data["timeframe"] or "1D"})
        return None
    return ObservedChartPanel(**data)


def receipt(answer, pack, chart, store, *, imported_at, paired=False):
    """Prepare only. Validated header bytes bind to Answer hash and immutable chart."""
    encoded = answer.chart_observation_header
    if encoded is None:
        return None  # Historical retained-observer contract remains readable.
    raw = json.loads(encoded)
    if parse(raw, paired=paired) != encoded:
        raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
    binding = pack.paired_bundle_identity if paired else chart.chart_revision_identity
    if (raw["review_pack_identity"] != pack.review_pack_identity
        or raw["review_cycle_identity"] != chart.review_cycle_identity
        or raw["chart_binding_identity"] != binding):
        raise ReviewError(ReviewFailure.ANSWER_IDENTITY_MISMATCH)
    panels = []
    for row in raw["panels"]:
        if (row["panel_state"] != "PRESENT" or row["right_edge"] != "EXACT"
            or row["observed"]["role"] is None or row["observed"]["timeframe"] is None):
            raise ReviewError(ReviewFailure.CHART_CORRESPONDENCE_UNVERIFIABLE)
        observed = panel(row["observed"], version=raw["schema_version"])
        if (observed.role, observed.timeframe) != (row["slot_role"], row["slot_timeframe"]):
            raise ReviewError(ReviewFailure.CHART_CORRESPONDENCE_INVALID)
        panels.append(observed)
    value = ChartInputObservation(chart.chart_revision_identity, chart.payload_sha256,
        chart.review_cycle_identity, chart.probables_run_identity, chart.probable_result_identity,
        "CHART-ANALYST-ANSWER-" + answer.source_sha256, imported_at, tuple(panels),
        schema_version="1.1.0" if any(p.temporal_context is not None for p in panels) else "1.0.0")
    existing = store.load_chart_input(chart)
    if existing is not None:
        # Retry after a validated receipt write may use its original receipt time;
        # source digest includes the exact header, pack and all analytical answers.
        if {k:v for k,v in asdict(existing).items() if k != "observed_at"} != {k:v for k,v in asdict(value).items() if k != "observed_at"}:
            raise ReviewError(ReviewFailure.ANSWER_CONFLICT)
        return existing
    return value


def verify_retained(answer, pack, chart, store, *, imported_at, paired=False):
    if answer.chart_observation_header is None:
        return
    existing = store.load_chart_input(chart)
    if existing is None or existing.observed_at > imported_at:
        raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
    if receipt(answer, pack, chart, store, imported_at=imported_at, paired=paired) != existing:
        raise ReviewError(ReviewFailure.INTEGRITY_INVALID)


PROTOCOL = (
    "chart_observation_header is independent Chart Analyst evidence. Preserve schema and binding/slot keys; fill observed values only from the supplied chart pixels, never from printed machine orientation, expected endpoints or the intended contract. slot_role/slot_timeframe are expectations; observed.role/timeframe must report what is actually visible, or null.",
    "Use schema 1.1.0 as printed. For each panel report panel_state PRESENT/ABSENT/CROPPED/LOADING/UNREADABLE/NOT_OBSERVABLE. right_edge and content use EXACT/APPROXIMATE/RELATIONAL/NOT_VISIBLE/UNVERIFIABLE/NOT_APPLICABLE. PRESENT and EXACT right_edge require full readable coverage, not an exact timestamp. Candles, identity, timeframe, price axis, temporal axis and lead-in must be genuinely visible. Cropped/unreadable timing cannot establish compatibility.",
    "KRONOS owns analysis boundary, expected trading date, exact selected completed candle start/end, canonical exchange session/timezone and calendar. Do not reconstruct these from pixels or copy them into observations. In candle_start, candle_end, latest_visible_end, trading_date, session, timezone, completion and captured_at retain only independently visible facts; otherwise null. Raw session/timezone labels need not equal canonical exchange vocabulary. Exact optional timestamps use timezone-aware ISO; trading_date uses YYYY-MM-DD. Never invent missing seconds. captured_at is capture time, not replay time or upload time. Exact optional facts, when supplied, are still checked for contradiction. trading_date, candle_start/end, latest_visible_end and completion describe the qualified completed evidence, not an excluded forming region or a blank axis tick. Put raw axis/display labels in visible_labels.",
    "Fill temporal_context with exactly context_sufficient, visible_labels, later_evidence, forming_evidence, forming_excluded, excluded_forming_date, other_contradiction, basis, exclusion_basis. visible_labels is a list of at most 16 distinct nonempty exact labels actually readable on the temporal axis/right edge; do not copy the Review orientation. basis explains which visible labels, candles and right edge support the findings. Text is trimmed and at most 2000 characters. A blank future date tick alone is not a future candle.",
    "context_sufficient is true only when the visible temporal axis and entire right edge are sufficient to check this Review's date/window, stale context, later evidence and forming scope. Use false/null if insufficient. later_evidence, forming_evidence and other_contradiction each use PRESENT/ABSENT/UNKNOWN. ABSENT is an affirmative visual finding supported by basis and readable labels, never a default for missing evidence. Later-day or completed future candles, stale qualified context, wrong temporal context or another known contradiction must be PRESENT. Unreadable dates/cropped edges and ambiguous scope remain UNKNOWN/insufficient, never PASS.",
    "A visible live/countdown/forming marker requires forming_evidence=PRESENT. If it contaminates qualified evidence set forming_excluded=false. It may be excluded only when the chart visibly and unambiguously separates that same-window current forming candle from the completed evidence used for every answer: forming_excluded=true, excluded_forming_date=its independently visible YYYY-MM-DD, and nonempty exclusion_basis naming the forming region and the completed evidence instead used. Do not infer this exclusion from the machine endpoint. Never exclude a later-day chart or completed future evidence. If forming evidence is ABSENT use forming_excluded=false, excluded_forming_date=null, exclusion_basis=null. If uncertain use UNKNOWN and null; absence of a countdown alone does not prove completion. Optional completion describes the qualified candle, not an excluded forming candle.",
    "KRONOS returns CONFIRMED_COMPATIBLE only with sufficient independent visual context, no later/other contradiction and no prohibited forming evidence, plus valid machine source and strict identity/timeframe/core checks. Known contradiction is VISIBLY_CONTRADICTED; missing proof is INSUFFICIENT_VISUAL_EVIDENCE. No exact observed endpoint is required merely to assert visual compatibility. Compatibility is not a claim that every machine timestamp was visually verified. MCX reference panels remain SUPPORTING_VISUAL_CONTEXT_ONLY / NOT_INDEPENDENTLY_ESTABLISHED even when visually compatible; native contract and machine source checks remain mandatory.",
    "Normal workflow is current Probables, current Review and same-window chart, not mandatory Bar Replay. Same date alone is insufficient if the viewport has advanced beyond the boundary. Forming evidence must be excluded from the presentation or clearly outside the qualified scope. Historical Review plus later live chart is prohibited; historical replay is exceptional. At Opening, governed prior completed higher-timeframe context may be lawful: do not demand a forming current higher-timeframe bar or delay 09:30 admission. Never use unqualified regions to answer questions.",
)
