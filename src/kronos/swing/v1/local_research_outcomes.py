"""LOCAL-04 v1: retained-session research measurement, never fills or accounting.

The caller supplies an owner-validated immutable original. This module has no
I/O, clock, Provider, model, store or execution capability. Legacy WO-12 horizons
and checkpoints remain unchanged; twenty sessions belongs only to this contract.
"""
from datetime import date, datetime
from decimal import Decimal
from kronos.swing.v1.prospective_research import (
    IST, GovernedCalendar, GovernedSession, FollowupCandle, _digest,
)

CONTRACT = 'KRONOS-SWING-LOCAL-OUTCOMES-1.0'
HORIZONS = (1, 3, 5, 10, 20)
WINDOWS = {'SHORT': 3, 'MEDIUM': 10, 'LONGER': 20}
AUTHORITY = 'RETAINED_RESEARCH_MEASUREMENT_NO_FILL_PNL_OR_TRADING'


def stamp(raw):
    value = datetime.fromisoformat(raw)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('LOCAL_OUTCOME_TIMESTAMP_INVALID')
    return value


def number(raw):
    if isinstance(raw, bool):
        raise ValueError('LOCAL_OUTCOME_PRICE_INVALID')
    value = Decimal(str(raw))
    if not value.is_finite() or value <= 0:
        raise ValueError('LOCAL_OUTCOME_PRICE_INVALID')
    return value


def metric(value):
    return str(value.quantize(Decimal('0.000001')))


def calendar_window(records, signal, as_of, count):
    """Require a complete retained sequence; never infer weekday sessions."""
    start = signal.astimezone(IST).date()
    candidates = []
    for r in records:
        r.__post_init__()
        d = r.data
        if d['market'] != 'NSE' or stamp(d['observed_at']) > as_of:
            continue
        sessions = tuple(GovernedSession(i, 'NSE', date.fromisoformat(day), stamp(o), stamp(c))
                         for i, day, o, c in d['sessions'])
        cal = GovernedCalendar('NSE', d['source_identity'], d['source_version'],
                              stamp(d['observed_at']), date.fromisoformat(d['complete_from']),
                              date.fromisoformat(d['complete_through']), sessions)
        if cal.complete_from <= start:
            candidates.append((r, cal))
    if not candidates:
        return 'UNAVAILABLE', 'GOVERNED_CALENDAR_UNAVAILABLE', (), ()
    # Inconsistent overlapping sequences cannot establish a preferred calendar.
    for _, a in candidates:
        for _, b in candidates:
            lo, hi = max(a.complete_from, b.complete_from), min(a.complete_through, b.complete_through)
            aa = tuple(s for s in a.sessions if lo <= s.trading_date <= hi)
            bb = tuple(s for s in b.sessions if lo <= s.trading_date <= hi)
            if aa != bb:
                return 'UNAVAILABLE', 'CALENDAR_CONTRADICTION', (), tuple(r.identity for r, _ in candidates)
    r, cal = max(candidates, key=lambda pair:(pair[1].complete_through, pair[1].observed_at, pair[0].identity))
    sessions = tuple(s for s in cal.sessions if start < s.trading_date <= cal.complete_through)
    if len(sessions) < count:
        return 'UNAVAILABLE', 'CALENDAR_HORIZON_NOT_COVERED', (), (r.identity,)
    window = sessions[:count]
    if window[-1].closes_at > as_of:
        return 'PENDING', 'GOVERNED_SESSION_NOT_COMPLETED', window, (r.identity,)
    return 'OBSERVED', None, window, (r.identity,)


