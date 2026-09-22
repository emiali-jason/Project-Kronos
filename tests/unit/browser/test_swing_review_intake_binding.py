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

SPONSOR_EIGHT = (
    "ADANIENT", "ADANIPORTS", "AXISBANK", "BAJFINANCE",
    "COALINDIA", "HCLTECH", "INFY", "RBLBANK",
)


def test_workspace_diagnostics_preserve_bounded_reason_not_exception_payload():
    from kronos.application.swing_visual_v3_live import NativeReviewIntakeWorkflow
    from kronos.swing.v1.review_evidence_binding import ReviewEvidenceError
    reason = NativeReviewIntakeWorkflow._reason
    assert reason(ReviewEvidenceError('REVIEW_ARTIFACT_DIGEST_MISMATCH'), 'REVIEW_RESTORATION_UNAVAILABLE') == 'REVIEW_ARTIFACT_DIGEST_MISMATCH'
    assert reason(ValueError('SYNTHETIC private path /not-for-display'), 'REVIEW_RESTORATION_UNAVAILABLE') == 'REVIEW_RESTORATION_UNAVAILABLE'


def _current_twelve(workflow, candidate_names=None):
    """Synthetic exact production-shaped population; never read live evidence."""
    from dataclasses import replace
    from types import SimpleNamespace
    from hashlib import sha256
    from kronos.swing.v1.native_discovery import NativeProductPath, Native1WState, NativeDiscoveryStatus
    from kronos.swing.v1.models import V1Direction
    from tests.unit.swing.v1.test_native_review import _evidence_run
    facts, base, probable = _evidence_run()
    names = candidate_names or ('DRREDDY', 'TCS', 'ASIANPAINT', 'TMPV', 'ADANIGREEN', 'ADANIENT',
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
            assert row['direction'] == requirement.thesis.direction.value
            assert row['requirement_sha256'] == requirement.requirement_sha256
            assert row['assessment_sha256'] == requirement.thesis.native_assessment_sha256
            assert row['expected'][row['instrument']]['expected_run_identity'] == state['native'].run_identity
            if row['instrument'] in {'TMPV', 'ADANIGREEN', 'BAJFINANCE'}:
                assert row['continuity'].opportunity_id is None and row['continuity'].material_revision is None
        page = _receipt_native_review(result)
        for text in ('Current Review workspace', 'NSE REVIEW', 'MCX REVIEW', 'CHART MISSING',
                     'ANALYTICAL ROOT UNCERTAIN', 'MANUAL REVIEW REQUIRED'):
            assert text in page
        assert page.count('aria-label="Paste MCX SIX-PANEL COMPOSITE"') == 2
        assert page.count('market=MCX&amp;instrument=GOLDM&amp;role=NATIVE_MCX') >= 1
        assert 'role=SUPPORTING_REFERENCE' not in page
        assert 'SUPPORTING COMEX: 1D / 4H / 1H' in page
        assert 'COMEX Gold / COMEX:GC1!' in page
        assert 'SUPPORTING NYMEX: 1D / 4H / 1H' in page
        assert 'NYMEX Crude Oil / NYMEX:CL1!' in page
        assert '@media(min-width:1200px){.wo07-card-grid{grid-template-columns:repeat(3' in page
        assert '@media(min-width:1480px){.wo07-card-grid{grid-template-columns:repeat(4' in page
        assert '@media(max-width:760px){.wo07-card-grid{grid-template-columns:minmax(0,1fr)}' in page
        assert '.wo07-chart-preview img{display:block;box-sizing:border-box;width:100%;height:auto;' in page
        assert 'max-height:360px;object-fit:contain' in page
        assert '.wo07-card .chart-paste-target>div>strong,.wo07-card .chart-paste-target>div>span{display:block}' in page
        assert 'object-fit:contain' in page
        assert page.count('wo07-direction direction-short') == 10
        assert page.count('wo07-direction direction-long') == 2
        assert 'Charts required for current NSE candidates.' in page
        assert 'Charts required for current MCX candidates.' in page
        assert 'QUESTION PACK NOT CURRENT' not in page
        assert 'EVIDENCE · MISSING' not in page
        assert 'MCX EVIDENCE MISSING' not in page
        assert page.count('CHART MISSING') == 12
        assert page.count('Questions · <strong>NOT READY</strong>') == 12
        assert page.count('ANSWER MISSING') == 12
        assert '<summary>Supporting evidence</summary>' in page
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
        if market == "MCX":
            native_responses = publication.native.value["subjects"][0]["responses"]
            reference_responses = publication.reference.value["subjects"][0]["responses"]
            assert len(native_responses) + len(reference_responses) == 6
            assert len({item["chart_revision_sha256"]
                        for item in (*native_responses, *reference_responses)}) == 1
            reference = workflow._requirements(market, (instrument,))[0].mcx_reference
            assert (publication.reference.value["subjects"][0]["reference_subject_identity"],
                    publication.reference.value["subjects"][0]["reference_market"],
                    publication.reference.value["subjects"][0]["reference_symbol"]) == (
                        reference.reference_subject_identity, reference.reference_market.value,
                        reference.reference_symbol)
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
    from tests.unit.swing.v1.test_review_evidence_binding import nse_v2_answer
    from tests.unit.swing.v1.test_mcx_native_visual_contract import successor_answer
    if market == "MCX":
        answer = successor_answer(publication.native, publication.reference)
        for response, requested in zip(answer["subjects"][0]["responses"], publication.native.value["subjects"][0]["responses"], strict=True):
            if requested["governed_reference_basis_availability"] == "UNAVAILABLE":
                observation = response["observations"][3]
                observation.update(observation_status="UNAVAILABLE", ambiguity_reason="Governed reference basis unavailable")
                observation["result"].update(presence="NOT_IDENTIFIABLE", relationship="NOT_OBSERVABLE", interaction="NOT_OBSERVABLE")
        return answer
    from types import SimpleNamespace
    value = nse_v2_answer(publication.mapping)
    value["subjects"] = []
    for subject in publication.mapping.value["subjects"]:
        candidate = nse_v2_answer(SimpleNamespace(value=dict(publication.mapping.value, subjects=[subject]),
            request_reference=publication.mapping.request_reference))["subjects"][0]
        for response in candidate["responses"]:
            response["chart_revision_sha256"] = subject["chart_revision_sha256"]
            for observation in response["observations"]:
                observation["source_chart_revision"] = subject["chart_revision_sha256"]
            response["observations"][0]["observed_instrument"] = subject["canonical_instrument"]
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
    if market == "MCX":
        receipt = workflow.store.native_acceptance_history(market,
            workflow._context()[1].run_identity)[0].receipts[0]
        charts = receipt.body["chart_revisions"]
        assert len(charts) == 6
        assert {(item["role"], item["timeframe_or_panel_identity"]) for item in charts} == {
            (role, timeframe) for role in ("NATIVE_MCX", "SUPPORTING_REFERENCE")
            for timeframe in ("1D", "4H", "1H")}
        assert len({item["sha256"] for item in charts}) == 1
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
    from kronos.swing.v1.review_evidence_binding import strict_json
    receipt = commit.receipts[0]
    if market == "NSE":
        assert receipt.body["comparison_evidence"] is None
        for item in receipt.body["structured_evidence"]:
            value = strict_json((workflow.store.root / item["retained_relative_path"]).read_bytes())
            assert value["answer_pdf_sha256"] == receipt.body["answer"]["pdf_sha256"]
    else:
        assert len(receipt.body["structured_evidence"]) == 6
        assert receipt.body["comparison_evidence"]["answer_identity"] == answer["answer_identity"]
    return market, instrument, publication, path, answer, commit


def _successor_identity(answer, suffix):
    answer["answer_identity"] += suffix
    if "supporting_reference_answer" in answer:
        answer["supporting_reference_answer"]["answer_identity"] = answer["answer_identity"]
        answer["comparison_answer"]["answer_identity"] = answer["answer_identity"]


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
    _successor_identity(answer, "-CHANGED")
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
    _successor_identity(answer, "-SUCCESSOR")
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


@pytest.mark.parametrize("native_intake", ["GOLDM"], indirect=True)
def test_mcx_comparison_sibling_corruption_fences_restore_and_get(native_intake, tmp_path, monkeypatch):
    workflow = native_intake
    market, instrument, _, _, _, commit = _accepted_native(workflow, tmp_path)
    sibling = commit.receipts[0].body["comparison_evidence"]
    assert sibling["answer_identity"] == commit.receipts[0].body["answer"]["answer_identity"]
    assert len(commit.receipts[0].body["structured_evidence"]) == 6
    path = workflow.store.root / sibling["retained_relative_path"]
    path.write_bytes(b"SYNTHETIC TAMPER")
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
        for response in subject["responses"]:
            response["observations"][0].update(observed_instrument=subject["canonical_instrument"],
                observed_market="NSE", observed_timeframe=response["timeframe"])
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
        assert 'class="wo07-chart-preview"' in page
        assert 'target="_blank" rel="noopener"' in page
        assert 'loading="lazy"' in page
        assert 'Paste the required current chart evidence before creating the question pack.' not in page
        received_card = page.split('<h3>' + instrument + '</h3>', 1)[1].split('</article>', 1)[0]
        assert 'Click and paste TradingView image with ⌘V' not in received_card
        assert 'Replace' in received_card and 'Remove' in received_card and 'Choose File' in received_card
        assert 'CHART READY' in received_card
        assert 'Questions · <strong>NOT READY</strong>' in received_card
        assert 'ANSWER MISSING' in received_card
        assert 'TRADINGVIEW COMPOSITE · RECEIVED' in received_card
        form_url, form_body = _rendered_form(page, "native-review-pack")
        form_headers = dict(headers, **{"Content-Type": "application/x-www-form-urlencoded"})
        assert request("POST", form_url, headers=form_headers, body=form_body)[0] == 303
        publication = workflow._publication(market)
        page = _request(server, "GET", "/swing/v1-review")[2]
        ready_card = page.split('<h3>' + instrument + '</h3>', 1)[1].split('</article>', 1)[0]
        assert 'ANSWER MISSING' in ready_card
        assert 'QUESTION PACK NOT READY' not in ready_card
        assert 'Questions · <strong>READY</strong>' in ready_card
        assert 'EVIDENCE · MISSING' not in ready_card and 'MCX EVIDENCE MISSING' not in ready_card
        path = workflow.live.transport.configuration.answer_directory / workflow.filenames(workflow._mapping(publication, market))[1]
        _answer_pdf(path, _native_answer(workflow, market, publication))
        page = _request(server, "GET", "/swing/v1-review")[2]
        form_url, form_body = _rendered_form(page, "native-review-answer")
        assert request("POST", form_url, headers=form_headers, body=form_body)[0] == 303
        before = _inventory(tmp_path)
        # Another still-open tab holds the pre-acceptance envelope. Never
        # silently replay its upload against the newly selected receipt.
        rejected, headers_after_rejection, _ = request("POST", form_url, headers=form_headers, body=form_body)
        assert rejected == 303
        notice_url = headers_after_rejection["Location"]
        assert notice_url.startswith("/swing/v1-review?answer_notice=")
        notice_page = _request(server, "GET", notice_url)[2]
        assert "ANSWER IMPORT REJECTED" in notice_page
        assert "REVIEW_BINDING_STALE" in notice_page
        assert "Nothing was imported or changed." in notice_page
        assert "ANSWER IMPORTED" in notice_page and "EVIDENCE ACCEPTED" in notice_page
        assert _inventory(tmp_path) == before
        for _ in range(2):
            status, _, body = _request(server, "GET", "/swing/v1-review")
            assert status == 200 and "ANSWER IMPORTED" in body and "EVIDENCE ACCEPTED" in body
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
        replacement = PNG + b"controlled replacement"
        assert request("POST", url("native-chart", instrument=instrument, role=role),
                       headers=headers, body=replacement)[0] == 303
        replaced = workflow.snapshot()["rows"][0]
        assert replaced["selected"][role]["selection_sha256"] != row["selected"][role]["selection_sha256"]
        query = urlencode(dict(market=market, instrument=instrument, role=role,
            selection=replaced["selected"][role]["selection_sha256"]))
        assert _request_bytes(server, "GET", "/swing/v1/native-chart-preview?" + query)[2] == replacement
        page = _request(server, "GET", "/swing/v1-review")[2]
        remove_url, remove_body = _rendered_form(page, "native-chart/remove")
        assert request("POST", remove_url, headers=form_headers, body=remove_body)[0] == 303
        removed_page = _request(server, "GET", "/swing/v1-review")[2]
        assert "CHART MISSING" in removed_page
        assert "Paste the required current chart evidence before creating the question pack." in removed_page
        assert workflow.store.native_chart_bytes(row["selected"][role]) == PNG
        assert workflow.store.native_chart_bytes(replaced["selected"][role]) == replacement
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)
        assert not thread.is_alive()


