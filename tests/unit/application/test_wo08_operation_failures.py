"""Canonical ordinary-Analysis publication failure taxonomy and retained truth."""
from datetime import datetime, timedelta
import pytest

from kronos.application.intraday_runtime import create_intraday_runtime
from kronos.application.intraday_discovery_operation import DiscoveryOperationState
from kronos.intraday.wo09_persistence import Wo09PublicationConflict
from kronos.intraday.probables_v2 import ProbablesV2Error
from tests.unit.application.test_intraday_discovery_operation import _configured_shared, _request_at
from tests.unit.application.test_wo08_production_rehearsal import BOUNDARY
from tests.unit.provider.test_shared_provider_runtime import _authenticate
from tests.unit.instrument.test_active_derivative_selection import _rows


def runtime(tmp_path):
    now = [BOUNDARY-timedelta(seconds=1)]
    shared, provider, factories, requests = _configured_shared()
    provider.capability.instrument_master_records = lambda:_rows()
    _authenticate(shared)
    composed = create_intraday_runtime(shared, evidence_root=tmp_path/'evidence', clock=lambda:now[0])
    now[0] = BOUNDARY
    return composed, now, shared, requests


@pytest.mark.parametrize('fault,stage,failure', [
    ('inventory','PROBABLES_INVOCATION','PROBABLES_REFRESH_FAILURE'),
    ('wo08_storage','WO08_ASSESSMENT_PUBLICATION','WO08_ASSESSMENT_PUBLICATION_FAILURE'),
    ('wo09_storage','WO09_READINESS_PUBLICATION','WO09_READINESS_PUBLICATION_FAILURE'),
    ('wo09_integrity','WO09_READINESS_PUBLICATION','WO09_READINESS_PUBLICATION_FAILURE'),
    ('wo09_conflict','PUBLICATION_CONFLICT','WO09_PUBLICATION_EXPECTATION_CHANGED'),
])
def test_normal_analysis_failure_does_not_become_analytical_negative(tmp_path,monkeypatch,fault,stage,failure):
    composed, now, shared, calls = runtime(tmp_path)
    error = (Wo09PublicationConflict() if fault == 'wo09_conflict' else
             ProbablesV2Error('PROBABLES_V2_PERSISTENCE_ARTIFACT_INVALID') if fault == 'wo09_integrity' else
             OSError('isolated storage failure'))
    def broken(*args, **kwargs):
        raise error
    if fault == 'inventory':
        from kronos.application import intraday_wo08_shadow
        monkeypatch.setattr(intraday_wo08_shadow,'retained_run_ids',broken)
    elif fault == 'wo08_storage':
        monkeypatch.setattr(composed.wo08_publication,'publish_run',broken)
    else:
        monkeypatch.setattr(composed.wo09_application,'evaluate_wo08',broken)
    request = _request_at('WO08-FAILURE-'+fault,BOUNDARY)
    result = composed.discovery_v2_operation.execute(request)
    assert result.state is DiscoveryOperationState.FAILED
    assert result.stage.value == stage
    assert result.failure.value == failure
    assert result.historical_request_count == calls[0] == 490
    assert shared.active_lease_count == 0
    if fault == 'inventory':
        assert composed.probables_v2_store.load_current_run() is None
        assert composed.wo08_store.current_pointer() is None
        assert result.probables_run_identity is None
    else:
        run = composed.probables_v2_store.load_current_run()
        assert run is not None and len(run.results) == 98
        assert result.probables_run_identity == run.run_identity
        if fault == 'wo08_storage':
            assert composed.wo08_store.current_pointer() is None
        else:
            assert len(composed.wo08_store.current_run()) == 98
    assert composed.wo09_application.restore() == ()
    assert not composed.review_v2_store.root.exists()
    assert not composed.wo09_store.handoffs.exists()
    count = calls[0]
    assert composed.discovery_v2_operation.execute(request) == result
    assert calls[0] == count


def test_later_publication_failure_preserves_prior_pointers_without_current_eligibility(tmp_path,monkeypatch):
    composed, now, shared, calls = runtime(tmp_path)
    first = composed.discovery_v2_operation.execute(_request_at('WO08-FIRST',BOUNDARY))
    assert first.state is DiscoveryOperationState.COMPLETE
    prior_assessments = composed.wo08_store.current_run()
    prior_pointer = (composed.wo08_store.root/'current.json').read_bytes()
    prior_readiness = {path.name:path.read_bytes() for path in composed.wo09_store.current.glob('*.json')}
    def broken(*args,**kwargs):
        raise OSError('isolated later publication failure')
    monkeypatch.setattr(composed.wo08_publication,'publish_run',broken)
    now[0] += timedelta(minutes=5)
    second = composed.discovery_v2_operation.execute(_request_at('WO08-LATER',now[0]))
    assert second.state is DiscoveryOperationState.FAILED
    assert second.failure.value == 'WO08_ASSESSMENT_PUBLICATION_FAILURE'
    assert second.probables_run_identity != first.probables_run_identity
    assert (composed.wo08_store.root/'current.json').read_bytes() == prior_pointer
    assert {path.name:path.read_bytes() for path in composed.wo09_store.current.glob('*.json')} == prior_readiness
    with pytest.raises(ValueError,match='SOURCE_SUPERSEDED'):
        composed.wo09_application.eligibility.capture_wo08(assessment=prior_assessments[0],
            created_at=datetime.fromisoformat(prior_assessments[0].data['created_at']))
    assert shared.active_lease_count == 0 and calls[0] == 980
