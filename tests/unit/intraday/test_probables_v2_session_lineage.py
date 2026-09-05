from __future__ import annotations

from dataclasses import asdict, fields, replace
from datetime import datetime, timedelta
from hashlib import sha256
from zoneinfo import ZoneInfo

import pytest

from kronos.intraday.operational_readiness_composition import (
    WoBCompositionError, adapt_probables_source,
)
from kronos.intraday.probables_v2 import (
    DiscoveryProbablesEvidenceV2, ProbableMemberResultV2, ProbablesRunV2,
    _identity, evaluate_probables_v2_run,
)
from kronos.intraday.probables_v2_diagnostics import (
    ProbablesV2ReplayEnvelope, create_probables_v2_replay_envelope,
    _identity as _envelope_identity,
)
from kronos.intraday.probables_v2_diagnostics_persistence import ProbablesV2DiagnosticsStore
from kronos.intraday.probables_v2_persistence import (
    ProbablesV2Store, create_current_probables_v2_pointer,
)
from kronos.intraday.probables_v2_refresh import map_discovery_execution_to_probables_v2
from kronos.intraday.probables_v2_session_lineage import (
    load_probables_session_envelope, probables_result_session_bound,
)
from kronos.intraday.reconciliation import RECONCILIATION_IDENTITY, RECONCILIATION_VERSION
from kronos.intraday.reconciliation_persistence import IntradayReconciliationStore
from tests.unit.intraday.test_discovery_source import _composition
from tests.unit.intraday.test_probables_v2_refresh_control import _control, _payload


def _reseal(value, **changes):
    """Build validly sealed negative fixtures, not merely invalid checksums."""
    identities = {
        ProbableMemberResultV2: ('result_identity', 'INTRADAY-PROBABLE-V2-RESULT-', 'INTEGRITY-INTRADAY-PROBABLE-V2-RESULT-'),
        ProbablesRunV2: ('run_identity', 'INTRADAY-PROBABLES-V2-RUN-', 'INTEGRITY-INTRADAY-PROBABLES-V2-RUN-'),
        DiscoveryProbablesEvidenceV2: ('mapping_identity', 'INTRADAY-DISCOVERY-PROBABLES-V2-MAPPING-', 'INTEGRITY-INTRADAY-DISCOVERY-PROBABLES-V2-MAPPING-'),
        ProbablesV2ReplayEnvelope: ('envelope_identity', 'INTRADAY-PROBABLES-V2-REPLAY-ENVELOPE-', 'INTEGRITY-INTRADAY-PROBABLES-V2-REPLAY-ENVELOPE-'),
    }
    name, prefix, integrity = identities[type(value)]
    values = {field.name: getattr(value, field.name) for field in fields(value)}
    values.update(changes)
    values.pop(name); values.pop('integrity_identity')
    identity = _envelope_identity if type(value) is ProbablesV2ReplayEnvelope else _identity
    return type(value)(**values, **{name: identity(prefix, values), 'integrity_identity': identity(integrity, values)})


@pytest.fixture(scope='module')
def mixed(tmp_path_factory):
    root = tmp_path_factory.mktemp('wo-b3c-mixed')
    execution, _, _, reads, _ = _composition(
        root, observed_at=datetime(2026, 8, 26, 10, 17, tzinfo=ZoneInfo('Asia/Kolkata')),
        active_mcx=True, retain_mcx=True,
    )
    reconciliation = IntradayReconciliationStore().load(
        publication_identity=RECONCILIATION_IDENTITY, publication_version=RECONCILIATION_VERSION,
    )
    mapping = map_discovery_execution_to_probables_v2(execution=execution, reconciliation=reconciliation)
    source = execution.run
    run = evaluate_probables_v2_run(
        source_discovery_run_identity=source.run_identity,
        universe_identity=source.universe_identity, universe_version=source.universe_version,
        reconciliation_identity=source.reconciliation_identity,
        reconciliation_version=source.reconciliation_version,
        market_session_identity=source.market_session_identity,
        analysis_boundary=source.observation_boundary,
        member_evidence=mapping.member_evidence, unavailable_members=mapping.unavailable_members,
        provenance=('WO-B3C-ISOLATED-TEST',),
    )
    envelope = create_probables_v2_replay_envelope(
        request_identity='WO-B3C-TEST', operation_identity='WO-B3C-TEST',
        execution=execution, reconciliation=reconciliation, created_at=source.observation_boundary,
    )
    return run, {item.mapping_identity: item for item in mapping.member_evidence}, envelope, reads


