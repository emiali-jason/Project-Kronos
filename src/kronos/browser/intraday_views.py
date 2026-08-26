"""Escaped HTML body for the read-only Intraday evidence workstation."""

from __future__ import annotations

from decimal import Decimal
from html import escape
from urllib.parse import quote

from kronos.application.intraday_discovery import (
    IntradayDiscoveryMemberSnapshot,
    IntradayDiscoverySnapshot,
)
from kronos.application.intraday_workstation import IntradayWorkstationSnapshot
from kronos.application.swing_opportunities import BrowserWorkspaceSnapshot
from kronos.browser.views import render_browser_page
from kronos.intraday.contracts import CandleCompletion, IntradayTimeframe
from kronos.intraday.probables import ProbableState
from kronos.intraday.telemetry import TelemetryType


_INTRADAY_CSS = r"""
.intraday-card{border:1px solid #25704c;background:linear-gradient(145deg,#071a12,#0b2519);border-radius:12px;padding:18px;max-width:760px}.intraday-card h2{margin:0;color:#67d99a}.intraday-card .event{border-top:1px solid #214c38;padding:10px 0}.intraday-card .detail-link{display:inline-block;margin-top:10px;color:#7de4aa;font-weight:800}.intraday-status{color:#9ccab0;margin:8px 0 14px}.intraday-status strong{color:#67d99a}
.intraday-warning{display:flex;justify-content:space-between;gap:16px;border:1px solid #82631f;background:#231d11;color:#f6d997;border-radius:8px;padding:12px 14px;margin-bottom:14px}.intraday-selector{display:flex;align-items:center;gap:10px;margin-bottom:14px}.intraday-selector label{font-weight:700}.intraday-selector select{border:1px solid #31506a;background:#04131f;color:var(--text);border-radius:7px;padding:9px 12px}.intraday-panel{border:1px solid var(--line);background:rgba(6,23,37,.88);border-radius:10px;padding:15px;margin-bottom:14px;min-width:0}.intraday-panel h2{margin:0 0 12px;color:var(--blue);font-size:17px}.intraday-panel h3{margin:14px 0 7px;color:var(--muted);font-size:11px;text-transform:uppercase}.intraday-facts{display:grid;grid-template-columns:minmax(140px,.35fr) minmax(0,1fr);margin:0}.intraday-facts dt,.intraday-facts dd{padding:6px 8px;border-top:1px solid var(--line);margin:0;overflow-wrap:anywhere}.intraday-facts dt{color:var(--muted)}.intraday-timeframes{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.incomplete-observation{display:grid;gap:5px;margin-top:11px;border:1px dashed #82631f;border-radius:7px;padding:9px;color:#f6d997}.incomplete-observation span{color:var(--muted);overflow-wrap:anywhere}.intraday-context{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.intraday-table{width:100%;border-collapse:collapse;font-size:12px}.intraday-table th,.intraday-table td{text-align:left;vertical-align:top;padding:8px;border-bottom:1px solid var(--line);overflow-wrap:anywhere}.intraday-table th{color:var(--muted);white-space:nowrap}.table-scroll{overflow:auto}.intraday-unavailable{color:var(--muted)}.intraday-unavailable strong{color:var(--amber)}
.intraday-discovery-header{border:1px solid #215f42;background:linear-gradient(135deg,#071a12,#0b271a);border-radius:9px;padding:13px 15px;margin-bottom:12px}.intraday-discovery-header h2{font-size:17px;color:#68dda0;margin:0 0 5px}.intraday-discovery-header p{margin:3px 0;color:#a8c8b6;font-size:12px}.intraday-metrics{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:8px;margin-bottom:12px}.intraday-metric{border:1px solid #264839;background:#081810;border-radius:7px;padding:9px}.intraday-metric span{display:block;color:#8eae9c;font-size:10px;text-transform:uppercase;letter-spacing:.04em}.intraday-metric strong{display:block;color:#d8f0e2;font-size:16px;margin-top:3px}.intraday-discovery-table{width:100%;border-collapse:collapse;font-size:12px}.intraday-discovery-table th,.intraday-discovery-table td{padding:7px 8px;border-bottom:1px solid #203a30;text-align:left}.intraday-discovery-table th{font-size:10px;color:#8eae9c;text-transform:uppercase}.intraday-state-ready{color:#75dda3}.intraday-state-held{color:#e0bd73}.intraday-failure{border:1px solid #81502a;background:#26170d;color:#f0c08e;border-radius:7px;padding:9px 11px;margin-bottom:12px}.intraday-methodology{border:1px solid #315941;background:#0a1d13;color:#b7ddc7;border-radius:7px;padding:9px 11px;margin-bottom:12px;font-size:12px}.intraday-mcx{margin-top:12px}.intraday-detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
@media(max-width:760px){.intraday-timeframes,.intraday-context{grid-template-columns:1fr}.intraday-warning,.intraday-selector{align-items:flex-start;flex-direction:column}.intraday-facts{grid-template-columns:1fr}.intraday-facts dd{padding-top:0}}
@media(max-width:900px){.intraday-metrics{grid-template-columns:repeat(3,minmax(0,1fr))}.intraday-detail-grid{grid-template-columns:1fr}}
"""


