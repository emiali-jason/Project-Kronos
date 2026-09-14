from dataclasses import replace
from types import SimpleNamespace

import pytest

from kronos.application import swing_opportunities as app
from kronos.swing.v1 import opportunity_continuity as c
from kronos.swing.v1.relative_context import build_relative_context_run
from kronos.swing.universe import SWING_PHASE1_UNIVERSE
from tests.unit.swing.test_run_publication import checkpoint, scenario, later
from tests.unit.application.test_swing_opportunities import _Provider


def service_for(checkpoint):
    co, snapshot, bindings, p = checkpoint
    next_snapshot = later(snapshot)
    queued = []
    service = app.SwingOpportunitiesApplication(_Provider, run_publication=co,
        clock=lambda:next_snapshot.observed_at,
        swing_run_identity_factory=lambda:next_snapshot.run_identity,
        background_runner=lambda callback,name:queued.append(callback))
    assert service.connect_provider()
    queued.pop(0)()
    return service,queued,next_snapshot


def test_02_duplicate_no_generation_or_dispatch_and_provider_distinct(checkpoint):
    service, queued, snapshot = service_for(checkpoint)
    co = checkpoint[0]
    assert service.run_analysis()
    control = co.status()
    assert not service.run_analysis()
    assert co.status() == control and len(queued) == 1
    assert service.publication_status()['request_result'] == 'DUPLICATE_RUNNING'
    unconnected = app.SwingOpportunitiesApplication(_Provider)
    assert not unconnected.run_analysis()
    assert unconnected.publication_status()['request_result'] == 'PROVIDER_UNAVAILABLE'


def test_03_admission_failure_does_not_dispatch(checkpoint):
    service, queued, snapshot = service_for(checkpoint)
    co = checkpoint[0]
    before = co.status()
    def fail(at):
        if at == 'before_control_replace': raise OSError('fault')
    co.fault = fail
    assert not service.run_analysis() and not queued and co.status() == before


def test_01_15_committed_predecessor_and_reconciliation_failure(checkpoint, monkeypatch):
    service, queued, snapshot = service_for(checkpoint)
    co, old, bindings, p = checkpoint
    prepared = c.prepare_continuity(snapshot,bindings,adopted_predecessor=p)
    captured = []
    def build(capability, **kwargs):
        captured.append(kwargs)
        assert kwargs['committed_predecessor'].reference == p.reference
        assert kwargs['prepare_publication'] is True
        return SimpleNamespace(
            workspace=replace(service.snapshot(), analysis_state=app.AnalysisState.READY,
                swing_analysis_run_identity=snapshot.run_identity,
                run_created_at=snapshot.observed_at, completed_at=snapshot.observed_at),
            evidence=SimpleNamespace(observation_boundary=snapshot.observed_at,
                market_data_snapshot_identity='SWING-MARKET-DATA-SNAPSHOT-'+'a'*64),
            mtf_fact_snapshot=snapshot,native_discovery_run=prepared.native_run,
            relative_context_run=build_relative_context_run(snapshot,SWING_PHASE1_UNIVERSE),
            continuity_contribution=prepared)
    monkeypatch.setattr(app,'build_completed_swing_analysis',build)
    effects=[]
    def reconcile():
        effects.append(co.current().native.run_identity)
        raise ValueError('downstream unavailable')
    service.register_analysis_reconciliation(reconcile)
    assert service.run_analysis()
    queued.pop()()
    assert len(captured)==1 and effects==[snapshot.run_identity]
    assert co.status()['latest_attempt']['state']=='SUCCEEDED'
    assert service.native_discovery_run()==prepared.native_run
    assert service.publication_status()['reconciliation_unavailable']
    service.register_analysis_reconciliation(lambda:effects.append('retry'))
    service.reconcile_committed_analysis()
    assert not service.publication_status()['reconciliation_unavailable']
    assert co.current().native==prepared.native_run


def test_10_no_latest_fallback_in_builder():
    import inspect
    source=inspect.getsource(app.build_completed_swing_analysis)
    assert '.latest()' not in source
    assert 'committed_predecessor.mtf' in source and 'committed_predecessor.native' in source


def test_10_foreign_commit_cannot_reconcile_or_refresh_old_native(checkpoint):
    from tests.unit.swing.test_run_publication import prepared
    service, queued, snapshot = service_for(checkpoint)
    co, old, bindings, prior = checkpoint
    token, values = prepared(co, old, bindings, 3)
    co.publish(token, co.prepare(token, **values), values['mtf'].observed_at)
    calls = []
    service.register_analysis_reconciliation(lambda: calls.append(True))
    service.reconcile_committed_analysis()
    assert not calls
    assert service.native_discovery_run() is None
    assert service.mtf_fact_snapshot() is None
    assert service.relative_context_run() is None
    assert service.publication_status()['request_result'] == 'PUBLICATION_UNAVAILABLE'
    # An explicit canonical restoration uses the control authority, not old memory.
    restored = app.SwingOpportunitiesApplication(_Provider, run_publication=co,
        clock=lambda: snapshot.observed_at)
    assert restored.native_discovery_run() == values['native']


def test_01_two_explicit_factual_builds_each_retrieve_same_98():
    from tests.unit.application.test_swing_mtf_facts import _build
    from kronos.provider.contracts.market_data import HistoricalInterval
    first, first_requests = _build()
    second, second_requests = _build()
    expected = {i.canonical_identity for i in SWING_PHASE1_UNIVERSE}
    for snapshot, requests in ((first, first_requests), (second, second_requests)):
        hours = [r for r in requests if r.interval is HistoricalInterval.SIXTY_MINUTE]
        assert len(hours) == 98
        assert {r.instrument.trading_symbol for r in hours} == expected
        assert {i.canonical_instrument for i in snapshot.instruments} == expected
    assert first_requests is not second_requests
    assert len(first_requests) == len(second_requests)
