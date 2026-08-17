"""Escaped HTML body for the read-only Intraday evidence workstation."""

from __future__ import annotations

from decimal import Decimal
from html import escape

from kronos.application.intraday_workstation import IntradayWorkstationSnapshot
from kronos.intraday.contracts import CandleCompletion, IntradayTimeframe
from kronos.intraday.telemetry import TelemetryType


def render_intraday_body(snapshot: IntradayWorkstationSnapshot) -> str:
    selected_id = (
        "" if snapshot.selected_instrument is None
        else snapshot.selected_instrument.canonical.canonical_instrument_id
    )
    options = "".join(
        f'<option value="{escape(item.canonical.canonical_instrument_id)}"'
        f'{" selected" if item.canonical.canonical_instrument_id == selected_id else ""}>'
        f'{escape(item.canonical.canonical_instrument_id)}</option>'
        for item in snapshot.instruments
    )
    selector = (
        '<form class="intraday-selector" method="get" action="/intraday">'
        '<label for="instrument">Canonical Instrument</label>'
        f'<select id="instrument" name="instrument">{options}</select>'
        '<button type="submit">Inspect evidence</button></form>'
        if options else '<p class="intraday-unavailable">UNAVAILABLE — no governed DOMAIN-001 publication.</p>'
    )
    body = (
        '<div class="intraday-warning"><strong>ENGINEERING / EVIDENCE</strong>'
        '<span>NO TRADING CONCLUSION — EVIDENCE WORKSTATION</span></div>' + selector
    )
    if snapshot.selected_instrument is None:
        return body + _unavailable("Instrument / Session")
    body += _instrument_panel(snapshot)
    if snapshot.evidence is None:
        return body + _unavailable(
            "Factual Evidence",
            "No retained governed composition exists for this instrument.",
        )
    bundle = snapshot.evidence
    body += _session_panel(bundle.composition)
    structural = {item.timeframe: item for item in bundle.structural_evidence}
    body += '<div class="intraday-timeframes">'
    for evidence in bundle.composition.evidence:
        item = structural.get(evidence.reconciliation.timeframe)
        body += _timeframe_panel(evidence.reconciliation, item)
    body += "</div>"
    body += _context_panels(bundle.slice1e_context)
    body += _structure_panel(bundle.structural_evidence)
    body += _telemetry_panels(bundle.shadow_telemetry)
    body += _provenance_panel(snapshot)
    return body


def _instrument_panel(snapshot: IntradayWorkstationSnapshot) -> str:
    instrument = snapshot.selected_instrument
    assert instrument is not None
    canonical = instrument.canonical
    binding = instrument.provider_binding
    provider = (
        _facts((
            ("Binding", instrument.binding_status.value),
            ("Provider", "UNAVAILABLE" if binding is None else binding.provider),
            ("Provider Symbol", "UNAVAILABLE" if binding is None else binding.provider_symbol),
            ("Provider Token", "UNAVAILABLE" if binding is None else str(binding.provider_instrument_token)),
        ))
    )
    return (
        '<section class="intraday-panel"><h2>Instrument Identity</h2>'
        '<h3>Canonical</h3>' + _facts((
            ("Instrument", canonical.canonical_instrument_id),
            ("Exchange", canonical.exchange),
            ("Segment", canonical.segment),
            ("Instrument Type", canonical.instrument_type),
            ("Publication", instrument.publication_identity),
        )) + '<h3>Provider Binding (separate)</h3>' + provider + "</section>"
    )


def _session_panel(composition) -> str:  # type: ignore[no-untyped-def]
    session = composition.market_session
    schedule = session.schedule
    completeness = (
        "DATA_INCOMPLETE"
        if any(item.reconciliation.result.value == "DATA_INCOMPLETE" for item in composition.evidence)
        else "UNAVAILABLE"
        if any(item.reconciliation.result.value == "UNAVAILABLE" for item in composition.evidence)
        else "AVAILABLE"
    )
    windows = "UNAVAILABLE" if schedule is None else ", ".join(
        f"{item.opens_at.isoformat()} → {item.closes_at.isoformat()}"
        for item in schedule.windows
    ) or "NONE"
    return (
        '<section class="intraday-panel"><h2>Market / Session — DOMAIN-008</h2>'
        + _facts((
            ("Trading Date", session.trading_date.isoformat()),
            ("Exchange", session.exchange),
            ("Session Identity", "UNAVAILABLE" if schedule is None else schedule.session_id),
            ("Session Status", session.state.value),
            ("Session Windows", windows),
            ("Market Availability", "AVAILABLE" if session.availability else "UNAVAILABLE"),
            ("Observation Boundary", session.observed_at.isoformat()),
            ("Calendar Version", "UNAVAILABLE" if schedule is None else schedule.source_version),
            ("Data Completeness", completeness),
            ("Session End", str(session.session_end).upper()),
        )) + "</section>"
    )