def candle_window(records, exact_contract, sessions, as_of):
    """Select revisions only from the retained cut, preserving source ancestry."""
    selected = []
    all_refs = []
    for session in sessions:
        available = []
        for r in records:
            r.__post_init__()
            d = r.data
            if (d['exact_contract_identity'] != exact_contract or d['session_identity'] != session.identity
                    or stamp(d['retrieved_at']) > as_of):
                continue
            # Legacy records may predate the explicit basis flag. Missing is
            # unverified here, never a rewrite or invented positive assertion.
            raw = {k: d[k] for k in FollowupCandle.__dataclass_fields__ if k != 'price_basis_verified'}
            raw['price_basis_verified'] = d.get('price_basis_verified', False)
            raw['retrieved_at'] = stamp(raw['retrieved_at'])
            FollowupCandle(**raw)
            if raw['retrieved_at'] < session.closes_at:
                return 'CANDLE_CAPTURE_BEFORE_SESSION_CLOSE', (), tuple(all_refs + [r.identity])
            available.append(r)
        available.sort(key=lambda r:(stamp(r.data['retrieved_at']), r.identity))
        previous = None
        previous_capture = None
        for r in available:
            if (r.data['supersedes_source_identity'] != previous or previous_capture is not None
                    and stamp(r.data['retrieved_at']) <= previous_capture):
                return 'CANDLE_REVISION_UNRESOLVED', (), tuple(all_refs + [x.identity for x in available])
            previous = r.data['source_identity']
            previous_capture = stamp(r.data['retrieved_at'])
        all_refs.extend(r.identity for r in available)
        if not available:
            return 'EXACT_COMPLETED_CANDLE_UNAVAILABLE', (), tuple(all_refs)
        selected.append(available[-1])
    if not all(r.data['coverage_complete'] for r in selected):
        return 'CANDLE_COVERAGE_INCOMPLETE', (), tuple(all_refs)
    return None, tuple(selected), tuple(all_refs)


def scenario_touch(scenario, candles):
    """Coarse candle touches, not activation/fill simulation or realized R."""
    empty = dict(entry_session=None, terminal_session=None, entry_touch=False,
                 target_touch=False, invalidation_touch=False, realized_rr=None, realized_pnl=None)
    if scenario['state'] != 'AVAILABLE':
        return dict(empty, status='UNAVAILABLE', reason=scenario['reason'])
    low, high = (number(scenario['entry_zone'][k]) for k in ('low', 'high'))
    stop = number(scenario['stop_reference']['value'])
    direction = scenario['direction']
    target = number(scenario['target_zone']['low' if direction == 'LONG' else 'high'])
    if direction not in {'LONG', 'SHORT'} or low > high or not (
            stop < low <= high < target if direction == 'LONG' else target < low <= high < stop):
        raise ValueError('LOCAL_OUTCOME_SCENARIO_GEOMETRY_INVALID')
    entered = False
    for candle in candles:
        d = candle.data
        lo, hi = number(d['low']), number(d['high'])
        entry = lo <= high and hi >= low
        stop_touch = lo <= stop if direction == 'LONG' else hi >= stop
        target_touch = hi >= target if direction == 'LONG' else lo <= target
        if not entered and not entry:
            continue
        same_entry_candle = not entered
        if same_entry_candle:
            entered = True
            empty.update(entry_touch=True, entry_session=d['session_identity'])
        if stop_touch or target_touch:
            empty.update(target_touch=target_touch, invalidation_touch=stop_touch,
                         terminal_session=d['session_identity'])
            if same_entry_candle or stop_touch and target_touch:
                return dict(empty, status='AMBIGUOUS', reason='INTRACANDLE_ORDER_NOT_ESTABLISHED')
            return dict(empty, status='TARGET_TOUCH' if target_touch else 'INVALIDATION_TOUCH',
                        reason='LEVEL_TOUCH_ONLY_ACTIVATION_AND_FILL_NOT_ESTABLISHED')
    return dict(empty, status='ENTRY_TOUCH_ONLY' if entered else 'ENTRY_NOT_REACHED',
                reason='ENTRY_WINDOW_EXPIRED_NO_ASSUMED_FILL')


