from pathlib import Path
from threading import Thread
from urllib.parse import urlencode

import pytest

from kronos.application.swing_native_review import NativeReviewWorkflow
from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.application.swing_progression_watch import SwingProgressionWatchWorkflow
from kronos.application.swing_ux10 import (
    SwingUx10NotificationService,
    Ux10NotificationStore,
)
from kronos.application.swing_v1_review import SwingV1ReviewWorkflow
from kronos.browser.server import create_browser_server
from kronos.browser.views import render_notifications, render_settings
from kronos.configuration.openai_chart_analyst import (
    ChartAnalystConnectionStatus,
    ChartAnalystV2ActivationStatus,
)
from kronos.swing.v1.evidence_store import LocalTradingViewEvidenceStore
from kronos.swing.v1.native_review import NativeReviewEvidenceStore
from kronos.swing.v1.progression_watch import ProgressionWatchStore
from tests.unit.application.test_swing_opportunities import _Provider, _ready
from tests.unit.application.test_swing_ux10 import immediate
from tests.unit.integrations.test_telegram import TOKEN, service as telegram_service
from tests.unit.browser.test_browser_notifications import _triggered
from tests.unit.browser.test_browser_server import _request
from kronos.application.notifications import NotificationWorkspaceSnapshot


def _server(tmp_path: Path):  # type: ignore[no-untyped-def]
    telegram, vault, transport = telegram_service((
        {"message": {"chat": {"id": 11111, "type": "private"}}},
    ))
    ux10 = SwingUx10NotificationService(
        Ux10NotificationStore(tmp_path / "ux10"), telegram=telegram,
        background_runner=immediate,
    )
    server = create_browser_server(
        SwingOpportunitiesApplication(_Provider, initial_snapshot=_ready()),
        port=0,
        v1_review=SwingV1ReviewWorkflow(
            LocalTradingViewEvidenceStore(tmp_path / "legacy")
        ),
        native_review=NativeReviewWorkflow(
            NativeReviewEvidenceStore(tmp_path / "native")
        ),
        progression_watches=SwingProgressionWatchWorkflow(
            ProgressionWatchStore(tmp_path / "watches")
        ),
        telegram=telegram,
        ux10_notifications=ux10,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, telegram, vault, transport, ux10


def _post_headers(server, body=""):  # type: ignore[no-untyped-def]
    authority = f"127.0.0.1:{server.server_port}"
    return {
        "Host": authority,
        "Origin": f"http://{authority}",
        "Content-Type": "application/x-www-form-urlencoded",
        "Content-Length": str(len(body)),
    }


def test_settings_is_masked_and_contains_governed_telegram_controls() -> None:
    telegram, _, _ = telegram_service()
    telegram.configure_token(TOKEN)
    html = render_settings(
        _ready(), ChartAnalystConnectionStatus.NOT_CONFIGURED,
        ChartAnalystV2ActivationStatus.DISABLED,
        telegram_status=telegram.status(),
    )
    for value in (
        "Telegram Notifications", "CONFIGURED · ••••••••", "SAVE TELEGRAM TOKEN",
        "DISCOVER PRIVATE CHAT", "TEST TELEGRAM",
    ):
        assert value in html
    assert TOKEN not in html
    assert "chat_id" not in html


def test_settings_control_centre_is_compact_responsive_and_capability_tinted() -> None:
    telegram, vault, _ = telegram_service()
    telegram.configure_token(TOKEN)
    vault.store_api_key("ux10-private-chat", "11111")
    html = render_settings(
        _ready(), ChartAnalystConnectionStatus.CONNECTED,
        ChartAnalystV2ActivationStatus.ENABLED,
        telegram_status=telegram.status(),
        kite_active_watch_count=1,
    )
    for value in (
        "settings-control-centre", "settings-kite", "settings-telegram",
        "settings-calendar", "settings-openai", "settings-engineering",
        "settings-security", "@media(max-width:1100px)",
        "@media(max-width:700px)", "ADVANCED SETUP", "SYSTEM &amp; SECURITY",
        "ORDER CAPABILITY</span><strong>NONE", "LIVE MONITORING IS ACTIVE",
    ):
        assert value in html
    assert ".topbar .title h1{font-size:24px}" in html
    assert "Auto Trade" not in html and "Auto Buy" not in html


def test_blue_swing_notification_cards_render_delivery_state(tmp_path: Path) -> None:
    value = SwingUx10NotificationService(Ux10NotificationStore(tmp_path))
    value.observe_progression_watch(_triggered("CANBK"))
    html = render_notifications(
        _ready(), NotificationWorkspaceSnapshot(()), ux10=value.snapshot()
    )
    assert "ux10-row" in html
    assert "KRONOS · SWING" in html
    assert "PROMOTION CONDITION MET" in html
    assert "REFRESH SWING ANALYSIS" in html
    assert "TELEGRAM PENDING SETUP" in html


def test_settings_routes_configure_discover_confirm_and_test_without_rendering_secrets(
    tmp_path: Path,
) -> None:
    server, thread, telegram, vault, transport, _ = _server(tmp_path)
    try:
        token_body = urlencode({"bot_token": TOKEN})
        assert _request(
            server, "POST", "/settings/telegram/token",
            headers=_post_headers(server, token_body), body=token_body,
        )[0] == 303
        assert _request(
            server, "POST", "/settings/telegram/private-chat/discover",
            headers=_post_headers(server), body="",
        )[0] == 303
        candidate = telegram.private_chat_candidates()[0]
        selection_body = urlencode({"selection_id": candidate.selection_id})
        assert _request(
            server, "POST", "/settings/telegram/private-chat/confirm",
            headers=_post_headers(server, selection_body), body=selection_body,
        )[0] == 303
        assert _request(
            server, "POST", "/settings/telegram/test",
            headers=_post_headers(server), body="",
        )[0] == 303
        html = _request(server, "GET", "/settings")[2]
        assert "PRIVATE CHAT" in html and "CONFIRMED" in html
        assert TOKEN not in html and "11111" not in html
        assert vault.key
        assert transport.calls[-1][1]["text"] == (
            "KRONOS · SWING\nTelegram connection test successful."
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_telegram_disconnect_reconnect_and_explicit_removal_routes_are_distinct(
    tmp_path: Path,
) -> None:
    server, thread, telegram, vault, transport, _ = _server(tmp_path)
    telegram.configure_token(TOKEN)
    vault.store_api_key("ux10-private-chat", "11111")
    try:
        assert _request(
            server, "POST", "/settings/telegram/disconnect",
            headers=_post_headers(server), body="",
        )[0] == 303
        assert telegram.status().delivery_enabled is False
        assert vault.secret and vault.key
        call_count = len(transport.calls)
        assert _request(server, "GET", "/settings")[2].count("DISCONNECTED") >= 1

        assert _request(
            server, "POST", "/settings/telegram/connect",
            headers=_post_headers(server), body="",
        )[0] == 303
        assert telegram.status().delivery_enabled is True
        assert len(transport.calls) == call_count + 1

        bad = urlencode({"confirm_remove": "NO"})
        assert _request(
            server, "POST", "/settings/telegram/remove",
            headers=_post_headers(server, bad), body=bad,
        )[0] == 400
        assert vault.secret and vault.key
        assert _request(
            server, "POST", "/settings/telegram/remove?confirm=REMOVE",
            headers=_post_headers(server), body="",
        )[0] == 303
        assert vault.secret == {} and vault.key == {}
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_kite_disconnect_requires_confirmation_while_live_monitoring_is_active(
    tmp_path: Path,
) -> None:
    server, thread, *_ = _server(tmp_path)
    server.active_live_monitoring_count = lambda: 1  # type: ignore[method-assign]
    try:
        status, headers, _ = _request(
            server, "POST", "/provider/disconnect",
            headers=_post_headers(server), body="",
        )
        assert status == 303
        assert headers["Location"] == "/settings#kite-market-data"
        assert server.application.snapshot().provider_state.value == "CONNECTED"

        confirmed = urlencode({"confirm_active": "YES"})
        assert _request(
            server, "POST", "/provider/disconnect",
            headers=_post_headers(server, confirmed), body=confirmed,
        )[0] == 303
        assert server.application.snapshot().provider_state.value == "DISCONNECTED"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


@pytest.mark.parametrize(
    "path",
    (
        "/settings/telegram/token",
        "/settings/telegram/private-chat/discover",
        "/settings/telegram/private-chat/confirm",
        "/settings/telegram/test",
        "/settings/telegram/connect",
        "/settings/telegram/disconnect",
        "/settings/telegram/remove",
    ),
)
def test_all_telegram_mutations_reject_foreign_origin(tmp_path: Path, path: str) -> None:
    server, thread, *_ = _server(tmp_path)
    try:
        body = urlencode({
            "bot_token" if path.endswith("token") else "selection_id":
            TOKEN if path.endswith("token") else "a" * 64
        }) if path.endswith(("token", "confirm")) else ""
        headers = _post_headers(server, body)
        headers["Origin"] = "http://evil.example"
        assert _request(server, "POST", path, headers=headers, body=body)[0] == 403
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
