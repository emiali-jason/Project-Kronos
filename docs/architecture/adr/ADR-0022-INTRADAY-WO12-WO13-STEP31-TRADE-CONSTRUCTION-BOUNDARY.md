# ADR-0022 — Intraday WO-12 to WO-13 Step-31 Trade Construction Boundary

## Metadata

- **ADR Number:** ADR-0022
- **Decision Identity:** `KRONOS-INTRADAY-WO12-WO13-STEP31-BOUNDARY-V1`
- **Status:** APPROVED
- **Date:** 2026-08-31
- **Decision Owner:** Chief Architect / KRONOS Intraday / Step-31
- **Proposed By:** Sponsor / Intraday Engineering Architect
- **Reviewers:** Chief Architect / Sponsor / Intraday Engineering Architect
- **Approved By:** Chief Architect / Sponsor
- **Decision Scope:** Platform / Intraday Product / Interface
- **Authority Level:** Chief Architect
- **Repository Approval:** Approved for repository publication
- **Engineering Status:** Governance publication required before bounded WO-13 core engineering
- **Runtime Authority:** NONE
- **Provider Authority:** NONE
- **Risk / Entry Timing / Sponsor / Broker Authority:** NONE

## Context

[ADR-0011](ADR-0011-KR-370-ANALYTICAL-PROMOTION-AND-KR-380-ENTRY-OUTCOME-SEMANTICS.md)
establishes that exact current KR-370 `BUY_NOW` or `SELL_NOW` may enter the
governed Step-31 path and that Step-31 owns geometry. [ADR-0020](ADR-0020-INTRADAY-WO11-WO12-KR370-ANALYTICAL-PROMOTION-BOUNDARY.md)
and [ADR-0021](ADR-0021-INTRADAY-WO12-FOUR-CRITERION-PROMOTION-AND-WO15-EXTENSION-OWNERSHIP.md)
establish the Intraday WO-12 layer and its exact WO-13 eligibility boundary,
but expressly do not authorize WO-13 implementation or freeze Intraday
trade-construction methodology.

Swing has an existing Step-31 implementation and observation-phase evidence
architecture. Its immutable identity, exact-lineage, deterministic arithmetic,
append-only persistence and warning-versus-hard-failure patterns are useful.
Its Daily geometry, setup literals, tick movement, execution-context coupling,
and Swing-specific Sponsor-observation consequences are not Intraday policy.

This additive decision records the approved Intraday Step-31 architecture
without modifying Swing or the common KR-370 state family.

## Decision

### 1. Boundary and authority

WO-13 is `STEP 31 INTRADAY TRADE CONSTRUCTION` with authority
`TRADE_CONSTRUCTION_ONLY`.

Only an exact current, integrity-valid WO-12 V2 result classified `BUY_NOW` or
`SELL_NOW` may enter WO-13. Every other KR-370 classification is ineligible.
Direction is inherited and immutable.

WO-13 owns Entry Reference, geometric Entry Condition, Stop, Thesis
Invalidation Reference/Event, one Target, risk distance, reward distance,
Model R:R, availability, deterministic mathematical warnings, calculation
provenance and supersession lineage. It owns no analytical promotion, Risk,
quantity, position size, final 5M timing, Entry Outcome, Sponsor decision,
position, order, fill or broker authority.

### 2. Exact handoff

The immutable `KRONOS-INTRADAY-WO13-STEP31-HANDOFF-V1` binds the exact WO-12
request, evidence, result and eligibility records; WO-12 policy identity,
version and checksum; WO-11, WO-10 and Probables V2 lineage; canonical subject;
market family; inherited direction; setup family; analysis boundary; phase;
instrument or active-contract identity; source identities; source integrities;
and predecessor lineage where applicable.

Latest-file, mtime, symbol-only, cross-run, cross-cycle, V1 fallback and current
market substitution are prohibited. Any mismatch fails closed.

### 3. Timeframe ownership

- 15M is the sole primary geometry frame.
- 1H is context/regime only.
- 5M has no WO-13 geometry authority and remains WO-15 / KR-380 final timing.

WO-15 may not rewrite WO-13 direction, Entry Reference, Stop, Target or Model
R:R.

### 4. Setup families

The only V1 setup families are:

- `INTRADAY_PULLBACK_CONTINUATION`;
- `INTRADAY_RANGE_BREAKOUT`.

The setup family is inherited from exact governed upstream evidence. WO-13
does not inspect prices to reclassify it. The two construction paths remain
explicit and may share arithmetic utilities only.

### 5. Geometry principle

Market structure creates geometry. R:R evaluates geometry. R:R never
manufactures geometry. Entry, Stop or Target cannot move to improve R:R.
There is no Entry or Stop buffer in V1.