@pytest.mark.parametrize("native_intake", ["NSE"], indirect=True)
def test_native_chart_json_intake_has_one_admission_and_exact_identity(
    native_intake, monkeypatch,
):
    import json
    from kronos.swing.v1.review_evidence_binding import canonical
    workflow = native_intake
    market = "NSE"
    instrument = workflow._requirements(market)[0].canonical_instrument
    server = create_browser_server(SwingOpportunitiesApplication(_Provider), port=0,
        native_review=workflow.native_review, visual_v3_live=workflow.live)
    server.native_intake = workflow
    original = workflow._admit
    admissions = []
    def counted(*args, **kwargs):
        admissions.append(args)
        return original(*args, **kwargs)
    monkeypatch.setattr(workflow, "_admit", counted)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    authority = f"127.0.0.1:{server.server_port}"
    expected = canonical(workflow.expected(market, (instrument,))).decode()
    path = "/swing/v1/native-chart?" + urlencode(dict(
        market=market, instrument=instrument, role="NATIVE_NSE", expected=expected))
    try:
        status, headers, body = _request(server, "POST", path, headers={
            "Host": authority, "Origin": f"http://{authority}",
            "Content-Type": "image/png", "Accept": "application/json",
        }, body=PNG)
        result = json.loads(body)
        assert status == 200 and headers["Content-Type"] == "application/json; charset=utf-8"
        assert result == {
            "outcome": "CHART_RECEIVED", "market": market,
            "instrument": instrument, "role": "NATIVE_NSE",
            "selection_identity": workflow._selection(
                workflow._requirements(market, (instrument,))[0], "NATIVE_NSE"
            )["selection_sha256"],
            "chart_sha256": __import__("hashlib").sha256(PNG).hexdigest(),
        }
        assert len(admissions) == 1
    finally:
        server.shutdown(); server.server_close(); thread.join(3)
        assert not thread.is_alive()


