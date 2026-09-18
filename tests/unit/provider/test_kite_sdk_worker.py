"""PF-02E: actual spawn/exit proof, private IPC and retained consumer contracts."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import partial
import json
import multiprocessing
import os
import pickle
import resource
import threading
import time
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from kronos.provider.adapters.kite import sdk_worker as module
from kronos.provider.adapters.kite.client import _KiteCleanupError, _KiteCleanupPending
from kronos.provider.exceptions.connectivity import ProviderConnectivityError, ProviderErrorCode
from kronos.provider.services.provider_authentication import ConnectionAttemptDeadline
from tests.unit.provider.test_kite_login_navigator import _PF02DSignal

IST = ZoneInfo('Asia/Kolkata')
STAMP = datetime(2026, 9, 1, 10, 0, tzinfo=IST)


def _raw_instrument(index=0):
    return dict(instrument_token=1001 + index, exchange_token=2001 + index,
        tradingsymbol='RELIANCE' if index == 0 else f'SYMBOL{index}', name='RELIANCE',
        last_price=100.0, expiry='', strike=0.0, tick_size=0.05,
        lot_size=1, instrument_type='EQ', segment='NSE', exchange='NSE')


def _spawn_sdk(receiver, sender, *, mode, entered, release, telemetry, root=None):
    """Importable spawn target; patches only child-local external SDK dependencies."""
    import signal
    from kronos.provider.adapters.kite import client
    from kronos.provider.adapters.kite import sdk_worker
    def event(name):
        telemetry.send_bytes(json.dumps({'event': name}).encode())
    def fault(phase):
        event(phase)
        if mode == 'resist_' + phase:
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
        if mode in {'block_' + phase, 'resist_' + phase, 'late_' + phase}:
            entered.set()
            release.wait(8)
        if mode == 'exit_' + phase:
            entered.set()
            os._exit(19)
        if mode == 'fail_' + phase:
            raise RuntimeError('private SDK detail never transmitted')
    class Session:
        def close(self):
            fault('close')
    class SDK:
        def __init__(self, **arguments):
            fault('construct')
            self.api_key = arguments['api_key']
            self.access_token = None
            self.timeout = 7
            self.reqsession = Session()
            self.profiles = 0
        def set_session_expiry_hook(self, hook):
            self.hook = hook
        def login_url(self):
            return 'https://kite.zerodha.com/connect/login?v=3&api_key=redacted'
        def generate_session(self, token, secret):
            assert type(token) is str and token and type(secret) is str and secret
            fault('exchange')
            self.access_token = 'test-private-access'
            return {'access_token': self.access_token}
        def profile(self):
            self.profiles += 1
            fault('principal' if self.profiles == 1 else 'profile')
            if mode == 'expire' and self.profiles > 1:
                self.hook()
            return {'user_id': 'PRINCIPAL123'}
        def instruments(self, exchange=None):
            fault('master' if exchange is None else 'instruments')
            if mode == 'check_timeout':
                assert self.timeout > 1, 'old authentication budget retained'
            rows = [_raw_instrument(i) for i in range(25000 if mode == 'large' else 1)]
            if mode == 'nonfinite':
                rows[0]['tick_size'] = float('nan')
            return rows
        def historical_data(self, **arguments):
            fault('historical')
            assert arguments['continuous'] is False and arguments['oi'] is False
            assert arguments['from_date'].tzinfo == IST
            return [dict(date=arguments['from_date'], open=99., high=102., low=98., close=101., volume=10)]
        def quote(self, instruments):
            fault('quote')
            return {key: dict(instrument_token=1001, last_price=100., timestamp=STAMP,
                last_trade_time=STAMP, volume=20, buy_quantity=5, sell_quantity=7,
                oi=0, ohlc=dict(open=99., high=102., low=98., close=100.),
                depth=dict(buy=[dict(price=99., quantity=2, orders=1)], sell=[])) for key in instruments}
        ltp = quote
        ohlc = quote
        def invalidate_access_token(self):
            raise AssertionError('remote logout prohibited')
    if root is None:
        client._KiteConnect = SDK
    else:
        installed = client._KiteConnect
        def real_sdk(**arguments):
            sdk = installed(**arguments, root=root, timeout=0.08)
            # Installed requests.Session.request and HTTPAdapter remain real.
            sdk.reqsession.trust_env = False
            return sdk
        client._KiteConnect = real_sdk
    if mode in {'partial', 'oversized', 'malformed', 'wrong_id', 'partial_result'}:
        def bad_result(out, identity, result):
            entered.set()
            if mode == 'partial':
                out.sendall(b'\x00\x00')
                release.wait(8)
            elif mode == 'oversized':
                out.sendall((module._FRAME_BYTES + 1).to_bytes(4, 'big'))
            elif mode == 'malformed':
                module._send_frame(out, b'{"duplicate":1,"duplicate":2}')
            elif mode == 'wrong_id':
                module._send_frame(out, b'{"id":true,"type":"end","count":0}')
            else:
                module._send_frame(out, json.dumps(dict(id=identity, type='begin', kind='list')).encode())
                module._send_frame(out, json.dumps(dict(id=identity, type='data', items=[1])).encode())
                module._send_frame(out, json.dumps(dict(id=identity, type='end', count=2)).encode())
        sdk_worker._send_result = bad_result
    try:
        sdk_worker._sdk_worker(receiver, sender)
    finally:
        telemetry.send_bytes(json.dumps({'child_maxrss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}).encode())
        telemetry.close()


def worker_case(monkeypatch, *, mode='success', root=None, deadline=None):
    context = multiprocessing.get_context('spawn')
    entered, release = _PF02DSignal(context), _PF02DSignal(context)
    telemetry, child_telemetry = context.Pipe(duplex=False)
    rows, connections = [], []
    original_process = context.Process
    original_socket_pair = module._sdk_socket_pair
    original_close = multiprocessing.process.BaseProcess.close
    def process_factory(*args, **kwargs):
        process = original_process(*args, **kwargs)
        rows.append(SimpleNamespace(process=process, exit=None))
        return process
    def observed_close(process):
        row = next((r for r in rows if r.process is process), None)
        if row is not None:
            row.exit = (process.pid, process.exitcode, process.is_alive())
        return original_close(process)
    def socket_pair():
        pair = original_socket_pair()
        connections.extend(pair)
        return pair
    monkeypatch.setattr(context, 'Process', process_factory)
    monkeypatch.setattr(module, '_sdk_socket_pair', socket_pair)
    monkeypatch.setattr(multiprocessing.process.BaseProcess, 'close', observed_close)
    monkeypatch.setattr(module, '_sdk_worker', partial(_spawn_sdk, mode=mode,
        entered=entered, release=release, telemetry=child_telemetry, root=root))
    deadline = deadline or ConnectionAttemptDeadline(1, timeout_seconds=5)
    case = SimpleNamespace(deadline=deadline, entered=entered, release=release,
        rows=rows, connections=connections, telemetry=telemetry,
        child_telemetry=child_telemetry, original_close=original_close)
    case.owner = module.SDKWorkerOwner(deadline)
    return case


def finish_case(case):
    # Failed ownership is cleared only by test teardown after its assertions;
    # production never resets a sticky failed owner or retries physical close.
    case.release.set()
    case.deadline.cancel()
    for row in case.rows:
        process = row.process
        if not process._closed:
            if process.pid is not None:
                process.join(.1)
                if process.is_alive():
                    process.kill(); process.join(1)
            case.original_close(process)
    for connection in case.connections:
        connection.close()
    case.child_telemetry.close()
    case.telemetry.close()
    with module._owners_lock:
        module._owners[:] = [o for o in module._owners if o.process not in [r.process for r in case.rows]]


def observed_events(case):
    values = []
    while case.telemetry.poll():
        try:
            values.append(json.loads(case.telemetry.recv_bytes()))
        except EOFError:
            break
    return values


def assert_reaped(case, *, failed=False):
    assert case.rows
    for row in case.rows:
        assert row.process._closed
        pid, exitcode, alive = row.exit
        assert pid is not None and exitcode is not None and not alive
        with pytest.raises(ChildProcessError):
            os.waitpid(pid, os.WNOHANG)
    assert all(getattr(c, 'closed', getattr(c, '_closed', False)) for c in case.connections)
    assert case.owner.local_cleanup_state == ('FAILED' if failed else 'COMPLETE')
    assert case.deadline.snapshot()['resources_pending'] is failed
    print('PF02E_ACTUAL_EXIT', [r.exit for r in case.rows], 'IPC_CLOSED', len(case.connections),
          'SDK_CLOSE', case.owner.sdk_close_state, 'CUSTODY', case.owner.local_cleanup_state)


def retained(case):
    case.owner.start('test-private-key')
    adapter = module._WorkerAuthenticationHandle(case.owner)
    candidate = adapter.exchange_once('test-private-token', 'test-private-secret')
    assert candidate.principal_user_id_once(timeout_seconds=.05) == 'PRINCIPAL123'
    candidate.retain_session()
    return adapter, candidate


def in_thread(operation):
    values, errors = [], []
    def run():
        try:
            values.append(operation())
        except BaseException as error:
            errors.append(error)
    thread = threading.Thread(target=run)
    thread.start()
    return thread, values, errors


@pytest.mark.parametrize('phase', ['construct', 'exchange', 'principal', 'profile', 'master'])
@pytest.mark.parametrize('terminal', ['cancel', 'expire'])
def test_real_spawn_stalled_sdk_is_terminated_and_reaped(monkeypatch, phase, terminal):
    case = worker_case(monkeypatch, mode='block_' + phase)
    thread = None
    try:
        if phase == 'construct':
            operation = lambda: case.owner.start('synthetic-key')
        else:
            case.owner.start('synthetic-key')
            adapter = module._WorkerAuthenticationHandle(case.owner)
            if phase == 'exchange':
                operation = lambda: adapter.exchange_once('token', 'secret')
            else:
                candidate = adapter.exchange_once('token', 'secret')
                if phase == 'principal':
                    operation = candidate.principal_user_id_once
                else:
                    assert candidate.principal_user_id_once() == 'PRINCIPAL123'
                    candidate.retain_session()
                    case.owner._limit = .25
                    operation = candidate.verify_profile_once if phase == 'profile' else candidate.instrument_master_records
        thread, values, errors = in_thread(operation)
        assert case.entered.wait(3)
        started = time.monotonic()
        if phase in {'profile', 'master'}:
            if terminal == 'cancel':
                with pytest.raises(_KiteCleanupPending):
                    case.owner.close_local()
        else:
            case.deadline.finish('CANCELLED' if terminal == 'cancel' else 'TIMED_OUT')
        thread.join(2)
        assert not thread.is_alive() and not values and errors
        assert time.monotonic() - started < 1.5
        assert_reaped(case)
        assert case.owner.sdk_close_state == 'NOT_ATTEMPTED'
        assert len(case.rows) == 1
    finally:
        finish_case(case)
        if thread is not None:
            thread.join(1)


@pytest.mark.parametrize('mode', ['block_close', 'fail_close'])
def test_physical_sdk_close_failure_stays_failed_after_actual_os_exit(monkeypatch, mode):
    case = worker_case(monkeypatch, mode=mode)
    try:
        adapter, candidate = retained(case)
        start = time.monotonic()
        with pytest.raises(_KiteCleanupError):
            candidate.close_local()
        assert time.monotonic() - start < 1.5
        assert_reaped(case, failed=True)
        assert case.owner.sdk_close_state == 'FAILED_OR_UNCONFIRMED'
        with pytest.raises(_KiteCleanupError):
            candidate.close_local()
        other = module.SDKWorkerOwner(ConnectionAttemptDeadline(2, timeout_seconds=5))
        with pytest.raises(_KiteCleanupPending):
            other.start('another-key')
        assert len(case.rows) == 1 and case.owner in module._owners
    finally:
        finish_case(case)


@pytest.mark.parametrize('mode', ['partial', 'oversized', 'malformed', 'wrong_id', 'partial_result', 'exit_construct'])
def test_malformed_interrupted_ipc_and_child_exit_never_return_partial_success(monkeypatch, mode):
    case = worker_case(monkeypatch, mode=mode)
    try:
        thread, values, errors = in_thread(lambda: case.owner.start('synthetic-key'))
        assert case.entered.wait(3)
        if mode == 'partial':
            case.deadline.cancel()
        thread.join(2)
        assert not thread.is_alive() and errors and not values
        assert_reaped(case)
    finally:
        finish_case(case)


def test_term_resistant_child_requires_and_proves_sigkill(monkeypatch):
    case = worker_case(monkeypatch, mode='resist_exchange')
    try:
        case.owner.start('key')
        thread, _, errors = in_thread(lambda: case.owner.call('exchange', dict(token='token', secret='secret')))
        assert case.entered.wait(3)
        case.deadline.cancel()
        thread.join(2)
        assert errors and not thread.is_alive()
        assert_reaped(case)
        assert case.rows[0].exit[1] == -9
    finally:
        finish_case(case)


def test_unconfirmed_os_cleanup_retains_exact_owner_and_blocks_overlap(monkeypatch):
    case = worker_case(monkeypatch, mode='block_exchange')
    try:
        case.owner.start('key')
        process = case.owner.process
        original_kill = process.kill
        monkeypatch.setattr(process, 'terminate', lambda: None)
        monkeypatch.setattr(process, 'kill', lambda: None)
        thread, _, errors = in_thread(lambda: case.owner.call('exchange', dict(token='token', secret='secret')))
        assert case.entered.wait(3)
        case.deadline.cancel(); thread.join(2)
        assert errors and not thread.is_alive() and process.is_alive()
        assert case.owner.local_cleanup_state == 'FAILED'
        assert case.deadline.snapshot()['resources_pending']
        assert case.owner in module._owners
        with pytest.raises(_KiteCleanupPending):
            module.SDKWorkerOwner(ConnectionAttemptDeadline(2, timeout_seconds=5)).start('next')
        original_kill(); process.join(1)
        assert process.exitcode == -9
        print('PF02E_UNCONFIRMED_RETAINED', process.pid, 'test_teardown_exit', process.exitcode)
    finally:
        finish_case(case)


def test_transfer_old_disposal_deadline_detachment_and_fresh_attempt(monkeypatch):
    case = worker_case(monkeypatch, mode='check_timeout')
    try:
        adapter, candidate = retained(case)
        adapter.close_local()
        case.deadline.finish('TIMED_OUT')
        assert candidate.active
        assert candidate.instrument_records('NSE')[0]['tradingsymbol'] == 'RELIANCE'
        assert len(case.rows) == 1
        candidate.close_local(); candidate.close_local()
        assert_reaped(case)
        rows = observed_events(case)
        assert [r.get('event') for r in rows].count('exchange') == 1
        assert [r.get('event') for r in rows].count('principal') == 1
        assert [r.get('event') for r in rows].count('close') == 1
        assert case.owner.sdk_close_state == 'SUCCEEDED'
        fresh = module.SDKWorkerOwner(ConnectionAttemptDeadline(2, timeout_seconds=5))
        fresh.start('fresh-key'); fresh.close_local()
        assert len(case.rows) == 2
        assert_reaped(case)
    finally:
        finish_case(case)


def test_session_expiry_hook_invalidates_parent_and_never_reauthenticates(monkeypatch):
    case = worker_case(monkeypatch, mode='expire')
    try:
        _, candidate = retained(case)
        with pytest.raises(ProviderConnectivityError) as error:
            candidate.verify_profile_once()
        assert error.value.code is ProviderErrorCode.ACCESS_TOKEN_INVALID_OR_EXPIRED
        assert not candidate.active
        candidate.close_local()
        assert_reaped(case)
        assert sum(r.get('event') == 'exchange' for r in observed_events(case)) == 1
    finally:
        finish_case(case)


def test_bounded_admission_does_not_cancel_another_consumers_read(monkeypatch):
    case = worker_case(monkeypatch, mode='block_master')
    try:
        _, candidate = retained(case)
        first, values, errors = in_thread(candidate.instrument_master_records)
        assert case.entered.wait(3)
        second, _, second_errors = in_thread(lambda: case.owner.call('profile', {}, timeout_seconds=.05))
        second.join(1)
        assert second_errors and not second.is_alive()
        assert candidate.active and case.owner.process.is_alive()
        # Explicitly occupy the sole waiting slot, then reject a third admission.
        assert case.owner._slots.acquire(blocking=False)
        with pytest.raises(ProviderConnectivityError):
            candidate.verify_profile_once()
        case.owner._slots.release()
        case.release.set(); first.join(2)
        assert values and not errors
        candidate.close_local(); assert_reaped(case)
    finally:
        finish_case(case)


@pytest.mark.parametrize('value', [date(2026, 9, 1), STAMP, Decimal('0.0500'), {'t': 'date', 'v': 'ordinary-map'}, (), [None, True, 3, 1.5]])
def test_private_codec_preserves_allowed_types(value):
    result = module._decode(module._parse(module._json_bytes(module._encode(value), module._FRAME_BYTES)))
    assert type(result) is type(value) and result == value
    if isinstance(value, datetime):
        assert result.tzinfo == value.tzinfo


@pytest.mark.parametrize('operation,args', [('place_order', {}), ('__getattribute__', {'name': 'api_key'}), ('exchange', {'token': 'a'}), ('full_quotes', {'instruments': ('a', 'a')}), ('historical', {'instrument_token': True, 'from_date': STAMP, 'to_date': STAMP, 'interval': 'day'})])
def test_ipc_has_no_generic_or_trading_authority(operation, args):
    with pytest.raises(ValueError):
        module._validated_request(dict(v=1, id=1, op=operation, args=module._encode(args), seconds=1., retained=False), 0)


def test_handles_are_redacted_and_not_serializable():
    owner = module.SDKWorkerOwner(ConnectionAttemptDeadline(1, timeout_seconds=5))
    for value in (owner, module._WorkerAuthenticationHandle(owner), module._WorkerCandidateHandle(owner)):
        assert 'redacted' in repr(value)
        with pytest.raises(TypeError):
            pickle.dumps(value)


def test_installed_sdk_requests_trickling_http_has_absolute_bound(monkeypatch):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    seen, finished = threading.Event(), threading.Event()
    requests_seen = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests_seen.append(self.path)
            self.rfile.read(int(self.headers.get('Content-Length', 0)))
            body = b'{"status":"success","data":{"access_token":"test-only"}}'
            self.send_response(200); self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body))); self.end_headers()
            seen.set()
            try:
                for value in body:
                    self.wfile.write(bytes([value])); self.wfile.flush()
                    time.sleep(.01)  # 10ms gaps remain below SDK's 80ms inactivity timeout.
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                finished.set()
        def log_message(self, *_):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    serving = threading.Thread(target=lambda: server.serve_forever(poll_interval=.01)); serving.start()
    case = worker_case(monkeypatch, root=f'http://127.0.0.1:{server.server_port}')
    try:
        case.owner.start('isolated-key')
        start = time.monotonic()
        with pytest.raises(TimeoutError):
            case.owner.call('exchange', dict(token='isolated-token', secret='isolated-secret'))
        elapsed = time.monotonic() - start
        assert seen.is_set() and .07 <= elapsed < 1.2
        assert requests_seen == ['/session/token']
        assert_reaped(case)
        assert finished.wait(2)
        print('PF02E_INSTALLED_REQUESTS_TRICKLE', 'inactivity_seconds', .08, 'gap_seconds', .01, 'elapsed_seconds', elapsed)
    finally:
        finish_case(case)
        server.shutdown(); serving.join(1); server.server_close()


def service_case(monkeypatch, case):
    from kronos.provider.services.provider_authentication import ProviderAuthenticationService
    from kronos.provider.adapters.kite.authentication import create_kite_authentication_adapter
    from tests.unit.provider.test_provider_authentication_service import _Harness
    harness = _Harness()
    def receive_once(*, deadline):
        assert harness.clock() < deadline <= harness.clock() + timedelta(seconds=5)
        harness.listener.receive_count += 1
        return harness.callback
    harness.listener.receive_once = receive_once
    adapters = []
    def adapter(api_key):
        value = create_kite_authentication_adapter(api_key, use_sdk_worker=True)
        adapters.append(value)
        return value
    service = ProviderAuthenticationService(harness.configuration,
        **dict(harness.service_arguments, adapter_factory=adapter), ordinary_deadline=case.deadline)
    attempt = service.begin_login()
    case.owner = module._owners[0]
    return SimpleNamespace(harness=harness, adapters=adapters, service=service, attempt=attempt)


def test_real_service_publication_public_read_contracts_and_monitoring_bootstrap(monkeypatch):
    from kronos.provider.models.authentication import AuthenticationAttemptState
    from kronos.provider.contracts.market_data import HistoricalCandleRequest, HistoricalInterval
    from kronos.provider.adapters.kite import monitoring
    case = worker_case(monkeypatch)
    try:
        integration = service_case(monkeypatch, case)
        outcome = integration.service.complete_callback(integration.attempt)
        assert outcome.state is AuthenticationAttemptState.SUCCEEDED, (outcome.failure_code, observed_events(case))
        capability = integration.service.authenticated_read_only_capability()
        assert capability.active
        integration.adapters[0].dispose_local()
        case.deadline.commit(lambda: None)
        case.deadline.finish('TIMED_OUT')
        master = capability.instrument_master_records()
        instruments = capability.instrument_records('NSE')
        assert len(master) == len(instruments) == 1
        instrument = instruments[0]
        assert instrument.tick_size == Decimal('0.05')
        request = HistoricalCandleRequest(instrument=instrument, start=STAMP,
            end=STAMP + timedelta(hours=1), interval=HistoricalInterval.DAY)
        candles = capability.historical_candles(request)
        assert candles[0].timestamp == STAMP and candles[0].close == 101.
        assert capability.quote(instrument).last_price == 100.
        assert capability.ltp(instrument).last_price == 100.
        assert capability.ohlc(instrument).last_price == 100.
        snapshot = sealed_master(master)
        full = capability.full_quotes(snapshot.records, request_identity='isolated-full-quote')
        assert len(full) == 1 and full[0].last_price == Decimal('100')
        assert full[0].bids[0].quantity == 2 and full[0].total_bid_quantity == 5
        with pytest.raises(ValueError, match='FULL_QUOTE_RATE_LIMIT'):
            capability.full_quotes(snapshot.records, request_identity='isolated-rate-limited')
        assert capability.active
        bootstrap = []
        class Monitoring:
            def __init__(self, **kwargs):
                assert kwargs['access_token'] == 'test-private-access'
                assert kwargs['token_resolver'](instrument) == 1001
                bootstrap.append(kwargs['consumer'])
        monkeypatch.setattr(monitoring, 'KiteReadOnlyMonitoringSession', Monitoring)
        consumer = SimpleNamespace(on_market_tick=lambda _: None, on_order_update=lambda _: None, on_connection_state=lambda _: None)
        assert isinstance(capability.open_monitoring_session(consumer), Monitoring)
        assert bootstrap == [consumer]
        assert integration.harness.callback.token.use_count == 1
        assert integration.harness.credentials.lease.use_count == 1
        assert len(case.rows) == 1
        integration.service.end_kronos_session()
        assert_reaped(case)
    finally:
        finish_case(case)


def test_repeated_large_reads_have_one_worker_and_release_all_owned_handles(monkeypatch):
    case = worker_case(monkeypatch, mode='large')
    parent_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    observations = []
    try:
        for generation in range(3):
            if generation:
                case.owner = module.SDKWorkerOwner(ConnectionAttemptDeadline(generation + 1, timeout_seconds=5))
                case.deadline = case.owner._deadline
            _, candidate = retained(case)
            assert len(module._owners) == 1
            rows = candidate.instrument_master_records()
            assert len(rows) == 25000 and rows[-1]['instrument_token'] == 26000
            candidate.close_local(); assert_reaped(case)
            observations += observed_events(case)
            assert len(module._owners) == 0
        print('PF02E_RESOURCE_PROFILE', json.dumps(dict(cycles=3, maximum_owned_workers=1,
            large_read_records=25000, child_maxrss_bytes=[r['child_maxrss_bytes'] for r in observations if 'child_maxrss_bytes' in r],
            parent_maxrss_before_bytes=parent_before, parent_maxrss_after_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            closed_processes=len(case.rows), closed_ipc_handles=len(case.connections))))
    finally:
        finish_case(case)


def sealed_master(records):
    from kronos.provider.instrument_master import create_provider_instrument_snapshot, ProviderAcquisitionOutcome
    return create_provider_instrument_snapshot(records=records, provider='KITE',
        dataset_identity='ISOLATED-MASTER', operation_identity='ISOLATED-MASTER-OP',
        source_boundary=STAMP, request_started_at=STAMP, response_received_at=STAMP,
        acquired_at=STAMP, acquisition_effective_at=STAMP,
        authenticated_context_identity='isolated-context', authorized_operation_identity='isolated-master',
        component_identities=('ALL',), acquisition_outcome=ProviderAcquisitionOutcome.COMPLETE, provenance=('TEST',))


def production_case(tmp_path, monkeypatch, *, mode='success'):
    from tests.unit.tools.test_provider_foundation_v2_authentication import _timed_production_connection
    from tools.provider_pilots import provider_foundation_v2_historical_proof as proof
    from kronos.provider.adapters.kite.authentication import create_kite_authentication_adapter
    real_monotonic = time.monotonic
    production = _timed_production_connection(tmp_path, monkeypatch)
    # Its application deadline has its own injected clock. Restore the global
    # clock for real child operation budgets and measured execution time.
    monkeypatch.setattr(time, 'monotonic', real_monotonic)
    monkeypatch.setattr(proof, 'create_kite_authentication_adapter', create_kite_authentication_adapter)
    case = worker_case(monkeypatch, mode=mode)
    original_start = module.SDKWorkerOwner.start
    def observe_owner(owner, api_key):
        case.owner = owner
        case.deadline = owner._deadline
        return original_start(owner, api_key)
    monkeypatch.setattr(module.SDKWorkerOwner, 'start', observe_owner)
    return production, case


@pytest.mark.parametrize('phase', ['construct', 'exchange', 'principal'])
def test_ordinary_factory_expiry_terminates_child_and_fences_publication(tmp_path, monkeypatch, phase):
    from tests.unit.tools.test_provider_foundation_v2_authentication import (
        _start_connection_worker, _pf02b_assert_failed_but_resolved,
        _assert_status_reads_finish_while_worker_blocked,
    )
    production, case = production_case(tmp_path, monkeypatch, mode='block_' + phase)
    thread = None
    try:
        thread, errors = _start_connection_worker(production)
        assert case.entered.wait(3)
        _assert_status_reads_finish_while_worker_blocked(production)
        production.monotonic_now[0] = 10
        production.timers[-1].fire()
        thread.join(2)
        assert not thread.is_alive() and not errors
        status = _pf02b_assert_failed_but_resolved(production)
        assert status['state'] == 'TIMED_OUT'
        assert_reaped(case)
        assert len(case.rows) == 1
        if phase != 'construct':
            assert production.harness.callback.token.use_count == 1
            assert production.harness.credentials.lease.use_count == 1
        production.monotonic_now[0] = 30
        assert production.app.connect_provider()
        assert production.app.connection_attempt_status()['generation'] > status['generation']
        assert len(case.rows) == 1  # New eligible attempt is queued, not executed.
    finally:
        production.app.close()
        finish_case(case)
        if thread is not None:
            thread.join(1)


def test_late_successful_exchange_response_cannot_publish_or_restore(tmp_path, monkeypatch):
    from tests.unit.tools.test_provider_foundation_v2_authentication import _start_connection_worker, _pf02b_assert_failed_but_resolved
    production, case = production_case(tmp_path, monkeypatch)
    ready, release = threading.Event(), threading.Event()
    original = module.SDKWorkerOwner._exchange
    def delayed_response(owner, operation, arguments, expires, **keywords):
        value = original(owner, operation, arguments, expires, **keywords)
        if operation == 'exchange':
            ready.set()
            assert release.wait(3)
        return value
    monkeypatch.setattr(module.SDKWorkerOwner, '_exchange', delayed_response)
    thread = None
    try:
        thread, errors = _start_connection_worker(production)
        assert ready.wait(3)  # Actual SDK exchange already succeeded in the child.
        production.monotonic_now[0] = 10
        production.timers[-1].fire()
        assert production.app.authenticated_read_only_capability() is None
        release.set(); thread.join(2)
        assert not thread.is_alive() and not errors
        _pf02b_assert_failed_but_resolved(production)
        assert_reaped(case)
        events = [r.get('event') for r in observed_events(case)]
        assert events.count('exchange') == 1 and 'principal' not in events
        assert events.count('close') == 1
        assert case.owner.sdk_close_state == 'SUCCEEDED'
    finally:
        release.set()
        production.app.close()
        finish_case(case)
        if thread is not None:
            thread.join(1)


def test_concurrent_swing_intraday_leases_keep_same_retained_worker(tmp_path, monkeypatch):
    from tests.unit.tools.test_provider_foundation_v2_authentication import _run_ordinary_connection
    from kronos.provider.contracts.provider_authentication import ReadOnlyProviderOperation
    from kronos.provider.contracts.market_data import HistoricalCandleRequest, HistoricalInterval
    from kronos.provider.contracts.instrument_master import KITE_INSTRUMENT_MASTER_OPERATION
    production, case = production_case(tmp_path, monkeypatch)
    try:
        _run_ordinary_connection(production)
        assert production.app.snapshot().provider_state.value == 'CONNECTED'
        assert len(case.rows) == 1
        assert case.owner._deadline is None and case.owner._retained
        production.monotonic_now[0] = 1000  # Beyond old Connect expiry.
        case.deadline.require()
        swing = production.shared.acquire_lease(consumer_identity='SWING-READ', operations=frozenset(ReadOnlyProviderOperation))
        intraday = production.shared.acquire_lease(consumer_identity='INTRADAY-READ', operations=frozenset(ReadOnlyProviderOperation))
        assert swing.authenticated_context_identity == intraday.authenticated_context_identity
        assert swing.lease_identity != intraday.lease_identity
        instrument = swing.instrument_records('NSE')[0]
        barrier = threading.Barrier(2)
        def swing_read():
            barrier.wait()
            request = HistoricalCandleRequest(instrument, STAMP, STAMP + timedelta(hours=1), HistoricalInterval.DAY)
            result = swing.historical_candles(request)
            swing.release()
            return result
        def intraday_read():
            barrier.wait()
            return intraday.quote(instrument)
        with ThreadPoolExecutor(max_workers=2) as executor:
            a, b = executor.submit(swing_read), executor.submit(intraday_read)
            assert a.result(timeout=2)[0].close == 101.
            assert b.result(timeout=2).last_price == 100.
        assert not swing.active and intraday.active
        assert intraday.ltp(instrument).last_price == 100.
        assert len(case.rows) == 1 and case.owner.process.is_alive()
        records = production.shared.acquire_provider_instrument_master_records(operation_identity=KITE_INSTRUMENT_MASTER_OPERATION)
        assert len(records) == 1
        intraday.release()
        assert case.owner.process.is_alive()  # Product release never disposes shared SDK.
        production.shared.end_kronos_session()
        assert_reaped(case)
        events = [r.get('event') for r in observed_events(case)]
        assert events.count('construct') == events.count('exchange') == events.count('principal') == events.count('close') == 1
        print('PF02E_SHARED_CONSUMERS', 'single_context', 'single_worker', 'old_deadline_passed', 'independent_lease_release')
    finally:
        production.app.close()
        finish_case(case)


@pytest.mark.parametrize('started', [False, True])
def test_startup_exception_keeps_ambiguous_custody_or_reaps_published_child(monkeypatch, started):
    case = worker_case(monkeypatch)
    original = multiprocessing.process.BaseProcess.start
    def fail_start(process):
        if started:
            original(process)
        raise OSError('test startup boundary failure')
    monkeypatch.setattr(multiprocessing.process.BaseProcess, 'start', fail_start)
    try:
        with pytest.raises(OSError):
            case.owner.start('key')
        assert case.owner.start_attempted and not case.owner.start_returned
        if started:
            assert_reaped(case)
        else:
            assert case.owner.local_cleanup_state == 'FAILED'
            assert case.deadline.snapshot()['resources_pending']
            assert case.owner in module._owners
            assert case.rows[0].exit == (None, None, False)
    finally:
        finish_case(case)


@pytest.mark.parametrize('mode', ['fail_close', 'block_close'])
def test_retained_service_close_failure_stays_owned_and_blocks_fresh_service_attempt(monkeypatch, mode):
    from kronos.provider.models.authentication import AuthenticationAttemptState
    case = worker_case(monkeypatch, mode=mode)
    try:
        integration = service_case(monkeypatch, case)
        assert integration.service.complete_callback(integration.attempt).state is AuthenticationAttemptState.SUCCEEDED
        case.deadline.commit(lambda: None)
        integration.service.end_kronos_session()
        assert integration.service.authenticated_read_only_capability() is None
        assert_reaped(case, failed=True)
        with pytest.raises(RuntimeError, match='ATTEMPT_ALREADY_ACTIVE'):
            integration.service.begin_login()
        integration.service.end_kronos_session()
        assert_reaped(case, failed=True)
        assert sum(r.get('event') == 'close' for r in observed_events(case)) == 1
    finally:
        finish_case(case)


def test_existing_monitoring_constructor_gets_private_bootstrap_without_new_sdk_session(monkeypatch):
    from tests.unit.provider.test_kite_websocket_monitoring import _Socket, _Consumer, _NSE
    from kronos.provider.adapters.kite.monitoring import KiteReadOnlyMonitoringSession
    case = worker_case(monkeypatch)
    try:
        _, candidate = retained(case)
        socket, consumer = _Socket(), _Consumer()
        def create_socket(key, token):
            assert key == 'test-private-key' and token == 'test-private-access'
            return socket
        session = candidate.open_monitoring_session(token_resolver=lambda record: 1001 if record == _NSE else None,
            consumer=consumer, clock=lambda: STAMP, socket_factory=create_socket)
        assert type(session) is KiteReadOnlyMonitoringSession
        session.connect()
        session.subscribe((_NSE,))
        assert socket.subscribed[-1] == [1001]
        session.disconnect()
        assert socket.closed and candidate.active and len(case.rows) == 1
        candidate.close_local(); assert_reaped(case)
    finally:
        finish_case(case)


def test_public_large_master_preserves_every_record_and_types(monkeypatch):
    case = worker_case(monkeypatch, mode='large')
    try:
        integration = service_case(monkeypatch, case)
        integration.service.complete_callback(integration.attempt)
        capability = integration.service.authenticated_read_only_capability()
        before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        started = time.monotonic()
        records = capability.instrument_master_records()
        elapsed = time.monotonic() - started
        assert len(records) == 25000 and records[-1].provider_instrument_token == 26000
        assert all(type(r.tick_size) is Decimal and r.tick_size == Decimal('0.05') for r in records)
        integration.service.end_kronos_session(); assert_reaped(case)
        telemetry = observed_events(case)
        print('PF02E_PUBLIC_MASTER_PROFILE', json.dumps(dict(records=len(records), elapsed_seconds=elapsed,
            parent_maxrss_before_bytes=before, parent_maxrss_after_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            child_maxrss_bytes=[r['child_maxrss_bytes'] for r in telemetry if 'child_maxrss_bytes' in r])))
    finally:
        finish_case(case)


def test_installed_sdk_success_cycles_close_pooled_http_sockets_and_process_handles(monkeypatch):
    import csv
    from io import StringIO
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.parse import urlsplit, parse_qs
    from kronos.provider.adapters.kite.authentication import _KiteCandidateContext
    state_lock = threading.Lock()
    sockets = {'opened': 0, 'closed': 0}
    routes = []
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        def setup(self):
            super().setup()
            with state_lock:
                sockets['opened'] += 1
        def finish(self):
            try:
                super().finish()
            finally:
                with state_lock:
                    sockets['closed'] += 1
        def do_POST(self):
            assert self.path == '/session/token'
            self.rfile.read(int(self.headers.get('Content-Length', 0)))
            routes.append(self.path)
            self.reply(dict(access_token='isolated-token', login_time='2026-09-01 10:00:00'))
        def do_GET(self):
            path = urlsplit(self.path).path
            routes.append(path)
            if path == '/user/profile':
                self.reply(dict(user_id='PRINCIPAL123'))
            elif path.startswith('/instruments/historical/'):
                self.reply(dict(candles=[['2026-09-01T10:00:00+0530', 99, 102, 98, 101, 10]]))
            elif path.startswith('/instruments'):
                row = _raw_instrument()
                output = StringIO()
                writer = csv.DictWriter(output, fieldnames=list(row)); writer.writeheader(); writer.writerow(row)
                self.bytes_reply(output.getvalue().encode(), 'text/csv')
            elif path in {'/quote', '/quote/ltp', '/quote/ohlc'}:
                keys = parse_qs(urlsplit(self.path).query)['i']
                self.reply({key: dict(instrument_token=1001, last_price=100., timestamp='2026-09-01 10:00:00',
                    last_trade_time='2026-09-01 10:00:00', volume=20,
                    ohlc=dict(open=99., high=102., low=98., close=100.)) for key in keys})
            else:
                raise AssertionError('unauthorized isolated route')
        def reply(self, data):
            self.bytes_reply(json.dumps(dict(status='success', data=data)).encode(), 'application/json')
        def bytes_reply(self, payload, content_type):
            self.send_response(200); self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(payload))); self.end_headers()
            self.wfile.write(payload); self.wfile.flush()
        def log_message(self, *_):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    serving = threading.Thread(target=lambda: server.serve_forever(poll_interval=.01)); serving.start()
    case = worker_case(monkeypatch, root=f'http://127.0.0.1:{server.server_port}')
    try:
        from kronos.provider.contracts.market_data import HistoricalCandleRequest, HistoricalInterval
        for cycle in range(3):
            if cycle:
                case.deadline = ConnectionAttemptDeadline(cycle + 1, timeout_seconds=5)
                case.owner = module.SDKWorkerOwner(case.deadline)
            case.owner.start('isolated-key')
            auth = module._WorkerAuthenticationHandle(case.owner)
            candidate_handle = auth.exchange_once('isolated-request', 'isolated-secret')
            context = _KiteCandidateContext(candidate_handle, operation_recorder=None, remaining_budget=None)
            assert context.principal_evidence().compare_expected('PRINCIPAL123').value == 'MATCHED'
            capability = context.issue_read_only_capability()
            context.retain_session()
            records = capability.instrument_master_records()
            record = capability.instrument_records('NSE')[0]
            request = HistoricalCandleRequest(record, STAMP, STAMP + timedelta(hours=1), HistoricalInterval.DAY)
            assert capability.historical_candles(request)[0].timestamp == STAMP
            assert capability.quote(record).timestamp == STAMP
            assert capability.ltp(record).last_price == 100.
            assert capability.ohlc(record).ohlc.high == 102.
            assert capability.full_quotes(sealed_master(records).records, request_identity='isolated-full')[0].last_price == Decimal('100')
            context.dispose_local(); assert_reaped(case)
            until = time.monotonic() + 1
            while sockets['opened'] != sockets['closed'] and time.monotonic() < until:
                time.sleep(.01)
            assert sockets['opened'] == sockets['closed']
            assert not module._owners
        assert routes.count('/session/token') == 3 and routes.count('/user/profile') == 3
        print('PF02E_INSTALLED_SDK_CYCLES', json.dumps(dict(cycles=3, sockets=sockets,
            closed_workers=len(case.rows), closed_ipc_handles=len(case.connections), requests=len(routes))))
    finally:
        finish_case(case)
        server.shutdown(); serving.join(1); server.server_close()


def test_unexpected_retained_worker_exit_fences_capability_and_reaps(monkeypatch):
    case = worker_case(monkeypatch, mode='exit_profile')
    try:
        _, candidate = retained(case)
        with pytest.raises(Exception):
            candidate.verify_profile_once()
        assert not candidate.active
        assert_reaped(case)
        assert case.rows[0].exit[1] == 19
        assert case.owner.sdk_close_state == 'NOT_ATTEMPTED'
        candidate.close_local()
    finally:
        finish_case(case)


def test_disposal_transfer_race_cannot_publish_a_candidate_owned_by_old_closer(monkeypatch):
    case = worker_case(monkeypatch, mode='block_exchange')
    close_entered, close_release = threading.Event(), threading.Event()
    exchange_thread = close_thread = None
    try:
        case.owner.start('key')
        adapter = module._WorkerAuthenticationHandle(case.owner)
        actual_close = case.owner.close_local
        def delayed_close():
            close_entered.set()
            assert close_release.wait(3)
            actual_close()
        monkeypatch.setattr(case.owner, 'close_local', delayed_close)
        exchange_thread, values, errors = in_thread(lambda: adapter.exchange_once('token', 'secret'))
        assert case.entered.wait(3)
        close_thread, _, close_errors = in_thread(adapter.close_local)
        assert close_entered.wait(1)
        case.release.set(); exchange_thread.join(2)
        assert not exchange_thread.is_alive() and errors and not values
        close_release.set(); close_thread.join(2)
        assert not close_thread.is_alive() and not close_errors
        assert_reaped(case)
    finally:
        close_release.set()
        finish_case(case)
        for thread in (exchange_thread, close_thread):
            if thread is not None:
                thread.join(1)


def test_concurrent_close_cannot_regress_a_reaped_owner_to_pending(monkeypatch):
    case = worker_case(monkeypatch, mode='block_master')
    try:
        _, candidate = retained(case)
        io = case.owner._io_lock
        thread, _, errors = in_thread(candidate.instrument_master_records)
        assert case.entered.wait(3)
        class RacingAcquire:
            def acquire(self, *, blocking):
                assert blocking is False
                # close_local has already fenced the running read. It exits
                # through the actual terminate/reap path while this caller is
                # between its state check and failed lock acquisition.
                thread.join(2)
                assert not thread.is_alive()
                return False
            def release(self):
                io.release()
        monkeypatch.setattr(case.owner, '_io_lock', RacingAcquire())
        candidate.close_local()
        assert errors
        assert_reaped(case)
    finally:
        finish_case(case)


def test_partial_ipc_allocation_is_owned_and_closed_before_startup(monkeypatch):
    case = worker_case(monkeypatch)
    original = module._sdk_socket_pair
    calls = []
    def partial_allocation(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise OSError('isolated second pipe allocation failure')
        return original(*args, **kwargs)
    monkeypatch.setattr(module, '_sdk_socket_pair', partial_allocation)
    try:
        with pytest.raises(OSError):
            case.owner.start('key')
        assert len(case.connections) == 2 and all(
            getattr(c, 'closed', getattr(c, '_closed', False)) for c in case.connections)
        assert not case.rows and not case.owner.start_attempted
        assert case.owner.local_cleanup_state == 'COMPLETE'
        assert not case.deadline.snapshot()['resources_pending']
        assert case.owner not in module._owners
    finally:
        finish_case(case)


@pytest.mark.parametrize('value', [float('nan'), float('inf'), float('-inf'), Decimal('NaN'), Decimal('Infinity')])
def test_nonfinite_sdk_numbers_preserve_normalizer_error_contract(value):
    import math
    result = module._decode(module._parse(module._json_bytes(module._encode(value), module._FRAME_BYTES)))
    assert type(result) is type(value)
    if type(value) is float and math.isnan(value):
        assert math.isnan(result)
    else:
        assert str(result) == str(value)
    # Non-finite values require our explicit data tag. They are never accepted
    # as raw JSON constants or as operation budgets.
    with pytest.raises(ValueError):
        module._parse(b'NaN')
    with pytest.raises(ValueError):
        module._validated_request(dict(v=1, id=1, op='profile', args=module._encode({}),
            seconds=float('nan'), retained=True), 0)


def test_real_worker_retains_existing_malformed_master_diagnostic(monkeypatch):
    from kronos.provider.adapters.kite.authentication import _normalize_instrument_master_records
    from kronos.provider.contracts.instrument_master import ProviderInstrumentMasterError
    case = worker_case(monkeypatch, mode='nonfinite')
    row = _raw_instrument(); row['tick_size'] = float('nan')
    try:
        with pytest.raises(ProviderInstrumentMasterError) as expected:
            _normalize_instrument_master_records([row])
        assert expected.value.diagnostic is not None
        integration = service_case(monkeypatch, case)
        integration.service.complete_callback(integration.attempt)
        capability = integration.service.authenticated_read_only_capability()
        with pytest.raises(ProviderInstrumentMasterError) as actual:
            capability.instrument_master_records()
        assert actual.value.failure == expected.value.failure
        assert actual.value.diagnostic == expected.value.diagnostic
        assert capability.active
        integration.service.end_kronos_session(); assert_reaped(case)
    finally:
        finish_case(case)
