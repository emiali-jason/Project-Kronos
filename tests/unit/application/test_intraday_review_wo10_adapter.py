"""Offline WO-BR2 adapter qualification; production dispatch remains held."""
from dataclasses import fields
from datetime import timedelta
import json

import pytest

from kronos.application.intraday_review_wo10 import ADAPTER_IDENTITY, request_document
from kronos.application.intraday_wo10 import IntradayWo10Application
from kronos.application.intraday_wo10_runtime import (
    IntradayWo10RuntimeService, RetainedWo10EvidenceLoader,
    RuntimeWo10EvidenceAssembler, RuntimeWo10PolicyRegistry,
)
from kronos.browser.intraday_wo10_control import IntradayWo10OperationalControl
from kronos.browser.product_routes import BrowserGetRequest, BrowserPostRequest
from kronos.intraday.review import ReviewError
from kronos.intraday.review_v2 import (
    _identity, create_visual_evidence_pointer_v2,
)
from kronos.intraday.wo10_persistence import Wo10Store
from tests.unit.browser.test_intraday_review_workflow import _routes, _fingerprints
from tests.unit.browser.test_intraday_review_v2_control import _control, _payload
from tests.unit.browser.test_product_route_isolation import _snapshot
from tests.unit.intraday.test_review import _png
from tests.unit.intraday.test_review_v2 import _completed_batch_payload, _retain_later_current_run


def _ready(tmp_path):
    run, app, control = _control(tmp_path)
    control.execute_document(_payload(run))
    app.upload_chart(app.snapshot().candidates[0].cycle_identity,
                     media_type="image/png", payload=_png(12))
    batch = app.create_combined_question_transport()
    app.import_combined_answer(_completed_batch_payload(batch.answer_template_path, "Reliance Industries Ltd"))
    return run, app, batch


def _wo10(app, root):
    store = Wo10Store(root.resolve())
    registry = RuntimeWo10PolicyRegistry()
    loader = RetainedWo10EvidenceLoader(
        probables=app.probables_store, review=app.review_store, registry=registry,
    )
    application = IntradayWo10Application(
        run_store=app.probables_store, store=store, policy_registry=registry,
        evidence_assembler=RuntimeWo10EvidenceAssembler(loader),
    )
    runtime = IntradayWo10RuntimeService(application, store)
    return IntradayWo10OperationalControl(runtime, app.probables_store, registry)


def _offline_dispatch(app, control):
    # Test-only orchestration: no production route/control changes.
    return tuple(control.execute_document(request_document(request))
                 for request in app.current_reconciliation().requests)


def _visual(app, batch):
    return app.review_store.load_visual_evidence_for_pack(batch.packs[0].review_pack_identity)


def test_exact_ready_binding_and_existing_wo10_idempotency(tmp_path):
    run, app, batch = _ready(tmp_path)
    before = _fingerprints(app.review_store.root)
    selected = app.current_reconciliation()
    assert selected.candidate_count == selected.answer_ready_count == len(selected.requests) == 1
    request = selected.requests[0]
    visual = _visual(app, batch)
    assert request.probables_run_identity == run.run_identity
    assert request.probable_bindings[0].canonical_subject_identity == "NSE-EQ-RELIANCE"
    for identity in (ADAPTER_IDENTITY, batch.packs[0].review_cycle_identity,
                     batch.packs[0].chart_revision_identity, batch.packs[0].review_pack_identity,
                     visual.answer_pack_identity, visual.visual_evidence_identity,
                     visual.integrity_identity, request.policy.integrity_identity):
        assert identity in request.provenance
    control = _wo10(app, tmp_path / "offline-wo10")
    first = _offline_dispatch(app, control)
    retained = _fingerprints(control.runtime.store.root)
    second = _offline_dispatch(app, control)
    assert first[0]["outcome"] == "COMPLETED"
    assert second[0]["outcome"] == "RETAINED" and second[0]["idempotent"]
    assert retained == _fingerprints(control.runtime.store.root)
    assert before == _fingerprints(app.review_store.root)
    assert app.current_reconciliation() == selected


def test_zero_ready_never_calls_control(tmp_path):
    run, app, control = _control(tmp_path)
    control.execute_document(_payload(run))
    class Forbidden:
        def execute_document(self, payload):
            pytest.fail("zero-ready WO-10 invocation")
    assert _offline_dispatch(app, Forbidden()) == ()
    assert app.current_reconciliation().candidate_count == 1


def test_historical_answer_for_same_instrument_never_satisfies_current(tmp_path):
    _, app, batch = _ready(tmp_path)
    old = _visual(app, batch)
    run = _retain_later_current_run(app)
    app.create_eligible_cycles(run)
    assert app.review_store.load_visual_evidence(old.visual_evidence_identity) == old
    selected = app.current_reconciliation()
    assert selected.candidate_count == 1 and selected.requests == ()


def test_stale_review_rejected_before_dispatch(tmp_path):
    _, app, _ = _ready(tmp_path)
    _retain_later_current_run(app)
    with pytest.raises(ReviewError):
        app.current_reconciliation()


