"""Request-local read reuse with real disposable producers and owner locks.

Fault injection is confined to these temporary stores. Performance conclusions
come from the separate unmocked 98-member route comparison, not these tests.
"""
from datetime import datetime, timedelta
from dataclasses import replace
from hashlib import sha256
from threading import Event, Thread
from types import SimpleNamespace

import pytest

from kronos.application.intraday_evidence_currentness import IntradayPublicationBoundary
from kronos.application import intraday_review_ordered_batch
from kronos.application.intraday_native_selection import NativePullbackPublication
from kronos.application.intraday_wo08 import Wo08Publication
from kronos.browser.dashboard import project_intraday_dashboard
from kronos.browser.intraday_futures_control import domain008_session
from kronos.instrument.active_derivative_persistence import ActiveDerivativeBindingStore
from kronos.intraday.native_structural_selection import NativeStructuralStore
from kronos.intraday.probables_v2 import (
    ProbablesUnavailableMemberV2, ProbableReasonV2, evaluate_probables_v2_run,
)
from kronos.intraday.probables_v2_persistence import ProbablesV2Store
from kronos.intraday.review_v2_persistence import IntradayReviewV2Store
from kronos.intraday.review_mcx_paired_persistence import IntradayMcxPairedReviewStore
from kronos.intraday.visual_reconciliation_v2_persistence import VisualReconciliationStore
from kronos.intraday.wo08_assessment_store import Wo08AssessmentStore
from kronos.intraday.wo09_persistence import Wo09Store
from kronos.intraday.wo09_readiness import CurrentnessState
from kronos.intraday.wo10_futures_store import FuturesStore
from kronos.market.calendar import MarketCalendarPublisher
from tests.unit.intraday.test_wo08_experimental import experimental_fixture, START
from tests.unit.intraday.test_wo09_experimental import origin_for, publish
from tests.unit.browser.test_intraday_iwo_ux import mcx_options

FOUR = dict(five_rows=[(108,102,106)]*25+[(115,110,113),(117,114,116)])


