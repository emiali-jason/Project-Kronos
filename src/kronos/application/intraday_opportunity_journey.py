"""Read-only considered-cohort journey. WO11 retained model events only.

No candle touch inference, price fallback, acquisition or lifecycle mutation.
Unknown coverage cannot establish a negative hit or an exact market-touch time.
"""
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from kronos.intraday.probables_v2_persistence import _from_wire
from kronos.intraday.wo12_research_contract import digest

UNAVAILABLE = 'NOT_ESTABLISHED'
NOT_EVALUABLE = 'NOT_EVALUABLE'
JOURNEY_VERSION = '1.0.0'
JOURNEY_COLUMNS = (
    'Opportunity ID', 'Trading Date', 'Security', 'Market', 'Exact MCX Contract', 'Direction',
    'WO08 Version', 'Identified At', 'Assessment Price', 'I1', 'I2', 'I3', 'I4', 'I5',
    'Initial Count', 'Original Prediction', 'Original Disposition', 'Original Failure', 'Original Reasons', 'Initial WO09', 'Initial WO09 Direction', 'Initial WO09 Contract',
    'First 4 of 5 At', 'Missing at 4', 'Watch Eligible at 4', 'Watch Started At',
    'Watch Missing', 'Wake Hint Count', 'First Wake Hint At', 'Last Wake Hint At',
    'First 5 of 5 At', 'First Retained 5 Snapshot At', 'First Five Fact', 'Final WO09', 'Final WO09 Direction', 'Final WO09 Contract', 'Final Original Scope WO09', 'WO09 Currentness',
    '4 of 5 Measurement', '5 of 5 Measurement', 'Measurement Authority',
    'Canonical Entry', 'Canonical Stop', 'Canonical Target', 'Future Contract',
    'Future Entry', 'Future Stop', 'Future Target', 'Construction At',
    'Paper Created', 'Paper Class', 'Paper State', 'Entry Met', 'Entry First Met At',
    'Model Entry Price', 'Target Met', 'Target First Met At', 'Stop Met', 'Stop First Met At',
    'First Terminal Event', 'Chronology Coverage', 'Monitoring Gap Count', 'Monitoring Gap References', 'Identified to 4 Seconds',
    'Identified to 5 Seconds', '5 to Entry Seconds', 'Entry to Target Seconds',
    'Entry to Stop Seconds', 'Terminal 5M At', 'Terminal 5M Price',
    'Directional Move Pct', 'EOD Match', 'EOD Reason', 'False Advance 3',
    'False Advance 4', 'False Advance 5', 'Opportunity Identity', 'Consideration Identity',
    'Run Identity', 'Session Identity', 'WO08 Identity', 'WO08 Method',
    'Readiness References', 'Watch References', 'Hint References',
    'Construction References', 'Construction Selection', 'Lifecycle References', 'Other Scope Readiness References', 'Journey Identity',
)


def _at(value):
    if value is None:
        return None
    result = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('WO12_JOURNEY_AWARE_TIME_REQUIRED')
    return result


def _seconds(start, end):
    if start is None or end is None:
        return UNAVAILABLE
    value = (_at(end) - _at(start)).total_seconds()
    return value if value >= 0 else UNAVAILABLE


def _number(value):
    return UNAVAILABLE if value is None else Decimal(str(value))


def _joined(values):
    return '; '.join(sorted({str(v) for v in values if v is not None})) or UNAVAILABLE


def _measurement(document):
    measurement = (document or {}).get('experimental_measurement')
    return _number(None if measurement is None else measurement.get('price'))


