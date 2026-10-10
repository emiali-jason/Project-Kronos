"""Sponsor-approved terminal directional validation; research authority only.

Original consideration and later outcome are separate immutable records. This
module has no Provider, notification, readiness or lifecycle mutation capability.
"""
from dataclasses import replace
import json
from kronos.intraday.mcx_history import retained_mcx_candle_bytes, parse_retained_mcx_candle
from datetime import datetime

from kronos.intraday.assessment_observation import AssessmentPriceAuthority
from kronos.intraday.candles import expected_candle_boundaries
from kronos.intraday.contracts import IntradayTimeframe as TF
from kronos.intraday.historical_semantic import GovernedHistoricalCandlePayload
from kronos.intraday.live_shadow import directional_move
from kronos.intraday.probables_v2_persistence import _to_wire
from kronos.intraday.technical_context_research import native_binding
from kronos.intraday.wo12_research_contract import record, digest
from kronos.market.schedule import MarketDaySchedule

COHORT = 'WO12_WO08_CONSIDERATION_V1'
OUTCOME = 'WO12_WO08_EOD_VALIDATION_V1'
POLICY = 'WO12_V1_TERMINAL_DIRECTIONAL_MATCH'
VERSION = '1.0.0'
RULES = dict(baseline='EXACT_ORIGINAL_ASSESSMENT_PRICE',
    endpoint='EXACT_TERMINAL_COMPLETED_GOVERNED_5M_CLOSE',
    positive='MATCHED', negative='NOT_MATCHED', flat='NOT_MATCHED',
    missing='NOT_EVALUABLE', partial='NOT_COMMISSIONED',
    interpretation='DIRECTION_AT_SESSION_ENDPOINT_ONLY', authority='RESEARCH_ONLY')
CHECKSUM = digest(RULES)


def consideration(association, probables, schedule):
    """Freeze only the exact origin assessment, never a later replacement."""
    d = association.data
    p = d['original_prediction']
    if p is None:
        return record(COHORT, opportunity_id=d['opportunity_id'], opportunity_identity=d['opportunity_identity'],
            subject=d['subject'], market=d['market_family'], session=d['session_identity'],
            original_prediction=None, original_run_identity=None, run_integrity=None,
            origin_at=d['opportunity_origin_at'], direction=None,
            methodology={k:d[k] for k in ('methodology_identity','methodology_version','methodology_checksum')},
            methodology_provenance='WO09_ENTRANT_VERSION_ORIGINAL_PREDICTION_NOT_RETAINED',
            original_source=None, assessment_companion_identity=None, assessment_companion_integrity=None,
            original_assessment=None, schedule=None, exact_contract=None, roll_lineage=None,
            wo09_entry=d['wo09_entry'], policy=POLICY, policy_version=VERSION, policy_checksum=CHECKSUM,
            authority='RESEARCH_ONLY_NO_TRADING_AUTHORITY')
    original = probables.load_result(p['probable_result_identity'])
    run = probables.load_run(d['original_run_identity'])
    if original not in run.results or original.integrity_identity != p['probable_result_integrity']:
        raise ValueError('WO12_ORIGINAL_PREDICTION_BINDING_INVALID')
    companion = probables.load_assessment_observations(run.run_identity)
    prices = () if companion is None else tuple(o for o in companion.observations
        if o.admission_identity == original.result_identity)
    if len(prices) > 1:
        raise ValueError('WO12_ORIGINAL_ASSESSMENT_AMBIGUOUS')
    price = prices[0] if prices else None
    if price is not None:
        price.__post_init__()
    return record(COHORT, opportunity_id=d['opportunity_id'], opportunity_identity=d['opportunity_identity'],
        subject=d['subject'], market=d['market_family'], session=d['session_identity'],
        original_prediction=p, origin_at=d['opportunity_origin_at'], direction=p['direction'],
        methodology_provenance='EXACT_ORIGINAL_WO08_VERSION', original_run_identity=run.run_identity, run_integrity=run.integrity_identity,
        methodology=d['original_methodology'], original_source=d['original_source'],
        assessment_companion_identity=None if companion is None else companion.evidence_identity,
        assessment_companion_integrity=None if companion is None else companion.integrity_identity,
        original_assessment=None if price is None else _to_wire(price),
        schedule=None if schedule is None else _to_wire(schedule),
        exact_contract=d['original_source']['exact_mcx_contract_identity'],
        roll_lineage=d['original_source']['exact_mcx_roll_lineage'],
        wo09_entry=d['wo09_entry'], policy=POLICY, policy_version=VERSION, policy_checksum=CHECKSUM,
        authority='RESEARCH_ONLY_NO_TRADING_AUTHORITY')


