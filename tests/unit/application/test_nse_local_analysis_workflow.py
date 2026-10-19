"""LOCAL-02 actual-owner integration using isolated synthetic retained evidence.

The real LOCAL-01 mathematics and Native Review/currentness owner are exercised.
No fixture is production market evidence or an accepted Review Answer.
"""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
import json
from pathlib import Path
import socket
from types import SimpleNamespace

import pytest

from kronos.application import swing_opportunities as opportunities_module
from kronos.application import swing_local_analysis as local_module
from kronos.application.swing_local_analysis import SwingLocalAnalysisWorkflow
from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.application.swing_prospective_research import SwingProspectiveResearchApplication
from kronos.application.swing_visual_v3_live import NativeReviewIntakeWorkflow
from kronos.common.maintenance_admission import MaintenanceAdmissionCoordinator
from kronos.swing.v1.prospective_research import ProspectiveResearchStore, record
from kronos.swing.v1.review_evidence_store import ReviewEvidenceStore
from kronos.swing.v1.nse_local_analysis import decode_input, decode_result
from tests.unit.application.test_swing_opportunities import _Provider, _ready
from tests.unit.swing.v1.test_nse_local_analysis import _case, PUBLICATION
from tests.unit.browser.test_swing_visual_v3_live import _live
from tests.unit.swing.test_run_publication import checkpoint, scenario


@pytest.fixture
def nse_checkpoint(tmp_path, scenario):
    from tests.unit.swing.test_run_publication import make_checkpoint
    from tests.unit.application.test_swing_weekly_facts import _build, _history
    from kronos.swing.v1.native_discovery import discover_native_mtf, NativeDiscoveryStatus
    snapshot, bindings = scenario
    foundation, _, _ = _build(_history('rising'), observed_at=snapshot.observed_at)
    replacement = replace(snapshot.instrument('RELIANCE'),
        timeframes=tuple(replace(f, observation_boundary=f.observation_boundary - timedelta(hours=4),
            source_timestamp=f.source_timestamp - timedelta(hours=4),
            source_market_data_boundary=f.source_market_data_boundary - timedelta(hours=4))
            if f.timeframe.value == '4H' else f for f in snapshot.instrument('GOLDM').timeframes),
        nse_weekly_foundation=foundation,
        completed_series=(), reference_facts=(), one_hour_atr=None)
    snapshot = replace(snapshot, instruments=tuple(replacement if i.canonical_instrument == 'RELIANCE' else i
        for i in snapshot.instruments))
    assert next(a for a in discover_native_mtf(snapshot).assessments
                if a.canonical_instrument == 'RELIANCE').status is NativeDiscoveryStatus.PROBABLE
    return make_checkpoint(tmp_path / 'nse-checkpoint', snapshot, bindings)


def _fresh_completed_successor(service, snapshot, bindings, predecessor):
    """A newly completed synthetic 4H observation, not uncertain old-bar reuse."""
    from tests.unit.application.test_swing_run_publication import _completed_successor
    from kronos.swing.v1.native_discovery import NativeDiscoveryStatus, NativeProductPath
    instrument = snapshot.instrument('RELIANCE')
    fresh = replace(instrument, timeframes=tuple(replace(f,
        observation_boundary=f.observation_boundary + timedelta(hours=4),
        source_timestamp=f.source_timestamp + timedelta(hours=4),
        source_market_data_boundary=f.source_market_data_boundary + timedelta(hours=4))
        if f.timeframe.value == '4H' else f for f in instrument.timeframes))
    assert all(f.observation_boundary <= snapshot.observed_at for f in fresh.timeframes)
    snapshot = replace(snapshot, instruments=tuple(fresh if i.canonical_instrument == 'RELIANCE' else i
        for i in snapshot.instruments))
    completed = _completed_successor(service, snapshot, bindings, predecessor)
    native = next(a for a in completed.native_discovery_run.assessments
        if a.canonical_instrument == 'RELIANCE')
    assert native.product_path is NativeProductPath.NSE
    assert native.status is NativeDiscoveryStatus.PROBABLE, native
    return completed


def _inventory(root):
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in Path(root).rglob('*') if p.is_file()}


def _commission(research, at):
    marker = record('COMMISSIONING', release_identity='SYNTHETIC-RELEASE',
        source_manifest_sha256='a' * 64, owner_manifest_sha256=None,
        commissioned_at=(at - timedelta(days=1)).isoformat(),
        authority='PROSPECTIVE_CAPTURE_BOUNDARY')
    with research.store.transaction():
        research.store.retain(marker)
        research.store.publish_pointer('COMMISSIONING', 'active', marker)
    return marker


