"""Kronos Swing decision engine — Rulebook v2.2 (WO-08 LOCAL-01, WO-11 engine log).

Built only from rules that survived testing on Kite daily data, May 2019 – Nov 2026
(chosen on 2019–22, confirmed on 2023–26). Instruments are traded as stock futures.

  Gate 1  Market: Nifty above its 200-day average (else no new longs)
  Gate 2  Strength: stock in the top 30% of the NSE normalised momentum score
          (6- and 12-month return / 1-year daily volatility, z-scored — the Nifty200 Momentum 30 method)
  Setup   TREND  close above the previous 50-day high
                 exit: close below the 50-day average; stop min(3 ATR, 15%)
          DIP    RSI(2) below 10
                 exit: close above the 5-day average or after 10 sessions; stop 3 ATR
  Shorts  off by default (every short version lost money in testing); switch: shorts_enabled

Verdicts: BUY NOW / BUY READY (with "Waiting for") / WATCH / NO TRADE (with reason).
Pure Python, no network, same input -> same output.
"""
import math
import statistics as st
from dataclasses import dataclass, field


VERSION = "2.2"
LONG, SHORT = "LONG", "SHORT"


@dataclass(frozen=True)
class RulebookV22:
    version: str = VERSION
    regime_sma: int = 200
    mom_top_fraction: float = 0.30
    mom_periods: tuple = (126, 252)
    vol_window: int = 252
    warmup: int = 260
    trend_lookback: int = 50
    trend_exit_sma: int = 50
    trend_stop_atr: float = 3.0
    trend_stop_max_pct: float = 15.0
    trend_ready_atr: float = 1.0          # READY when within 1 ATR below the 50-day high
    dip_rsi_below: float = 10.0
    dip_ready_rsi_below: float = 30.0     # READY when RSI(2) is under 30 (one more down day needed)
    dip_exit_sma: int = 5
    dip_max_sessions: int = 10
    dip_stop_atr: float = 3.0
    atr_period: int = 14
    shorts_enabled: bool = False
    # v2.2 quality mode (Sponsor: at most 5 good trades a month)
    trend_min_ext_atr: float = 3.0        # breakout must close >= 3 ATR above the 50-day average
    dip_enabled: bool = False             # dip trades earn ~0.5% each: not worth one of 5 monthly slots
    max_new_per_month: int = 5


RB22 = RulebookV22()


def _atr(high, low, close, n=14):
    """Wilder's average true range."""
    out = [None] * len(close)
    trs = []
    for i in range(len(close)):
        if i == 0:
            tr = high[0] - low[0]
        else:
            tr = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
        trs.append(tr)
        if i == n - 1:
            out[i] = sum(trs) / n
        elif i >= n:
            out[i] = (out[i - 1] * (n - 1) + tr) / n
    return out




def _sma(c, n):
    out = [None] * len(c)
    run, cnt = 0.0, 0
    for i, x in enumerate(c):
        if x is None:
            run, cnt = 0.0, 0
            continue
        run += x; cnt += 1
        if cnt > n:
            run -= c[i - n]; cnt = n
        if cnt == n:
            out[i] = run / n
    return out


def _rsi2(c):
    """RSI(2) with Wilder smoothing; also returns avg gain/loss to solve for trigger prices."""
    n = len(c)
    rsi, G, L = [None] * n, [None] * n, [None] * n
    g = l = None
    prev = None
    k = 0
    for i, x in enumerate(c):
        if x is None:
            continue
        if prev is not None:
            ch = x - prev
            up, dn = max(ch, 0.0), max(-ch, 0.0)
            k += 1
            if k == 1:
                g, l = up, dn
            else:
                g, l = (g + up) / 2, (l + dn) / 2
            if k >= 2:
                G[i], L[i] = g, l
                rsi[i] = 100.0 if l == 0 else 100 - 100 / (1 + g / l)
        prev = x
    return rsi, G, L


