from dataclasses import replace
import http.client as http_client
from http.server import BaseHTTPRequestHandler, HTTPServer
import socket
from threading import Thread
import os
from pathlib import Path

import pytest

from tools import kronos_legacy_bootstrap as tool
from tests.unit.common.test_legacy_bootstrap import binding, snapshot, coordinator, consume
from kronos.common.legacy_bootstrap import BootstrapError


def documents():
    b=binding()
    runtime={'loaded_commit_revision':b.revision,'manifest_identity':b.runtime,'configuration_identity':b.configuration,
        'startup':dict(process_id=b.pid,startup_boundary_at=b.startup,source_state='CLEAN_COMMIT')}
    return {'/status':dict(service='KRONOS_BROWSER_V1',provider='CONNECTED',analysis='READY',live_monitoring='NOT TESTED'),
        tool.V1:dict(active_operation_identity=None),tool.V2:dict(active_operation_identity=None,runtime_identity=runtime),
        tool.HISTORY:dict(active_operation_identity=None),tool.MASTER:dict(context_availability='ACTIVE')}


def observe(monkeypatch, docs):
    monkeypatch.setattr(tool,'repository_gate',lambda b:None)
    monkeypatch.setattr(tool,'read_control',lambda *a:'do-not-retain')
    monkeypatch.setattr(tool,'digest',lambda p:'d'*64)
    return tool.snapshot(binding(),Path('/control'),Path('/package'),get=docs.__getitem__,listeners=lambda:(39393,))


def test_legacy_projection_uses_actual_frozen_identity_and_preserves_unknown(monkeypatch):
    s=observe(monkeypatch,documents());s.check(binding())
    assert s.binding==binding() and s.monitoring_inflight is None
    assert s.provider_task_inflight is None and s.browser_control_inflight is None


@pytest.mark.parametrize('route,key,value', [('/status','provider','CONNECTING'),('/status','analysis','RUNNING'),
    (tool.V1,'active_operation_identity','op'),(tool.V2,'active_operation_identity','op'),
    (tool.HISTORY,'active_operation_identity','op'),('/status','live_monitoring','TESTING')])
def test_known_inflight_operations_prevent_shutdown(monkeypatch,route,key,value):
    d=documents();d[route][key]=value
    with pytest.raises(BootstrapError):observe(monkeypatch,d).check(binding())


@pytest.mark.parametrize('state', ['INVENTED', None])
def test_unrecognized_status_rejected(monkeypatch,state):
    d=documents();d['/status']['provider']=state
    with pytest.raises(BootstrapError):observe(monkeypatch,d)


def test_replacement_environment_carries_no_provider_or_legacy_authority(monkeypatch):
    from kronos.common.legacy_bootstrap import Ticket
    for key in ('KRONOS_KITE_ACCESS_TOKEN','KRONOS_KITE_API_SECRET','KRONOS_MAINTENANCE_PROOF',
        'PYTHONPATH','PYTHONSTARTUP','DYLD_INSERT_LIBRARIES','AUTHORIZATION'):
        monkeypatch.setenv(key,'must-not-copy')
    env=tool.replacement_environment(Ticket('a'*64,'b'*64))
    assert 'must-not-copy' not in env.values()
    assert set(env)<= {'HOME','USER','LOGNAME','TMPDIR','LANG','PATH','KRONOS_LAUNCH_MODE',
                      'KRONOS_LEGACY_BOOTSTRAP_ID','KRONOS_LEGACY_BOOTSTRAP_PROOF'}


