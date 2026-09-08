"""WO-06F Sponsor-approved offline measurements, never admission authority.

VWAP: completed-5M session cumulative typical-price, not tick VWAP. All price
relationships below use explicitly labelled completed closes, never Assessment
Price. Existing SMA arithmetic and five-bar slope definition are reused.
"""
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal, Context, ROUND_HALF_EVEN, localcontext
from functools import wraps

from kronos.intraday.candles import expected_candle_boundaries
from kronos.intraday.contracts import IntradayTimeframe as TF
from kronos.intraday.historical_semantic import GovernedHistoricalCandlePayload
from kronos.intraday.population_measurement import identity
from kronos.intraday.wo10_facts import (
    _sma, WO10_SMA_CALCULATION_IDENTITY, WO10_SMA_PERIODS,
    WO10_SMA_SLOPE_COMPARISON_BARS, WO10_VOLUME_LOOKBACK,
    WO10_VOLUME_LOOKBACK_IDENTITY,
)

POLICY = "WO06F-OFFLINE-TECHNICAL-CONTEXT-V1"
VWAP_POLICY = "WO06F-SPONSOR-TYPICAL-PRICE-COMPLETED-5M-SESSION-VWAP-V1"
NE = "NOT_ESTABLISHED"


class ResearchError(ValueError):
    """Bounded, non-secret research source error."""


def decimal_policy(fn):
    @wraps(fn)
    def call(*args, **kwargs):
        with localcontext(Context(prec=28, rounding=ROUND_HALF_EVEN)):
            return fn(*args, **kwargs)
    return call


def side(a, b):
    return NE if a is None or b is None else "ABOVE" if a > b else "BELOW" if a < b else "AT"


def text(value):
    return None if value is None else str(value)


@dataclass(frozen=True)
class Window:
    subject: str
    timeframe: TF
    boundary: datetime
    operation: str
    schedule: object
    candles: tuple[GovernedHistoricalCandlePayload, ...]

    def __post_init__(self):
        if (type(self.candles) is not tuple or not self.subject or not self.operation
                or type(self.timeframe) is not TF or not isinstance(self.boundary, datetime)
                or self.boundary.utcoffset() is None):
            raise ResearchError("SOURCE_INVALID")
        expected = tuple((x.start, x.end) for x in expected_candle_boundaries(self.schedule, self.timeframe)
                         if x.end <= self.boundary)
        if tuple((c.candle_start, c.candle_end) for c in self.candles) != expected:
            raise ResearchError("COVERAGE_GAP_DUPLICATE_ORDER_OR_FUTURE")
        for c in self.candles:
            if type(c) is not GovernedHistoricalCandlePayload:
                raise ResearchError("CANDLE_TYPE_INVALID")
            replace(c)  # Revalidate immutable source identity and payload integrity.
            if (c.canonical_subject_identity != self.subject or c.timeframe is not self.timeframe
                    or c.observation_boundary != self.boundary
                    or c.source_operation_identity != self.operation
                    or c.market_session_identity != self.schedule.session_id):
                raise ResearchError("SUBJECT_TIMEFRAME_SESSION_OPERATION_BINDING_INVALID")

    def binding(self):
        sources = [[c.candle_identity, c.integrity_identity] for c in self.candles]
        return dict(subject=self.subject, timeframe=self.timeframe.value,
                    boundary=self.boundary.isoformat(), session=self.schedule.session_id,
                    calendar=self.schedule.source_identity, calendar_version=self.schedule.source_version,
                    operation=self.operation, count=len(sources),
                    source_identity=identity("WO06F-CANDLE-SET-", sources),
                    first=self.candles[0].candle_identity if sources else None,
                    last=self.candles[-1].candle_identity if sources else None)


def joined(windows):
    if not windows:
        raise ResearchError("WINDOWS_REQUIRED")
    first = windows[0]
    if any((w.subject, w.timeframe, w.boundary, w.operation) !=
           (first.subject, first.timeframe, first.boundary, first.operation) for w in windows):
        raise ResearchError("MIXED_SERIES")
    candles = tuple(c for w in windows for c in w.candles)
    if any(a.candle_end > b.candle_start for a, b in zip(candles, candles[1:])):
        raise ResearchError("SERIES_ORDER_INVALID")
    if len({c.candle_identity for c in candles}) != len(candles):
        raise ResearchError("DUPLICATE_SOURCE")
    return candles


def native_binding(candles, retained):
    """Exact same acquisition operation and OHLCV. Never borrow current contract.

    Missing native history is unavailable; ambiguous or conflicting evidence is
    rejected. No reference series, continuous construction or roll inference.
    """
    matches = []
    for c in candles:
        possible = retained.get((c.canonical_subject_identity,
                                 c.source_operation_identity.removeprefix("INTRADAY-DISCOVERY-V2-SEMANTIC:"),
                                 c.timeframe, c.candle_start, c.candle_end), ())
        if not possible:
            return dict(state=NE, reason="EXACT_NATIVE_CONTRACT_HISTORY_NOT_RETAINED")
        if len(possible) != 1:
            raise ResearchError("NATIVE_HISTORY_AMBIGUOUS")
        m = possible[0]
        replace(m)
        if (m.canonical_subject_identity != c.canonical_subject_identity
                or m.timeframe is not c.timeframe or m.candle_start != c.candle_start or m.candle_end != c.candle_end
                or m.source_operation_identity != c.source_operation_identity.removeprefix("INTRADAY-DISCOVERY-V2-SEMANTIC:")
                or m.observation_boundary != c.observation_boundary
                or m.domain008_session_identity != c.market_session_identity
                or any(getattr(m, name) != getattr(c, name) for name in ("open", "high", "low", "close", "volume"))):
            raise ResearchError("NATIVE_HISTORY_MISMATCH")
        matches.append(m)
    contracts = {(m.canonical_contract_identity, m.historical_binding_identity) for m in matches}
    if len(contracts) != 1:
        return dict(state=NE, reason="NATIVE_CONTRACT_TRANSITION_NOT_JOINED")
    contract, binding = next(iter(contracts))
    return dict(state="AVAILABLE", contract=contract, binding=binding,
                sources=identity("WO06F-NATIVE-SOURCE-", [m.integrity_identity for m in matches]))