class Market:
    """Daily candles for the stock list plus NIFTY, aligned on NIFTY's dates."""

    def __init__(self, stocks, nifty, rb=RB22):
        self.rb = rb
        self.dates = [x["date"][:10] for x in nifty]
        self.nc = [float(x["close"]) for x in nifty]
        self.n = len(self.dates)
        self.nsma = _sma(self.nc, rb.regime_sma)
        pos = {d: k for k, d in enumerate(self.dates)}
        self.syms = sorted(stocks)
        self.o, self.h, self.l, self.c, self.first = {}, {}, {}, {}, {}
        for s in self.syms:
            rows = {x["date"][:10]: x for x in stocks[s] if x["date"][:10] in pos and float(x["close"]) > 0}
            if not rows:
                raise ValueError(f"{s}: no candles on NIFTY dates")
            first = min(pos[d] for d in rows)
            O, H, Lo, C = [None] * self.n, [None] * self.n, [None] * self.n, [None] * self.n
            last = None
            for k in range(first, self.n):
                x = rows.get(self.dates[k])
                if x is None:          # exchange holiday for the stock only: carry the close
                    O[k] = H[k] = Lo[k] = C[k] = last
                    continue
                O[k], H[k], Lo[k], C[k] = (float(x[f]) for f in ("open", "high", "low", "close"))
                last = C[k]
            self.o[s], self.h[s], self.l[s], self.c[s], self.first[s] = O, H, Lo, C, first
        self.sma50 = {s: _sma(self.c[s], rb.trend_exit_sma) for s in self.syms}
        self.sma5 = {s: _sma(self.c[s], rb.dip_exit_sma) for s in self.syms}
        self.atr = {}
        self.rsi, self.rg, self.rl = {}, {}, {}
        for s in self.syms:
            f = self.first[s]
            a = _atr(self.h[s][f:], self.l[s][f:], self.c[s][f:], rb.atr_period)
            self.atr[s] = [None] * f + a
            self.rsi[s], self.rg[s], self.rl[s] = _rsi2(self.c[s])
        self._mom = {}

    def eligible(self, s, i):
        return i - self.first[s] >= self.rb.warmup

    def momentum(self, i):
        """{symbol: (rank 1 = strongest, score)} for stocks with enough history on day i."""
        if i in self._mom:
            return self._mom[i]
        rb = self.rb
        raw = {}
        for s in self.syms:
            if not self.eligible(s, i):
                continue
            c = self.c[s]
            rets = [math.log(c[j] / c[j - 1]) for j in range(i - rb.vol_window + 1, i + 1)]
            vol = st.pstdev(rets)
            if vol > 0:
                raw[s] = [(c[i] / c[i - p] - 1) / vol for p in rb.mom_periods]
        z = {s: 0.0 for s in raw}
        for k in range(len(rb.mom_periods)):
            xs = [v[k] for v in raw.values()]
            if len(xs) < 2:
                continue
            m, sd = st.mean(xs), st.pstdev(xs)
            for s, v in raw.items():
                z[s] += (v[k] - m) / sd / len(rb.mom_periods) if sd else 0.0
        order = sorted(z, key=z.get, reverse=True)
        self._mom[i] = {s: (r + 1, z[s]) for r, s in enumerate(order)}
        return self._mom[i]


@dataclass
class VerdictV22:
    symbol: str
    date: str
    direction: str
    verdict: str
    setup: str = None                 # TREND / DIP
    reasons: list = field(default_factory=list)
    waiting_for: list = field(default_factory=list)
    facts: dict = field(default_factory=dict)
    plan: dict = field(default_factory=dict)
    rulebook_version: str = VERSION
    priority: float = 0.0

    @property
    def state(self):
        return "NO TRADE" if self.verdict == "NO TRADE" else self.verdict.split()[-1]


def _r(x, nd=2):
    return round(x, nd) if isinstance(x, float) else x


