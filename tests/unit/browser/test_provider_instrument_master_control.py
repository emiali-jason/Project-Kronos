"""Browser control proof for the governed P1 operational composition."""

from __future__ import annotations

from http.client import HTTPConnection
import json
from pathlib import Path
from threading import Thread
from urllib.parse import urlencode

from kronos.application.provider_instrument_master_operation import (
    ProviderInstrumentMasterOperationalComposition,
)
from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.application.swing_v1_review import SwingV1ReviewWorkflow
from kronos.browser.server import create_browser_server
from kronos.intraday.universe import load_intraday_universe_publication
from kronos.provider.contracts.instrument_master import (
    ProviderInstrumentDiagnosticPhase,
    ProviderInstrumentFieldFamily,
    ProviderInstrumentValidationRule,
    ProviderInstrumentValueClassification,
    provider_instrument_schema_error,
)
from kronos.provider.instrument_master_persistence import ProviderInstrumentSnapshotStore
from kronos.swing.v1 import LocalTradingViewEvidenceStore
from tests.unit.application.test_provider_instrument_master_operation import (
    NOW,
    RUN_1,
    _Runtime,
    _complete_records,
)
from tests.unit.application.test_swing_opportunities import _Provider, _ready


def _composition(tmp_path: Path, runtime: _Runtime):  # type: ignore[no-untyped-def]
    return ProviderInstrumentMasterOperationalComposition(
        runtime,
        store=ProviderInstrumentSnapshotStore(tmp_path.resolve()),
        universe=load_intraday_universe_publication(),
        clock=lambda: NOW,
    )