def _args(mixed):
    run, mappings, envelope, _ = mixed
    result = next(item for item in run.results if item.source_mapping_identity in mappings)
    return dict(run=run, result=result, mapping=mappings[result.source_mapping_identity], envelope=envelope)


def _adapt(args, **changes):
    values = dict(
        run=args['run'], result=args['result'], current_pointer=create_current_probables_v2_pointer(args['run']),
        canonical_instrument_identity=args['result'].canonical_subject_identity,
        active_contract_identity=None,
        source_mapping=args['mapping'], replay_envelope=args['envelope'],
    )
    values.update(changes)
    return adapt_probables_source(**values)


def test_mixed_nse_mcx_exact_constituents_survive_round_trip_without_reads(mixed, tmp_path):
    run, mappings, envelope, reads = mixed
    before = len(reads)
    store = ProbablesV2DiagnosticsStore(tmp_path.resolve())
    path = store.retain_envelope(envelope)
    digest = sha256(path.read_bytes()).hexdigest()
    restored = store.load_envelope(envelope.envelope_identity)
    accepted = []
    for result in run.results:
        if result.source_mapping_identity not in mappings:
            continue
        assert result.market_session_identity != run.market_session_identity
        assert probables_result_session_bound(run=run, result=result, mapping=mappings[result.source_mapping_identity], envelope=restored)
        accepted.append(result.canonical_subject_identity)
    assert any(item.startswith('NSE-') for item in accepted)
    assert any(item.startswith('MCX-') for item in accepted)
    assert len(reads) == before
    assert sha256(path.read_bytes()).hexdigest() == digest


def test_adapter_accepts_exact_session_binding_and_preserves_result(mixed):
    args = _args(mixed)
    before = asdict(args['run'])
    anchor, source = _adapt(args)
    assert anchor.candidate_identity == args['result'].result_identity
    assert source.reference.exact_source_state == args['result'].state.value
    assert asdict(args['run']) == before


@pytest.mark.parametrize('foreign', ['FOREIGN-SESSION', 'OTHER-SAME-DATE-SESSION', 'OTHER-SAME-CLOCK-SESSION', 'OTHER-SAME-EXCHANGE-SESSION', 'another-member'])
def test_sealed_foreign_session_rejected_even_when_mapping_result_and_run_agree(mixed, foreign):
    args = _args(mixed)
    if foreign == 'another-member':
        foreign = next(item.market_session_identity for item in args['run'].results if item.market_session_identity != args['result'].market_session_identity)
    mapping = _reseal(args['mapping'], market_session_identity=foreign)
    result = _reseal(args['result'], market_session_identity=foreign, source_mapping_identity=mapping.mapping_identity)
    run = _reseal(args['run'], results=tuple(result if item == args['result'] else item for item in args['run'].results))
    with pytest.raises(WoBCompositionError, match='WO_B_PROBABLES_CURRENT_BINDING_MISMATCH'):
        _adapt(dict(args, mapping=mapping, result=result, run=run))


@pytest.mark.parametrize('change', ['omitted', 'reordered', 'foreign-run', 'tampered'])
def test_aggregate_lineage_fails_closed(mixed, change):
    args = _args(mixed)
    envelope = args['envelope']
    if change == 'omitted':
        envelope = _reseal(envelope, probables_v2_facts=envelope.probables_v2_facts[1:])
    elif change == 'reordered':
        # Reordering the unordered fact container is harmless; canonical order
        # belongs to reconciliation, so it must still pass.
        envelope = _reseal(envelope, probables_v2_facts=tuple(reversed(envelope.probables_v2_facts)))
        assert probables_result_session_bound(**dict(args, envelope=envelope))
        return
    elif change == 'foreign-run':
        run = _reseal(args['run'], market_session_identity='UNRELATED-AGGREGATE')
        args['run'] = run
    else:
        envelope = replace(envelope)
        object.__setattr__(envelope, 'integrity_identity', 'TAMPERED')
    assert not probables_result_session_bound(**dict(args, envelope=envelope))


@pytest.mark.parametrize('field,value', [('canonical_subject_identity', 'NSE-EQ-FOREIGN'), ('source_discovery_member_identity', 'FOREIGN-DISCOVERY-MEMBER')])
def test_sealed_foreign_candidate_binding_rejected(mixed, field, value):
    args = _args(mixed)
    result = _reseal(args['result'], **{field: value})
    run = _reseal(args['run'], results=tuple(result if item == args['result'] else item for item in args['run'].results))
    assert not probables_result_session_bound(**dict(args, run=run, result=result))


