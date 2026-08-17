from decimal import Decimal

from kronos.browser.views import _native_trade_plan
from kronos.swing.v1.native_sponsor_decision import SponsorTradeChoice
from tests.unit.swing.v1.test_native_sponsor_decision import _go


def test_step32_eligible_plan_renders_paper_live_ignore_controls() -> None:
    _, plan, *_ = _go(SponsorTradeChoice.PAPER)
    html = _native_trade_plan(plan, step32_eligible=True)
    assert "SPONSOR TRADE DECISION" in html
    assert "PAPER" in html and "1 LOT · LOCKED" in html
    assert "LIVE" in html and "Actual Entry" in html and "Lots" in html
    assert "IGNORE" in html
    assert "/swing/v1/native-trade-decision?plan=" in html
    assert "place_order" not in html


def test_paper_armed_and_live_active_render_without_fake_entry() -> None:
    paper, plan, *_ = _go(SponsorTradeChoice.PAPER)
    paper_html = _native_trade_plan(plan, initiation=paper)
    assert "PAPER ARMED · WAITING FOR ENTRY" in paper_html
    assert "ACTUAL ENTRY" not in paper_html
    live, live_plan, *_ = _go(
        SponsorTradeChoice.LIVE, actual_live_entry=Decimal("103.25"), live_lots=2,
    )
    live_html = _native_trade_plan(live_plan, initiation=live)
    assert "LIVE ACTIVE" in live_html
    assert "ACTUAL ENTRY ₹103.25" in live_html
    assert "MODEL ENTRY ₹100" in live_html
    assert "BROKER EXECUTION MANUAL" in live_html


def test_ignore_renders_terminal_state_without_position() -> None:
    ignored, plan, *_ = _go(SponsorTradeChoice.IGNORE)
    html = _native_trade_plan(plan, initiation=ignored)
    assert "IGNORED" in html and "NO POSITION" in html