def inventory(root):
    return {str(p.relative_to(root)): sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


@pytest.fixture
def sources(tmp_path):
    calendar = MarketCalendarPublisher()
    names = list(calendar.subject_session_applicability_publications[0].periods[-1].applicable_domain_subject_ids)[:97]
    at = START + timedelta(minutes=135)
    now = [at + timedelta(seconds=1)]
    bindings = ActiveDerivativeBindingStore(tmp_path/'bindings')
    gold = mcx_options()
    bindings.retain(gold['binding'])
    inputs = [experimental_fixture(subject=n, member='MEMBER-'+str(i),
        session=domain008_session(calendar, n, at).schedule.session_id,
        **(FOUR if i == 0 else {})) for i, n in enumerate(names[:2])]
    inputs.append(experimental_fixture(member='MEMBER-MCX', **gold))
    mappings = tuple(v[2] for v in inputs)
    facts = tuple(v[1] for v in inputs)
    missing = tuple(ProbablesUnavailableMemberV2('UNAVAILABLE-'+str(i), n,
        domain008_session(calendar, n, at).schedule.session_id, at,
        ProbableReasonV2.MANDATORY_EVIDENCE_UNAVAILABLE, 'DISCOVERY', ('SYNTHETIC',))
        for i, n in enumerate(names[2:]))
    args = dict(source_discovery_run_identity='DISCOVERY', universe_identity='SYNTHETIC',
        universe_version='1', reconciliation_identity='SYNTHETIC', reconciliation_version='1',
        market_session_identity='SYNTHETIC-MULTI-SESSION', analysis_boundary=at,
        member_evidence=mappings, unavailable_members=missing, provenance=('SYNTHETIC',))
    run = evaluate_probables_v2_run(**args)
    native = NativePullbackPublication(NativeStructuralStore(tmp_path/'native'),
        clock=lambda: at, commissioned_at=at, binding_store=bindings)
    native.publish(run, mappings, facts=facts, bundles=(gold['bundle'],), newly_published=True)
    machine = Wo08AssessmentStore(tmp_path/'machine')
    assessments = Wo08Publication(machine).publish_run(run=run, mapping=mappings,
        native_publication=native, published_at=at)
    probables = ProbablesV2Store(tmp_path/'probables')
    probables.retain_complete(run=run, mappings=mappings)
    wo09 = Wo09Store(tmp_path/'wo09')
    for a in assessments:
        publish(wo09, a, origin_for(a), now[0])
    boundary = IntradayPublicationBoundary(review=IntradayReviewV2Store(tmp_path/'review'),
        probables=probables, paired=IntradayMcxPairedReviewStore(tmp_path/'paired'), bindings=bindings,
        reconciliation=VisualReconciliationStore(tmp_path/'reconciliation'),
        ordered_batch=intraday_review_ordered_batch, wo09=wo09, futures=FuturesStore(tmp_path/'futures'),
        calendar=calendar, clock=lambda: now[0], wo08=machine, native=native.store)
    return SimpleNamespace(root=tmp_path, owner=boundary, store=wo09, now=now, at=at,
        run=run, run_args=args, assessments=assessments, gold=gold)


def test_real_full_population_output_and_bounded_source_calls(sources, monkeypatch):
    f = sources
    calls = []
    original = f.owner.probables.load_current
    def capture():
        calls.append(True)
        return original()
    monkeypatch.setattr(f.owner.probables, 'load_current', capture)
    before = inventory(f.root)
    result = project_intraday_dashboard(f.store, f.owner)
    assert result.state == 'CURRENT_SESSION_VERIFIED'
    assert len(result.current_readiness) == 98
    assert (result.ready, result.now) == (1, 2)
    assert {o['direction'] for o in result.opportunities} == {'LONG'}
    assert next(o['contract'] for o in result.opportunities if o['subject'].startswith('MCX-')) == f.gold['binding'].active_binding.derivative_contract_id
    assert len(calls) == 3  # initial, complete-run loader, fresh final comparison
    assert inventory(f.root) == before
    assert getattr(f.store, 'notification_listener', None) is None


@pytest.mark.parametrize('family', ['probables', 'wo08', 'wo09'])
def test_changes_during_callback_are_not_published(sources, family):
    f = sources
    changed = []
    def mutate(_):
        if changed:
            return None
        changed.append(True)
        if family == 'probables':
            args = {**f.run_args, 'provenance': ('SYNTHETIC-SUCCESSOR',)}
            successor = evaluate_probables_v2_run(**args)
            f.owner.probables.retain_complete(run=successor, mappings=args['member_evidence'])
        elif family == 'wo08':
            from kronos.intraday.wo08_assessment import canonical, digest
            pointer = f.owner.wo08.current_pointer()
            pointer['generation'] += 1
            pointer['integrity_sha256'] = digest({k:v for k,v in pointer.items() if k != 'integrity_sha256'})
            # Unexpected on-disk replacement, deliberately outside publication.
            f.owner.wo08._atomic_pointer(canonical(pointer))
        else:
            r = f.store.load_readiness(f.store.restore_current()[0][0].readiness_identity)
            f.store.mark_currentness(r.canonical_subject_identity, CurrentnessState.REASSESSMENT_DUE,
                updated_at=f.now[0]+timedelta(seconds=1), expected=f.store.expectation(r.canonical_subject_identity))
        return None
    result = project_intraday_dashboard(f.store, f.owner, monitoring_projection=mutate)
    assert changed
    assert result.now is result.ready is None
    assert result.current_readiness == result.opportunities == ()


@pytest.mark.parametrize('target', ['run', 'result', 'assessment', 'native', 'probable_pointer', 'wo08_pointer', 'wo09_pointer', 'binding'])
@pytest.mark.parametrize('damage', ['missing', 'corrupt'])
def test_real_corrupt_or_missing_evidence_fails_closed(sources, target, damage):
    f = sources
    a = next(a for a in f.assessments if a.data.get('native_decision_identity'))
    paths = {
        'run': f.owner.probables._path('runs', f.run.run_identity),
        'result': f.owner.probables._path('results', a.data['probable_result_identity']),
        'assessment': f.owner.wo08._record_path(a.identity),
        'native': f.owner.native.root/'records'/(a.data['native_decision_identity']+'.json'),
        'probable_pointer': f.owner.probables.root/'refresh-v2/CURRENT-PROBABLES-V2.json',
        'wo08_pointer': f.owner.wo08.root/'current.json',
        'wo09_pointer': next(f.store.current.glob('*.json')),
        'binding': f.owner.bindings.path_for(f.gold['binding'].binding_identity),
    }
    if damage == 'missing':
        paths[target].unlink()
    else:
        paths[target].write_bytes(b'{')
    if target == 'binding':
        from kronos.instrument.active_derivative import ActiveDerivativeSelectionError
        reason = ('ACTIVE_DERIVATIVE_BINDING_UNAVAILABLE' if damage == 'missing'
                  else 'ACTIVE_DERIVATIVE_BINDING_INTEGRITY_INVALID')
        with pytest.raises(ActiveDerivativeSelectionError, match='^'+reason+'$'):
            project_intraday_dashboard(f.store, f.owner)
        return
    result = project_intraday_dashboard(f.store, f.owner)
    # A missing WO09 pointer lawfully removes that subject from the retained
    # population. No source record or positivity is invented for the absent one.
    if target == 'wo09_pointer' and damage == 'missing':
        assert len(result.current_readiness) == 97
    else:
        assert result.now is result.ready is None
        assert result.current_readiness == ()


@pytest.mark.parametrize('kind', ['native', 'contract', 'result'])
def test_exact_joins_cannot_borrow_other_valid_records(sources, monkeypatch, kind):
    f = sources
    mcx = next(a for a in f.assessments if a.data['market_family'] == 'MCX')
    if kind == 'native':
        original = f.owner.native.bound_identity
        monkeypatch.setattr(f.owner.native, 'bound_identity', lambda identity:
            'OTHER-SELECTION' if identity == mcx.data['semantic_evidence_identity'] else original(identity))
    elif kind == 'contract':
        original = f.owner.bindings.load_current
        monkeypatch.setattr(f.owner.bindings, 'load_current', lambda **kwargs:
            SimpleNamespace(binding_identity=f.gold['binding'].binding_identity,
                active_binding=SimpleNamespace(derivative_contract_id='WRONG-CONTRACT'))
            if kwargs['canonical_subject_id'] == mcx.data['subject'] else original(**kwargs))
    else:
        original = f.owner.probables.load_result
        wrong = next(r for r in f.run.results if r.source_mapping_identity is None)
        monkeypatch.setattr(f.owner.probables, 'load_result', lambda identity:
            wrong if identity == mcx.data['probable_result_identity'] else original(identity))
    result = project_intraday_dashboard(f.store, f.owner)
    if kind == 'result':
        assert result.now is result.ready is None
    else:
        assert result.state == 'CURRENT_SESSION_VERIFIED'
        assert result.now == result.ready == 1
        assert not any(o['subject'].startswith('MCX-') for o in result.opportunities)


@pytest.mark.parametrize('error', [ValueError('INJECTED'), OSError('INJECTED'), RuntimeError('INJECTED')])
def test_exception_releases_owner_guards(sources, error):
    f = sources
    def fail(_):
        raise error
    if isinstance(error, RuntimeError):
        with pytest.raises(RuntimeError, match='INJECTED'):
            project_intraday_dashboard(f.store, f.owner, monitoring_projection=fail)
    else:
        assert project_intraday_dashboard(f.store, f.owner, monitoring_projection=fail).now is None
    acquired = []
    def another_reader():
        with f.owner._sources(f.store.restore_current()[0][1]):
            acquired.append(True)
    t = Thread(target=another_reader)
    t.start(); t.join(5)
    assert not t.is_alive() and acquired == [True]


@pytest.mark.parametrize('family', ['probables', 'wo08', 'binding'])
def test_independent_canonical_writer_waits_for_existing_request_guards(sources, family):
    f = sources
    blocked, done, observed = Event(), Event(), []
    failures = []
    if family == 'probables':
        writer = ProbablesV2Store(f.owner.probables.root)
        operation = lambda: writer.save_current(writer.load_current())
    elif family == 'wo08':
        writer = Wo08AssessmentStore(f.owner.wo08.root.parent)
        operation = lambda: writer.publish(f.run, f.assessments)
    else:
        writer = ActiveDerivativeBindingStore(f.root/'bindings')
        operation = lambda: writer.retain(f.gold['binding'])
    real_lock = writer._lock
    class ObservedLock:
        def __enter__(self):
            if not real_lock.acquire(blocking=False):
                blocked.set()
                real_lock.acquire()
            return self
        def __exit__(self, *args):
            real_lock.release()
    writer._lock = ObservedLock()
    def write():
        try:
            operation()
        except Exception as e:
            failures.append(e)
        finally:
            done.set()
    thread = Thread(target=write)
    def observe(_):
        if not observed:
            observed.append(True)
            thread.start()
            assert blocked.wait(5), 'writer did not encounter held canonical lock'
            assert not done.is_set()
        return None
    try:
        result = project_intraday_dashboard(f.store, f.owner, monitoring_projection=observe)
    finally:
        if thread.ident is not None:
            thread.join(5)
    assert (result.now, result.ready) == (2, 1)
    assert done.is_set() and not thread.is_alive() and not failures


def test_source_reuse_ends_with_request_and_does_not_mask_later_corruption(sources):
    f = sources
    assert project_intraday_dashboard(f.store, f.owner).now == 2
    f.owner.probables._path('runs', f.run.run_identity).write_bytes(b'{}')
    assert project_intraday_dashboard(f.store, f.owner).now is None


def test_sessions_are_subject_specific_and_calendar_unavailability_stays_unavailable(sources):
    f = sources
    f.now[0] = START + timedelta(hours=8)
    evening = project_intraday_dashboard(f.store, f.owner)
    assert evening.now == 1 and evening.ready == 0
    assert all(o['subject'].startswith('MCX-') for o in evening.opportunities)
    f.owner.calendar = SimpleNamespace(instrument_session_profile=lambda *a, **k:
        (_ for _ in ()).throw(ValueError('CALENDAR_UNAVAILABLE')))
    assert project_intraday_dashboard(f.store, f.owner).now is None