def test_wrong_current_run_pointer_rejected(mixed):
    args = _args(mixed)
    foreign = _reseal(args['run'], provenance=('FOREIGN-RUN',))
    with pytest.raises(WoBCompositionError, match='WO_B_PROBABLES_CURRENT_BINDING_MISMATCH'):
        _adapt(args, current_pointer=create_current_probables_v2_pointer(foreign))


def test_wrong_boundary_rejected_with_valid_run_and_result_seals(mixed):
    args = _args(mixed)
    boundary = args['run'].analysis_boundary + timedelta(minutes=1)
    results = tuple(_reseal(item, analysis_boundary=boundary) for item in args['run'].results)
    run = _reseal(args['run'], analysis_boundary=boundary, results=results)
    result = next(item for item in results if item.universe_member_identity == args['result'].universe_member_identity)
    assert not probables_result_session_bound(**dict(args, run=run, result=result))


def test_missing_proof_cannot_admit_aggregate_result(mixed):
    with pytest.raises(WoBCompositionError, match='WO_B_PROBABLES_CURRENT_BINDING_MISMATCH'):
        _adapt(_args(mixed), source_mapping=None, replay_envelope=None)


def test_exact_provenance_loader_and_runtime_loader_are_read_only(tmp_path):
    _, composition, control, _, reads = _control(tmp_path)
    outcome = control.execute_document(_payload('WO-B3C-LOADER'))
    assert outcome['outcome'] == 'SUCCESS'
    store = ProbablesV2Store(tmp_path.resolve())
    run = store.load_current_run()
    before = {path: sha256(path.read_bytes()).hexdigest() for path in tmp_path.rglob('*') if path.is_file()}
    count = reads[0]
    envelope = load_probables_session_envelope(tmp_path.resolve(), run)
    assert envelope.envelope_identity == outcome['replay_envelope_identity']
    requests = composition.wo_b_runtime._loader.current_requests(run.analysis_boundary)
    assert len(requests) == run.diagnostics.total_probables
    assert reads == [count]
    assert {path: sha256(path.read_bytes()).hexdigest() for path in tmp_path.rglob('*') if path.is_file()} == before


def test_missing_provenance_fails_closed(mixed, tmp_path):
    with pytest.raises(ValueError, match='PROBABLES_V2_SESSION_LINEAGE_UNAVAILABLE'):
        load_probables_session_envelope(tmp_path.resolve(), mixed[0])


def test_foreign_discovery_run_with_consistent_resealed_probables_is_rejected(mixed):
    args = _args(mixed)
    identity = 'FOREIGN-DISCOVERY-RUN'
    mapping = _reseal(args['mapping'], source_discovery_run_identity=identity)
    results = tuple(_reseal(item, source_discovery_run_identity=identity,
        **({'source_mapping_identity': mapping.mapping_identity} if item == args['result'] else {}))
        for item in args['run'].results)
    run = _reseal(args['run'], source_discovery_run_identity=identity, results=results)
    result = next(item for item in results if item.universe_member_identity == args['result'].universe_member_identity)
    assert not probables_result_session_bound(**dict(args, run=run, result=result, mapping=mapping))


def test_unrelated_session_schedule_with_identical_date_clock_exchange_has_no_authority(mixed):
    args = _args(mixed)
    fact = next(item for item in args['envelope'].probables_v2_facts if item.universe_member_identity == args['result'].universe_member_identity)
    original = fact.current_schedule
    unrelated = replace(original, session_id='UNRELATED-AUTHORITATIVE-SESSION')
    assert unrelated.trading_date == original.trading_date
    assert unrelated.windows == original.windows
    assert unrelated.exchange == original.exchange
    mapping = _reseal(args['mapping'], market_session_identity=unrelated.session_id)
    result = _reseal(args['result'], market_session_identity=unrelated.session_id, source_mapping_identity=mapping.mapping_identity)
    run = _reseal(args['run'], results=tuple(result if item == args['result'] else item for item in args['run'].results))
    assert not probables_result_session_bound(**dict(args, run=run, result=result, mapping=mapping))


