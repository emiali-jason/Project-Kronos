from dataclasses import replace
from pathlib import Path
from threading import Thread
from urllib.parse import urlencode

import pytest

from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.application.swing_v1_review import SwingV1ReviewWorkflow
from kronos.browser.server import create_browser_server
from kronos.swing.v1.evidence_store import LocalTradingViewEvidenceStore
from kronos.swing.v1.native_trade_construction import (
    create_trade_construction_evidence_package,
)
from tests.unit.application.test_swing_opportunities import _Provider, _immediate, _ready
from tests.unit.browser.test_browser_server import _request
from tests.unit.browser.test_swing_visual_v3_live import (
    _answer_pdf,
    _live,
    _payload,
)
from tests.unit.swing.v1.test_kr370_step31_handoff import (
    _completed,
    _context,
    _evidence,
    _price,
)
from tests.unit.swing.v1.test_native_review import _evidence_run


def _server(tmp_path: Path, *, connected: bool = False):  # type: ignore[no-untyped-def]
    native, facts, live = _live(tmp_path)
    record = live.generate(native.snapshot(), facts, native.original_chart_bytes)
    answer = live.transport.configuration.answer_directory / record.expected_answer_filename
    _answer_pdf(answer, _payload(live, native, facts, record))
    live.upload(native.snapshot(), facts, native.original_chart_bytes)
    run = _evidence_run()[1]
    initial = replace(_ready(), swing_analysis_run_identity=run.run_identity)
    if connected:
        initial = replace(
            initial,
            provider_state=type(initial.provider_state).DISCONNECTED,
        )
    application_options = (
        {"background_runner": _immediate} if connected else {}
    )
    application = SwingOpportunitiesApplication(
        _Provider, initial_snapshot=initial, **application_options
    )
    if connected:
        assert application.connect_provider()
    application.restore_mtf_fact_snapshot(facts)
    application.restore_native_discovery_run(run)
    server = create_browser_server(
        application,
        port=0,
        v1_review=SwingV1ReviewWorkflow(
            LocalTradingViewEvidenceStore(tmp_path / "legacy")
        ),
        native_review=native,
        visual_v3_live=live,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, server.visual_v3.completed_snapshot()[0]


def test_connected_browser_and_trade_window_share_active_capability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server, thread, completed = _server(tmp_path, connected=True)
    try:
        capability = server.application.authenticated_read_only_capability()
        assert server.application.snapshot().provider_state.value == "CONNECTED"
        assert capability is not None and capability.active is True
        assert server._provider_capability() is capability

        with monkeypatch.context() as patch:
            patch.setattr(
                server,
                "_execution_context",
                lambda *_values: (_ for _ in ()).throw(
                    ValueError("GOVERNED_INSTRUMENT_INVALID")
                ),
            )
            status, _, body = _post(server, completed)
        assert status == 303 and body == ""
        attempt = _latest(server, completed)
        assert attempt.stage.value == "EXECUTION_CONTEXT"
        assert attempt.safe_failure_code == "GOVERNED_INSTRUMENT_INVALID"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _post(server, completed, *, extra: bool = False):  # type: ignore[no-untyped-def]
    values = {
        "run_identity": completed.requirement.native_run_identity,
        "canonical_instrument": completed.requirement.canonical_instrument,
        "native_assessment_sha256": (
            completed.requirement.thesis.native_assessment_sha256
        ),
    }
    if extra:
        values["unexpected"] = "bounded"
    authority = f"127.0.0.1:{server.server_port}"
    return _request(
        server,
        "POST",
        "/swing/trade-window/construct",
        headers={
            "Host": authority,
            "Origin": f"http://{authority}",
            "Referer": f"http://{authority}/swing/opportunities",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        body=urlencode(values),
    )


def _latest(server, completed):  # type: ignore[no-untyped-def]
    return server.trade_window.latest_construction_attempt(
        completed.requirement.native_run_identity,
        completed.requirement.canonical_instrument,
        completed.requirement.thesis.native_assessment_sha256,
    )


def test_pre_step31_stage_failures_are_retained_and_redirected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server, thread, completed = _server(tmp_path)
    try:
        status, headers, body = _post(server, completed, extra=True)
        assert status == 303 and headers["Location"].startswith("/swing/trade-window/")
        assert body == ""
        assert _latest(server, completed).stage.value == "REQUEST_PARSE"

        with monkeypatch.context() as patch:
            patch.setattr(
                server.application,
                "opportunities_projection",
                lambda: (server.application.snapshot(), None),
            )
            status, headers, body = _post(server, completed)
        assert status == 303 and body == ""
        assert _latest(server, completed).stage.value == "CURRENT_BINDING"

        status, headers, body = _post(server, completed)
        assert status == 303 and body == ""
        attempt = _latest(server, completed)
        assert attempt.stage.value == "PROVIDER_CAPABILITY"
        assert attempt.safe_failure_code == "KITE_READ_ONLY_CAPABILITY_UNAVAILABLE"

        with monkeypatch.context() as patch:
            patch.setattr(server, "_provider_capability", lambda: object())
            patch.setattr(
                server,
                "_execution_context",
                lambda *_values: (_ for _ in ()).throw(
                    ValueError("GOVERNED_INSTRUMENT_INVALID")
                ),
            )
            status, headers, body = _post(server, completed)
        assert status == 303 and body == ""
        attempt = _latest(server, completed)
        assert attempt.stage.value == "EXECUTION_CONTEXT"
        assert attempt.safe_failure_code == "GOVERNED_INSTRUMENT_INVALID"

        with monkeypatch.context() as patch:
            patch.setattr(server, "_provider_capability", lambda: object())
            patch.setattr(
                server,
                "_execution_context",
                lambda *_values: (
                    object(),
                    _context(completed.requirement.canonical_instrument),
                ),
            )
            patch.setattr(
                "kronos.browser.server.build_current_trade_construction_evidence",
                lambda *_values: (_ for _ in ()).throw(
                    ValueError("CURRENT_TRADE_CONSTRUCTION_SOURCE_INVALID")
                ),
            )
            status, headers, body = _post(server, completed)
        assert status == 303 and body == ""
        attempt = _latest(server, completed)
        assert attempt.stage.value == "EVIDENCE_PACKAGE"
        assert attempt.safe_failure_code == "CURRENT_TRADE_CONSTRUCTION_SOURCE_INVALID"

        projection = server.trade_window.project(
            completed.requirement.native_run_identity,
            completed.requirement.canonical_instrument,
        )
        assert projection is not None
        assert projection.handoff is None and projection.trade_plan is None
        status, _, page = _request(server, "GET", headers["Location"])
        assert status == 200
        assert "TRADE PLAN NOT CONSTRUCTED" in page
        assert "CURRENT TRADE CONSTRUCTION SOURCE INVALID" in page
        assert "Trade Plan construction is not available for this current evidence" not in page
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_step31_invalid_geometry_redirects_and_reuses_one_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server, thread, _ = _server(tmp_path)
    completed = _completed(tmp_path / "controlled")
    server.trade_window.restore((completed,))
    base = _evidence(completed)
    invalid = create_trade_construction_evidence_package(
        package_identity=base.package_identity,
        native_run_identity=base.native_run_identity,
        canonical_instrument=base.canonical_instrument,
        native_assessment_sha256=base.native_assessment_sha256,
        setup_identity=base.setup_identity,
        observation_boundary=base.observation_boundary,
        provenance=base.provenance,
        qualification_candle=base.qualification_candle,
        governing_structural_low=_price(
            "INVALID-STRUCTURAL-LOW", "105", base.observation_boundary
        ),
        governing_structural_high=base.governing_structural_high,
        prior_directional_swing_high=base.prior_directional_swing_high,
        prior_directional_swing_low=base.prior_directional_swing_low,
        original_range_high=base.original_range_high,
        original_range_low=base.original_range_low,
        material_barriers=base.material_barriers,
    )
    try:
        with monkeypatch.context() as patch:
            patch.setattr(
                server.visual_v3,
                "completed_for",
                lambda *_values: completed,
            )
            patch.setattr(server, "_provider_capability", lambda: object())
            patch.setattr(
                server,
                "_execution_context",
                lambda *_values: (
                    object(),
                    _context(completed.requirement.canonical_instrument),
                ),
            )
            patch.setattr(
                "kronos.browser.server.build_current_trade_construction_evidence",
                lambda *_values: invalid,
            )
            first = _post(server, completed)
            first_handoff = server.trade_window.project(
                completed.requirement.native_run_identity,
                completed.requirement.canonical_instrument,
            ).handoff.handoff_identity
            second = _post(server, completed)
        assert first[0] == second[0] == 303
        projection = server.trade_window.project(
            completed.requirement.native_run_identity,
            completed.requirement.canonical_instrument,
        )
        assert projection is not None
        assert projection.handoff is not None and projection.trade_plan is None
        assert projection.handoff.handoff_identity == first_handoff
        assert _latest(server, completed).stage.value == "STEP31"
        assert _latest(server, completed).safe_failure_code == "GEOMETRY_INVALID"
        status, _, page = _request(server, "GET", first[1]["Location"])
        assert status == 200
        assert "GEOMETRY INVALID" in page
        assert "No PAPER / LIVE action is available." in page
        assert "CONSTRUCT TRADE PLAN" not in page
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