def _lifecycle_values(tracks, lifecycle):
    """Use the verified current WO11 graph; ambiguity never resurrects old exits."""
    values = dict.fromkeys(('Entry Met', 'Target Met', 'Stop Met', 'First Terminal Event'), NOT_EVALUABLE)
    values.update({'Paper Created': 'YES' if tracks else 'NO',
        'Paper Class': _joined(t.data['truth_class'] for t in tracks),
        'Paper State': _joined(t.data['state'] for t in tracks),
        'Lifecycle References': _joined(t.identity for t in tracks),
        'Chronology Coverage': 'NO_RETAINED_WO11_TRACK' if not tracks else 'MULTIPLE_RETAINED_TRACKS' if len(tracks) != 1 else 'RETAINED_WO11_MODEL_EVENTS_ONLY'})
    if len(tracks) != 1:
        return values
    d = tracks[0].data
    values['Monitoring Gap Count'] = len(d['gaps'])
    values['Monitoring Gap References'] = _joined(d['gaps'])
    if d['gaps']:
        values['Chronology Coverage'] = 'RETAINED_WO11_MODEL_EVENTS_WITH_MONITORING_GAPS'
    entry, exit_record = d['entry'], d['exit']
    for event in (entry, exit_record):
        if event is not None and lifecycle.load(event['identity']).data != {k:v for k,v in event.items() if k != 'identity'}:
            raise ValueError('WO12_JOURNEY_LIFECYCLE_EVENT_MISMATCH')
    if entry is not None:
        values.update({'Entry Met': 'YES', 'Entry First Met At': entry['at'], 'Model Entry Price': _number(entry['price'])})
    if d['state'] == 'OUTCOME_AMBIGUOUS':
        values['Chronology Coverage'] = 'WO11_OUTCOME_AMBIGUOUS'
        return values
    if exit_record is not None and exit_record['reason'] in {'TARGET', 'STOP_LOSS'}:
        target = exit_record['reason'] == 'TARGET'
        values.update({('Target Met' if target else 'Stop Met'): 'YES',
            ('Target First Met At' if target else 'Stop First Met At'): exit_record['at'],
            'First Terminal Event': 'TARGET_FIRST' if target else 'STOP_FIRST'})
    # No hit remains NOT_EVALUABLE: retained samples do not establish a full path.
    return values


