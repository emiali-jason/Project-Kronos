# KRONOS Intraday WO-09 Promotion Readiness V1 Interface

**Status:** Approved — bounded engineering implemented, publication/runtime pending
**Version:** 1.0.0
**Owner:** KRONOS Intraday / WO-09

## Input

The interface consumes one exact immutable WO-07F record, its verified integrity and the already-governed machine/visual facts bound to the same candidate, direction, Probables run/result, Review, chart revision, Answer, correspondence and machine evidence. An MCX input also requires the exact machine-owned contract and roll lineage. It does not use international-reference evidence as independent authority.

The historical WO-07F value `ELIGIBLE_FOR_WO10_EVALUATION` is preserved and mapped to WO-09 intake only when the exact record outcome and integrity remain admissible.

The governed-source adapter accepts typed semantic, completed-evidence and imported-visual artifacts. It verifies subject, direction, run/result, Review cycle/pack, chart revision, Answer source, visual identity/integrity and machine identity/integrity lineage before producing the bounded WO-09 fact input. An authoritative completed-1H/15M directional conflict is a hard gate. It does not parse prose or acquire evidence.

## Output

One immutable readiness record contains:

- policy identity, version and checksum;
- readiness identity and integrity;
- complete WO-07F and upstream lineage;
- ordered I1–I5 snapshots;
- hard gate, satisfied/outstanding counts and state;
- analysis/session boundary and currentness;
- explicit zero Entry, Risk, execution and broker authority.

Separate immutable requirement records contain current, required and gap facts, source evidence, observation boundary, monitorability, next trigger, notification state and lifecycle. With no numeric policy, `required_value` is unavailable and `gap` is `NUMERIC_GAP_NOT_GOVERNED`.

## State Contract

| Result | State |
| --- | --- |
| Hard gate | `HARD_GATE`, count `NOT_APPLICABLE` |
| Required evidence unavailable | `READINESS_UNAVAILABLE`, no five-criterion count |
| 0–2 | `NO_FOCUS` |
| 3 | `NEAR_READY` |
| 4 LONG/SHORT | `BUY_READY` / `SELL_READY` |
| 5 LONG/SHORT | `BUY_NOW` / `SELL_NOW` |

`CURRENT`, `REASSESSMENT_DUE`, `STALE_UNAVAILABLE` and `SUPERSEDED` are explicit currentness/lifecycle states. Newer governed machine or visual boundaries never rewrite historical snapshots.

## Projection and Notification

Browser and notification components consume persisted records only. They cannot calculate criteria. `NO_FOCUS` is retained but omitted from active-attention projection. Notifications use an immutable source identity, deduplicate exact source projections, project governed criterion-reassessment events without rewriting readiness, and withdraw attention on stale/superseded authority.

## Watch Boundary

WO-09 V1 watches are owned by `INTRADAY_WO09`. They bind readiness, criterion, subject/contract, source fact, trigger and policy. Their lifecycle is `ACTIVE`, `TRIGGERED`, `INACTIVE` or `STALE`. They can request reassessment only. No tick can directly create `READY` or `NOW`.

## Next-WO Handoff

Only current `BUY_NOW`/`SELL_NOW` with all five criteria satisfied and no hard gate may create the immutable handoff. The handoff binds the exact current-pointer identity/integrity/currentness and supersession lineage checked at creation. It has no Entry, Stop, Target, R:R, quantity, capital, Risk, PAPER/LIVE, order, fill or broker fields.
