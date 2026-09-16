"""WO-07 real route dispatch against isolated stores; no production operations."""
from threading import Thread
from urllib.parse import urlencode

import pytest

from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.browser.server import create_browser_server
from kronos.swing.v1.mcx_supporting_context import McxContextSlot
from kronos.swing.v1.review_evidence_store import ReviewEvidenceStore
from kronos.swing.v1.review_evidence_binding import ReviewMutationPrecondition
from tests.unit.application.test_swing_opportunities import _Provider
from tests.unit.browser.test_browser_server import _request
from tests.unit.swing.test_run_publication import checkpoint, scenario
from tests.unit.swing.v1.test_mcx_supporting_context import (
    DAY, PNG, _transport, _answer, _payload, _inventory,
)


def test_workspace_diagnostics_preserve_bounded_reason_not_exception_payload():
    from kronos.application.swing_visual_v3_live import NativeReviewIntakeWorkflow
    from kronos.swing.v1.review_evidence_binding import ReviewEvidenceError
    reason = NativeReviewIntakeWorkflow._reason
    assert reason(ReviewEvidenceError('REVIEW_ARTIFACT_DIGEST_MISMATCH'), 'REVIEW_RESTORATION_UNAVAILABLE') == 'REVIEW_ARTIFACT_DIGEST_MISMATCH'
    assert reason(ValueError('SYNTHETIC private path /not-for-display'), 'REVIEW_RESTORATION_UNAVAILABLE') == 'REVIEW_RESTORATION_UNAVAILABLE'


def _current_twelve(workflow):
    """Synthetic exact production-shaped population; never read live evidence."""
    from dataclasses import replace
    from types import SimpleNamespace
    from hashlib import sha256
    from kronos.swing.v1.native_discovery import NativeProductPath, Native1WState, NativeDiscoveryStatus
    from kronos.swing.v1.models import V1Direction
    from tests.unit.swing.v1.test_native_review import _evidence_run
    facts, base, probable = _evidence_run()
    names = ('DRREDDY', 'TCS', 'ASIANPAINT', 'TMPV', 'ADANIGREEN', 'ADANIENT',
             'RELIANCE', 'BAJFINANCE', 'UPL', 'VBL', 'GOLDM', 'CRUDEOIL')
    run_id = 'SWING-RUN-' + 'D' * 32
    facts = replace(facts, run_identity=run_id, instruments=tuple(
        replace(item, reference_facts=(), one_hour_atr=None) for item in facts.instruments))
    assessments = []
    for item in base.assessments:
        if item.canonical_instrument not in names:
            assessments.append(replace(item, run_identity=run_id, status=NativeDiscoveryStatus.NO_CURRENT_OPPORTUNITY))
            continue
        mcx = item.canonical_instrument in {'GOLDM', 'CRUDEOIL'}
        assessments.append(replace(probable, run_identity=run_id, canonical_instrument=item.canonical_instrument,
            product_path=NativeProductPath.MCX if mcx else NativeProductPath.NSE,
            direction=V1Direction.LONG if mcx else V1Direction.SHORT,
            weekly_state=Native1WState.NOT_APPLICABLE if mcx else Native1WState.NEUTRAL,
            result_sha256=sha256(item.canonical_instrument.encode()).hexdigest()))
    run = replace(base, run_identity=run_id, assessments=tuple(assessments))
    roots = tuple(SimpleNamespace(canonical_instrument=name, opportunity_id=None, material_revision=None,
        qualification=SimpleNamespace(validity='MANUAL_REVIEW_REQUIRED', reason='ANALYTICAL_ROOT_UNCERTAIN'),
        disposition=SimpleNamespace(value='MANUAL_REVIEW_REQUIRED'), reason='ANALYTICAL_ROOT_UNCERTAIN',
        latest_material_at=facts.observed_at, last_analysis_checked=facts.observed_at)
        for name in ('TMPV', 'ADANIGREEN', 'BAJFINANCE'))
    continuity = SimpleNamespace(contribution=SimpleNamespace(rows=roots))
    state = {'native': run, 'facts': facts, 'control': {'current_manifest': {'sha256': 'a' * 64}}, 'failed': False}
    workflow.application.opportunities_bundle_projection = lambda: (None, state['native'], continuity,
        dict(control=state['control'], reconciliation_unavailable=state['failed']))
    workflow.application.mtf_fact_snapshot = lambda: state['facts']
    return state, names


@pytest.mark.parametrize('native_intake', ['NSE'], indirect=True)
def test_current_twelve_old_review_pure_exact_workspace(native_intake, tmp_path, monkeypatch):
    from kronos.swing.v1.native_review import build_native_review_requirements
    from kronos.browser.views import _receipt_native_review
    workflow = native_intake
    old = workflow.native_review.snapshot()
    state, names = _current_twelve(workflow)
    assert old.native_run_identity != state['native'].run_identity
    before = _inventory(tmp_path)
    for name in ('prepare', 'refresh', 'restore'):
        monkeypatch.setattr(workflow.native_review, name, lambda *a, **k: pytest.fail('historical Review mutated'))
    monkeypatch.setattr(workflow.live.cycle, 'complete', lambda *a, **k: pytest.fail('downstream invoked'))
    expected = {r.canonical_instrument:r for r in build_native_review_requirements(state['native'], state['facts'])}
    for _ in range(3):
        result = workflow.snapshot()
        assert result['error'] is None
        assert result['workspace']['nse'] == 10 and result['workspace']['mcx'] == 2
        assert {r['instrument'] for r in result['rows']} == set(names)
        for row in result['rows']:
            requirement = expected[row['instrument']]
            assert row['eligible'] and row['expected'] and row['evidence'] == 'MISSING'
            assert row['requirement_sha256'] == requirement.requirement_sha256
            assert row['assessment_sha256'] == requirement.thesis.native_assessment_sha256
            assert row['expected'][row['instrument']]['expected_run_identity'] == state['native'].run_identity
            if row['instrument'] in {'TMPV', 'ADANIGREEN', 'BAJFINANCE'}:
                assert row['continuity'].opportunity_id is None and row['continuity'].material_revision is None
        page = _receipt_native_review(result)
        for text in ('Current Review workspace', 'NSE REVIEW', 'MCX REVIEW', 'CHART MISSING',
                     'ANSWER MISSING', 'ANALYTICAL ROOT UNCERTAIN', 'MANUAL REVIEW REQUIRED'):
            assert text in page
        for text in ('RETRY DOWNSTREAM', 'RECONCILE', 'Readiness ·', 'KR-370 ·'):
            assert text not in page
    assert workflow.native_review.snapshot() == old
    assert _inventory(tmp_path) == before


