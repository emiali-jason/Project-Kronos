# KRONOS Decision Pipeline Metrics

This folder records daily Decision Pipeline Summary data for KRONOS.

The programme separates decision inventory from decision flow:

- `KRONOS_DECISION_PIPELINE_SUMMARY.csv` records the end-of-session distribution of KRONOS decision states.
- `KRONOS_DECISION_PIPELINE_TRANSITIONS.csv` records how decisions moved between states during the reviewed session.

These records are evidence only. They do not authorize architecture changes, Pine changes, threshold changes, confidence changes, decision changes, or execution changes.

## Source Of Truth

The CSV files in this folder are the source of truth.

Do not enter fictional rows. Each row must come from a Trading Desk-reviewed session summary.

## Daily Summary Fields

For each review universe, record:

- Date.
- Session.
- Market or markets reviewed.
- Number of instruments reviewed.
- Counts for WATCH LONG, WATCH SHORT, BUY READY, SELL READY, BUY NOW, SELL NOW, AVOID, and WAIT.

## Transition Fields

For each review universe, record counts for observed transitions:

- WAIT -> WATCH LONG
- WAIT -> WATCH SHORT
- WATCH -> BUY READY
- WATCH -> SELL READY
- BUY READY -> BUY NOW
- SELL READY -> SELL NOW
- BUY READY -> WAIT
- SELL READY -> WAIT
- WATCH -> WAIT

Transition rows measure flow. They should not be treated as final decision distribution.

## Promotion Observation Rule

Create individual promotion observations only when an instrument:

- remains in WATCH for an unusually long period;
- experiences significant favourable movement while still in WATCH; or
- returns to WAIT or expires without reaching an executable state.

Record facts only. Do not interpret.

## Validate

From the repository root:

```bash
python3 data/validation/decision_pipeline/scripts/validate_decision_pipeline.py --check
```

The validator checks CSV schemas, ID formats, duplicate IDs, dates, allowed transitions, and non-negative count fields.