def evaluate(cohort, *, assessment, schedule, candle=None, native=None, now, source=None):
    """Endpoint classification, with no price fallback and no path-success rule.

    Invalid typed/integrity data raises; lawful absent/foreign/incomplete evidence
    is NOT_EVALUABLE. The caller must retain and compare the exact source bytes.
    """
    cohort.__post_init__()
    if cohort.schema != COHORT or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('WO12_EOD_INPUT_INVALID')
    d = cohort.data
    reason, move, state = None, None, 'NOT_ESTABLISHED'
    if d['original_prediction'] is None:
        reason = 'ORIGINAL_PREDICTION_NOT_RETAINED'
    elif assessment is None:
        reason = 'ORIGINAL_ASSESSMENT_PRICE_NOT_RETAINED'
    else:
        assessment.__post_init__()
        if _to_wire(assessment) != d['original_assessment']:
            raise ValueError('WO12_ORIGINAL_ASSESSMENT_CHANGED')
        if (assessment.canonical_subject_identity != d['subject']
                or assessment.market_session_identity != d['session']
                or assessment.direction != d['direction']
                or assessment.run_identity != d['original_run_identity']
                or assessment.admission_identity != d['original_prediction']['probable_result_identity']):
            reason = 'SUBJECT_SESSION_AUTHORITY_NOT_ESTABLISHED'
        if assessment.proof is not None and assessment.proof.available_at > now:
            reason = 'ORIGINAL_ASSESSMENT_NOT_AVAILABLE_AT_EVALUATION'
        if (assessment.classification is AssessmentPriceAuthority.PRICE_NOT_RETAINED
                or assessment.assessment_price is None):
            reason = 'ORIGINAL_ASSESSMENT_PRICE_NOT_RETAINED'
        elif assessment.assessment_price <= 0:
            reason = 'ORIGINAL_ASSESSMENT_PRICE_INVALID'
    if schedule is not None:
        if type(schedule) is not MarketDaySchedule:
            raise ValueError('WO12_SCHEDULE_TYPE_INVALID')
        replace(schedule)
    if reason is None and (schedule is None or _to_wire(schedule) != d['schedule']
            or schedule.session_id != d['session']):
        reason = 'SUBJECT_SESSION_AUTHORITY_NOT_ESTABLISHED'
    if candle is not None:
        if type(candle) is not GovernedHistoricalCandlePayload:
            raise ValueError('WO12_CANDLE_TYPE_INVALID')
        replace(candle)
    if reason is None and candle is None:
        reason = 'TERMINAL_COMPLETED_EVIDENCE_NOT_RETAINED'
    if reason is None:
        boundaries = expected_candle_boundaries(schedule, TF.FIVE_MINUTES)
        terminal = boundaries[-1] if boundaries else None
        if (terminal is None or candle.timeframe is not TF.FIVE_MINUTES
                or candle.completion_state != 'COMPLETE'
                or (candle.candle_start, candle.candle_end) != (terminal.start, terminal.end)
                or candle.candle_end > now or candle.observation_boundary > now
                or candle.candle_end <= datetime.fromisoformat(d['original_prediction']['analysis_boundary'])
                or assessment.assessment_time > candle.candle_end):
            reason = 'TERMINAL_COMPLETED_EVIDENCE_NOT_ESTABLISHED'
        elif (candle.canonical_subject_identity != d['subject']
                or candle.market_session_identity != d['session']
                or candle.exchange != schedule.exchange or candle.close <= 0):
            reason = 'SUBJECT_SESSION_AUTHORITY_NOT_ESTABLISHED'
        elif d['market'] == 'MCX':
            binding = native_binding((candle,), native or {})
            if (not d['exact_contract'] or not d['roll_lineage'] or binding['state'] != 'AVAILABLE'
                    or binding['contract'] != d['exact_contract']):
                reason = 'EXACT_CONTRACT_AUTHORITY_NOT_ESTABLISHED'
    if source is not None and (type(source) is not dict
            or set(source) != {'envelope_identity','envelope_integrity','facts_identity','facts_integrity'}
            or any(not isinstance(v,str) or not v for v in source.values())):
        raise ValueError('WO12_TERMINAL_SOURCE_REFERENCE_INVALID')
    if reason is None and not source:
        reason = 'TERMINAL_SOURCE_AUTHORITY_NOT_ESTABLISHED'
    if reason is None:
        move, state = directional_move(d['direction'],
            str(assessment.assessment_price), str(candle.close))
        reason = state
    match = ('NOT_EVALUABLE' if state == 'NOT_ESTABLISHED' else
             'MATCHED' if state == 'POSITIVE_DIRECTIONAL_MOVE' else 'NOT_MATCHED')
    return record(OUTCOME, consideration_identity=cohort.identity, consideration_integrity=cohort.integrity,
        opportunity_identity=d['opportunity_identity'], opportunity_id=d['opportunity_id'],
        methodology=d['methodology'], subject=d['subject'], market=d['market'], session=d['session'],
        direction=d['direction'], exact_contract=d['exact_contract'],
        original_assessment_price=None if assessment is None else assessment.assessment_price,
        terminal_price=None if candle is None else candle.close,
        terminal_at=None if candle is None else candle.candle_end,
        terminal_identity=None if candle is None else candle.candle_identity,
        terminal_integrity=None if candle is None else candle.integrity_identity,
        source=source, terminal_candle=None if candle is None else _to_wire(candle),
        native_evidence=[json.loads(retained_mcx_candle_bytes(v))
            for v in ((native or {}).get((candle.canonical_subject_identity,
                candle.source_operation_identity.removeprefix('INTRADAY-DISCOVERY-V2-SEMANTIC:'),
                candle.timeframe, candle.candle_start, candle.candle_end), ()) if candle is not None else ())],
        directional_move_pct=move, directional_move_state=state,
        prediction_match=match, reason=reason, policy=POLICY, policy_version=VERSION,
        policy_checksum=CHECKSUM, interpretation=RULES['interpretation'],
        evaluated_boundary=now, authority='RESEARCH_ONLY_NO_TRADING_AUTHORITY')