@pytest.mark.parametrize("native_intake", ["NSE"], indirect=True)
def test_invalid_native_chart_json_preserves_prepared_page_without_rebuild(
    native_intake, monkeypatch,
):
    import json
    from kronos.swing.v1.review_evidence_binding import canonical
    workflow = native_intake
    market = "NSE"
    instrument = workflow._requirements(market)[0].canonical_instrument
    assert workflow.prepare_page_state()
    server = create_browser_server(SwingOpportunitiesApplication(_Provider), port=0,
        native_review=workflow.native_review, visual_v3_live=workflow.live)
    server.native_intake = workflow
    rebuilds = []
    original = workflow.prepare_page_state
    monkeypatch.setattr(workflow, "prepare_page_state",
                        lambda: rebuilds.append(True) or original())
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    authority = f"127.0.0.1:{server.server_port}"
    expected = canonical(workflow.expected(market, (instrument,))).decode()
    path = "/swing/v1/native-chart?" + urlencode(dict(
        market=market, instrument=instrument, role="NATIVE_NSE", expected=expected))
    try:
        status, _, body = _request(server, "POST", path, headers={
            "Host": authority, "Origin": f"http://{authority}",
            "Content-Type": "image/png", "Accept": "application/json",
        }, body=b"not-an-image")
        assert status == 409
        assert json.loads(body) == {
            "outcome": "REJECTED", "reason": "REVIEW_ACCEPTANCE_INCOMPLETE",
        }
        assert rebuilds == []
        assert workflow.page_state_status()["state"] == "READY"
    finally:
        server.shutdown(); server.server_close(); thread.join(3)
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


# STAGE 10B-C1: real isolated component readers, not in-memory loader substitutes.
def _page_load_population(workflow, tmp_path, population=12, candidate_names=None):
    from dataclasses import replace
    from kronos.swing.v1 import native_discovery as native
    from kronos.swing.v1.mtf_facts import MtfFactEvidenceStore
    state, names = _current_twelve(workflow, candidate_names)
    state["control"]["latest_attempt"] = {"state": "SUCCEEDED"}
    run = state["native"]
    members = set(names[:population])
    assessments = tuple(replace(item, status=(item.status if item.canonical_instrument in members
        else native.NativeDiscoveryStatus.NO_CURRENT_OPPORTUNITY)) for item in run.assessments)
    assessments = tuple(replace(item, result_sha256=native._assessment_digest(item)) for item in assessments)
    run = replace(run, assessments=assessments)
    run = replace(run, result_sha256=native._digest(dict(run_identity=run.run_identity,
        provider_source_identity=run.provider_source_identity, observed_at=run.observed_at,
        assessments=run.assessments)))
    state["native"] = run
    stores = (native.NativeDiscoveryEvidenceStore(tmp_path / "page-native"),
              MtfFactEvidenceStore(tmp_path / "page-mtf"))
    paths = (stores[0].retain(run), stores[1].retain(state["facts"]))
    assert stores[0].load(run.run_identity) == run
    assert stores[1].load(run.run_identity) == state["facts"]
    workflow.application.native_discovery_evidence_store = lambda: stores[0]
    workflow.application.mtf_fact_evidence_store = lambda: stores[1]
    from contextlib import contextmanager
    from types import SimpleNamespace
    @contextmanager
    def guard():
        yield SimpleNamespace(control=state["control"], manifest={"run_id": state["native"].run_identity})
    workflow.application.publication_mutation_guard = guard
    return state, stores, paths


def _page_load_counts(monkeypatch, stores, paths):
    from collections import Counter
    from pathlib import Path
    from kronos.swing.v1 import native_discovery as native, mtf_facts as mtf
    counts = Counter()
    def wrap(owner, name, label):
        original = getattr(owner, name)
        def counted(*args, **kwargs):
            counts[label] += 1
            return original(*args, **kwargs)
        monkeypatch.setattr(owner, name, counted)
    for label, store, module, decoder, cls in (
        ("native", stores[0], native, "_run", native.NativeDiscoveryRun),
        ("mtf", stores[1], mtf, "_snapshot", mtf.SameRunMtfFactSnapshot)):
        wrap(store, "load", label + "_typed_loads")
        wrap(module, "_read", label + "_json_reconstructions")
        wrap(module, decoder, label + "_typed_reconstructions")
        wrap(cls, "__post_init__", label + "_root_validations")
        wrap(module, "sha256", label + "_hash_passes")
    original_open = Path.open
    labels = dict(zip(paths, ("native", "mtf")))
    def counted_open(path, mode="r", *args, **kwargs):
        if path in labels and "r" in mode:
            counts[labels[path] + "_file_reads"] += 1
        return original_open(path, mode, *args, **kwargs)
    monkeypatch.setattr(Path, "open", counted_open)
    import os
    original_os_open = os.open
    def counted_os_open(path, flags, *args, **kwargs):
        candidate = Path(path)
        if candidate in labels and not flags & (os.O_WRONLY | os.O_RDWR):
            counts[labels[candidate] + "_file_reads"] += 1
            counts[labels[candidate] + "_byte_fence_passes"] += 1
        return original_os_open(path, flags, *args, **kwargs)
    monkeypatch.setattr(os, "open", counted_os_open)
    return counts


@pytest.mark.parametrize("native_intake", ["NSE"], indirect=True)
@pytest.mark.parametrize("population", [1, 12])
def test_page_intake_reconstructs_each_bundle_once(native_intake, tmp_path, monkeypatch, population):
    import json
    state, stores, paths = _page_load_population(native_intake, tmp_path, population)
    before = _inventory(tmp_path)
    counts = _page_load_counts(monkeypatch, stores, paths)
    result = native_intake.snapshot()
    assert result["error"] is None
    assert result["workspace"]["eligible"] == population
    print("C1_COUNTS " + json.dumps(dict(population=population, counts=dict(counts)), sort_keys=True))
    assert _inventory(tmp_path) == before
    assert counts["native_typed_loads"] == counts["mtf_typed_loads"] == 1
    assert counts["native_json_reconstructions"] == counts["mtf_json_reconstructions"] == 1
    assert counts["native_typed_reconstructions"] == counts["mtf_typed_reconstructions"] == 1


@pytest.mark.parametrize("native_intake", ["NSE"], indirect=True)
def test_mutation_admission_reuses_each_typed_current_component_once(
    native_intake, tmp_path, monkeypatch,
):
    state, stores, paths = _page_load_population(native_intake, tmp_path, 12)
    with native_intake._page_state_lock:
        native_intake._page_state = None
        native_intake._page_state_failure = "SWING_PAGE_PREPARATION_MISSING"
    instrument = native_intake._requirements("NSE")[0].canonical_instrument
    expected = native_intake.expected("NSE", (instrument,))
    counts = _page_load_counts(monkeypatch, stores, paths)
    result = native_intake.stage("NSE", instrument, "NATIVE_NSE", expected,
                                 image=PNG, content_type="image/png")
    assert result["image"]["sha256"] == __import__("hashlib").sha256(PNG).hexdigest()
    assert counts["native_typed_loads"] == counts["mtf_typed_loads"] == 1
    assert counts["native_json_reconstructions"] == counts["mtf_json_reconstructions"] == 1
    assert counts["native_typed_reconstructions"] == counts["mtf_typed_reconstructions"] == 1


