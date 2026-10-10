"""Disposable exact successor generation and historical compatibility proofs."""
from dataclasses import replace
from datetime import timedelta
import json
from types import SimpleNamespace

import pytest
from kronos.application.intraday_evidence_currentness import IntradayPublicationBoundary
from kronos.application.intraday_wo09 import IntradayWo09Application
from kronos.application import intraday_review_ordered_batch
from kronos.intraday.wo09_machine_readiness import evaluate_machine_readiness, MachineReadinessRecord
from kronos.intraday.wo09_readiness import ReadinessState, CurrentnessState, create_next_wo_handoff, artifact_bytes
from kronos.intraday.wo09_persistence import Wo09Store, Wo09PublicationConflict
from kronos.intraday.probables_v2_persistence import ProbablesV2Store
from kronos.intraday.review_v2_persistence import IntradayReviewV2Store
from kronos.intraday.review_mcx_paired_persistence import IntradayMcxPairedReviewStore
from kronos.intraday.visual_reconciliation_v2_persistence import VisualReconciliationStore
from kronos.intraday.wo10_futures_store import FuturesStore
from kronos.instrument.active_derivative_persistence import ActiveDerivativeBindingStore
from kronos.intraday.wo08_assessment import canonical, digest
from tests.unit.intraday.test_wo08_assessment import publish


def graph(tmp_path, *, all_unavailable=False):
    run, mapping, native, owner, records = publish(tmp_path, all_unavailable=all_unavailable)
    probables = ProbablesV2Store(tmp_path / 'probables')
    probables.retain_complete(run=run, mappings=mapping.member_evidence)
    store = Wo09Store(tmp_path / 'readiness')
    boundary = IntradayPublicationBoundary(
        review=IntradayReviewV2Store(tmp_path/'review'), probables=probables,
        paired=IntradayMcxPairedReviewStore(tmp_path/'paired'), bindings=ActiveDerivativeBindingStore(tmp_path/'bindings'),
        reconciliation=VisualReconciliationStore(tmp_path/'reconciliations'),
        ordered_batch=intraday_review_ordered_batch, wo09=store, futures=FuturesStore(tmp_path/'futures'),
        calendar=object(), clock=lambda:run.analysis_boundary, wo08=owner.store, native=native.store)
    return run, records, boundary, IntradayWo09Application(store, eligibility=boundary)


def test_new_assessment_publishes_without_any_visual_owner_read(tmp_path, monkeypatch):
    run, records, boundary, app = graph(tmp_path)
    def forbidden(*args, **kwargs):
        pytest.fail('retired visual owner accessed')
    for owner in (boundary.review, boundary.paired, boundary.reconciliation):
        monkeypatch.setattr(owner, 'page_read_scope', forbidden)
    readiness, requirements = app.evaluate_wo08(records[0], created_at=run.analysis_boundary)
    assert isinstance(readiness, MachineReadinessRecord)
    assert readiness.satisfied_count is readiness.outstanding_count is None
    assert readiness.readiness_state in {ReadinessState.READINESS_UNAVAILABLE, ReadinessState.HARD_GATE}
    assert len(requirements) == 5 and readiness.wo07f_identity is None
    assert b'wo07f_identity' not in artifact_bytes(readiness)
    assert b'answer_pack_identity' not in artifact_bytes(readiness)
    assert Wo09Store(app.store.root).restore_current()[0][1] == readiness
    original = {str(p):p.read_bytes() for p in app.store.root.rglob('*.json')}
    app.evaluate_wo08(records[0], created_at=run.analysis_boundary)
    assert original == {str(p):p.read_bytes() for p in app.store.root.rglob('*.json')}
    with pytest.raises(ValueError, match='CRITERIA_NOT_ESTABLISHED'):
        app.create_handoff(readiness, created_at=run.analysis_boundary)
    assert not app.store.handoffs.exists()


def test_entire_unavailable_population_reaches_truthful_readiness(tmp_path):
    run, records, boundary, app = graph(tmp_path, all_unavailable=True)
    for assessment in records:
        readiness, _ = app.evaluate_wo08(assessment, created_at=run.analysis_boundary)
        assert readiness.satisfied_count is None
    assert len(app.restore()) == 98
    assert not boundary.review.root.exists()


def test_capture_rechecks_wo08_generation_before_pointer_mutation(tmp_path):
    run, records, boundary, app = graph(tmp_path)
    expected = boundary.capture_wo08(assessment=records[0], created_at=run.analysis_boundary)
    pointer = boundary.wo08.current_pointer()
    pointer['generation'] += 1
    pointer['integrity_sha256'] = digest({k:v for k,v in pointer.items() if k != 'integrity_sha256'})
    (boundary.wo08.root/'current.json').write_bytes(canonical(pointer))
    with pytest.raises(ValueError, match='SOURCE_SUPERSEDED'):
        with boundary.final_readiness(expected):
            pytest.fail('stale generation published')
    assert app.store.load_pointer(records[0].data['subject']) is None