@decimal_policy
def sma(windows):
    candles = joined(windows)
    closes = tuple(c.close for c in candles)
    price = closes[-1] if closes else None
    values = {p: _sma(closes, p) for p in WO10_SMA_PERIODS}
    results = {}
    for p, value in values.items():
        prior = _sma(closes[:-WO10_SMA_SLOPE_COMPARISON_BARS], p)
        delta = value-prior if value is not None and prior is not None else None
        results[str(p)] = dict(value=text(value), availability="AVAILABLE" if value is not None else "INSUFFICIENT_LOOKBACK",
                               price_side=side(price, value), slope_delta=text(delta),
                               slope=side(delta, Decimal(0)), slope_comparison_bars=WO10_SMA_SLOPE_COMPARISON_BARS)
    stack = NE
    if all(v is not None for v in values.values()):
        a, b, c = (values[p] for p in WO10_SMA_PERIODS)
        stack = "STRICT_BULLISH" if price > a > b > c else "STRICT_BEARISH" if price < a < b < c else "MIXED_OR_EQUAL"
    return dict(policy=WO10_SMA_CALCULATION_IDENTITY, bindings=[w.binding() for w in windows],
                count=len(candles), price_role="LAST_COMPLETED_CLOSE_NOT_ASSESSMENT_PRICE",
                price=text(price), price_time=candles[-1].candle_end.isoformat() if candles else None,
                periods=results, strict_stack=stack)


@decimal_policy
def vwap(window, *, volume_bearing):
    if window.timeframe is not TF.FIVE_MINUTES:
        raise ResearchError("VWAP_REQUIRES_5M")
    base = dict(policy=VWAP_POLICY, binding=window.binding(), price_role="LAST_COMPLETED_5M_CLOSE",
                tick_vwap_equivalence="NONE", slope_policy="ADJACENT_COMPLETED_5M_CUMULATIVE_VALUES")
    if not volume_bearing:
        return dict(base, availability="MEANINGFUL_TRADED_VOLUME_NOT_ESTABLISHED", side=NE)
    if not window.candles:
        return dict(base, availability="NO_COMPLETED_CANDLES", side=NE)
    weighted, volume, previous = Decimal(0), 0, None
    for c in window.candles:
        previous = weighted/volume if volume else None
        weighted += ((c.high+c.low+c.close)/Decimal(3))*c.volume
        volume += c.volume
    if not volume:
        return dict(base, availability="ZERO_TOTAL_VOLUME", side=NE)
    value = weighted/volume
    price = window.candles[-1].close
    delta = value-previous if previous is not None else None
    return dict(base, availability="AVAILABLE", value=str(value), volume=volume,
                side=side(price, value), price=str(price), price_time=window.candles[-1].candle_end.isoformat(),
                slope=side(delta, Decimal(0)), slope_delta=text(delta),
                distance=str(price-value), distance_pct=text((price-value)/value*100 if value else None))


@decimal_policy
def volume(window, *, volume_bearing):
    cs = window.candles
    base = dict(policy=WO10_VOLUME_LOOKBACK_IDENTITY, binding=window.binding(),
                consequence="NONE", published_participation="UNCHANGED")
    if not volume_bearing or not cs:
        return dict(base, availability="MEANINGFUL_TRADED_VOLUME_NOT_ESTABLISHED", change=NE)
    prior = cs[-(WO10_VOLUME_LOOKBACK+1):-1]
    usable = len(prior) == WO10_VOLUME_LOOKBACK and all(c.volume > 0 for c in prior)
    mean = sum((Decimal(c.volume) for c in prior), Decimal(0))/len(prior) if usable else None
    return dict(base, availability="AVAILABLE", current=cs[-1].volume,
                change=side(cs[-1].volume, cs[-2].volume if len(cs) >= 2 else None),
                change_policy="IMMEDIATE_PREVIOUS_COMPLETED_VOLUME_COMPARISON_V1",
                rolling_mean=text(mean), ratio=text(Decimal(cs[-1].volume)/mean if mean else None),
                normalization="AVAILABLE" if usable else "INSUFFICIENT_POSITIVE_PRIOR_20", lookback=20)


def movement(window):
    # Exact immediate-neighbour H/L/C relationships, no pivot/break inference.
    cs = window.candles
    if len(cs) < 2:
        return dict(policy="IMMEDIATE_NEIGHBOUR_RELATION_V1", direction=NE)
    relationships = {k: side(getattr(cs[-1], k), getattr(cs[-2], k)) for k in ("high", "low", "close")}
    values = tuple(relationships.values())
    return dict(policy="IMMEDIATE_NEIGHBOUR_RELATION_V1", binding=window.binding(), relationships=relationships,
                direction="LONG" if values == ("ABOVE",)*3 else "SHORT" if values == ("BELOW",)*3 else "NON_DIRECTIONAL")


def comparison(a, b):
    """Agreement of two same-time directional predicates is not independence."""
    directional = {"ABOVE", "BELOW"}
    if a == NE or b == NE:
        return "NOT_ESTABLISHED"
    if a not in directional or b not in directional:
        return "EQUALITY_OR_NON_DIRECTIONAL"
    return "AGREE" if a == b else "CONFLICT"