@pytest.mark.parametrize("native_intake", ["NSE"], indirect=True)
def test_mutation_admission_reuses_published_prepared_generation(
    native_intake, tmp_path, monkeypatch,
):
    _, stores, paths = _page_load_population(native_intake, tmp_path, 12)
    assert native_intake.prepare_page_state()
    instrument = native_intake._requirements("NSE")[0].canonical_instrument
    expected = native_intake.expected("NSE", (instrument,))
    counts = _page_load_counts(monkeypatch, stores, paths)
    result = native_intake.stage("NSE", instrument, "NATIVE_NSE", expected,
                                 image=PNG, content_type="image/png")
    assert result["image"]["sha256"] == __import__("hashlib").sha256(PNG).hexdigest()
    assert counts["native_typed_loads"] == counts["mtf_typed_loads"] == 0
    assert counts["native_typed_reconstructions"] == counts["mtf_typed_reconstructions"] == 0
    assert counts["native_byte_fence_passes"] >= 3
    assert counts["mtf_byte_fence_passes"] >= 3


@pytest.mark.parametrize("native_intake", ["NSE"], indirect=True)
def test_eight_current_candidates_accept_independent_chart_pastes_before_page_rerender(
    native_intake, tmp_path,
):
    """A sibling's successful chart must not stale another current card."""
    _page_load_population(native_intake, tmp_path, 8, SPONSOR_EIGHT)
    assert native_intake.prepare_page_state()
    rows = [row for row in native_intake.snapshot()["rows"] if row["market"] == "NSE"]
    assert len(rows) == 8
    for row in rows:
        instrument = row["instrument"]
        selected = native_intake.stage(
            "NSE", instrument, "NATIVE_NSE", row["expected"],
            image=PNG, content_type="image/png",
        )
        assert selected["binding"]["instrument"] == instrument
        assert selected["binding"]["candidate_identity"] == row["requirement_sha256"]


@pytest.mark.parametrize("native_intake", ["NSE"], indirect=True)
def test_eight_generated_review_cards_accept_serial_chart_posts_and_rerender(
    native_intake, tmp_path,
):
    import html
    import json
    import re
    from urllib.parse import parse_qs, urlsplit

    state, _, _ = _page_load_population(native_intake, tmp_path, 8, SPONSOR_EIGHT)
    server = _page_load_server(native_intake, state)
    serving = Thread(target=server.serve_forever, daemon=True)
    serving.start()
    authority = f"127.0.0.1:{server.server_port}"
    headers = {"Host": authority, "Origin": f"http://{authority}",
               "Content-Type": "image/png", "Accept": "application/json"}

    def card(page, instrument):
        return page.split("<h3>" + instrument + "</h3>", 1)[1].split("</article>", 1)[0]

    def card_url(page, instrument):
        match = re.search(r'data-upload-url="([^"]+)"', card(page, instrument))
        assert match is not None
        return html.unescape(match.group(1))

    try:
        status, _, page = _request(server, "GET", "/swing/v1-review")
        assert status == 200
        rows = [row for row in native_intake.snapshot()["rows"] if row["market"] == "NSE"]
        assert len(rows) == 8
        assert '<span data-chart-complete-count>0</span>' in page
        initial_urls = {row["instrument"]: card_url(page, row["instrument"]) for row in rows}
        first_selection = None
        for count, row in enumerate(rows, 1):
            instrument = row["instrument"]
            url = card_url(page, instrument)
            query = parse_qs(urlsplit(url).query)
            assert query["market"] == ["NSE"]
            assert query["instrument"] == [instrument]
            assert query["role"] == ["NATIVE_NSE"]
            expected = json.loads(query["expected"][0])[instrument]
            assert expected["expected_run_identity"] == state["native"].run_identity
            assert expected["expected_candidate_identity"] == row["requirement_sha256"]
            status, _, payload = _request(server, "POST", url, headers=headers, body=PNG)
            assert status == 200, payload
            result = json.loads(payload)
            assert result["outcome"] == "CHART_RECEIVED"
            assert result["instrument"] == instrument
            assert result["selection_identity"]
            before_get = _inventory(tmp_path)
            status, _, page = _request(server, "GET", "/swing/v1-review")
            assert status == 200
            assert f'<span data-chart-complete-count>{count}</span>' in page
            assert "BINDING CURRENT" in card(page, instrument)
            assert "CHART READY" in card(page, instrument)
            assert _inventory(tmp_path) == before_get
            if count == 1:
                first_selection = native_intake._selection(
                    native_intake._requirements("NSE", (instrument,))[0], "NATIVE_NSE")
        assert first_selection is not None
        first_requirement = native_intake._requirements("NSE", (rows[0]["instrument"],))[0]
        assert native_intake._selection(first_requirement, "NATIVE_NSE") == first_selection
        last = rows[-1]["instrument"]
        before_rejection = _inventory(tmp_path)
        stale, _, body = _request(server, "POST", initial_urls[last], headers=headers, body=PNG)
        assert stale == 409 and json.loads(body)["reason"] == "REVIEW_BINDING_STALE"
        duplicate, _, body = _request(server, "POST", card_url(page, last), headers=headers, body=PNG)
        assert duplicate == 409 and json.loads(body)["reason"] == "REVIEW_CHART_ALREADY_CURRENT"
        assert _inventory(tmp_path) == before_rejection
        status, _, refreshed = _request(server, "GET", "/swing/v1-review")
        assert status == 200
        assert "BINDING CURRENT" in card(refreshed, last)
        assert "REVIEW_BINDING_STALE" not in card(refreshed, last)
        assert _inventory(tmp_path) == before_rejection
    finally:
        server.shutdown(); serving.join(5); server.server_close()


@pytest.mark.parametrize("native_intake", ["NSE"], indirect=True)
def test_stale_candidate_projection_never_claims_binding_current(native_intake):
    from kronos.browser.views import _receipt_native_review

    projection = native_intake.snapshot()
    row = projection["rows"][0]
    row["error"] = "REVIEW_BINDING_STALE"
    page = _receipt_native_review(projection)
    card = page.split("<h3>" + row["instrument"] + "</h3>", 1)[1].split("</article>", 1)[0]
    assert "REVIEW_BINDING_STALE" in card
    assert "BINDING STALE" in card
    assert "BINDING CURRENT" not in card