def metrics(cohorts, outcomes, journeys):
    """One opportunity/version per denominator; count 3/4/5 separately.

    No single new definition of material advancement is imposed. Each governed
    progression level has its own evaluated denominator and non-match count.
    """
    latest = {o.data['consideration_identity']: o.data for o in outcomes}
    strata = {}
    for c in cohorts:
        d = c.data
        key = (*(d['methodology'][k] for k in ('methodology_identity', 'methodology_version', 'methodology_checksum')), d['market'], d['direction'],
               d['exact_contract'], d['session'])
        strata.setdefault(key, []).append(c)
    rows = []
    for key, group in sorted(strata.items(), key=lambda v: str(v[0])):
        label = 'WO12 terminal ' + ' / '.join(str(v) for v in key)
        values = [(c, latest.get(c.identity)) for c in group]
        evaluated = [(c, o) for c, o in values if o is not None and o['prediction_match'] != 'NOT_EVALUABLE']
        rows.append((label+' considered', len(group), len(group), len(group), 'Exact considered opportunity/version cohort'))
        rows.append((label+' evaluated', len(evaluated), len(group), len(evaluated)/len(group), 'Endpoint evidence coverage; no profitability claim'))
        for match in ('MATCHED', 'NOT_MATCHED', 'NOT_EVALUABLE'):
            count = sum((o['prediction_match'] if o else 'NOT_EVALUABLE') == match for _, o in values)
            rows.append((label+' '+match, count, len(group), count/len(group), 'Missing evidence stays in the cohort'))
        for match in ('MATCHED', 'NOT_MATCHED', 'NOT_EVALUABLE'):
            withheld = [(c, o) for c, o in values if not any(
                r['count'] is not None and r['count'] >= 3 for r in journeys.get(c.identity, ()))]
            count = sum((o['prediction_match'] if o else 'NOT_EVALUABLE') == match for _, o in withheld)
            rows.append((label+' withheld '+match, count, len(withheld),
                count/len(withheld) if withheld else None, 'No retained 3/5-or-higher progression; no unobserved transition inferred'))
        states = sorted({r['state'] for c, _ in values for r in journeys.get(c.identity, ()) if 'state' in r})
        for status in states:
            reached = sum(any(r.get('state') == status for r in journeys.get(c.identity, ())) for c, _ in values)
            rows.append((label+' progression '+status, reached, len(group), reached/len(group),
                'Distinct opportunities ever reaching exact retained state; states can overlap'))
        for threshold in (3, 4, 5):
            reached = [(c, o) for c, o in values if any(
                r['count'] is not None and r['count'] >= threshold for r in journeys.get(c.identity, ()))]
            unavailable = sum(o is None or o['prediction_match'] == 'NOT_EVALUABLE' for _, o in reached)
            rows.append((label+f' {threshold}/5 unevaluated advances', unavailable, len(reached),
                unavailable/len(reached) if reached else None, 'Unavailable endpoint is not an analytical non-match'))
            advanced = [(c, o) for c, o in evaluated if any(
                r['count'] is not None and r['count'] >= threshold
                for r in journeys.get(c.identity, ()))]
            false = sum(o['prediction_match'] == 'NOT_MATCHED' for _, o in advanced)
            rows.append((label+f' {threshold}/5 false advance', false, len(advanced),
                false/len(advanced) if advanced else None,
                'Terminal non-match among evaluated opportunities reaching this exact governed count; unavailable excluded and reported separately'))
    return tuple(rows)


def validate_result(cohort, outcome):
    """Readback checks the classification against the retained original baseline.

    Candle/session/contract provenance is verified again by the application from
    exact retained envelopes before completion. This validation does not claim
    a content hash independently establishes source authority.
    """
    from kronos.intraday.probables_v2_persistence import _from_wire
    d, o = cohort.data, outcome.data
    native = {}
    for value in o['native_evidence']:
        v = parse_retained_mcx_candle(json.dumps(value, sort_keys=True, separators=(',',':')).encode()+b'\n')
        native.setdefault((v.canonical_subject_identity, v.source_operation_identity,
            v.timeframe, v.candle_start, v.candle_end), []).append(v)
    expected = evaluate(cohort,
        assessment=None if d['original_assessment'] is None else _from_wire(d['original_assessment']),
        schedule=None if d['schedule'] is None else _from_wire(d['schedule']),
        candle=None if o['terminal_candle'] is None else _from_wire(o['terminal_candle']),
        native=native, now=datetime.fromisoformat(o['evaluated_boundary']), source=o['source'])
    if expected != outcome:
        raise ValueError('WO12_EOD_CLASSIFICATION_INVALID')
