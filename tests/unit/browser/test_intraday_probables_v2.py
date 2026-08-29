from datetime import datetime
from enum import StrEnum
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from kronos.browser.intraday_views import (
    _INTRADAY_CSS,
    _probable_v2_card,
    _render_probables_v2_triage,
)
from kronos.intraday.completed_evidence import IntradayAnalysisPhase
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.nifty_relative_context import (
    NiftyApplicability,
    NiftyRelationship,
)
from kronos.intraday.probables import ProbableState
from kronos.intraday.probables_v2 import ProbableReasonV2


_BOUNDARY = datetime(2026, 8, 28, 10, 15, tzinfo=ZoneInfo("Asia/Kolkata"))


class _DiagnosticOnlyState(StrEnum):
    HELD = "HELD"


def _member(label: str, family: str) -> SimpleNamespace:
    return SimpleNamespace(
        sponsor_label=label,
        canonical_identity=f"SUBJECT-{label}",
        market_family=family,
    )


def _result(
    label: str,
    state: ProbableState | _DiagnosticOnlyState,
    direction: SemanticDirection | None = None,
    *,
    nifty_applicability: NiftyApplicability | None = NiftyApplicability.APPLICABLE,
) -> SimpleNamespace:
    return SimpleNamespace(
        canonical_subject_identity=f"SUBJECT-{label}",
        methodology_version="2.0.0",
        phase=IntradayAnalysisPhase.OPENING,
        analysis_boundary=_BOUNDARY,
        nifty_applicability=nifty_applicability,
        nifty_relationship=(
            NiftyRelationship.NOT_APPLICABLE
            if nifty_applicability is NiftyApplicability.NOT_APPLICABLE
            else NiftyRelationship.SUPPORTING
        ),
        state=state,
        direction=direction,
        reasons=(ProbableReasonV2.V2_CONDITIONS_SATISFIED,),
    )


def _render(members: list[SimpleNamespace], results: list[SimpleNamespace]) -> str:
    long_count = sum(item.state is ProbableState.LONG_PROBABLE for item in results)
    short_count = sum(item.state is ProbableState.SHORT_PROBABLE for item in results)
    unavailable_count = sum(item.state is ProbableState.UNAVAILABLE for item in results)
    not_admitted_count = len(results) - long_count - short_count - unavailable_count
    diagnostics = SimpleNamespace(
        starting_population=len(results),
        long_probables=long_count,
        short_probables=short_count,
        total_probables=long_count + short_count,
        not_admitted_count=not_admitted_count,
        unavailable_count=unavailable_count,
        population_bucket=SimpleNamespace(value="VIABLE"),
        phase_counts=((IntradayAnalysisPhase.OPENING, len(results)),),
    )
    run = SimpleNamespace(
        diagnostics=diagnostics,
        results=tuple(results),
        methodology=SimpleNamespace(
            methodology_identity="KRONOS-INTRADAY-PROBABLES-METHODOLOGY-V2",
            methodology_version="2.0.0",
        ),
        analysis_boundary=_BOUNDARY,
    )
    snapshot = SimpleNamespace(members=tuple(members))
    return _render_probables_v2_triage(
        snapshot,
        run,
        refresh_enabled=False,
        last="28 Aug 2026 · 10:15 IST",
        failure="",
    )


def test_browser_projects_v2_phase_lineage_nifty_and_bounded_result() -> None:
    result = SimpleNamespace(
        canonical_subject_identity="NSE-EQ-RELIANCE",
        methodology_version="2.0.0",
        phase=IntradayAnalysisPhase.OPENING,
        analysis_boundary=datetime(
            2026, 8, 28, 10, 15, tzinfo=ZoneInfo("Asia/Kolkata")
        ),
        nifty_applicability=NiftyApplicability.APPLICABLE,
        nifty_relationship=NiftyRelationship.SUPPORTING,
        state=ProbableState.LONG_PROBABLE,
        direction=SemanticDirection.LONG,
        reasons=(ProbableReasonV2.V2_CONDITIONS_SATISFIED,),
    )
    html = _probable_v2_card(result, "RELIANCE")
    assert "OPENING" in html
    assert "PRIOR-SESSION CONTEXT" in html
    assert "SUPPORTING" in html
    assert "Long Probable" in html
    assert "V2 Conditions Satisfied" in html