def render_intraday_workstation(
    snapshot: BrowserWorkspaceSnapshot,
    intraday: IntradayWorkstationSnapshot | IntradayDiscoverySnapshot,
) -> str:
    """Render the complete Intraday page through the stable Browser shell."""

    return render_browser_page(
        title="Intraday Evidence Workstation — Native Discovery",
        subtitle="Native Discovery — governed facts, complete accounting, no trading authority.",
        snapshot=snapshot,
        active_nav="Intraday",
        active_tab="",
        body=render_intraday_triage(intraday),
        extra_styles=_INTRADAY_CSS,
    )


def render_intraday_detail(
    snapshot: BrowserWorkspaceSnapshot,
    intraday: IntradayWorkstationSnapshot | IntradayDiscoverySnapshot,
) -> str:
    if isinstance(intraday, IntradayDiscoverySnapshot):
        selected = intraday.selected_member
        identity = "Member" if selected is None else selected.sponsor_label
        body = '<p><a href="/intraday">← Intraday triage</a></p>' + _render_discovery_detail(intraday)
        subtitle = f"{identity} — governed factual evidence; no trading conclusion."
    else:
        body = '<p><a href="/intraday">← Intraday triage</a></p>' + render_intraday_body(intraday)
        subtitle = "Immutable factual evidence; no trading conclusion."
    return render_browser_page(
        title="Intraday Detailed Evidence",
        subtitle=subtitle,
        snapshot=snapshot,
        active_nav="Intraday",
        active_tab="",
        body=body,
        extra_styles=_INTRADAY_CSS,
    )


def render_intraday_triage(
    snapshot: IntradayWorkstationSnapshot | IntradayDiscoverySnapshot,
) -> str:
    if isinstance(snapshot, IntradayDiscoverySnapshot):
        return _render_discovery_triage(snapshot)
    warning = ('<div class="intraday-warning"><strong>ENGINEERING / EVIDENCE</strong>'
               '<span>NO TRADING CONCLUSION — EVIDENCE WORKSTATION</span></div>')
    if snapshot.selected_instrument is None:
        return warning + _unavailable(
            "RELIANCE",
            snapshot.runtime_detail or "UNAVAILABLE — no governed DOMAIN-001 publication.",
        )
    identity = snapshot.selected_instrument.canonical.canonical_instrument_id
    state = snapshot.availability
    if snapshot.evidence is None:
        label = "DATA INCOMPLETE" if state == "DATA_INCOMPLETE" else "UNAVAILABLE"
        return warning + (
            '<section class="intraday-card"><h2>' + escape(identity) + '</h2>'
            '<p class="intraday-status"><strong>' + label + '</strong> — '
            + escape(snapshot.runtime_detail or "Governed evidence is unavailable.") + '</p></section>'
        )
    bundle = snapshot.evidence
    events = []
    for timeframe in (IntradayTimeframe.FIFTEEN_MINUTES, IntradayTimeframe.FIVE_MINUTES):
        evidence = next((item for item in bundle.structural_evidence if item.timeframe is timeframe), None)
        fact = _latest_fact(() if evidence is None else evidence.facts)
        value = "No factual structural event" if fact is None else fact.fact_type.value
        events.append(f'<div class="event"><strong>{timeframe.value}</strong> · {escape(value)}</div>')
    participation = "UNAVAILABLE"
    for evidence in bundle.shadow_telemetry:
        for measure in evidence.measures:
            if measure.telemetry_type is TelemetryType.RECENT_VOLUME_COMPARISON:
                values = {item.name: item.value for item in measure.values}
                ratio = values.get("volume_ratio")
                if ratio is not None:
                    participation = f"5M volume ratio {format(ratio, 'f')} · {measure.comparison.value}"
    return warning + (
        '<p class="intraday-status">Latest completed factual event — '
        '<strong>PRESENTATION SELECTION ONLY</strong></p>'
        '<section class="intraday-card"><h2>' + escape(identity) + '</h2>'
        + ''.join(events) + '<div class="event"><strong>Participation</strong> · '
        + escape(participation) + '</div><a class="detail-link" href="/intraday/evidence/'
        + escape(identity) + '">DETAILED EVIDENCE →</a></section>'
    )


