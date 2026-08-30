# ADR-0020 — Intraday WO-11 to WO-12 KR-370 Analytical Promotion Boundary

## Metadata

- **ADR Number:** ADR-0020
- **Decision Identity:** `KRONOS-INTRADAY-WO11-WO12-KR370-BOUNDARY-V1`
- **Title:** Intraday WO-11 to WO-12 KR-370 Analytical Promotion Boundary
- **Status:** APPROVED
- **Date:** 2026-08-30
- **Decision Owner:** Chief Architect / KR-370 / DOMAIN-003-VALIDATION
- **Proposed By:** Sponsor / Intraday Engineering Architect
- **Reviewers:** Chief Architect / Sponsor
- **Approved By:** Chief Architect / Sponsor
- **Decision Scope:** Platform / Intraday Product / Interface
- **Authority Level:** Chief Architect
- **Repository Approval:** Approved for repository publication
- **Engineering Status:** Bounded WO-12 engineering authorized; runtime and production operation not authorized
- **Provider Authority:** NONE
- **Trading / Risk / Entry / Broker Authority:** NONE

## Context

[ADR-0011](ADR-0011-KR-370-ANALYTICAL-PROMOTION-AND-KR-380-ENTRY-OUTCOME-SEMANTICS.md)
defines the common current KR-370 analytical-promotion state family and keeps
it separate from KR-380 Entry Outcome semantics. [ADR-0019](ADR-0019-INTRADAY-WO10-WO11-PRE-KR370-SEMANTIC-BOUNDARY.md)
defines Intraday WO-10 and WO-11 as pre-KR-370 product stages and deliberately
leaves any downstream KR-370 crossing to a later separately governed,
versioned interface.

WO-10E, WO-10I and WO-10M are now implemented as independent Intraday
analytical-reconciliation policies. WO-11 validates, collates and publishes
their exact results with zero analytical discretion. A distinct WO-12 layer is
required to consume eligible WO-11 lineage and perform KR-370 analytical
promotion without treating any WO-10 or WO-11 state as a KR-370 state.

## Decision

### 1. Additive relationship to ADR-0019

ADR-0019 remains valid and is not modified or superseded.

- WO-10 remains Intraday analytical reconciliation.
- WO-11 remains validation, collation and publication.
- WO-12 is a distinct subsequent KR-370 analytical-promotion layer.
- A WO-10 state is not a KR-370 state.
- WO-11 downstream eligibility is not a KR-370 state.

This ADR supplies the separately governed interface and implementation gate
anticipated by ADR-0019. It does not remap `PROMOTION_READY`,
`WAIT_IMMEDIATE_CONFIRMATION`, or any other WO-10 state to a KR-370 state.

### 2. WO-12 authority and common state-family reuse

WO-12 is KR-370 Analytical Promotion owned by `KR-370` /
`DOMAIN-003-VALIDATION` with authority `ANALYTICAL_PROMOTION_ONLY`.

WO-12 reuses the approved common contract and state family:

- contract: `KRONOS-KR-370-ANALYTICAL-PROMOTION-V1`;
- owner: `KR-370`;
- state family: `KR370_ANALYTICAL_PROMOTION`;
- contract version: `1`;
- states: `BUY_NOW`, `SELL_NOW`, `BUY_READY`, `SELL_READY`,
  `POTENTIAL_BUY_SETUP`, `POTENTIAL_SELL_SETUP`, `NO_SETUP`.

No Intraday-specific duplicate of that state family is authorized.

### 3. Versioned WO-11 to WO-12 admission interface

WO-12 may consume only exact governed WO-11 publication and member lineage.
The versioned Intraday handoff must preserve and validate:

- WO-11 publication identity and integrity;
- WO-11 member identity and integrity;
- WO-10 result identity and integrity;
- WO-10 evidence lineage;
- Probables V2 run and result;
- canonical subject and market family;
- inherited direction;
- analysis boundary and phase;
- policy identities, versions, publications and checksums; and
- source identities and integrity digests.

No latest, current-pointer inference, mtime, symbol-only lookup, cross-run
substitution, current-market substitution or V1 fallback is permitted. Missing,
ambiguous, corrupt, stale, unsupported or mismatched binding fails closed.
Direction is inherited and cannot be reversed by WO-12.

### 4. Frozen Intraday V1 criteria

WO-12 evaluates exactly five criteria. Each uses the common criterion grammar
`SATISFIED`, `UNSATISFIED`, `UNAVAILABLE`.