def _timeframe_panel(reconciliation, structural) -> str:  # type: ignore[no-untyped-def]
    completed = reconciliation.structural_candles
    latest = completed[-1] if completed else None
    incomplete = tuple(
        item for item in reconciliation.observations
        if item.completion is CandleCompletion.INCOMPLETE
    )
    latest_text = "UNAVAILABLE" if latest is None else (
        f"{latest.boundary.start.isoformat()} → {latest.boundary.end.isoformat()}"
    )
    ohlcv = "UNAVAILABLE" if latest is None else (
        f"O {_number(latest.open)} · H {_number(latest.high)} · "
        f"L {_number(latest.low)} · C {_number(latest.close)} · V {latest.volume}"
    )
    missing = ", ".join(item.start.isoformat() for item in reconciliation.missing_boundaries) or "NONE"
    current = "NONE" if not incomplete else " | ".join(
        f"{item.boundary.start.isoformat()} · O {_number(item.open)} · H {_number(item.high)} · "
        f"L {_number(item.low)} · C {_number(item.close)} · V {item.volume}"
        for item in incomplete
    )
    return (
        '<section class="intraday-panel timeframe"><h2>'
        + escape(reconciliation.timeframe.value) + " Evidence</h2>"
        + _facts((
            ("Data Completeness", reconciliation.result.value),
            ("Availability", reconciliation.availability.value),
            ("Completed Candle Count", str(len(completed))),
            ("Latest Completed Boundary", latest_text),
            ("Latest Completed OHLCV", ohlcv),
            ("Missing Boundaries", missing),
            ("Structural Fact Count", str(0 if structural is None else len(structural.facts))),
        ))
        + '<div class="incomplete-observation"><strong>CURRENT INCOMPLETE OBSERVATION</strong><span>'
        + escape(current) + "</span></div></section>"
    )


def _context_panels(context) -> str:  # type: ignore[no-untyped-def]
    if context is None:
        return _unavailable("Previous Session / Classic Pivots / CPR")
    previous = context.previous_session
    pivots = context.classic_pivots
    cpr = context.cpr
    relationships = " | ".join(
        f"{item.reference_identity}: {item.relationship.value}"
        for item in context.price_relationships
    ) or "UNAVAILABLE"
    return (
        '<div class="intraday-context">'
        '<section class="intraday-panel"><h2>Previous Session</h2>' + _facts((
            ("Availability", previous.availability.value),
            ("Previous Session High / PDH", _optional(previous.pdh)),
            ("Previous Session Low / PDL", _optional(previous.pdl)),
            ("Previous Session Close", _optional(previous.close)),
        )) + "</section>"
        '<section class="intraday-panel"><h2>Classic Pivots</h2>' + _facts((
            ("Convention", pivots.evidence_family),
            ("R4", _optional(pivots.r4)), ("R3", _optional(pivots.r3)),
            ("R2", _optional(pivots.r2)), ("R1", _optional(pivots.r1)),
            ("P", _optional(pivots.p)), ("S1", _optional(pivots.s1)),
            ("S2", _optional(pivots.s2)), ("S3", _optional(pivots.s3)),
            ("S4", _optional(pivots.s4)),
        )) + "</section>"
        '<section class="intraday-panel"><h2>CPR</h2>' + _facts((
            ("Convention", cpr.evidence_family),
            ("CPR Upper", _optional(cpr.upper)),
            ("CPR Lower", _optional(cpr.lower)),
            ("CPR Width", _optional(cpr.width)),
            ("CPR Pivot", _optional(cpr.pivot)),
            ("Current vs Prior CPR", "UNAVAILABLE" if cpr.relationship_to_prior is None else cpr.relationship_to_prior.value),
            ("Current-price Relationships", relationships),
        )) + "</section></div>"
    )


def _structure_panel(evidence) -> str:  # type: ignore[no-untyped-def]
    if not evidence:
        return _unavailable("Structural Facts")
    rows = ""
    for item in evidence:
        for barrier in item.barriers:
            rows += _row((
                item.timeframe.value, "STRUCTURAL_BARRIER", barrier.reference_name,
                _optional(barrier.price), barrier.availability.value,
            ))
        for fact in item.facts:
            values = ", ".join(f"{value.name}={_number(value.value)}" for value in fact.values) or "—"
            attributes = ", ".join(f"{value.name}={value.value}" for value in fact.attributes)
            detail = values if not attributes else f"{values}; {attributes}"
            rows += _row((
                fact.timeframe.value, fact.fact_type.value, fact.direction.value,
                detail, fact.availability.value,
            ))
    if not rows:
        rows = '<tr><td colspan="5">No structural facts retained.</td></tr>'
    return _table_panel(
        "Structural Facts", ("Timeframe", "Fact", "Direction", "Values / Relationships", "Availability"), rows
    )


