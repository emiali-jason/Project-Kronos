# KR-340 Decision Pipeline Metrics

## Purpose

Collect longitudinal evidence describing the behaviour of the KRONOS decision pipeline.

This validation programme records daily summaries and transition statistics only. It contains no conclusions and no engineering recommendations.

KR-340 Decision Pipeline Metrics is a validation programme. It does not rename or modify the KR-340 Review Readiness Engine.

## Scope

The Trading Desk shall continue to observe, validate, and record KRONOS behaviour.

In addition to individual Validation Observations, the Trading Desk shall maintain a daily Decision Pipeline Summary for each review universe, such as NSE, MCX, or US.

No engineering recommendation shall be made from these metrics alone.

## Decision Inventory

Decision inventory records the state of KRONOS at the end of a reviewed session.

| Decision State | Count |
|---|---:|
| WATCH LONG |  |
| WATCH SHORT |  |
| BUY READY |  |
| SELL READY |  |
| BUY NOW |  |
| SELL NOW |  |
| AVOID |  |
| WAIT |  |

Each daily summary should also record:

- Date.
- Session.
- Market or markets reviewed.
- Number of instruments reviewed.

## Decision Flow

Decision flow records how KRONOS behaved throughout the session.

| Transition | Count |
|---|---:|
| WAIT -> WATCH LONG |  |
| WAIT -> WATCH SHORT |  |
| WATCH -> BUY READY |  |
| WATCH -> SELL READY |  |
| BUY READY -> BUY NOW |  |
| SELL READY -> SELL NOW |  |
| BUY READY -> WAIT |  |
| SELL READY -> WAIT |  |
| WATCH -> WAIT |  |

These metrics measure flow, not merely the final distribution of states.

## Promotion Observations

For any instrument that remains in WATCH LONG or WATCH SHORT, record an individual observation only if:

- it remained in WATCH for an unusually long period;
- it experienced significant favourable movement while still in WATCH; or
- it returned to WAIT or expired without reaching an executable state.

Record facts only. Do not interpret.

## Architectural Questions Supported

These metrics exist to help Master Architecture evaluate questions such as:

- How frequently do instruments enter WATCH?
- How frequently do they progress to BUY READY or SELL READY?
- How frequently do they progress to BUY NOW or SELL NOW?
- What is the average time spent in each decision state?
- How often do opportunities expire before promotion?
- Are READY states converting at the expected frequency?

## Engineering Policy

Daily observations may:

- increase confidence;
- identify repeatable patterns; or
- trigger future architectural review.

Daily observations do not authorize architecture changes, Pine changes, threshold changes, confidence changes, decision changes, execution changes, or implementation changes.

## Data Ledgers

CSV ledgers live at:

```text
data/validation/decision_pipeline/KRONOS_DECISION_PIPELINE_SUMMARY.csv
data/validation/decision_pipeline/KRONOS_DECISION_PIPELINE_TRANSITIONS.csv
```

Validate the ledgers from the repository root:

```bash
python3 data/validation/decision_pipeline/scripts/validate_decision_pipeline.py --check
```

## No Conclusions

No conclusions are recorded in this document.

## No Recommendations

No recommendations are recorded in this document.