| Criterion | Identity | Frozen authority |
| --- | --- | --- |
| K1 | `K1_15M_DIRECTIONAL_PROGRESSION` | Completed governed Intraday 15M structure progresses in the inherited direction through an exact existing Intraday evidence adapter. No LTP, 5M, Provider reacquisition or copied Swing 1H grammar. |
| K2 | `K2_15M_CPR_ACCEPTANCE` | LONG requires completed governed 15M close strictly above CPR upper/TC; SHORT requires completed governed 15M close strictly below CPR lower/BC. Equality is not acceptance. Wick, intrabar high/low, LTP and 5M are excluded. Missing close or CPR produces `UNAVAILABLE`. |
| K3 | `K3_15M_IMMEDIATE_PATH_CLEARANCE` | Structure-only determination of whether already-governed 15M evidence proves an immediate directional obstruction. A level ahead alone is not obstruction. If no existing deterministic structural predicate proves clear or blocked without a new threshold, the result is `UNAVAILABLE`. |
| K4 | `K4_15M_SETUP_QUALITY` | Bounded adaptation of existing governed Intraday Native and visual reconciliation evidence. It performs no new Review, Chart Analyst operation or subjective classification and does not copy Swing V3.1 literals by implication. |
| K5 | `K5_15M_NON_EXTENSION` | Factual 15M ATR-normalized directional distance from an exact governed 15M structural origin. The origin identity, completed close, ATR value/calculation identity, boundary, lineage and integrity are preserved. If no governed origin exists, the measurement and consequence are `UNAVAILABLE`. |

There is no K6, weighting, ranking, family vote, score or quota.

### 5. Timeframe ownership

- 1H is broader Intraday regime and Railway Track context reconciled upstream.
- 15M is the WO-12 KR-370 analytical-promotion frame.
- 5M has no WO-12 authority and remains reserved for WO-15 / KR-380 final
  Entry timing.

### 6. K3 prohibitions

K3 does not authorize Swing's `0.5 × 1H ATR`, `0.5 × 15M ATR`, any percentage
or ATR-distance threshold, R:R, entry-to-target room, Entry, Stop, Target or
trade geometry. WO-13 owns actual geometry.

### 7. K5 unresolved policy

`MATERIAL_EXTENSION_THRESHOLD = POLICY_UNRESOLVED`.

Engineering may calculate immutable factual extension telemetry, but until a
separately governed Intraday threshold is commissioned, K5 consequence is
`UNAVAILABLE`. Swing's `>2 × 1H ATR` policy is not copied and no `>2 × 15M ATR`
or other default is authorized. WO-12 engineering may proceed while full NOW
commissioning remains held.

### 8. Common five-criterion maturity model

Where all five mandatory criteria are available:

- five satisfied → `BUY_NOW` or `SELL_NOW` according to inherited direction;
- four satisfied → `BUY_READY` or `SELL_READY`;
- two or three satisfied → `POTENTIAL_BUY_SETUP` or
  `POTENTIAL_SELL_SETUP`;
- zero or one satisfied → `NO_SETUP`.

If any mandatory criterion is `UNAVAILABLE`, WO-12 fails closed to `NO_SETUP`
with an exact machine-readable unavailable reason. `UNAVAILABLE` remains
distinct from `UNSATISFIED`; WO-12 does not calculate a four-of-five result
when the fifth criterion is unavailable.

### 9. Universal Intraday hard gates

Only these universal V1 hard gates are authorized:

- `INVALID_EXACT_EVIDENCE_BINDING`;
- `MANDATORY_K_UNAVAILABLE`;
- `GOVERNING_15M_STRUCTURE_FAILED`;
- `AUTHORITATIVE_GOVERNED_DIRECTIONAL_CONFLICT`.

Swing 4H failure, weekly opposition, weekly unavailable and the Swing 1H
`MESSY_CHOPPY` literal are not Intraday gates.

### 10. WO-12 to WO-13 boundary

Only exact current WO-12 `BUY_NOW` or `SELL_NOW` may establish eligibility for
WO-13 / Step 31. `BUY_READY`, `SELL_READY`, either potential state and
`NO_SETUP` are ineligible. Eligibility is not geometry, Risk permission, Entry
timing or execution.

### 11. Authority exclusions

WO-12 owns no Entry, Entry Zone, Stop, Target, invalidation price, R:R,
quantity, position size, Risk approval, Sponsor PAPER/LIVE/IGNORE decision, 5M
final timing, Entry Outcome, broker mutation, fill or position authority.

- WO-13 owns Step-31 geometry.
- WO-14 owns DOMAIN-007 Risk.
- WO-15 owns KR-380 final Entry timing.

### 12. Current real population

The retained real WO-10/WO-11 population contains four
`CONTEXT_INCOMPLETE`, zero `PROMOTION_READY` and zero downstream-eligible
members. It supplies no real WO-12 candidate and must not be overridden or
recast for testing. This does not block bounded engineering with governed test
fixtures.

## Rationale

The explicit WO-12 layer preserves ADR-0019's non-equivalence while allowing
the platform-owned KR-370 semantics to be reused without duplicating product
state. Product-specific evidence adapters keep Intraday 15M authority separate
from Swing 1H methodology. The unresolved K5 threshold remains visible and
fail-closed rather than becoming a hidden default.

## Alternatives Considered

- **Map WO-10 `PROMOTION_READY` directly to KR-370:** rejected; ADR-0019
  prohibits semantic equivalence.
