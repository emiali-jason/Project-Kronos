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
    assert "SPONSOR DECISION PATH" in window
    assert "PENDING OBSERVATION-PHASE DECISION WIRING" in window
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
    assert "PENDING OBSERVATION-PHASE DECISION WIRING" in html
    assert "CONSTRUCT TRADE PLAN" not in html
    assert "PAPER</button>" not in html and "LIVE</button>" not in html