def _rig(tmp_path, *, arguments=None, commissioned=True):
    requirement, native, facts = arguments or _case()
    state = dict(native=native, facts=facts, manifest=PUBLICATION, unavailable=False, generation=1, attempt_state='SUCCEEDED')
    def control():
        return {'current_manifest': {'sha256': state['manifest']},
                'admission_generation': state['generation'],
                'latest_attempt': {'run_id': state['native'].run_identity, 'state': state['attempt_state']}}
    application = SwingOpportunitiesApplication(_Provider, initial_snapshot=replace(
        _ready(), swing_analysis_run_identity=native.run_identity,
        run_created_at=facts.observed_at, observation_boundary=facts.observed_at,
        completed_at=facts.observed_at))
    application.restore_native_discovery_run(native)
    application.restore_mtf_fact_snapshot(facts)
    def bundle():
        return (application.snapshot(), state['native'], None, dict(
            control=control(),
            reconciliation_unavailable=state['unavailable']))
    application.opportunities_bundle_projection = bundle
    application.mtf_fact_snapshot = lambda: state['facts']
    application.current_run_control_authority = lambda: (state['native'], control())
    application.publication_status = lambda: dict(control=control(), reconciliation_unavailable=state['unavailable'],
        request_result='SUCCEEDED', analysis_work=dict(application.analysis_work_status()))
    @contextmanager
    def guard():
        yield SimpleNamespace(control=control(),
                              manifest={'run_id': state['native'].run_identity})
    application.publication_mutation_guard = guard
    review, _, live = _live(tmp_path / 'native-owners')
    intake = NativeReviewIntakeWorkflow(application, review, live,
                                       ReviewEvidenceStore(tmp_path / 'intake'))
    research = SwingProspectiveResearchApplication(
        store=ProspectiveResearchStore((tmp_path / 'research').resolve()),
        publication_root=(tmp_path / 'publication').resolve(),
        clock=lambda: facts.observed_at + timedelta(minutes=1))
    marker = _commission(research, facts.observed_at) if commissioned else None
    owner = SwingLocalAnalysisWorkflow(application, intake, research,
        clock=lambda: facts.observed_at + timedelta(minutes=1))
    application.register_local_analysis(owner)
    intake.register_local_analysis(owner)
    return SimpleNamespace(application=application, intake=intake, research=research,
        owner=owner, state=state, requirement=requirement, marker=marker, root=tmp_path)


def _refresh(rig, **kwargs):
    return rig.owner.refresh(run_identity=rig.state['native'].run_identity,
        publication_sha256=rig.state['manifest'],
        requirement_id=rig.requirement.requirement_sha256, **kwargs)


def _projection(rig):
    with rig.intake.response() as response:
        return rig.owner.projection(_response=response)


def _row(rig):
    result = _projection(rig)
    return next(r for r in result['rows']
                if r['instrument'] == rig.requirement.canonical_instrument)


def _originals(rig):
    return rig.research.store.records('LOCAL_ANALYSIS_ORIGINAL')


def _deny_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('LOCAL02 attempted network/model/Provider acquisition')
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket.socket, 'connect_ex', forbidden)
    import urllib.request
    monkeypatch.setattr(urllib.request, 'urlopen', forbidden)
    return forbidden


def _trace_automatic_guard(service, monkeypatch):
    evidence = []
    capture = service._SwingOpportunitiesApplication__capture_local_analysis
    def traced(work, committed):
        _, native, _, status = service.opportunities_bundle_projection()
        evidence.append(dict(
            work_current=service._SwingOpportunitiesApplication__analysis_work_current(work),
            committed_is=service._SwingOpportunitiesApplication__committed_run is committed,
            mcx_handoff=work.mcx_handoff is not None,
            request_result=service._SwingOpportunitiesApplication__analysis_request_result,
            reconciliation_failure=service._SwingOpportunitiesApplication__reconciliation_failure,
            projection_status=status, native_is=native is committed.native,
            native_equal=native == committed.native,
            probables=[(a.canonical_instrument,a.product_path.value,a.status.value)
                for a in committed.native.assessments if a.status.value == 'PROBABLE'],
            nse_states=[(a.canonical_instrument,a.status.value,a.weekly_state.value,a.reason_codes)
                for a in committed.native.assessments if a.canonical_instrument == 'RELIANCE'],
        ))
        return capture(work, committed)
    monkeypatch.setattr(service, '_SwingOpportunitiesApplication__capture_local_analysis', traced)
    return evidence


