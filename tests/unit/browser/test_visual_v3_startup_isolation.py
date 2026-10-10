from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from threading import Thread
from types import SimpleNamespace

import pytest

from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.application.swing_v1_review import SwingV1ReviewWorkflow
from kronos.application.swing_visual_v3_live import SwingVisualV3LiveWorkflow
from kronos.browser.server import KronosBrowserServer, create_browser_server
from kronos.swing.v1.evidence_store import LocalTradingViewEvidenceStore
from kronos.swing.v1.pdf_visual_review import PdfReviewTransportError
from tests.unit.application.test_swing_opportunities import _Provider, _ready
from tests.unit.browser.test_browser_server import _request
from tests.unit.browser.test_swing_visual_v3_live import _live
from tests.unit.swing.v1.test_native_review import _evidence_run


def _bytes(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*") if path.is_file()
    }


@pytest.mark.parametrize("damage", ("missing", "changed", "unparseable"))
def test_invalid_saved_pdf_does_not_stop_browser_or_become_valid(
    tmp_path: Path, damage: str,
) -> None:
    native, facts, live = _live(tmp_path)
    record = live.generate(native.snapshot(), facts, native.original_chart_bytes)
    pdf = Path(record.question_path)
    if damage == "missing":
        pdf.unlink()
    elif damage == "changed":
        pdf.write_bytes(pdf.read_bytes() + b"changed")
    else:
        # A matching digest must not bypass independent PDF parsing/binding.
        pdf.write_bytes(b"%PDF-1.4\ninvalid object tree\n%%EOF")
        stored = live.transport.record_store.root / "review-packs" / f"{record.review_pack_id}.json"
        payload = json.loads(stored.read_text())
        payload["record"]["question_pdf_sha256"] = sha256(pdf.read_bytes()).hexdigest()
        for candidate in payload["record"]["candidate_packs"]:
            candidate["question_pdf_sha256"] = payload["record"]["question_pdf_sha256"]
        stored.write_text(json.dumps(payload))
    before = _bytes(tmp_path)
    restored = SwingVisualV3LiveWorkflow(live.cycle, live.transport)
    snapshot = restored.snapshot(facts.run_identity)
    assert snapshot.restoration_error == "VISUAL_V3_RESTORATION_UNAVAILABLE"
    assert snapshot.review_pack is None
    assert snapshot.answer_imports == ()
    assert not snapshot.current_run
    with pytest.raises(PdfReviewTransportError, match="PDF_BINDING_INVALID"):
        live.transport.record_store.load_current()
    with pytest.raises(PdfReviewTransportError, match="RESTORATION_UNAVAILABLE"):
        restored.upload(native.snapshot(), facts, native.original_chart_bytes)
    restored.restore(native.snapshot(), facts, native.original_chart_bytes)
    assert restored.cycle.completed_snapshot() == ()
    assert _bytes(tmp_path) == before

    run = _evidence_run()[1]
    application = SwingOpportunitiesApplication(
        _Provider,
        initial_snapshot=replace(_ready(), swing_analysis_run_identity=run.run_identity),
    )
    application.restore_mtf_fact_snapshot(facts)
    application.restore_native_discovery_run(run)
    server = create_browser_server(
        application, port=0, native_review=native, visual_v3_live=restored,
        v1_review=SwingV1ReviewWorkflow(LocalTradingViewEvidenceStore(tmp_path / "legacy")),
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert server.native_review_version() == "V3"
        assert _request(server, "GET", "/status")[0] == 200
        assert _request(server, "GET", "/swing/opportunities")[0] == 200
        status, _, page = _request(server, "GET", "/swing/v1-review")
        assert status == 200
        assert "SAVED V3 REVIEW UNAVAILABLE" in page
        assert 'action="/swing/v1/native-review-answer"' not in page
        assert str(pdf) not in page
        assert "Traceback" not in page
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_restoration_failure_cannot_fall_back_to_historical_v2() -> None:
    # No native/V2 selection may be consulted while persisted V3 is invalid.
    server = SimpleNamespace(
        visual_v3_live=SimpleNamespace(restoration_error="VISUAL_V3_RESTORATION_UNAVAILABLE")
    )
    assert KronosBrowserServer.native_review_version(server) == "V3"


def test_valid_new_pack_recovers_without_rewriting_invalid_history(tmp_path: Path) -> None:
    native, facts, live = _live(tmp_path)
    old = live.generate(native.snapshot(), facts, native.original_chart_bytes)
    pdf = Path(old.question_path)
    pdf.write_bytes(b"retained damaged PDF")
    stored = live.transport.record_store.root / "review-packs" / f"{old.review_pack_id}.json"
    old_record = stored.read_bytes()
    restored = SwingVisualV3LiveWorkflow(live.cycle, live.transport)
    assert restored.restoration_error is not None
    new = restored.generate(native.snapshot(), facts, native.original_chart_bytes)
    assert new.review_pack_id != old.review_pack_id
    assert restored.restoration_error is None
    assert restored.transport.record_store.load_current() == new
    assert pdf.read_bytes() == b"retained damaged PDF"
    assert stored.read_bytes() == old_record


@pytest.mark.parametrize('fault', [False, True], ids=['healthy-control', 'retained-v3-restoration-failure'])
def test_r4_actual_constructor_retains_v3_restore_failure(tmp_path, monkeypatch, fault):
    from kronos.application.swing_visual_v3 import SwingVisualV3ReviewCycle
    from kronos.swing.v1.visual_evidence_v3 import LocalVisualEvidenceV3Store
    from kronos.swing.v1.native_readiness_v3 import NativeLayer2ReadinessV3Store
    from tests.unit.browser.test_swing_visual_v3_live import _payload, _answer_pdf
    from tests.unit.provider.test_connection_governance import governance, GENERATION
    from kronos.browser.runtime_state import complete_startup
    native, facts, live = _live(tmp_path)
    pack = live.generate(native.snapshot(), facts, native.original_chart_bytes)
    answer = live.transport.configuration.answer_directory / pack.expected_answer_filename
    _answer_pdf(answer, _payload(live, native, facts, pack))
    imported = live.upload(native.snapshot(), facts, native.original_chart_bytes)
    assert imported[-1].consumed
    restored = SwingVisualV3LiveWorkflow(
        SwingVisualV3ReviewCycle(LocalVisualEvidenceV3Store((tmp_path/'visual-v3').resolve()),
                                NativeLayer2ReadinessV3Store((tmp_path/'readiness-v3').resolve())),
        live.transport)
    errors = []
    if fault:
        # Existing real restore raises VISUAL_V3_RESTART_EVIDENCE_MISSING when
        # its existing persisted-cycle lookup yields no required evidence.
        monkeypatch.setattr(restored.cycle, 'restore_persisted', lambda *a, **k: None)
    original = restored.restore
    def counted(*args, **kwargs):
        try:
            return original(*args, **kwargs)
        except ValueError as error:
            errors.append(str(error))
            raise
    monkeypatch.setattr(restored, 'restore', counted)
    g = governance(tmp_path/'governance', maintenance=GENERATION)
    run = _evidence_run()[1]
    def no_provider():
        pytest.fail('Provider acquisition forbidden')
    app = SwingOpportunitiesApplication(no_provider, connection_governance=g,
        initial_snapshot=replace(_ready(), swing_analysis_run_identity=run.run_identity))
    app.restore_mtf_fact_snapshot(facts)
    app.restore_native_discovery_run(run)
    server = create_browser_server(app, port=0, native_review=native, visual_v3_live=restored,
        v1_review=SwingV1ReviewWorkflow(LocalTradingViewEvidenceStore(tmp_path/'legacy')))
    try:
        assert errors == (['VISUAL_V3_RESTART_EVIDENCE_MISSING'] if fault else [])
        assert restored.restoration_error is None
        assert restored.snapshot(run.run_identity).answer_imports[-1].consumed
        assert len(restored.cycle.completed_snapshot()) == (0 if fault else len(pack.candidate_packs))
        # The real constructor retains the final owner outcome without another restore.
        result = server.startup_restoration_outcomes()
        assert type(result) is tuple
        assert dict(result)['V3_RESTORE'] == ('FAILED' if fault else 'SUCCESS')
        assert server.startup_restoration_outcomes() is result
        # Only WO06H/Provider inputs are fixtures; no serving loop is started.
        server.provider_runtime = SimpleNamespace(read_only_status=lambda: {'capability_state': 'ABSENT'})
        complete_startup(server, SimpleNamespace(status=lambda: {
            'failure': None, 'window': None, 'runtime_accepted': False}),
            swing_outcomes=server.startup_restoration_outcomes(),
            wo11=SimpleNamespace(last_failure=None),
            wo17=dict(restoration_state='NOT_YET_RUN', failure_stage=None, failure_reason=None, current_positions=[]))
        state = g.maintenance_status()
        receipts = list((tmp_path/'governance'/'audit').rglob('*.json'))
        assert g.startup_state == ('BLOCKED' if fault else 'READY')
        assert state['active'] is fault
        assert len(receipts) == (0 if fault else 1)
    finally:
        server.server_close()


@pytest.mark.parametrize("mode", ("legacy-unestablished", "restored", "finalization-failure", "restore-io-failure", "corrupt-pack-v0", "corrupt-pack-v3"))
def test_native_owner_outcome_controls_real_constructor_startup(tmp_path, monkeypatch, mode):
    from kronos.application.swing_native_review import NativeReviewWorkflow
    from kronos.swing.v1.native_review import NativeReviewEvidenceStore, build_native_review_requirements
    from kronos.browser.runtime_state import complete_startup
    from tests.unit.provider.test_connection_governance import governance, GENERATION

    facts, run, _ = _evidence_run()
    store = NativeReviewEvidenceStore(tmp_path / "native")
    if mode not in {"legacy-unestablished", "corrupt-pack-v0", "corrupt-pack-v3"}:
        # Real historical requirement publication without prospective backfill.
        store.retain(build_native_review_requirements(run, facts))
    if mode.startswith("corrupt-pack-"):
        pack = store.root / ("pdf-transport-" + mode.rsplit("-", 1)[-1]) / "review-packs" / "KRONOS-REVIEW-X.json"
        pack.parent.mkdir(parents=True)
        pack.write_text(json.dumps({"record": {
            "native_run_identity": ["lost-binding"],
            "review_pack_id": "KRONOS-REVIEW-X"}}))
    native = NativeReviewWorkflow(store,
        chart_store=LocalTradingViewEvidenceStore(tmp_path / "charts"))
    before = _bytes(tmp_path / "native")
    calls = []
    actual_restore = native.restore
    def restore(*args):
        calls.append("restore")
        if mode == "restore-io-failure":
            raise PermissionError("ISOLATED_NATIVE_READ_FAILURE")
        return actual_restore(*args)
    monkeypatch.setattr(native, "restore", restore)
    if mode == "finalization-failure":
        def fail():
            raise ValueError("ISOLATED_NATIVE_FINALIZATION_FAILURE")
        monkeypatch.setattr(native, "_reconcile_journal_unlocked", fail)
    g = governance(tmp_path / "governance", maintenance=GENERATION)
    def no_provider():
        pytest.fail("Provider operation forbidden")
    app = SwingOpportunitiesApplication(no_provider, connection_governance=g,
        initial_snapshot=replace(_ready(), swing_analysis_run_identity=run.run_identity))
    app.restore_mtf_fact_snapshot(facts)
    app.restore_native_discovery_run(run)
    server = create_browser_server(app, port=0, native_review=native,
        v1_review=SwingV1ReviewWorkflow(LocalTradingViewEvidenceStore(tmp_path / "legacy")))
    try:
        outcomes = server.startup_restoration_outcomes()
        assert dict(outcomes)["NATIVE_REVIEW"] == {
            "legacy-unestablished": "APPLICABILITY_NOT_ESTABLISHED",
            "restored": "SUCCESS", "finalization-failure": "FAILED", "restore-io-failure": "FAILED",
            "corrupt-pack-v0": "FAILED", "corrupt-pack-v3": "FAILED"}[mode]
        server.provider_runtime = SimpleNamespace(read_only_status=lambda: {"capability_state": "ABSENT"})
        complete_startup(server, SimpleNamespace(status=lambda: {
            "failure": None, "window": None, "runtime_accepted": False}),
            swing_outcomes=outcomes, wo11=SimpleNamespace(last_failure=None),
            wo17=dict(restoration_state="NOT_YET_RUN", failure_stage=None,
                      failure_reason=None, current_positions=[]))
        blocked = mode in {"finalization-failure", "restore-io-failure", "corrupt-pack-v0", "corrupt-pack-v3"}
        assert g.startup_state == ("BLOCKED" if blocked else "READY")
        assert g.maintenance_active == blocked
        assert calls == ["restore"]
        assert server.startup_restoration_outcomes() is outcomes
        assert _bytes(tmp_path / "native") == before
    finally:
        server.server_close()


@pytest.mark.parametrize("retained_preparation", (False, True))
def test_missing_analysis_uses_native_owner_applicability(tmp_path, retained_preparation):
    from kronos.application.swing_native_review import NativeReviewWorkflow
    from kronos.swing.v1.native_review import NativeReviewEvidenceStore, build_native_review_requirements
    from kronos.browser.runtime_state import complete_startup
    from tests.unit.provider.test_connection_governance import governance, GENERATION

    facts, run, _ = _evidence_run()
    store = NativeReviewEvidenceStore(tmp_path / "native")
    if retained_preparation:
        store.retain(build_native_review_requirements(run, facts))
    native = NativeReviewWorkflow(store,
        chart_store=LocalTradingViewEvidenceStore(tmp_path / "charts"))
    before = _bytes(tmp_path / "native")
    g = governance(tmp_path / "governance", maintenance=GENERATION)
    def no_provider():
        pytest.fail("Provider operation forbidden")
    app = SwingOpportunitiesApplication(no_provider, connection_governance=g)
    server = create_browser_server(app, port=0, native_review=native,
        v1_review=SwingV1ReviewWorkflow(LocalTradingViewEvidenceStore(tmp_path / "legacy")))
    try:
        outcomes = server.startup_restoration_outcomes()
        assert dict(outcomes)["NATIVE_REVIEW"] == (
            "FAILED" if retained_preparation else "APPLICABILITY_NOT_ESTABLISHED")
        assert native.restoration_result.native_run_identity is None
        server.provider_runtime = SimpleNamespace(read_only_status=lambda: {"capability_state": "ABSENT"})
        complete_startup(server, SimpleNamespace(status=lambda: {
            "failure": None, "window": None, "runtime_accepted": False}),
            swing_outcomes=outcomes, wo11=SimpleNamespace(last_failure=None),
            wo17=dict(restoration_state="NOT_YET_RUN", failure_stage=None,
                      failure_reason=None, current_positions=[]))
        assert g.startup_state == ("BLOCKED" if retained_preparation else "READY")
        assert g.maintenance_active == retained_preparation
        assert _bytes(tmp_path / "native") == before
    finally:
        server.server_close()
