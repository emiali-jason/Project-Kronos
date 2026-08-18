from pathlib import Path

from tools import kronos_browser


def test_launcher_uses_loopback_server_and_opens_swing_workspace(monkeypatch) -> None:
    events: list[object] = []
    control = object()

    class _Server:
        server_port = 9123
        def serve_forever(self, **kwargs):  # type: ignore[no-untyped-def]
            events.append(("serve", kwargs))
        def server_close(self):
            events.append("close")

    monkeypatch.setattr(
        kronos_browser,
        "SwingOpportunitiesApplication",
        lambda factory, **kwargs: events.append((factory, kwargs)) or object(),
    )
    monkeypatch.setattr(
        kronos_browser.BrowserBackendRestartControl,
        "create",
        lambda: control,
    )
    monkeypatch.setattr(
        kronos_browser,
        "create_browser_server",
        lambda app, port, restart_control, intraday_workstation: (
            events.append((app, port, restart_control, intraday_workstation)) or _Server()
        ),
    )
    monkeypatch.setattr(kronos_browser.webbrowser, "open_new_tab", lambda url: events.append(url) or True)
    assert kronos_browser.main(["--port", "9123"]) == 0
    assert "http://127.0.0.1:9123/swing/opportunities" in events
    assert "close" in events


def test_developer_no_browser_mode_does_not_open_browser(monkeypatch) -> None:
    control = object()
    class _Server:
        server_port = 9123
        def serve_forever(self, **_kwargs): pass  # type: ignore[no-untyped-def]
        def server_close(self): pass
    monkeypatch.setattr(
        kronos_browser,
        "SwingOpportunitiesApplication",
        lambda _factory, **_kwargs: object(),
    )
    monkeypatch.setattr(
        kronos_browser.BrowserBackendRestartControl,
        "create",
        lambda: control,
    )
    monkeypatch.setattr(
        kronos_browser,
        "create_browser_server",
        lambda _app, port, restart_control, intraday_workstation: _Server(),
    )
    monkeypatch.setattr(kronos_browser.webbrowser, "open_new_tab", lambda _url: (_ for _ in ()).throw(AssertionError))
    assert kronos_browser.main(["--no-browser"]) == 0


def test_macos_launcher_is_minimal_double_click_app_without_credentials() -> None:
    root = Path(__file__).resolve().parents[3]
    executable = root / "tools/macos/KRONOS.app/Contents/MacOS/KRONOS"
    launcher_source = root / "tools/macos/kronos_launcher.c"
    plist = root / "tools/macos/KRONOS.app/Contents/Info.plist"
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
    assert "backend_is_ready()" in source
    assert "GET /status HTTP/1.0" in source
    assert "POST /control/shutdown HTTP/1.0" in source
    assert "request_graceful_shutdown" in source
    assert "wait_for_backend_stop" in source
    assert "if (backend_is_ready()) return open_workspace();" not in source
    assert "It was not reused" in source
    assert "http://127.0.0.1:8947/swing/opportunities" in source
    assert '"/usr/bin/open"' in source
    assert '"Google Chrome"' in source
    assert "setsid()" in source
    assert "Terminal" not in source
    assert "api_key" not in source.lower()
    assert "secret" not in source.lower()
    assert "com.project-kronos.browser-v1" in plist.read_text(encoding="utf-8")
