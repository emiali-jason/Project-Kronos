# KRONOS Intraday V1 — Probables V2/V2.1 Review Successor Seam

**Status:** Implemented candidate

**Owner:** Intraday

**Contract version:** 2.0.0
**Trading authority:** None

## Purpose

This record establishes the additive, explicitly invoked Review intake seam
from an exact persisted `KRONOS-INTRADAY-PROBABLES-RUN-V2` result to
`KRONOS-INTRADAY-REVIEW-CYCLE-V2 / 2.0.0`. It provides mechanical lineage
compatibility for Probables methodology versions 2.0.0 and 2.1.0. It does not
change Probables admission, visual methodology, reconciliation, Readiness,
Promotion, trading, Risk, PAPER/LIVE, or broker authority.

## V1 preservation and selection

V1 Review contracts, storage and `CURRENT-REVIEW-POINTER.json` remain
unchanged. V2 artifacts use the separate `review-v2` namespace and
`CURRENT-REVIEW-V2-POINTER.json`. Neither pointer is a fallback for the other.
V2 intake receives an explicit governed run; directory order, modification
time, symbol-only matching, the V1 pointer, and a latest-successful heuristic
have no authority. Historical V1 cycles are never upgraded or rewritten.

## Exact V2 lineage

Only `LONG_PROBABLE` and `SHORT_PROBABLE` members may establish a V2 Review
cycle. `NOT_ADMITTED`, `UNAVAILABLE`, held MCX subjects, unknown states, and
unknown methodology tuples create no cycle. The handoff and cycle retain:

- exact Probables run/result and Discovery run/result/mapping identities;
- canonical subject, inherited direction, market session and analysis boundary;
- exact methodology identity, version, publication and checksum;
- the original `OPENING`, `STRUCTURE`, `FIRST_CURRENT_SESSION_1H`, or
  `CURRENT_SESSION_ESTABLISHED` phase without clock inference;
- exact completed-evidence selection identity and integrity;
- exact semantic V2 evidence identity and integrity;
- the governed NIFTY applicability/relationship and exact evidence identity and
  integrity where evidence exists;
- for MCX, the commissioned subject state plus exact registry publication,
  qualification evidence, family-expiry evidence and their integrity bindings.

The application reloads the run, result, mapping, completed selection,
semantic evidence and applicable NIFTY evidence by explicit identity before
retention. Missing, corrupted, cross-run or conflicting lineage fails closed.
Review does not reacquire candles, recompute phase or reinterpret admission.

## Chart, Question Pack and Answer compatibility

The Q1–Q10 question set, observation statuses, trust boundary and trading
prohibition remain the existing governed V1 visual methodology. The schema
envelopes that bind them are separately versioned as V2 because the historical
chart and Question Pack schemas are V1-cycle-specific:

- `KRONOS-INTRADAY-CHART-REVISION-V2 / 2.0.0`;
- `KRONOS-INTRADAY-VISUAL-REVIEW-QUESTION-PACK-V2 / 2.0.0`;
- `KRONOS-INTRADAY-IMPORTED-VISUAL-EVIDENCE-V2 / 2.0.0`.

The V2 Question Pack carries the exact methodology, phase, completed-evidence
and semantic-evidence binding. The existing strict Q1–Q10 Chart Analyst Answer
schema remains reusable: its exact cycle, request, pack, chart, candidate,
direction and Question Set bindings are checked against the V2 pack. The V2
imported-evidence envelope then retains the Answer identity/source digest and
the V2 lineage. Wrong run, result, cycle, pack, chart, candidate, direction,
boundary, methodology, phase or evidence binding fails closed.

Expected canonical identity remains KRONOS-owned. Observed visible identity
remains raw Chart Analyst evidence. The raw value is resolved through the
approved DOMAIN-001 `TRADINGVIEW_VISUAL_CHART` relationship at the governed
analysis boundary, and the resolved canonical identity must equal the separate
expected identity. Literal raw-label equality is not restored.

## Persistence, replay and authority

V2 artifacts are immutable, canonically serialized and content-addressed.
Retention is idempotent for exact inputs and rejects conflicting bytes. The V2
pointer contains explicit run and cycle identities; restart follows those
identities and validates cycle-to-handoff lineage without Provider calls,
Chart Analyst calls, market reacquisition or recomputation. The application
has no startup hook, Refresh hook, background worker or Browser GET side
effect. A real Review operation still requires separate Sponsor authority.

Batch transport remains mechanically feasible: multiple independently bound
V2 cycles may contribute to one combined transport while every Answer remains
candidate-isolated. This implementation does not create a production batch,
chart, Answer, import or reconciliation.

## Reuse classification

| Capability | Classification | Treatment |
|---|---|---|
| Q1–Q10, observation statuses, trust and trading prohibitions | `REUSE_AS_IS` | Imported unchanged from V1 Review |
| DOMAIN-001 visual identity resolution | `REUSE_AS_IS` | Exact source-qualified resolution at the governed boundary |
| Probables V2 store and immutable evidence | `REUSE_THROUGH_ADAPTER` | Explicit-identity reload and equality validation |
| V1 handoff/cycle/chart/pack/current pointer | `SUCCESSOR_VERSION_REQUIRED` | Separate V2 contracts and persistence namespace |
| V1 Answer binding result envelope | `SUCCESSOR_VERSION_REQUIRED` | V1 Q1–Q10 Answer schema, V2 imported-evidence envelope |
| V1 current pointer as V2 selection authority | `DO_NOT_REUSE` | No cross-version fallback or repointing |
| Swing Native Review/Visual/Readiness methodology | `DO_NOT_REUSE` | Only immutable-store and explicit-restoration patterns informed the seam |

## WO-10 future mechanical adapter

Current WO-10 `_validate_bindings` accepts exact V1 `ProbablesRun`,
`ProbableMemberResult`, `ReviewCycle`, `ReviewQuestionPack` and
`ImportedVisualEvidence` types. It must not be overloaded. A future separately
authorized V2 reconciliation adapter/successor must:

1. accept only exact V2 run/result/cycle/pack/imported-evidence types;
2. validate the additional methodology, phase, completed-evidence, semantic,
   NIFTY and MCX commissioning bindings;
3. feed the unchanged frozen Q1–Q10 reconciliation policy without translating
   V2 evidence into V1 artifacts or changing any consequence predicate;
4. persist a separately versioned reconciliation run/pointer if the existing
   schema cannot represent V2 lineage.

This seam preserves the immutable lineage needed for that future adaptation
and for later Review/Readiness/Promotion design. It does not implement WO-10,
WO-12, Trade Construction, Entry Timing or Risk.