@pytest.mark.parametrize('native_intake', ['NSE'], indirect=True)
def test_individual_ineligible_requirement_has_no_chart_target(native_intake, tmp_path):
    from dataclasses import replace
    from kronos.browser.views import _receipt_native_review
    from kronos.swing.v1.review_evidence_binding import ReviewEvidenceError
    state, _ = _current_twelve(native_intake)
    state['native'] = replace(state['native'], assessments=tuple(
        replace(a, operative_anchor=None) if a.canonical_instrument == 'TMPV' else a
        for a in state['native'].assessments))
    before = _inventory(tmp_path)
    result = native_intake.snapshot()
    assert result['workspace']['eligible'] == 11 and result['workspace']['excluded'] == 1
    row = next(r for r in result['rows'] if r['instrument'] == 'TMPV')
    assert not row['eligible'] and row['expected'] is None and not row['selected']
    assert row['error'] == 'NATIVE_REVIEW_ASSESSMENT_INELIGIBLE'
    page = _receipt_native_review(result)
    assert 'REVIEW INELIGIBLE' in page and 'Paste TMPV' not in page
    with pytest.raises(ReviewEvidenceError, match='REVIEW_REQUEST_MISMATCH'):
        native_intake.expected('NSE', ('TMPV',))
    assert _inventory(tmp_path) == before


@pytest.mark.parametrize('native_intake', ['NSE'], indirect=True)
@pytest.mark.parametrize('fault,reason', [
    ('control', 'SWING_PUBLICATION_CURRENT_UNAVAILABLE'), ('manifest', 'SWING_PUBLICATION_BUNDLE_INVALID'),
    ('native', 'NATIVE_DISCOVERY_RUN_INVALID'), ('facts', 'MTF_FACT_SNAPSHOT_INVALID'),
    ('mismatch', 'NATIVE_REVIEW_SAME_RUN_BINDING_INVALID'), ('failed', 'REVIEW_BINDING_STALE'),
    ('corrupt', 'SWING_PUBLICATION_BUNDLE_INVALID'), ('race', 'REVIEW_BINDING_STALE')])
def test_current_workspace_invalid_binding_fails_closed(native_intake, tmp_path, fault, reason):
    from dataclasses import replace
    from types import SimpleNamespace
    state, _ = _current_twelve(native_intake)
    if fault == 'control': state['control'] = None
    elif fault == 'manifest': state['control']['current_manifest'] = None
    elif fault == 'native': state['native'] = None
    elif fault == 'facts': state['facts'] = None
    elif fault == 'mismatch': state['facts'] = replace(state['facts'], run_identity='SWING-RUN-' + 'E' * 32)
    elif fault == 'failed': state['failed'] = True
    elif fault == 'corrupt':
        native_intake.application.native_discovery_evidence_store = lambda: SimpleNamespace(load=lambda _: None)
    else:
        original = native_intake.application.mtf_fact_snapshot
        def raced():
            state['control'] = {'current_manifest': {'sha256': 'b' * 64}}
            return original()
        native_intake.application.mtf_fact_snapshot = raced
    before = _inventory(tmp_path)
    result = native_intake.snapshot()
    assert result['error'] == reason and not result['rows'] and result['workspace'] is None
    assert _inventory(tmp_path) == before


@pytest.fixture(params=["NSE", "GOLDM", "SILVERM", "COPPER", "CRUDEOIL", "NATURALGAS"])
def native_intake(tmp_path, request):
    from contextlib import contextmanager
    from types import SimpleNamespace
    from kronos.application.swing_visual_v3_live import NativeReviewIntakeWorkflow
    from tests.unit.browser.test_swing_visual_v3_live import _live
    from tests.unit.swing.v1.test_native_review import _evidence_run
    native, facts, live = _live(tmp_path)
    run = _evidence_run()[1]
    if request.param == "NSE-BATCH":
        from tests.unit.swing.v1.test_pdf_visual_review import _workflow
        native, _ = _workflow(tmp_path / "batch-native", candidate_count=2)
        from dataclasses import replace
        probable = run.assessments[0]
        run = replace(run, assessments=tuple(replace(item,
            direction=probable.direction, weekly_state=probable.weekly_state,
            daily_state=probable.daily_state, four_hour_state=probable.four_hour_state,
            one_hour_state=probable.one_hour_state, status=probable.status,
            context_kind=probable.context_kind, opportunity_identity=probable.opportunity_identity,
            operative_anchor=probable.operative_anchor, reason_codes=("PDF_REVIEW_TEST_PROBABLE",),
            result_sha256=f"{index:064x}") if index <= 2 else item
            for index, item in enumerate(run.assessments, 1)), result_sha256="c" * 64)
    elif request.param != "NSE":
        from kronos.application.swing_native_review import NativeReviewWorkflow
        from kronos.swing.v1.native_review import NativeReviewEvidenceStore
        from kronos.swing.v1.evidence_store import LocalTradingViewEvidenceStore
        from tests.unit.swing.v1.test_native_review_mcx_reference import _run_with_probables
        facts, run = _run_with_probables(request.param)
        native = NativeReviewWorkflow(NativeReviewEvidenceStore(tmp_path / "mcx-native"),
            chart_store=LocalTradingViewEvidenceStore(tmp_path / "mcx-charts"))
        native.prepare(run, facts)
    manifest = "a" * 64
    @contextmanager
    def guard():
        yield SimpleNamespace(control={"current_manifest": {"sha256": manifest}},
                              manifest={"run_id": facts.run_identity})
    application = SimpleNamespace(
        opportunities_bundle_projection=lambda: (None, run, None,
            dict(control={"current_manifest": {"sha256": manifest}}, reconciliation_unavailable=False)),
        mtf_fact_snapshot=lambda: facts, publication_mutation_guard=guard)
    workflow = NativeReviewIntakeWorkflow(application, native, live, ReviewEvidenceStore(tmp_path / "intake"))
    return workflow


def test_native_prospective_chart_selection_generation_and_stale_tabs(native_intake, tmp_path):
    from kronos.swing.v1.review_evidence_binding import ReviewEvidenceError
    workflow = native_intake
    market = "NSE" if workflow.native_review.snapshot().requirements[0].thesis.product_path.name == "NSE" else "MCX"
    for market in (market,):
        instrument = workflow._requirements(market)[0].canonical_instrument
        expected = workflow.expected(market, (instrument,))
        for role in workflow._roles(market):
            workflow.stage(market, instrument, role, workflow.expected(market, (instrument,)), image=PNG, content_type="image/png")
        before = _inventory(tmp_path)
        with pytest.raises(ReviewEvidenceError, match="REVIEW_BINDING_STALE"):
            workflow.stage(market, instrument, workflow._roles(market)[0], expected, image=PNG, content_type="image/png")
        assert _inventory(tmp_path) == before
        publication = workflow.generate(market, workflow.expected(market, (instrument,)))
        assert publication == workflow._publication(market)
        assert workflow.snapshot()['rows'][0]['question_ready']
        mapping = workflow._mapping(publication, market)
        assert mapping["subjects"][0]["canonical_instrument"] == instrument
        frames = [item["timeframe"] for item in mapping["subjects"][0]["responses"]]
        assert frames == (["1W", "1D", "4H", "1H"] if market == "NSE" else ["1D", "4H", "1H"])
        before = _inventory(tmp_path)
        for _ in range(3):
            workflow.expected(market, (instrument,))
            assert workflow._publication(market) == publication
        assert _inventory(tmp_path) == before
        # Retaining the old PDF does not make a changed chart request-ready.
        workflow.stage(market, instrument, workflow._roles(market)[0],
                       workflow.expected(market, (instrument,)))
        projection = workflow.snapshot()
        assert not projection['rows'][0]['question_ready']
        assert projection['packages'][0]['expected'] is None