def _server(tmp_path: Path, runtime: _Runtime):  # type: ignore[no-untyped-def]
    operation = _composition(tmp_path, runtime)
    app = SwingOpportunitiesApplication(_Provider, initial_snapshot=_ready())
    server = create_browser_server(
        app,
        port=0,
        v1_review=SwingV1ReviewWorkflow(
            LocalTradingViewEvidenceStore((tmp_path / "swing").resolve())
        ),
        provider_instrument_master_operation=operation,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _request(
    server: object,
    method: str,
    path: str,
    *,
    origin: str | None = None,
    fields: dict[str, str] | None = None,
):  # type: ignore[no-untyped-def]
    port = server.server_port  # type: ignore[attr-defined]
    authority = f"127.0.0.1:{port}"
    headers = {"Host": authority}
    body: str | None = None
    if origin is not None:
        headers["Origin"] = origin
    if fields is not None:
        body = urlencode(fields)
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    encoded = response.read().decode("utf-8")
    connection.close()
    return response.status, encoded


def test_status_uses_actual_runtime_not_restored_connected_presentation(
    tmp_path: Path,
) -> None:
    runtime = _Runtime(_complete_records(), lifecycle="ABSENT")
    server, thread = _server(tmp_path, runtime)
    try:
        status, encoded = _request(
            server,
            "GET",
            "/control/provider-instrument-master/status",
        )
        payload = json.loads(encoded)
        assert status == 200
        assert payload == {"context_availability": "CONTEXT_UNAVAILABLE"}
        assert server.application.snapshot().provider_state.value == "CONNECTED"
        assert runtime.calls == []
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()


def test_same_origin_post_runs_once_and_get_only_replays_sanitized_result(
    tmp_path: Path,
) -> None:
    runtime = _Runtime(_complete_records())
    server, thread = _server(tmp_path, runtime)
    authority = f"127.0.0.1:{server.server_port}"
    try:
        status, first = _request(
            server,
            "POST",
            "/control/provider-instrument-master",
            origin=f"http://{authority}",
            fields={"operation_identity": RUN_1},
        )
        status_repeat, repeated = _request(
            server,
            "POST",
            "/control/provider-instrument-master",
            origin=f"http://{authority}",
            fields={"operation_identity": RUN_1},
        )
        status_get, projected = _request(
            server,
            "GET",
            "/control/provider-instrument-master/status"
            f"?operation_identity={RUN_1}",
        )
        payload = json.loads(first)
        assert (status, status_repeat, status_get) == (200, 200, 200)
        assert repeated == first == projected
        assert payload["state"] == "COMPLETE"
        assert payload["commissioning_member_count"] == 98
        assert runtime.calls == ["KITE-CONSOLIDATED-INSTRUMENT-MASTER-V1"]
        assert "provider_instrument_token" not in first
        assert "access_token" not in first
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()


def test_browser_replays_only_sanitized_schema_diagnostic(
    tmp_path: Path,
) -> None:
    forbidden = (
        "access_token=SENSITIVE_ACCESS api_secret=SENSITIVE_SECRET "
        "request_token=SENSITIVE_REQUEST Authorization: Bearer SENSITIVE_BEARER "
        "provider_token=738561 provider_symbol=RELIANCE raw exception detail"
    )
    failure = provider_instrument_schema_error(
        phase=ProviderInstrumentDiagnosticPhase.PROVIDER_NORMALIZATION,
        rule=ProviderInstrumentValidationRule.SYMBOL_REQUIRED,
        field_family=ProviderInstrumentFieldFamily.SYMBOL,
        value_classification=ProviderInstrumentValueClassification.MISSING,
        input_ordinal=5,
    )
    failure.__cause__ = RuntimeError(forbidden)
    runtime = _Runtime(_complete_records(), failure=failure)
    server, thread = _server(tmp_path, runtime)
    authority = f"127.0.0.1:{server.server_port}"
    try:
        post_status, first = _request(
            server,
            "POST",
            "/control/provider-instrument-master",
            origin=f"http://{authority}",
            fields={"operation_identity": RUN_1},
        )
        get_status, repeated = _request(
            server,
            "GET",
            "/control/provider-instrument-master/status"
            f"?operation_identity={RUN_1}",
        )
        payload = json.loads(first)

        assert (post_status, get_status) == (200, 200)
        assert repeated == first
        assert runtime.calls == ["KITE-CONSOLIDATED-INSTRUMENT-MASTER-V1"]
        assert payload["state"] == "FAILED"
        assert payload["stage"] == "INSTRUMENT_MASTER_ACQUISITION"
        assert payload["failure"] == "SNAPSHOT_SCHEMA_INVALID"
        assert payload["diagnostic_phase"] == "PROVIDER_NORMALIZATION"
        assert payload["validation_rule"] == "SYMBOL_REQUIRED"
        assert payload["field_family"] == "SYMBOL"
        assert payload["value_classification"] == "MISSING"
        assert payload["input_ordinal"] == 5
        assert payload["affected_count"] == 1
        for prohibited in (
            "SENSITIVE_ACCESS",
            "SENSITIVE_SECRET",
            "SENSITIVE_REQUEST",
            "SENSITIVE_BEARER",
            "738561",
            "RELIANCE",
            "raw exception detail",
            "traceback",
        ):
            assert prohibited.lower() not in first.lower()
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()


def test_foreign_or_malformed_invocation_is_rejected_without_acquisition(
    tmp_path: Path,
) -> None:
    runtime = _Runtime(_complete_records())
    server, thread = _server(tmp_path, runtime)
    authority = f"127.0.0.1:{server.server_port}"
    try:
        foreign, _ = _request(
            server,
            "POST",
            "/control/provider-instrument-master",
            origin="http://evil.example",
            fields={"operation_identity": RUN_1},
        )
        malformed, _ = _request(
            server,
            "POST",
            "/control/provider-instrument-master",
            origin=f"http://{authority}",
            fields={"operation_identity": "INVALID"},
        )
        unknown, _ = _request(
            server,
            "GET",
            "/control/provider-instrument-master/status"
            f"?operation_identity={RUN_1}",
        )
        malformed_status, _ = _request(
            server,
            "GET",
            "/control/provider-instrument-master/status?operation_identity=",
        )
        assert (foreign, malformed, unknown, malformed_status) == (403, 400, 404, 400)
        assert runtime.calls == []
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()
