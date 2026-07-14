#!/usr/bin/env python3
"""Validate the KRONOS WATCH conversion log."""

from __future__ import annotations

import csv
import re
import sys
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
LOG_PATH = REPO_ROOT / "data" / "validation" / "watch_conversion" / "KRONOS_WATCH_CONVERSION_LOG.csv"

REQUIRED_HEADERS = [
    "observation_id",
    "date",
    "market",
    "instrument",
    "direction",
    "watch_start_time",
    "watch_start_price",
    "blocker_at_start",
    "maximum_favourable_price",
    "maximum_favourable_excursion",
    "maximum_adverse_price",
    "maximum_adverse_excursion",
    "current_or_final_state",
    "execution_time",
    "execution_price",
    "time_in_watch_minutes",
    "converted_to_execution",
    "expired_or_reversed",
    "screenshot_ids",
    "notes",
]

OBSERVATION_ID_RE = re.compile(r"^KR-OBS-\d{8}-\d{3}$")
SCREENSHOT_ID_RE = re.compile(r"^KR-SCR-\d{8}-\d{3}$")
VALID_DIRECTIONS = {"LONG", "SHORT"}
VALID_STATES = {"WATCH LONG", "WATCH SHORT", "BUY NOW", "SELL NOW", "NO TRIGGER", "FORMING", "EXTENDED", "FAILED", ""}
VALID_BOOL = {"true", "false", ""}


def validate_number(value: str, field: str, line_number: int, errors: list[str]) -> None:
    if not value:
        return
    try:
        float(value)
    except ValueError:
        errors.append(f"line {line_number}: {field} must be numeric when present")


def main() -> int:
    if not LOG_PATH.exists():
        print(f"Missing log: {LOG_PATH.relative_to(REPO_ROOT)}", file=sys.stderr)
        return 1

    with LOG_PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        if headers != REQUIRED_HEADERS:
            print("Invalid WATCH conversion schema", file=sys.stderr)
            print(f"Expected: {', '.join(REQUIRED_HEADERS)}", file=sys.stderr)
            print(f"Actual: {', '.join(headers)}", file=sys.stderr)
            return 1
        rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]

    errors: list[str] = []
    seen_observations: set[str] = set()

    for line_number, row in enumerate(rows, start=2):
        observation_id = row["observation_id"]
        if not OBSERVATION_ID_RE.match(observation_id):
            errors.append(f"line {line_number}: observation_id must match KR-OBS-YYYYMMDD-###")
        if observation_id in seen_observations:
            errors.append(f"line {line_number}: duplicate observation_id {observation_id}")
        seen_observations.add(observation_id)

        try:
            date.fromisoformat(row["date"])
        except ValueError:
            errors.append(f"line {line_number}: date must use YYYY-MM-DD")

        if row["direction"] not in VALID_DIRECTIONS:
            errors.append(f"line {line_number}: direction must be LONG or SHORT")

        if row["current_or_final_state"] not in VALID_STATES:
            errors.append(f"line {line_number}: unsupported current_or_final_state {row['current_or_final_state']!r}")

        if row["converted_to_execution"] not in VALID_BOOL:
            errors.append(f"line {line_number}: converted_to_execution must be true, false, or blank")

        if row["expired_or_reversed"] not in VALID_BOOL:
            errors.append(f"line {line_number}: expired_or_reversed must be true, false, or blank")

        for field in [
            "watch_start_price",
            "maximum_favourable_price",
            "maximum_favourable_excursion",
            "maximum_adverse_price",
            "maximum_adverse_excursion",
            "execution_price",
            "time_in_watch_minutes",
        ]:
            validate_number(row[field], field, line_number, errors)

        if row["screenshot_ids"]:
            for screenshot_id in [item.strip() for item in row["screenshot_ids"].split(";")]:
                if screenshot_id and not SCREENSHOT_ID_RE.match(screenshot_id):
                    errors.append(f"line {line_number}: screenshot_ids must contain KR-SCR-YYYYMMDD-### values")

    if errors:
        print("WATCH conversion validation failed:", file=sys.stderr)
        print("\n".join(errors), file=sys.stderr)
        return 1

    print(f"Validation OK: {LOG_PATH.relative_to(REPO_ROOT)} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