def measure(original, input_body, result, calendars, candles, *, as_of, origin=None, basis=None):
    """Matched Native/Local research cohort, clocked at original completion."""
    signal = stamp(original.data['completed_at'])
    if as_of.tzinfo is None or as_of < signal:
        return None
    binding = result['binding']
    daily = next(f for f in input_body['summary']['frames'] if f['timeframe'] == '1D')
    reference = number(daily['values']['close'])
    if stamp(daily['observed_boundary']) > signal or stamp(input_body['information_cutoff']) > signal:
        raise ValueError('LOCAL_OUTCOME_REFERENCE_FROM_FUTURE')
    exact = None
    if origin is not None and origin.data.get('contract_binding') is not None:
        origin.__post_init__()
        d = origin.data
        if (d['origin_run_identity'] != binding['run_identity']
                or d['origin_assessment_sha256'] != binding['assessment_sha256']
                or d['market'] != 'NSE' or d['contract_binding']['canonical_instrument'] != binding['instrument']
                or d['direction'] != binding['direction']):
            raise ValueError('LOCAL_OUTCOME_ORIGIN_BINDING_INVALID')
        exact = d['exact_contract_identity']
    overall = result['thesis']['overall']
    cohort = ('LOCAL_ACCEPTED' if overall['disposition'] == 'SUPPORT' else
              'LOCAL_REJECTED' if overall['disposition'] in {'REJECT', 'CHALLENGE'} else 'LOCAL_ABSTAINED')
    rows, cache, refs, basis_refs = [], {}, {original.identity}, []
    if origin is not None: refs.add(origin.identity)
    for count in HORIZONS:
        state, reason, sessions, cal_refs = calendar_window(calendars, signal, as_of, count)
        refs.update(cal_refs)
        window = ()
        if exact is None:
            state, reason = 'UNAVAILABLE', 'EXACT_RESEARCH_ORIGIN_UNAVAILABLE'
        elif state == 'OBSERVED':
            reason, window, candle_refs = candle_window(candles, exact, sessions, as_of)
            refs.update(candle_refs)
            if reason:
                state = 'UNAVAILABLE'
            else:
                basis_state, basis_identity = (None, None) if basis is None else basis(
                    origin, signal.astimezone(IST).date(), sessions[-1].trading_date, as_of)
                if basis_identity is not None: basis_refs.append(basis_identity)
                if any(c.data['corporate_action'] for c in window) or basis_state == 'AFFECTED':
                    state, reason = 'UNAVAILABLE', 'CORPORATE_ACTION_COMMON_BASIS_UNAVAILABLE'
                elif basis_state == 'UNKNOWN' or (basis_state != 'VERIFIED_NO_ACTION'
                        and not all(c.data.get('price_basis_verified', False) for c in window)):
                    state, reason = 'UNAVAILABLE', 'PRICE_BASIS_UNVERIFIED'
        cache[count] = (state, reason, window)
        raw = None if state != 'OBSERVED' else (number(window[-1].data['close']) / reference - 1) * 100
        for name, direction in (('NATIVE_PAIRED', binding['direction']), (cohort, overall['direction'])):
            adjusted = None if raw is None or direction not in {'LONG', 'SHORT'} else raw * (1 if direction == 'LONG' else -1)
            favourable = adverse = None
            if adjusted is not None:
                top = max(number(c.data['high']) for c in window)
                bottom = min(number(c.data['low']) for c in window)
                favourable = max(Decimal(0), (top/reference-1)*100 if direction == 'LONG' else (1-bottom/reference)*100)
                adverse = min(Decimal(0), (bottom/reference-1)*100 if direction == 'LONG' else (1-top/reference)*100)
            rows.append(dict(horizon_sessions=count, cohort=name, direction=direction,
                status=state if direction in {'LONG', 'SHORT'} else 'ABSTAINED', reason=reason,
                due_session=None if not sessions else sessions[-1].identity,
                direction_adjusted_pct=None if adjusted is None else metric(adjusted),
                candle_mfe_pct=None if favourable is None else metric(favourable),
                candle_mae_pct=None if adverse is None else metric(adverse),
                result=None if adjusted is None else 'WITH_DIRECTION' if adjusted > 0 else 'AGAINST_DIRECTION' if adjusted < 0 else 'UNCHANGED'))
    scenarios = []
    for s in result['thesis']['scenarios']:
        state, reason, window = cache[WINDOWS[s['horizon']]]
        measured = (scenario_touch(s, window) if state == 'OBSERVED' else
                    dict(status=state, reason=reason, entry_touch=None, target_touch=None,
                         invalidation_touch=None, entry_session=None, terminal_session=None,
                         realized_rr=None, realized_pnl=None))
        scenarios.append(dict(horizon=s['horizon'], kind=s['kind'], direction=s['direction'],
            structural_radius=s['structural_radius'], entry_window_sessions=WINDOWS[s['horizon']],
            theoretical_rr=None if s['risk_reward'] is None else s['risk_reward']['conservative_ratio'],
            **measured))
    body = dict(contract=CONTRACT, original_identity=original.identity,
        instrument=binding['instrument'], exact_contract_identity=exact, signal_at=signal.isoformat(),
        reference_price=str(reference), reference_observed_at=daily['observed_boundary'],
        reference_rule='RETAINED_1D_CLOSE_NOT_ENTRY_PRICE',
        clock_rule='POST_ORIGINAL_COMPLETION_DATE_GOVERNED_SESSIONS',
        cohort_rule='ONE_ORIGINAL_PER_MATCHED_PAIR_NOT_INDEPENDENT_SECURITY_SAMPLES',
        native_direction=binding['direction'], local_direction=overall['direction'],
        local_disposition=overall['disposition'], method_version=result['method_version'],
        direction=rows, scenarios=scenarios, source_records=sorted(refs), basis_identities=sorted(set(basis_refs)),
        authority=AUTHORITY, win_probability=None,
        limitations=['RETAINED_ASSESSMENTS_ONLY_UNSCANNED_UNIVERSE_UNAVAILABLE',
                     'CANDLE_EXCURSIONS_NOT_POSITION_MFE_MAE', 'NO_FILLS_FEES_PNL_OR_CALIBRATED_PROBABILITY'])
    return dict(body, identity=_digest(body))


