"""Historical V1 Review restoration cannot replace current analytical authority."""
from dataclasses import replace
from unittest.mock import Mock

import pytest

from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.browser import server as browser
from kronos.swing.v1.evidence_store import LocalTradingViewEvidenceStore
from tests.unit.application.test_swing_opportunities import _Provider
from tests.unit.swing.test_run_publication import checkpoint, scenario
from tests.unit.swing.v1.test_swing_v1_slice3 import _classified_run


@pytest.mark.parametrize("case", ["historical", "same-parent", "mtf-invalid",
    "native-invalid", "control-invalid", "header-only"])
def test_retained_review_restoration_respects_exact_current_publication(
    checkpoint, tmp_path, monkeypatch, case,
):
    co, _, _, current = checkpoint
    historical = case in {"historical", "control-invalid", "header-only"}
    parent = "SWING-RUN-413912F4B30840CAAC8EEFFCADEB666C" if historical else current.native.run_identity
    provenance = replace(current.provenance, run_id=parent)
    co.provenance_store.retain(provenance)
    layer1 = _classified_run(set())
    boundary = provenance.analysis_boundary
    layer1 = replace(layer1, run_identity=f"{layer1.policy_bundle}@{boundary.isoformat()}",
        observation_boundary=boundary, instruments=tuple(replace(item,
            assessments=tuple(replace(assessment, observation_boundary=boundary)
                              for assessment in item.assessments))
            for item in layer1.instruments))
    review_store = LocalTradingViewEvidenceStore(tmp_path / "legacy-review")
    review_store.retain_review_run(layer1, swing_analysis_run_identity=parent)
    before_review = {str(p.relative_to(review_store.root)): p.read_bytes()
                    for p in review_store.root.rglob('*') if p.is_file()}
    monkeypatch.setattr(browser, "LocalTradingViewEvidenceStore", lambda *args: review_store)
    monkeypatch.setattr(browser, "LocalSwingRunProvenanceStore", lambda: co.provenance_store)
    app = SwingOpportunitiesApplication(_Provider, run_publication=co,
        mtf_fact_evidence_store=co.mtf_store, native_discovery_evidence_store=co.native_store,
        relative_context_evidence_store=co.relative_store)
    if case == "header-only":
        # A different presentation header with matching in-memory components is
        # still not verified publication authority for waiving legacy restore.
        header = app.snapshot()
        app = SwingOpportunitiesApplication(_Provider, initial_snapshot=header,
            mtf_fact_evidence_store=co.mtf_store, native_discovery_evidence_store=co.native_store)
        app.restore_mtf_fact_snapshot(current.mtf)
        app.restore_native_discovery_run(current.native)
    if case == "control-invalid":
        (co.root / "control.json").write_bytes(b"corrupt")
    if case in {"mtf-invalid", "native-invalid"}:
        owner = co.mtf_store if case == "mtf-invalid" else co.native_store
        monkeypatch.setattr(owner, "load", Mock(side_effect=ValueError("INVALID_RETAINED_COMPONENT")))
    installed_mtf = Mock(wraps=app.restore_mtf_fact_snapshot)
    installed_native = Mock(wraps=app.restore_native_discovery_run)
    monkeypatch.setattr(app, "restore_mtf_fact_snapshot", installed_mtf)
    monkeypatch.setattr(app, "restore_native_discovery_run", installed_native)
    instance = browser.create_browser_server(app, port=0)
    try:
        outcomes = dict(instance.startup_restoration_outcomes())
        expected = {
            "historical": ("NOT_APPLICABLE", "NOT_APPLICABLE"),
            "same-parent": ("SUCCESS", "SUCCESS"),
            "mtf-invalid": ("FAILED", "SUCCESS"),
            "native-invalid": ("SUCCESS", "FAILED"),
            "control-invalid": ("FAILED", "FAILED"),
            "header-only": ("FAILED", "FAILED"),
        }[case]
        assert (outcomes["LEGACY_MTF"], outcomes["LEGACY_NATIVE"]) == expected
        assert app.snapshot().swing_analysis_run_identity == current.native.run_identity
        assert review_store.latest_review_run() == (parent, layer1)
        assert {str(p.relative_to(review_store.root)): p.read_bytes()
                for p in review_store.root.rglob('*') if p.is_file()} == before_review
        if historical:
            installed_mtf.assert_not_called()
            installed_native.assert_not_called()
        if case == "historical":
            assert app.mtf_fact_snapshot() == current.mtf
            assert app.native_discovery_run() == current.native
            assert app.relative_context_run() == current.relative
            assert co.current().reference == current.reference
        elif case == "same-parent":
            installed_mtf.assert_called_once_with(current.mtf)
            installed_native.assert_called_once_with(current.native)
    finally:
        instance.server_close()
        app.close()
