# ADR-0019 — Intraday WO-10/WO-11 Pre-KR-370 Semantic Boundary

## Metadata

- **ADR Number:** ADR-0019
- **Decision Identity:** `KRONOS-INTRADAY-WO10-WO11-PRE-KR370-SEMANTIC-BOUNDARY-V1`
- **Title:** Intraday WO-10/WO-11 Pre-KR-370 Semantic Boundary
- **Status:** APPROVED
- **Date:** 2026-08-30
- **Decision Owner:** KRONOS Intraday
- **Proposed By:** Sponsor / Intraday Engineering Architect
- **Reviewers:** Sponsor / Intraday Engineering Architect
- **Approved By:** Sponsor / Intraday Engineering Architect within the Intraday product boundary
- **Decision Scope:** Product / Interface clarification
- **Authority Level:** Intraday product architecture
- **Repository Approval:** Approved for repository publication
- **Engineering Status:** Governance only; implementation not started
- **Provider Authority:** NONE
- **Trading / Risk / Entry / Broker Authority:** NONE

## Context

ADR-0011 defines KR-370 analytical-promotion semantics and separates them from
KR-380 Entry Outcome semantics. Intraday subsequently froze a distinct WO-10
analytical-reconciliation state family for Equity, Index and MCX, followed by a
zero-discretion WO-11 consolidation/publication stage.

The names `PROMOTION_READY` and `WAIT_IMMEDIATE_CONFIRMATION` could otherwise
be misread as KR-370 `BUY_NOW`, `SELL_NOW`, `BUY_READY` or `SELL_READY`. The
repository also retains a historical WO-10 V1 implementation with a separate
two-state `PROMOTED` / `NOT_PROMOTED` result. Neither historical contract
establishes the meaning of the frozen WO-10 E/I/M successor architecture.

This ADR records the product-local boundary without rewriting or superseding
ADR-0011.

## Decision

> **WO-10/WO-11 ANALYTICAL PROMOTION IS A PRE-ENTRY PRODUCT STATE.**
> It does not instantiate KR-370 BUY/SELL Entry Outcome semantics.

### 1. Product-local state family

WO-10 owns a product-local analytical-reconciliation state family:

1. `CONTEXT_INCOMPLETE`
2. `INVALIDATED`
3. `WEAKENING`
4. `HELD_BY_CONTRADICTION`
5. `WAIT_SETUP_DEVELOPMENT`
6. `WAIT_IMMEDIATE_CONFIRMATION`
7. `PROMOTION_READY`

The states describe whether an exact Native Probable has survived the
Intraday analytical-reconciliation stage. They are not KR-370 or KR-380
states.

### 2. Precedence

The order above is authoritative. Evaluation applies it as follows:

- required governed evidence unavailable or invalid → `CONTEXT_INCOMPLETE`;
- governing structural thesis failed → `INVALIDATED`;
- thesis intact but materially deteriorating → `WEAKENING`;
- authoritative evidence materially conflicts → `HELD_BY_CONTRADICTION`;
- 15M setup structurally incomplete → `WAIT_SETUP_DEVELOPMENT`;
- analytical setup sufficiently formed but immediate progression absent →
  `WAIT_IMMEDIATE_CONFIRMATION`;
- required governed evidence materially coherent → `PROMOTION_READY`.

No score, vote, weight, rank or quota participates in this precedence.

### 3. KR-370 non-equivalence

The following equivalences are prohibited:

- `PROMOTION_READY == BUY_NOW`;
- `PROMOTION_READY == SELL_NOW`;
- `PROMOTION_READY == BUY_READY`;
- `PROMOTION_READY == SELL_READY`;
- `WAIT_IMMEDIATE_CONFIRMATION == BUY_READY`;
- `WAIT_IMMEDIATE_CONFIRMATION == SELL_READY`.

WO-10/WO-11 analytical promotion is a pre-entry product state. It does not
instantiate KR-370 `BUY_NOW`, `SELL_NOW`, `BUY_READY`, `SELL_READY`, potential
or `NO_SETUP` semantics and cannot establish Step-31 eligibility.

### 4. `PROMOTION_READY`

`PROMOTION_READY` means only that the candidate has satisfied the governed
WO-10 analytical-reconciliation requirements sufficiently to progress to the
next governed analytical stage. It has no Entry, Stop, Target, R:R, Trade
Construction, Risk, Sponsor-position, execution or broker authority.

### 5. `WAIT_IMMEDIATE_CONFIRMATION`

`WAIT_IMMEDIATE_CONFIRMATION` means that the setup remains analytically viable
and sufficiently developed but immediate progression is not established for
completion of WO-10. It is not an order, broker wait state, `BUY_READY` or
`SELL_READY`. WO-15 remains the precision Entry/Exit timing authority.

### 6. Direction

WO-10 inherits `LONG` or `SHORT` from the exact Native Probable. WO-10 and
WO-11 cannot reverse it. A contrary opportunity must originate through Native
Discovery and Probables.

### 7. WO-11

