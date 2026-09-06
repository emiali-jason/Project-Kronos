"""ENG-05: execute the rendered shared-shell poll, never live Provider calls."""

from html.parser import HTMLParser
import json
import re
import shutil
import subprocess
from threading import Thread
from unittest.mock import Mock

import pytest

from kronos.application.swing_opportunities import (
    AnalysisState,
    BrowserWorkspaceSnapshot,
    ProviderConnectionState,
    SwingOpportunitiesApplication,
)
from kronos.browser.intraday_routes import IntradayBrowserRoutes
from kronos.browser.product_routes import ProductBrowserRoutes
from kronos.browser.server import create_browser_server
from kronos.browser.views import (
    render_browser_page,
    render_legacy_opportunities,
    render_opportunities,
)
from tests.unit.application.test_intraday_discovery import _application
from tests.unit.application.test_swing_opportunities import _Provider
from tests.unit.browser.test_browser_server import _request


class _BodyAttributes(HTMLParser):
    def handle_starttag(self, tag, attrs):
        if tag == "body":
            self.attributes = dict(attrs)


def _page(shell):
    snapshot = BrowserWorkspaceSnapshot(
        ProviderConnectionState.CONNECTING, AnalysisState.NOT_RUN, 98
    )
    if shell == "swing":
        return render_opportunities(snapshot, projection_revision="REVISION-1")
    if shell == "history":
        return render_legacy_opportunities(snapshot)
    return render_browser_page(
        title="Intraday", subtitle="Shared-shell compatibility",
        snapshot=snapshot, active_nav="Intraday", active_tab="", body="",
    )


