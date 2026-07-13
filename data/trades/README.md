# KRONOS Trade Database

The KRONOS Trade Database stores approved paper trades, observations, screenshot references, and daily review records for Project KRONOS.

This database is a repository-maintained record system. It does not perform trading analysis and does not decide whether a trade should be created.

## Role Boundaries

- Main ChatGPT chat performs trading analysis and decides whether an observation or paper trade should be recorded.
- ChatGPT Work coordinates repository tasks and prepares implementation requests.
- Codex records approved data and maintains repository structure.
- Codex must not independently create trades, interpret screenshots, or make trading decisions.

## Source Of Truth

CSV files are the source of truth.

The Excel workbook is generated from the CSV files and should not be edited as the primary record.

## Files

| File | Purpose |
|------|---------|
| `KRONOS_TRADE_LEDGER.csv` | Master paper trade ledger. |
| `KRONOS_OBSERVATION_LEDGER.csv` | Approved market and architecture observations. |
| `KRONOS_SCREENSHOT_INDEX.csv` | Repository-relative screenshot index. |
| `KRONOS_DAILY_REVIEW.csv` | Daily review summaries. |
| `KRONOS_TRADE_LEDGER.xlsx` | Generated review workbook. |
| `templates/TRADE_RECORD_TEMPLATE.md` | Markdown template for individual trade notes. |
| `templates/DAILY_REVIEW_TEMPLATE.md` | Markdown template for daily review notes. |
| `scripts/generate_trade_workbook.py` | Validates CSV files and rebuilds the workbook. |

## ID Conventions

Use stable KR-prefixed IDs:

- Trades: `KR-TRD-YYYYMMDD-###`
- Observations: `KR-OBS-YYYYMMDD-###`
- Screenshots: `KR-SCR-YYYYMMDD-###`
- Daily reviews: `KR-REV-YYYYMMDD`

IDs must not depend on Excel row numbers.

## Screenshot Paths

Screenshot paths must be repository-relative and must live under:

```text
assets/validation/entries/
assets/validation/exits/
assets/validation/observations/
```

Do not use local absolute paths.

Example:

```text
assets/validation/observations/KR-SCR-20260712-001-silver-4h.png
```

## Engine Evidence Snapshot

Trade and observation records include a structured evidence snapshot:

- `ev_kr300_trend_stage`
- `ev_kr310_trend_quality`
- `ev_kr315_compression`
- `ev_kr320_acceptance`
- `ev_kr330_momentum`
- `ev_kr335_price_action`
- `ev_kr340_review_readiness`
- `ev_kr345_relative_intelligence`

These fields should be populated only from approved analysis. Leave them blank when not available.

## Trade Source

`trade_source` records where the trade idea came from.

Examples include:

- `ChatGPT Screenshot Review`
- `Weekly Review`
- `Manual Backtest`
- `Approved Research Note`

Only use values supported by the approved workflow.

## Validation

Run from the repository root:

```bash
python3 data/trades/scripts/generate_trade_workbook.py --check
```

The script validates required headers, ID formats, duplicate IDs, and screenshot path rules.

## Regenerating The Workbook

Run from the repository root:

```bash
python3 data/trades/scripts/generate_trade_workbook.py
```

The script validates the CSV files and rebuilds:

```text
data/trades/KRONOS_TRADE_LEDGER.xlsx
```

## End-Of-Day Validation Report

Run from the repository root:

```bash
python3 data/trades/scripts/end_of_day_review.py
```

The script reads the trade, observation, and daily-review CSV files and writes:

```text
docs/validation/DAILY_REPORT_YYYYMMDD.md
```

To generate a report for a specific date:

```bash
python3 data/trades/scripts/end_of_day_review.py --date 2026-07-13
```

The report summarizes charts reviewed, observations, paper trades, open/closed trades, validation categories, and repository statistics. It does not create trade or observation records.

## Git Rules

- Commit CSV changes as the durable record.
- Treat the workbook as generated review output.
- Keep screenshot paths relative.
- Do not duplicate records across ledgers.
- Do not add fictional trades or placeholder market records.
