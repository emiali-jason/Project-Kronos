"""Retained-only EOD completion at explicit WO12 update; no automatic acquisition."""
from datetime import datetime
from kronos.intraday.probables_v2_diagnostics_persistence import ProbablesV2DiagnosticsStore
from kronos.intraday.probables_v2_persistence import _from_wire
from kronos.intraday.mcx_history_persistence import McxContractHistoryStore
from kronos.intraday.wo12_eod_validation import COHORT, OUTCOME, consideration, evaluate


def complete(*, associations, probables, store, now, retain=False):
    existing = store.records(COHORT)
    results = store.records(OUTCOME)
    verify_originals(existing, probables, associations)
    verify_sources(results, probables, now)
    if not retain:
        return existing, results
    # Load existing immutable ordinary Analysis evidence only. No Provider lease,
    # current-calendar inference, replay calculation or operational pointer write.
    diagnostics = ProbablesV2DiagnosticsStore(probables.root)
    candidates = [d for d in associations if d.data['wo09_entry'] is not None
        and d.data['opportunity_identity'] is not None]
    if not candidates and not existing:
        return existing, results
    envelopes = tuple(diagnostics.load_envelope(p.stem) for p in
        sorted((diagnostics.root/'replay-envelopes').glob('*.json')))
    for a in candidates:
        d = a.data
        old = [c for c in existing if c.data['opportunity_identity'] == d['opportunity_identity']
               and c.data['methodology'] == (d['original_methodology'] or {k:d[k] for k in
                   ('methodology_identity','methodology_version','methodology_checksum')})]
        if len(old) > 1:
            raise ValueError('WO12_CONSIDERATION_CONFLICT')
        schedules = [] if d['original_source'] is None else [f.current_schedule for e in envelopes
            if e.analysis_boundary <= now and e.created_at <= now
            and e.discovery_run.run_identity == d['original_source']['discovery_identity']
            for f in e.probables_v2_facts if f.canonical_subject_identity == d['subject']
            and f.current_schedule.session_id == d['session_identity']]
        if schedules and any(s != schedules[0] for s in schedules):
            raise ValueError('WO12_ORIGINAL_SCHEDULE_CONFLICT')
        c = old[0] if old else consideration(a, probables, schedules[0] if schedules else None)
        if c is None:
            continue
        if not old:
            store.retain(c)
            existing += (c,)
    for c in existing:
        d = c.data
        schedule = None if d['schedule'] is None else _from_wire(d['schedule'])
        assessment = None if d['original_assessment'] is None else _from_wire(d['original_assessment'])
        matches = []
        for e in envelopes:
            if e.analysis_boundary > now or e.created_at > now:
                continue
            for f in e.probables_v2_facts:
                if f.canonical_subject_identity != d['subject'] or f.current_schedule != schedule:
                    continue
                f.__post_init__()
                from kronos.intraday.candles import expected_candle_boundaries
                from kronos.intraday.contracts import IntradayTimeframe as TF
                boundaries = expected_candle_boundaries(schedule, TF.FIVE_MINUTES)
                if not boundaries:
                    continue
                terminal = boundaries[-1]
                for candle in f.current_five_minute:
                    if (candle.candle_start, candle.candle_end) == (terminal.start, terminal.end):
                        matches.append((candle, dict(envelope_identity=e.envelope_identity,
                            envelope_integrity=e.integrity_identity, facts_identity=f.facts_identity,
                            facts_integrity=f.integrity_identity)))
        if not matches:
            matches = [(None, None)]
        completed = [o for o in results if o.data['consideration_identity'] == c.identity
            and o.data['prediction_match'] != 'NOT_EVALUABLE']
        for candle, source in matches:
            native = {}
            if candle is not None and d['market'] == 'MCX' and d['exact_contract']:
                history = McxContractHistoryStore(probables.root)
                try:
                    values = history.load_contract(canonical_subject_identity=d['subject'],
                        canonical_contract_identity=d['exact_contract'])
                except ValueError as error:
                    if str(error) != 'MCX_HISTORY_CONTRACT_UNAVAILABLE':
                        raise
                    values = ()
                for value in values:
                    native.setdefault((value.canonical_subject_identity, value.source_operation_identity,
                        value.timeframe, value.candle_start, value.candle_end), []).append(value)
            value = evaluate(c, assessment=assessment, schedule=schedule, candle=candle,
                native=native, now=now, source=source)
            if completed:
                prior = completed[0].data
                if value.data['prediction_match'] == 'NOT_EVALUABLE':
                    continue
                # Retrieval/provenance variants may agree, but cannot revise the
                # terminal OHLCV or original price/methodology/session truth.
                keys = ('terminal_price', 'terminal_at', 'prediction_match', 'directional_move_pct', 'terminal_candle')
                if any(_terminal_truth(prior[k]) != _terminal_truth(value.data[k]) if k == 'terminal_candle'
                       else prior[k] != value.data[k] for k in keys):
                    raise ValueError('WO12_EOD_PUBLICATION_CONFLICT')
                continue
            equivalent = [o for o in results if o.data['consideration_identity'] == c.identity
                and all(v == o.data.get(k) for k, v in value.data.items() if k != 'evaluated_boundary')]
            if not equivalent:
                store.retain(value)
                results += (value,)
            if value.data['prediction_match'] != 'NOT_EVALUABLE':
                completed = [value]
    verify_sources(results, probables, now)
    return existing, results


