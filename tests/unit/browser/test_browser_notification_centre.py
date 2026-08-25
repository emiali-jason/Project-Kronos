from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Thread
from urllib.parse import urlencode

import pytest

from kronos.application.notification_centre import (
    SponsorNotificationCentre,
    SponsorNotificationCentreSnapshot,
    SponsorNotificationFilter,
    SponsorNotificationLifecycleStore,
    SponsorNotificationQuery,
    SponsorNotificationState,
    project_sponsor_notifications,
)
from kronos.application.notifications import NotificationWorkspaceSnapshot
from kronos.application.swing_notifications import project_swing_notification_workspace
from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.application.swing_v1_review import SwingV1ReviewWorkflow
from kronos.application.swing_refresh_reminder import (
    K5RefreshReminderRecord,
    RefreshReminderState,
    _integrity_values as reminder_integrity,
)
from kronos.application.swing_ux10 import (
    SwingUx10NotificationService,
    Ux10NotificationSnapshot,
    Ux10NotificationStore,
)
from kronos.browser.server import create_browser_server
from kronos.browser.views import render_notifications
from kronos.provider.contracts.monitoring import MonitoringConnectionState
from tests.unit.application.test_swing_opportunities import _Provider, _ready
from tests.unit.browser.test_browser_notifications import (
    RUN,
    _requirement,
    _triggered,
)
from tests.unit.browser.test_browser_server import _request
from kronos.swing.v1.progression_watch import (
    activate_watch,
    deactivate_watch,
)
from kronos.swing.v1 import LocalTradingViewEvidenceStore
from kronos.application.swing_progression_watch import SwingProgressionWatchSnapshot


NOW = datetime(2026, 8, 25, 5, 45, tzinfo=UTC)
NEW_RUN = "SWING-RUN-FEDCBA9876543210FEDCBA9876543210"


def _reminder(
    *, identity: str = "1" * 64, instrument: str = "CDSL"
) -> K5RefreshReminderRecord:
    values = dict(
        reminder_identity=identity,
        run_identity=RUN,
        instrument_bindings=((instrument, "a" * 64, "BUY_READY", "NSE"),),
        source_boundaries=((instrument, NOW - timedelta(hours=1)),),
        next_eligible_completed_1h_boundary=NOW,
        calendar_bindings=(("NSE", "KRONOS-MARKET-CALENDAR-V1-NSE", "2026.1.2"),),
        state=RefreshReminderState.PENDING,
        created_at=NOW - timedelta(minutes=5),
        updated_at=NOW - timedelta(minutes=5),
        notification_identity=None,
        integrity_sha256="",
    )
    return K5RefreshReminderRecord(**(
        values | {"integrity_sha256": reminder_integrity(values)}
    ))


def _ux10(tmp_path: Path) -> tuple[SwingUx10NotificationService, Ux10NotificationSnapshot]:
    service = SwingUx10NotificationService(
        Ux10NotificationStore(tmp_path / "ux10"), clock=lambda: NOW,
    )
    service.observe_refresh_analysis_reminder(_reminder())
    service.observe_progression_watch(_triggered("CANBK"))
    return service, service.snapshot()


def _watches() -> NotificationWorkspaceSnapshot:
    active = activate_watch(_requirement("RELIANCE", "7"), activated_at=NOW)
    inactive = deactivate_watch(
        activate_watch(_requirement("SAIL", "8"), activated_at=NOW),
        occurred_at=NOW + timedelta(minutes=1),
    )
    return project_swing_notification_workspace(
        SwingProgressionWatchSnapshot(RUN, (), (active, inactive))
    )


