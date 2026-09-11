# ADR-0038 — Intraday WO-09 Governed Promotion and Active Readiness

**Document Status:** Approved

## Metadata

- **ADR Number:** ADR-0038
- **Status:** APPROVED
- **Date:** 2026-09-11
- **Decision Owner:** Sponsor / Executive Architect
- **Decision Scope:** Intraday Product and KR-370 ownership
- **Repository Approval:** Approved for bounded WO-09 engineering
- **Engineering Status:** Implemented candidate; publication and runtime activation pending

## Context

ADR-0021 established WO-12 V2 as a four-criterion Intraday promotion authority and moved entry-relative extension to WO-15. The completed WO-07F governed visual reconciliation now provides a stronger exact-lineage input for a prospective five-criterion analytical readiness decision. Retaining WO-12 as a concurrent current promotion owner would create two current authorities.

## Decision

WO-09 is the prospective authoritative Intraday governed promotion and active-readiness owner. It consumes immutable WO-07F lineage and produces I1 direction/structure, I2 establishment/follow-through, I3 path/obstacle clearance, I4 setup quality and I5 analytical visual extension.

WO-09 analytical visual extension is distinct from WO-15 execution-time and entry-relative extension/chase authority. WO-09 uses the already-reconciled Q8-equivalent visual state and owns no Entry, geometry, Risk, Sponsor decision, position or broker authority.

Only `CONFIRMED` and `CONDITIONAL` WO-07F outcomes enter positive evaluation. All other outcomes and NATGAS commissioning `HELD` are hard gates with a non-applicable positive count. A missing required criterion produces a fail-closed unavailable readiness state rather than an invented score.

WO-12 V1/V2 records remain immutable historical evidence under their original policies. The operational runtime restores them read-only, while prospective WO-12 V2 execution is disabled in the composed runtime. The retained WO-07F value `ELIGIBLE_FOR_WO10_EVALUATION` remains byte-stable and is admitted through an explicit WO-07F-to-WO-09 V1 compatibility adapter.

Only `BUY_NOW` or `SELL_NOW` may produce a next-WO handoff. The handoff carries analytical authority only.

## Consequences

- WO-09 readiness is an immutable evidence-bound snapshot with append-only history and an atomic current pointer.
- Browser and notifications project the same persisted authority and do not calculate readiness.
- Reassessment watches can request governed reacquisition; a market tick cannot directly create a readiness transition in V1.
- Disconnect gaps make affected watches stale until governed reacquisition.
- `NO_FOCUS` remains in the research denominator but is excluded from normal Sponsor attention.

## Validation Requirements

All hard gates; I1-I5; zero-through-five state mappings; unavailable evidence; WO-07F compatibility; persistence, idempotency, conflict, supersession and restoration; watches, notifications and Browser projection; NATGAS and NIFTY; current-seven isolated mapping; affected Intraday, Opening, MCX, Review/Chart Analyst, WO-07F, monitoring, notifications, 98-identity and WO-06H regression.

## Supersedes

- ADR-0021 only where it names WO-12 V2 as the current prospective Intraday promotion owner.
- ADR-0021 remains authoritative for historical WO-12 interpretation and WO-15 execution-time/entry-relative extension ownership.

## Related Documents

- [`ADR-0021`](ADR-0021-INTRADAY-WO12-FOUR-CRITERION-PROMOTION-AND-WO15-EXTENSION-OWNERSHIP.md)
- [`WO-07F`](../products/intraday/KRONOS-INTRADAY-WO-07F-GOVERNED-VISUAL-RECONCILIATION.md)
- [`WO-09`](../products/intraday/KRONOS-INTRADAY-WO-09-GOVERNED-PROMOTION-AND-ACTIVE-READINESS.md)
- [`WO-09 interface`](../interfaces/KRONOS-INTRADAY-WO09-PROMOTION-READINESS-V1.md)

## Revision History

| Date | Revision | Author | Description | Approval status |
| --- | --- | --- | --- | --- |
| 2026-09-11 | 1.0 | KRONOS Engineering | Records frozen WO-09 authority and WO-12 historical transition | Sponsor/EA approved |