@pytest.mark.parametrize("native_intake", ["NSE"], indirect=True)
def test_overlapping_candidate_chart_posts_are_serialized_without_cross_binding(
    native_intake, tmp_path, monkeypatch,
):
    import json
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from time import monotonic
    from kronos.swing.v1.review_evidence_binding import canonical

    state, _, _ = _page_load_population(native_intake, tmp_path, 2, SPONSOR_EIGHT)
    server = _page_load_server(native_intake, state)
    serving = Thread(target=server.serve_forever, daemon=True)
    serving.start()
    authority = f"127.0.0.1:{server.server_port}"
    headers = {"Host": authority, "Origin": f"http://{authority}",
               "Content-Type": "image/png", "Accept": "application/json"}
    instruments = tuple(row["instrument"] for row in native_intake.snapshot()["rows"]
                        if row["market"] == "NSE")
    assert len(instruments) == 2
    urls = ["/swing/v1/native-chart?" + urlencode(dict(market="NSE", instrument=name,
            role="NATIVE_NSE", expected=canonical(native_intake.expected(
                "NSE", (name,))).decode())) for name in instruments]
    entered, release = Event(), Event()
    calls = []
    original = native_intake.stage

    def blocked_stage(*args, **kwargs):
        calls.append(args[1])
        if len(calls) == 1:
            entered.set()
            assert release.wait(10)
        return original(*args, **kwargs)

    monkeypatch.setattr(native_intake, "stage", blocked_stage)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(_request, server, "POST", urls[0], headers=headers, body=PNG)
            assert entered.wait(10)
            second = pool.submit(_request, server, "POST", urls[1], headers=headers, body=PNG)
            deadline = monotonic() + 10
            while server.request_capacity_status()["active"] < 2 and monotonic() < deadline:
                release.wait(0.01)
            assert server.request_capacity_status()["active"] == 2
            assert calls == [instruments[0]]
            release.set()
            responses = [first.result(20), second.result(20)]
        assert calls == list(instruments)
        assert all(status == 200 and json.loads(body)["outcome"] == "CHART_RECEIVED"
                   for status, _, body in responses)
        selected = {row["instrument"]: row["selected"]["NATIVE_NSE"]
                    for row in native_intake.snapshot()["rows"]}
        assert all(selected[name]["binding"]["instrument"] == name for name in instruments)
    finally:
        release.set()
        server.shutdown(); serving.join(5); server.server_close()


@pytest.mark.parametrize("native_intake", ["NSE"], indirect=True)
def test_invalid_native_chart_fails_before_expensive_authority_admission(
    native_intake, monkeypatch,
):
    instrument = native_intake._requirements("NSE")[0].canonical_instrument
    expected = native_intake.expected("NSE", (instrument,))
    monkeypatch.setattr(native_intake, "_admit",
                        lambda *_args, **_kwargs: pytest.fail("invalid bytes reached admission"))
    with pytest.raises(ValueError, match="REVIEW_ACCEPTANCE_INCOMPLETE"):
        native_intake.stage("NSE", instrument, "NATIVE_NSE", expected,
                            image=b"not-an-image", content_type="image/png")


def _page_load_server(workflow, state):
    from dataclasses import replace
    from tests.unit.browser.test_browser_views import _ready
    application = SwingOpportunitiesApplication(_Provider, initial_snapshot=replace(
        _ready(), swing_analysis_run_identity=state["native"].run_identity))
    application.restore_native_discovery_run(state["native"])
    application.restore_mtf_fact_snapshot(state["facts"])
    server = create_browser_server(application, port=0, native_review=workflow.native_review,
                                   visual_v3_live=workflow.live)
    server.native_intake = workflow
    original = workflow.application.opportunities_bundle_projection
    def projection():
        _, native, continuity, status = original()
        return application.snapshot(), native, None, status
    application.opportunities_bundle_projection = projection
    assert workflow.prepare_page_state()
    return server


@pytest.mark.parametrize("successor_preparation", ("success", "failure"))
def test_compact_routes_keep_committed_generation_while_analysis_is_blocked(
    checkpoint, tmp_path, monkeypatch, successor_preparation
):
    """Operational attempt state cannot invalidate unchanged page authority."""

    from dataclasses import replace
    from types import SimpleNamespace
    from threading import Event
    from kronos.application import swing_opportunities as swing
    from kronos.swing.v1 import opportunity_continuity as continuity
    from kronos.swing.v1.relative_context import build_relative_context_run
    from kronos.swing.universe import SWING_PHASE1_UNIVERSE
    from tests.unit.swing.test_run_publication import later, provenance
    from tests.unit.browser.test_swing_visual_v3_live import _live

    publication, current_facts, bindings, committed = checkpoint
    successor_facts = later(current_facts, 2)
    successor_continuity = continuity.prepare_continuity(
        successor_facts,
        bindings,
        adopted_predecessor=committed,
    )
    started, release = Event(), Event()
    successor_prepare_started, release_successor_prepare = Event(), Event()
    workers = []
    provider = _Provider()

    def build(*_args, **_kwargs):
        started.set()
        assert release.wait(30)
        return SimpleNamespace(
            workspace=replace(
                application.snapshot(),
                analysis_state=swing.AnalysisState.READY,
                analysis_failure="",
                swing_analysis_run_identity=successor_facts.run_identity,
            ),
            evidence=SimpleNamespace(
                observation_boundary=successor_facts.observed_at,
                market_data_snapshot_identity=(
                    provenance(successor_facts).market_data_snapshot_identity
                ),
            ),
            continuity_contribution=successor_continuity,
            mtf_fact_snapshot=successor_facts,
            native_discovery_run=successor_continuity.native_run,
            relative_context_run=build_relative_context_run(
                successor_facts, SWING_PHASE1_UNIVERSE
            ),
        )

    def runner(operation, name):
        worker = Thread(target=operation, name=name)
        workers.append(worker)
        worker.start()

    monkeypatch.setattr(swing, "build_completed_swing_analysis", build)
    application = SwingOpportunitiesApplication(
        lambda: provider,
        clock=lambda: successor_facts.observed_at,
        background_runner=runner,
        swing_run_identity_factory=lambda: successor_facts.run_identity,
        run_publication=publication,
        mtf_fact_evidence_store=publication.mtf_store,
        native_discovery_evidence_store=publication.native_store,
        relative_context_evidence_store=publication.relative_store,
    )
    application._SwingOpportunitiesApplication__provider = provider
    application._SwingOpportunitiesApplication__snapshot = replace(
        application.snapshot(), provider_state=swing.ProviderConnectionState.CONNECTED
    )
    historical, _, live = _live(tmp_path / "retained-review")
    server = create_browser_server(
        application,
        port=0,
        native_review=historical,
        visual_v3_live=live,
    )
    prepare_page_generation = server.native_intake.prepare_page_generation
    intake_snapshot = server.native_intake.snapshot

    def blocked_successor_prepare():
        successor_prepare_started.set()
        assert release_successor_prepare.wait(30)
        if successor_preparation == "success":
            return prepare_page_generation()

        def fail_successor_snapshot(*_args, **_kwargs):
            raise ValueError("CONTROLLED_SUCCESSOR_PREPARATION_FAILURE")

        server.native_intake.snapshot = fail_successor_snapshot
        try:
            return prepare_page_generation()
        finally:
            server.native_intake.snapshot = intake_snapshot

    monkeypatch.setattr(
        server.native_intake,
        "prepare_page_generation",
        blocked_successor_prepare,
    )
    serving = Thread(target=server.serve_forever, daemon=True)
    serving.start()
    routes = ("/swing/opportunities", "/swing/v1-review")
    committed_run_identity = committed.native.run_identity
    try:
        before_status = application.publication_status()
        for route in routes:
            status, _, body = _request(server, "GET", route)
            assert status == 200
            assert committed_run_identity in body and "BINDING CURRENT" in body

        assert application.run_analysis() and started.wait(5)
        running_status = application.publication_status()
        assert running_status["request_result"] == "RUNNING"
        assert running_status["control"]["latest_attempt"]["state"] == "RUNNING"
        assert (
            running_status["control"]["current_manifest"]
            == before_status["control"]["current_manifest"]
        )
        during_inventory = _inventory(tmp_path)
        for route in routes:
            status, _, body = _request(server, "GET", route)
            assert status == 200
            assert committed_run_identity in body and "BINDING CURRENT" in body
            assert successor_facts.run_identity not in body
            if route == "/swing/opportunities":
                assert "Analysis running" in body
        assert _inventory(tmp_path) == during_inventory

        assert not application.run_analysis()
        assert application.publication_status()["request_result"] == "DUPLICATE_RUNNING"
        for route in routes:
            status, _, body = _request(server, "GET", route)
            assert status == 200
            assert committed_run_identity in body and successor_facts.run_identity not in body
            if route == "/swing/opportunities":
                assert "Duplicate request rejected" in body

        from concurrent.futures import ThreadPoolExecutor
        requested = routes * 20
        with ThreadPoolExecutor(max_workers=8) as pool:
            concurrent = tuple(
                pool.map(lambda route: _request(server, "GET", route), requested)
            )
        assert len(concurrent) == 40
        assert all(status == 200 for status, _, _ in concurrent)
        assert all(
            committed_run_identity in body
            and successor_facts.run_identity not in body
            for _, _, body in concurrent
        )

        release.set()
        assert successor_prepare_started.wait(10)
        from concurrent.futures import TimeoutError
        from threading import Barrier
        transition_requests_started = Barrier(len(routes) + 1)

        def request_during_transition(route):
            transition_requests_started.wait()
            return _request(server, "GET", route)

        with ThreadPoolExecutor(max_workers=len(routes)) as pool:
            transition_requests = tuple(
                pool.submit(request_during_transition, route) for route in routes
            )
            transition_requests_started.wait()
            early_dispositions = []
            for request in transition_requests:
                try:
                    status, _, body = request.result(timeout=0.25)
                except TimeoutError:
                    continue
                early_dispositions.append((status, body))
            assert early_dispositions == []
            release_successor_prepare.set()
            transitioned = tuple(
                request.result(timeout=10) for request in transition_requests
            )
        for worker in workers:
            worker.join(10)
        assert not any(worker.is_alive() for worker in workers)
        assert application.analysis_work_status()["state"] == "IDLE"
        final_status = application.publication_status()
        assert final_status["request_result"] == "SUCCEEDED"
        assert final_status["control"]["current_manifest"] != before_status["control"]["current_manifest"]
        if successor_preparation == "success":
            assert not final_status["reconciliation_unavailable"]
            assert all(status == 200 for status, _, _ in transitioned)
            assert all(
                successor_facts.run_identity in body and "BINDING CURRENT" in body
                for _, _, body in transitioned
            )
        else:
            assert final_status["reconciliation_unavailable"]
            assert all(status == 409 for status, _, _ in transitioned)
            assert all(
                "SWING_PAGE_PREPARATION_UNAVAILABLE" in body
                and committed_run_identity not in body
                and successor_facts.run_identity not in body
                for _, _, body in transitioned
            )
        for route in routes:
            status, _, body = _request(server, "GET", route)
            if successor_preparation == "success":
                assert status == 200
                assert successor_facts.run_identity in body and "BINDING CURRENT" in body
            else:
                assert status == 409
                assert "SWING_PAGE_PREPARATION_UNAVAILABLE" in body
                assert committed_run_identity not in body
                assert successor_facts.run_identity not in body
    finally:
        release.set()
        release_successor_prepare.set()
        for worker in workers:
            worker.join(10)
        server.shutdown()
        server.server_close()
        serving.join(5)


