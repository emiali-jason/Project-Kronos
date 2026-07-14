# KRONOS Decision Frequency Validation

This folder records chart-level decision-frequency validation for KRONOS.

The purpose is to determine whether BUY READY and SELL READY are rare because the market evidence does not qualify, or because one KRONOS rule is acting as a bottleneck.

## Source Of Truth

`KRONOS_DECISION_FREQUENCY_LOG.csv` is the source of truth.

Do not enter fictional rows. Each row must come from a reviewed TradingView chart or an approved screenshot review.

## Required Chart Fields

For each evaluated chart, record:

- Current Decision: use KR-370 / KR-705 Decision text.
- First unmet requirement: use KR-370 primary blocker or the first unchecked Need item shown in KR-705.
- Confidence: use KR-360 score.
- Trend state: use KR-300 trend stage text or KR-705 trend display.
- Acceptance state: use KR-320 acceptance text.
- Momentum state: use KR-330 momentum text.
- Execution state: use KR-380 execution state when visible.

## ID Convention

Use:

```text
KR-DFV-YYYYMMDD-###
```

Example:

```text
KR-DFV-20260714-001
```

## Screenshot Paths

Screenshot paths must be repository-relative. Preferred locations:

- `assets/validation/observations/`
- `assets/validation/entries/`
- `assets/validation/exits/`

## Run Validation

From the repository root:

```bash
python3 data/validation/decision_frequency/scripts/analyze_decision_frequency.py --date 2026-07-14 --check
```

## Generate Report

From the repository root:

```bash
python3 data/validation/decision_frequency/scripts/analyze_decision_frequency.py --date 2026-07-14
```

The report is written to:

```text
docs/validation/DECISION_FREQUENCY_REPORT_YYYYMMDD.md
```
