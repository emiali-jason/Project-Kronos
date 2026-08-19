from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Thread
from urllib.parse import urlencode

from kronos.application.notifications import NotificationProduct
from kronos.application.swing_notifications import project_swing_notification_workspace
from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.application.swing_progression_watch import (
    SwingProgressionWatchSnapshot,
    SwingProgressionWatchWorkflow,
)
from kronos.browser.server import create_browser_server
from kronos.browser.views import render_notifications
from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.mtf_facts import FactualTimeframe
from kronos.swing.v1.progression_watch import (
    GovernedCompletedBar,
    ProgressionComparator,
    ProgressionRequirement,
    ProgressionRequirementState,
    ProgressionWatchStore,
    activate_watch,
    deactivate_watch,
    hide_watch,
    mark_watch_stale,
    observe_completed_bar,
)
from tests.unit.application.test_swing_opportunities import _Provider, _ready
from tests.unit.application.test_swing_progression_watch import (
    _Capability as WatchCapability,
    _workflow as watch_workflow,
)
from tests.unit.browser.test_browser_server import _request


NOW = datetime(2026, 8, 19, 8, 0, tzinfo=UTC)
RUN = "SWING-RUN-0123456789ABCDEF0123456789ABCDEF"


def _requirement(instrument: str, suffix: str) -> ProgressionRequirement:
    return ProgressionRequirement(
        suffix * 64, "SWING", instrument, V1Direction.LONG, RUN, "a" * 64,
        "WAIT_PULLBACK_DEVELOPING", "ONE_HOUR_PROGRESSION",
        "1H close above 1482.5", ProgressionRequirementState.WATCH_AVAILABLE,
        FactualTimeframe.ONE_HOUR, ProgressionComparator.BAR_CLOSE_ABOVE,
        1482.5, None, None, ("b" * 64,), NOW, ("KITE",),
    )


def _triggered(instrument: str):  # type: ignore[no-untyped-def]
    watch = activate_watch(_requirement(instrument, "2"), activated_at=NOW)
    return observe_completed_bar(watch, GovernedCompletedBar(
        instrument, FactualTimeframe.ONE_HOUR, 1500.0,
        NOW + timedelta(hours=1), "KITE_NORMALIZED_HISTORICAL",
        "KRONOS-MARKET-CALENDAR-V1-NSE", "2026.1.2", "NSE-CM-REGULAR",
        ("DOMAIN-008",),
    ))


def test_product_neutral_projection_reuses_ux08_identity_and_hides_deleted() -> None:
    active = activate_watch(_requirement("RELIANCE", "1"), activated_at=NOW)
    triggered = _triggered("CANBK")
    inactive = deactivate_watch(
        activate_watch(_requirement("CDSL", "3"), activated_at=NOW),
        occurred_at=NOW + timedelta(minutes=1),
    )
    stale = mark_watch_stale(
        activate_watch(_requirement("RVNL", "4"), activated_at=NOW),
        occurred_at=NOW + timedelta(minutes=1),
    )
    hidden = hide_watch(
        activate_watch(_requirement("SAIL", "5"), activated_at=NOW),
        occurred_at=NOW + timedelta(minutes=1),
    )
    source = SwingProgressionWatchSnapshot(
        RUN, (), (active, triggered, inactive, stale, hidden),
    )
    projection = project_swing_notification_workspace(source)

    assert {item.source_identity for item in projection.records} == {
        active.watch_id, triggered.watch_id, inactive.watch_id, stale.watch_id,
    }
    assert projection.for_product(NotificationProduct.INTRADAY) == ()
    assert projection.action_required[0].source_identity == triggered.watch_id