@pytest.mark.parametrize("terminal", ("failure", "cancellation"))
def test_compact_routes_retain_committed_generation_after_unsuccessful_analysis(
    checkpoint, tmp_path, monkeypatch, terminal
):
    """An unsuccessful attempt changes telemetry, not the current manifest."""

    from dataclasses import replace
    from threading import Event
    from kronos.application import swing_opportunities as swing
    from tests.unit.swing.test_run_publication import later
    from tests.unit.browser.test_swing_visual_v3_live import _live

    publication, current_facts, _, committed = checkpoint
    successor_facts = later(current_facts, 2)
    started, release = Event(), Event()
    workers = []
    provider = _Provider()

    def build(*_args, **_kwargs):
        started.set()
        assert release.wait(10)
        if terminal == "failure":
            raise RuntimeError("controlled analysis failure")
        return None

    def runner(operation, name):
        worker = Thread(target=operation, name=name)
        workers.append(worker)
        worker.start()

    monkeypatch.setattr(swing, "build_completed_swing_analysis", build)
    application = SwingOpportunitiesApplication(
        lambda: provider,
        clock=lambda: successor_facts.observed_at,
        background_runner=runner,
        swing_run_identity_factory=lambda: successor_facts.run_identity,
        run_publication=publication,
        mtf_fact_evidence_store=publication.mtf_store,
        native_discovery_evidence_store=publication.native_store,
        relative_context_evidence_store=publication.relative_store,
    )
    application._SwingOpportunitiesApplication__provider = provider
    application._SwingOpportunitiesApplication__snapshot = replace(
        application.snapshot(), provider_state=swing.ProviderConnectionState.CONNECTED
    )
    historical, _, live = _live(tmp_path / "retained-review")
    server = create_browser_server(
        application,
        port=0,
        native_review=historical,
        visual_v3_live=live,
    )
    serving = Thread(target=server.serve_forever, daemon=True)
    serving.start()
    routes = ("/swing/opportunities", "/swing/v1-review")
    current_manifest = application.publication_status()["control"]["current_manifest"]
    current_run = committed.native.run_identity
    try:
        assert application.run_analysis() and started.wait(5)
        for route in routes:
            status, _, body = _request(server, "GET", route)
            assert status == 200 and current_run in body
        if terminal == "cancellation":
            assert application.cancel_analysis()
            assert application.publication_status()["request_result"] == "CANCELLATION_REQUESTED"
            for route in routes:
                status, _, body = _request(server, "GET", route)
                assert status == 200 and current_run in body
        release.set()
        for worker in workers:
            worker.join(10)
        assert not any(worker.is_alive() for worker in workers)
        final = application.publication_status()
        assert final["control"]["current_manifest"] == current_manifest
        assert final["control"]["latest_attempt"]["state"] == "FAILED"
        assert final["control"]["latest_attempt"]["failure_reason"] == (
            "SWING_ANALYSIS_FAILED"
            if terminal == "failure"
            else "SWING_ANALYSIS_INTERRUPTED"
        )
        for route in routes:
            status, _, body = _request(server, "GET", route)
            assert status == 200 and current_run in body
            assert successor_facts.run_identity not in body
            if route == "/swing/opportunities":
                assert "Latest attempt failed" in body
    finally:
        release.set()
        for worker in workers:
            worker.join(10)
        server.shutdown()
        server.server_close()
        serving.join(5)