_JAVASCRIPT_HARNESS = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const input = JSON.parse(process.argv[1]);
const requests = [], intervals = [];
let reloads = 0, parses = 0, next = 0;
const context = {
  document: {body: {dataset: input.dataset}},
  location: {reload: () => {reloads++;}},
  setInterval: (callback, delay) => {intervals.push({callback, delay}); return 1;},
  // Supply only a mock fetch. The script has no real network/Provider interface.
  fetch: async (url, options) => {
    requests.push({url, options});
    const response = input.responses[next++];
    if (response.mode === 'network') throw new Error('NETWORK_UNAVAILABLE');
    return {
      ok: response.mode !== 'http',
      json: async () => {
        parses++;
        if (response.mode === 'malformed') throw new SyntaxError('INVALID_JSON');
        return response.payload;
      }
    };
  }
};
vm.runInNewContext(input.script, context);
assert.equal(requests.length, 0); // Merely rendering does not initiate a request.
assert.equal(intervals.length, 1);
assert.equal(intervals[0].delay, 1500);
(async () => {
  for (let i = 0; i < input.responses.length; i++) {
    await intervals[0].callback();
    assert.equal(reloads, input.expectedReloads[i]);
  }
  assert.equal(parses, input.expectedParses);
  assert.equal(requests.length, input.responses.length);
  for (const request of requests) {
    assert.equal(request.url, '/status');
    assert.equal(request.options.cache, 'no-store');
    assert.equal(request.options.method, undefined); // Default GET, never POST.
    assert.equal(request.options.body, undefined);
    assert.equal(Object.keys(request.options).join(','), 'cache');
  }
  process.stdout.write(JSON.stringify({reloads, parses, requests: requests.length}));
})().catch(error => {console.error(error); process.exitCode = 1;});
"""


@pytest.mark.parametrize("shell", ["swing", "intraday", "history"])
@pytest.mark.parametrize("case", [
    "connected", "error", "unchanged", "analysis", "completed", "revision",
    "malformed", "http", "network", "malformed_then_success",
    "http_then_success", "network_then_success", "mixed_failures_then_success",
])
def test_rendered_polling_javascript(shell, case):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js required for isolated JavaScript unit tests")
    page = _page(shell)
    parsed = _BodyAttributes()
    parsed.feed(page)
    dataset = {"statusSignature": parsed.attributes["data-status-signature"]}
    revision = parsed.attributes.get("data-swing-projection-revision")
    if revision is not None:
        dataset["swingProjectionRevision"] = revision
    scripts = [
        script for script in re.findall(r"<script>(.*?)</script>", page, re.S)
        if "document.body.dataset.statusSignature" in script
    ]
    assert len(scripts) == 1
    payload = {
        "provider": "CONNECTING", "analysis": "NOT RUN", "completed_at": None,
        "swing_projection_revision": "REVISION-1",
    }
    changes = {
        "connected": ("provider", "CONNECTED"),
        "error": ("provider", "ERROR"),
        "analysis": ("analysis", "RUNNING"),
        "completed": ("completed_at", "2026-09-06T10:00:00+00:00"),
        "revision": ("swing_projection_revision", "REVISION-2"),
    }
    if case in changes:
        key, value = changes[case]
        payload[key] = value
    modes = ["success"]
    expected = [int(case in changes and (case != "revision" or revision is not None))]
    if case in {"malformed", "http", "network"}:
        modes, expected = [case], [0]
    elif case.endswith("_then_success"):
        failures = (
            ["malformed", "network", "http"]
            if case == "mixed_failures_then_success"
            else [case.removesuffix("_then_success")]
        )
        modes = failures + ["success"]
        expected = [0] * len(failures) + [1]
        payload["provider"] = "CONNECTED"
    responses = [{"mode": mode, "payload": payload} for mode in modes]
    result = subprocess.run(
        [node, "-e", _JAVASCRIPT_HARNESS, json.dumps({
            "script": scripts[0], "dataset": dataset, "responses": responses,
            "expectedReloads": expected,
            "expectedParses": sum(mode in {"success", "malformed"} for mode in modes),
        })],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["reloads"] == expected[-1]


@pytest.mark.parametrize("outcome", ["CONNECTED", "ERROR"])
def test_fresh_navigation_renders_authoritative_connection_and_controls(tmp_path, outcome):
    queue = []
    provider = _Provider()
    provider.begin_login = Mock(wraps=provider.begin_login)
    if outcome == "ERROR":
        provider.complete_callback = Mock(side_effect=RuntimeError("AUTH_FAILED"))
    app = SwingOpportunitiesApplication(
        lambda: provider, background_runner=lambda operation, name: queue.append(operation)
    )
    app.run_analysis = Mock(side_effect=AssertionError("ANALYSIS_MUST_NOT_RUN"))
    intraday, *_ = _application(tmp_path / "intraday")
    server = create_browser_server(
        app, port=0,
        product_routes=ProductBrowserRoutes((IntradayBrowserRoutes(intraday),)),
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        def get(path):
            status, _, body = _request(server, "GET", path)
            assert status == 200
            return body

        initial = get("/swing/opportunities")
        assert "Kite: DISCONNECTED" in initial
        assert 'class="primary">Connect</button>' in initial
        status, headers, _ = _request(
            server, "POST", "/provider/connect",
            headers={"Origin": f"http://127.0.0.1:{server.server_port}"},
        )
        assert status == 303 and headers["Location"] == "/swing/opportunities"
        connecting = get("/swing/opportunities")
        assert "Kite: CONNECTING" in connecting
        assert 'class="primary" disabled>Connect</button>' in connecting
        assert json.loads(get("/status"))["provider"] == "CONNECTING"
        queue.pop()()
        snapshot = app.snapshot()
        assert snapshot.provider_state.value == outcome
        assert json.loads(get("/status"))["provider"] == outcome
        for path in ("/intraday", "/swing/opportunities"):
            page = get(path)
            assert f"Kite: {outcome}" in page
            assert 'class="primary" disabled>Connect</button>' not in page
            if outcome == "CONNECTED":
                assert '<button>Disconnect</button>' in page
            else:
                assert 'class="primary">Connect</button>' in page
            assert app.snapshot() is snapshot
        assert provider.begin_login.call_count == 1
        app.run_analysis.assert_not_called()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
