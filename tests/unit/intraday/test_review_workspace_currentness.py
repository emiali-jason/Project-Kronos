"""WO-07B1 exact producer-generation workspace and mutation boundaries."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
import json
from threading import Event

import pytest

from kronos.application.intraday_review_v2 import IntradayReviewV2Application
from kronos.browser.intraday_review_v2_control import IntradayReviewV2OperationalControl
from kronos.browser.intraday_views import _review_v2_projection, _review_v2_inbox_result
from kronos.intraday.probables_v2 import create_probables_v2_methodology, evaluate_probables_v2_run
from kronos.intraday.probables_v2_persistence import ProbablesV2Store
from kronos.intraday.review import ReviewError, ReviewFailure
from kronos.intraday.review_v2_operation_persistence import ReviewV2OperationProvenanceStore
from kronos.intraday.review_v2_persistence import IntradayReviewV2Store
from tests.unit.intraday.test_opening_admission_correction import opening_mapping
from tests.unit.intraday.test_probables_v2 import PROVENANCE, SOURCE_RUN
from tests.unit.intraday.test_review import _png
from tests.unit.intraday.test_review_v2 import _retain_later_current_run
from tests.unit.intraday.test_review_v2_individual_inbox import _fixture, _completed


def hashes(root):
    return {str(p.relative_to(root)): sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def load(app, run):
    m = run.methodology
    return app.currentize_eligible_cycles_for_run_identity(
        probables_run_identity=run.run_identity, methodology_identity=m.methodology_identity,
        methodology_version=m.methodology_version,
        methodology_publication_identity=m.publication_identity, methodology_checksum=m.payload_checksum)


def publish(app, subjects, *, direction="LONG", narrow=True):
    methodology = create_probables_v2_methodology()
    mappings = tuple(opening_mapping(methodology, subject="NSE-EQ-" + subject,
                                    direction=direction, narrow=narrow) for subject in subjects)
    first = mappings[0]
    run = evaluate_probables_v2_run(source_discovery_run_identity=SOURCE_RUN,
        universe_identity="KRONOS-INTRADAY-NATIVE-UNIVERSE-V1", universe_version="1.0.0",
        reconciliation_identity="KRONOS-INTRADAY-RECONCILIATION-V1", reconciliation_version="1.0.0",
        market_session_identity=first.market_session_identity, analysis_boundary=first.analysis_boundary,
        member_evidence=mappings, unavailable_members=(), provenance=PROVENANCE, methodology=methodology)
    app.probables_store.retain_complete(run=run, mappings=mappings)
    return run


def restore(app):
    restored = IntradayReviewV2Application(probables_store=ProbablesV2Store(app.probables_store.root),
        review_store=IntradayReviewV2Store(app.review_store.root), transport=app._transport,
        visual_identity_resolver=app._visual_identity_resolver, clock=app._clock)
    from tests.unit.intraday.chart_input_fixtures import configure_fixture_calendar
    configure_fixture_calendar(restored)
    return restored


def answer_ready(app, *, combined=False):
    cycles = app.snapshot().candidates
    for n, c in enumerate(cycles):
        app.upload_chart(c.cycle_identity, media_type="image/png", payload=_png(n + 21))
    if combined:
        results = (app.create_combined_question_transport(),)
    else:
        results = tuple(app.create_individual_question_transport(c.cycle_identity) for c in cycles)
    for result in results:
        (app._transport.answer_inbox / result.transport.expected_answer_filename).write_bytes(
            _completed(result.answer_template_path))
    return cycles, results


@pytest.mark.parametrize("old_count,new_count", [(9, 8), (8, 9), (1, 3), (3, 1)])
@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
def test_exact_population_replacement_and_direction(tmp_path, old_count, new_count, direction):
    old_subjects = tuple(["NTPC"] + ["OLD" + str(i) for i in range(old_count - 1)])
    run_a, app = _fixture(tmp_path, old_subjects)
    old_pointer = app.review_store.load_current()
    before = hashes(app.review_store.root)
    new_subjects = tuple(["NTPC"] + ["NEW" + str(i) for i in range(new_count - 1)])
    run_b = publish(app, new_subjects, direction=direction)
    assert run_a.run_identity != run_b.run_identity
    assert app.workspace_state() == "REVIEW_NON_CURRENT"
    assert app.snapshot().candidates == ()
    assert app.review_store.load_current() == old_pointer
    assert hashes(app.review_store.root) == before
    result = load(app, run_b)
    assert not result.retained and len(result.cycles) == new_count
    active = app.snapshot()
    assert {c.sponsor_label for c in active.candidates} == set(new_subjects)
    assert {c.direction for c in active.candidates} == {direction}
    assert all(c.chart_state == "CHART_REQUIRED" for c in active.candidates)
    assert active.probables_run_identity == run_b.run_identity
    assert all(hashes(app.review_store.root)[key] == value for key, value in before.items()
               if key != "current/CURRENT-REVIEW-V2-POINTER.json")
    after = hashes(app.review_store.root)
    assert load(app, run_b).retained
    assert hashes(app.review_store.root) == after


@pytest.mark.parametrize("state", ["NO_REVIEW_LOADED", "CURRENT_REVIEW_LOADED", "REVIEW_NON_CURRENT"])
def test_restart_restores_truth_without_currentization(tmp_path, state):
    run, app = _fixture(tmp_path, ("NTPC",))
    if state == "NO_REVIEW_LOADED":
        (app.review_store.root / "current/CURRENT-REVIEW-V2-POINTER.json").unlink()
    elif state == "REVIEW_NON_CURRENT":
        _retain_later_current_run(app)
    before = hashes(tmp_path)
    restored = restore(app)
    assert restored.workspace_state() == state
    assert len(restored.snapshot().candidates) == int(state == "CURRENT_REVIEW_LOADED")
    assert hashes(tmp_path) == before
    if state == "CURRENT_REVIEW_LOADED":
        _retain_later_current_run(restored)
        assert app.workspace_state() == restored.workspace_state() == "REVIEW_NON_CURRENT"


def test_zero_candidate_generation_can_be_explicitly_loaded(tmp_path):
    _, app = _fixture(tmp_path, ("NTPC",))
    run = publish(app, ("NTPC",), narrow=False)
    assert all(r.state.value not in ("LONG_PROBABLE", "SHORT_PROBABLE") for r in run.results)
    assert app.workspace_state() == "REVIEW_NON_CURRENT"
    assert load(app, run).cycles == ()
    assert app.workspace_state() == "CURRENT_REVIEW_LOADED"
    assert app.snapshot().candidates == ()
    assert restore(app).workspace_state() == "CURRENT_REVIEW_LOADED"
    assert load(app, run).retained


@pytest.mark.parametrize("action", ["chart", "individual_pack", "batch_pack", "individual_answer", "batch_answer", "manual_answer"])
def test_new_operations_after_advance_fail_closed_without_writes(tmp_path, action):
    _, app = _fixture(tmp_path, ("NTPC",))
    cycles, results = answer_ready(app, combined=action == "manual_answer")
    cycle = cycles[0].cycle_identity
    _retain_later_current_run(app)
    before = hashes(tmp_path)
    operations = {
        "chart": lambda: app.upload_chart(cycle, media_type="image/png", payload=_png(66)),
        "individual_pack": lambda: app.create_individual_question_transport(cycle),
        "batch_pack": app.create_combined_question_transport,
        "individual_answer": lambda: app.import_expected_answer(cycle),
        "batch_answer": app.import_all_expected_answers,
        "manual_answer": lambda: app.import_combined_answer(_completed(results[0].answer_template_path)),
    }
    if action == "individual_answer":
        result = operations[action]()
        assert result.imported_count == 0
        assert result.members[0].reason == ReviewFailure.NOT_CURRENT.value
    else:
        with pytest.raises(ReviewError, match=ReviewFailure.NOT_CURRENT.value):
            operations[action]()
    assert hashes(tmp_path) == before


@pytest.mark.parametrize("fresh_replacement", [False, True])
@pytest.mark.parametrize("manual", [False, True])
def test_historical_identical_replay_preserves_every_byte(tmp_path, fresh_replacement, manual):
    _, app = _fixture(tmp_path, ("NTPC",))
    cycles, results = answer_ready(app, combined=manual)
    payload = _completed(results[0].answer_template_path)
    invoke = (lambda: app.import_combined_answer(payload)) if manual else (lambda: app.import_expected_answer(cycles[0].cycle_identity))
    assert invoke().imported_count == 1
    newer = _retain_later_current_run(app)
    if fresh_replacement:
        load(app, newer)
    before = hashes(tmp_path)
    result = invoke()
    assert result.imported_count == 0 and result.already_imported_count == 1
    assert hashes(tmp_path) == before


@pytest.mark.parametrize("manual", [False, True])
def test_conflicting_replay_after_advance_rejected(tmp_path, manual):
    _, app = _fixture(tmp_path, ("NTPC",))
    cycles, results = answer_ready(app, combined=manual)
    payload = _completed(results[0].answer_template_path)
    if manual:
        app.import_combined_answer(payload)
    else:
        app.import_expected_answer(cycles[0].cycle_identity)
    _retain_later_current_run(app)
    doc = json.loads(payload)
    doc["candidates"][0]["answers"][0]["visible_basis"] = "Different retained observation."
    changed = json.dumps(doc).encode()
    path = app._transport.answer_inbox / results[0].transport.expected_answer_filename
    path.write_bytes(changed)
    before = hashes(tmp_path)
    if manual:
        with pytest.raises(ReviewError, match=ReviewFailure.ANSWER_CONFLICT.value):
            app.import_combined_answer(changed)
    else:
        result = app.import_expected_answer(cycles[0].cycle_identity)
        assert result.members[0].reason == ReviewFailure.ANSWER_CONFLICT.value
    assert hashes(tmp_path) == before


@pytest.mark.parametrize("combined", [False, True])
def test_partial_batch_stops_new_members_and_restores(tmp_path, monkeypatch, combined):
    _, app = _fixture(tmp_path, ("BDL", "NTPC", "TITAN"))
    cycles, _ = answer_ready(app, combined=combined)
    original = app.review_store.save_visual_evidence_pointer
    advanced = False
    def save_then_advance(value):
        nonlocal advanced
        result = original(value)
        if not advanced:
            advanced = True
            _retain_later_current_run(app)
        return result
    monkeypatch.setattr(app.review_store, "save_visual_evidence_pointer", save_then_advance)
    result = app.import_all_expected_answers()
    assert result.imported_count == 1 and result.rejected_count == 2
    assert result.state == "PARTIAL_PRODUCER_ADVANCED"
    assert sum(x.reason == ReviewFailure.NOT_CURRENT.value for x in result.members) == 2
    assert "PARTIAL PRODUCER ADVANCED" in _review_v2_inbox_result(result)
    assert app.snapshot().candidates == ()
    before = hashes(tmp_path)
    restored = restore(app)
    assert restored.workspace_state() == "REVIEW_NON_CURRENT"
    assert hashes(tmp_path) == before
    assert len(list((app.review_store.root / "visual-evidence").glob("*.json"))) == 1


def test_final_batch_boundary_reports_advance_without_recurrentizing(tmp_path, monkeypatch):
    _, app = _fixture(tmp_path, ("BDL",))
    answer_ready(app, combined=True)
    original = app._persist_prepared_answer
    def persist_then_advance(*args):
        result = original(*args)
        _retain_later_current_run(app)
        return result
    monkeypatch.setattr(app, "_persist_prepared_answer", persist_then_advance)
    result = app.import_all_expected_answers()
    assert result.imported_count == 1 and result.producer_advanced
    assert result.state == "PARTIAL_PRODUCER_ADVANCED"
    assert app.workspace_state() == "REVIEW_NON_CURRENT"


@pytest.mark.parametrize("stage", ["prepare", "publish"])
def test_advance_during_fresh_load_keeps_old_pointer(tmp_path, monkeypatch, stage):
    _, app = _fixture(tmp_path, ("NTPC",))
    old = app.review_store.load_current()
    run_b = publish(app, ("BDL", "TITAN"))
    method = "_retain_eligible_cycles" if stage == "prepare" else "_publish_current_review"
    original = getattr(app, method)
    def advance(*args):
        if stage == "prepare":
            result = original(*args)
            _retain_later_current_run(app)
            return result
        _retain_later_current_run(app)
        return original(*args)
    monkeypatch.setattr(app, method, advance)
    with pytest.raises(ReviewError, match=ReviewFailure.NOT_CURRENT.value):
        load(app, run_b)
    assert app.review_store.load_current() == old
    assert app.snapshot().candidates == ()


@pytest.mark.parametrize("failure", ["cycle", "pointer"])
def test_partial_preparation_failure_can_retry_without_mixed_population(tmp_path, monkeypatch, failure):
    _, app = _fixture(tmp_path, ("NTPC",))
    before = hashes(app.review_store.root)
    run = publish(app, ("BDL", "TITAN"))
    name = "retain_cycle" if failure == "cycle" else "save_current"
    original = getattr(app.review_store, name)
    def fail(value):
        raise OSError("ISOLATED_FAILURE")
    monkeypatch.setattr(app.review_store, name, fail)
    with pytest.raises(OSError):
        load(app, run)
    after = hashes(app.review_store.root)
    assert all(after[k] == v for k, v in before.items())
    assert app.snapshot().candidates == ()
    monkeypatch.setattr(app.review_store, name, original)
    assert len(load(app, run).cycles) == 2
    assert {c.sponsor_label for c in app.snapshot().candidates} == {"BDL", "TITAN"}


@pytest.mark.parametrize("tamper", ["bytes", "foreign"])
def test_invalid_pointer_never_exposes_current_cards(tmp_path, tamper):
    _, app = _fixture(tmp_path, ("NTPC",))
    path = app.review_store.root / "current/CURRENT-REVIEW-V2-POINTER.json"
    if tamper == "bytes":
        doc = json.loads(path.read_bytes())
        doc["integrity_identity"] = "TAMPERED"
        path.write_text(json.dumps(doc))
        with pytest.raises(ReviewError):
            restore(app).snapshot()
    else:
        _, other = _fixture(tmp_path / "foreign", ("BDL",))
        path.write_bytes((other.review_store.root / "current/CURRENT-REVIEW-V2-POINTER.json").read_bytes())
        with pytest.raises(ReviewError):
            app.snapshot()
    control = IntradayReviewV2OperationalControl(app, ReviewV2OperationProvenanceStore(app.review_store.root))
    status = control.status_document()
    assert status["workspace_state"] == "INTEGRITY_INVALID" and status["cycle_count"] == 0


def test_two_fresh_requests_share_one_workspace_publication(tmp_path):
    _, app = _fixture(tmp_path, ("NTPC",))
    run = publish(app, ("BDL", "TITAN"))
    other = restore(app)
    assert app.review_store.workspace_lock is other.review_store.workspace_lock
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda a: load(a, run), (app, other)))
    assert sorted(x.retained for x in results) == [False, True]
    assert results[0].cycles == results[1].cycles


def test_producer_publication_waits_for_consumer_critical_section(tmp_path):
    _, app = _fixture(tmp_path, ("NTPC",))
    other = ProbablesV2Store(app.probables_store.root)
    entered, attempted, finished = Event(), Event(), Event()
    pointer = other.load_current()
    def publish_pointer():
        attempted.set()
        other.save_current(pointer)
        finished.set()
    with ThreadPoolExecutor(max_workers=1) as pool:
        with app.probables_store.current_generation_guard():
            future = pool.submit(publish_pointer)
            assert attempted.wait(2)
            assert not finished.wait(0.05)
        future.result(timeout=2)
    assert finished.is_set()


@pytest.mark.parametrize("action", ["pack", "answer", "chart"])
def test_generation_advance_during_operation_preparation_rejects(tmp_path, monkeypatch, action):
    _, app = _fixture(tmp_path, ("NTPC",))
    cycles, results = answer_ready(app)
    cycle = cycles[0].cycle_identity
    if action == "pack":
        original = app._create_question_transport
        def changed(entries):
            _retain_later_current_run(app)
            return original(entries)
        monkeypatch.setattr(app, "_create_question_transport", changed)
        invoke = lambda: app.create_individual_question_transport(cycle)
    elif action == "answer":
        original = app._persist_prepared_answer
        def changed(*args):
            _retain_later_current_run(app)
            return original(*args)
        monkeypatch.setattr(app, "_persist_prepared_answer", changed)
        result = app.import_expected_answer(cycle)
        assert result.imported_count == 0 and result.rejected_count == 1
        return
    else:
        import kronos.application.intraday_review_v2 as module
        original = module.create_chart_revision_v2
        def changed(*args, **kwargs):
            value = original(*args, **kwargs)
            _retain_later_current_run(app)
            return value
        monkeypatch.setattr(module, "create_chart_revision_v2", changed)
        invoke = lambda: app.upload_chart(cycle, media_type="image/png", payload=_png(99))
    with pytest.raises(ReviewError, match=ReviewFailure.NOT_CURRENT.value):
        invoke()


def test_browser_stale_cards_and_controls_hidden_get_is_inert(tmp_path):
    _, app = _fixture(tmp_path, ("BDL", "NTPC"))
    control = IntradayReviewV2OperationalControl(app, ReviewV2OperationProvenanceStore(app.review_store.root))
    run = _retain_later_current_run(app)
    before = hashes(tmp_path)
    status = control.status_document()
    page = _review_v2_projection(app.snapshot(), run, status)
    assert "REVIEW NON CURRENT" in page and "LOAD FRESH REVIEW" in page
    assert "data-cycle=" not in page and "IMPORT ALL EXPECTED ANSWERS" not in page
    assert "CREATE ALL REVIEW PDF" not in page
    assert status["cycle_count"] == 0
    assert hashes(tmp_path) == before


@pytest.mark.parametrize("kind", ["missing", "empty"])
def test_browser_exposes_explicit_load_for_no_review_and_empty_generation(tmp_path, kind):
    run, app = _fixture(tmp_path, ("NTPC",))
    if kind == "missing":
        (app.review_store.root / "current/CURRENT-REVIEW-V2-POINTER.json").unlink()
    else:
        run = publish(app, ("NTPC",), narrow=False)
    control = IntradayReviewV2OperationalControl(app, ReviewV2OperationProvenanceStore(app.review_store.root))
    status = control.status_document()
    page = _review_v2_projection(app.snapshot(), run, status)
    assert "LOAD FRESH REVIEW" in page
    assert "data-cycle=" not in page
    assert status["workspace_state"] == ("NO_REVIEW_LOADED" if kind == "missing" else "REVIEW_NON_CURRENT")


def test_browser_discards_snapshot_if_status_observes_producer_advance(tmp_path, monkeypatch):
    _, app = _fixture(tmp_path, ("NTPC",))
    old_snapshot = app.snapshot()
    run = _retain_later_current_run(app)
    monkeypatch.setattr(app, "snapshot", lambda: old_snapshot)
    control = IntradayReviewV2OperationalControl(app, ReviewV2OperationProvenanceStore(app.review_store.root))
    status = control.status_document()
    assert status["cycle_count"] == 0
    page = _review_v2_projection(old_snapshot, run, status)
    assert "data-cycle=" not in page


@pytest.mark.parametrize("replay", [False, True])
def test_paired_import_retains_same_currentness_boundary(tmp_path, replay):
    from tests.unit.intraday.test_review_v2_paired_intake import paired_fixture, complete_paired
    from tests.unit.intraday.chart_input_fixtures import retain_legacy_paired_fixture
    app, cycle, metadata = paired_fixture(tmp_path)
    chart = app.upload_chart(cycle.cycle_identity, media_type="image/png", payload=_png(88), paired_metadata=metadata)
    result = app.create_individual_question_transport(cycle.cycle_identity)
    complete_paired(app, result)
    if replay:
        assert app.import_expected_answer(cycle.cycle_identity).members[0].reason == ReviewFailure.CHART_CORRESPONDENCE_UNVERIFIABLE.value
        retain_legacy_paired_fixture(app, cycle, chart)
    _retain_later_current_run(app)
    before = hashes(tmp_path)
    result = app.import_expected_answer(cycle.cycle_identity)
    assert result.imported_count == 0
    if replay:
        assert result.already_imported_count == 1
    else:
        assert result.members[0].reason == ReviewFailure.NOT_CURRENT.value
    assert hashes(tmp_path) == before
    with pytest.raises(ReviewError, match=ReviewFailure.NOT_CURRENT.value):
        app.create_individual_question_transport(cycle.cycle_identity)


def test_independent_invalid_batch_member_does_not_block_valid_member(tmp_path):
    _, app = _fixture(tmp_path, ("BDL", "NTPC"))
    _, results = answer_ready(app, combined=True)
    path = app._transport.answer_inbox / results[0].transport.expected_answer_filename
    doc = json.loads(path.read_bytes())
    doc["candidates"][0]["observed_visible_subject_identity"] = "FOREIGN VISUAL SUBJECT"
    path.write_text(json.dumps(doc))
    result = app.import_all_expected_answers()
    assert result.imported_count == 1 and result.rejected_count == 1
    assert not result.producer_advanced
    assert app.workspace_state() == "CURRENT_REVIEW_LOADED"
