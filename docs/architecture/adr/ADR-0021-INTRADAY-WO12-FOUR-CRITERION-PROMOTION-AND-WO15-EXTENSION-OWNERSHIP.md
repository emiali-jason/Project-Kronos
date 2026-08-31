# ADR-0021 — Intraday WO-12 Four-Criterion Promotion and WO-15 Extension Ownership

## Metadata

- **ADR Number:** ADR-0021
- **Decision Identity:** `KRONOS-INTRADAY-WO12-FOUR-K-WO15-EXTENSION-BOUNDARY-V1`
- **Status:** APPROVED
- **Date:** 2026-08-31
- **Decision Owner:** Chief Architect / KR-370 / DOMAIN-003-VALIDATION
- **Approved By:** Chief Architect / Sponsor
- **Decision Scope:** Intraday product and KR-370 interface
- **Authority Level:** Chief Architect
- **Repository Approval:** Approved for publication
- **Engineering Status:** WO-12 V2 contracts, persistence, runtime and Browser engineering authorized
- **Provider / Trading / Risk / Entry / Broker Authority:** NONE

## Context

[ADR-0020](ADR-0020-INTRADAY-WO11-WO12-KR370-ANALYTICAL-PROMOTION-BOUNDARY.md)
correctly established the distinct WO-11 to WO-12 crossing and common KR-370
state-family reuse. It also froze a five-criterion Intraday model in which K5
was a 15M material-extension consequence. Subsequent architectural review
determined that extension/chase is final Entry-timing responsibility and
belongs to WO-15 / KR-380, not WO-12 analytical promotion.

The completed K5 fact-foundation and research remain useful factual telemetry.
This decision changes only their product consequence authority.

## Decision

### 1. Supersession scope

This ADR supersedes only ADR-0020's Intraday five-criterion model, K5
mandatory-gate consequence and K5 commissioning hold. ADR-0020 remains the
historical authority for the original V1 contracts and artifacts.

ADR-0020's distinct WO-11 → WO-12 boundary, exact-lineage admission,
common KR-370 state-family reuse, direction immutability, 15M authority,
hard-gate principles and authority exclusions remain active where they do not
conflict with this successor.

[ADR-0019](ADR-0019-INTRADAY-WO10-WO11-PRE-KR370-SEMANTIC-BOUNDARY.md)
remains unchanged and approved.

### 2. Intraday WO-12 V2 criteria

Intraday WO-12 V2 evaluates exactly four mandatory criteria:

1. `K1_15M_DIRECTIONAL_PROGRESSION`;
2. `K2_15M_CPR_ACCEPTANCE`;
3. `K3_15M_IMMEDIATE_PATH_CLEARANCE`;
4. `K4_15M_SETUP_QUALITY`.

Their frozen predicates and exact evidence responsibilities are unchanged from
ADR-0020. There is no Intraday WO-12 V2 K5 or K6.

### 3. Four-criterion mapping

With all four mandatory criteria available:

| Satisfied | LONG | SHORT |
| ---: | --- | --- |
| 4 | `BUY_NOW` | `SELL_NOW` |
| 3 | `BUY_READY` | `SELL_READY` |
| 2 | `POTENTIAL_BUY_SETUP` | `POTENTIAL_SELL_SETUP` |
| 0–1 | `NO_SETUP` | `NO_SETUP` |

Any unavailable K1–K4 fails closed to `NO_SETUP` with
`MANDATORY_K_UNAVAILABLE`. `UNAVAILABLE` is never treated as
`UNSATISFIED`. There is no weighting, score, rank, vote or quota.

The common public contract remains
`KRONOS-KR-370-ANALYTICAL-PROMOTION-V1`, owner `KR-370`, state family
`KR370_ANALYTICAL_PROMOTION`. Swing retains its separate five-criterion
classifier and all existing Swing consequences unchanged.

### 4. K5 and ATR authority transfer

`K5_15M_NON_EXTENSION` is not an Intraday WO-12 V2 criterion. The published
structural-origin, completed-15M ATR, extension measurement and forward-outcome
research remain immutable supporting research/telemetry for future WO-15
extension/chase design.