def test_manual_retained_source_creates_valid_original_with_exact_engine_output(tmp_path, monkeypatch):
    rig = _rig(tmp_path)
    forbidden = _deny_network(monkeypatch)
    monkeypatch.setattr(rig.application, 'run_analysis', forbidden)
    monkeypatch.setattr(rig.application, 'authenticated_read_only_capability', forbidden)
    marker = _inventory(rig.research.store.root / 'current')
    _refresh(rig)
    original, = _originals(rig)
    data = original.data
    source = decode_input(data['input_json'])
    result = decode_result(data['result_json'], source, expected_source=source.binding)
    assert data['input_sha256'] == source.identity
    assert data['output_sha256'] == result.identity
    assert data['method_version'] == 'KRONOS-NSE-LOCAL-RESEARCH-1.0'
    assert data['operation_identity']
    assert data['captured_at'] and data['completed_at']
    assert result.to_dict()['visual'] == {'Q3':'UNKNOWN','Q5':'UNKNOWN','Q10':'UNKNOWN'}
    row = _row(rig)
    assert row['state'] == 'SUCCEEDED' and row['result'] == result.to_dict()
    assert row['original_identity'] == original.identity
    assert _inventory(rig.research.store.root / 'current') == marker
    assert not rig.research.store.records('ORIGIN')
    assert not rig.research.store.records('MILESTONE')


def test_unchanged_manual_auto_and_restart_reuse_original_without_engine_or_store_write(tmp_path, monkeypatch):
    rig = _rig(tmp_path)
    _refresh(rig)
    original, = _originals(rig)
    before = _inventory(tmp_path)
    def forbidden(*a, **k):
        pytest.fail('Unchanged evidence must not be recalculated')
    monkeypatch.setattr(local_module, 'analyze_local', forbidden)
    _refresh(rig)
    _refresh(rig, trigger='AUTOMATIC')
    rig.owner.close()
    restarted = SwingLocalAnalysisWorkflow(rig.application, rig.intake, rig.research,
        clock=lambda: rig.state['facts'].observed_at + timedelta(days=1))
    rig.owner = restarted
    restarted.prepare()
    _refresh(rig)
    assert _originals(rig) == (original,)
    assert _row(rig)['result'] is not None
    assert _inventory(tmp_path) == before


@pytest.mark.parametrize('change', ['publication','native','facts'])
def test_final_source_change_keeps_completed_original_but_withholds_current_result(tmp_path, monkeypatch, change):
    rig = _rig(tmp_path)
    analyze = local_module.analyze_local
    outputs = []
    def raced(source, **kwargs):
        result = analyze(source, **kwargs)
        outputs.append(result)
        if change == 'publication':
            rig.state['manifest'] = 'b' * 64
        elif change == 'native':
            rig.state['native'] = replace(rig.state['native'], assessments=tuple(
                replace(a, result_sha256='c' * 64) if a.canonical_instrument == rig.requirement.canonical_instrument else a
                for a in rig.state['native'].assessments))
        else:
            facts = rig.state['facts']
            rig.state['facts'] = replace(facts, instruments=tuple(
                replace(i, timeframes=tuple(replace(f, close=99.0) for f in i.timeframes))
                if i.canonical_instrument == rig.requirement.canonical_instrument else i
                for i in facts.instruments))
        return result
    monkeypatch.setattr(local_module, 'analyze_local', raced)
    _refresh(rig)
    original, = _originals(rig)
    assert original.data['result_json'] == outputs[0].to_json()
    assert original.data['output_sha256'] == outputs[0].identity
    dispositions = rig.research.store.records('LOCAL_ANALYSIS_DISPOSITION')
    assert any(d.data['state'] == 'STALE' and d.data['original_identity'] == original.identity
               for d in dispositions)
    assert all(row.get('result') is None for row in _projection(rig)['rows'])
    before = _inventory(tmp_path)
    restored = SwingLocalAnalysisWorkflow(rig.application, rig.intake, rig.research,
        clock=lambda: rig.state['facts'].observed_at + timedelta(days=1))
    restored.prepare()
    assert all(row.get('result') is None for row in restored.projection()['rows'])
    assert _inventory(tmp_path) == before


@pytest.mark.parametrize('wrong', ['run','publication','requirement'])
def test_stale_manual_form_fails_before_engine_and_retention(tmp_path, monkeypatch, wrong):
    rig = _rig(tmp_path)
    before = _inventory(tmp_path)
    monkeypatch.setattr(local_module, 'analyze_local', lambda *a, **k: pytest.fail('stale input analyzed'))
    fields = dict(run_identity=rig.state['native'].run_identity,
        publication_sha256=rig.state['manifest'], requirement_id=rig.requirement.requirement_sha256)
    fields[{'run':'run_identity','publication':'publication_sha256','requirement':'requirement_id'}[wrong]] = (
        'SWING-RUN-' + 'F' * 32 if wrong == 'run' else 'f' * 64)
    with pytest.raises(ValueError):
        rig.owner.refresh(**fields)
    assert _inventory(tmp_path) == before


def test_missing_commissioning_does_not_create_or_present_persisted_original(tmp_path, monkeypatch):
    rig = _rig(tmp_path, commissioned=False)
    before = _inventory(tmp_path)
    monkeypatch.setattr(local_module, 'analyze_local', lambda *a, **k: pytest.fail('uncommissioned engine'))
    with pytest.raises(ValueError, match='COMMISSION'):
        _refresh(rig)
    assert not _originals(rig)
    assert all(row.get('result') is None for row in _projection(rig)['rows'])
    assert _inventory(tmp_path) == before


