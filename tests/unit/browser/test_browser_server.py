from http.client import HTTPConnection
from threading import Thread
import json

import pytest

from kronos.application.swing_opportunities import (
    MarketPanel,
    SwingOpportunitiesApplication,
    V1ProbableSnapshot,
)
from kronos.application.swing_v1_review import SwingV1ReviewWorkflow
from kronos.browser.server import KronosBrowserServer, create_browser_server
from kronos.browser.restart_control import BrowserBackendRestartControl
from kronos.swing.v1 import (
    LocalTradingViewEvidenceStore,
    V1Direction,
    V1Setup,
)
from tests.unit.application.test_swing_opportunities import (
    _Provider,
    _eligible,
    _opportunity,
    _ready,
)


def _running_server(snapshot=None, *, v1_review=None):  # type: ignore[no-untyped-def]
    app = SwingOpportunitiesApplication(_Provider, initial_snapshot=snapshot)
    server = create_browser_server(app, port=0, v1_review=v1_review)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _active_v1(snapshot, instrument: str = "NAUKRI"):  # type: ignore[no-untyped-def]
    from dataclasses import replace

    return replace(
        snapshot,
        v1_probables=(V1ProbableSnapshot(
            instrument=instrument,
            panel=MarketPanel.EQUITIES_INDICES,
            setups=(V1Setup.PULLBACK_CONTINUATION,),
            directions=(V1Direction.LONG,),
        ),),
    )


def _request(server, method: str, path: str, *, headers=None, body=None):  # type: ignore[no-untyped-def]
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=3)
    connection.request(method, path, body=body, headers=headers or {})
    response = connection.getresponse()
    body = response.read().decode("utf-8")
    connection.close()
    return response.status, dict(response.headers), body


def _request_bytes(server, method: str, path: str):  # type: ignore[no-untyped-def]
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=3)
    connection.request(method, path)
    response = connection.getresponse()
    body = response.read()
    connection.close()
    return response.status, dict(response.headers), body


def test_v1_review_route_and_chart_intake_use_selected_slot_binding(tmp_path) -> None:
    from tests.unit.swing.v1.test_swing_v1_slice3 import _classified_run

    review = SwingV1ReviewWorkflow(LocalTradingViewEvidenceStore(tmp_path))
    review.publish_layer1(_classified_run({
        ("NAUKRI", V1Setup.PULLBACK_CONTINUATION),
        ("NAUKRI", V1Setup.CONSOLIDATION_BREAKOUT),
    }))
    server, thread = _running_server(_ready(), v1_review=review)
    try:
        status, _, rendered = _request(server, "GET", "/swing/v1-review")
        assert status == 200
        assert rendered.count("<h2>NAUKRI</h2>") == 1
        assert "Click, then paste" in rendered
        assert "Choose File" in rendered
        authority = f"127.0.0.1:{server.server_port}"
        headers = {
            "Host": authority,
            "Origin": f"http://{authority}",
            "Content-Type": "image/png",
        }
        status, response_headers, _ = _request(
            server,
            "POST",
            "/swing/v1/chart?instrument=NAUKRI&timeframe=DAILY",
            headers=headers,
            body=b"\x89PNG\r\n\x1a\nserver-upload",
        )
        assert status == 303
        assert response_headers["Location"] == "/swing/v1-review"
        assert review.snapshot().packages[0].context_status.value == "TRADINGVIEW_CONTEXT_RECEIVED"
        revision = review.snapshot().packages[0].active_revisions[0]
        preview = (
            "/swing/v1/chart-preview?instrument=NAUKRI&timeframe=DAILY"
            f"&sha256={revision.sha256}"
        )
        status, preview_headers, preview_body = _request_bytes(server, "GET", preview)
        assert status == 200
        assert preview_headers["Content-Type"] == "image/png"
        assert preview_body == b"\x89PNG\r\n\x1a\nserver-upload"
        assert _request_bytes(
            server,
            "GET",
            preview.replace("instrument=NAUKRI", "instrument=TITAN"),
        )[0] == 404
        status, response_headers, _ = _request(
            server,
            "POST",
            "/swing/v1/chart/remove?instrument=NAUKRI&timeframe=DAILY",
            headers={"Host": authority, "Origin": f"http://{authority}"},
        )
        assert status == 303
        assert response_headers["Location"] == "/swing/v1-review"
        package = review.snapshot().packages[0]
        assert package.active_revisions == ()
        assert len(package.revisions) == 1
        assert _request_bytes(server, "GET", preview)[0] == 404
        assert _request(
            server,
            "POST",
            "/swing/v1/chart?instrument=TITAN&timeframe=DAILY",
            headers=headers,
            body=b"\x89PNG\r\n\x1a\nwrong-binding",
        )[0] == 400
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_server_rejects_non_loopback_binding() -> None:
    app = SwingOpportunitiesApplication(_Provider)
    with pytest.raises(ValueError, match="BROWSER_SERVER_MUST_BIND_LOOPBACK"):
        KronosBrowserServer(("0.0.0.0", 0), app)