WO-10E, WO-10I and WO-10M decide independently. WO-11 only validates,
collates and publishes their exact results. It preserves family, canonical
subject, inherited direction, policy identity/version/publication/checksum,
result identity, state, reasons, analysis boundary, phase, evidence lineage
and integrity. WO-11 has no analytical discretion and performs no KR-370
remapping.

Only `PROMOTION_READY` may become eligible for a later separately governed
handoff. That eligibility is not itself KR-370, Trade Construction, Entry,
Risk, PAPER/LIVE or broker authority.

### 8. Unresolved policy

Frozen precedence does not authorize Engineering to invent a missing
consequence predicate. If an item is explicitly informational in a policy
version, it may be retained without consequence. If a required consequence
depends on unresolved policy, evaluation fails closed as `POLICY_UNRESOLVED`
and produces no fabricated seven-state result. Evidence unavailability and
policy unavailability remain different facts.

## Relationship to ADR-0011

ADR-0011 remains unchanged and approved. Its KR-370 state family belongs to a
later semantic layer. This ADR neither alters KR-370 nor authorizes an adapter
from WO-10/WO-11 to KR-370. Any future handoff requires a separately governed,
versioned interface that preserves the non-equivalence recorded here.

## Rationale

A separate product state family prevents analytical reconciliation from being
mistaken for Entry readiness or an Entry Outcome. It also lets Equity, Index
and MCX share one consequence vocabulary while retaining independent policy
publications and evidence requirements.

## Alternatives Considered

- **Map `PROMOTION_READY` to KR-370 `BUY_NOW`/`SELL_NOW`:** rejected; it would
  grant an unauthorized later-layer meaning.
- **Map `WAIT_IMMEDIATE_CONFIRMATION` to `BUY_READY`/`SELL_READY`:** rejected;
  it would conflate analytical progression with later readiness/timing.
- **Modify ADR-0011 in place:** rejected; approved ADR history is immutable.
- **Keep the boundary implicit:** rejected; current naming is susceptible to
  unsafe semantic routing.

## Consequences

- WO-10 successor contracts require their own owner, family and version.
- WO-11 remains a zero-discretion product publication.
- Historical WO-10 V1 artifacts remain immutable and readable but are not the
  successor E/I/M state family.
- No consumer may route by display text alone.
- A future KR-370 handoff is a separate architecture and implementation gate.

## Risks

- UI text could omit the owner/state-family identity and recreate ambiguity.
- A consumer could treat `PROMOTION_READY` as Step-31 eligibility.
- Engineering could turn an unresolved empirical item into a hidden default.

All three fail closed and require version-aware tests in later slices.

## Affected Products

- KRONOS Intraday only.
- Swing behavior and state are unchanged.

## Affected Interfaces

- Future Intraday WO-10 request/result contracts.
- Future WO-11 consolidation/publication contract.
- Future separately governed downstream handoff.

No current implementation contract is modified by this ADR.

## Implementation Implications

- Slice 1 may define the product-local state and binding contracts.
- Slice 1 must not implement the classifier.
- No automatic operation may occur on startup, restart, GET, Refresh,
  Discovery, Probables, Review completion, Answer import or timers.
- No production artifact is created by this ADR.

## Validation Requirements

- Every state is owner/family/version bound.
- Direction never flips.
- No state is accepted as a KR-370 or KR-380 state.
- `PROMOTION_READY` grants no downstream authority by itself.
- `WAIT_IMMEDIATE_CONFIRMATION` grants no Entry-timing authority.
- Unresolved required policy produces no fabricated result.
- V1 historical artifacts remain readable and unchanged.

## Validation Evidence

- [WO-10 E/I/M Frozen Architecture V1](../products/intraday/KRONOS-INTRADAY-WO-10-E-I-M-FROZEN-ARCHITECTURE-V1.md)
- [ADR-0011](ADR-0011-KR-370-ANALYTICAL-PROMOTION-AND-KR-380-ENTRY-OUTCOME-SEMANTICS.md)

## Supersedes

None.

## Superseded By

None.

## Related ADRs

- [ADR-0011](ADR-0011-KR-370-ANALYTICAL-PROMOTION-AND-KR-380-ENTRY-OUTCOME-SEMANTICS.md)

## Related Documents

- [Intraday Contract and State Ownership Registry](../products/intraday/KRONOS-INTRADAY-CONTRACT-STATE-OWNERSHIP-REGISTRY.md)
- [Intraday Deferred Decision Register](../products/intraday/KRONOS-INTRADAY-DEFERRED-DECISION-REGISTER.md)
- [Intraday Programme Roadmap](../products/intraday/KRONOS-INTRADAY-V1-PROGRAMME-ROADMAP.md)

## Revision History

| Date | Revision | Author | Description | Approval status |
| --- | --- | --- | --- | --- |
| 2026-08-30 | 1.0 | Sponsor / Intraday EA, recorded by Codex | Establish product-local WO-10/WO-11 pre-KR-370 boundary | APPROVED |