def _native_market(workflow):
    return "NSE" if workflow.native_review.snapshot().requirements[0].thesis.product_path.name == "NSE" else "MCX"


def _native_answer(workflow, market, publication):
    from tests.unit.swing.v1.test_review_evidence_binding import nse_answer
    from tests.unit.swing.v1.test_mcx_native_visual_contract import answer_for
    from kronos.swing.v1.mcx_native_visual_contract import mcx_question_pack_from_mappings
    if market == "MCX":
        answer = answer_for(mcx_question_pack_from_mappings(publication.native, publication.reference))
        for response, requested in zip(answer["subjects"][0]["responses"], publication.native.value["subjects"][0]["responses"], strict=True):
            if requested["governed_reference_basis_availability"] == "UNAVAILABLE":
                observation = response["observations"][3]
                observation.update(observation_status="UNAVAILABLE", ambiguity_reason="Governed reference basis unavailable")
                observation["result"].update(presence="NOT_IDENTIFIABLE", relationship="NOT_OBSERVABLE", interaction="NOT_OBSERVABLE")
        return answer
    from types import SimpleNamespace
    value = nse_answer(publication.mapping)
    value["subjects"] = []
    for subject in publication.mapping.value["subjects"]:
        candidate = nse_answer(SimpleNamespace(value=dict(publication.mapping.value, subjects=[subject]),
            request_reference=publication.mapping.request_reference))["subjects"][0]
        for response in candidate["responses"]:
            response["chart_revision_sha256"] = subject["chart_revision_sha256"]
            for observation in response["observations"]:
                observation["source_chart_revision"] = subject["chart_revision_sha256"]
        value["subjects"].append(candidate)
    return value


def _stage_native(workflow, market, instrument):
    for role in workflow._roles(market):
        workflow.stage(market, instrument, role, workflow.expected(market, (instrument,)), image=PNG, content_type="image/png")


def _guard_scope_spies(monkeypatch, owner, method="publication_mutation_guard"):
    from contextlib import contextmanager
    import json
    from pypdf import PdfReader
    from kronos.swing.v1 import review_evidence_binding as binding
    from kronos.swing.v1 import review_evidence_store as store
    held = [False]
    original_guard = getattr(owner, method)

    @contextmanager
    def guarded():
        with original_guard() as snapshot:
            assert not held[0]
            held[0] = True
            try:
                yield snapshot
            finally:
                held[0] = False

    monkeypatch.setattr(owner, method, guarded)

    def protect(owner, name):
        original = getattr(owner, name)
        def outside(*args, **kwargs):
            assert not held[0], f"{name} executed under WO-05"
            assert not store._INTAKE_HELD.get(), f"{name} executed under WO-07"
            return original(*args, **kwargs)
        monkeypatch.setattr(owner, name, outside)

    protect(json, "loads")
    protect(PdfReader, "__init__")
    for cls in (binding.ReviewAcceptanceReceipt, binding.NseReviewRequestMapping,
                store.ReviewAcceptanceCommit, store.ReviewDownstreamAttempt,
                store.NseRequestPublication, store.McxRequestPublication):
        protect(cls, "__post_init__")
    for name in ("load_request", "load_current_request", "load_mcx_request", "load_current_mcx_request",
                 "acceptance_history", "native_chart_selection", "load_acceptance", "downstream_attempts"):
        protect(store.ReviewEvidenceStore, name)
    return held, protect


@pytest.mark.parametrize("native_intake", ["NSE", "GOLDM"], indirect=True)
def test_native_guard_scope_parsers_constructors_and_downstream_are_unlocked(native_intake, tmp_path, monkeypatch):
    from tests.unit.browser.test_swing_visual_v3_live import _answer_pdf
    workflow = native_intake
    market = _native_market(workflow)
    instrument = workflow._requirements(market)[0].canonical_instrument
    held, protect = _guard_scope_spies(monkeypatch, workflow.application)
    from kronos.application import swing_visual_v3 as cycle_module
    protect(cycle_module, "create_native_readiness_record_v3")
    protect(cycle_module, "evaluate_kr370_analytical_promotion")
    for name in ("current_state", "_history", "_selection", "_prepared"):
        protect(workflow, name)
    for name in ("prepare", "retain", "restore_persisted", "complete"):
        if market == "MCX":
            monkeypatch.setattr(workflow.live.cycle, name, lambda *_a, **_k: pytest.fail("MCX downstream"))
        else:
            protect(workflow.live.cycle, name)
    _stage_native(workflow, market, instrument)
    publication = workflow.generate(market, workflow.expected(market, (instrument,)))
    path = tmp_path / "guard-answer.pdf"
    _answer_pdf(path, _native_answer(workflow, market, publication))
    commit = workflow.import_answer(market, workflow.expected(market, (instrument,)), path.read_bytes())
    row = workflow.snapshot()["rows"][0]
    assert row["evidence"] == "ACCEPTED"
    assert row["downstream"] == ("SUCCEEDED" if market == "NSE" else "UNSUPPORTED_CONTRACT")
    before = _inventory(tmp_path)
    assert workflow.import_answer(market, workflow.expected(market, (instrument,)), path.read_bytes()) == commit
    workflow.restore()
    assert _inventory(tmp_path) == before
    assert not held[0]


