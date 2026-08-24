"""SETTINGS-UX-01 restrained operational-status presentation proofs."""

from dataclasses import replace
from datetime import date

from kronos.application.live_monitoring_e2e import (
    LiveMonitoringTestResult,
    LiveMonitoringTestState,
)
from kronos.application.swing_opportunities import ProviderConnectionState
from kronos.browser.views import render_settings
from kronos.configuration.openai_chart_analyst import (
    ChartAnalystConnectionStatus,
    ChartAnalystV2ActivationStatus,
)
from kronos.integrations.telegram import (
    TelegramConfigurationState,
    TelegramConfigurationStatus,
)
from kronos.market.calendar import CalendarCoverageHealth, CalendarCoverageStatus
from tests.unit.application.test_swing_opportunities import _ready


def _calendar(status: CalendarCoverageStatus) -> CalendarCoverageHealth:
    return CalendarCoverageHealth(
        "NSE",
        "KRONOS-MARKET-CALENDAR-V1-NSE-CAPITAL-MARKET",
        "2026.1.2",
        date(2026, 12, 31),
        date(2026, 8, 24),
        status,
    )


def _status(value: str, tone: str) -> str:
    return (
        f'class="settings-status settings-status-{tone}"><span '
        'class="settings-status-dot" aria-hidden="true"></span>'
        f"{value}</strong>"
    )


def _wrapped_status(value: str, tone: str) -> str:
    return (
        f'class="settings-status settings-status-{tone}"><span '
        'class="settings-status-dot" aria-hidden="true"></span><span '
        f'class="settings-status-text"> {value}</span></strong>'
    )


def test_established_operational_states_use_bounded_positive_signals() -> None:
    rendered = render_settings(
        _ready(),
        ChartAnalystConnectionStatus.CONNECTED,
        ChartAnalystV2ActivationStatus.ENABLED,
        LiveMonitoringTestResult(
            LiveMonitoringTestState.PASS,
            "RELIANCE",
            market_data_received=True,
            domain_002_accepted=True,
        ),
        ("RELIANCE",),
        (_calendar(CalendarCoverageStatus.CURRENT),),
        TelegramConfigurationStatus(
            TelegramConfigurationState.READY,
            token_configured=True,
            private_chat_configured=True,
            delivery_enabled=True,
        ),
    )

    assert _wrapped_status("CONNECTED", "positive") in rendered
    assert (
        'class="settings-status settings-status-positive connection-status">'
        '<span class="settings-status-dot" aria-hidden="true"></span>'
        'CONNECTED</strong>'
    ) in rendered
    for value in (
        "PASS",
        "CONFIGURED · ••••••••",
        "CONFIRMED",
        "CURRENT",
        "ENABLED",
    ):
        assert _status(value, "positive") in rendered
    assert '.settings-telegram{--card-accent:#39b99a' in rendered
    assert '.settings-openai{--card-accent:#c06acb' in rendered


def test_genuine_failures_use_restrained_negative_signals() -> None:
    rendered = render_settings(
        replace(_ready(), provider_state=ProviderConnectionState.DISCONNECTED),
        ChartAnalystConnectionStatus.CONNECTION_FAILED,
        ChartAnalystV2ActivationStatus.DISABLED,
        LiveMonitoringTestResult(
            LiveMonitoringTestState.FAIL,
            "RELIANCE",
            safe_reason="WEBSOCKET_NOT_CONNECTED",
        ),
        ("RELIANCE",),
        (_calendar(CalendarCoverageStatus.EXPIRED),),
        TelegramConfigurationStatus(
            TelegramConfigurationState.CONNECTION_FAILED,
            token_configured=False,
            private_chat_configured=False,
            safe_detail="SECURE CREDENTIAL BACKEND UNAVAILABLE",
        ),
    )

    assert _wrapped_status("DISCONNECTED", "negative") in rendered
    assert (
        'class="settings-status settings-status-negative connection-status">'
        '<span class="settings-status-dot" aria-hidden="true"></span>'
        'CONNECTION FAILED</strong>'
    ) in rendered
    for value in ("FAIL", "EXPIRED"):
        assert _status(value, "negative") in rendered
    assert '<span class="dot DISCONNECTED"></span><strong>Kite: DISCONNECTED</strong>' in rendered
    assert ".topbar .dot.DISCONNECTED,.topbar .dot.ERROR{background:var(--red)}" in rendered
    assert _status("DISABLED", "neutral") in rendered