@pytest.mark.parametrize("family", ["cycles", "chart-revisions", "question-packs", "visual-evidence"])
def test_conflicting_bytes_under_same_identity_fail_closed(tmp_path, family):
    _, app, _ = _ready(tmp_path)
    artifact = next((app.review_store.root / family).glob("*.json"))
    document = json.loads(artifact.read_bytes())
    document["integrity_identity"] = "INTEGRITY-FOREIGN"
    artifact.write_text(json.dumps(document))
    with pytest.raises(ReviewError):
        app.current_reconciliation()


@pytest.mark.parametrize("field,value", [
    ("review_cycle_identity", "FOREIGN-CYCLE"),
    ("probable_result_identity", "FOREIGN-CANDIDATE"),
    ("chart_revision_identity", "FOREIGN-CHART"),
    ("review_pack_identity", "FOREIGN-PACK"),
    ("answer_pack_identity", "FOREIGN-ANSWER"),
    ("probables_run_identity", "FOREIGN-RUN"),
    ("proposed_direction", "SHORT"),
    ("methodology_publication_identity", "FOREIGN-POLICY"),
    ("methodology_checksum", "FOREIGN-CHECKSUM"),
    ("visual_identity_publication_version", "99.0.0"),
    ("visual_identity_relationship_integrity_identity", "FOREIGN-INTEGRITY"),
    ("analysis_boundary", None),
])
def test_self_consistent_foreign_visual_bindings_rejected(tmp_path, field, value):
    _, app, batch = _ready(tmp_path)
    visual = _visual(app, batch)
    values = {f.name: getattr(visual, f.name) for f in fields(visual)
              if f.name not in {"visual_evidence_identity", "integrity_identity"}}
    values[field] = visual.analysis_boundary + timedelta(minutes=1) if value is None else value
    foreign = type(visual)(
        visual_evidence_identity=_identity("INTRADAY-VISUAL-EVIDENCE-V2-", values),
        integrity_identity=_identity("INTEGRITY-INTRADAY-VISUAL-EVIDENCE-V2-", values), **values,
    )
    # Simulate a coherently signed foreign payload at the exact pack alias.
    app.review_store.retain_visual_evidence(foreign)
    pointer = create_visual_evidence_pointer_v2(foreign)
    from kronos.intraday.review_v2 import artifact_bytes_v2
    path = app.review_store.root / "current-visual-evidence" / (batch.packs[0].review_pack_identity + ".json")
    path.write_bytes(artifact_bytes_v2(pointer))
    with pytest.raises(ReviewError):
        app.current_reconciliation()


@pytest.mark.parametrize("mutation", ["missing", "changed", "foreign", "symlink"])
def test_exact_retained_answer_is_required(tmp_path, mutation):
    _, app, batch = _ready(tmp_path)
    visual = _visual(app, batch)
    path = app.review_store.root / "answer-transports" / (visual.review_pack_identity + "-" + visual.answer_source_sha256 + ".json")
    if mutation == "missing":
        path.unlink()
        assert not app.current_reconciliation().requests
        return
    if mutation == "changed":
        path.write_bytes(path.read_bytes() + b" ")
    elif mutation == "foreign":
        document = json.loads(path.read_bytes())
        document["review_cycle_identity"] = "FOREIGN-CYCLE"
        path.write_text(json.dumps(document))
    else:
        target = tmp_path / "foreign-answer.json"
        target.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(target)
    with pytest.raises(ReviewError):
        app.current_reconciliation()


def test_chart_replacement_requires_new_current_answer(tmp_path):
    _, app, batch = _ready(tmp_path)
    prior = app.current_reconciliation()
    app.upload_chart(batch.packs[0].review_cycle_identity, media_type="image/png", payload=_png(19))
    current = app.current_reconciliation()
    assert len(prior.requests) == 1 and not current.requests
    assert current.chart_ready_count == 1 and current.answer_ready_count == 0


def test_current_counts_and_browser_dispatch_use_only_ready_v2_candidate(tmp_path, monkeypatch):
    run, app, control, routes = _routes(tmp_path)
    control.execute_document(_payload(run))
    app.upload_chart(app.snapshot().candidates[0].cycle_identity, media_type="image/png", payload=_png(15))
    batch = app.create_combined_question_transport()
    app.import_combined_answer(_completed_batch_payload(batch.answer_template_path, "Reliance Industries Ltd"))
    review_before = _fingerprints(app.review_store.root)
    wo10 = _wo10(app, tmp_path / "offline-browser-wo10")
    routes._wo10_control = wo10
    monkeypatch.setattr(routes._reconciliation, "reconcile_all_ready", lambda: pytest.fail("historical dispatch"))
    page = routes.handle_get(BrowserGetRequest("/intraday/review", {}), _snapshot).body
    assert "Chart ready: 1 / 1" in page
    assert "Answer ready: 1 / 1" in page
    assert "Reconcile eligible: 1 / 1" in page
    assert page.count('data-current-review-bulk="true"') == 1
    assert '<button type="submit">RECONCILE ALL READY REVIEWS</button>' in page
    result = routes.handle_post(BrowserPostRequest("/intraday/review/reconcile-all", {}, "", b""), _snapshot)
    document = json.loads(result.body)
    assert result.status == 200 and document["outcome"] == "COMPLETED"
    assert document["invocation_count"] == document["success_count"] == 1
    assert document["failure_count"] == document["not_dispatched_count"] == 0
    assert document["results"][0]["candidates"][0]["canonical_subject_identity"] == "NSE-EQ-RELIANCE"
    assert review_before == _fingerprints(app.review_store.root)
