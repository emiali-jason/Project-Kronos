"""Context-specific Intraday presentation; never analytical or event authority."""
CRITERION_NAMES = {'I1': 'Direction Support', 'I2': 'Follow-through',
                   'I3': 'Path Clearance', 'I4': 'Structural Quality', 'I5': 'Extension'}


def opportunity_label(card):
    """INT-D attention vocabulary over an already validated WO09 card.

    A score alone never overrides a hard gate or unavailable readiness.
    This is presentation only; it neither evaluates criteria nor grants work.
    """
    if card is None or card.source_authority != 'WO08' or card.monitorability_state != 'CURRENT':
        return None
    if card.score == '3 / 5' and card.readiness_state == 'NEAR_READY':
        return 'NEAR READY'
    prefix = {'LONG': 'BUY', 'SHORT': 'SELL'}.get(card.direction)
    if prefix and card.score == '4 / 5' and card.readiness_state == prefix + '_READY':
        return 'READY'
    if prefix and card.score == '5 / 5' and card.readiness_state == prefix + '_NOW':
        return 'NOW'
    return None


def security_name(subject):
    for prefix in ('NSE-EQ-', 'NSE-INDEX-', 'NSE-', 'MCX-SUBJECT-'):
        if subject.startswith(prefix):
            return subject[len(prefix):].replace('-', ' ')
    return subject


def waiting_for(criteria):
    if isinstance(criteria, str):
        rows = [part.strip().split(':', 1) for part in criteria.split(',') if ':' in part]
    else:
        rows = [(c.get('criterion_id', c.get('criterion')), c['state']) for c in criteria]
    if not rows:
        return 'Assessment detail unavailable'
    missing = [CRITERION_NAMES.get(code, code) for code, state in rows
               if state not in {'SATISFIED', 'DETERMINISTICALLY_ESTABLISHED'}]
    return ', '.join(missing) if missing else 'No outstanding criteria'


def criterion_explanation(code, direction):
    if direction not in {'LONG', 'SHORT'} and code in {'I2', 'I3'}:
        return 'An admitted LONG or SHORT direction is required before these direction-specific conditions can be assessed.'
    long = direction == 'LONG'
    if code == 'I2':
        return ('Two consecutive completed 5-minute candles after the qualification candle: '
                + ('first close above its high, second close above the first close, and second low above the pullback low.' if long else
                   'first close below its low, second close below the first close, and second high below the pullback high.'))
    if code == 'I3':
        return ('The latest completed 5-minute close must remain ' + ('below' if long else 'above')
                + ' the prior impulse extreme, with no governed level in the path. '
                'A level at the close blocks; the impulse endpoint is excluded. The complete retained level population is required.')
    return {'I1': 'Completed 1-hour regime and normal 15-minute structure support the inherited direction.',
            'I4': 'Every completed 15-minute candle after pullback confirmation must preserve the pullback extreme.',
            'I5': 'The latest completed 5-minute close must lie strictly between the pullback and prior impulse extremes.'}.get(code, '')


def monitoring_text(projection):
    return projection['state'] + ' · ' + projection['reason']


def lifecycle_monitoring(state):
    return {'LIVE': ('ACTIVE', 'Lifecycle observer established.'),
            'IDLE': ('INACTIVE', 'Lifecycle monitoring is not running.'),
            'NOT_REQUIRED': ('INACTIVE', 'Monitoring is not required for this event.'),
            'INTERRUPTED': ('UNAVAILABLE', 'Lifecycle monitoring was interrupted.')}.get(state,
            ('UNAVAILABLE', 'Authoritative monitoring state is unavailable.'))


def exclusion_reason(code):
    # These are the actual admission/evidence dispositions, not research buckets.
    return {'PROBABLES_NOT_ADMITTED': 'Admission requirements were not met',
            'REQUIRED_CRITERIA_UNAVAILABLE': 'Required assessment evidence is unavailable',
            'MANDATORY_EVIDENCE_UNAVAILABLE': 'Required source evidence is unavailable',
            'PROBABLES_UNAVAILABLE': 'Admission evidence is unavailable',
            'ASSESSMENT_UNAVAILABLE': 'Assessment evidence is unavailable',
            'ASSESSMENT_ESTABLISHED': 'Retained assessment outside the current eligible population',
            'NATIVE_SELECTION_UNAVAILABLE': 'Native structure evidence is unavailable',
            'DIRECTION_CONFLICT': 'Directional evidence conflicts'}.get(code, 'Governed exclusion — see its exact evidence')