def test_store_failure_never_promotes_unretained_output_and_releases_operation(tmp_path, monkeypatch):
    rig = _rig(tmp_path)
    retain = rig.research.store.retain
    def fail(value):
        if value.schema == 'SWING_WO12_LOCAL_ANALYSIS_ORIGINAL_V1':
            raise OSError('synthetic retained-original storage failure')
        return retain(value)
    monkeypatch.setattr(rig.research.store, 'retain', fail)
    try:
        _refresh(rig)
    except OSError:
        pass
    assert not _originals(rig)
    assert all(row.get('result') is None for row in _projection(rig)['rows'])
    monkeypatch.setattr(rig.research.store, 'retain', retain)
    # A deliberate separate test invocation proves lock cleanup, not an automatic retry.
    _refresh(rig)
    assert len(_originals(rig)) == 1


def test_projection_is_cached_read_without_math_history_scan_or_write(tmp_path, monkeypatch):
    rig = _rig(tmp_path)
    _refresh(rig)
    rig.owner.prepare()
    before = _inventory(tmp_path)
    def forbidden(*a, **k):
        pytest.fail('Ordinary projection performed work or storage access')
    monkeypatch.setattr(local_module, 'analyze_local', forbidden)
    monkeypatch.setattr(rig.research.store, 'records', forbidden)
    monkeypatch.setattr(rig.research.store, 'retain', forbidden)
    for _ in range(3):
        row = _row(rig)
        assert row['state'] == 'SUCCEEDED' and row['result']
    assert _inventory(tmp_path) == before


def test_concurrent_manual_refresh_never_calculates_or_retains_duplicate(tmp_path, monkeypatch):
    from threading import Event, Thread
    rig = _rig(tmp_path)
    entered, release = Event(), Event()
    analyze = local_module.analyze_local
    calls, errors = [], []
    def slow(*args, **kwargs):
        calls.append(True)
        entered.set()
        assert release.wait(10)
        return analyze(*args, **kwargs)
    monkeypatch.setattr(local_module, 'analyze_local', slow)
    def work():
        try: _refresh(rig)
        except Exception as error: errors.append(error)
    worker = Thread(target=work)
    worker.start()
    try:
        assert entered.wait(10)
        with pytest.raises(ValueError, match='BUSY|RUNNING'):
            _refresh(rig)
    finally:
        release.set(); worker.join(10)
    assert not worker.is_alive() and not errors
    assert len(calls) == 1 and len(_originals(rig)) == 1


@pytest.mark.parametrize('error_class', [ValueError, RuntimeError])
def test_engine_failure_does_not_fabricate_original_output(tmp_path, monkeypatch, error_class):
    rig = _rig(tmp_path)
    _deny_network(monkeypatch)
    def fail(*a, **k): raise error_class('SYNTHETIC_ENGINE_REJECTION')
    monkeypatch.setattr(local_module, 'analyze_local', fail)
    try: _refresh(rig)
    except error_class: pass
    assert rig.owner.status()['state'] == 'UNAVAILABLE'
    assert not _originals(rig)
    assert all(row.get('result') is None for row in _projection(rig)['rows'])


def test_invalid_historical_original_is_unavailable_preserved_without_repair(tmp_path):
    rig = _rig(tmp_path)
    _refresh(rig)
    original, = _originals(rig)
    path = rig.research.store.root / 'records' / original.schema / (original.identity + '.json')
    raw = json.loads(path.read_bytes())
    raw['data']['output_sha256'] = 'f' * 64
    path.write_text(json.dumps(raw))
    before = _inventory(tmp_path)
    restored = SwingLocalAnalysisWorkflow(rig.application, rig.intake, rig.research,
        clock=lambda: rig.state['facts'].observed_at + timedelta(days=1))
    restored.prepare()
    result = restored.projection()
    assert result.get('reason') or any(r.get('reason') for r in result['rows'])
    assert all(row.get('result') is None for row in result['rows'])
    assert _inventory(tmp_path) == before


