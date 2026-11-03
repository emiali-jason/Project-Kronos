import json
import math
from datetime import date, datetime, time, timedelta
from xml.etree import ElementTree
from zipfile import ZipFile

import pytest

from kronos.application.swing_engine_log import IST, SwingEngineLog, write_xlsx
from kronos.swing.engine_v22 import Market


def series(n, drift, amp=0.01, base=100.0, period=3.0, burst=None, flat_from=None):
    d0 = date(2025, 1, 1)
    out, prev = [], base
    for i in range(n):
        t = i if flat_from is None else min(i, flat_from)
        c = base * math.exp(drift * t) * (1 + amp * math.sin(i / period))
        if burst and i >= burst:
            c *= 1.25                                   # a strong breakout from day `burst`
        out.append({"date": (d0 + timedelta(days=i)).isoformat(), "open": prev,
                    "high": max(prev, c) * 1.004, "low": min(prev, c) * 0.996, "close": c, "volume": 1000})
        prev = c
    return out


def market(n, burst=None):
    stocks = {f"S{k}": series(n, -0.0003 * k) for k in range(9)}
    stocks["HOT"] = series(n, 0.004, burst=burst, flat_from=260)
    return Market(stocks, series(n, 0.0008))


def log(tmp_path, **kw):
    return SwingEngineLog(application=None, ready=lambda: True, state_root=tmp_path / "state",
                          workbook_root=tmp_path / "wb", runner=lambda fn: fn(), **kw)


def test_first_run_starts_today_without_backfill(tmp_path):
    el = log(tmp_path)
    res = el.process(market(330), {"HOT": 500})
    assert res["processed_days"] == 1 and el.state["started"] == el.state["last_processed"]


def test_signal_fills_next_open_and_tracks_pnl_with_lot_size(tmp_path):
    el = log(tmp_path)
    el.process(market(330), {"HOT": 500})
    el.process(market(331, burst=330), {"HOT": 500})            # fresh strong breakout on the last day
    assert [p["symbol"] for p in el.state["pending"]] == ["HOT"]
    el.process(market(333, burst=330), {"HOT": 500})
    pos = [p for p in el.state["open"] + el.state["closed"] if p["symbol"] == "HOT"]
    assert pos and pos[0]["lot_size"] == 500 and pos[0]["stop"] < pos[0]["entry"]
    assert pos[0]["entry_date"] == market(333).dates[331]       # next session's open


def test_stop_exit_and_rupee_pnl(tmp_path):
    el = log(tmp_path)
    el.state.update(started="2025-01-01", last_processed=series(331, 0)[-2]["date"],
                    open=[{"symbol": "S1", "signal_date": "2025-01-01", "entry_date": "2025-01-02",
                           "entry": 1000.0, "stop": 10_000.0, "lot_size": 10, "lots": 1}])
    el.process(market(331), {})
    t = el.state["closed"][0]
    assert t["exit_reason"] == "STOP" and t["net_pnl"] == round(t["gross_pnl"] - t["costs"], 2)
    assert t["gross_pnl"] == round((t["exit"] - 1000.0) * 10, 2)


def test_monthly_limit_respected(tmp_path):
    el = log(tmp_path)
    m = market(331, burst=330)
    el.state.update(started="x", last_processed=series(331, 0)[-2]["date"], taken={series(331, 0)[-1]["date"][:7]: 5})
    el.process(m, {})
    assert not el.state["pending"]
    rows = json.loads((tmp_path / "state" / f"verdicts-{m.dates[-1][:7]}.json").read_text())["rows"]
    hot = [r for r in rows if r["symbol"] == "HOT" and r["date"] == m.dates[-1]][0]
    if hot["verdict"] == "BUY NOW":
        assert hot["note"] == "monthly limit reached"


def test_idempotent_and_catch_up(tmp_path):
    el = log(tmp_path)
    el.process(market(330), {})
    assert el.process(market(330), {})["processed_days"] == 0
    assert el.process(market(334), {})["processed_days"] == 4      # four missed sessions caught up


def test_workbook_is_valid_xlsx(tmp_path):
    el = log(tmp_path)
    m = market(330)
    el.process(m, {})
    path = tmp_path / "wb" / f"KRONOS_Engine_v2.2_Log_{m.dates[-1][:7]}.xlsx"
    with ZipFile(path) as z:
        names = z.namelist()
        assert "xl/workbook.xml" in names and "xl/worksheets/sheet5.xml" in names
        for n in names:
            if n.endswith(".xml") or n.endswith(".rels"):
                ElementTree.fromstring(z.read(n))
        assert b"All_Verdicts" in z.read("xl/workbook.xml")