def evaluate(m, symbol, direction, i):
    rb = m.rb
    v = VerdictV22(symbol, m.dates[i], direction, "NO TRADE")
    if direction == SHORT and not rb.shorts_enabled:
        v.reasons.append("Shorts are switched off: every short version lost money in 2019–2026 testing")
        return v
    if direction == SHORT:
        v.reasons.append("Short rules are not defined in Rulebook v2.1")
        return v
    if not m.eligible(symbol, i):
        v.reasons.append("Not enough history (needs about 13 months of candles)")
        return v

    c, h, a = m.c[symbol], m.h[symbol], m.atr[symbol][i]
    close = c[i]
    # Gate 1 — market
    nifty_ok = m.nc[i] > m.nsma[i]
    v.facts["nifty_close"], v.facts["nifty_sma200"] = _r(m.nc[i]), _r(m.nsma[i])
    if not nifty_ok:
        v.reasons.append(f"Market: Nifty {m.nc[i]:.0f} is below its 200-day average {m.nsma[i]:.0f}; no new longs")
    # Gate 2 — strength
    mom = m.momentum(i)
    rank, score = mom[symbol]
    cutoff = max(1, int(len(mom) * rb.mom_top_fraction))
    v.facts.update(momentum_rank=rank, momentum_of=len(mom), momentum_cutoff=cutoff, momentum_score=_r(score))
    if rank > cutoff:
        v.reasons.append(f"Strength: momentum rank {rank} of {len(mom)}; needs to be in the top {cutoff}")

    # Setups (computed even when a gate fails, so the card can show how close it is)
    hi50 = max(h[i - rb.trend_lookback:i])
    sma50, sma5 = m.sma50[symbol][i], m.sma5[symbol][i]
    rsi = m.rsi[symbol][i]
    g, l = m.rg[symbol][i], m.rl[symbol][i]
    dip_trigger = close - max(0.0, 9 * g - l)       # next close at or below this puts RSI(2) under 10
    v.facts.update(close=_r(close), high_50d_prior=_r(hi50), sma50=_r(sma50), sma5=_r(sma5),
                   rsi2=_r(rsi, 1), atr=_r(a), dip_trigger_close=_r(dip_trigger))

    ext = (close - sma50) / a if a else 0.0
    strong_level = sma50 + rb.trend_min_ext_atr * a
    v.facts.update(ext_atr=_r(ext), strong_close_level=_r(strong_level))
    broke = close > hi50
    hi50_prev = max(h[i - 1 - rb.trend_lookback:i - 1])
    fresh = not c[i - 1] > hi50_prev           # today is the first close above the prior 50-day high
    v.facts["fresh_breakout"] = fresh
    trend_now = broke and ext >= rb.trend_min_ext_atr and fresh
    trend_ready = not trend_now and not broke and hi50 - close <= rb.trend_ready_atr * a
    trend_need = max(hi50, strong_level)
    dip_now = rb.dip_enabled and rsi is not None and rsi < rb.dip_rsi_below
    dip_ready = rb.dip_enabled and not dip_now and rsi is not None and rsi < rb.dip_ready_rsi_below
    v.priority = ext                     # used to pick the best when more than the monthly limit qualify

    if v.reasons:
        return v

    if trend_now or dip_now:
        v.setup = "TREND" if trend_now else "DIP"
        v.verdict = "BUY NOW"
    elif trend_ready or dip_ready:
        v.setup = "TREND" if trend_ready else "DIP"
        v.verdict = "BUY READY"
        if trend_ready:
            v.waiting_for.append(f"Trend: a strong close at or above {trend_need:.2f} "
                                 f"(above the 50-day high {hi50:.2f} and 3 ATR over the 50-day average; now {close:.2f})")
        if dip_ready:
            v.waiting_for.append(f"Dip: a close at or below {dip_trigger:.2f} (RSI(2) under 10; now {rsi:.0f})")
    else:
        v.verdict = "WATCH"
        v.waiting_for.append(f"Trend: a strong close at or above {trend_need:.2f}")
        if rb.dip_enabled:
            v.waiting_for.append(f"Dip: a close at or below {dip_trigger:.2f}")

    if v.setup == "TREND":
        risk = min(rb.trend_stop_atr * a, close * rb.trend_stop_max_pct / 100)
        v.plan = {"setup": "TREND", "entry": "next session's open (reference close " + f"{close:.2f})",
                  "stop": _r(close - risk), "risk_pct": _r(risk / close * 100),
                  "exit": f"close below the 50-day average (now {sma50:.2f}); no fixed target",
                  "typical_hold": "weeks to months (tested average about 2 months)"}
    elif v.setup == "DIP":
        risk = rb.dip_stop_atr * a
        v.plan = {"setup": "DIP", "entry": "next session's open (reference close " + f"{close:.2f})",
                  "stop": _r(close - risk), "risk_pct": _r(risk / close * 100),
                  "exit": f"close above the 5-day average (now {sma5:.2f}) or after {rb.dip_max_sessions} sessions",
                  "typical_hold": "a few days (tested average about 4 sessions)"}
    return v


def monthly_selection(candidates, already_this_month, rb=RB22):
    """Pick today's BUY NOW verdicts to act on, best first, without exceeding the monthly limit.

    candidates: today's verdicts; already_this_month: BUY NOW trades already taken this calendar month.
    Returns (selected, skipped); skipped ones are reported as 'monthly limit reached'.
    """
    now = sorted((v for v in candidates if v.state == "NOW"), key=lambda v: -v.priority)
    room = max(0, rb.max_new_per_month - already_this_month)
    return now[:room], now[room:]