def test_root_redirects_and_opportunities_route_renders() -> None:
    server, thread = _running_server(_active_v1(_ready(_opportunity())))
    try:
        status, headers, _ = _request(server, "GET", "/")
        assert status == 303
        assert headers["Location"] == "/swing/opportunities"
        status, headers, body = _request(server, "GET", "/swing/opportunities")
        assert status == 200
        assert "NAUKRI" in body
        assert "HDFCBANK" not in body
        assert headers["Cache-Control"] == "no-store"
        assert headers["Referrer-Policy"] == "same-origin"
        assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_workspace_and_placeholder_routes() -> None:
    server, thread = _running_server(_ready(_opportunity()))
    try:
        status, _, body = _request(server, "GET", "/swing/opportunities/1")
        assert status == 404
        assert "V0 workspaces are reference-only" in body
        assert _request(server, "GET", "/swing/opportunities/2")[0] == 404
        status, _, body = _request(server, "GET", "/swing/active")
        assert status == 200 and "not implemented" in body
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_v0_eligible_workspace_is_outside_active_sponsor_workflow() -> None:
    from dataclasses import replace

    first = _opportunity(1)
    second = replace(_opportunity(2), instrument="MARUTI")
    third = replace(_opportunity(1), position=3, instrument="POWERINDIA")
    snapshot = replace(
        _ready(first, second),
        attention_eligible_count=3,
        eligible_plans=(
            _eligible(first),
            _eligible(second),
            _eligible(third, selected=False),
        ),
    )
    server, thread = _running_server(snapshot)
    try:
        status, _, body = _request(server, "GET", "/swing/eligible/3")
        assert status == 404
        assert "V0 workspaces are reference-only" in body
        assert _request(server, "GET", "/swing/eligible/4")[0] == 404
        assert server.application.snapshot().opportunities == (first, second)
        assert server.application.snapshot().analysis_state is snapshot.analysis_state
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_status_endpoint_is_small_and_sanitized() -> None:
    server, thread = _running_server(_ready(_opportunity()))
    try:
        status, _, body = _request(server, "GET", "/status")
        assert status == 200
        assert set(__import__("json").loads(body)) == {
            "service", "provider", "analysis", "completed_at", "v1_probables",
            "analysis_diagnostic",
        }
        assert __import__("json").loads(body)["service"] == "KRONOS_BROWSER_V1"
        assert "HDFCBANK" not in body
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_private_restart_control_gracefully_stops_exact_server(tmp_path) -> None:
    token = "a" * 64
    control = BrowserBackendRestartControl.create(
        tmp_path / "browser.control",
        process_id=4242,
        token=token,
    )
    app = SwingOpportunitiesApplication(_Provider)
    server = create_browser_server(app, port=0, restart_control=control)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    authority = f"127.0.0.1:{server.server_port}"
    try:
        status, _, body = _request(
            server,
            "POST",
            "/control/shutdown",
            headers={
                "Host": authority,
                "X-Kronos-Backend-Pid": "4242",
                "X-Kronos-Restart-Token": token,
                "Content-Length": "0",
            },
        )
        assert status == 202
        assert body == '{"status":"STOPPING"}'
        assert token not in body
        thread.join(timeout=3)
        assert not thread.is_alive()
    finally:
        if thread.is_alive():
            server.shutdown(); thread.join()
        server.server_close()
    assert not control.path.exists()