@pytest.mark.parametrize("native_intake", ["NSE"], indirect=True)
@pytest.mark.parametrize("component", [0, 1])
@pytest.mark.parametrize("fault", ["missing", "json", "schema", "mismatch"])
def test_page_context_rejects_selected_component_fault(native_intake, tmp_path, component, fault):
    import json
    state, _, paths = _page_load_population(native_intake, tmp_path)
    target = paths[component]
    if fault == "missing":
        target.unlink()
    elif fault == "json":
        target.write_text("not JSON")
    else:
        payload = json.loads(target.read_text())
        if fault == "schema":
            payload["schema"] = "UNSUPPORTED"
        else:
            payload["run" if component == 0 else "snapshot"]["run_identity"] = "SWING-RUN-" + "E" * 32
        target.write_text(json.dumps(payload))
    before = _inventory(tmp_path)
    result = native_intake.snapshot()
    assert result["error"] == "SWING_PUBLICATION_BUNDLE_INVALID"
    assert not result["rows"] and result["workspace"] is None
    assert _inventory(tmp_path) == before


@pytest.mark.parametrize("native_intake", ["NSE"], indirect=True)
@pytest.mark.parametrize("change", ["native_bytes", "mtf_bytes", "publication", "chart_pointer"])
def test_page_context_final_fence_rejects_mid_projection_change(native_intake, tmp_path, monkeypatch, change):
    state, _, paths = _page_load_population(native_intake, tmp_path)
    original = native_intake._selection
    changed = []
    def raced(requirement, role, **kwargs):
        value = original(requirement, role, **kwargs)
        if not changed and kwargs.get("_response") is not None:
            changed.append(True)
            if change.endswith("_bytes"):
                target = paths[0 if change == "native_bytes" else 1]
                target.write_bytes(target.read_bytes() + b" ")  # Valid JSON, changed exact bytes.
            elif change == "publication":
                state["control"]["current_manifest"]["sha256"] = "b" * 64
            else:
                # A separate explicit writer has an independent ContextVar readset.
                failures = []
                def publish():
                    try:
                        native_intake.stage("NSE", requirement.canonical_instrument, role,
                            native_intake.expected("NSE", (requirement.canonical_instrument,)),
                            image=PNG, content_type="image/png")
                    except Exception as error:
                        failures.append(error)
                writer = Thread(target=publish); writer.start(); writer.join(10)
                assert not writer.is_alive() and not failures
        return value
    monkeypatch.setattr(native_intake, "_selection", raced)
    result = native_intake.snapshot()
    assert result["error"] == "REVIEW_BINDING_STALE"
    assert result["rows"] == () and result["workspace"] is None


@pytest.mark.parametrize("native_intake", ["NSE"], indirect=True)
def test_get_context_never_authorizes_later_mutation(native_intake, tmp_path):
    from kronos.swing.v1.review_evidence_binding import ReviewEvidenceError
    state, _, _ = _page_load_population(native_intake, tmp_path)
    row = native_intake.snapshot()["rows"][0]
    state["control"]["current_manifest"]["sha256"] = "b" * 64
    before = _inventory(tmp_path)
    with pytest.raises(ReviewEvidenceError, match="REVIEW_BINDING_STALE"):
        native_intake.stage(row["market"], row["instrument"], "NATIVE_NSE", row["expected"],
                            image=PNG, content_type="image/png")
    assert _inventory(tmp_path) == before


@pytest.mark.parametrize("native_intake", ["NSE", "GOLDM"], indirect=True)
def test_response_receipt_package_helpers_share_validated_components(native_intake, tmp_path, monkeypatch):
    import json
    from dataclasses import replace
    from kronos.swing.v1 import native_discovery as native
    from kronos.swing.v1.mtf_facts import MtfFactEvidenceStore
    _, facts, _ = native_intake._context()
    _, run, continuity, status = native_intake.application.opportunities_bundle_projection()
    assessments = tuple(replace(item, result_sha256=native._assessment_digest(item)) for item in run.assessments)
    run = replace(run, assessments=assessments)
    run = replace(run, result_sha256=native._digest(dict(run_identity=run.run_identity,
        provider_source_identity=run.provider_source_identity, observed_at=run.observed_at,
        assessments=run.assessments)))
    native_intake.application.opportunities_bundle_projection = lambda: (None, run, continuity, status)
    stores = (native.NativeDiscoveryEvidenceStore(tmp_path / "components-native"),
              MtfFactEvidenceStore(tmp_path / "components-mtf"))
    paths = (stores[0].retain(run), stores[1].retain(facts))
    native_intake.application.native_discovery_evidence_store = lambda: stores[0]
    native_intake.application.mtf_fact_evidence_store = lambda: stores[1]
    market, instrument, publication, _, _, commit = _accepted_native(native_intake, tmp_path)
    before = _inventory(tmp_path)
    counts = _page_load_counts(monkeypatch, stores, paths)
    with native_intake.response() as prepared:
        result = native_intake.snapshot(_response=prepared)
        assert native_intake.snapshot(_response=prepared) is result
        receipt = commit.receipts[0]
        native_intake._verify_receipt_current(receipt, _response=prepared)
        native_intake.expected(market, (instrument,), _response=prepared)
    print("C1_RECEIPT_COUNTS " + json.dumps(dict(market=market, counts=dict(counts)), sort_keys=True))
    assert counts["native_typed_loads"] == counts["mtf_typed_loads"] == 1
    assert counts["native_file_reads"] == counts["mtf_file_reads"] == 3
    assert result["packages"] and result["rows"][0]["evidence"] == "ACCEPTED"
    assert _inventory(tmp_path) == before
    assert not prepared.active and not prepared.values
    assert native_intake.snapshot(_response=prepared)["error"] == "REVIEW_BINDING_STALE"


@pytest.mark.parametrize("native_intake", ["NSE"], indirect=True)
def test_compact_page_uses_prepared_actual_history_and_inert_status(
    native_intake, tmp_path, monkeypatch
):
    market, instrument, _, _, _, _ = _accepted_native(native_intake, tmp_path)
    assert market == "NSE"
    generation = native_intake.prepare_page_generation()
    assert generation is not None
    monkeypatch.setattr(native_intake, "_history",
                        lambda *a, **k: pytest.fail("GET reconstructed history"))
    monkeypatch.setattr(native_intake, "_publication",
                        lambda *a, **k: pytest.fail("GET reconstructed publication"))
    projection = native_intake.prepared_page_projection(generation)
    assert native_intake.publish_page_generation(generation)
    status = native_intake.page_state_status()
    assert status["state"] == "READY"
    assert status["retained_generations"] == 1
    assert status["retained_input_count"] > 0
    with native_intake.page_response() as prepared:
        assert native_intake.snapshot(_response=prepared) is projection
        row = next(item for item in projection["rows"]
                   if item["instrument"] == instrument)
        assert row["evidence"] == "ACCEPTED"
    from pathlib import Path
    monkeypatch.setattr(Path, "open", lambda *a, **k: pytest.fail("status performed I/O"))
    assert native_intake.page_state_status() == status


