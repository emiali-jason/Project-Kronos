"""Actual Browser intake boundary; fake Provider, isolated canonical owners."""
from http import HTTPStatus
from io import BytesIO
from types import MethodType, SimpleNamespace
from urllib.parse import urlencode
import pytest

from kronos.browser.server import _BrowserHandler
from kronos.browser.views import render_mcx_v1_workspace
from tests.unit.application.test_swing_mcx_observation import setup
from tests.unit.application.test_swing_mcx_v1_composition import compose, inventory


def handler(server, fields, *, origin=True):
    body = fields if isinstance(fields, bytes) else urlencode(fields).encode('ascii')
    authority = '127.0.0.1:' + str(server.server_port)
    replies = []
    h = SimpleNamespace(server=server, path='/swing/mcx-v1/observe',
        headers={'Host': authority, 'Origin': 'http://' + authority if origin else 'https://wrong',
                 'Content-Type': 'application/x-www-form-urlencoded', 'Content-Length': str(len(body))},
        rfile=BytesIO(body), _json=lambda value: replies.append((HTTPStatus.OK, value)),
        _text=lambda status, text: replies.append((status, text)))
    for name in ('_same_origin', '_exact_loopback_host', '_dispatch_post', '_mcx_observe'):
        setattr(h, name, MethodType(getattr(_BrowserHandler, name), h))
    return h, replies


def test_canonical_browser_observation_bypasses_analysis_and_preserves_every_other_store(tmp_path, monkeypatch):
    server, _, _ = compose(tmp_path / 'browser')
    f = setup(tmp_path / 'fixture')
    server.mcx_v1_composition.observation = f.owner
    # Bind the same canonical maintenance owner used by Browser POST.
    f.owner.admission = server.maintenance_admission
    f.hub = server.swing_monitoring_hub
    f.owner.hub = f.hub
    monkeypatch.setattr(server.application, 'reconcile_committed_analysis',
                        lambda: pytest.fail('Observation must not reconcile analysis'))
    before = inventory(tmp_path / 'browser')
    try:
        h, replies = handler(server, {**f.args, 'family': f.args['family'].value})
        _BrowserHandler.do_POST(h)
        assert replies[0][0] == HTTPStatus.OK
        assert replies[0][1]['record']['state'] == 'OBSERVED'
        assert server.maintenance_admission.snapshot()['owners'] == {}
        assert server._active_sponsor_work == 0
        after = inventory(tmp_path / 'browser')
        baseline = 'review/ux10-notifications-v1/context/connection-baselines.json'
        assert set(after) - set(before) == {baseline}
        assert {key: after[key] for key in before} == before
        assert server.ux10_notifications._connection_state['SHARED-SWING-MONITORING']['state'] == 'CONNECTED'
        assert replies[0][1]['record']['cleanup']['hub']['owner_count'] == 0
        # The existing shared connection listener retains its factual baseline;
        # it is not a position or proof of a presently attached stream.
        # Receipt reads, including unavailable and ambiguous queries, are pure.
        h.path = '/swing/mcx-v1/observation?operation=' + f.args['operation']
        receipt_before = inventory(f.owner.root)
        _BrowserHandler._mcx_observation_receipt(h)
        assert replies[-1][1] == replies[0][1]
        for query in ('operation=' + '2'*32, 'operation=a&operation=b', 'extra=value'):
            h.path = '/swing/mcx-v1/observation?' + query
            _BrowserHandler._mcx_observation_receipt(h)
            assert replies[-1][0] == HTTPStatus.CONFLICT
        assert inventory(f.owner.root) == receipt_before
        assert f.cap.calls == ['records', 'assertions', 'session']
    finally: server.server_close()


@pytest.mark.parametrize('invalid', ['extra', 'duplicate', 'empty', 'unknown-family', 'origin', 'fenced'])
def test_malformed_direct_or_fenced_post_never_reaches_observation_owner(tmp_path, invalid):
    server, _, _ = compose(tmp_path)
    f = setup(tmp_path / 'fixture'); calls = []
    server.mcx_v1_composition.observation = SimpleNamespace(observe=lambda **kw: calls.append(kw))
    fields = {**f.args, 'family': f.args['family'].value}
    if invalid == 'extra': fields['unexpected'] = 'value'
    if invalid == 'empty': fields['run'] = ''
    if invalid == 'unknown-family': fields['family'] = 'WRONG'
    if invalid == 'duplicate': fields = urlencode(fields).encode() + b'&run=OTHER'
    if invalid == 'fenced': assert server.maintenance_admission.claim('a'*64)
    before = inventory(tmp_path)
    try:
        h, replies = handler(server, fields, origin=invalid != 'origin')
        _BrowserHandler.do_POST(h)
        expected = HTTPStatus.FORBIDDEN if invalid == 'origin' else HTTPStatus.SERVICE_UNAVAILABLE if invalid == 'fenced' else HTTPStatus.CONFLICT
        assert replies[0][0] == expected and calls == []
        assert not f.cap.calls and inventory(tmp_path) == before
        assert server.maintenance_admission.snapshot()['owners'] == {}
    finally: server.server_close()


def test_observation_control_requires_current_projection_and_capability_without_get_side_effects():
    projection = dict(run='RUN', current=True, reserved=False, error=None,
        publication_sha256='b'*64, capability_active=True, preparations=(), plans=(), positions=(),
        observation_targets=(('CRUDEOIL', 'CRUDEOIL26OCTFUT', '2026-10-19', 'a'*64),))
    page = render_mcx_v1_workspace(projection, ())
    assert '/swing/mcx-v1/observe' in page and 'CRUDEOIL26OCTFUT (2026-10-19)' in page
    assert 'no position' in page and 'name="operation"' in page
    for change in (dict(current=False), dict(capability_active=False), dict(observation_targets=())):
        assert '/swing/mcx-v1/observe' not in render_mcx_v1_workspace({**projection, **change}, ())
