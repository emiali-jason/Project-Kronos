from threading import Thread
from urllib.parse import urlencode

from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.application.swing_v1_review import SwingV1ReviewWorkflow
from kronos.browser.server import create_browser_server
from kronos.configuration.openai_chart_analyst import (
    ChartAnalystV2ActivationService,
    OPENAI_CHART_ANALYST_CREDENTIAL_REF,
    OpenAIChartAnalystCredentialService,
)
from kronos.swing.v1.evidence_store import LocalTradingViewEvidenceStore
from tests.unit.application.test_swing_opportunities import _Provider, _ready
from tests.unit.browser.test_browser_server import _request


class _ProtectedBackend:
    def __init__(self) -> None:
        self.stored = False
        self.provision_calls = 0
        self.presence_calls = 0
        self.last_reference: str | None = None

    def store_api_key(self, reference: str, value: str) -> None:
        assert len(value) >= 8
        self.provision_calls += 1
        self.last_reference = reference
        self.stored = True

    def api_key_stored(self, reference: str) -> bool:
        self.presence_calls += 1
        self.last_reference = reference
        return self.stored


class _CapabilityTester:
    def __init__(self, connected: bool = True) -> None:
        self.connected = connected
        self.calls = 0

    def test_connection(self) -> bool:
        self.calls += 1
        return self.connected


def _running_server(tmp_path, *, connected: bool = True):  # type: ignore[no-untyped-def]
    backend = _ProtectedBackend()
    tester = _CapabilityTester(connected)
    credentials = OpenAIChartAnalystCredentialService(
        provisioner=backend,
        presence_probe=backend,
        capability_tester=tester,
    )
    review = SwingV1ReviewWorkflow(LocalTradingViewEvidenceStore(tmp_path))
    application = SwingOpportunitiesApplication(_Provider, initial_snapshot=_ready())
    server = create_browser_server(
        application,
        port=0,
        v1_review=review,
        chart_analyst_credentials=credentials,
        chart_analyst_activation=ChartAnalystV2ActivationService(
            tmp_path / "chart-analyst-v2-activation.json"
        ),
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, backend, tester, review


def _origin_headers(server, **extra: str) -> dict[str, str]:  # type: ignore[no-untyped-def]
    authority = f"127.0.0.1:{server.server_port}"
    return {
        "Host": authority,
        "Origin": f"http://{authority}",
        **extra,
    }


def test_settings_renders_masked_write_only_credential_field(tmp_path) -> None:  # type: ignore[no-untyped-def]
    server, thread, _, _, _ = _running_server(tmp_path)
    try:
        status, headers, body = _request(server, "GET", "/settings")

        assert status == 200
        assert headers["Cache-Control"] == "no-store"
        assert 'type="password"' in body
        assert 'name="api_key"' in body
        assert 'autocomplete="off"' in body
        assert 'value=' not in body
        assert ">NOT CONFIGURED<" in body
        assert ">CONNECTED<" not in body
        assert ">CONNECTION FAILED<" not in body
        assert "OPENAI_API_KEY" not in body
        assert OPENAI_CHART_ANALYST_CREDENTIAL_REF not in body
        assert "Credential" in body
        assert "Chart Analyst V2" in body
        assert ">DISABLED<" in body
        assert "Enable Chart Analyst V2" in body
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_browser_enable_disable_control_is_persistent_and_non_secret(tmp_path) -> None:  # type: ignore[no-untyped-def]
    server, thread, _, _, _ = _running_server(tmp_path)
    try:
        status, headers, body = _request(
            server,
            "POST",
            "/settings/chart-analyst/enable",
            headers=_origin_headers(server),
        )
        assert status == 303
        assert headers["Location"] == "/settings"
        assert body == ""
        enabled = _request(server, "GET", "/settings")[2]
        assert ">ENABLED<" in enabled
        assert "Disable Chart Analyst V2" in enabled
        assert "KRONOS_CHART_ANALYST_ENABLED" not in enabled
        assert 'value=' not in enabled

        status, _, _ = _request(
            server,
            "POST",
            "/settings/chart-analyst/disable",
            headers=_origin_headers(server),
        )
        assert status == 303
        assert ">DISABLED<" in _request(server, "GET", "/settings")[2]
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_credential_submission_returns_no_key_and_never_rehydrates_field(
    tmp_path,
    capsys,
) -> None:  # type: ignore[no-untyped-def]
    server, thread, backend, _, _ = _running_server(tmp_path)
    api_key = "fake-browser-openai-key"
    body = urlencode({"api_key": api_key})
    try:
        status, headers, response_body = _request(
            server,
            "POST",
            "/settings/chart-analyst/credential",
            headers=_origin_headers(
                server,
                **{"Content-Type": "application/x-www-form-urlencoded"},
            ),
            body=body,
        )

        assert status == 303
        assert headers["Location"] == "/settings"
        assert response_body == ""
        assert backend.provision_calls == 1
        assert backend.last_reference == OPENAI_CHART_ANALYST_CREDENTIAL_REF

        _, _, rendered = _request(server, "GET", "/settings")
        assert ">CONNECTED<" in rendered
        assert api_key not in rendered
        assert 'value=' not in rendered
        captured = capsys.readouterr()
        assert api_key not in captured.out
        assert api_key not in captured.err
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_connection_action_calls_only_capability_probe_and_not_swing(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    server, thread, backend, tester, review = _running_server(tmp_path)
    backend.stored = True
    before = review.snapshot()
    try:
        status, headers, response_body = _request(
            server,
            "POST",
            "/settings/chart-analyst/test",
            headers=_origin_headers(server),
        )

        assert status == 303
        assert headers["Location"] == "/settings"
        assert response_body == ""
        assert tester.calls == 1
        assert backend.provision_calls == 0
        assert review.snapshot() == before
        assert _request(server, "GET", "/settings")[2].count(">CONNECTED<") == 1
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_failed_connection_exposes_only_connection_failed(tmp_path) -> None:  # type: ignore[no-untyped-def]
    server, thread, backend, tester, _ = _running_server(
        tmp_path,
        connected=False,
    )
    backend.stored = True
    try:
        _request(
            server,
            "POST",
            "/settings/chart-analyst/test",
            headers=_origin_headers(server),
        )
        rendered = _request(server, "GET", "/settings")[2]

        assert tester.calls == 1
        assert ">CONNECTION FAILED<" in rendered
        assert ">NOT CONFIGURED<" not in rendered
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_cross_origin_or_malformed_credential_submission_is_rejected(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    server, thread, backend, _, _ = _running_server(tmp_path)
    api_key = "fake-browser-openai-key"
    body = urlencode({"api_key": api_key})
    try:
        status, _, response = _request(
            server,
            "POST",
            "/settings/chart-analyst/credential",
            headers={
                "Host": f"127.0.0.1:{server.server_port}",
                "Origin": "http://evil.example",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            body=body,
        )
        assert status == 403
        assert api_key not in response

        status, _, response = _request(
            server,
            "POST",
            "/settings/chart-analyst/credential",
            headers=_origin_headers(server, **{"Content-Type": "text/plain"}),
            body=api_key,
        )
        assert status == 400
        assert response == "Request rejected."
        assert api_key not in response
        assert backend.provision_calls == 0
    finally:
        server.shutdown(); server.server_close(); thread.join()