`STOP_VALUE`, `THESIS_INVALIDATION_REFERENCE` and
`THESIS_INVALIDATION_EVENT` are distinct semantic fields even when they refer
to the same structural level.

### 6. Pullback continuation

For LONG, Entry Reference is the High of the exact completed governed 15M
qualification/resumption candle; Stop is the exact governing completed 15M
pullback structural Low; invalidation is completed governed 15M structural
failure through that Low; and setup-native Target is the prior directional 15M
impulse/swing High interrupted by the pullback.

For SHORT, the symmetric values are the qualification/resumption candle Low,
governing pullback structural High, completed structural failure through that
High, and prior directional 15M impulse/swing Low.

Missing or ambiguous governing structure remains unavailable. A measured-move
pullback Target, arbitrary lookback, LTP replacement, percentage/ATR/tick
offset and substitute candle are prohibited.

### 7. Range breakout

The original governed 15M range identity, High, Low, width, direction,
qualification candle, boundary and integrity are immutable.

For LONG, Entry Reference is original Range High; Stop is the exact completed
15M breakout qualification candle Low; invalidation is a completed governed
15M close back at or inside the original range; and setup-native Target is
`Range High + (Range High - Range Low)`.

For SHORT, Entry Reference is original Range Low; Stop is the qualification
candle High; invalidation is the symmetric completed close back at or inside
the range; and setup-native Target is
`Range Low - (Range High - Range Low)`.

Acceptance belongs upstream. Retest is not mandatory, and later price, retest
or LTP cannot redefine the range, Entry or Stop.

### 8. Target constraint

WO-13 derives setup-native Target first. A nearer authoritative forward
structural objective strictly between Entry and that Target may constrain the
canonical Target. Directional price ordering, not label ordering, selects the
nearest constraint. A level behind Entry is ignored; a level beyond the
setup-native Target cannot extend it.

Eligible objectives, when already governed and legitimate, are the relevant
15M swing extreme, current-session structural high/low, PDH/PDL, Classic Pivot
R1-R4/S1-S4, governed 15M structural barrier and the Range-Breakout measured
objective. SMA20/50/200, CPR, COMEX, NYMEX, USDINR, LTP and synthetic desired
R:R prices are not standalone Targets. Intraday V1 has exactly one Target.

### 9. Market-family authority

Equity geometry is stock-local. NIFTY context cannot replace stock Entry,
Stop or Target.

Index geometry belongs to the NIFTY/BANKNIFTY underlying. Option premium and
strike selection have no WO-13 geometry authority.

MCX geometry belongs to the exact governed active futures contract and is
contract-local and roll-safe. COMEX, NYMEX and USDINR have no Entry, Stop or
Target authority. Cross-roll synthetic bridging is prohibited. NATGAS remains
operationally held.

### 10. Mathematics, availability and warnings

For LONG, risk distance is `Entry - Stop` and reward distance is
`Target - Entry`. For SHORT, risk distance is `Stop - Entry` and reward
distance is `Entry - Target`. Model R:R is reward divided by risk only when
both distances are positive and all values are finite.

There is no V1 minimum R:R threshold and no `RR_UNFAVOURABLE` consequence.
Each geometry field has independent availability. The aggregate states are
`GEOMETRY_COMPLETE`, `GEOMETRY_PARTIAL` and `GEOMETRY_UNAVAILABLE`.

Deterministic warnings are `NON_POSITIVE_RISK`, `NON_POSITIVE_REWARD`,
`INVALID_DIRECTIONAL_GEOMETRY`, `NON_FINITE_VALUE` and, only through existing
governed Instrument authority, `TICK_NORMALIZATION_FAILURE`.

Warnings retain poor geometry as evidence. They are not trust-boundary
failures, Risk decisions or Sponsor decisions.

### 11. Hard trust boundary

Foreign/stale WO-12 source, policy or evidence-cycle mismatch, direction or
setup-family mismatch, instrument or market-family mismatch, corrupt evidence,
wrong MCX active contract and roll-lineage mismatch yield no trusted
construction result.

### 12. Immutability and supersession

Every Trade Plan is immutable. A changed structure cannot rewrite an existing
plan. A successor requires a new exact eligible WO-12 cycle and records the
predecessor, supersession relationship/reason and new boundary. Historical
plans remain explicitly reloadable.

### 13. Persistence and application

WO-13 uses a dedicated Intraday namespace with content-derived identities,
independent integrity identities, append-only immutable artifacts, idempotent
same-content retention, conflicting rewrite rejection, explicit-identity
reload, corruption failure and atomic final current-pointer publication.
No latest-file, mtime or symbol-only authority exists.