@pytest.mark.parametrize("native_intake", ["NSE"], indirect=True)
@pytest.mark.parametrize("changed", ["control", "immutable", "publication"])
def test_native_guard_scope_exact_prepare_to_lock_fence_publishes_nothing(native_intake, tmp_path, monkeypatch, changed):
    from contextlib import contextmanager
    from types import SimpleNamespace
    from kronos.swing.v1.review_evidence_binding import ReviewEvidenceError
    workflow = native_intake
    instrument = workflow._requirements("NSE")[0].canonical_instrument
    _stage_native(workflow, "NSE", instrument)
    expected = workflow.expected("NSE", (instrument,))
    original_guard = workflow.application.publication_mutation_guard
    raced = []

    @contextmanager
    def guard():
        # Preparation already selected and validated these exact bytes. Change
        # them at admission, not during PDF extraction or before preparation.
        if changed != "publication":
            path = next(workflow.store.root.glob("current-chart-*.json")) if changed == "control" else next(
                (workflow.store.root / "chart-images").iterdir())
            path.write_bytes(path.read_bytes() + b" ")
        raced.append(_inventory(tmp_path))
        with original_guard() as snapshot:
            if changed == "publication":
                snapshot = SimpleNamespace(control={"current_manifest": {"sha256": "b" * 64}},
                                           manifest=snapshot.manifest)
            yield snapshot

    monkeypatch.setattr(workflow.application, "publication_mutation_guard", guard)
    with pytest.raises(ReviewEvidenceError, match="REVIEW_BINDING_STALE"):
        workflow.generate("NSE", expected)
    assert len(raced) == 1
    assert _inventory(tmp_path) == raced[0]
    assert not (workflow.store.root / "current-request.json").exists()


@pytest.mark.parametrize("native_intake", ["NSE"], indirect=True)
def test_native_guard_scope_absent_acceptance_is_not_a_wildcard(native_intake, tmp_path, monkeypatch):
    from contextlib import contextmanager
    from tests.unit.browser.test_swing_visual_v3_live import _answer_pdf
    from kronos.swing.v1.review_evidence_binding import ReviewEvidenceError
    workflow = native_intake
    instrument = workflow._requirements("NSE")[0].canonical_instrument
    _stage_native(workflow, "NSE", instrument)
    publication = workflow.generate("NSE", workflow.expected("NSE", (instrument,)))
    path = tmp_path / "race-acceptance.pdf"
    _answer_pdf(path, _native_answer(workflow, "NSE", publication))
    expected = workflow.expected("NSE", (instrument,))
    original_guard = workflow.application.publication_mutation_guard
    raced = []

    @contextmanager
    def guard():
        monkeypatch.setattr(workflow.application, "publication_mutation_guard", original_guard)
        workflow.import_answer("NSE", expected, path.read_bytes())
        raced.append(_inventory(tmp_path))
        with original_guard() as snapshot:
            yield snapshot

    monkeypatch.setattr(workflow.application, "publication_mutation_guard", guard)
    with pytest.raises(ReviewEvidenceError, match="REVIEW_BINDING_STALE"):
        workflow.generate("NSE", expected)
    assert len(raced) == 1 and _inventory(tmp_path) == raced[0]
    assert workflow._publication("NSE") == publication


def test_native_receipt_browser_owner_acceptance_replay_restoration_and_purity(native_intake, tmp_path, monkeypatch):
    from kronos.application.swing_visual_v3_live import NativeReviewIntakeWorkflow
    from tests.unit.browser.test_swing_visual_v3_live import _answer_pdf
    workflow = native_intake
    market = _native_market(workflow)
    instrument = workflow._requirements(market)[0].canonical_instrument
    if market == "MCX":
        for name in ("prepare", "retain", "restore_persisted", "complete"):
            monkeypatch.setattr(workflow.live.cycle, name, lambda *_args, **_kwargs: pytest.fail("MCX consumer invoked"))
    _stage_native(workflow, market, instrument)
    publication = workflow.generate(market, workflow.expected(market, (instrument,)))
    workflow.export_question(market, publication)
    path = workflow.live.transport.configuration.answer_directory / workflow.filenames(workflow._mapping(publication, market))[1]
    _answer_pdf(path, _native_answer(workflow, market, publication))
    commit = workflow.import_from_directory(market, workflow.expected(market, (instrument,)))
    assert len(commit.receipts) == 1
    row = workflow.snapshot()["rows"][0]
    assert row["evidence"] == "ACCEPTED"
    assert row["downstream"] == ("SUCCEEDED" if market == "NSE" else "UNSUPPORTED_CONTRACT")
    before = _inventory(tmp_path)
    assert workflow.import_from_directory(market, workflow.expected(market, (instrument,))) == commit
    assert _inventory(tmp_path) == before
    from kronos.application.swing_visual_v3 import SwingVisualV3ReviewCycle
    from kronos.application.swing_visual_v3_live import SwingVisualV3LiveWorkflow
    from kronos.swing.v1.visual_evidence_v3 import LocalVisualEvidenceV3Store
    from kronos.swing.v1.native_readiness_v3 import NativeLayer2ReadinessV3Store
    cold_cycle = SwingVisualV3ReviewCycle(LocalVisualEvidenceV3Store(tmp_path / "visual-v3"),
        NativeLayer2ReadinessV3Store(tmp_path / "readiness-v3"))
    cold_live = SwingVisualV3LiveWorkflow(cold_cycle, workflow.live.transport, clock=workflow.live._clock,
                                        recover_historical=False)
    if market == "MCX":
        for name in ("prepare", "retain", "restore_persisted", "complete"):
            monkeypatch.setattr(cold_cycle, name, lambda *_args, **_kwargs: pytest.fail("MCX restoration consumer invoked"))
    restored = NativeReviewIntakeWorkflow(workflow.application, workflow.native_review, cold_live, workflow.store)
    restored.restore()
    assert not restored.errors
    for _ in range(3):
        assert restored.snapshot() == workflow.snapshot()
    assert _inventory(tmp_path) == before


def _accepted_native(workflow, tmp_path):
    from tests.unit.browser.test_swing_visual_v3_live import _answer_pdf
    market = _native_market(workflow)
    instrument = workflow._requirements(market)[0].canonical_instrument
    _stage_native(workflow, market, instrument)
    publication = workflow.generate(market, workflow.expected(market, (instrument,)))
    path = tmp_path / "CONTROLLED_NATIVE_ANSWER.pdf"
    answer = _native_answer(workflow, market, publication)
    _answer_pdf(path, answer)
    commit = workflow.import_answer(market, workflow.expected(market, (instrument,)), path.read_bytes())
    return market, instrument, publication, path, answer, commit


