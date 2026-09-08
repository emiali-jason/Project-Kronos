"""WO-06E Sponsor-approved CPR research definitions; no production authority.

Inputs to the pure classifiers are explicit research projections of governed
records. They do not manufacture source authority or resolve sessions by date.
The retained-history adapter refuses to manufacture these inputs when absent.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from math import sqrt
from collections import Counter

NOT_ESTABLISHED = "NOT_ESTABLISHED"
POLICY = "WO06E-SPONSOR-CPR-CONTEXT-2026-09-08"


class CprContextError(ValueError):
    """Bounded invalid-source/chronology result."""


def _aware(value):
    return isinstance(value, datetime) and value.utcoffset() is not None


@dataclass(frozen=True)
class Band:
    subject: str
    session: str
    source: str
    available_at: datetime
    lower: Decimal
    upper: Decimal

    def __post_init__(self):
        if (not all(isinstance(s, str) and s.strip() == s and s for s in
                    (self.subject, self.session, self.source))
                or not _aware(self.available_at)
                or any(type(x) is not Decimal or not x.is_finite() or x < 0
                       for x in (self.lower, self.upper)) or self.lower > self.upper):
            raise CprContextError("BAND_INVALID")


def band_context(current, previous, *, previous_session, boundary):
    """Both bounds must move strictly; equal bands satisfy both containments."""
    if not _aware(boundary):
        raise CprContextError("BOUNDARY_INVALID")
    if current is None or previous is None or previous_session is None:
        return dict(direction=NOT_ESTABLISHED, relationships=(NOT_ESTABLISHED,))
    if (type(current) is not Band or type(previous) is not Band
            or current.subject != previous.subject
            or previous.session != previous_session or current.session == previous.session
            or previous.available_at > current.available_at
            or current.available_at > boundary or previous.available_at > boundary):
        raise CprContextError("BAND_SOURCE_OR_CHRONOLOGY_INVALID")
    direction = "MIXED_OR_NOT_DIRECTIONAL"
    if current.lower > previous.lower and current.upper > previous.upper:
        direction = "ASCENDING"
    elif current.lower < previous.lower and current.upper < previous.upper:
        direction = "DESCENDING"
    states = []
    if current.lower >= previous.lower and current.upper <= previous.upper:
        states.append("CURRENT_INSIDE_PREVIOUS")
    if current.lower <= previous.lower and current.upper >= previous.upper:
        states.append("CURRENT_CONTAINS_PREVIOUS")
    if not states:
        if current.lower > previous.upper:
            states.append("NON_OVERLAPPING_ABOVE")
        elif current.upper < previous.lower:
            states.append("NON_OVERLAPPING_BELOW")
        else:
            states.append("OVERLAPPING")
    return dict(direction=direction, relationships=tuple(states))


def price_location(*, lower_relationship=None, upper_relationship=None):
    """Consume existing exact price/bound comparisons, never a substituted price."""
    if lower_relationship is None or upper_relationship is None:
        return NOT_ESTABLISHED
    pair = lower_relationship, upper_relationship
    if pair == ("ABOVE", "ABOVE"):
        return "ABOVE"
    if pair == ("BELOW", "BELOW"):
        return "BELOW"
    if pair in {("AT", "BELOW"), ("ABOVE", "BELOW"), ("ABOVE", "AT"), ("AT", "AT")}:
        return "INSIDE"
    raise CprContextError("PRICE_RELATIONSHIP_INVALID")


@dataclass(frozen=True)
class PriceInterval:
    subject: str
    source: str
    start: datetime
    end: datetime
    low: Decimal
    high: Decimal


def virgin(band, *, active_at, boundary, windows, prices):
    """Windows must be the complete governed active-to-boundary trading schedule.

    No off-session prices or gaps may stand in for complete interval coverage.
    The caller must resolve windows from governance; this function has no clock,
    calendar lookup, historical search or source-acquisition authority.
    """
    if not _aware(boundary):
        raise CprContextError("BOUNDARY_INVALID")
    if band is None or not windows or active_at is None:
        return NOT_ESTABLISHED
    if type(band) is not Band or band.available_at > boundary:
        raise CprContextError("VIRGIN_BAND_INVALID")
    windows = tuple(windows)
    prices = tuple(prices)
    if not _aware(active_at) or windows[0][0] != active_at or active_at < band.available_at:
        raise CprContextError("VIRGIN_ACTIVE_BOUNDARY_INVALID")
    if any(not _aware(s) or not _aware(e) or s >= e or e > boundary
           or s < band.available_at for s, e in windows):
        raise CprContextError("VIRGIN_WINDOW_INVALID")
    if any(a[1] > b[0] for a, b in zip(windows, windows[1:])):
        raise CprContextError("VIRGIN_WINDOW_ORDER_INVALID")
    # Validate timestamps before reading any OHLC range; future data rejects.
    for p in prices:
        if (type(p) is not PriceInterval or not _aware(p.start) or not _aware(p.end)
                or p.start >= p.end or p.end > boundary):
            raise CprContextError("VIRGIN_PRICE_CHRONOLOGY_INVALID")
    if len({p.source for p in prices}) != len(prices):
        raise CprContextError("VIRGIN_DUPLICATE_SOURCE")
    for p in prices:
        if (p.subject != band.subject or not p.source
                or any(type(x) is not Decimal or not x.is_finite() or x < 0
                       for x in (p.low, p.high)) or p.low > p.high
                or sum(s <= p.start and p.end <= e for s, e in windows) != 1):
            raise CprContextError("VIRGIN_PRICE_SOURCE_INVALID")
    for start, end in windows:
        cursor = start
        for p in sorted((p for p in prices if start <= p.start and p.end <= end),
                        key=lambda p: (p.start, p.end)):
            if p.start != cursor:
                return NOT_ESTABLISHED
            cursor = p.end
        if cursor != end:
            return NOT_ESTABLISHED
    return "NO" if any(p.high >= band.lower and p.low <= band.upper for p in prices) else "YES"


def multi_day_narrow(*, sessions, evidence, subject, boundary):
    """Sessions are exact governed consecutive IDs, newest first, never dates.

    Evidence entries: (session, previous_session, subject, available_at,
    narrow_bool, source_identity). Missing entries remain unknown even if a
    supplied entry is non-Narrow. Calendar adjacency is never inferred.
    """
    if len(sessions) not in (2, 3) or len(set(sessions)) != len(sessions) or not _aware(boundary):
        raise CprContextError("NARROW_SEQUENCE_INVALID")
    if any(s not in evidence for s in sessions):
        return NOT_ESTABLISHED
    selected = [evidence[s] for s in sessions]
    for i, (session, predecessor, actual_subject, available_at, narrow, source) in enumerate(selected):
        if (session != sessions[i] or actual_subject != subject or not source
                or not _aware(available_at) or available_at > boundary or type(narrow) is not bool
                or i < len(sessions)-1 and predecessor != sessions[i+1]
                or i > 0 and available_at > selected[i-1][3]):
            raise CprContextError("NARROW_SEQUENCE_SOURCE_INVALID")
    return "YES" if all(e[4] for e in selected) else "NO"


def _pearson(x, y):
    if len(x) < 2:
        return None
    mx, my = sum(x)/len(x), sum(y)/len(y)
    xx, yy = sum((a-mx)**2 for a in x), sum((b-my)**2 for b in y)
    return (sum((a-mx)*(b-my) for a, b in zip(x, y))/sqrt(xx*yy)) if xx and yy else None


def _ranks(values):
    counts = Counter(values)
    rank = 1
    lookup = {}
    for value in sorted(counts):
        lookup[value] = rank + (counts[value]-1)/2
        rank += counts[value]
    return [lookup[v] for v in values]


def width_range_statistics(rows):
    """Descriptive percentages share previous-close denominator; no outcome claim."""
    x = [float(r["total_width_pct"]) for r in rows]
    y = [float(r["prior_range_pct"]) for r in rows]
    if any(not Decimal(str(v)).is_finite() or v < 0 for v in (*x, *y)):
        raise CprContextError("WIDTH_RANGE_INVALID")
    return dict(count=len(rows), pearson=_pearson(x, y), spearman=_pearson(_ranks(x), _ranks(y)))
