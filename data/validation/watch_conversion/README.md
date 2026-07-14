# KRONOS WATCH Conversion Validation

This dataset measures how KRONOS WATCH states evolve after directional evidence appears.

It is for evidence collection only. A single row must not be used to change thresholds, confidence calculations, execution logic, or architecture.

## Source Of Truth

`KRONOS_WATCH_CONVERSION_LOG.csv` is the source of truth.

## What This Dataset Measures

- WATCH-to-execution conversion rate.
- Time spent in WATCH before execution, expiration, reversal, or continued waiting.
- Favourable movement that occurred before execution.
- Adverse movement that occurred while still in WATCH.
- Setups that reversed or expired without execution.

## Data Rules

- Record only values visible in screenshots or explicitly approved from review discussion.
- Preserve blanks when timestamps, prices, blockers, or screenshot links are unavailable.
- Use repository-relative screenshot IDs and paths only after screenshots exist in the repository.
- Do not infer BUY NOW, SELL NOW, or execution timing from price movement alone.
- Do not generate conclusions from one observation.

## Current Interpretation Rules

`converted_to_execution` should be:

- `true` only when BUY NOW or SELL NOW was observed.
- `false` when the setup remained WATCH or explicitly ended without execution.
- blank when the outcome is unknown.

`expired_or_reversed` should remain blank unless the reviewed evidence confirms expiration or reversal.

## Validate

From the repository root:

```bash
python3 data/validation/watch_conversion/scripts/validate_watch_conversion.py
```