def _render_discovery_triage(snapshot: IntradayDiscoverySnapshot) -> str:
    last = (
        "NO SUCCESSFUL DISCOVERY RUN AVAILABLE"
        if snapshot.last_successful_analysis is None
        else "LAST SUCCESSFUL ANALYSIS · "
        + snapshot.last_successful_analysis.astimezone().isoformat()
    )
    failure_text = {
        "PUBLICATION_STALE": (
            "Discovery could not run because the selected observation boundary "
            "predates the active Intraday universe publication."
        ),
    }.get(snapshot.current_failure, _plain(snapshot.current_failure or ""))
    failure = "" if snapshot.current_failure is None else (
        '<div class="intraday-failure"><strong>CURRENT RUN FAILURE</strong> · '
        + escape(failure_text) + "</div>"
    )
    probable_snapshot = snapshot.probables
    if probable_snapshot is not None and probable_snapshot.current_failure is not None:
        failure += (
            '<div class="intraday-failure"><strong>CURRENT PROBABLES FAILURE</strong> · '
            + escape(_plain(probable_snapshot.current_failure))
            + " · last successful Probables remain preserved.</div>"
        )
    probable_run = None if probable_snapshot is None else probable_snapshot.run
    if probable_snapshot is None:
        metrics = (
            ("Universe", snapshot.universe_count),
            ("Factual path ready", snapshot.pre_evaluable_count),
            ("Prerequisite unavailable", snapshot.prerequisite_unavailable_count),
            ("Machine facts complete", snapshot.machine_fact_success_count),
            ("Long Probables", 0),
            ("Short Probables", 0),
        )
        probable_note = (
            '<div class="intraday-methodology"><strong>Candidate-admission methodology '
            'is not yet commissioned.</strong> Factual availability is not an opportunity; '
            'no candidates are manufactured for presentation.</div>'
        )
    elif probable_run is None:
        metrics = (
            ("Universe", snapshot.universe_count),
            ("Factual path ready", snapshot.pre_evaluable_count),
            ("Prerequisite unavailable", snapshot.prerequisite_unavailable_count),
            ("Machine facts complete", snapshot.machine_fact_success_count),
            ("Long Probables", 0),
            ("Short Probables", 0),
        )
        probable_note = (
            '<div class="intraday-methodology"><strong>V0 Probables methodology '
            'commissioned.</strong> No successful governed Probables run is loaded. '
            'Browser refresh does not create an analytical run.</div>'
        )
    else:
        diagnostics = probable_run.diagnostics
        metrics = (
            ("Universe", diagnostics.starting_population),
            ("Long Probables", diagnostics.long_probables),
            ("Short Probables", diagnostics.short_probables),
            ("Not Admitted", diagnostics.not_admitted_count),
            ("Unavailable", diagnostics.unavailable_count),
            ("Population", diagnostics.population_bucket.value),
        )
        probable_note = (
            '<div class="intraday-methodology"><strong>V0 Probables methodology · '
            + escape(probable_run.methodology_version)
            + '</strong> Last successful analysis '
            + escape(probable_run.observation_boundary.isoformat())
            + '. Probable means selected for deeper review only; no trading authority.</div>'
        )
    metric_html = '<div class="intraday-metrics">' + "".join(
        '<div class="intraday-metric"><span>' + escape(label)
        + '</span><strong>' + str(value) + "</strong></div>"
        for label, value in metrics
    ) + "</div>"
    available = tuple(item for item in snapshot.members if item.prerequisite_ready)
    probable_members = tuple(
        item for item in available
        if item.probable_result is not None
        and item.probable_result.state in (
            ProbableState.LONG_PROBABLE,
            ProbableState.SHORT_PROBABLE,
        )
    )
    presentation = (probable_members if probable_run is not None else available)[:15]
    rows = "".join(_discovery_member_row(item) for item in presentation)
    unavailable = tuple(item for item in snapshot.members if not item.prerequisite_ready)
    unavailable_rows = "".join(
        _row((
            item.sponsor_label,
            item.market_family,
            _plain(item.reasons[0].value),
            "Not evaluated — prerequisite unavailable",
        ))
        for item in unavailable
    )
    return (
        '<section class="intraday-discovery-header"><h2>INTRADAY · NATIVE DISCOVERY</h2>'
        '<p>' + escape(last) + '</p><p>Presentation order: stable canonical ordering only; '
        'no ranking or analytical meaning.</p></section>'
        + failure + metric_html
        + probable_note
        + _table_panel(
            "Current Probables triage" if probable_run is not None else "Current factual triage",
            ("Instrument", "Market", "Factual state", "Probables state", "Observation", "Evidence"),
            rows or '<tr><td colspan="6">No governed Probables in the current run.</td></tr>',
        )
        + '<div class="intraday-mcx">'
        + _table_panel(
            f"MCX prerequisites — {len(unavailable)} unavailable",
            ("Member", "Market", "Reason", "State"),
            unavailable_rows or '<tr><td colspan="4">None unavailable.</td></tr>',
        ) + "</div>"
    )