@pytest.mark.parametrize('phase', ['success','failed','cancelled','reconciliation_failed'])
def test_real_committed_analysis_hook_runs_only_after_successful_reconciliation_under_ownership(nse_checkpoint, monkeypatch, phase):
    from tests.unit.application.test_swing_run_publication import service_for, _completed_successor
    service, queued, snapshot = service_for(nse_checkpoint)
    coordinator, _, bindings, previous = nse_checkpoint
    completed = _fresh_completed_successor(service, snapshot, bindings, previous)
    calls = []
    guard_evidence = _trace_automatic_guard(service, monkeypatch)
    def captured(bundle):
        calls.append((bundle.reference, service.analysis_work_status()['owned_work_count']))
        return {'state':'READY'}
    owner = SimpleNamespace(on_committed=captured, prepare=lambda: None, projection=lambda: {},
        close=lambda: None, intake=SimpleNamespace(prepare_page_state=lambda: True))
    service.register_local_analysis(owner)
    def build(*args, **kwargs):
        if phase == 'failed': raise RuntimeError('synthetic Native failure')
        return completed
    monkeypatch.setattr(opportunities_module, 'build_completed_swing_analysis', build)
    if phase == 'reconciliation_failed':
        service.register_analysis_reconciliation(lambda: (_ for _ in ()).throw(ValueError('synthetic review unavailable')))
    assert service.run_analysis()
    if phase == 'cancelled': service.disconnect_provider()
    queued.pop()()
    assert service.analysis_work_status()['owned_work_count'] == 0
    if phase == 'success':
        assert calls == [(coordinator.current().reference, 1)], {
            'guard_evidence':guard_evidence, 'local_status': service.local_analysis_status(),
            'publication_status': service.publication_status(),
            'completed_probables': [(a.canonical_instrument, a.product_path.value, a.status.value)
                for a in completed.native_discovery_run.assessments if a.status.value == 'PROBABLE'],
        }
        assert coordinator.current().native == completed.native_discovery_run
    else:
        assert not calls
    service.close()


def test_local_failure_does_not_rewrite_committed_native_success(nse_checkpoint, monkeypatch):
    from tests.unit.application.test_swing_run_publication import service_for, _completed_successor
    service, queued, snapshot = service_for(nse_checkpoint)
    coordinator, _, bindings, previous = nse_checkpoint
    completed = _fresh_completed_successor(service, snapshot, bindings, previous)
    monkeypatch.setattr(opportunities_module, 'build_completed_swing_analysis', lambda *a, **k: completed)
    def fail(bundle): raise ValueError('SYNTHETIC_LOCAL_FAILURE')
    service.register_local_analysis(SimpleNamespace(on_committed=fail, prepare=lambda: None,
        projection=lambda: {}, close=lambda: None, intake=SimpleNamespace(prepare_page_state=lambda: True)))
    assert service.run_analysis(); queued.pop()()
    assert coordinator.status()['latest_attempt']['state'] == 'SUCCEEDED'
    assert service.publication_status()['request_result'] == 'SUCCEEDED'
    assert service.analysis_work_status()['owned_work_count'] == 0
    assert coordinator.current().native == completed.native_discovery_run
    service.close()


def test_changed_eligible_evidence_creates_distinct_original_without_rewriting_first(tmp_path):
    rig = _rig(tmp_path)
    _refresh(rig)
    first, = _originals(rig)
    first_path = rig.research.store.root / 'records' / first.schema / (first.identity + '.json')
    original_bytes = first_path.read_bytes()
    requirement, native, facts = _case(directions=('SHORT',) * 4)
    rig.state.update(native=native, facts=facts)
    rig.requirement = requirement
    _refresh(rig)
    originals = _originals(rig)
    assert len(originals) == 2
    assert len({o.data['input_sha256'] for o in originals}) == 2
    assert first_path.read_bytes() == original_bytes
    assert _row(rig)['result']['thesis']['overall']['disposition'] == 'REJECT'


@pytest.mark.parametrize('field', ['input_sha256','output_sha256','input_json','result_json',
    'operation_identity','captured_at','completed_at','method_version'])
def test_self_rehashed_invalid_research_record_never_restores_as_current(tmp_path, field):
    rig = _rig(tmp_path)
    _refresh(rig)
    original, = _originals(rig)
    data = deepcopy(original.data)
    data.pop('contract_identity'); data.pop('contract_version')
    data[field] = {
        'input_sha256':'f' * 64, 'output_sha256':'f' * 64,
        'input_json':'{}', 'result_json':'{}', 'operation_identity':'',
        'captured_at':'2026-08-14T12:00:00',
        'completed_at':'1900-01-01T00:00:00+00:00',
        'method_version':'MADE-UP-METHOD',
    }[field]
    invalid = record('LOCAL_ANALYSIS_ORIGINAL', **data)
    # Malformed retained-history fixture: outer content digest is self-consistent.
    rig = _rig(tmp_path / 'invalid-history-only')
    rig.research.store.retain(invalid)
    before = _inventory(tmp_path)
    restored = SwingLocalAnalysisWorkflow(rig.application, rig.intake, rig.research,
        clock=lambda: rig.state['facts'].observed_at + timedelta(days=1))
    restored.prepare()
    projection = restored.projection()
    assert projection.get('reason') or any(r.get('reason') for r in projection['rows'])
    assert all(r.get('result') is None for r in projection['rows'])
    assert _inventory(tmp_path) == before


