"""WO-11: Rulebook v2.2 daily engine log and PAPER trading (research only).

Runs the v2.2 engine on the 91 Swing NSE equities each day, records every verdict,
and keeps 1-lot PAPER futures trades for the BUY NOW selections (max 5 a month).
Read-only: it uses the existing authenticated read-only Provider capability for
instruments and Daily candles. It never places orders, never changes the frozen
Swing method, its records or publications, and owns only its own folders:

  state:    ~/Library/Application Support/KRONOS/engine-log-v2.2/
  workbook: ~/Documents/Project-KRONOS/Statistics/Swing/KRONOS_Engine_v2.2_Log_YYYY-MM.xlsx

Prices are NSE cash-market Daily candles used as the futures proxy (futures trade
at a small basis); lot sizes come from the current NFO futures contracts.
"""
from __future__ import annotations

import json
import os
import threading
import time as _time
from datetime import date, datetime, time, timedelta
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile
from zoneinfo import ZoneInfo

from kronos.swing.engine_v22 import LONG, RB22, Market, evaluate, monthly_selection

IST = ZoneInfo("Asia/Kolkata")
STATE_ROOT = Path.home() / "Library" / "Application Support" / "KRONOS" / "engine-log-v2.2"
WORKBOOK_ROOT = Path.home() / "Documents" / "Project-KRONOS" / "Statistics" / "Swing"
HISTORY_CALENDAR_DAYS = 430          # about 290 sessions: enough for 12-month and 200-day measures
COST = 0.0010                        # per round trip, of notional
ROLL = 0.0005                        # per 21 sessions held (monthly futures rollover)
CLOSE_COMPLETE = time(15, 45)        # today's candle counts only after the close
SCHEDULE = time(23, 0)


def _now():
    return datetime.now(IST)


