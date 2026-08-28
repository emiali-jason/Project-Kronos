from dataclasses import replace
from pathlib import Path
from threading import Thread

from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.application.swing_native_review import (
    NativeReviewWorkflow,
    project_native_analysis_details,
)
from kronos.application.swing_v1_review import SwingV1ReviewWorkflow
from kronos.browser.server import create_browser_server
from kronos.browser.views import render_native_analysis_details, render_v1_review
from kronos.swing.v1 import LocalTradingViewEvidenceStore
from kronos.swing.v1.native_review import NativeReviewEvidenceStore
from kronos.swing.v1.relative_context import (
    RelativeContextEvidenceStore,
    build_relative_context_run,
)
from kronos.swing.run_provenance import (
    LocalSwingRunProvenanceStore,
    SwingAnalysisRunProvenance,
)

from tests.unit.application.test_swing_opportunities import _Provider
from tests.unit.browser.test_browser_server import _request
from tests.unit.browser.test_browser_views import _ready
from tests.unit.swing.v1.test_native_review import _evidence_run


def test_native_review_projects_compact_non_veto_nifty_relative_context(
    tmp_path: Path,
) -> None:
    facts, run, probable = _evidence_run()
    relative = build_relative_context_run(facts)
    workflow = NativeReviewWorkflow(NativeReviewEvidenceStore(tmp_path / "native"))
    prepared = workflow.prepare(run, facts)
    legacy = SwingV1ReviewWorkflow(
        LocalTradingViewEvidenceStore(tmp_path / "legacy")
    ).snapshot()

    html = render_v1_review(
        _ready(), legacy, prepared, relative_context=relative
    )

    assert "Relative strength vs NIFTY" in html
    assert "1D +0.00% · EQUAL · NEUTRAL CONTEXT" in html
    assert "4H +0.00% · EQUAL · NEUTRAL CONTEXT" in html
    assert "1H +0.00% · EQUAL · NEUTRAL CONTEXT" in html
    assert "SUPPORTING CONTEXT ONLY · NON-VETO" in html
    assert probable.canonical_instrument in html


def test_analysis_details_projects_returns_state_and_authority_without_raw_json(
    tmp_path: Path,
) -> None:
    facts, run, probable = _evidence_run()
    relative = build_relative_context_run(facts)
    workflow = NativeReviewWorkflow(NativeReviewEvidenceStore(tmp_path / "native"))
    prepared = workflow.prepare(run, facts)
    details = project_native_analysis_details(
        run, prepared, run.run_identity, probable.canonical_instrument
    )
    assert details is not None

    html = render_native_analysis_details(
        _ready(), details,
        relative_context=relative.record(probable.canonical_instrument),
    )

    assert "RELATIVE STRENGTH VS NIFTY" in html
    assert "Stock return" in html
    assert "NIFTY return" in html
    assert "Relative return" in html
    assert "EQUAL · NEUTRAL CONTEXT" in html
    assert "NO DISCOVERY, READINESS, TRADE OR EXECUTION AUTHORITY" in html
    assert relative.integrity_sha256 not in html


def test_exact_run_relative_context_restores_without_provider_or_review_replay(
    tmp_path: Path,
) -> None:
    facts, run, _probable = _evidence_run()
    relative = build_relative_context_run(facts)
    store = RelativeContextEvidenceStore(tmp_path / "relative")
    store.retain(relative)

    restarted = RelativeContextEvidenceStore(tmp_path / "relative")
    restored = restarted.load(run.run_identity)

    assert restored == relative
    assert restored.run_identity == facts.run_identity


def test_application_restart_restores_exact_current_relative_context(
    tmp_path: Path,
) -> None:
    facts, run, _probable = _evidence_run()
    relative = build_relative_context_run(facts)
    relative_store = RelativeContextEvidenceStore(tmp_path / "relative")
    relative_store.retain(relative)
    provenance_store = LocalSwingRunProvenanceStore(tmp_path / "provenance")
    provenance_store.retain(SwingAnalysisRunProvenance(
        run_id=run.run_identity,
        run_created_at=run.observed_at,
        analysis_boundary=run.observed_at,
        market_data_snapshot_identity="SWING-MARKET-DATA-SNAPSHOT-" + "a" * 64,
        successful_completed_at=run.observed_at,
    ))

    restarted = SwingOpportunitiesApplication(
        _Provider,
        initial_snapshot=_ready(),
        run_provenance_store=provenance_store,
        relative_context_evidence_store=relative_store,
    )

    assert restarted.relative_context_run() == relative
    assert restarted.relative_context_run().run_identity == run.run_identity


def test_relative_context_does_not_change_native_discovery_digest() -> None:
    facts, run, _probable = _evidence_run()
    before = run
    relative = build_relative_context_run(facts)

    assert run == before
    assert run.result_sha256 == before.result_sha256
    assert relative.run_identity == run.run_identity


def test_browser_routes_bind_exact_current_run_relative_context(tmp_path: Path) -> None:
    facts, run, probable = _evidence_run()
    relative = build_relative_context_run(facts)
    application = SwingOpportunitiesApplication(
        _Provider,
        initial_snapshot=replace(
            _ready(), swing_analysis_run_identity=run.run_identity
        ),
    )
    application.restore_mtf_fact_snapshot(facts)
    application.restore_native_discovery_run(run)
    application.restore_relative_context_run(relative)
    native = NativeReviewWorkflow(NativeReviewEvidenceStore(tmp_path / "native"))
    native.prepare(run, facts)
    server = create_browser_server(
        application,
        port=0,
        v1_review=SwingV1ReviewWorkflow(
            LocalTradingViewEvidenceStore(tmp_path / "legacy")
        ),
        native_review=native,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, review = _request(server, "GET", "/swing/v1-review")
        assert status == 200
        assert "Relative strength vs NIFTY" in review

        status, _, details = _request(
            server,
            "GET",
            f"/swing/analysis-details/{run.run_identity}/{probable.canonical_instrument}",
        )
        assert status == 200
        assert "RELATIVE STRENGTH VS NIFTY" in details
        assert "SUPPORTING CONTEXT ONLY" in details
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
