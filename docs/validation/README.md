# KRONOS Validation and Research Workflow

This folder contains the live validation and research documentation system for KRONOS. It is used to capture chart observations, paper trades, screenshot references, recurring issues, hypotheses, and weekly engineering conclusions.

The core rule is simple: one observation does not justify one code change. A change should normally require repeated evidence unless the observation reveals a clear runtime or calculation defect.

## Workflow

1. User captures an entry, exit, or unusual chart screenshot.
2. The screenshot is reviewed from trader and architecture perspectives.
3. The observation is written as `KR-OBS-XXXX` in [KRONOS_OBSERVATION_LOG.md](KRONOS_OBSERVATION_LOG.md).
4. A paper trade is written as `KR-TRD-XXXX` in [KRONOS_TRADE_JOURNAL.md](KRONOS_TRADE_JOURNAL.md) when applicable.
5. Repeated findings are summarized in [KRONOS_WEEKLY_REVIEW.md](KRONOS_WEEKLY_REVIEW.md).
6. Only approved weekly findings become Codex implementation tasks.

## Documents

- [KRONOS Observation Log](KRONOS_OBSERVATION_LOG.md) — records notable chart behaviour, KRONOS output, independent chart readings, hypotheses, affected engines, priority, and status.
- [KRONOS Trade Journal](KRONOS_TRADE_JOURNAL.md) — records one-lot paper trades, entry and exit screenshots, trade outcome, classification, and trader lessons.
- [KRONOS Weekly Review](KRONOS_WEEKLY_REVIEW.md) — converts repeated observations and paper-trade evidence into approved, deferred, rejected, research, or bug-fix decisions.
- [Pine and TradingView Validation Protocol](TESTING.md) — defines static, compile, visual, and replay/live validation evidence.
- [MCX Metals Validation Record](MCX-METALS-VALIDATION.md) — records current MCX Metals validation evidence and remaining work.

## Decision Frequency Analysis

Use the decision-frequency log when KRONOS appears to produce unusually few BUY READY or SELL READY decisions across a broad chart review.

The CSV source of truth is:

```text
data/validation/decision_frequency/KRONOS_DECISION_FREQUENCY_LOG.csv
```

For each evaluated chart, record the current decision, first unmet requirement, confidence score, trend state, acceptance state, momentum state, and execution state when visible.

Validate the log:

```bash
python3 data/validation/decision_frequency/scripts/analyze_decision_frequency.py --date 2026-07-14 --check
```

Generate the aggregate report:

```bash
python3 data/validation/decision_frequency/scripts/analyze_decision_frequency.py --date 2026-07-14
```

The report ranks WAIT/WATCH/READY outcomes and blocker frequency without changing Pine logic or thresholds.

## Decision Pipeline Metrics

Use the decision-pipeline ledgers to separate end-of-session decision inventory from intraday decision flow.

The CSV sources of truth are:

```text
data/validation/decision_pipeline/KRONOS_DECISION_PIPELINE_SUMMARY.csv
data/validation/decision_pipeline/KRONOS_DECISION_PIPELINE_TRANSITIONS.csv
```

The summary ledger records, for each review universe, the date, session, markets reviewed, number of instruments reviewed, and final counts for WATCH LONG, WATCH SHORT, BUY READY, SELL READY, BUY NOW, SELL NOW, AVOID, and WAIT.

The transition ledger records daily counts for WAIT -> WATCH, WATCH -> READY, READY -> NOW, READY -> WAIT, and WATCH -> WAIT transitions.

Validate the ledgers:

```bash
python3 data/validation/decision_pipeline/scripts/validate_decision_pipeline.py --check
```

These metrics are evidence only. They do not authorize architecture changes, Pine changes, threshold changes, confidence changes, decision changes, execution changes, or implementation changes.

## WATCH Conversion Analysis

Use the WATCH conversion log when KRONOS remains in WATCH LONG or WATCH SHORT while price continues to move in the expected direction.

The CSV source of truth is:

```text
data/validation/watch_conversion/KRONOS_WATCH_CONVERSION_LOG.csv
```

This dataset measures WATCH-to-execution conversion rate, time spent in WATCH, favourable movement before execution, and setups that reverse or expire without execution. It is evidence collection only; one observation must not produce a trading-logic change.

Validate the log:

```bash
python3 data/validation/watch_conversion/scripts/validate_watch_conversion.py
```

## Screenshot References

Screenshots may remain outside Git if they are large. The Markdown documents should store a stable filename or repository path when screenshots are committed.

Do not embed local absolute paths such as `/Users/...`.

Prefer repository-relative paths such as:

```text
assets/validation/2026-07-13/HDFCBANK_1H_entry.png
```

Placeholder screenshot folders are available at:

- `assets/validation/entries/`
- `assets/validation/exits/`
- `assets/validation/observations/`

Do not copy or invent screenshots when creating documentation records.

## Privacy and Safety

Do not commit account numbers, broker balances, personal data, or sensitive trading-account information. Redact screenshots before committing them if they contain private or account-specific details.

## Engineering Discipline

Use engine-level tags consistently when observations appear related to system behaviour. Examples include `KR-335 Price Action`, `KR-345 Relative`, `KR-360 Confidence`, `KR-370 Decision`, `KR-705 Presentation`, `Routing`, and `Market Data`.

Implementation prompts should be written only after the weekly review approves a change or identifies a clear runtime/calculation defect requiring immediate repair.
