"""WO-06A policy truth table and pre-change byte-for-byte replay fixtures."""

from dataclasses import replace
from datetime import datetime, time
from decimal import Decimal
from hashlib import sha256
from itertools import product
import json
from pathlib import Path

import pytest

from kronos.application.intraday_probables_v2 import IntradayProbablesV2Application
from kronos.intraday.completed_evidence import (
    CompletedEvidenceError,
    build_completed_evidence_selection,
)
from kronos.intraday.contracts import IntradayTimeframe as TF
from kronos.intraday.nifty_relative_context import (
    NIFTY_CANONICAL_IDENTITY,
    NiftyApplicability,
    NiftyRelationship,
    build_nifty_relative_context,
)
from kronos.intraday.opening_semantic import (
    OpeningSemanticError,
    build_opening_semantic_evidence,
)
from kronos.intraday.probables import ProbableState
from kronos.intraday.probables_v2 import (
    PROBABLES_V2_CORRECTION_METHODOLOGY_CHECKSUM,
    ProbableReasonV2,
    ProbablesV2Error,
    build_semantic_qualification_evidence_v2,
    create_discovery_probables_evidence_v2,
    create_probables_v2_methodology,
    evaluate_probables_v2_run,
)
from kronos.intraday.probables_v2_persistence import ProbablesV2Store, _artifact_bytes
from tests.unit.intraday.test_probables_v2 import (
    CURRENT_DAY,
    PREVIOUS_DAY,
    IST,
    OPEN,
    SOURCE_RUN,
    PROVENANCE,
    _candle,
    _later_mapping,
    _narrow,
    _narrow_from_daily,
    _schedule,
)


def opening_mapping(
    methodology, direction='LONG', prior='SUPPORTING', five='INFORMATIONAL',
    nifty='INFORMATIONAL', subject='NSE-EQ-RELIANCE', missing=None, narrow=True,
    source_binding_version=None,
):
    if source_binding_version is None:
        source_binding_version = "1.0.0" if methodology.methodology_version in {"2.0.0", "2.1.0"} else "1.1.0"
    (current, previous) = (_schedule(CURRENT_DAY), _schedule(PREVIOUS_DAY))
    boundary = datetime.combine(CURRENT_DAY, time(10, 15), IST)
    sign = 1 if direction == 'LONG' else -1 if direction == 'SHORT' else 0

    def candle(schedule, tf, start, op, cl):
        return _candle(
            subject,
            schedule,
            tf,
            datetime.combine(schedule.trading_date, start, IST),
            opening=str(op),
            close=str(cl),
            observation_boundary=boundary,
        )
    daily_close = 101 if source_binding_version == "1.0.0" else 100 if narrow else 103
    daily = (candle(previous, TF.DAILY, OPEN, 100, daily_close),)

    def pairs(relationship, count):
        step = sign if relationship == 'SUPPORTING' else -sign if relationship == 'CONFLICTING' else 0
        return [(100 + step * i, 101 + step * i) for i in range(count)]
    hours = tuple((candle(previous, TF.ONE_HOUR, time(14 + i, 0), *p) for (i, p) in enumerate(pairs(prior, 2))))
    fifteens = (candle(current, TF.FIFTEEN_MINUTES, OPEN, 100, 100 + 3 * sign),)
    fives = tuple(
        (candle(current, TF.FIVE_MINUTES, time(10, i * 5), *p) for (i, p) in enumerate(pairs(five, 3))),
    )
    selection = build_completed_evidence_selection(
        canonical_subject_identity=subject,
        analysis_boundary=boundary,
        current_schedule=current,
        previous_schedule=previous,
        previous_daily=() if missing == '1D' else daily,
        previous_one_hour=() if missing == '1H' else hours,
        current_one_hour=(),
        current_fifteen_minute=() if missing == '15M' else fifteens,
        current_five_minute=() if missing == '5M' else fives,
        provenance=PROVENANCE,
    )
    benchmark_close = 100 + sign * {'SUPPORTING': 1, 'INFORMATIONAL': 3, 'CONFLICTING': 5}[nifty]
    benchmark = _candle(
        NIFTY_CANONICAL_IDENTITY,
        current,
        TF.FIFTEEN_MINUTES,
        datetime.combine(CURRENT_DAY, OPEN, IST),
        opening='100',
        close=str(benchmark_close),
        observation_boundary=boundary,
    )
    relative = build_nifty_relative_context(
        source_binding_version=source_binding_version,
        subject_schedule=current, benchmark_schedule=current,
        canonical_subject_identity=subject,
        subject_exchange='NSE',
        opening_direction=direction,
        analysis_boundary=boundary,
        subject_candle=fifteens[0],
        benchmark_candle=None if missing == 'NIFTY' else benchmark,
        subject_session_open=Decimal('100'),
        benchmark_session_open=Decimal('100'),
        provenance=PROVENANCE,
    )
    cpr = (
        _narrow(subject, boundary, narrow) if source_binding_version == "1.0.0"
        else _narrow_from_daily(daily[0], current.session_id, boundary)
    )
    if missing == "CPR":
        cpr = None
    opening = build_opening_semantic_evidence(
        source_binding_version=source_binding_version,
        selection=selection,
        narrow_cpr_fact=cpr,
        nifty_relative_evidence=relative,
        participation_state='AVAILABLE_SUPPORTING_NON_BLOCKING',
        provenance=PROVENANCE,
    )
    semantic = build_semantic_qualification_evidence_v2(
        source_binding_version=source_binding_version,
        selection=selection,
        narrow_cpr_fact=cpr,
        opening_semantic=opening,
        nifty_relative=relative,
        participation_state='AVAILABLE_SUPPORTING_NON_BLOCKING',
        provenance=PROVENANCE,
    )
    return create_discovery_probables_evidence_v2(
        universe_member_identity=f'INTRADAY-UNIVERSE-MEMBER:{subject}',
        source_discovery_run_identity=SOURCE_RUN,
        source_discovery_member_identity=f'INTRADAY-DISCOVERY-RESULT:{subject}',
        market_session_identity=current.session_id,
        completed_evidence=selection,
        semantic_evidence=semantic,
        opening_semantic=opening,
        nifty_relative=relative,
        provenance=PROVENANCE,
        methodology=methodology,
    )