def test_existing_wo12_and_commissioning_history_remain_byte_identical(tmp_path):
    from tests.unit.swing.v1.test_prospective_research_wo12 import _origin
    rig = _rig(tmp_path)
    old = rig.research.store.retain(_origin())
    old_path = rig.research.store.root / 'records' / old.schema / (old.identity + '.json')
    before = old_path.read_bytes(), old_path.stat().st_mtime_ns
    commissioning = _inventory(rig.research.store.root / 'current')
    _refresh(rig)
    assert (old_path.read_bytes(), old_path.stat().st_mtime_ns) == before
    assert _inventory(rig.research.store.root / 'current') == commissioning
    assert rig.research.store.origins() == (old,)


def test_existing_store_exclusive_lock_prevents_overlapping_capture(tmp_path):
    rig = _rig(tmp_path)
    with rig.research.store.transaction():
        with pytest.raises(ValueError, match='BUSY'):
            _refresh(rig)
    assert not _originals(rig)


def test_closed_owner_cannot_run_or_promote_another_analysis(tmp_path):
    rig = _rig(tmp_path)
    rig.owner.close()
    with pytest.raises(ValueError):
        _refresh(rig)
    assert not _originals(rig)


def test_noneligible_and_mcx_population_is_not_analyzed(tmp_path, monkeypatch):
    from kronos.swing.v1.native_discovery import NativeDiscoveryStatus
    from tests.unit.swing.v1.test_native_review_mcx_reference import _run_with_probables
    rig = _rig(tmp_path)
    monkeypatch.setattr(local_module, 'analyze_local', lambda *a, **k: pytest.fail('non-NSE or excluded analysis'))
    native = replace(rig.state['native'], assessments=tuple(
        replace(a, status=NativeDiscoveryStatus.NO_CURRENT_OPPORTUNITY)
        for a in rig.state['native'].assessments))
    rig.state['native'] = native
    with pytest.raises(ValueError, match='REQUIREMENT_UNAVAILABLE'):
        rig.owner.refresh(run_identity=native.run_identity, publication_sha256=rig.state['manifest'])
    assert not _originals(rig)
    facts, native = _run_with_probables('CRUDEOIL', retain_mcx_lineage=True)
    rig.state.update(native=native, facts=facts)
    with pytest.raises(ValueError, match='REQUIREMENT_UNAVAILABLE'):
        rig.owner.refresh(run_identity=native.run_identity, publication_sha256=rig.state['manifest'])
    assert not _originals(rig)


def test_isolated_worker_install_invokes_local_once_after_commit_under_analysis_ticket(nse_checkpoint, monkeypatch):
    from kronos.application.swing_analysis_process import SwingAnalysisProcessOwner
    from kronos.market.calendar import MarketCalendarPublisher
    from kronos.swing.run_provenance import SwingAnalysisRunProvenance
    from tests.unit.application.test_swing_run_publication import service_for, _completed_successor
    service, queued, snapshot = service_for(nse_checkpoint)
    coordinator, _, bindings, previous = nse_checkpoint
    completed = _fresh_completed_successor(service, snapshot, bindings, previous)
    process = SwingAnalysisProcessOwner()
    monkeypatch.setattr(service, '_SwingOpportunitiesApplication__analysis_process_owner', process)
    monkeypatch.setattr(service, '_SwingOpportunitiesApplication__market_calendar_publisher', MarketCalendarPublisher())
    calls, events = [], []
    guard_evidence = _trace_automatic_guard(service, monkeypatch)
    def capture(bundle):
        events.append('local')
        calls.append((bundle.reference, service.analysis_work_status()['owned_work_count']))
        return {'state':'READY'}
    service.register_local_analysis(SimpleNamespace(on_committed=capture,
        prepare=lambda: None, projection=lambda: {}, close=lambda: None,
        intake=SimpleNamespace(prepare_page_state=lambda: events.append('page') or True)))
    def execute(capability, publication, calendar, token, **kwargs):
        assert kwargs['is_current']()
        ref = publication.prepare(token, mtf=completed.mtf_fact_snapshot,
            native=completed.native_discovery_run, relative=completed.relative_context_run,
            provenance=SwingAnalysisRunProvenance(snapshot.run_identity, snapshot.observed_at,
                snapshot.observed_at, completed.evidence.market_data_snapshot_identity, snapshot.observed_at),
            continuity=completed.continuity_contribution)
        assert kwargs['authorize_commit'](ref, snapshot.observed_at)
        with kwargs['commit_scope']():
            committed = publication.publish(token, ref, snapshot.observed_at)
            events.append('commit')
            assert kwargs['install_result'](SimpleNamespace(completed=completed, committed=committed))
    monkeypatch.setattr(process, 'execute', execute)
    assert service.run_analysis(); queued.pop()()
    assert events == ['commit','local','page'], {
        'guard_evidence':guard_evidence,'local_status':service.local_analysis_status(),'publication_status':service.publication_status(),
        'completed_probables':[(a.canonical_instrument,a.product_path.value,a.status.value)
            for a in completed.native_discovery_run.assessments if a.status.value == 'PROBABLE'],
    }
    assert calls == [(coordinator.current().reference, 1)], {
            'guard_evidence':guard_evidence, 'local_status': service.local_analysis_status(),
            'publication_status': service.publication_status(),
            'completed_probables': [(a.canonical_instrument, a.product_path.value, a.status.value)
                for a in completed.native_discovery_run.assessments if a.status.value == 'PROBABLE'],
        }
    assert service.analysis_work_status()['owned_work_count'] == 0
    assert service.publication_status()['request_result'] == 'SUCCEEDED'
    service.close()