@pytest.mark.parametrize("native_intake", ["NSE", "GOLDM"], indirect=True)
def test_native_successor_replaced_stale_and_invalid_attempt_preserve_acceptance(native_intake, tmp_path):
    from datetime import timedelta
    from kronos.swing.v1.review_evidence_binding import ReviewEvidenceError
    from tests.unit.browser.test_swing_visual_v3_live import _answer_pdf
    workflow = native_intake
    market, instrument, publication, path, answer, first = _accepted_native(workflow, tmp_path)
    before = _inventory(tmp_path)
    with pytest.raises(ReviewEvidenceError):
        workflow.import_answer(market, workflow.expected(market, (instrument,)), b"invalid PDF")
    assert _inventory(tmp_path) == before
    assert workflow.snapshot()["rows"][0]["evidence"] == "ACCEPTED"
    answer["answer_identity"] += "-CHANGED"
    _answer_pdf(path, answer)
    before = _inventory(tmp_path)
    with pytest.raises(ReviewEvidenceError, match="REVIEW_PREDECESSOR_INVALID"):
        workflow.import_answer(market, workflow.expected(market, (instrument,)), path.read_bytes())
    assert _inventory(tmp_path) == before
    instant = workflow.live._now() + timedelta(seconds=1)
    workflow.live._clock = lambda: instant
    successor = workflow.generate(market, workflow.expected(market, (instrument,)))
    assert workflow.snapshot()["rows"][0]["evidence"] == "STALE"
    if market == "NSE":
        assert not workflow.downstream_applicable(workflow.live.cycle.completed_for(
            workflow._context()[1].run_identity, instrument))
    answer = _native_answer(workflow, market, successor)
    answer["answer_identity"] += "-SUCCESSOR"
    _answer_pdf(path, answer)
    second = workflow.import_answer(market, workflow.expected(market, (instrument,)), path.read_bytes())
    assert second.receipts[0].body["predecessor_receipt_id"] == first.receipts[0].receipt_id
    row = workflow.snapshot()["rows"][0]
    assert row["evidence"] == "ACCEPTED" and row["replaced"] == (first.receipts[0].receipt_id,)
    stale = workflow.expected(market, (instrument,))
    workflow.stage(market, instrument, workflow._roles(market)[0], stale)
    assert workflow.snapshot()["rows"][0]["evidence"] == "STALE"
    with pytest.raises(ReviewEvidenceError, match="REVIEW_BINDING_STALE"):
        workflow.generate(market, stale)


@pytest.mark.parametrize("native_intake", ["NSE", "GOLDM"], indirect=True)
@pytest.mark.parametrize("artifact", ["receipt", "answer", "structured", "request", "question", "pointer"])
def test_native_corrupt_graph_never_restores_or_repairs(native_intake, tmp_path, monkeypatch, artifact):
    workflow = native_intake
    market, instrument, publication, _, _, commit = _accepted_native(workflow, tmp_path)
    receipt = commit.receipts[0]
    paths = dict(receipt=commit.value["receipts"][0]["relative_path"],
        answer=receipt.body["answer"]["retained_relative_path"],
        structured=receipt.body["structured_evidence"][0]["retained_relative_path"],
        request=(publication.value["request_mapping_artifact"]["relative_path"] if market == "NSE"
                 else publication.value["reference_mapping_relative_path"]),
        question=(publication.value["question_pdf_artifact"]["relative_path"] if market == "NSE"
                  else publication.value["question_pdf_relative_path"]),
        pointer="acceptance-current/" + commit.value["package_key"] + ".json")
    (workflow.store.root / paths[artifact]).write_bytes(b"SYNTHETIC TAMPER")
    monkeypatch.setattr(workflow, "handoff", lambda *_a, **_k: pytest.fail("Invalid graph reached handoff"))
    before = _inventory(tmp_path)
    workflow.restore()
    assert workflow.errors[(market, None)] == "REVIEW_RESTORATION_UNAVAILABLE"
    assert workflow.snapshot()["rows"][0]["evidence"] == "INVALID"
    assert _inventory(tmp_path) == before


@pytest.mark.parametrize("native_intake", ["NSE", "GOLDM"], indirect=True)
@pytest.mark.parametrize("operation", ["REMOVE", "REPLACE", "GENERATE"])
def test_native_import_rechecks_chart_and_request_races(native_intake, tmp_path, monkeypatch, operation):
    import kronos.application.swing_visual_v3_live as module
    from kronos.swing.v1.review_evidence_binding import ReviewEvidenceError
    from tests.unit.browser.test_swing_visual_v3_live import _answer_pdf
    workflow = native_intake
    market = _native_market(workflow)
    instrument = workflow._requirements(market)[0].canonical_instrument
    _stage_native(workflow, market, instrument)
    publication = workflow.generate(market, workflow.expected(market, (instrument,)))
    path = tmp_path / "CONTROLLED_RACING_ANSWER.pdf"
    _answer_pdf(path, _native_answer(workflow, market, publication))
    original = module.extract_successor_answer_pdf
    def racing_capture(payload):
        captured = original(payload)
        expected = workflow.expected(market, (instrument,))
        if operation == "REMOVE":
            workflow.stage(market, instrument, workflow._roles(market)[0], expected)
        elif operation == "REPLACE":
            from tests.unit.swing.v1.test_pdf_visual_review import _png
            workflow.stage(market, instrument, workflow._roles(market)[0], expected,
                           image=_png(instrument), content_type="image/png")
        else:
            workflow.generate(market, expected)
        return captured
    monkeypatch.setattr(module, "extract_successor_answer_pdf", racing_capture)
    # Changed bytes fail the exact retained request/chart digest check before
    # publication; missing selection and changed request use the stale gates.
    expected_error = ("REVIEW_ARTIFACT_DIGEST_MISMATCH" if operation == "REPLACE"
                      else "REVIEW_BINDING_STALE|REVIEW_ACCEPTANCE_INCOMPLETE")
    with pytest.raises(ReviewEvidenceError, match=expected_error):
        workflow.import_answer(market, workflow.expected(market, (instrument,)), path.read_bytes())
    assert workflow.store.native_acceptance_history(market, workflow._context()[1].run_identity) == ()


@pytest.mark.parametrize("native_intake", ["NSE", "GOLDM"], indirect=True)
@pytest.mark.parametrize("phase,visible", [("before_acceptance_pointer", False), ("after_acceptance_pointer", True)])
def test_native_pointer_fault_and_pending_residue_are_observational(native_intake, tmp_path, monkeypatch, phase, visible):
    from tests.unit.browser.test_swing_visual_v3_live import _answer_pdf
    workflow = native_intake
    market = _native_market(workflow)
    instrument = workflow._requirements(market)[0].canonical_instrument
    _stage_native(workflow, market, instrument)
    publication = workflow.generate(market, workflow.expected(market, (instrument,)))
    path = tmp_path / "CONTROLLED_FAULT_ANSWER.pdf"
    _answer_pdf(path, _native_answer(workflow, market, publication))
    def fault(point):
        if point == phase:
            raise OSError("CONTROLLED POINTER FAULT")
    monkeypatch.setattr(workflow.store, "_fault", fault)
    with pytest.raises(OSError, match="CONTROLLED POINTER FAULT"):
        workflow.import_answer(market, workflow.expected(market, (instrument,)), path.read_bytes())
    before = _inventory(tmp_path)
    workflow.restore()
    row = workflow.snapshot()["rows"][0]
    assert row["evidence"] == ("ACCEPTED" if visible else "MISSING")
    assert row["downstream"] == "NOT_RUN"
    assert workflow.live.cycle.completed_snapshot() == ()
    assert _inventory(tmp_path) == before