Those facts have no independent WO-12 decision, veto, trigger, rejection or
mandatory-availability authority. Unavailable ATR or origin telemetry cannot
create `MANDATORY_K_UNAVAILABLE` in WO-12 V2.

WO-15 / KR-380 owns any future extension/chase consequence and any future 5M
ATR/reference methodology. This ADR does not commission such a methodology.

### 5. Hard gates

The only universal Intraday WO-12 V2 hard gates are:

- `INVALID_EXACT_EVIDENCE_BINDING`;
- `MANDATORY_K_UNAVAILABLE`, for K1–K4 only;
- `GOVERNING_15M_STRUCTURE_FAILED`;
- `AUTHORITATIVE_GOVERNED_DIRECTIONAL_CONFLICT`.

### 6. WO-13 boundary

Only an exact current integrity-valid `BUY_NOW` or `SELL_NOW` result may be
eligible for WO-13 / Step 31. WO-12 owns no geometry. WO-13 owns Entry, Stop,
Target, invalidation and R:R geometry; WO-14 owns DOMAIN-007 Risk; WO-15 owns
KR-380 final Entry timing.

### 7. Versioning and compatibility

The successor product contract is
`KRONOS-INTRADAY-WO-12-KR370-ANALYTICAL-PROMOTION-V2 / 2.0.0`.
V2 uses successor policy, request, criterion, evidence, result, eligibility,
pointer and operation identities. The exact WO-11 handoff V1 is retained
because its admission semantics do not change. V2 persistence uses a separate
namespace and current pointer. Historical V1 artifacts remain immutable,
readable and are never reinterpreted as V2.

### 8. Runtime authority

Bounded Intraday-owned runtime composition, explicit Sponsor POST control,
inert GET status/product routes, V2 restoration and Browser projection are
authorized. Startup, restart and GET perform no WO-12 evaluation. WO-12 makes
no Provider call and does not automatically follow WO-11.

## Consequences

- The K5 policy hold no longer blocks Intraday WO-12 engineering closure.
- Swing KR-370 K1–K5 remains unchanged.
- Existing V1 code and artifacts remain historical compatibility assets.
- Future extension/chase methodology requires separate WO-15 authority.
- A zero eligible WO-11 population is a valid operational state.

## Validation Requirements

- V2 contains K1–K4 exactly and no K5/K6.
- LONG and SHORT mappings are symmetric at 4/3/2/1/0 satisfied.
- Unavailable K1–K4 fails closed; unavailable ATR/K5 telemetry has no effect.
- 5M evidence has no WO-12 consequence.
- Only NOW is WO-13 eligible.
- Swing remains a five-criterion implementation.
- V1 artifacts restore unchanged and V2 uses a distinct namespace.
- Browser GET is inert and no Provider, Entry, Risk or broker authority exists.

## Supersedes

- [ADR-0020](ADR-0020-INTRADAY-WO11-WO12-KR370-ANALYTICAL-PROMOTION-BOUNDARY.md),
  only for the Intraday five-criterion/K5 model and its commissioning hold.

## Superseded By

None.

## Related Documents

- [ADR-0011](ADR-0011-KR-370-ANALYTICAL-PROMOTION-AND-KR-380-ENTRY-OUTCOME-SEMANTICS.md)
- [ADR-0019](ADR-0019-INTRADAY-WO10-WO11-PRE-KR370-SEMANTIC-BOUNDARY.md)
- [Intraday WO-12 V2](../products/intraday/KRONOS-INTRADAY-WO-12-KR370-ANALYTICAL-PROMOTION-V2.md)
- [K5 Fact Foundation V1](../products/intraday/KRONOS-INTRADAY-WO12-K5-FACT-FOUNDATION-V1.md)

## Revision History

| Date | Revision | Author | Description | Approval status |
| --- | --- | --- | --- | --- |
| 2026-08-31 | 1.0 | Chief Architect / Sponsor, recorded by Codex | Move extension/chase to WO-15 and authorize four-criterion Intraday WO-12 V2 | APPROVED |
