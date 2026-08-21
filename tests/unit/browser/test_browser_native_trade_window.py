from kronos.application.swing_trade_window import SwingTradeWindowWorkflow
from kronos.browser.swing_v3_presentation import present_visual_v3_review
from kronos.browser.views import render_native_trade_window, render_opportunities
from kronos.swing.v1.kr370_step31_handoff import LocalKr370Step31HandoffStore
from kronos.swing.v1.native_trade_construction import LocalTradePlanStore
from tests.unit.application.test_swing_opportunities import _ready
from tests.unit.swing.v1.test_kr370_step31_handoff import (
    NOW,
    _completed,
    _context,
    _evidence,
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
    assert "No LIVE / PAPER / IGNORE control is available" in window
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
