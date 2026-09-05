from datetime import datetime
from enum import StrEnum
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from kronos.browser.intraday_views import (
    _INTRADAY_CSS,
    _probable_v2_card,
    _render_probables_v2_triage,
)
from kronos.browser.intraday_market_availability import (
    project_intraday_market_availability,
)
from kronos.intraday.completed_evidence import IntradayAnalysisPhase
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.nifty_relative_context import (
    NiftyApplicability,
    NiftyRelationship,
)
from kronos.intraday.probables import ProbableState
from kronos.intraday.probables_v2 import ProbableReasonV2
from kronos.market.calendar import MarketCalendarPublisher
from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.discovery_failure_provenance import (
    MachineFactFailureAvailability,
    MachineFactFailureComponent,
    MachineFactFailureStage,
)


_BOUNDARY = datetime(2026, 8, 28, 10, 15, tzinfo=ZoneInfo("Asia/Kolkata"))


class _DiagnosticOnlyState(StrEnum):
    HELD = "HELD"


def _member(label: str, family: str) -> SimpleNamespace:
    return SimpleNamespace(
        sponsor_label=label,
        canonical_identity=f"SUBJECT-{label}",
        market_family=family,
        failure_provenance=None,
    )


def test_machine_fact_failure_is_visible_only_inside_collapsed_diagnostics() -> None:
    member = _member("NIFTY", "NSE_INDEX")
    member.failure_provenance = SimpleNamespace(
        failure_stage=MachineFactFailureStage.REQUIRED_TIMEFRAME_ABSENCE,
        required_component=MachineFactFailureComponent.CURRENT_OPENING_15M_EVIDENCE,
        required_timeframe=IntradayTimeframe.FIFTEEN_MINUTES,
        expected_candle_interval="15minute",
        availability_failure=MachineFactFailureAvailability.NOT_COMPLETED,
        sanitized_failure_code="COMPLETED_CANDLE_MISSING",
    )
    html = _render([member], [_result("NIFTY", ProbableState.UNAVAILABLE)])
    primary, diagnostics = html.split(
        '<details class="intraday-probables-diagnostics">', maxsplit=1
    )

    assert "COMPLETED_CANDLE_MISSING" not in primary
    assert "REQUIRED_TIMEFRAME_ABSENCE" in diagnostics
    assert "CURRENT_OPENING_15M_EVIDENCE" in diagnostics
    assert "15minute" in diagnostics


def _result(
    label: str,
    state: ProbableState | _DiagnosticOnlyState,
    direction: SemanticDirection | None = None,
    *,
    nifty_applicability: NiftyApplicability | None = NiftyApplicability.APPLICABLE,
) -> SimpleNamespace:
    return SimpleNamespace(
        result_identity=f"INTRADAY-PROBABLE-V2-RESULT-{label}",
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


def _render(
    members: list[SimpleNamespace],
    results: list[SimpleNamespace],
    *,
    observed_at: datetime | None = None,
) -> str:
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
        evaluable_count=len(results) - unavailable_count,
        population_bucket=SimpleNamespace(value="VIABLE"),
        phase_counts=((IntradayAnalysisPhase.OPENING, len(results)),),
    )
    run = SimpleNamespace(
        run_identity="INTRADAY-PROBABLES-V2-RUN-CURRENT",
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
        market_availability=(
            ()
            if observed_at is None
            else project_intraday_market_availability(
                MarketCalendarPublisher(), observed_at=observed_at
            )
        ),
        refresh_status={} if observed_at is not None else None,
    )


