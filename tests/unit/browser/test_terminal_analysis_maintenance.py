"""Real analysis ownership and Browser maintenance, isolated other domains."""
from contextlib import nullcontext
from datetime import UTC, datetime
from threading import Event, Thread
from types import MethodType, SimpleNamespace
import os

import pytest

from kronos.application.swing_analysis_process import (
    SwingAnalysisProcessOwner, SwingAnalysisProcessError,
)
from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.browser.server import KronosBrowserServer
from kronos.market.calendar import MarketCalendarPublisher
from kronos.common.maintenance import verify_drain_handoff, consume_drain_handoff
from kronos.common.connection_governance import ConnectionGovernanceError
from kronos.application import swing_analysis_process as process_module
from tests.unit.browser.test_browser_server import _mcx_drain_server
from tests.unit.application.test_swing_opportunities import _Provider
from tests.unit.swing.test_run_publication import make_checkpoint, scenario


def _failed_owner(tmp_path, scenario):
    snapshot, bindings = scenario
    publication, _, _, _ = make_checkpoint(tmp_path/'publication', snapshot, bindings)
    now = datetime.now(UTC)
    token, _ = publication.admit('SWING-RUN-'+'7'*32, now)
    owner = SwingAnalysisProcessOwner(timeout_seconds=12)
    capability = SimpleNamespace(instrument_records=lambda _exchange: (
        _ for _ in ()).throw(ValueError('ISOLATED_PROVIDER_FAILURE')))
    with pytest.raises(SwingAnalysisProcessError):
        owner.execute(capability, publication, MarketCalendarPublisher(), token,
            generation=7, analysis_run_identity='ANALYSIS-000007',
            swing_run_identity='SWING-RUN-'+'7'*32,
            run_created_at=now, now=now, pace=lambda: None,
            progress_observer=lambda _value: None, completion_clock=lambda: now,
            authorize_commit=lambda *_args: False, is_current=lambda: True,
            commit_scope=nullcontext, install_result=lambda _result: False)
    owner.release(7)
    assert publication.fail(token, now)
    application = SwingOpportunitiesApplication(_Provider, run_publication=publication,
        analysis_process_owner=owner)
    assert application.analysis_work_status()['state'] == 'IDLE'
    assert owner.status()['state'] == 'FAILED'
    assert owner.status()['owned_workers'] == 0
    return owner, application, publication


def _server(tmp_path, application):
    server = _mcx_drain_server(tmp_path/'domains')
    server.application = application
    server.native_review = SimpleNamespace(snapshot=lambda: SimpleNamespace(analysis_outcomes=()))
    server._domain_closed = False
    phase = {'lifecycle_state': 'IDLE', 'owned_workers': 0, 'pass_active': False}
    lifecycle = {'state':'IDLE','continuity':'COMPLETE','owned_workers':0,'queued_items':0}
    server.intraday_lifecycle.work_status = lambda: dict(lifecycle)
    server.intraday_wo17_monitoring.work_status = lambda: dict(lifecycle)
    server.housekeeping = SimpleNamespace(status_document=lambda: dict(phase))
    events = []
    server._quiesce_monitoring_producers = application.close
    def cleanup(**_kwargs):
        server._domain_closed = True
        phase['lifecycle_state'] = 'STOPPED'
        lifecycle['state'] = 'TERMINATED'
        events.append('cleanup')
    server._close_domain_owners = cleanup
    server.shutdown = lambda: events.append('shutdown')
    for name in ('maintenance_replacement_idle', '_complete_governed_shutdown'):
        setattr(server, name, MethodType(getattr(KronosBrowserServer, name), server))
    return server, events


def test_terminal_failed_real_worker_can_reach_maintenance(tmp_path, scenario):
    owner, application, publication = _failed_owner(tmp_path, scenario)
    server, _ = _server(tmp_path, application)
    before = owner.status()
    files = {str(p): p.read_bytes() for p in publication.root.rglob('*') if p.is_file()}
    assert server.maintenance_replacement_idle(allow_drainable=True)
    assert owner.status() == before
    assert {str(p): p.read_bytes() for p in publication.root.rglob('*') if p.is_file()} == files