def latest_outcomes(results):
    latest = {}
    for result in sorted(results, key=lambda r: (datetime.fromisoformat(r.data['evaluated_boundary']), r.identity)):
        key = result.data['consideration_identity']
        prior = latest.get(key)
        if prior is None or prior.data['prediction_match'] == 'NOT_EVALUABLE':
            latest[key] = result
        elif result.data['prediction_match'] != 'NOT_EVALUABLE' and any(
            (_terminal_truth(prior.data[k]) != _terminal_truth(result.data[k]) if k == 'terminal_candle'
             else prior.data[k] != result.data[k]) for k in ('terminal_price', 'terminal_at', 'prediction_match', 'directional_move_pct', 'terminal_candle')):
            raise ValueError('WO12_EOD_PUBLICATION_CONFLICT')
    return tuple(latest.values())


def _terminal_truth(wire):
    """Compare retained market content across later retrievals without restamping."""
    if wire is None:
        return None
    candle = _from_wire(wire)
    return tuple(getattr(candle, name) for name in ('canonical_subject_identity', 'exchange',
        'market_session_identity', 'timeframe', 'candle_start', 'candle_end',
        'open', 'high', 'low', 'close', 'volume', 'completion_state'))


def verify_sources(results, probables, now):
    """Resolve pinned retained terminal authority on every projection/readback.

    Missing source is a bounded unavailable exception; integrity/schema/storage
    faults remain faults. Neither absence nor corruption authorizes a substitute.
    """
    from kronos.intraday.probables_v2_persistence import _to_wire
    from kronos.intraday.mcx_history import retained_mcx_candle_bytes, parse_retained_mcx_candle
    import json
    diagnostics = ProbablesV2DiagnosticsStore(probables.root)
    envelopes = {}
    for outcome in results:
        o = outcome.data
        if o['prediction_match'] == 'NOT_EVALUABLE':
            continue
        ref = o['source']
        try:
            identity = ref['envelope_identity']
            if identity not in envelopes:
                envelopes[identity] = diagnostics.load_envelope(identity)
            e = envelopes[identity]
        except FileNotFoundError:
            raise ValueError('WO12_TERMINAL_SOURCE_UNAVAILABLE') from None
        if (e.integrity_identity != ref['envelope_integrity'] or e.analysis_boundary > now
                or e.created_at > datetime.fromisoformat(o['evaluated_boundary'])):
            raise ValueError('WO12_TERMINAL_SOURCE_BINDING_INVALID')
        f = next((f for f in e.probables_v2_facts if f.facts_identity == ref['facts_identity']), None)
        if (f is None or f.integrity_identity != ref['facts_integrity']
                or f.canonical_subject_identity != o['subject']
                or not any(_to_wire(c) == o['terminal_candle'] for c in f.current_five_minute)):
            raise ValueError('WO12_TERMINAL_SOURCE_BINDING_INVALID')
        f.__post_init__()
        if o['market'] == 'MCX':
            values = McxContractHistoryStore(probables.root).load_contract(
                canonical_subject_identity=o['subject'], canonical_contract_identity=o['exact_contract'])
            retained = {retained_mcx_candle_bytes(v) for v in values}
            if any(retained_mcx_candle_bytes(parse_retained_mcx_candle(json.dumps(v, sort_keys=True, separators=(',',':')).encode()+b'\n')) not in retained for v in o['native_evidence']):
                raise ValueError('WO12_TERMINAL_NATIVE_SOURCE_BINDING_INVALID')


def verify_originals(cohorts, probables, associations):
    from kronos.intraday.probables_v2_persistence import _to_wire
    runs, companions = {}, {}
    envelopes = None
    for c in cohorts:
        d = c.data
        candidates = [a for a in associations if a.data['opportunity_identity'] == d['opportunity_identity']
            and a.data['wo09_entry'] == d['wo09_entry']
            and (a.data['original_methodology'] if d['original_prediction'] is not None else
                 {k:a.data[k] for k in ('methodology_identity','methodology_version','methodology_checksum')}) == d['methodology']]
        if not candidates:
            raise ValueError('WO12_ORIGINAL_AUTHORITY_UNAVAILABLE')
        if d['original_prediction'] is not None:
            schedule = None if d['schedule'] is None else _from_wire(d['schedule'])
            expected = consideration(candidates[0], probables, schedule)
            if expected != c:
                raise ValueError('WO12_ORIGINAL_AUTHORITY_CHANGED')
            if schedule is not None:
                if envelopes is None:
                    diagnostics = ProbablesV2DiagnosticsStore(probables.root)
                    envelopes = tuple(diagnostics.load_envelope(p.stem) for p in
                        sorted((diagnostics.root/'replay-envelopes').glob('*.json')))
                if not any(e.discovery_run.run_identity == d['original_source']['discovery_identity']
                    and f.canonical_subject_identity == d['subject'] and f.current_schedule == schedule
                    for e in envelopes for f in e.probables_v2_facts):
                    raise ValueError('WO12_ORIGINAL_SCHEDULE_AUTHORITY_CHANGED')
    for c in cohorts:
        d = c.data
        p = d['original_prediction']
        if p is None:
            continue
        run_id = d['original_run_identity']
        if run_id not in runs:
            runs[run_id] = probables.load_run(run_id)
            companions[run_id] = probables.load_assessment_observations(run_id)
        run = runs[run_id]
        result = probables.load_result(p['probable_result_identity'])
        if run.integrity_identity != d['run_integrity'] or result not in run.results or result.integrity_identity != p['probable_result_integrity']:
            raise ValueError('WO12_ORIGINAL_PREDICTION_BINDING_INVALID')
        companion = companions[run_id]
        originals = () if companion is None else tuple(a for a in companion.observations if a.admission_identity == result.result_identity)
        original = originals[0] if len(originals) == 1 else None
        if len(originals) > 1 or (None if original is None else _to_wire(original)) != d['original_assessment']:
            raise ValueError('WO12_ORIGINAL_ASSESSMENT_CHANGED')