@pytest.mark.parametrize("native_intake", ["NSE"], indirect=True)
def test_compact_page_current_pointer_change_is_stale_without_recovery(
    native_intake, tmp_path
):
    _accepted_native(native_intake, tmp_path)
    assert native_intake.prepare_page_state()
    pointer = native_intake.store.root / "current-request.json"
    pointer.write_bytes(pointer.read_bytes() + b" ")
    with pytest.raises(ValueError, match="REVIEW_BINDING_STALE"):
        with native_intake.page_response() as prepared:
            assert native_intake.snapshot(_response=prepared)["rows"]


@pytest.mark.parametrize("native_intake", ["NSE"], indirect=True)
@pytest.mark.parametrize("reason", [
    "REVIEW_REQUEST_MISMATCH", "REVIEW_BINDING_STALE", "ANSWER_PACK_NOT_FOUND",
    "REVIEW_ACCEPTANCE_INCOMPLETE", "ANSWER_FORMAT_INVALID", "REVIEW_JSON_INVALID",
    "REVIEW_CONTRACT_UNSUPPORTED", "REVIEW_UNKNOWN_FIELD", "REVIEW_REQUIRED_FIELD_MISSING",
    "CHART_IDENTITY_MISMATCH", "REVIEW_ARTIFACT_DIGEST_MISMATCH",
    "REVIEW_ANSWER_IDENTITY_CONFLICT", "ANSWER_REPLAY_CONFLICT", "MCX_UNKNOWN_FIELD",
])
def test_swing_answer_rejection_redirect_keeps_current_review_shell(
    native_intake, tmp_path, monkeypatch, reason
):
    from kronos.swing.v1.review_evidence_binding import ReviewEvidenceError
    workflow = native_intake
    market = "NSE"
    instrument = workflow._requirements(market)[0].canonical_instrument
    _stage_native(workflow, market, instrument)
    workflow.generate(market, workflow.expected(market, (instrument,)))
    server = create_browser_server(SwingOpportunitiesApplication(_Provider), port=0,
        native_review=workflow.native_review, visual_v3_live=workflow.live)
    server.native_intake = workflow
    assert workflow.prepare_page_state()
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    authority = f"127.0.0.1:{server.server_port}"
    headers = {"Host": authority, "Origin": f"http://{authority}",
               "Content-Type": "application/x-www-form-urlencoded"}
    calls = []
    def reject(*_args):
        calls.append(reason)
        raise ReviewEvidenceError(reason, "/private/not-for-display")
    monkeypatch.setattr(workflow, "import_from_directory", reject)
    try:
        initial = _request(server, "GET", "/swing/v1-review")[2]
        form_url, form_body = _rendered_form(initial, "native-review-answer")
        before = _inventory(tmp_path)
        status, response_headers, body = _request(server, "POST", form_url,
                                                   headers=headers, body=form_body)
        assert status == 303 and not body
        notice_url = response_headers["Location"]
        assert notice_url.startswith("/swing/v1-review?answer_notice=")
        for _ in range(2):
            status, response_headers, rendered = _request(server, "GET", notice_url)
            assert status == 200 and response_headers["Content-Type"].startswith("text/html")
            assert 'class="sidebar"' in rendered and 'class="wo07-card-grid"' in rendered
            assert '<h3>' + instrument + '</h3>' in rendered
            assert 'role="alert"' in rendered and "ANSWER IMPORT REJECTED" in rendered
            assert "Reason: <code>" + reason + "</code>" in rendered
            assert "Nothing was imported or changed." in rendered
            assert 'href="/swing/v1-review">Current Review</a>' in rendered
            assert 'href="/swing/v1-review#current-question-pack">Question Pack</a>' in rendered
            assert "/private/not-for-display" not in rendered
            assert "Traceback" not in rendered and "PROCESSING" not in rendered.split('answer-rejection-banner', 1)[1].split('</section>', 1)[0]
        assert calls == [reason]
        assert _inventory(tmp_path) == before
        assert _request(server, "GET", "/intraday")[0] == 200
        assert _request(server, "GET", "/status")[0] == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


@pytest.mark.parametrize("native_intake", ["NSE"], indirect=True)
def test_swing_answer_unknown_failure_is_bounded_and_page_level(
    native_intake, tmp_path, monkeypatch
):
    workflow = native_intake
    server = create_browser_server(SwingOpportunitiesApplication(_Provider), port=0,
        native_review=workflow.native_review, visual_v3_live=workflow.live)
    server.native_intake = workflow
    assert workflow.prepare_page_state()
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    authority = f"127.0.0.1:{server.server_port}"
    headers = {"Host": authority, "Origin": f"http://{authority}"}
    def fail(*_args):
        raise RuntimeError("secret=/private/answers/token-cookie")
    monkeypatch.setattr(workflow, "import_from_directory", fail)
    try:
        before = _inventory(tmp_path)
        status, response_headers, _ = _request(server, "POST",
            "/swing/v1/native-review-answer?market=NSE&expected=%7B%7D", headers=headers)
        assert status == 303
        rendered = _request(server, "GET", response_headers["Location"])[2]
        assert "ANSWER IMPORT COULD NOT BE CONFIRMED" in rendered
        assert "REVIEW_INTAKE_UNAVAILABLE" in rendered
        assert "Diagnostic ID: <code>D-" in rendered
        assert "Affected candidate: current Review workspace." in rendered
        assert "Nothing was imported or changed." not in rendered
        assert "secret=" not in rendered and "/private/" not in rendered
        assert "Traceback" not in rendered and "token-cookie" not in rendered
        assert _inventory(tmp_path) == before
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


@pytest.mark.parametrize("native_intake", ["NSE"], indirect=True)
def test_swing_answer_rejection_does_not_claim_no_change_after_pointer_transition(
    native_intake, monkeypatch
):
    from kronos.browser.server import _BrowserHandler
    from kronos.swing.v1.review_evidence_binding import ReviewEvidenceError
    workflow = native_intake
    instrument = workflow._requirements("NSE")[0].canonical_instrument
    _stage_native(workflow, "NSE", instrument)
    workflow.generate("NSE", workflow.expected("NSE", (instrument,)))
    server = create_browser_server(SwingOpportunitiesApplication(_Provider), port=0,
        native_review=workflow.native_review, visual_v3_live=workflow.live)
    server.native_intake = workflow
    assert workflow.prepare_page_state()
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    authority = f"127.0.0.1:{server.server_port}"
    headers = {"Host": authority, "Origin": f"http://{authority}",
               "Content-Type": "application/x-www-form-urlencoded"}
    markers = iter((b"before", b"after"))
    monkeypatch.setattr(_BrowserHandler, "_answer_acceptance_marker",
                        staticmethod(lambda *_args: next(markers)))
    def reject(*_args):
        raise ReviewEvidenceError("REVIEW_BINDING_STALE")
    monkeypatch.setattr(workflow, "import_from_directory", reject)
    try:
        form_url, form_body = _rendered_form(_request(server, "GET", "/swing/v1-review")[2],
                                             "native-review-answer")
        status, response_headers, _ = _request(server, "POST", form_url,
                                                headers=headers, body=form_body)
        assert status == 303
        rendered = _request(server, "GET", response_headers["Location"])[2]
        assert "ANSWER IMPORT COULD NOT BE CONFIRMED" in rendered
        assert "REVIEW_INTAKE_UNAVAILABLE" in rendered
        assert "Nothing was imported or changed." not in rendered
        assert "Diagnostic ID: <code>D-" in rendered
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
