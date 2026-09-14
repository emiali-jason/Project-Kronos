from dataclasses import replace
from datetime import timedelta
import inspect
from types import SimpleNamespace

import pytest

from kronos.application.swing_opportunities import prepare_swing_opportunity_contribution
from kronos.swing.v1 import opportunity_continuity as c
from tests.unit.swing.v1.test_opportunity_continuity import scenario, commit, later, row
from tests.unit.application.test_swing_mtf_facts import _instrument


def test_C01_C09_prepared_application_handoff_no_publication(scenario, tmp_path):
    snapshot, bindings = scenario
    dataset = SimpleNamespace(records=tuple(SimpleNamespace(canonical_identity=b.canonical_instrument,
        _analysis_instrument=_instrument(b.canonical_instrument, b.exchange)) for b in bindings))
    completed_at = snapshot.observed_at + timedelta(seconds=20)
    prepared = prepare_swing_opportunity_contribution(snapshot, dataset, successful_completed_at=completed_at)
    assert row(prepared).first_admitted == completed_at
    assert row(prepared).last_analysis_checked == completed_at
    assert list(tmp_path.iterdir()) == []
    committed = commit(prepared, snapshot)
    assert committed.successful_completed_at == completed_at
    # WO-05 now invokes the pure seam only inside prepared publication.
    from kronos.application.swing_opportunities import build_completed_swing_analysis, SwingOpportunitiesApplication
    assert 'if prepare_publication:' in inspect.getsource(build_completed_swing_analysis)
    assert 'prepare_swing_opportunity_contribution' in inspect.getsource(build_completed_swing_analysis)
    assert 'prepare_swing_opportunity_contribution' not in inspect.getsource(SwingOpportunitiesApplication)


def test_C08_C09_C10_exact_bundle_binding_and_restart(scenario, tmp_path):
    snapshot, bindings = scenario
    prepared = c.prepare_continuity(snapshot, bindings)
    store = c.ContinuityEvidenceStore(tmp_path)
    store.retain_prepared(prepared)
    restored = c.ContinuityEvidenceStore(tmp_path).load_prepared(snapshot.run_identity)
    committed = commit(restored, snapshot)
    current = later(snapshot)
    next_bundle = c.prepare_continuity(current, bindings, predecessor=committed)
    assert row(next_bundle).opportunity_id == row(prepared).opportunity_id
    assert next_bundle.native_run.run_identity != prepared.native_run.run_identity
    assert next_bundle.native_run.result_sha256 != prepared.native_run.result_sha256
    with pytest.raises(ValueError, match='COMMITTED_BINDING'):
        commit(prepared, replace(snapshot, run_identity=current.run_identity))
    with pytest.raises(ValueError, match='REQUEST_INVALID'):
        c.prepare_continuity(current, bindings, predecessor=prepared)


def test_C14_continuity_has_no_shared_authority_inputs():
    source = inspect.getsource(c)
    for forbidden in ('kronos.intraday', 'kronos.market', 'kronos.provider.runtime',
                      'requests.', 'urlopen', 'subprocess', 'sqlite', 'research_epoch'):
        assert forbidden not in source
    assert 'latest' not in c.ContinuityEvidenceStore.__dict__
    assert 'current' not in c.ContinuityEvidenceStore.__dict__
