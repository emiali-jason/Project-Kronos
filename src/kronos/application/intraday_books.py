"""WO-15/16 read-only source binding, independent of presentation stores.

Lazy bounded hydration performs no startup I/O. Only typed WO10 selection,
WO11 action/current pointer populations are visited once per process. Committed
source callbacks replace compact rows; ordinary filters never reload graphs.
No projection is a lifecycle store and no projection writes production files.
"""
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from threading import RLock

from kronos.application.intraday_journal import IntradaySourceAdapter, _instant
from kronos.intraday.wo15_portfolio import is_exposure
from kronos.intraday.books_factual_contract import FactualRow, factual_row

MAX_RECORDS = 10000






class IntradayBooks(IntradaySourceAdapter):
    revision_factory = staticmethod(factual_row)

    def __init__(self, *, research, futures, lifecycle):
        from kronos.application.failed_fenced_owners import register_owner
        register_owner('BOOKS', self, __file__)
        super().__init__(research=research, futures=futures, lifecycle=lifecycle, store=self)
        self._rows = {}
        self._lock = RLock()
        self._hydrated = False
        self._failure = None

    def bind(self):
        self.futures.book_listener = self.consume_source
        self.lifecycle.book_listener = self.consume_source

    def publish(self, row):
        if len(self._rows) >= MAX_RECORDS and row.identity not in self._rows:
            raise ValueError("INTRADAY_BOOK_CAPACITY_UNAVAILABLE")
        self._rows[row.identity] = row
        return row

    def _monitoring(self, track_identity, stored, terminal):
        # Retain lifecycle truth only. Dynamic owner state is read separately.
        return "NOT_REQUIRED" if terminal else stored if stored in {"LIVE", "INTERRUPTED", "IDLE"} else "UNAVAILABLE"

    def _track_extras(self, data):
        return {"observation": {k: data.get(k) for k in (
            "last_price", "last_observed_at", "last_sequence", "last_connection",
            "last_fact_identity", "baseline_required", "monitoring")}
            | {"gap_count": len(data.get("gaps", ())), "source_lifecycle_identity": None}}

    def _track(self, current):
        produced = super()._track(current)
        # Replace only the compact source pointer, not source facts or history.
        for key, row in tuple(self._rows.items()):
            if row.data["track_identity"] == current.data["track_identity"]:
                d = row.data
                d["observation"]["source_lifecycle_identity"] = current.identity
                self._rows[key] = FactualRow(key, json.dumps(d, sort_keys=True, separators=(",", ":")))
        return None if produced is None else self._rows[produced.identity]

    def consume_source(self, kind, identity):
        with self._lock:
            try:
                return super().consume_source(kind, identity)
            except Exception:
                self._failure = "INTRADAY_BOOK_SOURCE_UNAVAILABLE"
                raise

    def _original_output(self, row):
        # Called while consume_source holds this owner's lock.  This captures
        # the original exact FactualRow, without snapshot/hydration or writes.
        if type(row) is not FactualRow or self._rows.get(row.identity) != row:
            raise ValueError("INTRADAY_BOOK_CALLBACK_OUTPUT_CHANGED")
        data = row.data
        expected = factual_row(**data)
        if expected != row:
            raise ValueError("INTRADAY_BOOK_CALLBACK_OUTPUT_INVALID")
        return {"adapter": "BOOKS_FACTUAL_ROW_V1", "identity": row.identity,
                "bytes": row.payload.encode("utf-8"), "pointer": None}

    def _hydrate(self):
        if self._hydrated:
            return
        # No Journal, Notifications, research ledger or workbook reads.
        # Origin records are consumed by the shared exact-identity adapter only.
        for kind, source, schema in (
            ("SELECTION", self.futures, "WO10_SPONSOR_SELECTION_V1"),
            ("ACTION", self.lifecycle, "WO11_ACTION_V1"),
        ):
            root = getattr(source, "root", None)
            if root is not None:
                from itertools import islice
                paths = tuple(islice((root / "records").glob(schema + "-*.json"), MAX_RECORDS + 1))
                if len(paths) > MAX_RECORDS:
                    raise ValueError("INTRADAY_BOOK_CAPACITY_UNAVAILABLE")
                population = (source.load(path.stem) for path in sorted(paths))
            else:
                population = source.records(schema)
            for item in population:
                self.consume_source(kind, item.identity)
        root = getattr(self.lifecycle, "root", None)
        if root is not None:
            from itertools import islice
            if len(tuple(islice((root / "current").glob("*.json"), MAX_RECORDS + 1))) > MAX_RECORDS:
                raise ValueError("INTRADAY_BOOK_CAPACITY_UNAVAILABLE")
        for item in self.lifecycle.restore():
            self.consume_source("TRACK", item.identity)
        self._hydrated = True

    def snapshot(self):
        with self._lock:
            if not self._hydrated:
                try:
                    self._hydrate()
                except (ValueError, OSError, KeyError, TypeError):
                    self._failure = "INTRADAY_BOOK_SOURCE_UNAVAILABLE"
                finally:
                    self._hydrated = True
            if self._failure:
                raise ValueError(self._failure)
            return tuple(sorted(self._rows.values(), key=lambda r: (
                -_instant(r.data["decision_at"]).timestamp(), r.identity)))

    def portfolio(self, *, search="", direction="", monitoring=""):
        result = []
        for row in self.snapshot():
            d = row.data
            if not is_exposure(d):
                continue
            resolver = getattr(self.lifecycle_application, "portfolio_observation", None)
            live = {"monitoring": "UNAVAILABLE", "price": None, "observed_at": None}
            if resolver is not None:
                live = resolver(d["track_identity"], d["observation"])
            d = dict(d, current_observation=live, record_identity=row.identity)
            haystack = json.dumps({k: d[k] for k in (
                "opportunity_id", "subject", "direction", "future")}).casefold()
            if search.casefold() not in haystack or (direction and d["direction"] != direction):
                continue
            if monitoring and live["monitoring"] != monitoring:
                continue
            # Never compute points/economics here; only current eligible WO11 metrics.
            if live["price"] is None:
                d["metrics"] = None
            result.append(d)
        return tuple(result)
