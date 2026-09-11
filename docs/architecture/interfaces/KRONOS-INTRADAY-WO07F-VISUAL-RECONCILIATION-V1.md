# KRONOS Intraday WO-07F Visual Reconciliation V1

**Status:** Sponsor/EA Approved Contract — Engineering Candidate
**Policy:** `KRONOS-INTRADAY-WO-07F-VISUAL-RECONCILIATION-POLICY / 1.0.0`

## Inputs

Every evaluation binds the canonical candidate, proposed direction, Probables
run/result, Review cycle/pack, chart revision, accepted Answer pack and source
SHA-256, imported visual evidence, correspondence identity, and ordered machine
evidence identities. NSE requires exact Q1–Q10 V2 observations. MCX requires
exact M1–M5 native observations, R1–R5/X1–X5 supporting observations, exact
native contract/binding, and the frozen supporting-reference authority pair.

The prerequisite vector is explicit: current machine Review, accepted Answer,
visual identity, chart binding, confirmed correspondence, machine sources, and
for MCX the native contract. A false prerequisite is not interpreted as visual
contradiction.

## Deterministic matrix

| Precedence | Condition | Outcome |
| --- | --- | --- |
| 1 | Any required upstream prerequisite fails | `NOT_RECONCILABLE` |
| 2 | Q4/M3 failure, governed anchor invalidation, or classified residual contradiction | `CONTRADICTED` |
| 3 | Material partial/unavailable/unclear required observation or unclassifiable material residual | `INSUFFICIENT` |
| 4 | One or more bounded degradation conditions | `CONDITIONAL` |
| 5 | All prerequisites, sufficient evidence, no contradiction or degradation | `CONFIRMED` |

Degradation values are frozen as:

- Q1/M1: `OPPOSING`, `MIXED`;
- Q2/M2: `MIXED_STRUCTURE`, `CONGESTED_STRUCTURE`;
- Q3: `WEAK_OR_MIXED_BASE`, `NO_CLEAR_BASE`;
- Q4/M3: `WEAK_OR_STALLING`, `MIXED`;
- Q5/M4: `MIXED`, `DISORDERLY`, `NO_CLEAR_PULLBACK_OR_PROGRESSION`;
- Q7: `LIMITED_SPACE`, `OBSTACLE_CLOSE`;
- Q8: `VISIBLY_EXTENDED`, `MIXED`;
- Q10/X5: only a predeclared `CONDITIONAL_REASON` classification.

`SELECTED_Q6_Q9_ANCHOR = NOT_ESTABLISHED` plus lawful `NOT_OBSERVABLE`
is neutral. When an anchor exists, an external machine-owned mapping must name
the exact Q6/Q9/M5 observation that invalidates the proposed direction.

## Result record

`KRONOS-INTRADAY-WO-07F-RECONCILIATION-RECORD-V1 / 1.0.0` contains:

- reconciliation and canonical input identities;
- creation time and policy identity/version;
- exact candidate, direction, Probables, Review, chart, Answer, visual evidence,
  correspondence, and machine evidence identities;
- one five-state outcome;
- ordered reasons with class, code, question, source identity, and bounded detail;
- `ELIGIBLE_FOR_WO10_EVALUATION` or
  `NOT_ELIGIBLE_FOR_WO10_EVALUATION`;
- canonical integrity identity.

The current pointer binds one Review cycle to one record and input identity.
Records are append-only. Pointer publication is atomic. Restoration verifies
the pointer, record, policy, and identity chain. The same input is idempotent;
changed evidence never overwrites prior history.

## Operating boundary

The batch control processes current Review order and returns a result for every
candidate. A missing/rejected candidate remains isolated as
`NOT_RECONCILABLE`. The control does not call WO-10. The result contains no
BUY/SELL decision or execution economics.