def _discovery_member_row(item: IntradayDiscoveryMemberSnapshot) -> str:
    factual = (
        "Factual data available"
        if item.machine_facts_available
        else "Factual path ready"
    )
    observed = (
        "Not yet run"
        if item.observation_boundary is None
        else item.observation_boundary.isoformat()
    )
    detail = f'/intraday/evidence/{quote(item.canonical_identity, safe="")}'
    analytical = (
        _plain(item.candidate_state.value)
        if item.probable_result is None
        else _plain(item.probable_result.state.value)
    )
    return (
        "<tr><td><strong>" + escape(item.sponsor_label) + "</strong></td><td>"
        + escape(item.market_family) + '</td><td class="intraday-state-ready">'
        + escape(factual) + "</td><td>" + escape(analytical)
        + "</td><td>" + escape(observed) + '</td><td><a href="'
        + detail + '">DETAIL →</a></td></tr>'
    )


def _render_discovery_detail(snapshot: IntradayDiscoverySnapshot) -> str:
    item = snapshot.selected_member
    if item is None:
        return _unavailable("Intraday member", "The governed member was not found.")
    reasons = ", ".join(_plain(reason.value) for reason in item.reasons)
    probable = item.probable_result
    probable_state = "NOT YET ANALYSED" if probable is None else _plain(probable.state.value)
    probable_reason = "UNAVAILABLE" if probable is None else ", ".join(
        _plain(reason.value) for reason in probable.reasons
    )
    header = (
        '<section class="intraday-discovery-header"><h2>' + escape(item.sponsor_label)
        + '</h2><p>' + escape(item.canonical_identity) + " · "
        + escape(item.market_family) + '</p></section><div class="intraday-detail-grid">'
        + '<section class="intraday-panel"><h2>Identity / Availability</h2>'
        + _facts((
            ("Canonical identity", item.canonical_identity),
            ("Factual prerequisite", "AVAILABLE" if item.prerequisite_ready else "UNAVAILABLE"),
            ("Machine facts", "AVAILABLE" if item.machine_facts_available else "NOT AVAILABLE"),
            ("Discovery state", _plain(item.candidate_state.value)),
            ("Probables state", probable_state),
            ("Probables reason", probable_reason),
            ("Reason", reasons),
            ("Execution eligibility", "NOT ESTABLISHED"),
        )) + "</section>"
    )
    bundle = item.machine_fact_bundle
    if bundle is None:
        factual = _unavailable(
            "Timeframe completeness / factual evidence",
            "No completed machine-fact bundle is retained for this member.",
        )
    else:
        rows = "".join(_row((
            "SESSION" if fact.timeframe is None else fact.timeframe.value,
            _plain(fact.family.value),
            "COMPLETED" if fact.completed_candle is True else "FACTUAL",
            fact.fact_version,
        )) for fact in bundle.evidence)
        factual = _table_panel(
            "Timeframe completeness / evidence",
            ("Timeframe", "Fact family", "Boundary", "Version"), rows,
        )
    rich = item.evidence
    if rich is None:
        detail = (
            _unavailable("Previous Session / PDH / PDL")
            + _unavailable("Classic Pivots / CPR")
            + _unavailable("Structure / Volume / Distance / R:R telemetry")
        )
    else:
        structural = {value.timeframe: value for value in rich.structural_evidence}
        detail = _session_panel(rich.composition)
        detail += '<div class="intraday-timeframes">' + "".join(
            _timeframe_panel(
                value.reconciliation,
                structural.get(value.reconciliation.timeframe),
            )
            for value in rich.composition.evidence
        ) + "</div>"
        detail += _context_panels(rich.slice1e_context)
        detail += _structure_panel(rich.structural_evidence)
        detail += _telemetry_panels(rich.shadow_telemetry)
    source = "UNAVAILABLE" if bundle is None else " | ".join(bundle.source_identities)
    probable_lineage = () if probable is None else (
        ("Methodology", f"{probable.methodology_identity} / {probable.methodology_version}"),
        ("Probable result identity", probable.result_identity),
        ("Narrow CPR fact", probable.lineage.narrow_cpr_fact_identity or "UNAVAILABLE"),
        ("1H fact", probable.lineage.one_hour_fact_identity or "UNAVAILABLE"),
        ("15M fact", probable.lineage.fifteen_minute_fact_identity or "UNAVAILABLE"),
        ("Coherence fact", probable.lineage.coherence_fact_identity or "UNAVAILABLE"),
        ("Participation", probable.participation_state),
    )
    lineage = '<section class="intraday-panel"><h2>Evidence / Timestamp</h2>' + _facts((
        (
            "Observation boundary",
            "UNAVAILABLE" if item.observation_boundary is None
            else item.observation_boundary.isoformat(),
        ),
        (
            "Machine-fact contract",
            "UNAVAILABLE" if bundle is None
            else f"{bundle.schema_identity} / {bundle.bundle_version}",
        ),
        ("Source identities", source),
        *probable_lineage,
    )) + "</section></div>"
    return header + lineage + factual + detail


def _plain(value: str) -> str:
    return value.replace("_", " ").title()


def _latest_fact(facts):  # type: ignore[no-untyped-def]
    return None if not facts else max(
        facts,
        key=lambda item: (
            item.confirmation_boundary or item.end_boundary or item.start_boundary
            or item.observation_boundary.observed_at,
            item.fact_id,
        ),
    )


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
            ("Tick Size", _optional(canonical.canonical_tick_size)),
            ("Lot Size", "UNAVAILABLE" if canonical.canonical_lot_size is None else str(canonical.canonical_lot_size)),
            ("Price Precision", "UNAVAILABLE" if canonical.canonical_price_precision is None else str(canonical.canonical_price_precision)),
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


__all__ = [
    "render_intraday_body",
    "render_intraday_detail",
    "render_intraday_triage",
    "render_intraday_workstation",
]
