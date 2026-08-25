from dataclasses import replace

from kronos.application.swing_trade_window import (
    LocalTradePlanConstructionDiagnosticStore,
    SwingTradeWindowWorkflow,
    TradePlanConstructionAttemptResult,
    TradePlanConstructionStage,
)
from kronos.application.swing_refresh_reminder import (
    K5RefreshReminderStore,
    SwingK5RefreshReminderWorkflow,
)
from datetime import datetime
from zoneinfo import ZoneInfo
from kronos.browser.swing_v3_presentation import present_visual_v3_review
from kronos.browser.views import render_native_trade_window, render_opportunities
from kronos.swing.v1.kr370_step31_handoff import LocalKr370Step31HandoffStore
from kronos.swing.v1.native_trade_construction import (
    LocalTradePlanStore,
    create_trade_construction_evidence_package,
)
from kronos.swing.v1.native_entry_timing import (
    LocalPortfolioStateV1Store,
    LocalRiskPermissionV1Store,
)
from kronos.swing.v1.native_sponsor_decision import SponsorTradeChoice
from kronos.swing.v1.sponsor_observation_decision import (
    LocalSponsorObservationDecisionStore,
    SponsorActivationDisposition,
    SponsorObservationReason,
)
from tests.unit.application.test_swing_opportunities import _ready
from tests.unit.swing.v1.test_kr370_step31_handoff import (
    NOW,
    _completed,
    _context,
    _evidence,
    _price,
)
from tests.unit.swing.v1.test_native_review import _evidence_run


def test_now_card_exposes_trade_window_and_window_uses_persisted_geometry(tmp_path) -> None:
    completed = _completed(tmp_path)
    workflow = SwingTradeWindowWorkflow(
        LocalKr370Step31HandoffStore(tmp_path / "handoffs"),
        LocalTradePlanStore(tmp_path / "plans"),
    )
    projection = workflow.construct(
        completed,
        _evidence(completed),
        _context(completed.requirement.canonical_instrument),
        current_run_identity=completed.requirement.native_run_identity,
        current_analysis_boundary=completed.promotion.analysis_boundary,
        created_at=NOW,
    )
    _, run, _ = _evidence_run()
    opportunities = render_opportunities(
        _ready(),
        run,
        visual_v3=(present_visual_v3_review(completed),),
        trade_windows=(projection,),
    )
    window = render_native_trade_window(_ready(), projection)

    assert "Open Trade Window" in opportunities
    assert projection.native_run_identity in opportunities
    assert "TRADE GEOMETRY AVAILABLE" in window
    assert "₹100" in window and "₹90" in window and "₹120" in window
    assert "1 : 2" in window
    assert "RISK UNAVAILABLE" in window
    assert "SPONSOR DECISION" in window
    assert 'action="/swing/trade-window/observation-decision"' in window
    assert "These controls record Sponsor judgment" in window
    assert "Analytical promotion is complete" in window
    assert "not an entry trigger or an order instruction" in window


def test_non_now_card_has_no_trade_window_action(tmp_path) -> None:
    completed = _completed(tmp_path, cpr_accepted=False)
    workflow = SwingTradeWindowWorkflow(
        LocalKr370Step31HandoffStore(tmp_path / "handoffs"),
        LocalTradePlanStore(tmp_path / "plans"),
    )
    workflow.restore((completed,))
    _, run, _ = _evidence_run()
    html = render_opportunities(
        _ready(),
        run,
        visual_v3=(present_visual_v3_review(completed),),
        trade_windows=workflow.projections(),
    )

    assert "Open Trade Window" not in html