def test_real_claim_drain_signed_handoff_preserves_failure(tmp_path, scenario):
    owner, application, publication = _failed_owner(tmp_path, scenario)
    server, events = _server(tmp_path, application)
    before = owner.status()
    history = {str(p): p.read_bytes() for p in publication.root.rglob('*') if p.is_file()}
    generation = 'd'*64
    assert server.maintenance_replacement_idle(allow_drainable=True)
    assert server.maintenance_admission.claim(generation)
    assert server.maintenance_admission.admit('SWING_ANALYSIS') is None
    server._complete_governed_shutdown(generation, 'b'*64, 5)
    assert events == ['cleanup', 'shutdown']
    assert server.maintenance_admission.snapshot()['state'] == 'STOPPING'
    root = server.restart_control.path.parent/'maintenance'
    now = datetime.now(UTC)
    signed = verify_drain_handoff(root, generation=generation, parent_pid=os.getpid(),
        proof='a'*64, loaded_revision='c'*40, now=now)
    assert all(v == 0 for k, v in signed['drain'].items() if k != 'notification_checkpoint')
    assert signed['drain']['notification_checkpoint']['state'] == 'EMPTY'
    context = consume_drain_handoff(root, {
        'KRONOS_MAINTENANCE_GENERATION':generation,
        'KRONOS_MAINTENANCE_PARENT':str(os.getpid()),
        'KRONOS_MAINTENANCE_PROOF':'a'*64}, runtime_identity='e'*64,
        loaded_revision='c'*40, now=now, process_id=os.getpid()+1,
        predecessor_gone=lambda _pid: True, port_free=lambda: True)
    assert context.notification_checkpoint() == signed['drain']['notification_checkpoint']
    with pytest.raises(ConnectionGovernanceError):
        verify_drain_handoff(root, generation=generation, parent_pid=os.getpid(),
            proof='a'*64, loaded_revision='c'*40, now=now)
    assert owner.status() == before
    assert {str(p): p.read_bytes() for p in publication.root.rglob('*') if p.is_file()} == history


def test_missing_busy_or_unknown_terminal_proof_blocks_at_every_boundary(tmp_path, scenario, monkeypatch):
    owner, application, _ = _failed_owner(tmp_path, scenario)
    server, _ = _server(tmp_path, application)
    complete = owner.status()
    assert complete['cleanup_state'] == 'COMPLETE'
    invalid = [dict(complete, **change) for change in (
        {'owned_workers':1}, {'queued_jobs':1}, {'pid':1234}, {'generation':8},
        {'cleanup_state':'PENDING'}, {'cleanup_state':'INCOMPLETE'},
        {'state':'UNKNOWN'}, {'state':'CLEANUP_FAILED'}, {'owned_workers':False},
    )]
    invalid += [{k:v for k,v in complete.items() if k != missing}
                for missing in ('cleanup_state','pid','generation','owned_workers','queued_jobs')]
    for status in invalid:
        monkeypatch.setattr(owner, 'status', lambda: dict(status))
        assert not server.maintenance_replacement_idle(allow_drainable=True)
        server._domain_closed = True
        server.housekeeping.status_document = lambda: {
            'lifecycle_state':'STOPPED','owned_workers':0,'pass_active':False}
        assert not server._maintenance_final_owner_proof()
        with pytest.raises(ValueError, match='NOT_ZERO'):
            server._maintenance_drain_attestation()
        server._domain_closed = False
        server.housekeeping.status_document = lambda: {
            'lifecycle_state':'IDLE','owned_workers':0,'pass_active':False}
    assert not (server.restart_control.path.parent/'maintenance').exists()


def test_active_counted_analysis_drains_after_cleanup_and_stale_sample_cannot_attest(
    tmp_path, scenario, monkeypatch,
):
    owner, application, _ = _failed_owner(tmp_path, scenario)
    server, events = _server(tmp_path, application)
    old_sample = owner.status()
    entered, finish, cleanup_finished = Event(), Event(), Event()
    ticket = server.maintenance_admission.admit('SWING_ANALYSIS')
    def worker_body(*_args, cleanup_proof, **kwargs):
        kwargs['status_update']('RUNNING', 1234, None)
        entered.set()
        assert finish.wait(5)
        cleanup_proof.update(worker_stopped=True, directory_removed=True)
        cleanup_finished.set()
        raise process_module.SwingAnalysisProcessError('ISOLATED_LATER_FAILURE')
    monkeypatch.setattr(process_module, '_run_worker_body', worker_body)
    def operation():
        from tests.unit.application.test_swing_analysis_process import _execute
        try:
            with pytest.raises(SwingAnalysisProcessError):
                _execute(owner, generation=8)
        finally:
            owner.release(8)
            ticket.release()
    worker = Thread(target=operation)
    worker.start()
    assert entered.wait(5)
    assert old_sample['owned_workers'] == 0
    assert owner.status()['owned_workers'] == 1
    assert server.maintenance_replacement_idle(allow_drainable=True)
    with pytest.raises(ValueError, match='NOT_ZERO'):
        server._maintenance_drain_attestation()
    generation = 'f'*64
    assert server.maintenance_admission.claim(generation)
    drain = Thread(target=lambda: server._complete_governed_shutdown(generation, 'b'*64, 5))
    drain.start()
    assert events == []
    finish.set()
    worker.join(5); drain.join(5)
    assert not worker.is_alive() and not drain.is_alive()
    assert cleanup_finished.is_set() and events == ['cleanup', 'shutdown']
    assert owner.status()['state'] == 'FAILED'
    assert owner.status()['cleanup_state'] == 'COMPLETE'
    assert owner.status()['failure'] == 'ISOLATED_LATER_FAILURE'
