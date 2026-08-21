from pathlib import Path
from threading import Thread

from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.application.swing_v1_review import SwingV1ReviewWorkflow
from kronos.browser.server import create_browser_server
from kronos.browser.views import render_legacy_opportunities, render_settings
from kronos.configuration.openai_chart_analyst import (
    ChartAnalystConnectionStatus,
    ChartAnalystV2ActivationStatus,
)
from kronos.swing.v1 import LocalTradingViewEvidenceStore

from tests.unit.application.test_swing_opportunities import _Provider
from tests.unit.browser.test_browser_server import _request
from tests.unit.browser.test_browser_views import _ready


def _swing_tabs(rendered: str) -> str:
    return rendered.split('<nav class="tabs">', 1)[1].split("</nav>", 1)[0]


def test_primary_swing_tabs_contain_only_sponsor_workflow() -> None:
    rendered = render_legacy_opportunities(_ready())
    tabs = _swing_tabs(rendered)

    for label in ("Opportunities", "Review", "Trade Candidates", "Active", "Closed"):
        assert label in tabs
    for label in ("Layer-1 History", "Control vs Native", "MTF Data"):
        assert label not in tabs


def test_settings_exposes_read_only_swing_engineering_diagnostics() -> None:
    rendered = render_settings(
        _ready(),
        ChartAnalystConnectionStatus.NOT_CONFIGURED,
        ChartAnalystV2ActivationStatus.DISABLED,
    )

    assert "Engineering &amp; Diagnostics" in rendered
    assert "READ ONLY" in rendered
    assert "Read-only technical and historical evidence for KRONOS diagnostics." in rendered
    for label, route in (
        ("LAYER-1 HISTORY", "/swing/layer1-history"),
        ("CONTROL VS NATIVE", "/swing/native-discovery"),
        ("MTF DATA", "/swing/mtf-diagnostics"),
    ):
        assert label in rendered
        assert f'href="{route}"' in rendered
    assert rendered.count("<small>SWING</small>") == 3


def test_diagnostic_deep_links_remain_read_only_and_resolve(tmp_path: Path) -> None:
    application = SwingOpportunitiesApplication(_Provider, initial_snapshot=_ready())
    review = SwingV1ReviewWorkflow(LocalTradingViewEvidenceStore(tmp_path))
    server = create_browser_server(application, port=0, v1_review=review)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for route, marker in (
            ("/swing/layer1-history", "Historical Swing V1 Layer-1 validation evidence"),
            ("/swing/native-discovery", "Control vs KRONOS Native MTF"),
            ("/swing/mtf-diagnostics", "Current governed MTF facts are not available"),
        ):
            status, _, body = _request(server, "GET", route)
            assert status == 200
            assert marker in body
            assert 'method="post" action="/swing/analysis"' not in body
            assert "Engineering &amp; Diagnostics" not in _swing_tabs(body)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