@pytest.mark.parametrize("native_intake", ["NSE"], indirect=True)
def test_native_failed_downstream_preserves_receipt_and_explicit_retry(native_intake, tmp_path, monkeypatch):
    workflow = native_intake
    complete = workflow.live.cycle.complete
    def fail(*_args, **_kwargs):
        raise ValueError("CONTROLLED CONSUMER FAILURE")
    monkeypatch.setattr(workflow.live.cycle, "complete", fail)
    market, instrument, _, _, _, commit = _accepted_native(workflow, tmp_path)
    row = workflow.snapshot()["rows"][0]
    assert row["evidence"] == "ACCEPTED" and row["downstream"] == "FAILED"
    before = _inventory(tmp_path)
    workflow.restore()
    assert _inventory(tmp_path) == before
    monkeypatch.setattr(workflow.live.cycle, "complete", complete)
    result = workflow.handoff(commit, commit.receipts[0], expected=workflow.expected(market, (instrument,)))
    assert result.value["state"] == "SUCCEEDED"
    assert workflow.snapshot()["rows"][0]["receipt_id"] == commit.receipts[0].receipt_id
    assert workflow.snapshot()["rows"][0]["supported_result"] is not None


@pytest.mark.parametrize("native_intake", ["NSE-BATCH"], indirect=True)
def test_native_multi_candidate_batch_envelopes_and_atomic_receipts(native_intake, tmp_path):
    from tests.unit.browser.test_swing_visual_v3_live import _answer_pdf
    workflow = native_intake
    instruments = tuple(item.canonical_instrument for item in workflow._requirements("NSE"))
    assert len(instruments) == 2
    for instrument in instruments:
        _stage_native(workflow, "NSE", instrument)
    expected = workflow.expected("NSE", instruments)
    assert len({value["expected_candidate_identity"] for value in expected.values()}) == 2
    publication = workflow.generate("NSE", expected)
    from kronos.swing.v1.pdf_visual_review_v3_live import extract_successor_answer_pdf
    from kronos.swing.v1.review_evidence_binding import canonical, strict_json
    from kronos.swing.v1.visual_evidence_v3 import validate_nse_successor_answer
    printed = strict_json(extract_successor_answer_pdf(workflow.question_bytes("NSE", publication.identity)))
    for subject in printed["subjects"]:
        subject["observed_chart_instrument"] = subject["canonical_instrument"]
    printed["answer_identity"] = "CONTROLLED_PRINTED_EXAMPLE_ONLY"
    assert len(validate_nse_successor_answer(canonical(printed), publication.mapping)) == 2
    path = tmp_path / "CONTROLLED_BATCH_ANSWER.pdf"
    _answer_pdf(path, _native_answer(workflow, "NSE", publication))
    commit = workflow.import_answer("NSE", workflow.expected("NSE", instruments), path.read_bytes())
    assert {item.binding.value["canonical_instrument"] for item in commit.receipts} == set(instruments)
    assert all(item["evidence"] == "ACCEPTED" and item["downstream"] == "SUCCEEDED" for item in workflow.snapshot()["rows"])


def _rendered_form(body, endpoint):
    import re
    from html import unescape
    match = re.search(r'<form method="post" action="([^\"]*' + re.escape(endpoint)
        + r'\?[^\"]*)"><input type="hidden" name="expected" value="([^\"]+)">', body)
    assert match is not None
    return unescape(match[1]), urlencode({"expected": unescape(match[2])})


def test_native_http_wiring_paste_generate_import_stale_and_observational_get(native_intake, tmp_path):
    from kronos.swing.v1.review_evidence_binding import canonical
    from tests.unit.browser.test_swing_visual_v3_live import _answer_pdf
    from tests.unit.browser.test_browser_server import _request_bytes
    workflow = native_intake
    market = _native_market(workflow)
    instrument = workflow._requirements(market)[0].canonical_instrument
    server = create_browser_server(SwingOpportunitiesApplication(_Provider), port=0,
        native_review=workflow.native_review, visual_v3_live=workflow.live)
    server.native_intake = workflow
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    authority = f"127.0.0.1:{server.server_port}"
    headers = {"Host": authority, "Origin": f"http://{authority}", "Content-Type": "image/png"}
    from threading import Event
    finished = Event()
    original_finish = server.finish_sponsor_work
    def finish():
        original_finish()
        finished.set()
    server.finish_sponsor_work = finish
    def request(method, path, **values):
        if method == "POST":
            finished.clear()
        result = _request(server, method, path, **values)
        if method == "POST":
            assert finished.wait(5), "Controlled Sponsor mutation did not finish"
        return result
    def url(endpoint, **extra):
        return "/swing/v1/" + endpoint + "?" + urlencode(dict(market=market,
            expected=canonical(workflow.expected(market, (instrument,))).decode(), **extra))
    try:
        stale = url("native-review-pack")
        for role in workflow._roles(market):
            assert request("POST", url("native-chart", instrument=instrument, role=role),
                            headers=headers, body=PNG)[0] == 303
        before = _inventory(tmp_path)
        status, _, explanation = request("POST", stale, headers=headers)
        assert status == 409 and 'Review intake did not complete' in explanation
        assert 'Reason: REVIEW_BINDING_STALE' in explanation
        assert _inventory(tmp_path) == before
        page = _request(server, "GET", "/swing/v1-review")[2]
        form_url, form_body = _rendered_form(page, "native-review-pack")
        form_headers = dict(headers, **{"Content-Type": "application/x-www-form-urlencoded"})
        assert request("POST", form_url, headers=form_headers, body=form_body)[0] == 303
        publication = workflow._publication(market)
        path = workflow.live.transport.configuration.answer_directory / workflow.filenames(workflow._mapping(publication, market))[1]
        _answer_pdf(path, _native_answer(workflow, market, publication))
        page = _request(server, "GET", "/swing/v1-review")[2]
        form_url, form_body = _rendered_form(page, "native-review-answer")
        assert request("POST", form_url, headers=form_headers, body=form_body)[0] == 303
        before = _inventory(tmp_path)
        # Another still-open tab holds the pre-acceptance envelope. Never
        # silently replay its upload against the newly selected receipt.
        assert request("POST", form_url, headers=form_headers, body=form_body)[0] == 409
        assert _inventory(tmp_path) == before
        for _ in range(2):
            status, _, body = _request(server, "GET", "/swing/v1-review")
            assert status == 200 and ("MCX EVIDENCE ACCEPTED" if market == "MCX" else "EVIDENCE · ACCEPTED") in body
            assert "RETRY DOWNSTREAM" not in body and "Readiness ·" not in body
            assert workflow.snapshot()["rows"][0]["downstream"] == (
                "UNSUPPORTED_CONTRACT" if market == "MCX" else "SUCCEEDED")
            assert "native-review-answer?market=" in body and 'name="expected"' in body
            assert _request(server, "GET", "/swing/opportunities")[0] == 200
            assert _request(server, "GET", "/status")[0] == 200
        assert _inventory(tmp_path) == before
        row = workflow.snapshot()["rows"][0]
        role = workflow._roles(market)[0]
        query = urlencode(dict(market=market, instrument=instrument, role=role,
            selection=row["selected"][role]["selection_sha256"]))
        assert _request_bytes(server, "GET", "/swing/v1/native-chart-preview?" + query)[2] == PNG
        assert _inventory(tmp_path) == before
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)
        assert not thread.is_alive()


