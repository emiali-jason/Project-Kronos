"""Production-composed WO12 rehearsal; disposable stores and Provider doubles only."""
from datetime import timedelta
from hashlib import sha256
import json
import pytest
from pathlib import Path

from kronos.intraday.wo12_eod_validation import COHORT, OUTCOME
from tests.unit.intraday.test_live_shadow_integration import pipeline
from tests.unit.intraday.test_probables_v2_refresh_control import _payload
from kronos.provider.contracts.market_data import QuoteSnapshot, OhlcValues
from kronos.application.intraday_runtime import create_intraday_runtime


def retained(root):
    return {str(p.relative_to(root)): sha256(p.read_bytes()).hexdigest()
        for p in root.rglob('*.json') if 'prospective-v2-wo12-research-ledger-v1' not in p.parts}


def test_composed_considered_cohort_terminal_completion_and_restore(tmp_path):
    c, control, shadow, response, envelope, quotes, calls, sources, clock = pipeline(tmp_path, active=False)
    research = c.research_application
    research.publication_root = tmp_path/'Statistics'
    first_run = c.probables_v2_application.snapshot().run
    before = retained(tmp_path)
    request_counts = (len(quotes), len(calls))
    initial = research.update(operation_identity='ISOLATED-WO12-T0')
    assert initial.outcome == 'PUBLISHED'
    cohorts = research.store.records(COHORT)
    assert len(first_run.results) == 98 and len(cohorts) == 93
    assert all(v.data['prediction_match'] == 'NOT_EVALUABLE' for v in research.store.records(OUTCOME))
    assert retained(tmp_path) == before
    assert request_counts == (len(quotes), len(calls))
    original = {v.identity: v for v in cohorts}
    # A separate ordinary Analysis supplies later completed evidence. These calls
    # are local test doubles; WO12 makes none and does not trigger this operation.
    clock[0] = clock[0].replace(hour=15, minute=30)
    capability = c.discovery_v2_operation._runtime._SharedAuthenticatedProviderRuntime__capability
    original_hist = capability.historical_candles
    from kronos.provider.contracts.market_data import HistoricalInterval
    # Correct only the isolated double: a candle starting at the closed endpoint
    # is outside the governed schedule and is not a legitimate Provider sample.
    def bounded_hist(request):
        values=original_hist(request)
        return values if request.interval is HistoricalInterval.DAY else tuple(v for v in values if v.timestamp < request.end)
    capability.historical_candles=bounded_hist
    result = control.execute_document(_payload('ISOLATED-WO12-EOD-SOURCE', boundary=clock[0]))
    assert result['outcome'] == 'SUCCESS', result
    late = c.probables_v2_diagnostics_store.load_envelope(result['replay_envelope_identity'])
    assert len(late.probables_v2_facts)==93, [(r.canonical_identity, r.reasons) for r in late.discovery_run.results[:3]]
    before = retained(tmp_path)
    request_counts = (len(quotes), len(calls))
    completed = research.update(operation_identity='ISOLATED-WO12-EOD')
    assert completed.outcome == 'PUBLISHED'
    from kronos.application.intraday_wo12_eod import latest_outcomes
    outcomes = latest_outcomes(research.store.records(OUTCOME))
    assert len(outcomes) == 93
    assert {o.data['prediction_match'] for o in outcomes} == {'MATCHED'}, {o.data['reason'] for o in outcomes}
    assert all(research.store.load(k) == v for k, v in original.items())
    assert retained(tmp_path) == before
    assert request_counts == (len(quotes), len(calls))
    from kronos.intraday.wo12_research_store import ResearchStore
    restored = ResearchStore(research.store.root)
    assert {o.identity: restored.load(o.identity) for o in outcomes} == {o.identity: o for o in outcomes}
    repeat = research.update(operation_identity='ISOLATED-WO12-REPEAT')
    assert repeat.outcome == 'ALREADY_UP_TO_DATE' and repeat.receipt_identity == completed.receipt_identity
    assert request_counts == (len(quotes), len(calls))


def terminal_envelope_fixture(original, later):
    """Synthetic market inputs through existing typed source/envelope contracts.

    This is a source-level fixture, not an authorized production acquisition or
    evidence that current closed-window Analysis collects EOD bars.
    """
    from dataclasses import fields
    from kronos.intraday.probables_v2_refresh import create_discovery_probables_v2_facts
    from kronos.intraday.probables_v2_diagnostics import ProbablesV2ReplayEnvelope, _identity
    from kronos.provider.contracts.market_data import HistoricalCandle
    from kronos.intraday.candles import expected_candle_boundaries
    from kronos.intraday.contracts import IntradayTimeframe as TF
    def raw(c):
        return HistoricalCandle(c.candle_start, float(c.open), float(c.high), float(c.low), float(c.close), c.volume)
    facts = []
    for f in original.probables_v2_facts:
        complete = tuple(HistoricalCandle(b.start, 150., 152., 149., 151., 100)
            for b in expected_candle_boundaries(f.current_schedule, TF.FIVE_MINUTES))
        facts.append(create_discovery_probables_v2_facts(
            universe_member_identity=f.universe_member_identity, canonical_subject_identity=f.canonical_subject_identity,
            subject_exchange=f.subject_exchange, discovery_bundle_identity=f.discovery_bundle_identity,
            observation_boundary_identity='ISOLATED-EOD-BOUNDARY', observation_boundary=later.analysis_boundary,
            current_schedule=f.current_schedule, previous_schedule=f.previous_schedule,
            previous_daily=tuple(raw(c) for c in f.previous_daily), previous_one_hour=tuple(raw(c) for c in f.previous_one_hour),
            current_one_hour=tuple(raw(c) for c in f.current_one_hour),
            current_fifteen_minute=tuple(raw(c) for c in f.current_fifteen_minute), current_five_minute=complete))
    core = {field.name:getattr(later, field.name) for field in fields(later)
        if field.name not in ('envelope_identity','integrity_identity')}
    core.update(probables_v2_facts=tuple(facts), provenance=('ISOLATED_SYNTHETIC_EOD_SOURCE_NO_PRODUCTION_AUTHORITY',))
    return ProbablesV2ReplayEnvelope(envelope_identity=_identity('INTRADAY-PROBABLES-V2-REPLAY-ENVELOPE-',core),
        integrity_identity=_identity('INTEGRITY-INTRADAY-PROBABLES-V2-REPLAY-ENVELOPE-',core), **core)