def test_write_xlsx_escapes_text(tmp_path):
    write_xlsx(tmp_path / "x.xlsx", [("A", [["a<b&c", 1.5, True, None]])])
    with ZipFile(tmp_path / "x.xlsx") as z:
        ElementTree.fromstring(z.read("xl/worksheets/sheet1.xml"))


def test_poll_runs_once_after_2300_and_failure_is_recorded(tmp_path):
    clock = {"t": datetime(2026, 11, 3, 22, 59, tzinfo=IST)}
    el = log(tmp_path, clock=lambda: clock["t"])
    calls = []
    el._run = lambda: calls.append(1) or {"processed_days": 1}
    el.poll(); assert calls == []
    clock["t"] = datetime(2026, 11, 3, 23, 1, tzinfo=IST); el._next_check = 0
    el.poll(); assert calls == [1]
    el._next_check = 0; el.poll(); assert calls == [1]          # once per day
    def boom():
        raise RuntimeError("KITE_NOT_CONNECTED")
    el._run = boom
    assert el.start("MANUAL")
    assert el.status()["last_result"]["state"] == "FAILED"
    assert el.status()["last_result"]["reason"] == "KITE_NOT_CONNECTED"


def test_not_ready_does_not_run(tmp_path):
    el = SwingEngineLog(application=None, ready=lambda: False, state_root=tmp_path, workbook_root=tmp_path,
                        runner=lambda fn: fn(), clock=lambda: datetime(2026, 11, 3, 23, 30, tzinfo=IST))
    el._run = lambda: pytest.fail("must not run")
    el.poll()


def test_fetch_through_real_kite_provider_classes(tmp_path):
    from kronos.provider.contracts.instrument import InstrumentRecord
    from kronos.provider.contracts.market_data import HistoricalCandle
    from kronos.provider.contracts.provider_authentication import ReadOnlyProviderOperation

    now = datetime(2026, 11, 3, 14, 0, tzinfo=IST)            # before the close: today's candle is dropped
    days = [now.date() - timedelta(days=k) for k in range(5, -1, -1)]

    class Cap:
        active = True
        operations = frozenset({ReadOnlyProviderOperation.INSTRUMENTS, ReadOnlyProviderOperation.HISTORICAL_DATA})
        requests = []
        def instrument_records(self, exchange):
            if exchange == "NSE":
                return (InstrumentRecord("KITE", "NSE", "INDICES", "NIFTY 50", "NIFTY 50", "EQ", None),
                        InstrumentRecord("KITE", "NSE", "NSE", "RELIANCE", "RELIANCE", "EQ", None),
                        InstrumentRecord("KITE", "NSE", "NSE", "BAJAJ-AUTO", "BAJAJ-AUTO", "EQ", None))
            return (InstrumentRecord("KITE", "NFO", "NFO-FUT", "RELIANCE26NOVFUT", "RELIANCE", "FUT", date(2026, 11, 25), lot_size=500),
                    InstrumentRecord("KITE", "NFO", "NFO-FUT", "RELIANCE26DECFUT", "RELIANCE", "FUT", date(2026, 12, 30), lot_size=250),
                    InstrumentRecord("KITE", "NFO", "NFO-FUT", "BAJAJ-AUTO26NOVFUT", "BAJAJ-AUTO", "FUT", date(2026, 11, 25), lot_size=75))
        def historical_candles(self, request):
            self.requests.append(request.instrument.trading_symbol)
            return tuple(HistoricalCandle(datetime.combine(d, time(0), IST), 100.0, 101.0, 99.0, 100.5, 10) for d in days)

    class App:
        def authenticated_read_only_capability(self):
            return Cap()

    el = SwingEngineLog(application=App(), ready=lambda: True, state_root=tmp_path, workbook_root=tmp_path,
                        clock=lambda: now, pace=lambda: None, universe=["RELIANCE", "BAJAJ_AUTO", "MISSINGCO"])
    stocks, nifty, lots, missing = el._fetch()
    assert Cap.requests[0] == "NIFTY 50" and set(stocks) == {"RELIANCE", "BAJAJ_AUTO"} and missing == ["MISSINGCO"]
    assert lots == {"RELIANCE": 500, "BAJAJ_AUTO": 75}                     # nearest unexpired contract
    assert stocks["RELIANCE"][-1]["date"] == (now.date() - timedelta(days=1)).isoformat()
    assert len(nifty) == 5


def test_fetch_without_kite_connection_fails_cleanly(tmp_path):
    class App:
        def authenticated_read_only_capability(self):
            return None
    el = SwingEngineLog(application=App(), ready=lambda: True, state_root=tmp_path, workbook_root=tmp_path,
                        runner=lambda fn: fn())
    el.start("MANUAL")
    assert el.status()["last_result"]["reason"] == "KITE_NOT_CONNECTED"
