from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

from kronos.application.swing_opportunities import (
    AnalysisState,
    BrowserWorkspaceSnapshot,
    MarketPanel,
    OpportunitySnapshot,
    ProviderConnectionState,
    V1ProbableSnapshot,
)
from kronos.application.swing_v1_review import SwingV1ReviewWorkflow
from kronos.browser.views import (
    render_legacy_opportunities,
    render_opportunities,
    render_placeholder,
    render_settings,
    render_v1_review,
    render_workspace,
)
from kronos.application.live_monitoring_e2e import (
    LiveMonitoringTestResult,
    LiveMonitoringTestState,
)
from kronos.configuration.openai_chart_analyst import (
    ChartAnalystConnectionStatus,
    ChartAnalystV2ActivationStatus,
)
from kronos.market.calendar import MarketCalendarPublisher
from kronos.swing.v1 import (
    ChartTimeframe,
    LocalTradingViewEvidenceStore,
    V1Direction,
    V1Setup,
)


def _v1_probable(
    instrument: str = "HDFCBANK",
    *,
    panel: MarketPanel = MarketPanel.EQUITIES_INDICES,
    direction: V1Direction = V1Direction.SHORT,
) -> V1ProbableSnapshot:
    return V1ProbableSnapshot(
        instrument=instrument,
        panel=panel,
        setups=(V1Setup.CONSOLIDATION_BREAKOUT,),
        directions=(direction,),
    )


def _v1_ready(*probables: V1ProbableSnapshot) -> BrowserWorkspaceSnapshot:
    return replace(
        _ready(),
        v1_layer1_run_identity=(
            "SWING-PHASE1-V1-LAYER1-POLICY-BUNDLE@2026-08-11T00:00:00+05:30"
        ),
        v1_probables=tuple(probables),
    )
from tests.unit.swing.v1.test_swing_v1_slice3 import _classified_run
from tests.unit.application.test_swing_opportunities import (
    NOW,
    _eligible,
    _opportunity,
    _ready,
)


def test_opportunities_has_frozen_navigation_and_lifecycle_shell() -> None:
    rendered = render_legacy_opportunities(_ready())
    for label in (
        "Dashboard", "Swing", "Intraday", "Theta Earners", "Trading Journal",
        "Portfolio", "Reports", "Settings", "Opportunities", "Review",
        "Trade Candidates", "Active", "Closed",
    ):
        assert label in rendered
    assert "Placeholder" not in rendered


def test_live_monitoring_settings_distinguishes_pass_no_data_and_disconnected() -> None:
    pending = render_settings(
        _ready(),
        ChartAnalystConnectionStatus.NOT_CONFIGURED,
        ChartAnalystV2ActivationStatus.DISABLED,
        LiveMonitoringTestResult(
            LiveMonitoringTestState.CONNECTED_NO_DATA,
            "RELIANCE",
            safe_reason="NO_LIVE_MARKET_DATA",
        ),
        ("RELIANCE",),
    )
    assert "CONNECTED — NO LIVE MARKET DATA" in pending
    assert "Live Kite E2E remains: PENDING" in pending
    assert "LIVE MONITORING: PASS" not in pending

    passed = render_settings(
        _ready(),
        ChartAnalystConnectionStatus.NOT_CONFIGURED,
        ChartAnalystV2ActivationStatus.DISABLED,
        LiveMonitoringTestResult(
            LiveMonitoringTestState.PASS,
            "RELIANCE",
            market_data_received=True,
            domain_002_accepted=True,
            observed_at=NOW,
        ),
        ("RELIANCE",),
    )
    assert "LIVE MONITORING: PASS" in passed
    assert "Market data received: YES" in passed
    assert "DOMAIN-002: ACCEPTED" in passed

    disconnected = render_settings(
        replace(_ready(), provider_state=ProviderConnectionState.DISCONNECTED),
        ChartAnalystConnectionStatus.NOT_CONFIGURED,
        ChartAnalystV2ActivationStatus.DISABLED,
        live_monitoring_instruments=("RELIANCE",),
    )
    assert "TEST LIVE MONITORING" in disconnected
    assert (
        '<button class="primary" type="submit" disabled>'
        "TEST LIVE MONITORING</button>"
    ) in disconnected