def test_complete_coordinator_orders_preparation_shutdown_consumption_guard_stop(tmp_path,monkeypatch):
    monkeypatch.setattr(tool,'safe_path',lambda path:path)
    c=coordinator(tmp_path);events=[]
    monkeypatch.setattr(tool,'verify',lambda *a:events.append('package-verified'))
    def observe_():events.append('observe');return snapshot()
    def shutdown():
        assert (c.root/'prepared.json').exists() and (c.root/'shutdown-authorized.json').exists()
        events.append('shutdown')
    def launch(env):
        from kronos.common.legacy_bootstrap import Ticket, ENV_ID, ENV_PROOF
        assert (c.root/'stopped.json').exists()
        consume(c,Ticket(env[ENV_ID],env[ENV_PROOF]));events.append('guarded-start')
    def accept(t):events.append('verify-guard');return {'pid':999999}
    r=tool.migrate(binding(),Path('/Applications/KRONOS.app'),'a'*64,'SPONSOR_AUTH',observe=observe_,shutdown=shutdown,
        launch=launch,accept=accept,alive=lambda pid:False,free=lambda:True,coordinator=c)
    assert events==['package-verified','observe','observe','shutdown','package-verified','guarded-start','verify-guard']
    assert r['bootstrap']=='PERMANENTLY_CONSUMED' and r['end_maintenance']=='NOT_INVOKED'
    assert r['evidence_inertness']=='REQUIRES_SEPARATE_BEFORE_AFTER_INVENTORY'


def test_preparation_failure_never_shutdown_or_launch(tmp_path,monkeypatch):
    monkeypatch.setattr(tool,'safe_path',lambda path:path)
    monkeypatch.setattr(tool,'verify',lambda *a:None);calls=[]
    with pytest.raises(BootstrapError):
        tool.migrate(binding(),Path('/Applications/KRONOS.app'),'a'*64,'AUTH',observe=lambda:replace(snapshot(),authentication_inflight=True),
            shutdown=lambda:calls.append('stop'),launch=lambda e:calls.append('start'),coordinator=coordinator(tmp_path))
    assert calls==[]


def test_stop_timeout_does_not_kill_or_retry(tmp_path,monkeypatch):
    monkeypatch.setattr(tool,'safe_path',lambda path:path)
    monkeypatch.setattr(tool,'verify',lambda *a:None);calls=[]
    with pytest.raises(BootstrapError,match='TIMEOUT'):
        tool.migrate(binding(),Path('/Applications/KRONOS.app'),'a'*64,'AUTH',observe=snapshot,shutdown=lambda:calls.append('stop'),
            launch=lambda e:calls.append('start'),alive=lambda pid:True,free=lambda:False,
            sleep=lambda t:None,coordinator=coordinator(tmp_path))
    assert calls==['stop']


def test_guard_acceptance_requires_current_clean_inactive_runtime():
    from kronos.common.legacy_bootstrap import Ticket
    b=binding();t=Ticket('a'*64,'b'*64);d=documents()
    d['/status'].update(provider='DISCONNECTED',maintenance=dict(protocol='KRONOS_MAINTENANCE_HANDOFF_V1',active=True,generation=t.identity))
    d[tool.V2]['runtime_identity']['startup'].update(process_id=999999)
    d[tool.V2]['runtime_identity']['loaded_commit_revision']=b.replacement_revision
    d[tool.V1]['operation_available']=False;d[tool.V2]['operation_available']=False
    d[tool.V2]['live_shadow']={'enabled':False}
    assert tool.verify_replacement(b,t,get=d.__getitem__,listeners=lambda:(999999,))['provider']=='DISCONNECTED'
    d['/status']['provider']='CONNECTED'
    with pytest.raises(BootstrapError):tool.verify_replacement(b,t,get=d.__getitem__,listeners=lambda:(999999,))


def test_migration_requires_approved_package_hash_before_inspection(tmp_path,monkeypatch):
    calls=[];monkeypatch.setattr(tool,'verify',lambda *a:calls.append(1))
    with pytest.raises(BootstrapError,match='APPROVED_PACKAGE_IDENTITY'):
        tool.migrate(binding(),tmp_path,None,'AUTH')
    assert calls==[]


@pytest.mark.parametrize('address',['*:8947','0.0.0.0:8947','[::1]:8947','127.0.0.1:8948'])
def test_exact_listener_address_required_even_when_pid_matches(address):
    with pytest.raises(BootstrapError,match='LISTENER_ADDRESS'):
        tool.listener_owners('p39393\nn'+address+'\n')


def test_exact_listener_address_and_duplicate_ownership_retained():
    assert tool.listener_owners('p39393\nf8\nn127.0.0.1:8947\n')==(39393,)
    assert tool.listener_owners('p39393\nn127.0.0.1:8947\np39394\nn127.0.0.1:8947\n')==(39393,39394)