class SwingEngineLog:
    def __init__(self, *, application, ready, state_root=STATE_ROOT, workbook_root=WORKBOOK_ROOT,
                 clock=_now, pace=lambda: _time.sleep(0.4), runner=None, universe=None):
        self.application = application
        self.ready = ready
        self.state_root = Path(state_root)
        self.workbook_root = Path(workbook_root)
        self.clock = clock
        self.pace = pace
        self.runner = runner or (lambda fn: threading.Thread(target=fn, name="kronos-engine-log", daemon=True).start())
        self._universe = universe
        self._lock = threading.Lock()
        self._running = False
        self._next_check = 0.0
        self._last_result = None
        self.state = self._load()

    # ------------------------------------------------------------------ state
    def _state_path(self):
        return self.state_root / "state.json"

    def _load(self):
        try:
            return json.loads(self._state_path().read_text())
        except (OSError, ValueError):
            return {"rulebook": RB22.version, "started": None, "last_processed": None,
                    "last_auto_run": None, "taken": {}, "pending": [], "open": [], "closed": [], "runs": []}

    def _save(self):
        self.state_root.mkdir(parents=True, exist_ok=True)
        tmp = self._state_path().with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, indent=1, sort_keys=True))
        os.replace(tmp, self._state_path())

    def _month_log_path(self, month):
        return self.state_root / f"verdicts-{month}.json"

    # ----------------------------------------------------------------- status
    def status(self):
        with self._lock:
            running, last = self._running, self._last_result
        s = self.state
        return {"state": "RUNNING" if running else "IDLE", "last_result": last,
                "last_processed": s.get("last_processed"), "started": s.get("started"),
                "open": len(s.get("open", [])), "pending": len(s.get("pending", [])),
                "closed": len(s.get("closed", [])),
                "taken_this_month": s.get("taken", {}).get(self.clock().strftime("%Y-%m"), 0),
                "workbook_root": str(self.workbook_root)}

    # --------------------------------------------------------------- triggers
    def poll(self):
        """Cheap check from the existing server pulse; starts the 23:00 run once a day."""
        moment = _time.monotonic()
        if moment < self._next_check:
            return
        self._next_check = moment + 30
        now = self.clock()
        if now.time() < SCHEDULE or self.state.get("last_auto_run") == now.date().isoformat():
            return
        if not self.ready():
            return
        self.start("SCHEDULE")

    def start(self, trigger="MANUAL"):
        with self._lock:
            if self._running:
                return False
            self._running = True

        def work():
            result = {"trigger": trigger, "started_at": self.clock().isoformat()}
            try:
                result.update(self._run())
                result["state"] = "COMPLETED"
                if trigger == "SCHEDULE":
                    self.state["last_auto_run"] = self.clock().date().isoformat()
            except Exception as error:  # recorded, never raised into the server
                result.update(state="FAILED", failure=type(error).__name__,
                              reason=str(error)[:200])
                if trigger == "SCHEDULE":   # one scheduled attempt per day; the button can retry
                    self.state["last_auto_run"] = self.clock().date().isoformat()
            result["finished_at"] = self.clock().isoformat()
            self.state.setdefault("runs", []).append(result)
            self.state["runs"] = self.state["runs"][-200:]
            try:
                self._save()
            except OSError:
                result["state"] = "FAILED"; result["failure"] = "STATE_WRITE_FAILED"
            with self._lock:
                self._running = False
                self._last_result = result

        self.runner(work)
        return True

    # ------------------------------------------------------------------ data
    def _members(self):
        if self._universe is not None:
            return self._universe
        from kronos.swing.universe import SwingUniverseAssetClass, enabled_swing_phase1_universe
        return [m.canonical_identity for m in enabled_swing_phase1_universe()
                if m.asset_class is SwingUniverseAssetClass.NSE_EQUITY]

    def _fetch(self):
        from kronos.provider.contracts.instrument import InstrumentKind, InstrumentResolutionRequest
        from kronos.provider.contracts.market_data import HistoricalCandleRequest, HistoricalInterval
        from kronos.provider.kite.instruments.kite_instrument_provider import KiteInstrumentProvider
        from kronos.provider.kite.marketdata.kite_market_data_provider import KiteMarketDataProvider

        capability = self.application.authenticated_read_only_capability()
        if capability is None:
            raise RuntimeError("KITE_NOT_CONNECTED")
        instruments = KiteInstrumentProvider(capability)
        market_data = KiteMarketDataProvider(capability)
        nse = instruments.retrieve("NSE")
        lots = {}
        try:
            today = self.clock().date()
            for r in instruments.retrieve("NFO"):
                if r.instrument_type == "FUT" and r.expiry is not None and r.expiry >= today and r.lot_size:
                    prev = lots.get(r.name)
                    if prev is None or r.expiry < prev[0]:
                        lots[r.name] = (r.expiry, int(r.lot_size))
        except Exception:
            lots = {}
        now = self.clock()
        end = now
        start = end - timedelta(days=HISTORY_CALENDAR_DAYS)
        complete_today = now.time() >= CLOSE_COMPLETE

        def candles(kind, symbol):
            record = instruments.resolve_from_records(
                nse, InstrumentResolutionRequest(kind=kind, symbol=symbol, as_of=now.date()))
            rows = market_data.historical_candles(
                HistoricalCandleRequest(instrument=record, start=start, end=end, interval=HistoricalInterval.DAY))
            self.pace()
            out = []
            for c in rows:
                d = c.timestamp.astimezone(IST).date()
                if d > now.date() or (d == now.date() and not complete_today):
                    continue
                out.append({"date": d.isoformat(), "open": c.open, "high": c.high,
                            "low": c.low, "close": c.close, "volume": c.volume})
            return out

        nifty = candles(InstrumentKind.NSE_INDEX, "NIFTY")
        stocks, missing = {}, []
        for s in self._members():
            try:
                rows = candles(InstrumentKind.NSE_EQUITY, s)
                if rows:
                    stocks[s] = rows
                else:
                    missing.append(s)
            except Exception:
                missing.append(s)
        try:
            from kronos.provider.kite.instruments.kite_instrument_provider import _NSE_EQUITY_SYMBOLS as kite_name
        except ImportError:
            kite_name = {"BAJAJ_AUTO": "BAJAJ-AUTO"}
        lot_size = {s: lots.get(kite_name.get(s, s), (None, None))[1] for s in stocks}
        return stocks, nifty, lot_size, missing

    # ------------------------------------------------------------ processing
    def _run(self):
        stocks, nifty, lot_size, missing = self._fetch()
        if not nifty or not stocks:
            raise RuntimeError("DAILY_CANDLES_UNAVAILABLE")
        m = Market(stocks, nifty)
        return self.process(m, lot_size, missing)

    def process(self, m, lot_size, missing=()):
        s = self.state
        last_i = m.n - 1
        if s.get("last_processed") is None:
            first_i = last_i                       # paper trading starts on the first run; no back-fill
            s["started"] = m.dates[last_i]
        else:
            lp = s["last_processed"]
            first_i = next((k for k, d in enumerate(m.dates) if d > lp), None)
            if first_i is None:
                return {"processed_days": 0, "through": lp, "missing_symbols": list(missing)}
        days = 0
        for k in range(first_i, last_i + 1):
            self._process_day(m, k, lot_size)
            days += 1
            s["last_processed"] = m.dates[k]
        self._save()
        months = sorted({m.dates[k][:7] for k in range(first_i, last_i + 1)})
        for month in months:
            self.write_workbook(month)
        return {"processed_days": days, "through": m.dates[last_i], "missing_symbols": list(missing),
                "open": len(s["open"]), "pending": len(s["pending"])}

    def _process_day(self, m, k, lot_size):
        s = self.state
        day = m.dates[k]
        events = []
        # 1. fill yesterday's signals at today's open
        still = []
        for p in s["pending"]:
            sym = p["symbol"]
            if sym not in m.c or m.dates.index(p["signal_date"]) >= k:
                still.append(p); continue
            entry = m.o[sym][k]
            risk = min(RB22.trend_stop_atr * p["atr"], entry * RB22.trend_stop_max_pct / 100)
            pos = dict(p, entry_date=day, entry=round(entry, 2), stop=round(entry - risk, 2),
                       lot_size=lot_size.get(sym), lots=1, entry_index_date=day)
            s["open"].append(pos)
            events.append(f"ENTRY {sym} at {entry:.2f}")
        s["pending"] = still
        # 2. manage open PAPER positions with today's candle
        keep = []
        for pos in s["open"]:
            sym = pos["symbol"]
            if sym not in m.c or m.c[sym][k] is None:
                keep.append(pos); continue          # candle unavailable today: keep, check next run
            lo, op, cl = m.l[sym][k], m.o[sym][k], m.c[sym][k]
            why = px = None
            if lo <= pos["stop"]:
                px = pos["stop"] if pos["entry_date"] == day else min(op, pos["stop"]); why = "STOP"
            elif cl < m.sma50[sym][k]:
                px, why = cl, "EXIT_RULE_CLOSE_BELOW_50D"
            if why is None:
                pos["last_close"] = round(cl, 2); pos["exit_level_50d"] = round(m.sma50[sym][k], 2)
                keep.append(pos); continue
            sessions = k - m.dates.index(pos["entry_date"]) + 1
            lsz = pos.get("lot_size") or 0
            gross = (px - pos["entry"]) * lsz
            costs = pos["entry"] * lsz * (COST + ROLL * (sessions // 21))
            pos.update(exit_date=day, exit=round(px, 2), exit_reason=why, sessions=sessions,
                       ret_pct=round(100 * (px / pos["entry"] - 1 - COST - ROLL * (sessions // 21)), 2),
                       gross_pnl=round(gross, 2), costs=round(costs, 2), net_pnl=round(gross - costs, 2))
            s["closed"].append(pos)
            events.append(f"EXIT {sym} {why} at {px:.2f}")
        s["open"] = keep
        # 3. today's verdicts and selection
        month = day[:7]
        verdicts = [evaluate(m, sym, LONG, k) for sym in m.syms]
        busy = {p["symbol"] for p in s["open"]} | {p["symbol"] for p in s["pending"]}
        cands = [v for v in verdicts if v.state == "NOW" and v.symbol not in busy]
        selected, skipped = monthly_selection(cands, s["taken"].get(month, 0))
        for v in selected:
            s["taken"][month] = s["taken"].get(month, 0) + 1
            s["pending"].append({"symbol": v.symbol, "signal_date": day, "setup": v.setup,
                                 "signal_close": v.facts["close"], "atr": v.facts["atr"],
                                 "priority": round(v.priority, 2)})
            events.append(f"SIGNAL {v.symbol} BUY NOW (paper entry at next open)")
        skipped_syms = {v.symbol for v in skipped}
        rows = []
        for v in verdicts:
            f = v.facts
            rows.append({"date": day, "symbol": v.symbol, "verdict": v.verdict,
                         "selected": v.symbol in {x.symbol for x in selected},
                         "note": ("monthly limit reached" if v.symbol in skipped_syms else
                                  "already in a paper trade" if v.state == "NOW" and v.symbol in busy else ""),
                         "reasons": " | ".join(v.reasons), "waiting_for": " | ".join(v.waiting_for),
                         "close": f.get("close"), "momentum_rank": f.get("momentum_rank"),
                         "ext_atr": f.get("ext_atr"), "high_50d": f.get("high_50d_prior"),
                         "sma50": f.get("sma50"), "stop": v.plan.get("stop"), "risk_pct": v.plan.get("risk_pct"),
                         "trend_trigger": f.get("trend_trigger"), "pct_to_trigger": f.get("pct_to_trigger"),
                         "strength_ok": (f.get("momentum_rank") is not None
                                         and f.get("momentum_rank") <= f.get("momentum_cutoff", 0))})
        nifty_ok = m.nc[k] > m.nsma[k]
        summary = {"date": day, "nifty": round(m.nc[k], 2), "nifty_200d": round(m.nsma[k], 2),
                   "market_gate": "OPEN" if nifty_ok else "CLOSED",
                   "now": sum(v.state == "NOW" for v in verdicts), "ready": sum(v.state == "READY" for v in verdicts),
                   "watch": sum(v.state == "WATCH" for v in verdicts),
                   "no_trade": sum(v.state == "NO TRADE" for v in verdicts),
                   "selected": len(selected), "taken_this_month": s["taken"].get(month, 0),
                   "open_positions": len(s["open"]), "events": " ; ".join(events)}
        path = self._month_log_path(month)
        try:
            log = json.loads(path.read_text())
        except (OSError, ValueError):
            log = {"days": [], "rows": []}
        log["days"] = [d for d in log["days"] if d["date"] != day] + [summary]
        log["rows"] = [r for r in log["rows"] if r["date"] != day] + rows
        self.state_root.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp"); tmp.write_text(json.dumps(log)); os.replace(tmp, path)

    # -------------------------------------------------------------- workbook
    def write_workbook(self, month):
        try:
            log = json.loads(self._month_log_path(month).read_text())
        except (OSError, ValueError):
            return None
        s = self.state
        trades = [t for t in s["closed"] + s["open"] + s["pending"]
                  if t.get("signal_date", "")[:7] == month or t.get("exit_date", "")[:7] == month or t in s["open"]]
        closed_m = [t for t in s["closed"] if t["exit_date"][:7] == month]
        all_closed = s["closed"]
        def agg(ts):
            n = len(ts); w = [t for t in ts if t["net_pnl"] > 0]
            return [n, len(w), round(100 * len(w) / n) if n else "", round(sum(t["net_pnl"] for t in ts), 2),
                    round(sum(t["ret_pct"] for t in ts) / n, 2) if n else ""]
        summary = [["KRONOS Engine v2.2 — daily log and PAPER trading", ""],
                   ["Month", month], ["Paper trading started", s.get("started")],
                   ["Rules", "Nifty > 200-day; top 30% momentum; fresh close above prior 50-day high, >= 3 ATR above 50-day average; max 5 new a month; stop min(3 ATR,15%); exit close below 50-day average"],
                   ["Sizing", "1 futures lot per trade (current NFO lot size); prices = NSE cash candles as futures proxy; costs 0.10% + 0.05% per month held"],
                   ["", ""], ["", "Trades closed, Winners, Win %, Net P&L (Rs), Avg return %"],
                   ["This month"] + agg(closed_m), ["Since start"] + agg(all_closed),
                   ["Open paper positions", len(s["open"])], ["Pending entries (next open)", len(s["pending"])]]
        daily_cols = ["date", "nifty", "nifty_200d", "market_gate", "now", "ready", "watch", "no_trade",
                      "selected", "taken_this_month", "open_positions", "events"]
        verdict_cols = ["date", "symbol", "verdict", "selected", "note", "close", "momentum_rank", "ext_atr",
                        "high_50d", "sma50", "trend_trigger", "pct_to_trigger", "stop", "risk_pct",
                        "waiting_for", "reasons"]
        trade_cols = ["symbol", "signal_date", "entry_date", "entry", "stop", "lot_size", "lots", "last_close",
                      "exit_level_50d", "exit_date", "exit", "exit_reason", "sessions", "ret_pct",
                      "gross_pnl", "costs", "net_pnl"]
        def table(cols, items):
            return [cols] + [[it.get(c, "") for c in cols] for it in items]
        days = sorted(log["days"], key=lambda d: d["date"])
        rows = sorted(log["rows"], key=lambda r: (r["date"], {"BUY NOW": 0, "BUY READY": 1, "WATCH": 2}.get(r["verdict"], 3), r["symbol"]))
        ready_now = [r for r in rows if r["date"] == (days[-1]["date"] if days else None) and r["verdict"] in ("BUY NOW", "BUY READY")]
        last_day = days[-1]["date"] if days else None
        watch = sorted((r for r in rows if r["date"] == last_day and r.get("strength_ok")
                        and r.get("pct_to_trigger") is not None),
                       key=lambda r: r["pct_to_trigger"])
        watch_cols = ["date", "symbol", "verdict", "close", "trend_trigger", "pct_to_trigger", "momentum_rank",
                      "ext_atr", "high_50d", "sma50", "waiting_for"]
        sheets = [("Summary", summary), ("Daily", table(daily_cols, days)),
                  ("Today_Ready_Now", table(verdict_cols, ready_now)),
                  ("Watchlist", table(watch_cols, watch)),
                  ("Paper_Trades", table(trade_cols, sorted(trades, key=lambda t: t.get("signal_date", "")))),
                  ("All_Verdicts", table(verdict_cols, rows))]
        self.workbook_root.mkdir(parents=True, exist_ok=True)
        path = self.workbook_root / f"KRONOS_Engine_v2.2_Log_{month}.xlsx"
        tmp = path.with_name("." + path.name + ".tmp")
        write_xlsx(tmp, sheets)
        os.replace(tmp, path)
        return path


# ---------------------------------------------------------------- tiny XLSX writer
def _col(n):
    out = ""
    while n:
        n, r = divmod(n - 1, 26); out = chr(65 + r) + out
    return out


def _cell(ref, v, bold=False):
    st = ' s="1"' if bold else ""
    if isinstance(v, bool):
        v = "Yes" if v else ""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return f'<c r="{ref}"{st}><v>{v}</v></c>'
    if v is None or v == "":
        return ""
    return f'<c r="{ref}" t="inlineStr"{st}><is><t xml:space="preserve">{escape(str(v))}</t></is></c>'


def write_xlsx(path, sheets):
    with ZipFile(path, "w", ZIP_DEFLATED) as z:
        names = [n for n, _ in sheets]
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                   + "".join(f'<Override PartName="/xl/worksheets/sheet{i+1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(len(names)))
                   + '</Types>')
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                   + "".join(f'<sheet name="{escape(n)}" sheetId="{i+1}" r:id="rId{i+1}"/>' for i, n in enumerate(names)) + '</sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + "".join(f'<Relationship Id="rId{i+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i+1}.xml"/>' for i in range(len(names)))
                   + f'<Relationship Id="rId{len(names)+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        z.writestr("xl/styles.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                   '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
                   '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
                   '<borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs>'
                   '<cellXfs count="2"><xf fontId="0"/><xf fontId="1" applyFont="1"/></cellXfs></styleSheet>')
        for i, (_, rows) in enumerate(sheets):
            body = []
            for r, row in enumerate(rows, start=1):
                cells = "".join(_cell(f"{_col(c)}{r}", v, bold=(r == 1)) for c, v in enumerate(row, start=1))
                body.append(f'<row r="{r}">{cells}</row>')
            z.writestr(f"xl/worksheets/sheet{i+1}.xml",
                       '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                       '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
                       '<sheetData>' + "".join(body) + '</sheetData></worksheet>')
