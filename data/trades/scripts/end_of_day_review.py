#!/usr/bin/env python3
"""Generate a KRONOS end-of-day validation report.

The script reads existing trade, observation, and daily-review CSV files and
produces a Markdown report in docs/validation. It does not create or modify
trade database records.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Sequence


REPO_ROOT = Path(__file__).resolve().parents[3]
TRADE_DIR = REPO_ROOT / "data" / "trades"
VALIDATION_DIR = REPO_ROOT / "docs" / "validation"

TRADE_LEDGER = TRADE_DIR / "KRONOS_TRADE_LEDGER.csv"
OBSERVATION_LEDGER = TRADE_DIR / "KRONOS_OBSERVATION_LEDGER.csv"
DAILY_REVIEW_LEDGER = TRADE_DIR / "KRONOS_DAILY_REVIEW.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a KRONOS end-of-day validation report.")
    parser.add_argument(
        "--date",
        dest="report_date",
        default=date.today().isoformat(),
        help="Report date in YYYY-MM-DD format. Defaults to today.",
    )
    return parser.parse_args()


def normalize_date(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise SystemExit(f"Invalid --date value {value!r}; expected YYYY-MM-DD") from exc


def compact_date(value: str) -> str:
    return value.replace("-", "")


def read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        raise SystemExit(f"Missing required CSV: {path.relative_to(REPO_ROOT)}")
    with path.open(newline="", encoding="utf-8") as handle:
        return [
            {key: (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle)
        ]


def filter_by_date(rows: Sequence[Dict[str, str]], field: str, report_date: str) -> List[Dict[str, str]]:
    return [row for row in rows if row.get(field) == report_date]


def lower_join(row: Dict[str, str], fields: Sequence[str]) -> str:
    return " ".join(row.get(field, "") for field in fields).lower()


def count_matching(rows: Sequence[Dict[str, str]], fields: Sequence[str], keywords: Sequence[str]) -> int:
    count = 0
    for row in rows:
        haystack = lower_join(row, fields)
        if any(keyword in haystack for keyword in keywords):
            count += 1
    return count


def classify_observations(observations: Sequence[Dict[str, str]]) -> Dict[str, int]:
    fields = ("observation_type", "summary", "action_required")
    return {
        "watch": count_matching(observations, fields, ("watch long", "watch short", "watch")),
        "no_action": count_matching(observations, fields, ("no action", "observation only", "no trade", "avoid", "wait")),
        "trade_management": count_matching(observations, fields, ("trade management", "manage", "open trades reviewed", "stop", "target")),
        "possible_bug": count_matching(observations, fields, ("bug", "ui", "presentation", "hypothesis", "conflicting evidence", "architectural review")),
    }


def status_counts(trades: Sequence[Dict[str, str]]) -> Counter:
    return Counter((trade.get("status") or "blank").lower() for trade in trades)


def get_git_stat() -> str:
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return "Git status unavailable."

    output = result.stdout.strip()
    if not output:
        return "Working tree clean."
    return output


def markdown_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(value).replace("\n", " ") for value in row) + " |")
    return "\n".join(lines)


def build_report(report_date: str) -> str:
    trades = read_csv(TRADE_LEDGER)
    observations = read_csv(OBSERVATION_LEDGER)
    daily_reviews = read_csv(DAILY_REVIEW_LEDGER)

    trades_today = filter_by_date(trades, "trade_date", report_date)
    observations_today = filter_by_date(observations, "observation_date", report_date)
    reviews_today = filter_by_date(daily_reviews, "review_date", report_date)

    trade_status_counts = status_counts(trades)
    open_trades = sum(trade_status_counts[status] for status in ("open", "active"))
    closed_trades = trade_status_counts["closed"]
    classification_counts = classify_observations(observations_today)
    instruments = sorted({row.get("instrument", "") for row in observations_today if row.get("instrument")})
    markets = Counter(row.get("market", "blank") or "blank" for row in observations_today)

    observation_rows = [
        [
            row.get("observation_id", ""),
            row.get("instrument", ""),
            row.get("market", ""),
            row.get("timeframe", ""),
            row.get("action_required", ""),
        ]
        for row in observations_today
    ]

    repo_stats = [
        ["Trade ledger rows", str(len(trades))],
        ["Observation ledger rows", str(len(observations))],
        ["Daily review rows", str(len(daily_reviews))],
        ["Instruments observed today", str(len(instruments))],
        ["Markets observed today", ", ".join(f"{key}: {value}" for key, value in sorted(markets.items())) or "None"],
    ]

    summary_rows = [
        ["Date", report_date],
        ["Total charts reviewed", str(len(observations_today))],
        ["Observations created", str(len(observations_today))],
        ["Paper trades created", str(len(trades_today))],
        ["Open trades", str(open_trades)],
        ["Closed trades", str(closed_trades)],
        ["WATCH count", str(classification_counts["watch"])],
        ["NO ACTION count", str(classification_counts["no_action"])],
        ["TRADE MANAGEMENT count", str(classification_counts["trade_management"])],
        ["POSSIBLE BUG count", str(classification_counts["possible_bug"])],
    ]

    report = [
        f"# KRONOS Daily Validation Report - {report_date}",
        "",
        "## Summary",
        "",
        markdown_table(["Metric", "Value"], summary_rows),
        "",
        "## Observations",
        "",
        markdown_table(
            ["Observation ID", "Instrument", "Market", "Timeframe", "Action"],
            observation_rows,
        )
        if observation_rows
        else "No observations recorded for this date.",
        "",
        "## Daily Review Records",
        "",
        markdown_table(
            ["Review ID", "Session", "Instruments Reviewed", "Follow-Up Required"],
            [
                [
                    row.get("review_id", ""),
                    row.get("market_session", ""),
                    row.get("instruments_reviewed", ""),
                    row.get("follow_up_required", ""),
                ]
                for row in reviews_today
            ],
        )
        if reviews_today
        else "No daily review records found for this date.",
        "",
        "## Repository Statistics",
        "",
        markdown_table(["Metric", "Value"], repo_stats),
        "",
        "## Git Status",
        "",
        "```text",
        get_git_stat(),
        "```",
        "",
        "## Notes",
        "",
        "- This report is generated from CSV files only.",
        "- CSV files remain the source of truth.",
        "- This report does not create trades, observations, or trading decisions.",
    ]

    return "\n".join(report) + "\n"


def write_report(report_date: str, content: str) -> Path:
    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)
    report_path = VALIDATION_DIR / f"DAILY_REPORT_{compact_date(report_date)}.md"
    report_path.write_text(content, encoding="utf-8")
    return report_path


def main() -> int:
    report_date = normalize_date(parse_args().report_date)
    report_path = write_report(report_date, build_report(report_date))
    print(f"Daily validation report written: {report_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