@pytest.fixture
def local_http_wrapper(monkeypatch):
    """Redirect only the wrapper's fixed endpoint; use real stdlib HTTP/socket I/O."""
    requests, connections, destinations = [], [], []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append((self.command, self.path))
            if self.path == '/bad-http':
                self.wfile.write(b'not-an-http-response\r\n\r\n')
                return
            code, body = {
                '/status': (200, b'{"service":"ISOLATED_FAKE"}'),
                '/wrong-status': (503, b'{"secret":"must-not-escape"}'),
                '/redirect': (302, b'{}'),
                '/bad-json': (200, b'not-json: must-not-escape'),
                '/oversized': (200, b' ' * 2_000_001),
            }[self.path]
            self.send_response(code)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            requests.append((self.command, self.path))
            self.send_response(202)
            self.end_headers()
            self.wfile.write(b'{"status":"ISOLATED_ACCEPTED"}')

        def log_message(self, *args):
            pass

    server = HTTPServer(('127.0.0.1', 0), Handler)
    assert server.server_port != 8947
    target = ('127.0.0.1', server.server_port)
    real_connect = socket.create_connection
    real_connection = http_client.HTTPConnection

    def only_isolated_socket(address, *args, **kwargs):
        assert address == target  # Reject production port and all external hosts.
        destinations.append(address)
        return real_connect(address, *args, **kwargs)

    def redirected_connection(host, port, *, timeout):
        assert (host, port, timeout) == ('127.0.0.1', 8947, 5)
        connection = real_connection(*target, timeout=timeout)
        connections.append(connection)
        return connection

    monkeypatch.setattr(socket, 'create_connection', only_isolated_socket)
    monkeypatch.setattr(http_client, 'HTTPConnection', redirected_connection)
    thread = Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
    thread.start()
    try:
        yield requests, connections, destinations
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()
        assert all(c.sock is None for c in connections)


@pytest.mark.parametrize('method,route,expected', [
    ('GET', '/status', {'service': 'ISOLATED_FAKE'}),
    ('POST', '/isolated-control', {'status': 'ISOLATED_ACCEPTED'}),
])
def test_real_http_wrapper_success(local_http_wrapper, method, route, expected):
    requests, connections, destinations = local_http_wrapper
    assert tool.http(method, route) == expected
    assert requests == [(method, route)]
    assert len(connections) == len(destinations) == 1
    assert connections[0].timeout == 5


@pytest.mark.parametrize('route', [
    '/wrong-status', '/redirect', '/bad-json', '/bad-http', '/oversized',
])
def test_real_http_wrapper_rejects_invalid_responses(local_http_wrapper, route):
    with pytest.raises(BootstrapError, match='^BOOTSTRAP_HTTP_REJECTED$'):
        tool.http('GET', route)
    assert local_http_wrapper[0] == [('GET', route)]  # No redirect or retry.


@pytest.mark.parametrize('failure', [ConnectionRefusedError, TimeoutError])
def test_real_http_wrapper_connection_failure_and_timeout(local_http_wrapper, monkeypatch, failure):
    destinations = []

    def fail_connect(address, timeout, *args, **kwargs):
        assert address[0] == '127.0.0.1' and address[1] != 8947
        assert timeout == 5
        destinations.append(address)
        raise failure('must-not-escape')

    monkeypatch.setattr(socket, 'create_connection', fail_connect)
    with pytest.raises(BootstrapError, match='^BOOTSTRAP_HTTP_REJECTED$'):
        tool.http('GET', '/status')
    assert len(destinations) == 1
    assert local_http_wrapper[0] == []


@pytest.mark.parametrize('name', ['repository', 'output', 'rollback', 'installer'])
def test_noncanonical_migration_rejected_before_package_or_shutdown(tmp_path, monkeypatch, name):
    calls = []
    monkeypatch.setattr(tool, 'verify', lambda *a: calls.append('verify'))
    with pytest.raises(BootstrapError, match='NONCANONICAL_LAUNCHER'):
        tool.migrate(binding(), tmp_path / name / 'KRONOS.app', 'a'*64, 'AUTH',
                     observe=lambda: calls.append('observe'),
                     shutdown=lambda: calls.append('shutdown'), launch=lambda e: calls.append('launch'))
    assert calls == []
