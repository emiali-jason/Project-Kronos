"""Pure retained WO-15/16 factual-row codec, without application startup.

The application re-exports these exact existing record and formatting bodies.
No source hydration, trading authority or lifecycle ownership lives here.
"""
from dataclasses import dataclass
from hashlib import sha256
import json

@dataclass(frozen=True)
class FactualRow:
    identity: str
    payload: str

    @property
    def data(self):
        return json.loads(self.payload)


def factual_row(**data):
    if data["truth_class"] not in {"PAPER_POSITION", "PAPER_OBSERVATION", "NONE", "DO_NOTHING"}:
        raise ValueError("INTRADAY_BOOK_TRUTH_UNAVAILABLE")
    if not data["opportunity_id"] or not data["opportunity_identity"]:
        raise ValueError("INTRADAY_BOOK_ORIGIN_UNAVAILABLE")
    if data["track_identity"] and data["model_lots"] != 1:
        raise ValueError("INTRADAY_BOOK_ONE_LOT_REQUIRED")
    # Exact source adapter; this is a display identity, never an opportunity ID.
    key = [data[k] for k in ("opportunity_identity", "decision_identity", "track_identity", "truth_class")]
    identity = "INTRADAY-FACTUAL-ROW-" + sha256(json.dumps(key).encode()).hexdigest()
    data["future"] = {k: (data.get("future") or {}).get(k) for k in (
        "tradingsymbol", "trading_symbol", "exchange", "segment", "expiry", "lot_size")}
    if data.get("metrics") is not None:
        data["metrics"] = {key: data["metrics"].get(key) for key in (
            "points", "model_r", "mfe", "mae", "gross_model_result", "complete", "samples",
            "coverage_label", "coverage_start", "coverage_end")}
    data.setdefault("observation", None)
    def portable(value):
        if isinstance(value, str) and (len(value) > 512 or any(marker in value for marker in (
                "/Users/", "/private/", "/tmp/", "file://", "Bearer ", "access_token", "api_key", "Cookie:"))):
            raise ValueError("INTRADAY_BOOK_NONPORTABLE_SOURCE")
        if isinstance(value, dict):
            for key, item in value.items():
                portable(key); portable(item)
        elif isinstance(value, (list, tuple)):
            if len(value) > 1000:
                raise ValueError("INTRADAY_BOOK_SOURCE_SIZE_UNAVAILABLE")
            for item in value:
                portable(item)
    portable(data)
    return FactualRow(identity, json.dumps(data, sort_keys=True, separators=(",", ":")))
