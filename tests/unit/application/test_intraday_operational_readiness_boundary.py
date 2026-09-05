from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from kronos.application import intraday_operational_readiness as application
from kronos.application.intraday_runtime import create_intraday_runtime
from kronos.intraday.operational_readiness import WoBSourceBoundary
from kronos.intraday.operational_readiness_composition import reconstruct_operational_review
from kronos.intraday.probables import ProbableState
from kronos.intraday.probables_v2 import (
    ProbableReasonV2, SemanticDirection, _diagnostics, evaluate_probables_v2_run,
)
from kronos.intraday.probables_v2_diagnostics import create_probables_v2_replay_envelope
from kronos.intraday.probables_v2_persistence import create_current_probables_v2_pointer
from kronos.intraday.probables_v2_refresh import map_discovery_execution_to_probables_v2
from kronos.intraday.reconciliation import RECONCILIATION_IDENTITY, RECONCILIATION_VERSION
from kronos.intraday.reconciliation_persistence import IntradayReconciliationStore
from kronos.provider.runtime import SharedAuthenticatedProviderRuntime
from tests.unit.intraday.test_discovery_source import _composition
from tests.unit.intraday.test_probables_v2_session_lineage import _reseal
from tests.unit.instrument.test_active_derivative_selection import _resolve


@pytest.fixture(scope="module")
def prior_day_sources(tmp_path_factory):
    """Sealed isolated producer-state fixtures; never read production evidence."""
    boundary = datetime(2026, 9, 4, 10, 17, tzinfo=ZoneInfo("Asia/Kolkata"))
    execution, _, _, reads, _ = _composition(
        tmp_path_factory.mktemp("wo-b3e"), observed_at=boundary,
        active_mcx=True, retain_mcx=True,
    )
    reconciliation = IntradayReconciliationStore().load(
        publication_identity=RECONCILIATION_IDENTITY, publication_version=RECONCILIATION_VERSION,
    )
    mapped = map_discovery_execution_to_probables_v2(execution=execution, reconciliation=reconciliation)
    source = execution.run
    run = evaluate_probables_v2_run(
        source_discovery_run_identity=source.run_identity,
        universe_identity=source.universe_identity, universe_version=source.universe_version,
        reconciliation_identity=source.reconciliation_identity,
        reconciliation_version=source.reconciliation_version,
        market_session_identity=source.market_session_identity,
        analysis_boundary=source.observation_boundary,
        member_evidence=mapped.member_evidence, unavailable_members=mapped.unavailable_members,
        provenance=("WO-B3E-ISOLATED-PRODUCER-STATE-FIXTURE",),
    )
    longs = {"NSE-EQ-EICHERMOT", "NSE-EQ-NTPC", "NSE-EQ-TITAN"}
    shorts = {"NSE-EQ-BDL", "NSE-EQ-MAXHEALTH", "NSE-EQ-SRF", "NSE-EQ-TATAPOWER", "NSE-EQ-TMPV", "MCX-SUBJECT-CRUDE"}
    # Supply explicit producer states to the consumer test. WO-B must preserve
    # these states, not run the analytical admission algorithm again.
    results = tuple(
        _reseal(r, state=ProbableState.LONG_PROBABLE if r.canonical_subject_identity in longs else ProbableState.SHORT_PROBABLE,
            direction=SemanticDirection.LONG if r.canonical_subject_identity in longs else SemanticDirection.SHORT,
            reasons=(ProbableReasonV2.V2_CONDITIONS_SATISFIED,))
        if r.canonical_subject_identity in longs | shorts else r
        for r in run.results
    )
    run = _reseal(run, results=results, diagnostics=_diagnostics(results))
    assert run.diagnostics.total_probables == 9
    envelope = create_probables_v2_replay_envelope(
        request_identity="WO-B3E", operation_identity="WO-B3E", execution=execution,
        reconciliation=reconciliation, created_at=boundary,
    )
    return run, {m.mapping_identity: m for m in mapped.member_evidence}, envelope, _resolve(boundary), reads