def test_v2_opportunities_show_only_admitted_grouped_and_sorted_candidates() -> None:
    members = [
        _member("ZETA", "NSE_EQUITY"),
        _member("ALPHA", "NSE_INDEX"),
        _member("OMEGA", "NSE_EQUITY"),
        _member("BETA", "NSE_EQUITY"),
        _member("SILVERM", "MCX"),
        _member("COPPER", "MCX"),
        _member("GOLDM", "MCX"),
        _member("CRUDE", "MCX"),
        _member("NOTADMITTED", "NSE_EQUITY"),
        _member("UNAVAILABLE", "MCX"),
        _member("NATGAS", "MCX"),
    ]
    results = [
        _result("OMEGA", ProbableState.SHORT_PROBABLE, SemanticDirection.SHORT),
        _result("ZETA", ProbableState.LONG_PROBABLE, SemanticDirection.LONG),
        _result("CRUDE", ProbableState.SHORT_PROBABLE, SemanticDirection.SHORT,
                nifty_applicability=NiftyApplicability.NOT_APPLICABLE),
        _result("ALPHA", ProbableState.LONG_PROBABLE, SemanticDirection.LONG),
        _result("SILVERM", ProbableState.LONG_PROBABLE, SemanticDirection.LONG,
                nifty_applicability=NiftyApplicability.NOT_APPLICABLE),
        _result("BETA", ProbableState.SHORT_PROBABLE, SemanticDirection.SHORT),
        _result("GOLDM", ProbableState.LONG_PROBABLE, SemanticDirection.LONG,
                nifty_applicability=NiftyApplicability.NOT_APPLICABLE),
        _result("COPPER", ProbableState.SHORT_PROBABLE, SemanticDirection.SHORT,
                nifty_applicability=NiftyApplicability.NOT_APPLICABLE),
        _result("NOTADMITTED", ProbableState.NOT_ADMITTED, SemanticDirection.LONG),
        _result("UNAVAILABLE", ProbableState.UNAVAILABLE),
        _result("NATGAS", _DiagnosticOnlyState.HELD, SemanticDirection.SHORT),
    ]

    html = _render(members, results)
    primary, diagnostics = html.split(
        '<details class="intraday-probables-diagnostics">', maxsplit=1
    )
    equity = primary.split("intraday-market-equity", maxsplit=1)[1].split(
        "intraday-market-mcx", maxsplit=1
    )[0]
    mcx = primary.split("intraday-market-mcx", maxsplit=1)[1]

    assert primary.count('class="opportunity native-opportunity intraday-probable"') == 8
    assert all(label not in primary for label in ("NOTADMITTED", "UNAVAILABLE", "NATGAS"))
    assert equity.index("ALPHA") < equity.index("ZETA") < equity.index("BETA") < equity.index("OMEGA")
    assert mcx.index("GOLDM") < mcx.index("SILVERM") < mcx.index("COPPER") < mcx.index("CRUDE")
    assert primary.index("intraday-market-equity") < primary.index("intraday-market-mcx")
    assert diagnostics.index("NATGAS") < diagnostics.index("NOTADMITTED") < diagnostics.index("UNAVAILABLE")
    assert "Semantic direction (diagnostic)" in diagnostics
    assert "NOT APPLICABLE" in mcx


def test_v2_historical_projection_keeps_four_shorts_and_empty_mcx_primary() -> None:
    admitted_labels = ["POLICYBZR", "HEROMOTOCO", "APOLLOHOSP", "BAJAJ-AUTO"]
    excluded_labels = [f"EQUITY-{index:03d}" for index in range(89)]
    mcx_labels = ["GOLDM", "SILVERM", "COPPER", "NATGAS", "CRUDE"]
    members = (
        [_member(label, "NSE_EQUITY") for label in admitted_labels + excluded_labels]
        + [_member(label, "MCX") for label in mcx_labels]
    )
    results = [
        _result(label, ProbableState.SHORT_PROBABLE, SemanticDirection.SHORT)
        for label in admitted_labels
    ] + [
        _result(label, ProbableState.NOT_ADMITTED, SemanticDirection.NON_DIRECTIONAL)
        for label in excluded_labels
    ] + [
        _result(label, ProbableState.UNAVAILABLE)
        for label in mcx_labels
    ]

    html = _render(members, results)
    primary = html.split('<details class="intraday-probables-diagnostics">', maxsplit=1)[0]

    assert primary.count('class="opportunity native-opportunity intraday-probable"') == 4
    positions = [primary.index(label) for label in sorted(admitted_labels, key=str.casefold)]
    assert positions == sorted(positions)
    assert "No current admitted MCX Probables." in primary
    assert all(label not in primary for label in excluded_labels + mcx_labels)
    assert "Equity / Index Short</span><strong>4" in primary
    assert "MCX Short</span><strong>0" in primary


def test_v2_projection_is_responsive_and_does_not_compute_analytical_state() -> None:
    members = [_member("RELIANCE", "NSE_EQUITY")]
    results = [_result("RELIANCE", ProbableState.LONG_PROBABLE, SemanticDirection.LONG)]
    states_before = tuple(item.state for item in results)
    html = _render(members, results)

    assert 'data-layout="equity-left-mcx-right"' in html
    assert ".intraday-opportunities-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr)" in _INTRADAY_CSS
    assert ".intraday-market-panels,.intraday-opportunities-grid{grid-template-columns:1fr}" in _INTRADAY_CSS
    assert "evaluate" not in _render_probables_v2_triage.__code__.co_names
    assert "publish" not in _render_probables_v2_triage.__code__.co_names
    assert _render(members, results) == html
    assert tuple(item.state for item in results) == states_before