@pytest.fixture
def intake_browser(tmp_path, checkpoint):
    application = SwingOpportunitiesApplication(_Provider, run_publication=checkpoint[0])
    workflow, transport, historical = _transport(tmp_path / "context")
    workflow.intake_store = ReviewEvidenceStore(tmp_path / "native-review")
    workflow.publication_source = application
    server = create_browser_server(application, port=0, mcx_supporting_context=workflow)
    assert server.native_intake is not None
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    authority = f"127.0.0.1:{server.server_port}"
    headers = {"Host": authority, "Origin": f"http://{authority}",
               "Referer": f"http://{authority}/swing/v1-review", "Content-Type": "image/png"}
    try:
        yield server, workflow, transport, historical, headers
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        assert not thread.is_alive()


def context_url(workflow, endpoint, *, slot=McxContextSlot.MORNING, family=None):
    status = next(item for item in workflow.snapshot().slots if item.slot == slot)
    assert status.intake_precondition is not None
    query = {"slot": slot.value, "expected": status.intake_precondition}
    if family is not None:
        query["family"] = family
    return "/swing/mcx-context/" + endpoint + "?" + urlencode(query)


def test_context_guard_scope_whole_slot_prepare_and_restore_are_unlocked(intake_browser, tmp_path, monkeypatch):
    from kronos.swing.v1.mcx_supporting_context import McxContextFamily
    from kronos.swing.v1.mcx_supporting_context_pdf import McxContextQuestionPack, McxContextStagedImage
    _, workflow, transport, historical, _ = intake_browser
    held, protect = _guard_scope_spies(monkeypatch, workflow.publication_source)
    protect(workflow, "current_intake_state")
    protect(workflow, "governed_trading_date")
    for name in ("current", "current_image", "load_exact", "image_bytes"):
        protect(transport.store, name)
    protect(McxContextQuestionPack, "__post_init__")
    protect(McxContextStagedImage, "__post_init__")

    def mutate(slot, operation, **values):
        expected = ReviewMutationPrecondition.create(dict(workflow.current_intake_state(slot),
            mutation_identity="GUARD-SCOPE-CONTROLLED"))
        return workflow.mutate_intake(slot, operation, expected, **values)

    for slot in McxContextSlot:
        for family in McxContextFamily:
            mutate(slot, "STAGE", family=family, payload=PNG, content_type="image/png")
        pack = mutate(slot, "GENERATE")
        assert transport.configuration.answer_directory.is_dir()
        _answer(transport.configuration.answer_directory / pack.expected_answer_filename, _payload(pack))
        commit = mutate(slot, "IMPORT")
        assert len(workflow.intake_store.context_records(DAY, slot)) == 2
        assert len(commit.receipts[0].body["structured_evidence"]) == 2
        before = _inventory(tmp_path)
        assert mutate(slot, "IMPORT") == commit
        workflow.snapshot()
        assert _inventory(tmp_path) == before
        assert not held[0]
    assert historical.records() == ()


def test_context_browser_current_and_stale_tabs_whole_acceptance_and_get_purity(intake_browser, tmp_path):
    server, workflow, transport, historical, headers = intake_browser
    first = context_url(workflow, "image", family="METALS")
    second_tab = context_url(workflow, "image", family="ENERGY")
    assert _request(server, "POST", first, headers=headers, body=PNG)[0] == 303
    before = _inventory(tmp_path)
    status, _, body = _request(server, "POST", second_tab, headers=headers, body=PNG)
    assert status == 409 and body == "REVIEW_BINDING_STALE"
    assert _inventory(tmp_path) == before
    assert _request(server, "POST", context_url(workflow, "image", family="ENERGY"),
                    headers=headers, body=PNG)[0] == 303
    empty = dict(headers, **{"Content-Type": "application/x-www-form-urlencoded"})
    assert _request(server, "POST", context_url(workflow, "question-pack"), headers=empty)[0] == 303
    pack = transport.store.current(DAY, McxContextSlot.MORNING)
    assert pack is not None
    _answer(transport.configuration.answer_directory / pack.expected_answer_filename, _payload(pack))
    old_import = context_url(workflow, "answer")
    assert _request(server, "POST", old_import, headers=empty)[0] == 303
    assert historical.records() == ()
    assert len(workflow.intake_store.context_records(DAY, McxContextSlot.MORNING)) == 2
    before = _inventory(tmp_path)
    status, _, body = _request(server, "POST", old_import, headers=empty)
    assert status == 409 and body == "REVIEW_BINDING_STALE"
    assert _inventory(tmp_path) == before
    assert _request(server, "POST", context_url(workflow, "answer"), headers=empty)[0] == 303
    assert _inventory(tmp_path) == before
    for _ in range(3):
        status, _, body = _request(server, "GET", "/swing/v1-review")
        assert status == 200 and "EVIDENCE · ACCEPTED" in body
        assert "EVIDENCE · MISSING" in body  # independent Evening package
    assert _inventory(tmp_path) == before


def test_context_browser_missing_precondition_and_invalid_answer_do_not_publish(intake_browser, tmp_path):
    server, workflow, transport, historical, headers = intake_browser
    before = _inventory(tmp_path)
    assert _request(server, "POST", "/swing/mcx-context/image?slot=MORNING&family=METALS",
                    headers=headers, body=PNG)[0] == 400
    assert _inventory(tmp_path) == before
    for family in ("METALS", "ENERGY"):
        assert _request(server, "POST", context_url(workflow, "image", family=family),
                        headers=headers, body=PNG)[0] == 303
    empty = dict(headers, **{"Content-Type": "application/x-www-form-urlencoded"})
    assert _request(server, "POST", context_url(workflow, "question-pack"), headers=empty)[0] == 303
    pack = transport.store.current(DAY, McxContextSlot.MORNING)
    payload = _payload(pack)
    payload["families"].pop()
    _answer(transport.configuration.answer_directory / pack.expected_answer_filename, payload)
    before = _inventory(tmp_path)
    _request(server, "POST", context_url(workflow, "answer"), headers=empty)
    assert workflow.intake_store.context_records(DAY, McxContextSlot.MORNING) == ()
    assert historical.records() == ()
    assert _inventory(tmp_path) == before
    assert workflow.snapshot().slots[0].evidence_state == "INVALID"


