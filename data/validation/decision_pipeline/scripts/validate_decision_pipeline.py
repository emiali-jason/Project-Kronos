#!/usr/bin/env python3
"""Validate KRONOS Decision Pipeline Metrics ledgers."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = REPO_ROOT / "data" / "validation" / "decision_pipeline"
SUMMARY_PATH = DATA_DIR / "KRONOS_DECISION_PIPELINE_SUMMARY.csv"
TRANSITIONS_PATH = DATA_DIR / "KRONOS_DECISION_PIPELINE_TRANSITIONS.csv"

SUMMARY_HEADERS = [
    "schema_version",
    "summary_id",
    "review_date",
    "session",
    "review_universe",
    "markets_reviewed",
    "instruments_reviewed",
    "watch_long_count",
    "watch_short_count",
    "buy_ready_count",
    "sell_ready_count",
    "buy_now_count",
    "sell_now_count",
    "avoid_count",
    "wait_count",
    "notes",
    "created_at",
    "updated_at",
]

TRANSITION_HEADERS = [
    "schema_version",
    "transition_id",
    "review_date",
    "session",
    "review_universe",
    "markets_reviewed",
    "transition",
    "transition_count",
    "notes",
    "created_at",
    "updated_at",
]

SUMMARY_ID_RE = re.compile(r"^KR-DPS-\d{8}-\d{3}$")
TRANSITION_ID_RE = re.compile(r"^KR-DPT-\d{8}-\d{3}$")

SUMMARY_COUNT_FIELDS = [
    "instruments_reviewed",
    "watch_long_count",
    "watch_short_count",
    "buy_ready_count",
    "sell_ready_count",
    "buy_now_count",
    "sell_now_count",
    "avoid_count",
    "wait_count",
]

ALLOWED_TRANSITIONS = {
    "WAIT -> WATCH LONG",
    "WAIT -> WATCH SHORT",
    "WATCH -> BUY READY",
    "WATCH -> SELL READY",
    "BUY READY -> BUY NOW",
    "SELL READY -> SELL NOW",
    "BUY READY -> WAIT",
    "SELL READY -> WAIT",
    "WATCH -> WAIT",
}


def read_csv(path: Path, expected_headers: list[str], errors: list[str]) -> list[dict[str, str]]:
    if not path.exists():
        errors.append(f"missing file: {path.relative_to(REPO_ROOT)}")
        return []

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        if headers != expected_headers:
            errors.append(
                "invalid schema for "
                f"{path.relative_to(REPO_ROOT)}\n"
                f"expected: {', '.join(expected_headers)}\n"
                f"actual: {', '.join(headers)}"
            )
            return []
        return [{key: (value or "").strip() for key, value in row.items()} for row in reader]


def validate_date(value: str, field: str, line_number: int, errors: list[str]) -> None:
    try:
        date.fromisoformat(value)
    except ValueError:
        errors.append(f"line {line_number}: {field} must use YYYY-MM-DD")


def validate_non_negative_int(value: str, field: str, line_number: int, errors: list[str]) -> None:
    if value == "":
        errors.append(f"line {line_number}: {field} is required")
        return
    try:
        parsed = int(value)
    except ValueError:
        errors.append(f"line {line_number}: {field} must be an integer")
        return
    if parsed < 0:
        errors.append(f"line {line_number}: {field} must be non-negative")


def validate_summary_rows(rows: list[dict[str, str]], errors: list[str]) -> None:
    seen_ids: set[str] = set()
    for line_number, row in enumerate(rows, start=2):
        summary_id = row["summary_id"]
        if not SUMMARY_ID_RE.match(summary_id):
            errors.append(f"line {line_number}: summary_id must match KR-DPS-YYYYMMDD-###")
        if summary_id in seen_ids:
            errors.append(f"line {line_number}: duplicate summary_id {summary_id}")
        seen_ids.add(summary_id)

        validate_date(row["review_date"], "review_date", line_number, errors)

        for field in SUMMARY_COUNT_FIELDS:
            validate_non_negative_int(row[field], field, line_number, errors)


def validate_transition_rows(rows: list[dict[str, str]], errors: list[str]) -> None:
    seen_ids: set[str] = set()
    for line_number, row in enumerate(rows, start=2):
        transition_id = row["transition_id"]
        if not TRANSITION_ID_RE.match(transition_id):
            errors.append(f"line {line_number}: transition_id must match KR-DPT-YYYYMMDD-###")
        if transition_id in seen_ids:
            errors.append(f"line {line_number}: duplicate transition_id {transition_id}")
        seen_ids.add(transition_id)

        validate_date(row["review_date"], "review_date", line_number, errors)

        if row["transition"] not in ALLOWED_TRANSITIONS:
            errors.append(f"line {line_number}: unsupported transition {row['transition']!r}")

        validate_non_negative_int(row["transition_count"], "transition_count", line_number, errors)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate KRONOS Decision Pipeline Metrics ledgers.")
    parser.add_argument("--check", action="store_true", help="Validate ledgers and exit non-zero on failure.")
    parser.parse_args()

    errors: list[str] = []
    summary_rows = read_csv(SUMMARY_PATH, SUMMARY_HEADERS, errors)
    transition_rows = read_csv(TRANSITIONS_PATH, TRANSITION_HEADERS, errors)

    if not errors:
        validate_summary_rows(summary_rows, errors)
        validate_transition_rows(transition_rows, errors)

    if errors:
        print("Decision Pipeline Metrics validation failed:", file=sys.stderr)
        print("\n".join(errors), file=sys.stderr)
        return 1

    print(
        "Validation OK: "
        f"{SUMMARY_PATH.relative_to(REPO_ROOT)} ({len(summary_rows)} rows), "
        f"{TRANSITIONS_PATH.relative_to(REPO_ROOT)} ({len(transition_rows)} rows)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