The bounded application validates the exact handoff, loads exact retained
evidence, executes the setup-specific constructor, applies the target
constraint, calculates arithmetic/availability/warnings, persists all
artifacts, publishes the pointer only after successful persistence, and
explicitly reloads and verifies the result.

WO-13 makes zero Provider calls and zero Chart Analyst calls.

### 14. Versioned contracts

The V1 contract family is:

- `KRONOS-INTRADAY-WO13-STEP31-HANDOFF-V1`;
- `KRONOS-INTRADAY-WO13-TRADE-CONSTRUCTION-REQUEST-V1`;
- `KRONOS-INTRADAY-WO13-GEOMETRY-EVIDENCE-V1`;
- `KRONOS-INTRADAY-WO13-TRADE-PLAN-V1`;
- `KRONOS-INTRADAY-WO13-OPERATION-PROVENANCE-V1`;
- `KRONOS-INTRADAY-CURRENT-WO13-POINTER-V1`.

The policy is
`KRONOS-INTRADAY-WO13-STEP31-TRADE-CONSTRUCTION-POLICY-V1 / 1.0.0`.
Its canonical checksum binds the policy payload published with the product
architecture and is
`c5ea70a5af50af251088785a58a39da4e824b5cc6058c11c98e880fce0fb0e6b`.

### 15. Downstream boundaries

The frozen sequence is:

```text
WO-12 recommends
  -> WO-13 constructs and calculates
  -> WO-14 / DOMAIN-007 judges Risk
  -> WO-15 / KR-380 judges final 5M Entry timing
  -> Sponsor decides participation
```

WO-14 may approve, constrain, reject or be unavailable under separately frozen
Risk policy, but may not move WO-13 geometry. Position size may respond to
geometry; geometry may not respond to desired position size.

## Relationship to existing decisions

This ADR is additive to ADR-0011, ADR-0019 and ADR-0021. It supplies the
separately governed WO-13 implementation authority left absent by ADR-0020 and
the current roadmap. It does not supersede any current ADR.

ADR-0015 remains Swing-specific. Its observation-first separation is
compatible, but its policy, warning grammar and Sponsor-observation consequences
are not copied into Intraday.

## Implementation authorization

After this governance slice is published in the repository, bounded Intraday-
owned core engineering is authorized for contracts, exact handoff, arithmetic,
the two setup-specific constructors, target constraints, family adapters,
persistence and application. Runtime, Browser and real WO-13 operation remain
separately gated.

## Validation requirements

- Exact current WO-12 NOW-only admission and immutable direction.
- Separate pullback and range-breakout construction paths.
- Exact LONG/SHORT symmetry and 15M-only geometry.
- Setup-native Target before nearest forward constraint.
- R:R never selects or moves geometry and has no minimum gate.
- Independent field and aggregate availability.
- Exact market-family authority and MCX contract/roll binding.
- Immutable persistence, supersession and explicit reload.
- No Provider, Chart Analyst, Risk, 5M timing, Sponsor or broker authority.
- Swing Step-31 behavior and persistence unchanged.

## Supersedes

None.

## Superseded By

None.

## Related Documents

- [ADR-0011](ADR-0011-KR-370-ANALYTICAL-PROMOTION-AND-KR-380-ENTRY-OUTCOME-SEMANTICS.md)
- [ADR-0015](ADR-0015-SWING-SPONSOR-OBSERVATION-PHASE-AUTHORITY-AND-STEP-31-EVIDENCE-GOVERNANCE.md)
- [ADR-0020](ADR-0020-INTRADAY-WO11-WO12-KR370-ANALYTICAL-PROMOTION-BOUNDARY.md)
- [ADR-0021](ADR-0021-INTRADAY-WO12-FOUR-CRITERION-PROMOTION-AND-WO15-EXTENSION-OWNERSHIP.md)
- [Intraday WO-12 V2](../products/intraday/KRONOS-INTRADAY-WO-12-KR370-ANALYTICAL-PROMOTION-V2.md)
- [Intraday WO-13 V1](../products/intraday/KRONOS-INTRADAY-WO-13-STEP31-TRADE-CONSTRUCTION-V1.md)
- [KR-370 / KR-380 state-family contracts](../interfaces/KR-370-KR-380-STATE-FAMILY-CONTRACTS.md)

## Revision History

| Date | Revision | Author | Description | Approval status |
| --- | --- | --- | --- | --- |
| 2026-08-31 | 1.0 | Chief Architect / Sponsor, recorded by Codex | Authorize the Intraday WO-12 → WO-13 Step-31 boundary and frozen V1 geometry | APPROVED |
