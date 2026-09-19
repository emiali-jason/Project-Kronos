from pathlib import Path
from types import SimpleNamespace
import shutil

from kronos.application.shared_monitoring import SharedSwingMonitoringHub
from tools import kronos_browser
import pytest


@pytest.fixture(autouse=True)
def isolated_composition_authority(monkeypatch):
    # Tests compose fake servers in the kernel-isolated test home; no production bypass.
    monkeypatch.setattr("tools.runtime_source_gate.qualify_startup", lambda *_: "a" * 40)
    monkeypatch.setattr("kronos.browser.runtime_state.complete_startup", lambda *_: None)
    class _IntradayNotifications:
        def __init__(self, **_kwargs):
            pass
        def bind(self, _probables):
            pass
    monkeypatch.setattr(
        "kronos.application.intraday_notifications.IntradayNotifications",
        _IntradayNotifications,
    )


def test_launcher_uses_loopback_server_and_opens_swing_workspace(monkeypatch) -> None:
    events: list[object] = []
    control = object()

    class _Server:
        server_port = 9123
        swing_monitoring_hub = SharedSwingMonitoringHub()
        notification_centre = object()
        telegram = None
        def serve_forever(self, **kwargs):  # type: ignore[no-untyped-def]
            events.append(("serve", kwargs))
        def server_close(self):
            events.append("close")

    server = _Server()

    class _Application:
        def authenticated_read_only_capability(self):
            return None

    monkeypatch.setattr(
        kronos_browser,
        "SwingOpportunitiesApplication",
        lambda factory, **kwargs: events.append((factory, kwargs)) or _Application(),
    )
    monkeypatch.setattr(
        kronos_browser.BrowserBackendRestartControl,
        "create",
        lambda: control,
    )
    monkeypatch.setattr(
        kronos_browser,
        "create_browser_server",
        lambda app, port, restart_control, product_routes,
        provider_instrument_master_operation, intraday_discovery_control,
        intraday_historical_control, provider_login_navigation: (
            events.append((
                app,
                port,
                restart_control,
                product_routes,
                provider_instrument_master_operation,
                intraday_discovery_control,
                intraday_historical_control,
                provider_login_navigation,
            )) or server
        ),
    )
    housekeeping = SimpleNamespace(production_activation=True)
    monkeypatch.setattr(
        kronos_browser,
        "_compose_housekeeping",
        lambda _server, _runtime: housekeeping,
    )
    monkeypatch.setattr(
        kronos_browser.webbrowser,
        "open_new_tab",
        lambda url: events.append(url) or True,
    )
    assert kronos_browser.main(["--port", "9123"]) == 0
    assert "http://127.0.0.1:9123/swing/opportunities" in events
    assert "close" in events
    server_event = next(
        item for item in events if isinstance(item, tuple) and len(item) == 8
    )
    operation = server_event[4]
    intraday_control = server_event[5]
    historical_control = server_event[6]
    application_event = next(
        item
        for item in events
        if isinstance(item, tuple)
        and len(item) == 2
        and callable(item[0])
        and isinstance(item[1], dict)
    )
    swing_factory = application_event[0]
    assert swing_factory.__closure__ is not None
    assert any(
        cell.cell_contents is operation._runtime
        for cell in swing_factory.__closure__
    )
    assert intraday_control.operation_service._runtime is operation._runtime
    assert historical_control.historical_invocation.operation_service is (
        historical_control.operation_service
    )
    assert historical_control.operation_service._runtime is operation._runtime
    assert historical_control.operation_service.last_result is None
    assert historical_control.operation_service.active_operation_identity is None
    assert server.housekeeping is housekeeping
    assert housekeeping.production_activation is True
    provider_factory = (
        server.provider_runtime
        ._SharedAuthenticatedProviderRuntime__provider_factory
    )
    assert provider_factory.__closure__ is not None
    assert "http://127.0.0.1:9123/swing/opportunities" in {
        cell.cell_contents for cell in provider_factory.__closure__
        if isinstance(cell.cell_contents, str)
    }
    source = Path(kronos_browser.__file__).read_text(encoding="utf-8")
    assert source.count("SharedAuthenticatedProviderRuntime(") == 1


def test_developer_no_browser_mode_does_not_open_browser(monkeypatch) -> None:
    control = object()
    class _Server:
        server_port = 9123
        swing_monitoring_hub = SharedSwingMonitoringHub()
        notification_centre = object()
        telegram = None
        def serve_forever(self, **_kwargs): pass  # type: ignore[no-untyped-def]
        def server_close(self): pass

    class _Application:
        def authenticated_read_only_capability(self):
            return None

    monkeypatch.setattr(
        kronos_browser,
        "SwingOpportunitiesApplication",
        lambda _factory, **_kwargs: _Application(),
    )
    monkeypatch.setattr(
        kronos_browser.BrowserBackendRestartControl,
        "create",
        lambda: control,
    )
    monkeypatch.setattr(
        kronos_browser,
        "create_browser_server",
        lambda _app, port, restart_control, product_routes,
        provider_instrument_master_operation, intraday_discovery_control,
        intraday_historical_control, provider_login_navigation: _Server(),
    )
    monkeypatch.setattr(
        kronos_browser,
        "_compose_housekeeping",
        lambda _server, _runtime: SimpleNamespace(production_activation=True),
    )
    monkeypatch.setattr(
        kronos_browser.webbrowser,
        "open_new_tab",
        lambda _url: (_ for _ in ()).throw(AssertionError),
    )
    assert kronos_browser.main(["--no-browser"]) == 0