def test_notifications_render_all_states_controls_history_and_non_trading_wording() -> None:
    watches = (
        activate_watch(_requirement("RELIANCE", "1"), activated_at=NOW),
        _triggered("CANBK"),
        deactivate_watch(
            activate_watch(_requirement("CDSL", "3"), activated_at=NOW),
            occurred_at=NOW + timedelta(minutes=1),
        ),
        mark_watch_stale(
            activate_watch(_requirement("RVNL", "4"), activated_at=NOW),
            occurred_at=NOW + timedelta(minutes=1),
        ),
    )
    workspace = project_swing_notification_workspace(
        SwingProgressionWatchSnapshot(RUN, (), watches)
    )
    html = render_notifications(_ready(), workspace)

    for label in (
        "Notifications", "ALL", "SWING", "INTRADAY", "ACTIVE", "TRIGGERED",
        "INACTIVE", "STALE", "DEACTIVATE", "REACTIVATE", "DELETE",
        "PROMOTION WATCH REACHED", "REASSESSMENT REQUIRED",
        "NO TRADE HAS BEEN AUTHORIZED", "WATCH HISTORY",
        "PROVIDER MONITORING UNAVAILABLE",
    ):
        assert label in html
    assert "ACTION CENTRE · 1 REASSESSMENT REQUIRED" in html
    assert "VIEW ANALYSIS DETAILS" in html
    assert "ANALYSIS DETAILS UNAVAILABLE · STALE SOURCE" in html
    assert "BUY" not in html and "SELL" not in html and "ENTRY TRIGGERED" not in html


def test_intraday_filter_is_controlled_empty_and_does_not_manufacture_policy() -> None:
    active = activate_watch(_requirement("RELIANCE", "1"), activated_at=NOW)
    workspace = project_swing_notification_workspace(
        SwingProgressionWatchSnapshot(RUN, (), (active,))
    )
    html = render_notifications(
        _ready(), workspace, selected_product=NotificationProduct.INTRADAY,
    )
    assert "No Intraday notifications" in html
    assert "Intraday alert policy has not been manufactured" in html
    assert "RELIANCE" not in html


def test_notifications_routes_load_and_global_navigation_is_permanent(tmp_path: Path) -> None:
    app = SwingOpportunitiesApplication(_Provider, initial_snapshot=_ready())
    workflow = SwingProgressionWatchWorkflow(ProgressionWatchStore(tmp_path / "watches"))
    server = create_browser_server(app, port=0, progression_watches=workflow)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for path in ("/notifications", "/notifications/swing", "/notifications/intraday"):
            status, _, body = _request(server, "GET", path)
            assert status == 200
            assert 'href="/notifications"' in body
            assert "Notifications" in body
        assert "No Intraday notifications" in _request(
            server, "GET", "/notifications/intraday"
        )[2]
        assert _request(server, "GET", "/swing/opportunities")[0] == 200
        assert _request(server, "GET", "/intraday")[0] == 200
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_notification_posts_are_same_origin_and_update_the_owned_ux08_record(tmp_path: Path) -> None:
    app = SwingOpportunitiesApplication(_Provider, initial_snapshot=_ready())
    workflow = watch_workflow(tmp_path / "watches")
    server = create_browser_server(app, port=0, progression_watches=workflow)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    requirement = _requirement("RELIANCE", "1")
    workflow.synchronize(RUN, (requirement,))
    watch = workflow.activate_requirement(requirement.requirement_id, WatchCapability())
    body = urlencode({"watch_id": watch.watch_id})
    authority = f"127.0.0.1:{server.server_port}"
    headers = {
        "Host": authority,
        "Origin": f"http://{authority}",
        "Content-Type": "application/x-www-form-urlencoded",
        "Content-Length": str(len(body)),
    }
    try:
        status, response_headers, _ = _request(
            server, "POST", "/notifications/watch/deactivate",
            headers=headers, body=body,
        )
        assert status == 303
        assert response_headers["Location"] == "/notifications"
        assert workflow.snapshot().watches[0].state.value == "INACTIVE"

        foreign = dict(headers, Origin="http://evil.example")
        assert _request(
            server, "POST", "/notifications/watch/delete",
            headers=foreign, body=body,
        )[0] == 403
        assert workflow.snapshot().watches[0].workspace_hidden is False

        assert _request(
            server, "POST", "/notifications/watch/delete",
            headers=headers, body=body,
        )[0] == 303
        assert workflow.snapshot().watches[0].workspace_hidden is True
        assert "RELIANCE" not in _request(server, "GET", "/notifications")[2]
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
