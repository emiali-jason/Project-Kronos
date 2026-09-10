"""Sponsor-authorized independent Analyst header; never derive pixels from expectations."""
from dataclasses import asdict, fields
from datetime import date, datetime
import json
from kronos.intraday.chart_input import (ObservedChartPanel, ChartInputObservation,
    NSE_PANELS, MCX_PANELS, CONTENT, FactObservability, CandleCompletion)
from kronos.intraday.review import ReviewError, ReviewFailure

SCHEMA = "KRONOS-CHART-ANALYST-CORRESPONDENCE"
VERSION = "1.0.0"
FIELD = "chart_observation_header"
PANEL_FIELDS = {f.name for f in fields(ObservedChartPanel)}
HEADER_FIELDS = {"schema_identity", "schema_version", "review_pack_identity",
                 "review_cycle_identity", "chart_binding_identity", "panels"}
ROW_FIELDS = {"slot_role", "slot_timeframe", "panel_state", "right_edge", "observed"}
STATES = {"PRESENT", "ABSENT", "CROPPED", "LOADING", "UNREADABLE", "NOT_OBSERVABLE"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def template(pack, *, paired=False):
    """Only envelope/slot expectations are populated; no observed fact is supplied."""
    return {"schema_identity": SCHEMA, "schema_version": VERSION,
        "review_pack_identity": pack.review_pack_identity,
        "review_cycle_identity": pack.review_cycle_identity,
        "chart_binding_identity": pack.paired_bundle_identity if paired else pack.chart_revision_identity,
        "panels": [{"slot_role": role, "slot_timeframe": frame,
            "panel_state": "NOT_OBSERVABLE", "right_edge": "UNVERIFIABLE",
            "observed": {**{name: None for name in PANEL_FIELDS},
                "content": [[name, "UNVERIFIABLE"] for name in CONTENT]}}
            for role, frame in (MCX_PANELS if paired else NSE_PANELS)]}


def parse(document, *, paired=False):
    """Canonical immutable string in Answer model; strict object in JSON transport."""
    try:
        if type(document) is not dict or set(document) != HEADER_FIELDS:
            raise ValueError
        if document["schema_identity"] != SCHEMA or document["schema_version"] != VERSION:
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
            panel(row["observed"], allow_missing=True)
        return canonical(document)
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID) from error


def panel(raw, *, allow_missing=False):
    if type(raw) is not dict or set(raw) != PANEL_FIELDS:
        raise ValueError
    data = dict(raw)
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
        observed = panel(row["observed"])
        if (observed.role, observed.timeframe) != (row["slot_role"], row["slot_timeframe"]):
            raise ReviewError(ReviewFailure.CHART_CORRESPONDENCE_INVALID)
        panels.append(observed)
    value = ChartInputObservation(chart.chart_revision_identity, chart.payload_sha256,
        chart.review_cycle_identity, chart.probables_run_identity, chart.probable_result_identity,
        "CHART-ANALYST-ANSWER-" + answer.source_sha256, imported_at, tuple(panels))
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
    "For each panel report panel_state PRESENT/ABSENT/CROPPED/LOADING/UNREADABLE/NOT_OBSERVABLE; right_edge and each content item use EXACT/APPROXIMATE/RELATIONAL/NOT_VISIBLE/UNVERIFIABLE/NOT_APPLICABLE as governed observability. PRESENT requires a complete readable panel. Use null for unprovable observed facts, not guessed dates or copied timestamps. Missing precise correspondence can truthfully prevent import.",
    "Observed fields: role NATIVE/REFERENCE; timeframe 1D/1H/4H/15M/5M; exact visible subject, venue, listed series, currency/unit; trading_date YYYY-MM-DD; visible session/timezone; candle_start/end, captured_at and latest_visible_end use timezone-aware ISO timestamps only when independently established; completion COMPLETE/INCOMPLETE (or null when not independently established); entire_panel_observed and opinion_overlays_present are true/false/null. Content records candles, identity, timeframe, price_axis, time_axis, context_lead_in and optional volume/cpr/sma/vwap/rsi/factual_levels. Do not infer absence of future/forming candles from machine expectations. No OCR or second observation source is involved.",
)