def _runtime(tmp_path, monkeypatch, prior_day_sources, review_boundary):
    run, mappings, envelope, bindings, reads = prior_day_sources
    def forbidden():
        pytest.fail("WO-B must not construct Provider")
    runtime = create_intraday_runtime(
        SharedAuthenticatedProviderRuntime(forbidden, provider_identity="KITE"),
        evidence_root=tmp_path.resolve(), clock=lambda: review_boundary,
    )
    loader = runtime.wo_b_runtime._loader
    monkeypatch.setattr(loader._probables, "load_current", lambda: create_current_probables_v2_pointer(run))
    monkeypatch.setattr(loader._probables, "load_current_run", lambda: run)
    monkeypatch.setattr(loader._probables, "load_mapping", lambda identity: mappings[identity])
    monkeypatch.setattr(application, "load_probables_session_envelope", lambda root, value: envelope)
    monkeypatch.setattr(loader._active_derivatives, "load_current",
        lambda *, canonical_subject_id: bindings.for_subject(canonical_subject_id).binding)
    return runtime


@pytest.mark.parametrize("days", (0, 1, 3))
def test_prior_session_mcx_review_keeps_schedule_boundary_and_current_clock_separate(
    tmp_path, monkeypatch, prior_day_sources, days,
):
    run, _, _, _, reads = prior_day_sources
    now = run.analysis_boundary + timedelta(days=days)
    runtime = _runtime(tmp_path, monkeypatch, prior_day_sources, now)
    before = asdict(run)
    read_count = len(reads)
    document = runtime.wo_b_runtime.status_document()
    assert document["failure_reason"] is None
    assert len(document["reviews"]) == 9
    for review in document["reviews"]:
        items = {i["source_boundary"]: i for i in review["items"]}
        session = items["DOMAIN_008_SESSION"]
        # September 5 (Saturday) and September 7 must still describe the exact
        # September 4 session as ended, never roll the opportunity to today.
        expected = "OPEN" if days == 0 else "SESSION_ENDED"
        assert session["source_state"] == expected
        assert session["classification"] == ("AVAILABLE" if expected == "OPEN" else "TERMINAL")
        assert review["review_boundary"] == now.isoformat()
        assert len(review["source_references"]) == 3
        for name in ("ANALYTICAL_PROMOTION", "WO13_TRADE_PLAN", "WO14_RISK_OBSERVATION", "WO15_TIMING_HANDOFF", "WO16_SPONSOR_LIFECYCLE", "WO17_POSITION_MONITORING"):
            assert items[name]["source_state"] == items[name]["classification"] == "NOT_REACHED"
        original = next(r for r in run.results if r.result_identity == review["candidate_identity"])
        assert items["PROBABLES"]["source_state"] == original.state.value
    assert asdict(run) == before
    assert len(reads) == read_count
    assert not any(tmp_path.rglob("*.json"))
    assert document["provider_calls"] == document["upstream_operations"] == document["broker_operations"] == 0


def test_expired_active_contract_still_rejects_whole_projection(
    tmp_path, monkeypatch, prior_day_sources,
):
    active = prior_day_sources[3].for_subject("MCX-SUBJECT-CRUDE").binding
    now = active.expiry_eligibility_boundary + timedelta(microseconds=1)
    runtime = _runtime(tmp_path, monkeypatch, prior_day_sources, now)
    document = runtime.wo_b_runtime.status_document()
    assert document["failure_reason"] == "WO_B_DOMAIN_001_BINDING_MISMATCH"
    assert document["reviews"] == ()  # No silent partial eight-opportunity result.
    assert not any(tmp_path.rglob("*.json"))


def test_required_absence_is_unavailable_and_missing_foundation_is_rejected(
    tmp_path, monkeypatch, prior_day_sources,
):
    now = prior_day_sources[0].analysis_boundary + timedelta(days=1)
    runtime = _runtime(tmp_path, monkeypatch, prior_day_sources, now)
    request = runtime.wo_b_runtime._loader.current_requests(now)[0]
    required = replace(request, required_missing_boundaries=(WoBSourceBoundary.ANALYTICAL_PROMOTION,))
    review = reconstruct_operational_review(required)
    promotion = next(i for i in review.review_items if i.source_boundary is WoBSourceBoundary.ANALYTICAL_PROMOTION)
    assert promotion.review_classification.value == "UNAVAILABLE"
    assert promotion.exact_source_reason == "WO_B_REQUIRED_SOURCE_MISSING"
    missing = replace(request, sources=tuple(s for s in request.sources if s.reference.source_boundary is not WoBSourceBoundary.DOMAIN_008_SESSION))
    with pytest.raises(application.WoBCompositionError, match="WO_B_REQUIRED_FOUNDATION_SOURCE_MISSING"):
        reconstruct_operational_review(missing)