def test_automatic_mcxs_only_commit_does_not_invoke_local_nse_owner(checkpoint, monkeypatch):
    from tests.unit.application.test_swing_run_publication import service_for, _completed_successor
    service, queued, snapshot = service_for(checkpoint)
    coordinator, _, bindings, previous = checkpoint
    completed = _completed_successor(service, snapshot, bindings, previous)
    monkeypatch.setattr(opportunities_module, 'build_completed_swing_analysis', lambda *a, **k: completed)
    service.register_local_analysis(SimpleNamespace(
        on_committed=lambda bundle: pytest.fail('MCX-only commit invoked local NSE engine'),
        prepare=lambda: None, projection=lambda: {}, close=lambda: None))
    assert service.run_analysis(); queued.pop()()
    assert service.publication_status()['request_result'] == 'SUCCEEDED'
    assert coordinator.current().native == completed.native_discovery_run
    service.close()


def test_automatic_real_owner_and_restart_use_no_network_and_preserve_input_output(tmp_path, monkeypatch):
    rig = _rig(tmp_path)
    forbidden = _deny_network(monkeypatch)
    monkeypatch.setattr(rig.application, 'run_analysis', forbidden)
    monkeypatch.setattr(rig.application, 'authenticated_read_only_capability', forbidden)
    bundle = SimpleNamespace(native=rig.state['native'], reference={'sha256':rig.state['manifest']})
    assert rig.owner.on_committed(bundle)['state'] == 'READY'
    original, = _originals(rig)
    assert original.data['trigger'] == 'AUTOMATIC'
    before = _inventory(tmp_path)
    restored = SwingLocalAnalysisWorkflow(rig.application, rig.intake, rig.research,
        clock=lambda: rig.state['facts'].observed_at + timedelta(days=1))
    restored.prepare()
    with rig.intake.response() as response:
        current = restored.projection(_response=response)
    assert current['rows'][0]['original_identity'] == original.identity
    assert current['rows'][0]['result'] is not None
    assert _inventory(tmp_path) == before


def test_self_rehashed_future_capture_original_is_unavailable_at_restore_boundary(tmp_path):
    rig = _rig(tmp_path / 'valid')
    _refresh(rig)
    original, = _originals(rig)
    data = deepcopy(original.data)
    data.pop('contract_identity'); data.pop('contract_version')
    future = rig.state['facts'].observed_at + timedelta(days=30)
    data.update(captured_at=future.isoformat(), completed_at=future.isoformat())
    invalid = record('LOCAL_ANALYSIS_ORIGINAL', **data)
    target = _rig(tmp_path / 'future-only')
    target.research.store.retain(invalid)
    before = _inventory(tmp_path)
    restored = SwingLocalAnalysisWorkflow(target.application, target.intake, target.research,
        clock=lambda: target.state['facts'].observed_at + timedelta(minutes=1))
    prepared = restored.prepare()
    assert prepared['state'] == 'UNAVAILABLE'
    assert prepared['reason'] == 'NSE_LOCAL_CLOCK_INVALID'
    assert not prepared['rows']
    with target.intake.response() as response:
        projected = restored.projection(_response=response)
        assert projected['state'] == 'UNAVAILABLE'
        assert projected['reason'] == 'NSE_LOCAL_CLOCK_INVALID'
        assert not projected['rows']
    assert _inventory(tmp_path) == before


def test_clock_rollback_after_preparation_withholds_original_without_rewrite(tmp_path):
    rig = _rig(tmp_path)
    _refresh(rig)
    original, = _originals(rig)
    assert _row(rig)['state'] == 'SUCCEEDED'
    before = _inventory(tmp_path)
    rig.owner.clock = lambda: rig.state['facts'].observed_at
    projection = _projection(rig)
    assert projection['state'] == 'UNAVAILABLE'
    assert projection['reason'] == 'NSE_LOCAL_CLOCK_INVALID'
    assert not projection['rows']
    assert _originals(rig) == (original,)
    assert _inventory(tmp_path) == before