- **Create an Intraday-only KR-370 state family:** rejected; the approved common
  state-family contract is sufficient.
- **Copy Swing K1–K5 and hard gates:** rejected; Swing timeframe, numerical and
  visual policy is product-specific.
- **Choose a K5 threshold during implementation:** rejected; empirical policy
  remains unresolved.
- **Allow 5M into WO-12:** rejected; 5M belongs to WO-15 final Entry timing.

## Consequences

- ADR-0019 remains the authority for WO-10/WO-11 pre-KR-370 semantics.
- A new versioned Intraday interface may bind eligible WO-11 lineage to WO-12.
- Common KR-370 states and authority are reused without duplicating Swing
  artifacts or persistence.
- Bounded WO-12 engineering is authorized.
- Full NOW commissioning remains held while K5 is unavailable under unresolved
  threshold policy.
- No real WO-12 operation is authorized by this ADR publication.

## Risks

- Treating WO-11 eligibility as a KR-370 state would bypass WO-12.
- Reusing Swing thresholds would introduce unapproved Intraday methodology.
- Treating an unavailable K5 as merely unsatisfied would fabricate a maturity
  result.
- Allowing 5M evidence into WO-12 would absorb WO-15 timing authority.
- A current/latest lookup could bind evidence from the wrong run or phase.

All risks fail closed and require exact version-aware tests during engineering.

## Affected Products

- KRONOS Intraday V1.
- Shared KR-370 contract consumption only; Swing behavior and artifacts remain
  unchanged.

## Affected Interfaces

- New versioned Intraday WO-11 → WO-12 handoff.
- New Intraday WO-12 request, evidence, result, persistence and operation
  contracts in bounded engineering slices.
- Existing `KRONOS-KR-370-ANALYTICAL-PROMOTION-V1` remains unchanged.

## Implementation Implications

This ADR authorizes bounded engineering of:

- Intraday WO-12 contracts;
- the exact WO-11 → WO-12 adapter;
- K1–K5 evidence adapters;
- common KR-370 classification;
- the four authorized hard gates;
- the WO-13 eligibility boundary;
- immutable persistence and application composition; and
- runtime, control and Browser integration only through separately bounded
  engineering slices.

It does not authorize a real production WO-12 operation, a K5 threshold,
WO-13 implementation, Risk implementation, KR-380 implementation, runtime
restart or production evidence mutation.

## Validation Requirements

- ADR numbering and links are unique and valid.
- ADR-0019 remains unchanged and valid.
- The common KR-370 contract and state family are not duplicated.
- The handoff validates exact WO-11/WO-10/Probables lineage.
- Exactly five criteria and no K6 exist.
- No 5M, Swing numerical threshold or Swing-specific hard gate enters WO-12.
- K5 remains unavailable while its threshold is unresolved.
- Only NOW states establish WO-13 eligibility.
- No Entry, Trade, Risk, Sponsor-decision or broker authority is introduced.

## Validation Evidence

- [ADR-0011](ADR-0011-KR-370-ANALYTICAL-PROMOTION-AND-KR-380-ENTRY-OUTCOME-SEMANTICS.md)
- [ADR-0019](ADR-0019-INTRADAY-WO10-WO11-PRE-KR370-SEMANTIC-BOUNDARY.md)
- [KR-370 / KR-380 State-Family Contracts](../interfaces/KR-370-KR-380-STATE-FAMILY-CONTRACTS.md)
- [Intraday WO-12 KR-370 Analytical Promotion V1](../products/intraday/KRONOS-INTRADAY-WO-12-KR370-ANALYTICAL-PROMOTION-V1.md)

## Supersedes

None. This ADR is additive to ADR-0019.

## Superseded By

None.

## Related ADRs

- [ADR-0011](ADR-0011-KR-370-ANALYTICAL-PROMOTION-AND-KR-380-ENTRY-OUTCOME-SEMANTICS.md)
- [ADR-0019](ADR-0019-INTRADAY-WO10-WO11-PRE-KR370-SEMANTIC-BOUNDARY.md)

## Related Documents

- [KR-370 / KR-380 State-Family Contracts](../interfaces/KR-370-KR-380-STATE-FAMILY-CONTRACTS.md)
- [Intraday WO-10 E/I/M Frozen Architecture V1](../products/intraday/KRONOS-INTRADAY-WO-10-E-I-M-FROZEN-ARCHITECTURE-V1.md)
- [Intraday Contract and State Ownership Registry](../products/intraday/KRONOS-INTRADAY-CONTRACT-STATE-OWNERSHIP-REGISTRY.md)
- [Intraday Programme Roadmap](../products/intraday/KRONOS-INTRADAY-V1-PROGRAMME-ROADMAP.md)

## Revision History

| Date | Revision | Author | Description | Approval status |
| --- | --- | --- | --- | --- |
| 2026-08-30 | 1.0 | Chief Architect / Sponsor, recorded by Codex | Authorize the explicit Intraday WO-11 → WO-12 KR-370 boundary and bounded engineering | APPROVED |