def test_canonical_housekeeping_composes_enabled_actual_owned_stores(
    tmp_path,
) -> None:
    from kronos.swing.v1.review_evidence_store import ReviewEvidenceStore
    from tests.unit.application.test_intraday_research import _application

    review = ReviewEvidenceStore(tmp_path / "review")
    review.root.mkdir(parents=True)
    (review.root / "receipts").mkdir()
    pending = review.root / "receipts" / ".prepared-canonical"
    pending.write_bytes(b"disposable")
    research, _ = _application(tmp_path / "research")
    publication = research.update(operation_identity="PF10-CANONICAL-HOUSEKEEPING")
    stage = research.store.root / "staging" / __import__(
        "kronos.intraday.wo12_research_contract", fromlist=["digest"]
    ).digest("PF10-CANONICAL-HOUSEKEEPING")
    stage.mkdir(parents=True)
    shutil.copyfile(publication.workbook_path, stage / publication.workbook_path.name)
    server = SimpleNamespace(native_intake=SimpleNamespace(store=review))
    runtime = SimpleNamespace(research_application=research)

    queued = []
    clock = [0.0]
    canonical = kronos_browser._compose_housekeeping(
        server,
        runtime,
        clock=lambda: clock[0],
        background_runner=queued.append,
    )
    status = canonical.status_document()
    assert status["production_activation"] is True
    assert status["lifecycle_state"] == "IDLE"
    assert status["interval_seconds"] == 6 * 60 * 60
    assert canonical.trigger_periodic(now=(6 * 60 * 60) - 1) == "NOT_DUE"
    assert pending.exists() and stage.exists()
    assert canonical.trigger_periodic(now=6 * 60 * 60) == "SCHEDULED"
    assert canonical.trigger_periodic(now=6 * 60 * 60) == "PENDING"
    clock[0] = 6 * 60 * 60
    queued.pop()()
    assert not pending.exists() and not stage.exists()
    assert research.open_current("2026_08")[1] == publication.workbook_path.read_bytes()
    result = canonical.status_document()
    assert result["last_result"]["removed_files"] == 2
    assert result["next_due_monotonic"] == 2 * 6 * 60 * 60


def test_macos_launcher_is_minimal_double_click_app_without_credentials() -> None:
    root = Path(__file__).resolve().parents[3]
    executable = root / "tools/macos/KRONOS.app/Contents/MacOS/KRONOS"
    launcher_source = root / "tools/macos/kronos_launcher.c"
    plist = root / "tools/macos/KRONOS.app/Contents/Info.plist"
    brand_mark = root / "assets/images/brand/kronos-brand-mark.png"
    icon_png = root / "tools/macos/KRONOS.app/Contents/Resources/KRONOS.png"
    icon_icns = root / "tools/macos/KRONOS.app/Contents/Resources/KRONOS.icns"
    source = launcher_source.read_text(encoding="utf-8")
    assert executable.stat().st_mode & 0o111
    assert executable.read_bytes()[:4] in {b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf"}
    assert "discover_repository" in source
    assert "Documents/GitHub" in source
    assert "directory_exists(git_directory)" in source
    assert "matches == 1" in source
    assert ".rc02-publication-worktree" not in source
    assert ".venv/bin/python" in source
    assert "tools/kronos_browser.py" in source
    assert ".ready = backend_is_ready" in source
    assert "GET /status HTTP/1.0" in source
    assert "POST /control/shutdown HTTP/1.0" in source
    assert "request_graceful_shutdown" in source
    assert "wait_for_backend_stop" in source
    assert "if (backend_is_ready()) return open_workspace();" not in source
    assert "It was not reused" not in source
    assert "KRONOS restart blocked" in source
    assert "KRONOS is still starting" in source
    assert "http://127.0.0.1:8947/swing/opportunities" in source
    assert '"/usr/bin/open"' in source
    assert '"Google Chrome"' in source
    assert "setsid()" in source
    assert "Terminal" not in source
    assert "api_key" not in source.lower()
    assert "secret" not in source.lower()
    assert "com.project-kronos.browser-v1" in plist.read_text(encoding="utf-8")
    assert "<string>KRONOS</string>" in plist.read_text(encoding="utf-8")
    assert icon_png.read_bytes() == brand_mark.read_bytes()
    assert icon_icns.read_bytes().startswith(b"icns")