def test_attention_and_intentional_inactive_states_are_not_failures() -> None:
    rendered = render_settings(
        replace(_ready(), provider_state=ProviderConnectionState.CONNECTING),
        ChartAnalystConnectionStatus.NOT_CONFIGURED,
        ChartAnalystV2ActivationStatus.DISABLED,
        LiveMonitoringTestResult(LiveMonitoringTestState.NOT_TESTED),
        market_calendar_health=(_calendar(CalendarCoverageStatus.EXPIRING),),
        telegram_status=TelegramConfigurationStatus(
            TelegramConfigurationState.PRIVATE_CHAT_REQUIRED,
            token_configured=True,
            private_chat_configured=False,
        ),
    )

    assert _wrapped_status("CONNECTING", "attention") in rendered
    assert _wrapped_status("PRIVATE CHAT REQUIRED", "attention") in rendered
    assert _status("EXPIRING", "attention") in rendered
    assert _status("NOT TESTED", "neutral") in rendered
    assert (
        'class="settings-status settings-status-neutral connection-status">'
        '<span class="settings-status-dot" aria-hidden="true"></span>'
        'NOT CONFIGURED</strong>'
    ) in rendered
    assert _status("DISABLED", "neutral") in rendered

    connected_no_data = render_settings(
        _ready(),
        ChartAnalystConnectionStatus.NOT_CONFIGURED,
        ChartAnalystV2ActivationStatus.DISABLED,
        LiveMonitoringTestResult(
            LiveMonitoringTestState.CONNECTED_NO_DATA,
            "RELIANCE",
            safe_reason="NO_LIVE_MARKET_DATA",
        ),
    )
    testing = render_settings(
        _ready(),
        ChartAnalystConnectionStatus.NOT_CONFIGURED,
        ChartAnalystV2ActivationStatus.DISABLED,
        LiveMonitoringTestResult(LiveMonitoringTestState.TESTING, "RELIANCE"),
    )
    assert (
        _status("CONNECTED — NO LIVE MARKET DATA", "attention")
        in connected_no_data
    )
    assert _status("TESTING", "attention") in testing


def test_telegram_disconnected_is_negative_but_configuration_stays_positive() -> None:
    rendered = render_settings(
        _ready(),
        ChartAnalystConnectionStatus.NOT_CONFIGURED,
        ChartAnalystV2ActivationStatus.DISABLED,
        telegram_status=TelegramConfigurationStatus(
            TelegramConfigurationState.DISCONNECTED,
            token_configured=True,
            private_chat_configured=True,
            delivery_enabled=False,
        ),
    )

    assert _wrapped_status("DISCONNECTED", "negative") in rendered
    assert _status("CONFIGURED · ••••••••", "positive") in rendered
    assert _status("CONFIRMED", "positive") in rendered


def test_colour_remains_text_backed_restrained_and_settings_local() -> None:
    rendered = render_settings(
        _ready(),
        ChartAnalystConnectionStatus.CONNECTED,
        ChartAnalystV2ActivationStatus.ENABLED,
    )
    security = rendered.split(
        '<section class="configuration settings-card settings-security">', 1
    )[1].split("</section>", 1)[0]

    for fact in (
        "LOCAL · READ ONLY",
        "INSIDE THIS PROCESS",
        "ORDER CAPABILITY</span><strong>NONE",
        "LOCAL ONLY",
        "KEYCHAIN / SECURE BOUNDARY",
    ):
        assert fact in security
    assert "settings-status-negative" not in security
    assert '.settings-engineering{--card-accent:#d8a542' in rendered
    assert '.settings-security{--card-accent:#4ca8a9' in rendered
    assert '.settings-calendar{--card-accent:#3b91e8' in rendered
    assert "settings-card settings-status-positive" not in rendered
    assert "settings-card settings-status-negative" not in rendered
    assert 'button class="settings-status' not in rendered
    assert "aria-hidden=\"true\"></span>CONNECTED</strong>" in rendered
    assert "@keyframes" not in rendered
