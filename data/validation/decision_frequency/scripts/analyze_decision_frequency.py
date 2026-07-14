#!/usr/bin/env python3
"""Generate KRONOS decision-frequency validation reports."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
LOG_PATH = REPO_ROOT / "data" / "validation" / "decision_frequency" / "KRONOS_DECISION_FREQUENCY_LOG.csv"
REPORT_DIR = REPO_ROOT / "docs" / "validation"

REQUIRED_HEADERS = [
    "schema_version",
    "validation_id",
    "review_date",
    "instrument",
    "market",
    "symbol",
    "timeframe",
    "chart_context",
    "current_decision",
    "first_unmet_requirement",
    "confidence",
    "trend_state",
    "acceptance_state",
    "momentum_state",
    "execution_state",
    "screenshot_id",
    "screenshot_path",
    "notes",
    "created_at",
]

DECISION_ORDER = ["WAIT", "WATCH LONG", "WATCH SHORT", "BUY READY", "SELL READY"]
KNOWN_DECISIONS = set(DECISION_ORDER + ["AVOID"])
EXECUTION_ORDER = ["NO TRIGGER", "FORMING", "BUY NOW", "SELL NOW", "EXTENDED", "FAILED"]
KNOWN_EXECUTION_STATES = set(EXECUTION_ORDER)
VALIDATION_ID_RE = re.compile(r"^KR-DFV-\d{8}-\d{3}$")
SCREENSHOT_ID_RE = re.compile(r"^KR-SCR-\d{8}-\d{3}$")
ALLOWED_SCREENSHOT_PREFIXES = (
    "assets/validation/entries/",
    "assets/validation/exits/",
    "assets/validation/observations/",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze KRONOS decision-frequency validation data.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Review date to report, in YYYY-MM-DD format.")
    parser.add_argument("--check", action="store_true", help="Validate the CSV without writing a report.")
    return parser.parse_args()


def read_log() -> list[dict[str, str]]:
    if not LOG_PATH.exists():
        raise ValueError(f"Missing validation log: {LOG_PATH.relative_to(REPO_ROOT)}")

    with LOG_PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        if headers != REQUIRED_HEADERS:
            missing = [header for header in REQUIRED_HEADERS if header not in headers]
            extra = [header for header in headers if header not in REQUIRED_HEADERS]
            details = []
            if missing:
                details.append(f"missing headers: {', '.join(missing)}")
            if extra:
                details.append(f"extra headers: {', '.join(extra)}")
            if not details:
                details.append("header order differs from required schema")
            raise ValueError("Invalid decision-frequency CSV schema: " + "; ".join(details))
        return [{key: (value or "").strip() for key, value in row.items()} for row in reader]


def validate_rows(rows: list[dict[str, str]]) -> None:
    seen_validation_ids: set[str] = set()
    seen_screenshot_ids: set[str] = set()
    errors: list[str] = []

    for line_number, row in enumerate(rows, start=2):
        validation_id = row["validation_id"]
        review_date = row["review_date"]
        current_decision = row["current_decision"].upper()
        execution_state = row["execution_state"].upper()
        confidence = row["confidence"]
        screenshot_id = row["screenshot_id"]
        screenshot_path = row["screenshot_path"]

        if not VALIDATION_ID_RE.match(validation_id):
            errors.append(f"line {line_number}: validation_id must match KR-DFV-YYYYMMDD-###")
        if validation_id in seen_validation_ids:
            errors.append(f"line {line_number}: duplicate validation_id {validation_id}")
        seen_validation_ids.add(validation_id)

        try:
            date.fromisoformat(review_date)
        except ValueError:
            errors.append(f"line {line_number}: review_date must use YYYY-MM-DD")

        if current_decision and current_decision not in KNOWN_DECISIONS:
            errors.append(f"line {line_number}: unknown current_decision {row['current_decision']!r}")

        if execution_state and execution_state not in KNOWN_EXECUTION_STATES:
            errors.append(f"line {line_number}: unknown execution_state {row['execution_state']!r}")

        if confidence:
            try:
                confidence_value = float(confidence)
            except ValueError:
                errors.append(f"line {line_number}: confidence must be numeric")
            else:
                if confidence_value < 0 or confidence_value > 100:
                    errors.append(f"line {line_number}: confidence must be between 0 and 100")

        if screenshot_id:
            if not SCREENSHOT_ID_RE.match(screenshot_id):
                errors.append(f"line {line_number}: screenshot_id must match KR-SCR-YYYYMMDD-###")
            if screenshot_id in seen_screenshot_ids:
                errors.append(f"line {line_number}: duplicate screenshot_id {screenshot_id}")
            seen_screenshot_ids.add(screenshot_id)

        if screenshot_path:
            if Path(screenshot_path).is_absolute():
                errors.append(f"line {line_number}: screenshot_path must be repository-relative")
            if not screenshot_path.startswith(ALLOWED_SCREENSHOT_PREFIXES):
                allowed = ", ".join(ALLOWED_SCREENSHOT_PREFIXES)
                errors.append(f"line {line_number}: screenshot_path must begin with one of: {allowed}")

    if errors:
        raise ValueError("Validation failed:\n" + "\n".join(errors))


def rows_for_date(rows: list[dict[str, str]], report_date: str) -> list[dict[str, str]]:
    return [row for row in rows if row["review_date"] == report_date]


def count_values(rows: list[dict[str, str]], field: str) -> Counter[str]:
    return Counter((row[field].strip() or "Unspecified") for row in rows)


def decision_counts(rows: list[dict[str, str]]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for row in rows:
        decision = row["current_decision"].upper() or "Unspecified"
        counter[decision] += 1
    return counter


def execution_counts(rows: list[dict[str, str]]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for row in rows:
        execution_state = row["execution_state"].upper() or "Unspecified"
        counter[execution_state] += 1
    return counter


def markdown_count_table(title: str, counter: Counter[str], ordered: list[str] | None = None) -> list[str]:
    lines = [f"## {title}", "", "| Value | Count |", "|---|---:|"]
    emitted: set[str] = set()

    if ordered:
        for key in ordered:
            lines.append(f"| {key} | {counter.get(key, 0)} |")
            emitted.add(key)

    for key, value in counter.most_common():
        if key not in emitted:
            lines.append(f"| {key} | {value} |")

    if not counter and not ordered:
        lines.append("| None | 0 |")

    lines.append("")
    return lines


def build_report(rows: list[dict[str, str]], report_date: str) -> str:
    filtered = rows_for_date(rows, report_date)
    decisions = decision_counts(filtered)
    executions = execution_counts(filtered)
    blockers = count_values(filtered, "first_unmet_requirement")
    markets = count_values(filtered, "market")
    timeframes = count_values(filtered, "timeframe")
    trend_states = count_values(filtered, "trend_state")
    acceptance_states = count_values(filtered, "acceptance_state")
    momentum_states = count_values(filtered, "momentum_state")

    open_ready = decisions.get("BUY READY", 0) + decisions.get("SELL READY", 0)
    watch_count = decisions.get("WATCH LONG", 0) + decisions.get("WATCH SHORT", 0)
    buy_now_count = executions.get("BUY NOW", 0)
    sell_now_count = executions.get("SELL NOW", 0)

    lines = [
        f"# KRONOS Decision Frequency Report - {report_date.replace('-', '')}",
        "",
        "## Summary",
        "",
        f"- Date: {report_date}",
        f"- Total charts reviewed: {len(filtered)}",
        f"- WAIT: {decisions.get('WAIT', 0)}",
        f"- WATCH LONG: {decisions.get('WATCH LONG', 0)}",
        f"- WATCH SHORT: {decisions.get('WATCH SHORT', 0)}",
        f"- BUY READY: {decisions.get('BUY READY', 0)}",
        f"- SELL READY: {decisions.get('SELL READY', 0)}",
        f"- READY total: {open_ready}",
        f"- WATCH total: {watch_count}",
        f"- BUY NOW: {buy_now_count}",
        f"- SELL NOW: {sell_now_count}",
        f"- Execution NOW total: {buy_now_count + sell_now_count}",
        f"- Unique instruments: {len({row['instrument'] for row in filtered if row['instrument']})}",
        f"- Repository rows in source log: {len(rows)}",
        f"- Trading logic changed: No",
        "",
    ]

    if not filtered:
        lines.extend([
            "No decision-frequency rows are recorded for this date yet.",
            "",
            "This is a valid empty report. Append approved chart-level validation rows to `data/validation/decision_frequency/KRONOS_DECISION_FREQUENCY_LOG.csv`, then rerun the analyzer.",
            "",
        ])

    lines.extend(markdown_count_table("Decision Distribution", decisions, DECISION_ORDER))
    lines.extend(markdown_count_table("Execution-State Distribution", executions, EXECUTION_ORDER))
    lines.extend(markdown_count_table("Blocking Conditions Ranked", blockers))
    lines.extend(markdown_count_table("Markets", markets))
    lines.extend(markdown_count_table("Timeframes", timeframes))
    lines.extend(markdown_count_table("Trend States", trend_states))
    lines.extend(markdown_count_table("Acceptance States", acceptance_states))
    lines.extend(markdown_count_table("Momentum States", momentum_states))

    lines.extend([
        "## Unresolved Validation Questions",
        "",
        "- Does execution-state scarcity reflect expected strictness or an execution-timing bottleneck?",
        "- Which blocker dominates after the full reviewed chart set is entered with chart-level rows?",
        "- Are READY states failing to advance because KR-380 execution timing is rare, or because execution-state fields were not captured in the reviewed screenshots?",
        "- No trading logic, thresholds, confidence calculations, architecture, or execution rules were changed by this validation report.",
        "",
    ])

    lines.extend([
        "## Chart-Level Records",
        "",
        "| Validation ID | Instrument | Market | Timeframe | Decision | First Unmet Requirement | Confidence | Trend | Acceptance | Momentum | Execution |",
        "|---|---|---|---|---|---|---:|---|---|---|---|",
    ])

    for row in filtered:
        lines.append(
            "| {validation_id} | {instrument} | {market} | {timeframe} | {current_decision} | {first_unmet_requirement} | {confidence} | {trend_state} | {acceptance_state} | {momentum_state} | {execution_state} |".format(
                validation_id=row["validation_id"] or "-",
                instrument=row["instrument"] or "-",
                market=row["market"] or "-",
                timeframe=row["timeframe"] or "-",
                current_decision=row["current_decision"] or "-",
                first_unmet_requirement=row["first_unmet_requirement"] or "-",
                confidence=row["confidence"] or "-",
                trend_state=row["trend_state"] or "-",
                acceptance_state=row["acceptance_state"] or "-",
                momentum_state=row["momentum_state"] or "-",
                execution_state=row["execution_state"] or "-",
            )
        )

    if not filtered:
        lines.append("| - | - | - | - | - | - | - | - | - | - | - |")

    lines.extend([
        "",
        "## Method",
        "",
        "- CSV source of truth: `data/validation/decision_frequency/KRONOS_DECISION_FREQUENCY_LOG.csv`",
        "- Current Decision maps to KR-370 / KR-705 Decision.",
        "- First unmet requirement maps to KR-370 primary blocker or the first unchecked KR-705 Need item.",
        "- Confidence maps to KR-360 score.",
        "- Trend, Acceptance, and Momentum map to KR-300, KR-320, and KR-330 displayed states.",
        "- Execution maps to KR-380 displayed state when visible.",
        "- This report makes no trading decision and changes no thresholds.",
        "",
        "## Known Limitations",
        "",
        "- TradingView chart values must be entered into the CSV before aggregate statistics can represent the reviewed chart universe.",
        "- The analyzer ranks recorded blockers; it does not infer missing chart states from screenshots.",
        "- Empty reports are expected until approved validation rows are recorded.",
        "",
    ])

    return "\n".join(lines)


def main() -> int:
    args = parse_args()

    try:
        date.fromisoformat(args.date)
        rows = read_log()
        validate_rows(rows)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.check:
        print(f"Validation OK: {LOG_PATH.relative_to(REPO_ROOT)} ({len(rows)} rows)")
        return 0

    report_path = REPORT_DIR / f"DECISION_FREQUENCY_REPORT_{args.date.replace('-', '')}.md"
    report_path.write_text(build_report(rows, args.date), encoding="utf-8")
    print(f"Wrote {report_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
