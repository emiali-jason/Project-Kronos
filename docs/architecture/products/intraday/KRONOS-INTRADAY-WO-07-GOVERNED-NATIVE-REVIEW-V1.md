# KRONOS Intraday V1 - WO-07 Governed Native Review

**Status:** Implemented foundation
**Owner:** Intraday
**Contract version:** 1.0.0
**Trading authority:** None

## Purpose

WO-07 binds an exact-current Long or Short Probable to one governed visual
review cycle. It does not rerun Discovery or Probables and does not call the
Provider or Chart Analyst.

```text
exact-current Probable
  -> immutable Review Handoff
  -> immutable Review Cycle (CHART_REQUIRED)
  -> Sponsor manual 1D | 1H | 15M | 5M composite
  -> immutable Chart Revision (CHART_READY)
  -> canonical Question Pack JSON
  -> deterministic Sponsor PDF transport
  -> STOP
```

Not Admitted, Unavailable and superseded Probables cannot originate a current
Review Cycle. Earlier cycles remain immutable historical evidence when a later
Probables run supersedes them.

## Ownership and identities

Intraday owns:

- `KRONOS-INTRADAY-REVIEW-HANDOFF-V1 / 1.0.0`;
- `KRONOS-INTRADAY-REVIEW-CYCLE-V1 / 1.0.0`;
- `KRONOS-INTRADAY-CHART-ARTIFACT-V1 / 1.0.0`;
- `KRONOS-INTRADAY-CHART-REVISION-V1 / 1.0.0`;
- `KRONOS-INTRADAY-CHART-ANALYST-QUESTION-SET-V1 / 1.0.0`;
- `KRONOS-INTRADAY-VISUAL-REVIEW-QUESTION-PACK-V1 / 1.0.0`;
- `KRONOS-INTRADAY-CURRENT-REVIEW-POINTER-V1 / 1.0.0`.

The exact evidence cycle binds Probables Run, Probables member, Discovery
run/member, canonical subject, observation boundary, Review Cycle/Request,
Chart Revision and Review Pack. Instrument name, revision ordinal, filename,
directory order and mtime are never sufficient restoration authority.

Every replacement image creates a new immutable Chart Revision. Replaying the
same image for the same active cycle is idempotent. A new chart creates a new
Question Pack; a new Probables run creates a new Review Cycle even when the
instrument and direction are unchanged. This prevents the Swing BEL-class
same-instrument/same-revision restoration defect.

## Chart intake and storage

The Sponsor supplies exactly one composite containing completed 1D, 1H, 15M
and 5M panels. KRONOS does not scrape or authenticate to TradingView, generate
a Kite substitute, infer missing panels, or OCR the image in WO-07.

Only bounded, decodable PNG and JPEG payloads are accepted. Storage is
append-only, digest-bound, non-executable and derived exclusively from governed
identities. User filenames never select filesystem paths. The Browser route is
same-origin, sponsor-work-admitted and capped at 25 MiB by the shared generic
product POST seam.

## Question Pack

The constitutional order is Q1 through Q10, with no Q11. The frozen global
observation statuses are `OBSERVED`, `PARTIAL`, `NOT_VISIBLE`,
`NOT_APPLICABLE`, `UNAVAILABLE` and `INVALID`. `UNCLEAR` is a substantive
answer when evidence is visible and is not equivalent to `NOT_VISIBLE`.

Q7, Q8 and Q9 use one typed multi-panel scope: 15M + 5M. Q10 preserves its
conditional null and material-observation instructions. Exact wording, allowed
values and scopes live in the governed contract and are validated before
persistence or export.

The Question Pack supplies expected canonical identity and proposed direction.
It never forces the future independently observed chart identity to equal that
expected identity. A future answer can therefore represent expected WIPRO and
visibly observed TCS without corrupting KRONOS provenance.

Chart Analyst authority is visual evidence only. The pack prohibits trading,
Risk, Entry, Stop, Target, R:R, position sizing, derivative selection,
PAPER/LIVE, probabilities, outcome claims and machine provenance invention.

## Persistence and transport

Canonical JSON in the KRONOS Intraday evidence store is analytical authority.
The PDF is deterministic human transport and contains the Sponsor chart,
identity context, exact questions, allowed answers, observation instructions
and trust boundary. It does not expose Provider tokens, credentials or
unnecessary machine analytical conclusions.

The frozen workstation transport locations are:

- Question outbox: `/Users/imranali/Documents/Project-KRONOS/KRONOS REVIEW PACK/Intraday/KRONOS QUESTIONS`;
- future Answer inbox: `/Users/imranali/Documents/Project-KRONOS/KRONOS REVIEW PACK/Intraday/CHATGPT ANSWERS`.

Deleting a PDF does not delete governed evidence. Adding a file to the future
Answer inbox creates no authority. WO-07 does not scan or import answers.

## Browser boundary

`/intraday/review` is product-owned. GET only projects persisted state and is
side-effect free. Product POST actions are limited to starting an exact-current
Review, receiving one bounded chart, and creating the Question Pack PDF. The
shared Browser seam contains no Intraday, Provider, analytical, trading or Risk
policy.

Restart restoration uses the explicit integrity-bound current pointer. A
missing or tampered referenced artifact fails closed; no latest-file or
same-instrument fallback exists.

## Future boundary

WO-09 may later define and import a governed Answer Pack against the exact
Probables Run, instrument, Review Cycle/Request, Chart Revision, Review Pack and
Question Set/version. WO-07 does not invoke Chart Analyst, import an answer,
establish Readiness or perform Analytical Promotion.