def test_browser_projects_v2_phase_lineage_nifty_and_bounded_result() -> None:
    result = SimpleNamespace(
        canonical_subject_identity="NSE-EQ-RELIANCE",
        result_identity="INTRADAY-PROBABLE-V2-RESULT-RELIANCE",
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


def test_established_phase_labels_nifty_as_not_evaluated_without_changing_result() -> None:
    for phase in (
        IntradayAnalysisPhase.STRUCTURE,
        IntradayAnalysisPhase.FIRST_CURRENT_SESSION_1H,
        IntradayAnalysisPhase.CURRENT_SESSION_ESTABLISHED,
    ):
        result = _result(
            "HDFCAMC", ProbableState.SHORT_PROBABLE, SemanticDirection.SHORT
        )
        result.phase = phase
        result.nifty_relationship = None
        state_before = result.state

        html = _probable_v2_card(result, "HDFCAMC")

        assert phase.value in html
        assert "NIFTY</span><strong>NOT EVALUATED IN THIS PHASE" in html
        assert "OPENING LINEAGE RETAINED" in html
        assert "NIFTY</span><strong>UNAVAILABLE" not in html
        assert result.state is state_before


def test_opening_phase_with_missing_nifty_relationship_remains_unavailable() -> None:
    result = _result(
        "RELIANCE", ProbableState.LONG_PROBABLE, SemanticDirection.LONG
    )
    result.nifty_relationship = None

    html = _probable_v2_card(result, "RELIANCE")

    assert "OPENING" in html
    assert "NIFTY</span><strong>UNAVAILABLE" in html
    assert "NOT EVALUATED IN THIS PHASE" not in html
    assert "OPENING LINEAGE RETAINED" not in html


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
    assert ".intraday-card-fact small{display:block" in _INTRADAY_CSS
    assert "evaluate" not in _render_probables_v2_triage.__code__.co_names
    assert "publish" not in _render_probables_v2_triage.__code__.co_names
    assert _render(members, results) == html
    assert tuple(item.state for item in results) == states_before


def test_non_evaluable_refresh_preserves_prior_projection_and_separates_freshness() -> None:
    members = [_member("RELIANCE", "NSE_EQUITY")]
    prior_result = _result(
        "RELIANCE", ProbableState.SHORT_PROBABLE, SemanticDirection.SHORT
    )
    current_result = _result("RELIANCE", ProbableState.UNAVAILABLE)
    prior_diagnostics = SimpleNamespace(
        starting_population=1,
        long_probables=0,
        short_probables=1,
        total_probables=1,
        not_admitted_count=0,
        unavailable_count=0,
        evaluable_count=1,
        population_bucket=SimpleNamespace(value="STARVED"),
        phase_counts=((IntradayAnalysisPhase.OPENING, 1),),
    )
    current_diagnostics = SimpleNamespace(
        starting_population=1,
        long_probables=0,
        short_probables=0,
        total_probables=0,
        not_admitted_count=0,
        unavailable_count=1,
        evaluable_count=0,
        population_bucket=SimpleNamespace(value="STARVED"),
        phase_counts=(),
    )
    methodology = SimpleNamespace(
        methodology_identity="KRONOS-INTRADAY-PROBABLES-METHODOLOGY-V2",
        methodology_version="2.1.0",
    )
    prior = SimpleNamespace(
        run_identity="INTRADAY-PROBABLES-V2-RUN-PRIOR",
        diagnostics=prior_diagnostics,
        results=(prior_result,),
        methodology=methodology,
        analysis_boundary=datetime(
            2026, 8, 28, 14, 45, tzinfo=ZoneInfo("Asia/Kolkata")
        ),
    )
    current = SimpleNamespace(
        run_identity="INTRADAY-PROBABLES-V2-RUN-CURRENT",
        diagnostics=current_diagnostics,
        results=(current_result,),
        methodology=methodology,
        analysis_boundary=datetime(
            2026, 9, 4, 8, 45, tzinfo=ZoneInfo("Asia/Kolkata")
        ),
    )
    html = _render_probables_v2_triage(
        SimpleNamespace(members=tuple(members)),
        current,
        refresh_enabled=False,
        last="04 Sep 2026 · 08:45 IST",
        failure="",
        refresh_status={
            "last_refresh_attempt": {
                "attempted_at": "2026-09-04T08:45:03+05:30",
                "outcome": "SUCCESS",
            }
        },
        latest_evaluable_run=prior,
    )

    assert "Last refresh attempt" in html
    assert "04 SEP 2026 08:45 IST · Success" in html
    assert "Last successful evaluable analysis" in html
    assert "28 AUG 2026 14:45 IST" in html
    assert "NOT YET EVALUABLE — WAITING FOR MARKET WINDOW" in html
    assert "PRIOR SESSION / REFERENCE ONLY" in html
    assert "Original trading date: 2026-08-28" in html
    assert "STALE — NOT NEWLY QUALIFIED OR ACTIONABLE TODAY" in html
    primary = html.split('<details class="intraday-probables-diagnostics">', 1)[0]
    assert "RELIANCE" in primary
    assert "NO EVALUABLE PHASE" not in primary
    assert "NO EVALUABLE PHASE" in html


def test_refresh_presentation_tracks_available_market_families() -> None:
    members = [_member("RELIANCE", "NSE_EQUITY")]
    results = [_result("RELIANCE", ProbableState.LONG_PROBABLE, SemanticDirection.LONG)]

    mcx_only = _render(
        members,
        results,
        observed_at=datetime(2026, 8, 28, 15, 30, tzinfo=ZoneInfo("Asia/Kolkata")),
    )
    both = _render(
        members,
        results,
        observed_at=datetime(2026, 8, 28, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
    )
    neither = _render(
        members,
        results,
        observed_at=datetime(2026, 8, 28, 23, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
    )

    assert "REFRESH AVAILABLE FOR: MCX" in mcx_only
    assert "REFRESH AVAILABLE FOR: EQUITY / INDEX + MCX" in both
    assert "REFRESH UNAVAILABLE — NO MARKET IS CURRENTLY EVALUABLE" in neither
    assert "ANALYSIS WINDOW CLOSED" in neither
    assert ".intraday-availability-grid,.intraday-freshness-grid{grid-template-columns:1fr}" in _INTRADAY_CSS
