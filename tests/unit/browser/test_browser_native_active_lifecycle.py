from datetime import timedelta
from decimal import Decimal

from kronos.application.swing_v1_browser import BrowserStep32Snapshot
from kronos.browser.views import render_active_candidates, render_closed_candidates
from kronos.swing.v1.native_active_trade_lifecycle import (
    ActiveTradeLifecycleEngine,
    ActiveTradeLifecycleSnapshot,
    GovernedLifecycleObservation,
    create_active_lifecycle,
)
from kronos.swing.v1.native_sponsor_decision import SponsorTradeChoice
from tests.unit.application.test_swing_opportunities import _ready
from tests.unit.swing.v1.test_native_sponsor_decision import NOW, _go


def _observation(position, number, price):  # type: ignore[no-untyped-def]
    stamp = NOW + timedelta(minutes=number)
    return GovernedLifecycleObservation(
        f"OBS-{number}", position.canonical_instrument, Decimal(price), stamp, stamp,
        "KITE_CONNECT_WEBSOCKET", "CONNECTION-1", number, True, True, True,
        "NSE-CM", "NSE-CALENDAR", "2026.1", "SESSION-1", "WINDOW-1",
        ("KITE_CONNECT_WEBSOCKET", "DOMAIN-002", "DOMAIN-008"),
    )


def test_active_tab_shows_paper_waiting_active_values_and_exit_control() -> None:
    result, plan, *_ = _go(SponsorTradeChoice.PAPER)
    position = create_active_lifecycle(result.decision, result.position, plan)
    waiting = ActiveTradeLifecycleSnapshot((position,), (), (), ())
    html = render_active_candidates(_ready(), BrowserStep32Snapshot(None, ()), waiting)
    assert "PAPER · WAITING FOR ENTRY" in html
    assert "Model Entry" in html and "Model R:R" in html
    position, *_ = ActiveTradeLifecycleEngine.observe(position, _observation(position, 1, "99"))
    position, events, notifications, _ = ActiveTradeLifecycleEngine.observe(position, _observation(position, 2, "102"))
    active = ActiveTradeLifecycleSnapshot((position,), events, notifications, ())
    html = render_active_candidates(_ready(), BrowserStep32Snapshot(None, ()), active)
    assert "PAPER ACTIVE" in html and "Actual Entry" in html
    assert ">EXIT<" in html
    assert "place_order" not in html


def test_live_notification_and_record_exit_control_are_prominent() -> None:
    result, plan, *_ = _go(
        SponsorTradeChoice.LIVE, actual_live_entry=Decimal("101"), live_lots=2,
    )
    position = create_active_lifecycle(result.decision, result.position, plan)
    position, events, notifications, _ = ActiveTradeLifecycleEngine.observe(
        position, _observation(position, 1, "122"),
    )
    html = render_active_candidates(
        _ready(), BrowserStep32Snapshot(None, ()),
        ActiveTradeLifecycleSnapshot((position,), events, notifications, ()),
    )
    assert "LIVE ACTIVE" in html
    assert "ACTION REQUIRED — TARGET HIT" in html
    assert "RECORD EXIT" in html and "Actual broker Exit" in html
    assert "close broker" not in html.lower()


def test_active_monitoring_confirmation_requires_actual_attached_position() -> None:
    result, plan, *_ = _go(SponsorTradeChoice.PAPER)
    position = create_active_lifecycle(result.decision, result.position, plan)
    snapshot = ActiveTradeLifecycleSnapshot((position,), (), (), ())

    inactive = render_active_candidates(
        _ready(), BrowserStep32Snapshot(None, ()), snapshot,
    )
    active = render_active_candidates(
        _ready(), BrowserStep32Snapshot(None, ()), snapshot,
        active_monitoring_position_ids=(position.position_id,),
    )

    assert "MONITORING NOT ACTIVE" in inactive
    assert "LIVE MONITORING · SL + TARGET" not in inactive
    assert "LIVE MONITORING · SL + TARGET" in active


def test_closed_tab_renders_factual_economics_and_deterministic_commentary() -> None:
    result, plan, *_ = _go(SponsorTradeChoice.PAPER)
    position = create_active_lifecycle(result.decision, result.position, plan)
    position, *_ = ActiveTradeLifecycleEngine.observe(position, _observation(position, 1, "99"))
    position, entry_events, _, _ = ActiveTradeLifecycleEngine.observe(position, _observation(position, 2, "102"))
    position, exit_events, _, closure = ActiveTradeLifecycleEngine.observe(position, _observation(position, 3, "122"))
    html = render_closed_candidates(
        _ready(), BrowserStep32Snapshot(None, ()),
        ActiveTradeLifecycleSnapshot((position,), (*entry_events, *exit_events), (), (closure,)),
    )
    assert "PAPER CLOSED" in html
    assert "Actual Exit" in html and "Realised R" in html and "Model R:R" in html
    assert "Target was observed before the protective Stop" in html
    assert "excellent" not in html.lower() and "poor trade" not in html.lower()