@pytest.mark.parametrize("proof", ["missing", "unrelated"])
def test_run_aggregate_cannot_substitute_for_constituent(mixed, proof):
    """WO-B3D: permanent reproduction of the local-publication-gate bypass."""
    args = _args(mixed)
    aggregate = args["run"].market_session_identity
    assert all(f.current_schedule.session_id != aggregate for f in args["envelope"].probables_v2_facts)
    result = _reseal(args["result"], market_session_identity=aggregate)
    run = _reseal(args["run"], results=tuple(
        result if item == args["result"] else item for item in args["run"].results
    ))
    supplied = {} if proof == "unrelated" else dict(source_mapping=None, replay_envelope=None)
    with pytest.raises(WoBCompositionError, match="WO_B_PROBABLES_CURRENT_BINDING_MISMATCH"):
        _adapt(dict(args, run=run, result=result), **supplied)


@pytest.mark.parametrize("missing", ["source_mapping", "replay_envelope"])
def test_each_required_proof_artifact_must_be_present(mixed, missing):
    with pytest.raises(WoBCompositionError, match="WO_B_PROBABLES_CURRENT_BINDING_MISMATCH"):
        _adapt(_args(mixed), **{missing: None})


def test_missing_exact_member_in_sealed_replay_fails_closed(mixed):
    args = _args(mixed)
    envelope = _reseal(args["envelope"], probables_v2_facts=tuple(
        f for f in args["envelope"].probables_v2_facts
        if f.universe_member_identity != args["result"].universe_member_identity
    ))
    with pytest.raises(WoBCompositionError, match="WO_B_PROBABLES_CURRENT_BINDING_MISMATCH"):
        _adapt(dict(args, envelope=envelope))


@pytest.mark.parametrize("family", ["NSE", "MCX"])
def test_exact_nse_and_mcx_constituents_pass_adapter(mixed, family):
    run, mappings, envelope, reads = mixed
    count = len(reads)
    result = next(r for r in run.results
        if r.canonical_subject_identity.startswith(family + "-")
        and r.source_mapping_identity in mappings)
    args = dict(run=run, result=result, mapping=mappings[result.source_mapping_identity], envelope=envelope)
    instrument = result.canonical_subject_identity
    contract = None
    if family == "MCX":
        from tests.unit.instrument.test_active_derivative_selection import _resolve
        binding = _resolve(run.analysis_boundary).for_subject(result.canonical_subject_identity).binding
        instrument = binding.provider_symbol
        contract = binding.active_binding.derivative_contract_id
    anchor, source = _adapt(args, canonical_instrument_identity=instrument, active_contract_identity=contract)
    assert anchor.candidate_identity == result.result_identity
    assert source.reference.exact_source_state == result.state.value
    assert len(reads) == count


def test_equal_sessions_do_not_establish_a_non_aggregate_v2_contract():
    from tests.unit.intraday.test_probables_v2 import _opening_inputs, _run
    mapping = _opening_inputs()[-1]
    run = _run(mapping)
    result = run.results[0]
    assert result.market_session_identity == run.market_session_identity
    with pytest.raises(WoBCompositionError, match="WO_B_PROBABLES_CURRENT_BINDING_MISMATCH"):
        _adapt(dict(run=run, result=result, mapping=mapping, envelope=None))


def test_loader_requires_proof_even_when_all_admitted_sessions_equal_aggregate(mixed, tmp_path, monkeypatch):
    from kronos.application import intraday_operational_readiness as application
    from tests.unit.intraday.test_probables_v2 import _opening_inputs, _run
    original = _run(_opening_inputs()[-1])
    assert original.diagnostics.total_probables > 0
    aggregate = mixed[0].market_session_identity
    results = tuple(_reseal(r, market_session_identity=aggregate) for r in original.results)
    run = _reseal(original, market_session_identity=aggregate, results=results)
    calls = []

    class Store:
        root = tmp_path.resolve()
        def load_current(self):
            return create_current_probables_v2_pointer(run)
        def load_current_run(self):
            return run

    def unavailable(root, value):
        calls.append((root, value.run_identity))
        raise ValueError("PROBABLES_V2_SESSION_LINEAGE_UNAVAILABLE")

    monkeypatch.setattr(application, "load_probables_session_envelope", unavailable)
    loader = application.PersistedWoBRequestLoader(
        probables=Store(), catalogue=None, active_derivatives=None, calendar=None,
        wo12=None, wo13=None, wo14=None, wo15=None, wo16=None, wo17=None,
    )
    with pytest.raises(WoBCompositionError, match="WO_B_PROBABLES_CURRENT_BINDING_MISMATCH"):
        loader.current_requests(run.analysis_boundary)
    assert calls == [(tmp_path.resolve(), run.run_identity)]