def test_restart_control_rejects_wrong_process_or_token(tmp_path) -> None:
    control = BrowserBackendRestartControl.create(
        tmp_path / "browser.control",
        process_id=4242,
        token="a" * 64,
    )
    app = SwingOpportunitiesApplication(_Provider)
    server = create_browser_server(app, port=0, restart_control=control)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    authority = f"127.0.0.1:{server.server_port}"
    try:
        for pid, token in (("4243", "a" * 64), ("4242", "b" * 64)):
            status, _, body = _request(
                server,
                "POST",
                "/control/shutdown",
                headers={
                    "Host": authority,
                    "X-Kronos-Backend-Pid": pid,
                    "X-Kronos-Restart-Token": token,
                    "Content-Length": "0",
                },
            )
            assert status == 403
            assert body == "Request rejected."
            assert thread.is_alive()
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_status_exposes_only_bounded_sanitized_analysis_diagnostic(
    monkeypatch,
) -> None:
    application = SwingOpportunitiesApplication(
        _Provider,
        background_runner=lambda operation, _name: operation(),
    )
    assert application.connect_provider()
    monkeypatch.setattr(
        "kronos.application.swing_opportunities.build_completed_swing_analysis",
        lambda *_a, **_k: (_ for _ in ()).throw(
            RuntimeError("access_token=forbidden")
        ),
    )
    assert application.run_analysis()
    server = create_browser_server(application, port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, body = _request(server, "GET", "/status")
        payload = json.loads(body)
        diagnostic = payload["analysis_diagnostic"]
        assert status == 200
        assert diagnostic["failing_stage"] == "PROVIDER_CAPABILITY"
        assert diagnostic["exception_class"] == "RuntimeError"
        assert diagnostic["sanitized_summary"] == "SANITIZED_FAILURE"
        assert "forbidden" not in body.lower()
        assert "access_token" not in body.lower()
    finally:
        server.shutdown(); server.server_close(); thread.join()


@pytest.mark.parametrize(
    "path",
    ("/provider/connect", "/provider/disconnect", "/swing/analysis"),
)
def test_post_accepts_exact_running_loopback_origin(path: str) -> None:
    server, thread = _running_server()
    try:
        authority = f"127.0.0.1:{server.server_port}"
        status, headers, _ = _request(
            server,
            "POST",
            path,
            headers={"Host": authority, "Origin": f"http://{authority}"},
        )
        assert status == 303
        assert headers["Location"] == "/swing/opportunities"
    finally:
        server.shutdown(); server.server_close(); thread.join()


@pytest.mark.parametrize(
    ("host", "origin"),
    (
        ("127.0.0.1:{port}", None),
        ("127.0.0.1:{port}", "null"),
        ("127.0.0.1:{port}", "not-an-origin"),
        ("127.0.0.1:{port}", "http://127.0.0.1:1"),
        ("evil.example:{port}", "http://evil.example:{port}"),
        ("192.168.1.25:{port}", "http://192.168.1.25:{port}"),
        ("127.0.0.1:{port}", "http://localhost:{port}"),
        ("127.0.0.1:{port}", "https://127.0.0.1:{port}"),
    ),
)
@pytest.mark.parametrize(
    "path",
    (
        "/provider/connect",
        "/provider/disconnect",
        "/swing/analysis",
        "/swing/v1/chart",
        "/swing/v1/chart/remove",
        "/swing/v1/analyze",
    ),
)
def test_post_rejects_every_non_current_origin(
    host: str,
    origin: str | None,
    path: str,
) -> None:
    server, thread = _running_server()
    try:
        port = server.server_port
        headers = {"Host": host.format(port=port)}
        if origin is not None:
            headers["Origin"] = origin.format(port=port)
        status, _, _ = _request(
            server,
            "POST",
            path,
            headers=headers,
        )
        assert status == 403
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_no_order_or_generic_provider_endpoint_exists() -> None:
    server, thread = _running_server()
    try:
        for path in ("/orders", "/provider", "/provider/raw", "/api/analysis"):
            assert _request(server, "GET", path)[0] == 404
    finally:
        server.shutdown(); server.server_close(); thread.join()
