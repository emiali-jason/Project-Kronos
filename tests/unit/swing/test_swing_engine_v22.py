import json, math, os
import pytest
from kronos.swing.engine_v22 import Market, evaluate, RulebookV22, LONG, SHORT, _rsi2

def make(n=420, drift=0.002, amp=0.01, base=100.0, period=3.0, start=0):
    out, prev = [], base
    for i in range(n):
        c = base * math.exp(drift * i) * (1 + amp * math.sin(i / period))
        out.append({"date": f"D{i + start:04d}", "open": prev, "high": max(prev, c) * 1.005,
                    "low": min(prev, c) * 0.995, "close": c, "volume": 1e6})
        prev = c
    return out

def uni(stocks=None, nifty=None, **kw):
    stocks = stocks or {f"S{k}": make(drift=0.0005 * k) for k in range(10)}
    return Market(stocks, nifty or make(drift=0.0008), RulebookV22(**kw))

def test_shorts_off_by_default():
    m = uni(); v = evaluate(m, "S9", SHORT, m.n - 1)
    assert v.verdict == "NO TRADE" and "switched off" in v.reasons[0]

def test_market_gate():
    m = uni(nifty=make(drift=-0.002)); v = evaluate(m, "S9", LONG, m.n - 1)
    assert any("200-day" in r for r in v.reasons)

def test_momentum_gate_blocks_weak_stock():
    m = uni(); v = evaluate(m, "S0", LONG, m.n - 1)
    assert any("momentum rank" in r for r in v.reasons)
    assert v.facts["momentum_rank"] == 10

def test_strongest_stock_passes_gates_and_has_a_plan_when_now_or_ready():
    m = uni(); seen = set()
    for i in range(300, m.n):
        v = evaluate(m, "S9", LONG, i); seen.add(v.state)
        assert not v.reasons
        if v.state in ("NOW", "READY"):
            assert v.plan["stop"] < v.facts["close"] and v.setup in ("TREND", "DIP")
        if v.state == "READY":
            assert v.waiting_for
    assert "NOW" in seen

def test_trend_stop_capped_at_15pct():
    m = uni(trend_stop_atr=100.0)
    for i in range(300, m.n):
        v = evaluate(m, "S9", LONG, i)
        if v.setup == "TREND":
            assert v.plan["risk_pct"] <= 15.0 + 1e-9
            return
    pytest.fail("no TREND setup found")

def test_dip_trigger_price_really_triggers():
    c = [100, 101, 102, 101.5, 103, 102, 101]
    rsi, G, L = _rsi2(c)
    i = len(c) - 1
    trig = c[i] - max(0.0, 9 * G[i] - L[i])
    rsi2, _, _ = _rsi2(c + [trig - 0.01])
    rsi3, _, _ = _rsi2(c + [trig + 0.5])
    assert rsi2[-1] < 10 <= rsi3[-1]

def test_late_listing_waits_for_history():
    stocks = {"OLD": make(), "NEW": make(n=200, start=220)}
    m = Market(stocks, make(), RulebookV22())
    v = evaluate(m, "NEW", LONG, m.n - 1)
    assert "history" in v.reasons[0]

def test_deterministic():
    m1, m2 = uni(), uni()
    assert evaluate(m1, "S9", LONG, 400).__dict__ == evaluate(m2, "S9", LONG, 400).__dict__

def test_v22_quality_and_monthly_limit():
    from kronos.swing.engine_v22 import monthly_selection, VerdictV22
    m = uni()
    for i in range(300, m.n):
        v = evaluate(m, "S9", LONG, i)
        if v.state == "NOW":
            assert v.setup == "TREND" and v.facts["ext_atr"] >= 3.0
    vs = []
    for k, p in enumerate([1.0, 5.0, 3.0, 4.0]):
        x = VerdictV22(f"X{k}", "D", LONG, "BUY NOW"); x.priority = p; vs.append(x)
    sel, skip = monthly_selection(vs, already_this_month=3)
    assert [x.priority for x in sel] == [5.0, 4.0] and len(skip) == 2


def test_no_trade_still_shows_watchlist_needs():
    m = uni(nifty=make(drift=-0.002)); v = evaluate(m, "S9", LONG, m.n - 1)
    assert v.verdict == "NO TRADE"
    assert v.waiting_for[0].startswith("Market: Nifty to close above its 200-day average")
    assert any(w.startswith("Trend:") for w in v.waiting_for)
    v0 = evaluate(m, "S0", LONG, m.n - 1)
    assert any(w.startswith("Strength: momentum rank in the top") for w in v0.waiting_for)