def aggregate(outcomes):
    """Explicit observation denominators; no probability or security independence."""
    groups = {}
    for o in outcomes:
        for row in o['direction']:
            key = (row['horizon_sessions'], row['cohort'], o['method_version'])
            g = groups.setdefault(key, dict(horizon_sessions=key[0], cohort=key[1], method_version=key[2], observations=0,
                observed=0, pending=0, unavailable=0, abstained=0, with_direction=0,
                against_direction=0, unchanged=0, observed_missed_native=0, native_disagreements=0, instruments=set()))
            g['observations'] += 1; g['instruments'].add(o['instrument'])
            g[{'OBSERVED':'observed','PENDING':'pending','UNAVAILABLE':'unavailable','ABSTAINED':'abstained'}[row['status']]] += 1
            if row['result']: g[row['result'].lower()] += 1
            if o['local_direction'] in {'LONG', 'SHORT'} and o['local_direction'] != o['native_direction']:
                g['native_disagreements'] += 1
            if row['cohort'] == 'NATIVE_PAIRED' and o['local_disposition'] in {'REJECT', 'CHALLENGE'} and row['result'] == 'WITH_DIRECTION':
                g['observed_missed_native'] += 1
    return tuple(dict(**{k:v for k,v in g.items() if k != 'instruments'},
                      distinct_instruments=len(g['instruments']), win_probability=None)
                 for _,g in sorted(groups.items()))


def scenario_counts(outcomes):
    groups = {}
    for o in outcomes:
        for s in o['scenarios']:
            key = (o['method_version'], s['horizon'], s['kind'], s['direction'], s['structural_radius'])
            g = groups.setdefault(key, dict(method_version=key[0], horizon=key[1], setup=key[2],
                direction=key[3], structural_radius=key[4], observations=0, observed=0, pending=0,
                unavailable=0, ambiguous=0, entry_not_reached=0, entry_touch_only=0,
                target_touch=0, invalidation_touch=0))
            g['observations'] += 1
            status = s['status']
            g[status.lower()] += 1
            if status not in {'PENDING', 'UNAVAILABLE'}: g['observed'] += 1
    return tuple(g for _,g in sorted(groups.items()))
