# KRONOS Intraday V1 - WO-09 Governed Chart Analyst Answer Import

**Status:** Implemented
**Owner:** Intraday
**Contract version:** 1.0.0
**Trading authority:** None

## Contracts and trust boundary

WO-09 establishes:

- `KRONOS-INTRADAY-CHART-ANALYST-ANSWER-PACK-V1 / 1.0.0`;
- `KRONOS-INTRADAY-IMPORTED-VISUAL-EVIDENCE-V1 / 1.0.0`;
- `KRONOS-INTRADAY-ANSWER-IMPORT-RECORD-V1 / 1.0.0`;
- `KRONOS-INTRADAY-VISUAL-EVIDENCE-POINTER-V1 / 1.0.0`.

The Chart Analyst reports visual evidence only. The JSON Answer Pack contains
the exact ordered Q1-Q10 observations, governed observation statuses, bounded
visible timeframe scope and concise visible basis. `UNCLEAR` remains a
substantive allowed answer and is never an observation status. No Answer Pack
field can establish Readiness, Promotion, Entry, Stop, Target, Risk, PAPER,
LIVE, broker authority or a trade-confidence claim.

The Swing extraction-confidence field is deliberately not copied: the current
Swing contract does not expose a bounded product-neutral enum that Intraday can
reuse without inventing new meaning.

## Expected and observed identity

Expected canonical subject identity is supplied by the exact governed Question
Pack. Observed visible subject identity is independently returned by the Chart
Analyst. KRONOS never fills or corrects the observed value. A mismatch or
unreadable observed identity creates a typed failed import and no trusted visual
evidence.

Successful binding requires exact equality for Question Set/version, Review
Pack, Review Cycle/Request, Chart Revision, expected subject and proposed
direction. KRONOS then adds its own Probables, chart artifact and immutable
provenance linkage; the external Answer Pack may not supply those fields.

## Individual and batch operation

`UPLOAD ANSWER` resolves the one deterministic `.json` filename derived from
the candidate's exact current Question Pack. `UPLOAD ALL ANSWERS` processes
eligible current candidates in canonical-subject order. Each candidate is
isolated and reports imported, already imported, missing, invalid, identity
mismatch, schema invalid or conflict state. One failure cannot block a valid
candidate.

Only individual Answer Pack files are supported. Combined answer documents are
not accepted. The governed inbox is:

`/Users/imranali/Documents/Project-KRONOS/KRONOS REVIEW PACK/Intraday/CHATGPT ANSWERS`

There is no recursive scan, mtime ordering, latest-file heuristic, symlink
following or arbitrary filename selection. Files outside the exact candidate
manifest are ignored.

## Persistence and restart

The validated canonical Answer Pack, Answer Import record and trusted imported
visual evidence are separate immutable artifacts. A per-Review-Pack current
pointer carries exact Answer Pack, import and evidence identities with an
integrity digest. Restart follows that pointer only.

Repeated identical valid import is idempotent. A different answer for an exact
Review Pack is a conflict and cannot supersede prior trusted evidence. Missing,
malformed, oversized, unsupported, identity-mismatched or tampered inputs fail
closed and cannot blank prior evidence. A new Chart Revision creates a new
Question Pack and therefore requires a new Answer Pack.

## Browser and WO-10 boundary

The Intraday Review page projects factual status, expected filename, observed
identity, imported evidence identity and compact Q1-Q10 evidence. GET is
side-effect free. Both controls use the existing same-origin, Sponsor-work,
body-size and request-validation Browser seam; no shared Browser file changes
are required.

WO-09 performs zero Provider, Discovery, Probables or automatic Chart Analyst
operations. WO-10 alone may define Native-plus-visual reconciliation, typed
consequences, Review/Readiness state or Analytical Promotion.
