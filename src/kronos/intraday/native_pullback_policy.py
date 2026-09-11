"""Sponsor-commissioned prospective PULLBACK-only policy; no geometry arithmetic."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from itertools import product
from kronos.intraday.wo10_futures_contract import digest
from kronos.intraday.historical_semantic import GovernedHistoricalCandlePayload

POLICY_ID = "KRONOS-INTRADAY-NATIVE-STRUCTURAL-SELECTION-POLICY"
VERSION = "1.0.0"
RULES = {
    "identity": POLICY_ID, "version": VERSION, "programme": "KRONOS-INTRADAY-PROSPECTIVE-PROGRAMME-V2",
    "outputs": ["PULLBACK", "NOT_ESTABLISHED"], "breakout": "NOT_COMMISSIONED_V1",
    "timeframe": "15M", "pivot": "STRICT_IMMEDIATE_NEIGHBOURS_RIGHT_COMPLETED",
    "long": "L0-H1-L2-Q;H1>L0;L2>L0;Q.close>previous.high",
    "short": "H0-L1-H2-Q;L1<H0;H2<H0;Q.close<previous.low",
    "qualification": "FIRST_COMPLETED_CANDLE_STRICTLY_AFTER_PULLBACK_CONFIRMATION",
    "invalidation": "ORIGIN_BREACH_OR_EQUALITY_AFTER_ORIGIN_THROUGH_QUALIFICATION",
    "selection": "MAX_QUALIFICATION_COMPLETION;DISTINCT_IDENTITIES_TIED_FAIL_CLOSED",
    "targets": ["SETUP_NATIVE_TARGET", "PDH_PDL", "CLASSIC_PIVOTS", "CURRENT_SESSION_EXTREMES", "GOVERNED_15M_BARRIERS"],
    "target_resolution": "EXISTING_WO13_NEAREST_FORWARD_CONSTRAINT",
    "effective": "NEW_NATIVE_PUBLICATION_ONLY_NO_BACKFILL",
    "mcx": "SAME_EXACT_ACTIVE_CONTRACT_AND_ROLL", "natgas": "HELD",
}
CHECKSUM = digest(RULES)
APPROVED_POLICY = (POLICY_ID, VERSION, CHECKSUM)

class Reason(StrEnum):
    NO_CYCLE = "NO_CONFIRMED_STRUCTURAL_CYCLE"
    ORIGIN = "PULLBACK_ORIGIN_NOT_ESTABLISHED"
    IMPULSE = "PRIOR_IMPULSE_NOT_ESTABLISHED"
    PULLBACK = "PULLBACK_EXTREME_NOT_ESTABLISHED"
    RESUMPTION = "RESUMPTION_NOT_ESTABLISHED"
    INVALIDATED = "STRUCTURAL_CYCLE_INVALIDATED"
    AMBIGUOUS = "STRUCTURAL_CYCLE_AMBIGUOUS"
    TARGETS = "TARGET_SOURCE_POPULATION_INCOMPLETE"
    BREAKOUT = "BREAKOUT_SELECTOR_NOT_COMMISSIONED_V1"
    INTEGRITY = "SOURCE_INTEGRITY_INVALID"
    SESSION = "SOURCE_SESSION_MISMATCH"
    DIRECTION = "SOURCE_DIRECTION_MISMATCH"
    BOUNDARY = "SOURCE_ANALYSIS_BOUNDARY_MISMATCH"
    MCX = "MCX_CONTRACT_BINDING_INVALID"

@dataclass(frozen=True)
class Pivot:
    identity: str
    kind: str
    index: int
    candle_identity: str
    confirmation_identity: str
    confirmation_end: datetime
    price: Decimal

@dataclass(frozen=True)
class Cycle:
    identity: str
    origin: Pivot
    impulse: Pivot
    pullback: Pivot
    qualification_identity: str
    qualification_index: int
    qualification_end: datetime

def confirmed_pivots(candles):
    """Same strict three-candle predicate as structure._local_pivots."""
    result = []
    for i in range(1, len(candles)-1):
        a, b, c = candles[i-1:i+2]
        for kind in ("HIGH", "LOW"):
            values = [getattr(x, kind.lower()) for x in (a, b, c)]
            qualifies = values[1] > max(values[0], values[2]) if kind == "HIGH" else values[1] < min(values[0], values[2])
            if qualifies:
                identity = "NATIVE-PIVOT-" + digest(dict(kind=kind, sources=[x.candle_identity for x in (a,b,c)],
                    integrities=[x.integrity_identity for x in (a,b,c)], policy="IMMEDIATE_NEIGHBOUR_RELATION_V1"))
                result.append(Pivot(identity, kind, i, b.candle_identity, c.candle_identity, c.candle_end, values[1]))
    return tuple(result)

def select_cycle(candles, *, subject, direction, session, boundary):
    """Pure prospective selector. Enumerate lawful cycles; never optimize geometry."""
    if direction not in {"LONG", "SHORT"}:
        return None, (Reason.DIRECTION.value,)
    candles = tuple(candles)
    try:
        for candle in candles:
            if type(candle) is not GovernedHistoricalCandlePayload:
                return None, (Reason.INTEGRITY.value,)
            candle.__post_init__()
            if candle.canonical_subject_identity != subject:
                return None, (Reason.INTEGRITY.value,)
            if candle.market_session_identity != session:
                return None, (Reason.SESSION.value,)
            if (candle.timeframe.value != "15M" or candle.completion_state != "COMPLETE"
                    or candle.candle_end > boundary or candle.observation_boundary != boundary):
                return None, (Reason.BOUNDARY.value,)
        if len({c.candle_identity for c in candles}) != len(candles):
            return None, (Reason.INTEGRITY.value,)
        if any(a.candle_end != b.candle_start for a,b in zip(candles,candles[1:])):
            return None, (Reason.INTEGRITY.value,)
    except (ValueError, AttributeError, TypeError):
        return None, (Reason.INTEGRITY.value,)
    pivots = confirmed_pivots(candles)
    origin_kind, impulse_kind = ("LOW","HIGH") if direction == "LONG" else ("HIGH","LOW")
    origins = [p for p in pivots if p.kind == origin_kind]
    impulses = [p for p in pivots if p.kind == impulse_kind]
    if not origins:
        return None, (Reason.NO_CYCLE.value, Reason.ORIGIN.value)
    if not any(o.index < i.index for o,i in product(origins,impulses)):
        return None, (Reason.IMPULSE.value,)
    triples = [(o,i,p) for o,i,p in product(origins,impulses,origins) if o.index < i.index < p.index]
    if not triples:
        return None, (Reason.PULLBACK.value,)
    candidates, invalidated = [], False
    for o,i,p in triples:
        if not (i.price > o.price and p.price > o.price if direction == "LONG" else i.price < o.price and p.price < o.price):
            invalidated = True
            continue
        for q in range(o.index+1, len(candles)):
            c = candles[q]
            if (c.low <= o.price if direction == "LONG" else c.high >= o.price):
                invalidated = True
                break
            if q <= p.index+1:
                continue
            previous = candles[q-1]
            if (c.close > previous.high if direction == "LONG" else c.close < previous.low):
                identity = "NATIVE-STRUCTURAL-CYCLE-" + digest(dict(subject=subject,direction=direction,session=session,
                    origin=o.identity,impulse=i.identity,pullback=p.identity,qualification=c.candle_identity,
                    analysis_boundary=boundary,policy_identity=POLICY_ID,policy_version=VERSION))
                candidates.append(Cycle(identity,o,i,p,c.candle_identity,q,c.candle_end))
                break
    if not candidates:
        return None, ((Reason.INVALIDATED if invalidated else Reason.RESUMPTION).value,)
    newest = max(c.qualification_end for c in candidates)
    tied = {c.identity:c for c in candidates if c.qualification_end == newest}
    if len(tied) != 1:
        return None, (Reason.AMBIGUOUS.value,)
    return next(iter(tied.values())), ()