def test_k5_ready_card_shows_time_based_reminder_without_watching(tmp_path) -> None:
    completed = _completed(tmp_path, extended=True)
    scheduler = lambda _delay, _operation: None
    reminder = SwingK5RefreshReminderWorkflow(
        K5RefreshReminderStore(tmp_path / "reminders"),
        clock=lambda: datetime(2026, 8, 14, 16, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
        scheduler=scheduler,
    )
    reminder.synchronize(
        completed.requirement.native_run_identity,
        (completed.promotion,),
        {completed.requirement.canonical_instrument: "NSE"},
    )
    _, run, _ = _evidence_run()
    html = render_opportunities(
        _ready(),
        run,
        visual_v3=(present_visual_v3_review(completed),),
        refresh_reminders=reminder.snapshot(),
    )
    assert "REFRESH ANALYSIS AFTER NEXT COMPLETED 1H" in html
    assert "REMINDER SET · 17 AUG 10:15 IST" in html
    assert "WATCHING" not in html


def test_exact_now_without_plan_exposes_only_bounded_construct_action(tmp_path) -> None:
    completed = _completed(tmp_path)
    workflow = SwingTradeWindowWorkflow(
        LocalKr370Step31HandoffStore(tmp_path / "handoffs"),
        LocalTradePlanStore(tmp_path / "plans"),
    )
    workflow.restore((completed,))
    projection = workflow.project(
        completed.requirement.native_run_identity,
        completed.requirement.canonical_instrument,
    )

    html = render_native_trade_window(_ready(), projection)

    assert 'action="/swing/trade-window/construct"' in html
    assert "CONSTRUCT TRADE PLAN" in html
    assert completed.requirement.native_run_identity in html
    assert completed.requirement.thesis.native_assessment_sha256 in html
    assert "PAPER</button>" not in html
    assert "LIVE</button>" not in html


def test_provider_failure_returns_exact_trade_window_state_not_raw_error(tmp_path) -> None:
    completed = _completed(tmp_path)
    workflow = SwingTradeWindowWorkflow(
        LocalKr370Step31HandoffStore(tmp_path / "handoffs"),
        LocalTradePlanStore(tmp_path / "plans"),
        diagnostic_store=LocalTradePlanConstructionDiagnosticStore(
            tmp_path / "diagnostics"
        ),
    )
    workflow.restore((completed,))
    workflow.retain_construction_attempt(
        attempt_identity="d" * 64,
        run_identity=completed.requirement.native_run_identity,
        canonical_instrument=completed.requirement.canonical_instrument,
        native_assessment_sha256=completed.requirement.thesis.native_assessment_sha256,
        attempt_timestamp=NOW,
        stage=TradePlanConstructionStage.PROVIDER_CAPABILITY,
        result=TradePlanConstructionAttemptResult.FAILED,
        safe_failure_code="KITE_READ_ONLY_CAPABILITY_UNAVAILABLE",
        safe_bounded_reason="Connect Kite before constructing the Trade Plan.",
    )
    html = render_native_trade_window(
        _ready(),
        workflow.project(
            completed.requirement.native_run_identity,
            completed.requirement.canonical_instrument,
        ),
    )
    assert "TRADE PLAN NOT CONSTRUCTED" in html
    assert "KITE CONNECTION REQUIRED" in html
    assert "Connect Kite before constructing the Trade Plan." in html
    assert "Stage</strong> · PROVIDER CAPABILITY" in html
    assert "CONSTRUCT TRADE PLAN" in html
    assert "Trade Plan construction is not available for this current evidence" not in html


def test_historical_geometry_failure_exposes_prospective_observation_action_without_mutation(
    tmp_path,
) -> None:
    completed = _completed(tmp_path)
    diagnostic_store = LocalTradePlanConstructionDiagnosticStore(
        tmp_path / "diagnostics"
    )
    workflow = SwingTradeWindowWorkflow(
        LocalKr370Step31HandoffStore(tmp_path / "handoffs"),
        LocalTradePlanStore(tmp_path / "plans"),
        diagnostic_store=diagnostic_store,
    )
    workflow.restore((completed,))
    historical = workflow.retain_construction_attempt(
        attempt_identity="e" * 64,
        run_identity=completed.requirement.native_run_identity,
        canonical_instrument=completed.requirement.canonical_instrument,
        native_assessment_sha256=completed.requirement.thesis.native_assessment_sha256,
        attempt_timestamp=NOW,
        stage=TradePlanConstructionStage.STEP31,
        result=TradePlanConstructionAttemptResult.FAILED,
        safe_failure_code="GEOMETRY_INVALID",
        safe_bounded_reason=(
            "No valid governed trade geometry is available for this opportunity."
        ),
    )
    historical_path = diagnostic_store.root / f"{historical.attempt_identity}.json"
    historical_bytes = historical_path.read_bytes()

    before = render_native_trade_window(
        _ready(),
        workflow.project(
            completed.requirement.native_run_identity,
            completed.requirement.canonical_instrument,
        ),
    )
    assert 'action="/swing/trade-window/construct"' in before
    assert "EVALUATE TRADE MATHEMATICS" in before
    assert "CONSTRUCT TRADE PLAN</button>" not in before

    base = _evidence(completed)
    warning = create_trade_construction_evidence_package(
        package_identity=base.package_identity,
        native_run_identity=base.native_run_identity,
        canonical_instrument=base.canonical_instrument,
        native_assessment_sha256=base.native_assessment_sha256,
        setup_identity=base.setup_identity,
        observation_boundary=base.observation_boundary,
        provenance=base.provenance,
        qualification_candle=base.qualification_candle,
        governing_structural_low=base.governing_structural_low,
        governing_structural_high=base.governing_structural_high,
        prior_directional_swing_high=_price(
            "HISTORICAL-BRIDGE-TARGET", "95", base.observation_boundary
        ),
        prior_directional_swing_low=base.prior_directional_swing_low,
        original_range_high=base.original_range_high,
        original_range_low=base.original_range_low,
        material_barriers=base.material_barriers,
    )
    first = workflow.construct(
        completed,
        warning,
        _context(completed.requirement.canonical_instrument),
        current_run_identity=completed.requirement.native_run_identity,
        current_analysis_boundary=completed.promotion.analysis_boundary,
        created_at=NOW,
    )
    repeated = workflow.construct(
        completed,
        warning,
        _context(completed.requirement.canonical_instrument),
        current_run_identity=completed.requirement.native_run_identity,
        current_analysis_boundary=completed.promotion.analysis_boundary,
        created_at=NOW,
    )

    assert first.step31_observation is not None
    assert repeated.step31_observation == first.step31_observation
    assert first.step31_observation.severity.value == "RED"
    assert first.trade_plan is None
    assert historical_path.read_bytes() == historical_bytes
    assert workflow.sponsor_observation_decisions() == ()
    assert workflow.observation_research_snapshot() == ()


def test_step31_geometry_failure_preserves_handoff_and_blocks_actions(tmp_path) -> None:
    completed = _completed(tmp_path)
    workflow = SwingTradeWindowWorkflow(
        LocalKr370Step31HandoffStore(tmp_path / "handoffs"),
        LocalTradePlanStore(tmp_path / "plans"),
    )
    base = _evidence(completed)
    invalid_geometry = create_trade_construction_evidence_package(
        package_identity=base.package_identity,
        native_run_identity=base.native_run_identity,
        canonical_instrument=base.canonical_instrument,
        native_assessment_sha256=base.native_assessment_sha256,
        setup_identity=base.setup_identity,
        observation_boundary=base.observation_boundary,
        provenance=base.provenance,
        qualification_candle=base.qualification_candle,
        governing_structural_low=_price(
            "INVALID-STRUCTURAL-LOW", "105", base.observation_boundary
        ),
        governing_structural_high=base.governing_structural_high,
        prior_directional_swing_high=base.prior_directional_swing_high,
        prior_directional_swing_low=base.prior_directional_swing_low,
        original_range_high=base.original_range_high,
        original_range_low=base.original_range_low,
        material_barriers=base.material_barriers,
    )
    projection = workflow.construct(
        completed,
        invalid_geometry,
        _context(completed.requirement.canonical_instrument),
        current_run_identity=completed.requirement.native_run_identity,
        current_analysis_boundary=completed.promotion.analysis_boundary,
        created_at=NOW,
    )
    projection = workflow.project(
        completed.requirement.native_run_identity,
        completed.requirement.canonical_instrument,
    )
    html = render_native_trade_window(_ready(), projection)
    assert projection.handoff is not None
    assert projection.trade_plan is None
    assert "TRADE MATHEMATICS" in html
    assert "RED · COMPLETE WARNING" in html
    assert "Risk geometry is zero or negative." in html
    assert "No PAPER / LIVE action is available." not in html
    assert 'action="/swing/trade-window/observation-decision"' in html
    assert "warning_acknowledged" in html
    assert "POSITION ACTIVATION WILL REMAIN BLOCKED BY DOMAIN-007 RISK" in html
    assert "CONSTRUCT TRADE PLAN" not in html
    assert "PAPER</button>" in html and "LIVE</button>" in html
    assert "IGNORE</button>" in html


def test_blocked_observation_decision_is_idempotent_and_restores_separately(tmp_path) -> None:
    completed = _completed(tmp_path)
    handoff_store = LocalKr370Step31HandoffStore(tmp_path / "handoffs")
    plan_store = LocalTradePlanStore(tmp_path / "plans")
    decision_store = LocalSponsorObservationDecisionStore(tmp_path / "decisions")
    workflow = SwingTradeWindowWorkflow(
        handoff_store, plan_store, sponsor_observation_store=decision_store
    )
    base = _evidence(completed)
    warning = create_trade_construction_evidence_package(
        package_identity=base.package_identity,
        native_run_identity=base.native_run_identity,
        canonical_instrument=base.canonical_instrument,
        native_assessment_sha256=base.native_assessment_sha256,
        setup_identity=base.setup_identity,
        observation_boundary=base.observation_boundary,
        provenance=base.provenance,
        qualification_candle=base.qualification_candle,
        governing_structural_low=base.governing_structural_low,
        governing_structural_high=base.governing_structural_high,
        prior_directional_swing_high=_price(
            "RED-TARGET", "95", base.observation_boundary
        ),
        prior_directional_swing_low=base.prior_directional_swing_low,
        original_range_high=base.original_range_high,
        original_range_low=base.original_range_low,
        material_barriers=base.material_barriers,
    )
    projection = workflow.construct(
        completed,
        warning,
        _context(completed.requirement.canonical_instrument),
        current_run_identity=completed.requirement.native_run_identity,
        current_analysis_boundary=completed.promotion.analysis_boundary,
        created_at=NOW,
    )
    observation = projection.step31_observation
    assert observation is not None
    values = dict(
        run_identity=projection.native_run_identity,
        canonical_instrument=projection.canonical_instrument,
        native_assessment_sha256=projection.native_assessment_sha256,
        observation_evidence_id=observation.observation_evidence_id,
        choice=SponsorTradeChoice.PAPER,
        disposition=SponsorActivationDisposition.BLOCKED_RISK_UNAVAILABLE,
        current_run_identity=projection.native_run_identity,
        warning_acknowledged=True,
        sponsor_reason=SponsorObservationReason.STEP31_WARNING,
        risk_state="RISK_UNAVAILABLE",
    )
    first = workflow.record_sponsor_observation_choice(decided_at=NOW, **values)
    repeated = workflow.record_sponsor_observation_choice(
        decided_at=NOW.replace(microsecond=1), **values
    )
    assert repeated is first
    projected = workflow.project(
        projection.native_run_identity, projection.canonical_instrument
    )
    assert projected.sponsor_observation_decision_state == "PAPER · RECORDED"
    assert projected.activation_disposition == "BLOCKED_RISK_UNAVAILABLE"
    assert projected.sponsor_position_id is None

    restored = SwingTradeWindowWorkflow(
        handoff_store, plan_store, sponsor_observation_store=decision_store
    )
    restored.restore((completed,))
    recovery = restored.project(
        projection.native_run_identity, projection.canonical_instrument
    )
    assert recovery.sponsor_observation_decision_id == first.decision.decision_identity
    assert recovery.activation_disposition == "BLOCKED_RISK_UNAVAILABLE"
    assert recovery.sponsor_observation_controls_available is False


def test_trade_ux_separates_recorded_paper_choice_from_confirmed_entry(tmp_path) -> None:
    completed = _completed(tmp_path)
    handoff_store = LocalKr370Step31HandoffStore(tmp_path / "handoffs")
    plan_store = LocalTradePlanStore(tmp_path / "plans")
    decision_store = LocalSponsorObservationDecisionStore(tmp_path / "decisions")
    workflow = SwingTradeWindowWorkflow(
        handoff_store,
        plan_store,
        LocalPortfolioStateV1Store(tmp_path / "portfolio"),
        LocalRiskPermissionV1Store(tmp_path / "risk"),
        sponsor_observation_store=decision_store,
    )
    projection = workflow.construct(
        completed,
        _evidence(completed),
        _context(completed.requirement.canonical_instrument),
        current_run_identity=completed.requirement.native_run_identity,
        current_analysis_boundary=completed.promotion.analysis_boundary,
        created_at=NOW,
    )
    plan = projection.trade_plan
    observation = projection.step31_observation
    assert plan is not None and observation is not None
    from tests.unit.browser.test_browser_trade_lifecycle_continuity import _review

    workflow.publish_current_portfolio_state(
        _review(completed, plan),
        native_run_identity=plan.native_run_identity,
        as_of_boundary=plan.observation_boundary,
    )
    risk = workflow.evaluate_current_risk(
        plan.native_run_identity, plan.canonical_instrument, evaluated_at=NOW
    )
    pending = workflow.record_sponsor_observation_choice(
        plan.native_run_identity,
        plan.canonical_instrument,
        plan.native_assessment_sha256,
        observation.observation_evidence_id,
        SponsorTradeChoice.PAPER,
        SponsorActivationDisposition.PENDING_ENTRY_CONFIRMATION,
        current_run_identity=plan.native_run_identity,
        decided_at=NOW,
        warning_acknowledged=False,
        risk_identity=risk.risk_result_id,
        risk_state="RISK_APPROVED",
    )
    projected = workflow.project(plan.native_run_identity, plan.canonical_instrument)
    html = render_native_trade_window(_ready(), projected)
    assert "PAPER · RECORDED" in html
    assert "PAPER TRADE ENTRY" in html
    assert 'action="/swing/trade-window/activate"' in html
    assert "ONE LOT" in html
    assert "CONFIRM PAPER ENTRY" in html
    assert "SELECT PAPER" not in html

    activated = workflow.finalize_sponsor_observation_activation(
        plan.native_run_identity,
        plan.canonical_instrument,
        pending.decision.decision_identity,
        SponsorTradeChoice.PAPER,
        disposition=SponsorActivationDisposition.ACTIVATED,
        existing_sponsor_decision_identity="SPONSOR-DECISION-PAPER",
        sponsor_position_identity="SPONSOR-POSITION-PAPER",
        recorded_at=NOW,
    )
    assert activated.decision == pending.decision
    research = workflow.observation_research_snapshot()
    assert len(research) == 1
    assert research[0].source.activation.disposition is SponsorActivationDisposition.ACTIVATED
    assert research[0].record.activation_disposition is SponsorActivationDisposition.PENDING_ENTRY_CONFIRMATION
    restored = SwingTradeWindowWorkflow(
        handoff_store,
        plan_store,
        LocalPortfolioStateV1Store(tmp_path / "portfolio"),
        LocalRiskPermissionV1Store(tmp_path / "risk"),
        sponsor_observation_store=decision_store,
    )
    restored.restore((completed,))
    recovery = restored.project(plan.native_run_identity, plan.canonical_instrument)
    assert recovery.activation_disposition == "ACTIVATED"
    assert recovery.sponsor_observation_decision_state == "PAPER · RECORDED"


def test_trade_ux_is_compact_responsive_and_renders_bounded_entry_error(tmp_path) -> None:
    completed = _completed(tmp_path)
    workflow = SwingTradeWindowWorkflow(
        LocalKr370Step31HandoffStore(tmp_path / "handoffs"),
        LocalTradePlanStore(tmp_path / "plans"),
    )
    projection = workflow.construct(
        completed,
        _evidence(completed),
        _context(completed.requirement.canonical_instrument),
        current_run_identity=completed.requirement.native_run_identity,
        current_analysis_boundary=completed.promotion.analysis_boundary,
        created_at=NOW,
    )
    html = render_native_trade_window(
        _ready(),
        projection,
        workflow_error=(
            "ENTRY NOT ACTIVATED",
            "The recorded Sponsor observation decision has been preserved.",
        ),
    )
    assert "trade-window-grid" in html
    assert "grid-template-columns:minmax(0,1.15fr)" in html
    assert "@media(max-width:980px)" in html
    assert "ENTRY NOT ACTIVATED" in html
    assert "recorded Sponsor observation decision has been preserved" in html
    assert "KEY CONTEXT" in html and "NEXT STEP" in html


def test_trade_ux_live_entry_requires_manual_facts_and_never_claims_broker_authority(
    tmp_path,
) -> None:
    completed = _completed(tmp_path)
    workflow = SwingTradeWindowWorkflow(
        LocalKr370Step31HandoffStore(tmp_path / "handoffs"),
        LocalTradePlanStore(tmp_path / "plans"),
    )
    projection = workflow.construct(
        completed,
        _evidence(completed),
        _context(completed.requirement.canonical_instrument),
        current_run_identity=completed.requirement.native_run_identity,
        current_analysis_boundary=completed.promotion.analysis_boundary,
        created_at=NOW,
    )
    live = replace(
        projection,
        sponsor_observation_controls_available=False,
        sponsor_observation_decision_state="LIVE · RECORDED",
        sponsor_observation_choice="LIVE",
        sponsor_observation_decision_id="SPONSOR-OBSERVATION-DECISION-LIVE",
        sponsor_observation_snapshot_id="SPONSOR-DECISION-SNAPSHOT-LIVE",
        activation_disposition="PENDING_ENTRY_CONFIRMATION",
        activation_reason="PENDING_ENTRY_CONFIRMATION",
        risk_state="RISK_APPROVED",
        risk_reason="NO_GOVERNED_PROHIBITION",
    )
    html = render_native_trade_window(_ready(), live)
    assert "LIVE TRADE ENTRY" in html
    assert 'name="actual_entry"' in html
    assert 'name="lots"' in html
    assert 'name="manual_execution_confirmed"' in html
    assert "KRONOS will not place, modify or cancel an order" in html
    assert "CONFIRM LIVE ENTRY" in html


def test_blocked_paper_decision_exposes_distinct_explicit_track_control(tmp_path) -> None:
    completed = _completed(tmp_path)
    workflow = SwingTradeWindowWorkflow(
        LocalKr370Step31HandoffStore(tmp_path / "handoffs"),
        LocalTradePlanStore(tmp_path / "plans"),
    )
    projected = workflow.construct(
        completed,
        _evidence(completed),
        _context(completed.requirement.canonical_instrument),
        current_run_identity=completed.requirement.native_run_identity,
        current_analysis_boundary=completed.promotion.analysis_boundary,
        created_at=NOW,
    )
    observation = projected.step31_observation
    assert observation is not None
    decision = workflow.record_sponsor_observation_choice(
        projected.native_run_identity,
        projected.canonical_instrument,
        projected.native_assessment_sha256,
        observation.observation_evidence_id,
        SponsorTradeChoice.PAPER,
        SponsorActivationDisposition.BLOCKED_RISK_UNAVAILABLE,
        current_run_identity=projected.native_run_identity,
        decided_at=NOW,
        warning_acknowledged=False,
        risk_state="RISK_UNAVAILABLE",
    )
    available = workflow.project(
        projected.native_run_identity, projected.canonical_instrument
    )
    html = render_native_trade_window(_ready(), available)

    assert available.paper_observation_track_start_available
    assert available.paper_observation_track_state == "AVAILABLE"
    assert "PAPER OBSERVATION TRACK" in html
    assert "Research-only factual path observation" in html
    assert 'action="/swing/trade-window/paper-observation/start"' in html
    assert 'name="track_confirmed"' in html
    assert "START PAPER OBSERVATION" in html
    assert "no Sponsor Position" in html
    assert "trade-blocked" in html
    assert "PAPER-OBSERVATION-TRACK" not in html
    assert html.index("SPONSOR DECISION") < html.index("POSITION ACTIVATION")
    assert html.index("POSITION ACTIVATION") < html.index("PAPER OBSERVATION TRACK")

    started = workflow.start_paper_observation_track(
        projected.native_run_identity,
        projected.canonical_instrument,
        projected.native_assessment_sha256,
        decision.decision.decision_identity,
        current_run_identity=projected.native_run_identity,
        started_at=NOW,
    )
    assert started.track.track_identity
    active_html = render_native_trade_window(
        _ready(),
        workflow.project(projected.native_run_identity, projected.canonical_instrument),
    )
    assert "ACTIVE" in active_html
    assert "NOT ACTIVE" in active_html
    assert "ENTRY NOT OBSERVED" in active_html
    assert "START PAPER OBSERVATION" not in active_html
    assert "No position, order, fill, P&amp;L or actual R is created" in active_html

    current = workflow.project(
        projected.native_run_identity, projected.canonical_instrument
    )
    interrupted_html = render_native_trade_window(
        _ready(),
        replace(
            current,
            paper_observation_track_state="MONITORING_INTERRUPTED",
            paper_observation_monitoring_state="INTERRUPTED",
            paper_observation_monitoring_reason="PROVIDER_DISCONNECTED",
        ),
    )
    assert "MONITORING INTERRUPTED" in interrupted_html
    assert "PROVIDER DISCONNECTED" in interrupted_html

    complete_html = render_native_trade_window(
        _ready(),
        replace(
            current,
            paper_observation_track_state="COMPLETE",
            paper_observation_monitoring_state="COMPLETE",
            paper_observation_monitoring_reason="TERMINAL_FACTUAL_OUTCOME_RETAINED",
            paper_observation_entry_state="ENTRY_OBSERVED",
            paper_observation_outcome_state="TARGET_LEVEL_TOUCHED",
        ),
    )
    assert "PAPER OBSERVATION TRACK" in complete_html
    assert "COMPLETE" in complete_html
    assert "ENTRY OBSERVED" in complete_html
    assert "TARGET LEVEL TOUCHED" in complete_html
    assert "PROFIT" not in complete_html and "ACTUAL R" not in complete_html


def test_activated_paper_position_suppresses_duplicate_track(tmp_path) -> None:
    completed = _completed(tmp_path)
    workflow = SwingTradeWindowWorkflow(
        LocalKr370Step31HandoffStore(tmp_path / "handoffs"),
        LocalTradePlanStore(tmp_path / "plans"),
    )
    projection = workflow.construct(
        completed,
        _evidence(completed),
        _context(completed.requirement.canonical_instrument),
        current_run_identity=completed.requirement.native_run_identity,
        current_analysis_boundary=completed.promotion.analysis_boundary,
        created_at=NOW,
    )
    activated = replace(
        projection,
        sponsor_observation_controls_available=False,
        sponsor_observation_decision_state="PAPER · RECORDED",
        sponsor_observation_choice="PAPER",
        sponsor_observation_decision_id="SPONSOR-OBSERVATION-DECISION-PAPER",
        sponsor_observation_snapshot_id="SPONSOR-DECISION-SNAPSHOT-PAPER",
        activation_disposition="ACTIVATED",
        activation_reason="GOVERNED_SPONSOR_POSITION_ACTIVATED",
        sponsor_position_state="PAPER · ACTIVE",
        sponsor_position_id="SPONSOR-POSITION-PAPER",
        paper_observation_track_state="NOT REQUIRED",
        paper_observation_monitoring_reason="GOVERNED SPONSOR POSITION ACTIVATED",
    )
    html = render_native_trade_window(_ready(), activated)
    assert "PAPER OBSERVATION TRACK" in html
    assert "NOT REQUIRED" in html
    assert "duplicate non-position Track is not created" in html
    assert "START PAPER OBSERVATION" not in html


def test_risk_permitted_paper_pending_entry_does_not_offer_duplicate_track(
    tmp_path,
) -> None:
    completed = _completed(tmp_path)
    workflow = SwingTradeWindowWorkflow(
        LocalKr370Step31HandoffStore(tmp_path / "handoffs"),
        LocalTradePlanStore(tmp_path / "plans"),
        LocalPortfolioStateV1Store(tmp_path / "portfolio"),
        LocalRiskPermissionV1Store(tmp_path / "risk"),
    )
    projection = workflow.construct(
        completed,
        _evidence(completed),
        _context(completed.requirement.canonical_instrument),
        current_run_identity=completed.requirement.native_run_identity,
        current_analysis_boundary=completed.promotion.analysis_boundary,
        created_at=NOW,
    )
    observation = projection.step31_observation
    plan = projection.trade_plan
    assert observation is not None and plan is not None
    from tests.unit.browser.test_browser_trade_lifecycle_continuity import _review

    workflow.publish_current_portfolio_state(
        _review(completed, plan),
        native_run_identity=plan.native_run_identity,
        as_of_boundary=plan.observation_boundary,
    )
    risk = workflow.evaluate_current_risk(
        plan.native_run_identity, plan.canonical_instrument, evaluated_at=NOW
    )
    workflow.record_sponsor_observation_choice(
        projection.native_run_identity,
        projection.canonical_instrument,
        projection.native_assessment_sha256,
        observation.observation_evidence_id,
        SponsorTradeChoice.PAPER,
        SponsorActivationDisposition.PENDING_ENTRY_CONFIRMATION,
        current_run_identity=projection.native_run_identity,
        decided_at=NOW,
        warning_acknowledged=False,
        risk_state="RISK_APPROVED",
        risk_identity=risk.risk_result_id,
    )
    pending = workflow.project(
        projection.native_run_identity, projection.canonical_instrument
    )
    html = render_native_trade_window(_ready(), pending)

    assert pending.paper_observation_track_state == "NOT AVAILABLE"
    assert not pending.paper_observation_track_start_available
    assert "START PAPER OBSERVATION" not in html


def test_live_and_ignore_presentations_never_offer_paper_observation_track(
    tmp_path,
) -> None:
    completed = _completed(tmp_path)
    workflow = SwingTradeWindowWorkflow(
        LocalKr370Step31HandoffStore(tmp_path / "handoffs"),
        LocalTradePlanStore(tmp_path / "plans"),
    )
    base = workflow.construct(
        completed,
        _evidence(completed),
        _context(completed.requirement.canonical_instrument),
        current_run_identity=completed.requirement.native_run_identity,
        current_analysis_boundary=completed.promotion.analysis_boundary,
        created_at=NOW,
    )
    for choice, disposition in (
        ("LIVE", "BLOCKED_RISK_UNAVAILABLE"),
        ("IGNORE", "NOT_APPLICABLE_IGNORE"),
    ):
        html = render_native_trade_window(
            _ready(),
            replace(
                base,
                sponsor_observation_choice=choice,
                sponsor_observation_decision_state=choice + " · RECORDED",
                sponsor_observation_decision_id="SPONSOR-OBSERVATION-" + choice,
                sponsor_observation_snapshot_id="SPONSOR-SNAPSHOT-" + choice,
                activation_disposition=disposition,
                activation_reason=disposition,
            ),
        )
        assert "START PAPER OBSERVATION" not in html