def _telemetry_panels(evidence) -> str:  # type: ignore[no-untyped-def]
    volume_rows = ""
    extension_rows = ""
    for item in evidence:
        for measure in item.measures:
            values = ", ".join(f"{value.name}={_number(value.value)}" for value in measure.values) or "—"
            attrs = ", ".join(f"{value.name}={value.value}" for value in measure.attributes)
            detail = values if not attrs else f"{values}; {attrs}"
            row = _row((
                item.timeframe.value, measure.telemetry_type.value,
                measure.comparison.value, detail, measure.availability.value,
            ))
            if measure.telemetry_type in {
                TelemetryType.VOLUME_OBSERVATION,
                TelemetryType.RECENT_VOLUME_COMPARISON,
                TelemetryType.SESSION_VOLUME_COMPARISON,
            }:
                volume_rows += row
            else:
                extension_rows += row
    return (
        _table_panel(
            "Volume / Participation — Shadow Telemetry",
            ("Timeframe", "Measure", "Exact Comparison", "Raw / Derived Values", "Availability"),
            volume_rows or '<tr><td colspan="5">UNAVAILABLE</td></tr>',
        )
        + _table_panel(
            "Extension / Reward-Risk — Shadow Telemetry",
            ("Timeframe", "Measure", "Comparison", "Explicit Inputs / Values", "Availability"),
            extension_rows or '<tr><td colspan="5">UNAVAILABLE</td></tr>',
        )
    )


def _provenance_panel(snapshot: IntradayWorkstationSnapshot) -> str:
    bundle = snapshot.evidence
    assert bundle is not None
    rows = "".join(
        _row((
            item.reconciliation.timeframe.value,
            item.reconciliation.provenance.provider,
            item.reconciliation.provenance.source_identity,
            item.reconciliation.provenance.source_version,
            item.reconciliation.provenance.retrieved_at.isoformat(),
        )) for item in bundle.composition.evidence
    )
    identities = _facts((
        ("Run ID", bundle.composition.run.run_id),
        ("Mapping Identity", bundle.composition.instrument.mapping_identity),
        ("Observation Boundary", bundle.composition.run.observation_boundary.observed_at.isoformat()),
        ("Factual Evidence IDs", " | ".join(item.evidence_id for item in bundle.composition.evidence)),
        ("Shadow Telemetry IDs", " | ".join(item.evidence_id for item in bundle.shadow_telemetry) or "UNAVAILABLE"),
    ))
    table = _table_panel(
        "Provenance / Availability",
        ("Timeframe", "Provider", "Source Identity", "Version", "Retrieved"), rows,
    )
    return '<section class="intraday-panel intraday-wide"><h2>Evidence Identities</h2>' + identities + "</section>" + table


def _facts(items: tuple[tuple[str, str], ...]) -> str:
    return '<dl class="intraday-facts">' + "".join(
        f"<dt>{escape(label)}</dt><dd>{escape(value)}</dd>" for label, value in items
    ) + "</dl>"


def _table_panel(title: str, headings: tuple[str, ...], rows: str) -> str:
    return (
        '<section class="intraday-panel intraday-wide"><h2>' + escape(title) + "</h2>"
        '<div class="table-scroll"><table class="intraday-table"><thead><tr>'
        + "".join(f"<th>{escape(item)}</th>" for item in headings)
        + "</tr></thead><tbody>" + rows + "</tbody></table></div></section>"
    )


def _row(values: tuple[str, ...]) -> str:
    return "<tr>" + "".join(f"<td>{escape(item)}</td>" for item in values) + "</tr>"


def _unavailable(title: str, detail: str = "Governed evidence is unavailable.") -> str:
    return (
        '<section class="intraday-panel intraday-unavailable"><h2>' + escape(title)
        + "</h2><strong>UNAVAILABLE</strong><p>" + escape(detail) + "</p></section>"
    )


def _number(value: Decimal) -> str:
    return format(value, "f")


def _optional(value: Decimal | None) -> str:
    return "UNAVAILABLE" if value is None else _number(value)


__all__ = ["render_intraday_body"]
