# KR-370 Analytical Promotion and KR-380 Entry Outcome State-Family Contracts

**Status:** Approved
**Version:** 1.0
**Approval date:** 2026-08-21
**Owner / approved by:** Chief Architect
**Governing ADR:** [ADR-0011](../adr/ADR-0011-KR-370-ANALYTICAL-PROMOTION-AND-KR-380-ENTRY-OUTCOME-SEMANTICS.md)
**Governing decision identity:** KR-370-ADR-01
**Implementation:** Architecture and contracts activated; classifier/runtime migration is separate

## Purpose

Define unambiguous current and historical public state families for KR-370
analytical promotion and KR-380 Entry Outcome. A display label is never a
contract identity.

## Mandatory binding envelope

Every persisted or exchanged record in these families identifies:

- `owner_identity`;
- `state_family_identity`;
- `contract_identity`;
- `contract_version`;
- bound product, run, candidate/assessment, instrument, direction, and source
  integrity identities required by its governing product contract;
- outcome state;
- creation/observation time and integrity digest.

Missing, unsupported, stale, mismatched, or ambiguous binding fails closed.
Consumers must not infer an owner, family, or version from the state text.

## KRONOS-KR-370-ANALYTICAL-PROMOTION-V1

- **Owner:** `KR-370` / `DOMAIN-003-VALIDATION`
- **State family:** `KR370_ANALYTICAL_PROMOTION`
- **Contract version:** `1`
- **Authority:** analytical promotion only
- **States:** `BUY_NOW`, `SELL_NOW`, `BUY_READY`, `SELL_READY`,
  `POTENTIAL_BUY_SETUP`, `POTENTIAL_SELL_SETUP`, `NO_SETUP`
- **Authorized consumer boundary:** current exact `BUY_NOW` / `SELL_NOW` may
  establish eligibility for the governed Step-31 path; no other state may.

This contract has no execution, Risk, Sponsor-decision, position, fill, model,
alert, quantity, order, or broker authority.

## KRONOS-KR-380-ENTRY-OUTCOME-V2

- **Owner:** `KR-380` / `DOMAIN-004-EXECUTION`
- **State family:** `KR380_ENTRY_OUTCOME`
- **Contract version:** `2`
- **Authority:** final entry timing and Entry Outcome only
- **States:** `NO_TRIGGER`, `FORMING`, `LONG_ENTRY_TRIGGERED`,
  `SHORT_ENTRY_TRIGGERED`, `EXTENDED`, `FAILED`
- **Required upstream boundary:** exact current candidate, KR-370 analytical
  promotion complete in the same direction, immutable Step-31 geometry,
  DOMAIN-007 Risk permission, monitoring binding, governed Observation,
  qualified Execution Context, and final timing.

`LONG_ENTRY_TRIGGERED` and `SHORT_ENTRY_TRIGGERED` are analytical Entry Outcomes,
not fills, Sponsor positions, or broker orders.

## KRONOS-KR-380-ENTRY-OUTCOME-V1 — historical

- **Owner:** `KR-380` / `DOMAIN-004-EXECUTION`
- **State family:** `KR380_ENTRY_OUTCOME`
- **Contract version:** `1`
- **Status:** historical, immutable, read-only/restorable
- **States:** `NO_TRIGGER`, `FORMING`, `BUY_NOW`, `SELL_NOW`, `EXTENDED`,
  `FAILED`

Version 1 `BUY_NOW` / `SELL_NOW` retains its original KR-380 entry-timing
meaning. Current producers do not emit Version 1. Restoration may preserve
already-recorded historical consequences but cannot create a new current event.

## Consumer isolation

### Step 31

Step 31 may consume only exact current KR-370 V1 `BUY_NOW` / `SELL_NOW`
eligibility and remains the sole owner of Entry, Stop, Target, invalidation, and
R:R geometry. It does not consume KR-380 Entry Outcomes to construct geometry.

### KR-390

For new current progression, KR-390 accepts only:

- owner `KR-380`;
- family `KR380_ENTRY_OUTCOME`;
- contract `KRONOS-KR-380-ENTRY-OUTCOME-V2`;
- state `LONG_ENTRY_TRIGGERED` or `SHORT_ENTRY_TRIGGERED`;
- valid Risk and immutable geometry bindings.

Owner `KR-370` or family `KR370_ANALYTICAL_PROMOTION` is invalid at this
boundary, regardless of state text. Historical V1 restoration does not create a
new model trade.

### KR-400

For new current entry alerts, KR-400 accepts only the transition into a valid
KR-380 Version 2 `LONG_ENTRY_TRIGGERED` or `SHORT_ENTRY_TRIGGERED` outcome with
event identity `KR380_LONG_ENTRY_TRIGGERED` or
`KR380_SHORT_ENTRY_TRIGGERED`. KR-370 analytical transitions never satisfy this
boundary. KR-370 notifications require separate UX-10 authority.

### Sponsor Decision and broker boundary

No state in either family records `LIVE`, `PAPER`, or `IGNORE`, creates a
Sponsor position, claims a fill, or places/modifies/cancels an order.

## Machine-readable registry

The exact state/owner/version registry is published in
[`KR-370-KR-380-STATE-FAMILY-CONTRACTS.json`](KR-370-KR-380-STATE-FAMILY-CONTRACTS.json).
The JSON registry and this contract must agree. Conflict fails closed.

## Historical compatibility and migration

- Version 1 KR-380 records remain immutable and readable.
- Version 2 is the only current KR-380 Entry Outcome family.
- KR-370 V1 is a distinct analytical family and is never an alias of KR-380 V1.
- Unsupported combinations produce no Step-31, Risk, Entry Outcome, KR-390,
  KR-400, Sponsor, or broker progression.

## Authority declaration

These contracts create no new broker authority and do not implement KR-370 V1,
UX-10, trade geometry, Risk behavior, or execution logic.
