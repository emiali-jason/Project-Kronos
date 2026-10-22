"""Admission closure: dedicated Review routes reject stale retained authority."""
from urllib.parse import urlencode

import pytest

from tests.unit.browser.test_browser_server import _request
from tests.unit.browser.test_swing_local_analysis import (
    _admission_rig, _admit_successor, _serving, _post, _originals, _inventory,
)


@pytest.mark.parametrize('path', ['/swing/nse-review', '/swing/mcx-review'])
@pytest.mark.parametrize('fault', ['successor', 'publication', 'navigation'])
def test_dedicated_review_cannot_promote_historical_authority(tmp_path, monkeypatch, path, fault):
    rig = _admission_rig(tmp_path)
    with _serving(rig) as server:
        assert _post(server, rig)[0] == 303
        original, = _originals(rig)
        before = _inventory(rig.research.store.root)
        intake_before = _inventory(rig.intake.store.root)
        review_before = server.native_review.snapshot()
        if fault == 'successor':
            _admit_successor(rig)
        elif fault == 'publication':
            rig.state['manifest'] = 'f' * 64
        else:
            path += '?' + urlencode(dict(run='SWING-RUN-' + 'B' * 32,
                                        candidate=rig.requirement.requirement_sha256))
        def forbidden(*a, **k):
            pytest.fail('GET attempted acquisition, new analysis or evidence write')
        monkeypatch.setattr(rig.application, 'run_analysis', forbidden)
        monkeypatch.setattr(rig.application, 'authenticated_read_only_capability', forbidden)
        monkeypatch.setattr(rig.research.store, 'retain', forbidden)
        monkeypatch.setattr(rig.intake.store, '_immutable', forbidden)
        monkeypatch.setattr(rig.intake.store, '_replace_pointer', forbidden)
        for _ in range(2):
            status, _, body = _request(server, 'GET', path)
            assert status == 409
            assert 'REVIEW_BINDING_STALE' in body
            assert original.identity not in body
            assert 'BINDING CURRENT' not in body
            assert '<h4>SUPPORT' not in body
            assert 'ANSWER ACCEPTED' not in body
        assert server.native_review.snapshot() == review_before
        assert _originals(rig) == (original,)
        assert _inventory(rig.research.store.root) == before
        assert _inventory(rig.intake.store.root) == intake_before
