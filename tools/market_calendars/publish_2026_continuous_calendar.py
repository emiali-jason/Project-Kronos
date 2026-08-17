"""Publish the governed DOMAIN-008 2026 NSE/MCX calendar revisions.

The checked-in exception tables below are transcriptions of the official
annual exchange publications already cited by the immutable base calendars.
Normal sessions are generated only inside that governed annual boundary;
explicit holidays and special sessions always override them.
"""

from __future__ import annotations

from datetime import date, timedelta
from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CALENDAR_ROOT = ROOT / "data/market_calendars/KRONOS-MARKET-CALENDAR-V1"
END = date(2026, 12, 31)

NSE_BASE = "NSE-CAPITAL-MARKET-2022-2026.v2.json"
NSE_OUTPUT = "NSE-CAPITAL-MARKET-2022-2026.v3.json"
MCX_BASE = "MCX-NON-AGRI-2026.v1.json"
MCX_OUTPUT = "MCX-NON-AGRI-2026.v2.json"

NSE_HOLIDAYS = {
    date(2026, 9, 14): "GANESH_CHATURTHI",
    date(2026, 10, 2): "MAHATMA_GANDHI_JAYANTI",
    date(2026, 10, 20): "DUSSEHRA",
    date(2026, 11, 10): "DIWALI_BALIPRATIPADA",
    date(2026, 11, 24): "GURUNANAK_JAYANTI",
    date(2026, 12, 25): "CHRISTMAS",
}

MCX_FULL_HOLIDAYS = {
    date(2026, 10, 2): "MAHATMA_GANDHI_JAYANTI",
    date(2026, 12, 25): "CHRISTMAS",
}

MCX_EVENING_ONLY = {
    date(2026, 9, 14): "EVENING_ONLY_GANESH_CHATURTHI",
    date(2026, 10, 20): "EVENING_ONLY_DUSSEHRA",
    date(2026, 11, 10): "EVENING_ONLY_DIWALI_BALIPRATIPADA",
    date(2026, 11, 24): "EVENING_ONLY_GURUNANAK_JAYANTI",
}

# The annual circular announces Muhurat trading on this Sunday but defers its
# hours. Fail closed for that date until a later authoritative circular is
# published; do not manufacture a schedule.
PENDING_SPECIAL = {
    date(2026, 11, 8): "SPECIAL_MUHURAT_TIMING_PENDING",
}


def _load(name: str) -> dict[str, object]:
    return json.loads((CALENDAR_ROOT / name).read_text(encoding="utf-8"))


def _extend(
    payload: dict[str, object],
    *,
    version: str,
    exchange: str,
) -> dict[str, object]:
    trading = dict(payload["trading_dates"])  # type: ignore[arg-type]
    non_trading = dict(payload["non_trading_dates"])  # type: ignore[arg-type]
    cursor = date.fromisoformat(payload["coverage_end"]) + timedelta(days=1)  # type: ignore[arg-type]
    while cursor <= END:
        key = cursor.isoformat()
        if cursor in PENDING_SPECIAL:
            non_trading[key] = PENDING_SPECIAL[cursor]
        elif cursor.weekday() >= 5:
            non_trading[key] = "WEEKEND"
        elif exchange == "NSE" and cursor in NSE_HOLIDAYS:
            non_trading[key] = NSE_HOLIDAYS[cursor]
        elif exchange == "MCX" and cursor in MCX_FULL_HOLIDAYS:
            non_trading[key] = MCX_FULL_HOLIDAYS[cursor]
        elif exchange == "MCX" and cursor in MCX_EVENING_ONLY:
            trading[key] = {
                "session_type": MCX_EVENING_ONLY[cursor],
                "open": "17:00:00",
                "close": "23:30:00",
            }
        elif exchange == "NSE":
            trading[key] = {
                "session_type": "REGULAR",
                "open": "09:15:00",
                "close": "15:30:00",
            }
        else:
            trading[key] = {
                "session_type": "REGULAR",
                "open": "09:00:00",
                "close": "23:30:00",
            }
        cursor += timedelta(days=1)
    payload = dict(payload)
    payload["calendar_version"] = version
    payload["coverage_end"] = END.isoformat()
    payload["source_boundary"] = "2026-08-17T00:00:00+05:30"
    payload["trading_dates"] = dict(sorted(trading.items()))
    payload["non_trading_dates"] = dict(sorted(non_trading.items()))
    return payload


def _write(name: str, payload: dict[str, object]) -> str:
    path = CALENDAR_ROOT / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return sha256(path.read_bytes()).hexdigest()


def main() -> int:
    nse_sha = _write(
        NSE_OUTPUT,
        _extend(_load(NSE_BASE), version="2026.1.2", exchange="NSE"),
    )
    mcx_sha = _write(
        MCX_OUTPUT,
        _extend(_load(MCX_BASE), version="2026.1.1", exchange="MCX"),
    )
    manifest = {
        "schema": "KRONOS-MARKET-CALENDAR-MANIFEST-V1",
        "publications": [
            {"file": NSE_OUTPUT, "sha256": nse_sha},
            {"file": MCX_OUTPUT, "sha256": mcx_sha},
        ],
    }
    (CALENDAR_ROOT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