def run_mapping(mapping, methodology):
    return evaluate_probables_v2_run(
        source_discovery_run_identity=SOURCE_RUN,
        universe_identity='KRONOS-INTRADAY-NATIVE-UNIVERSE-V1',
        universe_version='1.0.0',
        reconciliation_identity='KRONOS-INTRADAY-RECONCILIATION-V1',
        reconciliation_version='1.0.0',
        market_session_identity=mapping.market_session_identity,
        analysis_boundary=mapping.analysis_boundary,
        member_evidence=(mapping,),
        unavailable_members=(),
        provenance=PROVENANCE,
        methodology=methodology,
    )


RELATIONSHIPS = ('SUPPORTING', 'INFORMATIONAL', 'CONFLICTING')


TRUTH_ROWS = tuple(product(RELATIONSHIPS, repeat=3))


# Captured from 3a4a5fb3d545a0a6c24d3fec97bbb2d83faaefab before correction.
HISTORICAL_GOLDEN = json.loads(Path(__file__).with_name('wo06a_historical_opening_golden.json').read_text())


@pytest.mark.parametrize('direction', ('LONG', 'SHORT'))
@pytest.mark.parametrize(('prior', 'five', 'nifty'), TRUTH_ROWS)
def test_corrected_admission_full_truth_table(direction, prior, five, nifty):
    methodology = create_probables_v2_methodology()
    mapping = opening_mapping(methodology, direction, prior, five, nifty)
    fact = mapping.opening_semantic.fact
    assert fact.prior_one_hour_relationship.value == prior
    assert fact.five_minute_relationship.value == five
    assert mapping.nifty_relative.relationship.value == nifty
    values = (prior, five, nifty)
    expected = 'CONFLICTING' if 'CONFLICTING' in values else 'SUPPORTING' if 'SUPPORTING' in values else 'INFORMATIONAL'
    assert mapping.opening_semantic.combined_relationship.value == expected
    result = run_mapping(mapping, methodology).results[0]
    assert result.direction.value == direction
    assert result.state.value == (f'{direction}_PROBABLE' if expected == 'SUPPORTING' else 'NOT_ADMITTED')
    assert ProbableReasonV2.OPENING_5M_NOT_SUPPORTING not in result.reasons