def test_settings_presents_current_domain_008_coverage_horizon() -> None:
    publisher = MarketCalendarPublisher()
    observed = datetime(2026, 8, 17, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    rendered = render_settings(
        _ready(),
        ChartAnalystConnectionStatus.NOT_CONFIGURED,
        ChartAnalystV2ActivationStatus.DISABLED,
        market_calendar_health=tuple(
            publisher.coverage_health(exchange, observed_at=observed)
            for exchange in ("NSE", "MCX")
        ),
    )

    assert "DOMAIN-008 Market Calendar" in rendered
    assert "NSE VALID THROUGH 31 DEC 2026" in rendered
    assert "MCX VALID THROUGH 31 DEC 2026" in rendered
    assert rendered.count("CURRENT") >= 2


def test_v1_review_renders_all_unique_probables_and_only_requested_upload_slots(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    workflow = SwingV1ReviewWorkflow(LocalTradingViewEvidenceStore(tmp_path))
    review = workflow.publish_layer1(_classified_run({
        ("NAUKRI", V1Setup.PULLBACK_CONTINUATION),
        ("NAUKRI", V1Setup.CONSOLIDATION_BREAKOUT),
        ("TITAN", V1Setup.PULLBACK_CONTINUATION),
    }))
    rendered = render_v1_review(_ready(), review)

    assert rendered.count('class="chart-intake-card"') == 2
    assert rendered.count("<h2>NAUKRI</h2>") == 1
    assert "TITAN" in rendered
    assert 'timeframe=DAILY' in rendered
    assert 'timeframe=4H' not in rendered
    assert rendered.count("Click, then paste") == 2
    assert rendered.count("Choose File") == 2
    assert rendered.count("4-CHART") >= 2
    assert rendered.count("1W · 1D · 4H · 1H") == 2
    assert "Pullback Continuation LONG" in rendered
    assert "Consolidation Breakout LONG" in rendered
    assert "Analyze Charts" not in rendered
    for hidden_detail in (
        "PULLBACK_CONTINUATION",
        "CONSOLIDATION_BREAKOUT",
        "TRADINGVIEW_REVIEW_REQUIRED",
        "CONTEXT_INCOMPLETE",
        "TRADINGVIEW_CONTEXT_RECEIVED",
        "Risk : Reward",
    ):
        assert hidden_detail not in rendered


def test_v1_review_zero_state_and_received_chart_use_operator_labels(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    store = LocalTradingViewEvidenceStore(tmp_path)
    workflow = SwingV1ReviewWorkflow(store)
    zero = render_v1_review(_ready(), workflow.publish_layer1(_classified_run(set())))
    assert "No instruments currently need charts." in zero

    workflow = SwingV1ReviewWorkflow(store)
    workflow.publish_layer1(_classified_run({("NAUKRI", V1Setup.PULLBACK_CONTINUATION)}))
    workflow.upload(
        instrument="NAUKRI",
        timeframe=ChartTimeframe.DAILY,
        content_type="image/png",
        original_bytes=b"\x89PNG\r\n\x1a\nchart",
    )
    received = render_v1_review(_ready(), workflow.snapshot())
    assert "Chart received" in received
    assert "4-CHART" in received
    assert ">DAILY<" not in received
    assert "Replace" in received
    assert "Remove" in received
    assert "Choose File" in received
    assert "Analyze Charts" in received
    assert "chart-preview?" in received
    assert 'class="chart-paste-target received"' in received
    assert "TRADINGVIEW_CONTEXT_RECEIVED" not in received


def test_review_run_status_requires_explicit_move_to_new_parent(tmp_path) -> None:  # type: ignore[no-untyped-def]
    parent_a = "SWING-RUN-0000000000000000000000000000000A"
    parent_b = "SWING-RUN-0000000000000000000000000000000B"
    workflow = SwingV1ReviewWorkflow(LocalTradingViewEvidenceStore(tmp_path))
    review = workflow.publish_layer1(
        _classified_run({("NAUKRI", V1Setup.PULLBACK_CONTINUATION)}),
        swing_analysis_run_identity=parent_a,
    )
    current = replace(_ready(), swing_analysis_run_identity=parent_a)
    assert "NEW ANALYSIS AVAILABLE" not in render_v1_review(current, review)

    newer = replace(current, swing_analysis_run_identity=parent_b)
    rendered = render_v1_review(newer, review)
    assert "NEW ANALYSIS AVAILABLE" in rendered
    assert 'action="/swing/v1/load-latest"' in rendered
    assert "Load latest review" in rendered


def test_market_panels_are_side_by_side_and_stack_responsively() -> None:
    rendered = render_legacy_opportunities(_ready())
    assert "EQUITIES + INDICES" in rendered
    assert "COMMODITIES" in rendered
    assert rendered.count("0 V1 Probables") == 2
    assert ".panels{grid-template-columns:repeat(2,minmax(0,1fr))}" in rendered
    assert "@media(max-width:1050px)" in rendered
    assert ".panels,.workspace{grid-template-columns:1fr}" in rendered


def test_zero_opportunity_state_has_no_fake_card() -> None:
    rendered = render_legacy_opportunities(_ready())
    assert "No V1 Probables were found for this analysis." in rendered
    assert "Open Workspace" not in rendered
    assert "Qualified" not in rendered
    assert "Actionable" not in rendered


def test_one_v1_probable_renders_without_v0_trade_projection() -> None:
    rendered = render_legacy_opportunities(_v1_ready(_v1_probable()))
    for expected in ("HDFCBANK", "SHORT", "Consolidation Breakout"):
        assert expected in rendered
    for forbidden in ("R:R", "Open Workspace", "Qualified", "Actionable"):
        assert forbidden not in rendered


def test_two_v1_probables_preserve_panel_grouping() -> None:
    commodity = _v1_probable(
        "GOLDM",
        panel=MarketPanel.COMMODITIES,
        direction=V1Direction.LONG,
    )
    rendered = render_legacy_opportunities(_v1_ready(_v1_probable(), commodity))
    panels = rendered.index('<div class="panels">')
    equity_card = rendered.index("<h3>HDFCBANK</h3>", panels)
    commodity_panel = rendered.index("<h2>COMMODITIES</h2>", panels)
    commodity_card = rendered.index("<h3>GOLDM</h3>", commodity_panel)
    assert equity_card < commodity_panel < commodity_card
    assert "/swing/opportunities/1" not in rendered
    assert "/swing/opportunities/2" not in rendered
    assert rendered.count('class="opportunity"') == 2


def test_direction_is_coloured_by_authoritative_long_short_meaning() -> None:
    long = _v1_probable("MARUTI", direction=V1Direction.LONG)
    rendered = render_legacy_opportunities(_v1_ready(_v1_probable(), long))
    assert '<span class="direction direction-short">SHORT</span>' in rendered
    assert '<span class="direction direction-long">LONG</span>' in rendered
    assert ".direction-long{color:var(--green)}" in rendered
    assert ".direction-short{color:var(--red)}" in rendered


def test_v1_probable_presentation_has_no_v0_rank() -> None:
    snapshot = _v1_ready(
        _v1_probable("GOLDM", panel=MarketPanel.COMMODITIES),
        _v1_probable("HDFCBANK"),
    )
    rendered = render_legacy_opportunities(snapshot)
    assert 'class="rank"' not in rendered


def test_instrument_workspace_contains_only_authoritative_fields_and_stage10_reservation() -> None:
    opportunity = _opportunity()
    rendered = render_workspace(_ready(opportunity), opportunity)
    for expected in (
        "Trade Plan", "Entry", "Entry condition", "Stop", "Target 1", "Risk : Reward",
        "Risk:", "Reward:", "Thesis Invalidation", "Why KRONOS selected it",
        "Evidence For", "Evidence Against / Risks", "What Needs To Happen Next",
        "SWING-ZERO-V0-CLASSIFICATION-POLICY", "Chart reserved for Stage 10",
        "TradingView integration is not implemented.",
    ):
        assert expected in rendered
    assert "instrument_token" not in rendered


def test_all_dynamic_values_are_html_escaped() -> None:
    unsafe = replace(
        _opportunity(),
        instrument='<script>alert("x")</script>',
        why="<b>unsafe</b>",
        evidence_for=("<img src=x onerror=alert(1)>",),
    )
    rendered = render_workspace(_ready(unsafe), unsafe)
    assert '<script>alert("x")</script>' not in rendered
    assert "&lt;script&gt;" in rendered
    assert "&lt;b&gt;unsafe&lt;/b&gt;" in rendered
    assert "&lt;img src=x onerror=alert(1)&gt;" in rendered


def test_secrets_and_order_capabilities_are_not_rendered() -> None:
    rendered = render_opportunities(_ready(_opportunity())).lower()
    for forbidden in (
        "api secret", "access token", "request token", "instrument token",
        "raw kite", "place_order", "modify_order", "cancel_order",
    ):
        assert forbidden not in rendered
    assert "order capability: none" in rendered


def test_placeholder_is_explicit_and_does_not_fake_capability() -> None:
    rendered = render_placeholder(_ready(), "Active", active_nav="Swing", active_tab="Active")
    assert "not implemented in Browser V1" in rendered
    assert "P/L" not in rendered


def test_analysis_statuses_and_actions_are_rendered_without_diagnostics() -> None:
    disconnected = BrowserWorkspaceSnapshot(
        ProviderConnectionState.DISCONNECTED, AnalysisState.NOT_RUN, 98
    )
    rendered = render_opportunities(disconnected)
    assert "Kite: DISCONNECTED" in rendered
    assert "Connect" in rendered
    assert "Run Swing Analysis" in rendered
    assert "disabled" in rendered


def test_provider_action_matches_connection_state() -> None:
    disconnected = render_opportunities(BrowserWorkspaceSnapshot(
        ProviderConnectionState.DISCONNECTED, AnalysisState.NOT_RUN, 98
    ))
    connected = render_opportunities(_ready())

    assert 'action="/provider/connect"' in disconnected
    assert ">Connect</button>" in disconnected
    assert 'action="/provider/disconnect"' not in disconnected
    assert 'action="/provider/disconnect"' in connected
    assert ">Disconnect</button>" in connected
    assert 'action="/provider/connect"' not in connected


def test_primary_status_is_a_compact_v1_probable_summary() -> None:
    snapshot = _v1_ready(_v1_probable())
    rendered = render_legacy_opportunities(snapshot)
    assert 'class="status-grid"' in rendered
    for expected in (
        "Universe", "98", "V1 Probables", "Equities + Indices",
        "Commodities",
    ):
        assert expected in rendered
    assert "Analysis boundary" not in rendered


def test_sponsor_header_shows_only_last_successful_analysis_completion_in_ist() -> None:
    snapshot = replace(
        _v1_ready(_v1_probable()),
        swing_analysis_run_identity=(
            "SWING-RUN-0000000000000000000000004423B656"
        ),
        run_created_at=NOW.replace(day=13, hour=5, minute=1),
        completed_at=NOW.replace(day=13, hour=5, minute=17),
        observation_boundary=NOW.replace(day=11, hour=18, minute=30),
        market_data_snapshot_identity=(
            "SWING-MARKET-DATA-SNAPSHOT-" + "a" * 64
        ),
    )

    rendered = render_opportunities(snapshot)

    assert "LAST SUCCESSFUL ANALYSIS · 13 AUG 2026 10:47 IST" in rendered
    assert "RUN 4423B656" not in rendered
    assert "ANALYSIS BOUNDARY" not in rendered


def test_sponsor_header_uses_completion_even_when_legacy_run_time_is_missing() -> None:
    snapshot = replace(
        _v1_ready(_v1_probable()),
        swing_analysis_run_identity=(
            "SWING-RUN-000000000000000000000000D14E267F"
        ),
        run_created_at=None,
        observation_boundary=NOW.replace(day=11, hour=18, minute=30),
    )

    rendered = render_opportunities(snapshot)

    assert "LAST SUCCESSFUL ANALYSIS ·" in rendered
    assert "RUN D14E267F" not in rendered
    assert "ANALYSIS BOUNDARY" not in rendered


def test_v0_eligible_plans_are_absent_from_active_sponsor_page() -> None:
    first = _opportunity(1)
    second = replace(_opportunity(2), instrument="MARUTI", direction="LONG")
    third = replace(_opportunity(1), position=3, instrument="POWERINDIA")
    snapshot = replace(
        _ready(first, second),
        attention_eligible_count=3,
        eligible_plans=(
            _eligible(first),
            _eligible(second),
            _eligible(third, selected=False),
        ),
    )

    rendered = render_legacy_opportunities(replace(
        snapshot,
        v1_probables=(_v1_probable("NAUKRI"),),
    ))
    assert "NAUKRI" in rendered
    assert 'class="eligible-selection' not in rendered
    assert "/swing/eligible/" not in rendered
    assert "Attention standard" not in rendered