def test_unchanged_adopted_four_hour_bar_remains_manual_review_and_does_not_trigger_local(nse_checkpoint, monkeypatch):
    from tests.unit.application.test_swing_run_publication import service_for, _completed_successor
    from kronos.swing.v1.native_discovery import NativeDiscoveryStatus
    service, queued, snapshot = service_for(nse_checkpoint)
    coordinator, _, bindings, previous = nse_checkpoint
    completed = _completed_successor(service, snapshot, bindings, previous)
    native = next(a for a in completed.native_discovery_run.assessments if a.canonical_instrument == 'RELIANCE')
    assert native.status is not NativeDiscoveryStatus.PROBABLE
    assert 'SWING_CONTINUITY_REUSE_REQUIRES_MANUAL_REVIEW' in native.reason_codes
    monkeypatch.setattr(opportunities_module, 'build_completed_swing_analysis', lambda *a, **k: completed)
    service.register_local_analysis(SimpleNamespace(
        on_committed=lambda bundle: pytest.fail('uncertain reused 4H evidence invoked local analysis'),
        prepare=lambda: None, projection=lambda: {}, close=lambda: None))
    assert service.run_analysis(); queued.pop()()
    assert service.publication_status()['request_result'] == 'SUCCEEDED'
    assert service.analysis_work_status()['owned_work_count'] == 0
    service.close()


def test_unchanged_manual_and_automatic_capture_do_not_recalculate_via_result_decoder(tmp_path, monkeypatch):
    from kronos.swing.v1 import nse_local_analysis as engine
    rig = _rig(tmp_path)
    _refresh(rig)
    original, = _originals(rig)
    before = _inventory(tmp_path)
    engine_calls = []
    analyze = engine.analyze_local
    def observed(*args, **kwargs):
        engine_calls.append(True)
        return analyze(*args, **kwargs)
    monkeypatch.setattr(engine, 'analyze_local', observed)
    monkeypatch.setattr(local_module, 'analyze_local', observed)
    _refresh(rig)
    _refresh(rig, trigger='AUTOMATIC')
    assert engine_calls == [], 'Already validated unchanged original was recalculated'
    assert _originals(rig) == (original,)
    assert _inventory(tmp_path) == before
    assert _row(rig)['result'] is not None


@pytest.mark.parametrize('field', ['output_sha256', 'result_json'])
def test_warm_validated_cache_rejects_changed_self_rehashed_original(tmp_path, monkeypatch, field):
    rig = _rig(tmp_path)
    _refresh(rig)
    original, = _originals(rig)
    original_path = rig.research.store.root / 'records' / original.schema / (original.identity + '.json')
    original_bytes = original_path.read_bytes()
    data = deepcopy(original.data)
    data.pop('contract_identity'); data.pop('contract_version')
    data[field] = 'f' * 64 if field == 'output_sha256' else '{}'
    invalid = record('LOCAL_ANALYSIS_ORIGINAL', **data)
    rig.research.store.retain(invalid)
    records = rig.research.store.records
    # Isolate the changed self-consistent record from duplicate-input detection.
    # The original is preserved on disk; authoritative history now exposes this
    # different body, which must not inherit the warmed validation cache.
    monkeypatch.setattr(rig.research.store, 'records', lambda kind:
        (invalid,) if kind == 'LOCAL_ANALYSIS_ORIGINAL' else records(kind))
    before = _inventory(tmp_path)
    expected_reason = 'NSE_LOCAL_RECORD_INVALID' if field == 'output_sha256' else 'NSE_LOCAL_INPUT_INVALID'
    with pytest.raises(ValueError, match='^' + expected_reason + '$'):
        _refresh(rig)
    assert rig.owner.status()['state'] == 'UNAVAILABLE'
    assert not _projection(rig)['rows']
    assert original_path.read_bytes() == original_bytes
    assert _inventory(tmp_path) == before


def test_known_immutable_history_disappearance_stops_without_recalculation_or_repair(tmp_path, monkeypatch):
    rig = _rig(tmp_path)
    _refresh(rig)
    original, = _originals(rig)
    before = _inventory(tmp_path)
    records = rig.research.store.records
    monkeypatch.setattr(rig.research.store, 'records', lambda kind:
        () if kind in ('LOCAL_ANALYSIS_ORIGINAL','LOCAL_ANALYSIS_DISPOSITION') else records(kind))
    def forbidden(*args, **kwargs):
        pytest.fail('Missing known immutable history must not be recalculated or repaired')
    monkeypatch.setattr(local_module, 'analyze_local', forbidden)
    monkeypatch.setattr(rig.research.store, 'retain', forbidden)
    with pytest.raises(ValueError, match='HISTORY|ORIGINAL'):
        _refresh(rig)
    assert rig.owner.status()['state'] == 'UNAVAILABLE'
    assert not _projection(rig)['rows']
    assert _inventory(tmp_path) == before
    assert original in records('LOCAL_ANALYSIS_ORIGINAL')