@pytest.mark.parametrize('key', sorted(HISTORICAL_GOLDEN))
def test_pre_correction_artifact_bytes_and_membership_are_preserved(key, tmp_path):
    (version, direction, prior, five, nifty) = key.split('|')
    methodology = create_probables_v2_methodology(version=version)
    mapping = opening_mapping(methodology, direction, prior, five, nifty)
    run = run_mapping(mapping, methodology)
    expected = HISTORICAL_GOLDEN[key]
    assert run.run_identity == expected['run_identity']
    assert methodology.integrity_identity == expected['methodology_integrity']
    assert sha256(_artifact_bytes(run)).hexdigest() == expected['artifact_sha256']
    assert run.results[0].state.value == expected['state']
    assert [r.value for r in run.results[0].reasons] == expected['reasons']
    store = ProbablesV2Store(tmp_path.resolve())
    store.retain_complete(run=run, mappings=(mapping,))
    assert store.load_current_run() == run
    assert store.load_mapping(mapping.mapping_identity) == mapping
    assert IntradayProbablesV2Application(store=store).snapshot().run == run


@pytest.mark.parametrize('direction', ('LONG', 'SHORT'))
@pytest.mark.parametrize('missing', ('1H', '5M', '15M', '1D', 'CPR'))
def test_missing_mandatory_evidence_never_becomes_informational(direction, missing):
    with pytest.raises((CompletedEvidenceError, OpeningSemanticError)):
        opening_mapping(create_probables_v2_methodology(), direction, missing=missing)


@pytest.mark.parametrize('direction', ('LONG', 'SHORT'))
def test_missing_applicable_nifty_is_unavailable(direction):
    methodology = create_probables_v2_methodology()
    mapping = opening_mapping(methodology, direction, missing='NIFTY')
    result = run_mapping(mapping, methodology).results[0]
    assert result.state is ProbableState.UNAVAILABLE
    assert result.reasons == (ProbableReasonV2.NIFTY_CONTEXT_UNAVAILABLE,)


@pytest.mark.parametrize('direction', ('LONG', 'SHORT'))
@pytest.mark.parametrize('prior', ('SUPPORTING', 'INFORMATIONAL', 'CONFLICTING'))
def test_nifty_self_reference_is_not_required_or_treated_as_support(direction, prior):
    methodology = create_probables_v2_methodology()
    mapping = opening_mapping(
        methodology,
        direction,
        prior=prior,
        subject=NIFTY_CANONICAL_IDENTITY,
        missing='NIFTY',
    )
    assert mapping.nifty_relative.fact.applicability is NiftyApplicability.NOT_APPLICABLE
    assert mapping.nifty_relative.relationship is NiftyRelationship.NOT_APPLICABLE
    result = run_mapping(mapping, methodology).results[0]
    assert result.state.value == (f'{direction}_PROBABLE' if prior == 'SUPPORTING' else 'NOT_ADMITTED')


@pytest.mark.parametrize('direction', ('LONG', 'SHORT'))
def test_narrow_cpr_still_blocks_combined_support(direction):
    methodology = create_probables_v2_methodology()
    result = run_mapping(opening_mapping(methodology, direction, narrow=False), methodology).results[0]
    assert result.state is ProbableState.NOT_ADMITTED
    assert result.reasons == (ProbableReasonV2.NARROW_CPR_NOT_SATISFIED,)


def rebind(mapping, methodology):
    return create_discovery_probables_evidence_v2(
        universe_member_identity=mapping.universe_member_identity,
        source_discovery_run_identity=mapping.source_discovery_run_identity,
        source_discovery_member_identity=mapping.source_discovery_member_identity,
        market_session_identity=mapping.market_session_identity,
        completed_evidence=mapping.completed_evidence,
        semantic_evidence=mapping.semantic_evidence,
        opening_semantic=mapping.opening_semantic,
        nifty_relative=mapping.nifty_relative,
        provenance=mapping.provenance,
        methodology=methodology,
    )