@pytest.mark.parametrize("racing_operation", ["REMOVE", "GENERATE"])
def test_context_browser_import_commit_recheck_fences_image_and_request_races(intake_browser, monkeypatch, racing_operation):
    from kronos.swing.v1.mcx_supporting_context import McxContextFamily
    server, workflow, transport, historical, headers = intake_browser
    empty = dict(headers, **{"Content-Type": "application/x-www-form-urlencoded"})
    for family in ("METALS", "ENERGY"):
        assert _request(server, "POST", context_url(workflow, "image", family=family),
                        headers=headers, body=PNG)[0] == 303
    assert _request(server, "POST", context_url(workflow, "question-pack"), headers=empty)[0] == 303
    pack = transport.store.current(DAY, McxContextSlot.MORNING)
    _answer(transport.configuration.answer_directory / pack.expected_answer_filename, _payload(pack))
    capture = transport.capture_and_validate
    def concurrent_mutation(record):
        captured = capture(record)
        expected = workflow.snapshot().slots[0].intake_precondition
        kwargs = {"family": McxContextFamily.ENERGY} if racing_operation == "REMOVE" else {}
        workflow.mutate_intake(McxContextSlot.MORNING, racing_operation,
            ReviewMutationPrecondition(expected.encode()), **kwargs)
        return captured
    monkeypatch.setattr(transport, "capture_and_validate", concurrent_mutation)
    status, _, body = _request(server, "POST", context_url(workflow, "answer"), headers=empty)
    assert status == 409 and body == "REVIEW_BINDING_STALE"
    assert workflow.intake_store.context_records(DAY, McxContextSlot.MORNING) == ()
    assert historical.records() == ()


def test_context_browser_successor_and_evening_are_separate(intake_browser, tmp_path):
    server, workflow, transport, historical, headers = intake_browser
    empty = dict(headers, **{"Content-Type": "application/x-www-form-urlencoded"})
    receipts = []
    for slot, identity in ((McxContextSlot.MORNING, "ANSWER-1"),
                           (McxContextSlot.MORNING, "ANSWER-2"),
                           (McxContextSlot.EVENING, "ANSWER-3")):
        for family in ("METALS", "ENERGY"):
            assert _request(server, "POST", context_url(workflow, "image", slot=slot, family=family),
                            headers=headers, body=PNG)[0] == 303
        assert _request(server, "POST", context_url(workflow, "question-pack", slot=slot), headers=empty)[0] == 303
        pack = transport.store.current(DAY, slot)
        payload = _payload(pack)
        payload["manifest"]["answer_pack_identity"] = identity
        _answer(transport.configuration.answer_directory / pack.expected_answer_filename, payload)
        assert _request(server, "POST", context_url(workflow, "answer", slot=slot), headers=empty)[0] == 303
        receipts.append(workflow.intake_store.context_acceptance_history(DAY, slot)[0].receipts[0])
    assert receipts[1].body["predecessor_receipt_id"] == receipts[0].receipt_id
    assert receipts[2].body["predecessor_receipt_id"] is None
    assert len(workflow._records(trading_date=DAY, slot=McxContextSlot.MORNING)) == 4
    assert len(workflow._records(trading_date=DAY, slot=McxContextSlot.EVENING)) == 2
    assert historical.records() == ()


def test_configured_context_cannot_use_unguarded_historical_mutation_entrypoints(intake_browser, tmp_path):
    from kronos.swing.v1.mcx_supporting_context import McxContextFamily
    from kronos.swing.v1.review_evidence_binding import ReviewEvidenceError
    _, workflow, _, _, _ = intake_browser
    before = _inventory(tmp_path)
    actions = (
        lambda: workflow.stage_image(slot=McxContextSlot.MORNING, family=McxContextFamily.METALS,
                                     content_type="image/png", payload=PNG),
        lambda: workflow.remove_image(slot=McxContextSlot.MORNING, family=McxContextFamily.METALS),
        lambda: workflow.create_question_pack(McxContextSlot.MORNING),
        lambda: workflow.upload_answer(McxContextSlot.MORNING),
    )
    for action in actions:
        with pytest.raises(ReviewEvidenceError, match="REVIEW_PRECONDITION_INVALID"):
            action()
    assert _inventory(tmp_path) == before


def test_context_browser_corruption_is_invalid_without_historical_fallback_or_get_writes(intake_browser, tmp_path):
    server, workflow, transport, historical, headers = intake_browser
    empty = dict(headers, **{"Content-Type": "application/x-www-form-urlencoded"})
    for family in ("METALS", "ENERGY"):
        assert _request(server, "POST", context_url(workflow, "image", family=family),
                        headers=headers, body=PNG)[0] == 303
    assert _request(server, "POST", context_url(workflow, "question-pack"), headers=empty)[0] == 303
    pack = transport.store.current(DAY, McxContextSlot.MORNING)
    _answer(transport.configuration.answer_directory / pack.expected_answer_filename, _payload(pack))
    assert _request(server, "POST", context_url(workflow, "answer"), headers=empty)[0] == 303
    receipt = workflow.intake_store.context_acceptance_history(DAY, McxContextSlot.MORNING)[0].receipts[0]
    relative = receipt.body["structured_evidence"][0]["retained_relative_path"]
    (workflow.intake_store.root / relative).write_bytes(b"controlled corruption")
    before = _inventory(tmp_path)
    for _ in range(2):
        status, _, body = _request(server, "GET", "/swing/v1-review")
        assert status == 200 and "EVIDENCE · INVALID" in body
        assert "EVIDENCE · ACCEPTED" not in body
    from tests.unit.swing.v1.test_mcx_supporting_context import MORNING
    assert workflow.context_for("GOLDM", assessment_boundary=MORNING) is None
    assert _inventory(tmp_path) == before


@pytest.mark.parametrize("relative", [
    "current/2026-08-24/MORNING.json",
    "staged-current/2026-08-24/MORNING/METALS.json",
])
def test_context_browser_corrupt_selection_is_bounded_invalid_and_read_only(intake_browser, tmp_path, relative):
    server, workflow, transport, _, _ = intake_browser
    path = transport.store.root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"controlled corrupt selection")
    before = _inventory(tmp_path)
    for _ in range(2):
        status, _, body = _request(server, "GET", "/swing/v1-review")
        assert status == 200 and "EVIDENCE · INVALID" in body
        assert "controlled corrupt selection" not in body
    assert workflow.snapshot().slots[0].intake_precondition is None
    assert _inventory(tmp_path) == before
