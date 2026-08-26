# KRONOS Intraday V1 - WO-07A Sponsor Review UX and Batch Transport

**Status:** Implemented amendment
**Owner:** Intraday
**Contract version:** 1.0.0
**Trading authority:** None

## Purpose

WO-07A amends the WO-07 Review workstation with the Sponsor's Swing-style,
paste-first operating flow while preserving Intraday product ownership and
candidate isolation.

Each exact-current Probable remains an independent card and Review Cycle. The
Sponsor focuses a candidate-owned target and pastes one `1D | 1H | 15M | 5M`
TradingView composite with Cmd+V or Ctrl+V. File upload and clipboard paste use
the same bounded `/intraday/review/chart` POST, validation, immutable digest,
Chart Revision and persistence path. There is no global paste target and no
candidate inference.

## Batch Question Pack transport

`CREATE ALL REVIEW PDF` processes current Review candidates in deterministic
canonical-subject order:

- `CHART_READY` with a valid current Chart Revision creates or reuses its own
  governed Question Pack;
- `CHART_REQUIRED` is explicitly skipped;
- an integrity failure is reported for that candidate without contaminating
  successful candidates.

The batch action never merges analytical governance. Every included candidate
retains its own Probables member, Review Cycle, Chart Revision and Review Pack
identity. Repeated execution with unchanged inputs reuses those identities.

The optional combined transport is:

`KRONOS-INTRADAY-REVIEW-BATCH-PDF-V1 / 1.0.0`

Its immutable membership binds the current Probables Run and the ordered
individual Review Pack identities. Its PDF is Sponsor transport convenience
only. Individual canonical Question Pack JSON remains authoritative.

## Persistence and restoration

Batch membership is retained by explicit immutable identity. Current batch
restoration is computed from exact current individual pack identities and an
explicit batch-record lookup; filesystem order, mtime and latest-file scanning
have no authority. Historical runs, cycles, charts, packs and batches remain
immutable.

## Browser and future-answer boundary

The Review page uses a compact responsive multi-card grid, visible keyboard
focus, explicit textual states and large candidate-bound paste targets. The
batch action is Intraday-owned behind the existing same-origin product POST
seam. No shared Browser change is required.

`UPLOAD ALL ANSWERS` is displayed disabled as `NOT YET COMMISSIONED`. WO-07A
does not scan the Answer inbox, invoke Chart Analyst, import answers, establish
Readiness or Promotion, or create trading, Risk or broker authority. WO-09 must
validate any future batch transport as independent exact-cycle answers; one bad
answer cannot contaminate another candidate.