@pytest.mark.parametrize(
    ('fifteen', 'hours', 'hour', 'minute'),
    ((2, 0, 10, 30), (4, 1, 11, 0), (8, 2, 12, 0)),
)
def test_later_phases_keep_the_same_admission_across_publications(fifteen, hours, hour, minute):
    mapping = _later_mapping(fifteen, hours, boundary=datetime(2026, 8, 28, hour, minute, tzinfo=IST))
    outcomes = []
    for version in ('2.0.0', '2.1.0', '2.2.0'):
        methodology = create_probables_v2_methodology(version=version)
        result = run_mapping(rebind(mapping, methodology), methodology).results[0]
        outcomes.append((result.state, result.direction, result.reasons, result.phase))
    assert outcomes[0] == outcomes[1] == outcomes[2]


def test_publication_payload_checksum_and_exact_version_selection():
    root = Path(__file__).resolve().parents[3]
    path = root / 'docs/architecture/products/intraday/KRONOS-INTRADAY-WO-06A-OPENING-CORRECTION-V2.2-METHODOLOGY-PAYLOAD.json'
    payload = json.loads(path.read_text())
    assert sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest() == PROBABLES_V2_CORRECTION_METHODOLOGY_CHECKSUM
    assert create_probables_v2_methodology().methodology_version == '2.2.0'
    assert create_probables_v2_methodology(legacy=True) == create_probables_v2_methodology(version='2.0.0')
    for version in ('2.0.0', '2.1.0', '2.2.0'):
        with pytest.raises(ProbablesV2Error):
            replace(create_probables_v2_methodology(version=version), payload_checksum='0' * 64)
    with pytest.raises(ProbablesV2Error):
        create_probables_v2_methodology(version='2.3.0')
    with pytest.raises(ProbablesV2Error):
        create_probables_v2_methodology(legacy=True, version='2.2.0')


@pytest.mark.parametrize('version', ('2.0.0', '2.1.0', '2.2.0'))
def test_replay_envelope_selects_its_original_methodology(version, tmp_path):
    from kronos.intraday.probables_v2_diagnostics import ProbablesV2ReplayEnvelope, _identity, replay_v2_mapping
    from tests.unit.intraday.test_probables_v2_refresh_control import _control, _payload
    (_, composition, control, _, requests) = _control(tmp_path)
    outcome = control.execute_document(_payload('WO06A-REPLAY'))
    original = composition.probables_v2_diagnostics_store.load_envelope(outcome['replay_envelope_identity'])
    methodology = create_probables_v2_methodology(version=version)
    values = {name: getattr(original, name) for name in original.__dataclass_fields__ if name not in {'envelope_identity', 'integrity_identity'}}
    values.update(
        methodology_version=version,
        methodology_publication_identity=methodology.publication_identity,
        methodology_checksum=methodology.payload_checksum,
    )
    envelope = ProbablesV2ReplayEnvelope(
        **values,
        envelope_identity=_identity('INTRADAY-PROBABLES-V2-REPLAY-ENVELOPE-', values),
        integrity_identity=_identity('INTEGRITY-INTRADAY-PROBABLES-V2-REPLAY-ENVELOPE-', values),
    )
    reads = requests[0]
    mapping = replay_v2_mapping(envelope)
    assert mapping.member_evidence
    assert {m.methodology_version for m in mapping.member_evidence} == {version}
    assert {m.methodology_checksum for m in mapping.member_evidence} == {methodology.payload_checksum}
    assert requests[0] == reads


def test_non_directional_first_15m_still_blocks_admission():
    methodology = create_probables_v2_methodology()
    mapping = opening_mapping(methodology, direction="NON_DIRECTIONAL")
    result = run_mapping(mapping, methodology).results[0]
    assert result.state is ProbableState.NOT_ADMITTED
    assert result.reasons == (ProbableReasonV2.OPENING_NON_DIRECTIONAL,)