def test_current_manifest_integrity_mismatch_is_not_analytical_negative(tmp_path):
    run, records, boundary, app = graph(tmp_path)
    pointer = boundary.wo08.current_pointer()
    pointer['manifest_integrity'] = '0'*64
    pointer['integrity_sha256'] = digest({k:v for k,v in pointer.items() if k != 'integrity_sha256'})
    (boundary.wo08.root/'current.json').write_bytes(canonical(pointer))
    with pytest.raises(ValueError, match='CURRENT_MANIFEST_MISMATCH'):
        app.evaluate_wo08(records[0], created_at=run.analysis_boundary)
    assert not app.store.current.exists()


def test_all_writer_expectation_is_not_recaptured_for_machine_successor(tmp_path):
    run, records, boundary, app = graph(tmp_path)
    readiness, requirements = app.evaluate_wo08(records[0], created_at=run.analysis_boundary)
    expected = boundary.capture_wo08(assessment=records[0], created_at=run.analysis_boundary)
    app.store.mark_currentness(readiness.canonical_subject_identity, CurrentnessState.REASSESSMENT_DUE,
        updated_at=run.analysis_boundary+timedelta(seconds=1), expected=app.store.expectation(readiness.canonical_subject_identity))
    with pytest.raises(Wo09PublicationConflict):
        with boundary.final_readiness(expected) as mutation:
            mutation.retain_readiness(readiness, requirements)
    assert app.store.load_pointer(readiness.canonical_subject_identity).currentness is CurrentnessState.REASSESSMENT_DUE


def test_historical_readiness_bytes_and_mixed_restore_preserved(tmp_path):
    from tests.unit.intraday.test_wo09_readiness import evaluated
    run, records, boundary, app = graph(tmp_path)
    historical, requirements = evaluated()
    original = artifact_bytes(historical)
    app.store.retain(historical, requirements, expected=app.store.expectation(historical.canonical_subject_identity))
    app.evaluate_wo08(records[0], created_at=run.analysis_boundary)
    assert artifact_bytes(app.store.load_readiness(historical.readiness_identity)) == original
    assert any(record == historical for _,record in app.restore())
    assert not any(path.exists() for path in (boundary.review.root,boundary.reconciliation.root))


def test_machine_unavailable_has_no_notification_even_without_opportunity(tmp_path):
    from kronos.application.intraday_notification_sources import ready
    from kronos.application.intraday_wo09_notifications import project_notification
    from kronos.application.intraday_notifications import IntradayNotifications
    run, records, _, app = graph(tmp_path, all_unavailable=True)
    readiness, _ = app.evaluate_wo08(records[0], created_at=run.analysis_boundary)
    assert ready(None,readiness) is None and project_notification(readiness) is None
    service = object.__new__(IntradayNotifications)
    service._origins = {}; service.wo09 = app.store
    service._consume('READINESS',readiness.readiness_identity)


def test_composed_successor_refuses_new_historical_visual_authority_before_visual_access(tmp_path):
    from tests.unit.intraday.test_wo09_readiness import evaluated
    _, _, boundary, _ = graph(tmp_path)
    historical, _ = evaluated()
    with pytest.raises(ValueError, match='WO07F_NEW_WORK_RETIRED'):
        boundary.capture_readiness(record=None,semantic=None,selection=None,visual=None,created_at=None)
    with pytest.raises(ValueError, match='WO07F_NEW_WORK_RETIRED'):
        boundary._source(historical,'futures')
    with pytest.raises(ValueError, match='WO11_NEW_WORK_WO07F_NEW_WORK_RETIRED'):
        boundary._source(historical,'lifecycle')
    assert not boundary.review.root.exists()


def test_assessment_cannot_be_retimestamped_into_another_readiness(tmp_path):
    run, records, _, app = graph(tmp_path)
    with pytest.raises(ValueError, match='PUBLICATION_TIME_MISMATCH'):
        app.evaluate_wo08(records[0], created_at=run.analysis_boundary+timedelta(seconds=1))
    assert not app.store.current.exists()


def test_machine_readiness_storage_failure_never_claims_current_publication(tmp_path, monkeypatch):
    run, records, boundary, app = graph(tmp_path)
    def failed(*args, **kwargs):
        raise OSError('isolated unavailable storage')
    monkeypatch.setattr(app.store, '_atomic', failed)
    with pytest.raises(OSError, match='unavailable storage'):
        app.evaluate_wo08(records[0], created_at=run.analysis_boundary)
    assert app.store.load_pointer(records[0].data['subject']) is None
    assert boundary.wo08.load(records[0].identity) == records[0]
    assert not app.store.handoffs.exists()