def _next_boundary(_identity: str, after: datetime) -> datetime:
    elapsed = int((after - NOW).total_seconds() // 3600)
    return NOW + timedelta(hours=elapsed + 1)


def _centre(tmp_path: Path, clock: list[datetime]) -> SponsorNotificationCentre:
    return SponsorNotificationCentre(
        SponsorNotificationLifecycleStore(tmp_path / "centre"),
        clock=lambda: clock[0],
        reminder_boundary_resolver=_next_boundary,
    )


def test_compact_swing_centre_projects_live_expired_families_and_ws(tmp_path: Path) -> None:
    clock = [NOW]
    _, ux10 = _ux10(tmp_path)
    centre = _centre(tmp_path, clock)
    snapshot = centre.synchronize(
        _watches(), ux10, current_run_identity=RUN, websocket_state="CONNECTED"
    )
    projection = project_sponsor_notifications(snapshot, SponsorNotificationQuery())
    html = render_notifications(
        _ready(), _watches(), selected_product=None, ux10=ux10,
        operational=projection,
    )
    assert snapshot.live_count == 3 and snapshot.expired_count == 1
    for value in (
        "SWING", "INTRADAY", "WS ● CONNECTED", "LIVE 3", "EXPIRED 1",
        "notification-centre-row", "NEXT 12:15", "REFRESH", "OPEN", "🗑",
        "DELETE NOTIFICATION", "GOVERNED EVIDENCE",
    ):
        assert value in html
    assert "KITE CONNECTED" not in html
    assert "notification-row ux10-row" not in html


@pytest.mark.parametrize(
    ("state", "expected"),
    (("CONNECTED", "WS ● CONNECTED"), ("DISCONNECTED", "WS ● DISCONNECTED"), ("IDLE", "WS ○ IDLE")),
)
def test_ws_state_is_textual_restrained_and_provider_independent(
    tmp_path: Path, state: str, expected: str,
) -> None:
    clock = [NOW]
    snapshot = _centre(tmp_path, clock).synchronize(
        NotificationWorkspaceSnapshot(()), Ux10NotificationSnapshot(()),
        current_run_identity=RUN, websocket_state=state,
    )
    html = render_notifications(
        _ready(), NotificationWorkspaceSnapshot(()),
        operational=project_sponsor_notifications(snapshot, SponsorNotificationQuery()),
    )
    assert expected in html


def test_individual_delete_is_durable_idempotent_and_preserves_source(tmp_path: Path) -> None:
    clock = [NOW]
    service, ux10 = _ux10(tmp_path)
    store = SponsorNotificationLifecycleStore(tmp_path / "centre")
    centre = SponsorNotificationCentre(
        store, clock=lambda: clock[0], reminder_boundary_resolver=_next_boundary,
    )
    snapshot = centre.synchronize(
        NotificationWorkspaceSnapshot(()), ux10,
        current_run_identity=RUN, websocket_state="IDLE",
    )
    target = next(item for item in snapshot.records if item.state is SponsorNotificationState.LIVE)
    clock[0] += timedelta(minutes=1)
    deleted = centre.dismiss(target.notification_identity, target.integrity_sha256)
    assert deleted.dismissed and deleted.recurrence_cancelled
    assert centre.dismiss(target.notification_identity, target.integrity_sha256) == deleted
    assert len(service.snapshot().records) == 2
    restored = SponsorNotificationCentre(
        store, clock=lambda: clock[0], reminder_boundary_resolver=_next_boundary,
    ).synchronize(
        NotificationWorkspaceSnapshot(()), service.snapshot(),
        current_run_identity=RUN, websocket_state="IDLE",
    )
    assert target.notification_identity not in {
        item.notification_identity for item in restored.visible
    }


def test_delete_expired_scopes_only_expired_and_preserves_live(tmp_path: Path) -> None:
    clock = [NOW]
    _, ux10 = _ux10(tmp_path)
    centre = _centre(tmp_path, clock)
    snapshot = centre.synchronize(
        _watches(), ux10, current_run_identity=RUN, websocket_state="IDLE"
    )
    live = {item.notification_identity for item in snapshot.visible if item.state.value == "LIVE"}
    assert centre.dismiss_expired(occurred_at=NOW + timedelta(minutes=2)) == 1
    after = centre.synchronize(
        _watches(), ux10, current_run_identity=RUN, websocket_state="IDLE"
    )
    assert {item.notification_identity for item in after.visible} == live


def test_refresh_reactivation_creates_one_linked_identity_and_stale_fails(tmp_path: Path) -> None:
    clock = [NOW]
    _, ux10 = _ux10(tmp_path)
    centre = _centre(tmp_path, clock)
    snapshot = centre.synchronize(
        NotificationWorkspaceSnapshot(()), ux10,
        current_run_identity=RUN, websocket_state="IDLE",
    )
    reminder = next(item for item in snapshot.records if item.notification_type == "REFRESH_ANALYSIS_REMINDER")
    clock[0] += timedelta(minutes=1)
    expired = centre.expire(
        reminder.notification_identity, reminder.integrity_sha256,
        source_still_valid=True,
    )
    clock[0] += timedelta(minutes=1)
    child = centre.reactivate(
        expired.notification_identity, expired.integrity_sha256, source_valid=True
    )
    repeated = centre.reactivate(
        expired.notification_identity, expired.integrity_sha256, source_valid=True
    )
    assert child == repeated
    assert child.reactivated_from == expired.notification_identity
    assert child.notification_identity != expired.notification_identity
    assert centre.record(expired.notification_identity).state is SponsorNotificationState.EXPIRED  # type: ignore[union-attr]
    restored = SponsorNotificationCentre(
        SponsorNotificationLifecycleStore(tmp_path / "centre"),
        clock=lambda: clock[0], reminder_boundary_resolver=_next_boundary,
    )
    assert restored.record(child.notification_identity) == child
    assert restored.record(expired.notification_identity) == expired
    with pytest.raises(ValueError, match="SOURCE_SUPERSEDED"):
        centre.reactivate(
            expired.notification_identity, expired.integrity_sha256,
            source_valid=False, occurred_at=clock[0] + timedelta(minutes=1),
        )


def test_hourly_reminders_use_one_row_history_and_resolve_only_on_new_run(tmp_path: Path) -> None:
    clock = [NOW]
    _, ux10 = _ux10(tmp_path)
    centre = _centre(tmp_path, clock)
    first = centre.synchronize(
        NotificationWorkspaceSnapshot(()), ux10,
        current_run_identity=RUN, websocket_state="IDLE",
    )
    identity = next(item.notification_identity for item in first.records if item.notification_type == "REFRESH_ANALYSIS_REMINDER")
    for hour in (1, 2):
        clock[0] = NOW + timedelta(hours=hour)
        current = centre.synchronize(
            NotificationWorkspaceSnapshot(()), ux10,
            current_run_identity=RUN, websocket_state="IDLE",
        )
        record = centre.record(identity)
        assert record is not None and record.reminder_count == hour + 1
        assert sum(item.notification_type == "REFRESH_ANALYSIS_REMINDER" for item in current.visible) == 1
    failed_refresh = centre.synchronize(
        NotificationWorkspaceSnapshot(()), ux10,
        current_run_identity=RUN, websocket_state="IDLE",
    )
    assert centre.record(identity).state is SponsorNotificationState.LIVE  # type: ignore[union-attr]
    resolved = centre.synchronize(
        NotificationWorkspaceSnapshot(()), ux10,
        current_run_identity=NEW_RUN, websocket_state="IDLE",
    )
    assert centre.record(identity).state is SponsorNotificationState.EXPIRED  # type: ignore[union-attr]
    assert failed_refresh.revision != resolved.revision


def test_missed_hour_recovery_adds_one_event_and_next_future_boundary(tmp_path: Path) -> None:
    clock = [NOW]
    _, ux10 = _ux10(tmp_path)
    store = SponsorNotificationLifecycleStore(tmp_path / "centre")
    centre = SponsorNotificationCentre(
        store, clock=lambda: clock[0], reminder_boundary_resolver=_next_boundary,
    )
    first = centre.synchronize(
        NotificationWorkspaceSnapshot(()), ux10,
        current_run_identity=RUN, websocket_state="IDLE",
    )
    identity = next(item.notification_identity for item in first.records if item.notification_type == "REFRESH_ANALYSIS_REMINDER")
    clock[0] = NOW + timedelta(hours=4, minutes=10)
    restored = SponsorNotificationCentre(
        store, clock=lambda: clock[0], reminder_boundary_resolver=_next_boundary,
    )
    restored.synchronize(
        NotificationWorkspaceSnapshot(()), ux10,
        current_run_identity=RUN, websocket_state="IDLE",
    )
    record = restored.record(identity)
    assert record is not None and record.reminder_count == 2
    assert record.next_reminder_at == NOW + timedelta(hours=5)
    unchanged = restored.synchronize(
        NotificationWorkspaceSnapshot(()), ux10,
        current_run_identity=RUN, websocket_state="IDLE",
    )
    assert unchanged.revision == restored.synchronize(
        NotificationWorkspaceSnapshot(()), ux10,
        current_run_identity=RUN, websocket_state="IDLE",
    ).revision


def test_restart_before_boundary_emits_exactly_one_due_reminder(tmp_path: Path) -> None:
    clock = [NOW]
    _, ux10 = _ux10(tmp_path)
    store = SponsorNotificationLifecycleStore(tmp_path / "centre")
    first = SponsorNotificationCentre(
        store, clock=lambda: clock[0], reminder_boundary_resolver=_next_boundary,
    )
    snapshot = first.synchronize(
        NotificationWorkspaceSnapshot(()), ux10,
        current_run_identity=RUN, websocket_state="IDLE",
    )
    identity = next(
        item.notification_identity for item in snapshot.records
        if item.notification_type == "REFRESH_ANALYSIS_REMINDER"
    )
    clock[0] = NOW + timedelta(minutes=59)
    restored = SponsorNotificationCentre(
        store, clock=lambda: clock[0], reminder_boundary_resolver=_next_boundary,
    )
    restored.synchronize(
        NotificationWorkspaceSnapshot(()), ux10,
        current_run_identity=RUN, websocket_state="IDLE",
    )
    assert restored.record(identity).reminder_count == 1  # type: ignore[union-attr]
    clock[0] = NOW + timedelta(hours=1)
    restored.synchronize(
        NotificationWorkspaceSnapshot(()), ux10,
        current_run_identity=RUN, websocket_state="IDLE",
    )
    restored.synchronize(
        NotificationWorkspaceSnapshot(()), ux10,
        current_run_identity=RUN, websocket_state="IDLE",
    )
    assert restored.record(identity).reminder_count == 2  # type: ignore[union-attr]


def test_deleted_live_reminder_stops_recurrence_but_future_source_is_independent(
    tmp_path: Path,
) -> None:
    clock = [NOW]
    service, ux10 = _ux10(tmp_path)
    centre = _centre(tmp_path, clock)
    snapshot = centre.synchronize(
        NotificationWorkspaceSnapshot(()), ux10,
        current_run_identity=RUN, websocket_state="IDLE",
    )
    reminder = next(
        item for item in snapshot.records
        if item.notification_type == "REFRESH_ANALYSIS_REMINDER"
    )
    clock[0] += timedelta(minutes=1)
    centre.dismiss(reminder.notification_identity, reminder.integrity_sha256)
    clock[0] = NOW + timedelta(hours=3)
    centre.synchronize(
        NotificationWorkspaceSnapshot(()), service.snapshot(),
        current_run_identity=RUN, websocket_state="IDLE",
    )
    assert centre.record(reminder.notification_identity).reminder_count == 1  # type: ignore[union-attr]
    service.observe_refresh_analysis_reminder(
        _reminder(identity="2" * 64, instrument="RVNL")
    )
    current = centre.synchronize(
        NotificationWorkspaceSnapshot(()), service.snapshot(),
        current_run_identity=RUN, websocket_state="IDLE",
    )
    refresh_rows = tuple(
        item for item in current.visible
        if item.notification_type == "REFRESH_ANALYSIS_REMINDER"
    )
    assert len(refresh_rows) == 1
    assert refresh_rows[0].source_identity != reminder.source_identity


def test_recycle_visibility_and_accessibility_are_family_bounded(tmp_path: Path) -> None:
    clock = [NOW]
    _, ux10 = _ux10(tmp_path)
    centre = _centre(tmp_path, clock)
    snapshot = centre.synchronize(
        NotificationWorkspaceSnapshot(()), ux10,
        current_run_identity=RUN, websocket_state="IDLE",
    )
    reminder = next(
        item for item in snapshot.records
        if item.notification_type == "REFRESH_ANALYSIS_REMINDER"
    )
    expired = centre.expire(
        reminder.notification_identity, reminder.integrity_sha256,
        source_still_valid=True, occurred_at=NOW + timedelta(minutes=1),
    )
    html = render_notifications(
        _ready(), NotificationWorkspaceSnapshot(()),
        operational=project_sponsor_notifications(
            SponsorNotificationCentreSnapshot((expired,), "IDLE"),
            SponsorNotificationQuery(),
        ),
    )
    assert "♻" in html and 'aria-label="RE-ACTIVATE NOTIFICATION"' in html
    assert 'aria-label="DELETE NOTIFICATION"' in html
    factual = _centre(tmp_path / "factual", clock).synchronize(
        _watches(), Ux10NotificationSnapshot(()),
        current_run_identity=RUN, websocket_state="IDLE",
    )
    factual_html = render_notifications(
        _ready(), _watches(),
        operational=project_sponsor_notifications(
            factual, SponsorNotificationQuery(state=SponsorNotificationFilter.EXPIRED)
        ),
    )
    assert "♻" not in factual_html


def test_ux10_delivery_copy_does_not_duplicate_governed_watch_row(tmp_path: Path) -> None:
    clock = [NOW]
    service = SwingUx10NotificationService(Ux10NotificationStore(tmp_path / "ux10"))
    triggered = _triggered("CANBK")
    service.observe_progression_watch(triggered)
    watches = project_swing_notification_workspace(
        SwingProgressionWatchSnapshot(RUN, (), (triggered,))
    )
    snapshot = _centre(tmp_path, clock).synchronize(
        watches, service.snapshot(), current_run_identity=RUN, websocket_state="IDLE",
    )
    assert sum(item.instrument == "CANBK" for item in snapshot.visible) == 1


def test_filters_search_order_pagination_and_capacity_are_deterministic(tmp_path: Path) -> None:
    clock = [NOW]
    service = SwingUx10NotificationService(Ux10NotificationStore(tmp_path / "ux10"))
    for index in range(130):
        service.observe_connection_state(
            f"WATCH-{index:03d}", f"ITEM{index:03d}",
            MonitoringConnectionState.DISCONNECTED,
            occurred_at=NOW + timedelta(seconds=index),
        )
    centre = _centre(tmp_path, clock)
    snapshot = centre.synchronize(
        NotificationWorkspaceSnapshot(()), service.snapshot(),
        current_run_identity=RUN, websocket_state="IDLE",
    )
    first = project_sponsor_notifications(snapshot, SponsorNotificationQuery(page=1))
    second = project_sponsor_notifications(snapshot, SponsorNotificationQuery(page=2))
    assert len(first.records) == 130 and first.page_count == 6
    assert len(first.page_records) == len(second.page_records) == 25
    assert not {item.notification_identity for item in first.page_records} & {
        item.notification_identity for item in second.page_records
    }
    search = project_sponsor_notifications(
        snapshot, SponsorNotificationQuery(search="ITEM129")
    )
    assert len(search.records) == 1
    assert project_sponsor_notifications(
        snapshot, SponsorNotificationQuery(state=SponsorNotificationFilter.EXPIRED)
    ).records == ()


def test_intraday_is_bounded_without_swing_ws_or_records() -> None:
    html = render_notifications(
        _ready(), NotificationWorkspaceSnapshot(()),
        selected_product=__import__(
            "kronos.application.notifications", fromlist=["NotificationProduct"]
        ).NotificationProduct.INTRADAY,
    )
    assert "INTRADAY NOTIFICATIONS" in html and "NOT YET OPERATIONAL" in html
    assert "WS — NOT AVAILABLE" in html and "WS ● CONNECTED" not in html


def test_browser_routes_delete_with_same_origin_and_return_in_page_notice(tmp_path: Path) -> None:
    clock = [NOW]
    ux10_service, _ = _ux10(tmp_path)
    centre = _centre(tmp_path, clock)
    app = SwingOpportunitiesApplication(_Provider, initial_snapshot=_ready())
    server = create_browser_server(
        app, port=0, ux10_notifications=ux10_service,
        notification_centre=centre,
        v1_review=SwingV1ReviewWorkflow(
            LocalTradingViewEvidenceStore(tmp_path / "review")
        ),
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, html = _request(server, "GET", "/notifications/swing")
        assert status == 200 and "notification-centre-row" in html
        record = centre.synchronize(
            NotificationWorkspaceSnapshot(()), ux10_service.snapshot(),
            current_run_identity=RUN, websocket_state="IDLE",
        ).visible[0]
        body = urlencode({
            "notification_id": record.notification_identity,
            "revision": record.integrity_sha256,
        })
        authority = f"127.0.0.1:{server.server_port}"
        headers = {
            "Host": authority, "Origin": f"http://{authority}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Content-Length": str(len(body)),
        }
        assert _request(
            server, "POST", "/notifications/dismiss", headers=headers, body=body,
        )[0] == 303
        assert len(ux10_service.snapshot().records) == 2
        stale = urlencode({"notification_id": record.notification_identity, "revision": "0" * 64})
        headers["Content-Length"] = str(len(stale))
        response = _request(
            server, "POST", "/notifications/reactivate", headers=headers, body=stale,
        )
        assert response[0] == 303 and "notice=" in response[1]["Location"]
        notice_page = _request(server, "GET", response[1]["Location"])[2]
        assert "CANNOT RE-ACTIVATE OR DELETE" in notice_page
        response = _request(
            server, "POST", "/notifications/refresh", headers=headers, body=stale,
        )
        assert response[0] == 303 and "notice=" in response[1]["Location"]
        notice_page = _request(server, "GET", response[1]["Location"])[2]
        assert "REFRESH NOT STARTED" in notice_page
    finally:
        server.shutdown(); thread.join(timeout=2); server.server_close()