def build_journey_rows(*, cohorts, associations, readiness, outcomes, futures,
                       lifecycle, tracks, pointer_currentness, assessments=None):
    """One row per frozen considered opportunity/method/exact-contract cohort."""
    all_readiness = {r.readiness_identity:r for group in readiness.values() for r in group}
    outcome_by_id = {o.data['consideration_identity']:o.data for o in outcomes}
    opportunities = futures.records('WO10_OPPORTUNITY_V1')
    comparisons = futures.records('WO10_SPONSOR_COMPARISON_V1')
    document_cache = {}
    def document(r):
        identity = r.wo08_identity
        if identity not in document_cache:
            supplied = getattr(r, 'assessment_document', None)
            document_cache[identity] = supplied if supplied is not None else None if assessments is None else (assessments.load(identity).data if hasattr(assessments, 'load') else next(a.data for a in assessments.records() if a.identity == identity))
        return document_cache[identity]
    rows = []
    for cohort in sorted(cohorts, key=lambda c:(c.data['origin_at'],c.data['subject'],c.identity)):
        d = cohort.data
        original = d['original_prediction']
        related = [a.data for a in associations if a.data['opportunity_identity'] == d['opportunity_identity']
            and a.data['subject'] == d['subject'] and a.data['session_identity'] == d['session']
            and {k:a.data[k] for k in ('methodology_identity','methodology_version','methodology_checksum')} == d['methodology']]
        refs = {r['identity'] for a in related for r in a['readiness_references']}
        considered_history = sorted((all_readiness[identity] for identity in refs), key=lambda r:(r.created_at,r.readiness_identity))
        history = []
        for identity in refs:
            r = all_readiness[identity]
            doc = document(r)
            # A later contract must not enter the frozen original contract cohort.
            if d['market'] == 'MCX' and (doc is None or doc.get('exact_mcx_contract_identity') != d['exact_contract']):
                continue
            if d['direction'] is None or r.direction != d['direction']:
                continue
            history.append(r)
        history.sort(key=lambda r:(r.created_at,r.readiness_identity))
        scoped_ids = {r.readiness_identity for r in history}
        scoped_assessments = {r.wo08_identity for r in history}
        related = [a for a in related if a['assessment_identity'] in scoped_assessments]
        four = next((r for r in history if r.satisfied_count == 4), None)
        first_docs = {f['fact_identity']:f for r in history if (f:=getattr(r,'first_five_document',None)) is not None and f['assessment_document']['direction'] == d['direction']}
        first = min(first_docs.values(), key=lambda f:(_at(f['observed_at']),f['fact_identity'])) if first_docs else None
        five = next((r for r in history if r.satisfied_count == 5), None)
        at_four = None if four is None else four.created_at
        at_five = first['observed_at'] if first is not None else None
        bindings = {b['identity']:b for a in related for b in a.get('selective_watch_bindings',()) if b['readiness_identity'] in scoped_ids}
        hints = {h['identity']:h for a in related for h in a.get('advisory_wake_hints',()) if h['binding_identity'] in bindings}
        hint_times = sorted(_at(h['observed_at']) for h in hints.values())
        watch_times = sorted(_at(b['watch_started_at']) for b in bindings.values())
        from kronos.application.intraday_experimental_watch import watch_eligible, is_experimental
        eligible = UNAVAILABLE if four is None or not is_experimental(four) else 'YES' if watch_eligible(four,at=four.created_at) else 'NO'
        plans = [o for o in opportunities if o.data['readiness_identity'] in scoped_ids]
        plan_ids = {o.identity for o in plans}
        constructions = [c for c in comparisons if c.data.get('opportunity_identity') in plan_ids]
        linked_tracks = [t for t in tracks if t.data['intake']['opportunity_identity'] in plan_ids]
        # A lifecycle references its exact construction. Otherwise show the latest
        # retained construction, while keeping every reference available for audit.
        track_comparisons = {t.data['intake'].get('comparison_identity') for t in linked_tracks}
        chosen = [c for c in constructions if c.identity in track_comparisons] if linked_tracks else constructions
        comparison = (chosen[0] if len(linked_tracks) == 1 and len(chosen) == 1 else
            max(chosen,key=lambda c:(_at(c.data['created_at']),c.identity)) if not linked_tracks and chosen else None)
        plan = expression = None
        if comparison is not None:
            plan = futures.load(comparison.data['plan_identity']).data
            expression = futures.load(comparison.data['expression_identity']).data
        original_price = None if d['original_assessment'] is None else _from_wire(d['original_assessment']).assessment_price
        criteria = {} if original is None else {c['criterion_id']:c for c in original['criteria']}
        known = criteria and all(c['state'] in {'SATISFIED','OUTSTANDING','DETERMINISTICALLY_ESTABLISHED','DETERMINISTICALLY_NEGATIVE'} for c in criteria.values())
        eod = outcome_by_id.get(cohort.identity,{})
        match = eod.get('prediction_match',NOT_EVALUABLE)
        highest = max((r.satisfied_count for r in history if r.satisfied_count is not None),default=None)
        values = {'Trading Date':_at(d['origin_at']).astimezone(ZoneInfo('Asia/Kolkata')).date().isoformat(),
            'Security':d['subject'],'Market':d['market'],'Exact MCX Contract':d['exact_contract'] or 'N/A',
            'Direction':d['direction'] or UNAVAILABLE,'WO08 Version':d['methodology']['methodology_version'],
            'Identified At':d['origin_at'],'Assessment Price':_number(original_price),
            'Initial Count':sum(c['state'] in {'SATISFIED','DETERMINISTICALLY_ESTABLISHED'} for c in criteria.values()) if known else UNAVAILABLE,
            'Original Prediction':UNAVAILABLE if original is None else original['direction'],
            'Original Disposition':UNAVAILABLE if original is None else original['disposition'],
            'Original Failure':UNAVAILABLE if original is None else original['failure_reason'],
            'Original Reasons':UNAVAILABLE if original is None else _joined([*original['probables_reasons'],*(c['criterion_id']+':'+','.join(c['reason_codes']) for c in original['criteria'])]),
            'Initial WO09':UNAVAILABLE if not considered_history else considered_history[0].readiness_state.value,
            'Initial WO09 Direction':UNAVAILABLE if not considered_history else considered_history[0].direction,
            'Initial WO09 Contract':UNAVAILABLE if not considered_history else getattr(considered_history[0],'exact_mcx_contract_identity',None) or 'N/A',
            'First 4 of 5 At':at_four,'Missing at 4':UNAVAILABLE if four is None else _joined(c.criterion_id.value+':'+c.state.value for c in four.criteria if c.state.value!='SATISFIED'),
            'Watch Eligible at 4':eligible,'Watch Started At':watch_times[0] if watch_times else None,
            'Watch Missing':_joined(b['missing_criterion'] for b in bindings.values()),
            'Wake Hint Count':len(hints),'First Wake Hint At':hint_times[0] if hint_times else None,'Last Wake Hint At':hint_times[-1] if hint_times else None,
            'First 5 of 5 At':at_five,'First Retained 5 Snapshot At':None if five is None else five.created_at,'First Five Fact':UNAVAILABLE if first is None else first['fact_identity'],
            'Final WO09':UNAVAILABLE if not considered_history else considered_history[-1].readiness_state.value,
            'Final WO09 Direction':UNAVAILABLE if not considered_history else considered_history[-1].direction,
            'Final WO09 Contract':UNAVAILABLE if not considered_history else getattr(considered_history[-1],'exact_mcx_contract_identity',None) or 'N/A',
            'Final Original Scope WO09':UNAVAILABLE if not history else history[-1].readiness_state.value,
            'WO09 Currentness':pointer_currentness.get(cohort.identity) or UNAVAILABLE,
            '4 of 5 Measurement':UNAVAILABLE if four is None else _measurement(document(four)),
            '5 of 5 Measurement':_measurement(first['assessment_document'] if first else None if five is None else document(five)),
            'Measurement Authority':'ANALYTICAL_COMPLETED_5M_CLOSE_NOT_ASSESSMENT_PRICE_OR_ENTRY',
            'Construction At':None if comparison is None else comparison.data['created_at'],
            'Terminal 5M At':eod.get('terminal_at'),'Terminal 5M Price':_number(eod.get('terminal_price')),
            'Directional Move Pct':_number(eod.get('directional_move_pct')),'EOD Match':match,'EOD Reason':eod.get('reason','TERMINAL_VALIDATION_NOT_RETAINED'),
            'Opportunity ID':d['opportunity_id'],'Opportunity Identity':d['opportunity_identity'],'Consideration Identity':cohort.identity,'Run Identity':d['original_run_identity'] or UNAVAILABLE,
            'Session Identity':d['session'],'WO08 Identity':UNAVAILABLE if original is None else original['assessment_identity'],
            'WO08 Method':d['methodology']['methodology_identity'],'Readiness References':_joined(scoped_ids),
            'Watch References':_joined(bindings),'Hint References':_joined(hints),'Construction References':_joined(c.identity for c in constructions),
            'Other Scope Readiness References':_joined(refs-scoped_ids),
            'Construction Selection':'MULTIPLE_TRACKS_NOT_SELECTED' if len(linked_tracks)>1 else 'EXACT_TRACK_COMPARISON' if comparison is not None and linked_tracks else 'LATEST_RETAINED_COMPARISON' if comparison is not None else UNAVAILABLE,
            'Journey Identity':'WO12-JOURNEY-ROW-'+digest({'cohort':cohort.identity,'version':JOURNEY_VERSION})}
        values.update({f'I{i}':criteria.get(f'I{i}',{}).get('state',UNAVAILABLE) for i in range(1,6)})
        for title,key in (('Entry','entry'),('Stop','stop'),('Target','target')):
            values['Canonical '+title] = _number(None if plan is None else plan.get(key))
            values['Future '+title] = _number(None if expression is None else expression.get(key))
        values['Future Contract'] = UNAVAILABLE if expression is None else expression['future'].get('provider_record_identity',expression['future'].get('trading_symbol',UNAVAILABLE))
        values.update(_lifecycle_values(linked_tracks,lifecycle))
        values.update({'Identified to 4 Seconds':_seconds(d['origin_at'],at_four),
            'Identified to 5 Seconds':_seconds(d['origin_at'],at_five),
            '5 to Entry Seconds':_seconds(at_five,values.get('Entry First Met At')),
            'Entry to Target Seconds':_seconds(values.get('Entry First Met At'),values.get('Target First Met At')),
            'Entry to Stop Seconds':_seconds(values.get('Entry First Met At'),values.get('Stop First Met At'))})
        for threshold in (3,4,5):
            values[f'False Advance {threshold}'] = ('NOT_ADVANCED' if highest is not None and highest<threshold else
                NOT_EVALUABLE if highest is None or match==NOT_EVALUABLE else 'YES' if match=='NOT_MATCHED' else 'NO')
        for column, value in tuple(values.items()):
            if column.endswith(' At') and value is not None:
                values[column] = _at(value).astimezone(ZoneInfo('Asia/Kolkata')).isoformat(sep=' ') + ' IST'
        rows.append(tuple(values.get(c,UNAVAILABLE) if values.get(c) is not None else UNAVAILABLE for c in JOURNEY_COLUMNS))
    return tuple(rows)
